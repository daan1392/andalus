"""Module containing the AssimilationSuite class, which is used to
manage a collection of benchmark, application and covariance data
for assimilation purposes.
"""

__all__ = ["AssimilationSuite"]

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from andalus.application import ApplicationSuite
from andalus.benchmark import BenchmarkSuite
from andalus.covariance import CovarianceSuite
from andalus.filters import Chi2Filter, Chi2NuclearDataFilter
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
    xs_adjustment: pd.Series | None = None
    prior_c: pd.Series | None = None

    def __post_init__(self):
        if self.benchmarks is not None or self.applications is not None:
            if self.prior_c is None:
                self.prior_c = self.c

    @property
    def titles(self):
        """Get a list of all case titles in the assimilation suite, including both
        benchmarks and applications.

        Returns
        -------
        list
            A list of strings representing the titles of all cases in the suite.
        """
        benchmark_titles = self.benchmarks.titles if self.benchmarks else []
        application_titles = self.applications.titles if self.applications else []
        return benchmark_titles + application_titles

    @property
    def m(self):
        """Return experimental values from the benchmark and application suites.

        Returns
        -------
        pd.Series
            A Series containing the experimental values from the benchmark and application suites.
        """
        parts = []
        if self.benchmarks is not None and len(self.benchmarks) > 0:
            parts.append(self.benchmarks.m)
        if self.applications is not None and len(self.applications) > 0:
            parts.append(self.applications.m)

        if not parts:
            raise ValueError("No applications or benchmarks in the assimilation suite.")

        if len(parts) == 1:
            return parts[0]
        return pd.concat(parts, axis=0).fillna(0.0)

    @property
    def dm(self):
        """Return experimental uncertainty values from the benchmark and application suites.

        Returns
        -------
        pd.Series
            A Series containing the experimental uncertainty values from the benchmark and application suites.
        """
        parts = []
        if self.benchmarks is not None and len(self.benchmarks) > 0:
            parts.append(self.benchmarks.dm)
        if self.applications is not None and len(self.applications) > 0:
            parts.append(self.applications.dm)

        if not parts:
            raise ValueError("No applications or benchmarks in the assimilation suite.")

        if len(parts) == 1:
            return parts[0]
        return pd.concat(parts, axis=0).fillna(0.0)

    @property
    def c(self):
        """Concatenate calculated values from all benchmarks and applications.

        This property gathers calculated values from available benchmark and
        application suites, aligns them by their titles, and fills missing
        values with zeros to create a unified calculated value vector.

        Returns
        -------
        pd.Series
            A combined Series containing calculated values, aligned by index.

        Raises
        ------
        ValueError
            If both `benchmarks` and `applications` are None or empty.
        """
        parts = []
        if self.benchmarks is not None and len(self.benchmarks) > 0:
            parts.append(self.benchmarks.c)
        if self.applications is not None and len(self.applications) > 0:
            parts.append(self.applications.c)

        if not parts:
            raise ValueError("No applications or benchmarks in the assimilation suite.")

        if len(parts) == 1:
            return parts[0]
        return pd.concat(parts, axis=0).fillna(0.0)

    @property
    def dc(self):
        """Concatenate calculated value uncertainties from all benchmarks and applications.

        This property gathers calculated value uncertainties from available benchmark
        and application suites, aligns them by their titles, and fills missing
        values with zeros to create a unified calculated value uncertainty vector.

        Returns
        -------
        pd.Series
            A combined Series containing calculated value uncertainties, aligned by index.

        Raises
        ------
        ValueError
            If both `benchmarks` and `applications` are None or empty.
        """
        parts = []
        if self.benchmarks is not None and len(self.benchmarks) > 0:
            parts.append(self.benchmarks.dc)
        if self.applications is not None and len(self.applications) > 0:
            parts.append(self.applications.dc)

        if not parts:
            raise ValueError("No applications or benchmarks in the assimilation suite.")

        if len(parts) == 1:
            return parts[0]
        return pd.concat(parts, axis=0).fillna(0.0)

    @property
    def s(self):
        """
        Concatenate sensitivity data from all benchmarks and applications.

        This property gathers sensitivity vectors from available benchmark and
        application suites, aligns them by their MultiIndex, and fills missing
        values with zeros to create a unified sensitivity matrix.

        Returns
        -------
        pd.DataFrame
            A combined DataFrame containing sensitivities, aligned along the
            columns (axis=1).

        Raises
        ------
        ValueError
            If both `benchmarks` and `applications` are None or empty.
        """
        # Do not concatenate if there are only benchmarks or applications.
        if self.benchmarks is None and self.applications:
            return self.applications.s
        elif self.applications is None and self.benchmarks:
            return self.benchmarks.s
        elif self.benchmarks and self.applications:
            return pd.concat([self.benchmarks.s, self.applications.s], axis=1).fillna(0.0)
        else:
            raise ValueError("No applications or benchmarks in the assimilation suite.")

    @property
    def ds(self):
        """
        Concatenate sensitivity uncertainties data from all benchmarks and applications.

        This property gathers sensitivity uncertainty vectors from available benchmark
        and application suites, aligns them by their MultiIndex, and fills missing
        values with zeros to create a unified sensitivity uncertainty matrix.

        Returns
        -------
        pd.DataFrame
            A combined DataFrame containing sensitivity uncertainties, aligned
            along the columns (axis=1).

        Raises
        ------
        ValueError
            If both `benchmarks` and `applications` are None or empty.
        """
        if self.benchmarks is None and self.applications:
            return self.applications.ds
        elif self.applications is None and self.benchmarks:
            return self.benchmarks.ds
        elif self.benchmarks and self.applications:
            return pd.concat([self.benchmarks.ds, self.applications.ds], axis=1).fillna(0.0)
        else:
            raise ValueError("No applications or benchmarks in the assimilation suite.")

    @property
    def is_posterior(self) -> bool:
        """Check if the assimilation suite contains posterior data by checking if nd_adjustments is not None.

        Returns
        -------
        bool
            True if the suite contains posterior data, False otherwise.
        """
        return self.xs_adjustment is not None and not self.xs_adjustment.empty

    @property
    def prior_discrepancy(self) -> pd.Series:
        """Return the prior discrepancy between calculated and measured responses for the benchmarks.

        Returns
        -------
        pd.Series
            A Series containing the prior discrepancy for each benchmark in the suite.
        """
        if self.benchmarks is not None:
            return (self.prior_c - self.m) / self.m
        else:
            raise ValueError("No benchmarks in the assimilation suite.")

    def propagate_nuclear_data_uncertainty(self):
        """Propagate the nuclear data uncertainty through the sensitivity profiles
        to calculate the contribution of the nuclear data uncertainty to the
        overall uncertainty in the calculated values.

        Returns
        -------
        pd.Series
            A Series containing the propagated nuclear data uncertainty for each case in the suite.
        """
        return pd.Series(
            np.sqrt(np.diag(sandwich(self.s, self.covariances.matrix, self.s))),
            index=self.titles,
            name="uncertainty_from_nuclear_data",
        )

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
        zais_set = set()
        if benchmarks:
            zais_set.update(benchmarks.zais)
        if applications:
            zais_set.update(applications.zais)
        zais_list = sorted(list(zais_set))
        covariances = CovarianceSuite.from_yaml(path, zais=zais_list)

        return cls(benchmarks=benchmarks, applications=applications, covariances=covariances)

    def ck_matrix(self) -> pd.DataFrame:
        """Generate a ck-similarity matrix for the current assimilation suite.

        Returns
        -------
        pd.DataFrame
            A dataframe containing the similarity coefficients between
            all benchmarks and applications in the AssimilationSuite.
        """
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

    def filter(self, filter_fn) -> "AssimilationSuite":
        """Filter the benchmarks available in the assimilation suite based on a provided
        filter function.

        Parameters
        ----------
        filter_fn : function or Filter
            A function that takes a Benchmark object and returns True
            if it should be included in the filtered suite.
        """
        filtered_benchmarks = self.benchmarks.filter(filter_fn) if self.benchmarks else None

        if filtered_benchmarks is None or len(filtered_benchmarks) == 0:
            raise ValueError("Filtering resulted in an empty benchmark suite. Please adjust the filter criteria.")

        return type(self)(
            benchmarks=filtered_benchmarks,
            applications=self.applications,  # We typically do not filter applications.
            covariances=self.covariances,
            xs_adjustment=self.xs_adjustment,
            prior_c=self.prior_c,
        )

    def glls(self, include_sensitivity_uncertainty: bool = False) -> "AssimilationSuite":
        """Perform a GLLS update [1] on the assimilation suite using the sensitivity
        profiles and covariance data loaded in the AssimilationSuite. This method updates
        the calculated response and the covariance matrices.

        Returns
        -------
        AssimilationSuite
            A new AssimilationSuite instance with updated sensitivity profiles.

        References
        ----------
        .. [1] B. L. Broadhead, B. T. Rearden, C. M. Hopper, J. J. Wagschal, and C. V. Parks,
         “Sensitivity- and Uncertainty-Based Criticality Safety Validation Techniques,”
         Nuclear Science and Engineering, vol. 146, no. 3, pp. 340–366, Mar. 2004,
         doi: 10.13182/NSE03-2.

        """
        print("Performing GLLS update on the assimilation suite...")
        print(f"    Number of benchmarks included in GLLS: {len(self.benchmarks) if self.benchmarks else 0}")
        print(f"    Prior chi-squared with nuclear data: {self.chi_squared(nuclear_data=True):.4f}")
        print(f"    Prior chi-squared without nuclear data: {self.chi_squared(nuclear_data=False):.4f}")

        if self.applications is None or self.benchmarks is None:
            raise ValueError("glls() cannot be called: applications or benchmarks are not initialized.")

        # Calculate prior covariance matrix of the benchmarks
        cov_prior = sandwich(self.benchmarks.s, self.covariances.matrix, self.benchmarks.s)

        # Propagate the uncertainty on the sensitivity profiles
        cov_ds = (
            pd.DataFrame(
                np.diag(((self.benchmarks.s * self.benchmarks.ds.values) ** 2).sum(axis=0)),
                self.benchmarks.s.columns,
                self.benchmarks.s.columns,
            )
            if include_sensitivity_uncertainty
            else None
        )

        # Build total benchmark covariance before inversion
        cov_exp_calc = pd.DataFrame(
            np.diag(self.benchmarks.dm**2 + self.benchmarks.dc**2),
            index=cov_prior.index,
            columns=cov_prior.columns,
        )

        cov_total = cov_prior + cov_exp_calc
        if include_sensitivity_uncertainty and cov_ds is not None:
            cov_total = cov_total + cov_ds

        # Inverse (pseudo-inverse) of total covariance
        C_inv = pd.DataFrame(
            np.linalg.pinv(cov_total.values),
            index=cov_total.index,
            columns=cov_total.columns,
        )

        # Calculate difference between experimental and calculated values
        b = (self.benchmarks.m - self.benchmarks.c) / self.benchmarks.m

        idx = self.benchmarks.s.index.intersection(self.covariances.matrix.index)
        A = self.covariances.matrix.loc[idx, idx] @ self.benchmarks.s.loc[idx]

        dx = A @ C_inv @ b
        Vx_post = self.covariances.matrix.loc[idx, idx] - A @ C_inv @ A.T

        c_ = self.benchmarks.c + self.benchmarks.s.loc[idx].T @ dx.loc[idx] * self.benchmarks.c

        idx_a = self.applications.s.index.intersection(idx)
        c_a = self.applications.c + self.applications.s.loc[idx_a].T @ dx.loc[idx_a] * self.applications.c
        # Vc_post = self.benchmarks.s.loc[idx].T @ Vx_post.loc[idx, idx] @ self.benchmarks.s.loc[idx]

        # Initialize new benchmarkSuite with updated calculation values
        # TODO: Possiblity to add a PosteriorSuite which contains posterior nuclear data and biases.
        post_bench = {}
        for title, bm in self.benchmarks.items():
            bm_ = replace(bm, c=c_.loc[title])
            post_bench[title] = bm_

        # Initialize new applicationSuite with updated calculated values
        post_app = {}
        for title, app in self.applications.items():
            app_ = replace(app, c=c_a.loc[title])
            post_app[title] = app_

        posteriorSuite = AssimilationSuite(
            benchmarks=BenchmarkSuite(post_bench),
            applications=ApplicationSuite(post_app),
            covariances=CovarianceSuite.from_df(Vx_post),
            xs_adjustment=dx,
            prior_c=self.prior_c,
        )

        C_dsds = pd.DataFrame(
            np.diag(
                ((posteriorSuite.applications.s * posteriorSuite.applications.ds.values) ** 2).values.reshape(1, -1)[0]
            ),
            index=posteriorSuite.applications.ds.index,
            columns=posteriorSuite.applications.ds.index,
        )
        prediction_uncertainty = np.sqrt(sandwich(posteriorSuite.xs_adjustment, C_dsds)) * 1e5

        print(f"    Posterior chi-squared with nuclear data: {posteriorSuite.chi_squared(nuclear_data=True):.4f}")
        print(f"    Posterior chi-squared without nuclear data: {posteriorSuite.chi_squared(nuclear_data=False):.4f}")
        print(
            f"    Calculated bias: {posteriorSuite.applications.c - posteriorSuite.applications.prior_c}"
            rf" $\pm$ {prediction_uncertainty:.5f}"
        )
        print("")

        return posteriorSuite

    def individual_chi_squared(self, nuclear_data: bool = False) -> pd.Series:
        r"""Calculate individual chi-squared for each benchmark in the suite.

        .. math::
        \chi^2 = \frac{(m - c)^2}{\sigma_m^2 + \sigma_c^2 + s^T C s}

        Parameters
        ----------
        nuclear_data : bool, optional
            Whether to include the contribution of the nuclear data
            uncertainty in the chi² calculation, by default False.
        """
        cov = np.diag(self.benchmarks.dm**2 + self.benchmarks.dc**2)

        if nuclear_data:
            cov += sandwich(self.benchmarks.s, self.covariances.matrix, self.benchmarks.s)

        cov_inv = np.diag(cov) ** -1

        b = (self.benchmarks.m - self.benchmarks.c) / self.benchmarks.m

        chi2 = b**2 * cov_inv

        return pd.Series(chi2, index=self.benchmarks.titles).rename("chi_squared")

    def chi_squared(self, nuclear_data: bool = False) -> float:
        r"""Calculate the total chi-squared for the suite.

        .. math::
        \chi^2 = (m - c)^T C^{-1} (m - c)

        Parameters
        ----------
        nuclear_data : bool, optional
            Whether to include the contribution of the nuclear data
            uncertainty in the chi² calculation, by default False.
        """
        cov = np.diag(self.benchmarks.dm**2 + self.benchmarks.dc**2)

        if nuclear_data:
            cov += sandwich(self.benchmarks.s, self.covariances.matrix, self.benchmarks.s)

        cov_inv = np.linalg.pinv(cov)

        b = (self.benchmarks.m - self.benchmarks.c) / self.benchmarks.m

        chi2 = b.T @ cov_inv @ b

        return chi2

    def summarize(self):
        """Print a summary of the assimilation suite, including the number of benchmarks and applications,
        the titles of the cases included, and the chi-squared values with and without nuclear data.
        """
        print("Assimilation Suite Summary:")
        print(f"  Number of benchmarks: {len(self.benchmarks) if self.benchmarks else 0}")
        print(f"  Number of applications: {len(self.applications) if self.applications else 0}")
        print(f"  Titles: {', '.join(self.titles)}")
        print(f"  Chi-squared with nuclear data: {self.chi_squared(nuclear_data=True):.4f}")
        print(f"  Chi-squared without nuclear data: {self.chi_squared(nuclear_data=False):.4f}")
        print(f"  Calculated bias: {self.c - self.prior_c}")
        print("")


if __name__ == "__main__":
    assimilation_suite = AssimilationSuite.from_yaml("data/config.yaml")
    from andalus.filters import Chi2Filter

    post_suite = (
        assimilation_suite.filter(Chi2Filter(threshold=1))
        .filter(Chi2NuclearDataFilter(threshold=1, covariance_matrix=assimilation_suite.covariances.matrix))
        .glls()
        .summarize()
    )

    # print(assimilation_suite.applications.c)
    # print(posterior_assimilation_suite.applications.c)
    # assert not np.allclose(assimilation_suite.applications.c, posterior_assimilation_suite.applications.c)
    # # print(posterior_assimilation_suite.ck_matrix())

    # print(assimilation_suite.chi_squared(nuclear_data=True))
    # print(assimilation_suite.prior_discrepancy)
    # print(post_suite.prior_discrepancy)
