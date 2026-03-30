from typing import Any

import pandas as pd

from andalus.utils import sandwich


class Filter:
    """Base class for benchmark and application filters.
    Supports composition using bitwise operators (&, |, ~).
    """

    def __call__(self, item: Any) -> bool:
        raise NotImplementedError

    def __and__(self, other: "Filter") -> "Filter":
        return _AndFilter(self, other)

    def __or__(self, other: "Filter") -> "Filter":
        return _OrFilter(self, other)

    def __invert__(self) -> "Filter":
        return _NotFilter(self)


class _AndFilter(Filter):
    def __init__(self, f1, f2):
        self.f1 = f1
        self.f2 = f2

    def __call__(self, item) -> bool:
        return self.f1(item) and self.f2(item)


class _OrFilter(Filter):
    def __init__(self, f1, f2):
        self.f1 = f1
        self.f2 = f2

    def __call__(self, item) -> bool:
        return self.f1(item) or self.f2(item)


class _NotFilter(Filter):
    def __init__(self, f):
        self.f = f

    def __call__(self, item) -> bool:
        return not self.f(item)


class Chi2Filter(Filter):
    """Filter based on the standard experimental chi-squared criterion."""

    def __init__(self, threshold: float):
        self.threshold = threshold

    def __call__(self, item) -> bool:
        # Benchmarks typically have this method
        if hasattr(item, "chi_squared"):
            return item.chi_squared() <= self.threshold

        # Fallback for Applications equipped with optional measurements
        m = getattr(item, "m", None)
        dm = getattr(item, "dm", None)
        if m is not None and dm is not None and dm > 0:
            return ((m - getattr(item, "c", 0)) / dm) ** 2 <= self.threshold

        return True  # Pass-through for entries lacking measurements


class Chi2NuclearDataFilter(Filter):
    """Filter an item based on the chi2 value calculated including the nuclear data covariance matrix."""

    def __init__(self, threshold: float, covariance_matrix: pd.DataFrame):
        self.threshold = threshold
        self.covariance_matrix = covariance_matrix

    def __call__(self, item: Any) -> bool:
        m = getattr(item, "m", None)
        dm = getattr(item, "dm", None)
        if m is None or dm is None:
            return True

        # Get the nominal sensitivity profile
        s = getattr(item, "s", None)
        if s is not None:
            s = s.iloc[:, 0]

        v_nd = sandwich(s, self.covariance_matrix)

        var_total = dm**2 + getattr(item, "dc", 0) ** 2 + v_nd

        if var_total == 0:
            return True

        chi2 = ((m - item.c) ** 2) / var_total
        return chi2 <= self.threshold
