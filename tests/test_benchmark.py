from unittest.mock import MagicMock

import pytest

from andalus.benchmark import Benchmark
from andalus.sensitivity import Sensitivity


@pytest.fixture
def mock_sensitivity():
    """Provides a fake Sensitivity object for testing."""
    return MagicMock(spec=Sensitivity)


def test_benchmark_initialization(mock_sensitivity):
    """Test if the dataclass stores values correctly."""
    b = Benchmark("EXP", "keff", 1.0, 0.1, 1.0, 0.1, mock_sensitivity)
    assert b.title == "EXP"
    assert b.m == 1.0


def test_invalid_kind(mock_sensitivity):
    """Ensure our __post_init__ catches bad 'kind' inputs."""
    with pytest.raises(ValueError):
        Benchmark("EXP", "invalid", 1.0, 0.1, 1.0, 0.1, mock_sensitivity)


# def test_from_serpent_real_files():
#     """Integration test using actual Serpent output files."""
#     # Ensure these paths are correct relative to where you run pytest
#     res_path = "tests/hmf001.ser_res.m"
#     sens_path = "tests/hmf001.ser_sens0.m"

#     bench = Benchmark.from_serpent(title="HMF001", m=1.00000, dm=0.00100, results_path=res_path, sens0_path=sens_path)

#     # Check values from your actual HMF001 results
#     assert bench.title == "HMF001"
#     assert 0.998895 < bench.c < 0.998899  # Broad check to ensure it read a k-eff
#     print(f"Read real k-eff: {bench.c}")
