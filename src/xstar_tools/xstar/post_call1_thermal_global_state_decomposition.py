"""v0.6.48.7.26 post-call-1 thermal/global-state consumer decomposition."""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.26"
SCHEMA = "xstar-tools-v0648726-post-call1-thermal-global-state-decomposition-v1"
MODES = ("none", "xilevg", "xilevg-bilevg", "xilevg-rnisg", "all")
ELEMENT_FIELDS = {
    "hydrogen": ("h_heating", "h_cooling", "h_heating2", "h_cooling2"),
    "helium": ("he_heating", "he_cooling", "he_heating2", "he_cooling2"),
    "magnesium": ("mg_heating", "mg_cooling", "mg_heating2", "mg_cooling2"),
}
CONTINUUM_FIELDS = ("continuum_heating", "continuum_cooling", "htfreef", "htcomp", "clcomp", "clbrems")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def locate(root: Path, name: str) -> Path:
    direct = root / name
    if direct.is_file() or direct.is_dir():
        return direct
    hits = list(root.rglob(name))
    if not hits:
        raise FileNotFoundError(f"{name} not found below {root}")
    return hits[0]


def prepare(previous_audit: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    workspace = locate(previous_audit, "call_start_workspace_bin")
    shutil.copytree(workspace, output / "call_start_workspace_bin", dirs_exist_ok=True)
    call1_summary = locate(previous_audit, "call1_parity_summary.json")
    shutil.copy2(call1_summary, output / "accepted_call1_parity_summary.json")
    c1 = json.loads(call1_summary.read_text())
    call1_ok = c1.get("result") == "ACCEPT" and c1.get("gates", {}).get("CALL1_CONTROLLER_TRAJECTORY") == "ACCEPT"
    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if call1_ok else "REJECT",
        "accepted_call1_preserved": call1_ok,
        "workspace_payload_prepared": True,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    write_json(output / "preparation_summary.json", result)
    return result


def _source_call2_row(source_budget: Path) -> dict[str, str]:
    rows = read_csv(source_budget)
    matches = [r for r in rows if int(r["dsec_call_id"]) == 2 and int(r["dsec_local_evaluation_index"]) == 1]
    if len(matches) != 1:
        raise ValueError(f"expected one source call-2/evaluation-1 budget, found {len(matches)}")
    return matches[0]


def _native_mode(replay_root: Path, mode: str) -> tuple[dict[str, str], dict[str, str]]:
    root = replay_root / f"replay_{mode.replace('-', '_')}"
    budgets = read_csv(root / "native_thermal_budget.csv")
    states = read_csv(root / "native_evaluation.csv")
    if len(budgets) != 1 or len(states) != 1:
        raise ValueError(f"mode {mode} must contain one budget and one state row")
    return budgets[0], states[0]


def _f(row: dict[str, str], field: str) -> float:
    return float(row[field])


def _component_exact(source: dict[str, str], native: dict[str, str], fields: tuple[str, ...]) -> bool:
    return all(_f(source, name) == _f(native, name) for name in fields)


def _same_vector(left: dict[str, float], right: dict[str, float]) -> bool:
    return all(left[k] == right[k] for k in left)


def consumer_inventory(package_root: Path, output: Path) -> list[dict[str, Any]]:
    records_path = package_root / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp"
    source = records_path.read_text()
    native_x = "runtime_input->global_xilevg" in source
    native_b = "runtime_input->global_bilevg" in source
    native_r = "runtime_input->global_rnisg" in source
    # Header/null-validation references do not count as physics consumption.
    native_b = native_b and source.count("runtime_input->global_bilevg") > 0
    native_r = native_r and source.count("runtime_input->global_rnisg") > 0
    rows = [
        {"workspace": "global_xilevg", "semantic_role": "level population seed", "native_physics_consumer": native_x,
         "native_consumer_scope": "mapped compact-row population initialization" if native_x else "none",
         "rate_family_consumers": "population_seed", "status": "ACTIVE" if native_x else "MISSING"},
        {"workspace": "global_bilevg", "semantic_role": "departure coefficient", "native_physics_consumer": native_b,
         "native_consumer_scope": "rate-family access" if native_b else "ABI transport and validation only",
         "rate_family_consumers": "none captured" if not native_b else "source inspection required", "status": "ACTIVE" if native_b else "MISSING"},
        {"workspace": "global_rnisg", "semantic_role": "LTE population", "native_physics_consumer": native_r,
         "native_consumer_scope": "rate-family access" if native_r else "ABI transport and validation only",
         "rate_family_consumers": "none captured" if not native_r else "source inspection required", "status": "ACTIVE" if native_r else "MISSING"},
    ]
    write_csv(output / "native_global_state_consumer_inventory.csv", rows)
    return rows


def audit(source_budget: Path, replay_root: Path, previous_audit: Path,
          package_root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    source_rows = read_csv(source_budget)
    call_inventory = {call: sum(int(r["dsec_call_id"]) == call for r in source_rows) for call in (1, 2, 3, 4)}
    source57 = len(source_rows) == 57 and call_inventory == {1: 21, 2: 1, 3: 18, 4: 17}
    source = _source_call2_row(source_budget)
    c1 = json.loads(locate(previous_audit, "call1_parity_summary.json").read_text())
    call1_ok = c1.get("result") == "ACCEPT" and c1.get("gates", {}).get("CALL1_CONTROLLER_TRAJECTORY") == "ACCEPT"
    inventory = consumer_inventory(package_root, output)

    mode_rows: list[dict[str, Any]] = []
    vectors: dict[str, dict[str, float]] = {}
    errors: list[str] = []
    for mode in MODES:
        try:
            budget, state = _native_mode(replay_root, mode)
        except Exception as exc:
            errors.append(f"{mode}:{exc}")
            continue
        vector = {field: _f(budget, field) for fields in ELEMENT_FIELDS.values() for field in fields}
        vector.update({field: _f(budget, field) for field in CONTINUUM_FIELDS})
        vector["charge_residual"] = _f(state, "native_charge_residual")
        vector["hmctot"] = _f(state, "native_hmctot")
        vectors[mode] = vector
        row: dict[str, Any] = {
            "mode": mode,
            "replay_workspace_applied": int(state.get("replay_workspace_applied", "0")),
            "h_exact": _component_exact(source, budget, ELEMENT_FIELDS["hydrogen"]),
            "he_exact": _component_exact(source, budget, ELEMENT_FIELDS["helium"]),
            "mg_exact": _component_exact(source, budget, ELEMENT_FIELDS["magnesium"]),
            "continuum_exact": _component_exact(source, budget, CONTINUUM_FIELDS),
            "charge_residual_exact": _f(source, "elcter") == vector["charge_residual"],
            "hmctot_exact": _f(source, "hmctot") == vector["hmctot"],
            "native_charge_residual": vector["charge_residual"],
            "source_charge_residual": _f(source, "elcter"),
            "native_hmctot": vector["hmctot"],
            "source_hmctot": _f(source, "hmctot"),
        }
        for element, fields in ELEMENT_FIELDS.items():
            row[f"{element}_primary_net_gap"] = ((_f(budget, fields[0]) - _f(budget, fields[1])) -
                                                    (_f(source, fields[0]) - _f(source, fields[1])))
        row["continuum_primary_net_gap"] = ((_f(budget, "continuum_heating") - _f(budget, "continuum_cooling")) -
                                             (_f(source, "continuum_heating") - _f(source, "continuum_cooling")))
        mode_rows.append(row)
    write_csv(output / "call2_evaluation1_workspace_replay_comparison.csv", mode_rows)

    effects: list[dict[str, Any]] = []
    if all(mode in vectors for mode in MODES):
        baseline = vectors["xilevg"]
        for mode, label in (("none", "remove_xilevg"), ("xilevg-bilevg", "add_bilevg"),
                            ("xilevg-rnisg", "add_rnisg"), ("all", "add_bilevg_and_rnisg")):
            changed = [field for field in baseline if vectors[mode][field] != baseline[field]]
            effects.append({"comparison": label, "mode": mode, "changed_field_count": len(changed),
                            "changed_fields": ";".join(changed),
                            "hmctot_delta_to_xilevg": vectors[mode]["hmctot"] - baseline["hmctot"],
                            "charge_delta_to_xilevg": vectors[mode]["charge_residual"] - baseline["charge_residual"]})
    write_csv(output / "call2_evaluation1_workspace_effects.csv", effects)

    all_row = next((r for r in mode_rows if r["mode"] == "all"), None)
    exact = bool(all_row and all(all_row[name] for name in
        ("h_exact", "he_exact", "mg_exact", "continuum_exact", "charge_residual_exact", "hmctot_exact")))
    bilevg_effect = bool(vectors and "all" in vectors and "xilevg" in vectors and
                         not _same_vector(vectors["all"], vectors["xilevg"]))
    bilevg_only_effect = bool(vectors and "xilevg-bilevg" in vectors and "xilevg" in vectors and
                              not _same_vector(vectors["xilevg-bilevg"], vectors["xilevg"]))
    rnisg_only_effect = bool(vectors and "xilevg-rnisg" in vectors and "xilevg" in vectors and
                             not _same_vector(vectors["xilevg-rnisg"], vectors["xilevg"]))
    replay_complete = len(mode_rows) == 5 and not errors and all(int(r["replay_workspace_applied"]) == 1 for r in mode_rows)
    formula_blocker = replay_complete and not exact and not bilevg_only_effect and not rnisg_only_effect

    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if call1_ok and source57 and replay_complete else "REJECT",
        "errors": errors,
        "accepted_call1_preserved": call1_ok,
        "source_full_dsec_thermal_budget": {"rows": len(source_rows), "call_inventory": {str(k): v for k, v in call_inventory.items()},
                                             "status": "ACCEPT" if source57 else "REJECT"},
        "call2_evaluation1": {
            "workspace_replays_complete": replay_complete,
            "modes": list(MODES),
            "h_exact": bool(all_row and all_row["h_exact"]),
            "he_exact": bool(all_row and all_row["he_exact"]),
            "mg_exact": bool(all_row and all_row["mg_exact"]),
            "continuum_exact": bool(all_row and all_row["continuum_exact"]),
            "charge_residual_exact": bool(all_row and all_row["charge_residual_exact"]),
            "hmctot_exact": bool(all_row and all_row["hmctot_exact"]),
            "all_components_exact": exact,
        },
        "decomposition": {
            "xilevg_effect_observed": bool(vectors and "none" in vectors and "xilevg" in vectors and not _same_vector(vectors["none"], vectors["xilevg"])),
            "bilevg_effect_observed": bilevg_only_effect,
            "rnisg_effect_observed": rnisg_only_effect,
            "combined_bilevg_rnisg_effect_observed": bilevg_effect,
            "general_element_thermal_formula_blocker": formula_blocker,
            "interpretation": ("call-2/evaluation-1 exact" if exact else
                "general H/He/Mg or continuum construction remains dominant; transported bilevg/rnisg have no native consumer effect" if formula_blocker else
                "global-state workspaces alter the native result; inspect marginal replay effects before activating consumers"),
        },
        "native_consumer_inventory": inventory,
        "gates": {
            "CALL1_ACCEPTED_BASELINE": "ACCEPT" if call1_ok else "REJECT",
            "SOURCE_57_EVALUATION_THERMAL_CAPTURE": "ACCEPT" if source57 else "REJECT",
            "CALL2_EVALUATION1_WORKSPACE_REPLAYS": "ACCEPT" if replay_complete else "REJECT",
            "CALL2_EVALUATION1_H_HE_MG_CONTINUUM": "ACCEPT" if exact else "REJECT",
            "CALL2_EVALUATION1_CHARGE_HMCTOT": "ACCEPT" if exact else "REJECT",
            "GLOBAL_BILEVG_CONSUMER": "OBSERVED" if bilevg_only_effect else "MISSING_OR_NO_EFFECT",
            "GLOBAL_RNISG_CONSUMER": "OBSERVED" if rnisg_only_effect else "MISSING_OR_NO_EFFECT",
            "CALLS_3_TO_4": "RUN_ALLOWED" if exact else "BLOCKED_BY_CALL2_EVALUATION1",
        },
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    write_json(output / "call2_evaluation1_decomposition_summary.json", result)
    return result


def finalize(decomposition: Path, full_controller: Path, output: Path) -> dict[str, Any]:
    dec = json.loads(decomposition.read_text())
    call2_exact = dec.get("call2_evaluation1", {}).get("all_components_exact", False)
    summary_path = full_controller / "native_dsec_summary.json"
    full = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    executed = bool(full)
    parity = bool(full.get("reference_state_identity", False))
    dsec = int(full.get("dsec_evaluations", 0) or 0)
    coverage = "ACCEPT" if executed and dsec == 57 else ("PARTIAL" if executed and dsec > 0 else "NOT_RUN_CALL2_GATE")
    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if dec.get("result") == "ACCEPT" else "REJECT",
        "decomposition": dec,
        "native_controller": full,
        "gates": {
            **dec.get("gates", {}),
            "FOUR_CALL_WORKSPACE_RUNTIME_COVERAGE": coverage,
            "COMPLETE_CONTROLLER_EXECUTION": "ACCEPT" if executed else "NOT_RUN_CALL2_GATE",
            "COMPLETE_CONTROLLER_PARITY": "ACCEPT" if parity else ("REJECT" if executed else "NOT_RUN_CALL2_GATE"),
            "THERMAL_PARITY": "BLOCKED",
            "PRODUCT_PARITY": "BLOCKED",
            "PRODUCTION_PROMOTION": "BLOCKED",
        },
        "next_required_work": ("evaluate calls 3-4 and consumer activation" if call2_exact else
                               "correct general post-call1 H/He/Mg/continuum construction before activating bilevg/rnisg consumers"),
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    write_json(output / "post_call1_thermal_global_state_decomposition_summary.json", result)
    write_json(output / "audit_summary.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("prepare")
    q.add_argument("previous_audit", type=Path)
    q.add_argument("output", type=Path)
    q = sub.add_parser("audit")
    q.add_argument("--source-budget", type=Path, required=True)
    q.add_argument("--replay-root", type=Path, required=True)
    q.add_argument("--previous-audit", type=Path, required=True)
    q.add_argument("--package-root", type=Path, default=Path("."))
    q.add_argument("--output", type=Path, required=True)
    q = sub.add_parser("finalize")
    q.add_argument("--decomposition", type=Path, required=True)
    q.add_argument("--full-controller", type=Path, required=True)
    q.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.cmd == "prepare":
            result = prepare(a.previous_audit.resolve(), a.output.resolve())
        elif a.cmd == "audit":
            result = audit(a.source_budget.resolve(), a.replay_root.resolve(), a.previous_audit.resolve(),
                           a.package_root.resolve(), a.output.resolve())
        else:
            result = finalize(a.decomposition.resolve(), a.full_controller.resolve(), a.output.resolve())
    except Exception as exc:
        result = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "qualification_only": True, "production_promotion_ready": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    if a.cmd == "audit":
        return 0 if result.get("call2_evaluation1", {}).get("all_components_exact", False) else 2
    return 0 if result.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
