import csv
import json
import subprocess
import sys
from pathlib import Path


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields=[]
    for row in rows:
        for k in row:
            if k not in fields:
                fields.append(k)
    with path.open('w', newline='') as fh:
        w=csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)


def test_source_basis_filter_example(tmp_path):
    run = tmp_path / 'c5_solver_source_fit_density_xstar_grid_v031'
    fit = run / 'fit_ne_1'
    fit.mkdir(parents=True)
    write_csv(fit / 'o7_solver_response_matrix.csv', [
        {'source_level': 2, 'raw_forbidden': 1.0, 'raw_intercombination': 0.0, 'raw_resonance': 0.0},
        {'source_level': 3, 'raw_forbidden': 0.0, 'raw_intercombination': 0.0, 'raw_resonance': 0.0},
        {'source_level': 4, 'raw_forbidden': -1.0, 'raw_intercombination': 1.0, 'raw_resonance': 0.0},
    ])
    write_csv(fit / 'o7_solver_source_fit_weights.csv', [
        {'source_level': 2, 'fit_weight_norm': 0.2},
        {'source_level': 3, 'fit_weight_norm': 0.5},
        {'source_level': 4, 'fit_weight_norm': 0.3},
    ])
    (fit / 'o7_solver_source_fit_summary.json').write_text(json.dumps({
        'element': 'C', 'ion_stage': 5, 'electron_density_cm^-3': 1,
        'target_components_normalized': {'forbidden': 1.0, 'intercombination': 0.0, 'resonance': 0.0},
        'xstar_reference': {'R_f_over_i': None, 'G_f_plus_i_over_r': None},
    }))
    out = tmp_path / 'out'
    cmd = [sys.executable, 'examples/37_filter_source_basis_response.py', str(run), '--out-dir', str(out), '--print-summary']
    subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], check=True)
    rows = list(csv.DictReader((out / 'helike_source_basis_filter_comparison.csv').open()))
    filters = {r['filter']: r for r in rows}
    assert 'positive_nonzero_response' in filters
    assert int(float(filters['positive_nonzero_response']['n_source_levels_kept'])) == 1
    assert float(filters['all']['original_fit_weight_on_zero_response']) == 0.5
    assert float(filters['all']['original_fit_weight_on_negative_response']) == 0.3
