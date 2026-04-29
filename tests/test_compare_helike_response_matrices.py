import csv
import json
import subprocess
import sys
from pathlib import Path


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _make_fit(run: Path, tag: str, density: str, combined: bool):
    fit = run / f'fit_ne_{density}'
    fit.mkdir(parents=True)
    prefix = tag.split('_')[0]
    summary = {
        'element': 'O' if prefix == 'o7' else 'C',
        'ion_stage': 7 if prefix == 'o7' else 5,
        'electron_density_cm^-3': float(density.replace('e', 'E')),
        'xstar_reference': {'R_f_over_i': 2.0, 'G_f_plus_i_over_r': 3.0},
        'target_components_normalized': {'forbidden': 0.5, 'intercombination': 0.25, 'resonance': 0.25},
        'uniform_prediction': {'R_f_over_i': 1.0, 'G_f_plus_i_over_r': 1.0},
        'fitted_prediction': {'R_f_over_i': 2.0, 'G_f_plus_i_over_r': 3.0, 'fit_info': {'objective': 1e-12}},
        'combined_source_validation': {
            'R_f_over_i': 2.0 if combined else None,
            'G_f_plus_i_over_r': 3.0 if combined else None,
            'R_over_xstar': 1.0 if combined else None,
            'G_over_xstar': 1.0 if combined else None,
            'solver_diagnostics': {'matrix_rank': 3, 'matrix_size': 4, 'linear_residual_l2': 1e-6 if combined else 9.0, 'linear_residual_linf': 1e-6},
        },
    }
    (fit / f'{prefix}_solver_source_fit_summary.json').write_text(json.dumps(summary))
    _write_csv(fit / f'{prefix}_solver_response_matrix.csv', [
        {'source_level': 2, 'raw_forbidden': 1, 'raw_intercombination': 0, 'raw_resonance': 0},
        {'source_level': 3, 'raw_forbidden': 0, 'raw_intercombination': 1, 'raw_resonance': 0},
        {'source_level': 4, 'raw_forbidden': 0, 'raw_intercombination': 0, 'raw_resonance': 1},
    ])
    _write_csv(fit / f'{prefix}_solver_source_fit_weights.csv', [
        {'source_level': 2, 'fit_weight_norm': 0.5},
        {'source_level': 3, 'fit_weight_norm': 0.25},
        {'source_level': 4, 'fit_weight_norm': 0.25},
    ])


def test_compare_helike_response_matrices(tmp_path: Path):
    good = tmp_path / 'o7_solver_source_fit_density_xstar_grid_type69_suppressed'
    bad = tmp_path / 'c5_solver_source_fit_density_xstar_grid'
    _make_fit(good, 'o7', '1', True)
    _make_fit(bad, 'c5', '1', False)
    out = tmp_path / 'out'
    script = Path(__file__).resolve().parents[1] / 'examples' / '35_compare_helike_response_matrices.py'
    res = subprocess.run([sys.executable, str(script), str(good), str(bad), '--out-dir', str(out), '--print-summary'], check=True, text=True, capture_output=True)
    assert 'o7_suppressed: status=validated' in res.stdout
    assert 'c5: status=not_validated' in res.stdout
    assert (out / 'helike_response_matrix_comparison.md').exists()
    assert (out / 'helike_response_matrix_density_comparison.csv').exists()
