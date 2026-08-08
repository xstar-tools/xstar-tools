"""Source-faithful radial density and pass-control contracts from ``xstar.f90``.

The original radial caller has two important control paths that are not
subroutines of their own:

* ``radexp < -99`` opens ``density.dat``, consumes the first radius/density
  pair before the pass loop, and consumes one additional pair after every
  shell; and
* the outer iteration is a fixed user-requested pass count, not an adaptive
  numerical convergence test.  ``numrec <= 0`` forces ``npass = 1`` and the
  shell loops use the literal source predicates.

This module translates those inline contracts without introducing output
writers or an invented convergence algorithm.
"""

# Source correspondence:
#   Fortran: inline radial/pass predicates in xstar.f90.
#   Role: density.dat progression and literal pass/shell loop contracts.
#   Concordance: RADIAL-001; qualification: all-62 STEP science accepted at 12.3.42.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence, Tuple

import numpy as np

from .state import XSTARPythonState


class RadialControlPortError(RuntimeError):
    """Raised when source-defined radial control would enter undefined state."""


class TabulatedRadialDensityError(RadialControlPortError):
    """Base error for the ``density.dat`` source branch."""


class TabulatedRadialRadiusError(TabulatedRadialDensityError):
    """Python equivalent of the source ``stop 'radius error'``."""


@dataclass(frozen=True)
class TabulatedDensityReadResult:
    """One sequential list-directed ``density.dat`` read."""

    radius_cm: float
    density_cm3: float
    iostat: int
    row_one_based: int | None
    retained_previous_values: bool


@dataclass
class TabulatedRadialDensityState:
    """Caller-owned sequential state for the source ``density.dat`` unit.

    A failed end-of-file read retains the previous ``rnew`` and ``dennew``
    values, matching the observed gfortran behavior used by XSTAR.  ``iostat``
    becomes nonzero and terminates the next source shell-loop condition.
    """

    radii_cm: np.ndarray
    densities_cm3: np.ndarray
    next_index_zero_based: int = 0
    last_radius_cm: float | None = None
    last_density_cm3: float | None = None
    iostat: int = 0
    initialized: bool = False
    source_path: str | None = None

    @classmethod
    def from_rows(
        cls,
        rows: Iterable[Sequence[float]],
        *,
        source_path: str | None = None,
    ) -> "TabulatedRadialDensityState":
        values = np.asarray(list(rows), dtype=float)
        if values.ndim != 2 or values.shape[1] != 2 or values.shape[0] < 1:
            raise TabulatedRadialDensityError(
                "tabulated radial density requires at least one (radius, density) row"
            )
        if not np.all(np.isfinite(values)):
            raise TabulatedRadialDensityError(
                "tabulated radial density contains non-finite values"
            )
        if np.any(values[:, 1] <= 0.0):
            raise TabulatedRadialDensityError(
                "tabulated radial density requires positive densities"
            )
        return cls(
            radii_cm=np.asarray(values[:, 0], dtype=float),
            densities_cm3=np.asarray(values[:, 1], dtype=float),
            source_path=source_path,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "TabulatedRadialDensityState":
        """Read the two-column list-directed input used by ``density.dat``."""
        source = Path(path)
        rows: list[Tuple[float, float]] = []
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise TabulatedRadialDensityError(
                f"missing density file: {source}"
            ) from exc
        for lineno, raw in enumerate(lines, start=1):
            text = raw.strip()
            if not text:
                continue
            fields = text.replace(",", " ").split()
            if len(fields) < 2:
                raise TabulatedRadialDensityError(
                    f"density row {lineno} has fewer than two values"
                )
            try:
                radius = float(fields[0].replace("D", "E").replace("d", "e"))
                density = float(fields[1].replace("D", "E").replace("d", "e"))
            except ValueError as exc:
                raise TabulatedRadialDensityError(
                    f"invalid density row {lineno}: {raw!r}"
                ) from exc
            rows.append((radius, density))
        return cls.from_rows(rows, source_path=str(source))

    @property
    def row_count(self) -> int:
        return int(self.radii_cm.size)

    def read_next(self) -> TabulatedDensityReadResult:
        """Perform one source-order sequential read with retained EOF values."""
        idx = int(self.next_index_zero_based)
        if idx < self.row_count:
            radius = float(self.radii_cm[idx])
            density = float(self.densities_cm3[idx])
            self.next_index_zero_based = idx + 1
            self.last_radius_cm = radius
            self.last_density_cm3 = density
            self.iostat = 0
            return TabulatedDensityReadResult(
                radius_cm=radius,
                density_cm3=density,
                iostat=0,
                row_one_based=idx + 1,
                retained_previous_values=False,
            )
        if self.last_radius_cm is None or self.last_density_cm3 is None:
            raise TabulatedRadialDensityError(
                "initial density.dat read reached end of file and left source values undefined"
            )
        self.iostat = -1
        return TabulatedDensityReadResult(
            radius_cm=float(self.last_radius_cm),
            density_cm3=float(self.last_density_cm3),
            iostat=-1,
            row_one_based=None,
            retained_previous_values=True,
        )


def initialize_tabulated_radial_density(
    state: XSTARPythonState,
    table: TabulatedRadialDensityState,
) -> TabulatedDensityReadResult:
    """Apply the pre-pass ``density.dat`` read from ``xstar.f90``."""
    if table.initialized:
        raise TabulatedRadialDensityError(
            "tabulated radial density state has already been initialized"
        )
    result = table.read_next()
    if result.iostat != 0:
        raise TabulatedRadialDensityError(
            "initial density.dat read failed and source rnew/dennew are undefined"
        )
    state.transfer.radius = result.radius_cm
    state.plasma.xpx = result.density_cm3
    state.control["r"] = result.radius_cm
    state.control["xpx"] = result.density_cm3
    state.control["density_iostat"] = result.iostat
    state.control["tabulated_density_state"] = table
    table.initialized = True
    state.transfer.provenance["tabulated_density_initialization"] = {
        "source_file": "xstar/src/xstar/xstar.f90",
        "source_path": table.source_path or "caller-owned rows",
        "row_one_based": result.row_one_based,
        "radius_cm": result.radius_cm,
        "density_cm3": result.density_cm3,
        "iostat": result.iostat,
    }
    return result


def advance_tabulated_radial_density(
    state: XSTARPythonState,
) -> TabulatedDensityReadResult:
    """Apply the post-``savd`` tabulated radius/density update literally."""
    table = state.control.get("tabulated_density_state")
    if not isinstance(table, TabulatedRadialDensityState):
        raise TabulatedRadialDensityError(
            "radexp < -99 requires caller-owned TabulatedRadialDensityState"
        )
    if not table.initialized:
        raise TabulatedRadialDensityError(
            "tabulated radial density must be initialized before shell execution"
        )
    current_radius = float(state.transfer.radius)
    result = table.read_next()
    delr = result.radius_cm - current_radius
    if delr < 0.0:
        raise TabulatedRadialRadiusError("radius error")
    # Preserve assignment order: delr, r, xpx.  Accumulation follows in caller.
    state.transfer.step_size = float(delr)
    state.transfer.radius = result.radius_cm
    state.plasma.xpx = result.density_cm3
    state.control["delr"] = float(delr)
    state.control["r"] = result.radius_cm
    state.control["xpx"] = result.density_cm3
    state.control["density_iostat"] = result.iostat
    state.transfer.provenance.setdefault("tabulated_density_reads", []).append(
        {
            "source_file": "xstar/src/xstar/xstar.f90",
            "row_one_based": result.row_one_based,
            "radius_cm": result.radius_cm,
            "density_cm3": result.density_cm3,
            "delr_cm": float(delr),
            "iostat": result.iostat,
            "retained_previous_values": result.retained_previous_values,
        }
    )
    return result


@dataclass(frozen=True)
class RadialPassConvergenceContract:
    """Explicit source contract for XSTAR's radial pass loop.

    XSTAR performs exactly ``npass`` requested passes (except that
    ``numrec <= 0`` forces one pass).  It does not compare successive passes
    against a numerical tolerance.  ``completed`` therefore means fixed pass
    schedule completion, not an invented physical convergence test.
    """

    requested_passes: int
    effective_passes: int
    initial_numrec: int
    directions: tuple[int, ...]
    adaptive_convergence_used: bool
    convergence_kind: str
    first_pass_predicate: str
    repeated_pass_predicate: str
    source_file: str = "xstar/src/xstar/xstar.f90"


def build_radial_pass_convergence_contract(
    *, numrec: int, npass: int
) -> RadialPassConvergenceContract:
    requested = int(npass)
    if requested < 1:
        raise RadialControlPortError("npass must be positive")
    initial_numrec = int(numrec)
    effective = 1 if initial_numrec <= 0 else requested
    directions = tuple(int((-1) ** kk) for kk in range(1, effective + 1))
    return RadialPassConvergenceContract(
        requested_passes=requested,
        effective_passes=effective,
        initial_numrec=initial_numrec,
        directions=directions,
        adaptive_convergence_used=False,
        convergence_kind="fixed_requested_pass_count",
        first_pass_predicate=(
            "xcol<xpxcol and xee>xeemin and t>tinf*0.99 and numrec>0 and ierr==0"
        ),
        repeated_pass_predicate="jkp<numrec and ierr==0",
    )


def first_pass_shell_condition(state: XSTARPythonState) -> bool:
    """Evaluate the literal first-pass ``do while`` state predicate."""
    return bool(
        float(state.transfer.column) < float(state.control.get("xpxcol", np.inf))
        and float(state.plasma.xee) > float(state.control.get("xeemin", -np.inf))
        # Python owns temperature in kelvin; source ``t`` and ``tinf`` are
        # measured in 10^4 K.
        and float(state.plasma.temperature) / 1.0e4
        > float(state.control.get("tinf", 0.0)) * 0.99
        and int(state.control.get("numrec", 0)) > 0
        and int(state.control.get("density_iostat", 0)) == 0
    )


def repeated_pass_shell_condition(
    state: XSTARPythonState, *, completed_shells: int
) -> bool:
    """Evaluate the literal later-pass ``jkp<numrec`` and ``ierr==0`` test."""
    return bool(
        int(completed_shells) < int(state.control.get("numrec", 0))
        and int(state.control.get("density_iostat", 0)) == 0
    )


__all__ = [
    "RadialControlPortError",
    "TabulatedRadialDensityError",
    "TabulatedRadialRadiusError",
    "TabulatedDensityReadResult",
    "TabulatedRadialDensityState",
    "initialize_tabulated_radial_density",
    "advance_tabulated_radial_density",
    "RadialPassConvergenceContract",
    "build_radial_pass_convergence_contract",
    "first_pass_shell_condition",
    "repeated_pass_shell_condition",
]


def direct_fortran_tabulated_density_reference_cases() -> dict[str, object]:
    """Frozen outputs from the literal inline ``xstar.f90`` density fragment."""
    return {
        "initial": {
            "iostat": 0,
            "radius_cm": 1.0e18,
            "density_cm3": 1.25e8,
            "radial_depth_cm": 0.0,
            "column_cm2": 0.0,
        },
        "steps": [
            {
                "iostat": 0,
                "delr_cm": 4.0e17,
                "radius_cm": 1.4e18,
                "density_cm3": 2.5e8,
                "radial_depth_cm": 4.0e17,
                "column_cm2": 1.0e26,
            },
            {
                "iostat": 0,
                "delr_cm": 7.0e17,
                "radius_cm": 2.1e18,
                "density_cm3": 4.0e8,
                "radial_depth_cm": 1.1e18,
                "column_cm2": 3.8000000000000002e26,
            },
            {
                "iostat": -1,
                "delr_cm": 0.0,
                "radius_cm": 2.1e18,
                "density_cm3": 4.0e8,
                "radial_depth_cm": 1.1e18,
                "column_cm2": 3.8000000000000002e26,
            },
        ],
    }


def run_direct_fortran_tabulated_density_validation(
    *, rtol: float = 2.0e-15, atol: float = 0.0
) -> dict[str, bool]:
    """Compare Python to the compiled literal source-fragment reference."""
    reference = direct_fortran_tabulated_density_reference_cases()
    state = XSTARPythonState()
    state.control["radexp"] = -100.0
    table = TabulatedRadialDensityState.from_rows(
        [(1.0e18, 1.25e8), (1.4e18, 2.5e8), (2.1e18, 4.0e8)]
    )
    initial = initialize_tabulated_radial_density(state, table)
    initial_ref = reference["initial"]
    initial_ready = bool(
        initial.iostat == initial_ref["iostat"]
        and np.isclose(state.transfer.radius, initial_ref["radius_cm"], rtol=rtol, atol=atol)
        and np.isclose(state.plasma.xpx, initial_ref["density_cm3"], rtol=rtol, atol=atol)
    )

    rows: list[dict[str, float | int | bool]] = []
    for _ in range(3):
        read = advance_tabulated_radial_density(state)
        delr = float(state.transfer.step_size)
        state.transfer.radial_depth += delr
        state.transfer.column += float(state.plasma.xpx) * delr
        rows.append(
            {
                "iostat": read.iostat,
                "delr_cm": delr,
                "radius_cm": state.transfer.radius,
                "density_cm3": state.plasma.xpx,
                "radial_depth_cm": state.transfer.radial_depth,
                "column_cm2": state.transfer.column,
                "retained_previous_values": read.retained_previous_values,
            }
        )
    step_ready = []
    for got, expected in zip(rows, reference["steps"]):
        step_ready.append(
            got["iostat"] == expected["iostat"]
            and all(
                np.isclose(float(got[key]), float(expected[key]), rtol=rtol, atol=atol)
                for key in (
                    "delr_cm",
                    "radius_cm",
                    "density_cm3",
                    "radial_depth_cm",
                    "column_cm2",
                )
            )
        )
    eof_ready = bool(
        rows[-1]["iostat"] == -1
        and rows[-1]["retained_previous_values"] is True
        and rows[-1]["delr_cm"] == 0.0
    )
    return {
        "tabulated_density_initial_direct_fortran_ready": initial_ready,
        "tabulated_density_updates_direct_fortran_ready": bool(all(step_ready)),
        "tabulated_density_eof_retains_values_ready": eof_ready,
        "tabulated_density_direct_original_fortran_reference_ready": bool(
            initial_ready and all(step_ready) and eof_ready
        ),
    }


__all__.extend([
    "direct_fortran_tabulated_density_reference_cases",
    "run_direct_fortran_tabulated_density_validation",
])
