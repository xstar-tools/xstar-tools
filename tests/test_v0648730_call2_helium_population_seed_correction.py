from pathlib import Path
from xstar_tools.xstar.call2_helium_population_seed_correction import RELEASE
def test_release(): assert RELEASE=='0.6.48.7.30'
def test_files():
 r=Path(__file__).resolve().parents[1]; assert (r/'run_v048730_call2_helium_population_seed_correction.sh').is_file(); assert (r/'check_v048730_call2_helium_population_seed_correction.py').is_file()
