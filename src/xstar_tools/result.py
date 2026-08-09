"""Stable public result and product objects for :mod:`xstar_tools`."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


_FITS_NAMES = (
    "xout_abund1.fits",
    "xout_lines1.fits",
    "xout_rrc1.fits",
    "xout_cont1.fits",
    "xout_spect1.fits",
    "xo01_detail.fits",
    "xo01_detal2.fits",
    "xo01_detal3.fits",
    "xo01_detal4.fits",
)


@dataclass(frozen=True)
class XStarProducts:
    """Deterministic typed paths for principal XSTAR output products."""
    output_dir: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_dir", Path(self.output_dir).expanduser().resolve())

    @property
    def abundances(self) -> Path:
        return self.output_dir / "xout_abund1.fits"

    @property
    def lines(self) -> Path:
        return self.output_dir / "xout_lines1.fits"

    @property
    def rrc(self) -> Path:
        return self.output_dir / "xout_rrc1.fits"

    @property
    def continuum(self) -> Path:
        return self.output_dir / "xout_cont1.fits"

    @property
    def spectrum(self) -> Path:
        return self.output_dir / "xout_spect1.fits"

    @property
    def detail(self) -> Path:
        return self.output_dir / "xo01_detail.fits"

    @property
    def detail_lines(self) -> Path:
        return self.output_dir / "xo01_detal2.fits"

    @property
    def detail_rates(self) -> Path:
        return self.output_dir / "xo01_detal3.fits"

    @property
    def detail_continuum(self) -> Path:
        return self.output_dir / "xo01_detal4.fits"

    @property
    def step_log(self) -> Path:
        return self.output_dir / "xout_step.log"

    @property
    def expected_fits(self) -> tuple[Path, ...]:
        return tuple(self.output_dir / name for name in _FITS_NAMES)

    @property
    def produced_fits(self) -> tuple[Path, ...]:
        return tuple(path for path in self.expected_fits if path.is_file())

    def as_dict(self) -> dict[str, str]:
        return {
            "abundances": str(self.abundances),
            "lines": str(self.lines),
            "rrc": str(self.rrc),
            "continuum": str(self.continuum),
            "spectrum": str(self.spectrum),
            "detail": str(self.detail),
            "detail_lines": str(self.detail_lines),
            "detail_rates": str(self.detail_rates),
            "detail_continuum": str(self.detail_continuum),
            "step_log": str(self.step_log),
        }


@dataclass(frozen=True)
class XStarResult:
    """Stable public result returned by :func:`xstar_tools.run_xstar`."""
    success: bool
    status: str
    return_code: int
    output_dir: Path
    products: XStarProducts
    step_log: Path
    runtime_seconds: float
    timings: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    raw_summary: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def produced_fits(self) -> tuple[Path, ...]:
        return self.products.produced_fits

    @property
    def ready(self) -> bool:
        """Compatibility alias for the Milestone-3 ``PublicRunResult.ready``."""
        return self.success

    @property
    def mode(self) -> str | None:
        execution = dict(self.provenance).get("execution", {}) if isinstance(self.provenance, Mapping) else {}
        return execution.get("actual_mode") if isinstance(execution, Mapping) else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "return_code": self.return_code,
            "output_dir": str(self.output_dir),
            "products": self.products.as_dict(),
            "produced_fits": [str(p) for p in self.produced_fits],
            "step_log": str(self.step_log),
            "runtime_seconds": self.runtime_seconds,
            "timings": dict(self.timings),
            "provenance": dict(self.provenance),
            "diagnostics": list(self.diagnostics),
            "warnings": list(self.warnings),
        }


__all__ = ["XStarProducts", "XStarResult"]
