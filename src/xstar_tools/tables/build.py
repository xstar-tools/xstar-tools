"""Native XSTAR2XSPEC table-conversion entry points."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


def _native_xstar2table_executable(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise FileNotFoundError(f"native xstar2table executable is not runnable: {path}")
    env = os.environ.get("XSTAR_XSPEC_TABLE_BIN")
    if env:
        path = Path(env).expanduser().resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    found = shutil.which("xstar-xspec-table")
    if found:
        return Path(found).resolve()
    source_candidate = Path(__file__).resolve().parents[1] / "xstar" / "cpp" / "xstar-xspec-table"
    if source_candidate.is_file() and os.access(source_candidate, os.X_OK):
        return source_candidate
    raise FileNotFoundError(
        "xstar-xspec-table is not available; build it with "
        "`make -C src/xstar_tools/xstar/cpp xstar-xspec-table` or set XSTAR_XSPEC_TABLE_BIN"
    )


def build_xspec_tables(
    config: str | os.PathLike[str],
    spectra: Iterable[str | os.PathLike[str]],
    output_dir: str | os.PathLike[str],
    *,
    initable: bool = False,
    native_executable: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Build the four canonical-compatible XSPEC table products.

    By default ``config`` is the historical 0.6.81 metadata text format.
    With ``initable=True``, ``config`` is the native/canonical
    ``xstinitable.fits`` contract used by the 0.6.84 production pipeline.
    """
    exe = _native_xstar2table_executable(native_executable)
    config_path = Path(config).expanduser().resolve()
    out = Path(output_dir).expanduser().resolve()
    source_paths = [Path(path).expanduser().resolve() for path in spectra]
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    if not source_paths:
        raise ValueError("at least one xout_spect1.fits path is required")
    missing = [str(path) for path in source_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing spectrum inputs: " + ", ".join(missing))
    out.mkdir(parents=True, exist_ok=True)
    flag = "--initable" if initable else "--metadata"
    command = [str(exe), flag, str(config_path), "--output-dir", str(out), *(str(path) for path in source_paths)]
    return subprocess.run(command, text=True, capture_output=True, check=True)
