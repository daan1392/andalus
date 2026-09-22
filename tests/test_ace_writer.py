"""Tests for the ASCII ACE writer."""

import os

import numpy as np
import pandas as pd
import pytest

from andalus.ace.core import ACE

H1_PATH = "data/1-H-1g-300.0"
U235_PATH = "examples/drafts/92235_0.03c"

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
        e_lo, e_hi = float(energy[10]), float(energy[50])
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
                [(18, float(energy[0]), float(energy[-1]))],
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
    def test_perturbed_multi_reaction_u235_reread_matches_in_memory(self, tmp_path):
        """Round-trip several simultaneous perturbations on U-235: MT=18 (fission),
        MT=102 (capture), and total nu-bar (MT=452). MT=4 (aggregate inelastic) is
        confirmed to be rejected rather than silently double-counted against its
        MT=51..91 sublevels.
        """
        ace = ACE.read(U235_PATH)

        with pytest.raises(ValueError, match="aggregate"):
            ace.perturb(
                pd.Series(
                    [0.1],
                    index=pd.MultiIndex.from_tuples([(4, 1.0, 2.0)], names=["MT", "E_min_eV", "E_max_eV"]),
                )
            )

        fission_energy = ace.reactions[18].energies
        capture_energy = ace.reactions[102].energies
        xs_adjustment = pd.Series(
            [0.05, -0.03],
            index=pd.MultiIndex.from_tuples(
                [
                    (18, float(fission_energy[0]), float(fission_energy[-1])),
                    (102, float(capture_energy[0]), float(capture_energy[-1])),
                ],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb(xs_adjustment)

        nu_energy = ace.nu["total"].energy
        nu_adjustment = pd.Series(
            [0.08],
            index=pd.MultiIndex.from_tuples(
                [(452, float(nu_energy[0]), float(nu_energy[-1]))],
                names=["MT", "E_min_eV", "E_max_eV"],
            ),
        )
        ace.perturb_nu(nu_adjustment)

        out = tmp_path / "u235_multi_perturbed.ace"
        ace.write(str(out))
        reread = ACE.read(str(out))

        np.testing.assert_allclose(reread.reactions[18].xs, ace.reactions[18].xs, rtol=1e-10)
        np.testing.assert_allclose(reread.reactions[102].xs, ace.reactions[102].xs, rtol=1e-10)
        np.testing.assert_allclose(reread.total_xs, ace.total_xs, rtol=1e-10)
        np.testing.assert_allclose(reread.absorption_xs, ace.absorption_xs, rtol=1e-10)
        np.testing.assert_allclose(reread.nu["total"].values, ace.nu["total"].values, rtol=1e-10)
        np.testing.assert_allclose(reread.nu["prompt"].values, ace.nu["prompt"].values, rtol=1e-10)

        # sanity: perturbations actually changed something (not accidental no-ops)
        original = ACE.read(U235_PATH)
        assert not np.allclose(reread.reactions[18].xs, original.reactions[18].xs)
        assert not np.allclose(reread.reactions[102].xs, original.reactions[102].xs)
        assert not np.allclose(reread.nu["total"].values, original.nu["total"].values)
        # prompt nu-bar was not targeted, so it must be untouched
        np.testing.assert_allclose(reread.nu["prompt"].values, original.nu["prompt"].values)
