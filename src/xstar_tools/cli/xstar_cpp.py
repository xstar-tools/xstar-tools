"""Installed-wheel launcher for the packaged native ``xstar-cpp`` executable."""
from __future__ import annotations

import os
import sys


def main() -> int:
    from xstar_tools.execution import native_executable_path

    executable = native_executable_path()
    if executable is None:
        print(
            "xstar-cpp native runtime is not installed for this environment. "
            "On Linux, reinstall with native build prerequisites available; "
            "Python-only installations can use 'xstar-tools run --mode pure-python'.",
            file=sys.stderr,
        )
        return 69
    os.execv(str(executable), [str(executable), *sys.argv[1:]])
    return 70  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
