"""Module containing the Covariance class, which is used to represent
and manage covariance data. Covariances inherit from pandas DataFrames.
Covariance objects can be saved to a sparse HDF5 format and reconstructed from it.
A covariance suite can be assembled from multiple Covariance objects, creating a block-diagonal matrix.
"""

__all__ = ["Covariance", "CovarianceSuite"]
__version__ = "0.1.1"
__author__ = "Daan Houben"

from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.sparse
from sandy.zam import zam2nuclide


class Covariance(pd.DataFrame):
    """
    Subclass of pd.DataFrame for handling individual nuclide covariance data.
    """

    _metadata = ["zai", "temperature", "err"]

    @property
    def _constructor(self):
        return Covariance

    @property
    def nuclide(self) -> str | None:
        """Return a string representation of the isotope based on ZAI."""
        return zam2nuclide(self.zai)

    @classmethod
    def from_hdf5(cls, file_path: str, zai: int, mts: list[int] | None = None) -> "Covariance":
        """
        Load a covariance matrix from HDF5 and reconstruct from sparse storage.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file.
        zai : int
            Nuclide identifier (ZAI).
        mts : list of int, optional
            Filter for specific MT numbers.

        Returns
        -------
        Covariance
            Reconstructed symmetric covariance matrix.
        """
        zai_str = str(zai)
        with pd.HDFStore(file_path, mode="r") as store:
            key = f"zai_{zai_str}/covariances/data"
            if key not in store:
                return cls()

            # 1. Component Extraction
            sparse_data = store[key]
            attrs = store.get_storer(key).attrs

            # 2. Index Reconstruction
            index = cls._reconstruct_index(store, zai_str, attrs)

            # 3. Filtering and Matrix Assembly
            matrix, final_index = cls._assemble_matrix(sparse_data, index, attrs.shape, mts)

            # 4. Object Initialization
            obj = cls(matrix, index=final_index, columns=final_index)
            obj.zai = zai
            obj.temperature = getattr(attrs, "temperature", None)
            obj.err = getattr(attrs, "err", None)
            return obj

    @staticmethod
    def _reconstruct_index(store: pd.HDFStore, zai_str: str, attrs) -> pd.Index | pd.MultiIndex:
        """
        Rebuild the pandas index from stored HDF5 levels.
        """
        if not attrs.is_multiindex:
            return store[f"zai_{zai_str}/covariances_index/values"]

        # Dynamically gather all index levels.
        index_levels = []
        for i in range(len(attrs.index_names)):
            key = f"zai_{zai_str}/covariances_index/level_{i}"
            if key in store:
                index_levels.append(store[key])
            else:
                break  # Stop if we hit a level that isn't there

        # Build the index
        idx = pd.MultiIndex.from_arrays(index_levels)

        # FIX: If the stored names are generic (level_0) or missing,
        # force them to our standard to prevent 'MT not found' errors.
        standard_names = ["MT", "E_min", "E_max"]
        if len(index_levels) == 3:
            idx.names = standard_names
        else:
            # Fallback for 4-level suites (ZAI, MT, E_min, E_max)
            idx.names = ["ZAI"] + standard_names[: len(index_levels) - 1]

        return idx

    @staticmethod
    def _assemble_matrix(
        sparse_data: pd.DataFrame, index: pd.Index, original_shape: tuple[int, int], mts: list[int] | None
    ) -> tuple[np.ndarray, pd.Index]:
        """
        Filter sparse coordinates and expand to a symmetric dense matrix.
        """
        shape = original_shape
        final_index = index

        # Handle MT Filtering
        if mts is not None:
            mask = index.get_level_values("MT").isin(mts)
            final_index = index[mask]

            # Map old integer positions to new ones after filtering
            idx_map = {old: new for new, old in enumerate(np.where(mask)[0])}
            sparse_data = sparse_data[
                sparse_data["row"].isin(idx_map.keys()) & sparse_data["col"].isin(idx_map.keys())
            ].copy()

            sparse_data["row"] = sparse_data["row"].map(idx_map)
            sparse_data["col"] = sparse_data["col"].map(idx_map)
            shape = (len(final_index), len(final_index))

        # Symmetrize Lower Triangular Matrix
        #
        coo = scipy.sparse.coo_matrix(
            (sparse_data["value"], (sparse_data["row"], sparse_data["col"])),
            shape=shape,
        )
        full_matrix = coo + coo.T
        full_matrix.setdiag(coo.diagonal())

        return full_matrix.toarray(), final_index

    def to_hdf5(self, file_path: str):
        """
        Save the matrix to HDF5 using sparse lower-triangular storage.

        Parameters
        ----------
        file_path : str
            Path to save the HDF5 file.
        """
        zai_str = str(self.zai)
        rows, cols = np.tril_indices(len(self))
        data = self.values[rows, cols]

        sparse_df = pd.DataFrame({"row": rows, "col": cols, "value": data})
        sparse_df = sparse_df[sparse_df["value"] != 0]

        with pd.HDFStore(file_path, mode="a") as store:
            # Save Index Levels
            for i, _name in enumerate(self.index.names):
                store.put(
                    f"zai_{zai_str}/covariances_index/level_{i}",
                    pd.Series(self.index.get_level_values(i)),
                    format="table",
                )

            # Save Data with Metadata
            key = f"zai_{zai_str}/covariances/data"
            store.put(key, sparse_df, format="table", complevel=9, complib="blosc")

            attrs = store.get_storer(key).attrs
            attrs.shape = self.shape
            attrs.index_names = self.index.names
            attrs.is_multiindex = True
            attrs.zai = self.zai
            attrs.temperature = getattr(self, "temperature", None)

    def correlation(self) -> pd.DataFrame:
        """
        Calculate the correlation matrix from the covariance matrix.

        Returns
        -------
        pd.DataFrame
            Correlation matrix with values between -1 and 1.
        """
        diag = np.sqrt(np.diag(self.values))
        # Prevent division by zero for bins with 0 uncertainty
        diag[diag == 0] = 1.0

        outer_std = np.outer(diag, diag)
        corr_values = self.values / outer_std
        return pd.DataFrame(corr_values, index=self.index, columns=self.columns).fillna(0)


@dataclass
class CovarianceSuite:
    """
    Container for global nuclear data covariance systems.

    This class manages the transition from independent nuclide matrices
    to a fully correlated global system, often used in Least Squares adjustments.

    Parameters
    ----------
    matrix : pd.DataFrame
        The unified global covariance matrix with a 5-level MultiIndex:
        (ZAI, MF, MT, E_min, E_max).
    """

    matrix: pd.DataFrame

    @classmethod
    def from_hdf5(
        cls, file_path: str, zais: list[int] | None = None, mts: list[int] | None = None
    ) -> "CovarianceSuite":
        """
        Load a suite from an HDF5 file.

        Parameters
        ----------
        file_path : str
            Path to the HDF5 file.
        zais : Optional[List[int]]
            List of ZAI values to include in the suite.
        mts : Optional[List[int]]
            List of MT values to include in the suite.

        Returns
        -------
        CovarianceSuite
            The loaded suite.
        """
        covs = {}
        with pd.HDFStore(file_path, mode="r") as store:
            zai_keys = [key for key in store.keys() if key.startswith("/zai_")]
            for zai_key in zai_keys:
                zai = int(zai_key.split("/")[2].split("_")[1])
                if zais is not None and zai not in zais:
                    continue

                cov = Covariance.from_hdf5(file_path, zai=zai, mts=mts)
                covs[zai] = cov

        return cls.from_dict(covs)

    @classmethod
    def from_dict(cls, items: dict[int, Covariance]) -> "CovarianceSuite":
        """
        Construct a suite from a dictionary of independent Covariance objects.

        This creates a block-diagonal matrix where off-diagonal blocks
        (cross-nuclide correlations) are initialized to zero.

        Parameters
        ----------
        items : Dict[int, Covariance]
            Dictionary mapping ZAI to Covariance objects.

        Returns
        -------
        CovarianceSuite
            A suite containing the assembled block-diagonal matrix.
        """
        if not items:
            return cls(pd.DataFrame())

        parts = []

        for zai in sorted(items.keys()):
            cov = items[zai].copy()

            # Prepend ZAI to the index
            new_index = pd.MultiIndex.from_tuples(
                [(zai,) + tup for tup in cov.index], names=["ZAI", "MT", "E_min_eV", "E_max_eV"]
            )
            cov.index = new_index
            cov.columns = new_index
            parts.append(cov)

        # pd.concat handles block-diagonal alignment and zero-filling
        global_matrix = pd.concat(parts, axis=1).fillna(0)
        return cls(matrix=global_matrix.sort_index(axis=0).sort_index(axis=1))

    @classmethod
    def from_df(cls, df: pd.DataFrame) -> "CovarianceSuite":
        """
        Construct a suite directly from a DataFrame.
        Useful for loading adjusted/correlated matrices.

        Parameters
        ----------
        df : pd.DataFrame
            The global covariance matrix.

        Returns
        -------
        CovarianceSuite
            A suite wrapping the provided DataFrame.
        """
        return cls(matrix=df)

    def get_uncertainties(self) -> pd.Series:
        """
        Return the standard deviations (sqrt of diagonal) for all bins.

        Returns
        -------
        pd.Series
            Standard deviation values.
        """
        mat = self.matrix
        return pd.Series(np.sqrt(np.diag(mat)), index=mat.index)

    def get_correlation_matrix(self) -> pd.DataFrame:
        """
        Calculate the correlation matrix from the current covariance matrix.

        Returns
        -------
        pd.DataFrame
            Matrix of correlation coefficients (-1 to 1).
        """
        diag = np.sqrt(np.diag(self.matrix))
        # Prevent division by zero for bins with 0 uncertainty
        diag[diag == 0] = 1.0

        outer_std = np.outer(diag, diag)
        corr = self.matrix / outer_std
        return corr.fillna(0)


if __name__ == "__main__":
    # covs = {}

    # for zai in [922350, 922380]:
    #     covs[zai] = Covariance.from_hdf5(
    #         r"c:\Users\dhouben\OneDrive - Studiecentrum voor Kernenergie\Documents\data\jeff_40\jeff40_ecco33.h5",
    #         zai=zai,
    #         mts=[2, 4, 18, 102, 456, 35018],
    #     )
    #     print(f"ZAI: {zai}, Nuclide: {covs[zai].nuclide}, Shape: {covs[zai].shape}")
    #     print(covs[zai])
    #     covs[zai].to_hdf5("covariances_test.h5")

    # suite = CovarianceSuite.from_dict(covs)
    # print(suite.matrix)
    # print(suite.get_uncertainties())
    # print(suite.get_correlation_matrix())

    cov = Covariance.from_hdf5("data/covariances_test.h5", zai=922380, mts=[18])
    print(cov.correlation())
