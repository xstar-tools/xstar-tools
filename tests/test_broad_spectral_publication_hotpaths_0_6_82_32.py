from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_source_gate():
    checker = ROOT / 'tools/qualification/check_broad_spectral_publication_hotpaths_0_6_82_32.py'
    p = subprocess.run([sys.executable, str(checker)], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'BROAD_HOTPATH_068232_SOURCE_RESULT=ACCEPT' in p.stdout


def test_host_prepare_contains_all_three_anchors(tmp_path):
    runner = ROOT / 'tools/qualification/run_broad_spectral_publication_host_0_6_82_32.py'
    p = subprocess.run([
        sys.executable, str(runner), 'prepare',
        '--candidate-package', str(ROOT),
        '--baseline-package', str(ROOT.parent / 'xstar_tools-0.6.82.31'),
        '--data-dir', str(tmp_path / 'unused-data'),
        '--output-root', str(tmp_path / 'out'),
        '--replace',
    ], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'c5_lowxi_cf0_em025_ne1e12' in p.stdout
    assert 'multi_element_xi1_ne1e12' in p.stdout
    assert 'fe_reference_ne1e8' in p.stdout
    assert 'BROAD_HOTPATH_068232_RESULT=PREPARED' in p.stdout


def test_science_and_abi_identifiers_remain_frozen():
    manifest = json.loads((ROOT / 'qualification/broad_spectral_publication_0_6_82_32/broad_spectral_publication_0_6_82_32.json').read_text())
    assert manifest['science_revision'] == '0.6.48.12.3.45.3.3.8'
    assert manifest['science_change'] is False
    assert manifest['c_api_abi'] == 60487
    assert manifest['production_zone_abi'] == 6048110
    assert manifest['fixed_state_abi'] == 60488


def test_type50_cache_only_prepares_first_nbinc_geometry():
    opacity = (ROOT / 'src/xstar_tools/xstar/cpp/opacity_kernels.cpp').read_text()
    line = (ROOT / 'src/xstar_tools/xstar/cpp/line_emissivity.cpp').read_text()
    assert 'xstar_opacity_prepare_line_geometry_v068232' in opacity
    assert 'int ml1 = nbinc(line_energy_ev, epi, ncn2);' in opacity
    assert 'Type50GeometryCacheEntryV068232' in line
    assert 'line_energy_bits' in line and 'energy_count' in line and 'const double* epi' in line
    assert 'seed_profiles' not in line[line.index('struct Type50GeometryCacheEntryV068232'):line.index('struct xstar_spectral_context')]


def test_dense_fits_staging_preserves_ordered_flush_contract():
    fits = (ROOT / 'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp').read_text()
    assert 'struct DenseBulkColumnsV068232' in fits
    assert 'std::map<int, BulkColumnSegmentV06823088' not in fits
    assert 'ordered_columns_v068232' in fits
    assert 'std::sort(columns.active_columns.begin(), columns.active_columns.end());' in fits
    assert 'seg.values.clear();' in fits


def test_combined_thermal_contribution_scratch_was_removed():
    local = (ROOT / 'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    assert 'thermal_domain_contributions' not in local
    assert 'canonical_thermal_builder.finish(contributions, thermal_only_contributions)' in local
    assert 'std::vector<xstar_element_contribution_v1> ordered_contributions;' in local
    assert 'std::stable_sort(' in local


def test_fits_payload_comparator_ignores_header_only_changes(tmp_path):
    import importlib.util
    import pytest
    np = pytest.importorskip('numpy')
    fits = pytest.importorskip('astropy.io.fits')
    runner = ROOT / 'tools/qualification/run_broad_spectral_publication_host_0_6_82_32.py'
    spec = importlib.util.spec_from_file_location('hotpath_test_runner', runner)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules['hotpath_test_runner'] = mod
    spec.loader.exec_module(mod)
    a = tmp_path / 'a'; b = tmp_path / 'b'
    a.mkdir(); b.mkdir()
    data = np.arange(8, dtype=np.float32)
    h1 = fits.PrimaryHDU(data=data); h1.header['TEST'] = 'baseline'; h1.writeto(a / 'x.fits')
    h2 = fits.PrimaryHDU(data=data); h2.header['TEST'] = 'candidate'; h2.writeto(b / 'x.fits')
    assert mod.compare_fits_payloads(b, a)['accept'] is True
    fits.PrimaryHDU(data=np.arange(8, dtype=np.float32) + 1).writeto(b / 'x.fits', overwrite=True)
    assert mod.compare_fits_payloads(b, a)['accept'] is False
