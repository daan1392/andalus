"""Module containing the FluxSpectrum class, which is used to represent
and manage energy-dependent flux data.
"""

__all__ = ["FluxSpectrum"]

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from andalus.utils import read_serpent


class FluxSpectrum(pd.DataFrame):
    """
    Energy-dependent flux spectrum.

    Inherits from ``pandas.DataFrame`` with a 2-level MultiIndex
    ``(E_min_eV, E_max_eV)`` and columns ``flux`` and ``flux_std``.

    Parameters
    ----------
    data : array-like, Iterable, dict, or scalar value
        Contains data to be stored in the DataFrame.
    title : str, optional
        The name of the benchmark or experiment (e.g., ``'HMF001'``).
    *args : list
        Additional positional arguments forwarded to ``pd.DataFrame``.
    **kwargs : dict
        Additional keyword arguments forwarded to ``pd.DataFrame``.

    Attributes
    ----------
    title : str
        The identifier for the flux spectrum data.
    """

    _metadata = ["title"]

    def __init__(self, data=None, *args, **kwargs):
        self.title = kwargs.pop("title", None)
        super().__init__(data, *args, **kwargs)

    @property
    def _constructor(self):
        """
        Ensures that pandas operations return a ``FluxSpectrum`` instance.

        Returns
        -------
        type
            The ``FluxSpectrum`` class.
        """
        return FluxSpectrum

    @property
    def ealf(self) -> float:
        r"""
        Energy of Average Lethargy causing Fission (EALF) in eV.

        Computed as the flux-weighted geometric mean energy:

        .. math::

            \text{EALF} = \exp\!\left(
                \frac{\sum_i \phi_i \ln \bar{E}_i}{\sum_i \phi_i}
            \right)

        where :math:`\bar{E}_i = \sqrt{E_{\min,i} \cdot E_{\max,i}}` is the
        geometric mean energy of bin *i*.

        Returns
        -------
        float
            The EALF in electronvolts (eV).

        Raises
        ------
        ValueError
            If the total flux is zero.
        """
        e_min = self.index.get_level_values("E_min_eV").to_numpy(dtype=float)
        e_max = self.index.get_level_values("E_max_eV").to_numpy(dtype=float)
        e_mid = np.sqrt(e_min * e_max)
        phi = self["flux"].to_numpy(dtype=float)
        phi_total = phi.sum()
        if phi_total == 0.0:
            raise ValueError("Cannot compute EALF: total flux is zero.")
        return float(np.exp(np.dot(phi, np.log(e_mid)) / phi_total))

    @property
    def mean_energy(self) -> float:
        r"""
        Flux-weighted arithmetic mean energy in eV.

        .. math::

            \langle E \rangle =
            \frac{\sum_i \phi_i \bar{E}_i}{\sum_i \phi_i}

        where :math:`\bar{E}_i = \sqrt{E_{\min,i} \cdot E_{\max,i}}`.

        Returns
        -------
        float
            The flux-weighted mean energy in electronvolts (eV).

        Raises
        ------
        ValueError
            If the total flux is zero.
        """
        e_min = self.index.get_level_values("E_min_eV").to_numpy(dtype=float)
        e_max = self.index.get_level_values("E_max_eV").to_numpy(dtype=float)
        e_mid = np.sqrt(e_min * e_max)
        phi = self["flux"].to_numpy(dtype=float)
        phi_total = phi.sum()
        if phi_total == 0.0:
            raise ValueError("Cannot compute mean energy: total flux is zero.")
        return float(np.dot(phi, e_mid) / phi_total)

    @classmethod
    def from_serpent(
        cls,
        det_path: str,
        det_name: str,
        title: str | None = None,
    ) -> "FluxSpectrum":
        """
        Create a ``FluxSpectrum`` from a Serpent detector output file.

        Parameters
        ----------
        det_path : str
            Path to the Serpent detector output file (e.g., ``*_det0.m``).
        det_name : str
            Name of the detector to read from the file.
        title : str, optional
            Title for the returned object. Defaults to ``det_name``.

        Returns
        -------
        FluxSpectrum
            A ``FluxSpectrum`` populated with the tally values and
            uncertainties from the detector.
        """
        reader = read_serpent(det_path)
        det = reader.detectors[det_name]

        # Energy grid: shape (N_bins, 3) – columns are [E_lo, E_hi, E_mid]
        # in MeV, as produced by serpentTools.
        e_grid = det.grids["E"]
        e_min = np.round(e_grid[:, 0] * 1e6, decimals=6)
        e_max = np.round(e_grid[:, 1] * 1e6, decimals=6)

        flux = det.tallies.squeeze()
        flux_std = det.errors.squeeze() * np.abs(flux)

        index = pd.MultiIndex.from_arrays(
            [e_min, e_max], names=["E_min_eV", "E_max_eV"]
        )
        return cls(
            pd.DataFrame({"flux": flux, "flux_std": flux_std}, index=index),
            title=title or det_name,
        )

    @classmethod
    def from_hdf5(
        cls,
        file_path: str,
        title: str,
        kind: str = "keff",
    ) -> "FluxSpectrum":
        """
        Create a ``FluxSpectrum`` from an HDF5 file.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file.
        title : str
            Title of the case to load.
        kind : str, optional
            Observable kind used as the top-level HDF5 group
            (e.g., ``"keff"``). Default is ``"keff"``.

        Returns
        -------
        FluxSpectrum
            A ``FluxSpectrum`` loaded from the HDF5 file.
        """
        return cls(
            pd.read_hdf(file_path, key=f"{kind}/{title}/flux"),
            title=title,
        )

    def to_hdf5(self, file_path: str, kind: str = "keff") -> None:
        """
        Save the ``FluxSpectrum`` to an HDF5 file.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file.
        kind : str, optional
            Observable kind used as the top-level HDF5 group
            (e.g., ``"keff"``). Default is ``"keff"``.
        """
        self.to_hdf(
            path_or_buf=file_path,
            key=f"{kind}/{self.title}/flux",
            mode="a",
            format="table",
        )

    def plot_spectrum(
        self,
        ax=None,
        normalize: bool = True,
        **kwargs,
    ):
        """
        Plot the flux spectrum per unit lethargy.

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional
            Axes to plot on. A new figure and axes are created when ``None``.
        normalize : bool, optional
            When ``True`` (default) the flux is normalized so that the sum
            over all bins equals 1 before dividing by the lethargy width.
        **kwargs
            Additional keyword arguments forwarded to
            ``matplotlib.axes.Axes.step``.

        Returns
        -------
        matplotlib.axes.Axes
            The axes containing the plot.
        """
        if ax is None:
            _, ax = plt.subplots(figsize=(5, 4), layout="constrained")

        e_min = self.index.get_level_values("E_min_eV").to_numpy(dtype=float)
        e_max = self.index.get_level_values("E_max_eV").to_numpy(dtype=float)
        lethargy_width = np.log(e_max / e_min)

        flux = self["flux"].to_numpy(dtype=float)
        flux_std = self["flux_std"].to_numpy(dtype=float)

        if normalize:
            phi_total = flux.sum()
            if phi_total > 0:
                flux = flux / phi_total
                flux_std = flux_std / phi_total

        phi = flux / lethargy_width
        phi_err = flux_std / lethargy_width

        label = kwargs.pop("label", self.title)
        p = ax.step(e_min, phi, where="post", label=label, **kwargs)
        ax.fill_between(
            e_min,
            phi - phi_err,
            phi + phi_err,
            step="post",
            alpha=0.3,
            color=p[0].get_color(),
        )

        ax.set(
            xscale="log",
            xlabel="Energy (eV)",
            ylabel=r"$\phi(E)\,/\,\Delta u$ (normalized)",
        )
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()

        return ax
