#!/usr/bin/env python3
"""Run the public physical Python XSTAR API and optional parity gate.

This wrapper applies --blas-threads before importing xstar_atomic so NumPy/BLAS
thread pools are capped early enough for memory-safe Mg/Ca benchmark runs.
"""
from __future__ import annotations

import os
import sys


def _prelimit_threads(argv: list[str]) -> None:
    value: str | None = None
    for index, item in enumerate(argv):
        if item == "--blas-threads" and index + 1 < len(argv):
            value = argv[index + 1]
            break
        if item.startswith("--blas-threads="):
            value = item.split("=", 1)[1]
            break
    if value is None:
        return
    try:
        threads = max(1, int(value))
    except ValueError:
        return
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        os.environ[name] = str(threads)
    os.environ.setdefault("MALLOC_ARENA_MAX", "2")


_prelimit_threads(sys.argv[1:])

from xstar_atomic.source_port_physical_runner_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
