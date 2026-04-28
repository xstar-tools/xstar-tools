import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE20 = ROOT / "examples" / "20_o7_solver_source_fit.py"


def _load_example20():
    spec = importlib.util.spec_from_file_location("example20", EXAMPLE20)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_read_xstar_triplet_ratios_generic_c_v(tmp_path):
    csv_path = tmp_path / "xstar_c5_triplet_lines.csv"
    csv_path.write_text(
        "ion,lower_level,upper_level,wavelength,emit_outward\n"
        "c_v,1s2.1S_0,1s1.2s1.3S_1,41.4721,6.03168\n"
        "c_v,1s2.1S_0,1s1.2p1.1P_1,40.2678,1.37636\n"
        "c_v,1s2.1S_0,1s1.2p1.3P_2,40.7283,0.000797067\n"
        "c_v,1s2.1S_0,1s1.2p1.3P_1,40.7306,0.00067928\n"
        "c_v,1s2.1S_0,1s1.2p1.3P_0,40.7285,0.000559578\n",
        encoding="utf-8",
    )
    m = _load_example20()
    out = m.read_xstar_triplet_ratios(csv_path, "emit_outward", element="C", ion_stage=5)
    assert out["available"] is True
    assert out["counts"] == {"f": 1, "i": 3, "r": 1}
    assert abs(out["forbidden"] - 6.03168) < 1e-12
    assert abs(out["intercombination"] - (0.000797067 + 0.00067928 + 0.000559578)) < 1e-12
    assert abs(out["resonance"] - 1.37636) < 1e-12
    assert out["R_f_over_i"] is not None
    assert out["G_f_plus_i_over_r"] is not None


def test_read_xstar_triplet_ratios_rejects_wrong_ion(tmp_path):
    csv_path = tmp_path / "xstar_c5_triplet_lines.csv"
    csv_path.write_text(
        "ion,lower_level,upper_level,wavelength,emit_outward\n"
        "c_v,1s2.1S_0,1s1.2s1.3S_1,41.4721,6.0\n"
        "c_v,1s2.1S_0,1s1.2p1.1P_1,40.2678,1.0\n"
        "c_v,1s2.1S_0,1s1.2p1.3P_1,40.7306,1.0\n",
        encoding="utf-8",
    )
    m = _load_example20()
    out = m.read_xstar_triplet_ratios(csv_path, "emit_outward", element="O", ion_stage=7)
    assert out["counts"] == {"f": 0, "i": 0, "r": 0}
    assert out["R_f_over_i"] is None
    assert out["G_f_plus_i_over_r"] is None
