from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from xstar_tools.xstar.continuum_refresh_payload_audit import (
    PAYLOAD_ARRAYS,
    _heatf_residual,
    _sha_array,
    audit,
    verify_payload_bundle,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_source_heatf_residual_is_exact_for_all_call1_rows() -> None:
    benchmark = _root() / "src/xstar_tools/benchmarks/v0648722_call1_thermal_refresh_reference"
    with (benchmark / "v0472_call1_thermal_budget.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 21
    assert all(
        _heatf_residual(float(row["httot"]), float(row["cltot"])) == float(row["hmctot"])
        for row in rows
    )


def test_offline_causal_audit_localizes_element_and_mg_blockers(tmp_path: Path) -> None:
    root = _root()
    benchmark = root / "src/xstar_tools/benchmarks/v0648722_call1_thermal_refresh_reference"
    result = audit(root, None, benchmark, tmp_path)
    assert result["result"] == "ACCEPT"
    gates = result["gates"]
    assert gates["source_heatf_residual_formula"] == "ACCEPT"
    assert gates["continuum_only_complete_fix"] == "RULED_OUT"
    assert gates["element_thermal_scale_blocker"] == "ACCEPT"
    assert gates["magnesium_absolute_scale_blocker"] == "ACCEPT"
    assert gates["between_call_workspace_identity"] == "ACCEPT"
    assert gates["between_call_workspace_payload"] == "RUN_REQUIRED"
    evaluation4 = result["call1_causality"]["evaluation4"]
    assert not evaluation4["continuum_only_double_divide"]
    assert evaluation4["element_only_double_divide"]
    assert result["call1_causality"]["native_to_source_mg_absolute_scale_ratio"] > 1.0e5


def test_payload_verifier_accepts_four_exact_call_payloads(tmp_path: Path) -> None:
    payload_dir = tmp_path / "call_start_payloads"
    payload_dir.mkdir()
    fields = ["dsec_call_id"] + [name + "_sha256" for name in PAYLOAD_ARRAYS]
    rows = []
    for call_id in range(1, 5):
        payload = {
            name: np.asarray([call_id, index + 0.25], dtype=np.float64)
            for index, name in enumerate(PAYLOAD_ARRAYS)
        }
        np.savez_compressed(payload_dir / f"call_{call_id}.npz", **payload)
        row = {"dsec_call_id": call_id}
        row.update({name + "_sha256": _sha_array(payload[name]) for name in PAYLOAD_ARRAYS})
        rows.append(row)
    with (tmp_path / "v0472_between_call_state_fingerprints.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    result = verify_payload_bundle(tmp_path)
    assert result["status"] == "ACCEPT"
    assert result["captured"]
    assert result["calls"] == 4
    assert not result["errors"]


def test_native_source_contains_literal_heatf_residual_and_prefix_mode() -> None:
    root = _root()
    engine = (root / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    standalone = (root / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "kHeatfResidualFactor" in engine
    assert "kHeatfResidualFloor" in engine
    assert "legacy_hmctot" in engine
    assert "native_compton_heating" in engine
    assert "--controller-prefix-evaluations" in standalone


def test_payload_probe_compiles_and_streams_four_npz_files() -> None:
    from xstar_tools.xstar import v0472_continuum_refresh_payload_capture as capture

    compile(capture._PROBE, "<v048722-probe>", "exec")
    assert "np.savez_compressed" in capture._PROBE
    assert "payload_files" in capture._PROBE
    assert "retain_fixed_state_results = False" not in capture._PROBE


def test_release_version() -> None:
    import xstar_tools

    assert xstar_tools.__version__ == "0.6.48.7.46.9.6"
