import numpy as np
import pandas as pd
import pytest

from andalus.assimilation import AssimilationSuite


@pytest.fixture
def mock_sensitivity_df():
    """Creates a small MultiIndex DataFrame representing sensitivities."""
    index = pd.MultiIndex.from_tuples(
        [(922350, 18, 1.0, 2.0), (922350, 102, 1.0, 2.0)], names=["ZAI", "MT", "E_min_eV", "E_max_eV"]
    )
    return pd.DataFrame({"case1": [0.1, -0.05]}, index=index)


@pytest.fixture
def assimilation_setup(mock_sensitivity_df):
    """Sets up a suite with mocked sub-suites."""
    # Mock BenchmarkSuite
    suite = AssimilationSuite.from_yaml("data/config.yaml")
    return suite


def test_s_property_concatenation(assimilation_setup):
    suite = assimilation_setup
    combined_s = suite.s

    assert "HMF001" in combined_s.columns
    assert "HMF002-002" in combined_s.columns
    assert combined_s.shape == (594, 3)


def test_ck_matrix(assimilation_setup):
    suite = assimilation_setup
    ck = suite.ck_matrix()

    # Diagonal of a similarity matrix (correlation) must be 1.0
    assert np.allclose(np.diag(ck), 1.0)
    assert ck.shape == (3, 3)
    assert "HMF001" in ck.index
    assert "HMF002-002" in ck.index


def test_ck_target_missing_error(assimilation_setup):
    suite = assimilation_setup
    with pytest.raises(ValueError, match="not found"):
        suite.ck_target("non_existent_case")


def test_chi_squared_logic(assimilation_setup):
    suite = assimilation_setup

    # Test without nuclear data
    chi2 = suite.chi_squared(nuclear_data=False)
    assert isinstance(chi2, float)
    assert chi2 > 0

    # Test with nuclear data (should be smaller because uncertainty increases)
    chi2_nd = suite.chi_squared(nuclear_data=True)
    assert chi2_nd < chi2


def test_glls_execution(assimilation_setup):
    """Verify GLLS returns a new suite with updated 'c' values."""
    suite = assimilation_setup

    post_suite = suite.glls()

    assert isinstance(post_suite, AssimilationSuite)
    assert post_suite.benchmarks is not None
    assert post_suite.applications is not None


def test_glls_reduces_chi_squared(assimilation_setup):
    """
    Fundamental Test: The posterior chi-squared must be lower than
    the prior chi-squared if the assimilation is working correctly.
    """
    suite = assimilation_setup
    post_suite = suite.glls()

    prior_chi2 = suite.chi_squared(nuclear_data=True)
    post_chi2 = post_suite.chi_squared(nuclear_data=True)

    assert post_chi2 < prior_chi2, f"Posterior Chi2 ({post_chi2}) should be < Prior Chi2 ({prior_chi2})"


def test_glls_application_shift(assimilation_setup):
    """
    Test that the application values actually change.
    """
    suite = assimilation_setup
    post_suite = suite.glls()

    # Check that at least one value has shifted by a meaningful amount
    # (Using 1e-8 to avoid tiny floating point noise)
    diff = np.abs(suite.applications.c - post_suite.applications.c)
    assert np.any(diff > 1e-8), "GLLS did not result in any shift in application values."


def test_glls_covariance_shrinkage(assimilation_setup):
    """
    Fundamental Test: Assimilation of new information must reduce
    (or keep equal) the uncertainty in the nuclear data.
    """
    suite = assimilation_setup
    post_suite = suite.glls()

    prior_unc = np.diag(suite.covariances.matrix)
    post_unc = np.diag(post_suite.covariances.matrix)

    # Posterior uncertainty must be less than or equal to prior uncertainty
    assert np.all(post_unc <= prior_unc + 1e-12)  # + epsilon for float noise
    assert np.any(post_unc < prior_unc), "Posterior uncertainty should be strictly smaller than prior."
