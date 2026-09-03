"""Native ``xstinitable`` grid-planning entry points for xstar_tools 0.6.84.

The grid semantics live in the C++17 ``xstar-xspec-initable`` executable.
This Python layer only locates and launches that native planner.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable

from xstar_tools.native_runtime import packaged_native_executable_path, native_executable_is_runnable


def _native_xstinitable_executable(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if native_executable_is_runnable(path):
            return path
        raise FileNotFoundError(f"native xstinitable executable is not runnable: {path}")
    path = packaged_native_executable_path(
        "xstar-xspec-initable", env_var="XSTAR_XSPEC_INITABLE_BIN", include_path=True
    )
    if path is not None:
        return path
    raise FileNotFoundError(
        "xstar-xspec-initable is not available; install a native wheel, build it with "
        "`make -C src/xstar_tools/xstar/cpp xstar-xspec-initable`, or set "
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
