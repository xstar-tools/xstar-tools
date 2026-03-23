import pytest
pytest.importorskip("astropy")
from xstar_atomic.hierarchy import ATDBIndexArrays, IndexedRecord, ElementInfo, IonInfo


def _record(recno, z, stage, data_type, rate_type):
    return IndexedRecord(
        recno=recno,
        data_type=data_type,
        rate_type=rate_type,
        continuation=0,
        nreal=0,
        nint=0,
        nchar=0,
        real_ptr=1,
        int_ptr=1,
        char_ptr=1,
        element_z=z,
        element_symbol="O" if z == 8 else "Ne",
        element_name="oxygen" if z == 8 else "neon",
        element_record=1,
        ion_global_index=1,
        ion_stage=stage,
        ion_label=f"O {stage}" if z == 8 else f"Ne {stage}",
        charge_label="",
        ion_record=2,
        level_index=None,
        parent_kind="ion_process",
        data_type_label="",
        rate_type_label="",
    )


def test_array_index_selects_and_reconstructs_subset():
    records = [
        _record(1, 8, 8, 50, 4),
        _record(2, 8, 8, 63, 3),
        _record(3, 8, 7, 50, 4),
        _record(4, 10, 9, 98, 3),
    ]
    elements = [ElementInfo(8, "O", "oxygen", 1, None, None, []), ElementInfo(10, "Ne", "neon", 4, None, None, [])]
    ions = [IonInfo(1, 8, "O", "oxygen", 8, "O VIII", "", 2, 0, [], [], "")]
    idx = ATDBIndexArrays.from_records(records, elements, ions, {"format_version": 2})
    selected = idx.to_records(idx.select_indices(z=8, ion_stage=8, data_type=[50, 63]))
    assert [r.recno for r in selected] == [1, 2]
    assert selected[0].element_symbol == "O"
    assert selected[0].ion_label == "O VIII"
