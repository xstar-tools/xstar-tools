from pathlib import Path
import csv
import subprocess
import sys


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open('w', newline='', encoding='utf-8') as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def test_mg_ca_sourcecode_first_validation_reports_xi_invariance(tmp_path):
    root = tmp_path / 'results'
    # Two Mg XI solver directories with identical solver summaries but changing XSTAR target.
    for tag, target_f in [('mg11_xi1p5_ne1e8', 0.7), ('mg11_xi2_ne1e8', 0.5)]:
        d = root / f'{tag}_xstar_like_element_solver_v03111_superlevels'
        d.mkdir(parents=True)
        (d / 'xstar_detail_population_comparison_summary.json').write_text(
            '{"f_fraction":0.8,"i_fraction":0.1,"r_fraction":0.1,"R":8,"G":9}', encoding='utf-8'
        )
        _write_csv(root / 'xstar_test_run' / tag / 'xstar_mg11_triplet_lines.csv', [
            {'upper_level':'1s1.2s1.3S_1','emit_outward':target_f, 'depth_inward':0},
            {'upper_level':'1s1.2p1.3P_1','emit_outward':0.1, 'depth_inward':0},
            {'upper_level':'1s1.2p1.1P_1','emit_outward':0.2, 'depth_inward':0},
        ])
    out = tmp_path / 'out'
    script = Path(__file__).resolve().parents[1] / 'examples' / '48_sourcecode_first_mg_ca_validation.py'
    subprocess.run([
        sys.executable, str(script), '--results-root', str(root), '--out-dir', str(out), '--print-summary'
    ], check=True, text=True)
    text = (out / 'mg_ca_sourcecode_first_validation.md').read_text(encoding='utf-8')
    assert 'do not choose empirical best scale' in text.lower()
    rows = list(csv.DictReader((out / 'mg_ca_xi_invariance_audit.csv').open(encoding='utf-8')))
    assert rows and rows[0]['diagnosis'] == 'solver_state_xi_invariant_but_xstar_target_varies'
