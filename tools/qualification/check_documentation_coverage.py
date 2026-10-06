#!/usr/bin/env python3
"""Validate the active xstar-tools documentation coverage/structure contract."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def reject(message: str) -> None:
    raise SystemExit(f"DOCUMENTATION_COVERAGE_REJECT: {message}")


def require(path: str) -> Path:
    p = ROOT / path
    if not p.is_file():
        reject(f"missing required file: {path}")
    return p


def main() -> int:
    required = [
        "docs/_static/custom.css",
        "docs/_static/custom.js",
        "docs/_static/favicon.ico",
        "docs/_static/xstar-tools-logo.png",
        "docs/user/cli.md",
        "docs/python/index.md",
        "docs/python/execution.md",
        "docs/python/atomic_database.md",
        "docs/python/outputs.md",
        "docs/python/tables.md",
        "docs/api/public_api.rst",
        "docs/api/atomic_api.rst",
        "docs/api/outputs_api.rst",
        "docs/api/tables_api.rst",
        "docs/cpp/xstar_cpp.md",
        "docs/cpp/xstar_xspec_initable.md",
        "docs/cpp/xstar_xspec_table.md",
        "docs/cpp/xstar_xspec.md",
        "docs/cpp/xstar_xspec_mpi.md",
        "docs/history/documentation_coverage_closure_0_6_90_4.md",
    ]
    for path in required:
        require(path)

    conf = require("docs/conf.py").read_text(encoding="utf-8")
    for token in [
        'html_static_path = ["_static"]',
        'html_logo = "_static/xstar-tools-logo.png"',
        'html_favicon = "_static/favicon.ico"',
        'html_css_files = ["custom.css"]',
        'html_js_files = ["custom.js"]',
    ]:
        if token not in conf:
            reject(f"Sphinx static configuration missing: {token}")

    public_api = require("docs/api/public_api.rst").read_text(encoding="utf-8")
    if "xstar_tools.backends.available" in public_api or "xstar_tools.backends.describe" in public_api:
        reject("autosummary import-cycle form is still present")
    for name in ["ExecutionMode", "backends.available", "backends.describe"]:
        if name not in public_api:
            reject(f"public API coverage missing {name}")

    root_index = require("docs/index.md").read_text(encoding="utf-8")
    if "api/public_api" in root_index:
        reject("public_api is directly included by root and api toctrees")
    for target in ["user/index", "python/index", "api/index", "cpp/index", "developer/index", "science/index", "history/index"]:
        if target not in root_index:
            reject(f"root documentation index missing {target}")

    history = require("docs/history/index.md").read_text(encoding="utf-8")
    if "documentation_coverage_closure_0_6_90_4" not in history or "repository_history_and_qualification_cleanup_0_6_90_3" not in history:
        reject("history toctree is incomplete")

    pyproject = require("pyproject.toml").read_text(encoding="utf-8")
    scripts = re.findall(r'^([A-Za-z0-9_.-]+)\s*=\s*"[^"]+"$', pyproject.split('[project.scripts]',1)[1].split('[tool.setuptools]',1)[0], flags=re.MULTILINE)
    cli_doc = require("docs/user/cli.md").read_text(encoding="utf-8")
    missing_scripts = [name for name in scripts if f"`{name}`" not in cli_doc]
    if missing_scripts:
        reject("installed console scripts undocumented: " + ", ".join(missing_scripts))

    forbidden_refs = [
        "historical/documentation/performance/",
        "historical/python/xstar_parity_campaign/",
        "historical/cpp/retired_sources/",
        "historical/examples/legacy_pre_productization/",
        "qualification/python_source_comment_overlay.json",
        "qualification/cpp_source_comment_overlay.json",
        "check_python_history_cleanup.py",
        "check_public_python_api.py",
        "check_xstar_cpp_first_class.py",
        "qualification/xstar_cpp_first_class_0_6_69.json",
        "run_windows_git_preflight_shell_closure_host_0_6_88_6_1_2_1.py",
    ]
    active_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in DOCS.rglob("*.md"))
    for token in forbidden_refs:
        if token in active_text:
            reject(f"stale removed-history/checker reference remains: {token}")

    # Simple Markdown heading-level guard used for authored Markdown. Ignore fenced blocks.
    for path in DOCS.rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        in_fence = False
        previous = None
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = re.match(r'^(#{1,6})\s+', line)
            if not m:
                continue
            level = len(m.group(1))
            if previous is not None and level > previous + 1:
                reject(f"non-consecutive heading level in {path.relative_to(ROOT)}:{lineno}")
            previous = level

    print(f"DOCUMENTATION_COVERAGE_CONSOLE_SCRIPTS={len(scripts)}")
    print("DOCUMENTATION_COVERAGE_STATIC=ACCEPT")
    print("DOCUMENTATION_COVERAGE_PYTHON=ACCEPT")
    print("DOCUMENTATION_COVERAGE_NATIVE=ACCEPT")
    print("DOCUMENTATION_COVERAGE_STALE_REFERENCES=ACCEPT")
    print("DOCUMENTATION_COVERAGE_RESULT=ACCEPT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
