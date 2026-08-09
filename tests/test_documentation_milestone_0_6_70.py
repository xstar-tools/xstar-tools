from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_documentation_milestone_checker_accepts():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_documentation_milestone.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DOCUMENTATION_MILESTONE_RESULT=ACCEPT" in proc.stdout


def test_readme_has_user_centered_milestone7_order():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    headings = [
        "## 1. What `xstar-tools` is",
        "## 2. Relationship to XSTAR",
        "## 3. Installation",
        "## 4. Atomic-data setup",
        "## 5. Five-minute Python example",
        "## 6. Five-minute CLI example",
        "## 7. Backend modes",
        "## 8. `xstar-cpp` example",
        "## 9. Output products",
        "## 10. Reproducibility and provenance",
        "## 11. Documentation",
        "## 12. Development and qualification",
        "## 13. Citation and license",
    ]
    positions = [text.index(h) for h in headings]
    assert positions == sorted(positions)


def test_documentation_layers_and_api_generation_contract():
    data = json.loads((ROOT / "qualification/documentation_milestone_0_6_70.json").read_text())
    for rel in data["required_docs"]:
        assert (ROOT / rel).is_file()
    api = (ROOT / "docs/api/public_api.rst").read_text()
    assert ".. autosummary::" in api
    assert ".. automodule:: xstar_tools" in api
    conf = (ROOT / "docs/conf.py").read_text()
    assert '"myst_parser"' in conf
    assert '"sphinx.ext.autodoc"' in conf
    assert '"sphinx.ext.autosummary"' in conf


def test_documentation_workflow_is_release_strict():
    wf = (ROOT / ".github/workflows/docs.yml").read_text()
    assert "sphinx-build -W --keep-going -b html" in wf
    assert "sphinx-build -W --keep-going -b linkcheck" in wf
    assert "actions/deploy-pages@" in wf
