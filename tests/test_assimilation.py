import numpy as np
import pandas as pd
import pytest

from andalus.assimilation import AssimilationSuite, _parse_xsdata


@pytest.fixture
def mock_sensitivity_df():
    """Creates a small MultiIndex DataFrame representing sensitivities."""
    index = pd.MultiIndex.from_tuples(
        [(922350, 18, 1.0, 2.0), (922350, 102, 1.0, 2.0)], names=["ZAI", "MT", "E_min_eV", "E_max_eV"]
    )
    return pd.DataFrame({"case1": [0.1, -0.05]}, index=index)


@pytest.fixture
def assimilation_setup():
    """Sets up a suite with mocked sub-suites."""
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


def test_e_index_matrix(assimilation_setup):
    """Verify that the e_index_matrix method returns a DataFrame of the correct shape.
    And that values are between -1 and 1 (since it's a correlation matrix) and all diagonal elements are 1.0."""
    suite = assimilation_setup
    e_index = suite.e_index_matrix()

    assert isinstance(e_index, pd.DataFrame)
    assert e_index.shape == (3, 3)
    assert e_index.values.min() >= -1.0 - 1e-12
    assert e_index.values.max() <= 1.0 + 1e-12
    assert np.allclose(np.diag(e_index), 1.0), "Diagonal elements of e_index_matrix should be 1.0"


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


def test_m_property_error_when_no_benchmarks_or_applications():
    """Test that m property raises ValueError when benchmarks and applications are None."""
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=None, applications=None, covariances=covariances)  # type: ignore

    with pytest.raises(ValueError, match="No applications or benchmarks in the assimilation suite."):
        _ = suite.m


def test_dm_property_error_when_no_benchmarks_or_applications():
    """Test that dm property raises ValueError when benchmarks and applications are None."""
    covariances = AssimilationSuite.from_yaml("data/config.yaml").covariances

    suite = AssimilationSuite(benchmarks=None, applications=None, covariances=covariances)  # type: ignore

    with pytest.raises(ValueError, match="No applications or benchmarks in the assimilation suite."):
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


def test_to_ace_no_posterior(assimilation_setup):
    """Test conversion to ACE format when no posterior has been calculated."""
    suite = assimilation_setup

    with pytest.raises(
        ValueError, match="No nuclear data adjustments found in the assimilation suite. Cannot export to ACE format."
    ):
        _ = suite.to_ace(library="jeff_40")


def test_parse_xsdata_maps_za_to_path(tmp_path):
    """Fields are alias, filename, type, ZA, isomeric_state, awr, temperature,
    binary_flag, path (the format written by to_ace_direct's create_xsdata),
    with the path optionally double-quoted."""
    ace_path = tmp_path / "92234.03c"
    ace_path.write_text("")
    xsdata_path = tmp_path / "test.xsdata"
    xsdata_path.write_text(f'  92234.03c 92234.03c 1 92234 0 234.0 300 0 "{ace_path}"\n')

    libraries = _parse_xsdata(str(xsdata_path))

    assert libraries == {92234: str(ace_path.resolve())}


def test_to_ace_direct_no_posterior(assimilation_setup):
    """Test direct conversion to ACE format when no posterior has been calculated."""
    suite = assimilation_setup

    with pytest.raises(
        ValueError, match="No nuclear data adjustments found in the assimilation suite. Cannot export to ACE format."
    ):
        _ = suite.to_ace_direct(ace_dir="unused", out_dir="unused")


def test_to_ace_direct_missing_source_file(assimilation_setup, tmp_path):
    """Test that a missing source ACE file raises FileNotFoundError."""
    suite = assimilation_setup
    suite.xs_adjustment = pd.Series(
        [0.1],
        index=pd.MultiIndex.from_tuples([(10010, 102, 1.0, 2.0)], names=["ZAI", "MT", "E_min_eV", "E_max_eV"]),
    )

    with pytest.raises(FileNotFoundError, match="1001.03c"):
        suite.to_ace_direct(ace_dir=str(tmp_path), out_dir=str(tmp_path / "out"))


def test_to_ace_direct_perturbs_and_writes(assimilation_setup, tmp_path):
    """Test that to_ace_direct perturbs a source ACE file and writes the result."""
    from andalus.ace import ACE

    suite = assimilation_setup

    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    out_dir = tmp_path / "out"

    import shutil

    source = ACE.read("data/1-H-1g-300.0")
    energy = source.reactions[102].energies
    # ACE energies are in MeV; xs_adjustment bins are in eV (see andalus.ace.core._EV_PER_MEV).
    e_lo, e_hi = float(energy[10]) * 1e6, float(energy[50]) * 1e6
    shutil.copy("data/1-H-1g-300.0", ace_dir / "1001.03c")

    zai = 10010  # ZAID 1001 (H-1), ground state
    suite.xs_adjustment = pd.Series(
        [0.2],
        index=pd.MultiIndex.from_tuples([(zai, 102, e_lo, e_hi)], names=["ZAI", "MT", "E_min_eV", "E_max_eV"]),
    )

    written = suite.to_ace_direct(ace_dir=str(ace_dir), out_dir=str(out_dir))

    assert written == [str(out_dir / "1001.03c")]
    result = ACE.read(written[0])

    in_bin = (energy * 1e6 > e_lo) & (energy * 1e6 <= e_hi)
    ratio = result.reactions[102].xs / source.reactions[102].xs
    np.testing.assert_allclose(ratio[in_bin], 1.2, rtol=1e-10)
    np.testing.assert_allclose(ratio[~in_bin], 1.0, rtol=1e-10)


def test_to_ace_direct_with_xsdata_path(assimilation_setup, tmp_path):
    """Regression test: to_ace_direct(xsdata_path=...) must locate the source
    ACE file via the ZA field (not the always-"1" type field it used to read)."""
    import shutil

    from andalus.ace import ACE

    suite = assimilation_setup

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    shutil.copy("data/1-H-1g-300.0", source_dir / "1001.03c")
    out_dir = tmp_path / "out"

    xsdata_path = tmp_path / "test.xsdata"
    xsdata_path.write_text(f'  1001.03c 1001.03c 1 1001 0 1.0 300 0 "{source_dir / "1001.03c"}"\n')

    zai = 10010
    energy = ACE.read("data/1-H-1g-300.0").reactions[102].energies
    e_lo, e_hi = float(energy[10]) * 1e6, float(energy[50]) * 1e6
    suite.xs_adjustment = pd.Series(
        [0.2],
        index=pd.MultiIndex.from_tuples([(zai, 102, e_lo, e_hi)], names=["ZAI", "MT", "E_min_eV", "E_max_eV"]),
    )

    written = suite.to_ace_direct(out_dir=str(out_dir), xsdata_path=str(xsdata_path))

    assert written == [str(out_dir / "1001.03c")]


def test_to_ace_direct_routes_chi_mts_to_perturb_chi(assimilation_setup, tmp_path):
    """MT=35018 (ANDALUS's MF*1000+MT convention for prompt fission chi) must be
    routed to ACE.perturb_chi, not ACE.perturb (which has no MT=35018 reaction)."""
    import shutil

    from andalus.ace import ACE

    suite = assimilation_setup

    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    out_dir = tmp_path / "out"

    source = ACE.read("data/92235.03c")
    dist = source.chi[18]
    e_out = dist.tables[0].energy_out
    e_lo, e_hi = float(e_out[len(e_out) // 4]) * 1e6, float(e_out[3 * len(e_out) // 4]) * 1e6
    shutil.copy("data/92235.03c", ace_dir / "92235.03c")

    zai = 922350
    suite.xs_adjustment = pd.Series(
        [0.2],
        index=pd.MultiIndex.from_tuples([(zai, 35018, e_lo, e_hi)], names=["ZAI", "MT", "E_min_eV", "E_max_eV"]),
    )

    written = suite.to_ace_direct(ace_dir=str(ace_dir), out_dir=str(out_dir))

    assert written == [str(out_dir / "92235.03c")]
    result = ACE.read(written[0])

    in_bin = (e_out * 1e6 > e_lo) & (e_out * 1e6 <= e_hi)
    for source_table, result_table in zip(source.chi[18].tables, result.chi[18].tables, strict=True):
        expected = source_table.pdf.copy()
        expected[in_bin] *= 1.2
        expected /= np.trapz(expected, e_out)
        np.testing.assert_allclose(result_table.pdf, expected, rtol=1e-6)
