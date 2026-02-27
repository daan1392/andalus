def do_something_useful() -> None:
    print("Replace this with a utility function")


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def sandwich(s1, cov, s2):
    """
    Perform the sandwich formula to propagate uncertainties using
    first-order Taylor expansion.

    Parameters
    ----------
    s1 : pd.DataFrame or pd.Series
        First sensitivity matrix or vector.
    cov : pd.DataFrame
        Covariance matrix.
    s2 : pd.DataFrame or pd.Series
        Second sensitivity matrix or vector.

    Returns
    -------
    pd.DataFrame or pd.Series
        Result of the sandwich formula.
    """
    idx = s1.index.intersection(cov.index.intersection(s2.index))
    return s1.loc[idx].T @ cov.loc[idx, idx] @ s2.loc[idx]
