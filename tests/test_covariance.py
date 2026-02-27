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
    return Covariance.from_hdf5("data/covariances_test.h5", zai=922380, mts=[2, 4, 18, 102, 456, 35018])


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
    suite = CovarianceSuite.from_dict({922350: sample_cov, 922380: real_cov})

    full_mat = suite.matrix
    assert full_mat.shape == (4 + 6 * 33, 4 + 6 * 33)  # 202 = 4 bins for 922350 + 33 bins for 922380 * 6 MTs
    assert "ZAI" in full_mat.index.names
    # Check that cross-isotope blocks are zero
    assert full_mat.loc[922350, 922380].sum().sum() == 0


def test_correlation_calculation(sample_cov):
    """Test that the correlation matrix is correctly calculated."""
    corr = sample_cov.correlation()
    assert corr.shape == sample_cov.shape
    # ensure diagonal elements are ones (use values to avoid index/dataframe issues)
    assert np.allclose(np.diag(corr.values), 1.0)
    # Check that off-diagonal elements are between -1 and 1
    off_diag = corr.values[~np.eye(corr.shape[0], dtype=bool)]
    assert np.all((off_diag >= -1) & (off_diag <= 1))
