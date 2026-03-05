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


def test_titles_property_with_empty_benchmarks():
    """Test the titles property when benchmarks is None."""
    from andalus.application import ApplicationSuite
    from andalus.benchmark import BenchmarkSuite

    # Create a suite with empty benchmarks
    empty_benchmarks = BenchmarkSuite({})
    applications = ApplicationSuite.from_yaml("data/config.yaml")

    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=empty_benchmarks, applications=applications, covariances=covariances)

    # Should only return application titles
    titles = suite.titles
    assert len(titles) == 1
    assert "HMF002-002" in titles


def test_m_property_error_when_no_benchmarks():
    """Test that m property raises ValueError when benchmarks is None."""
    from andalus.application import ApplicationSuite

    applications = ApplicationSuite.from_yaml("data/config.yaml")
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=None, applications=applications, covariances=covariances)  # type: ignore

    with pytest.raises(ValueError, match="No benchmarks in the assimilation suite"):
        _ = suite.m


def test_dm_property_error_when_no_benchmarks():
    """Test that dm property raises ValueError when benchmarks is None."""
    from andalus.application import ApplicationSuite

    applications = ApplicationSuite.from_yaml("data/config.yaml")
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=None, applications=applications, covariances=covariances)  # type: ignore

    with pytest.raises(ValueError, match="No benchmarks in the assimilation suite"):
        _ = suite.dm


def test_c_property_only_applications():
    """Test c property when only applications are present."""
    from andalus.application import ApplicationSuite

    applications = ApplicationSuite.from_yaml("data/config.yaml")
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=None, applications=applications, covariances=covariances)  # type: ignore

    c = suite.c
    assert isinstance(c, pd.Series)
    assert len(c) == 1


def test_c_property_only_benchmarks():
    """Test c property when only benchmarks are present."""
    from andalus.benchmark import BenchmarkSuite

    benchmarks = BenchmarkSuite.from_yaml("data/config.yaml")
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=benchmarks, applications=None, covariances=covariances)  # type: ignore

    c = suite.c
    assert isinstance(c, pd.Series)
    assert len(c) == 2


def test_c_property_error_when_both_none():
    """Test that c property raises ValueError when both benchmarks and applications are None."""
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances
    suite = AssimilationSuite(benchmarks=None, applications=None, covariances=covariances)  # type: ignore

    with pytest.raises(ValueError, match="No applications or benchmarks in the assimilation suite"):
        _ = suite.c


def test_dc_property_only_applications():
    """Test dc property when only applications are present."""
    from andalus.application import ApplicationSuite

    applications = ApplicationSuite.from_yaml("data/config.yaml")
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=None, applications=applications, covariances=covariances)  # type: ignore

    dc = suite.dc
    assert isinstance(dc, pd.Series)
    assert len(dc) == 1


def test_dc_property_only_benchmarks():
    """Test dc property when only benchmarks are present."""
    from andalus.benchmark import BenchmarkSuite

    benchmarks = BenchmarkSuite.from_yaml("data/config.yaml")
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=benchmarks, applications=None, covariances=covariances)  # type: ignore

    dc = suite.dc
    assert isinstance(dc, pd.Series)
    assert len(dc) == 2


def test_dc_property_error_when_both_none():
    """Test that dc property raises ValueError when both benchmarks and applications are None."""
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances
    suite = AssimilationSuite(benchmarks=None, applications=None, covariances=covariances)  # type: ignore

    with pytest.raises(ValueError, match="No applications or benchmarks in the assimilation suite"):
        _ = suite.dc


def test_s_property_only_applications():
    """Test s property when only applications are present."""
    from andalus.application import ApplicationSuite

    applications = ApplicationSuite.from_yaml("data/config.yaml")
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=None, applications=applications, covariances=covariances)  # type: ignore

    s = suite.s
    assert isinstance(s, pd.DataFrame)
    assert "HMF002-002" in s.columns


def test_s_property_only_benchmarks():
    """Test s property when only benchmarks are present."""
    from andalus.benchmark import BenchmarkSuite

    benchmarks = BenchmarkSuite.from_yaml("data/config.yaml")
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=benchmarks, applications=None, covariances=covariances)  # type: ignore

    s = suite.s
    assert isinstance(s, pd.DataFrame)
    assert "HMF001" in s.columns


def test_s_property_error_when_both_none():
    """Test that s property raises ValueError when both benchmarks and applications are None."""
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances
    suite = AssimilationSuite(benchmarks=None, applications=None, covariances=covariances)  # type: ignore

    with pytest.raises(ValueError, match="No applications or benchmarks in the assimilation suite"):
        _ = suite.s


def test_ds_property_only_applications():
    """Test ds property when only applications are present."""
    from andalus.application import ApplicationSuite

    applications = ApplicationSuite.from_yaml("data/config.yaml")
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=None, applications=applications, covariances=covariances)  # type: ignore

    ds = suite.ds
    assert isinstance(ds, pd.DataFrame)
    assert "HMF002-002_std" in ds.columns


def test_ds_property_only_benchmarks():
    """Test ds property when only benchmarks are present."""
    from andalus.benchmark import BenchmarkSuite

    benchmarks = BenchmarkSuite.from_yaml("data/config.yaml")
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=benchmarks, applications=None, covariances=covariances)  # type: ignore

    ds = suite.ds
    assert isinstance(ds, pd.DataFrame)
    assert "HMF001_std" in ds.columns


def test_ds_property_error_when_both_none():
    """Test that ds property raises ValueError when both benchmarks and applications are None."""
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances
    suite = AssimilationSuite(benchmarks=None, applications=None, covariances=covariances)  # type: ignore

    with pytest.raises(ValueError, match="No applications or benchmarks in the assimilation suite"):
        _ = suite.ds


def test_propagate_nuclear_data_uncertainty(assimilation_setup):
    """Test nuclear data uncertainty propagation."""
    suite = assimilation_setup

    uncertainty = suite.propagate_nuclear_data_uncertainty()

    assert isinstance(uncertainty, pd.Series)
    assert uncertainty.name == "uncertainty_from_nuclear_data"
    assert len(uncertainty) == 3
    assert all(uncertainty >= 0)


def test_individual_chi_squared_without_nuclear_data(assimilation_setup):
    """Test individual chi-squared calculation without nuclear data."""
    suite = assimilation_setup

    chi2 = suite.individual_chi_squared(nuclear_data=False)

    assert isinstance(chi2, pd.Series)
    assert chi2.name == "chi_squared"
    assert len(chi2) == 2
    assert all(chi2 >= 0)


def test_individual_chi_squared_with_nuclear_data(assimilation_setup):
    """Test individual chi-squared calculation with nuclear data."""
    suite = assimilation_setup

    chi2 = suite.individual_chi_squared(nuclear_data=True)

    assert isinstance(chi2, pd.Series)
    assert chi2.name == "chi_squared"
    assert len(chi2) == 2
    assert all(chi2 >= 0)


def test_ck_target_found(assimilation_setup):
    """Test ck_target for an existing target."""
    suite = assimilation_setup

    ck = suite.ck_target("HMF001")

    assert isinstance(ck, pd.Series)
    assert len(ck) == 2  # Should exclude the target itself
    assert "HMF001" not in ck.index
