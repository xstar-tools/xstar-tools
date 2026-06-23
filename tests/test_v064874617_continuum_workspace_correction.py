from __future__ import annotations
import json,subprocess,sys
from pathlib import Path
import numpy as np
from xstar_tools.xstar.continuum_workspace_correction_v04874617 import source_epim,reconstruct
from xstar_tools.xstar.v4616_baseline_gate_v04874617 import REQUIRED_GATES
ROOT=Path(__file__).resolve().parents[1]
def test_release_version():
 import xstar_tools
 assert xstar_tools.__version__=="0.6.48.7.46.21"
def test_source_reduced_grid_contract():
 e=source_epim();assert len(e)==999;assert e[0]==float(np.float32(.1));assert np.all(np.diff(e)>0);assert 9.9e5<e[-1]<1.1e6
def test_bremsmap_is_source_nearest_bin():
 full=np.geomspace(.1,1e6,9999);flux=np.arange(9999,dtype=np.float64);epim,idx,mapped=reconstruct(full,flux)
 assert len(epim)==len(idx)==len(mapped)==999;assert np.all(np.diff(idx)>=0);assert np.array_equal(mapped,flux[idx-1])
def test_cpp_and_runner_contract():
 cpp=(ROOT/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text();run=(ROOT/'run_v04874617_continuum_compton_free_free_workspace_reduction.sh').read_text()
 assert 'XSTAR_QUALIFICATION_CONTINUUM_WORKSPACE_SOURCE_FAITHFUL' in cpp
 assert 'source_continuum_thermal' in cpp and '_continuum_workspace.csv' in cpp
 assert 'XSTAR_QUALIFICATION_CONTINUUM_WORKSPACE_SOURCE_FAITHFUL=1' in run
 assert '--require-continuum-workspace' in run
def test_v4616_baseline_gate(tmp_path):
 source=tmp_path/'checker.json';out=tmp_path/'out.json';source.write_text(json.dumps({'release':'0.6.48.7.46.16','result':'ACCEPT','gates':{x:'ACCEPT' for x in REQUIRED_GATES}}))
 p=subprocess.run([sys.executable,'-m','xstar_tools.xstar.v4616_baseline_gate_v04874617',str(source),'--output-json',str(out)],cwd=ROOT,env={'PYTHONPATH':str(ROOT/'src')},capture_output=True,text=True)
 assert p.returncode==0,p.stdout+p.stderr;assert json.loads(out.read_text())['result']=='ACCEPT'
def test_readiness_accepts(tmp_path):
 out=tmp_path/'readiness.json';p=subprocess.run([sys.executable,str(ROOT/'check_v04874617_continuum_compton_free_free_workspace_reduction_readiness.py'),'--package-dir',str(ROOT),'--output-json',str(out)],cwd=ROOT,capture_output=True,text=True)
 assert p.returncode==0,p.stdout+p.stderr;assert json.loads(out.read_text())['result']=='ACCEPT'
