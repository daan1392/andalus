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
