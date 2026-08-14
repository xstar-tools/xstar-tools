from __future__ import annotations
import importlib.util, json, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MAN=ROOT/'qualification/npass_0_6_82_27_16/npass_hotfix_source_scope_0_6_82_27_16.json'
OUT=ROOT/'src/xstar_tools/xstar/output_writers.py'
PP=ROOT/'src/xstar_tools/xstar/pprint_legacy.py'
PHYS=ROOT/'src/xstar_tools/xstar/physical_runner.py'
DIAG=ROOT/'tools/qualification/run_c5_python_fixed_state_population_heating_0_6_82_27_16.py'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_16.py'

def source_roundtrip(value: float)->float:
    r4=struct.unpack('=f',struct.pack('=f',value))[0]
    return struct.unpack('=f',struct.pack('=f',float(f'{r4:.3E}')))[0]

def load_saved():
    sys.path.insert(0,str(ROOT/'src'))
    try:
        from xstar_tools.xstar import saved_radial_state as mod
        return mod
    finally: sys.path.pop(0)

def test_06822716_scope_and_e3_header_contract():
    o=json.loads(MAN.read_text())
    assert o['predecessor']=='0.6.82.27.15'
    assert o['protected_cpp_baseline']=='0.6.82.27.13'
    assert set(o['intentional_numerical_source_changes'])=={'src/xstar_tools/xstar/output_writers.py','src/xstar_tools/xstar/physical_runner.py','src/xstar_tools/xstar/pprint_legacy.py'}
    text=OUT.read_text()
    for key in ('RINNER','ROUTER','RDEL','TEMPERAT','PRESSURE','COLUMN','XEE','DENSITY','LOGXI'):
        assert f'"{key}": _savd_keyword_e3_real4_scalar(' in text
    mod=load_saved()
    for value in (1.2017343044281006,4.6960086822509766,316227780608.0):
        assert mod._savd_keyword_e3_real4_scalar(value)==source_roundtrip(value)

def test_06822716_terminal_option9_publishes_logxi_before_savd():
    text=PP.read_text(); start=text.index('def _option9_zone_line'); end=text.index('def _option10',start) if 'def _option10' in text[start:] else len(text)
    block=text[start:end]
    assert 'state.control["zeta"] = float(zeta)' in block
    assert block.index('state.control["zeta"] = float(zeta)') < block.index('nry = int(nbinc')

def test_06822716_detail_rrc_inventory_is_literal_type7_not_broad_npcon():
    out=OUT.read_text(); phys=PHYS.read_text()
    assert 'source_rows = metadata.detail_rrcs' in out
    assert 'rate_type", 0) or 0) == 7' in out
    assert 'detail_rrcs = tuple(row for row in rrcs if int(row.rate_type) == 7)' in phys
    assert 'detail_rrcs = [row for row in rrcs if int(row.rate_type) == 7]' in phys

def test_06822716_fast_fixed_state_diagnostic_targets_requested_levels_and_heating():
    text=DIAG.read_text()
    assert 'TARGET_GLOBAL_LEVELS = (2, 3, 17, 18, 27, 89, 90, 106)' in text
    assert 'fixed_state=True' in text
    assert 'fixed_state_target_levels.csv' in text
    assert 'fixed_state_target_matrix_terms.csv' in text
    assert 'fixed_state_population_heating_summary.json' in text
    assert 'hydrogen_heating' in text
    assert 'zone1_dsec_capture_lucy_trace_element_z' in PHYS.read_text()

def test_06822716_npass_runner_is_prepared_but_npass5_remains_deferred_by_policy():
    spec=importlib.util.spec_from_file_location('npass02716_runner',RUNNER); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
    assert mod.EXPECTED_VERSION=='0.6.82.27.16'
    assert mod.REL_LIMIT==0.01
    assert '"--mode", "pure-python"' in RUNNER.read_text()
