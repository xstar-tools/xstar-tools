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


def _write_summary(path: Path, r, g, x_r, x_g, components, weights_top=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'xstar_reference': {'R_f_over_i': x_r, 'G_f_plus_i_over_r': x_g, 'path': 'xstar.csv', 'target_label': 'target'},
        'target_components_normalized': {'forbidden': 0.1, 'intercombination': 0.2, 'resonance': 0.7},
        'fitted_prediction': {'R_f_over_i': r, 'G_f_plus_i_over_r': g, 'components': components, 'fit_info': {'status': 'converged', 'objective': 0.01}},
        'combined_source_validation': {
            'R_f_over_i': r,
            'G_f_plus_i_over_r': g,
            'triplet_components': {'forbidden': components['forbidden'], 'intercombination': components['intercombination'], 'resonance': components['resonance']},
            'solver_diagnostics': {'matrix_rank': 10, 'matrix_size': 10, 'solver': 'test'}
        },
    }
    path.write_text(json.dumps(data), encoding='utf-8')


def test_high_density_mismatch_diagnostic_without_atdb(tmp_path):
    grid = tmp_path / 'grid'
    rows = [
        {
            'electron_density_cm^-3': 1.0,
            'xstar_R_f_over_i': 4.8,
            'xstar_G_f_plus_i_over_r': 10.0,
            'fixed_ne1_R_f_over_i': 4.8,
            'fixed_ne1_G_f_plus_i_over_r': 10.0,
            'refitted_combined_R_f_over_i': 4.8,
            'refitted_combined_G_f_plus_i_over_r': 10.0,
            'refitted_combined_R_over_xstar': 1.0,
            'refitted_combined_G_over_xstar': 1.0,
            'target_reachable': True,
            'fit_success_vs_xstar': True,
            'fit_objective': 1e-12,
            'weight_delta_l1_vs_ne1': 0.0,
            'weight_delta_l2_vs_ne1': 0.0,
            'fit_dir': str(grid / 'fit_ne_1'),
        },
        {
            'electron_density_cm^-3': 1.0e12,
            'xstar_R_f_over_i': 0.08,
            'xstar_G_f_plus_i_over_r': 4.5,
            'fixed_ne1_R_f_over_i': 0.1,
            'fixed_ne1_G_f_plus_i_over_r': 2.2,
            'refitted_combined_R_f_over_i': 0.04,
            'refitted_combined_G_f_plus_i_over_r': 3.2,
            'refitted_combined_R_over_xstar': 0.5,
            'refitted_combined_G_over_xstar': 0.71,
            'target_reachable': False,
            'fit_success_vs_xstar': False,
            'fit_objective': 0.004,
            'weight_delta_l1_vs_ne1': 1.8,
            'weight_delta_l2_vs_ne1': 0.9,
            'fit_dir': str(grid / 'fit_ne_1e12'),
        },
    ]
    _write_csv(grid / 'o7_solver_source_fit_density_grid.csv', rows)
    (grid / 'o7_solver_source_fit_density_grid_summary.json').write_text(json.dumps({'density_summaries': []}), encoding='utf-8')
    _write_summary(grid / 'fit_ne_1' / 'o7_solver_source_fit_summary.json', 4.8, 10.0, 4.8, 10.0, {'forbidden': 0.6, 'intercombination': 0.125, 'resonance': 0.275})
    _write_summary(grid / 'fit_ne_1e12' / 'o7_solver_source_fit_summary.json', 0.04, 3.2, 0.08, 4.5, {'forbidden': 0.04, 'intercombination': 1.0, 'resonance': 0.325})
    _write_csv(grid / 'fit_ne_1' / 'o7_source_fit_weights.csv', [{'source_level': 2, 'fit_weight_norm': 0.5}, {'source_level': 17, 'fit_weight_norm': 0.5}])
    _write_csv(grid / 'fit_ne_1e12' / 'o7_source_fit_weights.csv', [{'source_level': 2, 'fit_weight_norm': 0.0}, {'source_level': 17, 'fit_weight_norm': 1.0}])

    out = tmp_path / 'diag'
    cmd = [
        sys.executable,
        'examples/24_o7_high_density_mismatch_diagnostics.py',
        '--density-grid-dir', str(grid),
        '--density', '1e12',
        '--reference-density', '1',
        '--out-dir', str(out),
        '--print-summary',
    ]
    result = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], check=True, text=True, capture_output=True)
    assert 'target reachable: False' in result.stdout
    summary = json.loads((out / 'o7_high_density_mismatch_summary.json').read_text())
    assert summary['refitted_prediction']['target_reachable'] is False
    assert summary['source_weight_collapse']['high_density_stats']['top1_level'] == 17
    assert (out / 'o7_high_density_component_mismatch.csv').exists()
    assert (out / 'o7_high_density_source_weight_changes.csv').exists()
