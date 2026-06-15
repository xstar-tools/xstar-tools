from pathlib import Path

from xstar_tools.xstar.call2_helium_source_ordinal_mapping_correction import RELEASE


def test_release():
    assert RELEASE == "0.6.48.7.30.4"


def test_complete_heii_source_ordinal_fix_uses_resolved_global_index():
    text = Path("src/xstar_tools/xstar/native_fixed_program.py").read_text()
    start = text.index("# v0.6.48.7.30.4:")
    block = text[start:text.index("rows.append", start)]
    assert "int(element_z) == 2 and stage == 2 and global_level_index > 0" in block
    assert "global_level_index -= 1" in block
    assert "local_level - 1" not in block


def test_audit_separates_row_ledger_from_exact_mapping():
    text = Path("src/xstar_tools/xstar/call2_helium_source_ordinal_mapping_correction.py").read_text()
    assert '"CALL2_HE_78_ROW_LEDGER"' in text
    assert '"CALL2_HE_78_ROW_MAPPING_EXACT"' in text
    assert '"CALL2_HE_BOUNDARY_ROW_GLOBAL_LEVEL_79"' in text
