"""Benchmark original XSTAR run scripts against independent Python outputs.

The benchmark input is a tree of ``run_xstar.sh`` files such as the user's
``original_xstar.tar.gz`` suite.  The scripts are parsed as data; they are not
sourced.  Original XSTAR may optionally be executed directly with the parsed
``key=value`` arguments.  Python output directories must be generated
independently and are compared to the original products with the existing
physical output comparator.

XSTAR products are validation oracles only.  They are never read to initialize
or alter a Python physical calculation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from hashlib import sha256
from pathlib import Path, PurePosixPath
import csv
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import time
from typing import Any, Iterable, Mapping, Sequence

from .physical_output_parity import (
    PhysicalOutputParityResult,
    compare_physical_output_directories,
)


REQUIRED_XSTAR_PRODUCTS: tuple[str, ...] = (
    "xo01_detail.fits",
    "xo01_detal2.fits",
    "xo01_detal3.fits",
    "xo01_detal4.fits",
    "xout_abund1.fits",
    "xout_spect1.fits",
    "xout_lines1.fits",
    "xout_cont1.fits",
    "xout_rrc1.fits",
    "xout_step.log",
)

CANONICAL_STANDARD_CASES: tuple[str, ...] = (
    "helike_type69/c5_ne1e8",
    "helike_type69/o7_ne1e8",
    "helike_type69/mg11_ne1e8",
    "helike_type69/ca19_xi3_ne1e8",
)

_ABUNDANCE_TO_ELEMENT = {
    "habund": "H", "heabund": "He", "liabund": "Li", "beabund": "Be",
    "babund": "B", "cabund": "C", "nabund": "N", "oabund": "O",
    "fabund": "F", "neabund": "Ne", "naabund": "Na", "mgabund": "Mg",
    "alabund": "Al", "siabund": "Si", "pabund": "P", "sabund": "S",
    "clabund": "Cl", "arabund": "Ar", "kabund": "K", "caabund": "Ca",
    "scabund": "Sc", "tiabund": "Ti", "vabund": "V", "crabund": "Cr",
    "mnabund": "Mn", "feabund": "Fe", "coabund": "Co", "niabund": "Ni",
    "cuabund": "Cu", "znabund": "Zn",
}


class PhysicalBenchmarkError(RuntimeError):
    """Raised when benchmark inputs violate the strict suite contract."""


@dataclass(frozen=True)
class ParsedXSTARCommand:
    executable: str
    ordered_arguments: tuple[str, ...]
    parameters: Mapping[str, str]

    def argv(self, executable: str | None = None) -> list[str]:
        return [str(executable or self.executable), *self.ordered_arguments]


@dataclass(frozen=True)
class OriginalXSTARBenchmarkCase:
    relative_case_dir: str
    suite_name: str
    case_name: str
    run_script: str
    run_script_sha256: str
    command: ParsedXSTARCommand
    model_name: str
    density_cm3: float | None
    log_xi: float | None
    turbulent_velocity_kms: float | None
    active_elements: tuple[str, ...]
    canonical_standard_case: bool
    duplicate_parameter_key: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["command"] = {
            "executable": self.command.executable,
            "ordered_arguments": list(self.command.ordered_arguments),
            "parameters": dict(self.command.parameters),
        }
        data["active_elements"] = list(self.active_elements)
        return data


@dataclass(frozen=True)
class OriginalExecutionResult:
    relative_case_dir: str
    attempted: bool
    returncode: int | None
    elapsed_seconds: float
    stdout_log: str | None
    stderr_log: str | None
    products_present: tuple[str, ...]
    missing_products: tuple[str, ...]
    ready: bool


@dataclass(frozen=True)
class CasePhysicalBenchmarkResult:
    relative_case_dir: str
    original_run_dir: str
    python_run_dir: str
    original_products_present: tuple[str, ...]
    python_products_present: tuple[str, ...]
    missing_original_products: tuple[str, ...]
    missing_python_products: tuple[str, ...]
    parity: PhysicalOutputParityResult

    @property
    def inputs_available(self) -> bool:
        return self.parity.inputs_available

    @property
    def all_files_match(self) -> bool:
        return self.parity.all_files_ready

    def as_dict(self) -> dict[str, Any]:
        return {
            "relative_case_dir": self.relative_case_dir,
            "original_run_dir": self.original_run_dir,
            "python_run_dir": self.python_run_dir,
            "original_products_present": list(self.original_products_present),
            "python_products_present": list(self.python_products_present),
            "missing_original_products": list(self.missing_original_products),
            "missing_python_products": list(self.missing_python_products),
            "inputs_available": self.inputs_available,
            "parity_run": self.parity.parity_run,
            "all_files_match": self.all_files_match,
            "parity": self.parity.as_dict(),
        }


@dataclass(frozen=True)
class PhysicalBenchmarkSuiteResult:
    suite_root: str
    original_run_root: str
    python_run_root: str | None
    selection: str
    discovered_cases: tuple[OriginalXSTARBenchmarkCase, ...]
    selected_cases: tuple[OriginalXSTARBenchmarkCase, ...]
    original_executions: tuple[OriginalExecutionResult, ...] = ()
    case_results: tuple[CasePhysicalBenchmarkResult, ...] = ()
    source_archive: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @property
    def scripts_parsed_ready(self) -> bool:
        return bool(self.discovered_cases)

    @property
    def original_execution_ready(self) -> bool:
        return bool(self.original_executions) and all(item.ready for item in self.original_executions)

    @property
    def parity_requested(self) -> bool:
        return self.python_run_root is not None

    @property
    def parity_run_count(self) -> int:
        return sum(1 for item in self.case_results if item.parity.parity_run)

    @property
    def all_selected_cases_match(self) -> bool:
        return bool(self.case_results) and len(self.case_results) == len(self.selected_cases) and all(
            item.all_files_match for item in self.case_results
        )

    def as_dict(self) -> dict[str, Any]:
        original_complete = 0
        for case in self.selected_cases:
            _present, missing = products_present(Path(self.original_run_root) / case.relative_case_dir)
            if not missing:
                original_complete += 1
        canonical_discovered = sum(c.canonical_standard_case for c in self.discovered_cases)
        return {
            "suite_root": self.suite_root,
            "original_run_root": self.original_run_root,
            "python_run_root": self.python_run_root,
            "source_archive": self.source_archive,
            "selection": self.selection,
            "n_cases_discovered": len(self.discovered_cases),
            "n_cases_selected": len(self.selected_cases),
            "n_canonical_cases_discovered": canonical_discovered,
            "attached_suite_62_case_inventory_ready": len(self.discovered_cases) == 62,
            "canonical_four_case_gate_ready": canonical_discovered == len(CANONICAL_STANDARD_CASES),
            "strict_ten_product_contract_ready": len(REQUIRED_XSTAR_PRODUCTS) == 10,
            "original_run_scripts_parsed_ready": self.scripts_parsed_ready,
            "original_output_cases_complete": original_complete,
            "original_output_cases_incomplete": len(self.selected_cases) - original_complete,
            "original_execution_requested": bool(self.original_executions),
            "original_execution_ready": self.original_execution_ready,
            "parity_requested": self.parity_requested,
            "physical_benchmark_cases_run": self.parity_run_count,
            "physical_benchmark_all_selected_cases_match": self.all_selected_cases_match,
            "required_products": list(REQUIRED_XSTAR_PRODUCTS),
            "canonical_standard_cases": list(CANONICAL_STANDARD_CASES),
            "python_physical_runner_built_in": False,
            "xstar_outputs_used_as_python_inputs": False,
            "physical_all_atdb_parity_claimed": self.all_selected_cases_match,
            "next_source_target": (
                "expand_physical_standard_suite_after_parity"
                if self.all_selected_cases_match
                else "physical_input_to_state_runner_and_standard_suite_parity"
            ),
            "provenance": dict(self.provenance),
            "cases": [case.as_dict() for case in self.selected_cases],
            "original_executions": [asdict(item) for item in self.original_executions],
            "case_results": [item.as_dict() for item in self.case_results],
        }


def _sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace("D", "E").replace("d", "e"))
    except (TypeError, ValueError):
        return None


def _xstar_command_text(script_text: str) -> str:
    lines = script_text.splitlines()
    collecting = False
    chunks: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not collecting:
            if stripped == "xstar" or stripped.startswith("xstar "):
                collecting = True
            else:
                continue
        # Only the literal command continuation is accepted.  Shell operators,
        # substitutions, and redirections are outside the benchmark format.
        if any(token in stripped for token in ("$(", "`", "${", "|", ">", "<", ";", "&&", "||")):
            raise PhysicalBenchmarkError("unsupported shell syntax in xstar command")
        continued = stripped.endswith("\\")
        chunks.append(stripped[:-1].strip() if continued else stripped)
        if not continued:
            break
    if not chunks:
        raise PhysicalBenchmarkError("run script does not contain an xstar command")
    return " ".join(chunks)


def parse_run_xstar_script(path: str | Path) -> ParsedXSTARCommand:
    """Parse the simple ``xstar key=value ...`` command from one run script."""
    script = Path(path)
    command_text = _xstar_command_text(script.read_text(encoding="utf-8"))
    tokens = shlex.split(command_text, posix=True)
    if not tokens or Path(tokens[0]).name != "xstar":
        raise PhysicalBenchmarkError(f"unexpected executable in {script}")
    ordered: list[str] = []
    parameters: dict[str, str] = {}
    for token in tokens[1:]:
        if "=" not in token:
            raise PhysicalBenchmarkError(f"non key=value token {token!r} in {script}")
        key, value = token.split("=", 1)
        if not key or key in parameters:
            raise PhysicalBenchmarkError(f"invalid or duplicate parameter {key!r} in {script}")
        ordered.append(f"{key}={value}")
        parameters[key] = value
    if not parameters:
        raise PhysicalBenchmarkError(f"no XSTAR parameters found in {script}")
    return ParsedXSTARCommand(tokens[0], tuple(ordered), parameters)


def _active_elements(parameters: Mapping[str, str]) -> tuple[str, ...]:
    active: list[str] = []
    for key, element in _ABUNDANCE_TO_ELEMENT.items():
        value = _float_or_none(parameters.get(key))
        if value is not None and value != 0.0:
            active.append(element)
    return tuple(active)


def _parameter_key(parameters: Mapping[str, str]) -> str:
    # Exclude modelname because the attached suite contains aliases that are
    # physically identical despite different directory/model labels.
    payload = "\n".join(
        f"{key}={parameters[key]}" for key in sorted(parameters) if key != "modelname"
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _relative_case_dir(script: Path, suite_root: Path) -> str:
    return script.parent.relative_to(suite_root).as_posix()


def discover_original_xstar_cases(suite_root: str | Path) -> tuple[OriginalXSTARBenchmarkCase, ...]:
    """Discover and parse every ``run_xstar.sh`` below a suite root."""
    root = Path(suite_root).resolve()
    if not root.is_dir():
        raise PhysicalBenchmarkError(f"suite root is not a directory: {root}")
    cases: list[OriginalXSTARBenchmarkCase] = []
    for script in sorted(root.rglob("run_xstar.sh")):
        command = parse_run_xstar_script(script)
        rel = _relative_case_dir(script, root)
        parts = PurePosixPath(rel).parts
        suite_name = parts[0] if len(parts) > 1 else "root"
        digest = sha256(script.read_bytes()).hexdigest()
        params = command.parameters
        cases.append(
            OriginalXSTARBenchmarkCase(
                relative_case_dir=rel,
                suite_name=suite_name,
                case_name=script.parent.name,
                run_script=str(script),
                run_script_sha256=digest,
                command=command,
                model_name=str(params.get("modelname", script.parent.name)),
                density_cm3=_float_or_none(params.get("density")),
                log_xi=_float_or_none(params.get("rlogxi")),
                turbulent_velocity_kms=_float_or_none(params.get("vturbi")),
                active_elements=_active_elements(params),
                canonical_standard_case=rel in CANONICAL_STANDARD_CASES,
                duplicate_parameter_key=_parameter_key(params),
            )
        )
    if not cases:
        raise PhysicalBenchmarkError(f"no run_xstar.sh files found under {root}")
    return tuple(cases)


def select_benchmark_cases(
    cases: Sequence[OriginalXSTARBenchmarkCase],
    *,
    selection: str = "canonical-four",
    patterns: Sequence[str] = (),
) -> tuple[OriginalXSTARBenchmarkCase, ...]:
    """Select canonical, all, or glob-matched cases."""
    if patterns:
        selected = [
            case for case in cases
            if any(fnmatch(case.relative_case_dir, pattern) for pattern in patterns)
        ]
    elif selection == "canonical-four":
        by_path = {case.relative_case_dir: case for case in cases}
        selected = [by_path[path] for path in CANONICAL_STANDARD_CASES if path in by_path]
    elif selection == "all":
        selected = list(cases)
    else:
        raise PhysicalBenchmarkError(f"unsupported selection: {selection}")
    if not selected:
        raise PhysicalBenchmarkError("case selection is empty")
    return tuple(selected)


def _safe_extract_archive(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as tf:
        members = tf.getmembers()
        top_level: set[str] = set()
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts:
                raise PhysicalBenchmarkError(f"unsafe archive member: {member.name}")
            if member.issym() or member.islnk():
                raise PhysicalBenchmarkError(f"links are not accepted in benchmark archives: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise PhysicalBenchmarkError(f"special archive member is not accepted: {member.name}")
            if name.parts:
                top_level.add(name.parts[0])
        try:
            # Python versions with PEP 706 extraction filters.
            tf.extractall(destination, members=members, filter="data")
        except TypeError:
            # The members have already been constrained to ordinary files and
            # directories with relative, traversal-free paths.
            tf.extractall(destination, members=members)
    candidates = sorted(
        path for path in destination.rglob("run_xstar.sh") if path.is_file()
    )
    if not candidates:
        raise PhysicalBenchmarkError("archive contains no run_xstar.sh files")
    if len(top_level) == 1:
        top = destination / next(iter(top_level))
        if top.is_dir():
            return top
    roots = {path.parent for path in candidates}
    common = Path(os.path.commonpath([str(path) for path in roots]))
    return common


def prepare_original_xstar_suite(
    *,
    suite_archive: str | Path | None = None,
    suite_root: str | Path | None = None,
    work_root: str | Path,
) -> tuple[Path, str | None]:
    """Return a usable suite root from either an archive or directory."""
    if bool(suite_archive) == bool(suite_root):
        raise PhysicalBenchmarkError("supply exactly one of suite_archive or suite_root")
    work = Path(work_root)
    work.mkdir(parents=True, exist_ok=True)
    if suite_root:
        return Path(suite_root).resolve(), None
    archive = Path(str(suite_archive)).resolve()
    if not archive.is_file():
        raise PhysicalBenchmarkError(f"suite archive not found: {archive}")
    staged = work / "staged_original_xstar"
    archive_digest = _sha256_file(archive)
    digest_marker = staged / ".source_archive_sha256"
    if staged.exists():
        staged_digest = digest_marker.read_text(encoding="ascii").strip() if digest_marker.is_file() else ""
        if staged_digest == archive_digest:
            named = staged / "original_xstar"
            if named.is_dir() and any(named.rglob("run_xstar.sh")):
                return named.resolve(), str(archive)
            existing = sorted(path for path in staged.rglob("run_xstar.sh") if path.is_file())
            if existing:
                roots = {path.parent for path in existing}
                return Path(os.path.commonpath([str(path) for path in roots])).resolve(), str(archive)
        # A changed or unverifiable archive must never silently reuse a prior
        # staged suite.  Same-archive reuse preserves generated XSTAR products.
        shutil.rmtree(staged)
    root = _safe_extract_archive(archive, staged)
    digest_marker.write_text(archive_digest + "\n", encoding="ascii")
    return root, str(archive)


def products_present(run_dir: str | Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    root = Path(run_dir)
    present = tuple(name for name in REQUIRED_XSTAR_PRODUCTS if (root / name).is_file())
    missing = tuple(name for name in REQUIRED_XSTAR_PRODUCTS if name not in present)
    return present, missing


def clean_expected_products(run_dir: str | Path) -> None:
    root = Path(run_dir)
    for name in REQUIRED_XSTAR_PRODUCTS:
        path = root / name
        if path.exists():
            path.unlink()


def run_original_xstar_case(
    case: OriginalXSTARBenchmarkCase,
    *,
    suite_root: str | Path,
    xstar_executable: str = "xstar",
    log_root: str | Path,
    clean_products: bool = False,
    timeout: float | None = None,
    env: Mapping[str, str] | None = None,
) -> OriginalExecutionResult:
    """Run one original-XSTAR case without sourcing its shell script."""
    root = Path(suite_root)
    case_dir = root / case.relative_case_dir
    if clean_products:
        clean_expected_products(case_dir)
    logs = Path(log_root) / case.relative_case_dir
    logs.mkdir(parents=True, exist_ok=True)
    stdout_path = logs / "original_xstar.stdout.log"
    stderr_path = logs / "original_xstar.stderr.log"
    started = time.monotonic()
    run_env = os.environ.copy()
    if env:
        run_env.update({str(k): str(v) for k, v in env.items()})
    try:
        completed = subprocess.run(
            case.command.argv(xstar_executable),
            cwd=case_dir,
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        returncode: int | None = int(completed.returncode)
    except FileNotFoundError as exc:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc) + "\n", encoding="utf-8")
        returncode = 127
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text((exc.stderr or "") + "\nTIMEOUT\n", encoding="utf-8")
        returncode = 124
    elapsed = time.monotonic() - started
    present, missing = products_present(case_dir)
    return OriginalExecutionResult(
        relative_case_dir=case.relative_case_dir,
        attempted=True,
        returncode=returncode,
        elapsed_seconds=float(elapsed),
        stdout_log=str(stdout_path),
        stderr_log=str(stderr_path),
        products_present=present,
        missing_products=missing,
        ready=bool(returncode == 0 and not missing),
    )


def compare_benchmark_case(
    case: OriginalXSTARBenchmarkCase,
    *,
    original_run_root: str | Path,
    python_run_root: str | Path,
    rtol: float = 5.0e-5,
    atol: float = 1.0e-30,
    step_rtol: float = 5.0e-3,
    step_atol: float = 5.0e-3,
) -> CasePhysicalBenchmarkResult:
    original_dir = Path(original_run_root) / case.relative_case_dir
    python_dir = Path(python_run_root) / case.relative_case_dir
    original_present, original_missing = products_present(original_dir)
    python_present, python_missing = products_present(python_dir)
    parity = compare_physical_output_directories(
        original_dir,
        python_dir,
        rtol=rtol,
        atol=atol,
        step_rtol=step_rtol,
        step_atol=step_atol,
        required_files=REQUIRED_XSTAR_PRODUCTS,
    )
    return CasePhysicalBenchmarkResult(
        relative_case_dir=case.relative_case_dir,
        original_run_dir=str(original_dir),
        python_run_dir=str(python_dir),
        original_products_present=original_present,
        python_products_present=python_present,
        missing_original_products=original_missing,
        missing_python_products=python_missing,
        parity=parity,
    )


def run_physical_benchmark_suite(
    *,
    suite_archive: str | Path | None = None,
    suite_root: str | Path | None = None,
    work_root: str | Path = "xstar_physical_benchmark_v0471",
    selection: str = "canonical-four",
    case_patterns: Sequence[str] = (),
    original_run_root: str | Path | None = None,
    python_run_root: str | Path | None = None,
    run_original: bool = False,
    xstar_executable: str = "xstar",
    clean_original_products: bool = False,
    timeout: float | None = None,
    rtol: float = 5.0e-5,
    atol: float = 1.0e-30,
    step_rtol: float = 5.0e-3,
    step_atol: float = 5.0e-3,
) -> PhysicalBenchmarkSuiteResult:
    """Inventory, optionally run, and compare a physical XSTAR suite."""
    root, archive = prepare_original_xstar_suite(
        suite_archive=suite_archive,
        suite_root=suite_root,
        work_root=work_root,
    )
    discovered = discover_original_xstar_cases(root)
    selected = select_benchmark_cases(
        discovered, selection=selection, patterns=case_patterns
    )
    original_root = Path(original_run_root).resolve() if original_run_root else root

    executions: list[OriginalExecutionResult] = []
    if run_original:
        for case in selected:
            executions.append(
                run_original_xstar_case(
                    case,
                    suite_root=original_root,
                    xstar_executable=xstar_executable,
                    log_root=Path(work_root) / "original_run_logs",
                    clean_products=clean_original_products,
                    timeout=timeout,
                )
            )

    comparisons: list[CasePhysicalBenchmarkResult] = []
    if python_run_root is not None:
        for case in selected:
            comparisons.append(
                compare_benchmark_case(
                    case,
                    original_run_root=original_root,
                    python_run_root=python_run_root,
                    rtol=rtol,
                    atol=atol,
                    step_rtol=step_rtol,
                    step_atol=step_atol,
                )
            )

    return PhysicalBenchmarkSuiteResult(
        suite_root=str(root),
        original_run_root=str(original_root),
        python_run_root=(str(Path(python_run_root).resolve()) if python_run_root else None),
        selection=selection if not case_patterns else "patterns",
        discovered_cases=discovered,
        selected_cases=selected,
        original_executions=tuple(executions),
        case_results=tuple(comparisons),
        source_archive=archive,
        provenance={
            "benchmark_version": "v0.4.71",
            "benchmark_role": "strict diagnostic oracle",
            "source_archive_sha256": (_sha256_file(archive) if archive else None),
            "original_scripts_executed_as_shell": False,
            "original_command_parser": "literal xstar key=value argv",
            "original_xstar_executable_requested": str(xstar_executable),
            "original_xstar_environment_external": True,
            "original_xstar_atomic_database_not_bundled": True,
            "python_outputs_generated_independently": True,
            "fits_rtol": float(rtol),
            "fits_atol": float(atol),
            "step_rtol": float(step_rtol),
            "step_atol": float(step_atol),
        },
    )


def _case_rows(result: PhysicalBenchmarkSuiteResult) -> Iterable[dict[str, Any]]:
    selected = {case.relative_case_dir for case in result.selected_cases}
    duplicate_counts: dict[str, int] = {}
    for case in result.discovered_cases:
        duplicate_counts[case.duplicate_parameter_key] = duplicate_counts.get(case.duplicate_parameter_key, 0) + 1
    for case in result.discovered_cases:
        yield {
            "selected": case.relative_case_dir in selected,
            "canonical_standard_case": case.canonical_standard_case,
            "suite_name": case.suite_name,
            "relative_case_dir": case.relative_case_dir,
            "case_name": case.case_name,
            "model_name": case.model_name,
            "density_cm3": case.density_cm3,
            "log_xi": case.log_xi,
            "turbulent_velocity_kms": case.turbulent_velocity_kms,
            "active_elements": ";".join(case.active_elements),
            "duplicate_parameter_group_size": duplicate_counts[case.duplicate_parameter_key],
            "run_script_sha256": case.run_script_sha256,
        }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_physical_benchmark_products(
    result: PhysicalBenchmarkSuiteResult,
    out_dir: str | Path,
) -> dict[str, str]:
    """Write manifest, summary, case, and flattened parity diagnostics."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    summary = result.as_dict()

    manifest_path = root / "original_xstar_benchmark_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_archive": result.source_archive,
                "suite_root": result.suite_root,
                "required_products": list(REQUIRED_XSTAR_PRODUCTS),
                "canonical_standard_cases": list(CANONICAL_STANDARD_CASES),
                "cases": [case.as_dict() for case in result.discovered_cases],
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    summary_path = root / "original_xstar_benchmark_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    case_rows = list(_case_rows(result))
    cases_csv = root / "original_xstar_benchmark_cases.csv"
    _write_csv(cases_csv, case_rows)

    case_result_rows: list[dict[str, Any]] = []
    column_rows: list[dict[str, Any]] = []
    for item in result.case_results:
        case_result_rows.append(
            {
                "relative_case_dir": item.relative_case_dir,
                "inputs_available": item.inputs_available,
                "parity_run": item.parity.parity_run,
                "all_files_match": item.all_files_match,
                "missing_original_products": ";".join(item.missing_original_products),
                "missing_python_products": ";".join(item.missing_python_products),
            }
        )
        for file_result in item.parity.files:
            if not file_result.details:
                column_rows.append(
                    {
                        "relative_case_dir": item.relative_case_dir,
                        "filename": file_result.filename,
                        "hdu": "",
                        "column": "",
                        "kind": file_result.kind,
                        "ready": file_result.ready,
                        "n_values": 0,
                        "mismatch_count": 0 if file_result.ready else 1,
                        "max_abs_diff": 0.0,
                        "max_rel_diff": 0.0,
                        "notes": "; ".join(file_result.notes),
                    }
                )
            for detail in file_result.details:
                column_rows.append(
                    {
                        "relative_case_dir": item.relative_case_dir,
                        "filename": file_result.filename,
                        "hdu": detail.hdu,
                        "column": detail.column,
                        "kind": detail.kind,
                        "ready": detail.ready,
                        "n_values": detail.n_values,
                        "mismatch_count": detail.mismatch_count,
                        "max_abs_diff": detail.max_abs_diff,
                        "max_rel_diff": detail.max_rel_diff,
                        "notes": "; ".join(file_result.notes),
                    }
                )
    results_csv = root / "original_xstar_benchmark_case_results.csv"
    columns_csv = root / "original_xstar_benchmark_column_differences.csv"
    _write_csv(results_csv, case_result_rows)
    _write_csv(columns_csv, column_rows)

    plan_path = root / "run_original_selected_cases.sh"
    plan_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        'BENCHMARK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        "",
    ]
    original_root = Path(result.original_run_root).resolve()
    try:
        original_root_rel = original_root.relative_to(root.resolve())
    except ValueError:
        original_root_rel = None
    for case in result.selected_cases:
        if original_root_rel is None:
            case_dir = shlex.quote(str(original_root / case.relative_case_dir))
        else:
            rel_case = (original_root_rel / case.relative_case_dir).as_posix()
            case_dir = f'"${{BENCHMARK_ROOT}}/{rel_case}"'
        argv = " ".join(shlex.quote(token) for token in case.command.argv("${XSTAR_EXECUTABLE:-xstar}"))
        # Keep the executable environment expansion active while quoting every
        # parsed parameter token.
        argv = argv.replace("'${XSTAR_EXECUTABLE:-xstar}'", '"${XSTAR_EXECUTABLE:-xstar}"')
        plan_lines.extend([f"echo '=== {case.relative_case_dir} ==='", f"(cd {case_dir} && {argv})", ""])
    plan_path.write_text("\n".join(plan_lines), encoding="utf-8")
    plan_path.chmod(0o755)

    md_path = root / "original_xstar_benchmark_summary.md"
    lines = [
        "# Original XSTAR versus Python physical benchmark",
        "",
        f"- Discovered cases: **{len(result.discovered_cases)}**",
        f"- Selected cases: **{len(result.selected_cases)}**",
        f"- Selection: `{result.selection}`",
        f"- Original output root: `{result.original_run_root}`",
        f"- Python output root: `{result.python_run_root or 'not supplied'}`",
        f"- Cases actually compared: **{result.parity_run_count}**",
        f"- All selected cases match: **{result.all_selected_cases_match}**",
        "",
        "## Required products per case",
        "",
    ]
    lines.extend(f"- `{name}`" for name in REQUIRED_XSTAR_PRODUCTS)
    lines.extend(["", "## Selected cases", ""])
    lines.extend(f"- `{case.relative_case_dir}`" for case in result.selected_cases)
    lines.extend([
        "",
        "## Scope",
        "",
        "The original XSTAR products are diagnostic oracles only. They are not used to seed the Python calculation. ",
        "This release inventories and enforces the benchmark, but does not yet contain the general physical input-to-state Python runner. ",
        "True parity is accepted only when independently generated Python directories contain every required product and all comparisons pass.",
        "",
    ])
    if result.case_results:
        lines.extend(["## Case results", ""])
        for item in result.case_results:
            lines.append(
                f"- `{item.relative_case_dir}`: inputs={item.inputs_available}, all_files_match={item.all_files_match}"
            )
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "manifest": str(manifest_path),
        "summary_json": str(summary_path),
        "summary_markdown": str(md_path),
        "cases_csv": str(cases_csv),
        "case_results_csv": str(results_csv),
        "column_differences_csv": str(columns_csv),
        "run_original_script": str(plan_path),
    }


__all__ = [
    "REQUIRED_XSTAR_PRODUCTS",
    "CANONICAL_STANDARD_CASES",
    "PhysicalBenchmarkError",
    "ParsedXSTARCommand",
    "OriginalXSTARBenchmarkCase",
    "OriginalExecutionResult",
    "CasePhysicalBenchmarkResult",
    "PhysicalBenchmarkSuiteResult",
    "parse_run_xstar_script",
    "discover_original_xstar_cases",
    "select_benchmark_cases",
    "prepare_original_xstar_suite",
    "products_present",
    "clean_expected_products",
    "run_original_xstar_case",
    "compare_benchmark_case",
    "run_physical_benchmark_suite",
    "write_physical_benchmark_products",
]
