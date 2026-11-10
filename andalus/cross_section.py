"""Module containing the CrossSectionMG class, which is used to represent
and manage multigroup (MG) nuclear data (cross sections, nubar, chi, ...).
Cross sections inherit from pandas DataFrames with a
``(ZAI, MT, E_min_eV, E_max_eV)`` MultiIndex and a single column holding
the values of one library. They can be read from NJOY ERRORR files via SANDY,
stored in HDF5, and combined with relative sensitivity profiles to estimate
the effect of a change in nuclear data on a response (e.g. keff).
"""

__all__ = ["CrossSectionMG"]

import numpy as np
import pandas as pd
import sandy

INDEX_NAMES = ["ZAI", "MT", "E_min_eV", "E_max_eV"]

# Offsets used to keep different ENDF files apart in the MT level. They match
# the convention used by ``Covariance`` (e.g. 35018 is the prompt fission chi).
_MT_OFFSETS = {"errorr34": 34000, "errorr35": 35000}


class CrossSectionMG(pd.DataFrame):
    """
    Multigroup nuclear data with a ``(ZAI, MT, E_min_eV, E_max_eV)`` index.

    The frame has a single column, named after the library the data comes
    from (e.g. ``"jeff40"``). Values are in the natural units of each MT:
    barns for cross sections, dimensionless for nubar, and group fractions
    (summing to 1) for chi.

    Attributes
    ----------
    temperature : float, optional
        Temperature at which the data was generated.

    Notes
    -----
    Sensitivity coefficients are *relative*, :math:`S = (dk/k)/(d\\sigma/\\sigma)`.
    Differences between two libraries must therefore be expressed relative to
    the library the sensitivities were computed with, see
    :meth:`relative_difference` and :func:`andalus.utils.delta_response`.
    """

    _metadata = ["temperature"]

    @property
    def _constructor(self):
        return CrossSectionMG

    @property
    def label(self) -> str | None:
        """Name of the library (the column name) if the frame has one column."""
        return str(self.columns[0]) if self.shape[1] == 1 else None

    @property
    def zais(self) -> list[int]:
        """Sorted ZAIs present in the data."""
        return sorted(self.index.get_level_values("ZAI").unique())

    # ------------------------------------------------------------------ I/O
    @classmethod
    def from_errorr(
        cls,
        files: dict[str, str],
        zai: int,
        mts: list[int] | None = None,
        temperature: float | None = None,
        label: str = "xs",
    ) -> "CrossSectionMG":
        """
        Construct a CrossSectionMG from NJOY ERRORR output files using SANDY.

        Parameters
        ----------
        files : dict[str, str]
            Dictionary mapping section names (``'errorr31'``, ``'errorr33'``,
            ``'errorr34'``, ``'errorr35'``) to file paths. The MT numbers of
            errorr34/errorr35 are offset by 34000/35000, as in ``Covariance``.
        zai : int
            Nuclide identifier (ZAI).
        mts : list of int, optional
            Filter for specific MT numbers (after offsetting).
        temperature : float, optional
            Temperature at which the data was generated.
        label : str, default "xs"
            Column name, i.e. the name of the library.

        Returns
        -------
        CrossSectionMG
            Multigroup data with index ``(ZAI, MT, E_min_eV, E_max_eV)``.
        """
        parts = [cls._errorr_to_series(key, sandy.Errorr.from_file(path)) for key, path in files.items()]
        ser = pd.concat(parts)

        if mts:
            ser = ser[ser.index.get_level_values("MT").isin(mts)]

        ser = pd.concat({zai: ser}, names=["ZAI"])
        obj = cls(ser.rename(label).to_frame().sort_index())
        obj.temperature = temperature
        return obj

    @staticmethod
    def _errorr_to_series(key: str, errorr: sandy.Errorr) -> pd.Series:
        """Convert a sandy.Errorr object to a Series indexed by (MT, E_min_eV, E_max_eV)."""
        xs = errorr.get_xs().data.droplevel("MAT", axis=1)
        energies = pd.IntervalIndex(xs.index)

        mts = xs.columns.to_numpy() + _MT_OFFSETS.get(key, 0)
        n_groups = len(xs)
        index = pd.MultiIndex.from_arrays(
            [
                np.repeat(mts, n_groups),
                np.tile(energies.left.to_numpy(), len(mts)),
                np.tile(energies.right.to_numpy(), len(mts)),
            ],
            names=["MT", "E_min_eV", "E_max_eV"],
        )
        # Column-major ravel: all groups of the first MT, then the second, ...
        return pd.Series(xs.to_numpy().ravel(order="F"), index=index)

    @classmethod
    def from_zai_dict(cls, items: dict[int, "CrossSectionMG"]) -> "CrossSectionMG":
        """
        Combine single-nuclide objects into one frame.

        Parameters
        ----------
        items : dict[int, CrossSectionMG]
            Mapping of ZAI to data. Each value may have a 3-level
            ``(MT, E_min_eV, E_max_eV)`` or a 4-level index; in the latter case
            the ZAI level is replaced by the dictionary key.

        Returns
        -------
        CrossSectionMG
            Combined data sorted by index.
        """
        if not items:
            return cls(pd.DataFrame(columns=["xs"], index=pd.MultiIndex.from_arrays([[]] * 4, names=INDEX_NAMES)))

        parts = {}
        for zai, xs in items.items():
            df = pd.DataFrame(xs)
            if df.index.nlevels == 4:
                df = df.droplevel("ZAI")
            parts[zai] = df
        out = pd.concat(list(parts.values()), keys=list(parts.keys()), names=["ZAI"]).sort_index()
        return cls(out)

    @classmethod
    def from_hdf5(cls, file_path: str, zais: list[int] | None = None, mts: list[int] | None = None) -> "CrossSectionMG":
        """
        Load multigroup data from an HDF5 file written by :meth:`to_hdf5`.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file.
        zais : list of int, optional
            ZAIs to load. Default: all ZAIs with stored cross sections.
        mts : list of int, optional
            Filter for specific MT numbers.

        Returns
        -------
        CrossSectionMG
            The loaded data.
        """
        items = {}
        temperature = None
        with pd.HDFStore(file_path, mode="r") as store:
            for key in store.keys():
                parts = key.strip("/").split("/")
                if len(parts) != 3 or not parts[0].startswith("zai_") or parts[1:] != ["xs", "data"]:
                    continue
                zai = int(parts[0].split("_")[1])
                if zais is not None and zai not in zais:
                    continue
                df = store[key]
                if mts is not None:
                    df = df[df.index.get_level_values("MT").isin(mts)]
                items[zai] = df
                temperature = getattr(store.get_storer(key).attrs, "temperature", None)

        obj = cls.from_zai_dict(items)
        obj.temperature = temperature
        return obj

    def to_hdf5(self, file_path: str):
        """
        Append the data to an HDF5 file, one table per ZAI under ``zai_{ZAI}/xs/data``.

        The layout is compatible with the one used by ``Covariance.to_hdf5``,
        so both can live in the same file.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file.
        """
        with pd.HDFStore(file_path, mode="a") as store:
            for zai in self.zais:
                key = f"zai_{zai}/xs/data"
                df = pd.DataFrame(self.xs(zai, level="ZAI"))
                store.put(key, df, format="table", complevel=9, complib="blosc")
                store.get_storer(key).attrs.temperature = getattr(self, "temperature", None)

    # ------------------------------------------------------------ operations
    def adjusted(self, adjustment: pd.Series, label: str = "posterior") -> "CrossSectionMG":
        r"""
        Apply a relative adjustment, e.g. the output of GLLS.

        .. math::
            \sigma^{post}_i = \sigma_i \, (1 + \delta_i)

        Bins without an entry in ``adjustment`` are left unchanged.

        Parameters
        ----------
        adjustment : pd.Series
            Relative adjustment :math:`\delta_i` with index ``(ZAI, MT, E_min_eV, E_max_eV)``.
        label : str, default "posterior"
            Column name of the returned object.

        Returns
        -------
        CrossSectionMG
            The adjusted multigroup data.
        """
        factor = (1.0 + pd.Series(adjustment)).reindex(self.index).fillna(1.0)
        out = CrossSectionMG((self._as_series() * factor).rename(label).to_frame())
        out.temperature = getattr(self, "temperature", None)
        return out

    def _as_series(self) -> pd.Series:
        if self.shape[1] != 1:
            raise ValueError("CrossSectionMG must have exactly one column (one library) for this operation.")
        return pd.Series(self.iloc[:, 0])

    @staticmethod
    def _other_series(other) -> pd.Series:
        if isinstance(other, pd.DataFrame):
            if other.shape[1] != 1:
                raise ValueError("`other` must have exactly one column (one library).")
            return pd.Series(other.iloc[:, 0])
        return pd.Series(other)

    def relative_difference(self, other) -> pd.Series:
        r"""
        Difference with a reference library, relative to that reference.

        .. math::
            \delta_i = \frac{\sigma_i - \sigma^{ref}_i}{\sigma^{ref}_i}

        This is the dimensionless quantity that must be multiplied with a
        relative sensitivity coefficient. ``other`` must be the library the
        sensitivities were computed with. Bins where the reference is zero
        (e.g. below a reaction threshold) get :math:`\delta = 0`.
        Only bins present in both objects are returned.

        Parameters
        ----------
        other : CrossSectionMG or pd.Series
            Reference library with a compatible ``(ZAI, MT, E_min_eV, E_max_eV)`` index.

        Returns
        -------
        pd.Series
            Relative difference, named ``"relative_difference"``.
        """
        a = self._as_series()
        b = self._other_series(other)
        idx = a.index.intersection(b.index)
        if len(idx) == 0:
            raise ValueError("No common (ZAI, MT, E_min_eV, E_max_eV) bins between the two cross section sets.")
        a, b = a.loc[idx], b.loc[idx]
        rel = (a - b) / b.where(b != 0)
        return rel.fillna(0.0).rename("relative_difference")
