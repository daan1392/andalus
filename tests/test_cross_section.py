import numpy as np
import pandas as pd
import pytest

from andalus import AssimilationSuite, CrossSectionMG

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
        out = new.delta_response(s, ref)
        # S is relative: 10 % increase everywhere -> 0.1 * sum(S), independent of barn magnitude
        np.testing.assert_allclose(out["case"], 0.1 * s["case"].sum())

    def test_by_reaction(self):
        ref = _make([1.0, 2.0, 10.0, 20.0])
        new = _make([1.1, 2.2, 10.0, 20.0])
        s = pd.DataFrame({"case": [1.0, 1.0, 1.0, 1.0]}, index=ref.index)
        out = new.delta_response(s, ref, by="reaction")
        np.testing.assert_allclose(out.loc[(922350, 2), "case"], 0.2)
        np.testing.assert_allclose(out.loc[(922350, 18), "case"], 0.0)

    def test_invalid_by(self):
        ref = _make([1.0] * 4)
        with pytest.raises(ValueError):
            ref.delta_response(pd.DataFrame(index=ref.index), ref, by="nope")

    def test_no_sensitivity_overlap_raises(self):
        ref = _make([1.0] * 4)
        s = pd.DataFrame({"c": [1.0]}, index=pd.MultiIndex.from_tuples([(1, 1, 0.0, 1.0)], names=ref.index.names))
        with pytest.raises(ValueError, match="No sensitivity bins"):
            ref.delta_response(s, ref)


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
    suite.xs = xs
    scaled = CrossSectionMG(xs * 1.01)
    out = suite.delta_response(xs)  # identical -> zero
    np.testing.assert_allclose(out, 0.0)
    dk = scaled.delta_response(suite.s, xs)
    sens = suite.s.reindex(xs.index, fill_value=0.0).sum(axis=0)
    np.testing.assert_allclose(dk, 0.01 * sens, rtol=1e-10)


def test_suite_without_xs_raises():
    suite = AssimilationSuite.from_yaml("data/config.yaml")
    assert suite.xs is None
    with pytest.raises(ValueError, match="No multigroup"):
        suite.delta_response(None)
