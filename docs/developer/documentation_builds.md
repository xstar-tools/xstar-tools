# Building the documentation

The documentation source under `docs/` supports HTML, LaTeX source, and PDF output through Sphinx. The build entry point is `docs/sphinx/Makefile` on POSIX systems and `docs/sphinx/make.bat` on Windows.

## Install the Sphinx dependencies

From the repository root, install the documentation extra into the Python environment used for the build:

```bash
python -m pip install -e ".[docs]"
```

For reproducible Read the Docs hosted builds, `docs/requirements.txt` pins the warning-clean Sphinx/MyST toolchain used by the accepted documentation closure and includes the RTD theme plus NumPy/Astropy needed by autodoc imports. The top-level `.readthedocs.yaml` explicitly installs that requirements file.

A hosted build therefore uses the equivalent dependency step:

```text
python:
  install:
    - requirements: docs/requirements.txt
```

The current hosted documentation toolchain is Sphinx 8.2.3, MyST Parser 5.1.0, and `sphinx-rtd-theme` 3.1.0 on Python 3.13.

## External tools for LaTeX/PDF

The HTML builder needs only the Python/Sphinx documentation environment. The LaTeX builder additionally needs ImageMagick for SVG-to-EPS3 conversion. The PDF target uses the classic DVI/PostScript pipeline and therefore requires `latex`, `dvips`, and `ps2pdf`.

Check the external tools with:

```bash
convert --version
latex --version
dvips --version
ps2pdf --version
```

The SVG converter prefers the ImageMagick 7 `magick` launcher and falls back to the ImageMagick 6 `convert` command on POSIX systems. The four architecture SVG diagrams are converted with the ImageMagick EPS3 coder, equivalent to:

```bash
convert input.svg eps3:output.eps
```

HTML continues to use the original SVG files.

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

Generate the Sphinx LaTeX document without compiling a PDF:

```bash
cd docs/sphinx
make latex
```

The primary output is:

```text
docs/_build/latex/xstar-tools.tex
```

During this target Sphinx converts each architecture SVG to EPS3. Sphinx normally emits references such as:

```latex
\sphinxincludegraphics{{backend_dispatch}.eps}
```

The project then normalizes that generated spelling to the conventional filename form:

```latex
\sphinxincludegraphics{backend_dispatch.eps}
```

The same normalization applies to `local_zone_solve.eps`, `controller_radial_flow.eps`, and `publication_ownership.eps`. Only generated LaTeX is changed; HTML continues to use SVG.

The converted EPS assets are copied into `docs/_build/latex/` beside `xstar-tools.tex`.

## PDF: LaTeX -> DVI -> PostScript -> PDF

The project intentionally uses the classic EPS-aware pipeline rather than Sphinx `-M latexpdf`/`latexmk`:

```text
SVG -> ImageMagick EPS3 -> LaTeX/DVI -> dvips -> PostScript -> ps2pdf -> PDF
```

Run:

```bash
cd docs/sphinx
make latexpdf
```

The target is equivalent to:

```bash
make latex
cd ../_build/latex
latex -interaction=nonstopmode -halt-on-error xstar-tools.tex
latex -interaction=nonstopmode -halt-on-error xstar-tools.tex
dvips -o xstar-tools.ps xstar-tools.dvi
ps2pdf xstar-tools.ps xstar-tools.pdf
```

Two LaTeX passes are used so the table of contents, references, and page numbers can settle before the DVI is converted to PostScript.

The expected outputs are:

```text
docs/_build/latex/xstar-tools.tex
docs/_build/latex/xstar-tools.dvi
docs/_build/latex/xstar-tools.ps
docs/_build/latex/xstar-tools.pdf
```

The LaTeX configuration does not load `epstopdf`; EPS is consumed natively by the `latex`/`dvips` path.

## Link checking and release documentation

The link checker remains:

```bash
make linkcheck
```

The normal documentation release target remains:

```bash
make release
```

and builds HTML plus link checking only. PDF generation stays explicit because ImageMagick, TeX, dvips, and Ghostscript are optional host tools.

## Windows helper

The Windows helper exposes matching commands:

```bat
cd docs\sphinx
make.bat html
make.bat latex
make.bat latexpdf
```

The Windows `latexpdf` command uses the same two-pass `latex` -> `dvips` -> `ps2pdf` pipeline when those programs are available on `PATH`.
