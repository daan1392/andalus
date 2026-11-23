import os

import numpy as np
import pandas as pd
import pytest

from andalus.assimilation import AssimilationSuite, _find_xsdata_entry, _parse_xsdata


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
    # 3 nuclides x 7 reactions (MT 2, 4, 18, 102, 456, 34251, 35018) x 33 energy groups
    assert combined_s.shape == (693, 3)
    assert set(combined_s.index.get_level_values("MT")) == {2, 4, 18, 102, 456, 34251, 35018}
    assert combined_s.index.droplevel(["ZAI", "MT"]).nunique() == 33


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


@pytest.mark.parametrize("applications", [None, "empty"])
def test_glls_without_applications(assimilation_setup, applications):
    """Adjusting on benchmarks only must work, and give the same nuclear data adjustment
    as with applications (they do not enter the update)."""
    from andalus.application import ApplicationSuite

    suite = assimilation_setup
    bench_only = AssimilationSuite(
        benchmarks=suite.benchmarks,
        applications=ApplicationSuite({}) if applications == "empty" else None,
        covariances=suite.covariances,
    )

    post = bench_only.glls()

    pd.testing.assert_series_equal(post.xs_adjustment, suite.glls().xs_adjustment)
    assert post.chi_squared(nuclear_data=True) < bench_only.chi_squared(nuclear_data=True)
    assert (post.applications is None) == (applications is None)
    assert post.titles == suite.benchmarks.titles


def test_glls_without_benchmarks_raises(assimilation_setup):
    from andalus.benchmark import BenchmarkSuite

    suite = assimilation_setup
    no_bench = AssimilationSuite(
        benchmarks=BenchmarkSuite({}), applications=suite.applications, covariances=suite.covariances
    )

    with pytest.raises(ValueError, match="at least one benchmark"):
        no_bench.glls()


def test_sensitivity_covariance_uses_absolute_errors(assimilation_setup):
    """The sensitivity term is sum_i (eps_i * S_i)^2 * C_ii per benchmark, with eps the
    relative statistical error written by Serpent, and it is diagonal across benchmarks."""
    suite = assimilation_setup
    cov = suite.covariances.matrix

    v_s = suite._sensitivity_covariance()

    assert list(v_s.index) == suite.benchmarks.titles
    off_diagonal = v_s.to_numpy() - np.diag(np.diag(v_s.to_numpy()))
    assert not off_diagonal.any()
    for title, benchmark in suite.benchmarks.items():
        s = benchmark.s.iloc[:, 0]
        rel_err = benchmark.s.iloc[:, 1]
        idx = s.index.intersection(cov.index)
        variances = pd.Series(np.diag(cov.to_numpy()), index=cov.index).loc[idx]
        expected = ((rel_err.loc[idx] * s.loc[idx]) ** 2 * variances).sum()
        assert v_s.loc[title, title] == pytest.approx(expected, rel=1e-12)
        assert expected > 0


def test_glls_sensitivity_uncertainty_does_not_cancel_adjustment(assimilation_setup):
    """Regression test: the relative errors used to be summed directly (~1e2 against a total
    variance of ~1e-4), which shrank the adjustment by about six orders of magnitude."""
    suite = assimilation_setup

    dx = suite.glls().xs_adjustment
    dx_ds = suite.glls(include_sensitivity_uncertainty=True).xs_adjustment

    assert np.abs(dx_ds).max() > 0.5 * np.abs(dx).max()
    np.testing.assert_allclose(dx_ds, dx, rtol=1e-2, atol=1e-6 * np.abs(dx).max())


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

    suite = AssimilationSuite(benchmarks=benchmarks, applications=None, covariances=covariances)

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

    suite = AssimilationSuite(benchmarks=benchmarks, applications=None, covariances=covariances)

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

    suite = AssimilationSuite(benchmarks=benchmarks, applications=None, covariances=covariances)

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

    suite = AssimilationSuite(benchmarks=benchmarks, applications=None, covariances=covariances)

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


def test_to_ace_warns_about_mubar_and_passes_supported_kinds(assimilation_setup, monkeypatch):
    """Mubar (MT 34251) cannot be exported through SANDY (it only applies MF31, MF33 and
    MF35 perturbations): to_ace must warn about it instead of dropping it silently, and
    hand the other kinds to SANDY with ENDF MT numbers (35018 -> MF35 MT18)."""
    import sandy

    calls = []

    class FakeTape:
        mat = [9228]

        def apply_perturbations(self, smps, **kwargs):
            calls.append({mf: smp.data for mf, smp in smps.items()})

    monkeypatch.setattr(sandy, "get_endf6_file", lambda *args, **kwargs: FakeTape())

    suite = assimilation_setup
    suite.xs_adjustment = pd.Series(
        [0.01, 0.02, 0.03, 0.04],
        index=pd.MultiIndex.from_tuples(
            [
                (922350, 18, 1e5, 1e6),
                (922350, 456, 1e5, 1e6),
                (922350, 34251, 1e5, 1e6),
                (922350, 35018, 1e5, 1e6),
            ],
            names=["ZAI", "MT", "E_min_eV", "E_max_eV"],
        ),
    )

    with pytest.warns(UserWarning, match=r"MT 34251 \(U235\)"):
        suite.to_ace(library="jeff_40")

    assert len(calls) == 1
    smps = calls[0]
    assert set(smps) == {31, 33, 35}
    assert set(smps[33].index.get_level_values("MT")) == {18}
    assert set(smps[31].index.get_level_values("MT")) == {456}
    assert set(smps[35].index.get_level_values("MT")) == {18}


def test_parse_xsdata_maps_za_to_path(tmp_path):
    """Fields are alias, filename, type, ZA, isomeric_state, awr, temperature,
    binary_flag, path (the format written by to_ace_direct's create_xsdata),
    with the path optionally double-quoted."""
    ace_path = tmp_path / "92234.03c"
    ace_path.write_text("")
    xsdata_path = tmp_path / "test.xsdata"
    xsdata_path.write_text(f'  92234.03c 92234.03c 1 92234 0 234.0 300 0 "{ace_path}"\n')

    libraries = _parse_xsdata(str(xsdata_path))

    assert libraries == {922340: {300.0: str(ace_path.resolve())}}


def test_parse_xsdata_temperatures_isomers_types_and_spaces(tmp_path):
    """Entries are keyed by ZAI (isomer-aware) and temperature, only transport entries
    (type 1) are kept, and quoted paths may contain spaces."""
    spaced = tmp_path / "dir with spaces"
    spaced.mkdir()
    xsdata_path = tmp_path / "lib.xsdata"
    xsdata_path.write_text(
        "  92235.03c 92235.03c 1 92235 0 235.044 300 0 u235_300.ace\n"
        "  U-235.03c 92235.03c 1 92235 0 235.044 300 0 u235_alias.ace\n"
        "  92235.06c 92235.06c 1 92235 0 235.044 600 0 u235_600.ace\n"
        "  95242.03c 95242.03c 1 95242 0 242.059 300 0 am242.ace\n"
        "  95342.03c 95342.03c 1 95242 1 242.059 300 0 am242m.ace\n"
        "  92235.dos 92235.dos 2 92235 0 235.044 300 0 u235_dosimetry.ace\n"
        f'  1001.03c 1001.03c 1 1001 0 1.0 300 0 "{spaced / "h 1.ace"}"\n'
    )

    libraries = _parse_xsdata(str(xsdata_path))

    def name(zai, t):
        return os.path.basename(libraries[zai][t])

    assert set(libraries[922350]) == {300.0, 600.0}
    assert name(922350, 300.0) == "u235_300.ace"  # first alias wins, dosimetry entry ignored
    assert name(922350, 600.0) == "u235_600.ace"
    assert name(952420, 300.0) == "am242.ace"
    assert name(952421, 300.0) == "am242m.ace"
    assert libraries[10010][300.0] == str((spaced / "h 1.ace").resolve())


def test_find_xsdata_entry_selects_temperature(tmp_path):
    for name in ("u235_300.ace", "u235_600.ace"):
        (tmp_path / name).write_text("")
    libraries = {922350: {293.6: str(tmp_path / "u235_300.ace"), 600.0: str(tmp_path / "u235_600.ace")}}

    assert _find_xsdata_entry(libraries, 922350, 600, "lib.xsdata").endswith("u235_600.ace")
    assert _find_xsdata_entry(libraries, 922350, 293.6, "lib.xsdata").endswith("u235_300.ace")
    with pytest.raises(FileNotFoundError, match=r"at 300 K .*available for this nuclide: 293.6, 600 K"):
        _find_xsdata_entry(libraries, 922350, 300, "lib.xsdata")
    with pytest.raises(FileNotFoundError, match="available for this nuclide: none"):
        _find_xsdata_entry(libraries, 922351, 600, "lib.xsdata")


def test_to_ace_direct_xsdata_wrong_temperature_raises(assimilation_setup, tmp_path):
    """Regression test: the first xsdata entry of a nuclide used to be taken whatever its
    temperature, so a 300 K file was perturbed and written out as a 600 K one."""
    import shutil

    suite = assimilation_setup
    shutil.copy("data/1-H-1g-300.0", tmp_path / "1001.03c")
    xsdata_path = tmp_path / "lib.xsdata"
    xsdata_path.write_text(f"  1001.03c 1001.03c 1 1001 0 1.0 300 0 {tmp_path / '1001.03c'}\n")
    suite.xs_adjustment = pd.Series(
        [0.1], index=pd.MultiIndex.from_tuples([(10010, 102, 1.0, 2.0)], names=["ZAI", "MT", "E_min_eV", "E_max_eV"])
    )

    with pytest.raises(FileNotFoundError, match=r"ZAI=10010 at 600 K"):
        suite.to_ace_direct(out_dir=str(tmp_path / "out"), xsdata_path=str(xsdata_path), temperature=600)


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


def test_to_ace_direct_skips_mubar_with_warning(assimilation_setup, tmp_path):
    """Mubar (MT 34251) used to be routed to ACE.perturb, which raised a KeyError. It must
    be skipped with a warning while the other adjustments of the nuclide are applied."""
    import shutil

    from andalus.ace import ACE

    suite = assimilation_setup

    ace_dir = tmp_path / "ace"
    ace_dir.mkdir()
    shutil.copy("data/92235.03c", ace_dir / "92235.03c")

    source = ACE.read("data/92235.03c")
    energy = source.reactions[18].energies
    e_lo, e_hi = float(energy[10]) * 1e6, float(energy[50]) * 1e6
    suite.xs_adjustment = pd.Series(
        [0.2, 0.05],
        index=pd.MultiIndex.from_tuples(
            [(922350, 18, e_lo, e_hi), (922350, 34251, e_lo, e_hi)], names=["ZAI", "MT", "E_min_eV", "E_max_eV"]
        ),
    )

    with pytest.warns(UserWarning, match=r"MT 34251 \(U235\)"):
        written = suite.to_ace_direct(ace_dir=str(ace_dir), out_dir=str(tmp_path / "out"))

    result = ACE.read(written[0])
    in_bin = (energy * 1e6 > e_lo) & (energy * 1e6 <= e_hi)
    ratio = result.reactions[18].xs / source.reactions[18].xs
    np.testing.assert_allclose(ratio[in_bin], 1.2, rtol=1e-10)
    np.testing.assert_allclose(ratio[~in_bin], 1.0, rtol=1e-10)
    # Only the fission cross section and the totals it flows into changed
    np.testing.assert_array_equal(result.reactions[2].xs, source.reactions[2].xs)


def _flux_suite(fluxes, apps=()):
    """Build an AssimilationSuite whose cases carry the given flux vectors.

    ``fluxes`` maps benchmark titles to flux arrays and ``apps`` maps application
    titles to flux arrays. All cases share the same energy grid.
    """
    from andalus.application import Application, ApplicationSuite
    from andalus.benchmark import Benchmark, BenchmarkSuite
    from andalus.sensitivity import Sensitivity
    from andalus.spectrum import FluxSpectrum

    def make_flux(title, values):
        n = len(values)
        edges = np.logspace(-2, 7, n + 1)
        index = pd.MultiIndex.from_arrays([edges[:-1], edges[1:]], names=["E_min_eV", "E_max_eV"])
        return FluxSpectrum(
            pd.DataFrame({"flux": values, "flux_std": np.zeros(n)}, index=index),
            title=title,
        )

    def make_sens(title):
        index = pd.MultiIndex.from_tuples([(922350, 18, 1.0, 2.0)], names=["ZAI", "MT", "E_min_eV", "E_max_eV"])
        return Sensitivity(pd.DataFrame({title: [0.1], f"{title}_std": [0.01]}, index=index), title=title)

    benchmarks = {
        t: Benchmark(title=t, kind="keff", m=1.0, dm=0.002, c=1.0, dc=0.0002, s=make_sens(t), flux=make_flux(t, v))
        for t, v in fluxes.items()
    }
    applications = {
        t: Application(title=t, kind="keff", c=1.0, dc=0.0002, s=make_sens(t), flux=make_flux(t, v))
        for t, v in dict(apps).items()
    }
    return AssimilationSuite(
        benchmarks=BenchmarkSuite(benchmarks) if benchmarks else None,  # ty: ignore[invalid-argument-type]
        applications=ApplicationSuite(applications) if applications else None,
        covariances=None,  # ty: ignore[invalid-argument-type]
    )


class TestFluxSimMatrix:
    def test_shape_and_labels(self):
        suite = _flux_suite({"B1": [1.0, 2.0, 3.0], "B2": [3.0, 2.0, 1.0]}, apps={"A1": [1.0, 1.0, 1.0]})
        sim = suite.flux_sim_matrix()

        assert isinstance(sim, pd.DataFrame)
        assert sim.shape == (3, 3)
        assert list(sim.index) == list(sim.columns) == ["B1", "B2", "A1"]

    def test_diagonal_is_one_and_symmetric(self):
        suite = _flux_suite({"B1": [1.0, 2.0, 3.0], "B2": [3.0, 2.0, 1.0]}, apps={"A1": [0.5, 4.0, 1.0]})
        sim = suite.flux_sim_matrix()

        assert np.allclose(np.diag(sim), 1.0)
        assert np.allclose(sim.values, sim.values.T)
        assert sim.values.min() >= 0.0
        assert sim.values.max() <= 1.0 + 1e-12

    def test_known_cosine_values(self):
        suite = _flux_suite({"B1": [1.0, 0.0], "B2": [0.0, 1.0], "B3": [1.0, 1.0]})
        sim = suite.flux_sim_matrix()

        assert sim.loc["B1", "B2"] == pytest.approx(0.0)
        assert sim.loc["B1", "B3"] == pytest.approx(1 / np.sqrt(2))

    def test_scale_invariant(self):
        suite = _flux_suite({"B1": [1.0, 2.0, 3.0], "B2": [10.0, 20.0, 30.0]})
        assert suite.flux_sim_matrix().loc["B1", "B2"] == pytest.approx(1.0)

    def test_zero_flux_gives_nan(self):
        suite = _flux_suite({"B1": [1.0, 2.0], "B2": [0.0, 0.0]})
        sim = suite.flux_sim_matrix()

        assert np.isnan(sim.loc["B2", "B1"])
        assert np.isnan(sim.loc["B1", "B2"])
        assert np.isnan(sim.loc["B2", "B2"])
        assert sim.loc["B1", "B1"] == pytest.approx(1.0)

    def test_benchmarks_only(self):
        sim = _flux_suite({"B1": [1.0, 2.0], "B2": [2.0, 1.0]}).flux_sim_matrix()
        assert sim.shape == (2, 2)
        assert sim.loc["B1", "B2"] == pytest.approx(4.0 / 5.0)

    def test_missing_flux_raises(self):
        suite = _flux_suite({"B1": [1.0, 2.0]})
        object.__setattr__(suite.benchmarks["B1"], "flux", None)
        with pytest.raises(AssertionError, match="no flux spectrum"):
            suite.flux_sim_matrix()


def test_glls_experimental_correlation(assimilation_setup):
    """Correlated experiments enter the GLLS covariance and are carried to the posterior."""
    suite = assimilation_setup
    titles = suite.benchmarks.titles
    assert len(titles) >= 2
    pair = (titles[0], titles[1])

    correlated = AssimilationSuite(
        benchmarks=type(suite.benchmarks)(suite.benchmarks.benchmarks, exp_corr={pair: 0.8}),
        applications=suite.applications,
        covariances=suite.covariances,
    )

    cov = correlated._benchmark_covariance()
    base = suite._benchmark_covariance()
    rel = suite.benchmarks.dm / suite.benchmarks.c
    assert cov.loc[pair] - base.loc[pair] == pytest.approx(0.8 * rel[pair[0]] * rel[pair[1]])

    post = correlated.glls()
    assert post.benchmarks.exp_corr == {pair: 0.8}
    assert post.applications is not None
    assert np.abs(post.applications.c - suite.glls().applications.c).max() > 1e-8
    assert correlated.filter(lambda bm: True).benchmarks.exp_corr == {pair: 0.8}
