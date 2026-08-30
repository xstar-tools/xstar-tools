"""Native ``xstinitable`` grid-planning entry points for xstar_tools 0.6.83.2.

The grid semantics live in the C++17 ``xstar-xspec-initable`` executable.
This Python layer only locates and launches that native planner.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


def _native_xstinitable_executable(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise FileNotFoundError(f"native xstinitable executable is not runnable: {path}")

    env = os.environ.get("XSTAR_XSPEC_INITABLE_BIN")
    if env:
        path = Path(env).expanduser().resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path

    found = shutil.which("xstar-xspec-initable")
    if found:
        return Path(found).resolve()

    source_candidate = Path(__file__).resolve().parents[1] / "xstar" / "cpp" / "xstar-xspec-initable"
    if source_candidate.is_file() and os.access(source_candidate, os.X_OK):
        return source_candidate

    raise FileNotFoundError(
        "xstar-xspec-initable is not available; build it with "
        "`make -C src/xstar_tools/xstar/cpp xstar-xspec-initable` or set "
        "XSTAR_XSPEC_INITABLE_BIN"
    )


def build_xstinitable(
    parameters: Iterable[str] = (),
    output_dir: str | os.PathLike[str] = ".",
    *,
    input_file: str | os.PathLike[str] | None = None,
    xstar: str = "cpp",
    data_dir: str | os.PathLike[str] | None = None,
    native_executable: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Create ``xstinitable.lis`` and ``xstinitable.fits``.

    ``xstar='cpp'`` is the default production contract and emits ``xstar-cpp``
    commands. ``xstar='fortran'`` preserves the canonical historical
    ``xstar key=value`` command contract.  A HEASoft/IRAF-style
    ``xstinitable.par`` may be supplied via ``input_file`` and trailing
    ``parameters`` override values loaded from that file.
    """

    if xstar not in {"cpp", "fortran"}:
        raise ValueError("xstar must be 'cpp' or 'fortran'")

    exe = _native_xstinitable_executable(native_executable)
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    args = [str(value) for value in parameters]
    if input_file is None and not args:
        raise ValueError("provide input_file or at least one xstinitable key=value parameter")

    command = [str(exe), "--xstar", xstar, "--output-dir", str(out)]
    if input_file is not None:
        command += ["--input", str(Path(input_file).expanduser())]
    if data_dir is not None:
        command += ["--data-dir", str(Path(data_dir).expanduser())]
    command += args
    return subprocess.run(command, text=True, capture_output=True, check=True)
