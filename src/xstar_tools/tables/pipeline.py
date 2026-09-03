"""Native serial/parallel XSTAR2XSPEC orchestration for xstar_tools 0.6.88.2."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable

from xstar_tools.native_runtime import packaged_native_executable_path, native_executable_is_runnable


def _native_xstar2xspec_executable(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if native_executable_is_runnable(path):
            return path
        raise FileNotFoundError(f"native xstar-xspec executable is not runnable: {path}")
    path = packaged_native_executable_path(
        "xstar-xspec", env_var="XSTAR_XSPEC_BIN", include_path=True
    )
    if path is not None:
        return path
    raise FileNotFoundError(
        "xstar-xspec is not available; install a native wheel, build it with "
        "`make -C src/xstar_tools/xstar/cpp xstar-xspec`, or set XSTAR_XSPEC_BIN"
    )


def run_xstar2xspec(
    parameters: Iterable[str] = (),
    output_dir: str | os.PathLike[str] = ".",
    *,
    input_file: str | os.PathLike[str] | None = None,
    data_dir: str | os.PathLike[str] | None = None,
    processes: int = 1,
    workers: int | None = None,
    save: bool = False,
    restart: bool = False,
    verbose: bool = False,
    native_executable: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the complete native XSTAR2XSPEC pipeline with bounded process parallelism."""
    args = [str(value) for value in parameters]
    if input_file is None and not args:
        raise ValueError("provide input_file or at least one xstinitable key=value parameter")
    exe = _native_xstar2xspec_executable(native_executable)
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    if workers is not None:
        if processes != 1 and processes != workers:
            raise ValueError("processes and legacy workers aliases disagree")
        processes = workers
    if processes < 1:
        raise ValueError("processes must be >= 1")
    command = [str(exe), "--output-dir", str(out), "--processes", str(processes)]
    if input_file is not None:
        command += ["--input", str(Path(input_file).expanduser())]
    if data_dir is not None:
        command += ["--data-dir", str(Path(data_dir).expanduser())]
    if save:
        command.append("--save")
    if restart:
        command.append("--restart")
    if verbose:
        command.append("--verbose")
    command += args
    return subprocess.run(command, text=True, capture_output=not verbose, check=True)
