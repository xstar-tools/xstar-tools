from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_source_gate():
    checker = ROOT / 'tools/qualification/check_performance_foundation_0_6_82_31.py'
    p = subprocess.run([sys.executable, str(checker)], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'PERFORMANCE_FOUNDATION_068231_RESULT=ACCEPT' in p.stdout


def test_benchmark_prepare_contains_all_three_mandatory_cases(tmp_path):
    runner = ROOT / 'tools/qualification/run_performance_foundation_host_0_6_82_31.py'
    baseline = ROOT.parent / 'xstar_tools-0.6.82.30.8.14'
    p = subprocess.run([
        sys.executable, str(runner), 'prepare',
        '--candidate-package', str(ROOT),
        '--baseline-package', str(baseline),
        '--data-dir', str(tmp_path / 'unused-data'),
        '--output-root', str(tmp_path / 'out'),
        '--replace',
    ], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'c5_lowxi_cf0_em025_ne1e12' in p.stdout
    assert 'multi_element_xi1_ne1e12' in p.stdout
    assert 'fe_reference_ne1e8' in p.stdout
    assert 'PERFORMANCE_FOUNDATION_068231_RESULT=PREPARED' in p.stdout

    low = (tmp_path / 'out/params/c5_lowxi_cf0_em025_ne1e12.par').read_text()
    assert 'rlogxi,r,a,-3,' in low
    assert 'cfrac,r,h,0,' in low
    assert 'emult,r,h,0.25,' in low
    multi = (tmp_path / 'out/params/multi_element_xi1_ne1e12.par').read_text()
    assert 'rlogxi,r,a,1.0,' in multi
    assert 'density,r,a,1e12,' in multi
    assert 'feabund,r,h,1,' in multi
    assert 'niabund,r,h,1,' in multi


def test_science_and_abi_identifiers_remain_frozen():
    manifest = json.loads((ROOT / 'qualification/performance_foundation_0_6_82_31/performance_foundation_0_6_82_31.json').read_text())
    assert manifest['science_revision'] == '0.6.48.12.3.45.3.3.8'
    assert manifest['science_change'] is False
    assert manifest['c_api_abi'] == 60487
    assert manifest['production_zone_abi'] == 6048110
    assert manifest['fixed_state_abi'] == 60488


def test_type74_reduced_grid_path_is_not_rewritten_in_31():
    local = (ROOT / 'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    assert 'shared_reduced_v068231' not in local
    assert 'build_type99_reduced_radiation(\n                full_energy_ev, full_bremsa, full_bin_count,' in local


def test_fits_writer_is_hash_frozen():
    import hashlib
    manifest = json.loads((ROOT / 'qualification/performance_foundation_0_6_82_31/performance_foundation_0_6_82_31.json').read_text())
    path = ROOT / 'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['frozen_file_sha256'][str(path.relative_to(ROOT))]
