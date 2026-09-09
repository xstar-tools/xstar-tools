# Building the documentation

The documentation source under `docs/` supports HTML, LaTeX source, and PDF output through Sphinx. The build entry point is `docs/sphinx/Makefile` on POSIX systems and `docs/sphinx/make.bat` on Windows.

## Install the Sphinx dependencies

From the repository root, install the documentation extra into the Python environment used for the build:

```bash
python -m pip install -e ".[docs]"
```

The HTML and LaTeX-source builders require only the Python/Sphinx documentation dependencies. Building a PDF additionally requires a host LaTeX distribution with `latexmk` and the packages required by Sphinx's LaTeX output.

Check the external PDF toolchain with:

```bash
latexmk --version
pdflatex --version
```

A full TeX Live installation on Linux, MacTeX on macOS, or an equivalent LaTeX distribution is suitable. The project does not vendor a TeX distribution.

## HTML

```bash
cd docs/sphinx
make clean
make html
```

The HTML documentation is written to:

```text
docs/_build/html/
```

The HTML target uses `-W --keep-going`, so Sphinx warnings fail the target after the remaining sources have been processed.

## LaTeX source

Generate the complete Sphinx LaTeX document without compiling a PDF:

```bash
cd docs/sphinx
make latex
```

The primary output is:

```text
docs/_build/latex/xstar-tools.tex
```

This target is useful when the TeX source must be inspected, archived, or compiled with a site-specific LaTeX workflow.

## PDF

Generate the LaTeX source and compile the PDF through Sphinx make-mode:

```bash
cd docs/sphinx
make latexpdf
```

The expected PDF is:

```text
docs/_build/latex/xstar-tools.pdf
```

If `make latex` succeeds but `make latexpdf` fails, first verify the external LaTeX installation. Missing TeX packages or a missing `latexmk` executable are host-toolchain issues rather than failures of the Python documentation dependencies.

## Link checking and release documentation

The existing link checker remains:

```bash
make linkcheck
```

The normal documentation release target intentionally remains:

```bash
make release
```

and builds HTML plus link checking only. PDF generation is explicit because a complete LaTeX distribution is a substantially larger optional system dependency.

## Windows helper

The Windows helper exposes matching commands:

```bat
cd docs\sphinx
make.bat html
make.bat latex
make.bat latexpdf
```

The same distinction applies: `latex` generates TeX source, while `latexpdf` requires a working Windows LaTeX installation.
