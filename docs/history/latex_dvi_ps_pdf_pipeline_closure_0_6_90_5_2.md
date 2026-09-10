# 0.6.90.5.2 — LATEX_DVI_PS_PDF_PIPELINE_CLOSURE

This documentation-build closure replaces the generic Sphinx `latexpdf` make-mode path with the project’s explicitly qualified EPS-aware classic TeX pipeline:

```text
SVG -> ImageMagick EPS3 -> LaTeX/DVI -> dvips -> PostScript -> ps2pdf -> PDF
```

`make latex` still uses the Sphinx LaTeX builder and the `svg_to_eps` extension to convert the four architecture SVG diagrams to EPS3. A small deterministic postprocessor then normalizes Sphinx image references from forms such as `{{backend_dispatch}.eps}` to the conventional `backend_dispatch.eps` filename spelling inside `\sphinxincludegraphics{...}`.

`make latexpdf` depends on `make latex`, executes two `latex` passes, then runs `dvips` and `ps2pdf`. It no longer calls Sphinx `-M latexpdf`, `latexmk`, `pdflatex`, or `epstopdf`. The normal documentation `release` target remains HTML plus link checking and therefore does not require TeX/Ghostscript tooling.

Read the Docs continues to build HTML with SVG assets and the pinned documentation dependency set established in 0.6.90.5.1. There are no science, ABI, production-kernel, or runtime behavior changes in this closure.
