from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "qualification"))
from source_name_hygiene_compat import additional_versioned_callables
MANIFEST = ROOT / "qualification/source_name_hygiene_0_6_76.json"


def test_source_name_hygiene_checker_accepts():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_source_name_hygiene_0_6_76.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SOURCE_NAME_HYGIENE_0676_RESULT=ACCEPT" in proc.stdout


def test_no_version_or_patch_labels_remain_in_python_function_definitions():
    bad = []
    rx = re.compile(r"(?:_v\d|_patch\d)", re.I)
    for path in (ROOT / "src/xstar_tools/xstar").rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and rx.search(node.name):
                bad.append((str(path.relative_to(ROOT)), node.lineno, node.name))
    assert bad == []


def test_required_user_requested_renames_and_mg_retirement_are_frozen():
    data = json.loads(MANIFEST.read_text())
    renames = {}
    for key in ("cpp_internal_renames", "manual_stable_renames", "python_private_renames"):
        renames.update(data[key])
    assert renames["write_v0648123350_postsolve_attribution"] == "write_postsolve_attribution"
    assert renames["standalone_iteration_evaluator_v67"] == "standalone_iteration_evaluator"
    assert renames["finalize_accepted_boundary_snapshot_v064894"] == "finalize_accepted_boundary_snapshot"
    assert renames["write_patch52017381_detal4_writer_projection"] == "write_detal4_writer_projection"
    assert renames["_patch5201734_replay_selected_line_producers"] == "_replay_selected_line_producers"
    assert renames["_v0648101_env_true"] == "_final_recompute_env_true"

    retired = set(data["retired_mg_diagnostic_symbols"])
    assert "eval_mg_ion_accumulator_cpp" in retired
    assert "probe_mg_ion_accumulator_skeleton" in retired
    active = "\n".join(
        p.read_text(errors="ignore")
        for p in (ROOT / "src/xstar_tools/xstar").rglob("*")
        if p.is_file() and p.suffix in {".py", ".cpp", ".h", ".hpp"}
    )
    for name in retired:
        assert name not in active

    compat = set(data["abi_compatibility_exports_retained"])
    assert {
        "xstar_engine_eval_mg_ion_accumulator_v1",
        "xstar_matrix_eval_mg_ion_accumulator_v1",
        "xstar_engine_eval_mg_rate_payload_shadow_v1",
        "xstar_engine_eval_mg_rate_payload_native_scalars_v1",
    } == compat
    engine = (ROOT / "src/xstar_tools/xstar/cpp/xstar_engine.cpp").read_text()
    for name in compat:
        assert name in engine
    for name in data["preferred_general_rate_payload_exports"]:
        assert name in engine


def test_remaining_versioned_cpp_callables_are_exact_abi_allowlist():
    data = json.loads(MANIFEST.read_text())
    allow = set()
    for values in data["allowed_versioned_cpp_callables"].values():
        allow.update(values)
    # Preserve the immutable 0.6.76 ABI allowlist and add only versioned
    # callables from separately-qualified later ABIs (0.6.81 XSPEC table ABI).
    allow.update(additional_versioned_callables())
    rx = re.compile(r"\b([A-Za-z_]\w*(?:_v\d\w*|_patch\d\w*))\s*\(")
    actual = set()
    cpp = ROOT / "src/xstar_tools/xstar/cpp"
    for pattern in ("*.cpp", "*.h", "*.hpp"):
        for path in cpp.glob(pattern):
            actual.update(rx.findall(path.read_text(errors="ignore")))
    assert actual == allow
    assert all(name.startswith("xstar_") for name in allow)
    assert data["abi_rename_policy"]["current_decision"] == "retain_versioned_exports_in_0.6.76"
