"""Serial native XSTAR2XSPEC orchestration for xstar_tools 0.6.84."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


def _native_xstar2xspec_executable(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise FileNotFoundError(f"native xstar-xspec executable is not runnable: {path}")
    env = os.environ.get("XSTAR_XSPEC_BIN")
    if env:
        path = Path(env).expanduser().resolve()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    found = shutil.which("xstar-xspec")
    if found:
        return Path(found).resolve()
    source = Path(__file__).resolve().parents[1] / "xstar" / "cpp" / "xstar-xspec"
    if source.is_file() and os.access(source, os.X_OK):
        return source
    raise FileNotFoundError(
        "xstar-xspec is not available; build it with "
        "`make -C src/xstar_tools/xstar/cpp xstar-xspec` or set XSTAR_XSPEC_BIN"
    )


def run_xstar2xspec(
    parameters: Iterable[str] = (),
    output_dir: str | os.PathLike[str] = ".",
    *,
    input_file: str | os.PathLike[str] | None = None,
    data_dir: str | os.PathLike[str] | None = None,
    save: bool = False,
    restart: bool = False,
    verbose: bool = False,
    native_executable: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the complete serial native XSTAR2XSPEC pipeline."""
    args = [str(value) for value in parameters]
    if input_file is None and not args:
        raise ValueError("provide input_file or at least one xstinitable key=value parameter")
    exe = _native_xstar2xspec_executable(native_executable)
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    command = [str(exe), "--output-dir", str(out)]
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
