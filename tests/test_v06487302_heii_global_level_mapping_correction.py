from pathlib import Path
from xstar_tools.xstar.call2_helium_global_level_mapping_correction import RELEASE

def test_release(): assert RELEASE=='0.6.48.7.30.2'
def test_targeted_correction_present():
    t=Path('src/xstar_tools/xstar/native_fixed_program.py').read_text()
    assert 'int(element_z) == 2 and stage == 2 and local_level > 1' in t
    assert '(2, 2, local_level - 1)' in t
