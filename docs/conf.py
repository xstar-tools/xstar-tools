"""Sphinx configuration for the xstar-tools documentation."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DOCS_EXT = Path(__file__).resolve().parent / "_ext"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(DOCS_EXT))

project = "xstar-tools"
author = "Ashkbiz Danehkar"

_pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
_match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', _pyproject, re.MULTILINE)
release = _match.group(1) if _match else "unknown"
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "svg_to_eps",
]

autosummary_generate = True
autodoc_typehints = "description"
autodoc_member_order = "bysource"
napoleon_google_docstring = True
napoleon_numpy_docstring = True

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
myst_enable_extensions = ["colon_fence", "deflist", "fieldlist"]

html_theme = "sphinx_rtd_theme"
html_title = f"xstar-tools {release}"
html_static_path = ["_static"]
html_logo = "_static/xstar-tools-logo.png"
html_favicon = "_static/favicon.ico"
html_css_files = ["custom.css"]
html_js_files = ["custom.js"]

latex_documents = [
    (
        "index",
        "xstar-tools.tex",
        f"xstar-tools {release} Documentation",
        author,
        "manual",
    ),
]

latex_elements = {
    "papersize": "letterpaper",
    "pointsize": "10pt",
    "figure_align": "htbp",
}

exclude_patterns = [
    "_build",
    "sphinx",
    "*.tex",
    "TODO.md",
    "validation/**",
]

nitpicky = False
nitpick_ignore = []

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "astropy": ("https://docs.astropy.org/en/stable/", None),
}
