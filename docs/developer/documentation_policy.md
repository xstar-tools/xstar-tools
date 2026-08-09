# Documentation authoring and build policy

Milestone 7 standardizes on **MyST Markdown** for authored user/developer/science guides and **reStructuredText only where Sphinx autodoc/autosummary is clearer**, primarily generated API reference pages.

Rationale:

- the project, roadmap, handoffs, and source-concordance documents are already Markdown;
- MyST keeps user-facing documentation easy to review outside Sphinx;
- Sphinx remains the build engine for cross-references, autodoc/autosummary, intersphinx, HTML, and link checking;
- generated API pages can use concise RST `automodule` directives without forcing all authored prose into RST.

Release documentation policy:

```bash
sphinx-build -W --keep-going -b html docs docs/_build/html
sphinx-build -W --keep-going -b linkcheck docs docs/_build/linkcheck
```

Warnings are errors for release builds. The CI documentation workflow performs both builds. GitHub Pages deployment is configured for successful `main` builds; forks can run the build/check jobs without deployment permissions.

Historical parity/attribution reports are not included in the user toctree. They remain under the top-level `historical/` archive in history-preserving source releases.
