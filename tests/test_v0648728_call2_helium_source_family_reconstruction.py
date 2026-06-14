from pathlib import Path
from xstar_tools.xstar.call2_helium_source_family_reconstruction import RELEASE

def test_release(): assert RELEASE=='0.6.48.7.28'
def test_artifacts():
 r=Path(__file__).resolve().parents[1]
 assert (r/'run_v048728_call2_helium_source_family_reconstruction.sh').is_file()
 assert (r/'check_v048728_call2_helium_source_family_reconstruction.py').is_file()
