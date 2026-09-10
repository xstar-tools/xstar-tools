# Building the documentation

The documentation source under `docs/` supports HTML, LaTeX source, and PDF output through Sphinx. The build entry point is `docs/sphinx/Makefile` on POSIX systems and `docs/sphinx/make.bat` on Windows.

## Install the Sphinx dependencies

From the repository root, install the documentation extra into the Python environment used for the build:

```bash
python -m pip install -e ".[docs]"
```

The HTML and LaTeX-source builders require only the Python/Sphinx documentation dependencies. Building a PDF additionally requires a host LaTeX distribution with `latexmk` and the packages required by Sphinx's LaTeX output.

For reproducible hosted builds, `docs/requirements.txt` pins the warning-clean Sphinx/MyST toolchain used by the accepted documentation closure and includes the RTD theme plus NumPy/Astropy needed by autodoc imports. The top-level `.readthedocs.yaml` explicitly installs that requirements file. Read the Docs must not rely on its default bare-Sphinx environment because `conf.py` loads `myst_parser` and `sphinx_rtd_theme`, and the generated API pages import modules that depend on NumPy/Astropy.

A hosted build therefore uses the equivalent dependency step:

```text
python:
  install:
    - requirements: docs/requirements.txt
```

The current hosted documentation toolchain is Sphinx 8.2.3, MyST Parser 5.1.0, and `sphinx-rtd-theme` 3.1.0 on Python 3.13.

Check the external PDF/image toolchain with:

```bash
convert --version
latexmk --version
pdflatex --version
epstopdf --version
```

The LaTeX builder prefers the ImageMagick 7 `magick` launcher and falls back to the ImageMagick 6 `convert` command on POSIX systems. The four architecture SVG diagrams are converted with the ImageMagick EPS3 coder; this is equivalent to `convert input.svg eps3:output.eps`. The HTML builder continues to use the original SVG files.

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

During this target Sphinx converts each SVG architecture diagram to EPS3 using the equivalent of `convert input.svg eps3:output.eps`. The generated `xstar-tools.tex` therefore references `.eps` images rather than `.svg`; HTML remains unchanged and continues to use SVG.

The converted build assets include `backend_dispatch.eps`, `local_zone_solve.eps`, `controller_radial_flow.eps`, and `publication_ownership.eps`.

This target is useful when the TeX source must be inspected, archived, or compiled with a site-specific LaTeX workflow.

## PDF

Generate the LaTeX source and compile the PDF through Sphinx make-mode. Sphinx requires `-M` to appear before the source/output directories and before normal warning options; the project Makefile uses that ordering:

```bash
cd docs/sphinx
make latexpdf
```

The expected PDF is:

```text
docs/_build/latex/xstar-tools.pdf
```

If `make latex` succeeds but `make latexpdf` fails, first verify the external LaTeX installation. Missing TeX packages, `latexmk`, `epstopdf`, or ImageMagick are host-toolchain issues rather than failures of the Python documentation dependencies. The generated TeX intentionally retains `.eps` references; `epstopdf` provides the PDFLaTeX bridge when the PDF is compiled.

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
