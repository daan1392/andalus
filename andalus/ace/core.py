"""Core ACE class for reading and perturbing ACE data."""

import numpy as np
import pandas as pd

from andalus.ace.reader import Reaction, read_ace


class ACE:
    """Represents an ACE file with methods to read, perturb, and write."""

    def __init__(self, filepath: str):
        """Load ACE file from disk.

        Parameters
        ----------
        filepath : str
            Path to ASCII ACE file.
        """
        self.filepath = filepath
        self.data = read_ace(filepath)
        self.header = self.data["header"]
        self.nxs = self.data["nxs"]
        self.jxs = self.data["jxs"]
        self.xss = self.data["xss"]
        self.energy_grid = self.data["energy_grid"]
        self.total_xs = self.data["total_xs"]
        self.absorption_xs = self.data["absorption_xs"]
        self.reactions = self.data["reactions"]
        self.nu = self.data["nu"]
        self._raw_lines = self.data["raw_lines"]

    @classmethod
    def read(cls, filepath: str) -> "ACE":
        """Load an ACE file from disk.

        Parameters
        ----------
        filepath : str
            Path to ASCII ACE file.

        Returns
        -------
        ACE
            ACE instance with parsed data.
        """
        return cls(filepath)

    def perturb(self, xs_adjustment: pd.Series) -> None:
        """Apply multigroup adjustments to pointwise cross-sections.

        A pointwise energy exactly on a multigroup bin edge is assigned to
        the higher-energy bin (``E_min < E <= E_max``). Energies not covered
        by any bin for a given reaction are left unperturbed (factor 1.0).

        Threshold reactions are only tabulated above their threshold energy
        (``Reaction.ie > 1``), so bin membership is evaluated against that
        reaction's own energy sub-range rather than the full energy grid.

        Parameters
        ----------
        xs_adjustment : pd.Series
            Series with MultiIndex (MT, E_min_eV, E_max_eV) containing
            relative adjustments (e.g. from GLLS, not yet converted to a
            multiplicative factor). Internally converted via ``1 + adjustment``.

        Raises
        ------
        KeyError
            If an MT in ``xs_adjustment`` is not present in this ACE file's
            reactions.
        """
        for mt, group in xs_adjustment.groupby(level="MT"):
            if mt not in self.reactions:
                raise KeyError(
                    f"MT={mt} not found in ACE reactions for ZAID={self.header.zaid}. "
                    f"Available MTs: {sorted(self.reactions)}"
                )
            rxn = self.reactions[mt]
            rxn_energy = rxn.energy(self.energy_grid)

            factor = np.ones(len(rxn.xs))
            for (e_min, e_max), adjustment in group.droplevel("MT").items():
                mask = (rxn_energy > e_min) & (rxn_energy <= e_max)
                factor[mask] *= 1.0 + adjustment

            delta = rxn.xs * (factor - 1.0)
            rxn.xs += delta
            self._propagate_to_totals(rxn, delta)

    def _propagate_to_totals(self, rxn: Reaction, delta: np.ndarray) -> None:
        """Keep ``total_xs`` (and ``absorption_xs``) consistent after a perturbation.

        Rather than re-deriving which reactions sum into ``total_xs`` and
        ``absorption_xs`` (which would duplicate ENDF reaction-hierarchy rules,
        e.g. MT=4 already equals the sum of MT=51..91), the same incremental
        delta just applied to the reaction is added to the aggregate arrays.
        This preserves whatever summation NJOY originally used, without
        needing to reconstruct it.
        """
        start = rxn.ie - 1
        stop = start + len(delta)
        self.total_xs[start:stop] += delta
        if rxn.mt != 2:  # elastic already flows into total_xs directly
            self.absorption_xs[start:stop] += delta

    def write(self, filepath: str) -> None:
        """Write perturbed ACE back to disk.

        Parameters
        ----------
        filepath : str
            Output path for modified ACE file.
        """
        # TODO: Reconstruct ASCII ACE format and write to disk
        pass

    def __repr__(self) -> str:
        return (
            f"ACE(ZAID={self.header.zaid}, T={self.header.temperature}K, "
            f"NES={len(self.energy_grid)}, MTs={sorted(self.reactions)})"
        )
