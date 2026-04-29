import importlib.util
from pathlib import Path


def load_example20():
    path = Path(__file__).resolve().parents[1] / "examples" / "20_o7_solver_source_fit.py"
    spec = importlib.util.spec_from_file_location("example20_solver_source_fit", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_format_optional_float_handles_none_and_nan():
    mod = load_example20()
    assert mod.format_optional_float(None) == "NA"
    assert mod.format_optional_float(float("nan")) == "NA"
    assert mod.format_optional_float("bad") == "NA"
    assert mod.format_optional_float(2962.62) == "2962.62"


def test_missing_resonance_ratio_print_values_do_not_raise():
    mod = load_example20()
    ratios = mod.ratios_from_components([0.5, 0.5, 0.0])
    assert ratios["R_f_over_i"] == 1.0
    assert ratios["G_f_plus_i_over_r"] is None
    text = f"R={mod.format_optional_float(ratios.get('R_f_over_i'))} G={mod.format_optional_float(ratios.get('G_f_plus_i_over_r'))}"
    assert text == "R=1 G=NA"
