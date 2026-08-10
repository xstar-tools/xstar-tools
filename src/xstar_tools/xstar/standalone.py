"""Helpers for locating and invoking the bundled standalone native driver."""
from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Iterable


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the native directory operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Implementation helper around the source-faithful XSTAR model; no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
def native_directory() -> Path:
    """Return the retained native source/library directory."""
    return Path(__file__).resolve().parent / "cpp"


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the executable path operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Implementation helper around the source-faithful XSTAR model; no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
def executable_path() -> Path:
    """Return the bundled ``xstar_cpp`` path."""
    return native_directory() / "xstar_cpp"


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Execute standalone for this module while preserving the surrounding source/runtime invariants.
# Reference context: Implementation helper around the source-faithful XSTAR model; no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
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
