from __future__ import annotations
import importlib.util,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CPP=ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'
STEP=ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp'
FITS=ROOT/'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp'
PY_TRANSFER=ROOT/'src/xstar_tools/xstar/radial_transfer.py'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_2.py'

def _runner():
    spec=importlib.util.spec_from_file_location('npass0272_runner',RUNNER); assert spec and spec.loader
    m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m); return m

def test_0682272_cpp_unsavd_preserves_live_bilevg():
    text=CPP.read_text(); start=text.index('void restore_saved_shell_v068227'); end=text.index('void project_source_trnfrc_direction_v068227',start); block=text[start:end]
    assert 'data.global_xilevg = snap.source_global_xilevg;' in block
    assert 'data.global_rnisg = snap.source_global_rnisg;' in block
    assert 'recompute_global_bilevg(data)' not in block
    assert 'UNSAVD restores xilevg/rnisg but not bilevg' in block

def test_0682272_python_unsavd_updates_restored_dense_state_but_not_bilevg():
    text=PY_TRANSFER.read_text(); start=text.index('physical_runtime = state.control.get("physical_dsec_runtime")'); end=text.index('for key in ("calc_emisab_context"',start); block=text[start:end]
    assert 'physical_runtime.global_xilevg_by_index =' in block
    assert 'physical_runtime.global_rnisg_by_index =' in block
    assert 'global_bilevg_by_index =' not in block

def test_0682272_step_log_repeats_u_lbol_per_pass():
    text=STEP.read_text()
    assert 'const auto print_ispcg2_v0682272' in text
    assert text.count('print_ispcg2_v0682272();') >= 2
    r=_runner(); sample=''' U(1-1.8),U(1.8-4):  10 20\n Lbol= 3e-6\n pass number= 1 -1\n U(1-1.8),U(1.8-4):  10 20\n Lbol= 3e-6\n pass number= 2 1\n U(1-1.8),U(1.8-4):  10 20\n Lbol= 3e-6\n pass number= 3 -1\n'''
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as td:
        p=Path(td)/'xout_step.log'; p.write_text(sample)
        assert len(r.parse_ispcg2_blocks(p))==3

def test_0682272_detail_writer_uses_per_pass_real4_saved_surfaces():
    cpp=CPP.read_text(); fits=FITS.read_text()
    assert 'whole.multipass_detail_radial_zones.resize(effective_npass_v068227)' in cpp
    assert 'source SAVD REAL4 per-pass detail surface' in cpp
    assert 'state.multipass_detail_radial_zones' in fits
    for kind in ('detail.fits','detal2.fits','detal3.fits','detal4.fits'):
        assert kind in fits

def test_0682272_runner_rejects_missing_pass_files(tmp_path):
    r=_runner(); c=tmp_path/'c'; f=tmp_path/'f'; c.mkdir(); f.mkdir()
    for p in range(1,4):
        for k in ('detail','detal2','detal3','detal4'):
            q=f/r.final_detail_filename(p,k); q.write_bytes(b'x')
    for k in ('detail','detal2','detal3','detal4'):
        (c/r.final_detail_filename(1,k)).write_bytes(b'x')
    got=r.compare_pass_detail_inventory(c,f,3)
    assert not got['accept']
    assert any('xo02_' in e for e in got['errors'])
