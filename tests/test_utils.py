import pandas as pd
import pytest

from andalus.utils import sandwich, sandwich_binwise, uncertainty_reactionwise


@pytest.fixture
def test_assimilatin_suite():
    from andalus.assimilation import AssimilationSuite

    return AssimilationSuite.from_yaml("data/config.yaml")


def test_sandwich_basic_vector():
    """Test the sandwich formula with 1D vectors (Series)."""
    # 2x1 vectors and 2x2 covariance
    s1 = pd.Series([1, 2], index=["a", "b"])
    cov = pd.DataFrame([[1, 0.5], [0.5, 1]], index=["a", "b"], columns=["a", "b"])
    s2 = pd.Series([3, 4], index=["a", "b"])

    # Calculation: [1, 2] * [[1, 0.5], [0.5, 1]] * [3, 4]^T
    # [1*1 + 2*0.5, 1*0.5 + 2*1] = [2, 2.5]
    # [2, 2.5] * [3, 4] = 6 + 10 = 16.0
    result = sandwich(s1, cov, s2)
    assert result == 16.0


def test_sandwich_index_alignment():
    """Test that the function correctly intersects indices."""
    s1 = pd.Series([1, 2, 100], index=["a", "b", "c"])  # 'c' is extra
    cov = pd.DataFrame([[1, 0], [0, 1]], index=["a", "b"], columns=["a", "b"])
    s2 = pd.Series([3, 4, 200], index=["a", "b", "d"])  # 'd' is extra

    # Intersection is ['a', 'b']
    # Result should ignore 'c' and 'd'
    # [1, 2] * I * [3, 4] = 3 + 8 = 11
    result = sandwich(s1, cov, s2)
    assert result == 11.0


def test_sandwich_dataframes():
    """Test with DataFrames (multiple sensitivities/outputs)."""
    s1 = pd.DataFrame({"out1": [1, 0], "out2": [0, 1]}, index=["a", "b"])

    cov = pd.DataFrame({"a": [2, 0], "b": [0, 3]}, index=["a", "b"])

    s2 = s1  # Square case

    # Result should be a DataFrame (S^T * Cov * S)
    # Since S is Identity-like, result should effectively be the Cov matrix
    result = sandwich(s1, cov, s2)

    assert isinstance(result, pd.DataFrame)
    assert result.loc["out1", "out1"] == 2
    assert result.loc["out2", "out2"] == 3
    assert result.loc["out1", "out2"] == 0


def test_sandwich_empty_intersection():
    """Test behavior when indices do not overlap."""
    s1 = pd.Series([1], index=["a"])
    cov = pd.DataFrame([[1]], index=["b"], columns=["b"])
    s2 = pd.Series([1], index=["c"])

    # Intersection is empty. Depending on pandas version,
    # @ on empty objects may return 0.0 or an empty structure.
    result = sandwich(s1, cov, s2)
    assert result == 0 or (hasattr(result, "empty") and result.empty)


def test_binwise_sandwich(test_assimilatin_suite):
    """Test the binwise sandwich formula."""
    # Test with a specific benchmark
    benchmark = test_assimilatin_suite.benchmarks.s["HMF001"]
    covariances = test_assimilatin_suite.covariances.matrix

    # Calculate the binwise sandwich result
    result = sandwich_binwise(benchmark, covariances)

    # Check that the result is a Series with expected structure
    assert isinstance(result, pd.Series)
    assert result.index.names == [
        "ZAI_1",
        "MT_1",
        "E_min_eV_1",
        "E_max_eV_1",
        "ZAI_2",
        "MT_2",
        "E_min_eV_2",
        "E_max_eV_2",
    ]

    # JEFF-4.0 Uncertainty for HMF001 is around 1.3%
    assert (result.sum() ** 0.5) >= 0.01000


def test_uncertainty_reactionwise(test_assimilatin_suite):
    """Test the reaction-wise uncertainty calculation."""
    benchmark = test_assimilatin_suite.benchmarks.s["HMF001"]
    covariances = test_assimilatin_suite.covariances.matrix

    result = uncertainty_reactionwise(benchmark, covariances)

    assert isinstance(result, pd.Series)
    assert result.index.names == ["ZAI_1", "MT_1", "ZAI_2", "MT_2"]
    assert result.sum() != 0
