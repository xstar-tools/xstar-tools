"""Console-script launchers for packaged native XSTAR/XSTAR2XSPEC programs."""
from __future__ import annotations

import subprocess
import sys

from xstar_tools.native_runtime import native_subprocess_environment, packaged_native_executable_path


def _run(name: str, env_var: str, *, compatibility_names: tuple[str, ...] = ()) -> int:
    executable = packaged_native_executable_path(
        name,
        env_var=env_var,
        compatibility_names=compatibility_names,
        include_path=False,
    )
    if executable is None:
        raise SystemExit(
            f"{name} native runtime is not installed for this environment. "
            "Install a native xstar-tools wheel or build the retained C++ Makefile targets."
        )
    return subprocess.run([str(executable), *sys.argv[1:]], check=False, env=native_subprocess_environment()).returncode


def main_xstar_xspec_initable() -> int:
    return _run("xstar-xspec-initable", "XSTAR_XSPEC_INITABLE_BIN")


def main_xstar_xspec_table() -> int:
    return _run("xstar-xspec-table", "XSTAR_XSPEC_TABLE_BIN")


def main_xstar_xspec() -> int:
    return _run("xstar-xspec", "XSTAR_XSPEC_BIN")
