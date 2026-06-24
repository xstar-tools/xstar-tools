from __future__ import annotations

import csv
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREPARER = ROOT / "prepare_v048746251_runtime_assets.py"
FIXTURE_CASE = ROOT / "src/xstar_tools/benchmarks/v06485_active_family_phase2_fixture"
TRAJECTORY = ROOT / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/trajectory.csv"
ATDB_STANDIN = ROOT / "src/xstar_tools/benchmarks/v064874625_native_product_state/detail_baselines/xo01_detail.fits"
SUFFIXES = (
    "radiation_energy.bin", "bremsa.bin", "continuum_tau_in.bin", "continuum_tau_out.bin",
    "global_xilevg.bin", "global_bilevg.bin", "global_rnisg.bin",
)


def make_capture(root: Path) -> Path:
    capture = root / "capture"
    runtime = capture / "all61_input_workspaces"
    runtime.mkdir(parents=True)
    for name in (
        "v0472_all61_element_solve_rows.csv",
        "v0472_magnesium_type50_line_index_map.csv",
        "v0472_all61_magnesium_type50_endpoint_escape.csv",
        "v0472_magnesium_type50_endpoint_energy_map.csv",
        "v0472_all61_magnesium_type99_primary_thermal_ledger.csv",
        "v0472_all61_magnesium_primary_cooling_source_order_ledger.csv",
    ):
        (capture / name).write_text("header\n")
    with (capture / "v0472_all61_input_states.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("kind", "dsec_call_id", "sequence"))
        writer.writeheader()
        for call in range(1, 5):
            writer.writerow({"kind": "dsec", "dsec_call_id": call, "sequence": call})
    for sequence in range(1, 62):
        evaluation = runtime / f"evaluation_{sequence:04d}"
        evaluation.mkdir()
        if sequence <= 4:
            for suffix in SUFFIXES:
                (evaluation / f"call_{sequence}_{suffix}").write_bytes(struct.pack("d", float(sequence)))
    return runtime


def test_makefile_links_emissivity_directly() -> None:
    text = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    assert "$(EMISSIVITY_TARGET) $(THERMAL_TARGET)" in text
    assert "-lxstar_fixed_state -lxstar_emissivity -lxstar_thermal" in text


def test_runtime_asset_preparer_derives_call_start(tmp_path: Path) -> None:
    runtime = make_capture(tmp_path)
    out = tmp_path / "out"
    report = tmp_path / "report.json"
    env_file = tmp_path / "assets.env"
    env = os.environ.copy()
    env["XSTAR_V048746251_NATIVE_CASE_DIR"] = str(FIXTURE_CASE)
    env["XSTAR_V048746251_TRAJECTORY_CSV"] = str(TRAJECTORY)
    proc = subprocess.run(
        [
            sys.executable, str(PREPARER), "--package-dir", str(ROOT),
            "--atdb-path", str(ATDB_STANDIN), "--output-dir", str(out),
            "--runtime-state-workspace-dir", str(runtime),
            "--output-json", str(report), "--output-env", str(env_file),
        ],
        env=env,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(report.read_text())
    assert data["result"] == "ACCEPT"
    assert data["public_oracle_bytes_read"] == 0
    call_start = Path(data["call_start_workspaces"])
    assert len(list(call_start.glob("*.bin"))) == 28
    assert not data["call_start_missing_files"]


def test_readiness_checker_accepts(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_v048746251_native_public_product_runtime_asset_closure_readiness.py"),
            "--package-dir", str(ROOT), "--output-json", str(output),
        ],
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(output.read_text())["result"] == "ACCEPT"
