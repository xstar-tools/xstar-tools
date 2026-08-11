"""Schemas for the 0.6.81 XSTAR2XSPEC characterization metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class XSpecTableProducts:
    """Paths of the four table products written by native xstar2table."""

    ain: Path
    aout: Path
    mtable: Path
    etable: Path

    @classmethod
    def from_directory(cls, directory: str | Path) -> "XSpecTableProducts":
        root = Path(directory)
        return cls(
            ain=root / "xout_ain.fits",
            aout=root / "xout_aout.fits",
            mtable=root / "xout_mtable.fits",
            etable=root / "xout_etable.fits",
        )
