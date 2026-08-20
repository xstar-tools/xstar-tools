from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_LOWER = ROOT / "src/xstar_tools/xstar/native_fixed_program.py"
PY_UCALC = ROOT / "src/xstar_tools/xstar/ucalc.py"
PY_ELEMENT = ROOT / "src/xstar_tools/xstar/element_equilibrium.py"


def test_package_version_3085():
    assert 'version = "0.6.82.30.8.5"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.82.30.8.5" in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()


def test_native_fixed_program_type82_uses_low_high_abi():
    text = PY_LOWER.read_text()
    block = text.split("elif dt == 82:", 1)[1].split("elif dt == 85:", 1)[0]
    assert "energy_order_source_pair(int(raw_ints[0]), int(raw_ints[1]))" in block
    assert "upper_lower_source_pair(int(raw_ints[0]), int(raw_ints[1]))" not in block
    assert "calc_hmc_ion.f90" in block
    assert "lower_row/upper_row ABI" in block


def test_pure_python_type82_source_result_remains_upper_lower():
    text = PY_UCALC.read_text()
    block = text.split("def _eval_type82", 1)[1].split("def _eval_type85", 1)[0]
    assert "idest1=up,idest2=lo" in block
    assert "calc_hmc_ion-equivalent matrix builder" in block


def test_pure_python_matrix_builder_energy_orders_ordinary_rate_types():
    text = PY_ELEMENT.read_text()
    block = text.split("def _lower_upper", 1)[1].split("def _matrix_cpp_active_for_mg", 1)[0]
    assert "if result.rate_type not in {7, 41}:" in block
    assert "upper, lower = id2, id1" in block
    assert "upper, lower = id1, id2" in block
    assert "essential for Type 82" in block


def test_cpp_3084_type82_fix_is_retained():
    text = (ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp").read_text()
    block = text.split("case 82: {", 1)[1].split("case 85:", 1)[0]
    assert "energy_order_pair(ii[0],ii[1]);" in block
    assert "upper_lower_pair(ii[0],ii[1]);" not in block
