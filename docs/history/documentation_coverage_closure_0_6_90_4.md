# 0.6.90.4 — DOCUMENTATION_COVERAGE_CLOSURE

`0.6.90.4` is a documentation/productization-only closure on top of the cleaned `0.6.90.3` repository. It does not change the accepted science revision, public ABI numbers, or science-critical source bytes.

The closure:

- integrates the repository-owned Sphinx `_static` branding bundle (logo, favicon, CSS, and corrected xstar-tools sidebar JavaScript);
- closes all Sphinx warnings reported against `0.6.90.3`, including autosummary import cycles, heading-level consistency, history-toctree inclusion, and duplicate API-toctree references;
- adds task-oriented Python documentation for stable execution, the `XSTARAtomic` database API, XSTAR FITS output readers, and Python XSTAR2XSPEC wrappers;
- adds a unified CLI reference and classifies all installed console scripts as primary, specialist, compatibility, or development/qualification interfaces;
- adds dedicated native references for `xstar-xspec-initable` and `xstar-xspec-table`;
- completes the option reference for `xstar-cpp`, `xstar-xspec`, and `xstar-xspec-mpi`;
- makes the Windows guide version-neutral and removes instructions that depended on retired milestone runners;
- removes active-documentation references to historical directories/checkers that are no longer shipped after `0.6.90.3`.

Release documentation is expected to pass Sphinx HTML and linkcheck builds with warnings treated as errors when the documentation dependencies and network-required intersphinx/linkcheck resources are available.
