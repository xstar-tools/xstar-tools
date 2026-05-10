"""High-level Python API for :mod:`xstar_atomic`.

The :class:`XSTARAtomic` class is a convenience wrapper around the lower-level
:class:`xstar_atomic.hierarchy.ATDB` packed-FITS reader.  It provides notebook-
and script-friendly methods for the currently implemented decoders while keeping
``ATDB`` available for direct record access.

This API is intentionally thin and workflow-oriented: it delegates to the same validated
module-level functions used by the command-line tools, so results should match
CLI output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, Optional, Sequence, Tuple, Union

from .hierarchy import ATDB, SYMBOL_TO_Z

# Heavy decoder modules are imported lazily inside XSTARAtomic methods.
# This keeps ``import xstar_atomic`` lightweight and avoids runpy warnings when
# executing submodules such as ``python -m xstar_atomic.collisions``.

IonLike = Union[str, Tuple[str, int], Tuple[int, int], None]


def roman_to_int(text: str) -> int:
    """Convert a Roman numeral ion stage to an integer."""
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    prev = 0
    for ch in reversed(text.upper().strip()):
        val = vals.get(ch)
        if val is None:
            raise ValueError(f"Invalid Roman numeral character {ch!r} in {text!r}")
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    if total <= 0:
        raise ValueError(f"Invalid Roman numeral: {text!r}")
    return total


def _split_ion_string(text: str) -> Tuple[str, Optional[str]]:
    """Split flexible ion strings into ``(element_symbol, stage_text)``.

    Accepted examples include ``"O VIII"``, ``"o viii"``, ``"o_viii"``,
    ``"O-VIII"``, ``"O.VIII"``, ``"OVIII"``, and ``"o8"``.
    """
    import re

    original = text
    t = str(text).strip()
    if not t:
        raise ValueError("Empty ion string")

    # Normalize common separators to spaces.
    t = re.sub(r"[_\-./]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    parts = t.split()

    if len(parts) >= 2:
        return parts[0], parts[1]

    token = parts[0]

    # Compact forms: OVIII, O8, FeXXVI, Fe26.  Try a valid 2-letter
    # element first, then a valid 1-letter element; this avoids parsing
    # "OVIII" as the nonexistent element "Ov" + "III".
    m = re.match(r"^([A-Za-z]{1,2})([0-9]+|[IVXLCDMivxlcdm]+)$", token)
    if m:
        prefix = m.group(1)
        suffix = m.group(2)
        if prefix.upper() in SYMBOL_TO_Z:
            return prefix, suffix

    m = re.match(r"^([A-Za-z])([0-9]+|[IVXLCDMivxlcdm]+)$", token)
    if m:
        return m.group(1), m.group(2)

    # More general compact form where a two-letter valid element is followed
    # by a roman/integer stage: FeXXVI, Mg12, SiXIV.
    for nchar in (2, 1):
        if len(token) > nchar:
            prefix = token[:nchar]
            suffix = token[nchar:]
            if prefix.upper() in SYMBOL_TO_Z and re.match(r"^([0-9]+|[IVXLCDMivxlcdm]+)$", suffix):
                return prefix, suffix

    # Element only.
    return token, None


def parse_ion(ion: IonLike = None, *, element: Optional[Union[str, int]] = None, ion_stage: Optional[int] = None) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Normalize ion input into ``(Z, ion_stage, element_symbol)``.

    Examples
    --------
    ``"O VIII"`` -> ``(8, 8, "O")``
    ``"o viii"`` -> ``(8, 8, "O")``
    ``"o_viii"`` -> ``(8, 8, "O")``
    ``"OVIII"`` -> ``(8, 8, "O")``
    ``("O", 8)`` -> ``(8, 8, "O")``
    ``(8, 8)`` -> ``(8, 8, "O")``
    """
    z: Optional[int] = None
    symbol: Optional[str] = None
    stage: Optional[int] = ion_stage

    if ion is not None:
        if isinstance(ion, tuple):
            if len(ion) != 2:
                raise ValueError("ion tuple must be (element, ion_stage)")
            element, stage = ion
        elif isinstance(ion, str):
            elem_text, stage_text = _split_ion_string(ion)
            element = elem_text
            if stage_text is not None:
                try:
                    stage = int(stage_text)
                except ValueError:
                    stage = roman_to_int(stage_text)
        else:
            raise TypeError("ion must be None, a string, or a 2-tuple")

    if element is not None:
        if isinstance(element, int):
            z = int(element)
        else:
            s = str(element).strip()
            if not s:
                raise ValueError("Empty element string")
            if s.isdigit():
                z = int(s)
            else:
                symbol = s[0].upper() + s[1:].lower()
                z = SYMBOL_TO_Z.get(symbol.upper())
                if z is None:
                    raise ValueError(f"Unknown element: {element!r}")

    if stage is not None:
        stage = int(stage)

    if z is not None and symbol is None:
        # Avoid importing Z_TO_SYMBOL from __init__; hierarchy guarantees this map.
        from .hierarchy import Z_TO_SYMBOL
        symbol = Z_TO_SYMBOL.get(z)

    return z, stage, symbol

@dataclass(frozen=True)
class AtomicSelection:
    """Normalized element/ion selection."""

    z: Optional[int]
    ion_stage: Optional[int]
    element: Optional[str]



class _ContextNamespace:
    """Context constructors exposed as ``db.context``."""

    def __init__(self, owner: "XSTARAtomic"):
        self._owner = owner

    def from_values(self, **kwargs):
        from .context import context_from_values
        return context_from_values(**kwargs)

    def from_xstar_run(self, run_dir, **kwargs):
        from .context import context_from_xstar_run
        return context_from_xstar_run(run_dir, **kwargs)


class _RatesNamespace:
    """Rate evaluators exposed as ``db.rates``."""

    def __init__(self, owner: "XSTARAtomic"):
        self._owner = owner

    def type50(self, *args, **kwargs):
        if args:
            if "ion" not in kwargs:
                kwargs["ion"] = args[0]
            else:
                raise TypeError("ion was supplied both positionally and by keyword")
            if len(args) > 1:
                raise TypeError("type50 accepts at most one positional ion argument")
        from .rates_type50 import evaluate_type50_bound_bound
        return evaluate_type50_bound_bound(**kwargs)

    def type50_bound_bound(self, *args, **kwargs):
        return self.type50(*args, **kwargs)


class _AuditNamespace:
    """Audit workflows exposed as ``db.audit``."""

    def __init__(self, owner: "XSTARAtomic"):
        self._owner = owner

    def type50_line_pumping(self, cases_csv, **kwargs):
        from .audit import type50_line_pumping
        return type50_line_pumping(cases_csv, **kwargs)

    def resonance_deficit(self, *args, **kwargs):
        raise NotImplementedError(
            "resonance_deficit is still implemented as examples/53_audit_helike_resonance_deficit.py; "
            "it is scheduled for migration into xstar_atomic.audit in a later API release."
        )

    def resonance_population_flux(self, *args, **kwargs):
        raise NotImplementedError(
            "resonance_population_flux is still implemented as examples/54_audit_helike_resonance_population_flux.py; "
            "it is scheduled for migration into xstar_atomic.audit in a later API release."
        )


class _MatrixNamespace:
    """Population-matrix helpers exposed as ``db.matrix``."""

    def __init__(self, owner: "XSTARAtomic"):
        self._owner = owner

    def build_ion(self, ion, **kwargs):
        from .workflow import build_matrix
        return build_matrix(ion, db=self._owner, **kwargs)


class _SolveNamespace:
    """Population-solver helpers exposed as ``db.solve``."""

    def __init__(self, owner: "XSTARAtomic"):
        self._owner = owner

    def ion(self, ion, **kwargs):
        from .workflow import solve_populations
        return solve_populations(ion, db=self._owner, **kwargs)


class _ValidateNamespace:
    """Validation helpers exposed as ``db.validate``."""

    def __init__(self, owner: "XSTARAtomic"):
        self._owner = owner

    def compare_xstar_run(self, run_dir, *, ion=None, wavelength=None, value_column="emit_outward", **kwargs):
        from .workflow import calc_triplet
        ctx = self._owner.context.from_xstar_run(run_dir, ion=ion, **kwargs)
        triplet = calc_triplet(ion=ion, context=ctx, wavelength=wavelength, value_column=value_column)
        return {"context": ctx.to_dict(), "triplet": triplet.to_dict(), "lines": list(triplet.lines)}

class XSTARAtomic:
    """High-level interface to XSTAR's packed ``atdb.fits`` atomic database.

    Parameters
    ----------
    fitsfile:
        Path to XSTAR's released packed atomic database, usually
        ``xstar/data/atdb.fits``. If omitted, xstar-atomic resolves the path
        from ``XSTAR_ATDB_FITS``, the persistent ``datapath`` file, or by prompting
        with :func:`xstar_atomic.download_data`.
    load_reals:
        Whether to load/map the REALS array immediately. Most physical decoders
        need real values, so the default is ``True``.
    build_index:
        If ``True``, build the record/element/ion index at initialization.
    """

    def __init__(
        self,
        fitsfile: Union[str, Path, None] = None,
        *,
        load_reals: bool = True,
        build_index: bool = True,
        index_cache: Union[bool, str, Path] = False,
        rebuild_index_cache: bool = False,
        index_cache_format: str = "npz",
    ):
        self.db = ATDB(fitsfile, load_reals=load_reals)
        self.fitsfile = str(self.db.filename)
        self.index_cache = index_cache
        self.rebuild_index_cache = rebuild_index_cache
        self.index_cache_format = index_cache_format
        self._records = None
        self._elements = None
        self._ions = None
        self.context = _ContextNamespace(self)
        self.rates = _RatesNamespace(self)
        self.audit = _AuditNamespace(self)
        self.matrix = _MatrixNamespace(self)
        self.solve = _SolveNamespace(self)
        self.validate = _ValidateNamespace(self)
        if build_index:
            self.build_index()

    def close(self) -> None:
        """Close the underlying FITS file handle."""
        self.db.close()

    def __enter__(self) -> "XSTARAtomic":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def records(self):
        if self._records is None:
            self.build_index()
        return self._records

    @property
    def elements(self):
        if self._elements is None:
            self.build_index()
        return self._elements

    @property
    def ions(self):
        if self._ions is None:
            self.build_index()
        return self._ions

    def build_index(self, *, index_cache: Union[bool, str, Path, None] = None, rebuild_index_cache: Optional[bool] = None, index_cache_format: Optional[str] = None):
        """Build and cache ``(records, elements, ions)`` from the packed ATDB.

        Parameters
        ----------
        index_cache:
            ``False`` disables disk caching. ``True`` uses the default cache path
            next to ``atdb.fits``. A string/path uses that explicit cache file.
        rebuild_index_cache:
            If true, ignore an existing cache and rewrite it.
        """
        cache_setting = self.index_cache if index_cache is None else index_cache
        rebuild = self.rebuild_index_cache if rebuild_index_cache is None else bool(rebuild_index_cache)
        fmt = self.index_cache_format if index_cache_format is None else str(index_cache_format)
        use_cache = bool(cache_setting)
        cache_path = None if cache_setting is True or cache_setting is False or cache_setting is None else cache_setting
        self._records, self._elements, self._ions = self.db.build_index(
            use_cache=use_cache,
            cache_path=cache_path,
            rebuild_cache=rebuild,
            cache_format=fmt,
        )
        return self._records, self._elements, self._ions

    def select(self, ion: IonLike = None, *, element: Optional[Union[str, int]] = None, ion_stage: Optional[int] = None) -> AtomicSelection:
        z, stage, symbol = parse_ion(ion, element=element, ion_stage=ion_stage)
        return AtomicSelection(z=z, ion_stage=stage, element=symbol)

    def _records_for_selection(self, sel: AtomicSelection, *, data_type=None, rate_type=None):
        """Return records for one selection, using array-backed NPZ cache when available."""
        if self.index_cache and self.index_cache_format == "npz":
            cache_setting = self.index_cache
            cache_path = None if cache_setting is True or cache_setting is False or cache_setting is None else cache_setting
            return self.db.select_records(
                z=sel.z,
                ion_stage=sel.ion_stage,
                data_type=data_type,
                rate_type=rate_type,
                use_cache=True,
                cache_path=cache_path,
                rebuild_cache=self.rebuild_index_cache,
                cache_format="npz",
            )
        return self.records

    def summary(self) -> dict:
        """Return a compact hierarchy summary for the database."""
        from .hierarchy import summarize as hierarchy_summary

        return hierarchy_summary(self.records, self.elements, self.ions, self.db)

    def levels(self, ion: IonLike = None, *, element: Optional[Union[str, int]] = None, ion_stage: Optional[int] = None) -> list[dict]:
        """Decode level records for an element/ion selection."""
        from .lines import extract_levels

        sel = self.select(ion, element=element, ion_stage=ion_stage)
        return extract_levels(self.db, self._records_for_selection(sel), sel.z, sel.ion_stage)

    def lines(
        self,
        ion: IonLike = None,
        *,
        element: Optional[Union[str, int]] = None,
        ion_stage: Optional[int] = None,
        wavelength: Optional[Tuple[float, float]] = None,
        energy_kev: Optional[Tuple[float, float]] = None,
        lower_level: Optional[int] = None,
        upper_level: Optional[int] = None,
        data_type: Optional[int] = None,
        rate_type: Optional[int] = None,
        slim: bool = False,
    ) -> list[dict]:
        """Return decoded radiative line records, optionally filtered."""
        from .lines import extract_lines, filter_lines

        sel = self.select(ion, element=element, ion_stage=ion_stage)
        rows = extract_lines(self.db, self._records_for_selection(sel), sel.z, sel.ion_stage)
        wmin, wmax = wavelength if wavelength is not None else (None, None)
        emin, emax = energy_kev if energy_kev is not None else (None, None)
        rows = filter_lines(rows, wmin, wmax, emin, emax, lower_level, upper_level, data_type, rate_type)
        if slim:
            from .lines import slim_line
            rows = [slim_line(r) for r in rows]
        return rows

    def photoionization(
        self,
        ion: IonLike = None,
        *,
        element: Optional[Union[str, int]] = None,
        ion_stage: Optional[int] = None,
        threshold_ev: Optional[Tuple[float, float]] = None,
        data_type: Optional[int] = None,
        rate_type: Optional[int] = None,
        lower_level: Optional[int] = None,
        include_grid: bool = False,
    ) -> Union[list[dict], dict]:
        """Return photoionization/bound-free summaries, optionally with grid rows."""
        from .photoionization import (
            extract_photoionization,
            filter_summaries as filter_photoionization_summaries,
        )

        sel = self.select(ion, element=element, ion_stage=ion_stage)
        summaries, grids = extract_photoionization(self.db, self._records_for_selection(sel), sel.z, sel.ion_stage)
        tmin, tmax = threshold_ev if threshold_ev is not None else (None, None)
        summaries = filter_photoionization_summaries(summaries, tmin, tmax, data_type, rate_type, lower_level)
        if include_grid:
            keep_records = {r.get("record") for r in summaries}
            grids = [g for g in grids if g.get("record") in keep_records]
            return {"summary": summaries, "grid": grids}
        return summaries

    def collisions(
        self,
        ion: IonLike = None,
        *,
        element: Optional[Union[str, int]] = None,
        ion_stage: Optional[int] = None,
        temperatures: Sequence[float] = (),
        wavelength: Optional[Tuple[float, float]] = None,
        energy_kev: Optional[Tuple[float, float]] = None,
        lower_level: Optional[int] = None,
        upper_level: Optional[int] = None,
        data_type: Optional[int] = None,
        include_grid: bool = False,
        electron_density_for_lmixing: float = 1.0,
    ) -> dict:
        """Return collision summaries and evaluated rates."""
        from .collisions import extract_collisions, filter_rows as filter_collision_rows

        sel = self.select(ion, element=element, ion_stage=ion_stage)
        summary_rows, grid_rows, eval_rows = extract_collisions(
            self.db, self._records_for_selection(sel), sel.z, sel.ion_stage, temperatures,
            electron_density_cm3=electron_density_for_lmixing,
        )
        args = SimpleNamespace(
            data_type=data_type,
            lower_level=lower_level,
            upper_level=upper_level,
            wavelength_min=wavelength[0] if wavelength else None,
            wavelength_max=wavelength[1] if wavelength else None,
            energy_min_kev=energy_kev[0] if energy_kev else None,
            energy_max_kev=energy_kev[1] if energy_kev else None,
        )
        selected = filter_collision_rows(summary_rows, args)
        keep = {r.get("record") for r in selected}
        eval_selected = [r for r in eval_rows if r.get("record") in keep]
        out = {
            "summary": selected,
            "evaluated": eval_selected,
            # Backward-compatible aliases used by examples and early API tests.
            "matches": selected,
            "evaluated_rates": eval_selected,
        }
        if include_grid:
            grid_selected = [r for r in grid_rows if r.get("record") in keep]
            out["grid"] = grid_selected
        return out

    def recombination(
        self,
        ion: IonLike = None,
        *,
        element: Optional[Union[str, int]] = None,
        ion_stage: Optional[int] = None,
        temperatures: Sequence[float] = (1e6,),
        electron_densities: Sequence[float] = (1.0,),
        neutral_h_densities: Sequence[float] = (1.0,),
        include_charge_exchange: bool = False,
        source_mode: str = "none",
        source_levels: Optional[Sequence[int]] = None,
        parent_population_scale: float = 1.0,
        min_alpha: float = 0.0,
        allow_charge_exchange_sources: bool = False,
        cascade_mode: str = "none",
    ) -> dict:
        """Return recombination inventory/evaluations and optional source terms."""
        from .recombination import (
            extract_recombination_records,
            evaluate_records as evaluate_recombination_records,
            make_source_rows as make_recombination_source_rows,
            make_cascade_rows,
            classify_recombination_records,
            build_summary as build_recombination_summary,
        )

        sel = self.select(ion, element=element, ion_stage=ion_stage)
        rows = extract_recombination_records(self.db, self._records_for_selection(sel), sel.z, sel.ion_stage)
        rows = classify_recombination_records(rows)
        eval_rows = evaluate_recombination_records(self.db, rows, temperatures, include_charge_exchange=include_charge_exchange)
        source_levels = list(source_levels or [])
        level_rows = self.levels(element=sel.z, ion_stage=sel.ion_stage) if sel.ion_stage is not None else []
        source_rows = make_recombination_source_rows(
            eval_rows,
            level_rows,
            source_mode,
            source_levels,
            electron_densities,
            neutral_h_densities,
            parent_population_scale,
            min_alpha,
            allow_charge_exchange_sources=allow_charge_exchange_sources,
        )
        summary_args = SimpleNamespace(
            fitsfile=self.fitsfile,
            element=sel.element if sel.element is not None else (str(sel.z) if sel.z is not None else None),
            ion_stage=sel.ion_stage,
            temperatures=list(temperatures),
            electron_densities=list(electron_densities),
            neutral_h_densities=list(neutral_h_densities),
            include_charge_exchange=include_charge_exchange,
            allow_charge_exchange_sources=allow_charge_exchange_sources,
            source_mode=source_mode,
            source_levels=",".join(str(v) for v in source_levels),
            parent_population_scale=parent_population_scale,
        )
        summary = build_recombination_summary(rows, eval_rows, source_rows, summary_args, sel.z)
        summary.update({
            "cascade_mode": cascade_mode,
            "n_cascade_source_rows": 0,
            "n_cascade_path_rows": 0,
            "cascade_max_depth": 50,
            "cascade_min_probability": 0.0,
            "counts_by_recombination_record_class": {},
            "n_true_level_resolved_recombination_records_found": sum(
                1 for r in rows if r.get("is_true_level_resolved_recombination")
            ),
            "cascade_warning": (
                "radiative-branching cascade redistribution is an approximation; do not combine "
                "original and cascade sources unless intentionally testing double-counting"
            ),
        })
        from collections import Counter
        summary["counts_by_recombination_record_class"] = dict(
            Counter(str(r.get("recombination_record_class")) for r in rows)
        )

        out = {"records": rows, "evaluated": eval_rows, "sources": source_rows, "summary": summary}
        if cascade_mode == "radiative-branching":
            if sel.ion_stage is None:
                raise ValueError("cascade_mode requires an ion-stage-specific selection")
            line_rows = self.lines(element=sel.z, ion_stage=sel.ion_stage)
            cascade_sources, cascade_paths = make_cascade_rows(source_rows, line_rows)
            out["cascade_sources"] = cascade_sources
            out["cascade_paths"] = cascade_paths
            summary["n_cascade_source_rows"] = len(cascade_sources)
            summary["n_cascade_path_rows"] = len(cascade_paths)
        return out

    def emissivity(
        self,
        ion: IonLike = None,
        *,
        element: Optional[Union[str, int]] = None,
        ion_stage: Optional[int] = None,
        temperatures: Sequence[float] = (1e6,),
        wavelength: Optional[Tuple[float, float]] = None,
        energy_kev: Optional[Tuple[float, float]] = None,
        lower_level: Optional[int] = None,
        upper_level: Optional[int] = None,
        include_unmatched_lines: bool = False,
        include_two_photon: bool = False,
        include_superlevel_radiative: bool = False,
        collision_data_type: Optional[int] = None,
        electron_density_for_lmixing: float = 1.0,
    ) -> dict:
        """Build a direct-excitation emissivity table for selected lines."""
        from .lines import extract_lines
        from .collisions import extract_collisions
        from .emissivity import (
            build_emissivity_rows,
            filter_lines_for_query as filter_emissivity_lines,
            filter_collision_rows as filter_emissivity_collision_rows,
            summarize as emissivity_summary,
        )

        sel = self.select(ion, element=element, ion_stage=ion_stage)
        line_rows_all = extract_lines(self.db, self.records, sel.z, sel.ion_stage)
        args = SimpleNamespace(
            wavelength_min=wavelength[0] if wavelength else None,
            wavelength_max=wavelength[1] if wavelength else None,
            energy_min_kev=energy_kev[0] if energy_kev else None,
            energy_max_kev=energy_kev[1] if energy_kev else None,
            lower_level=lower_level,
            upper_level=upper_level,
            include_two_photon=include_two_photon,
            include_superlevel=include_superlevel_radiative,
            include_superlevel_radiative=include_superlevel_radiative,
            collision_data_type=collision_data_type,
        )
        line_rows = filter_emissivity_lines(line_rows_all, args)
        collision_summary, _collision_grid, collision_eval = extract_collisions(
            self.db, self._records_for_selection(sel), sel.z, sel.ion_stage, temperatures,
            electron_density_cm3=electron_density_for_lmixing,
        )
        collision_summary = filter_emissivity_collision_rows(collision_summary, args)
        keep = {r.get("record") for r in collision_summary}
        collision_eval = [r for r in collision_eval if r.get("record") in keep]
        emiss_rows = build_emissivity_rows(line_rows, collision_eval, temperatures, include_unmatched_lines=include_unmatched_lines)
        return {
            "summary": emissivity_summary(line_rows, collision_summary, collision_eval, emiss_rows),
            "lines": line_rows,
            "collisions": collision_summary,
            "collision_evaluations": collision_eval,
            "emissivity": emiss_rows,
            # Backward-compatible alias used by examples and early API tests.
            "rows": emiss_rows,
        }


    def get_levels(self, *args, **kwargs):
        """Alias for :meth:`levels` for workflow-style code."""
        return self.levels(*args, **kwargs)

    def get_lines(self, *args, **kwargs):
        """Alias for :meth:`lines` for workflow-style code."""
        return self.lines(*args, **kwargs)

    def get_wavelengths(self, ion: IonLike = None, **kwargs) -> list[float]:
        """Return sorted wavelengths in Angstrom for selected line records."""
        vals = []
        for row in self.lines(ion, **kwargs):
            value = row.get("wavelength_A", row.get("wavelength"))
            if value is not None:
                try:
                    vals.append(float(value))
                except Exception:
                    pass
        return sorted(vals)

    def match_line(self, ion: IonLike = None, **kwargs):
        """Return the closest selected line by wavelength or energy."""
        from .workflow import match_line
        return match_line(ion, db=self, **kwargs)

    def get_collisions(self, *args, **kwargs):
        """Alias for :meth:`collisions`."""
        return self.collisions(*args, **kwargs)

    def get_photoionization(self, *args, **kwargs):
        """Alias for :meth:`photoionization`."""
        return self.photoionization(*args, **kwargs)

    def get_recombination(self, *args, **kwargs):
        """Alias for :meth:`recombination`."""
        return self.recombination(*args, **kwargs)

    def calc_emissivity(self, *args, **kwargs):
        """Alias for :meth:`emissivity`."""
        return self.emissivity(*args, **kwargs)

    def calc_triplet(self, ion: str | None = None, **kwargs):
        """Calculate a He-like triplet summary from rows or an XSTAR context."""
        from .workflow import calc_triplet
        return calc_triplet(ion=ion, **kwargs)

    def solve_populations(self, ion: IonLike, **kwargs):
        """Workflow-style alias for ``db.solve.ion(...)``."""
        return self.solve.ion(ion, **kwargs)

    def build_matrix(self, ion: IonLike, **kwargs):
        """Workflow-style alias for ``db.matrix.build_ion(...)``."""
        return self.matrix.build_ion(ion, **kwargs)

    def type50_rate(self, **kwargs):
        """Evaluate an audit-only XSTAR type-50 bound-bound radiative rate.

        This is a convenience wrapper around
        :func:`xstar_atomic.rates_type50.evaluate_type50_bound_bound`.  It does
        not alter the population solver.
        """
        from .rates_type50 import evaluate_type50_bound_bound

        return evaluate_type50_bound_bound(**kwargs)

    def audit_type50_line_pumping(self, cases_csv: Union[str, Path], **kwargs):
        """Run the reusable He-like type-50 line-pumping audit workflow.

        This wraps :func:`xstar_atomic.audit.type50_line_pumping` so users who
        start from an :class:`XSTARAtomic` object can access the audit API
        without importing the audit module separately.
        """
        from .audit import type50_line_pumping

        return type50_line_pumping(cases_csv, **kwargs)
