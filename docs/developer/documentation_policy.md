# Documentation authoring and build policy

Authored user/developer/science guides use **MyST Markdown**. reStructuredText is reserved mainly for Sphinx autodoc/autosummary API reference pages.

Sphinx provides cross-references, autodoc/autosummary, intersphinx, HTML generation, and link checking. The Read the Docs theme uses repository-owned branding assets under `docs/_static/`.

## Release documentation gates

From `docs/sphinx/`:

```bash
make clean
make html
make linkcheck
```

Equivalent direct commands are:

```bash
sphinx-build -W --keep-going -b html docs docs/_build/html
sphinx-build -W --keep-going -b linkcheck docs docs/_build/linkcheck
```

Warnings are errors for release documentation. Every authored history page must be reachable from a toctree; API pages should be included exactly once; internal links must resolve.

## Current versus historical documentation

Active documentation describes current behavior and current qualification commands. Closed milestone narratives, forensic reports, and removed checkers are preserved by Git history/release tags rather than referenced as if they were still shipped directories.

A productization/documentation-only release must not change the accepted science revision, ABI contracts, or frozen science-critical source bytes.
