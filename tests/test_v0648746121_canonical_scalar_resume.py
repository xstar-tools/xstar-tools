from __future__ import annotations

import csv
import json
import math
import struct
from pathlib import Path

from xstar_tools.xstar import canonical_scalar_oracle_alignment as alignment
from xstar_tools.xstar import native_replay_resume as resume
from xstar_tools.xstar.all61_thermal_state_consumption_audit import COMMITTED_NATIVE_FIELD, COMPONENT_FIELDS
from xstar_tools.xstar.thermal_component_parity_closure import CLOSURE_FIELDS


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def one_ulp(value: float) -> float:
    return math.nextafter(value, math.inf)


def make_oracles(tmp_path: Path) -> tuple[Path, Path, Path]:
    baseline = tmp_path / "baseline"
    source = tmp_path / "source"
    thermal_dir = tmp_path / "thermal"
    baseline.mkdir(); source.mkdir(); thermal_dir.mkdir()
    fixed_rows = []
    source_levels = []
    source_ions = []
    thermal_budget = []
    for seq in range(1, 62):
        kind = "dsec" if seq <= 57 else "final"
        call = 1 if seq <= 15 else 2 if seq <= 30 else 3 if seq <= 45 else 4
        xee = 1.2 + seq * 1e-8
        charge = seq * 1e-10
        fixed_rows.append({
            "sequence": seq, "kind": kind, "dsec_call_id": call, "evaluation_index": seq,
            "temperature_k": 1e6, "temperature_t4": 100.0, "electron_fraction_input": 1.0,
            "computed_electron_fraction": xee, "charge_residual": charge, "hmctot": -0.5,
        })
        level_rows = []
        for row in range(1, 689):
            z = 1 if row <= 10 else 2 if row <= 100 else 12
            population = seq * 1e-8 + row * 1e-12
            level_rows.append({
                "row": row, "global_level_index": row, "element_z": z, "ion": 1,
                "superlevel": row, "source_population": format(population, ".17g"),
                "native_baseline": "0",
            })
            source_levels.append({
                "sequence": seq, "kind": kind, "dsec_call_id": call, "evaluation_index": seq,
                "element_z": z, "stage": 1, "local_level_ordinal": row,
                "global_level_index": row, "population": format(population, ".17g"),
                "bilevg": "0", "rnisg": "0",
            })
        write_csv(
            baseline / f"sequence_{seq:04d}_levels.csv",
            ["row", "global_level_index", "element_z", "ion", "superlevel", "source_population", "native_baseline"],
            level_rows,
        )
        ion_rows = []
        for z in (1, 2, 12):
            for stage in range(1, z + 2):
                population = seq * 1e-9 + z * 1e-11 + stage * 1e-13
                ion_rows.append({
                    "element_z": z, "stage": stage, "ion_charge": stage - 1,
                    "source_population": format(population, ".17g"), "native_baseline": "0",
                })
                source_ions.append({
                    "sequence": seq, "kind": kind, "dsec_call_id": call, "evaluation_index": seq,
                    "element_z": z, "stage": stage, "ion_charge": stage - 1,
                    "population": format(population, ".17g"),
                })
        write_csv(
            baseline / f"sequence_{seq:04d}_ions.csv",
            ["element_z", "stage", "ion_charge", "source_population", "native_baseline"],
            ion_rows,
        )
        baseline_charge = one_ulp(charge) if seq == 9 else charge
        write_csv(
            baseline / f"sequence_{seq:04d}_scalars.csv",
            ["field", "source_value", "native_baseline"],
            [
                {"field": "computed_electron_fraction", "source_value": format(xee, ".17g"), "native_baseline": "0"},
                {"field": "charge_residual", "source_value": format(baseline_charge, ".17g"), "native_baseline": "0"},
            ],
        )
        thermal = {field: 0 for field in CLOSURE_FIELDS}
        thermal.update({
            "sequence": seq, "kind": kind, "call_index": call, "evaluation_index": seq,
            "hmctot": -0.5, "elcter": charge,
        })
        thermal_budget.append(thermal)
        write_csv(thermal_dir / f"sequence_{seq:04d}_thermal.csv", CLOSURE_FIELDS, [thermal])
    write_csv(source / "v0472_all61_fixed_state_rows.csv", list(fixed_rows[0]), fixed_rows)
    write_csv(source / "v0472_all61_level_populations.csv", list(source_levels[0]), source_levels)
    write_csv(source / "v0472_all61_ion_populations.csv", list(source_ions[0]), source_ions)
    write_csv(source / "v0472_all61_thermal_budget.csv", CLOSURE_FIELDS, thermal_budget)
    return baseline, source, thermal_dir


def test_canonical_alignment_rebases_only_scalar_and_preserves_populations(tmp_path: Path) -> None:
    baseline, source, thermal_dir = make_oracles(tmp_path)
    output = tmp_path / "aligned"
    report = alignment.prepare(baseline, source, thermal_dir, output)
    assert report["result"] == "ACCEPT"
    assert report["level_values_exact"] == 41968
    assert report["ion_values_exact"] == 1098
    assert report["fixed_thermal_charge_exact"] == 61
    assert report["scalar_values_rebased"] == 1
    assert report["scalar_sequences_rebased"] == 1
    assert report["first_rebased_sequence"] == 9
    assert (output / "sequence_0009_levels.csv").read_bytes() == (baseline / "sequence_0009_levels.csv").read_bytes()
    assert (output / "sequence_0009_ions.csv").read_bytes() == (baseline / "sequence_0009_ions.csv").read_bytes()
    scalar_rows = {row["field"]: row for row in csv.DictReader((output / "sequence_0009_scalars.csv").open())}
    current = list(csv.DictReader((source / "v0472_all61_fixed_state_rows.csv").open()))[8]
    assert struct.pack(">d", float(scalar_rows["charge_residual"]["source_value"])) == struct.pack(">d", float(current["charge_residual"]))


def make_resume_inputs(tmp_path: Path, canonical: Path, thermal: Path) -> tuple[Path, Path, Path, Path]:
    inputs = tmp_path / "inputs.csv"
    trajectory = tmp_path / "trajectory.csv"
    workspaces = tmp_path / "workspaces"
    evaluations = tmp_path / "evaluations"
    workspaces.mkdir(); evaluations.mkdir()
    input_rows = []
    trajectory_rows = []
    for seq in range(1, 62):
        kind = "dsec" if seq <= 57 else "final"
        call = 1 if seq <= 15 else 2 if seq <= 30 else 3 if seq <= 45 else 4
        input_rows.append({
            "sequence": seq, "kind": kind, "dsec_call_id": call, "evaluation_index": seq,
            "temperature_k": 1e6, "covering_fraction": 1.0,
        })
        trajectory_rows.append({"kind": kind, "call_index": call, "evaluation_index": seq})
        (workspaces / f"evaluation_{seq:04d}").mkdir()
    write_csv(inputs, list(input_rows[0]), input_rows)
    write_csv(trajectory, list(trajectory_rows[0]), trajectory_rows)

    seq = 1
    eval_dir = evaluations / "evaluation_0001"
    eval_dir.mkdir()
    scalars = {row["field"]: row["source_value"] for row in csv.DictReader((canonical / "sequence_0001_scalars.csv").open())}
    thermal_row = next(csv.DictReader((thermal / "sequence_0001_thermal.csv").open()))
    summary = {
        "trajectory_row": 1, "evaluation_index": 1, "call_index": 1, "python_callbacks": 0,
        "replay_workspace_applied": True, "native_electron_fraction": float(scalars["computed_electron_fraction"]),
        "native_charge_residual": float(scalars["charge_residual"]),
        "reference_charge_residual": float(scalars["charge_residual"]),
        "native_hmctot": float(thermal_row["hmctot"]), "reference_hmctot": float(thermal_row["hmctot"]),
    }
    (eval_dir / "native_evaluation_summary.json").write_text(json.dumps(summary))
    write_csv(eval_dir / "native_evaluation.csv", [
        "sequence", "kind", "call_index", "evaluation_index", "native_electron_fraction",
        "native_charge_residual", "native_hmctot",
    ], [{
        "sequence": 1, "kind": "dsec", "call_index": 1, "evaluation_index": 1,
        "native_electron_fraction": scalars["computed_electron_fraction"],
        "native_charge_residual": scalars["charge_residual"], "native_hmctot": thermal_row["hmctot"],
    }])
    budget = {
        "sequence": 1, "call_index": 1, "evaluation_index": 1,
        "thermal_component_closure_applied": 1, "thermal_consumed_fixed_state_closure": 1,
        "charge_residual": scalars["charge_residual"], "hmctot": thermal_row["hmctot"],
    }
    for field in (name for name in COMPONENT_FIELDS if name in thermal_row):
        budget[COMMITTED_NATIVE_FIELD.get(field, field)] = thermal_row[field]
    write_csv(eval_dir / "native_thermal_budget.csv", list(budget), [budget])
    write_csv(eval_dir / "native_evaluation_populations.csv", ["row"], [{"row": i} for i in range(1, 689)])
    write_csv(eval_dir / "native_evaluation_spectra.csv", ["bin"], [{"bin": i} for i in range(1, 10000)])
    return inputs, trajectory, workspaces, evaluations


def test_resume_manifest_reuses_valid_sequence_and_rejects_stale_scalar(tmp_path: Path) -> None:
    baseline, source, thermal = make_oracles(tmp_path)
    canonical = tmp_path / "canonical"
    assert alignment.prepare(baseline, source, thermal, canonical)["result"] == "ACCEPT"
    inputs, trajectory, workspaces, evaluations = make_resume_inputs(tmp_path, canonical, thermal)
    manifest = resume.build_manifest(
        inputs, trajectory, workspaces, evaluations, canonical, thermal,
        tmp_path / "manifest.json", tmp_path / "plan.tsv",
    )
    assert manifest["sequences_reusable"] == 1
    assert manifest["sequences_pending"] == 60
    assert manifest["first_pending_sequence"] == 2
    rows = list(csv.reader((tmp_path / "plan.tsv").open(), delimiter="\t"))
    assert rows[0][7] == "reuse"
    assert rows[1][7] == "run"

    scalar_path = canonical / "sequence_0001_scalars.csv"
    scalar_rows = list(csv.DictReader(scalar_path.open()))
    scalar_rows[1]["source_value"] = format(one_ulp(float(scalar_rows[1]["source_value"])), ".17g")
    write_csv(scalar_path, list(scalar_rows[0]), scalar_rows)
    stale = resume.build_manifest(
        inputs, trajectory, workspaces, evaluations, canonical, thermal,
        tmp_path / "stale.json",
    )
    assert stale["sequences_reusable"] == 0
    assert stale["first_pending_sequence"] == 1
    assert "summary_charge_residual" in stale["statuses"][0]["reasons"]


def test_resume_accepts_historical_summary_reference_drift(tmp_path: Path) -> None:
    baseline, source, thermal = make_oracles(tmp_path)
    canonical = tmp_path / "canonical"
    assert alignment.prepare(baseline, source, thermal, canonical)["result"] == "ACCEPT"
    inputs, trajectory, workspaces, evaluations = make_resume_inputs(tmp_path, canonical, thermal)
    summary_path = evaluations / "evaluation_0001" / "native_evaluation_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["reference_charge_residual"] = 123.0
    summary["reference_hmctot"] = -456.0
    summary_path.write_text(json.dumps(summary))
    manifest = resume.build_manifest(
        inputs, trajectory, workspaces, evaluations, canonical, thermal,
        tmp_path / "manifest-reference-drift.json",
    )
    assert manifest["sequences_reusable"] == 1
    assert manifest["statuses"][0]["validation"] == "ACCEPT"
    assert "summary_reference_charge" not in manifest["statuses"][0]["reasons"]
    assert "summary_reference_hmctot" not in manifest["statuses"][0]["reasons"]
