"""Tests for the ACE reader and perturbation logic.

Uses ``data/1-H-1g-300.0`` (non-fissile, checked into the repo) as the
baseline fixture, and the fissile U-234/U-235/U-238 ACE files under
``examples/drafts/`` (large, not checked in) for nu-bar / fission-family
coverage. The fissile tests are skipped if those files aren't present.
"""

import os

import numpy as np
import pandas as pd
import pytest

from andalus.ace.core import (
    ACE,
    FISSION_MTS,
    NEUTRON_PRODUCING_MTS,
    NON_XS_MTS,
)
from andalus.ace.reader import PolynomialNu, TabulatedNu

H1_PATH = "data/1-H-1g-300.0"
U234_PATH = "examples/drafts/92234_0.03c"
U235_PATH = "examples/drafts/92235_0.03c"
U238_PATH = "examples/drafts/92238_0.03c"

requires_u235 = pytest.mark.skipif(not os.path.exists(U235_PATH), reason=f"fissile fixture not available: {U235_PATH}")
requires_u234 = pytest.mark.skipif(not os.path.exists(U234_PATH), reason=f"fissile fixture not available: {U234_PATH}")
requires_u238 = pytest.mark.skipif(not os.path.exists(U238_PATH), reason=f"fissile fixture not available: {U238_PATH}")


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

    @requires_u234
    def test_total_identity_u234(self):
        _assert_total_identity(ACE.read(U234_PATH))

    @requires_u235
    def test_total_identity_u235(self):
        _assert_total_identity(ACE.read(U235_PATH))

    @requires_u238
    def test_total_identity_u238(self):
        _assert_total_identity(ACE.read(U238_PATH))


class TestNuBar:
    @requires_u235
    def test_u235_has_prompt_and_total_nu(self):
        ace = ACE.read(U235_PATH)
        assert ace.nu is not None
        assert set(ace.nu) == {"prompt", "total"}
        for table in ace.nu.values():
            assert isinstance(table, (PolynomialNu, TabulatedNu))

    @requires_u234
    def test_u234_nu_present(self):
        ace = ACE.read(U234_PATH)
        assert ace.nu is not None

    def test_non_fissile_has_no_nu(self):
        ace = ACE.read(H1_PATH)
        assert ace.nu is None


class TestThresholdReactions:
    @requires_u235
    def test_n2n_has_offset_and_shorter_grid(self):
        ace = ACE.read(U235_PATH)
        rxn = ace.reactions[16]  # (n,2n), threshold reaction
        assert rxn.ie > 1
        assert len(rxn.xs) < len(ace.energy_grid)
        energy = rxn.energies
        assert len(energy) == len(rxn.xs)
        np.testing.assert_array_equal(energy, ace.energy_grid[rxn.ie - 1 : rxn.ie - 1 + len(rxn.xs)])

    @requires_u235
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

    @requires_u235
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

    @requires_u235
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
