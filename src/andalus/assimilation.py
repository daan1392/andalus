from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from andalus.application import ApplicationSuite
from andalus.benchmark import BenchmarkSuite
from andalus.covariance import CovarianceSuite
from andalus.utils import sandwich


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
        """Concatenate sensitivity data from all benchmarks and applications into
        a single DataFrame.
        """
        return pd.concat([self.benchmarks.s, self.applications.s], axis=1).fillna(0.0)

    @property
    def ds(self):
        """Concatenate uncertainties on the sensitivity profiles from all benchmarks
        and applications into a single DataFrame.
        """
        return pd.concat([self.benchmarks.ds, self.applications.ds], axis=1).fillna(0.0)

    @classmethod
    def from_yaml(cls, path: str = "assimilation_suite.yaml"):
        """Factory method to create an AssimilationSuite instance from a YAML
        configuration file.

        Parameters
        ----------
        path : str, optional
            The path to the YAML configuration file, by default "assimilation_suite.yaml".

        Returns
        -------
        AssimilationSuite
            An instance of AssimilationSuite populated with data from the YAML file.
        """
        # Load benchmark and application data from the YAML file
        benchmarks = BenchmarkSuite.from_yaml(path)
        applications = ApplicationSuite.from_yaml(path)

        # Get the zais used in the benchmarks and applications to filter the covariance data
        zais_set = set(benchmarks.s.index.get_level_values("ZAI")).union(applications.s.index.get_level_values("ZAI"))
        zais_list = sorted(list(zais_set))
        covariances = CovarianceSuite.from_yaml(path, zais=zais_list)

        return cls(benchmarks=benchmarks, applications=applications, covariances=covariances)

    def ck_matrix(self) -> pd.DataFrame:
        """Generate a ck-similarity matrix for the current assimilation suite."""
        cov = sandwich(self.s, self.covariances.matrix, self.s)
        var = np.diag(cov)

        return cov.div(np.sqrt(var), axis=0).div(np.sqrt(var), axis=1)

    def ck_target(self, target: str) -> pd.Series:
        """Calculate the ck-similarity of all sensitivities in the suite with a
        specified target sensitivity profile.

        Parameters
        ----------
        target : str
            The name of the target sensitivity profile to compare against.

        Returns
        -------
        pd.Series
            A Series containing the ck-similarity values for each sensitivity profile
            in the suite compared to the target.
        """
        if target not in self.s.columns:
            raise ValueError(f"Target '{target}' not found in sensitivity profiles.")

        ck_matrix = self.ck_matrix()

        return ck_matrix[target].drop(labels=target)

    def glls(
        self,
    ):
        """Perform a GLLS update on the assimilation suite using the current sensitivity
        profiles and covariance data. This method updates the calculated response and the
        covariance matrices.

        Returns
        -------
        AssimilationSuite
            A new AssimilationSuite instance with updated sensitivity profiles.
        """

        # Calculate prior covariance matrix of the benchmarks
        cov_prior = sandwich(self.benchmarks.s, self.covariances.matrix, self.benchmarks.s)

        # Propagate the uncertainty on the sensitivity profiles
        # cov_ds = sandwich(self.benchmarks.ds, self.covariances.matrix, self.benchmarks.ds)

        # Calculate inverse of the precision matrix
        C_inv = pd.DataFrame(
            np.linalg.pinv(cov_prior + np.diag(self.benchmarks.dm**2 + self.benchmarks.dc**2)),
            cov_prior.columns,
            cov_prior.index,
        )

        # Calculate difference between experimental and calculated values
        b = (self.benchmarks.m - self.benchmarks.c) / self.benchmarks.m

        idx = self.benchmarks.s.index.intersection(self.covariances.matrix.index)
        A = self.covariances.matrix.loc[idx, idx] @ self.benchmarks.s.loc[idx]

        dx = A @ C_inv @ b
        Vx_post = self.covariances.matrix.loc[idx, idx] - A @ C_inv @ A.T

        c_ = self.benchmarks.c + self.benchmarks.s.loc[idx].T @ dx.loc[idx] * self.benchmarks.c
        c_a = self.applications.c + self.applications.s.loc[idx].T @ dx.loc[idx] * self.applications.c
        # Vc_post = self.benchmarks.s.loc[idx].T @ Vx_post.loc[idx, idx] @ self.benchmarks.s.loc[idx]

        post_bench = {}
        for title, bm in self.benchmarks.items():
            bm_ = replace(bm, c=c_.loc[title])
            post_bench[title] = bm_

        post_app = {}
        for title, am in self.applications.items():
            am_ = replace(am, c=c_a.loc[title])
            post_app[title] = am_

        posteriorSuite = AssimilationSuite(
            benchmarks=BenchmarkSuite(post_bench),
            applications=ApplicationSuite(post_app),
            covariances=CovarianceSuite.from_df(Vx_post),
        )

        return posteriorSuite


if __name__ == "__main__":
    assimilation_suite = AssimilationSuite.from_yaml("data/config.yaml")

    print(assimilation_suite.ck_matrix())

    posterior_assimilation_suite = assimilation_suite.glls()

    print(posterior_assimilation_suite.ck_matrix())
