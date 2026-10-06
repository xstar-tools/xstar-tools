#!/usr/bin/env python3
"""Validate the current Sphinx HTML/LaTeX/PDF build-output contract."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "qualification" / "documentation_build_outputs_0_6_90_5_2.json"


def reject(message: str) -> None:
    raise SystemExit(f"DOCUMENTATION_BUILD_OUTPUTS_REJECT: {message}")


def require(path: str) -> Path:
    target = ROOT / path
    if not target.is_file():
        reject(f"missing required file: {path}")
    return target


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if policy.get("schema") != "xstar-tools-documentation-build-outputs-v3":
        reject("unsupported policy schema")
    if policy.get("version") != "0.6.90.5.2":
        reject("policy version mismatch")
    if policy.get("science_revision") != "0.6.48.12.3.45.3.3.8":
        reject("science revision changed")
    if policy.get("latexpdf_pipeline") != ["latex", "latex", "dvips", "ps2pdf"]:
        reject("DVI/PostScript/PDF pipeline policy changed")
    if policy.get("latex_eps_reference_style") != "filename.ext":
        reject("EPS reference-style policy changed")

    makefile = require("docs/sphinx/Makefile").read_text(encoding="utf-8")
    for target in ["html", "latex", "latexpdf", "linkcheck", "release", "clean"]:
        if not re.search(rf"^{re.escape(target)}:\s*", makefile, flags=re.MULTILINE):
            reject(f"Makefile target missing: {target}")
    if '-b latex "$(SOURCEDIR)" "$(BUILDDIR)/latex"' not in makefile:
        reject("latex target does not use the expected Sphinx LaTeX builder")
    if 'normalize_latex_eps_references.py' not in makefile:
        reject("latex target does not normalize generated EPS references")
    if not re.search(r"^latexpdf:\s+latex\s*$", makefile, flags=re.MULTILINE):
        reject("latexpdf target does not depend on normalized latex output")
    for token in [
        'latex -interaction=nonstopmode -halt-on-error $(LATEXDOC).tex',
        'dvips -o $(LATEXDOC).ps $(LATEXDOC).dvi',
        'ps2pdf $(LATEXDOC).ps $(LATEXDOC).pdf',
    ]:
        if token not in makefile:
            reject(f"classic PDF pipeline missing from Makefile: {token}")
    if makefile.count('latex -interaction=nonstopmode -halt-on-error $(LATEXDOC).tex') != 2:
        reject("latexpdf must run exactly two explicit LaTeX passes")
    for forbidden in ["-M latexpdf", "latexmk", "pdflatex", "epstopdf"]:
        if forbidden in makefile:
            reject(f"obsolete PDF pipeline token remains in Makefile: {forbidden}")
    release_line = next((line for line in makefile.splitlines() if line.startswith("release:")), "")
    if "latex" in release_line or "latexpdf" in release_line:
        reject("normal release target unexpectedly requires LaTeX")

    makebat = require("docs/sphinx/make.bat").read_text(encoding="utf-8")
    for target in ["html", "latex", "latexpdf", "linkcheck", "release", "clean"]:
        if f'if "%1"=="{target}"' not in makebat:
            reject(f"make.bat command missing: {target}")
    for token in [
        'normalize_latex_eps_references.py',
        'latex -interaction=nonstopmode -halt-on-error %LATEXDOC%.tex',
        'dvips -o %LATEXDOC%.ps %LATEXDOC%.dvi',
        'ps2pdf %LATEXDOC%.ps %LATEXDOC%.pdf',
    ]:
        if token not in makebat:
            reject(f"Windows classic PDF pipeline missing: {token}")
    for forbidden in ["-M latexpdf", "latexmk", "pdflatex", "epstopdf"]:
        if forbidden in makebat:
            reject(f"obsolete PDF pipeline token remains in make.bat: {forbidden}")

    conf = require("docs/conf.py").read_text(encoding="utf-8")
    for token in [
        '"xstar-tools.tex"',
        'f"xstar-tools {release} Documentation"',
        '"papersize": "letterpaper"',
        '"pointsize": "10pt"',
        '"figure_align": "htbp"',
        '"svg_to_eps"',
    ]:
        if token not in conf:
            reject(f"LaTeX Sphinx configuration missing: {token}")
    if "epstopdf" in conf:
        reject("epstopdf preamble remains despite classic LaTeX/dvips pipeline")

    converter = require("docs/_ext/svg_to_eps.py").read_text(encoding="utf-8")
    for token in [
        '("image/svg+xml", EPS_MIMETYPE)',
        'EPS_MIMETYPE = "application/postscript"',
        'f"eps3:{target}"',
        'source_name.with_suffix(".eps")',
        'app.builder.name != "latex"',
    ]:
        if token not in converter:
            reject(f"SVG-to-EPS converter contract missing: {token}")

    normalizer_path = require("docs/_ext/normalize_latex_eps_references.py")
    spec = importlib.util.spec_from_file_location("xstar_latex_eps_normalizer", normalizer_path)
    if spec is None or spec.loader is None:
        reject("cannot load EPS reference normalizer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sample = "\\sphinxincludegraphics{{backend_dispatch}.eps}\n"
    normalized, count = module.normalize_text(sample)
    if count != 1 or normalized != "\\sphinxincludegraphics{backend_dispatch.eps}\n":
        reject(f"EPS reference normalization failed: {normalized!r}")

    rtd = require(".readthedocs.yaml").read_text(encoding="utf-8")
    for token in [
        'version: 2',
        'python: "3.13"',
        'configuration: docs/conf.py',
        'fail_on_warning: true',
        'requirements: docs/requirements.txt',
    ]:
        if token not in rtd:
            reject(f"Read the Docs configuration missing: {token}")

    pyproject = require("pyproject.toml").read_text(encoding="utf-8")
    for token in [
        'sphinx==8.2.3',
        'sphinx-rtd-theme==3.1.0',
        'myst-parser==5.1.0',
    ]:
        if token not in pyproject:
            reject(f"pyproject docs extra is not pinned to the qualified stack: {token}")

    requirements = require("docs/requirements.txt").read_text(encoding="utf-8")
    for token in [
        'sphinx==8.2.3',
        'myst-parser==5.1.0',
        'sphinx-rtd-theme==3.1.0',
        'numpy>=1.24',
        'astropy>=7.2',
    ]:
        if token not in requirements:
            reject(f"Read the Docs requirement missing: {token}")

    guide = require("docs/developer/documentation_builds.md").read_text(encoding="utf-8")
    for token in [
        "make latex",
        "make latexpdf",
        "xstar-tools.tex",
        "xstar-tools.dvi",
        "xstar-tools.ps",
        "xstar-tools.pdf",
        "convert --version",
        "latex --version",
        "dvips --version",
        "ps2pdf --version",
        "EPS3",
        "backend_dispatch.eps",
        "docs/requirements.txt",
        ".readthedocs.yaml",
        "Read the Docs",
    ]:
        if token not in guide:
            reject(f"documentation build guide missing: {token}")
    for forbidden in ["latexmk -pdf", "pdflatex xstar-tools.tex", "sphinx-build -M latexpdf"]:
        if forbidden in guide:
            reject(f"obsolete PDF workflow remains as an instruction in documentation guide: {forbidden}")

    history = require("docs/history/index.md").read_text(encoding="utf-8")
    if "latex_dvi_ps_pdf_pipeline_closure_0_6_90_5_2" not in history:
        reject("0.6.90.5.2 history record is not included in the history toctree")

    print("DOCUMENTATION_BUILD_OUTPUTS_HTML=ACCEPT")
    print("DOCUMENTATION_BUILD_OUTPUTS_LATEX=ACCEPT")
    print("DOCUMENTATION_BUILD_OUTPUTS_EPS3=ACCEPT")
    print("DOCUMENTATION_BUILD_OUTPUTS_EPS_REFERENCE_NORMALIZATION=ACCEPT")
    print("DOCUMENTATION_BUILD_OUTPUTS_DVI_PS_PDF=ACCEPT")
    print("DOCUMENTATION_BUILD_OUTPUTS_OPTIONAL_TEX=ACCEPT")
    print("DOCUMENTATION_BUILD_OUTPUTS_READTHEDOCS=ACCEPT")
    print("DOCUMENTATION_BUILD_OUTPUTS_RESULT=ACCEPT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
