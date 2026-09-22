"""Core ACE class for reading and perturbing ACE data."""

import numpy as np
import pandas as pd

from andalus.ace.reader import Reaction, read_ace
from andalus.ace.writer import write_ace

#: Reactions whose cross-section is already the sum of other reactions
#: present in the same file (MT=4 is the sum of the MT=51..91 inelastic
#: levels; MT=101 is the sum of the absorption reactions; MT=27/3/1 are
#: not emitted as separate ``Reaction`` entries by the reader but are
#: listed here for completeness). Perturbing one of these directly would
#: silently double-count against its constituent levels once propagated,
#: so :meth:`ACE.perturb` refuses to touch them.
AGGREGATE_MTS = frozenset({1, 3, 4, 27, 101})

#: Fission-family reactions (total, first/second/third/fourth-chance
#: fission). These produce secondary neutrons, so a perturbation must
#: flow into ``total_xs`` but must NOT flow into ``absorption_xs`` (the
#: ESZ "absorption" array is the true-disappearance/capture cross
#: section and excludes fission).
FISSION_MTS = frozenset({18, 19, 20, 21, 38})

#: Reactions that emit one or more secondary neutrons without being
#: elastic or fission ((n,2n), (n,3n), (n,n'), (n,np), etc., including
#: their discrete/continuum level breakdowns). Like fission, these flow
#: into ``total_xs`` but not ``absorption_xs``.
NEUTRON_PRODUCING_MTS = frozenset(
    {11, 16, 17, 22, 23, 24, 25, 28, 29, 30, 32, 33, 34, 35, 36, 37, 41, 42, 44, 45}
    | set(range(51, 92))  # (n,n') discrete/continuum inelastic levels
    | set(range(152, 201))  # (n,xn) discrete/continuum production reactions
)

#: Quantities that are stored in the ACE reaction blocks (MTR/LSIG/SIG)
#: but are not themselves cross sections that sum into ``total_xs``
#: (e.g. MT=444 is damage energy production; MT=203/207/etc. are
#: secondary-particle *production* cross sections, redundant with
#: 103/107). Perturbing these has no well-defined effect on totals, so
#: they are excluded from automatic total/absorption propagation.
NON_XS_MTS = frozenset({203, 204, 205, 206, 207, 444})


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
        self._xss_tokens = self.data["xss_tokens"]
        self._original_xss = self.xss.copy()
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
        ValueError
            If an MT in ``xs_adjustment`` is an aggregate reaction (e.g.
            MT=4) or a non-cross-section quantity (e.g. MT=444), for which
            propagation into ``total_xs``/``absorption_xs`` is undefined.
        """
        for mt, group in xs_adjustment.groupby(level="MT"):
            if mt not in self.reactions:
                raise KeyError(
                    f"MT={mt} not found in ACE reactions for ZAID={self.header.zaid}. "
                    f"Available MTs: {sorted(self.reactions)}"
                )
            if mt in AGGREGATE_MTS or mt in NON_XS_MTS:
                raise ValueError(
                    f"MT={mt} cannot be perturbed directly: it is an aggregate or "
                    "non-cross-section quantity, not an independent reaction. "
                    "Perturb its constituent MTs instead."
                )
            rxn = self.reactions[mt]
            rxn_energy = rxn.energies

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

        Every non-aggregate reaction flows into ``total_xs`` (it is, by
        definition, part of the total interaction cross section). Only
        reactions that do *not* emit a secondary neutron flow into
        ``absorption_xs`` — elastic (MT=2), fission (:data:`FISSION_MTS`),
        and neutron-producing reactions (:data:`NEUTRON_PRODUCING_MTS`)
        are excluded, since the ACE ESZ "absorption" array is the true
        disappearance/capture cross section and does not include them.
        """
        start = rxn.ie - 1
        stop = start + len(delta)
        self.total_xs[start:stop] += delta
        if rxn.mt != 2 and rxn.mt not in FISSION_MTS and rxn.mt not in NEUTRON_PRODUCING_MTS:
            self.absorption_xs[start:stop] += delta

    def write(self, filepath: str) -> None:
        """Write perturbed ACE back to disk.

        Header, IZAW, NXS, and JXS lines are reproduced verbatim (they are
        never touched by :meth:`perturb`). XSS entries that are unchanged
        from the value originally read are reproduced byte-for-byte from
        their original text; entries that were perturbed are re-formatted
        as ``%20.11E`` (the format ACE uses for genuine cross-section
        data, which is the only kind of entry :meth:`perturb` ever
        changes).

        Parameters
        ----------
        filepath : str
            Output path for modified ACE file.
        """
        write_ace(self, filepath)

    def __repr__(self) -> str:
        return (
            f"ACE(ZAID={self.header.zaid}, T={self.header.temperature}K, "
            f"NES={len(self.energy_grid)}, MTs={sorted(self.reactions)})"
        )
