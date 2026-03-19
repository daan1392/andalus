import os

import numpy as np
import pandas as pd
import pytest

from andalus.covariance import Covariance, CovarianceSuite


@pytest.fixture
def sample_cov():
    """Create a dummy symmetric covariance matrix."""
    # only four index entries to match the 4×4 data array
    idx = pd.MultiIndex.from_product([[18], [1.0, 10.0], [10.0, 100.0]], names=["MT", "E_min", "E_max"])
    # Create a 4x4 symmetric matrix
    data = np.array([[1.0, 0.2, 0.0, 0.0], [0.2, 1.0, 0.0, 0.0], [0.0, 0.0, 0.5, 0.1], [0.0, 0.0, 0.1, 0.5]])
    cov = Covariance(data, index=idx, columns=idx)
    cov.zai = 922350
    cov.mf = 33
    return cov


@pytest.fixture
def real_cov():
    """Load a real covariance matrix from the test data directory."""
    path = os.path.join("data", "covariances_test.h5")
    if not os.path.exists(path):
        return Covariance()
    return Covariance.from_hdf5(path, zai=922380, mts=[18])


def test_covariance_from_errorr():
    """Test constructing a Covariance from NJOY errorr files."""
    files = {
        "errorr31": os.path.join("data", "u235.errorr31"),
        "errorr33": os.path.join("data", "u235.errorr33"),
        "errorr34": os.path.join("data", "u235.errorr34"),
        "errorr35": os.path.join("data", "u235.errorr35"),
    }
    cov = Covariance.from_errorr(files, zai=922350, mts=[2, 4, 18, 102, 35018, 456, 34251])

    assert cov.zai == 922350
    assert not cov.empty
    assert all(mt in cov.index.get_level_values("MT") for mt in [2, 4, 18, 102, 35018, 456, 34251])
    assert cov.shape[0] == cov.shape[1]
    assert np.allclose(cov.values, cov.values.T)  # Check symmetry
    assert cov.index.names == ["MT", "E_min_eV", "E_max_eV"]


def test_metadata_persistence(sample_cov):
    """Ensure ZAI and MF stick during slicing."""
    sliced = sample_cov.iloc[:2, :2]
    assert sliced.zai == 922350


def test_hdf5_roundtrip(sample_cov, tmp_path):
    """Test saving and loading from HDF5."""
    file_path = str(tmp_path / "test_data.h5")
    sample_cov.to_hdf5(file_path)

    loaded = Covariance.from_hdf5(file_path, zai=922350)

    assert loaded.zai == 922350
    pd.testing.assert_frame_equal(loaded, sample_cov)


def test_mt_filtering(sample_cov, tmp_path):
    """Test if MT filtering works during HDF5 loading."""
    file_path = str(tmp_path / "test_filter.h5")
    sample_cov.to_hdf5(file_path)

    # Only load fission (MT 18)
    loaded = Covariance.from_hdf5(file_path, zai=922350, mts=[18])

    # all four bins remain after filtering for MT 18
    assert len(loaded) == 4
    assert all(loaded.index.get_level_values("MT") == 18)


def test_suite_assembly(sample_cov, real_cov):
    """Test block-diagonal assembly in CovarianceSuite."""
    # Ensure real_cov actually loaded correctly and has the right index names
    if real_cov.empty:
        pytest.skip("Real covariance file 'data/covariances_test.h5' not found or empty.")

    assert "MT" in real_cov.index.names

    suite = CovarianceSuite.from_dict({922350: sample_cov, 922380: real_cov})

    full_mat = suite.matrix

    # Make sure shape of matrix is as expected (sum of individual covariances)
    assert full_mat.shape[0] == len(sample_cov) + len(real_cov)
    assert "ZAI" in full_mat.index.names

    # Check that cross-isotope blocks are zero
    assert full_mat.loc[922350, 922380].values.sum() == 0


def test_correlation_calculation(sample_cov):
    """Test that the correlation matrix is correctly calculated."""
    corr = sample_cov.correlation()
    assert corr.shape == sample_cov.shape
    # ensure diagonal elements are ones (use values to avoid index/dataframe issues)
    assert np.allclose(np.diag(corr.values), 1.0)
    # Check that off-diagonal elements are between -1 and 1
    off_diag = corr.values[~np.eye(corr.shape[0], dtype=bool)]
    assert np.all((off_diag >= -1) & (off_diag <= 1))


def test_covariance_nuclide_property(sample_cov):
    """Test the nuclide property returns correct string."""
    nuclide = sample_cov.nuclide
    assert isinstance(nuclide, str)
    assert "U" in nuclide  # U-235


def test_covariance_empty():
    """Test creating an empty Covariance object."""
    empty_cov = Covariance()
    assert len(empty_cov) == 0
    assert empty_cov.empty


def test_covariance_suite_from_df():
    """Test creating CovarianceSuite from a DataFrame."""
    idx = pd.MultiIndex.from_product([[922350], [18], [1.0, 10.0]], names=["ZAI", "MT", "E_min"])
    data = np.eye(2)
    df = pd.DataFrame(data, index=idx, columns=idx)

    suite = CovarianceSuite.from_df(df)
    assert isinstance(suite, CovarianceSuite)
    assert suite.matrix.shape == (2, 2)


def test_is_unrealistic_uncertainty(sample_cov):
    """Test is_unrealistic_uncertainty method."""
    # Normal covariance should not be unrealistic
    assert not sample_cov.is_unrealistic_uncertainty(threshold=10)

    # Create an unrealistic covariance
    idx = pd.MultiIndex.from_product([[18], [1.0]], names=["MT", "E_min"])
    data = np.array([[100.0]])  # Very large variance
    unrealistic_cov = Covariance(data, index=idx, columns=idx)
    unrealistic_cov.zai = 922350

    # Should return True for unrealistic uncertainty
    assert unrealistic_cov.is_unrealistic_uncertainty(threshold=10)


def test_covariance_suite_from_dict():
    """Test creating CovarianceSuite from a dictionary."""
    # Create simple covariances with proper MultiIndex structure
    idx1 = pd.MultiIndex.from_product([[18], [1.0], [10.0]], names=["MT", "E_min_eV", "E_max_eV"])
    cov1 = Covariance(np.array([[1.0]]), index=idx1, columns=idx1)
    cov1.zai = 922350

    idx2 = pd.MultiIndex.from_product([[18], [1.0], [10.0]], names=["MT", "E_min_eV", "E_max_eV"])
    cov2 = Covariance(np.array([[0.5]]), index=idx2, columns=idx2)
    cov2.zai = 922380

    suite = CovarianceSuite.from_dict({922350: cov1, 922380: cov2})

    assert isinstance(suite, CovarianceSuite)
    assert suite.matrix.shape[0] == 2
    assert "ZAI" in suite.matrix.index.names
