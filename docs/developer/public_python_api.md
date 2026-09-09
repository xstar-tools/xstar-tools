# Stable public Python API

The supported application-facing execution surface is:

```python
from xstar_tools import (
    BackendMode,
    ExecutionMode,
    XStarConfig,
    XStarData,
    XStarProducts,
    XStarResult,
    run_xstar,
)
```

The task-oriented user documentation is in {doc}`../python/execution`; generated signatures/docstrings are in {doc}`../api/public_api`.

`xstar_tools.xstar.*` remains the source-faithful scientific/runtime implementation layer. Normal applications should not depend on internal qualification modules.

## Configuration contract

Exactly one input source is required: `input_file`, `parameters`, or `fortran_run_directory`. The named constructors are preferred:

```python
XStarConfig.from_par_file(...)
XStarConfig.from_mapping(...)
XStarConfig.from_fortran_run_directory(...)
```

The stable API rejects non-empty output directories unless `overwrite=True`, validates local data explicitly, and keeps package version and scientific revision distinct.

## Result contract

`run_xstar(XStarConfig(...))` returns `XStarResult`; `XStarProducts` provides deterministic product paths and `produced_fits()` reports files actually present. Provenance records requested/actual mode, package/science identities, ABI values, native/runtime identity, atomic-data identity, thread settings, and fallback events where applicable.

## Compatibility boundary

The earlier keyword-style `run_xstar(mode=..., run_script=..., ...)` call is retained for compatibility with benchmark/legacy integrations. New applications should use the typed configuration/result API.

Changes to this public layer must keep the current behavioral regression tests green and must pass `tools/qualification/check_parity_freeze.py` plus `tools/qualification/check_source_concordance.py` when the change could touch source-faithful behavior.
