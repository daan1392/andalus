from typing import Any

import pandas as pd

from andalus.utils import sandwich


class Filter:
    """Base class for benchmark and application filters.

    Supports composition using bitwise operators (&, |, ~).
    """

    def __call__(self, item: Any) -> bool:
        """Evaluate the filter criterion on the given item.

        Parameters
        ----------
        item : Any
            The item to be evaluated, typically a Benchmark or Application.

        Returns
        -------
        bool
            True if the item passes the filter, False otherwise.
        """
        raise NotImplementedError

    def __and__(self, other: "Filter") -> "Filter":
        """Combine this filter with another using a logical AND.

        Parameters
        ----------
        other : Filter
            The other filter to combine with.

        Returns
        -------
        Filter
            A new filter representing the logical AND of both filters.
        """
        return _AndFilter(self, other)

    def __or__(self, other: "Filter") -> "Filter":
        """Combine this filter with another using a logical OR.

        Parameters
        ----------
        other : Filter
            The other filter to combine with.

        Returns
        -------
        Filter
            A new filter representing the logical OR of both filters.
        """
        return _OrFilter(self, other)

    def __invert__(self) -> "Filter":
        """Invert this filter using a logical NOT.

        Returns
        -------
        Filter
            A new filter representing the logical NOT of this filter.
        """
        return _NotFilter(self)


class _AndFilter(Filter):
    """Internal class representing a logical AND between two filters."""

    def __init__(self, f1: Filter, f2: Filter):
        """Initialize the AND filter.

        Parameters
        ----------
        f1 : Filter
            The first filter.
        f2 : Filter
            The second filter.
        """
        self.f1 = f1
        self.f2 = f2

    def __call__(self, item: Any) -> bool:
        """Evaluate the logical AND on the given item.

        Parameters
        ----------
        item : Any
            The item to evaluate.

        Returns
        -------
        bool
            True if the item passes both filters, False otherwise.
        """
        return self.f1(item) and self.f2(item)


class _OrFilter(Filter):
    """Internal class representing a logical OR between two filters."""

    def __init__(self, f1: Filter, f2: Filter):
        """Initialize the OR filter.

        Parameters
        ----------
        f1 : Filter
            The first filter.
        f2 : Filter
            The second filter.
        """
        self.f1 = f1
        self.f2 = f2

    def __call__(self, item: Any) -> bool:
        """Evaluate the logical OR on the given item.

        Parameters
        ----------
        item : Any
            The item to evaluate.

        Returns
        -------
        bool
            True if the item passes at least one of the filters, False otherwise.
        """
        return self.f1(item) or self.f2(item)


class _NotFilter(Filter):
    """Internal class representing a logical NOT for a filter."""

    def __init__(self, f: Filter):
        """Initialize the NOT filter.

        Parameters
        ----------
        f : Filter
            The filter to invert.
        """
        self.f = f

    def __call__(self, item: Any) -> bool:
        """Evaluate the logical NOT on the given item.

        Parameters
        ----------
        item : Any
            The item to evaluate.

        Returns
        -------
        bool
            True if the item does not pass the underlying filter, False otherwise.
        """
        return not self.f(item)


class Chi2Filter(Filter):
    """Filter based on the standard experimental chi-squared criterion."""

    def __init__(self, threshold: float):
        """Initialize the Chi2 filter.

        Parameters
        ----------
        threshold : float
            The maximum allowed chi-squared value.
        """
        self.threshold = threshold

    def __call__(self, item: Any) -> bool:
        """Evaluate the chi-squared criterion on the item.

        Parameters
        ----------
        item : Any
            The item to evaluate (e.g., Benchmark or Application).

        Returns
        -------
        bool
            True if the item passes the chi-squared threshold or lacks measurements, False otherwise.
        """
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
        """Initialize the Chi2 Nuclear Data filter.

        Parameters
        ----------
        threshold : float
            The maximum allowed chi-squared value.
        covariance_matrix : pd.DataFrame
            The nuclear data covariance matrix to be used in evaluating the uncertainty.
        """
        self.threshold = threshold
        self.covariance_matrix = covariance_matrix

    def __call__(self, item: Any) -> bool:
        """Evaluate the nuclear data-inclusive chi-squared criterion on the item.

        Parameters
        ----------
        item : Any
            The item to evaluate (e.g., Benchmark or Application).

        Returns
        -------
        bool
            True if the item passes the threshold or is missing required attributes, False otherwise.
        """
        m = getattr(item, "m", None)
        dm = getattr(item, "dm", None)
        if m is None or dm is None:
            return True

        # Get the sensitivity profile
        s = getattr(item, "s", None)
        if s is not None:
            s = s.iloc[:, 0]

        v_nd = sandwich(s, self.covariance_matrix)

        var_total = dm**2 + getattr(item, "dc", 0) ** 2 + v_nd

        if var_total == 0:
            return True

        chi2 = ((m - item.c) ** 2) / var_total
        return chi2 <= self.threshold
