import os
import shutil

import pandas as pd
import pytest

from andalus import Covariance, CrossSectionMG
from andalus.scripts.make_library import build_library, main, remove_zais, zai_from_filename


@pytest.mark.parametrize(
    "name, zai",
    [
        ("n_92-U-235g.jeff", 922350),
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


@pytest.fixture
def workspace(tmp_path):
    """ENDF-6 stand-in plus ready-made ERRORR files, so that NJOY is not run."""
    endf6 = tmp_path / "endf6"
    errorr = tmp_path / "errorr"
    endf6.mkdir()
    errorr.mkdir()
    (endf6 / "n_92-U-235g.jeff").write_text("")
    for section in ("errorr31", "errorr33", "errorr34", "errorr35"):
        shutil.copy(f"data/u235.{section}", errorr / f"n_92-U-235g.{section}")
    return str(endf6), str(errorr), str(tmp_path / "lib.h5")


def test_build_library_xs_and_covariances(workspace):
    endf6, errorr, out = workspace
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
    chi = CrossSectionMG.from_errorr({"errorr35": f"{errorr}/n_92-U-235g.errorr35"}, zai=922350)
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
