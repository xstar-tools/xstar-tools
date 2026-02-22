"""High-level Python API for :mod:`xstar_atomic`.

The :class:`XSTARAtomic` class is a convenience wrapper around the lower-level
:class:`xstar_atomic.hierarchy.ATDB` packed-FITS reader.  It provides notebook-
and script-friendly methods for the currently implemented decoders while keeping
``ATDB`` available for direct record access.

This API is intentionally thin in v0.1.x: it delegates to the same validated
module-level functions used by the command-line tools, so results should match
CLI output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, Optional, Sequence, Tuple, Union

from .hierarchy import ATDB, SYMBOL_TO_Z, summarize as hierarchy_summary
from .lines import (
    extract_levels,
    extract_lines,
    filter_lines,
)
from .photoionization import (
    extract_photoionization,
    filter_summaries as filter_photoionization_summaries,
)
from .collisions import (
    extract_collisions,
    filter_rows as filter_collision_rows,
)
from .recombination import (
    extract_recombination_records,
    evaluate_records as evaluate_recombination_records,
    make_source_rows as make_recombination_source_rows,
    make_cascade_rows,
    classify_recombination_records,
)
from .emissivity import (
    build_emissivity_rows,
    filter_lines_for_query as filter_emissivity_lines,
    filter_collision_rows as filter_emissivity_collision_rows,
    summarize as emissivity_summary,
)

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


class XSTARAtomic:
    """High-level interface to XSTAR's packed ``atdb.fits`` atomic database.

    Parameters
    ----------
    fitsfile:
        Path to XSTAR's released packed atomic database, usually
        ``xstar/data/atdb.fits``.
    load_reals:
        Whether to load/map the REALS array immediately. Most physical decoders
        need real values, so the default is ``True``.
    build_index:
        If ``True``, build the record/element/ion index at initialization.
    """

    def __init__(self, fitsfile: Union[str, Path], *, load_reals: bool = True, build_index: bool = True):
        self.fitsfile = str(fitsfile)
        self.db = ATDB(self.fitsfile, load_reals=load_reals)
        self._records = None
        self._elements = None
        self._ions = None
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

    def build_index(self):
        """Build and cache ``(records, elements, ions)`` from the packed ATDB."""
        self._records, self._elements, self._ions = self.db.build_index()
        return self._records, self._elements, self._ions

    def select(self, ion: IonLike = None, *, element: Optional[Union[str, int]] = None, ion_stage: Optional[int] = None) -> AtomicSelection:
        z, stage, symbol = parse_ion(ion, element=element, ion_stage=ion_stage)
        return AtomicSelection(z=z, ion_stage=stage, element=symbol)

    def summary(self) -> dict:
        """Return a compact hierarchy summary for the database."""
        return hierarchy_summary(self.records, self.elements, self.ions, self.db)

    def levels(self, ion: IonLike = None, *, element: Optional[Union[str, int]] = None, ion_stage: Optional[int] = None) -> list[dict]:
        """Decode level records for an element/ion selection."""
        sel = self.select(ion, element=element, ion_stage=ion_stage)
        return extract_levels(self.db, self.records, sel.z, sel.ion_stage)

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
        sel = self.select(ion, element=element, ion_stage=ion_stage)
        rows = extract_lines(self.db, self.records, sel.z, sel.ion_stage)
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
        sel = self.select(ion, element=element, ion_stage=ion_stage)
        summaries, grids = extract_photoionization(self.db, self.records, sel.z, sel.ion_stage)
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
    ) -> dict:
        """Return collision summaries and evaluated rates."""
        sel = self.select(ion, element=element, ion_stage=ion_stage)
        summary_rows, grid_rows, eval_rows = extract_collisions(self.db, self.records, sel.z, sel.ion_stage, temperatures)
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
        out = {"summary": selected, "evaluated": eval_selected}
        if include_grid:
            out["grid"] = [r for r in grid_rows if r.get("record") in keep]
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
        sel = self.select(ion, element=element, ion_stage=ion_stage)
        rows = extract_recombination_records(self.db, self.records, sel.z, sel.ion_stage)
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
        out = {"records": rows, "evaluated": eval_rows, "sources": source_rows}
        if cascade_mode == "radiative-branching":
            if sel.ion_stage is None:
                raise ValueError("cascade_mode requires an ion-stage-specific selection")
            line_rows = self.lines(element=sel.z, ion_stage=sel.ion_stage)
            cascade_sources, cascade_paths = make_cascade_rows(source_rows, line_rows)
            out["cascade_sources"] = cascade_sources
            out["cascade_paths"] = cascade_paths
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
    ) -> dict:
        """Build a direct-excitation emissivity table for selected lines."""
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
        collision_summary, _collision_grid, collision_eval = extract_collisions(self.db, self.records, sel.z, sel.ion_stage, temperatures)
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
        }
