"""Reader for ASCII (Type 1) ACE files.

Parses the ACE directory (NXS/JXS arrays) per the ACE format
specification rather than inferring block boundaries heuristically.

References
----------
- ACE format specification: https://github.com/nucleardata/ACEFormat
- `endf-python <https://github.com/paulromano/endf-python>`_'s ``endf.ace``
  and ``endf.reaction`` modules were used as an independent reference to
  cross-check the NXS/JXS/XSS parsing and per-reaction threshold logic
  implemented here.
"""

import re
from dataclasses import dataclass

import numpy as np

# Fixed layout of an ASCII ACE header, in lines (0-indexed).
_N_HEADER_LINES = 2
_N_IZAW_LINES = 4  # 16 (IZ, AW) pairs, 8 values/line
_N_NXS_LINES = 2  # 16 integers, 8 values/line
_N_JXS_LINES = 4  # 32 integers, 8 values/line
_XSS_START_LINE = _N_HEADER_LINES + _N_IZAW_LINES + _N_NXS_LINES + _N_JXS_LINES


@dataclass
class ACEHeader:
    """Metadata from ACE file header."""

    zaid: int
    mass: float
    temperature: float
    date: str
    title: str
    mat: int


@dataclass
class Reaction:
    """A single MT reaction's cross-section table.

    Attributes
    ----------
    mt : int
        ENDF reaction identifier.
    ie : int
        1-indexed starting position of this reaction's threshold energy
        within the full energy grid.
    xs : np.ndarray
        Cross-section values, aligned with ``energies``.
    energies : np.ndarray
        The subset of the full pointwise energy grid this reaction is
        defined on, i.e. ``energy_grid[ie - 1 : ie - 1 + len(xs)]``,
        precomputed at parse time so it lines up directly with ``xs``.
    """

    mt: int
    ie: int
    xs: np.ndarray
    energies: np.ndarray


@dataclass
class PolynomialNu:
    """Nu-bar (average neutrons per fission) given as a polynomial in energy.

    ``nu(E) = sum(coefficients[i] * E**i for i in range(len(coefficients)))``,
    with E in MeV per the ACE convention.
    """

    coefficients: np.ndarray


@dataclass
class TabulatedNu:
    """Nu-bar given as a tabulated function of incident energy.

    Note this has its own energy grid, independent of the main pointwise
    ``energy_grid`` used for cross-sections.
    """

    energy: np.ndarray
    values: np.ndarray


@dataclass
class ContinuousTabularEnergy:
    """A single incident-energy's outgoing-energy distribution (LAW=4).

    Attributes
    ----------
    intt : int
        Interpolation law for this table (1=histogram, 2=lin-lin).
    n_discrete : int
        Number of leading discrete lines (0 if none).
    energy_out : np.ndarray
        Outgoing energy grid.
    pdf : np.ndarray
        Probability density, aligned with ``energy_out``.
    cdf : np.ndarray
        Cumulative distribution, aligned with ``energy_out``.
    """

    intt: int
    n_discrete: int
    energy_out: np.ndarray
    pdf: np.ndarray
    cdf: np.ndarray


@dataclass
class EnergyDistribution:
    """A reaction's prompt fission (or secondary-neutron) energy distribution.

    Only reactions with a single LAW=4 (Continuum Tabular Distribution) law
    are fully parsed; see :func:`_parse_energy_distributions`.

    Attributes
    ----------
    energy_in : np.ndarray
        Incident-energy grid (``NE2`` values from the LAW=4 data).
    tables : list of ContinuousTabularEnergy
        One outgoing-energy table per incident energy, aligned with
        ``energy_in``.
    """

    energy_in: np.ndarray
    tables: list[ContinuousTabularEnergy]


@dataclass
class UnsupportedEnergyLaw:
    """Marker for an energy distribution this reader does not parse.

    Recorded instead of raising, so a single unsupported reaction (multiple
    laws, or a LAW other than 4) does not prevent the rest of the file from
    being read. Attempting to perturb it raises clearly.
    """

    law: int


def read_ace(filepath: str) -> dict:
    """Parse an ASCII ACE file and extract all data.

    Parameters
    ----------
    filepath : str
        Path to ASCII ACE file.

    Returns
    -------
    dict
        Dictionary with keys: ``header``, ``nxs``, ``jxs``, ``xss``,
        ``xss_tokens``, ``energy_grid``, ``total_xs``, ``absorption_xs``,
        ``reactions``, ``nu``, ``chi``, ``raw_lines``.
        ``reactions`` maps MT number (including MT=2, elastic) to a :class:`Reaction`.
        ``nu`` is ``None`` for non-fissile isotopes, otherwise a dict with
        keys ``{"prompt", "total"}`` or ``{"nu"}`` (see :func:`_parse_nu`),
        mapping to :class:`PolynomialNu` or :class:`TabulatedNu`.
        ``chi`` maps MT number to :class:`EnergyDistribution` (LAW=4) or
        :class:`UnsupportedEnergyLaw` (see :func:`_parse_energy_distributions`),
        empty if the file has no secondary-energy data.
    """
    with open(filepath) as f:
        lines = f.readlines()

    header = _parse_header(lines)
    nxs = _parse_int_block(lines, _N_HEADER_LINES + _N_IZAW_LINES, _N_NXS_LINES)
    jxs = _parse_int_block(lines, _N_HEADER_LINES + _N_IZAW_LINES + _N_NXS_LINES, _N_JXS_LINES)
    xss, xss_tokens = _parse_xss(lines, nxs)

    nes = nxs[2]  # NXS(3): number of energy points
    ntr = nxs[3]  # NXS(4): number of reactions excluding elastic

    esz_start = jxs[0] - 1  # JXS(1): pointer to ESZ block (1-indexed)
    energy_grid = xss[esz_start : esz_start + nes]
    total_xs = xss[esz_start + nes : esz_start + 2 * nes]
    absorption_xs = xss[esz_start + 2 * nes : esz_start + 3 * nes]
    elastic_xs = xss[esz_start + 3 * nes : esz_start + 4 * nes]

    reactions = {2: Reaction(mt=2, ie=1, xs=elastic_xs, energies=energy_grid)}
    reactions.update(_parse_reactions(xss, nxs, jxs, ntr, energy_grid))

    nu = _parse_nu(xss, jxs)
    chi = _parse_energy_distributions(xss, jxs, ntr)

    return {
        "header": header,
        "nxs": nxs,
        "jxs": jxs,
        "xss": xss,
        "xss_tokens": xss_tokens,
        "energy_grid": energy_grid,
        "total_xs": total_xs,
        "absorption_xs": absorption_xs,
        "reactions": reactions,
        "nu": nu,
        "chi": chi,
        "raw_lines": lines,
    }


def _parse_header(lines: list[str]) -> ACEHeader:
    """Parse header and title from the first two lines."""
    tokens = lines[0].split()
    # ZAID carries a library suffix, e.g. "1001.41c" -> strip the trailing letters.
    zaid_str = tokens[0].rstrip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    zaid = int(float(zaid_str))
    mass = float(tokens[1])
    temperature = float(tokens[2])
    date = tokens[3] if len(tokens) > 3 else ""

    title_line = lines[1]
    mat_match = re.search(r"mat\s+(\d+)", title_line)
    mat = int(mat_match.group(1)) if mat_match else 0
    title = title_line.rstrip()

    return ACEHeader(zaid=zaid, mass=mass, temperature=temperature, date=date, title=title, mat=mat)


def _parse_int_block(lines: list[str], start_line: int, n_lines: int) -> list[int]:
    """Parse a fixed-width block of integers spanning n_lines."""
    values = []
    for i in range(start_line, start_line + n_lines):
        values.extend(int(x) for x in lines[i].split())
    return values


def _parse_xss(lines: list[str], nxs: list[int]) -> tuple[np.ndarray, list[str]]:
    """Parse the XSS data array, whose length is given by NXS(1).

    Returns both the parsed floats and the original whitespace-split text
    token for each entry. ACE ASCII formats some XSS entries (locators,
    counts, MT numbers) as bare integers and others (actual cross section
    data) in scientific notation, and which is which depends on the
    entry's role in the file rather than its numeric value (both ``0``
    and ``0.0`` appear, formatted differently, a few entries apart) — so
    the writer cannot reconstruct the original formatting from the value
    alone. Keeping the original token lets it reproduce unperturbed
    entries byte-for-byte instead.
    """
    values = []
    tokens = []
    length = nxs[0]
    line_idx = _XSS_START_LINE
    while len(values) < length and line_idx < len(lines):
        line_tokens = lines[line_idx].split()
        tokens.extend(line_tokens)
        values.extend(float(x) for x in line_tokens)
        line_idx += 1
    return np.array(values[:length], dtype=np.float64), tokens[:length]


def _parse_nu(xss: np.ndarray, jxs: list[int]) -> dict[str, PolynomialNu | TabulatedNu] | None:
    """Parse the NU block (fission nu-bar), if present.

    Per the ACE spec: ``JXS(2)`` points to the NU block, or is 0 if the
    isotope is non-fissile. The first value there (``KNU``) determines the
    layout:

    - ``KNU > 0``: a single nu-bar table starts at this position (ambiguous
      whether it represents prompt or total nu-bar; returned under key ``"nu"``).
    - ``KNU < 0``: two tables are present, prompt nu-bar starting right after
      ``KNU``, and total nu-bar starting ``|KNU|`` words later (returned under
      keys ``"prompt"`` and ``"total"``).

    Each table itself is either polynomial (``LNU == 1``) or tabulated
    (``LNU == 2``).

    Returns
    -------
    dict or None
        ``None`` if the isotope has no fission nu-bar data (``JXS(2) == 0``).
    """
    nu_ptr = jxs[1]  # JXS(2)
    if nu_ptr == 0:
        return None

    nu_start = nu_ptr - 1  # 0-indexed
    knu = xss[nu_start]

    if knu < 0:
        prompt_start = nu_start + 1
        total_start = nu_start + int(abs(knu)) + 1
        return {
            "prompt": _read_nu_table(xss, prompt_start),
            "total": _read_nu_table(xss, total_start),
        }
    else:
        return {"nu": _read_nu_table(xss, nu_start)}


def _read_nu_table(xss: np.ndarray, start: int) -> PolynomialNu | TabulatedNu:
    """Read a single polynomial (LNU=1) or tabulated (LNU=2) nu-bar table."""
    lnu = int(xss[start])

    if lnu == 1:
        nc = int(xss[start + 1])
        coefficients = xss[start + 2 : start + 2 + nc]
        return PolynomialNu(coefficients=coefficients)
    elif lnu == 2:
        nr = int(xss[start + 1])
        pos = start + 2 + 2 * nr  # skip NBT/INT interpolation region pairs
        ne = int(xss[pos])
        energy = xss[pos + 1 : pos + 1 + ne]
        values = xss[pos + 1 + ne : pos + 1 + 2 * ne]
        return TabulatedNu(energy=energy, values=values)
    else:
        raise ValueError(f"Unexpected LNU={lnu} in nu-bar table (expected 1 or 2)")


def _parse_reactions(
    xss: np.ndarray, nxs: list[int], jxs: list[int], ntr: int, energy_grid: np.ndarray
) -> dict[int, Reaction]:
    """Parse the MTR/LSIG/SIG blocks into per-MT cross-section tables."""
    if ntr == 0:
        return {}

    mtr_start = jxs[2] - 1  # JXS(3): pointer to MT array
    lsig_start = jxs[5] - 1  # JXS(6): pointer to cross-section locators
    sig_start = jxs[6] - 1  # JXS(7): pointer to cross-section block

    mt_numbers = xss[mtr_start : mtr_start + ntr].astype(int)
    locators = xss[lsig_start : lsig_start + ntr].astype(int)

    reactions = {}
    for mt, loc in zip(mt_numbers, locators, strict=True):
        pos = sig_start + loc - 1
        ie = int(xss[pos])
        ne = int(xss[pos + 1])
        xs_vals = xss[pos + 2 : pos + 2 + ne]
        reactions[int(mt)] = Reaction(mt=int(mt), ie=ie, xs=xs_vals, energies=energy_grid[ie - 1 : ie - 1 + ne])

    return reactions


def _parse_energy_distributions(
    xss: np.ndarray, jxs: list[int], ntr: int
) -> dict[int, EnergyDistribution | UnsupportedEnergyLaw]:
    """Parse the LDLW/DLW blocks (secondary-energy distributions) per MT.

    Per the ACE spec: ``JXS(10)`` (``LDLW``) is a locator array with ``ntr``
    entries, in the same MT order as ``MTR``/``LSIG`` (elastic excluded, it
    has no exit-energy law); ``JXS(11)`` (``DLW``) is the block start. Each
    reaction's law header is 4 words (``LNW``, ``LAW``, ``IDAT``, ``NR``),
    located and indexed relative to ``DLW``; a nonzero ``LNW`` means
    additional laws follow (multiple laws, not supported here).

    Only reactions with a single ``LAW == 4`` (Continuum Tabular
    Distribution) are parsed into an :class:`EnergyDistribution`; anything
    else is recorded as :class:`UnsupportedEnergyLaw` so a single
    unsupported reaction doesn't prevent parsing the rest of the file.

    Parameters
    ----------
    xss : np.ndarray
        Full XSS data array.
    jxs : list of int
        JXS locator array.
    ntr : int
        NXS(4): number of reactions excluding elastic.

    Returns
    -------
    dict
        Maps MT number to :class:`EnergyDistribution` or
        :class:`UnsupportedEnergyLaw`. Empty if ``JXS(10) == 0`` (no
        secondary-energy data, e.g. non-fissile isotopes without any
        neutron-producing reactions).
    """
    ldlw_ptr = jxs[9]  # JXS(10)
    if ldlw_ptr == 0 or ntr == 0:
        return {}

    mtr_start = jxs[2] - 1  # JXS(3): pointer to MT array, same order as LDLW
    ldlw_start = ldlw_ptr - 1
    dlw_start = jxs[10] - 1  # JXS(11)

    mt_numbers = xss[mtr_start : mtr_start + ntr].astype(int)
    locators = xss[ldlw_start : ldlw_start + ntr].astype(int)

    distributions: dict[int, EnergyDistribution | UnsupportedEnergyLaw] = {}
    for mt, loc in zip(mt_numbers, locators, strict=True):
        header_pos = dlw_start + loc - 1
        lnw = int(xss[header_pos])
        law = int(xss[header_pos + 1])
        idat = int(xss[header_pos + 2])

        if lnw != 0 or law != 4:
            distributions[int(mt)] = UnsupportedEnergyLaw(law=law)
            continue

        distributions[int(mt)] = _parse_law4(xss, dlw_start, idat)

    return distributions


def _parse_law4(xss: np.ndarray, dlw_start: int, idat: int) -> EnergyDistribution:
    """Parse a single LAW=4 (Continuum Tabular Distribution) data block.

    Parameters
    ----------
    xss : np.ndarray
        Full XSS data array.
    dlw_start : int
        0-indexed start of the DLW block (``JXS(11) - 1``).
    idat : int
        1-indexed pointer to this law's data, relative to ``dlw_start``.
    """
    pos = dlw_start + idat - 1
    nr2 = int(xss[pos])
    pos += 1 + 2 * nr2  # skip NBT/INT interpolation region pairs
    ne2 = int(xss[pos])
    energy_in = xss[pos + 1 : pos + 1 + ne2]
    locators = xss[pos + 1 + ne2 : pos + 1 + 2 * ne2].astype(int)

    tables = []
    for loc in locators:
        table_pos = dlw_start + int(loc) - 1
        inttp = int(xss[table_pos])
        intt = inttp % 10
        n_discrete = (inttp - intt) // 10
        np_ = int(xss[table_pos + 1])
        energy_out = xss[table_pos + 2 : table_pos + 2 + np_]
        pdf = xss[table_pos + 2 + np_ : table_pos + 2 + 2 * np_]
        cdf = xss[table_pos + 2 + 2 * np_ : table_pos + 2 + 3 * np_]
        tables.append(
            ContinuousTabularEnergy(intt=intt, n_discrete=n_discrete, energy_out=energy_out, pdf=pdf, cdf=cdf)
        )

    return EnergyDistribution(energy_in=energy_in, tables=tables)
