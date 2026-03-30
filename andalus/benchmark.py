"""Module containing the Benchmark and BenchmarkSuite classes,
which are used to represent and manage benchmark data.
"""

__all__ = ["Benchmark", "BenchmarkSuite"]

from dataclasses import dataclass, field, replace

import h5py
import numpy as np
import pandas as pd

from andalus.sensitivity import Sensitivity
from andalus.utils import read_serpent


@dataclass(frozen=True)
class Benchmark:
    """
    A benchmark is an application that has an associated measurement.

    Attributes
    ----------
    title : str
        The unique name or identifier for the application.
    kind : str
        The kind of the observable (e.g., "keff", "void").
    m : float
        The measured value (Nominal).
    dm : float
        The uncertainty of the measurement.
    c : float
        The calculated value (Nominal).
    dc : float
        The uncertainty of the calculation.
    s : Sensitivity
        The energy-dependent sensitivity profiles.
    """

    title: str
    kind: str
    m: float
    dm: float
    c: float
    dc: float
    s: Sensitivity

    def __post_init__(self):
        if not isinstance(self.title, str):
            raise TypeError(f"Title '{self.title}' must be a string")
        if self.kind not in ["keff"]:
            raise ValueError(f"Type '{self.kind}' not implemented.")
        if not isinstance(self.m, (int, float)):
            raise TypeError(f"Measurement {self.m} must be a number")
        if not isinstance(self.dm, (int, float)):
            raise TypeError(f"Measurement uncertainty {self.dm} must be a number")
        if not isinstance(self.c, (int, float)):
            raise TypeError(f"Calculated value {self.c} must be a number")
        if not isinstance(self.dc, (int, float)):
            raise TypeError(f"Calculated uncertainty {self.dc} must be a number")
        if not isinstance(self.s, Sensitivity):
            raise TypeError(f"Sensitivity {self.s} must be a Sensitivity object")

    @classmethod
    def from_serpent(
        cls,
        title: str,
        m: float,
        dm: float,
        sens0_path: str,
        results_path: str,
        kind: str = "keff",
        materials=None,
        zailist=None,
        pertlist=None,
    ):
        """Method to create a Benchmark object from a serpent output.

        Parameters
        ----------
        title : str
            title of the benchmark.
        m : float
            measurement value.
        dm : float
            measurement uncertainty.
        results_path : str
            path to the Serpent _res.m file.
        sens0_path : str
            path to the Serpent _sens0.m file.
        kind : str, optional
            kind of observable, by default "keff".
        materials : _type_, optional
            The material in which the sensitivity is calculated, by default None.
        zailist : _type_, optional
            The ZAIs which have to be extracted from the sensitivity file, by default None.
        pertlist : _type_, optional
            The perturbations which have to be extracted from the sensitivity file, by default None.

        Returns
        -------
        _type_
            Returns a Benchmark object with the calculated value and sensitivity data extracted from the Serpent files.
        """

        if materials is None:
            materials = ["total"]
        if pertlist is None:
            pertlist = ["mt 2 xs", "mt 4 xs", "mt 18 xs", "mt 102 xs", "nubar prompt", "chi prompt"]

        results = read_serpent(results_path)
        c = results.resdata["absKeff"][0]
        dc = results.resdata["absKeff"][1]

        sensitivity = Sensitivity.from_serpent(
            sens0_path=sens0_path,
            title=title,
            materiallist=materials,
            zailist=zailist,
            pertlist=pertlist,
        )

        return cls(title=title, kind=kind, m=m, dm=dm, c=c, dc=dc, s=sensitivity)

    @classmethod
    def from_hdf5(cls, file_path, title: str, kind: str = "keff"):
        """
        Create a Benchmark instance from an HDF5 file.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file containing the benchmark data.
        title : str
            Title of the benchmark to load.
        kind : str, optional
            Type of benchmark (e.g., "keff"). Default is "keff".

        Returns
        -------
        Benchmark
            A new Benchmark instance with the loaded data.
        """
        with h5py.File(file_path, "r") as f:
            if kind not in f:
                raise KeyError(f"Benchmark type '{kind}' not found in {file_path}")
            if title not in f[kind]:
                raise KeyError(f"Benchmark '{title}' not found in {file_path}")

            grp = f[kind][title]
            m = grp.attrs["m"]
            dm = grp.attrs["dm"]
            c = grp.attrs["c"]
            dc = grp.attrs["dc"]

        return cls(
            title=title,
            kind=kind,
            m=m,
            dm=dm,
            c=c,
            dc=dc,
            s=Sensitivity.from_hdf5(file_path, title=title, kind=kind),
        )

    def to_hdf5(self, file_path="benchmarks.h5"):
        """
        Save the benchmark data to an HDF5 file.

        Parameters
        ----------
        file_path : str, optional
            The path to the HDF5 file where the benchmark data will be saved.
              Default is 'benchmarks.h5'.
        """
        with h5py.File(file_path, "a") as f:
            # Create group for this benchmark if it exists
            # if self.title in f[self.kind]:
            #     del f[f"{self.kind}/{self.title}"]

            # Create group and save attributes
            grp = f.create_group(f"{self.kind}/{self.title}")
            grp.attrs["m"] = self.m
            grp.attrs["dm"] = self.dm
            grp.attrs["c"] = self.c
            grp.attrs["dc"] = self.dc

        # Save sensitivity DataFrame using pandas to_hdf
        self.s.to_hdf(file_path, key=f"{self.kind}/{self.title}/sensitivity", mode="a", format="table")

    def print_summary(self):
        """Print a quick summary of a benchmark object."""
        print(f"Benchmark: {self.title}")
        print(f"Type: {self.kind}")
        print(f"Measurement: {self.m} ± {self.dm}")
        print(f"Calculated: {self.c} ± {self.dc}")

    def plot_sensitivity(self, zais, perts, ax=None, **kwargs):
        """Plot the sensitivity profiles for the specified ZAIs and perturbations.

        Parameters
        ----------
        zais : list of int
            List of ZAIs to include in the plot.
        perts : list of str
            List of perturbations to include in the plot.
        ax : matplotlib.axes.Axes, optional
            Matplotlib Axes object to plot on. If None, a new figure and axes will be created.
        **kwargs
            Additional keyword arguments to pass to the plotting function.

        Returns
        -------
        matplotlib.axes.Axes
            The Axes object containing the plot.
        """
        return self.s.plot(zais=zais, perts=perts, ax=ax, **kwargs)

    def chi_squared(self) -> float:
        """Calculate the experimental chi-squared value for the benchmark.

        Returns
        -------
        float
            The experimental chi-squared value calculated as ((m - c) / dm)^2.
        """
        return ((self.m - self.c) / self.dm) ** 2


@dataclass
class BenchmarkSuite:
    """A benchmarksuite is a combined set of benchmark objects.

    Attributes
    ----------
    benchmarks : dict[str, Benchmark]
        A dictionary of benchmark objects, indexed by their title.
    """

    benchmarks: dict[str, Benchmark] = field(default_factory=dict)

    def __post_init__(self):
        for benchmark in self.benchmarks.values():
            if not isinstance(benchmark, Benchmark):
                raise TypeError(f"Benchmark {benchmark.title} is not a Benchmark object")

    def __getitem__(self, key):
        return self.benchmarks[key]

    def __iter__(self):
        return iter(self.benchmarks.values())

    def __len__(self):
        return len(self.benchmarks)

    def __contains__(self, key):
        return key in self.benchmarks

    def items(self):
        """
        Return the suite's benchmarks as (title, Benchmark) pairs.

        Returns
        -------
        dict_items
            A view of the internal benchmarks dictionary items.
        """
        return self.benchmarks.items()

    def values(self):
        """Return an iterator over the benchmark objects."""
        return self.benchmarks.values()

    def keys(self):
        """Return an iterator over the benchmark titles."""
        return self.benchmarks.keys()

    @property
    def titles(self) -> list:
        """Returns a list of benchmark titles in the suite.

        Returns
        -------
        list of str
            List of benchmark titles in the suite.
        """
        if not self.benchmarks:
            raise AssertionError("No benchmarks in the suite.")
        return list(self.benchmarks.keys())

    @property
    def kinds(self) -> pd.Series:
        """Returns a pd.Series of benchmark types in the suite.

        Returns
        -------
        pd.Series of str
            Series of benchmark types in the suite.
        """
        if not self.benchmarks:
            raise AssertionError("No benchmarks in the suite.")
        return pd.Series([benchmark.kind for benchmark in self.benchmarks.values()], index=self.titles)

    @property
    def zais(self) -> list:
        """Returns a list of unique ZAIs in the sensitivity data of the benchmarks in the suite.

        Returns
        -------
        list of int
            List of unique ZAIs in the sensitivity data of the benchmarks in the suite.
        """
        if not self.benchmarks:
            raise AssertionError("No benchmarks in the suite.")
        zais = set()
        for benchmark in self.benchmarks.values():
            zais.update(benchmark.s.index.get_level_values("ZAI").unique())
        return sorted(zais)

    @property
    def m(self) -> pd.Series:
        """Returns a pd.Series of benchmark measurements in the suite.

        Returns
        -------
        pd.Series of float
            Series of benchmark measurements in the suite.
        """
        if not self.benchmarks:
            raise AssertionError("No benchmarks in the suite.")
        return pd.Series([benchmark.m for benchmark in self.benchmarks.values()], index=self.titles)

    @property
    def dm(self) -> pd.Series:
        """Returns a pd.Series of benchmark measurement uncertainties in the suite.

        Returns
        -------
        pd.Series of float
            Series of benchmark measurement uncertainties in the suite.
        """
        if not self.benchmarks:
            raise AssertionError("No benchmarks in the suite.")
        return pd.Series([benchmark.dm for benchmark in self.benchmarks.values()], index=self.titles)

    @property
    def cov_m(self) -> pd.DataFrame:
        """Returns a pd.DataFrame of benchmark measurement covariance in the suite.

        Returns
        -------
        pd.DataFrame
            DataFrame of benchmark measurement covariance in the suite.
        """
        if not self.benchmarks:
            raise AssertionError("No benchmarks in the suite.")
        return pd.DataFrame(
            data=np.diag([benchmark.dm**2 for benchmark in self.benchmarks.values()]),
            index=self.titles,
            columns=self.titles,
        )

    @property
    def c(self) -> pd.Series:
        """Returns a pd.Series of benchmark calculated values in the suite.

        Returns
        -------
        pd.Series of float
            Series of benchmark calculated values in the suite.
        """
        if not self.benchmarks:
            raise AssertionError("No benchmarks in the suite.")
        return pd.Series([benchmark.c for benchmark in self.benchmarks.values()], index=self.titles)

    @property
    def dc(self) -> pd.Series:
        """Returns a pd.Series of benchmark calculated uncertainties in the suite.

        Returns
        -------
        pd.Series of float
            Series of benchmark calculated uncertainties in the suite.
        """
        if not self.benchmarks:
            raise AssertionError("No benchmarks in the suite.")
        return pd.Series([benchmark.dc for benchmark in self.benchmarks.values()], index=self.titles)

    @property
    def s(self) -> pd.DataFrame:
        """Returns a pd.DataFrame of sensitivity objects in the suite.

        Returns
        -------
        pd.DataFrame
            DataFrame of sensitivity objects in the suite.
        """
        if not self.benchmarks:
            raise AssertionError("No benchmarks in the suite.")
        return pd.concat([benchmark.s.iloc[:, 0].to_frame() for benchmark in self.benchmarks.values()], axis=1).fillna(
            0
        )

    @property
    def ds(self) -> pd.DataFrame:
        """Returns a pd.DataFrame of sensitivity uncertainties in the suite.

        Returns
        -------
        pd.DataFrame
            DataFrame of sensitivity uncertainties in the suite.
        """
        if not self.benchmarks:
            raise AssertionError("No benchmarks in the suite.")
        return pd.concat([benchmark.s.iloc[:, 1].to_frame() for benchmark in self.benchmarks.values()], axis=1).fillna(
            0
        )

    @classmethod
    def from_list(cls, benchmarks: list[Benchmark]):
        """Factory method to create a BenchmarkSuite instance from a list of Benchmark objects.

        Parameters
        ----------
        benchmarks : list[Benchmark]
            A list of Benchmark objects to be included in the suite.

        Returns
        -------
        BenchmarkSuite
            An instance of BenchmarkSuite containing the provided Benchmark objects.
        """
        return cls(benchmarks={benchmark.title: benchmark for benchmark in benchmarks})

    @classmethod
    def from_hdf5(cls, file_path: str, titles: list, kind: str = "keff"):
        """Retrieve a set of benchmarks from a database.

        Parameters
        ----------
        file_path : str
            file path where the database is located.
        titles : list, optional
            Titles which have to be extracted from the database, if None
            return all the benchmarks available in the database, by default None.

        Returns
        -------
        BenchmarkSuite
            Returns a BenchmarkSuite object containing the imported Benchmark objects.

        Notes
        -----
        If `titles` is None, the method will attempt to load all benchmarks of the specified `kind` from the HDF5 file.
        """
        if not titles:
            with h5py.File(file_path, "r") as f:
                titles = list(f[kind].keys())

        return cls(benchmarks={title: Benchmark.from_hdf5(file_path, title) for title in titles})

    @classmethod
    def from_yaml(cls, path: str):
        """Factory method to create a BenchmarkSuite instance from a YAML configuration file.

        Parameters
        ----------
        path : str
            The path to the YAML configuration file.

        Returns
        -------
        BenchmarkSuite
            An instance of BenchmarkSuite populated with data from the YAML file.
        """
        import yaml

        with open(path) as f:
            config = yaml.safe_load(f)

        benchmarks = {}
        for benchmark_config in config.get("benchmarks", []):
            if "sens0_path" in benchmark_config and "results_path" in benchmark_config:
                benchmark = Benchmark.from_serpent(
                    title=benchmark_config["title"],
                    m=benchmark_config["m"],
                    dm=benchmark_config["dm"],
                    sens0_path=benchmark_config["sens0_path"],
                    results_path=benchmark_config["results_path"],
                    kind=benchmark_config.get("kind", "keff"),
                    materials=benchmark_config.get("materials"),
                    zailist=benchmark_config.get("zailist"),
                    pertlist=benchmark_config.get("pertlist"),
                )
                benchmarks[benchmark.title] = benchmark
            elif "hdf5_path" in benchmark_config:
                benchmark = Benchmark.from_hdf5(
                    file_path=benchmark_config["hdf5_path"],
                    title=benchmark_config["title"],
                    kind=benchmark_config.get("kind", "keff"),
                )
                benchmarks[benchmark.title] = benchmark

        return cls(benchmarks=benchmarks)

    def get(self, title: str) -> Benchmark | None:
        """
        Get a benchmark from the suite.

        Parameters
        ----------
        title : str
            Title of the benchmark to be retrieved.

        Returns
        -------
        Benchmark
            Benchmark object.
        """
        return self.benchmarks.get(title)

    def remove(self, title: str):
        """
        Remove benchmark from the suite.

        Parameters
        ----------
        title : str
            Title of the benchmark to be removed.
        """
        self.benchmarks.pop(title, None)

    def update_c(self, new_c: pd.Series) -> "BenchmarkSuite":
        """
        Create a new BenchmarkSuite with updated calculated values.

        This method is typically used to generate a posterior suite after
        an assimilation update (e.g., GLLS).

        Parameters
        ----------
        new_c : pd.Series
            A series containing the updated 'c' values, indexed by
            benchmark title.

        Returns
        -------
        BenchmarkSuite
            A new instance of the suite containing updated Benchmark objects.

        Raises
        ------
        KeyError
            If a benchmark title in the suite is missing from the index of `new_c`.
        """
        return BenchmarkSuite({title: replace(bm, c=new_c.loc[title]) for title, bm in self.benchmarks.items()})

    def filter(self, filter_fn) -> "BenchmarkSuite":
        """Filter the BenchmarkSuite based on a filter function and print a summary of the benchmarks removed.

        Parameters
        ----------
        filter_fn : function
            A function that takes a Benchmark object as input and returns a boolean
              indicating whether to include the benchmark in the filtered suite.

        Returns
        -------
        BenchmarkSuite
            A new BenchmarkSuite instance containing only the benchmarks for which `filter_fn` returns True.
        """
        print(f"Filtering benchmarks using {filter_fn.__class__.__name__}...")
        print(f"    Filter threshold: {filter_fn.threshold}")
        print(f"    Initial number of benchmarks: {len(self.benchmarks)}")
        filtered_benchmarks = {title: bm for title, bm in self.benchmarks.items() if filter_fn(bm)}
        removed_benchmarks = set(self.benchmarks.keys()) - set(filtered_benchmarks.keys())
        if removed_benchmarks:
            print(f"    Removed benchmarks: {', '.join(removed_benchmarks)} \n")
        else:
            print("    No benchmarks were removed. \n")
        return BenchmarkSuite(benchmarks=filtered_benchmarks)


if __name__ == "__main__":
    bmarks = BenchmarkSuite.from_yaml("data/config.yaml")
    print(bmarks.s)
    print(bmarks.ds)
    print(bmarks.titles)
