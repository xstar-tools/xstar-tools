from pathlib import Path
import importlib.util


def test_compare_script_parser_has_output_options():
    script = Path(__file__).resolve().parents[1] / "examples" / "08_compare_xstar_outputs.py"
    spec = importlib.util.spec_from_file_location("compare_xstar_outputs_example", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    parser = mod.build_parser()
    opts = {opt for action in parser._actions for opt in action.option_strings}
    assert "--mode" in opts
    assert "--out-csv" in opts
    assert "--out-json" in opts
    assert "--wavelength-column" in opts
