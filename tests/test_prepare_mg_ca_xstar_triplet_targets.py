from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_prepare_mg_ca_xstar_triplet_targets_plan(tmp_path: Path) -> None:
    cmd = [
        sys.executable,
        str(ROOT / 'examples' / '47_prepare_mg_ca_xstar_triplet_targets.py'),
        '--root', str(tmp_path),
        '--rlogxi-grid', '2.5', '3.5',
        '--print-summary',
    ]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
    assert 'Prepared Mg XI / Ca XIX XSTAR triplet target plan' in result.stdout
    summary = tmp_path / 'xstar_runs' / 'mg_ca_triplet_target_plan.csv'
    readme = tmp_path / 'xstar_runs' / 'README_mg_ca_triplet_targets.md'
    assert summary.exists()
    assert readme.exists()
    rows = list(csv.DictReader(summary.open(newline='', encoding='utf-8')))
    assert len(rows) == 4
    assert {row['ion'] for row in rows} == {'Mg XI', 'Ca XIX'}
    for row in rows:
        assert (tmp_path / row['run_script']).exists()
        assert (tmp_path / row['convert_script']).exists()
        assert 'examples/42_xstar_like_element_solver_demo.py' in row['solver_command']
        assert '--xstar-triplet-lines-csv' in row['compare_command']
    text = readme.read_text(encoding='utf-8')
    assert 'Mg XI' in text and 'Ca XIX' in text
    assert '--element Mg --he-like-stage 11' in text
    assert '--element Ca --he-like-stage 19' in text
