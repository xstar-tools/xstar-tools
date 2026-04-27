import csv
import json
import subprocess
import sys
from pathlib import Path


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_expanded_source_scan_dry_run(tmp_path):
    grid = tmp_path / 'grid'
    xstar = tmp_path / 'xstar_o7.csv'
    _write_csv(xstar, [{'ion': 'O VII', 'wavelength': 21.602, 'emit_outward': 1.0}])
    _write_csv(grid / 'o7_solver_source_fit_density_grid.csv', [
        {'electron_density_cm^-3': 1.0e12, 'xstar_lines_csv': str(xstar), 'xstar_value_column': 'emit_outward'}
    ])
    out = tmp_path / 'scan'
    cmd = [
        sys.executable,
        'examples/25_o7_high_density_expanded_source_scan.py',
        '--density-grid-dir', str(grid),
        '--density', '1e12',
        '--sets', 'baseline,custom',
        '--source-set', 'custom:2,3,4,5,7,8,9,10',
        '--dry-run',
        '--out-dir', str(out),
        '--print-summary',
    ]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], check=True, text=True, capture_output=True)
    assert 'Dry run' in result.stdout
    summary = json.loads((out / 'o7_high_density_expanded_source_scan_summary.json').read_text())
    assert summary['dry_run'] is True
    assert summary['n_source_sets'] == 2
    assert (out / 'o7_high_density_expanded_source_sets.csv').exists()
    rows = list(csv.DictReader((out / 'o7_high_density_expanded_source_scan.csv').open()))
    assert rows[0]['source_set'] == 'baseline'
