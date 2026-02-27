import os
import tempfile
from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest

from andalus.benchmark import Benchmark, BenchmarkSuite
from andalus.sensitivity import Sensitivity


@pytest.fixture
def test_sensitivity():
    """Provides a Sensitivity object from real test data."""
    return Sensitivity.from_serpent(
        sens0_path="tests/hmf001.ser_sens0.m",
        title="HMF001",
        kind="keff",
        materiallist=["total"],
        pertlist=[
            "mt 2 xs",
            "mt 4 xs",
            "mt 16 xs",
            "mt 18 xs",
            "mt 102 xs",
            "nubar prompt",
            "chi prompt",
            "ela leg mom 1",
        ],
    )


@pytest.fixture
def test_benchmark(test_sensitivity):
    """Provides a Benchmark object for testing."""
    return Benchmark(
        title="HMF001",
        kind="keff",
        m=1.0,
        dm=0.002,
        c=0.9989,
        dc=0.00018,
        s=test_sensitivity,
    )


class TestBenchmarkInitialization:
    """Tests for Benchmark initialization and validation."""

    def test_benchmark_basic_initialization(self, test_sensitivity):
        """Test basic Benchmark object creation."""
        b = Benchmark(
            title="HMF001",
            kind="keff",
            m=1.0,
            dm=0.1,
            c=1.0,
            dc=0.1,
            s=test_sensitivity,
        )
        assert b.title == "HMF001"
        assert b.kind == "keff"
        assert b.m == 1.0
        assert b.dm == 0.1
        assert b.c == 1.0
        assert b.dc == 0.1
        assert isinstance(b.s, Sensitivity)

    def test_benchmark_is_frozen(self, test_benchmark):
        """Test that Benchmark is immutable."""
        with pytest.raises(FrozenInstanceError):
            test_benchmark.m = 2.0

    def test_invalid_title_type(self, test_sensitivity):
        """Test that title must be a string."""
        with pytest.raises(TypeError, match="Title.*must be a string"):
            Benchmark(
                title=123,  # type: ignore[arg-type]
                kind="keff",
                m=1.0,
                dm=0.1,
                c=1.0,
                dc=0.1,
                s=test_sensitivity,
            )

    def test_invalid_kind(self, test_sensitivity):
        """Test that invalid kind raises ValueError."""
        with pytest.raises(ValueError, match="Type.*not implemented"):
            Benchmark(
                title="HMF001",
                kind="invalid",
                m=1.0,
                dm=0.1,
                c=1.0,
                dc=0.1,
                s=test_sensitivity,
            )

    def test_invalid_measurement_type(self, test_sensitivity):
        """Test that measurement must be numeric."""
        with pytest.raises(TypeError, match="Measurement.*must be a number"):
            Benchmark(
                title="HMF001",
                kind="keff",
                m="not_a_number",  # type: ignore[arg-type]
                dm=0.1,
                c=1.0,
                dc=0.1,
                s=test_sensitivity,
            )

    def test_invalid_measurement_uncertainty_type(self, test_sensitivity):
        """Test that measurement uncertainty must be numeric."""
        with pytest.raises(TypeError, match="Measurement uncertainty.*must be a number"):
            Benchmark(
                title="HMF001",
                kind="keff",
                m=1.0,
                dm="not_a_number",  # type: ignore[arg-type]
                c=1.0,
                dc=0.1,
                s=test_sensitivity,
            )

    def test_invalid_calculated_value_type(self, test_sensitivity):
        """Test that calculated value must be numeric."""
        with pytest.raises(TypeError, match="Calculated value.*must be a number"):
            Benchmark(
                title="HMF001",
                kind="keff",
                m=1.0,
                dm=0.1,
                c="not_a_number",  # type: ignore[arg-type]
                dc=0.1,
                s=test_sensitivity,
            )

    def test_invalid_calculated_uncertainty_type(self, test_sensitivity):
        """Test that calculated uncertainty must be numeric."""
        with pytest.raises(TypeError, match="Calculated uncertainty.*must be a number"):
            Benchmark(
                title="HMF001",
                kind="keff",
                m=1.0,
                dm=0.1,
                c=1.0,
                dc="not_a_number",  # type: ignore[arg-type]
                s=test_sensitivity,
            )

    def test_invalid_sensitivity_type(self):
        """Test that sensitivity must be a Sensitivity object."""
        with pytest.raises(TypeError, match="Sensitivity.*must be a Sensitivity object"):
            Benchmark(
                title="HMF001",
                kind="keff",
                m=1.0,
                dm=0.1,
                c=1.0,
                dc=0.1,
                s="not_a_sensitivity",  # type: ignore[arg-type]
            )


class TestBenchmarkFromSerpent:
    """Tests for creating Benchmark from Serpent files."""

    def test_from_serpent_basic(self):
        """Test creating Benchmark from Serpent output files."""
        b = Benchmark.from_serpent(
            title="HMF001",
            m=1.00000,
            dm=0.00200,
            results_path="tests/hmf001.ser_res.m",
            sens0_path="tests/hmf001.ser_sens0.m",
        )
        assert b.title == "HMF001"
        assert b.kind == "keff"
        assert b.m == 1.0
        assert b.dm == 0.002
        assert 0.998895 < b.c < 0.998899  # Check k-eff is in expected range
        assert b.dc > 0  # Uncertainty should be positive
        assert isinstance(b.s, Sensitivity)

    def test_from_serpent_custom_kind(self):
        """Test from_serpent with custom kind parameter."""
        b = Benchmark.from_serpent(
            title="HMF001",
            m=1.0,
            dm=0.002,
            results_path="tests/hmf001.ser_res.m",
            sens0_path="tests/hmf001.ser_sens0.m",
            kind="keff",
        )
        assert b.kind == "keff"
        assert b.s.kind == "keff"

    def test_from_serpent_default_materials(self):
        """Test that from_serpent uses default materials list."""
        b = Benchmark.from_serpent(
            title="HMF001",
            m=1.0,
            dm=0.002,
            results_path="tests/hmf001.ser_res.m",
            sens0_path="tests/hmf001.ser_sens0.m",
            materials=None,
        )
        assert b.s is not None
        assert len(b.s) > 0

    def test_from_serpent_default_perturbations(self):
        """Test that from_serpent uses default perturbations."""
        b = Benchmark.from_serpent(
            title="HMF001",
            m=1.0,
            dm=0.002,
            results_path="tests/hmf001.ser_res.m",
            sens0_path="tests/hmf001.ser_sens0.m",
            pertlist=None,
        )
        assert b.s is not None


class TestBenchmarkHDF5:
    """Tests for HDF5 serialization."""

    def test_to_hdf5(self, test_benchmark):
        """Test saving benchmark to HDF5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_bench.h5")
            test_benchmark.to_hdf5(filepath)
            assert os.path.exists(filepath)

    def test_from_hdf5(self, test_benchmark):
        """Test loading benchmark from HDF5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_bench.h5")
            test_benchmark.to_hdf5(filepath)

            loaded = Benchmark.from_hdf5(filepath, "HMF001")
            assert loaded.title == test_benchmark.title
            assert loaded.kind == test_benchmark.kind
            assert loaded.m == test_benchmark.m
            assert loaded.dm == test_benchmark.dm
            assert loaded.c == test_benchmark.c
            assert loaded.dc == test_benchmark.dc

    def test_from_hdf5_missing_title(self):
        """Test that from_hdf5 raises KeyError for missing title."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "empty.h5")
            import h5py

            with h5py.File(filepath, "w") as f:
                f.create_group("dummy")

            with pytest.raises(KeyError, match="Benchmark.*not found"):
                Benchmark.from_hdf5(filepath, "NonExistent")


class TestBenchmarkPrintSummary:
    """Tests for the print_summary method."""

    def test_print_summary(self, test_benchmark, capsys):
        """Test that print_summary outputs correctly."""
        test_benchmark.print_summary()
        captured = capsys.readouterr()
        assert "HMF001" in captured.out
        assert "keff" in captured.out
        assert "Measurement:" in captured.out
        assert "Calculated:" in captured.out


class TestBenchmarkSuiteHDF5:
    """Tests for BenchmarkSuite HDF5 operations."""

    def test_suite_from_hdf5_with_titles(self, test_benchmark):
        """Test loading specific benchmarks from HDF5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "suite.h5")
            test_benchmark.to_hdf5(filepath)

            suite = BenchmarkSuite.from_hdf5(filepath, titles=["HMF001"])
            assert len(suite.benchmarks) == 1
            assert "HMF001" in suite.benchmarks

    def test_suite_from_hdf5_without_titles(self, test_benchmark):
        """Test loading all benchmarks from HDF5 when titles is None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "suite.h5")
            test_benchmark.to_hdf5(filepath)

            suite = BenchmarkSuite.from_hdf5(filepath, titles=[])
            assert len(suite.benchmarks) == 1
            assert "HMF001" in suite.benchmarks

    def test_suite_from_hdf5_multiple_benchmarks(self, test_benchmark):
        """Test loading multiple benchmarks from HDF5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "suite.h5")
            test_benchmark.to_hdf5(filepath)

            # Create a second benchmark with different title
            b2 = Benchmark(
                title="HMF002",
                kind="keff",
                m=1.0,
                dm=0.002,
                c=0.9989,
                dc=0.00018,
                s=test_benchmark.s,
            )
            b2.to_hdf5(filepath)

            suite = BenchmarkSuite.from_hdf5(filepath, titles=[])
            assert len(suite.benchmarks) == 2
            assert "HMF001" in suite.benchmarks
            assert "HMF002" in suite.benchmarks


class TestBenchmarkSuiteInitialization:
    """Tests for BenchmarkSuite initialization and validation."""

    def test_empty_suite_creation(self):
        """Test creating an empty BenchmarkSuite."""
        suite = BenchmarkSuite()
        assert len(suite.benchmarks) == 0

    def test_suite_with_benchmarks(self, test_benchmark):
        """Test creating a BenchmarkSuite with benchmarks."""
        suite = BenchmarkSuite(benchmarks={"HMF001": test_benchmark})
        assert len(suite.benchmarks) == 1
        assert "HMF001" in suite.benchmarks

    def test_suite_get_existing_benchmark(self, test_benchmark):
        """Test retrieving an existing benchmark from suite."""
        suite = BenchmarkSuite(benchmarks={"HMF001": test_benchmark})
        retrieved = suite.get("HMF001")
        assert retrieved is test_benchmark

    def test_suite_get_missing_benchmark(self, test_benchmark):
        """Test retrieving a non-existent benchmark returns None."""
        suite = BenchmarkSuite(benchmarks={"HMF001": test_benchmark})
        retrieved = suite.get("NonExistent")
        assert retrieved is None

    def test_suite_remove_benchmark(self, test_benchmark):
        """Test removing a benchmark from suite."""
        suite = BenchmarkSuite(benchmarks={"HMF001": test_benchmark})
        suite.remove("HMF001")
        assert len(suite.benchmarks) == 0
        assert suite.get("HMF001") is None

    def test_suite_remove_nonexistent_benchmark(self, test_benchmark):
        """Test that removing non-existent benchmark doesn't raise error."""
        suite = BenchmarkSuite(benchmarks={"HMF001": test_benchmark})
        suite.remove("NonExistent")  # Should not raise
        assert len(suite.benchmarks) == 1

    def test_suite_properties(self, test_benchmark):
        """Test BenchmarkSuite properties (titles, kinds, m/dm/c/dc, cov, s/ds)."""
        b2 = Benchmark(
            title="HMF002",
            kind="keff",
            m=2.0,
            dm=0.003,
            c=1.001,
            dc=0.0002,
            s=test_benchmark.s.rename_sensitivity("HMF002"),
        )
        suite = BenchmarkSuite(benchmarks={"HMF001": test_benchmark, "HMF002": b2})

        # titles & kinds
        assert suite.titles == ["HMF001", "HMF002"]
        assert isinstance(suite.kinds, pd.Series)
        assert list(suite.kinds.values) == ["keff", "keff"]

        # measurement series and uncertainties
        assert isinstance(suite.m, pd.Series)
        assert suite.m["HMF001"] == pytest.approx(1.0)
        assert suite.m["HMF002"] == pytest.approx(2.0)

        assert isinstance(suite.dm, pd.Series)
        assert suite.dm["HMF001"] == pytest.approx(0.002)
        assert suite.dm["HMF002"] == pytest.approx(0.003)

        # covariance matrix (diagonal dm^2, off-diagonal zero)
        cov = suite.cov_m
        assert isinstance(cov, pd.DataFrame)
        expected_diag = np.array([0.002**2, 0.003**2])
        assert np.allclose(np.diag(cov.values), expected_diag)
        assert np.allclose(cov.values - np.diag(np.diag(cov.values)), 0)

        # calculated values and uncertainties
        assert isinstance(suite.c, pd.Series)
        assert suite.c["HMF001"] == pytest.approx(test_benchmark.c)
        assert suite.c["HMF002"] == pytest.approx(1.001)

        assert isinstance(suite.dc, pd.Series)
        assert suite.dc["HMF001"] == pytest.approx(test_benchmark.dc)
        assert suite.dc["HMF002"] == pytest.approx(0.0002)

        # sensitivity matrices
        s_df = suite.s
        ds_df = suite.ds
        assert isinstance(s_df, pd.DataFrame)
        assert isinstance(ds_df, pd.DataFrame)
        assert list(s_df.columns) == ["HMF001", "HMF002"]
        assert list(ds_df.columns) == ["HMF001_std", "HMF002_std"]
        # indices should match the sensitivity index from the input sensitivity
        assert list(s_df.index) == list(test_benchmark.s.index)
