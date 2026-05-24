from __future__ import annotations

from pathlib import Path
import shutil

import pytest

import xstar_atomic as xa
from xstar_atomic.source_port import (
    CANONICAL_STANDARD_CASES,
    REQUIRED_XSTAR_PRODUCTS,
    compare_benchmark_case,
    default_port_ledger,
    discover_original_xstar_cases,
    parse_run_xstar_script,
    run_output_writer_validation,
    run_physical_benchmark_suite,
    select_benchmark_cases,
    write_physical_benchmark_products,
)


def _write_case(root: Path, rel: str, *, density: str, logxi: str, element: str) -> Path:
    case = root / rel
    case.mkdir(parents=True, exist_ok=True)
    abundance = {"C": "cabund", "O": "oabund", "Mg": "mgabund", "Ca": "caabund"}[element]
    (case / "run_xstar.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "cd \"$(dirname \"$0\")\"\n\n"
        "xstar \\\n"
        "  spectrum='pow' nsteps=10 npass=1 \\\n"
        f"  modelname='case_{case.name}' density={density} rlogxi={logxi} vturbi=100 \\\n"
        f"  habund=1 heabund=1 {abundance}=1\n",
        encoding="utf-8",
    )
    return case


@pytest.fixture()
def four_case_suite(tmp_path: Path) -> Path:
    root = tmp_path / "original_xstar"
    specs = (
        (CANONICAL_STANDARD_CASES[0], "1e8", "1.5", "C"),
        (CANONICAL_STANDARD_CASES[1], "1e8", "1.5", "O"),
        (CANONICAL_STANDARD_CASES[2], "1e8", "1.5", "Mg"),
        (CANONICAL_STANDARD_CASES[3], "1e8", "3", "Ca"),
    )
    for rel, density, logxi, element in specs:
        _write_case(root, rel, density=density, logxi=logxi, element=element)
    return root


def test_v0471_parse_literal_xstar_command(four_case_suite: Path):
    script = four_case_suite / CANONICAL_STANDARD_CASES[1] / "run_xstar.sh"
    parsed = parse_run_xstar_script(script)
    assert parsed.executable == "xstar"
    assert parsed.parameters["spectrum"] == "pow"
    assert parsed.parameters["density"] == "1e8"
    assert parsed.parameters["oabund"] == "1"
    assert parsed.argv("/opt/xstar/bin/xstar")[0] == "/opt/xstar/bin/xstar"


def test_v0471_discovery_and_canonical_order(four_case_suite: Path):
    cases = discover_original_xstar_cases(four_case_suite)
    assert len(cases) == 4
    selected = select_benchmark_cases(cases, selection="canonical-four")
    assert tuple(case.relative_case_dir for case in selected) == CANONICAL_STANDARD_CASES
    assert all(case.canonical_standard_case for case in selected)
    assert selected[0].active_elements == ("H", "He", "C")
    assert selected[-1].log_xi == 3.0


def test_v0471_archive_inventory_and_reports(four_case_suite: Path, tmp_path: Path):
    archive = tmp_path / "original_xstar.tar.gz"
    shutil.make_archive(str(archive).removesuffix(".tar.gz"), "gztar", root_dir=four_case_suite.parent, base_dir=four_case_suite.name)
    out = tmp_path / "benchmark"
    result = run_physical_benchmark_suite(
        suite_archive=archive,
        work_root=out,
        selection="canonical-four",
    )
    assert result.scripts_parsed_ready is True
    assert len(result.discovered_cases) == 4
    assert len(result.selected_cases) == 4
    assert result.parity_requested is False
    assert result.all_selected_cases_match is False
    paths = write_physical_benchmark_products(result, out)
    assert all(Path(value).exists() for value in paths.values())
    assert "xstar_outputs_used_as_python_inputs" in Path(paths["summary_json"]).read_text()


def _copy_bounded_products(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_XSTAR_PRODUCTS:
        shutil.copy2(source / name, target / name)


def test_v0471_strict_case_parity_identical_and_mismatch(four_case_suite: Path, tmp_path: Path):
    generated_root = tmp_path / "generated"
    summary = run_output_writer_validation(out_dir=generated_root)
    bounded = Path(summary["validation_root"]) / "generated_fits"

    original_root = tmp_path / "original_results"
    python_root = tmp_path / "python_results"
    rel = CANONICAL_STANDARD_CASES[0]
    _copy_bounded_products(bounded, original_root / rel)
    _copy_bounded_products(bounded, python_root / rel)

    case = select_benchmark_cases(
        discover_original_xstar_cases(four_case_suite), patterns=(rel,)
    )[0]
    result = compare_benchmark_case(
        case,
        original_run_root=original_root,
        python_run_root=python_root,
    )
    assert result.inputs_available is True
    assert result.all_files_match is True
    assert tuple(result.parity.required_files) == REQUIRED_XSTAR_PRODUCTS

    step_log = python_root / rel / "xout_step.log"
    with step_log.open("a", encoding="utf-8") as handle:
        handle.write("\nr= 9.99999E+99\n")
    mismatch = compare_benchmark_case(
        case,
        original_run_root=original_root,
        python_run_root=python_root,
    )
    assert mismatch.inputs_available is True
    assert mismatch.all_files_match is False
    assert any(
        (not file_result.ready) or any(detail.mismatch_count > 0 for detail in file_result.details)
        for file_result in mismatch.parity.files
    )


def test_v0471_missing_products_never_claim_parity(four_case_suite: Path, tmp_path: Path):
    case = select_benchmark_cases(
        discover_original_xstar_cases(four_case_suite),
        patterns=(CANONICAL_STANDARD_CASES[0],),
    )[0]
    result = compare_benchmark_case(
        case,
        original_run_root=tmp_path / "missing_original",
        python_run_root=tmp_path / "missing_python",
    )
    assert result.inputs_available is False
    assert result.all_files_match is False
    assert result.missing_original_products == REQUIRED_XSTAR_PRODUCTS
    assert result.missing_python_products == REQUIRED_XSTAR_PRODUCTS


def test_v0471_version_and_ledger():
    assert xa.__version__ == "0.4.87"
    routines = {entry.routine: entry for entry in default_port_ledger().entries}
    assert routines["physical_benchmark_suite"].status.value == "partial"


def test_v0471_archive_digest_controls_staged_reuse(four_case_suite: Path, tmp_path: Path):
    archive1 = tmp_path / "suite1.tar.gz"
    shutil.make_archive(
        str(archive1).removesuffix(".tar.gz"),
        "gztar",
        root_dir=four_case_suite.parent,
        base_dir=four_case_suite.name,
    )
    out = tmp_path / "benchmark"
    first = run_physical_benchmark_suite(
        suite_archive=archive1,
        work_root=out,
        selection="all",
    )
    assert len(first.discovered_cases) == 4
    retained = out / "staged_original_xstar" / four_case_suite.name / "retained.txt"
    retained.write_text("same archive keeps generated products\n", encoding="utf-8")

    second = run_physical_benchmark_suite(
        suite_archive=archive1,
        work_root=out,
        selection="all",
    )
    assert len(second.discovered_cases) == 4
    assert retained.is_file()

    replacement_parent = tmp_path / "replacement"
    replacement = replacement_parent / "original_xstar2"
    _write_case(
        replacement,
        CANONICAL_STANDARD_CASES[0],
        density="1e8",
        logxi="1.5",
        element="C",
    )
    archive2 = tmp_path / "suite2.tar.gz"
    shutil.make_archive(
        str(archive2).removesuffix(".tar.gz"),
        "gztar",
        root_dir=replacement_parent,
        base_dir=replacement.name,
    )
    third = run_physical_benchmark_suite(
        suite_archive=archive2,
        work_root=out,
        selection="all",
    )
    assert len(third.discovered_cases) == 1
    assert not retained.exists()
