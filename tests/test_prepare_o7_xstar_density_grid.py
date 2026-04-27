import csv
import subprocess
import sys
from pathlib import Path


def test_prepare_o7_xstar_density_grid_writes_commands(tmp_path):
    script = Path('examples/23_prepare_o7_xstar_density_grid.py')
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            '--root',
            str(tmp_path),
            '--densities',
            '1',
            '1e4',
            '--print-summary',
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert 'Prepared O VII XSTAR density-grid run plan' in result.stdout

    mapping = tmp_path / 'xstar_o7_density_grid_references.csv'
    summary = tmp_path / 'xstar_runs/o7_density_grid_run_plan.csv'
    readme = tmp_path / 'xstar_runs/README_o7_density_grid.md'
    assert mapping.exists()
    assert summary.exists()
    assert readme.exists()

    rows = list(csv.DictReader(mapping.open(newline='', encoding='utf-8')))
    assert [r['electron_density_cm^-3'] for r in rows] == ['1', '10000']
    assert rows[0]['xstar_lines_csv'] == 'xstar_test_run/o7_ne1/xstar_o7_triplet_lines.csv'
    assert rows[1]['xstar_lines_csv'] == 'xstar_test_run/o7_ne1e4/xstar_o7_triplet_lines.csv'

    run_script = tmp_path / 'xstar_runs/o7_ne1/run_xstar.sh'
    convert_script = tmp_path / 'xstar_runs/o7_ne1/convert_o7_triplet.sh'
    assert run_script.exists()
    assert convert_script.exists()
    run_text = run_script.read_text(encoding='utf-8')
    convert_text = convert_script.read_text(encoding='utf-8')
    assert "density=1" in run_text
    assert "rlogxi=1.5" in run_text
    assert "oabund=1" in run_text
    assert "--ion \"O VII\"" in convert_text
    assert "--wavelength-min 21.5" in convert_text

    readme_text = readme.read_text(encoding='utf-8')
    assert 'Full command in that script' in readme_text
    assert 'examples/22_o7_solver_source_fit_density_xstar_grid.py' in readme_text
