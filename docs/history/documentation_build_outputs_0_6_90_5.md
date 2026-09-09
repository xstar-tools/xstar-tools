# 0.6.90.5 — DOCUMENTATION_BUILD_OUTPUTS

`0.6.90.5` extends the accepted `0.6.90.4` documentation baseline with explicit Sphinx LaTeX and PDF build targets. It is a documentation/build-metadata milestone only; the accepted XSTAR science revision, science-critical source hashes, and public ABI values are unchanged.

## Changes

- Added `make latex` under `docs/sphinx/` to generate `docs/_build/latex/xstar-tools.tex` with warnings treated as errors.
- Added `make latexpdf` to invoke Sphinx `latexpdf` make-mode and produce `docs/_build/latex/xstar-tools.pdf` when a host LaTeX toolchain is installed.
- Added equivalent `latex` and `latexpdf` commands to `docs/sphinx/make.bat`.
- Added explicit `latex_documents` metadata so the generated source file is predictably named `xstar-tools.tex` and the compiled manual `xstar-tools.pdf`.
- Added restrained LaTeX defaults for letter paper, 10-point text, and figure placement.
- Added a developer documentation page describing HTML, TeX, PDF, link-check, dependency, and output-location workflows.
- Kept `make release` as HTML plus link checking so ordinary documentation/release validation does not require a system TeX installation.

## Scientific boundary

The frozen science revision remains `0.6.48.12.3.45.3.3.8`. C API ABI `60487`, production-zone ABI `6048110`, fixed-state ABIs `60486`/`60488`, and XSPEC-table ABI `1` are unchanged. No science-critical source file is modified by this milestone.
