from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from xstar_tools.xstar import all61_dense_matrix_causal_attribution as causal

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_record_alignment_self_test_accepts() -> None:
    report = causal.canonical_record_alignment_self_test()
    assert report["result"] == "ACCEPT", report
    assert report["source_identity"] == report["native_identity"]
    assert report["source_ion_index"] != report["native_ion_index"]


def test_type53_live_radiation_contract_is_present() -> None:
    lowerer = (ROOT / "src/xstar_tools/xstar/native_fixed_program.py").read_text()
    native = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "derived.npconi2[rec]" in lowerer
    assert "payload_ints = [continuum_index]" in lowerer
    assert "record_context.continuum_index_one_based" in native
    assert "contract_ptmp1 = pescv_source(contract_tau_in)" in native
    assert "pescv_source(contract_tau_in + contract_tau_out)" in native
    assert "hydrogen type53 live-radiation transport requires canonical continuum index and tau workspaces" in native


def test_canonical_identity_excludes_noninvariant_ion_index() -> None:
    source = (ROOT / "src/xstar_tools/xstar/all61_dense_matrix_causal_attribution.py").read_text()
    assert "return (self.record, self.data_type, self.rate_type, self.ion_stage)" in source
    assert '"source_ion_index"' in source
    assert '"native_ion_index"' in source


def test_v92_runner_reuses_source_and_regenerates_native() -> None:
    runner = (ROOT / "run_v04874692_hydrogen_type53_live_radiation_and_canonical_alignment.sh").read_text()
    assert "v0472_all61_post_seed_system_capture capture" not in runner
    assert "xstar_cpp run-fixed-evaluation" in runner
    assert "source_capture_replayed=false" in runner
    assert "native_replay_replayed=true" in runner


def test_v92_readiness_accepts(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_v04874692_hydrogen_type53_live_radiation_readiness.py"),
            "--package-dir",
            str(ROOT),
            "--output-json",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT", report
    assert report["source_capture_replayed"] is False
    assert report["native_replay_required"] is True
