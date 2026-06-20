from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from xstar_tools.xstar.canonical_thermal_ownership_v048746212 import audit as ownership_audit
from xstar_tools.xstar.compact_population_parity_v048746212 import audit as population_audit

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _population_inputs(root: Path, mismatch: bool = False) -> tuple[Path, Path]:
    source = root / "source"
    native = root / "native"
    source_rows: list[dict[str, object]] = []
    native_rows: list[dict[str, object]] = []
    counts = {1: [33] * 61, 2: [78] * 61, 12: [548] * 11 + [547] * 50}
    for sequence in range(1, 62):
        for element_z in (1, 2, 12):
            for compact_row in range(1, counts[element_z][sequence - 1] + 1):
                value = sequence * 1.0e-3 + element_z * 1.0e-5 + compact_row * 1.0e-9
                common = {
                    "sequence": sequence,
                    "element_z": element_z,
                    "compact_row": compact_row,
                    "active_min_stage": 1,
                    "active_max_stage": element_z + 1,
                    "ion": 1,
                    "ion_stage": 1,
                    "ion_charge": 0,
                    "superlevel": 0,
                    "is_normalization_row": int(compact_row == counts[element_z][sequence - 1]),
                }
                source_rows.append({**common, "final_population": format(value, ".17g")})
                native_value = value
                if mismatch and sequence == 1 and element_z == 2 and compact_row == 1:
                    native_value = value + 1.0e-12
                native_rows.append({**common, "thermal_population": format(native_value, ".17g")})
    source_fields = list(source_rows[0])
    native_fields = list(native_rows[0])
    _write_csv(source / "v0472_all61_element_solve_rows.csv", source_fields, source_rows)
    _write_csv(native / "native_all61_thermal_compact_populations.csv", native_fields, native_rows)
    return source, native


def _canonical_inputs(root: Path, mismatch: bool = False) -> Path:
    native = root / "native"
    canonical_rows: list[dict[str, object]] = []
    diagonal_rows: list[dict[str, object]] = []
    for sequence in range(1, 62):
        for element_z in (1, 2, 12):
            fingerprint = f"{sequence:04x}{element_z:04x}abcdef00"
            for term_index, role in ((1, "forward_diag_loss"), (2, "reverse_diag_loss")):
                cj = 0.25 * term_index
                if mismatch and sequence == 1 and element_z == 1 and term_index == 1:
                    diagonal_cj = cj + 1.0e-12
                else:
                    diagonal_cj = cj
                common = {
                    "sequence": sequence,
                    "element_z": element_z,
                    "source_position": 100 + term_index,
                    "record": 1000 + term_index,
                    "data_type": 50,
                    "rate_type": 1,
                    "ion_index": 1,
                    "ion_stage": 1,
                    "compact_row": term_index,
                    "native_compact_row": term_index,
                    "source_compact_row": term_index,
                    "role": role,
                    "is_normalization_row": 0,
                    "source_domain_included": 1,
                    "cj2": format(cj / 10.0, ".17g"),
                    "native_cj": format(cj, ".17g"),
                    "source_cj": format(cj, ".17g"),
                }
                canonical_rows.append(
                    {
                        **common,
                        "ledger_fingerprint": fingerprint,
                        "element_consumer_fingerprint": fingerprint,
                        "fixed_state_consumer_fingerprint": fingerprint,
                        "shared_ownership": 1,
                        "matrix_insertion_captured": 1,
                        "term_index": term_index,
                        "type99_source_corrected": 0,
                        "primary_source_ordered": 0,
                        "primary_source_order_index": 0,
                        "cj": format(cj, ".17g"),
                    }
                )
                diagonal_rows.append(
                    {
                        **common,
                        "source_order_index": term_index,
                        "magnesium_type99_primary_cooling_reduction_applied": 0,
                        "magnesium_primary_cooling_source_order_applied": 0,
                        "magnesium_primary_cooling_source_order_index": 0,
                        "cj": format(diagonal_cj, ".17g"),
                    }
                )
    _write_csv(
        native / "native_all61_canonical_thermal_terms.csv",
        list(canonical_rows[0]),
        canonical_rows,
    )
    _write_csv(
        native / "native_all61_thermal_diagonal_ledger.csv",
        list(diagonal_rows[0]),
        diagonal_rows,
    )
    return native


def test_release_version() -> None:
    assert 'version = "0.6.48.7.46.21.2"' in (ROOT / "pyproject.toml").read_text()


def test_canonical_ledger_is_shared_by_both_consumers() -> None:
    header = (CPP / "xstar_element_engine.h").read_text()
    fixed = (CPP / "fixed_state_engine.cpp").read_text()
    element = (CPP / "element_engine.cpp").read_text()
    assert "typedef struct xstar_canonical_thermal_term_v1" in header
    assert "const xstar_canonical_thermal_term_v1* thermal_terms" in header
    assert fixed.count("CanonicalThermalLedgerBuilderV048746212 canonical_thermal_builder") == 1
    append_at = fixed.index("canonical_thermal_builder.append_matrix_committed(contribution)")
    closure_at = fixed.index("apply_matrix_closure_contribution_corrections(", append_at)
    finish_at = fixed.index("canonical_thermal_builder.finish(contributions)", closure_at)
    assert append_at < closure_at < finish_at
    assert "build_canonical_thermal_ledger_v048746212" not in fixed
    assert "xstar_element_engine_run_construction_with_thermal_ledger_v1" in fixed
    assert "xstar_canonical_thermal::reduce" in fixed
    assert "xstar_canonical_thermal::reduce" in element


def test_population_audit_accepts_all_40149_and_61_fingerprints(tmp_path: Path) -> None:
    source, native = _population_inputs(tmp_path)
    report = population_audit(source, native, tmp_path / "out")
    assert report["result"] == "ACCEPT"
    assert report["compact_population_values_exact"] == 40149
    assert report["sequence_fingerprints_exact"] == 61
    assert report["compact_population_values_by_element"]["1"]["exact"] == 2013
    assert report["compact_population_values_by_element"]["2"]["exact"] == 4758
    assert report["compact_population_values_by_element"]["12"]["exact"] == 33378


def test_population_audit_rejects_before_thermal_on_one_bitwise_mismatch(tmp_path: Path) -> None:
    source, native = _population_inputs(tmp_path, mismatch=True)
    report = population_audit(source, native, tmp_path / "out")
    assert report["result"] == "REJECT"
    assert report["accepted_gates"]["ALL_40149_COMPACT_POPULATIONS_EXACT"] == "REJECT"
    assert report["accepted_gates"]["ALL_61_COMPACT_POPULATION_FINGERPRINTS_EXACT"] == "REJECT"
    assert report["first_mismatch"]["element_z"] == 2


def test_canonical_ownership_audit_accepts_shared_identity(tmp_path: Path) -> None:
    native = _canonical_inputs(tmp_path)
    report = ownership_audit(native, tmp_path / "out")
    assert report["result"] == "ACCEPT"
    assert report["sequence_element_groups"] == 183
    assert report["fingerprint_groups_exact"] == 183
    assert report["matrix_insertion_captured_rows"] == 366
    assert report["accepted_gates"]["CANONICAL_TERMS_CAPTURED_AT_MATRIX_INSERTION"] == "ACCEPT"
    assert report["canonical_term_rows"] == 366
    assert report["diagonal_identity_exact_rows"] == 366


def test_canonical_ownership_audit_rejects_identity_divergence(tmp_path: Path) -> None:
    native = _canonical_inputs(tmp_path, mismatch=True)
    report = ownership_audit(native, tmp_path / "out")
    assert report["result"] == "REJECT"
    assert report["accepted_gates"]["CANONICAL_DIAGONAL_LEDGER_IDENTITY"] == "REJECT"
    assert report["first_mismatch"]["sequence"] == 1


def test_checker_marks_downstream_not_run_when_population_prerequisite_fails(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    (tmp_path / "baseline.json").write_text(json.dumps({"result": "ACCEPT"}))
    (tmp_path / "source.json").write_text(json.dumps({"result": "ACCEPT"}))
    rejected = {
        "result": "REJECT",
        "accepted_gates": {
            "H_COMPACT_POPULATIONS_EXACT": "REJECT",
            "HE_COMPACT_POPULATIONS_EXACT": "REJECT",
            "MG_COMPACT_POPULATIONS_EXACT": "REJECT",
            "ALL_40149_COMPACT_POPULATIONS_EXACT": "REJECT",
            "ALL_61_COMPACT_POPULATION_FINGERPRINTS_EXACT": "REJECT",
            "COMPACT_POPULATION_TOPOLOGY_EXACT": "ACCEPT",
        },
        "compact_population_values_exact": 3501,
        "compact_population_values_expected": 40149,
        "sequence_fingerprints_exact": 0,
    }
    accepted_ownership = {
        "result": "ACCEPT",
        "accepted_gates": {
            "CANONICAL_THERMAL_LEDGER_PRESENT_ALL61": "ACCEPT",
            "CANONICAL_THERMAL_LEDGER_SHARED_OWNERSHIP": "ACCEPT",
            "CANONICAL_TERMS_CAPTURED_AT_MATRIX_INSERTION": "ACCEPT",
            "ELEMENT_FIXED_STATE_LEDGER_FINGERPRINTS_IDENTICAL": "ACCEPT",
            "CANONICAL_THERMAL_TERM_INDICES_CONTIGUOUS": "ACCEPT",
            "CANONICAL_DIAGONAL_LEDGER_IDENTITY": "ACCEPT",
        },
        "canonical_term_rows": 100,
    }
    (audit / "v048746212_compact_population_parity_report.json").write_text(json.dumps(rejected))
    (audit / "v048746212_canonical_thermal_ownership_report.json").write_text(json.dumps(accepted_ownership))
    output = tmp_path / "checker.json"
    completed = subprocess.run(
        [
            "python",
            str(ROOT / "check_v048746212_compact_population_and_canonical_thermal_parity.py"),
            "--audit-output",
            str(audit),
            "--baseline-report",
            str(tmp_path / "baseline.json"),
            "--source-capture-report",
            str(tmp_path / "source.json"),
            "--output-json",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    report = json.loads(output.read_text())
    assert report["prerequisite_result"] == "REJECT"
    assert report["downstream_thermal_science"] == "NOT_RUN_PREREQUISITE"
    assert report["gates"]["NATIVE_COMPUTED_THERMAL_VALUES_EXACT_2440"] == "NOT_RUN_PREREQUISITE"


def test_runner_orders_prerequisites_before_downstream_science() -> None:
    source = (ROOT / "run_v048746212_compact_population_and_canonical_thermal_parity.sh").read_text()
    population = source.index("compact_population_parity_v048746212")
    ownership = source.index("canonical_thermal_ownership_v048746212")
    fail_first = source.index('if [ "$COMPACT_RC" -ne 0 ] || [ "$CANONICAL_RC" -ne 0 ]')
    downstream = source.index("all61_thermal_state_consumption_audit")
    assert population < fail_first < downstream
    assert ownership < fail_first < downstream
    assert "downstream_thermal_science=NOT_RUN_PREREQUISITE" in source


def test_readiness_accepts(tmp_path: Path) -> None:
    report = tmp_path / "readiness.json"
    subprocess.run(
        [
            "python",
            str(ROOT / "check_v048746212_compact_population_and_canonical_thermal_parity_readiness.py"),
            "--package-dir",
            str(ROOT),
            "--output-json",
            str(report),
        ],
        check=True,
    )
    result = json.loads(report.read_text())
    assert result["result"] == "ACCEPT"
    assert result["module_contract"]["canonical_builder_instantiated"] == 1
    assert result["module_contract"]["canonical_insertion_capture"] == 1
    assert result["module_contract"]["canonical_finish_once"] == 1
    assert result["module_contract"]["runner_fail_first"] >= 1
