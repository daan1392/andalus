"""Top-level package for ANDALUS."""

from importlib.metadata import PackageNotFoundError, version

from .application import Application, ApplicationSuite
from .assimilation import AssimilationSuite
from .benchmark import Benchmark, BenchmarkSuite
from .covariance import Covariance, CovarianceSuite
from .sensitivity import Sensitivity
from .utils import sandwich

try:
    __version__ = version("andalus")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "Application",
    "ApplicationSuite",
    "AssimilationSuite",
    "Benchmark",
    "BenchmarkSuite",
    "Covariance",
    "CovarianceSuite",
    "Sensitivity",
    "sandwich",
    "__version__",
]
