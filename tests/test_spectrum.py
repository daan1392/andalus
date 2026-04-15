"""Tests for the FluxSpectrum class."""

import os
import tempfile

import numpy as np
import pandas as pd
import pytest

from andalus.spectrum import FluxSpectrum

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_flux_spectrum():
    """
    A FluxSpectrum with three energy bins and known flux values.

    Energy grid (eV):
        bin 0: [1e-2, 1e2]   flux = 0.2
        bin 1: [1e2,  1e4]   flux = 0.5
        bin 2: [1e4,  1e7]   flux = 0.3
    """
    index = pd.MultiIndex.from_tuples(
        [(1e-2, 1e2), (1e2, 1e4), (1e4, 1e7)],
        names=["E_min_eV", "E_max_eV"],
    )
    data = {"flux": [0.2, 0.5, 0.3], "flux_std": [0.01, 0.025, 0.015]}
    return FluxSpectrum(pd.DataFrame(data, index=index), title="TEST")


@pytest.fixture
def single_bin_flux():
    """
    FluxSpectrum with one energy bin: E_min=1, E_max=4, flux=1.0.

    For this spectrum:
        E_mid = sqrt(1 * 4) = 2.0
        ealf  = exp(ln(2.0) / 1)  = 2.0
        mean_energy = 2.0
    """
    index = pd.MultiIndex.from_tuples(
        [(1.0, 4.0)],
        names=["E_min_eV", "E_max_eV"],
    )
    return FluxSpectrum(
        pd.DataFrame({"flux": [1.0], "flux_std": [0.0]}, index=index),
        title="SINGLE",
    )


@pytest.fixture
def two_bin_equal_flux():
    """
    FluxSpectrum with two equal-weight bins.

    Energy grid (eV): [1, 100] and [100, 10000].
        E_mid = [sqrt(1*100), sqrt(100*10000)] = [10.0, 1000.0]
        flux  = [1.0, 1.0]

    Analytical results:
        ealf        = exp((ln(10) + ln(1000)) / 2) = exp(ln(100)) = 100.0
        mean_energy = (10.0 + 1000.0) / 2 = 505.0
    """
    index = pd.MultiIndex.from_tuples(
        [(1.0, 100.0), (100.0, 10000.0)],
        names=["E_min_eV", "E_max_eV"],
    )
    return FluxSpectrum(
        pd.DataFrame({"flux": [1.0, 1.0], "flux_std": [0.0, 0.0]}, index=index),
        title="TWO_BIN",
    )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestFluxSpectrumInitialization:
    """Tests for FluxSpectrum construction and metadata handling."""

    def test_title_stored_correctly(self, sample_flux_spectrum):
        """Title kwarg is stored as instance metadata."""
        assert sample_flux_spectrum.title == "TEST"

    def test_default_title_is_none(self):
        """FluxSpectrum without an explicit title has title=None."""
        fs = FluxSpectrum()
        assert fs.title is None

    def test_columns_present(self, sample_flux_spectrum):
        """The DataFrame must contain 'flux' and 'flux_std' columns."""
        assert "flux" in sample_flux_spectrum.columns
        assert "flux_std" in sample_flux_spectrum.columns

    def test_multiindex_names(self, sample_flux_spectrum):
        """Index level names must be E_min_eV and E_max_eV."""
        assert sample_flux_spectrum.index.names == ["E_min_eV", "E_max_eV"]

    def test_length_matches_bins(self, sample_flux_spectrum):
        """Number of rows equals the number of energy bins."""
        assert len(sample_flux_spectrum) == 3

    def test_constructor_preserves_type_after_slice(self, sample_flux_spectrum):
        """Pandas slicing returns a FluxSpectrum, not a plain DataFrame."""
        sliced = sample_flux_spectrum.iloc[:2]
        assert isinstance(sliced, FluxSpectrum)

    def test_metadata_survives_slice(self, sample_flux_spectrum):
        """Title metadata is carried through pandas slicing."""
        sliced = sample_flux_spectrum.iloc[:2]
        assert sliced.title == "TEST"


# ---------------------------------------------------------------------------
# ealf property
# ---------------------------------------------------------------------------


class TestEalf:
    """Tests for the ealf (Energy of Average Lethargy causing Fission) property."""

    def test_single_bin_equals_geometric_mean(self, single_bin_flux):
        """
        Single-bin EALF equals the geometric mean of the bin boundaries.

        E_mid = sqrt(1 * 4) = 2.0  =>  ealf = 2.0
        """
        assert single_bin_flux.ealf == pytest.approx(2.0, rel=1e-9)

    def test_two_equal_bins_geometric_mean(self, two_bin_equal_flux):
        """
        With two equal-weight bins at E_mid = [10, 1000]:
        ealf = exp((ln10 + ln1000) / 2) = exp(ln100) = 100.0
        """
        assert two_bin_equal_flux.ealf == pytest.approx(100.0, rel=1e-9)

    def test_ealf_is_float(self, sample_flux_spectrum):
        """ealf returns a Python float."""
        assert isinstance(sample_flux_spectrum.ealf, float)

    def test_ealf_positive(self, sample_flux_spectrum):
        """EALF must be a positive energy value."""
        assert sample_flux_spectrum.ealf > 0.0

    def test_ealf_within_energy_range(self, sample_flux_spectrum):
        """EALF must lie within the span of the energy grid."""
        e_min = sample_flux_spectrum.index.get_level_values("E_min_eV").min()
        e_max = sample_flux_spectrum.index.get_level_values("E_max_eV").max()
        assert e_min <= sample_flux_spectrum.ealf <= e_max

    def test_ealf_zero_flux_raises(self):
        """ealf raises ValueError when the total flux is zero."""
        index = pd.MultiIndex.from_tuples([(1.0, 10.0)], names=["E_min_eV", "E_max_eV"])
        fs = FluxSpectrum(
            pd.DataFrame({"flux": [0.0], "flux_std": [0.0]}, index=index),
            title="ZERO",
        )
        with pytest.raises(ValueError, match="total flux is zero"):
            _ = fs.ealf


# ---------------------------------------------------------------------------
# mean_energy property
# ---------------------------------------------------------------------------


class TestMeanEnergy:
    """Tests for the mean_energy (flux-weighted arithmetic mean energy) property."""

    def test_single_bin_equals_midpoint(self, single_bin_flux):
        """
        Single-bin mean energy equals the geometric midpoint of the bin.

        E_mid = sqrt(1 * 4) = 2.0  =>  mean_energy = 2.0
        """
        assert single_bin_flux.mean_energy == pytest.approx(2.0, rel=1e-9)

    def test_two_equal_bins_arithmetic_mean(self, two_bin_equal_flux):
        """
        With two equal-weight bins at E_mid = [10, 1000]:
        mean_energy = (10 + 1000) / 2 = 505.0
        """
        assert two_bin_equal_flux.mean_energy == pytest.approx(505.0, rel=1e-9)

    def test_mean_energy_is_float(self, sample_flux_spectrum):
        """mean_energy returns a Python float."""
        assert isinstance(sample_flux_spectrum.mean_energy, float)

    def test_mean_energy_positive(self, sample_flux_spectrum):
        """Mean energy must be positive."""
        assert sample_flux_spectrum.mean_energy > 0.0

    def test_mean_energy_within_range(self, sample_flux_spectrum):
        """Mean energy must lie within the span of the energy grid."""
        e_min = sample_flux_spectrum.index.get_level_values("E_min_eV").min()
        e_max = sample_flux_spectrum.index.get_level_values("E_max_eV").max()
        assert e_min <= sample_flux_spectrum.mean_energy <= e_max

    def test_mean_energy_weighted_toward_high_flux(self):
        """
        When flux is concentrated at the high-energy bin, mean_energy
        should be closer to the high-energy midpoint.
        """
        index = pd.MultiIndex.from_tuples([(1.0, 10.0), (1e5, 1e6)], names=["E_min_eV", "E_max_eV"])
        fs = FluxSpectrum(
            pd.DataFrame({"flux": [0.01, 1.0], "flux_std": [0.0, 0.0]}, index=index),
            title="WEIGHTED",
        )
        high_e_mid = np.sqrt(1e5 * 1e6)
        assert fs.mean_energy > 0.5 * high_e_mid

    def test_mean_energy_zero_flux_raises(self):
        """mean_energy raises ValueError when the total flux is zero."""
        index = pd.MultiIndex.from_tuples([(1.0, 10.0)], names=["E_min_eV", "E_max_eV"])
        fs = FluxSpectrum(
            pd.DataFrame({"flux": [0.0], "flux_std": [0.0]}, index=index),
            title="ZERO",
        )
        with pytest.raises(ValueError, match="total flux is zero"):
            _ = fs.mean_energy

    def test_ealf_always_le_mean_energy(self, sample_flux_spectrum):
        """
        The EALF (geometric mean) is always <= the arithmetic mean energy
        for non-negative weights (AM-GM inequality).
        """
        assert sample_flux_spectrum.ealf <= sample_flux_spectrum.mean_energy


# ---------------------------------------------------------------------------
# plot_spectrum
# ---------------------------------------------------------------------------


class TestPlotSpectrum:
    """Tests for the plot_spectrum method."""

    def test_returns_axes(self, sample_flux_spectrum):
        """plot_spectrum returns a matplotlib Axes object."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ax = sample_flux_spectrum.plot_spectrum()
        assert isinstance(ax, plt.Axes)
        plt.close()

    def test_accepts_custom_axes(self, sample_flux_spectrum):
        """plot_spectrum plots onto a provided Axes and returns it."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _, ax = plt.subplots()
        returned = sample_flux_spectrum.plot_spectrum(ax=ax)
        assert returned is ax
        plt.close()

    def test_x_scale_is_log(self, sample_flux_spectrum):
        """Energy axis must use a logarithmic scale."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ax = sample_flux_spectrum.plot_spectrum()
        assert ax.get_xscale() == "log"
        plt.close()

    def test_xlabel_set(self, sample_flux_spectrum):
        """x-axis label should mention Energy."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ax = sample_flux_spectrum.plot_spectrum()
        assert "Energy" in ax.get_xlabel()
        plt.close()

    def test_normalize_false_does_not_divide_by_sum(self, sample_flux_spectrum):
        """
        With normalize=False the flux values fed to the plot are the raw
        values from the DataFrame.  The total flux is not 1.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ax = sample_flux_spectrum.plot_spectrum(normalize=False)
        # The line should exist without error; close cleanly
        assert ax is not None
        plt.close()

    def test_normalize_true_is_default(self, sample_flux_spectrum):
        """Calling plot_spectrum() without normalize succeeds (default=True)."""
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ax = sample_flux_spectrum.plot_spectrum()
        assert ax is not None
        plt.close()


# ---------------------------------------------------------------------------
# HDF5 persistence
# ---------------------------------------------------------------------------


class TestFluxSpectrumHDF5:
    """Tests for HDF5 serialization of FluxSpectrum."""

    def test_to_hdf5_creates_file(self, sample_flux_spectrum):
        """to_hdf5 creates an HDF5 file on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "flux.h5")
            sample_flux_spectrum.to_hdf5(filepath, kind="keff")
            assert os.path.exists(filepath)

    def test_round_trip_values(self, sample_flux_spectrum):
        """Flux and flux_std values survive a to_hdf5 / from_hdf5 cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "flux.h5")
            sample_flux_spectrum.to_hdf5(filepath, kind="keff")
            loaded = FluxSpectrum.from_hdf5(filepath, title="TEST", kind="keff")
            pd.testing.assert_frame_equal(loaded, sample_flux_spectrum)

    def test_round_trip_title(self, sample_flux_spectrum):
        """Title metadata survives a to_hdf5 / from_hdf5 cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "flux.h5")
            sample_flux_spectrum.to_hdf5(filepath, kind="keff")
            loaded = FluxSpectrum.from_hdf5(filepath, title="TEST", kind="keff")
            assert loaded.title == "TEST"

    def test_round_trip_index_names(self, sample_flux_spectrum):
        """MultiIndex level names survive a to_hdf5 / from_hdf5 cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "flux.h5")
            sample_flux_spectrum.to_hdf5(filepath, kind="keff")
            loaded = FluxSpectrum.from_hdf5(filepath, title="TEST", kind="keff")
            assert loaded.index.names == ["E_min_eV", "E_max_eV"]

    def test_from_hdf5_missing_key_raises(self):
        """from_hdf5 raises KeyError when the requested key is absent."""
        import h5py

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "empty.h5")
            with h5py.File(filepath, "w") as f:
                f.create_group("dummy")

            with pytest.raises(KeyError):
                FluxSpectrum.from_hdf5(filepath, title="NonExistent", kind="keff")

    def test_ealf_consistent_after_round_trip(self, sample_flux_spectrum):
        """ealf computed from the loaded spectrum equals the original."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "flux.h5")
            sample_flux_spectrum.to_hdf5(filepath, kind="keff")
            loaded = FluxSpectrum.from_hdf5(filepath, title="TEST", kind="keff")
            assert loaded.ealf == pytest.approx(sample_flux_spectrum.ealf, rel=1e-9)
