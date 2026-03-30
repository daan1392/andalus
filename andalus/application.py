"""Module containing the Application and ApplicationSuite classes,
which are used to represent and manage application data.
"""

__all__ = ["Application", "ApplicationSuite"]

from dataclasses import dataclass, field, replace

import h5py
import pandas as pd

from andalus.sensitivity import Sensitivity
from andalus.utils import read_serpent


@dataclass(frozen=True)
class Application:
    """
    An application is a calculation without an associated measurement.

    Attributes
    ----------
    title : str
        The unique name or identifier for the application.
    kind : str
        The kind of the observable (e.g., "keff", "void").
    c : float
        The calculated value (Nominal).
    dc : float
        The uncertainty of the calculation.
    s : Sensitivity
        The energy-dependent sensitivity profiles.
    """

    title: str
    kind: str
    c: float
    dc: float
    s: Sensitivity
    m: float | None = None
    dm: float | None = None

    def __post_init__(self):
        if not isinstance(self.title, str):
            raise TypeError(f"Title '{self.title}' must be a string")
        if self.kind not in ["keff", "void"]:
            raise ValueError(f"Type '{self.kind}' not implemented.")
        if not isinstance(self.c, (int, float)):
            raise TypeError(f"Calculated value {self.c} must be a number")
        if not isinstance(self.dc, (int, float)):
            raise TypeError(f"Calculated uncertainty {self.dc} must be a number")
        if not isinstance(self.s, Sensitivity):
            raise TypeError(f"Sensitivity {self.s} must be a Sensitivity object")
        if not isinstance(self.m, (int, float, type(None))):
            raise TypeError(f"Measured value {self.m} must be a number or None")
        if not isinstance(self.dm, (int, float, type(None))):
            raise TypeError(f"Measured uncertainty {self.dm} must be a number or None")

    @classmethod
    def from_serpent(
        cls,
        title: str,
        sens0_path: str,
        results_path: str,
        kind: str = "keff",
        materials=None,
        zailist=None,
        pertlist=None,
        m: float | None = None,
        dm: float | None = None,
    ):
        """Method to create an Application object from a serpent output.

        Parameters
        ----------
        title : str
            title of the application.
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
        m : float, optional
            Measured value for the application, by default None.
        dm : float, optional
            Uncertainty of the measured value, by default None.

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
            kind=kind,
            materiallist=materials,
            zailist=zailist,
            pertlist=pertlist,
        )

        return cls(title=title, kind=kind, c=c, dc=dc, s=sensitivity, m=m, dm=dm)

    @classmethod
    def from_hdf5(cls, file_path, title: str, kind: str = "keff"):
        """
        Create an Application instance from an HDF5 file.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file containing the application data.
        title : str
            Title of the application to load.
        kind : str, optional
            Type of application (e.g., "keff"). Default is "keff".

        Returns
        -------
        Application
            A new Application instance with the loaded data.
        """
        with h5py.File(file_path, "r") as f:
            if kind not in f:
                raise KeyError(f"Application type '{kind}' not found in {file_path}")
            if title not in f[kind]:
                raise KeyError(f"Application '{title}' not found in {file_path}")

            grp = f[kind][title]
            c = grp.attrs["c"]
            dc = grp.attrs["dc"]
            m = grp.attrs["m"] if "m" in grp.attrs else None
            dm = grp.attrs["dm"] if "dm" in grp.attrs else None

        return cls(
            title=title,
            kind=kind,
            c=c,
            dc=dc,
            s=Sensitivity.from_hdf5(file_path, title=title, kind=kind),
            m=m,
            dm=dm,
        )

    def to_hdf5(self, file_path="benchmarks.h5"):
        """
        Save the application data to an HDF5 file.

        Parameters
        ----------
        file_path : str, optional
            The path to the HDF5 file where the application data will be saved.
              Default is 'benchmarks.h5'.
        """
        with h5py.File(file_path, "a") as f:
            # Create group for this application if it exists
            # if self.title in f[self.kind]:
            #     del f[f"{self.kind}/{self.title}"]

            # Create group and save attributes
            grp = f.create_group(f"{self.kind}/{self.title}")
            grp.attrs["c"] = self.c
            grp.attrs["dc"] = self.dc
            if self.m is not None:
                grp.attrs["m"] = self.m
            if self.dm is not None:
                grp.attrs["dm"] = self.dm

        # Save sensitivity DataFrame using pandas to_hdf
        self.s.to_hdf(file_path, key=f"{self.kind}/{self.title}/sensitivity", mode="a", format="table")

    def print_summary(self):
        """Print a quick summary of an application object."""
        print(f"Application: {self.title}")
        print(f"Type: {self.kind}")
        print(f"Calculated: {self.c} ± {self.dc}")
        print(f"Measured: {self.m} ± {self.dm}")

    def plot_sensitivity(self, zais, perts, ax=None, **kwargs):
        """Plot the sensitivity profiles for the application.

        Parameters
        ----------
        zais : list
            List of zais to be included in the plot.
        perts : list
            List of perts to be included in the plot.
        ax : plt.Axes, optional
            Ax for the plot to be displayed. If None, a new figure and axis will be created.
        **kwargs
            Additional keyword arguments to be passed to the plotting function.

        Returns
        -------
        matplotlib.axes.Axes
            The Axes object containing the plot.
        """
        return self.s.plot_sensitivity(zais=zais, perts=perts, ax=ax, **kwargs)


@dataclass
class ApplicationSuite:
    """A applicationsuite is a combined set of application objects.

    Attributes
    ----------
    applications : dict[str, Application]
        A dictionary of application objects, indexed by their title.
    """

    applications: dict[str, Application] = field(default_factory=dict)

    def __post_init__(self):
        for application in self.applications.values():
            if not isinstance(application, Application):
                raise TypeError(f"Application {application.title} is not an Application object")

    def __getitem__(self, key):
        return self.applications[key]

    def __iter__(self):
        return iter(self.applications.values())

    def __len__(self):
        return len(self.applications)

    def __contains__(self, key):
        return key in self.applications

    def items(self):
        """
        Return the suite's applications as (title, Application) pairs.

        Returns
        -------
        dict_items
            A view of the internal application dictionary items,
            which are of type Application.
        """
        return self.applications.items()

    def values(self):
        """Return an iterator over the application objects."""
        return self.applications.values()

    def keys(self):
        """Return an iterator over the application titles."""
        return self.applications.keys()

    @property
    def titles(self) -> list:
        """Returns a list of application titles in the suite.

        Returns
        -------
        list of str
            List of application titles in the suite.
        """
        if not self.applications:
            raise AssertionError("No applications in the suite.")
        return list(self.applications.keys())

    @property
    def kinds(self) -> pd.Series:
        """Returns a pd.Series of application types in the suite.

        Returns
        -------
        pd.Series of str
            Series of application types in the suite.
        """
        if not self.applications:
            raise AssertionError("No applications in the suite.")
        return pd.Series([application.kind for application in self.applications.values()], index=self.titles)

    @property
    def zais(self) -> list:
        """Returns a list of unique ZAIs in the sensitivity data of the applications in the suite.

        Returns
        -------
        list of int
            List of unique ZAIs in the sensitivity data of the applications in the suite.
        """
        if not self.applications:
            raise AssertionError("No applications in the suite.")
        zais = set()
        for application in self.applications.values():
            zais.update(application.s.index.get_level_values("ZAI").unique())
        return sorted(zais)

    @property
    def c(self) -> pd.Series:
        """Returns a pd.Series of application calculated values in the suite.

        Returns
        -------
        pd.Series of float
            Series of application calculated values in the suite.
        """
        if not self.applications:
            raise AssertionError("No applications in the suite.")
        return pd.Series([application.c for application in self.applications.values()], index=self.titles)

    @property
    def dc(self) -> pd.Series:
        """Returns a pd.Series of application calculated uncertainties in the suite.

        Returns
        -------
        pd.Series of float
            Series of application calculated uncertainties in the suite.
        """
        if not self.applications:
            raise AssertionError("No applications in the suite.")
        return pd.Series([application.dc for application in self.applications.values()], index=self.titles)

    @property
    def s(self) -> pd.DataFrame:
        """Returns a pd.DataFrame of sensitivity objects in the suite.

        Returns
        -------
        pd.DataFrame
            DataFrame of sensitivity objects in the suite.
        """
        if not self.applications:
            raise AssertionError("No applications in the suite.")
        return pd.concat(
            [application.s.iloc[:, 0].to_frame() for application in self.applications.values()], axis=1
        ).fillna(0)

    @property
    def ds(self) -> pd.DataFrame:
        """Returns a pd.DataFrame of sensitivity uncertainties in the suite.

        Returns
        -------
        pd.DataFrame
            DataFrame of sensitivity uncertainties in the suite.
        """
        if not self.applications:
            raise AssertionError("No applications in the suite.")
        return pd.concat(
            [application.s.iloc[:, 1].to_frame() for application in self.applications.values()], axis=1
        ).fillna(0)

    @property
    def m(self) -> pd.Series:
        """Returns a pd.Series of application measured values in the suite.

        Returns
        -------
        pd.Series of float
            Series of application measured values in the suite.
        """
        if not self.applications:
            raise AssertionError("No applications in the suite.")
        return pd.Series([application.m for application in self.applications.values()], index=self.titles)

    @property
    def dm(self) -> pd.Series:
        """Returns a pd.Series of application measured uncertainties in the suite.

        Returns
        -------
        pd.Series of float
            Series of application measured uncertainties in the suite.
        """
        if not self.applications:
            raise AssertionError("No applications in the suite.")
        return pd.Series([application.dm for application in self.applications.values()], index=self.titles)

    @classmethod
    def from_list(cls, applications: list[Application]):
        """Method to create an ApplicationSuite instance from a list of Application objects.

        Parameters
        ----------
        applications : list[Application]
            A list of Application objects to be included in the suite.

        Returns
        -------
        ApplicationSuite
            An instance of ApplicationSuite containing the provided applications.
        """
        return cls(applications={app.title: app for app in applications})

    @classmethod
    def from_hdf5(cls, file_path: str, titles: list, kind: str = "keff"):
        """Retrieve a set of applications from a database.

        Parameters
        ----------
        file_path : str
            file path where the database is located.
        titles : list, optional
            Titles which have to be extracted from the database, if None
            return all the applications available in the database, by default None.

        Returns
        -------
        BenchmarkSuite
            Returns a BenchmarkSuite object containing the imported Benchmark objects.
        """
        if not titles:
            with h5py.File(file_path, "r") as f:
                titles = list(f[kind].keys())

        return cls(applications={title: Application.from_hdf5(file_path, title) for title in titles})

    @classmethod
    def from_yaml(cls, path: str):
        """Factory method to create an ApplicationSuite instance from a YAML configuration file.

        Parameters
        ----------
        path : str
            The path to the YAML configuration file.

        Returns
        -------
        ApplicationSuite
            An instance of ApplicationSuite populated with data from the YAML file.
        """
        import yaml

        with open(path) as f:
            config = yaml.safe_load(f)

        applications = {}
        for application_config in config.get("applications", []):
            if "sens0_path" in application_config and "results_path" in application_config:
                application = Application.from_serpent(
                    title=application_config["title"],
                    sens0_path=application_config["sens0_path"],
                    results_path=application_config["results_path"],
                    kind=application_config.get("kind", "keff"),
                    materials=application_config.get("materials"),
                    zailist=application_config.get("zailist"),
                    pertlist=application_config.get("pertlist"),
                    m=application_config.get("m") if "m" in application_config else None,
                    dm=application_config.get("dm") if "dm" in application_config else None,
                )
                applications[application.title] = application
            elif "hdf5_path" in application_config:
                application = Application.from_hdf5(
                    file_path=application_config["hdf5_path"],
                    title=application_config["title"],
                    kind=application_config.get("kind", "keff"),
                )
                applications[application.title] = application

        return cls(applications=applications)

    def get(self, title: str) -> Application | None:
        """
        Get an application from the suite.

        Parameters
        ----------
        title : str
            Title of the application to be retrieved.

        Returns
        -------
        Application
            Application object.
        """
        return self.applications.get(title)

    def remove(self, title: str):
        """
        Remove application from the suite.

        Parameters
        ----------
        title : str
            Title of the application to be removed.
        """
        self.applications.pop(title, None)

    def update_c(self, new_c: pd.Series) -> "ApplicationSuite":
        """
        Create a new ApplicationSuite with updated calculated values.

        This method is typically used to generate a posterior suite after
        an assimilation update (e.g., GLLS).

        Parameters
        ----------
        new_c : pd.Series
            A series containing the updated 'c' values, indexed by
            application title.

        Returns
        -------
        ApplicationSuite
            A new instance of the suite containing updated Application objects.

        Raises
        ------
        KeyError
            If an applicaiton title in the suite is missing from the index of `new_c`.
        """
        return ApplicationSuite({title: replace(bm, c=new_c.loc[title]) for title, bm in self.items()})


if __name__ == "__main__":
    # Example usage
    app = Application.from_serpent(
        title="HMF001",
        results_path="data/hmf001.ser_res.m",
        sens0_path="data/hmf001.ser_sens0.m",
        m=1.0000,
        dm=0.00100,
    )
    app2 = Application.from_serpent(
        title="HMF002-001",
        results_path="data/hmf002-001.ser_res.m",
        sens0_path="data/hmf002-001.ser_sens0.m",
        m=1.0000,
        dm=0.00300,
    )
    app.print_summary()

    app_suite = ApplicationSuite.from_list([app, app2])

    print(app.m, app.dm)
    print(app2.m, app2.dm)

    print(app_suite.m)
    # import matplotlib.pyplot as plt

    # app.s.plot_sensitivity(zais=[922380], perts=[2, 4])
    # plt.show()
