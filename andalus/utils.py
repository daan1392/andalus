import warnings

import numpy as np
import pandas as pd
import serpentTools

from andalus.cross_section import CrossSectionMG


def read_serpent(path):
    """Read a Serpent file while suppressing a known upstream NumPy deprecation warning."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            message=r"Conversion of an array with ndim > 0 to a scalar is deprecated.*",
            module=r"serpentTools\.parsers\.results",
        )
        return serpentTools.read(path)


def sandwich(s1, cov, s2=None):
    """
    Perform the sandwich formula to propagate uncertainties using
    first-order Taylor expansion.

    Parameters
    ----------
    s1 : pd.DataFrame or pd.Series
        First sensitivity matrix or vector.
    cov : pd.DataFrame
        Covariance matrix.
    s2 : pd.DataFrame or pd.Series, optional
        Second sensitivity matrix or vector.

    Returns
    -------
    pd.DataFrame or pd.Series
        Result of the sandwich formula.
    """
    if s2 is None:
        s2 = s1

    idx1 = s1.index.intersection(cov.index)
    idx2 = s2.index.intersection(cov.columns)
    return s1.loc[idx1].T @ cov.loc[idx1, idx2] @ s2.loc[idx2]


def sandwich_binwise(s1, cov, s2=None):
    """
    Calculate the variance contribution ZAI/MT/E pairs.

    Parameters
    ----------
    s1 : pd.Series or pd.DataFrame
        First sensitivity vector. Must have a MultiIndex (ZAI, MT, E_min_eV, E_max_eV).
    cov : pd.DataFrame
        Square covariance matrix with MultiIndex (ZAI, MT, E_min_eV, E_max_eV).
    s2 : pd.Series or pd.DataFrame, optional
        Second sensitivity vector. If None, s2 is assumed to be s1.

    Returns
    -------
    pd.Series
        A Series with a 4-level MultiIndex:
        (ZAI_1, MT_1, E_min_eV_1, E_max_eV_1, ZAI_2, MT_2, E_min_eV_2, E_max_eV_2) representing the contribution
        of the correlation between those specific bins.
    """
    if not isinstance(s1, pd.Series) and s1.columns.nlevels > 1:
        raise ValueError("s1 must be a Series or a DataFrame with a single column.")
    if s2 is not None and not isinstance(s2, pd.Series) and s2.columns.nlevels > 1:
        raise ValueError("s2 must be a Series or a DataFrame with a single column.")

    # Align to the covariance matrix
    s1_aligned = s1.reindex(cov.index).fillna(0).values.flatten()

    if s2 is not None:
        s2_aligned = s2.reindex(cov.columns).fillna(0).values.flatten()
    else:
        s2_aligned = s1_aligned

    # Compute weighted matrix
    weighted_matrix = np.outer(s1_aligned, s2_aligned) * cov.values

    # Rebuild the DataFrame with MultiIndex for both axes
    df_weighted = pd.DataFrame(weighted_matrix, index=cov.index, columns=cov.columns)

    # Stack the DataFrame
    contributions = df_weighted.stack(level=list(range(cov.columns.nlevels)))

    # Dynamic Naming
    orig_levels = cov.index.names
    # We create names for rows (_1) and columns (_2)
    new_names = [f"{n}_1" for n in orig_levels] + [f"{n}_2" for n in orig_levels]

    contributions.index.names = new_names
    return contributions


def uncertainty_reactionwise(s1, cov, s2=None):
    """
    Calculate the variance contribution for each reaction.

    Parameters
    ----------
    s1 : pd.Series or pd.DataFrame
        First sensitivity vector. Must have a MultiIndex (ZAI, MT, E_min_eV, E_max_eV).
    cov : pd.DataFrame
        Square covariance matrix with MultiIndex (ZAI, MT, E_min_eV, E_max_eV).
    s2 : pd.Series or pd.DataFrame, optional
        Second sensitivity vector. If None, s2 is assumed to be s1.

    Returns
    -------
    pd.Series
        A Series with a MultiIndex (ZAI_1, MT_1, ZAI_2, MT_2) representing the
        uncertainty contribution of each reaction.
    """
    variances = sandwich_binwise(s1, cov, s2).groupby(["ZAI_1", "MT_1", "ZAI_2", "MT_2"]).sum()

    uncertainties = np.sign(variances) * np.sqrt(np.abs(variances))

    sorted_uncertainties = uncertainties.sort_values(ascending=False, key=abs)

    return sorted_uncertainties


def _warn_uncovered(s, covered, max_listed=10):
    """Warn about bins of ``s`` with a non-zero sensitivity that are not in ``covered``."""
    uncovered = s.loc[s.index.difference(covered)]
    uncovered = uncovered[(uncovered != 0).any(axis=1)]
    if uncovered.empty:
        return
    summary = (
        uncovered.abs()
        .max(axis=1)
        .groupby(level=["ZAI", "MT"])
        .agg(["size", "max"])
        .sort_values("max", ascending=False)
    )
    listed = ", ".join(
        f"ZAI {zai} MT {mt} ({int(row['size'])} bins, max |S| = {row['max']:.3g})"
        for (zai, mt), row in summary.head(max_listed).iterrows()
    )
    extra = f" and {len(summary) - max_listed} more" if len(summary) > max_listed else ""
    warnings.warn(
        f"{len(uncovered)} sensitivity bins with non-zero sensitivity have no cross section data "
        f"and contribute zero to the response change: {listed}{extra}.",
        UserWarning,
        stacklevel=3,
    )


_LEVELS = ("ZAI", "MT", "E_min_eV", "E_max_eV")
_ENERGY_LEVELS = ("E_min_eV", "E_max_eV")


def _by_levels(by):
    """Translate the ``by`` argument of ``delta_response`` to a list of index level names (or None)."""
    if by is None:
        return None
    if not isinstance(by, str | list | tuple):
        raise ValueError(f"`by` must be None, a level name or a list of level names, not {type(by).__name__}.")
    lookup = {name.lower(): name for name in _LEVELS} | {"nuclide": "ZAI"}
    levels = []
    for item in [by] if isinstance(by, str) else list(by):
        name = lookup.get(item.lower()) if isinstance(item, str) else None
        if name is None:
            raise ValueError(f"Invalid `by` entry {item!r}. Use None or a list of {list(_LEVELS)}.")
        if name not in levels:
            levels.append(name)
    if not levels:
        raise ValueError("`by` must be None or contain at least one level name.")
    # an energy bin is identified by both of its edges
    if set(levels) & set(_ENERGY_LEVELS):
        levels += [name for name in _ENERGY_LEVELS if name not in levels]
    return levels


def delta_response(xs_ref, s, xs_other, by=None):
    r"""
    First-order relative change of responses when replacing ``xs_ref`` by ``xs_other``.

    .. math::
        \frac{\Delta R}{R} = \sum_i S_i \, \frac{\sigma^{other}_i - \sigma^{ref}_i}{\sigma^{ref}_i}

    Sensitivities are relative, so the cross section difference is divided by the
    reference library, which must be the one used to compute ``s``. Bins with a
    zero reference cross section and sensitivity bins without cross section data
    contribute zero.

    Parameters
    ----------
    xs_ref : CrossSectionMG
        Reference multigroup data, the library ``s`` was generated with.
    s : pd.DataFrame
        Sensitivities with index ``(ZAI, MT, E_min_eV, E_max_eV)``, one column per case.
    xs_other : CrossSectionMG
        Multigroup data to switch to.
    by : None, str or list of str, default None
        Index levels to keep in the result, from ``"ZAI"``, ``"MT"``, ``"E_min_eV"`` and
        ``"E_max_eV"`` (case-insensitive). The contributions are summed over the levels that are
        not listed. ``None`` gives the total per case. For example ``["ZAI"]`` gives the
        contribution per nuclide, ``["ZAI", "MT"]`` per reaction and ``["ZAI", "MT", "E_min_eV"]``
        per energy bin. Listing one energy edge adds the other, since both identify a bin.

    Returns
    -------
    pd.Series or pd.DataFrame
        Relative response change per case (Series), or a DataFrame with one column per case
        and the requested levels as index. The contributions add up to the total.

    Raises
    ------
    ValueError
        If ``by`` is invalid, or if the sensitivity and cross section bins do not overlap.

    Warns
    -----
    UserWarning
        If sensitivity bins with a non-zero value have no cross section data.
    """
    levels = _by_levels(by)
    rel = CrossSectionMG(pd.DataFrame(xs_other)).relative_difference(xs_ref)
    s = pd.DataFrame(s)
    if s.index.intersection(rel.index).empty:
        raise ValueError(
            "No sensitivity bins match the cross section bins. Check that the ERRORR energy "
            "grid equals the sensitivity energy grid."
        )
    _warn_uncovered(s, rel.index)
    contrib = s.reindex(rel.index, fill_value=0.0).mul(rel, axis=0)
    if levels is not None:
        return contrib.groupby(level=levels).sum()
    return contrib.sum(axis=0).rename("delta_response")
