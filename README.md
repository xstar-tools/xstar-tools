# xstar-atomic

Latest package note: **v0.3.150** adds explicit Python live-state containers for future XSTAR-output recreation. v0.3.149 added the first Python XSTAR-output recreation planning layer. It parses shell-style `xstar` commands and maps standard XSTAR FITS products to the live internal arrays needed for exact source-code parity. v0.3.148 restored the `xstar-local-state` benchmark preset to the historical examples/51--52 full-global branch and separates the unsafe output-table type-50 pumping experiment into `xstar-local-state-experimental-pumping`.  XSTAR source parity requires the live local `tau0(:,:)` and `bremsa(:)` arrays passed to `calc_hmc_ion.f90`/`ucalc.f90`; post-transfer `xout_lines1.fits` and `xout_cont1.fits` are not substituted into the population matrix by default.

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


Python XSTAR-output recreation planning is available for future full-emulation work:

```python
import xstar_atomic as xa

params = xa.parse_xstar_command("xstar spectrum='pow' nsteps=10 density=1 rlogxi=1.5 cfrac=1.0")
plan = xa.xstar_recreation_plan(params)
paths = xa.write_xstar_recreation_plan(params, "xstar_python_recreation_plan")
```

CLI wrapper:

```bash
PYTHONPATH=src python examples/58_plan_xstar_output_recreation.py \
  --command-file xstar_runs/helike_type69/o7_ne1e8/run_xstar.sh \
  --out-dir xstar_python_recreation_plan_o7 \
  --print-summary
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

v0.3.145 adds the first opt-in matrix injection of XSTAR type-50 photoexcitation / line pumping through `xstar-line-escape-and-pumping`.  The implementation follows the `ucalc.f90` type-50 algebra on the explicit solver `epi`/`bremsa` grid and remains a validation mode until the same-run C/O/Mg/Ca benchmark is inspected.

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


## XSTAR live-state model

v0.3.150 introduces explicit Python containers for the live arrays required to recreate XSTAR outputs from input parameters.  The state model includes `epi(:)`, `bremsa(:)`, `bremsint(:)`, `tau0(1:2,line)`, `tauc/dpthc(1:2,continuum)`, `cfrac`, `vturbi`, zone-local temperature/electron density, ion fractions, and level populations.  These containers are schema/state infrastructure, not a complete XSTAR replacement yet.

```python
import xstar_atomic as xa

params = xa.parse_xstar_command("xstar nsteps=10 density=1 rlogxi=1.5 cfrac=1.0 vturbi=100")
state = xa.create_initial_xstar_run_state_from_input(params)
print(state.zones[0].missing_core_fields())
```

Command-line skeleton writer:

```bash
PYTHONPATH=src python examples/59_create_xstar_live_state_skeleton.py \
  --command-file xstar_runs/helike_type69/o7_ne1e8/run_xstar.sh \
  --out-dir xstar_live_state_skeleton_o7 \
  --print-summary
```


### XSTAR detail live-state population

The package can populate the Python live-state containers from XSTAR detail outputs written with `lwrite=1`/`lprint=1`:

```python
import xstar_atomic as xa
state = xa.read_xstar_detail_run_state("xstar_runs/helike_type69/o7_ne1e8")
paths = xa.write_xstar_detail_state(state, "xstar_detail_live_state_o7")
```

This maps `epi(:)`, reconstructed `bremsa(:)`, `bremsint(:)`, `tau0(1:2,line)`, `tauc/dpthc`, `cfrac`, `vturbi`, local `T/ne`, ion fractions, and level populations into one Python state object.

### XSTAR detail-state type-50 rate audit

For source-code parity work, use example 61 to audit type-50 rates directly from XSTAR detail outputs:

```bash
PYTHONPATH=src python examples/61_audit_xstar_detail_type50_rates.py \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --out-dir xstar_detail_type50_rate_audit_o7 \
  --print-summary
```

This reads `xo01_detal2.fits` and `xo01_detal4.fits`, computes `ptmp1`, `ptmp2`, escaped decay, and photoexcitation using the XSTAR `calc_hmc_ion.f90`/`ucalc.f90` type-50 formula, and writes CSV/JSON/Markdown audit products.
