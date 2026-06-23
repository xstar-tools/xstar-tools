from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_tools.xstar.source_order_electron_controller_closure_v048746227 import (
    audit,
    residual_value,
)

ROOT = Path(__file__).resolve().parents[1]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_release_version_and_abi_retained() -> None:
    assert 'version = "0.6.48.7.46.21.17"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "0.6.48.7.46.21.17"' in (
        ROOT / "src/xstar_tools/__init__.py"
    ).read_text()
    assert "XSTAR_API_ABI_VERSION 60487u" in (
        ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h"
    ).read_text()
    assert "XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60487u" in (
        ROOT / "src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h"
    ).read_text()


def test_source_order_global_electron_accumulator_replaces_element_subtotal() -> None:
    text = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "element_electron_fraction" not in text
    represented = text.index("computed_electron_fraction + source_term")
    stripped = text.index("computed_electron_fraction + fully_stripped_term")
    assert represented < stripped
    assert text.count("volatile double next_electron_fraction") == 2
    assert "volatile double weighted_fraction" in text
    assert "volatile double source_term" in text


def test_canonical_e7_zero_floor_and_raw_e10_diagnostics_retained() -> None:
    text = (
        ROOT / "src/xstar_tools/xstar/canonical_thermal_controller_parity_v048746217.py"
    ).read_text()
    assert 'format(numeric, ".7e")' in text
    assert "abs(numeric) < 1.0e-30" in text
    assert 'format(numeric, ".10e")' in text


def test_focused_residual_schema_accepts_both_names() -> None:
    assert residual_value({"elcter": "3.5"}) == 3.5
    assert residual_value({"charge_residual": "3.5"}) == 3.5


def test_focused_required_gates_accept_synthetic_exact_closure(tmp_path: Path) -> None:
    source = tmp_path / "source"
    evaluations = tmp_path / "evaluations"
    controller = tmp_path / "controller"
    output = tmp_path / "output"

    residual = 3.5395526509773845e-09
    secant_xee = 1.2003632957721315
    hmctot = -0.0038913671499111627

    write_csv(
        source / "v0472_all61_thermal_budget.csv",
        [{"sequence": 4, "elcter": residual}],
    )
    write_csv(
        source / "v0472_dsec_thermal_trace.csv",
        [
            {
                "dsec_call_id": 1,
                "dsec_local_evaluation_index": 4,
                "electron_fraction_xee": secant_xee,
                "elcter": residual,
                "hmctot": -1.0,
            },
            {
                "dsec_call_id": 3,
                "dsec_local_evaluation_index": 6,
                "electron_fraction_xee": secant_xee,
                "elcter": 0.0,
                "hmctot": hmctot,
            },
        ],
    )
    write_csv(
        evaluations / "evaluation_0004/native_thermal_budget.csv",
        [{"charge_residual": residual}],
    )
    write_csv(
        controller / "native_dsec_trajectory.csv",
        [
            {
                "kind": "dsec",
                "call_index": 1,
                "evaluation_index": 4,
                "electron_fraction_input": secant_xee,
                "charge_residual": residual,
                "hmctot": -1.0,
            },
            {
                "kind": "dsec",
                "call_index": 3,
                "evaluation_index": 6,
                "electron_fraction_input": secant_xee,
                "charge_residual": 0.0,
                "hmctot": hmctot + 5.0e-15,
            },
        ],
    )
    write_csv(
        controller / "native_dsec_controller_events.csv",
        [
            {
                "call_index": 1,
                "evaluation_index": 4,
                "event_name": "after_evaluation",
                "elcter": residual,
                "hmctot": -1.0,
            },
            {
                "call_index": 3,
                "evaluation_index": 6,
                "event_name": "after_evaluation",
                "elcter": 0.0,
                "hmctot": hmctot + 5.0e-15,
            },
        ],
    )
    output.mkdir()
    (output / "v048746217_thermal_controller_report.json").write_text(
        json.dumps(
            {
                "canonical_digits_after_decimal": 7,
                "canonical_zero_floor": 1.0e-30,
                "rejected_differences": 0,
                "gates": {"REJECTED_SCIENTIFIC_DIFFERENCES_ZERO": "ACCEPT"},
            }
        )
    )

    report = audit(source, evaluations, controller, output)
    assert report["result"] == "ACCEPT"
    for gate in (
        "SEQUENCE4_FIXED_ELCTER_BIT_EXACT",
        "CALL1_CHARGE_SECANT_XEE_BIT_EXACT",
        "SEQUENCE4_CONTROLLER_RESIDUAL_BIT_EXACT",
        "CALL3_EVALUATION6_HMCTOT_IEEE_E7",
        "FOCUSED_AUDIT_SCHEMA_COMPATIBLE",
        "REJECTED_SCIENTIFIC_DIFFERENCES_ZERO",
    ):
        assert report["gates"][gate] == "ACCEPT"


def test_runner_preserves_fresh_case_contracts_and_shared_case() -> None:
    text = (ROOT / "run_v048746227_source_order_electron_controller_closure.sh").read_text()
    assert text.count("xstar_tools.xstar.native_fixed_program lower-atdb") == 1
    for module in (
        "type57_case_contract_v0487462201",
        "type53_leveltemp_case_contract_v048746221",
        "type49_leveltemp_case_contract_v048746222",
        "type99_leveltemp_case_contract_v048746223",
    ):
        assert text.count(module) == 1
    assert 'run_v048746227_native_fixed_replay.sh "$SOURCE_CAPTURE" "$CASE"' in text
    assert 'XSTAR_V048746217_NATIVE_CASE_DIR="$CASE"' in text
    assert "$BASE13/native_case_all61" not in text
