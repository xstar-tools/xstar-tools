from pathlib import Path
from xstar_tools.xstar.call2_general_thermal_family_attribution import heatf
def test_heatf_zero(): assert heatf(1.0,1.0)==0.0
def test_release_files():
 r=Path(__file__).resolve().parents[1]; assert (r/'run_v048727_call2_general_thermal_family_attribution.sh').is_file()
