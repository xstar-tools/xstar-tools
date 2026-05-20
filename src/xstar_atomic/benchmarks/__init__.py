"""Bundled immutable validation benchmarks for the source-faithful XSTAR port."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def oxygen_milestone3_v0422_path() -> Path:
    """Return the bundled frozen oxygen Milestone-3 benchmark directory."""
    return Path(str(files(__package__).joinpath("oxygen_milestone3_v0422")))


def oxygen_call73_v0434_acceptance_path() -> Path:
    """Return the bundled accepted oxygen call-73 regression directory."""
    return Path(str(files(__package__).joinpath("oxygen_call73_v0434_acceptance")))


def hydrogen_v0436_targets_path() -> Path:
    """Return the bounded H I v0.4.36 correction-target inventory."""
    return Path(str(files(__package__).joinpath("hydrogen_v0436_targets")))


__all__ = ["oxygen_milestone3_v0422_path", "oxygen_call73_v0434_acceptance_path", "hydrogen_v0436_targets_path"]
