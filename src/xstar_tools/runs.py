"""Public helpers for XSTAR run directories."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .context import context_from_xstar_run
from .benchmark import find_xstar_run_files, build_xstar_local_target, run_xstar_benchmark_suite


def select_local_state(run_dir, *, ion=None, **kwargs):
    """Return a lightweight local context selected from ``xout_abund1.fits``."""
    return context_from_xstar_run(run_dir, ion=ion, **kwargs)


def select_local_states(cases: Sequence[Mapping[str, Any]] | None = None, *, xstar_runs_root: str | Path | None = None, ions: Sequence[str] | None = None, **kwargs):
    """Select local XSTAR contexts for a small list of run directories.

    This is the first source-module migration of example 51.  Pass explicit
    ``cases`` with ``run_dir`` and ``ion`` columns for deterministic benchmark
    work.  Automatic tree discovery remains in the full example script.
    """
    if cases is None:
        if xstar_runs_root is None or ions is None:
            raise NotImplementedError(
                "select_local_states currently requires explicit cases=[{'ion': ..., 'run_dir': ...}, ...]. "
                "Use examples/51_run_helike_local_state_validation.py for broad xstar_runs tree discovery."
            )
        root = Path(xstar_runs_root)
        cases = []
        for ion in ions:
            # Deterministic conservative discovery: include directories that
            # already contain both XSTAR local-state and line files.
            for path in sorted(root.rglob("xout_abund1.fits")):
                run_dir = path.parent
                files = find_xstar_run_files(run_dir)
                if files["xout_lines"] is not None:
                    cases.append({"ion": ion, "run_dir": str(run_dir)})
    return [select_local_state(c.get("run_dir"), ion=c.get("ion"), **kwargs) for c in cases]


__all__ = [
    "context_from_xstar_run",
    "select_local_state",
    "select_local_states",
    "find_xstar_run_files",
    "build_xstar_local_target",
    "run_xstar_benchmark_suite",
]
