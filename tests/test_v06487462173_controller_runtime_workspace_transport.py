from pathlib import Path


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_release_version_and_runner_revision():
    text=(root()/"run_v048746217_canonical_thermal_controller_parity.sh").read_text()
    assert "source-faithful-type51-post-closure-thermal-v6" in text
    assert '--runtime-state-workspace-dir "$RUNTIME_WORKSPACES"' in text


def test_controller_restores_source_faithful_type50_and_type99_contracts():
    text=(root()/"run_v048746217_canonical_thermal_controller_parity.sh").read_text()
    for token in (
        "XSTAR_QUALIFICATION_HYDROGEN_TYPE50_ESCAPE_STATE=1",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ESCAPE_STATE=1",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_ENERGY_TRANSPORT=1",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_PRIMARY_COOLING_REDUCTION=1",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PRIMARY_COOLING_REDUCTION=1",
        "XSTAR_QUALIFICATION_MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_REDUCTION=1",
    ):
        assert token in text
    command_section = text.split("set +e", 1)[1].split("CONTROLLER_RC=$?", 1)[0]
    assert "--mg-primary-budget-csv" not in command_section
    assert "--call1-thermal-budget-csv" not in command_section


def test_standalone_binds_sequence_workspace_and_line_tau_paths():
    text=(root()/"src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "read_runtime_state_workspaces" in text
    assert "runtime-state workspace inventory does not cover all 61" in text
    assert 'setenv("XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_TAU_IN_BIN"' in text
    assert 'setenv("XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_TAU_OUT_BIN"' in text
    assert "sequence_runtime_workspace_evaluations" in text


def test_sequence_dependent_engine_state_is_not_process_static():
    text=(root()/"src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text()
    assert "static thread_local HydrogenType50EscapeStateV04874618 state" in text
    assert "static thread_local MagnesiumType50EscapeStateV04874619 state" in text
    assert "std::map<int, MagnesiumType99PrimaryCoolingStateV04874620> states" in text
    assert "std::map<int, MagnesiumPrimaryCoolingOrderStateV048746202> states" in text


def test_runtime_workspace_transport_executes_all_61_sequences(tmp_path: Path):
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
            "--skip-fits", "--output-dir", str(output),
        ],
        cwd=package,
        capture_output=True,
        text=True,
    )
    assert process.returncode in {0, 20}, process.stdout + process.stderr
    report = json.loads((output / "native_dsec_summary.json").read_text())
    assert report["total_evaluations"] == 61
    assert report["runtime_state_workspace_evaluations"] == 61
    assert report["sequence_runtime_workspace_evaluations"] == 61
    assert report["call_start_workspace_evaluations"] == 0
    assert report["python_callbacks"] == 0
