import os
import shutil

import pandas as pd
import pytest
import tables

from andalus import Covariance, CrossSectionMG
from andalus.scripts import make_library as ml
from andalus.scripts.make_library import build_library, main, remove_zais, zai_from_filename


@pytest.mark.parametrize(
    "name, zai",
    [
        ("n_92-U-235g.jeff", 922350),
        ("n-092_U_235.endf", 922350),
        ("n-073_Ta_180m1.endf", 731801),
        ("n-095_Am_242m1.endf", 952421),
        ("n-095_Am_242.endf", 952420),
        ("n-000_n_001.endf", 10),
        ("n-001_H_001.endf", 10010),
        ("92-U-235g.jeff33", 922350),
        ("95-Am-242m.jeff33", 952421),
        ("n_1-H-001g.jeff", 10010),
        ("n_95-Am-242m.jeff", 952421),
        ("n_95-Am-241g.jeff", 952410),  # "Am" is not a metastable state
        ("n_96-Cm-246g.jeff", 962460),
        ("n_100-Fm-255g.jeff", 1002550),
        ("C:/some/dir/n_94-Pu-239g.jeff", 942390),
    ],
)
def test_zai_from_filename(name, zai):
    assert zai_from_filename(name) == zai


def test_zai_from_filename_invalid():
    with pytest.raises(ValueError):
        zai_from_filename("u235.endf")


def _cache(errorr, energy_grid="ECCO33", temperature=300.0, err=0.01):
    """NJOY file directory for the given settings (the defaults of build_library)."""
    return ml.njoy_cache_dir(str(errorr), energy_grid, temperature, err)


def _stage(errorr, **settings):
    """Put ready-made GENDF and ERRORR files where a run with ``settings`` looks for them."""
    cache = _cache(errorr, **settings)
    os.makedirs(cache, exist_ok=True)
    for section in ("gendf", "errorr31", "errorr33", "errorr34", "errorr35"):
        shutil.copy(f"data/u235.{section}", os.path.join(cache, f"n_92-U-235g.{section}"))


@pytest.fixture
def workspace(tmp_path):
    """ENDF-6 stand-in plus ready-made GENDF and ERRORR files, so that NJOY is not run."""
    endf6 = tmp_path / "endf6"
    errorr = tmp_path / "errorr"
    endf6.mkdir()
    (endf6 / "n_92-U-235g.jeff").write_text("")
    _stage(errorr)
    return str(endf6), str(errorr), str(tmp_path / "lib.h5")


def test_build_library_xs_and_covariances(workspace):
    endf6, errorr, out = workspace
    _stage(errorr, err=0.02)
    outcome = build_library(endf6, errorr, out, mts=[2, 18, 102, 456, 35018], label="test", err=0.02)
    assert outcome == {"written": [922350], "no_data": [], "failed": []}

    xs = CrossSectionMG.from_hdf5(out)
    assert xs.zais == [922350] and xs.label == "test"
    assert set(xs.index.get_level_values("MT")) == {2, 18, 102, 456, 35018}

    cov = Covariance.from_hdf5(out, zai=922350)
    assert not cov.empty
    assert cov.err == 0.02

    with pd.HDFStore(out, mode="r") as store:
        assert {"zai_922350/xs/data", "zai_922350/covariances/data"} <= {k.strip("/") for k in store.keys()}
    assert os.path.exists(out.replace(".h5", "_make_library.log"))


def test_chi_only_is_merged_into_existing_library(workspace):
    endf6, errorr, out = workspace
    build_library(endf6, errorr, out, sections=("errorr33",), quantities=("xs",), label="lib", mts=[18, 102])
    build_library(endf6, errorr, out, sections=("errorr35",), quantities=("xs",), label="other")

    xs = CrossSectionMG.from_hdf5(out)
    assert xs.label == "lib"  # stored column name is kept
    assert set(xs.index.get_level_values("MT")) == {18, 102, 35018}
    chi = xs.xs((922350, 35018), level=("ZAI", "MT"))
    assert chi["lib"].sum() == pytest.approx(1.0, abs=1e-6)


def test_covariances_not_written_when_not_requested(workspace):
    endf6, errorr, out = workspace
    build_library(endf6, errorr, out, sections=("errorr35",), quantities=("xs",))
    with pd.HDFStore(out, mode="r") as store:
        assert not [k for k in store.keys() if "covariances" in k]


def test_to_hdf5_replaces_without_merge(workspace, tmp_path):
    endf6, errorr, out = workspace
    build_library(endf6, errorr, out, sections=("errorr33",), quantities=("xs",))
    chi = CrossSectionMG.from_errorr({"errorr35": f"{_cache(errorr)}/n_92-U-235g.errorr35"}, zai=922350)
    chi.to_hdf5(out)  # merge=False replaces the table
    assert set(CrossSectionMG.from_hdf5(out).index.get_level_values("MT")) == {35018}


def test_errors(workspace):
    endf6, errorr, out = workspace
    with pytest.raises(FileNotFoundError):
        build_library(endf6, errorr, out, zais=[942390])
    with pytest.raises(ValueError, match="Unknown"):
        build_library(endf6, errorr, out, sections=("errorr99",))


def test_cli(workspace):
    endf6, errorr, out = workspace
    code = main(
        [
            "--endf6-dir",
            endf6,
            "--errorr-dir",
            errorr,
            "--output",
            out,
            "--sections",
            "errorr35",
            "--quantities",
            "xs",
            "--zais",
            "922350",
            "--temperature",
            "300",
            "--err",
            "0.01",
        ]
    )
    assert code == 0
    assert CrossSectionMG.from_hdf5(out).zais == [922350]


def test_replace_drops_stale_mts(workspace):
    endf6, errorr, out = workspace
    build_library(endf6, errorr, out, sections=("errorr33",), quantities=("xs",), mts=[2, 18, 102])
    build_library(endf6, errorr, out, sections=("errorr33",), quantities=("xs",), mts=[18], replace=True)
    assert set(CrossSectionMG.from_hdf5(out).index.get_level_values("MT")) == {18}


def test_remove_zais(workspace):
    endf6, errorr, out = workspace
    build_library(endf6, errorr, out, sections=("errorr33",), quantities=("xs",))
    CrossSectionMG.from_hdf5(out).rename(index={922350: 952411}, level="ZAI").to_hdf5(out)
    assert remove_zais(out, [952411, 1]) == [952411]
    assert CrossSectionMG.from_hdf5(out).zais == [922350]
    assert remove_zais(out + ".missing", [1]) == []


def test_remove_option_in_build(workspace):
    endf6, errorr, out = workspace
    build_library(endf6, errorr, out, sections=("errorr33",), quantities=("xs",))
    CrossSectionMG.from_hdf5(out).rename(index={922350: 952411}, level="ZAI").to_hdf5(out)
    build_library(endf6, errorr, out, sections=("errorr35",), quantities=("xs",), remove=[952411])
    assert CrossSectionMG.from_hdf5(out).zais == [922350]


def test_duplicate_zai_in_directory(tmp_path):
    endf6 = tmp_path / "endf6"
    endf6.mkdir()
    (endf6 / "n_92-U-235g.jeff").write_text("")
    (endf6 / "n-092_U_235.endf").write_text("")
    with pytest.raises(ValueError, match="same ZAI"):
        build_library(str(endf6), str(tmp_path / "errorr"), str(tmp_path / "lib.h5"))


class _FakeErrorr:
    def __init__(self, source):
        self.source = source

    def to_file(self, path):
        shutil.copy(self.source, path)


class _FakeEndf6:
    """ENDF-6 stand-in that has the given MF numbers and records NJOY requests."""

    calls: list = []
    gendf_calls: list = []
    nubar_mts: tuple = ()
    mfs = (33, 34)

    @classmethod
    def from_file(cls, path):
        return cls()

    def get_records(self):
        mfs = [*self.mfs, *([1] * len(self.nubar_mts))]
        mts = [*([1] * len(self.mfs)), *self.nubar_mts]
        return pd.DataFrame({"MF": mfs, "MT": mts})

    def get_gendf(self, **kwargs):
        kwargs["groupr_input"] = ml.sandy.njoy._groupr_input(20, 21, 22, 9228, nubar=True)
        type(self).gendf_calls.append(kwargs)
        return _FakeErrorr("data/u235.gendf")

    def get_errorr(self, **kwargs):
        type(self).calls.append(kwargs)
        out = {}
        for key, switch in (("errorr31", "nubar"), ("errorr33", "xs"), ("errorr34", "mubar"), ("errorr35", "chi")):
            if kwargs[switch] is not False and int(key[-2:]) in self.mfs:
                out[key] = _FakeErrorr(f"data/u235.{key}")
        return out


@pytest.fixture
def fake_njoy(monkeypatch):
    _FakeEndf6.calls = []
    _FakeEndf6.gendf_calls = []
    _FakeEndf6.nubar_mts = ()
    _FakeEndf6.mfs = (33, 34)
    monkeypatch.setattr(ml.sandy, "Endf6", _FakeEndf6)
    return _FakeEndf6


def test_process_endf6_runs_only_missing_sections(workspace, fake_njoy):
    endf6, errorr, _ = workspace
    os.remove(f"{_cache(errorr)}/n_92-U-235g.errorr34")
    files = ml.process_endf6(f"{endf6}/n_92-U-235g.jeff", errorr, sections=("errorr33", "errorr34"))
    assert set(files) == {"errorr33", "errorr34"}
    assert len(fake_njoy.calls) == 1
    call = fake_njoy.calls[0]
    assert call["mubar"] is None and call["xs"] is False and call["nubar"] is False and call["chi"] is False


def test_process_endf6_skips_njoy_when_all_sections_exist(workspace, fake_njoy):
    endf6, errorr, _ = workspace
    ml.process_endf6(f"{endf6}/n_92-U-235g.jeff", errorr, sections=("errorr33", "errorr34"))
    assert fake_njoy.calls == []


def test_process_endf6_skips_sections_missing_in_evaluation(workspace, fake_njoy):
    endf6, errorr, _ = workspace
    os.remove(f"{_cache(errorr)}/n_92-U-235g.errorr34")
    fake_njoy.mfs = (33,)  # no MF34
    files = ml.process_endf6(f"{endf6}/n_92-U-235g.jeff", errorr, sections=("errorr34",))
    assert files == {}
    assert fake_njoy.calls == []


def test_add_legendre_to_existing_library(workspace):
    endf6, errorr, out = workspace
    build_library(endf6, errorr, out, sections=("errorr33",), mts=[2, 18], label="lib", err=0.01)
    build_library(endf6, errorr, out, sections=("errorr34",), merge_covariances=True, label="other", err=0.01)
    xs = CrossSectionMG.from_hdf5(out)
    assert set(xs.index.get_level_values("MT")) == {2, 18, 34251}
    assert xs.label == "lib"
    cov = Covariance.from_hdf5(out, zai=922350)
    assert {2, 18, 34251} <= set(cov.index.get_level_values("MT"))


def test_xs_come_from_gendf_by_default(workspace):
    endf6, errorr, out = workspace
    build_library(endf6, errorr, out, label="lib")
    mts = set(CrossSectionMG.from_hdf5(out).index.get_level_values("MT"))
    assert {51, 103, 107, 455, 34251, 35018} <= mts  # reactions ERRORR has no covariance, hence no data, for
    assert not Covariance.from_hdf5(out, zai=922350).empty


def test_nuclide_without_covariances_gets_xs(workspace):
    endf6, errorr, out = workspace
    for section in ("errorr31", "errorr33", "errorr34", "errorr35"):
        os.remove(f"{_cache(errorr)}/n_92-U-235g.{section}")
    outcome = build_library(endf6, errorr, out, sections=("gendf",))
    assert outcome["written"] == [922350]
    assert 18 in CrossSectionMG.from_hdf5(out).index.get_level_values("MT")
    with pd.HDFStore(out, mode="r") as store:
        assert not any("covariances" in key for key in store.keys())


def test_process_endf6_runs_groupr_for_gendf(workspace, fake_njoy):
    endf6, errorr, _ = workspace
    os.remove(f"{_cache(errorr)}/n_92-U-235g.gendf")
    fake_njoy.mfs = (3,)  # no covariance data at all
    files = ml.process_endf6(f"{endf6}/n_92-U-235g.jeff", errorr, sections=("gendf", "errorr33"))
    assert set(files) == {"gendf", "errorr33"}  # errorr33 was already there
    assert fake_njoy.calls == [] and len(fake_njoy.gendf_calls) == 1
    assert "errorr_kws" not in fake_njoy.gendf_calls[0]


def test_free_neutron_is_logged(tmp_path):
    """ENDF/B has an evaluation for the free neutron (Z = 0), which has no element symbol."""
    endf6, errorr = tmp_path / "endf6", tmp_path / "errorr"
    endf6.mkdir()
    os.makedirs(_cache(errorr))
    (endf6 / "n-000_n_001.endf").write_text("")
    shutil.copy("data/u235.gendf", os.path.join(_cache(errorr), "n-000_n_001.gendf"))
    outcome = build_library(str(endf6), str(errorr), str(tmp_path / "lib.h5"), sections=("gendf",), quantities=("xs",))
    assert outcome["written"] == [10]
    assert ml._nuclide_name(10) == "n" and ml._nuclide_name(922350) == "U235"


def test_groupr_is_asked_only_for_nubar_in_the_evaluation(workspace, fake_njoy):
    """Minor actinides without delayed nubar (MT455) make NJOY stop if it is requested."""
    endf6, errorr, _ = workspace
    os.remove(f"{_cache(errorr)}/n_92-U-235g.gendf")
    fake_njoy.mfs = (3,)
    fake_njoy.nubar_mts = (452, 456)
    ml.process_endf6(f"{endf6}/n_92-U-235g.jeff", errorr, sections=("gendf",))
    lines = fake_njoy.gendf_calls[0]["groupr_input"].split("\n")
    assert "3 452 /" in lines and "3 456 /" in lines and "3 455 /" not in lines
    assert lines[-3:] == ["0/", "0/", ""]  # the rest of the input is untouched
    # outside the run SANDY's input is back to normal
    assert "3 455 /" in ml.sandy.njoy._groupr_input(20, 21, 22, 9228, nubar=True)


def test_njoy_files_are_kept_per_settings(workspace, fake_njoy):
    """NJOY files used to be named only ``{stem}.{section}``, so a run with another energy
    grid silently reused the files of the previous grid."""
    endf6, errorr, _ = workspace
    assert _cache(errorr) == os.path.join(errorr, "ECCO33_300K_err0.01")
    files = ml.process_endf6(f"{endf6}/n_92-U-235g.jeff", errorr, sections=("errorr33",), energy_grid="SCALE238")
    assert len(fake_njoy.calls) == 1  # the ECCO33 file is not reused
    assert files == {"errorr33": os.path.join(_cache(errorr, energy_grid="SCALE238"), "n_92-U-235g.errorr33")}
    assert os.path.exists(os.path.join(_cache(errorr), "n_92-U-235g.errorr33"))  # and is kept


@pytest.mark.parametrize("setting", [{"energy_grid": "SCALE238"}, {"temperature": 600.0}, {"err": 0.001}])
def test_extending_library_with_other_settings_raises(workspace, setting):
    endf6, errorr, out = workspace
    build_library(endf6, errorr, out, sections=("errorr33",), quantities=("xs",))
    before = CrossSectionMG.from_hdf5(out)
    with pytest.raises(ValueError, match="cannot be mixed in one library"):
        build_library(endf6, errorr, out, sections=("errorr33",), quantities=("xs",), **setting)
    pd.testing.assert_frame_equal(CrossSectionMG.from_hdf5(out), before)
    with tables.open_file(out, "r") as h5:
        assert h5.root._v_attrs.energy_grid == "ECCO33" and h5.root._v_attrs.temperature == 300.0


def test_extending_library_with_same_settings_is_allowed(workspace):
    endf6, errorr, out = workspace
    build_library(endf6, errorr, out, sections=("errorr33",), quantities=("xs",), mts=[18])
    build_library(endf6, errorr, out, sections=("errorr33",), quantities=("xs",), mts=[102], temperature=300)
    assert set(CrossSectionMG.from_hdf5(out).index.get_level_values("MT")) == {18, 102}
