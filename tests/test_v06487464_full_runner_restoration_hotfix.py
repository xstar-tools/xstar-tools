from pathlib import Path
import subprocess


def test_v06487464_base_runner_is_complete():
    root = Path(__file__).resolve().parents[1]
    runner = root / "run_v048746_all61_post_seed_system_decomposition.sh"
    text = runner.read_text()
    assert runner.stat().st_size >= 6000
    assert len(text.splitlines()) >= 150
    for marker in (
        "v0472_all61_post_seed_system_capture capture",
        "native_fixed_program lower-atdb",
        "xstar_cpp run-fixed-evaluation",
        "all61_native_replay_aggregate",
        "all61_post_seed_system_decomposition",
    ):
        assert marker in text
    assert text.strip() != "#!/usr/bin/env bash\nexit 0"


def test_v06487464_runner_usage_guard():
    root = Path(__file__).resolve().parents[1]
    runner = root / "run_v048746_all61_post_seed_system_decomposition.sh"
    proc = subprocess.run([str(runner)], cwd=root, text=True, capture_output=True)
    assert proc.returncode == 64
    assert "usage:" in (proc.stdout + proc.stderr)


def test_v06487464_artifacts_present():
    root = Path(__file__).resolve().parents[1]
    for rel in (
        "run_v0487464_all61_post_seed_system_decomposition.sh",
        "check_v0487464_all61_post_seed_system_decomposition.py",
        "check_v0487464_all61_post_seed_system_decomposition_readiness.py",
        "V06487464_FULL_RUNNER_RESTORATION_HOTFIX.md",
    ):
        assert (root / rel).is_file(), rel
