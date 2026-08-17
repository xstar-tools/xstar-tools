from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "src/xstar_tools/xstar/element_equilibrium.py"


def _module_tree() -> tuple[str, ast.Module]:
    source = SOURCE_PATH.read_text()
    return source, ast.parse(source)


def _function_node(name: str) -> ast.FunctionDef:
    _source, tree = _module_tree()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found in production source")


def _load_source_fixed_difference():
    # Compile only the exact production helper so the regression does not need
    # optional runtime dependencies (notably astropy) just to exercise diff2.
    node = _function_node("_source_fixed_difference")
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    namespace = {"np": np}
    exec(compile(isolated, str(SOURCE_PATH), "exec"), namespace)
    return namespace["_source_fixed_difference"]


def test_diff2_1e3_limits_only_ordered_difference_scan():
    source_fixed_difference = _load_source_fixed_difference()

    # Row 1 alone drives diff2 above 1.e3. Row 2 is chosen so evaluating it
    # would change the result. Canonical msolvelucy stops the ordered row scan
    # once cumulative diff2 crosses 1.e3.
    previous = np.asarray([100.0, 7.0], dtype=float)
    current = np.asarray([1.0, 0.5], dtype=float)
    tst0 = previous[0] / current[0]
    expected_first_row_only = (tst0 - 1.0) ** 2

    diff2 = source_fixed_difference(previous, current, epsilon=1.0e-6)

    assert diff2 >= 1.0e3
    assert diff2 == expected_first_row_only


def test_diff2_1e3_does_not_break_production_fixed_point_loop():
    source, tree = _module_tree()
    msolve = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "msolvelucy"
    )

    fixed_loops = []
    for node in ast.walk(msolve):
        if not isinstance(node, ast.While):
            continue
        test_text = ast.get_source_segment(source, node.test) or ""
        if "fixed_iter" in test_text and "fixed_diff" in test_text:
            fixed_loops.append((node, test_text))

    assert len(fixed_loops) == 1
    loop, test_text = fixed_loops[0]
    assert "context.max_fixed_point_iterations" in test_text
    assert "fixed_diff >= context.fixed_point_tolerance" in test_text

    # Execute the exact production while-condition expression.  A diff2 of
    # 1500 must still request another fixed-point iteration; only nitmx2 and
    # crit2-equivalent controls may stop this loop.
    condition = ast.Expression(body=loop.test)
    ast.fix_missing_locations(condition)
    compiled = compile(condition, str(SOURCE_PATH), "eval")
    context = SimpleNamespace(max_fixed_point_iterations=4, fixed_point_tolerance=1.0e-2)
    assert eval(compiled, {}, {"fixed_iter": 1, "fixed_diff": 1500.0, "context": context}) is True
    assert eval(compiled, {}, {"fixed_iter": 4, "fixed_diff": 1500.0, "context": context}) is False
    assert eval(compiled, {}, {"fixed_iter": 1, "fixed_diff": 1.0e-3, "context": context}) is False

    # The 1.e3 cutoff may occur in _source_fixed_difference's row scan, but
    # must not govern a Break anywhere in the surrounding fixed-point loop.
    for node in ast.walk(loop):
        if isinstance(node, ast.If):
            condition = ast.get_source_segment(source, node.test) or ""
            if "fixed_diff" in condition and "1.0e3" in condition:
                assert not any(isinstance(child, ast.Break) for child in ast.walk(node))

    loop_text = ast.get_source_segment(source, loop) or ""
    assert "if fixed_diff >= 1.0e3" not in loop_text
    assert "A cumulative diff2 >= 1.e3 does *not* terminate" in loop_text
