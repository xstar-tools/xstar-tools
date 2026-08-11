"""Native XSTAR2XSPEC table-conversion entry points.

0.6.81 intentionally keeps the scientific conversion in C++/CFITSIO.  This
module is a thin orchestration layer for source checkouts or native installs.
"""

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
        "xstar-xspec-table is not available; build the native C++ target with "
        "`make -C src/xstar_tools/xstar/cpp xstar-xspec-table` or set XSTAR_XSPEC_TABLE_BIN"
    )


def build_xspec_tables(
    metadata: str | os.PathLike[str],
    spectra: Iterable[str | os.PathLike[str]],
    output_dir: str | os.PathLike[str],
    *,
    native_executable: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Build the four 0.6.81 canonical-compatible XSPEC table products.

    ``spectra`` must be ordinary XSTAR ``xout_spect1.fits`` files ordered by
    their historical ``loopcontrol`` value.  The metadata file describes the
    XSTINITABLE parameter surface; 0.6.83 will replace this characterization
    metadata format with the full native grid planner.
    """

    exe = _native_xstar2table_executable(native_executable)
    metadata_path = Path(metadata).expanduser().resolve()
    out = Path(output_dir).expanduser().resolve()
    source_paths = [Path(path).expanduser().resolve() for path in spectra]
    if not metadata_path.is_file():
        raise FileNotFoundError(metadata_path)
    if not source_paths:
        raise ValueError("at least one xout_spect1.fits path is required")
    missing = [str(path) for path in source_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing spectrum inputs: " + ", ".join(missing))
    out.mkdir(parents=True, exist_ok=True)
    command = [str(exe), "--metadata", str(metadata_path), "--output-dir", str(out), *(str(path) for path in source_paths)]
    return subprocess.run(command, text=True, capture_output=True, check=True)
