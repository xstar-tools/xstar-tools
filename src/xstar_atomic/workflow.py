"""Workflow-first public API helpers for :mod:`xstar_atomic`.

These functions provide the simple, CHIANTI-tools-like entry points discussed in
v0.3.131.  They are thin wrappers around :class:`xstar_atomic.api.XSTARAtomic`
and the source-aligned context/audit objects.  The goal is to let users start
with science tasks such as line lookup, emissivity estimates, triplet summaries,
or population solves without first navigating the lower-level packed-ATDB
readers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, TYPE_CHECKING
import csv

if TYPE_CHECKING:  # pragma: no cover
    from .api import XSTARAtomic

IonLike = Any

def _parse_ion(ion: IonLike):
    from .api import parse_ion
    return parse_ion(ion)

from .context import XSTARContext, context_from_values, context_from_xstar_run
from .rates_type50 import evaluate_type50_bound_bound


@dataclass(frozen=True)
class TripletResult:
    """He-like triplet summary returned by :func:`calc_triplet`.

    The values are normalized fractions when a nonzero total is available.  The
    original component fluxes/emissivities and contributing rows are retained so
    that validation workflows can trace how the diagnostic was constructed.
    """

    ion: str | None = None
    forbidden: float | None = None
    intercombination: float | None = None
    resonance: float | None = None
    f: float | None = None
    i: float | None = None
    r: float | None = None
    R_f_over_i: float | None = None
    G_f_plus_i_over_r: float | None = None
    total: float | None = None
    value_column: str = "emit_outward"
    lines: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    status: str = "ok"
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/CSV-friendly summary."""
        return {
            "ion": self.ion,
            "forbidden": self.forbidden,
            "intercombination": self.intercombination,
            "resonance": self.resonance,
            "f": self.f,
            "i": self.i,
            "r": self.r,
            "R_f_over_i": self.R_f_over_i,
            "G_f_plus_i_over_r": self.G_f_plus_i_over_r,
            "total": self.total,
            "value_column": self.value_column,
            "n_lines": len(self.lines),
            "status": self.status,
            "warnings": "; ".join(self.warnings),
            "metadata": dict(self.metadata),
        }


def open_database(fitsfile: str | Path | None = None, **kwargs: Any):
    """Open XSTAR's packed ``atdb.fits`` through the high-level API."""
    from .api import XSTARAtomic
    return XSTARAtomic(fitsfile, **kwargs)


def _coerce_db(db: Any = None, *, fitsfile: str | Path | None = None):
    from .api import XSTARAtomic
    if isinstance(db, XSTARAtomic):
        return db, False
    path = fitsfile if fitsfile is not None else db
    return XSTARAtomic(path), True


def get_levels(ion: IonLike = None, *, db: Any = None, fitsfile: str | Path | None = None, **kwargs: Any) -> list[dict]:
    """Return decoded level records for an ion or element selection."""
    handle, close = _coerce_db(db, fitsfile=fitsfile)
    try:
        return handle.levels(ion, **kwargs)
    finally:
        if close:
            handle.close()


def get_lines(ion: IonLike = None, *, db: Any = None, fitsfile: str | Path | None = None, **kwargs: Any) -> list[dict]:
    """Return decoded radiative lines for an ion or element selection."""
    handle, close = _coerce_db(db, fitsfile=fitsfile)
    try:
        return handle.lines(ion, **kwargs)
    finally:
        if close:
            handle.close()


def get_wavelengths(ion: IonLike = None, *, db: Any = None, fitsfile: str | Path | None = None, **kwargs: Any) -> list[float]:
    """Return sorted wavelengths in Angstrom for selected line records."""
    rows = get_lines(ion, db=db, fitsfile=fitsfile, **kwargs)
    vals: list[float] = []
    for row in rows:
        try:
            value = row.get("wavelength_A", row.get("wavelength"))
            if value is not None:
                vals.append(float(value))
        except Exception:
            pass
    return sorted(vals)


def get_energies(ion: IonLike = None, *, db: Any = None, fitsfile: str | Path | None = None, **kwargs: Any) -> list[float]:
    """Return sorted line energies in keV when available."""
    rows = get_lines(ion, db=db, fitsfile=fitsfile, **kwargs)
    vals: list[float] = []
    for row in rows:
        try:
            value = row.get("energy_kev", row.get("energy_keV"))
            if value is not None:
                vals.append(float(value))
        except Exception:
            pass
    return sorted(vals)


def match_line(
    ion: IonLike = None,
    *,
    wavelength: float | None = None,
    energy_kev: float | None = None,
    tolerance_A: float | None = None,
    tolerance_keV: float | None = None,
    db: Any = None,
    fitsfile: str | Path | None = None,
    **kwargs: Any,
) -> dict | None:
    """Return the closest matching line for a wavelength or energy query."""
    rows = get_lines(ion, db=db, fitsfile=fitsfile, **kwargs)
    best: tuple[float, dict] | None = None
    for row in rows:
        try:
            if wavelength is not None:
                val = row.get("wavelength_A", row.get("wavelength"))
                if val is None:
                    continue
                dist = abs(float(val) - float(wavelength))
                if tolerance_A is not None and dist > float(tolerance_A):
                    continue
            elif energy_kev is not None:
                val = row.get("energy_kev", row.get("energy_keV"))
                if val is None:
                    continue
                dist = abs(float(val) - float(energy_kev))
                if tolerance_keV is not None and dist > float(tolerance_keV):
                    continue
            else:
                raise ValueError("match_line requires wavelength=... or energy_kev=...")
        except Exception:
            continue
        if best is None or dist < best[0]:
            best = (dist, dict(row))
    return None if best is None else best[1]


def match_lines(
    ion: IonLike = None,
    *,
    wavelengths: Sequence[float] | None = None,
    energies_kev: Sequence[float] | None = None,
    **kwargs: Any,
) -> list[dict | None]:
    """Match multiple wavelengths or energies with :func:`match_line`."""
    if wavelengths is not None:
        return [match_line(ion, wavelength=w, **kwargs) for w in wavelengths]
    if energies_kev is not None:
        return [match_line(ion, energy_kev=e, **kwargs) for e in energies_kev]
    raise ValueError("match_lines requires wavelengths=... or energies_kev=...")


def get_collisions(ion: IonLike = None, *, db: Any = None, fitsfile: str | Path | None = None, **kwargs: Any) -> dict:
    """Return collision records/evaluations for a selection."""
    handle, close = _coerce_db(db, fitsfile=fitsfile)
    try:
        return handle.collisions(ion, **kwargs)
    finally:
        if close:
            handle.close()


def get_photoionization(ion: IonLike = None, *, db: Any = None, fitsfile: str | Path | None = None, **kwargs: Any):
    """Return photoionization/bound-free records for a selection."""
    handle, close = _coerce_db(db, fitsfile=fitsfile)
    try:
        return handle.photoionization(ion, **kwargs)
    finally:
        if close:
            handle.close()


def get_recombination(ion: IonLike = None, *, db: Any = None, fitsfile: str | Path | None = None, **kwargs: Any) -> dict:
    """Return recombination records/evaluations for a selection."""
    handle, close = _coerce_db(db, fitsfile=fitsfile)
    try:
        return handle.recombination(ion, **kwargs)
    finally:
        if close:
            handle.close()


def calc_emissivity(ion: IonLike = None, *, db: Any = None, fitsfile: str | Path | None = None, **kwargs: Any) -> dict:
    """Calculate direct-excitation emissivity rows for selected lines."""
    handle, close = _coerce_db(db, fitsfile=fitsfile)
    try:
        return handle.emissivity(ion, **kwargs)
    finally:
        if close:
            handle.close()


def calc_rate(kind: str, /, **kwargs: Any):
    """Evaluate a named source-aligned rate evaluator.

    Currently stable values for ``kind`` are ``"type50"`` and
    ``"type50_bound_bound"``.  Additional XSTAR data types will be routed here
    as their evaluators become provenance-complete.
    """
    key = str(kind).strip().lower().replace("-", "_")
    if key in {"type50", "type50_bound_bound", "bound_bound_type50"}:
        return evaluate_type50_bound_bound(**kwargs)
    raise NotImplementedError(f"No public rate evaluator is registered for kind={kind!r}")


def _read_csv_rows(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_triplet_rows_from_context(context: XSTARContext | None, ion: str | None, wavelength: tuple[float, float] | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if context is None or context.run_dir is None:
        return [], {}
    run_dir = Path(context.run_dir)
    lines_path = run_dir / "xout_lines1.fits"
    if not lines_path.exists():
        return [], {"warning": f"{lines_path} not found"}
    from .xstar_outputs import load_xstar_lines
    rows = load_xstar_lines(
        lines_path,
        ion=ion or context.ion,
        wavelength_min=wavelength[0] if wavelength else None,
        wavelength_max=wavelength[1] if wavelength else None,
    )
    return rows, {"xstar_lines_path": str(lines_path)}


def _classify_triplet(row: Mapping[str, Any]) -> str | None:
    text = " ".join(str(row.get(k, "")) for k in ("upper_level", "upper", "upper_label", "level_label")).lower()
    if "1p_1" in text or "1p1" in text or "1p.1" in text or "1p1.1p" in text or "1p 1p" in text:
        return "r"
    if "3s_1" in text or "3s1" in text or "3s.3" in text or "2s1.3s" in text:
        return "f"
    if "3p" in text:
        return "i"
    # XSTAR labels often look like 1s1.2p1.1P_1 / 1s1.2s1.3S_1.
    if "1p_1" in text or "1p" in text and "1" in text and "3p" not in text:
        return "r"
    return None


def calc_triplet(
    ion: str | None = None,
    *,
    context: XSTARContext | None = None,
    rows: Sequence[Mapping[str, Any]] | None = None,
    xstar_lines_csv: str | Path | None = None,
    value_column: str = "emit_outward",
    wavelength: tuple[float, float] | None = None,
) -> TripletResult:
    """Calculate a He-like triplet summary from XSTAR/output rows.

    This workflow function intentionally summarizes existing line rows; it does
    not yet run the population solver unless future versions opt in to a full
    source-aligned matrix workflow.
    """
    metadata: dict[str, Any] = {}
    warnings: list[str] = []
    if rows is None and xstar_lines_csv is not None:
        rows = _read_csv_rows(xstar_lines_csv)
        metadata["xstar_lines_csv"] = str(xstar_lines_csv)
    if rows is None:
        loaded, meta = _load_triplet_rows_from_context(context, ion, wavelength)
        rows = loaded
        metadata.update(meta)
        if meta.get("warning"):
            warnings.append(str(meta["warning"]))
    rows = list(rows or [])
    totals = {"f": 0.0, "i": 0.0, "r": 0.0}
    used: list[Mapping[str, Any]] = []
    for row in rows:
        component = _classify_triplet(row)
        if component is None:
            continue
        try:
            value = float(row.get(value_column, row.get("value", 0.0)) or 0.0)
        except Exception:
            continue
        totals[component] += value
        used.append(dict(row, triplet_component=component))
    total = totals["f"] + totals["i"] + totals["r"]
    f = totals["f"] / total if total else None
    i = totals["i"] / total if total else None
    r = totals["r"] / total if total else None
    R = totals["f"] / totals["i"] if totals["i"] else None
    G = (totals["f"] + totals["i"]) / totals["r"] if totals["r"] else None
    status = "ok" if total else "no_triplet_rows"
    if not total:
        warnings.append("No f/i/r triplet rows could be classified")
    return TripletResult(
        ion=ion or (context.ion if context is not None else None),
        forbidden=totals["f"] if total else None,
        intercombination=totals["i"] if total else None,
        resonance=totals["r"] if total else None,
        f=f,
        i=i,
        r=r,
        R_f_over_i=R,
        G_f_plus_i_over_r=G,
        total=total if total else None,
        value_column=value_column,
        lines=tuple(used),
        status=status,
        warnings=tuple(warnings),
        metadata=metadata,
    )


def _context_values(context: XSTARContext | None, *, temperature: float | None = None, electron_density: float | None = None) -> tuple[float, float]:
    temp = temperature
    dens = electron_density
    if context is not None:
        temp = temp if temp is not None else context.plasma.temperature_K
        dens = dens if dens is not None else context.plasma.electron_density_cm3
    if temp is None or dens is None:
        raise ValueError("temperature and electron_density are required, either directly or through context")
    return float(temp), float(dens)


def solve_populations(
    ion: IonLike,
    *,
    context: XSTARContext | None = None,
    db: Any = None,
    fitsfile: str | Path | None = None,
    temperature: float | None = None,
    electron_density: float | None = None,
    **kwargs: Any,
) -> dict:
    """Run the current source-level population solver wrapper for one ion.

    This is a convenience front end to :func:`solve_element_reference`.  It is
    most mature for He-like workflows, where ``ion`` supplies the element and
    He-like stage and ``context`` supplies local ``T``/``ne``.
    """
    z, stage, symbol = _parse_ion(ion)
    if symbol is None or stage is None:
        raise ValueError("solve_populations requires an ion such as 'O VII'")
    temp, dens = _context_values(context, temperature=temperature, electron_density=electron_density)
    handle, close = _coerce_db(db, fitsfile=fitsfile)
    try:
        from .xstar_element_solver import solve_element_reference
        return solve_element_reference(
            handle.fitsfile,
            element=symbol,
            he_like_stage=int(stage),
            temperature=temp,
            electron_density=dens,
            **kwargs,
        )
    finally:
        if close:
            handle.close()


def build_matrix(ion: IonLike, **kwargs: Any) -> dict:
    """Build/return the matrix-related part of a population-solver result.

    The current solver builds matrix terms internally.  This helper exposes the
    available matrix-related products without injecting new physics.
    """
    result = solve_populations(ion, **kwargs)
    keys = [
        "global_bound_bound_matrix_terms",
        "full_global_matrix_terms",
        "assembled_coupling_terms",
        "transitions",
        "ion_blocks",
        "summary",
    ]
    return {k: result.get(k) for k in keys if k in result}


__all__ = [
    "TripletResult",
    "open_database",
    "get_levels",
    "get_lines",
    "get_wavelengths",
    "get_energies",
    "match_line",
    "match_lines",
    "get_collisions",
    "get_photoionization",
    "get_recombination",
    "calc_emissivity",
    "calc_rate",
    "calc_triplet",
    "solve_populations",
    "build_matrix",
    "context_from_values",
    "context_from_xstar_run",
]
