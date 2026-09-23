"""Core ACE class for reading and perturbing ACE data."""

from typing import cast

import numpy as np
import pandas as pd

from andalus.ace.reader import EnergyDistribution, PolynomialNu, Reaction, TabulatedNu, read_ace
from andalus.ace.writer import write_ace

#: Reactions whose cross-section is already the sum of other reactions
#: present in the same file (MT=4 is the sum of the MT=51..91 inelastic
#: levels; MT=101 is the sum of the absorption reactions; MT=27/3/1 are
#: not emitted as separate ``Reaction`` entries by the reader but are
#: listed here for completeness). Perturbing one of these directly (i.e.
#: applying the adjustment to the aggregate's own tabulated array) would
#: silently double-count against its constituent levels once propagated,
#: so :meth:`ACE.perturb` redistributes the adjustment onto whichever of
#: :data:`AGGREGATE_MEMBERS` are present instead of touching the
#: aggregate's own array directly.
AGGREGATE_MTS = frozenset({1, 3, 4, 27, 101})

#: Constituent MTs that sum into each aggregate in :data:`AGGREGATE_MTS`.
#: Only MT=4 is listed: it is the only one of these that the reader ever
#: observes as an actual ``Reaction`` entry (MT=1/3/27/101 are either the
#: ESZ arrays themselves or simply absent from the ACE files this reader
#: has been tested against), so it is the only one with a verified
#: constituent mapping. Perturbing MT=1/3/27/101 still raises, since
#: there is nothing to redistribute onto.
AGGREGATE_MEMBERS: dict[int, frozenset[int]] = {4: frozenset(range(51, 92))}

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

#: ANDALUS encodes chi (secondary-energy distribution) MTs as MF*1000+MT
#: (e.g. 35018 for the MF=35 prompt fission neutron spectrum of MT=18),
#: matching the convention already used for the ``reaction_dict``/``mf35``
#: handling in :meth:`AssimilationSuite.to_ace`. :meth:`ACE.perturb_chi`
#: subtracts this offset to find the underlying reaction MT in :attr:`ACE.chi`.
CHI_MF = 35000


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


def _renormalize_and_rebuild_cdf(pdf: np.ndarray, energy_out: np.ndarray, cdf: np.ndarray) -> None:
    """Renormalize ``pdf`` to unit area and rebuild ``cdf`` in place.

    Both are updated in place via trapezoidal integration, matching the
    ``CDF[0] = 0`` convention the reader observed in real ACE files.
    """
    pdf /= np.trapz(pdf, energy_out)
    increments = np.diff(energy_out) * (pdf[:-1] + pdf[1:]) / 2.0
    cdf[:] = np.concatenate(([0.0], np.cumsum(increments)))


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
        self.chi = self.data["chi"]
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

        Aggregate reactions (:data:`AGGREGATE_MTS`, e.g. MT=4) are not
        perturbed directly — that would double-count against their
        constituent levels once propagated into ``total_xs``. Instead, the
        same adjustment is applied to each of the aggregate's constituent
        MTs that is present in this file (see :data:`AGGREGATE_MEMBERS`),
        and the aggregate's own tabulated array is then resynced to the
        new sum of its constituents.

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
            If an MT in ``xs_adjustment`` is a non-cross-section quantity
            (e.g. MT=444, for which propagation into ``total_xs`` is
            undefined), or an aggregate reaction with no known/present
            constituents to redistribute the adjustment onto.
        """
        for mt, group in xs_adjustment.groupby(level="MT"):
            if mt not in self.reactions:
                raise KeyError(
                    f"MT={mt} not found in ACE reactions for ZAID={self.header.zaid}. "
                    f"Available MTs: {sorted(self.reactions)}"
                )
            if mt in NON_XS_MTS:
                raise ValueError(
                    f"MT={mt} cannot be perturbed: it is a non-cross-section quantity, not an independent reaction."
                )
            if mt in AGGREGATE_MTS:
                self._perturb_aggregate(cast("int", mt), group.droplevel("MT"))
                continue
            rxn = self.reactions[mt]
            delta = _apply_bin_adjustment(rxn.xs, rxn.energies, group.droplevel("MT"))
            self._propagate_to_totals(rxn, delta)

    def _perturb_aggregate(self, mt: int, bins: pd.Series) -> None:
        """Redistribute an aggregate MT's adjustment onto its present constituents.

        Applies ``bins`` to each constituent reaction individually (through
        the normal leaf-reaction path, so ``total_xs``/``absorption_xs``
        stay correct), then resyncs the aggregate's own tabulated array to
        the new sum of *all* its present constituents over its own energy
        range — a full recompute rather than a delta, so it is correct
        even if a constituent was perturbed directly in an earlier call.

        Note this resync only happens when the aggregate itself is
        perturbed; perturbing a constituent directly (e.g. MT=52 without
        going through MT=4) leaves the aggregate's own array stale.
        """
        members = sorted(m for m in AGGREGATE_MEMBERS.get(mt, ()) if m in self.reactions)
        if not members:
            raise ValueError(
                f"MT={mt} is an aggregate reaction with no known constituent MTs present "
                f"for ZAID={self.header.zaid}. Cannot redistribute the perturbation."
            )

        for member_mt in members:
            rxn = self.reactions[member_mt]
            delta = _apply_bin_adjustment(rxn.xs, rxn.energies, bins)
            self._propagate_to_totals(rxn, delta)

        aggregate = self.reactions[mt]
        aggregate.xs[:] = 0.0
        agg_start = aggregate.ie - 1
        for member_mt in members:
            rxn = self.reactions[member_mt]
            start = rxn.ie - 1
            stop = start + len(rxn.xs)
            aggregate.xs[start - agg_start : stop - agg_start] += rxn.xs

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
            if mt == 452 and self.nu is not None and key not in self.nu and "nu" in self.nu:
                key = "nu"
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

    def perturb_chi(self, chi_adjustment: pd.Series) -> None:
        """Apply outgoing-energy-binned adjustments to a fission neutron spectrum.

        Adjustment is a `pd.Series` with MultiIndex ``(MT, E_min_eV,
        E_max_eV)``, the same shape as :meth:`perturb`/:meth:`perturb_nu`,
        where MT follows ANDALUS's MF*1000+MT chi convention (e.g. 35018
        for the prompt fission neutron spectrum of MT=18) and ``(E_min,
        E_max]`` bins the *outgoing* energy. ANDALUS does not currently
        produce chi sensitivities resolved by incident energy, so the
        adjustment is applied identically to every incident-energy table
        (future work, once incident-energy-resolved chi sensitivities
        exist, could target a subset via an extended index).

        The adjustment is applied to each table's PDF via the same bin
        convention as :meth:`perturb`/:meth:`perturb_nu` (``1 +
        adjustment`` over ``E_min < E_out <= E_max``), then the PDF is
        renormalized to unit area and the CDF rebuilt by trapezoidal
        integration.

        Parameters
        ----------
        chi_adjustment : pd.Series
            Series with MultiIndex (MT, E_min_eV, E_max_eV), MT following
            the MF*1000+MT convention (e.g. 35018).

        Raises
        ------
        KeyError
            If the underlying reaction MT has no energy-distribution data
            in this ACE file.
        NotImplementedError
            If the MT's energy distribution is not a single LAW=4
            (Continuum Tabular Distribution) table.
        """
        for mt_key, group in chi_adjustment.groupby(level="MT"):
            mt = cast("int", mt_key)
            base_mt = mt - CHI_MF if mt >= CHI_MF else mt
            if base_mt not in self.chi:
                raise KeyError(
                    f"MT={mt} (reaction MT={base_mt}) has no energy-distribution data for "
                    f"ZAID={self.header.zaid}. Available MTs: {sorted(self.chi)}"
                )
            dist = self.chi[base_mt]
            if not isinstance(dist, EnergyDistribution):
                raise NotImplementedError(
                    f"MT={mt} (reaction MT={base_mt}) energy distribution for ZAID={self.header.zaid} "
                    f"is LAW={dist.law}; only LAW=4 (Continuum Tabular Distribution) can be perturbed."
                )
            bins = group.droplevel("MT")
            for table in dist.tables:
                _apply_bin_adjustment(table.pdf, table.energy_out, bins)
                _renormalize_and_rebuild_cdf(table.pdf, table.energy_out, table.cdf)

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
