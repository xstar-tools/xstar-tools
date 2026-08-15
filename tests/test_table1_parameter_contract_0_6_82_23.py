from __future__ import annotations
import importlib.util, json, subprocess, textwrap, sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

def contract_module():
    path=ROOT/'src/xstar_tools/xstar/parameter_contract.py'
    spec=importlib.util.spec_from_file_location('xstar_parameter_contract_068223',path)
    mod=importlib.util.module_from_spec(spec); assert spec and spec.loader
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod

def test_ledger_and_python_rules_are_complete():
    m=contract_module(); ledger=json.loads((ROOT/'qualification/table1_parameter_contract_0_6_82_23.json').read_text())
    assert len(m.PARAMETER_RULES)==59
    assert set(m.PARAMETER_RULES)=={row['name'] for row in ledger['parameters']}
    assert m.XSTAR_PAR_DEFAULTS['density']==1e4
    assert m.XSTAR_PAR_DEFAULTS['rlrad38']==1e-6
    assert m.XSTAR_PAR_DEFAULTS['nsteps']==3
    assert m.XSTAR_PAR_DEFAULTS['niter']==0
    assert m.XSTAR_PAR_DEFAULTS['critf']==1e-7
    assert m.XSTAR_PAR_DEFAULTS['vturbi']==1.0
    assert m.XSTAR_PAR_DEFAULTS['cfrac']==0.0
    assert m.XSTAR_PAR_DEFAULTS['naabund']==1.0

def test_exact_xpi_range_boundaries():
    m=contract_module()
    for name,lo,hi in [('cfrac',0,1),('ncn2',999,999999),('nsteps',1,1000),('lprint',-1,6),('lwrite',0,1),('loopcontrol',0,30000),('spectun',0,2),('radexp',-3,3),('vturbi',0,30000),('xeemin',1e-6,0.5)]:
        assert m.coerce_and_validate_parameter(name,lo)==lo
        assert m.coerce_and_validate_parameter(name,hi)==hi
        with pytest.raises(ValueError): m.coerce_and_validate_parameter(name,lo-1 if isinstance(lo,int) else lo-abs(lo or 1)-1e-6)
        with pytest.raises(ValueError): m.coerce_and_validate_parameter(name,hi+1)
    with pytest.raises(ValueError): m.coerce_and_validate_parameter('ncn2',999.5)

def test_active_parameter_changes_are_not_default_overwritten():
    m=contract_module()
    values=m.normalize_public_parameter_values({'density':3.25e7,'cfrac':0.37,'emult':0.25,'critf':2e-8,'vturbi':77,'nsteps':7,'ncn2':12001,'cabund':2.5})
    for k,v in {'density':3.25e7,'cfrac':0.37,'emult':0.25,'critf':2e-8,'vturbi':77.0,'nsteps':7,'ncn2':12001,'cabund':2.5}.items(): assert values[k]==v

def test_metadata_classification_and_known_manual_conflicts():
    ledger=json.loads((ROOT/'qualification/table1_parameter_contract_0_6_82_23.json').read_text())
    by={r['name']:r for r in ledger['parameters']}
    assert by['modelname']['classification']=='metadata/interface'
    assert by['mode']['classification']=='metadata/interface'
    assert 'table1_vs_xstar_par_default' in by['cfrac']['conflicts']
    assert 'detailed_manual_vs_xstar_par_default' in by['column']['conflicts']
    assert not by['naabund']['table1_present']
    assert not by['lstep']['table1_present']

def test_cpp_header_accepts_and_rejects_contract(tmp_path):
    src=tmp_path/'probe.cpp'; exe=tmp_path/'probe'
    src.write_text(textwrap.dedent('''
      #include "xstar_parameter_contract.hpp"
      #include <iostream>
      int main(){
        xstar_parameter_contract::validate_text("cfrac","0.4");
        xstar_parameter_contract::validate_text("ncn2","999");
        try { xstar_parameter_contract::validate_text("ncn2","998"); return 2; } catch(...) {}
        try { xstar_parameter_contract::validate_text("lwrite","-1"); return 3; } catch(...) {}
        std::cout << xstar_parameter_contract::string_default("spectrum_file") << " " << xstar_parameter_contract::numeric_default("density") << "\\n";
        return 0;
      }
    '''))
    subprocess.run(['g++','-std=c++17','-I',str(ROOT/'src/xstar_tools/xstar/cpp'),str(src),'-o',str(exe)],check=True)
    out=subprocess.check_output([str(exe)],text=True).strip()
    assert out.startswith('spct.dat 10000')

def test_source_consumers_and_provenance_are_wired():
    cpp=(ROOT/'src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp').read_text()
    front=(ROOT/'src/xstar_tools/xstar/cpp/xstar_cpp_frontend.cpp').read_text()
    standalone=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    py=(ROOT/'src/xstar_tools/xstar/physical_runner.py').read_text()
    assert 'p.covering_fraction=public_number("cfrac",p.covering_fraction);' in cpp
    assert 'p.emission_multiplier=public_number("emult",p.emission_multiplier);' in cpp
    assert 'p.critical_fraction=public_number("critf",p.critical_fraction);' in cpp
    assert 'p.requested_niter=static_cast<int>(public_number("niter",p.niter));' in cpp
    assert 'for (const auto& rule : xstar_parameter_contract::kRules)' in front
    assert 'parameters_used' in front
    assert 'rows.reserve(59)' in standalone
    assert '0.6.82.23 public parameter provenance requires 59 rows' in py

def test_parameter_sensitivity_reaches_intended_consumers_and_metadata_stays_out_of_science_kernels():
    runtime=(ROOT/'src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp').read_text()
    standalone=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    local=(ROOT/'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    thermal=(ROOT/'src/xstar_tools/xstar/cpp/thermal_kernels.cpp').read_text()
    rates=(ROOT/'src/xstar_tools/xstar/cpp/rate_kernels.cpp').read_text()
    py=(ROOT/'src/xstar_tools/xstar/physical_runner.py').read_text()
    # Representative active parameters must be read from the public envelope,
    # not replaced by benchmark constants.
    for token in (
        'public_number("density"', 'public_number("cfrac"',
        'public_number("emult"', 'public_number("nsteps"',
        'public_number("critf"', 'public_number("vturbi"',
        'public_number("ncn2"',
    ):
        assert token in runtime
    assert 'coerce_and_validate_parameter' in py
    # Metadata/interface values may be retained/published but must not enter
    # the local atomic/rate/thermal science kernels.
    kernels=local+thermal+rates
    assert 'model_name' not in kernels
    assert 'modelname' not in kernels
    assert 'loopcontrol' not in kernels
    assert 'XPI interface mode' not in kernels
    assert 'parameters_used' in (ROOT/'src/xstar_tools/xstar/cpp/xstar_cpp_frontend.cpp').read_text()
    assert 'model_name' in runtime or 'modelname' in standalone
