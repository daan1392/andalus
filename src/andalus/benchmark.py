from dataclasses import dataclass

import h5py
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
            raise TypeError("Title must be a string")
        if self.kind not in ["keff"]:
            raise ValueError(f"Type '{self.kind}' not implemented.")
        if not isinstance(self.m, (int, float)):
            raise TypeError("Measurement must be a number")
        if not isinstance(self.dm, (int, float)):
            raise TypeError("Measurement uncertainty must be a number")
        if not isinstance(self.c, (int, float)):
            raise TypeError("Calculated value must be a number")
        if not isinstance(self.dc, (int, float)):
            raise TypeError("Calculated uncertainty must be a number")
        if not isinstance(self.s, Sensitivity):
            raise TypeError("Sensitivity must be a Sensitivity object")

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
            title of the benchmar
        m : float
            measurement value
        dm : float
            measurement uncertainty
        results_path : str
            path to the Serpent _res.m file
        sens0_path : str
            path to the Serpent _sens0.m file
        kind : str, optional
            kind of observable, by default "k-eff"
        materials : _type_, optional
            The material in which the sensitivity is calculated, by default None
        zailist : _type_, optional
            The ZAIs which have to be extracted from the sensitivity file, by default None
        pertlist : _type_, optional
            The perturbations which have to be extracted from the sensitivity file, by default None

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
        c = results.resData["absKeff"][0]
        dc = results.resData["absKeff"][1]

        sensitivity = Sensitivity.from_serpent(
            sens0_path=sens0_path,
            title=title,
            materiallist=materials,
            zailist=zailist,
            pertlist=pertlist,
        )

        return cls(title=title, kind=kind, m=m, dm=dm, c=c, dc=dc, s=sensitivity)

    @classmethod
    def from_hdf5(cls, file_path, title, kind: str = "k-eff"):
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
            if title not in f:
                raise KeyError(f"Benchmark '{title}' not found in {file_path}")

            grp = f[title]
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
            s=Sensitivity(pd.read_hdf(file_path, f"{title}/sensitivity")),
        )

    def print_summary(self):
        print(f"Benchmark: {self.title}")
        print(f"Type: {self.kind}")
        print(f"Measurement: {self.m} ± {self.dm}")
        print(f"Calculated: {self.c} ± {self.dc}")

    def to_hdf5(self, file_path="benchmarks.h5"):
        """
        Save the benchmark data to an HDF5 file.

        Parameters
        ----------
        file_path : str, optional
            The path to the HDF5 file where the benchmark data will be saved. Default is 'benchmarks.h5'.
        """
        with h5py.File(file_path, "a") as f:
            # Create group for this benchmark if it exists
            if self.title in f:
                del f[self.title]

            # Create group and save attributes
            grp = f.create_group(self.title)
            grp.attrs["m"] = self.m
            grp.attrs["dm"] = self.dm
            grp.attrs["c"] = self.c
            grp.attrs["dc"] = self.dc

        # Save sensitivity DataFrame using pandas to_hdf
        self.s.to_hdf(
            path_or_buf=file_path,
            key=f"{self.title}/sensitivity",
            mode="a",
            format="table",
        )


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
