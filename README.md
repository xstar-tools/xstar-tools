# xstar-atomic

Latest package note: **v0.3.144** adds the first opt-in source-code-matched XSTAR type-50 line-pumping matrix mode.  The `xstar-local-state` preset now uses `type50_bound_bound_treatment="xstar-line-escape-and-pumping"`: downward type-50 decay uses same-run line-depth escape probabilities, while the lower-to-upper photoexcitation branch follows the `ucalc.f90` formula using the explicit solver `epi`/`bremsa` radiation grid, `nbinc` binning, `vtherm`, `flinabs=1`, and `cfrac`.  This is the first physics implementation of type-50 pumping and should be validated against the C V / O VII / Mg XI / Ca XIX same-run XSTAR benchmark before it is treated as a final default.

- `docs/user_guide.md`
- `docs/user_guide.tex`
- `docs/sphinx/source/user_guide.rst`
- `docs/sphinx/source/api.rst`

The simple workflow API includes:

```python
import xstar_atomic as xa

db = xa.open_database("/path/to/atdb.fits")
levels = xa.get_levels("O VII", db=db)
lines = xa.get_lines("O VII", db=db, wavelength=(21.4, 22.2))
rate = xa.calc_rate("type50", aij_s_inv=..., oscillator_strength=..., wavelength_A=...)
triplet = xa.calc_triplet("O VII", rows=xstar_line_rows)
```

The expert object API exposes namespace-style entry points:

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic("/path/to/atdb.fits")
ctx = db.context.from_xstar_run("xstar_runs/helike_type69/o7_ne1e8", ion="O VII")
rate = db.rates.type50("O VII", aij_s_inv=..., oscillator_strength=..., wavelength_A=...)
comparison = db.validate.compare_xstar_run("xstar_runs/helike_type69/o7_ne1e8", ion="O VII")
```

Public namespace modules are available for future API growth: `xstar_atomic.rates`, `xstar_atomic.solve`, `xstar_atomic.matrix`, `xstar_atomic.validate`, and `xstar_atomic.runs`.
The same-run XSTAR reproduction API is now available:

```python
target = xa.build_xstar_local_target(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
)
comparison = xa.reproduce_xstar_run(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
    run_solver=False,
)
```

Single-ion CLI wrapper:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --out-dir xstar_o7_local_reproduction \
  --print-summary
```

Four-ion standard suite:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --standard-helike-suite \
  --xstar-runs-root xstar_runs \
  --out-dir helike_local_reproduction_suite \
  --print-summary
```

Four-ion solver comparison using the local-state validation preset:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --standard-helike-suite \
  --xstar-runs-root xstar_runs \
  --run-solver \
  --solver-preset xstar-local-state \
  --out-dir helike_local_reproduction_suite_solver_v03144 \
  --print-summary
```

The quick workflow solver remains available with `--solver-preset workflow-default`, but it is not the same path used in the earlier source-code-first local-state validations.

v0.3.144 adds the first opt-in matrix injection of XSTAR type-50 photoexcitation / line pumping through `xstar-line-escape-and-pumping`.  The implementation follows the `ucalc.f90` type-50 algebra on the explicit solver `epi`/`bremsa` grid and remains a validation mode until the same-run C/O/Mg/Ca benchmark is inspected.

## Earlier v0.3.128 API infrastructure

New public objects and functions:

```python
from xstar_atomic import (
    LocalPlasmaState,
    RadiationField,
    EscapeContext,
    XSTARContext,
    RateEvaluation,
    evaluate_type50_bound_bound,
    type50_line_pumping,
)
```

## Examples

See `examples/README.md` for grouped runnable examples and recommended learning paths. The most advanced validation examples remain diagnostic/source-code-first workflows and may require same-run XSTAR outputs.
