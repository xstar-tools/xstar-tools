from __future__ import annotations

import csv
import gzip
import json
import subprocess
import sys
from pathlib import Path

from xstar_tools.xstar import all61_dense_matrix_causal_attribution as causal

ROOT = Path(__file__).resolve().parents[1]


def test_indexed_performance_contract_accepts() -> None:
    report = causal.indexed_performance_self_test()
    assert report["result"] == "ACCEPT", report
    assert report["term_sequence_equivalence"] is True
    assert report["identity_check_reduction_factor"] >= 50.0
    assert report["indexed_identity_checks"] < report["full_identity_checks_baseline"]


def test_large_record_output_is_compressed_and_streamed() -> None:
    source = (ROOT / "src/xstar_tools/xstar/all61_dense_matrix_causal_attribution.py").read_text()
    assert causal.RECORD_NAME.endswith(".csv.gz")
    assert "cell_writer.writerows(local_cells)" in source
    assert "record_writer.writerows(local_records)" in source
    assert "def _atomic_csv_writer" in source
    assert "relevant_identities = sorted" in source


def test_atomic_gzip_writer_publishes_valid_csv(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv.gz"
    with causal._atomic_csv_writer(path, ["a", "b"], gzip_output=True) as writer:
        writer.writerow({"a": 1, "b": 2})
        writer.writerow({"a": 3, "b": 4})
    with gzip.open(path, "rt", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
    assert not path.with_name(path.name + ".tmp").exists()


def test_resume_runner_never_replays_source_or_native() -> None:
    runner = ROOT / "run_v04874691_indexed_causal_attribution_resume.sh"
    text = runner.read_text()
    assert "RESUME_ONLY_NO_SOURCE_OR_NATIVE_REPLAY=1" in text
    assert "xstar_cpp run-fixed-evaluation" not in text
    assert "v0472_all61_post_seed_system_capture capture" not in text
    assert "source_capture_replayed=false" in text
    assert "native_replay_replayed=false" in text


def test_release_readiness_accepts(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_v04874691_indexed_causal_attribution_readiness.py"),
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
    assert report["indexed_performance_self_test"]["identity_check_reduction_factor"] >= 50.0


def test_checker_accepts_completed_performance_milestone(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    audit.mkdir()
    summary = {
        "release": causal.RELEASE,
        "result": "ACCEPT",
        "scientific_result": "REJECT",
        "errors": [],
        "source_systems": 1,
        "causal_cell_rows_written": 1,
        "causal_record_rows_written": 1,
        "indexed_attribution_metrics": {
            "identity_check_reduction_factor": 100.0,
            "performance_gate_exact": True,
        },
        "gates": {
            "V064874691_INDEXED_CAUSAL_ATTRIBUTION_PERFORMANCE": "ACCEPT",
            "V06487469_DENSE_MATRIX_CAUSAL_ATTRIBUTION": "REJECT",
        },
    }
    (audit / causal.SUMMARY_NAME).write_text(json.dumps(summary))
    for name, fields, row in (
        (causal.SYSTEM_NAME, causal.SYSTEM_FIELDS, {field: 0 for field in causal.SYSTEM_FIELDS}),
        (causal.CELL_NAME, causal.CELL_FIELDS, {field: 0 for field in causal.CELL_FIELDS}),
    ):
        with (audit / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow(row)
    with gzip.open(audit / causal.RECORD_NAME, "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=causal.RECORD_FIELDS)
        writer.writeheader()
        writer.writerow({field: 0 for field in causal.RECORD_FIELDS})
    output = tmp_path / "checker.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_v04874691_indexed_causal_attribution.py"),
            "--audit-output",
            str(audit),
            "--output-json",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT"
    assert report["scientific_result"] == "REJECT"
