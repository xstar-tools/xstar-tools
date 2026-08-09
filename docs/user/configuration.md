# Configuration

`XStarConfig` is the stable configuration object for public Python execution.

Supported input sources are:

```python
XStarConfig.from_par_file(...)
XStarConfig.from_mapping(...)
XStarConfig.from_fortran_run_directory(...)
```

Exactly one parameter source is allowed per configuration. Textual numerical literals read from HEASoft/IRAF-style parameter files or command-style sources are preserved as text until the qualified execution path consumes them.

Important public controls include:

- `data_dir` — XSTAR data directory;
- `output_dir` — run directory;
- `mode` — one of the five stable execution modes;
- `threads` — run-scoped thread count;
- `progress` and `log_level`;
- `reproducible` — stable-run reproducibility intent;
- `overwrite` — explicit output replacement;
- cache controls for development/reference workflows.

Advanced backend overrides are accepted only for Python-controller modes. Monolithic `zone-cpp`, `zone-all`, and `xstar-cpp` reject them so their public names remain exact contracts.

A configuration can be exported back to a deterministic HEASoft/IRAF-style parameter file:

```python
config.to_par_file("canonical-xstar.par")
```
