# ...existing code...
import os
import tempfile
from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from andalus.application import Application, ApplicationSuite
from andalus.sensitivity import Sensitivity


@pytest.fixture
def test_sensitivity():
    """Provides a Sensitivity object from real test data."""
    return Sensitivity.from_serpent(
        sens0_path="data/hmf001.ser_sens0.m",
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
def test_application(test_sensitivity):
    """Provides an Application object for testing."""
    return Application(
        title="HMF001",
        kind="keff",
        c=0.9989,
        dc=0.00018,
        s=test_sensitivity,
    )


class TestApplicationInitialization:
    """Tests for Application initialization and validation."""

    def test_application_basic_initialization(self, test_sensitivity):
        """Test basic Application object creation."""
        a = Application(
            title="HMF001",
            kind="keff",
            c=0.9989,
            dc=0.00018,
            s=test_sensitivity,
        )
        assert a.title == "HMF001"
        assert a.kind == "keff"
        assert a.c == pytest.approx(0.9989)
        assert a.dc == pytest.approx(0.00018)
        assert isinstance(a.s, Sensitivity)

    def test_application_is_frozen(self, test_application):
        """Test that Application is immutable."""
        with pytest.raises(FrozenInstanceError):
            test_application.c = 1.0

    def test_invalid_title_type(self, test_sensitivity):
        """Test that title must be a string."""
        with pytest.raises(TypeError, match="Title.*must be a string"):
            Application(
                title=123,  # type: ignore[arg-type]
                kind="keff",
                c=1.0,
                dc=0.1,
                s=test_sensitivity,
            )

    def test_invalid_kind(self, test_sensitivity):
        """Test that invalid kind raises ValueError."""
        with pytest.raises(ValueError, match="Type.*not implemented"):
            Application(
                title="HMF001",
                kind="invalid",
                c=1.0,
                dc=0.1,
                s=test_sensitivity,
            )

    def test_invalid_calculated_value_type(self, test_sensitivity):
        """Test that calculated value must be numeric."""
        with pytest.raises(TypeError, match="Calculated value.*must be a number"):
            Application(
                title="HMF001",
                kind="keff",
                c="not_a_number",  # type: ignore[arg-type]
                dc=0.1,
                s=test_sensitivity,
            )

    def test_invalid_calculated_uncertainty_type(self, test_sensitivity):
        """Test that calculated uncertainty must be numeric."""
        with pytest.raises(TypeError, match="Calculated uncertainty.*must be a number"):
            Application(
                title="HMF001",
                kind="keff",
                c=1.0,
                dc="not_a_number",  # type: ignore[arg-type]
                s=test_sensitivity,
            )

    def test_invalid_sensitivity_type(self):
        """Test that sensitivity must be a Sensitivity object."""
        with pytest.raises(TypeError, match="Sensitivity.*must be a Sensitivity object"):
            Application(
                title="HMF001",
                kind="keff",
                c=1.0,
                dc=0.1,
                s="not_a_sensitivity",  # type: ignore[arg-type]
            )


class TestApplicationFromSerpent:
    """Tests for creating Application from Serpent files."""

    def test_from_serpent_basic(self):
        """Test creating Application from Serpent output files."""
        a = Application.from_serpent(
            title="HMF001",
            results_path="data/hmf001.ser_res.m",
            sens0_path="data/hmf001.ser_sens0.m",
        )
        assert a.title == "HMF001"
        assert a.kind == "keff"
        assert 0.998895 < a.c < 0.998899
        assert a.dc > 0
        assert isinstance(a.s, Sensitivity)


class TestApplicationHDF5:
    """Tests for HDF5 serialization."""

    def test_to_hdf5(self, test_application):
        """Test saving application to HDF5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_app.h5")
            test_application.to_hdf5(filepath)
            assert os.path.exists(filepath)

    def test_from_hdf5(self, test_application):
        """Test loading application from HDF5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_app.h5")
            test_application.to_hdf5(filepath)

            loaded = Application.from_hdf5(filepath, "HMF001")
            assert loaded.title == test_application.title
            assert loaded.kind == test_application.kind
            assert loaded.c == test_application.c
            assert loaded.dc == test_application.dc

    def test_from_hdf5_missing_title(self):
        """Test that from_hdf5 raises KeyError for missing title."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "empty.h5")
            import h5py

            with h5py.File(filepath, "w") as f:
                f.create_group("dummy")

            with pytest.raises(KeyError, match="Application.*not found"):
                Application.from_hdf5(filepath, "NonExistent")


class TestApplicationPrintSummary:
    """Tests for the print_summary method."""

    def test_print_summary(self, test_application, capsys):
        """Test that print_summary outputs correctly."""
        test_application.print_summary()
        captured = capsys.readouterr()
        assert "HMF001" in captured.out
        assert "keff" in captured.out
        assert "Calculated:" in captured.out


class TestApplicationSuiteHDF5:
    """Tests for ApplicationSuite HDF5 operations."""

    def test_suite_from_hdf5_with_titles(self, test_application):
        """Test loading specific applications from HDF5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "suite.h5")
            test_application.to_hdf5(filepath)

            suite = ApplicationSuite.from_hdf5(filepath, titles=["HMF001"])
            assert len(suite.applications) == 1
            assert "HMF001" in suite.applications

    def test_suite_from_hdf5_without_titles(self, test_application):
        """Test loading all applications from HDF5 when titles is None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "suite.h5")
            test_application.to_hdf5(filepath)

            suite = ApplicationSuite.from_hdf5(filepath, titles=[])
            assert len(suite.applications) == 1
            assert "HMF001" in suite.applications

    def test_suite_from_hdf5_multiple_applications(self, test_application):
        """Test loading multiple applications from HDF5."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "suite.h5")
            test_application.to_hdf5(filepath)

            # Create a second application with different title
            a2 = Application(
                title="HMF002",
                kind="keff",
                c=1.001,
                dc=0.0002,
                s=test_application.s.rename_sensitivity("HMF002"),
            )
            a2.to_hdf5(filepath)

            suite = ApplicationSuite.from_hdf5(filepath, titles=[])
            assert len(suite.applications) == 2
            assert "HMF001" in suite.applications
            assert "HMF002" in suite.applications


class TestApplicationSuiteInitialization:
    """Tests for ApplicationSuite initialization and validation."""

    def test_empty_suite_creation(self):
        """Test creating an empty ApplicationSuite."""
        suite = ApplicationSuite()
        assert len(suite.applications) == 0

    def test_suite_with_applications(self, test_application):
        """Test creating an ApplicationSuite with applications."""
        suite = ApplicationSuite(applications={"HMF001": test_application})
        assert len(suite.applications) == 1
        assert "HMF001" in suite.applications

    def test_suite_get_existing_application(self, test_application):
        """Test retrieving an existing application from suite."""
        suite = ApplicationSuite(applications={"HMF001": test_application})
        retrieved = suite.get("HMF001")
        assert retrieved is test_application

    def test_suite_get_missing_application(self, test_application):
        """Test retrieving a non-existent application returns None."""
        suite = ApplicationSuite(applications={"HMF001": test_application})
        retrieved = suite.get("NonExistent")
        assert retrieved is None

    def test_suite_remove_application(self, test_application):
        """Test removing an application from suite."""
        suite = ApplicationSuite(applications={"HMF001": test_application})
        suite.remove("HMF001")
        assert len(suite.applications) == 0
        assert suite.get("HMF001") is None

    def test_suite_remove_nonexistent_application(self, test_application):
        """Test that removing non-existent application doesn't raise error."""
        suite = ApplicationSuite(applications={"HMF001": test_application})
        suite.remove("NonExistent")  # Should not raise
        assert len(suite.applications) == 1

    def test_suite_properties(self, test_application):
        """Test ApplicationSuite properties (titles, kinds, c/dc, s/ds)."""
        a2 = Application(
            title="HMF002",
            kind="keff",
            c=1.001,
            dc=0.0002,
            s=test_application.s.rename_sensitivity("HMF002"),
        )
        suite = ApplicationSuite(applications={"HMF001": test_application, "HMF002": a2})

        # titles & kinds
        assert suite.titles == ["HMF001", "HMF002"]
        assert isinstance(suite.kinds, pd.Series)
        assert list(suite.kinds.values) == ["keff", "keff"]

        # calculated values and uncertainties
        assert isinstance(suite.c, pd.Series)
        assert suite.c["HMF001"] == pytest.approx(test_application.c)
        assert suite.c["HMF002"] == pytest.approx(1.001)

        assert isinstance(suite.dc, pd.Series)
        assert suite.dc["HMF001"] == pytest.approx(test_application.dc)
        assert suite.dc["HMF002"] == pytest.approx(0.0002)

        # sensitivity matrices
        s_df = suite.s
        ds_df = suite.ds
        assert isinstance(s_df, pd.DataFrame)
        assert isinstance(ds_df, pd.DataFrame)
        assert list(s_df.columns) == ["HMF001", "HMF002"]
        assert list(ds_df.columns) == ["HMF001_std", "HMF002_std"]
        # indices should match the sensitivity index from the input sensitivity
        assert list(s_df.index) == list(test_application.s.index)
