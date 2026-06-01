"""Inventory and call-graph extraction for the original XSTAR source tree."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence
import csv
import json
import re
import tarfile


_SOURCE_SUFFIXES = (".f90", ".f", ".for", ".f95", ".f77")
_DEF_RE = re.compile(
    r"(?i)^\s*(?:recursive\s+|pure\s+|elemental\s+)?"
    r"(?:[a-z0-9_(),=*:\s]+\s+)?"
    r"(subroutine|function|program|module)\s+([a-z_][a-z0-9_]*)"
)
_CALL_RE = re.compile(r"(?i)\bcall\s+([a-z_][a-z0-9_]*)")
_USE_RE = re.compile(r"(?i)^\s*use\s+([a-z_][a-z0-9_]*)", re.MULTILINE)
_INCLUDE_RE = re.compile(r"(?i)^\s*include\s+['\"]([^'\"]+)", re.MULTILINE)


@dataclass(frozen=True)
class FortranRoutine:
    kind: str
    name: str
    source_path: str
    line_number: int


@dataclass(frozen=True)
class FortranSourceFile:
    path: str
    line_count: int
    code_line_count: int
    routines: Sequence[FortranRoutine]
    calls: Sequence[str]
    uses: Sequence[str]
    includes: Sequence[str]
    stage: str


@dataclass(frozen=True)
class XSTARSourceInventory:
    source_label: str
    files: Sequence[FortranSourceFile]

    @property
    def n_files(self) -> int:
        return len(self.files)

    @property
    def routines(self) -> List[FortranRoutine]:
        return [routine for file in self.files for routine in file.routines]

    @property
    def n_routines(self) -> int:
        return len(self.routines)

    def routine_to_file(self) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for routine in self.routines:
            result.setdefault(routine.name.lower(), routine.source_path)
        return result


def _strip_inline_comment(line: str) -> str:
    # XSTAR source uses ordinary Fortran comments heavily.  This intentionally
    # conservative parser is an inventory tool, not a compiler.
    return line.split("!", 1)[0]


def _classify_stage(path: str, routines: Sequence[FortranRoutine]) -> str:
    names = {r.name.lower() for r in routines}
    filename = Path(path).name.lower()
    if names & {"xstar", "xstarsetup", "xstarcalc", "step", "starf"}:
        return "driver"
    if "readtbl" in names or "setptrs" in names or "dbwk" in filename:
        return "atomic_database"
    if "ucalc" in names or filename.startswith(("calt", "upsil", "phint", "rnist")):
        return "atomic_rates"
    if names & {"calc_hmc_ion", "calc_hmc_element", "levwkelement", "msolvelucy"}:
        return "population_solver"
    if any(x in filename for x in ("heat", "cool", "ioneqm", "istruc", "dsec")):
        return "ionization_thermal"
    if any(x in filename for x in ("trnfr", "bremsmap", "tau", "pesc")):
        return "transfer"
    if any(x in filename for x in ("emis", "opacity", "spectrum", "spectra", "savd", "fstepr")):
        return "emissivity_output"
    if any(x in filename for x in ("ludcmp", "lubksb", "leqt", "mprove", "hunt", "sort")):
        return "numerical"
    return "support"


def _parse_source(path: str, text: str) -> FortranSourceFile:
    routines: List[FortranRoutine] = []
    calls = set()
    code_lines = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        code = _strip_inline_comment(line).strip()
        if not code:
            continue
        code_lines += 1
        match = _DEF_RE.match(code)
        if match and match.group(2).lower() != "procedure":
            routines.append(
                FortranRoutine(
                    kind=match.group(1).lower(),
                    name=match.group(2).lower(),
                    source_path=path,
                    line_number=line_number,
                )
            )
        calls.update(m.group(1).lower() for m in _CALL_RE.finditer(code))
    uses = sorted({m.group(1).lower() for m in _USE_RE.finditer(text)})
    includes = sorted({m.group(1) for m in _INCLUDE_RE.finditer(text)})
    return FortranSourceFile(
        path=path,
        line_count=len(text.splitlines()),
        code_line_count=code_lines,
        routines=tuple(routines),
        calls=tuple(sorted(calls)),
        uses=tuple(uses),
        includes=tuple(includes),
        stage=_classify_stage(path, routines),
    )


def build_source_inventory(
    *,
    source_root: Optional[str] = None,
    source_tar: Optional[str] = None,
) -> XSTARSourceInventory:
    """Build an inventory from an extracted source tree or source tarball."""
    if bool(source_root) == bool(source_tar):
        raise ValueError("Provide exactly one of source_root or source_tar")

    parsed: List[FortranSourceFile] = []
    if source_root:
        root = Path(source_root)
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in _SOURCE_SUFFIXES:
                parsed.append(
                    _parse_source(str(path.relative_to(root)), path.read_text(errors="replace"))
                )
        label = str(root)
    else:
        assert source_tar is not None
        with tarfile.open(source_tar, "r:*") as archive:
            for member in sorted(archive.getmembers(), key=lambda m: m.name):
                if not member.isfile() or not member.name.lower().endswith(_SOURCE_SUFFIXES):
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                parsed.append(
                    _parse_source(
                        member.name,
                        handle.read().decode("latin1", errors="replace"),
                    )
                )
        label = str(source_tar)

    return XSTARSourceInventory(source_label=label, files=tuple(parsed))


def write_source_inventory(inventory: XSTARSourceInventory, out_dir: str) -> Dict[str, str]:
    """Write file, routine, call-edge, and JSON inventory products."""
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    files_csv = output / "xstar_source_files.csv"
    routines_csv = output / "xstar_source_routines.csv"
    calls_csv = output / "xstar_source_call_edges.csv"
    summary_json = output / "xstar_source_inventory.json"

    with files_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "path", "stage", "line_count", "code_line_count",
                "n_routines", "n_calls", "uses", "includes",
            ],
        )
        writer.writeheader()
        for file in inventory.files:
            writer.writerow(
                {
                    "path": file.path,
                    "stage": file.stage,
                    "line_count": file.line_count,
                    "code_line_count": file.code_line_count,
                    "n_routines": len(file.routines),
                    "n_calls": len(file.calls),
                    "uses": ";".join(file.uses),
                    "includes": ";".join(file.includes),
                }
            )

    with routines_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["kind", "name", "source_path", "line_number", "stage"]
        )
        writer.writeheader()
        stage_by_path = {file.path: file.stage for file in inventory.files}
        for routine in inventory.routines:
            row = asdict(routine)
            row["stage"] = stage_by_path[routine.source_path]
            writer.writerow(row)

    routine_to_file = inventory.routine_to_file()
    with calls_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["caller_source_path", "callee", "callee_source_path", "resolved"],
        )
        writer.writeheader()
        for file in inventory.files:
            for callee in file.calls:
                target = routine_to_file.get(callee, "")
                writer.writerow(
                    {
                        "caller_source_path": file.path,
                        "callee": callee,
                        "callee_source_path": target,
                        "resolved": bool(target),
                    }
                )

    stage_counts: Dict[str, int] = {}
    for file in inventory.files:
        stage_counts[file.stage] = stage_counts.get(file.stage, 0) + 1
    summary = {
        "source_label": inventory.source_label,
        "n_source_files": inventory.n_files,
        "n_routines": inventory.n_routines,
        "stage_file_counts": stage_counts,
        "files": [
            {
                "path": file.path,
                "stage": file.stage,
                "line_count": file.line_count,
                "code_line_count": file.code_line_count,
                "routines": [asdict(routine) for routine in file.routines],
                "calls": list(file.calls),
                "uses": list(file.uses),
                "includes": list(file.includes),
            }
            for file in inventory.files
        ],
    }
    summary_json.write_text(json.dumps(summary, indent=2) + "\n")

    return {
        "files_csv": str(files_csv),
        "routines_csv": str(routines_csv),
        "calls_csv": str(calls_csv),
        "json": str(summary_json),
    }
