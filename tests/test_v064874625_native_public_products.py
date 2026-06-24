from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/'src/xstar_tools/benchmarks/v064874625_native_product_state'
PUBLIC={'xout_abund1.fits','xout_cont1.fits','xout_lines1.fits','xout_rrc1.fits','xout_spect1.fits','xout_step.log'}

def test_v25_schema_has_no_embedded_public_payloads():
    assert SCHEMA.is_dir()
    assert not [p for p in ROOT.rglob('*') if p.is_file() and p.name in PUBLIC]
    assert len(list((SCHEMA/'detail_baselines').glob('xo01_*.fits')))==4

def test_v25_runtime_writers_have_no_v24_byte_copy_path():
    text='\n'.join((ROOT/'src/xstar_tools/xstar/cpp'/name).read_text() for name in ('xstar_run_state.cpp','xstar_science_fits.cpp','xstar_step_log.cpp'))
    for token in ('require_python_product_payload','write_exact_product_payload','materialized_public_product','materialized_product_log','product_payloads.tsv'):
        assert token not in text

def test_v25_native_reducers_and_full_log_contract_present():
    writer=(ROOT/'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp').read_text()
    for token in ('write_native_abundances_file','write_native_lines_file','write_native_rrc_file','write_native_spectral_files'):
        assert token in writer
    step=(ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp').read_text()
    assert 'lines.size() != 5480' in step
    assert 'lines.size() != 44' in step
    assert 'lines.size() != 5524' in step
    assert 'total time human ' in step

def test_v25_comparator_ignores_only_version_and_timing_tail():
    text=(ROOT/'compare_v04874625_native_products.py').read_text()
    assert 'nl[1:5480]==ol[1:5480]' in text
    assert 'tail=lines[5480:]' in text
    assert 'len(tail)==44' in text
