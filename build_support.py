"""Setuptools build support for xstar-tools native runtime artifacts.

Project metadata lives in pyproject.toml. This module contains only the custom
build hook required to compile the retained, scientifically-qualified Makefile
implementation into an installed wheel without modifying the source checkout.

0.6.89 makes the staging contract platform-neutral across the accepted native
hosts (Linux, macOS, and Windows/MSYS2 UCRT64). Ordinary wheels deliberately
exclude the opt-in MPI executable and continue to leave ``atdb.fits`` external.
0.6.89.3 adds a PyPI macOS profile matching the accepted Linux packaging
boundary. 0.6.89.4 extends that release boundary to Windows: publishable
``win_amd64`` wheels build the accepted MinGW/UCRT64 runtime while omitting the
standalone Python-embedding plugin and leaving MPI/``atdb.fits`` external.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

from setuptools import Distribution
from setuptools.command.build_py import build_py as _build_py

_NATIVE_LIBRARY_STEMS = (
    "xstar_solver",
    "xstar_rates",
    "xstar_matrix",
    "xstar_emissivity",
    "xstar_opacity",
    "xstar_thermal",
    "xstar_engine",
    "xstar_local_zone",
    "xstar_final_recompute",
    "xstar_production_zone",
    "xstar_xspec_table",
    "xstar_api",
    "xstar_backend_cpp",
    "xstar_backend_python",
)
_NATIVE_EXECUTABLE_STEMS = (
    "xstar_cpp",
    "xstar-cpp",
    "xstar-xspec-initable",
    "xstar-xspec-table",
    "xstar-xspec",
)
_SUPPORTED_NATIVE_SYSTEMS = {"Linux", "Darwin", "Windows"}
_PLATFORM_KEYS = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}
_LIBRARY_SUFFIXES = {"Linux": ".so", "Darwin": ".dylib", "Windows": ".dll"}
_EXECUTABLE_SUFFIXES = {"Linux": "", "Darwin": "", "Windows": ".exe"}
_GENERATED_SUFFIXES = {".o", ".so", ".dylib", ".dll", ".a", ".exe", ".pyc"}


def _native_policy() -> str:
    value = os.environ.get("XSTAR_TOOLS_NATIVE", "auto").strip().lower()
    aliases = {
        "0": "off",
        "false": "off",
        "no": "off",
        "1": "required",
        "true": "required",
        "yes": "required",
    }
    value = aliases.get(value, value)
    if value not in {"auto", "required", "off"}:
        raise RuntimeError("XSTAR_TOOLS_NATIVE must be one of auto, required, or off")
    return value


def _native_system() -> str:
    return platform.system()


def _native_platform_key(system: str | None = None) -> str:
    value = system or _native_system()
    try:
        return _PLATFORM_KEYS[value]
    except KeyError as exc:
        raise RuntimeError(
            f"unsupported native platform {value!r}; expected Linux, Darwin, or Windows"
        ) from exc


def _native_profile() -> str:
    value = os.environ.get("XSTAR_TOOLS_NATIVE_PROFILE", "full").strip().lower()
    valid = {"full", "pypi-linux", "pypi-macos", "pypi-windows"}
    if value not in valid:
        raise RuntimeError(
            "XSTAR_TOOLS_NATIVE_PROFILE must be one of full, pypi-linux, pypi-macos, or pypi-windows"
        )
    required_system = {"pypi-linux": "Linux", "pypi-macos": "Darwin", "pypi-windows": "Windows"}.get(value)
    if required_system is not None and _native_system() != required_system:
        raise RuntimeError(
            f"XSTAR_TOOLS_NATIVE_PROFILE={value} requires {required_system}"
        )
    return value


def _native_artifacts(
    system: str | None = None, *, profile: str = "full"
) -> tuple[str, ...]:
    value = system or _native_system()
    if value not in _SUPPORTED_NATIVE_SYSTEMS:
        raise RuntimeError(
            f"unsupported native platform {value!r}; expected Linux, Darwin, or Windows"
        )
    valid_profiles = {"full", "pypi-linux", "pypi-macos", "pypi-windows"}
    if profile not in valid_profiles:
        raise RuntimeError(f"unsupported native artifact profile {profile!r}")
    required_system = {"pypi-linux": "Linux", "pypi-macos": "Darwin", "pypi-windows": "Windows"}.get(profile)
    if required_system is not None and value != required_system:
        raise RuntimeError(
            f"{profile} native artifact profile requires {required_system}"
        )
    lib_suffix = _LIBRARY_SUFFIXES[value]
    library_stems = _NATIVE_LIBRARY_STEMS
    if profile in {"pypi-linux", "pypi-macos", "pypi-windows"}:
        # Release wheels must not rely on or vendor a Python runtime library.
        # The standalone Python-embedding plugin links libpython by design, so
        # PyPI binary profiles omit only that optional plugin.  The ordinary
        # source/native profile remains unchanged and still stages it.
        library_stems = tuple(
            stem for stem in library_stems if stem != "xstar_backend_python"
        )
    exe_suffix = _EXECUTABLE_SUFFIXES[value]
    libraries = tuple(f"lib{stem}{lib_suffix}" for stem in library_stems)
    executables = tuple(f"{stem}{exe_suffix}" for stem in _NATIVE_EXECUTABLE_STEMS)
    return libraries + executables


def _native_make_target(profile: str) -> str:
    """Return the Makefile target for the requested native packaging profile."""
    if profile == "full":
        return "all"
    if profile == "pypi-linux":
        # The manylinux wheel deliberately omits the standalone Python-embedding
        # plugin.  Build the matching Makefile target so libpython is never a
        # build-time dependency of the PyPI Linux profile.
        return "pypi-linux"
    if profile == "pypi-macos":
        # The macOS release wheels use the same public runtime boundary: omit
        # the standalone Python-embedding plugin at build time so the repaired
        # wheel cannot acquire a Python-framework/libpython dependency.
        return "pypi-macos"
    if profile == "pypi-windows":
        # Windows release wheels likewise omit the standalone embedding plugin.
        # The remaining DLL/executable runtime is Python-version-independent
        # and is repaired with delvewheel for ordinary win_amd64 CPython.
        return "pypi-windows"
    raise RuntimeError(f"unsupported native build profile {profile!r}")


def _native_requested() -> bool:
    policy = _native_policy()
    if policy == "off":
        return False
    system = _native_system()
    if system in _SUPPORTED_NATIVE_SYSTEMS:
        return True
    if policy == "required":
        raise RuntimeError(
            f"native build requested on unsupported platform {system!r}; "
            "the current native wheel contract supports Linux, macOS, and Windows"
        )
    return False


def _tool(name: str, env_name: str | None = None) -> str | None:
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return shutil.which(name)


def _python_config_sibling(executable: str | None = None) -> str | None:
    """Find an extensionless Python config helper beside the active interpreter.

    MSYS2/UCRT64 installs ``python3-config`` and ``python-config`` as shell
    scripts without a Windows executable suffix.  Native Windows
    ``shutil.which`` can therefore miss them even though the MSYS2 shell used
    by GNU Make can execute them.  Prefer normal PATH discovery, but retain
    this same-interpreter sibling fallback for that boundary.
    """
    bindir = Path(executable or sys.executable).resolve().parent
    for name in ("python3-config", "python-config"):
        candidate = bindir / name
        if candidate.is_file():
            return candidate.as_posix()
    return None


def _python_config_tool() -> str | None:
    configured = os.environ.get("PYTHON_CONFIG")
    if configured:
        return configured
    return (
        shutil.which("python3-config")
        or shutil.which("python-config")
        or _python_config_sibling()
    )


def _require_native_prerequisites(profile: str = "full") -> dict[str, str]:
    system = _native_system()
    preferred_cxx = "clang++" if system == "Darwin" else "c++"
    # Publishable Windows wheels deliberately do not build the standalone
    # Python-embedding plugin, so official python.org CPython need not provide
    # an MSYS2-style python-config helper.  Retain the historical requirement
    # for every other profile.
    python_config = None if profile == "pypi-windows" else _python_config_tool()
    tools = {
        "make": _tool("make", "MAKE"),
        "cxx": _tool(preferred_cxx, "CXX") or _tool("g++", "CXX"),
        "python_config": python_config,
        "pkg_config": _tool("pkg-config", "PKG_CONFIG"),
    }
    required = ("make", "cxx", "pkg_config")
    if profile != "pypi-windows":
        required = (*required, "python_config")
    missing = [name for name in required if not tools[name]]
    if missing:
        raise RuntimeError(
            "native xstar-tools wheel build requires "
            + ", ".join(missing)
            + "; install build prerequisites or set XSTAR_TOOLS_NATIVE=off "
            "for a Python-only installation"
        )
    probe = subprocess.run([str(tools["pkg_config"]), "--exists", "cfitsio"], check=False)
    if probe.returncode != 0:
        raise RuntimeError(
            "native xstar-tools wheel build requires CFITSIO development metadata "
            "(pkg-config cfitsio); install the platform CFITSIO development package "
            "or set XSTAR_TOOLS_NATIVE=off"
        )
    return {k: ("" if v is None else str(v)) for k, v in tools.items()}


def _pkg_config_cfitsio_make_variables(pkg_config: str) -> tuple[str, str, str]:
    """Resolve CFITSIO metadata once for Make, avoiding shell re-discovery.

    This is required by the Windows PyPI path: ``pkg-config`` is validated and
    callable from the Python build backend, but a Win32 tool path injected into
    Make's ``$(shell ...)`` can be re-parsed by the MSYS2 shell and silently
    collapse to the historical ``-lcfitsio`` fallback.  Query the validated
    tool directly and pass the resulting flags as command-line Make variables.
    """

    def query(*args: str) -> str:
        proc = subprocess.run(
            [pkg_config, *args, "cfitsio"],
            check=True,
            text=True,
            capture_output=True,
        )
        return proc.stdout.strip().replace("\\", "/")

    cflags = query("--cflags")
    libdir = query("--variable=libdir")
    libs = query("--libs")
    if not libs:
        raise RuntimeError("pkg-config cfitsio returned an empty library link line")
    return cflags, libdir, libs


def _is_generated_build_product(path: Path) -> bool:
    if "__pycache__" in path.parts:
        return True
    if path.name.endswith(".dll.a"):
        return True
    if path.suffix in _GENERATED_SUFFIXES:
        return True
    return path.name in {
        *(_native_artifacts("Linux")),
        *(_native_artifacts("Darwin")),
        *(_native_artifacts("Windows")),
        "xstar-xspec-mpi",
        "xstar-xspec-mpi.exe",
    }


def _source_fingerprint(root: Path) -> str:
    h = hashlib.sha256()
    base = root / "src/xstar_tools/xstar/cpp"
    for path in sorted(p for p in base.rglob("*") if p.is_file()):
        if _is_generated_build_product(path):
            continue
        rel = path.relative_to(root).as_posix().encode()
        h.update(rel + b"\0" + path.read_bytes() + b"\0")
    h.update((root / "pyproject.toml").read_bytes())
    h.update((root / "build_support.py").read_bytes())
    return h.hexdigest()


def _prepare_stage(root: Path, stage: Path, *, clean: bool) -> Path:
    stage_cpp = stage / "src/xstar_tools/xstar/cpp"
    fingerprint = _source_fingerprint(root)
    marker = stage / ".xstar_tools_source_sha256"
    reuse = marker.is_file() and marker.read_text(encoding="utf-8").strip() == fingerprint
    if clean or not reuse:
        if stage.exists():
            shutil.rmtree(stage)
        stage_cpp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root / "src/xstar_tools/xstar/cpp", stage_cpp)
        # Never trust generated source-tree build products, even when a
        # persistent staging directory is requested.
        for candidate in stage_cpp.rglob("*"):
            if candidate.is_file() and _is_generated_build_product(candidate):
                candidate.unlink()
        marker.write_text(fingerprint + "\n", encoding="utf-8")
    return stage_cpp


class XStarBuildPy(_build_py):
    """Build package modules, then stage only installed native runtime artifacts."""

    def run(self) -> None:
        super().run()
        self._build_native_runtime()

    def _build_native_runtime(self) -> None:
        target_cpp = Path(self.build_lib) / "xstar_tools" / "xstar" / "cpp"
        target_cpp.mkdir(parents=True, exist_ok=True)
        policy = _native_policy()
        native = _native_requested()
        system = _native_system()
        profile = _native_profile()
        metadata: dict[str, object] = {
            "schema": "xstar-tools-native-build-v2",
            "package_version": self.distribution.metadata.version,
            "science_revision": "0.6.48.12.3.45.3.3.8",
            "c_api_abi": 60487,
            "production_zone_abi": 6048110,
            "policy": policy,
            "platform_system": system,
            "platform_machine": platform.machine(),
            "platform_key": _PLATFORM_KEYS.get(system),
            "native_profile": profile,
            "native_built": False,
            "artifacts": [],
            "mpi_included": False,
            "atomic_database_bundled": False,
        }
        if not native:
            metadata["reason"] = (
                "native build disabled"
                if policy == "off"
                else "native build not supported on this platform"
            )
            (target_cpp / "native_build.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return

        tools = _require_native_prerequisites(profile)
        root = Path(__file__).resolve().parent
        source_cpp = root / "src" / "xstar_tools" / "xstar" / "cpp"
        if not source_cpp.is_dir():
            raise RuntimeError("native C++ source tree missing from source distribution")

        artifacts = _native_artifacts(system, profile=profile)
        jobs_text = os.environ.get("XSTAR_TOOLS_NATIVE_JOBS", "2").strip()
        try:
            jobs = max(1, int(jobs_text))
        except ValueError as exc:
            raise RuntimeError("XSTAR_TOOLS_NATIVE_JOBS must be an integer") from exc

        persistent = os.environ.get("XSTAR_TOOLS_NATIVE_BUILD_DIR", "").strip()
        env = os.environ.copy()
        env["CXX"] = tools["cxx"]
        env["PYTHON_CONFIG"] = tools["python_config"] or "true"
        env["PKG_CONFIG"] = tools["pkg_config"]
        platform_key = _native_platform_key(system)
        cfitsio_make_args: list[str] = []
        if profile == "pypi-windows":
            cflags, libdir, libs = _pkg_config_cfitsio_make_variables(tools["pkg_config"])
            cfitsio_make_args = [
                f"CFITSIO_CFLAGS={cflags}",
                f"CFITSIO_LIBDIR={libdir}",
                f"CFITSIO_LIBS={libs}",
            ]
            print(f"XSTAR_TOOLS_CFITSIO_CFLAGS={cflags}")
            print(f"XSTAR_TOOLS_CFITSIO_LIBDIR={libdir}")
            print(f"XSTAR_TOOLS_CFITSIO_LIBS={libs}")

        def build_from_stage(stage: Path, *, clean: bool) -> None:
            stage_cpp = _prepare_stage(root, stage, clean=clean)
            make_base = [tools["make"], "-C", str(stage_cpp), f"PLATFORM={platform_key}"]
            if clean:
                subprocess.run([*make_base, "clean"], env=env, check=True)
            command = [
                *make_base,
                f"-j{jobs}",
                f"PACKAGE_VERSION={self.distribution.metadata.version}",
                *cfitsio_make_args,
                _native_make_target(profile),
            ]
            # Both supported packaging targets intentionally exclude
            # xstar-xspec-mpi. MPI remains an explicit `make mpi` /
            # `make xstar-xspec-mpi` HPC build.
            subprocess.run(command, env=env, check=True)
            missing = [name for name in artifacts if not (stage_cpp / name).is_file()]
            if missing:
                raise RuntimeError(
                    "native build completed without required artifact(s): " + ", ".join(missing)
                )
            for name in artifacts:
                src = stage_cpp / name
                dst = target_cpp / name
                shutil.copy2(src, dst)
                if name in {
                    f"xstar_cpp{_EXECUTABLE_SUFFIXES[system]}",
                    f"xstar-cpp{_EXECUTABLE_SUFFIXES[system]}",
                    f"xstar-xspec-initable{_EXECUTABLE_SUFFIXES[system]}",
                    f"xstar-xspec-table{_EXECUTABLE_SUFFIXES[system]}",
                    f"xstar-xspec{_EXECUTABLE_SUFFIXES[system]}",
                }:
                    dst.chmod(dst.stat().st_mode | 0o111)

        if persistent:
            # Release builders may keep a source-fingerprint-validated staging
            # directory so very large qualified translation units can be built
            # incrementally across constrained CI/tool invocations.
            stage = Path(persistent).expanduser().resolve()
            build_from_stage(stage, clean=False)
        else:
            with tempfile.TemporaryDirectory(prefix="xstar_tools_native_build_") as td:
                build_from_stage(Path(td) / "xstar_tools-build", clean=True)

        metadata.update(
            {
                "native_built": True,
                "artifacts": list(artifacts),
                "compiler": tools["cxx"],
                "make": tools["make"],
                "python_config": tools["python_config"],
                "cfitsio": subprocess.run(
                    [tools["pkg_config"], "--modversion", "cfitsio"],
                    text=True,
                    capture_output=True,
                    check=True,
                ).stdout.strip(),
                "jobs": jobs,
                "build_contract": "retained-qualified-Makefile-default-flags",
                "persistent_staging": bool(persistent),
            }
        )
        (target_cpp / "native_build.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


class XStarDistribution(Distribution):
    """Tag native wheels as platform/CPython-specific on every supported host."""

    def has_ext_modules(self) -> bool:
        try:
            return _native_requested()
        except RuntimeError:
            # Let build_py emit the detailed diagnostic during the actual build.
            return _native_policy() == "required"
