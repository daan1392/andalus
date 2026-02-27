from benchmark import BenchmarkSuite
from application import ApplicationSuite
from covariance import CovarianceSuite

import pandas as pd
import numpy as np
from .utils import sandwich

@dataclass
class AssimilationSuite:
    """Class to manage a collection of benchmark, application and covariance
    data for assimilation purposes. This class can be used to assemble a complete 
    dataset for assimilation, and to perform operations on the entire suite.
    """
    
    benchmarks: BenchmarkSuite
    applications: ApplicationSuite
    covariances: CovarianceSuite

    @property
    def s(self):
        """Concatenate sensitivity data from all benchmarks and applications into a single DataFrame."""
        return pd.concat([self.benchmarks.s, self.applications.s], axis=0)

    def ck_matrix(self):
        """Generate a ck-similarity matrix for the current assimilation suite.
        """
        cov = sandwich(self.s, self.covariances.matrix, self.s)
        var = np.diag(cov)

        return cov.div(np.sqrt(var), axis=0).div(np.sqrt(var), axis=1)