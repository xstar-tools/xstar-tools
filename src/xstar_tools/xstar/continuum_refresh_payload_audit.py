"""v0.6.48.7.22 call-1 thermal causality and refresh-payload audit.

This qualification-only audit consumes the physical v0.6.48.7.21.4 source
capture.  It distinguishes three independent questions:

* whether the native residual uses literal ``heatf.f90`` normalization;
* whether replacing only the continuum budget can restore the first controller
  branch; and
* which full between-call payloads must be captured before state transport can
  be implemented without an oracle.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

RELEASE = "0.6.48.7.22"
SCHEMA = "xstar-tools-v0648722-continuum-mg-causality-refresh-payload-audit-v1"
FAR_THRESHOLD = float(struct.unpack(">f", struct.pack(">f", 0.9))[0])
RESIDUAL_FACTOR = float(struct.unpack(">f", struct.pack(">f", 2.0))[0])
RESIDUAL_FLOOR = float(struct.unpack(">f", struct.pack(">f", 1.0e-37))[0])
csv.field_size_limit(sys.maxsize)

CHANGED_WORKSPACES = (
    "bremsa",
    "continuum_tau_in",
    "global_xilevg",
    "global_bilevg",
    "global_rnisg",
)
PAYLOAD_ARRAYS = (
    "radiation_energy",
    "bremsa",
    "continuum_tau_in",
    "continuum_tau_out",
    "global_xilevg",
    "global_bilevg",
    "global_rnisg",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


def _heatf_residual(heating: float, cooling: float) -> float:
    denominator = (RESIDUAL_FLOOR + float(heating)) + float(cooling)
    if denominator == 0.0:
        return 0.0
    return RESIDUAL_FACTOR * (float(heating) - float(cooling)) / denominator


def _native_call1_rows(native_dir: Path) -> list[dict[str, str]]:
    return [
        row
        for row in _read_csv(native_dir / "native_thermal_budget.csv")
        if row.get("kind") == "dsec" and int(row.get("call_index", 0)) == 1
    ]


def _run_native(root: Path, case_dir: Path, output_dir: Path) -> tuple[int, dict[str, Any] | None]:
    cpp = root / "src/xstar_tools/xstar/cpp"
    subprocess.run(["make", "-C", str(cpp), "-j2"], cwd=root, check=True)
    exe = cpp / "xstar_cpp"
    trajectory = root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/trajectory.csv"
    radiation = root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv"
    eval60 = root / "src/xstar_tools/benchmarks/v0648719_type53_two_state_promotion/evaluation60"
    records = _read_csv(eval60 / "type53_independent_state_runtime_records.csv")
    temperature = next(iter({float(row["temperature_k"]) for row in records}))
    covering = next(iter({float(row["covering_fraction"]) for row in records}))
    command = [
        str(exe), "run-fixed-dsec",
        "--case-dir", str(case_dir),
        "--trajectory-csv", str(trajectory),
        "--radiation-csv", str(radiation),
        "--dsec-radiation-csv", str(eval60 / "dsec_radiation_workspace.csv"),
        "--continuum-tau-csv", str(eval60 / "dsec_continuum_tau_workspace.csv"),
        "--dsec-covering-fraction", format(covering, ".17g"),
        "--temperature-k", format(temperature, ".17g"),
        "--controller-prefix-evaluations", "7",
        "--skip-fits",
        "--output-dir", str(output_dir),
    ]
    env = dict(os.environ)
    env["XSTAR_QUALIFICATION_REPLACEMENT"] = "1"
    env["XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION"] = "1"
    print("$ " + " ".join(command))
    completed = subprocess.run(
        command,
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(completed.stdout, end="")
    summary_path = output_dir / "controller_prefix_summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else None
    return completed.returncode, summary


def _source_element_totals(row: Mapping[str, str]) -> tuple[float, float]:
    return float(row["element_heating"]), float(row["element_cooling"])


def _source_continuum_totals(row: Mapping[str, str]) -> tuple[float, float]:
    return float(row["continuum_heating"]), float(row["continuum_cooling"])


def _native_element_totals(row: Mapping[str, str]) -> tuple[float, float]:
    return float(row["element_heating"]), float(row["element_cooling"])


def _native_continuum_totals(row: Mapping[str, str]) -> tuple[float, float]:
    return float(row["continuum_heating"]), float(row["continuum_cooling"])


def _sha_array(values: Iterable[float]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(struct.pack(">d", float(value)))
    return digest.hexdigest()


def verify_payload_bundle(capture_dir: Path) -> dict[str, Any]:
    """Verify optional per-call NPZ payloads against the captured fingerprints."""
    payload_dir = capture_dir / "call_start_payloads"
    fingerprint_path = capture_dir / "v0472_between_call_state_fingerprints.csv"
    if not payload_dir.is_dir() or not fingerprint_path.is_file():
        return {
            "status": "RUN_REQUIRED",
            "captured": False,
            "calls": 0,
            "errors": [],
        }
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - packaging/runtime guard
        return {"status": "REJECT", "captured": False, "calls": 0, "errors": [str(exc)]}
    fingerprints = {int(row["dsec_call_id"]): row for row in _read_csv(fingerprint_path)}
    errors: list[str] = []
    calls = 0
    manifest_rows: list[dict[str, Any]] = []
    for call_id in range(1, 5):
        path = payload_dir / f"call_{call_id}.npz"
        if not path.is_file():
            errors.append(f"missing:{path.name}")
            continue
        calls += 1
        with np.load(path, allow_pickle=False) as payload:
            for name in PAYLOAD_ARRAYS:
                if name not in payload:
                    errors.append(f"call{call_id}:missing:{name}")
                    continue
                array = np.asarray(payload[name], dtype=np.float64).reshape(-1)
                expected = fingerprints.get(call_id, {}).get(name + "_sha256")
                actual = _sha_array(array)
                if expected and actual != expected:
                    errors.append(f"call{call_id}:{name}:sha256")
                manifest_rows.append({
                    "dsec_call_id": call_id,
                    "workspace": name,
                    "count": int(array.size),
                    "sha256": actual,
                    "l1": float(np.sum(np.abs(array), dtype=np.float64)),
                })
    status = "ACCEPT" if calls == 4 and not errors else "REJECT"
    return {
        "status": status,
        "captured": status == "ACCEPT",
        "calls": calls,
        "errors": errors,
        "manifest_rows": manifest_rows,
    }


def audit(
    root: Path,
    case_dir: Path | None,
    capture_dir: Path,
    output_dir: Path,
    *,
    reuse_native: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    capture_dir = capture_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_rows = _read_csv(capture_dir / "v0472_call1_thermal_budget.csv")
    state_rows = _read_csv(capture_dir / "v0472_between_call_state_fingerprints.csv")
    if reuse_native is not None:
        native_dir = reuse_native.resolve()
        native_summary_path = native_dir / "native_dsec_summary.json"
        native_summary = json.loads(native_summary_path.read_text()) if native_summary_path.is_file() else None
        native_returncode = 20
    elif case_dir is not None:
        native_dir = output_dir / "native_full_controller"
        native_returncode, native_summary = _run_native(root, case_dir.resolve(), native_dir)
    else:
        benchmark = root / "src/xstar_tools/benchmarks/v0648722_call1_thermal_refresh_reference"
        native_dir = output_dir / "native_reference_copy"
        native_dir.mkdir(parents=True, exist_ok=True)
        source_native = benchmark / "native_thermal_budget_v0648722_prefix.csv"
        target_native = native_dir / "native_thermal_budget.csv"
        target_native.write_bytes(source_native.read_bytes())
        native_summary = json.loads((benchmark / "native_prefix_summary_v0648722.json").read_text())
        native_returncode = 20
    native_rows = _native_call1_rows(native_dir)
    common = min(len(source_rows), len(native_rows))
    causal_rows: list[dict[str, Any]] = []
    subcomponent_rows: list[dict[str, Any]] = []
    source_formula_exact = sum(
        int(_heatf_residual(float(row["httot"]), float(row["cltot"])) == float(row["hmctot"]))
        for row in source_rows
    )
    native_formula_exact = 0
    for index in range(common):
        source = source_rows[index]
        native = native_rows[index]
        sh, sc = float(source["httot"]), float(source["cltot"])
        neh, nec = _native_element_totals(native)
        nch, ncc = _native_continuum_totals(native)
        seh, sec = _source_element_totals(source)
        sch, scc = _source_continuum_totals(source)
        source_formula = _heatf_residual(sh, sc)
        native_formula = _heatf_residual(neh + nch, nec + ncc)
        continuum_only = _heatf_residual(neh + sch, nec + scc)
        element_only = _heatf_residual(seh + nch, sec + ncc)
        if "legacy_hmctot" in native:
            native_formula_exact += int(native_formula == float(native["hmctot"]))
        causal_rows.append({
            "call1_evaluation": index + 1,
            "source_hmctot": float(source["hmctot"]),
            "source_formula_hmctot": source_formula,
            "native_reported_hmctot": float(native["hmctot"]),
            "native_source_formula_hmctot": native_formula,
            "continuum_only_counterfactual_hmctot": continuum_only,
            "element_only_counterfactual_hmctot": element_only,
            "source_double_divide": abs(float(source["hmctot"])) > FAR_THRESHOLD,
            "native_double_divide": abs(native_formula) > FAR_THRESHOLD,
            "continuum_only_double_divide": abs(continuum_only) > FAR_THRESHOLD,
            "element_only_double_divide": abs(element_only) > FAR_THRESHOLD,
        })
        native_compton_heating = float(native.get("native_compton_heating", native["continuum_heating"]))
        native_compton_cooling = float(native.get("native_compton_cooling", 0.0))
        native_free_free_cooling = float(native.get("native_free_free_cooling", native["continuum_cooling"]))
        for component, source_value, native_value in (
            ("htfreef", float(source["htfreef"]), 0.0),
            ("htcomp", float(source["htcomp"]), native_compton_heating),
            ("clcomp", float(source["clcomp"]), native_compton_cooling),
            ("clbrems", float(source["clbrems"]), native_free_free_cooling),
            ("cmp1", float(source["cmp1"]), float("nan")),
            ("cmp2", float(source["cmp2"]), float("nan")),
        ):
            subcomponent_rows.append({
                "call1_evaluation": index + 1,
                "component": component,
                "source_value": source_value,
                "native_value": native_value,
                "absolute_gap": abs(native_value - source_value) if math.isfinite(native_value) else float("nan"),
            })
    _write_csv(output_dir / "call1_thermal_causal_counterfactuals.csv", causal_rows)
    _write_csv(output_dir / "call1_continuum_subcomponent_comparison.csv", subcomponent_rows)

    evaluation4 = causal_rows[3] if len(causal_rows) >= 4 else None
    source4 = source_rows[3] if len(source_rows) >= 4 else None
    native4 = native_rows[3] if len(native_rows) >= 4 else None
    mg_scale = None
    if source4 and native4:
        source_mg = max(abs(float(source4["mg_heating"])), abs(float(source4["mg_cooling"])), 1.0e-300)
        native_mg = max(abs(float(native4["mg_heating"])), abs(float(native4["mg_cooling"])))
        mg_scale = native_mg / source_mg

    changed = []
    if state_rows:
        for workspace in PAYLOAD_ARRAYS:
            key = workspace + "_sha256"
            if key in state_rows[0] and len({row[key] for row in state_rows}) > 1:
                changed.append(workspace)
    payload = verify_payload_bundle(capture_dir)
    if payload.get("manifest_rows"):
        _write_csv(output_dir / "between_call_workspace_payload_manifest.csv", payload["manifest_rows"])
    payload = {key: value for key, value in payload.items() if key != "manifest_rows"}

    formula_gate = source_formula_exact == len(source_rows) and len(source_rows) == 21
    native_formula_gate = native_formula_exact == common if common and "legacy_hmctot" in native_rows[0] else False
    continuum_ruled_out = bool(evaluation4 and not evaluation4["continuum_only_double_divide"])
    element_restores_branch = bool(evaluation4 and evaluation4["element_only_double_divide"])
    mg_blocker = bool(mg_scale is not None and mg_scale > 1.0e5)
    changed_exact = tuple(changed) == CHANGED_WORKSPACES
    analysis_ok = common >= 7 and formula_gate and continuum_ruled_out and element_restores_branch and mg_blocker and changed_exact
    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if analysis_ok else "REJECT",
        "qualification_only": True,
        "production_promotion_ready": False,
        "source_heatf_residual": {
            "formula": "2*(httot-cltot)/(float32(1e-37)+httot+cltot)",
            "rows_exact": source_formula_exact,
            "rows_expected": len(source_rows),
            "exact": formula_gate,
        },
        "native_heatf_residual": {
            "source_formula_present_in_runtime_ledger": bool(native_rows and "legacy_hmctot" in native_rows[0]),
            "rows_exact": native_formula_exact,
            "rows_compared": common,
            "exact": native_formula_gate,
        },
        "call1_causality": {
            "first_branch_evaluation": 4,
            "far_from_equilibrium_threshold": FAR_THRESHOLD,
            "evaluation4": evaluation4,
            "continuum_only_restores_source_branch": not continuum_ruled_out,
            "continuum_only_ruled_out_as_complete_fix": continuum_ruled_out,
            "source_element_with_native_continuum_restores_branch": element_restores_branch,
            "native_to_source_mg_absolute_scale_ratio": mg_scale,
            "mg_absolute_scale_blocker_localized": mg_blocker,
            "interpretation": (
                "continuum is the largest normalized contribution gap, but native Mg heating/cooling "
                "are each many orders of magnitude too large; replacing only continuum leaves hmctot near zero"
            ),
        },
        "between_call_refresh": {
            "changed_workspaces": changed,
            "expected_changed_workspaces": list(CHANGED_WORKSPACES),
            "identity_exact": changed_exact,
            "payload_capture": payload,
        },
        "native_controller": {
            "returncode": native_returncode,
            "total_evaluations": int((native_summary or {}).get("total_evaluations", (native_summary or {}).get("evaluations_completed", 0))),
            "reference_state_identity": bool((native_summary or {}).get("reference_state_identity", False)),
        },
        "gates": {
            "source_heatf_residual_formula": "ACCEPT" if formula_gate else "REJECT",
            "native_heatf_residual_formula": "ACCEPT" if native_formula_gate else "RUN_REQUIRED",
            "continuum_only_complete_fix": "RULED_OUT" if continuum_ruled_out else "UNRESOLVED",
            "element_thermal_scale_blocker": "ACCEPT" if element_restores_branch else "REJECT",
            "magnesium_absolute_scale_blocker": "ACCEPT" if mg_blocker else "REJECT",
            "between_call_workspace_identity": "ACCEPT" if changed_exact else "REJECT",
            "between_call_workspace_payload": payload["status"],
            "full_thermal_controller": "BLOCKED",
            "thermal_parity": "BLOCKED",
            "production_promotion": "BLOCKED",
        },
        "next_required_work": (
            "capture the full five-workspace call-start payloads, then correct Mg primary thermal "
            "heating/cooling construction before transporting per-call state"
        ),
    }
    _write_json(output_dir / "continuum_refresh_payload_summary.json", result)
    return result


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, default=Path.cwd())
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--case-dir", type=Path)
    parser.add_argument("--reuse-native", type=Path)
    args = parser.parse_args()
    result = audit(
        args.package_dir,
        args.case_dir,
        args.capture_dir,
        args.output_dir,
        reuse_native=args.reuse_native,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(_main())
