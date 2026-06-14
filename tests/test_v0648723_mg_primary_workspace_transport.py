from pathlib import Path
import csv
import json
import numpy as np

from xstar_tools.xstar.mg_primary_workspace_transport_audit import ARRAYS, audit, prepare

ROOT = Path(__file__).resolve().parents[1]


def test_fixed_state_runtime_contract_and_mg_correction_present() -> None:
    header = (ROOT / "src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h").read_text()
    engine = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    for field in ("global_xilevg", "global_bilevg", "global_rnisg", "mg_primary_heating_override"):
        assert field in header
    assert "XSTAR_QUALIFICATION_MG_PRIMARY_THERMAL_CORRECTION" in engine
    assert "element_heating *= element.abundance" in engine
    assert "--call-start-workspace-dir" in standalone
    assert "--mg-primary-budget-csv" in standalone
    assert "native_runtime_state_transport.csv" in standalone
    assert "call_start_workspace_applied" in standalone


def test_lowerer_serializes_global_level_index() -> None:
    text = (ROOT / "src/xstar_tools/xstar/native_fixed_program.py").read_text()
    assert "global_level_index_by_key" in text
    assert '"global_level_index"' in text


def _write_capture(root: Path) -> Path:
    capture = root / "capture" / "original_payload_capture" / "call_start_payloads"
    capture.mkdir(parents=True)
    for call in range(1, 5):
        np.savez(
            capture / f"call_{call}.npz",
            **{name: np.arange(call + 1, dtype=np.float64) for name in ARRAYS},
        )
    budget = root / "capture" / "original_payload_capture" / "v0472_call1_thermal_budget.csv"
    with budget.open("w", newline="") as handle:
        fields = (
            "dsec_call_id",
            "dsec_local_evaluation_index",
            "mg_heating",
            "mg_cooling",
            "mg_heating2",
            "mg_cooling2",
        )
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(1, 22):
            writer.writerow(
                {
                    "dsec_call_id": 1,
                    "dsec_local_evaluation_index": index,
                    "mg_heating": index,
                    "mg_cooling": index + 1,
                    "mg_heating2": index + 2,
                    "mg_cooling2": index + 3,
                }
            )
    return root / "capture"


def test_payload_prepare_writes_four_call_binary_contract(tmp_path: Path) -> None:
    capture = _write_capture(tmp_path)
    result = prepare(capture, tmp_path / "out")
    assert result["result"] == "ACCEPT"
    assert result["payload_calls"] == 4
    assert result["mg_budget_rows"] == 21
    for call in range(1, 5):
        for name in ARRAYS:
            assert (tmp_path / "out" / "call_start_workspace_bin" / f"call_{call}_{name}.bin").is_file()


def _write_native_output(root: Path, *, runtime_transport: bool) -> Path:
    native = root / "native"
    native.mkdir()
    fields = [
        "sequence",
        "kind",
        "call_index",
        "evaluation_index",
        "mg_heating",
        "mg_cooling",
        "mg_heating2",
        "mg_cooling2",
    ]
    with (native / "native_thermal_budget.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(1, 8):
            writer.writerow(
                {
                    "sequence": index,
                    "kind": "dsec",
                    "call_index": 1,
                    "evaluation_index": index,
                    "mg_heating": index,
                    "mg_cooling": index + 1,
                    "mg_heating2": index + 2,
                    "mg_cooling2": index + 3,
                }
            )
    if runtime_transport:
        with (native / "native_runtime_state_transport.csv").open("w", newline="") as handle:
            fields = [
                "sequence",
                "kind",
                "call_index",
                "evaluation_index",
                "call_start_workspace_applied",
                "mg_primary_override_applied",
                "radiation_bins",
                "continuum_tau_count",
                "global_level_count",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index in range(1, 8):
                writer.writerow(
                    {
                        "sequence": index,
                        "kind": "dsec",
                        "call_index": 1,
                        "evaluation_index": index,
                        "call_start_workspace_applied": 1,
                        "mg_primary_override_applied": 1,
                        "radiation_bins": 2,
                        "continuum_tau_count": 2,
                        "global_level_count": 2,
                    }
                )
    return native


def test_audit_requires_runtime_application_not_only_payload_files(tmp_path: Path) -> None:
    capture = _write_capture(tmp_path)
    output = tmp_path / "out"
    prepare(capture, output)
    native = _write_native_output(tmp_path, runtime_transport=False)
    result = audit(ROOT, capture, native, output)
    assert result["result"] == "REJECT"
    assert result["gates"]["five_workspace_transport"] == "REJECT"


def test_audit_accepts_bounded_runtime_application_and_leaves_controller_external(tmp_path: Path) -> None:
    capture = _write_capture(tmp_path)
    output = tmp_path / "out"
    prepare(capture, output)
    native = _write_native_output(tmp_path, runtime_transport=True)
    result = audit(ROOT, capture, native, output)
    assert result["result"] == "ACCEPT"
    assert result["gates"]["mg_primary_thermal_construction"] == "ACCEPT"
    assert result["gates"]["five_workspace_transport"] == "ACCEPT"
    assert result["gates"]["four_call_workspace_runtime_coverage"] == "RUN_REQUIRED"
    assert result["gates"]["complete_controller_execution"] == "RUN_REQUIRED"
