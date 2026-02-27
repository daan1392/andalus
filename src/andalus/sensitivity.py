"""Module containing the Sensitivity class, which is used to represent
and manage sensitivity data. Sensitivities inherit from pandas DataFrames,
and have some additional methods for plotting and loading from Serpent output.
"""

__all__ = ["Sensitivity"]
__version__ = "0.1.1"
__author__ = "Daan Houben"

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import serpentTools
from sandy import zam2latex

from andalus.constants import MT_TRANSLATION, PERT_LABELS


class Sensitivity(pd.DataFrame):
    """
    Data structure for nuclear data sensitivity analysis.

    Inherits from pandas.DataFrame and maintains metadata across
    slicing and transformation operations.

    Parameters
    ----------
    data : array-like, Iterable, dict, or scalar value
        Contains data to be stored in the DataFrame.
    title : str, optional
        The name of the benchmark or experiment (e.g., 'HMF001').
    kind : str, optional
        The response type, by default 'keff'.
    *args : list
        Additional positional arguments for pd.DataFrame.
    **kwargs : dict
        Additional keyword arguments for pd.DataFrame.

    Attributes
    ----------
    title : str
        The identifier for the sensitivity data.
    kind : str
        The type of observable the sensitivity relates to.
    """

    _metadata = ["title", "kind"]

    def __init__(self, data=None, *args, **kwargs):
        # Extract metadata from kwargs before initializing DataFrame
        self.title = kwargs.pop("title", None)
        self.kind = kwargs.pop("kind", "keff")
        super().__init__(data, *args, **kwargs)

    @property
    def _constructor(self):
        """
        Ensures that pandas operations return a Sensitivity instance.

        Returns
        -------
        type
            The Sensitivity class.
        """
        return Sensitivity

    @classmethod
    def from_serpent(
        cls,
        sens0_path: str,
        title: str,
        kind: str = "keff",
        materiallist=None,
        zailist=None,
        pertlist=None,
    ):
        """
        Returns a sensitivity object from a Serpent sensitivity file.

        Parameters
        ----------
        sens0_path : str
            Path to the Serpent sensitivity file.
        title : str
            Title for the sensitivity data.
        materiallist : list, optional
            List of materials to include. Default is ['total'].
        zailist : list, optional
            List of ZAIs to include. Default is None, which includes all ZAIs.
        pertlist : list, optional
            List of perturbations to include. Default is None, which corresponds to all
            perturbations in the sensitivity file.

        Returns
        -------
        Sensitivity
            Sensitivity object containing the sensitivity data.

        Raises
        ------
        SensitivityError
            If there is an error reading the sensitivity file.
        """
        sens = serpentTools.read(sens0_path)

        materiallist = materiallist or sens.materials
        zailist = zailist or sens.zais
        if "total" in zailist:
            sens.zais.pop("total")
        pertlist = pertlist or sens.perts

        records = []
        for material in materiallist:
            for zai in zailist:
                for pert in pertlist:
                    for i in range(len(sens.energies) - 1):
                        record = {
                            "ZAI": zai,
                            "MT": pert,
                            "E_min_eV": np.round(sens.energies[i] * 1e6, decimals=6),
                            "E_max_eV": np.round(sens.energies[i + 1] * 1e6, decimals=6),
                            title: sens.sensitivities[kind][sens.materials[material]][sens.zais[zai]][sens.perts[pert]][
                                i, 0
                            ],
                            f"{title}_std": sens.sensitivities[kind][sens.materials[material]][sens.zais[zai]][
                                sens.perts[pert]
                            ][i, 1],
                        }
                        records.append(record)

        df = pd.DataFrame(records)
        df.set_index(["ZAI", "MT", "E_min_eV", "E_max_eV"], inplace=True)
        if isinstance(df.index, pd.MultiIndex):
            new_levels = df.index.levels[1].map(lambda x: MT_TRANSLATION.get(x, x))
            df.index = df.index.set_levels(new_levels, level="MT")
        return cls(df, title=title, kind=kind)

    @classmethod
    def from_hdf5(cls, file_path, title, kind: str = "keff"):
        """
        Create a Sensitivity instance from an HDF5 file.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file containing the sensitivity data.
        title : str
            Title of the sensitivity data to load.
        kind : str, optional
            Type of sensitivity data (e.g., "keff"). Default is "keff".

        Returns
        -------
        Sensitivity
            Sensitivity object containing the loaded sensitivity data.
        """
        return cls(pd.read_hdf(file_path, key=f"{kind}/{title}/sensitivity"), title=title, kind=kind)

    def to_hdf5(self, file_path):
        """
        Save the Sensitivity instance to an HDF5 file.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file where the sensitivity data will be saved.
        title : str
            Title of the sensitivity data to save.
        kind : str, optional
            Type of sensitivity data (e.g., "keff"). Default is "keff".
        """
        self.to_hdf(
            path_or_buf=file_path,
            key=f"{self.kind}/{self.title}/sensitivity",
            mode="a",
            format="table",
        )

    @property
    def isotopes(self):
        """Returns a list of human readable isotopes.

        Returns
        -------
        list of str
            List of human readable isotopes.
        """
        unique_zais = self.index.get_level_values("ZAI").unique()
        return [zam2latex(z) for z in unique_zais]

    def rename_sensitivity(self, new_title: str) -> "Sensitivity":
        """
        Rename the benchmark columns and update the title metadata.

        Parameters
        ----------
        new_title : str
            The new identifier for the benchmark columns.

        Returns
        -------
        Sensitivity
            A new Sensitivity object with updated columns and title metadata.
        """
        s = self.copy()
        s.columns = [new_title, f"{new_title}_std"]

        s.title = new_title

        return s

    def plot_sensitivity(self, zais, perts, ax=None, **kwargs):
        """
        Return a plot of the sensitivity profile normalized by unit lethargy

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
        """
        if ax is None:
            _, ax = plt.subplots()

        # Use the column name directly if title metadata isn't set
        label_base = getattr(self, "title", self.columns[0])

        for zai, pert in [(z, p) for z in zais for p in perts]:
            try:
                subset = self.loc[zai, pert]
            except KeyError:
                continue

            e_min = subset.index.get_level_values("E_min_eV")
            e_max = subset.index.get_level_values("E_max_eV")
            lethargy_width = np.log(e_max / e_min)

            val = subset.iloc[:, 0] / lethargy_width
            err = subset.iloc[:, 1] * np.abs(val)

            p = ax.step(
                e_min,
                val,
                where="post",
                label=f"{label_base}: {zam2latex(zai)} {PERT_LABELS.get(pert, pert)}",
                **kwargs,
            )

            ax.fill_between(e_min, val - err, val + err, step="post", alpha=0.3, color=p[0].get_color())

        ax.set(xscale="log", xlabel="Energy (eV)", ylabel="Sensitivity / unit lethargy")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()
        return ax


if __name__ == "__main__":
    # Example usage
    sens = Sensitivity.from_serpent(
        sens0_path=r"C:\Users\dhouben\Documents\andalus\tests\hmf001.ser_sens0.m",
        title="ExampleSensitivity",
        kind="keff",
        materiallist=["total"],
        pertlist=["mt 18 xs", "mt 102 xs"],
    )
    # sens.plot_sensitivity(zais=[922380], perts=[18, 102])
    # plt.show()
    print(sens.index)
    print(sens.isotopes)
    sens.to_hdf5(r"C:\Users\dhouben\Documents\andalus\tests\example_sensitivity.h5")
