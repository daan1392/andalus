"""Top-level package for ANDALUS."""

from importlib.metadata import PackageNotFoundError, version

from .application import Application, ApplicationSuite
from .assimilation import AssimilationSuite
from .benchmark import Benchmark, BenchmarkSuite
from .covariance import Covariance, CovarianceSuite
from .filters import Chi2Filter, Chi2NuclearDataFilter
from .sensitivity import Sensitivity
from .spectrum import FluxSpectrum
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
    "FluxSpectrum",
    "Sensitivity",
    "sandwich",
    "Chi2Filter",
    "Chi2NuclearDataFilter",
    "__version__",
]
