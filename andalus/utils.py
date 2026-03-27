import warnings

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


# def safe_sandwich(s1, cov, s2):
#     """
#     Perform the sandwich formula to propagate uncertainties using
#     first-order Taylor expansion while reporting any missing indices.

#     Parameters
#     ----------
#     s1 : pd.DataFrame or pd.Series
#         First sensitivity matrix or vector.
#     cov : pd.DataFrame
#         Covariance matrix.
#     s2 : pd.DataFrame or pd.Series
#         Second sensitivity matrix or vector.

#     Returns
#     -------
#     pd.DataFrame, pd.Series, or float
#         Result of the sandwich formula.

#     Notes
#     -----
#     This function automatically aligns indices by intersection. Any indices
#     present in one input but missing in others are reported to stdout.
#     """
#     # Identify Index Sets
#     set1 = set(s1.index)
#     set_cov = set(cov.index)
#     set2 = set(s2.index)

#     # Calculate Intersection
#     idx1 = set1.intersection(set_cov)
#     idx2 = set2.intersection(set_cov)

#     # Diagnostic Reporting
#     mismatches = {
#         "s1 (Sensitivity 1)": set1 - idx1,
#         "cov (Covariance)": set_cov - idx1 - idx2,
#         "s2 (Sensitivity 2)": set2 - idx2,
#     }

#     has_mismatch = any(len(diff) > 0 for diff in mismatches.values())

#     if has_mismatch:
#         print("\n" + "=" * 50)
#         print("INDEX MISMATCH REPORT")
#         print("-" * 50)
#         print(f"{'Source':<20} | {'Count':<6} | {'Missing/Extra Indices'}")
#         print("-" * 50)
#         for name, diff in mismatches.items():
#             if diff:
#                 display_list = sorted(list(diff))
#                 # Truncate long lists for readability
#                 items = f"{display_list[:5]}..." if len(display_list) > 5 else f"{display_list}"
#                 print(f"{name:<20} | {len(diff):<6} | {items}")
#         print("=" * 50 + "\n")

#     # Calculation
#     return s1.loc[idx1].T @ cov.loc[idx1, idx2] @ s2.loc[idx2]
