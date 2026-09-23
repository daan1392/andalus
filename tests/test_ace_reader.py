"""Tests for the ACE reader and perturbation logic.

Uses ``data/1-H-1g-300.0`` (non-fissile) and ``data/92235.03c`` (fissile),
both checked into the repo, for nu-bar / fission-family coverage. U-234 and
U-238 ACE files aren't checked in, so those tests are skipped if the files
aren't present locally.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from andalus.ace.core import (
    ACE,
    FISSION_MTS,
    NEUTRON_PRODUCING_MTS,
    NON_XS_MTS,
)
from andalus.ace.reader import EnergyDistribution, PolynomialNu, TabulatedNu, UnsupportedEnergyLaw

H1_PATH = "data/1-H-1g-300.0"
U235_PATH = "data/92235.03c"


def _assert_total_identity(ace: ACE, rtol: float = 1e-6) -> None:
    """total_xs == elastic + absorption + (fission + neutron-producing reactions).

    MT=4 is skipped: it's an aggregate equal to the sum of the individually
    tabulated MT=51..91 inelastic levels, so including both would double-count.
    """
    total = ace.total_xs
    elastic = ace.reactions[2].xs
    absorbing = np.zeros(len(total))
    producing = np.zeros(len(total))
    for mt, rxn in ace.reactions.items():
        if mt in (2, 4) or mt in NON_XS_MTS:
            continue
        start = rxn.ie - 1
        stop = start + len(rxn.xs)
        if mt in FISSION_MTS or mt in NEUTRON_PRODUCING_MTS:
            producing[start:stop] += rxn.xs
        else:
            absorbing[start:stop] += rxn.xs

    np.testing.assert_allclose(absorbing, ace.absorption_xs, rtol=rtol)
    np.testing.assert_allclose(total, elastic + absorbing + producing, rtol=rtol)


class TestHeader:
    def test_zaid_mass_temperature(self):
        ace = ACE.read(H1_PATH)
        assert ace.header.zaid == 1001
        assert ace.header.mass == pytest.approx(0.999167)
        assert ace.header.temperature == pytest.approx(2.5852e-08)

    def test_mat_parsed_from_title(self):
        ace = ACE.read(H1_PATH)
        assert ace.header.mat > 0


class TestDirectoryConsistency:
    def test_nxs_nes_matches_energy_grid_length(self):
        ace = ACE.read(H1_PATH)
        assert ace.nxs[2] == len(ace.energy_grid)

    def test_esz_arrays_same_length_as_energy_grid(self):
        ace = ACE.read(H1_PATH)
        nes = len(ace.energy_grid)
        assert len(ace.total_xs) == nes
        assert len(ace.absorption_xs) == nes
        assert len(ace.reactions[2].xs) == nes  # elastic

    def test_known_reactions_present(self):
        ace = ACE.read(H1_PATH)
        for mt in (2, 102, 204, 444):
            assert mt in ace.reactions

    def test_full_span_reaction_has_no_threshold_offset(self):
        ace = ACE.read(H1_PATH)
        rxn = ace.reactions[102]
        assert rxn.ie == 1
        assert len(rxn.xs) == len(ace.energy_grid)


class TestPhysicalConsistency:
    def test_total_equals_elastic_plus_absorption_h1(self):
        _assert_total_identity(ACE.read(H1_PATH))

    def test_total_identity_u235(self):
        _assert_total_identity(ACE.read(U235_PATH))


class TestNuBar:
    def test_u235_has_prompt_and_total_nu(self):
        ace = ACE.read(U235_PATH)
        assert ace.nu is not None
        assert set(ace.nu) == {"prompt", "total"}
        for table in ace.nu.values():
            assert isinstance(table, (PolynomialNu, TabulatedNu))

    def test_non_fissile_has_no_nu(self):
        ace = ACE.read(H1_PATH)
        assert ace.nu is None


class TestThresholdReactions:
    def test_n2n_has_offset_and_shorter_grid(self):
        ace = ACE.read(U235_PATH)
        rxn = ace.reactions[16]  # (n,2n), threshold reaction
        assert rxn.ie > 1
        assert len(rxn.xs) < len(ace.energy_grid)
        energy = rxn.energies
        assert len(energy) == len(rxn.xs)
        np.testing.assert_array_equal(energy, ace.energy_grid[rxn.ie - 1 : rxn.ie - 1 + len(rxn.xs)])

    def test_fission_present(self):
        ace = ACE.read(U235_PATH)
        assert 18 in ace.reactions


class TestPerturb:
    def test_bin_edge_convention_and_uncovered_energies(self):
        ace = ACE.read(H1_PATH)
        energy = ace.reactions[102].energies
        e_lo, e_hi = float(energy[10]), float(energy[50])
        original = ace.reactions[102].xs.copy()

        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(102, e_lo, e_hi)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        ace.perturb(adjustment)

        in_bin = (energy > e_lo) & (energy <= e_hi)
        np.testing.assert_allclose(ace.reactions[102].xs[in_bin], original[in_bin] * 1.1)
        np.testing.assert_allclose(ace.reactions[102].xs[~in_bin], original[~in_bin])
        # the lower edge itself belongs to the bin below, not this one
        assert energy[10] == e_lo
        assert not in_bin[10]

    def test_unknown_mt_raises_keyerror(self):
        ace = ACE.read(H1_PATH)
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(999, 1.0, 2.0)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        with pytest.raises(KeyError):
            ace.perturb(adjustment)

    def test_non_xs_mt_raises_valueerror(self):
        ace = ACE.read(H1_PATH)
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(444, 1.0, 2.0)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        with pytest.raises(ValueError):
            ace.perturb(adjustment)

    def test_total_and_absorption_stay_consistent_after_capture_perturbation(self):
        ace = ACE.read(H1_PATH)
        energy = ace.reactions[102].energies
        adjustment = pd.Series(
            [0.2],
            index=pd.MultiIndex.from_tuples(
                [(102, float(energy[0]), float(energy[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb(adjustment)
        _assert_total_identity(ace)

    def test_total_and_absorption_stay_consistent_after_fission_perturbation(self):
        ace = ACE.read(U235_PATH)
        energy = ace.reactions[18].energies
        adjustment = pd.Series(
            [0.05],
            index=pd.MultiIndex.from_tuples(
                [(18, float(energy[0]), float(energy[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb(adjustment)
        _assert_total_identity(ace)

    def test_fission_perturbation_does_not_change_absorption(self):
        ace = ACE.read(U235_PATH)
        absorption_before = ace.absorption_xs.copy()
        energy = ace.reactions[18].energies
        adjustment = pd.Series(
            [0.05],
            index=pd.MultiIndex.from_tuples(
                [(18, float(energy[0]), float(energy[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb(adjustment)
        np.testing.assert_allclose(ace.absorption_xs, absorption_before)

    def test_aggregate_mt4_redistributes_to_constituents(self):
        ace = ACE.read(U235_PATH)
        levels = [mt for mt in range(51, 92) if mt in ace.reactions]
        originals = {mt: ace.reactions[mt].xs.copy() for mt in levels}

        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples(
                [(4, float(ace.energy_grid[0]), float(ace.energy_grid[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb(adjustment)

        for mt in levels:
            np.testing.assert_allclose(ace.reactions[mt].xs, originals[mt] * 1.1, rtol=1e-10)

    def test_aggregate_mt4_resynced_to_sum_of_constituents(self):
        ace = ACE.read(U235_PATH)
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples(
                [(4, float(ace.energy_grid[0]), float(ace.energy_grid[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb(adjustment)

        aggregate = ace.reactions[4]
        agg_start = aggregate.ie - 1
        expected = np.zeros(len(aggregate.xs))
        for mt in range(51, 92):
            if mt not in ace.reactions:
                continue
            rxn = ace.reactions[mt]
            start = rxn.ie - 1
            stop = start + len(rxn.xs)
            expected[start - agg_start : stop - agg_start] += rxn.xs

        np.testing.assert_allclose(aggregate.xs, expected, rtol=1e-10)

    def test_aggregate_mt4_keeps_totals_consistent(self):
        ace = ACE.read(U235_PATH)
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples(
                [(4, float(ace.energy_grid[0]), float(ace.energy_grid[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb(adjustment)
        _assert_total_identity(ace)

    def test_aggregate_mt_with_no_present_constituents_raises(self):
        ace = ACE.read(U235_PATH)
        # Simulate a file where MT=4 is present but none of its MT=51..91
        # constituents are (real ACE files always carry both together, but
        # the guard must still hold if that ever isn't the case).
        for mt in list(ace.reactions):
            if 51 <= mt <= 91:
                del ace.reactions[mt]

        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples(
                [(4, float(ace.energy_grid[0]), float(ace.energy_grid[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        with pytest.raises(ValueError, match="no known constituent"):
            ace.perturb(adjustment)

    def test_unmapped_aggregate_mt_raises_valueerror(self):
        # MT=1/3/27/101 are aggregate MTs with no entry in AGGREGATE_MEMBERS
        # (nothing to redistribute onto), regardless of whether they're
        # themselves present as a Reaction entry.
        ace = ACE.read(H1_PATH)
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(101, 1.0, 2.0)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        with pytest.raises(ValueError, match="no known constituent"):
            ace.perturb(adjustment)

    def test_aggregate_mt4_absent_still_redistributes_to_constituents(self):
        # Some ACE files carry MT=51..91 without a separate MT=4 aggregate
        # array (e.g. U-234). The adjustment should still reach the
        # constituents even though there's nothing to resync afterward.
        ace = ACE.read(U235_PATH)
        del ace.reactions[4]
        levels = [mt for mt in range(51, 92) if mt in ace.reactions]
        originals = {mt: ace.reactions[mt].xs.copy() for mt in levels}

        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples(
                [(4, float(ace.energy_grid[0]), float(ace.energy_grid[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        with pytest.warns(UserWarning, match="no aggregate array to resync"):
            ace.perturb(adjustment)

        for mt in levels:
            np.testing.assert_allclose(ace.reactions[mt].xs, originals[mt] * 1.1, rtol=1e-10)
        assert 4 not in ace.reactions

    def test_mt18_absent_redistributes_to_multichance_fission_constituents(self):
        # No checked-in fixture has multi-chance fission data (MT=19/20/21/38
        # without a separate MT=18), e.g. U-234, so this simulates that shape
        # on top of U-235's real MT=18 table.
        from andalus.ace.reader import Reaction

        ace = ACE.read(U235_PATH)
        fission = ace.reactions.pop(18)
        ace.reactions[19] = Reaction(mt=19, ie=fission.ie, xs=fission.xs.copy(), energies=fission.energies)
        ace.reactions[20] = Reaction(mt=20, ie=fission.ie, xs=fission.xs.copy() * 0.5, energies=fission.energies)
        original_19 = ace.reactions[19].xs.copy()
        original_20 = ace.reactions[20].xs.copy()

        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples(
                [(18, 0.0, float(fission.energies[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        with pytest.warns(UserWarning, match="no aggregate array to resync"):
            ace.perturb(adjustment)

        np.testing.assert_allclose(ace.reactions[19].xs, original_19 * 1.1, rtol=1e-10)
        np.testing.assert_allclose(ace.reactions[20].xs, original_20 * 1.1, rtol=1e-10)
        assert 18 not in ace.reactions

    def test_mt18_present_is_perturbed_directly_not_as_aggregate(self):
        ace = ACE.read(U235_PATH)
        fission = ace.reactions[18]
        original = fission.xs.copy()

        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples(
                [(18, 0.0, float(fission.energies[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            ace.perturb(adjustment)  # must not warn: MT=18 is present, perturbed as a leaf reaction

        np.testing.assert_allclose(ace.reactions[18].xs, original * 1.1, rtol=1e-10)


class TestChi:
    def test_u235_mt18_parsed_as_law4(self):
        ace = ACE.read(U235_PATH)
        assert 18 in ace.chi
        dist = ace.chi[18]
        assert isinstance(dist, EnergyDistribution)
        assert len(dist.energy_in) == len(dist.tables)

    def test_non_fissile_has_no_law4_chi(self):
        ace = ACE.read(H1_PATH)
        assert all(not isinstance(dist, EnergyDistribution) for dist in ace.chi.values())

    def test_all_incident_energy_tables_normalized_and_monotonic(self):
        ace = ACE.read(U235_PATH)
        dist = ace.chi[18]
        for table in dist.tables:
            integral = np.trapz(table.pdf, table.energy_out)
            assert integral == pytest.approx(1.0, abs=1e-4)
            assert table.cdf[0] == pytest.approx(0.0, abs=1e-6)
            assert table.cdf[-1] == pytest.approx(1.0, abs=1e-6)
            assert np.all(np.diff(table.cdf) >= -1e-12)
            assert np.all((table.cdf >= 0) & (table.cdf <= 1.0 + 1e-9))


class TestPerturbNu:
    def test_single_nu_table_accepts_mt452(self):
        ace = ACE.read(H1_PATH)
        table = TabulatedNu(energy=np.array([1.0, 2.0]), values=np.array([2.0, 3.0]))
        ace.nu = {"nu": table}

        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(452, 0.0, 2.0)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        ace.perturb_nu(adjustment)

        np.testing.assert_allclose(table.values, np.array([2.2, 3.3]))

    def test_bin_edge_convention_and_uncovered_energies(self):
        ace = ACE.read(U235_PATH)
        table = ace.nu["total"]
        e_lo, e_hi = float(table.energy[10]), float(table.energy[50])
        original = table.values.copy()

        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(452, e_lo, e_hi)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        ace.perturb_nu(adjustment)

        in_bin = (table.energy > e_lo) & (table.energy <= e_hi)
        np.testing.assert_allclose(table.values[in_bin], original[in_bin] * 1.1)
        np.testing.assert_allclose(table.values[~in_bin], original[~in_bin])

    def test_perturbing_total_does_not_change_prompt(self):
        ace = ACE.read(U235_PATH)
        prompt_before = ace.nu["prompt"].values.copy()
        table = ace.nu["total"]
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples(
                [(452, float(table.energy[0]), float(table.energy[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb_nu(adjustment)
        np.testing.assert_allclose(ace.nu["prompt"].values, prompt_before)

    def test_unsupported_mt_raises_keyerror(self):
        ace = ACE.read(U235_PATH)
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(455, 1.0, 2.0)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        with pytest.raises(KeyError):
            ace.perturb_nu(adjustment)

    def test_missing_nu_table_raises_keyerror(self):
        ace = ACE.read(H1_PATH)  # non-fissile, no nu block at all
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(452, 1.0, 2.0)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        with pytest.raises(KeyError):
            ace.perturb_nu(adjustment)


class TestPerturbChi:
    def test_all_incident_energy_tables_shifted_identically(self):
        ace = ACE.read(U235_PATH)
        dist = ace.chi[18]
        originals = [t.pdf.copy() for t in dist.tables]

        e_out = dist.tables[0].energy_out
        e_out_lo, e_out_hi = float(e_out[len(e_out) // 4]), float(e_out[3 * len(e_out) // 4])

        # MT=35018: ANDALUS's MF*1000+MT convention for prompt fission chi (MT=18).
        adjustment = pd.Series(
            [0.2],
            index=pd.MultiIndex.from_tuples([(35018, e_out_lo, e_out_hi)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        ace.perturb_chi(adjustment)

        in_bin = (e_out > e_out_lo) & (e_out <= e_out_hi)
        for table, original in zip(dist.tables, originals, strict=True):
            expected = original.copy()
            expected[in_bin] *= 1.2
            expected /= np.trapz(expected, e_out)  # perturb_chi renormalizes to unit area afterward
            np.testing.assert_allclose(table.pdf, expected, rtol=1e-6)

    def test_pdf_stays_normalized_and_cdf_monotonic(self):
        ace = ACE.read(U235_PATH)
        dist = ace.chi[18]

        adjustment = pd.Series(
            [0.5],
            index=pd.MultiIndex.from_tuples([(35018, 0.0, 30.0)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        ace.perturb_chi(adjustment)

        for table in dist.tables:
            assert np.trapz(table.pdf, table.energy_out) == pytest.approx(1.0, abs=1e-6)
            assert table.cdf[0] == pytest.approx(0.0, abs=1e-9)
            assert table.cdf[-1] == pytest.approx(1.0, abs=1e-6)
            assert np.all(np.diff(table.cdf) >= -1e-12)

    def test_unknown_mt_raises_keyerror(self):
        ace = ACE.read(U235_PATH)
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(35999, 0.0, 1.0)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        with pytest.raises(KeyError):
            ace.perturb_chi(adjustment)

    def test_non_law4_raises_not_implemented(self):
        ace = ACE.read(H1_PATH)
        mt = next(mt for mt, dist in ace.chi.items() if isinstance(dist, UnsupportedEnergyLaw))
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(35000 + mt, 0.0, 1.0)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        with pytest.raises(NotImplementedError):
            ace.perturb_chi(adjustment)
