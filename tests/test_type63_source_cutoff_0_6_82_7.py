from __future__ import annotations

import ast
import ctypes
import json
import math
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
ENGINE = CPP / "libxstar_engine.so"
DELTA_E_EV = 70.411590576171875


def _load_python_cutoff_helper():
    path = ROOT / "src/xstar_tools/collisions.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    fn = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_type63_source_delt_cutoff"
    )
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {"math": math, "Optional": object, "Tuple": object}
    # Remove annotations so the isolated helper can be executed without loading
    # the Astropy-dependent collisions module.
    fn.returns = None
    for arg in list(fn.args.args) + list(fn.args.kwonlyargs):
        arg.annotation = None
    exec(compile(module, str(path), "exec"), ns)
    return ns["_type63_source_delt_cutoff"]


PY_TYPE63_CUTOFF = _load_python_cutoff_helper()


@pytest.fixture(scope="module")
def type63_kernel():
    built_here = not ENGINE.exists()
    if built_here:
        if shutil.which("make") is None or shutil.which("g++") is None:
            pytest.skip("native Type-63 cutoff test requires make and g++")
        proc = subprocess.run(
            ["make", "-C", str(CPP), "libxstar_engine.so"],
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
    lib = ctypes.CDLL(str(ENGINE))
    func = lib.xstar_engine_type63_rates_v1
    func.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
    ]
    func.restype = ctypes.c_int
    try:
        yield func
    finally:
        if built_here:
            ENGINE.unlink(missing_ok=True)


def _evaluate(func, temperature_k: float, delta_e_ev: float = DELTA_E_EV):
    out = (ctypes.c_double * 6)()
    # A source-valid n-changing Type-63 transition analogous to the C V
    # 1s2p -> 1s5s family that exposed the missing source cutoff.
    rc = func(
        2,
        1,
        5,
        0,
        6,
        float(temperature_k),
        1.0e12,
        0.0,
        float(delta_e_ev),
        3.0,
        1.0,
        out,
    )
    assert rc == 0
    return tuple(float(x) for x in out)


def test_type63_kernel_suppresses_cv_like_record_at_t4_1p351(type63_kernel):
    cutoff, delt = PY_TYPE63_CUTOFF(1.351e4, 0.0, DELTA_E_EV)
    assert cutoff
    assert delt == pytest.approx(60.48, rel=5e-4)
    assert _evaluate(type63_kernel, 1.351e4) == (0.0,) * 6


def test_type63_kernel_evaluates_cv_like_record_at_t4_2p110(type63_kernel):
    cutoff, delt = PY_TYPE63_CUTOFF(2.110e4, 0.0, DELTA_E_EV)
    assert not cutoff
    assert delt == pytest.approx(38.73, rel=5e-4)
    out = _evaluate(type63_kernel, 2.110e4)
    assert out[0] > 0.0
    assert out[5] > 0.0


def test_type63_kernel_strict_gt_50_boundary(type63_kernel):
    # Choose the temperature from the literal source constants so the same
    # C++ operation order produces delt == 50.0 in binary64.
    threshold_temperature_k = DELTA_E_EV / (0.861707 * 50.0) * 1.0e4
    cutoff, delt = PY_TYPE63_CUTOFF(
        threshold_temperature_k, 0.0, DELTA_E_EV
    )
    assert delt == 50.0
    assert not cutoff
    assert _evaluate(type63_kernel, threshold_temperature_k)[0] > 0.0

    # The immediately lower representable temperature makes delt exceed 50,
    # so canonical Fortran's .gt. gate must suppress the record exactly.
    below_threshold_temperature_k = math.nextafter(threshold_temperature_k, 0.0)
    cutoff_hi, delt_hi = PY_TYPE63_CUTOFF(
        below_threshold_temperature_k, 0.0, DELTA_E_EV
    )
    assert cutoff_hi
    assert delt_hi > 50.0
    assert _evaluate(type63_kernel, below_threshold_temperature_k) == (0.0,) * 6


def test_type63_python_paths_apply_same_source_gate():
    path = ROOT / "src/xstar_tools/collisions.py"
    text = path.read_text(encoding="utf-8")
    assert text.count("cutoff, delt = _type63_source_delt_cutoff(") >= 2
    assert 'diag["type63_reason"] = "source_delt_gt_50_zero"' in text
    cutoff, delt = PY_TYPE63_CUTOFF(1.351e4, 0.0, DELTA_E_EV)
    assert cutoff
    assert delt == pytest.approx(60.48, rel=5e-4)




def test_type63_cpp_source_keeps_literal_fortran_gate_order():
    text = (CPP / "xstar_engine.cpp").read_text(encoding="utf-8")
    marker = "Canonical XSTAR ucalc.f90 type-63 source gate"
    pos = text.index(marker)
    block = text[pos : pos + 1200]
    assert "const double elin=12398.4016/std::abs(ef-ei+1.0e-24);" in block
    assert "const double t4=temp/1.0e4;" in block
    assert "const double ekt=0.861707*t4;" in block
    assert "const double delt=12398.4016/elin/ekt;" in block
    assert "if (delt>50.0) return true;" in block
    assert "delt>=50.0" not in block
