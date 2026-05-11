#!/usr/bin/env python3
"""Plan how to recreate standard XSTAR FITS outputs from an XSTAR command.

This example is intentionally a planning/audit step, not a full replacement for
XSTAR.  It parses a shell-style ``xstar`` command or ``run_xstar.sh`` file and
writes a source-code-parity checklist for recreating:

``xo01_detail.fits``, ``xo01_detal2.fits``, ``xo01_detal3.fits``,
``xo01_detal4.fits``, ``xout_abund1.fits``, ``xout_lines1.fits``,
``xout_rrc1.fits``, ``xout_cont1.fits``, and ``xout_spect1.fits``.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    here = Path(__file__).resolve()
    root = here.parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


_bootstrap_src_path()

from xstar_atomic.xstar_run import main


if __name__ == "__main__":
    raise SystemExit(main())
