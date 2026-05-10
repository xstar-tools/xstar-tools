"""Public same-run XSTAR validation workflow namespace."""
from __future__ import annotations

from typing import Any

from .context import context_from_xstar_run
from .workflow import calc_triplet


def compare_xstar_run(run_dir, *, ion=None, wavelength=None, value_column="emit_outward", **kwargs: Any) -> dict:
    """Build a lightweight context and triplet comparison from an XSTAR run.

    This v0.3.131 helper summarizes same-run triplet rows from ``xout_lines1``
    when available.  More detailed population/matrix comparison workflows still
    live in the validation examples and will be migrated in later releases.
    """
    ctx = context_from_xstar_run(run_dir, ion=ion, **kwargs)
    triplet = calc_triplet(ion=ion, context=ctx, wavelength=wavelength, value_column=value_column)
    return {"context": ctx.to_dict(), "triplet": triplet.to_dict(), "lines": list(triplet.lines)}


__all__ = ["compare_xstar_run"]
