"""Top-level package for ANDALUS."""

from importlib.metadata import PackageNotFoundError, version

from . import ace
from .application import Application, ApplicationSuite
from .assimilation import AssimilationSuite
from .benchmark import Benchmark, BenchmarkSuite
from .covariance import Covariance, CovarianceSuite
from .cross_section import CrossSectionMG
from .filters import Chi2Filter, Chi2NuclearDataFilter
from .sensitivity import Sensitivity
from .spectrum import FluxSpectrum
from .utils import delta_response, mt2latex, mt2reaction, sandwich, zam2latex, zam2nuclide

try:
    __version__ = version("andalus")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "ace",
    "Application",
    "ApplicationSuite",
    "AssimilationSuite",
    "Benchmark",
    "BenchmarkSuite",
    "Covariance",
    "CovarianceSuite",
    "CrossSectionMG",
    "FluxSpectrum",
    "Sensitivity",
    "sandwich",
    "delta_response",
    "zam2latex",
    "zam2nuclide",
    "mt2reaction",
    "mt2latex",
    "Chi2Filter",
    "Chi2NuclearDataFilter",
    "__version__",
]
