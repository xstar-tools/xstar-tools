"""Platform-neutral discovery for packaged xstar-tools native runtime artifacts.

The native libraries and executables are built by the retained qualified
``src/xstar_tools/xstar/cpp/Makefile`` and staged beside the Python package.
This module owns filename/platform discovery only; it does not choose scientific
backends or alter atomic-data discovery.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
from typing import Iterable

_WINDOWS_DLL_DIRECTORY_HANDLES: list[object] = []
_WINDOWS_DLL_DIRECTORIES: set[str] = set()


def native_platform_key(system: str | None = None) -> str:
    """Return the Makefile platform key for the running Python interpreter."""
    value = system or platform.system()
    mapping = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}
    try:
        return mapping[value]
    except KeyError as exc:
        raise RuntimeError(
            f"unsupported native platform {value!r}; expected Linux, Darwin, or Windows"
        ) from exc


def native_shared_library_suffix(system: str | None = None) -> str:
    """Return the native shared-library suffix used by the retained Makefile."""
    return {"linux": ".so", "macos": ".dylib", "windows": ".dll"}[
        native_platform_key(system)
    ]


def native_executable_suffix(system: str | None = None) -> str:
    """Return the native executable suffix used by the retained Makefile."""
    return ".exe" if native_platform_key(system) == "windows" else ""


def native_cpp_dir() -> Path:
    """Return the installed/source-tree directory containing native artifacts."""
    return Path(__file__).resolve().parent / "xstar" / "cpp"


def native_library_filename(stem: str, *, system: str | None = None) -> str:
    """Return the canonical native filename for ``stem`` (for example xstar_api)."""
    value = stem.removeprefix("lib")
    return f"lib{value}{native_shared_library_suffix(system)}"


def native_executable_filename(name: str, *, system: str | None = None) -> str:
    """Return the canonical native executable filename for ``name``."""
    suffix = native_executable_suffix(system)
    if suffix and name.lower().endswith(suffix):
        return name
    return f"{name}{suffix}"


def _deduplicate(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def native_library_candidates(
    stem: str,
    *,
    env_var: str | None = None,
    compatibility_names: Iterable[str] = (),
) -> list[Path]:
    """Return override-first candidate paths for one packaged shared library.

    ``compatibility_names`` is retained for older source-tree/library spellings;
    the canonical current-platform filename is always tried first.
    """
    paths: list[Path] = []
    if env_var:
        override = os.environ.get(env_var, "").strip()
        if override:
            paths.append(Path(override).expanduser())
    cpp = native_cpp_dir()
    paths.append(cpp / native_library_filename(stem))
    paths.extend(cpp / name for name in compatibility_names)
    return _deduplicate(paths)


def packaged_native_library_path(stem: str, *, env_var: str | None = None) -> Path:
    """Return the first existing library candidate, or the canonical candidate."""
    candidates = native_library_candidates(stem, env_var=env_var)
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return candidates[0].resolve() if candidates[0].is_absolute() else candidates[0]


def prepare_native_library_search(path: Path | None = None) -> None:
    """Make sibling dependent DLLs discoverable on Windows Python 3.8+.

    Windows no longer searches arbitrary DLL directories for ``ctypes`` loads.
    Retain each ``os.add_dll_directory`` handle for process lifetime so packaged
    ``libxstar_*.dll`` dependencies remain resolvable. Non-Windows hosts are a
    no-op because ELF/Mach-O sibling lookup is encoded by the qualified linker
    contract.
    """
    if native_platform_key() != "windows" or not hasattr(os, "add_dll_directory"):
        return
    directory = (path.parent if path is not None else native_cpp_dir()).resolve()
    key = str(directory)
    if key in _WINDOWS_DLL_DIRECTORIES or not directory.is_dir():
        return
    handle = os.add_dll_directory(key)
    _WINDOWS_DLL_DIRECTORY_HANDLES.append(handle)
    _WINDOWS_DLL_DIRECTORIES.add(key)


def native_executable_candidates(
    name: str,
    *,
    env_var: str | None = None,
    compatibility_names: Iterable[str] = (),
    include_path: bool = True,
) -> list[Path]:
    """Return packaged-first candidates for one native executable.

    Package-local candidates precede ``PATH`` so console-script wrappers with
    the same public name never recursively rediscover themselves.
    """
    paths: list[Path] = []
    if env_var:
        override = os.environ.get(env_var, "").strip()
        if override:
            paths.append(Path(override).expanduser())
    cpp = native_cpp_dir()
    canonical = native_executable_filename(name)
    paths.append(cpp / canonical)
    paths.extend(cpp / native_executable_filename(value) for value in compatibility_names)
    if include_path:
        found = shutil.which(canonical) or (shutil.which(name) if canonical != name else None)
        if found:
            paths.append(Path(found))
    return _deduplicate(paths)


def native_executable_is_runnable(path: Path) -> bool:
    """Return whether a native executable candidate is runnable on this host."""
    if not path.is_file():
        return False
    return native_platform_key() == "windows" or os.access(path, os.X_OK)


def packaged_native_executable_path(
    name: str,
    *,
    env_var: str | None = None,
    compatibility_names: Iterable[str] = (),
    include_path: bool = True,
) -> Path | None:
    """Resolve an executable from an override, the package, then optionally PATH."""
    for path in native_executable_candidates(
        name,
        env_var=env_var,
        compatibility_names=compatibility_names,
        include_path=include_path,
    ):
        if native_executable_is_runnable(path):
            return path.resolve()
    return None
