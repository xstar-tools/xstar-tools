from __future__ import annotations
import importlib.util
from pathlib import Path


def _mod():
    p=Path(__file__).resolve().parents[1]/'tools/qualification/v0648123361/compare_step_log_science.py'
    spec=importlib.util.spec_from_file_location('v0648123361_cmp',p)
    mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod); return mod


def _row(ion, value):
    return {'ion':ion,'wavelength':10.0,'ref_lum':0.0,'trn_lum':0.0,'backward_depth':value,'forward_depth':0.0}


def test_rowwise_tails_do_not_fail_material_surface_gate():
    m=_mod()
    r={i:_row('ca_viii',1.0e-28) for i in range(100)}
    c={i:_row('ca_viii',(1.02 if i==0 else 1.0)*1.0e-28) for i in range(100)}
    out=m.compare_option15_material_surfaces(c,r)
    assert out['rowwise_gt1pct_diagnostics']==1
    assert out['material_surface_failures']==0
    assert out['numeric_science_accept'] is True


def test_material_surface_above_one_percent_fails():
    m=_mod()
    r={i:_row('ca_viii',1.0e-20) for i in range(10)}
    c={i:_row('ca_viii',1.02e-20) for i in range(10)}
    out=m.compare_option15_material_surfaces(c,r)
    assert out['material_surface_failures']==1
    assert out['numeric_science_accept'] is False


def test_inventory_is_separate_from_common_row_numeric_science():
    m=_mod()
    r={1:_row('ca_viii',1.0e-20)}
    c={1:_row('ca_viii',1.0e-20),2:_row('ca_viii',1.0e-20)}
    out=m.compare_option15_material_surfaces(c,r)
    assert out['numeric_science_accept'] is True
    assert out['material_inventory_mismatches']==1
    assert out['scientific_accept'] is False
