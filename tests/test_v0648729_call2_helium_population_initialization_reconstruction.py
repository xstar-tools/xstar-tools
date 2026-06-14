from pathlib import Path
from xstar_tools.xstar.call2_helium_population_initialization_reconstruction import RELEASE,thermal_from_terms

def test_release(): assert RELEASE=='0.6.48.7.29'
def test_population_weighted_thermal():
 t=[{'destination_row':'1','abundance':'0.1','population':'2','cj':'-3','cj2':'4'}]
 r=thermal_from_terms(t,{1:2.0});assert abs(r['primary_heating']-0.6)<1e-15 and abs(r['secondary_cooling']-0.8)<1e-15
def test_files():
 root=Path(__file__).resolve().parents[1]
 assert (root/'run_v048729_call2_helium_population_initialization_reconstruction.sh').is_file()
 assert (root/'check_v048729_call2_helium_population_initialization_reconstruction.py').is_file()
