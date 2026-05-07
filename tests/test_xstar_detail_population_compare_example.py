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


def test_detail_population_compare_xstar_reference_depth_postprocess(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / 'solver_out'
    _write_csv(out / 'xstar_like_element_solver_full_global_normalized_solve_comparison.csv', [
        {
            'row_kind': 'summary',
            'comparison_case': 'full_global_xstar_tau0_calc_emis_ion',
            'f_fraction': '0.70',
            'i_fraction': '0.15',
            'r_fraction': '0.15',
        },
        {'row_kind': 'population', 'global_index': '0', 'ion_stage': '7', 'level_index': '1', 'population_fraction': '1'},
    ])
    _write_csv(out / 'xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv', [
        {'row_kind': 'calc_emis_ion_triplet_emergent_line', 'component': 'f', 'record': '1', 'wavelength_A': '22.1012', 'upper_level': '2', 'raw_pop_A_E_erg_s^-1': '0.70'},
        {'row_kind': 'calc_emis_ion_triplet_emergent_line', 'component': 'i', 'record': '2', 'wavelength_A': '21.8070', 'upper_level': '4', 'raw_pop_A_E_erg_s^-1': '0.15'},
        {'row_kind': 'calc_emis_ion_triplet_emergent_line', 'component': 'r', 'record': '3', 'wavelength_A': '21.6020', 'upper_level': '7', 'raw_pop_A_E_erg_s^-1': '0.15'},
    ])
    xstar = tmp_path / 'xstar_o7_triplet_lines.csv'
    _write_csv(xstar, [
        {'ion': 'o_vii', 'lower_level': '1s2.1S_0', 'upper_level': '1s1.2s1.3S_1', 'wavelength': '22.1012', 'emit_outward': '70', 'depth_inward': '0', 'depth_outward': '0'},
        {'ion': 'o_vii', 'lower_level': '1s2.1S_0', 'upper_level': '1s1.2p1.3P_1', 'wavelength': '21.8070', 'emit_outward': '15', 'depth_inward': '0', 'depth_outward': '0'},
        {'ion': 'o_vii', 'lower_level': '1s2.1S_0', 'upper_level': '1s1.2p1.1P_1', 'wavelength': '21.6020', 'emit_outward': '8', 'depth_inward': '6.9', 'depth_outward': '0'},
    ])
    cmd = [
        sys.executable,
        str(root / 'examples' / '43_compare_xstar_detail_populations.py'),
        '--solver-out-dir', str(out),
        '--element', 'O', '--he-like-stage', '7',
        '--comparison-case', 'full_global_xstar_reference_depth_emit_outward_calc_emis_ion',
        '--xstar-triplet-lines-csv', str(xstar),
        '--xstar-reference-depth-scale', '0.37',
        '--target-f', 'nan', '--target-i', 'nan', '--target-r', 'nan',
        '--print-summary',
    ]
    result = subprocess.run(cmd, cwd=root, text=True, capture_output=True, check=True)
    assert 'full_global_xstar_reference_depth_emit_outward_calc_emis_ion' in result.stdout
    assert (out / 'xstar_reference_depth_triplet_postprocess.csv').exists()
    assert (out / 'xstar_detail_population_comparison_summary.json').exists()
