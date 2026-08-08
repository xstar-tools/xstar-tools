from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src" / "xstar_tools" / "xstar"


def _data():
    return json.loads((ROOT / "qualification" / "python_history_cleanup_0_6_56.json").read_text())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_archived_parity_campaign_modules_are_outside_active_namespace():
    data = _data()
    assert data["schema"] == "xstar-tools-python-history-cleanup-v1"
    assert data["productization_version"] == "0.6.56"
    assert len(data["archived_modules"]) == 51
    assert len(data["archived_tests"]) == 36
    assert len(list(ACTIVE.glob("*.py"))) == 81
    for name in (
        "call1_secant_temperature_ieee_audit",
        "call2_helium_source_family_reconstruction",
        "type50_manifold_audit",
    ):
        info = data["archived_modules"][name]
        assert not (ROOT / info["original_path"]).exists()
        if (ROOT / "historical").is_dir():
            assert (ROOT / info["historical_path"]).is_file()


def test_archived_files_preserve_recorded_bytes():
    data = _data()
    if not (ROOT / "historical").is_dir():
        return
    for table in ("archived_modules", "archived_tests"):
        for info in data[table].values():
            assert _sha(ROOT / info["historical_path"]) == info["sha256"]


def test_active_runtime_diagnostics_that_still_have_callers_are_kept():
    for name in _data()["active_runtime_diagnostic_keep_set"]:
        assert (ACTIVE / name).is_file()


def test_obsolete_audit_console_scripts_are_removed():
    text = (ROOT / "pyproject.toml").read_text()
    for command in _data()["removed_console_scripts"]:
        assert command not in text


def test_active_python_imports_do_not_target_archived_modules():
    archived = set(_data()["archived_modules"])
    offenders = []
    for base in (ROOT / "src", ROOT / "tests", ROOT / "tools"):
        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(errors="ignore"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod.startswith("xstar_tools.xstar.") and mod.rsplit(".", 1)[-1] in archived:
                        offenders.append(str(path.relative_to(ROOT)))
                    if mod == "xstar_tools.xstar" and any(x.name in archived for x in node.names):
                        offenders.append(str(path.relative_to(ROOT)))
                    if node.level and path.parent == ACTIVE and mod and mod.rsplit(".", 1)[-1] in archived:
                        offenders.append(str(path.relative_to(ROOT)))
                elif isinstance(node, ast.Import):
                    if any(x.name.startswith("xstar_tools.xstar.") and x.name.rsplit(".", 1)[-1] in archived for x in node.names):
                        offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
