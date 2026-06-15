from pathlib import Path
from xstar_tools.xstar.call2_helium_global_level_mapping_correction import RELEASE

def test_release():
    assert RELEASE == '0.6.48.7.30.2'

def test_targeted_correction_retained_and_completed():
    t = Path('src/xstar_tools/xstar/native_fixed_program.py').read_text()
    assert 'int(element_z) == 2 and stage == 2 and global_level_index > 0:' in t
    assert 'global_level_index -= 1' in t
