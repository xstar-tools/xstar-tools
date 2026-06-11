from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_tools.xstar.fixed_state_parity import compare_fixed_state, verify_oracle

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "src/xstar_tools/benchmarks/v06487_fixed_state_reference_v0472"


def _write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _synthetic_exact_candidate(root: Path) -> Path:
    output = root / "qualification"
    diagnostics = output / "qualification_diagnostics"
    reference_input = output / "reference_input"
    diagnostics.mkdir(parents=True)
    reference_input.mkdir(parents=True)

    states = list(csv.DictReader((ORACLE / "trajectory_state_oracle.csv").open(newline="", encoding="utf-8")))
    trajectory_rows = []
    for row in states:
        trajectory_rows.append({
            "sequence": row["evaluation_ordinal"],
            "native_electron_fraction": row["reference_computed_electron_fraction"],
            "native_charge_residual": row["reference_charge_residual"],
        })
    _write_csv(reference_input / "native_trajectory.csv", trajectory_rows, list(trajectory_rows[0]))
    (reference_input / "native_trajectory_summary.json").write_text(
        json.dumps({"python_callbacks": 0, "evaluations": 61}) + "\n", encoding="utf-8"
    )

    ions = list(csv.DictReader((ORACLE / "accepted_ion_populations.csv").open(newline="", encoding="utf-8")))
    for evaluation in sorted({int(r["reference_evaluation_ordinal"]) for r in ions}):
        selected = [r for r in ions if int(r["reference_evaluation_ordinal"]) == evaluation]
        ion_rows = [{
            "element_z": r["element_z"],
            "stage": r["stage"],
            "final_fraction": r["reference_fraction"],
        } for r in selected]
        _write_csv(diagnostics / f"evaluation_{evaluation:04d}_ion_balance.csv", ion_rows, list(ion_rows[0]))

    levels = [r for r in csv.DictReader((ORACLE / "final_level_populations.csv").open(newline="", encoding="utf-8")) if r["mapping_status"] == "mapped"]
    level_rows = [{
        "global_population_row": r["global_population_row"],
        "final_population": r["reference_population"],
    } for r in levels]
    _write_csv(diagnostics / "evaluation_0061_populations.csv", level_rows, list(level_rows[0]))
    return output


def test_bundled_oracle_verifies() -> None:
    result = verify_oracle(ORACLE)
    assert result["result"] == "ACCEPT"
    assert result["files_verified"] == 3
    manifest = json.loads((ORACLE / "oracle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["reference_bundle"] == "v06486_qualification_reference_v0472"
    assert "reference_directory" not in manifest
    assert "program_rows_csv" not in manifest
    assert len(manifest["reference_manifest_sha256"]) == 64
    assert len(manifest["program_rows_sha256"]) == 64


def test_exact_available_subset_is_recognized_but_all61_claim_remains_blocked(tmp_path: Path) -> None:
    candidate = _synthetic_exact_candidate(tmp_path)
    report = compare_fixed_state(ORACLE, candidate, tmp_path / "report")
    assert report["all_61_electron_fraction_exact"] is True
    assert report["accepted_ion_population_exact"] is True
    assert report["accepted_ion_states_compared"] == 4
    assert report["final_ion_population_exact"] is True
    assert report["final_level_population_exact"] is True
    assert report["exact_h_he_mg_ion_populations_all_61"] is False
    assert report["exact_level_populations_all_61"] is False
    assert report["result"] == "REJECT"


def test_single_native_population_change_is_rejected(tmp_path: Path) -> None:
    candidate = _synthetic_exact_candidate(tmp_path)
    path = candidate / "qualification_diagnostics/evaluation_0061_ion_balance.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rows[0]["final_fraction"] = str(float(rows[0]["final_fraction"]) + 1.0e-12)
    _write_csv(path, rows, list(rows[0]))
    report = compare_fixed_state(ORACLE, candidate, tmp_path / "report")
    assert report["final_ion_population_exact"] is False
    assert report["max_abs_final_ion_population_delta"] > 0.0
