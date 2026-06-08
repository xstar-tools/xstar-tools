"""Helpers for locating and invoking the bundled standalone native driver."""
from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Iterable


def native_directory() -> Path:
    """Return the retained native source/library directory."""
    return Path(__file__).resolve().parent / "cpp"


def executable_path() -> Path:
    """Return the bundled ``xstar_cpp`` path."""
    return native_directory() / "xstar_cpp"


def run_standalone(
    arguments: Iterable[str],
    *,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run the bundled standalone driver with string arguments."""
    executable = executable_path()
    if not executable.exists():
        raise FileNotFoundError(
            f"xstar_cpp has not been built in {native_directory()}; run make there"
        )
    command = [str(executable), *(str(value) for value in arguments)]
    return subprocess.run(
        command,
        check=check,
        text=True,
        capture_output=capture_output,
    )
