"""Public helpers for XSTAR run directories."""
from __future__ import annotations

from .context import context_from_xstar_run


def select_local_state(run_dir, *, ion=None, **kwargs):
    """Return a lightweight local context selected from ``xout_abund1.fits``."""
    return context_from_xstar_run(run_dir, ion=ion, **kwargs)


def select_local_states(*args, **kwargs):
    """Placeholder for the future source-module version of example 51."""
    raise NotImplementedError(
        "Batch local-state discovery is still implemented as examples/51_run_helike_local_state_validation.py; "
        "use select_local_state(...) for a single XSTAR run directory in v0.3.132."
    )


__all__ = ["context_from_xstar_run", "select_local_state", "select_local_states"]
