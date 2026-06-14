from pathlib import Path
from xstar_tools.xstar.call2_helium_population_seed_phase_alignment import RELEASE,SCHEMA

def test_release():
    assert RELEASE=='0.6.48.7.30.1'
    assert 'phase-alignment' in SCHEMA

def test_files():
    r=Path(__file__).resolve().parents[1]
    assert (r/'run_v0487301_call2_helium_seed_phase_alignment_hotfix.sh').is_file()
    assert (r/'check_v0487301_call2_helium_seed_phase_alignment_hotfix.py').is_file()
