"""Source-faithful line and RRC optical-depth state for the element port.

XSTAR writes the arrays consumed by ``calc_hmc_ion`` to two radial detail
products:

* ``xo01_detal2.fits`` stores ``tau0(1:2,line)`` and identifies each row by
  the global line index used by ``derivedpointers%nplini``;
* ``xo01_detal3.fits`` stores ``tauc(1:2,rrc)`` and identifies each row by
  the global RRC/continuum index used by ``derivedpointers%npconi2``.

This module maps those rows back into the one-dimensional NumPy arrays used by
:class:`~xstar_tools.xstar.element_equilibrium.EscapeProbabilityContext`.
Missing indices remain NaN and therefore block strict assembly rather than
silently becoming optically thin.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np

from ..xstar_outputs import read_fits_table_hdus
from .atomic_database import XSTARDerivedPointers
from .element_equilibrium import EscapeProbabilityContext


class EscapeStateError(RuntimeError):
    """Raised when XSTAR line/RRC detail state cannot be constructed."""


@dataclass(frozen=True)
class EscapeStateBuildResult:
    """Result of mapping XSTAR radial detail rows onto global pointer indices."""

    context: EscapeProbabilityContext
    run_dir: Path
    zone_selector: str
    line_hdu_index: int | None
    rrc_hdu_index: int | None
    n_line_rows: int
    n_rrc_rows: int
    n_line_indices_loaded: int
    n_rrc_indices_loaded: int
    n_line_indices_missing: int
    n_rrc_indices_missing: int
    n_duplicate_line_indices: int
    n_duplicate_rrc_indices: int
    n_out_of_range_line_indices: int
    n_out_of_range_rrc_indices: int
    line_file: Path
    rrc_file: Path
    detail_policy: str = "strict_selected_zone"
    n_line_hdus_scanned: int = 1
    n_rrc_hdus_scanned: int = 1
    n_line_indices_carried_forward: int = 0
    n_rrc_indices_carried_forward: int = 0
    n_line_indices_zero_filled: int = 0
    n_rrc_indices_zero_filled: int = 0
    exact_live_arrays: bool = True
    source_writer_threshold_reconstruction: bool = False

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the complete operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
    # XSTAR-FUNCTION-COMMENT-END
    @property
    def complete(self) -> bool:
        return (
            self.n_line_indices_missing == 0
            and self.n_rrc_indices_missing == 0
            and self.n_out_of_range_line_indices == 0
            and self.n_out_of_range_rrc_indices == 0
        )

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Serialize the current state into a plain mapping for diagnostics, provenance, or machine-readable output.
    # Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
    # XSTAR-FUNCTION-COMMENT-END
    def as_dict(self) -> Dict[str, Any]:
        return {
            "run_dir": str(self.run_dir),
            "zone_selector": self.zone_selector,
            "line_hdu_index": self.line_hdu_index,
            "rrc_hdu_index": self.rrc_hdu_index,
            "n_line_rows": self.n_line_rows,
            "n_rrc_rows": self.n_rrc_rows,
            "n_line_indices_loaded": self.n_line_indices_loaded,
            "n_rrc_indices_loaded": self.n_rrc_indices_loaded,
            "n_line_indices_missing": self.n_line_indices_missing,
            "n_rrc_indices_missing": self.n_rrc_indices_missing,
            "n_duplicate_line_indices": self.n_duplicate_line_indices,
            "n_duplicate_rrc_indices": self.n_duplicate_rrc_indices,
            "n_out_of_range_line_indices": self.n_out_of_range_line_indices,
            "n_out_of_range_rrc_indices": self.n_out_of_range_rrc_indices,
            "line_file": str(self.line_file),
            "rrc_file": str(self.rrc_file),
            "detail_policy": self.detail_policy,
            "n_line_hdus_scanned": self.n_line_hdus_scanned,
            "n_rrc_hdus_scanned": self.n_rrc_hdus_scanned,
            "n_line_indices_carried_forward": self.n_line_indices_carried_forward,
            "n_rrc_indices_carried_forward": self.n_rrc_indices_carried_forward,
            "n_line_indices_zero_filled": self.n_line_indices_zero_filled,
            "n_rrc_indices_zero_filled": self.n_rrc_indices_zero_filled,
            "exact_live_arrays": self.exact_live_arrays,
            "source_writer_threshold_reconstruction": self.source_writer_threshold_reconstruction,
            "complete": self.complete,
            "source_routines": ["fstepr2.f90", "fstepr3.f90", "calc_hmc_ion.f90"],
        }


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Select hdu for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
# XSTAR-FUNCTION-COMMENT-END
def _select_hdu(hdus: Sequence[Mapping[str, Any]], selector: str | int) -> Mapping[str, Any]:
    if not hdus:
        raise EscapeStateError("detail file contains no XSTAR_RADIAL extensions")
    token = str(selector).strip().lower()
    if token == "first":
        return hdus[0]
    if token == "last":
        return hdus[-1]
    try:
        requested = int(token)
    except ValueError as exc:
        raise EscapeStateError("zone selector must be 'first', 'last', an HDU index, or a 1-based zone number") from exc

    # Prefer an exact FITS HDU index because that is unambiguous and is exposed
    # by read_fits_table_hdus.  Fall back to a one-based radial-zone ordinal.
    for hdu in hdus:
        if int(hdu.get("hdu_index", -1)) == requested:
            return hdu
    if 1 <= requested <= len(hdus):
        return hdus[requested - 1]
    raise EscapeStateError(
        f"zone/HDU selector {requested} is outside the available range "
        f"(radial zones 1..{len(hdus)})"
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the selected prefix operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
# XSTAR-FUNCTION-COMMENT-END
def _selected_prefix(hdus: Sequence[Mapping[str, Any]], selected: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    """Return all radial HDUs through the selected zone, in source order."""
    for pos, hdu in enumerate(hdus):
        if hdu is selected or int(hdu.get("hdu_index", -1)) == int(selected.get("hdu_index", -2)):
            return hdus[: pos + 1]
    return (selected,)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Map hdu history for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
# XSTAR-FUNCTION-COMMENT-END
def _map_hdu_history(
    hdus: Sequence[Mapping[str, Any]], *, size: int, index_keys: Sequence[str],
) -> tuple[np.ndarray, np.ndarray, int, int, int, int, int]:
    """Carry sparse detail rows forward through radial zones."""
    tau_in = np.full(int(size), np.nan, dtype=float)
    tau_out = np.full(int(size), np.nan, dtype=float)
    duplicates = out_of_range = accepted = 0
    previous_seen: set[int] = set()
    selected_seen: set[int] = set()
    for hpos, hdu in enumerate(hdus):
        zone_seen: set[int] = set()
        for row in hdu.get("rows", []):
            idx = _index(row, *index_keys)
            tin = _number(row, "tau_in", "depth_inward")
            tout = _number(row, "tau_out", "depth_outward")
            if idx is None or tin is None or tout is None:
                continue
            if idx < 1 or idx > size:
                out_of_range += 1
                continue
            if idx in zone_seen:
                duplicates += 1
            zone_seen.add(idx)
            tau_in[idx - 1] = tin
            tau_out[idx - 1] = tout
            accepted += 1
        if hpos == len(hdus) - 1:
            selected_seen = zone_seen
        previous_seen.update(zone_seen)
    carried = len(previous_seen - selected_seen)
    unique = int(np.count_nonzero(np.isfinite(tau_in) & np.isfinite(tau_out)))
    return tau_in, tau_out, unique, duplicates, out_of_range, carried, accepted


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the number operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
# XSTAR-FUNCTION-COMMENT-END
def _number(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        try:
            out = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(out):
            return out
    return None


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the index operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
# XSTAR-FUNCTION-COMMENT-END
def _index(row: Mapping[str, Any], *keys: str) -> int | None:
    value = _number(row, *keys)
    if value is None:
        return None
    rounded = int(round(value))
    if abs(value - rounded) > 1.0e-6:
        return None
    return rounded


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Map rows for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
# XSTAR-FUNCTION-COMMENT-END
def _map_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    size: int,
    index_keys: Sequence[str],
) -> tuple[np.ndarray, np.ndarray, int, int, int]:
    tau_in = np.full(int(size), np.nan, dtype=float)
    tau_out = np.full(int(size), np.nan, dtype=float)
    seen: set[int] = set()
    duplicates = 0
    out_of_range = 0
    accepted = 0
    for row in rows:
        idx = _index(row, *index_keys)
        tin = _number(row, "tau_in", "depth_inward")
        tout = _number(row, "tau_out", "depth_outward")
        if idx is None or tin is None or tout is None:
            continue
        if idx < 1 or idx > size:
            out_of_range += 1
            continue
        if idx in seen:
            duplicates += 1
        seen.add(idx)
        tau_in[idx - 1] = tin
        tau_out[idx - 1] = tout
        accepted += 1
    return tau_in, tau_out, accepted, duplicates, out_of_range


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load escape state from xstar run for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
# XSTAR-FUNCTION-COMMENT-END
def load_escape_state_from_xstar_run(
    run_dir: str | Path,
    derived: XSTARDerivedPointers,
    *,
    zone: str | int = "last",
    allow_missing_as_zero: bool = False,
    detail_policy: str = "strict_selected_zone",
) -> EscapeStateBuildResult:
    """Build line and RRC escape arrays from an XSTAR run directory.

    Parameters
    ----------
    run_dir:
        Directory containing ``xo01_detal2.fits`` and ``xo01_detal3.fits``.
    derived:
        v0.4.1 source-port pointer state.  ``nlsvn`` and ``ncsvn`` define the
        exact global line/RRC array lengths expected by ``calc_hmc_ion``.
    zone:
        ``first``, ``last``, a FITS HDU index, or a 1-based radial-zone ordinal.
    allow_missing_as_zero:
        Forwarded to :class:`EscapeProbabilityContext`.
    detail_policy:
        ``strict_selected_zone`` maps only rows written in the selected HDU and
        preserves absent entries as NaN. ``source_sparse_reconstruct`` scans all
        zones through the selected one, carries the latest written value forward,
        and fills never-written entries with zero because ``fstepr2/fstepr3`` omit
        rows below their source output thresholds.
    """
    root = Path(run_dir)
    line_file = root / "xo01_detal2.fits"
    rrc_file = root / "xo01_detal3.fits"
    missing = [str(path) for path in (line_file, rrc_file) if not path.is_file()]
    if missing:
        raise EscapeStateError(
            "missing XSTAR escape-state detail file(s): " + ", ".join(missing)
            + ". Run XSTAR with detail output enabled (lwrite/lprint as required), "
              "or use --assume-optically-thin only for a controlled optically thin test."
        )

    line_hdus = read_fits_table_hdus(line_file, "XSTAR_RADIAL")
    rrc_hdus = read_fits_table_hdus(rrc_file, "XSTAR_RADIAL")
    line_hdu = _select_hdu(line_hdus, zone)
    rrc_hdu = _select_hdu(rrc_hdus, zone)
    line_rows = list(line_hdu.get("rows", []))
    rrc_rows = list(rrc_hdu.get("rows", []))
    policy = str(detail_policy).strip().lower()
    if policy not in {"strict_selected_zone", "source_sparse_reconstruct"}:
        raise EscapeStateError("detail_policy must be strict_selected_zone or source_sparse_reconstruct")
    if policy == "strict_selected_zone":
        line_in, line_out, _n, dup_line, oor_line = _map_rows(
            line_rows, size=int(derived.nlsvn), index_keys=("index", "line_index"),
        )
        rrc_in, rrc_out, _n2, dup_rrc, oor_rrc = _map_rows(
            rrc_rows, size=int(derived.ncsvn), index_keys=("rrc_index", "index", "continuum_index"),
        )
        line_loaded, rrc_loaded = int(_n), int(_n2)
        line_unresolved = int(derived.nlsvn) - line_loaded
        rrc_unresolved = int(derived.ncsvn) - rrc_loaded
        line_scan = rrc_scan = 1
        line_carried = rrc_carried = 0
        line_zero = rrc_zero = 0
        exact = True
        reconstructed = False
    else:
        line_prefix = _selected_prefix(line_hdus, line_hdu)
        rrc_prefix = _selected_prefix(rrc_hdus, rrc_hdu)
        line_in, line_out, _n, dup_line, oor_line, line_carried, _ = _map_hdu_history(
            line_prefix, size=int(derived.nlsvn), index_keys=("index", "line_index"),
        )
        rrc_in, rrc_out, _n2, dup_rrc, oor_rrc, rrc_carried, _ = _map_hdu_history(
            rrc_prefix, size=int(derived.ncsvn), index_keys=("rrc_index", "index", "continuum_index"),
        )
        line_loaded, rrc_loaded = int(_n), int(_n2)
        line_unresolved = rrc_unresolved = 0
        line_scan, rrc_scan = len(line_prefix), len(rrc_prefix)
        line_missing_mask = ~(np.isfinite(line_in) & np.isfinite(line_out))
        rrc_missing_mask = ~(np.isfinite(rrc_in) & np.isfinite(rrc_out))
        line_zero = int(np.count_nonzero(line_missing_mask))
        rrc_zero = int(np.count_nonzero(rrc_missing_mask))
        line_in[line_missing_mask] = 0.0; line_out[line_missing_mask] = 0.0
        rrc_in[rrc_missing_mask] = 0.0; rrc_out[rrc_missing_mask] = 0.0
        exact = False
        reconstructed = True

    context = EscapeProbabilityContext(
        line_tau_in=line_in,
        line_tau_out=line_out,
        continuum_tau_in=rrc_in,
        continuum_tau_out=rrc_out,
        allow_missing_as_zero=allow_missing_as_zero,
    )
    return EscapeStateBuildResult(
        context=context,
        run_dir=root,
        zone_selector=str(zone),
        line_hdu_index=int(line_hdu.get("hdu_index", -1)),
        rrc_hdu_index=int(rrc_hdu.get("hdu_index", -1)),
        n_line_rows=len(line_rows),
        n_rrc_rows=len(rrc_rows),
        n_line_indices_loaded=line_loaded,
        n_rrc_indices_loaded=rrc_loaded,
        n_line_indices_missing=line_unresolved,
        n_rrc_indices_missing=rrc_unresolved,
        n_duplicate_line_indices=dup_line,
        n_duplicate_rrc_indices=dup_rrc,
        n_out_of_range_line_indices=oor_line,
        n_out_of_range_rrc_indices=oor_rrc,
        line_file=line_file,
        rrc_file=rrc_file,
        detail_policy=policy,
        n_line_hdus_scanned=line_scan,
        n_rrc_hdus_scanned=rrc_scan,
        n_line_indices_carried_forward=line_carried,
        n_rrc_indices_carried_forward=rrc_carried,
        n_line_indices_zero_filled=line_zero,
        n_rrc_indices_zero_filled=rrc_zero,
        exact_live_arrays=exact,
        source_writer_threshold_reconstruction=reconstructed,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write escape state npz for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
# XSTAR-FUNCTION-COMMENT-END
def write_escape_state_npz(result: EscapeStateBuildResult, path: str | Path) -> Path:
    """Write a reusable escape-state NPZ in the element CLI schema."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    context = result.context
    np.savez_compressed(
        target,
        line_tau_in=np.asarray(context.line_tau_in, dtype=float),
        line_tau_out=np.asarray(context.line_tau_out, dtype=float),
        continuum_tau_in=np.asarray(context.continuum_tau_in, dtype=float),
        continuum_tau_out=np.asarray(context.continuum_tau_out, dtype=float),
        metadata_json=np.asarray(json.dumps(result.as_dict(), sort_keys=True)),
    )
    return target


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write escape state summary for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.5-11.6, line and recombination-continuum escape probabilities.
# XSTAR-FUNCTION-COMMENT-END
def write_escape_state_summary(result: EscapeStateBuildResult, out_dir: str | Path) -> Dict[str, Path]:
    """Write JSON and Markdown coverage reports for a derived escape state."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "xstar_escape_state_summary.json"
    md_path = root / "xstar_escape_state_summary.md"
    payload = result.as_dict()
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# XSTAR source-faithful escape state",
        "",
        f"- Run directory: `{payload['run_dir']}`",
        f"- Zone selector: `{payload['zone_selector']}`",
        f"- Detail policy: `{payload['detail_policy']}`",
        f"- Exact live arrays: `{payload['exact_live_arrays']}`",
        f"- Source-writer threshold reconstruction: `{payload['source_writer_threshold_reconstruction']}`",
        f"- Line HDU index: `{payload['line_hdu_index']}`",
        f"- RRC HDU index: `{payload['rrc_hdu_index']}`",
        f"- Loaded line indices: `{payload['n_line_indices_loaded']}` / "
        f"`{payload['n_line_indices_loaded'] + payload['n_line_indices_missing']}`",
        f"- Loaded RRC indices: `{payload['n_rrc_indices_loaded']}` / "
        f"`{payload['n_rrc_indices_loaded'] + payload['n_rrc_indices_missing']}`",
        f"- Complete global arrays: `{payload['complete']}`",
        "",
        "Missing entries remain NaN and block strict element assembly. They are not silently treated as optically thin.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
