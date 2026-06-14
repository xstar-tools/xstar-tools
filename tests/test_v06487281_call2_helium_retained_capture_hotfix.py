from pathlib import Path
from xstar_tools.xstar.v0472_call2_helium_source_family_capture import RELEASE,_PROBE
def test_release(): assert RELEASE=="0.6.48.7.28.1"
def test_retention():
 assert "v0487281_he_retention_enable" in _PROBE
 assert "retain_element_results" in _PROBE
def test_files():
 r=Path(__file__).resolve().parents[1]
 assert (r/"run_v0487281_call2_helium_retained_capture_hotfix.sh").is_file()
