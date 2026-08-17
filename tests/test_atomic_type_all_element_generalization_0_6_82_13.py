from pathlib import Path
import subprocess
import sys

from xstar_tools.xstar import native_fixed_program as native


def test_atomic_type_all_element_generalization_gate():
    root = Path(__file__).resolve().parents[1]
    p = subprocess.run(
        [sys.executable, str(root / 'tools/qualification/check_atomic_type_all_element_generalization_0_6_82_13.py')],
        cwd=root,
        text=True,
        capture_output=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'ATOMIC_TYPE_ALL_ELEMENT_GENERALIZATION_068213_RESULT=ACCEPT' in p.stdout
    assert 'ATOMIC_TYPE_ALL_ELEMENT_GENERALIZATION_068213_PYTHON_LOWERER=78_OF_78_PHYSICAL_Z1_Z30' in p.stdout
    assert 'ATOMIC_TYPE_ALL_ELEMENT_GENERALIZATION_068213_CPP_GENERIC_OPCODE200=44_OF_44' in p.stdout


def test_python_native_lowerer_has_complete_physical_catalog_and_z1_z30_tables():
    assert len(native.PHYSICAL_DATA_TYPES) == 78
    assert native.ACTIVE_LOWERER_DATA_TYPES == native.PHYSICAL_DATA_TYPES
    assert native.SOURCE_UCALC_GENERIC_OPCODE == 200
    assert native.SOURCE_UCALC_GENERIC_OPCODE in native.ENGINE_RECOGNIZED_OPCODES
    assert set(native.ATOMIC_MASS_AMU) == set(range(1, 31))
    assert set(native.QUALIFIED_XDEF_ABUNDANCES_BY_Z) == set(range(1, 31))


def test_python_record_classification_treats_all_physical_labels_as_executable():
    for data_type in native.PHYSICAL_DATA_TYPES:
        assert native._classify_record(1, data_type) == 'native_executable'
    # Rate-type topology remains metadata even when its data label is otherwise physical.
    assert native._classify_record(13, 6) == 'topology_metadata'
    assert native._classify_record(1, 14) == 'unsupported_physics'


def test_type70_fortran_global_ion_identity_contract_is_serialized_not_compact_counter():
    root = Path(__file__).resolve().parents[1]
    atdb = (root / 'src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp').read_text()
    engine = (root / 'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    start = engine.index('case 70:{')
    end = engine.index('case 92:{', start)
    type70 = engine[start:end]
    assert 'kType70SourceIonIdentityMagicV068213 = 227' in atdb
    assert 'out.ints.push_back(static_cast<std::int64_t>(ion));' in atdb
    assert 'record.ion_index==1' not in type70
    assert 'record.ion_index == 1' not in type70
    assert 'source_global_hydrogen_ion' in type70
