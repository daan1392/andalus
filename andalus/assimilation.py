"""Module containing the AssimilationSuite class, which is used to
manage a collection of benchmark, application and covariance data
for assimilation purposes.
"""

__all__ = ["AssimilationSuite"]

import os
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from andalus.ace import ACE
from andalus.ace.core import CHI_MF, NU_MTS
from andalus.application import ApplicationSuite
from andalus.benchmark import BenchmarkSuite
from andalus.covariance import CovarianceSuite
from andalus.filters import Chi2Filter, Chi2NuclearDataFilter
from andalus.utils import sandwich


def _parse_xsdata(path: str) -> dict[int, str]:
    """Map ZA to source ACE file path from a Serpent xsdata file.

    Adapted from `endf.ace.get_libraries_from_xsdata
    <https://github.com/paulromano/endf-python/blob/main/src/endf/ace.py>`_
    by Paul Romano, keyed by ZA (word[3]) instead of returning an ordered
    list, so it can be looked up per ZAI. Each line's fields are ``alias,
    filename, type, ZA, isomeric_state, awr, temperature, binary_flag,
    path`` (the same order :meth:`AssimilationSuite.to_ace_direct` writes
    via its own ``create_xsdata`` option); the path field may be
    double-quoted (e.g. when it contains spaces), so surrounding quotes
    are stripped before resolving it.

    Parameters
    ----------
    path : str
        Path to the Serpent xsdata file.

    Returns
    -------
    dict[int, str]
        Mapping of ZA (``ZAI // 10``) to the resolved absolute path of the
        corresponding ACE file.
    """
    from pathlib import Path

    xsdata = Path(path)
    libraries = {}
    with open(xsdata) as xsdata_file:
        for line in xsdata_file:
            words = line.split()
            if len(words) >= 9:
                za = int(float(words[3]))
                lib = (xsdata.parent / words[8].strip('"')).resolve()
                if za not in libraries:
                    libraries[za] = str(lib)
    return libraries


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
        covariances = CovarianceSuite.from_yaml(path, zais=zais_list, mts=[2, 4, 18, 102, 456, 35018])

        return cls(benchmarks=benchmarks, applications=applications, covariances=covariances)

    def e_index_matrix(self) -> pd.DataFrame:
        r"""Generate an E-index similarity matrix for the assimilation suite.

        The E-index measures the physical similarity between two sensitivity
        profiles without the influence of a covariance matrix:

        .. math::

            E_{ij} = \frac{S_i^T S_j}{\sqrt{S_i^T S_i \cdot S_j^T S_j}}

        This is the cosine similarity of the sensitivity vectors.

        Returns
        -------
        pd.DataFrame
            A DataFrame with shape ``(N, N)`` containing the E-index values
            between every pair of benchmarks and applications in the suite.
            Entries are ``NaN`` when either sensitivity vector is all zeros.
        """
        s = self.s
        gram = s.T @ s
        norms = np.sqrt(np.diag(gram.values))
        norms_safe = np.where(norms == 0.0, np.nan, norms)
        return gram.div(norms_safe, axis=0).div(norms_safe, axis=1)

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

        # Propagate the uncertainty on the sensitivity profiles (ds already stored in relative units)
        cov_ds = (
            pd.DataFrame(
                np.diag(((self.benchmarks.ds.values) ** 2).sum(axis=0)),
                self.benchmarks.s.columns,
                self.benchmarks.s.columns,
            )
            if include_sensitivity_uncertainty
            else None
        )

        # Build total benchmark covariance before inversion
        cov_exp_calc = pd.DataFrame(
            np.diag((self.benchmarks.dm / self.benchmarks.m) ** 2 + (self.benchmarks.dc / self.benchmarks.c) ** 2),
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

        # Use the full prior covariance index rather than intersecting it down to the
        idx = self.covariances.matrix.index
        s_full = self.benchmarks.s.reindex(idx, fill_value=0.0)
        A = self.covariances.matrix.loc[idx, idx] @ s_full

        dx = A @ C_inv @ b
        Vx_post = self.covariances.matrix.loc[idx, idx] - A @ C_inv @ A.T

        c_ = self.benchmarks.c + s_full.T @ dx.loc[idx] * self.benchmarks.c

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

        print(f"    Posterior chi-squared with nuclear data: {posteriorSuite.chi_squared(nuclear_data=True):.4f}")
        print(f"    Posterior chi-squared without nuclear data: {posteriorSuite.chi_squared(nuclear_data=False):.4f}")
        # print(
        #     f"    Calculated bias: {posteriorSuite.applications.c - self.applications.c}"
        #     rf" $\pm$ {prediction_uncertainty:.5f}"
        # )
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
        cov = np.diag((self.benchmarks.dm / self.benchmarks.m) ** 2 + (self.benchmarks.dc / self.benchmarks.c) ** 2)

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
        cov = np.diag((self.benchmarks.dm / self.benchmarks.m) ** 2 + (self.benchmarks.dc / self.benchmarks.c) ** 2)

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

    def to_ace(
        self,
        library: str,
        reaction_dict=None,
        verbose: bool = False,
        temperature: int = 300,
        create_xsdata: bool = False,
        parallel: bool = False,
        max_workers: int | None = None,
        only_zais_applications: bool = False,
    ):
        """
        Export the current assimilation suite to an adjusted ACE library format via SANDY.

        This method iterates through the unique ZAIs in the cross-section adjustments,
        retrieves the base ENDF6 files from the specified library, applies the
        calculated perturbations, and generates ACE files. Optionally, it can
        append entries to a Serpent-style 'xsdata' directory file.

        Parameters
        ----------
        library : str
            Path to the base ENDF6 library or the name of the library
            recognized by sandy.
        reaction_dict : dict, optional
            A dictionary mapping ENDF6 MT numbers to reaction types.
            Default handles standard cross-sections (MF31, 33, 34, 35).
            Format: {MF: [MT_list]}.
        verbose : bool, default False
            If True, prints detailed progress and SANDY execution logs.
        temperature : int, default 300
            The temperature in Kelvin for the ACE file generation.
        create_xsdata : bool, default False
            If True, appends isotope definitions to 'adjusted.xsdata'
            formatted for the Serpent Monte Carlo code.
        parallel : bool, default False
            If True, process ZAIs concurrently using a thread pool.
        max_workers : int | None, default None
            Maximum number of worker threads used when `parallel=True`.
            If None, Python chooses a default.
        only_zais_applications : bool, default False
            If True, only process ZAIs that are present in the application suite,

        Raises
        ------
        ValueError
            If `self.xs_adjustment` is None, indicating no posterior
            has been calculated.

        Notes
        -----
        - Currently the method supports perturbations to nubar, cross sections
         and prompt fission neutron energy spectrum.

        See Also
        --------
        sandy.get_endf6_file : The underlying function for library retrieval.
        sandy.Samples : Object used to containerize perturbations.
        sandy.Endf6.apply_perturbations : The function that applies perturbations and generates ACE files.
        """
        import sandy

        # Default MT mapping for nubar, cross-sections, Elastic scattering cosine
        # and fission energy spectrum adjustments.
        if reaction_dict is None:
            reaction_dict = {31: [456], 33: [2, 4, 18, 102], 34: [340252], 35: [35018]}

        def _reindex_to_samples(delta, MAT):
            """Internal helper to format adjustments for SANDY Samples."""
            tmp = delta.rename_axis(index=["MT", "E_min_eV", "E_max_eV"]).reset_index(name="xs_adjustment")
            tmp["E"] = pd.IntervalIndex.from_arrays(tmp["E_min_eV"], tmp["E_max_eV"], closed="right")
            tmp["MAT"] = MAT

            xs_reindexed = pd.DataFrame(tmp.set_index(["MAT", "MT", "E"])["xs_adjustment"].rename("0"))
            return xs_reindexed

        if self.xs_adjustment is None:
            raise ValueError(
                "No nuclear data adjustments found in the assimilation suite. Cannot export to ACE format."
            )
        xs_adjustment = self.xs_adjustment

        def _zai_to_xsdata_line(zai: int) -> str:
            filename = f"{int(zai / 10)}.{int(temperature // 100):02}c"
            pert_filename = f"{int(zai / 10)}_0.{int(temperature // 100):02}c"
            return f"  {filename} {filename} 1 {int(zai / 10)} 0 {zai / 10 % 1000} {temperature} 0 {pert_filename}"

        def _process_single_zai(zai: int) -> str | None:
            print(f"Exporting adjustments for ZAI {sandy.zam.zam2nuclide(zai)} to ACE format...")
            # Extract the adjustments for the current ZAI
            # Add 1 to convert from relative adjustment to multiplicative factor!
            delta_xs = xs_adjustment.loc[zai] + 1

            tape = sandy.get_endf6_file(library, kind="xs", zam=zai)

            mat = tape.mat[0]

            # convert adjustments into the correct format for SANDY
            delta_xs_reindexed = _reindex_to_samples(delta_xs, mat)

            mf31 = delta_xs_reindexed.query(f"MT in {reaction_dict[31]}").copy()
            mf33 = delta_xs_reindexed.query(f"MT in {reaction_dict[33]}").copy()
            mf34 = delta_xs_reindexed.query(f"MT in {reaction_dict[34]}").copy()
            mf34 = mf34.rename(index=lambda x: x - 34000, level="MT")
            mf35 = delta_xs_reindexed.query(f"MT in {reaction_dict[35]}").copy()
            mf35 = mf35.rename(index=lambda x: x - 35000, level="MT")

            # Create dictionary of SANDY Samples objects for the reactions to be perturbed
            smps = {}
            if not mf31.empty:
                smps[31] = sandy.Samples(mf31)
            if not mf33.empty:
                smps[33] = sandy.Samples(mf33)
            if not mf34.empty:
                smps[34] = sandy.Samples(mf34)
            if not mf35.empty:
                smps[35] = sandy.Samples(mf35)

            # Apply perturbations to the ENDF6 tape and generate perturbed ACE files
            tape.apply_perturbations(
                smps,
                to_ace=True,
                to_file=True,
                ace_kws={"temperature": temperature},
                verbose=verbose,
                enable_tqdm=False,
            )

            return _zai_to_xsdata_line(zai) if create_xsdata else None

        # Iterate over each ZAI in the cross-section adjustments and generate perturbed ACE files
        zais = list(xs_adjustment.index.get_level_values("ZAI").unique())

        # Only export the ZAIs which are present in application
        if only_zais_applications:
            app_zais = set(self.applications.zais) if self.applications else set()
            zais = [zai for zai in zais if zai in app_zais]
            print(f"Filtering to only ZAIs present in applications. Number of ZAIs to process: {len(zais)}")

        xsdata_lines = []

        if parallel:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for line in executor.map(_process_single_zai, zais):
                    if line is not None:
                        xsdata_lines.append(line)
        else:
            for zai in zais:
                line = _process_single_zai(zai)
                if line is not None:
                    xsdata_lines.append(line)

        # Write xsdata entries once to avoid concurrent appends when running in parallel.
        if create_xsdata and xsdata_lines:
            with open("adjusted.xsdata", "a") as f:
                f.write("\n".join(xsdata_lines) + "\n")

    def to_ace_direct(
        self,
        out_dir: str,
        ace_dir: str | None = None,
        xsdata_path: str | None = None,
        temperature: int = 300,
        verbose: bool = False,
        only_zais_applications: bool = False,
        create_xsdata: bool = False,
    ) -> list[str]:
        """
        Export cross-section, nu-bar, and chi adjustments directly onto existing ACE files.

        Unlike `to_ace`, which reprocesses each isotope from ENDF via SANDY/NJOY
        (a matter of minutes per isotope), this method edits an already-processed
        ACE file's XSS array directly via `andalus.ace.ACE.perturb`/`perturb_nu`/
        `perturb_chi`, which takes a fraction of a second per isotope. It requires
        a source ASCII ACE file per ZAI being adjusted; it does not talk to ENDF
        or run NJOY.

        MTs are routed by ANDALUS's own numbering convention: 452/456 go to
        `perturb_nu`, MT >= 35000 (ANDALUS's MF*1000+MT chi encoding, e.g.
        35018 for prompt fission chi) go to `perturb_chi`, and everything else
        goes to `perturb`.

        Source ACE files can be located either by directory convention
        (`ace_dir`) or, for libraries that don't follow that naming convention
        (e.g. JEFF-4.0's ``1-H-1g-300.0``), via a Serpent-style xsdata directory
        file (`xsdata_path`). Exactly one of the two must be given.

        Parameters
        ----------
        out_dir : str
            Directory to write perturbed ACE files to (created if it doesn't
            exist). Written files are named ``{ZAID}.{temperature_code}c``
            (e.g. ``92235.03c`` for U-235 at 300 K).
        ace_dir : str, optional
            Directory containing source ACE files, named
            ``{ZAID}.{temperature_code}c`` — the same naming convention
            `to_ace`'s xsdata output uses. Mutually exclusive with `xsdata_path`.
        xsdata_path : str, optional
            Path to a Serpent-style xsdata file mapping ZAIDs to source ACE
            file paths (relative paths are resolved against the xsdata file's
            directory), allowing source libraries with arbitrary file naming.
            Mutually exclusive with `ace_dir`.
        temperature : int, default 300
            Temperature in Kelvin, used to build the ACE filename suffix
            (e.g. 300 -> "03c").
        verbose : bool, default False
            If True, print progress for each ZAI.
        only_zais_applications : bool, default False
            If True, only process ZAIs present in the application suite.
        create_xsdata : bool, default False
            If True, writes a Serpent-style xsdata directory file
            (``adjusted.xsdata`` in `out_dir`) listing the written ACE files.

        Returns
        -------
        list[str]
            Paths to the written ACE files, one per processed ZAI.

        Raises
        ------
        ValueError
            If `self.xs_adjustment` is None, indicating no posterior has
            been calculated, or if `ace_dir`/`xsdata_path` are not given
            exactly one at a time.
        FileNotFoundError
            If the source ACE file for a ZAI cannot be located.

        Notes
        -----
        The xsdata parsing follows the format used by
        `endf.ace.get_libraries_from_xsdata
        <https://github.com/paulromano/endf-python/blob/main/src/endf/ace.py>`_
        from Paul Romano's ``endf-python`` package.

        See Also
        --------
        to_ace : The SANDY/NJOY-based equivalent, for isotopes without an
            already-processed ACE file to perturb directly.
        andalus.ace.ACE.perturb : Applies pointwise cross-section adjustments.
        andalus.ace.ACE.perturb_nu : Applies nu-bar adjustments.
        andalus.ace.ACE.perturb_chi : Applies fission-spectrum adjustments.
        """
        if self.xs_adjustment is None:
            raise ValueError(
                "No nuclear data adjustments found in the assimilation suite. Cannot export to ACE format."
            )
        if (ace_dir is None) == (xsdata_path is None):
            raise ValueError("Exactly one of 'ace_dir' or 'xsdata_path' must be given.")
        xs_adjustment = self.xs_adjustment

        xsdata_map = _parse_xsdata(xsdata_path) if xsdata_path is not None else None

        zais = list(xs_adjustment.index.get_level_values("ZAI").unique())
        if only_zais_applications:
            app_zais = set(self.applications.zais) if self.applications else set()
            zais = [zai for zai in zais if zai in app_zais]
            print(f"Filtering to only ZAIs present in applications. Number of ZAIs to process: {len(zais)}")

        os.makedirs(out_dir, exist_ok=True)

        def _xsdata_line(zai: int, path: str) -> str:
            alias = f"{int(zai / 10)}.{int(temperature // 100):02}c"
            return f"  {alias} {alias} 1 {int(zai / 10)} 0 {zai / 10 % 1000} {temperature} 0 {path}"

        written_paths = []
        xsdata_lines = []
        for zai in zais:
            filename = f"{int(zai / 10)}.{int(temperature // 100):02}c"
            if xsdata_map is not None:
                in_path = xsdata_map.get(int(zai // 10))
                if in_path is None or not os.path.exists(in_path):
                    raise FileNotFoundError(
                        f"No source ACE file found for ZAI={zai} in xsdata file '{xsdata_path}'. "
                        "to_ace_direct requires an already-processed ACE file per ZAI."
                    )
            else:
                assert ace_dir is not None
                in_path = os.path.join(ace_dir, filename)
                if not os.path.exists(in_path):
                    raise FileNotFoundError(
                        f"No source ACE file found for ZAI={zai} at '{in_path}'. "
                        "to_ace_direct requires an already-processed ACE file per ZAI."
                    )
            if verbose:
                print(f"Perturbing ZAI={zai} directly from {in_path}...")

            ace = ACE.read(in_path)
            delta = xs_adjustment.loc[zai]

            mt_levels = delta.index.get_level_values("MT")
            nu_mask = mt_levels.isin(NU_MTS)
            chi_mask = mt_levels >= CHI_MF
            xs_delta = delta[~nu_mask & ~chi_mask]
            nu_delta = delta[nu_mask]
            chi_delta = delta[chi_mask]

            if not xs_delta.empty:
                ace.perturb(xs_delta)
            if not nu_delta.empty:
                ace.perturb_nu(nu_delta)
            if not chi_delta.empty:
                ace.perturb_chi(chi_delta)

            out_path = os.path.join(out_dir, filename)
            ace.write(out_path)
            written_paths.append(out_path)
            if create_xsdata:
                xsdata_lines.append(_xsdata_line(zai, filename))

        if create_xsdata and xsdata_lines:
            with open(os.path.join(out_dir, "adjusted.xsdata"), "a") as f:
                f.write("\n".join(xsdata_lines) + "\n")

        return written_paths


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
