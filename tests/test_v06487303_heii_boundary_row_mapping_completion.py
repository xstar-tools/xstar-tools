from pathlib import Path
from xstar_tools.xstar.call2_helium_boundary_row_mapping_completion import RELEASE

def test_release():
    assert RELEASE == '0.6.48.7.30.3'

def test_boundary_row_included_in_targeted_correction():
    t = Path('src/xstar_tools/xstar/native_fixed_program.py').read_text()
    assert 'int(element_z) == 2 and stage == 2:' in t
    block = t[t.index('# v0.6.48.7.30.3:'):t.index('rows.append', t.index('# v0.6.48.7.30.3:'))]
    assert 'local_level > 1' not in block
    assert '(2, 2, local_level - 1)' in block
