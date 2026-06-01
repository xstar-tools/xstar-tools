"""Public same-run XSTAR validation workflow namespace."""
from __future__ import annotations

from typing import Any

from .context import context_from_xstar_run
from .workflow import calc_triplet
from .benchmark import reproduce_xstar_run, build_xstar_local_target, run_xstar_benchmark_suite


def compare_xstar_run(run_dir, *, ion=None, wavelength=None, value_column="emit_outward", **kwargs: Any) -> dict:
    """Build a lightweight context and triplet comparison from an XSTAR run.

    This helper summarizes same-run triplet rows from ``xout_lines1`` when
    available.  For benchmark-grade local-state and line-target extraction use
    :func:`reproduce_xstar_run`, which records both ``xout_abund1`` and
    ``xout_lines1`` values.
    """
    ctx = context_from_xstar_run(run_dir, ion=ion, **kwargs)
    triplet = calc_triplet(ion=ion, context=ctx, wavelength=wavelength, value_column=value_column)
    return {"context": ctx.to_dict(), "triplet": triplet.to_dict(), "lines": list(triplet.lines)}


__all__ = ["compare_xstar_run", "reproduce_xstar_run", "build_xstar_local_target", "run_xstar_benchmark_suite"]
