"""Setuptools build support for xstar-tools native runtime artifacts.

Project metadata lives in pyproject.toml.  This module contains only the custom
build hook required to compile the retained, scientifically-qualified Makefile
implementation into an installed wheel without modifying the source checkout.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from setuptools import Distribution
from setuptools.command.build_py import build_py as _build_py

_NATIVE_ARTIFACTS = (
    "libxstar_solver.so",
    "libxstar_rates.so",
    "libxstar_matrix.so",
    "libxstar_emissivity.so",
    "libxstar_opacity.so",
    "libxstar_thermal.so",
    "libxstar_engine.so",
    "libxstar_local_zone.so",
    "libxstar_final_recompute.so",
    "libxstar_production_zone.so",
    "libxstar_xspec_table.so",
    "libxstar_api.so",
    "libxstar_backend_cpp.so",
    "libxstar_backend_python.so",
    "xstar_cpp",
    "xstar-cpp",
    "xstar-xspec-table",
)
_SUPPORTED_NATIVE_SYSTEMS = {"Linux"}


def _native_policy() -> str:
    value = os.environ.get("XSTAR_TOOLS_NATIVE", "auto").strip().lower()
    aliases = {"0": "off", "false": "off", "no": "off", "1": "required", "true": "required", "yes": "required"}
    value = aliases.get(value, value)
    if value not in {"auto", "required", "off"}:
        raise RuntimeError("XSTAR_TOOLS_NATIVE must be one of auto, required, or off")
    return value


def _native_requested() -> bool:
    policy = _native_policy()
    if policy == "off":
        return False
    if platform.system() in _SUPPORTED_NATIVE_SYSTEMS:
        return True
    if policy == "required":
        raise RuntimeError(
            f"native build requested on unsupported platform {platform.system()!r}; "
            "the current native wheel contract is Linux-only"
        )
    return False


def _tool(name: str, env_name: str | None = None) -> str | None:
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return shutil.which(name)


def _require_native_prerequisites() -> dict[str, str]:
    tools = {
        "make": _tool("make"),
        "cxx": _tool("c++", "CXX") or _tool("g++", "CXX"),
        "python_config": _tool("python3-config", "PYTHON_CONFIG"),
        "pkg_config": _tool("pkg-config"),
    }
    missing = [name for name, value in tools.items() if not value]
    if missing:
        raise RuntimeError(
            "native xstar-tools wheel build requires " + ", ".join(missing) +
            "; install build prerequisites or set XSTAR_TOOLS_NATIVE=off for a Python-only installation"
        )
    probe = subprocess.run([tools["pkg_config"], "--exists", "cfitsio"], check=False)
    if probe.returncode != 0:
        raise RuntimeError(
            "native xstar-tools wheel build requires CFITSIO development metadata (pkg-config cfitsio); "
            "install libcfitsio-dev/cfitsio-devel or set XSTAR_TOOLS_NATIVE=off"
        )
    return {k: str(v) for k, v in tools.items()}


def _source_fingerprint(root: Path) -> str:
    h = hashlib.sha256()
    base = root / "src/xstar_tools/xstar/cpp"
    for path in sorted(p for p in base.rglob("*") if p.is_file()):
        if path.name in _NATIVE_ARTIFACTS or path.suffix in {".o", ".so", ".pyc"} or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix().encode()
        h.update(rel + b"\0" + path.read_bytes() + b"\0")
    h.update((root / "pyproject.toml").read_bytes())
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
        for name in _NATIVE_ARTIFACTS:
            candidate = stage_cpp / name
            if candidate.exists():
                candidate.unlink()
        for candidate in stage_cpp.glob("*.o"):
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
        metadata: dict[str, object] = {
            "schema": "xstar-tools-native-build-v1",
            "package_version": self.distribution.metadata.version,
            "science_revision": "0.6.48.12.3.45.3.3.8",
            "c_api_abi": 60487,
            "production_zone_abi": 6048110,
            "policy": policy,
            "platform_system": platform.system(),
            "platform_machine": platform.machine(),
            "native_built": False,
            "artifacts": [],
        }
        if not native:
            metadata["reason"] = "native build disabled" if policy == "off" else "native build not supported on this platform"
            (target_cpp / "native_build.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return

        tools = _require_native_prerequisites()
        root = Path(__file__).resolve().parent
        source_cpp = root / "src" / "xstar_tools" / "xstar" / "cpp"
        if not source_cpp.is_dir():
            raise RuntimeError("native C++ source tree missing from source distribution")

        jobs_text = os.environ.get("XSTAR_TOOLS_NATIVE_JOBS", "2").strip()
        try:
            jobs = max(1, int(jobs_text))
        except ValueError as exc:
            raise RuntimeError("XSTAR_TOOLS_NATIVE_JOBS must be an integer") from exc

        persistent = os.environ.get("XSTAR_TOOLS_NATIVE_BUILD_DIR", "").strip()
        env = os.environ.copy()
        env["CXX"] = tools["cxx"]
        env["PYTHON_CONFIG"] = tools["python_config"]

        def build_from_stage(stage: Path, *, clean: bool) -> None:
            stage_cpp = _prepare_stage(root, stage, clean=clean)
            if clean:
                subprocess.run([tools["make"], "-C", str(stage_cpp), "clean"], check=True)
            command = [
                tools["make"], "-C", str(stage_cpp), f"-j{jobs}",
                f"PACKAGE_VERSION={self.distribution.metadata.version}", "all",
            ]
            subprocess.run(command, env=env, check=True)
            missing = [name for name in _NATIVE_ARTIFACTS if not (stage_cpp / name).is_file()]
            if missing:
                raise RuntimeError("native build completed without required artifact(s): " + ", ".join(missing))
            for name in _NATIVE_ARTIFACTS:
                src = stage_cpp / name
                dst = target_cpp / name
                shutil.copy2(src, dst)
                if name in {"xstar_cpp", "xstar-cpp", "xstar-xspec-table"}:
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

        metadata.update({
            "native_built": True,
            "artifacts": list(_NATIVE_ARTIFACTS),
            "compiler": tools["cxx"],
            "make": tools["make"],
            "python_config": tools["python_config"],
            "cfitsio": subprocess.run([tools["pkg_config"], "--modversion", "cfitsio"], text=True, capture_output=True, check=True).stdout.strip(),
            "jobs": jobs,
            "build_contract": "retained-qualified-Makefile-default-flags",
            "persistent_staging": bool(persistent),
        })
        (target_cpp / "native_build.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class XStarDistribution(Distribution):
    """Tag Linux native wheels as platform/CPython-specific."""

    def has_ext_modules(self) -> bool:
        try:
            return _native_requested()
        except RuntimeError:
            # Let build_py emit the detailed diagnostic during the actual build.
            return _native_policy() == "required"
