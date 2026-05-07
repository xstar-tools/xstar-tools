from pathlib import Path
import csv
import subprocess
import sys


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_detail_population_compare_solver_only(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / 'solver_out'
    full = out / 'xstar_like_element_solver_full_global_normalized_solve_comparison.csv'
    _write_csv(full, [
        {
            'row_kind': 'summary',
            'comparison_case': 'full_global_xstar_tau0_calc_emis_ion',
            'f_fraction': '0.8046715',
            'i_fraction': '0.0072326',
            'r_fraction': '0.1880959',
            'R': '111.256',
            'G': '4.31644',
            'l2_distance_to_target': '0.00394',
        },
        {
            'row_kind': 'population',
            'comparison_case': 'full_global_normalized_proxy_topology_solve',
            'global_index': '33',
            'ion_stage': '5',
            'level_index': '1',
            'level_label': '1s2.1S_0',
            'level_kind': 'spectroscopic',
            'population_fraction': '0.9785',
            'xstar_xileve_emissivity_population': '0.9785',
        },
    ])
    _write_csv(out / 'xstar_like_element_solver_global_index.csv', [
        {
            'global_index': '33',
            'ion_stage': '5',
            'level_index': '1',
            'level_kind': 'spectroscopic',
            'configuration': '1s2.1S_0',
            'level_label': '1s2.1S_0',
        }
    ])

    cmd = [
        sys.executable,
        str(root / 'examples' / '43_compare_xstar_detail_populations.py'),
        '--solver-out-dir', str(out),
        '--print-summary',
    ]
    result = subprocess.run(cmd, cwd=root, text=True, capture_output=True, check=True)
    assert 'full_global_xstar_tau0_calc_emis_ion' in result.stdout
    assert (out / 'xstar_detail_population_comparison.csv').exists()
    assert (out / 'xstar_detail_population_comparison_summary.json').exists()
    assert (out / 'xstar_detail_population_comparison.md').exists()
