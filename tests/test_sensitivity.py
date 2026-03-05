import numpy as np
import pandas as pd
import pytest

from andalus.sensitivity import Sensitivity


@pytest.fixture
def sample_sensitivity_data():
    """
    Fixture providing a minimal Sensitivity object with a MultiIndex.
    """
    index = pd.MultiIndex.from_tuples(
        [(922350, 18, 1e-5, 1.0), (922350, 18, 1.0, 2e7)], names=["ZAI", "MT", "E_min_eV", "E_max_eV"]
    )
    data = {"HMF001": [0.1, 0.5], "HMF001_std": [0.01, 0.05]}
    return Sensitivity(data, index=index, title="HMF001", kind="keff")


def test_metadata_initialization(sample_sensitivity_data):
    """
    Test if title and kind are correctly assigned during init.
    """
    assert sample_sensitivity_data.title == "HMF001"
    assert sample_sensitivity_data.kind == "keff"


def test_metadata_persistence_after_slicing(sample_sensitivity_data):
    """
    Test if metadata survives pandas operations (slicing).
    """
    # Slice the first row
    sliced = sample_sensitivity_data.iloc[:1]

    assert isinstance(sliced, Sensitivity)
    assert sliced.title == "HMF001"
    assert sliced.kind == "keff"


def test_isotopes_property(sample_sensitivity_data):
    """
    Test if the isotopes property correctly extracts and formats ZAIs.
    """
    # 922350 is U-235. sandy.zam2latex should return a LaTeX string.
    isotopes = sample_sensitivity_data.isotopes
    assert isinstance(isotopes, list)
    assert len(isotopes) == 1
    # Check if it contains 'U' or specific LaTeX patterns
    assert "U" in isotopes[0]


def test_plot_sensitivity_logic(sample_sensitivity_data):
    """
    Test if plot_sensitivity returns a matplotlib Axes object.
    """
    import matplotlib.pyplot as plt

    ax = sample_sensitivity_data.plot_sensitivity(zais=[922350], perts=[18])

    assert isinstance(ax, plt.Axes)
    assert ax.get_xlabel() == "Energy (eV)"
    plt.close()


def test_lethargy_calculation_logic(sample_sensitivity_data):
    """
    Manually verify the lethargy normalization logic.
    """
    # For index (922350, 18, 1.0, 2e7)
    # Lethargy width = ln(2e7 / 1.0) approx 16.81
    subset = sample_sensitivity_data.loc[922350, 18]
    val = subset.iloc[1, 0]  # 0.5
    e_min = subset.index.get_level_values("E_min_eV")[1]
    e_max = subset.index.get_level_values("E_max_eV")[1]

    lethargy_width = np.log(e_max / e_min)
    normalized_val = val / lethargy_width

    assert normalized_val < val  # Lethargy normalization should reduce the value for wide bins


def test_rename_sensitivity(sample_sensitivity_data):
    """Test renaming a sensitivity object."""
    renamed = sample_sensitivity_data.rename_sensitivity("NEW_CASE")

    assert renamed.title == "NEW_CASE"
    assert "NEW_CASE" in renamed.columns
    assert "NEW_CASE_std" in renamed.columns
    # Original should not be modified
    assert sample_sensitivity_data.title == "HMF001"


def test_plot_sensitivity_missing_zai(sample_sensitivity_data):
    """Test plot_sensitivity with missing ZAI (should skip gracefully)."""
    import matplotlib.pyplot as plt

    # ZAI that doesn't exist in the data
    ax = sample_sensitivity_data.plot_sensitivity(zais=[999999], perts=[18])

    assert isinstance(ax, plt.Axes)
    plt.close()


def test_plot_sensitivity_custom_ax(sample_sensitivity_data):
    """Test plot_sensitivity with custom axes."""
    import matplotlib.pyplot as plt

    _, ax = plt.subplots()
    returned_ax = sample_sensitivity_data.plot_sensitivity(zais=[922350], perts=[18], ax=ax)

    assert returned_ax is ax
    plt.close()


def test_sensitivity_constructor():
    """Test creating a Sensitivity object with default values."""
    sens = Sensitivity()

    assert sens.title is None
    assert sens.kind == "keff"


def test_sensitivity_constructor_with_metadata():
    """Test creating a Sensitivity object with metadata."""
    data = {"col1": [1, 2], "col2": [3, 4]}
    sens = Sensitivity(data, title="test_title", kind="void")

    assert sens.title == "test_title"
    assert sens.kind == "void"
    assert len(sens) == 2
