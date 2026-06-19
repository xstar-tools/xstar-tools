from __future__ import annotations

import csv
import json
from pathlib import Path

import xstar_tools
from xstar_tools.xstar import post_call1_thermal_global_state_decomposition as audit
from xstar_tools.xstar import v0472_full_dsec_thermal_budget_capture as capture


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def _budget(call: int, local: int, value: float = 1.0) -> dict[str, object]:
    row: dict[str, object] = {
        "global_evaluation_ordinal": 1, "dsec_call_id": call, "dsec_local_evaluation_index": local,
        "temperature_k": 64991.0, "temperature_t4": 6.4991, "electron_fraction_xee": 1.2,
        "hydrogen_density_cm3": 1e8, "hmctot": value, "elcter": value,
    }
    for fields in audit.ELEMENT_FIELDS.values():
        for field in fields: row[field] = value
    for field in audit.CONTINUUM_FIELDS: row[field] = value
    return row


def _native_budget(value: float) -> dict[str, object]:
    row: dict[str, object] = {"sequence": 1, "kind": "replay", "call_index": 2, "evaluation_index": 1}
    for fields in audit.ELEMENT_FIELDS.values():
        for field in fields: row[field] = value
    for field in audit.CONTINUUM_FIELDS: row[field] = value
    return row


def test_version_and_full_probe_contract() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.19.1"
    assert capture.BUDGET_NAME == "v0472_full_dsec_thermal_budget.csv"
    assert "retain the budget for every DSEC call" in capture._PROBE
    assert 'if call_id != 1:' not in capture._PROBE


def test_decomposition_separates_formula_gap_from_missing_consumers(tmp_path: Path) -> None:
    previous = tmp_path / "previous"
    previous.mkdir()
    (previous / "call1_parity_summary.json").write_text(json.dumps({
        "result": "ACCEPT", "gates": {"CALL1_CONTROLLER_TRAJECTORY": "ACCEPT"}
    }))
    source_rows = []
    for call, count in ((1, 21), (2, 1), (3, 18), (4, 17)):
        for local in range(1, count + 1):
            source_rows.append(_budget(call, local, 1.0))
    source = tmp_path / "source.csv"
    _write(source, source_rows)
    replay = tmp_path / "replays"
    for mode in audit.MODES:
        root = replay / f"replay_{mode.replace('-', '_')}"
        native_value = 2.0 if mode != "none" else 3.0
        _write(root / "native_thermal_budget.csv", [_native_budget(native_value)])
        _write(root / "native_evaluation.csv", [{
            "native_charge_residual": native_value,
            "native_hmctot": native_value,
            "replay_workspace_applied": 1,
        }])
    result = audit.audit(source, replay, previous, Path(__file__).parents[1], tmp_path / "out")
    assert result["result"] == "ACCEPT"
    assert result["call2_evaluation1"]["all_components_exact"] is False
    assert result["decomposition"]["xilevg_effect_observed"] is True
    assert result["decomposition"]["bilevg_effect_observed"] is False
    assert result["decomposition"]["rnisg_effect_observed"] is False
    assert result["decomposition"]["general_element_thermal_formula_blocker"] is True
    assert result["gates"]["CALLS_3_TO_4"] == "BLOCKED_BY_CALL2_EVALUATION1"


def test_cpp_replay_modes_are_published() -> None:
    root = Path(__file__).parents[1]
    text = (root / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    for token in ("--global-workspace-mode", "xilevg-bilevg", "xilevg-rnisg", "replay_workspace_applied"):
        assert token in text
