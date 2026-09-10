# 0.6.90.5.1 - LATEXPDF_MAKE_MODE_EPS_GRAPHICS_AND_READTHEDOCS_CLOSURE

This documentation-build hotfix corrects the Sphinx make-mode invocation introduced in 0.6.90.5, establishes vector EPS graphics for the LaTeX documentation path, and closes the hosted Read the Docs dependency boundary.

The `latexpdf` target now places `-M latexpdf` first, as required by Sphinx make-mode, followed by the source/build directories and warning options. The `latex` and `latexpdf` builders use a local Sphinx image post-transform that converts SVG diagrams to EPS3 through ImageMagick. The generated TeX references `.eps` images, while HTML continues to use the original SVG files.

The four current architecture diagrams covered by this path are `backend_dispatch`, `local_zone_solve`, `controller_radial_flow`, and `publication_ownership`. PDF compilation remains an optional host-toolchain operation and requires ImageMagick plus the LaTeX/latexmk/epstopdf tooling.

The failed Read the Docs build 34879414 showed that the repository configuration left `python.install` commented out, so RTD installed only bare Sphinx 9.1.0 and then failed while importing `myst_parser`. The current configuration adds `docs/requirements.txt` and makes `.readthedocs.yaml` install it explicitly. The hosted requirements also include `sphinx_rtd_theme`, NumPy, and Astropy so the configured theme and autodoc imports are available before Sphinx reads the source tree.

There are no science, ABI, production-kernel, or runtime behavior changes in this closure.
