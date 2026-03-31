import warnings

import numpy as np
import pandas as pd
import serpentTools


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
        First sensitivity vector. Must have a MultiIndex (ZAI, MT).
    cov : pd.DataFrame
        Square covariance matrix with MultiIndex (ZAI, MT).
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
        First sensitivity vector. Must have a MultiIndex (ZAI, MT).
    cov : pd.DataFrame
        Square covariance matrix with MultiIndex (ZAI, MT).
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
