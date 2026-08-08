from pathlib import Path


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_runner_enables_source_trajectory_guard():
    text = (root() / "run_v048746217_canonical_thermal_controller_parity.sh").read_text()
    assert "source-faithful-type51-post-closure-thermal-v6" in text
    assert "--source-trajectory-guard" in text


def test_analyzer_classifies_structured_prefix_as_reject():
    text = (root() / "src/xstar_tools/xstar/canonical_thermal_controller_parity_v048746217.py").read_text()
    assert '"result": "REJECT" if source_trajectory_diverged else "ACCEPT"' in text
    assert '"divergence_sequence": summary.get("divergence_sequence")' in text


def test_source_trajectory_guard_writes_prefix_outputs(tmp_path: Path):
    import csv
    import json
    import struct
    import subprocess

    package = root()
    trajectory = package / "tests/fixtures/historical/v0648_compiled_case_helike_type69_mg11_ne1e8/trajectory.csv"
    program = package / "tests/fixtures/historical/v06485_active_family_phase2_fixture"
    workspaces = tmp_path / "workspaces"
    for row in csv.DictReader(trajectory.open()):
        sequence = int(row["sequence"])
        call = int(row["call_index"])
        directory = workspaces / f"evaluation_{sequence:04d}"
        directory.mkdir(parents=True)
        prefix = f"call_{call}_"
        arrays = {
            "radiation_energy": [100.0 + i for i in range(64)],
            "bremsa": [1.0e-20] * 64,
            "continuum_tau_in": [0.0] * 64,
            "continuum_tau_out": [0.0] * 64,
            "global_xilevg": [1.0] * 128,
            "global_bilevg": [0.0] * 128,
            "global_rnisg": [0.0] * 128,
            "line_tau_in": [0.0],
            "line_tau_out": [0.0],
        }
        for name, values in arrays.items():
            (directory / f"{prefix}{name}.bin").write_bytes(
                struct.pack(f"{len(values)}d", *values)
            )
    output = tmp_path / "controller"
    process = subprocess.run(
        [
            str(package / "src/xstar_tools/xstar/cpp/xstar_cpp"), "run-fixed-dsec",
            "--case-dir", str(program),
            "--trajectory-csv", str(trajectory),
            "--runtime-state-workspace-dir", str(workspaces),
            "--source-trajectory-guard",
            "--skip-fits", "--output-dir", str(output),
        ],
        cwd=package,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 20, process.stdout + process.stderr
    report = json.loads((output / "native_dsec_summary.json").read_text())
    assert report["result"] == "REJECT"
    assert report["source_trajectory_diverged"] is True
    assert 2 <= report["divergence_sequence"] <= 61
    assert report["total_evaluations"] < 61
    assert report["python_callbacks"] == 0
    for name in (
        "native_dsec_trajectory.csv",
        "native_dsec_controller_events.csv",
        "native_dsec_call_summary.csv",
    ):
        assert (output / name).is_file()
