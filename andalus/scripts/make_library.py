"""Build (or extend) an HDF5 nuclear data library from ENDF-6 files.

For every ENDF-6 evaluation in a directory, NJOY (through SANDY) is run to
produce a multigroup GROUPR file (GENDF) and ERRORR files. These are stored in
a directory. The multigroup data is read from the GENDF file and the
covariances from the ERRORR files, and both are written to a single HDF5
file with ``CrossSectionMG.to_hdf5`` and ``Covariance.to_hdf5``::

    zai_{ZAI}/xs/data
    zai_{ZAI}/covariances/data
    zai_{ZAI}/covariances_index/level_{i}

An existing HDF5 file is extended, not replaced. With ``--quantities xs`` only
the multigroup data is written, and its MT numbers are merged into the stored
table, so for example chi (MT 35018) can be added to an existing library.

Sections and the MT numbers they hold:

* ``gendf``: GROUPR output with the multigroup data of every reaction: all cross sections of
  MF3, nubar (MT 452, 455, 456), mubar (stored as 34251) and chi (stored as 35018). It exists
  for every evaluation, also those without covariance data, and is the source of the
  multigroup data whenever it is selected. ERRORR only writes the reactions it has a
  covariance for; without ``gendf`` the multigroup data is read from the ERRORR files.
* ``errorr31``: nubar (MT 452, 455, 456)
* ``errorr33``: cross sections (MT 1, 2, 4, 16, 18, 102, ...)
* ``errorr34``: first-order Legendre moment of the elastic angular distribution, i.e. mubar
  (MT 251, offset to 34251). Add it to an existing library with ``--sections errorr34
  --quantities xs covariances --merge-covariances``.
* ``errorr35``: fission spectrum chi (MT 18, offset to 35018). Only available
  for evaluations with MF35 covariance data.

Examples
--------
Multigroup data of all reactions and nuclides, added to an existing library::

    python -m andalus.scripts.make_library --endf6-dir endf6 --errorr-dir errorr \\
        --output jeff40.h5 --sections gendf --quantities xs --jobs 4

Chi only, read from ERRORR, for two nuclides, added to an existing library::

    python -m andalus.scripts.make_library --endf6-dir endf6 --errorr-dir errorr \\
        --output jeff40.h5 --sections errorr35 --quantities xs --zais 922350 922380

Everything the previous libraries contained, on the ECCO-33 grid::

    python -m andalus.scripts.make_library --endf6-dir endf6 --errorr-dir errorr \\
        --output jeff40.h5 --energy-grid ECCO33 --jobs 4
"""

__all__ = ["zai_from_filename", "process_endf6", "remove_zais", "build_library", "main"]

import argparse
import os
import re
import traceback
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import pandas as pd
import sandy
import tables

from andalus.covariance import Covariance
from andalus.cross_section import CrossSectionMG

GENDF = "gendf"  # GROUPR output, the source of the multigroup data
SECTIONS = (GENDF, "errorr31", "errorr33", "errorr34", "errorr35")
DEFAULT_SECTIONS = (GENDF, "errorr31", "errorr33", "errorr35")  # angular distribution (errorr34) is opt-in
QUANTITIES = ("xs", "covariances")

# ENDF-6 files (MF) in which an ERRORR section finds its covariance; MF32 (resonance parameters)
# is processed into the cross section covariance as well
_MF_NEEDED = {GENDF: {3}, "errorr31": {31}, "errorr33": {32, 33}, "errorr34": {34}, "errorr35": {35}}
# ERRORR section -> keyword of ``sandy.Endf6.get_errorr`` that switches it on
_SWITCH = {"errorr31": "nubar", "errorr33": "xs", "errorr34": "mubar", "errorr35": "chi"}
# JEFF-4.0 ``n_92-U-235g.jeff``, JEFF-3.3 ``92-U-235g.jeff33`` (state letter g/m/n)
_JEFF_NAME = re.compile(r"^(?:n_)?(\d+)-([A-Za-z]+)-(\d+)([gmn]?)\.\w+$")
# ENDF/B-VIII.1 ``n-092_U_235.endf``, ``n-073_Ta_180m1.endf`` (state m1, m2, ...)
_ENDFB_NAME = re.compile(r"^n-(\d+)_([A-Za-z]+)_(\d+)(?:m(\d+))?\.\w+$")
_ISOMER = {"": 0, "g": 0, "m": 1, "n": 2}


def _parse_name(filename: str) -> int | None:
    """Return the ZAI of a recognised ENDF-6 file name, else None."""
    name = os.path.basename(filename)
    match = _JEFF_NAME.match(name)
    if match is not None:
        z, _, a, state = match.groups()
        return int(z) * 10000 + int(a) * 10 + _ISOMER[state]
    match = _ENDFB_NAME.match(name)
    if match is not None:
        z, _, a, state = match.groups()
        return int(z) * 10000 + int(a) * 10 + int(state or 0)
    return None


def _nuclide_name(zai: int) -> str:
    """Name of a nuclide for the log, e.g. ``U235``; the free neutron (Z = 0) has no element symbol."""
    try:
        return sandy.zam.zam2nuclide(zai)
    except KeyError:
        return "n" if zai == 10 else "?"


def zai_from_filename(filename: str) -> int:
    """
    Extract the ZAI from an ENDF-6 file name of a JEFF or ENDF/B library.

    Parameters
    ----------
    filename : str
        File name or path. Supported patterns:

        * JEFF-4.0 ``n_92-U-235g.jeff`` and JEFF-3.3 ``92-U-235g.jeff33``. The letter after the
          mass number is the state: ``g`` ground (0), ``m`` first (1), ``n`` second (2).
        * ENDF/B-VIII.1 ``n-092_U_235.endf`` and ``n-073_Ta_180m1.endf``, where ``m1``, ``m2``
          are the metastable states.

        The element symbol is not searched for state letters, so ``Am``, ``Cm`` or ``Fm`` are
        not mistaken for metastable states.

    Returns
    -------
    int
        ``Z * 10000 + A * 10 + state``, e.g. 922350 for U-235 and 952421 for Am-242m.

    Raises
    ------
    ValueError
        If the name matches none of the supported patterns.
    """
    zai = _parse_name(filename)
    if zai is None:
        raise ValueError(f"Cannot extract a ZAI from file name '{filename}'.")
    return zai


def process_endf6(
    endf6_path: str,
    errorr_dir: str,
    sections: tuple[str, ...] = DEFAULT_SECTIONS,
    temperature: float = 300.0,
    err: float = 0.01,
    energy_grid: str = "ECCO33",
    overwrite: bool = False,
) -> dict[str, str]:
    """
    Run NJOY on one ENDF-6 file and store the GENDF and ERRORR files.

    Each section is processed separately: existing files are reused unless ``overwrite``
    is set, and sections that the evaluation has no data for (e.g. no MF34) are skipped. NJOY is
    only run if at least one section is left, once for the GENDF file and once for the ERRORR
    files.

    Parameters
    ----------
    endf6_path : str
        Path to the ENDF-6 file.
    errorr_dir : str
        Directory for the GENDF and ERRORR files, named ``{endf6 file stem}.{section}``.
    sections : tuple of str
        Sections to produce, a subset of ``SECTIONS``.
    temperature : float, default 300.0
        Temperature in K.
    err : float, default 0.01
        Reconstruction tolerance (fractional) for NJOY.
    energy_grid : str, default "ECCO33"
        Name of a grid in ``sandy.energy_grids`` (e.g. ``ECCO33``, ``SCALE238``).
    overwrite : bool, default False
        Run NJOY even if the files exist.

    Returns
    -------
    dict[str, str]
        Mapping of section name to file path, for the sections that exist
        (an evaluation without MF35 gives no ``errorr35``).
    """
    stem = os.path.splitext(os.path.basename(endf6_path))[0]
    paths = {key: os.path.join(errorr_dir, f"{stem}.{key}") for key in sections}

    # Only sections without an ERRORR file are processed, unless overwrite is set.
    todo = [key for key in sections if overwrite or not os.path.exists(paths[key])]
    if todo:
        endf6 = sandy.Endf6.from_file(endf6_path)
        mfs = set(endf6.get_records().MF.unique())
        todo = [key for key in todo if mfs & _MF_NEEDED[key]]  # skip sections the evaluation does not have
    if todo:
        ek = getattr(sandy.energy_grids, energy_grid)
        njoy_kws = dict(
            temperature=temperature,
            err=err,
            heatr=False,
            purr=False,
            gaspr=False,
            thermr=False,
            groupr_kws=dict(ek=ek),
            suppress_njoy_output=True,
            suppress_warnings=True,
        )
        os.makedirs(errorr_dir, exist_ok=True)
        if GENDF in todo:
            endf6.get_gendf(**njoy_kws).to_file(paths[GENDF])
        if set(todo) - {GENDF}:
            switches = {_SWITCH[key]: (None if key in todo else False) for key in _SWITCH}
            errorrs = endf6.get_errorr(errorr_kws=dict(ek=ek), **njoy_kws, **switches)
            for key, errorr in errorrs.items():
                if key in todo:
                    errorr.to_file(paths[key])

    return {key: path for key, path in paths.items() if os.path.exists(path)}


def remove_zais(output: str, zais: list[int]) -> list[int]:
    """
    Delete the groups of ZAIs from an HDF5 library (cross sections and covariances).

    The file size is not reduced; use ``ptrepack`` to reclaim the space.

    Parameters
    ----------
    output : str
        HDF5 library.
    zais : list of int
        ZAIs to delete. ZAIs that are not stored are ignored.

    Returns
    -------
    list[int]
        The ZAIs that were deleted.
    """
    removed = []
    if not os.path.exists(output):
        return removed
    with tables.open_file(output, "a") as h5:
        for zai in zais:
            name = f"/zai_{zai}"
            if name in h5:
                h5.remove_node(name, recursive=True)
                removed.append(zai)
    return removed


def _job(args: tuple) -> tuple[int, dict[str, str] | None, str]:
    """Worker for ``process_endf6`` that returns errors as text, to be used in a process pool."""
    zai, kwargs = args
    try:
        return zai, process_endf6(**kwargs), ""
    except Exception:
        return zai, None, traceback.format_exc(limit=3)


def build_library(
    endf6_dir: str,
    errorr_dir: str,
    output: str,
    sections: tuple[str, ...] = DEFAULT_SECTIONS,
    quantities: tuple[str, ...] = QUANTITIES,
    mts: list[int] | None = None,
    temperature: float = 300.0,
    err: float = 0.01,
    energy_grid: str = "ECCO33",
    zais: list[int] | None = None,
    label: str = "xs",
    jobs: int = 1,
    overwrite: bool = False,
    replace: bool = False,
    remove: list[int] | None = None,
    merge_covariances: bool = False,
) -> dict[str, list[int]]:
    """
    Process ENDF-6 files and write the results to an HDF5 library.

    Parameters
    ----------
    endf6_dir : str
        Directory with ENDF-6 files, see :func:`zai_from_filename` for the supported names.
    errorr_dir : str
        Directory for the GENDF and ERRORR files.
    output : str
        HDF5 file, created or extended.
    sections : tuple of str
        Sections to process, a subset of ``SECTIONS``. With ``"gendf"`` the multigroup data is
        read from the GROUPR output (every reaction, also for nuclides without covariances),
        otherwise from the ERRORR sections (only reactions with a covariance).
    quantities : tuple of str
        ``"xs"`` for multigroup data, ``"covariances"`` for covariances. A stored
        covariance is replaced by one built from the selected ``sections`` only,
        unless ``merge_covariances`` is set. Multigroup
        data is merged per MT, see ``CrossSectionMG.to_hdf5``.
    mts : list of int, optional
        Keep only these MT numbers (after offsetting, e.g. 35018).
    temperature : float, default 300.0
        Temperature in K.
    err : float, default 0.01
        Reconstruction tolerance (fractional) for NJOY.
    energy_grid : str, default "ECCO33"
        Name of a grid in ``sandy.energy_grids``.
    zais : list of int, optional
        Only process these ZAIs. Default: every file in ``endf6_dir``.
    label : str, default "xs"
        Column name for new multigroup tables (stored tables keep their name).
    jobs : int, default 1
        Number of NJOY runs in parallel. HDF5 writing is always sequential.
    overwrite : bool, default False
        Run NJOY again even if the GENDF and ERRORR files exist.
    replace : bool, default False
        Delete the stored data of a ZAI right before writing its new data, instead of
        merging into it. ZAIs for which nothing is produced keep their stored data.
    remove : list of int, optional
        ZAIs to delete from the output before anything is written, for example keys
        that were stored under a wrong ZAI.

    merge_covariances : bool, default False
        Merge new covariances into the stored ones, MT by MT, instead of replacing them, see
        ``Covariance.to_hdf5``. Use it to add a section such as ``errorr34`` to a library.

    Returns
    -------
    dict[str, list[int]]
        ZAIs by outcome: ``"written"``, ``"no_data"`` (no requested section in
        the evaluation) and ``"failed"``.
    """
    unknown = (set(sections) - set(SECTIONS)) | (set(quantities) - set(QUANTITIES))
    if unknown:
        raise ValueError(f"Unknown sections or quantities: {sorted(unknown)}")

    candidates = {}
    for name in sorted(os.listdir(endf6_dir)):
        zai = _parse_name(name)
        if zai is None:
            continue
        if zai in candidates:
            raise ValueError(f"Files '{os.path.basename(candidates[zai])}' and '{name}' have the same ZAI {zai}.")
        candidates[zai] = os.path.join(endf6_dir, name)
    if zais is not None:
        missing = sorted(set(zais) - set(candidates))
        if missing:
            raise FileNotFoundError(f"No ENDF-6 file in '{endf6_dir}' for ZAIs {missing}.")
        candidates = {zai: candidates[zai] for zai in zais}

    log_path = os.path.splitext(output)[0] + "_make_library.log"

    def log(message: str):
        print(message, flush=True)
        with open(log_path, "a") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")

    log(
        f"Processing {len(candidates)} ZAIs | sections {list(sections)} | quantities {list(quantities)} | "
        f"T={temperature} K | err={err} | grid {energy_grid} | jobs {jobs}"
    )

    tasks = [
        (
            zai,
            dict(
                endf6_path=path,
                errorr_dir=errorr_dir,
                sections=tuple(sections),
                temperature=temperature,
                err=err,
                energy_grid=energy_grid,
                overwrite=overwrite,
            ),
        )
        for zai, path in candidates.items()
    ]

    outcome: dict[str, list[int]] = {"written": [], "no_data": [], "failed": []}

    if remove:
        log(f"Removed stored ZAIs {remove_zais(output, remove)} from {os.path.basename(output)}")

    def handle(zai: int, files: dict[str, str] | None, error: str):
        if files is None:
            outcome["failed"].append(zai)
            log(f"ZAI {zai} FAILED: {error.strip().splitlines()[-1] if error else 'unknown error'}")
            return
        if not files:
            outcome["no_data"].append(zai)
            log(f"ZAI {zai}: no requested section in the evaluation, nothing written")
            return
        try:
            if replace:
                remove_zais(output, [zai])
            errorr_files = {key: path for key, path in files.items() if key != GENDF}
            if "xs" in quantities:
                if GENDF in files:  # GROUPR has every reaction, ERRORR only those with a covariance
                    xs = CrossSectionMG.from_gendf(files[GENDF], zai, mts=mts, temperature=temperature, label=label)
                else:
                    xs = CrossSectionMG.from_errorr(errorr_files, zai, mts=mts, temperature=temperature, label=label)
                xs.to_hdf5(output, merge=True)
            if "covariances" in quantities and errorr_files:
                cov = Covariance.from_errorr(errorr_files, zai, mts=mts, temperature=temperature, err=err)
                cov.to_hdf5(output, merge=merge_covariances)
        except Exception as exc:
            outcome["failed"].append(zai)
            log(f"ZAI {zai} FAILED while writing: {exc!r}")
            return
        outcome["written"].append(zai)
        log(f"ZAI {zai} ({_nuclide_name(zai)}): wrote {sorted(files)}")

    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for zai, files, error in pool.map(_job, tasks):
                handle(zai, files, error)
    else:
        for task in tasks:
            handle(*_job(task))

    if os.path.exists(output):
        with tables.open_file(output, "a") as h5:
            h5.root._v_attrs.energy_grid = energy_grid
            h5.root._v_attrs.temperature = temperature
            h5.root._v_attrs.err = err
            h5.root._v_attrs.processing_timestamp = pd.Timestamp.now().isoformat()

    n_written, n_no_data, n_failed = (len(outcome[k]) for k in ("written", "no_data", "failed"))
    log(f"Done: {n_written} written, {n_no_data} without data, {n_failed} failed")
    return outcome


def main(argv: list[str] | None = None) -> int:
    """Command line entry point, see the module docstring."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--endf6-dir", required=True, help="directory with ENDF-6 files (n_92-U-235g.jeff)")
    parser.add_argument("--errorr-dir", required=True, help="directory for the GENDF and ERRORR files")
    parser.add_argument("--output", required=True, help="HDF5 library to create or extend")
    parser.add_argument("--sections", nargs="+", default=list(DEFAULT_SECTIONS), choices=SECTIONS)
    parser.add_argument("--quantities", nargs="+", default=list(QUANTITIES), choices=QUANTITIES)
    parser.add_argument("--mts", nargs="+", type=int, help="keep only these MT numbers (e.g. 2 18 102 456 34251 35018)")
    parser.add_argument("--temperature", type=float, default=300.0, help="temperature in K")
    parser.add_argument("--err", type=float, default=0.01, help="NJOY reconstruction tolerance (fractional)")
    parser.add_argument("--energy-grid", default="ECCO33", help="name in sandy.energy_grids")
    parser.add_argument("--zais", nargs="+", type=int, help="only process these ZAIs")
    parser.add_argument("--label", default="xs", help="column name of new multigroup tables")
    parser.add_argument("--jobs", type=int, default=1, help="parallel NJOY runs")
    parser.add_argument("--overwrite", action="store_true", help="rerun NJOY even if GENDF and ERRORR files exist")
    parser.add_argument("--replace", action="store_true", help="replace stored data of processed ZAIs, do not merge")
    parser.add_argument(
        "--merge-covariances", action="store_true", help="merge new covariances into stored ones, MT by MT"
    )
    parser.add_argument("--remove-zais", nargs="+", type=int, help="delete these ZAIs from the output first")
    args = parser.parse_args(argv)

    outcome = build_library(
        endf6_dir=args.endf6_dir,
        errorr_dir=args.errorr_dir,
        output=args.output,
        sections=tuple(args.sections),
        quantities=tuple(args.quantities),
        mts=args.mts,
        temperature=args.temperature,
        err=args.err,
        energy_grid=args.energy_grid,
        zais=args.zais,
        label=args.label,
        jobs=args.jobs,
        overwrite=args.overwrite,
        replace=args.replace,
        remove=args.remove_zais,
        merge_covariances=args.merge_covariances,
    )
    return 1 if outcome["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
