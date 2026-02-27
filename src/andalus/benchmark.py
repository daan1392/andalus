"""Module containing the Benchmark and BenchmarkSuite classes,
which are used to represent and manage benchmark data.
"""

__all__ = ["Benchmark", "BenchmarkSuite"]
__version__ = "0.1.1"
__author__ = "Daan Houben"

from dataclasses import dataclass, field
from typing import Dict

import h5py
import numpy as np
import pandas as pd
import serpentTools

from andalus.sensitivity import Sensitivity


@dataclass(frozen=True)
class Benchmark:
    "A benchmark is an experiment that has an associated measurement."

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

        results = serpentTools.read(results_path)
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


@dataclass
class BenchmarkSuite:
    """A benchmarksuite is a combined set of benchmark objects."""

    benchmarks: Dict[str, Benchmark] = field(default_factory=dict)

    def __post_init__(self):
        for benchmark in self.benchmarks.values():
            if not isinstance(benchmark, Benchmark):
                raise TypeError(f"Benchmark {benchmark.title} is not a Benchmark object")

    @property
    def titles(self) -> list:
        """Returns a list of benchmark titles in the suite.

        Returns
        -------
        list of str
            List of benchmark titles in the suite.
        """
        if not self.benchmarks:
            AssertionError("No benchmarks in the suite.")
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
            AssertionError("No benchmarks in the suite.")
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
            AssertionError("No benchmarks in the suite.")
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
            AssertionError("No benchmarks in the suite.")
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
            AssertionError("No benchmarks in the suite.")
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
            AssertionError("No benchmarks in the suite.")
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
            AssertionError("No benchmarks in the suite.")
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
            AssertionError("No benchmarks in the suite.")
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
            AssertionError("No benchmarks in the suite.")
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
        return pd.concat([benchmark.s.iloc[:, 1].to_frame() for benchmark in self.benchmarks.values()], axis=1).fillna(
            0
        )

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
        """
        if not titles:
            with h5py.File(file_path, "r") as f:
                titles = list(f[kind].keys())

        return cls(benchmarks={title: Benchmark.from_hdf5(file_path, title) for title in titles})

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


if __name__ == "__main__":
    # Example usage
    bench = Benchmark.from_serpent(
        title="HMF001",
        m=1.00000,
        dm=0.00200,
        results_path=r"C:\Users\dhouben\Documents\andalus\tests\hmf001.ser_res.m",
        sens0_path=r"C:\Users\dhouben\Documents\andalus\tests\hmf001.ser_sens0.m",
    )
    bench.print_summary()
    import matplotlib.pyplot as plt

    bench.s.plot_sensitivity(zais=[922380], perts=[2, 4])
    plt.show()

    bench.to_hdf5("benchmark_data.h5")
    loaded_bench = Benchmark.from_hdf5("benchmark_data.h5", title="HMF001")
    loaded_bench.print_summary()
