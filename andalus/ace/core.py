"""Core ACE class for reading and perturbing ACE data."""

from typing import cast

import numpy as np
import pandas as pd

from andalus.ace.reader import PolynomialNu, Reaction, TabulatedNu, read_ace
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

#: ENDF reaction identifiers for nu-bar (average neutrons per fission),
#: mapped to the corresponding key in :attr:`ACE.nu`. MT=455 (delayed
#: nu-bar) is intentionally not included: the reader does not parse a
#: separate delayed-nu table.
NU_MTS = {452: "total", 456: "prompt"}


def _apply_bin_adjustment(values: np.ndarray, energies: np.ndarray, bins: pd.Series) -> np.ndarray:
    """Apply relative multigroup adjustments to a pointwise array in place.

    A pointwise energy exactly on a bin edge is assigned to the
    higher-energy bin (``E_min < E <= E_max``). Energies not covered by
    any bin are left unperturbed (factor 1.0).

    Parameters
    ----------
    values : np.ndarray
        Pointwise values to perturb in place (e.g. ``Reaction.xs`` or a
        nu-bar table's ``values``).
    energies : np.ndarray
        The energy grid ``values`` is aligned with.
    bins : pd.Series
        Series indexed by ``(E_min_eV, E_max_eV)`` with relative
        adjustments, applied via ``1 + adjustment``.

    Returns
    -------
    np.ndarray
        The delta added to ``values`` (``values`` after minus before).
    """
    factor = np.ones(len(values))
    for edges, adjustment in bins.items():
        e_min, e_max = cast("tuple[float, float]", edges)
        mask = (energies > e_min) & (energies <= e_max)
        factor[mask] *= 1.0 + adjustment

    delta = values * (factor - 1.0)
    values += delta
    return delta


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
            delta = _apply_bin_adjustment(rxn.xs, rxn.energies, group.droplevel("MT"))
            self._propagate_to_totals(rxn, delta)

    def perturb_nu(self, nu_adjustment: pd.Series) -> None:
        """Apply multigroup adjustments to nu-bar (average neutrons per fission).

        Same convention as :meth:`perturb`: a `pd.Series` with MultiIndex
        ``(MT, E_min_eV, E_max_eV)``, where MT is 452 (total nu-bar) or 456
        (prompt nu-bar), containing relative adjustments applied via
        ``1 + adjustment`` over ``(E_min, E_max]``.

        Parameters
        ----------
        nu_adjustment : pd.Series
            Series with MultiIndex (MT, E_min_eV, E_max_eV), MT in {452, 456}.

        Raises
        ------
        KeyError
            If MT is not 452/456, or the corresponding nu-bar table is not
            present in this ACE file.
        NotImplementedError
            If the corresponding nu-bar table is a :class:`PolynomialNu`
            rather than a :class:`TabulatedNu` (only tabulated nu-bar can
            be perturbed bin-wise).
        """
        for mt, group in nu_adjustment.groupby(level="MT"):
            if mt not in NU_MTS:
                raise KeyError(f"MT={mt} is not a supported nu-bar MT. Supported: {sorted(NU_MTS)}")
            key = NU_MTS[mt]
            if self.nu is None or key not in self.nu:
                available = sorted(self.nu) if self.nu else []
                raise KeyError(
                    f"Nu-bar table '{key}' (MT={mt}) not found for ZAID={self.header.zaid}. "
                    f"Available nu-bar tables: {available}"
                )
            table = self.nu[key]
            if isinstance(table, PolynomialNu):
                raise NotImplementedError(
                    f"MT={mt} nu-bar for ZAID={self.header.zaid} is a polynomial table; "
                    "only tabulated nu-bar can be perturbed."
                )
            assert isinstance(table, TabulatedNu)
            _apply_bin_adjustment(table.values, table.energy, group.droplevel("MT"))

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
