import numpy as np
import pandas as pd
import pytest

from andalus import AssimilationSuite, CrossSectionMG, delta_response

ERRORR = {
    "errorr31": "data/u235.errorr31",
    "errorr33": "data/u235.errorr33",
    "errorr34": "data/u235.errorr34",
    "errorr35": "data/u235.errorr35",
}


@pytest.fixture(scope="module")
def xs():
    return CrossSectionMG.from_errorr(ERRORR, zai=922350, label="lib")


def _make(values, mts=(2, 18)):
    groups = [(1e-5, 1.0), (1.0, 2e7)]
    tuples = [(922350, mt, lo, hi) for mt in mts for lo, hi in groups]
    idx = pd.MultiIndex.from_tuples(tuples, names=["ZAI", "MT", "E_min_eV", "E_max_eV"])
    return CrossSectionMG(pd.DataFrame({"lib": values}, index=idx))


class TestFromErrorr:
    def test_index_and_mts(self, xs):
        assert list(xs.index.names) == ["ZAI", "MT", "E_min_eV", "E_max_eV"]
        mts = set(xs.index.get_level_values("MT"))
        assert {2, 18, 102, 456, 35018}.issubset(mts)
        assert xs.label == "lib"
        assert xs.zais == [922350]

    def test_33_groups_per_mt(self, xs):
        assert (xs.groupby(level="MT").size() == 33).all()

    def test_values_match_sandy(self, xs):
        import sandy

        ref = sandy.Errorr.from_file(ERRORR["errorr33"]).get_xs(mts=[18]).data.iloc[:, 0].to_numpy()
        np.testing.assert_allclose(xs.xs((922350, 18), level=("ZAI", "MT")).to_numpy().ravel(), ref)

    def test_mts_filter(self):
        x = CrossSectionMG.from_errorr(ERRORR, zai=922350, mts=[18])
        assert set(x.index.get_level_values("MT")) == {18}


class TestRelativeDifference:
    def test_units_relative(self):
        ref = _make([1.0, 2.0, 10.0, 20.0])
        new = _make([1.1, 2.0, 10.0, 22.0])
        rel = new.relative_difference(ref)
        np.testing.assert_allclose(rel.to_numpy(), [0.1, 0.0, 0.0, 0.1])

    def test_zero_reference_gives_zero(self):
        ref = _make([0.0, 2.0, 10.0, 20.0])
        new = _make([5.0, 2.0, 10.0, 20.0])
        rel = new.relative_difference(ref)
        assert np.isfinite(rel).all()
        assert rel.iloc[0] == 0.0

    def test_no_overlap_raises(self):
        a = _make([1.0] * 4)
        b = _make([1.0] * 4, mts=(102, 456))
        with pytest.raises(ValueError, match="No common"):
            a.relative_difference(b)


class TestDeltaResponse:
    def test_uniform_scaling_equals_scaled_sensitivity_sum(self):
        ref = _make([1.0, 2.0, 10.0, 20.0])
        new = CrossSectionMG(ref * 1.1)
        s = pd.DataFrame({"case": [0.1, 0.2, -0.3, 0.4]}, index=ref.index)
        out = delta_response(ref, s, new)
        # S is relative: 10 % increase everywhere -> 0.1 * sum(S), independent of barn magnitude
        np.testing.assert_allclose(out["case"], 0.1 * s["case"].sum())

    def test_by_reaction(self):
        ref = _make([1.0, 2.0, 10.0, 20.0])
        new = _make([1.1, 2.2, 10.0, 20.0])
        s = pd.DataFrame({"case": [1.0, 1.0, 1.0, 1.0]}, index=ref.index)
        out = delta_response(ref, s, new, by=["ZAI", "MT"])
        np.testing.assert_allclose(out.loc[(922350, 2), "case"], 0.2)
        np.testing.assert_allclose(out.loc[(922350, 18), "case"], 0.0)

    def test_warns_about_uncovered_sensitivity_bins(self):
        ref = _make([1.0, 2.0, 10.0, 20.0])
        extra = pd.MultiIndex.from_tuples(
            [(922350, 35018, 1e-5, 1.0), (922350, 35018, 1.0, 2e7), (922380, 18, 1e-5, 1.0)],
            names=ref.index.names,
        )
        s = pd.DataFrame({"case": [0.1] * 4}, index=ref.index)
        s = pd.concat([s, pd.DataFrame({"case": [0.5, -0.9, 0.0]}, index=extra)])
        with pytest.warns(
            UserWarning, match=r"2 sensitivity bins.*ZAI 922350 MT 35018 \(2 bins, max \|S\| = 0.9\)"
        ) as rec:
            delta_response(ref, s, ref)
        # the zero-sensitivity uncovered bin (ZAI 922380) is not reported
        assert "922380" not in str(rec[0].message)

    def test_no_warning_when_fully_covered(self, recwarn):
        ref = _make([1.0, 2.0, 10.0, 20.0])
        s = pd.DataFrame({"case": [0.1] * 4}, index=ref.index)
        delta_response(ref, s, ref)
        assert not [w for w in recwarn if issubclass(w.category, UserWarning)]

    @staticmethod
    def _two_zai_case():
        groups = [(1e-5, 1.0), (1.0, 2e7)]
        tuples = [(z, mt, lo, hi) for z in (922350, 922380) for mt in (2, 18) for lo, hi in groups]
        idx = pd.MultiIndex.from_tuples(tuples, names=["ZAI", "MT", "E_min_eV", "E_max_eV"])
        ref = CrossSectionMG(pd.DataFrame({"lib": np.arange(1.0, 9.0)}, index=idx))
        new = CrossSectionMG(pd.DataFrame({"lib": np.arange(1.0, 9.0) * np.linspace(1.0, 1.7, 8)}, index=idx))
        s = pd.DataFrame({"a": np.linspace(0.1, 0.8, 8), "b": np.linspace(-0.4, 0.3, 8)}, index=idx)
        return ref, new, s

    @pytest.mark.parametrize(
        "by, levels",
        [
            ("ZAI", ["ZAI"]),
            (["ZAI"], ["ZAI"]),
            ("nuclide", ["ZAI"]),
            (["mt"], ["MT"]),
            (["ZAI", "MT"], ["ZAI", "MT"]),
            (["zai", "mt", "E_min_eV"], ["ZAI", "MT", "E_min_eV", "E_max_eV"]),
            (["ZAI", "E_max_eV"], ["ZAI", "E_max_eV", "E_min_eV"]),
            (["MT", "ZAI"], ["MT", "ZAI"]),
            (["ZAI", "ZAI", "MT"], ["ZAI", "MT"]),
            (("ZAI", "MT"), ["ZAI", "MT"]),
        ],
    )
    def test_by_breakdowns_add_up_to_total(self, by, levels):
        ref, new, s = self._two_zai_case()
        total = delta_response(ref, s, new)
        out = delta_response(ref, s, new, by=by)
        assert list(out.index.names) == levels
        np.testing.assert_allclose(out.sum(axis=0), total)

    def test_by_zai_values(self):
        ref, new, s = self._two_zai_case()
        rel = new.relative_difference(ref)
        out = delta_response(ref, s, new, by=["ZAI"])
        expected = s.mul(rel, axis=0).xs(922380, level="ZAI").sum()
        np.testing.assert_allclose(out.loc[922380], expected)

    def test_by_energy_matches_reaction_sum(self):
        ref, new, s = self._two_zai_case()
        by_energy = delta_response(ref, s, new, by=["E_min_eV", "E_max_eV"])
        assert len(by_energy) == 2
        by_bin = delta_response(ref, s, new, by=["ZAI", "MT", "E_min_eV"])
        np.testing.assert_allclose(by_bin.groupby(level=["E_min_eV", "E_max_eV"]).sum(), by_energy)

    @pytest.mark.parametrize("bad", ["nope", ["ZAI", "nope"], [], 3, "reaction", "energy"])
    def test_invalid_by_entries(self, bad):
        ref, new, s = self._two_zai_case()
        with pytest.raises(ValueError):
            delta_response(ref, s, new, by=bad)

    def test_invalid_by(self):
        ref = _make([1.0] * 4)
        with pytest.raises(ValueError):
            delta_response(ref, pd.DataFrame(index=ref.index), ref, by="nope")

    def test_no_sensitivity_overlap_raises(self):
        ref = _make([1.0] * 4)
        s = pd.DataFrame({"c": [1.0]}, index=pd.MultiIndex.from_tuples([(1, 1, 0.0, 1.0)], names=ref.index.names))
        with pytest.raises(ValueError, match="No sensitivity bins"):
            delta_response(ref, s, ref)


def test_hdf5_roundtrip(xs, tmp_path):
    path = str(tmp_path / "xs.h5")
    xs.to_hdf5(path)
    back = CrossSectionMG.from_hdf5(path)
    pd.testing.assert_frame_equal(pd.DataFrame(back), pd.DataFrame(xs), check_names=True)
    assert CrossSectionMG.from_hdf5(path, zais=[1]).empty
    only = CrossSectionMG.from_hdf5(path, mts=[18])
    assert set(only.index.get_level_values("MT")) == {18}


def test_from_dict_multiple_zais(xs):
    other = CrossSectionMG(pd.DataFrame(xs).rename(index={922350: 922380}, level="ZAI"))
    combined = CrossSectionMG.from_zai_dict({922350: xs, 922380: other})
    assert combined.zais == [922350, 922380]


def test_suite_delta_response_with_real_sensitivities(xs):
    suite = AssimilationSuite.from_yaml("data/config.yaml")
    suite.xs = suite.prior_xs = xs
    scaled = CrossSectionMG(xs * 1.01)
    out = suite.delta_response(xs)  # identical -> zero
    np.testing.assert_allclose(out, 0.0)
    dk = suite.delta_response(scaled)
    np.testing.assert_allclose(dk, delta_response(xs, suite.s, scaled))
    sens = suite.s.reindex(xs.index, fill_value=0.0).sum(axis=0)
    np.testing.assert_allclose(dk, 0.01 * sens, rtol=1e-10)


def test_suite_without_xs_raises():
    suite = AssimilationSuite.from_yaml("data/config.yaml")
    assert suite.xs is None
    with pytest.raises(ValueError, match="No multigroup"):
        suite.delta_response(None)


class TestAdjusted:
    def test_scales_and_leaves_other_bins(self):
        ref = _make([1.0, 2.0, 10.0, 20.0])
        adj = pd.Series([0.1, -0.5], index=ref.index[[0, 3]])
        post = ref.adjusted(adj)
        assert post.label == "posterior"
        np.testing.assert_allclose(post["posterior"], [1.1, 2.0, 10.0, 10.0])


class TestSuiteAssimilation:
    @pytest.fixture
    def suites(self, xs):
        prior = AssimilationSuite.from_yaml("data/config.yaml")
        prior.xs = xs
        prior.prior_xs = xs
        return prior, prior.glls()

    def test_prior_suite_remembers_itself(self):
        suite = AssimilationSuite.from_yaml("data/config.yaml")
        assert suite.xs is None and suite.prior_xs is None

    def test_post_init_sets_prior(self, xs):
        suite = AssimilationSuite.from_yaml("data/config.yaml")
        suite2 = AssimilationSuite(suite.benchmarks, suite.applications, suite.covariances, xs=xs)
        assert suite2.prior_xs is xs

    def test_posterior_stores_prior_posterior_and_adjustment(self, suites, xs):
        prior, post = suites
        assert post.is_posterior and not prior.is_posterior
        pd.testing.assert_frame_equal(pd.DataFrame(post.prior_xs), pd.DataFrame(xs))
        assert post.xs.label == "posterior"
        expected = xs.adjusted(post.xs_adjustment)
        np.testing.assert_allclose(post.xs["posterior"], expected["posterior"])
        assert not np.allclose(post.xs["posterior"], xs["lib"])

    def test_posterior_xs_matches_adjustment(self, suites, xs):
        _, post = suites
        dx = post.xs_adjustment.loc[922350]
        common = post.xs.index.droplevel("ZAI").intersection(dx.index)
        prior = xs.loc[922350, "lib"].loc[common]
        nonzero = prior != 0  # zero bins stay zero whatever the adjustment
        ratio = post.xs.loc[922350, "posterior"].loc[common][nonzero] / prior[nonzero]
        np.testing.assert_allclose(ratio, 1.0 + dx.loc[common][nonzero])

    def test_delta_response_matches_glls_shift(self, suites, xs):
        prior, post = suites
        # first-order effect of the adjustment on the U-235 part of the response
        s235 = prior.s.loc[[922350]]
        dk = delta_response(post.prior_xs, s235, post.xs)
        dx = post.xs_adjustment.loc[922350]
        s_c = s235.loc[922350].reindex(dx.index, fill_value=0.0)
        np.testing.assert_allclose(dk, s_c.T @ dx, atol=1e-12)

    def test_filter_keeps_prior_xs(self, suites):
        _, post = suites
        from andalus import Chi2Filter

        filtered = post.filter(Chi2Filter(threshold=1e6))
        assert filtered.prior_xs is post.prior_xs
