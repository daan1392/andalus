"""Tests for the ASCII ACE writer."""

import os

import numpy as np
import pandas as pd
import pytest

from andalus.ace.core import ACE

H1_PATH = "data/1-H-1g-300.0"
U235_PATH = "data/92235.03c"

_EV_PER_MEV = 1.0e6

requires_u235 = pytest.mark.skipif(not os.path.exists(U235_PATH), reason=f"fissile fixture not available: {U235_PATH}")


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


class TestRoundTrip:
    def test_unperturbed_h1_byte_identical(self, tmp_path):
        ace = ACE.read(H1_PATH)
        out = tmp_path / "h1.ace"
        ace.write(str(out))
        assert _read_bytes(str(out)) == _read_bytes(H1_PATH)

    @requires_u235
    def test_unperturbed_u235_byte_identical(self, tmp_path):
        ace = ACE.read(U235_PATH)
        out = tmp_path / "u235.ace"
        ace.write(str(out))
        assert _read_bytes(str(out)) == _read_bytes(U235_PATH)

    def test_perturbed_h1_reread_matches_in_memory(self, tmp_path):
        ace = ACE.read(H1_PATH)
        energy = ace.reactions[102].energies
        e_lo, e_hi = float(energy[10]) * _EV_PER_MEV, float(energy[50]) * _EV_PER_MEV
        adjustment = pd.Series(
            [0.1],
            index=pd.MultiIndex.from_tuples([(102, e_lo, e_hi)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        ace.perturb(adjustment)

        out = tmp_path / "h1_perturbed.ace"
        ace.write(str(out))
        reread = ACE.read(str(out))

        np.testing.assert_allclose(reread.reactions[102].xs, ace.reactions[102].xs, rtol=1e-10)
        np.testing.assert_allclose(reread.total_xs, ace.total_xs, rtol=1e-10)
        np.testing.assert_allclose(reread.absorption_xs, ace.absorption_xs, rtol=1e-10)
        np.testing.assert_array_equal(reread.energy_grid, ace.energy_grid)

    @requires_u235
    def test_perturbed_fission_u235_reread_matches_in_memory(self, tmp_path):
        ace = ACE.read(U235_PATH)
        energy = ace.reactions[18].energies
        adjustment = pd.Series(
            [0.05],
            index=pd.MultiIndex.from_tuples(
                [(18, float(energy[0]) * _EV_PER_MEV, float(energy[-1]) * _EV_PER_MEV)],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb(adjustment)

        out = tmp_path / "u235_perturbed.ace"
        ace.write(str(out))
        reread = ACE.read(str(out))

        np.testing.assert_allclose(reread.reactions[18].xs, ace.reactions[18].xs, rtol=1e-10)
        np.testing.assert_allclose(reread.total_xs, ace.total_xs, rtol=1e-10)
        np.testing.assert_allclose(reread.absorption_xs, ace.absorption_xs, rtol=1e-10)
        assert reread.nu is not None
        assert set(reread.nu) == {"prompt", "total"}

    @requires_u235
    def test_perturbed_chi_u235_reread_matches_in_memory(self, tmp_path):
        ace = ACE.read(U235_PATH)
        dist = ace.chi[18]
        e_out = dist.tables[0].energy_out
        e_out_lo = float(e_out[len(e_out) // 4]) * _EV_PER_MEV
        e_out_hi = float(e_out[3 * len(e_out) // 4]) * _EV_PER_MEV

        # MT=35018: ANDALUS's MF*1000+MT convention for prompt fission chi (MT=18).
        adjustment = pd.Series(
            [0.2],
            index=pd.MultiIndex.from_tuples([(35018, e_out_lo, e_out_hi)], names=["MT", "E_min_eV", "E_max_eV"]),
        )
        ace.perturb_chi(adjustment)

        out = tmp_path / "u235_chi_perturbed.ace"
        ace.write(str(out))
        reread = ACE.read(str(out))

        reread_dist = reread.chi[18]
        for table, expected_table in zip(reread_dist.tables, dist.tables, strict=True):
            np.testing.assert_allclose(table.pdf, expected_table.pdf, rtol=1e-10)
            np.testing.assert_allclose(table.cdf, expected_table.cdf, rtol=1e-10)

        original = ACE.read(U235_PATH)
        for table, original_table in zip(reread_dist.tables, original.chi[18].tables, strict=True):
            assert not np.allclose(table.pdf, original_table.pdf)

    @requires_u235
    def test_perturbed_multi_reaction_u235_reread_matches_in_memory(self, tmp_path):
        """Round-trip several simultaneous perturbations on U-235: MT=4 (aggregate
        inelastic, redistributed onto its present MT=51..91 constituents), MT=18
        (fission), MT=102 (capture), total nu-bar (MT=452), and the prompt
        fission neutron spectrum (chi, MT=35018).
        """
        ace = ACE.read(U235_PATH)
        levels = [mt for mt in range(51, 92) if mt in ace.reactions]

        fission_energy = ace.reactions[18].energies
        capture_energy = ace.reactions[102].energies
        xs_adjustment = pd.Series(
            [0.1, 0.05, -0.03],
            index=pd.MultiIndex.from_tuples(
                [
                    (4, float(ace.energy_grid[0]) * _EV_PER_MEV, float(ace.energy_grid[-1]) * _EV_PER_MEV),
                    (18, float(fission_energy[0]) * _EV_PER_MEV, float(fission_energy[-1]) * _EV_PER_MEV),
                    (102, float(capture_energy[0]) * _EV_PER_MEV, float(capture_energy[-1]) * _EV_PER_MEV),
                ],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb(xs_adjustment)

        nu_energy = ace.nu["total"].energy
        nu_adjustment = pd.Series(
            [0.08],
            index=pd.MultiIndex.from_tuples(
                [(452, float(nu_energy[0]) * _EV_PER_MEV, float(nu_energy[-1]) * _EV_PER_MEV)],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb_nu(nu_adjustment)

        chi_dist = ace.chi[18]
        chi_e_out = chi_dist.tables[0].energy_out
        chi_e_out_lo = float(chi_e_out[len(chi_e_out) // 4]) * _EV_PER_MEV
        chi_e_out_hi = float(chi_e_out[3 * len(chi_e_out) // 4]) * _EV_PER_MEV
        chi_adjustment = pd.Series(
            [0.2],
            index=pd.MultiIndex.from_tuples(
                [(35018, chi_e_out_lo, chi_e_out_hi)], names=["MT", "E_min_eV", "E_max_eV"]
            ),
        )
        ace.perturb_chi(chi_adjustment)

        out = tmp_path / "u235_multi_perturbed.ace"
        ace.write(str(out))
        reread = ACE.read(str(out))

        np.testing.assert_allclose(reread.reactions[4].xs, ace.reactions[4].xs, rtol=1e-10)
        for mt in levels:
            np.testing.assert_allclose(reread.reactions[mt].xs, ace.reactions[mt].xs, rtol=1e-10)
        np.testing.assert_allclose(reread.reactions[18].xs, ace.reactions[18].xs, rtol=1e-10)
        np.testing.assert_allclose(reread.reactions[102].xs, ace.reactions[102].xs, rtol=1e-10)
        np.testing.assert_allclose(reread.total_xs, ace.total_xs, rtol=1e-10)
        np.testing.assert_allclose(reread.absorption_xs, ace.absorption_xs, rtol=1e-10)
        np.testing.assert_allclose(reread.nu["total"].values, ace.nu["total"].values, rtol=1e-10)
        np.testing.assert_allclose(reread.nu["prompt"].values, ace.nu["prompt"].values, rtol=1e-10)
        for table, expected_table in zip(reread.chi[18].tables, chi_dist.tables, strict=True):
            np.testing.assert_allclose(table.pdf, expected_table.pdf, rtol=1e-10)
            np.testing.assert_allclose(table.cdf, expected_table.cdf, rtol=1e-10)

        # sanity: perturbations actually changed something (not accidental no-ops)
        original = ACE.read(U235_PATH)
        assert not np.allclose(reread.reactions[4].xs, original.reactions[4].xs)
        for mt in levels:
            assert not np.allclose(reread.reactions[mt].xs, original.reactions[mt].xs)
        assert not np.allclose(reread.reactions[18].xs, original.reactions[18].xs)
        assert not np.allclose(reread.reactions[102].xs, original.reactions[102].xs)
        assert not np.allclose(reread.nu["total"].values, original.nu["total"].values)
        # prompt nu-bar was not targeted, so it must be untouched
        np.testing.assert_allclose(reread.nu["prompt"].values, original.nu["prompt"].values)
        for table, original_table in zip(reread.chi[18].tables, original.chi[18].tables, strict=True):
            assert not np.allclose(table.pdf, original_table.pdf)
