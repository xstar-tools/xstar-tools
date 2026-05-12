# xstar-atomic user guide

`xstar-atomic` reads XSTAR's packed `atdb.fits` atomic database, evaluates selected XSTAR rate formulae, builds prototype level-population products, and provides source-code-first validation tools for comparing against same-run XSTAR outputs.

The package is not intended to replace XSTAR. Its purpose is to make the atomic-data and local-rate pieces auditable from Python, with explicit provenance for the XSTAR record, source-code branch, local plasma state, radiation field, escape treatment, and population-matrix term.

```python
import xstar_atomic as xa
from xstar_atomic import XSTARAtomic
```

## Contents

1. [Installation and data setup](#1-installation-and-data-setup)
2. [Quick start](#2-quick-start)
3. [Public API cookbook: workflow-first and expert APIs](#3-public-api-cookbook-workflow-first-and-expert-apis)
4. [Atomic database access](#4-atomic-database-access)
5. [Local context objects](#5-local-context-objects)
6. [Source-code-aligned rate evaluators](#6-source-code-aligned-rate-evaluators)
7. [Matrix, solver, and emissivity workflows](#7-matrix-solver-and-emissivity-workflows)
8. [XSTAR-output readers and same-run validation](#8-xstar-output-readers-and-same-run-validation)
9. [Audit workflows](#9-audit-workflows)
10. [Examples and source-module migration](#10-examples-and-source-module-migration)
11. [Validation and tests](#11-validation-and-tests)
12. [Roadmap](#12-roadmap)


## 1. Installation and data setup

### 1.1 Install the package

From the source tree:

```bash
python -m pip install -e .
```

For development and tests:

```bash
python -m pip install -e .[dev]
PYTHONPATH=src pytest -q
```

Optional extras:

```bash
python -m pip install -e .[docs]
python -m pip install -e .[hdf5]
python -m pip install -e .[sparse]
```

### 1.2 Configure `atdb.fits`

The main database is XSTAR's packed atomic database, usually located at:

```text
xstar/data/atdb.fits
```

You can provide it explicitly:

```python
db = XSTARAtomic("/path/to/xstar/data/atdb.fits")
```

or configure a data path:

```python
import xstar_atomic as xa

xa.set_data_path("/path/to/xstar/data/atdb.fits")
print(xa.get_data_path())
```

Environment variables and the package `datapath` file can also be used by the data helpers.

### 1.3 Command-line access without installation

Most tools can be run directly from the source tree:

```bash
PYTHONPATH=src python -m xstar_atomic.lines /path/to/atdb.fits \
  --element O --ion-stage 8 \
  --line-search --wavelength-min 18.8 --wavelength-max 19.1
```

## 2. Quick start

### 2.1 Open the database and inspect the hierarchy

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic("/path/to/xstar/data/atdb.fits")
print(db.summary())
```

### 2.2 Extract levels and lines

```python
levels = db.levels("O VII")
lines = db.lines("O VII", wavelength=(21.4, 22.2), slim=True)
```

### 2.3 Evaluate collision and emissivity products

```python
coll = db.collisions("O VIII", temperatures=[1e6, 3e6], wavelength=(18.8, 19.1))
emiss = db.emissivity("O VIII", temperatures=[1e6, 3e6], wavelength=(18.8, 19.1))
```

### 2.4 Build an audit context and evaluate a type-50 rate

The v0.3.128 API infrastructure adds explicit context objects. These are required because XSTAR rates can depend on the local state and radiation/escape terms, not only on the atomic record.

```python
from xstar_atomic import LocalPlasmaState, EscapeContext, evaluate_type50_bound_bound

state = LocalPlasmaState(
    temperature_K=7.66552e4,
    electron_density_cm3=1.20466e8,
    log_xi=1.5,
)

escape = EscapeContext(
    cfrac=0.0,
    ptmp1=0.2,
    ptmp2=0.3,
    flinabs_ptmp1=0.8,
)

rate = evaluate_type50_bound_bound(
    aij_s_inv=1.0e12,
    oscillator_strength=0.7,
    wavelength_A=21.602,
    vtherm_cm_s=1.0e7,
    bremsa_nb1=1.0e5,
    plasma_state=state,
    escape_context=escape,
    ion="O VII",
)

print(rate.status)
print(rate.lower_to_upper_photoexcitation_s_inv)
print(rate.upper_to_lower_escaped_decay_s_inv)
print(rate.source_formula)
```

In v0.3.128 through v0.3.133 this evaluator is **audit-only**. It records the XSTAR `ucalc.f90` type-50 branch and returns a `RateEvaluation` object; it does not inject photoexcitation into the population solver.

## 3. Public API cookbook: workflow-first and expert APIs

This section is the canonical user-facing description of the public API added in v0.3.131 and clarified in v0.3.132--v0.3.139.  The design follows the useful `chianti-tools` pattern: common science tasks have short workflow-first functions, while advanced XSTAR-alignment work remains available through explicit context, rate, audit, and validation objects.

There are three supported public layers:

| Layer | Use when | Example |
|---|---|---|
| Module-level workflow API | You want a quick notebook/script call without navigating internal modules. | `xa.get_lines("O VII", db=db)` |
| `XSTARAtomic` object API | You want to keep one opened `atdb.fits` handle and reuse cached indices. | `db.lines("O VII", wavelength=(21.4, 22.2))` |
| Expert namespace API | You want source-code-first contexts, rate evaluators, audits, validation, and future matrix/solver workflows. | `db.rates.type50("O VII", ...)` |

The current API intentionally separates **implemented stable helpers** from **future namespace placeholders**.  In v0.3.132--v0.3.139, `db.rates.type50(...)`, `db.audit.type50_line_pumping(...)`, `db.context.*`, and `db.validate.compare_xstar_run(...)` and `db.validate.reproduce_xstar_run(...)` are callable.  Some planned functions, such as full `db.audit.resonance_deficit(...)` and full type-50 solver injection, are still intentionally not active as public solver physics.

### 3.1 Module-level workflow API

Use this style for quick analysis, examples, and notebooks.  These calls mirror the workflow-first style of `chianti-tools` while keeping XSTAR-specific provenance available in returned dictionaries or result objects.

```python
import xstar_atomic as xa

# Open the database once and reuse it.
db = xa.open_database("/path/to/xstar/data/atdb.fits")

# Atomic structure and line queries.
levels = xa.get_levels("O VII", db=db)
lines = xa.get_lines("O VII", db=db, wavelength=(21.4, 22.2), slim=True)
wavelengths = xa.get_wavelengths("O VIII", db=db, wavelength=(18.8, 19.1))
match = xa.match_line("O VIII", db=db, wavelength=18.969, tolerance_A=0.02)

# Atomic process products.
coll = xa.get_collisions("O VIII", db=db, temperatures=[1e6, 3e6])
rr = xa.get_recombination("O VII", db=db, temperatures=[1e6])
pi = xa.get_photoionization("O VII", db=db)
emiss = xa.calc_emissivity("O VIII", db=db, temperatures=[1e6], wavelength=(18.8, 19.1))
```

The same calls can receive `fitsfile="/path/to/atdb.fits"` instead of `db=db`.  Passing an opened `db` is faster for repeated queries because the hierarchy/index is reused.

### 3.2 Top-level API function summary

| Function | Purpose | Status |
|---|---|---|
| `xa.open_database(...)` | Open `atdb.fits` as an `XSTARAtomic` object. | implemented |
| `xa.get_levels(...)` | Return decoded level records for an ion. | implemented |
| `xa.get_lines(...)` | Return decoded radiative line records. | implemented |
| `xa.get_wavelengths(...)` | Return sorted wavelengths from selected lines. | implemented |
| `xa.get_energies(...)` | Return sorted line energies when available. | implemented |
| `xa.match_line(...)`, `xa.match_lines(...)` | Match nearest line(s) by wavelength or energy. | implemented |
| `xa.get_collisions(...)` | Return collision summaries and evaluated rows. | implemented |
| `xa.get_photoionization(...)` | Return photoionization summaries/grids. | implemented |
| `xa.get_recombination(...)` | Return recombination and optional source rows. | implemented |
| `xa.calc_emissivity(...)` | Build direct-excitation emissivity products. | implemented |
| `xa.context_from_values(...)` | Build an `XSTARContext` from explicit local values. | implemented |
| `xa.context_from_xstar_run(...)` | Build an `XSTARContext` from an XSTAR output directory. | implemented, lightweight |
| `xa.calc_rate("type50", ...)` | Dispatch to the audit-only type-50 evaluator. | implemented for type 50 |
| `xa.calc_triplet(...)` | Summarize He-like f/i/r line rows. | implemented for supplied/same-run rows |
| `xa.solve_populations(...)` | Wrapper around the current diagnostic population solver. | prototype |
| `xa.build_matrix(...)` | Return available matrix-related solver products. | prototype |
| `xa.build_xstar_local_target(...)` | Extract exact local-state and triplet targets from `xout_abund1.fits`/`xout_lines1.fits`. | implemented |
| `xa.reproduce_xstar_run(...)` | Build the exact XSTAR target and optionally compare the current solver. | implemented |

### 3.3 Function-by-function top-level API examples

The examples below make each top-level public helper visible as a copy-pasteable call.  They assume:

```python
import xstar_atomic as xa

ATDB = "/path/to/xstar/data/atdb.fits"
db = xa.open_database(ATDB, index_cache=True)
```

#### Database and data-path helpers

```python
# xa.open_database(...): open one reusable database handle.
db = xa.open_database(ATDB, index_cache=True)

# xa.set_data_path(...) and xa.get_data_path(...): configure a default ATDB path.
xa.set_data_path(ATDB)
print(xa.get_data_path())

# xa.find_atdb_file(...) and xa.resolve_atdb_path(...): locate the database.
candidate = xa.find_atdb_file()
resolved = xa.resolve_atdb_path(ATDB)

# xa.download_data(...): fetch or configure the XSTAR database when needed.
# Use this only when you want the helper to interact with the configured data path.
# db_path = xa.download_data()
```

#### Atomic level and line helpers

```python
# xa.get_levels(...): decoded level rows.
levels = xa.get_levels("O VII", db=db)

# xa.get_lines(...): decoded radiative lines in a wavelength window.
lines = xa.get_lines("O VII", db=db, wavelength=(21.4, 22.2), slim=True)

# xa.get_wavelengths(...) and xa.get_energies(...): quick arrays for matching/plots.
wavelengths = xa.get_wavelengths("O VIII", db=db, wavelength=(18.8, 19.1))
energies = xa.get_energies("O VIII", db=db, wavelength=(18.8, 19.1))

# xa.match_line(...) and xa.match_lines(...): nearest line identification.
ly_alpha = xa.match_line("O VIII", db=db, wavelength=18.969, tolerance_A=0.02)
matches = xa.match_lines("O VIII", db=db, wavelengths=[18.969, 18.973], tolerance_A=0.03)
```

#### Atomic-process helpers

```python
# xa.get_collisions(...): collision summaries and evaluated rates.
collisions = xa.get_collisions(
    "O VIII",
    db=db,
    temperatures=[1.0e6, 3.0e6],
    wavelength=(18.8, 19.1),
)

# xa.get_photoionization(...): bound-free records, optionally including grids.
photoionization = xa.get_photoionization("O VII", db=db, include_grid=True)

# xa.get_recombination(...): recombination records/evaluations.
recombination = xa.get_recombination(
    "O VII",
    db=db,
    temperatures=[1.0e6],
    electron_densities=[1.0e8],
)

# xa.calc_emissivity(...): direct-excitation emissivity products.
emissivity = xa.calc_emissivity(
    "O VIII",
    db=db,
    temperatures=[1.0e6],
    wavelength=(18.8, 19.1),
)
```

#### Context helpers

```python
# xa.LocalPlasmaState(...): local thermodynamic/ionization state.
state = xa.LocalPlasmaState(
    temperature_K=7.66552e4,
    electron_density_cm3=1.20466e8,
    log_xi=1.5,
    ion_fraction=0.255926,
)

# xa.RadiationField(...): sampled local radiation field.
radiation = xa.RadiationField.from_pairs(
    [(0.50, 1.0e4), (0.574, 2.5e4), (1.00, 1.0e4)],
    source="manual example",
)

# xa.EscapeContext(...): escape/covering quantities used by type-50 audits.
escape = xa.EscapeContext(cfrac=0.0, ptmp1=0.2, ptmp2=0.3, flinabs_ptmp1=0.8)

# xa.context_from_values(...): combine explicit local inputs into XSTARContext.
ctx = xa.context_from_values(
    ion="O VII",
    temperature_K=state.temperature_K,
    electron_density_cm3=state.electron_density_cm3,
    log_xi=state.log_xi,
    ion_fraction=state.ion_fraction,
    radiation=radiation,
    escape=escape,
)

# xa.context_from_xstar_run(...): start from an XSTAR run directory when available.
ctx_from_run = xa.context_from_xstar_run(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
    selection="max_fraction",
)
```

#### Rate, triplet, solver, and matrix helpers

```python
# xa.calc_rate(...): dispatch to an implemented provenance-rich rate evaluator.
rate = xa.calc_rate(
    "type50",
    ion="O VII",
    lower_level=1,
    upper_level=7,
    aij_s_inv=3.0e12,
    oscillator_strength=0.7,
    wavelength_A=21.602,
    vtherm_cm_s=1.0e7,
    bremsa_nb1=2.5e4,
    plasma_state=state,
    radiation=radiation,
    escape=escape,
)
assert isinstance(rate, xa.RateEvaluation)
print(rate.to_dict())

# xa.calc_triplet(...): summarize existing f/i/r rows from XSTAR outputs or CSV rows.
triplet = xa.calc_triplet(
    "O VII",
    rows=[
        {"upper_level": "1s1.2s1.3S_1", "emit_outward": 8.0},
        {"upper_level": "1s1.2p1.3P_1", "emit_outward": 1.5},
        {"upper_level": "1s1.2p1.1P_1", "emit_outward": 2.0},
    ],
)
print(triplet.to_dict())

# xa.solve_populations(...): prototype wrapper around the current diagnostic solver.
solution = xa.solve_populations("O VII", db=db, context=ctx)

# xa.build_matrix(...): prototype helper returning available matrix-related products.
matrix_products = xa.build_matrix("O VII", db=db, context=ctx)
```

#### Expert object namespace examples

```python
# db.context.* mirrors the module-level context helpers.
ctx = db.context.from_values(
    ion="O VII",
    temperature_K=7.66552e4,
    electron_density_cm3=1.20466e8,
    log_xi=1.5,
)
ctx = db.context.from_xstar_run("xstar_runs/helike_type69/o7_ne1e8", ion="O VII")

# db.rates.type50(...): object-oriented access to the audit-only type-50 evaluator.
rate = db.rates.type50(
    "O VII",
    aij_s_inv=3.0e12,
    oscillator_strength=0.7,
    wavelength_A=21.602,
    vtherm_cm_s=1.0e7,
    bremsa_nb1=2.5e4,
    ptmp1=0.2,
    ptmp2=0.3,
    flinabs_ptmp1=0.8,
    cfrac=0.0,
)

# db.audit.type50_line_pumping(...): reusable Python API behind example 55.
audit = db.audit.type50_line_pumping(
    "helike_local_state_validation_v03131/helike_local_state_cases.csv",
    solver_root=".",
    xstar_source_root="../xstar",
    out_dir="helike_type50_line_pumping_audit_v03131",
)

# db.validate.compare_xstar_run(...): lightweight same-run triplet/context comparison.
comparison = db.validate.compare_xstar_run(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
    wavelength=(21.4, 22.2),
)

# db.solve.ion(...) and db.matrix.build_ion(...): prototype object wrappers.
solution = db.solve.ion("O VII", context=ctx)
matrix_products = db.matrix.build_ion("O VII", context=ctx)
```

#### Same-run XSTAR reproduction benchmark helpers

The first benchmark step after API reorganization is to reproduce exactly what the same XSTAR run wrote to `xout_abund1.fits` and `xout_lines1.fits`.  The helper below is target extraction: it records XSTAR local `T`, `ne`, `log xi`, ion fraction, and triplet `f/i/r` before any solver correction is attempted.

```python
# xa.build_xstar_local_target(...): exact local-state and triplet target.
target = xa.build_xstar_local_target(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
)
print(target.local_state_row())
print(target.triplet_row())

# xa.reproduce_xstar_run(...): target extraction plus optional solver residuals.
comparison = xa.reproduce_xstar_run(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
    run_solver=False,
)
print(comparison.comparison_row())

# The object API exposes the same workflow.
comparison = db.validate.reproduce_xstar_run(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
)
```

The companion CLI wrapper is:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --out-dir xstar_o7_local_reproduction \
  --print-summary
```

For the C V / O VII / Mg XI / Ca XIX benchmark suite, use the built-in standard case table:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --standard-helike-suite \
  --xstar-runs-root xstar_runs \
  --out-dir helike_local_reproduction_suite \
  --print-summary
```

For a solver comparison, use the source-code-first local-state preset rather than the lightweight workflow-default solver:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --standard-helike-suite \
  --xstar-runs-root xstar_runs \
  --run-solver \
  --solver-preset xstar-local-state \
  --out-dir helike_local_reproduction_suite_solver_v03139 \
  --print-summary
```

The comparison CSV and Markdown include XSTAR and solver `f/i/r`, `R=f/i`, `G=(f+i)/r`, L2, residuals, and the solver-triplet source.

To create an editable CSV first, run:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --write-standard-cases-csv helike_reproduction_cases.csv \
  --xstar-runs-root xstar_runs \
  --print-summary
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --cases-csv helike_reproduction_cases.csv \
  --out-dir helike_local_reproduction_suite \
  --print-summary
```

### 3.4 Open and summarize an XSTAR database object

```python
import xstar_atomic as xa
from xstar_atomic import XSTARAtomic

xa.set_data_path("/path/to/xstar/data/atdb.fits")
db = XSTARAtomic(index_cache=True, index_cache_format="npz")
summary = db.summary()
print(summary)
```

Recommended practice for repeated workflows:

```python
with xa.open_database("/path/to/xstar/data/atdb.fits", index_cache=True) as db:
    o7 = db.lines("O VII", wavelength=(21.4, 22.2), slim=True)
    o8 = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)
```

### 3.5 Query lines, levels, and wavelength windows

```python
levels = db.levels("O VII")
triplet_lines = db.lines("O VII", wavelength=(21.4, 22.2), slim=True)
lya = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)

for line in triplet_lines:
    print(line.get("wavelength_A"), line.get("lower_level"), line.get("upper_level"))
```

Use this layer for quick inspection and for building small validation tables. Use the lower-level record objects only when you need raw ATDB indices.

### 3.6 Evaluate collisional, photoionization, recombination, and emissivity products

```python
coll = db.collisions(
    "O VIII",
    temperatures=[1.0e6, 3.0e6, 1.0e7],
    wavelength=(18.8, 19.1),
)

pi = db.photoionization("O VII", include_grid=True)

rr = db.recombination(
    "O VII",
    temperatures=[1.0e6],
    electron_densities=[1.0e8],
    source_mode="none",
)

emiss = db.emissivity(
    "O VIII",
    temperatures=[1.0e6, 3.0e6],
    wavelength=(18.8, 19.1),
)

print(len(coll["summary"]), len(coll["evaluated"]))
print(rr["summary"])
print(emiss["summary"])
```

### 3.7 Build a local XSTAR-style context

```python
from xstar_atomic import LocalPlasmaState, RadiationField, EscapeContext, context_from_values

state = LocalPlasmaState(
    temperature_K=7.66552e4,
    electron_density_cm3=1.20466e8,
    log_xi=1.5,
    ion_fraction=0.255926,
)

rad = RadiationField.from_pairs([
    (0.50, 1.0e4),
    (0.574, 2.5e4),
    (1.00, 1.0e4),
])

escape = EscapeContext(
    cfrac=0.0,
    ptmp1=0.2,
    ptmp2=0.3,
    flinabs_ptmp1=0.8,
)

ctx = context_from_values(
    ion="O VII",
    temperature_K=state.temperature_K,
    electron_density_cm3=state.electron_density_cm3,
    log_xi=state.log_xi,
    ion_fraction=state.ion_fraction,
    radiation=rad,
    escape=escape,
)
```

These objects are intentionally explicit. XSTAR rate terms can depend on local temperature, electron density, radiation-field binning, covering factor, and escape probabilities, so those values should not be hidden inside scalar helper functions.

To start from an existing XSTAR run directory:

```python
ctx = xa.context_from_xstar_run(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
    selection="max_fraction",
)
```

### 3.8 Evaluate the audit-only type-50 bound-bound branch

```python
from xstar_atomic import evaluate_type50_bound_bound

rate = evaluate_type50_bound_bound(
    aij_s_inv=3.0e12,
    oscillator_strength=0.7,
    wavelength_A=21.602,
    vtherm_cm_s=1.0e7,
    bremsa_nb1=2.5e4,
    plasma_state=state,
    radiation=rad,
    escape=escape,
    ion="O VII",
    lower_level=1,
    upper_level=7,
)

print(rate.value_s_inv)
print(rate.lower_to_upper_photoexcitation_s_inv)
print(rate.upper_to_lower_escaped_decay_s_inv)
print(rate.source_formula)
print(rate.terms)
```

In v0.3.128 through v0.3.133 this evaluator remains audit-only. It records the XSTAR `ucalc.f90` type-50 branch and branch swap but does not modify the level-population solver.

### 3.9 Expert `XSTARAtomic` namespace API

The object API exposes namespace-style entry points matching the future public API plan:

```python
ctx = db.context.from_values(
    ion="O VII",
    temperature_K=7.66552e4,
    electron_density_cm3=1.20466e8,
    log_xi=1.5,
)

rate = db.rates.type50(
    "O VII",
    aij_s_inv=3.0e12,
    oscillator_strength=0.7,
    wavelength_A=21.602,
    vtherm_cm_s=1.0e7,
    bremsa_nb1=2.5e4,
    ptmp1=0.2,
    ptmp2=0.3,
    flinabs_ptmp1=0.8,
    cfrac=0.0,
)

# Uses xout_abund1.fits to choose a local XSTAR zone when available.
ctx = db.context.from_xstar_run("xstar_runs/helike_type69/o7_ne1e8", ion="O VII")

# Summarizes same-run XSTAR triplet rows when xout_lines1.fits is available.
comparison = db.validate.compare_xstar_run(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
    wavelength=(21.4, 22.2),
)
```

`db.matrix.build_ion(...)` and `db.solve.ion(...)` are present as workflow wrappers around the current source-level solver:

```python
solution = db.solve.ion(
    "O VII",
    context=ctx,
    temperature=7.66552e4,
    electron_density=1.20466e8,
)

matrix_products = db.matrix.build_ion("O VII", context=ctx)
```

They do not yet add type-50 photoexcitation to the matrix; that remains a later opt-in physics mode after audit validation.

### 3.10 Public namespace modules

The following import locations are available for users who prefer module namespaces:

```python
from xstar_atomic import rates, solve, matrix, validate, runs

rate = rates.type50_bound_bound(
    ion="O VII",
    aij_s_inv=3.0e12,
    oscillator_strength=0.7,
    wavelength_A=21.602,
    vtherm_cm_s=1.0e7,
    bremsa_nb1=2.5e4,
    ptmp1=0.2,
    ptmp2=0.3,
    flinabs_ptmp1=0.8,
    cfrac=0.0,
)

triplet_comparison = validate.compare_xstar_run(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
    wavelength=(21.4, 22.2),
)
```

### 3.11 Run a source-code audit from Python

```python
from xstar_atomic.audit import type50_line_pumping

audit = type50_line_pumping(
    cases_csv="helike_local_state_validation_v03131/helike_local_state_cases.csv",
    solver_root=".",
    xstar_source_root="../xstar",
    out_dir="helike_type50_line_pumping_audit_v03131",
    print_summary=True,
)

print(audit.summary)
```

The corresponding command-line wrapper is `examples/55_audit_helike_type50_line_pumping.py`.

### 3.12 Export line-emissivity products

```python
from xstar_atomic.export import export_superwind_bundle, parse_band_specs

bands = parse_band_specs(["soft:0.5:2.0", "hard:2.0:10.0"])
bundle = export_superwind_bundle(
    "/path/to/atdb.fits",
    ions="O VIII,Ne IX",
    out_dir="atomic_export_example",
    temperatures=[1.0e6, 3.0e6, 1.0e7],
    wavelength=(1.0, 40.0),
    formats=["csv", "hdf5"],
    bands=bands,
)
```

This is the current public export workflow for downstream simulation or spectral-model post-processing.

### 3.13 What is not yet implemented as final physics

The API names reserve space for future source-aligned matrix/solver development.  The following are intentionally not final public physics modes yet:

```text
- type-50 photoexcitation injection into the population matrix
- full XSTAR radiation-field parity for bremsa(nb1) and exact nbinc binning
- migrated Python APIs for examples 53 and 54 resonance audits
- a stable production replacement for XSTAR thermal/radiative transfer
```

The policy is: audit-only first, opt-in solver treatment second, default behavior only after same-run XSTAR validation.

## 4. Atomic database access

### 4.1 Packed XSTAR database structure

The public XSTAR `atdb.fits` file contains packed arrays rather than one simple table:

```text
POINTERS
REALS
INTEGERS
CHARS
```

`xstar-atomic` rebuilds the hierarchy:

```text
element -> ion -> levels -> radiative/collisional/photoionization/recombination records
```

The low-level reader is `ATDB`; the higher-level convenience class is `XSTARAtomic`.

### 4.2 Public database functions

Common functions and methods include:

```python
xa.find_atdb_file(...)
xa.resolve_atdb_path(...)
xa.set_data_path(...)
xa.get_data_path()

XSTARAtomic(...).summary()
XSTARAtomic(...).levels("O VII")
XSTARAtomic(...).lines("O VII")
XSTARAtomic(...).photoionization("O VII")
XSTARAtomic(...).collisions("O VII")
XSTARAtomic(...).recombination("O VII")
XSTARAtomic(...).emissivity("O VII")
```

### 4.3 Current decoder status

| Component | XSTAR data type(s) | Current status |
|---|---:|---|
| Packed FITS reader / hierarchy | arrays | validated on released `atdb.fits` |
| Levels | 6 | implemented |
| Radiative lines | 50 | implemented; v0.3.128 adds audit-only source-code rate object for line pumping |
| Photoionization grids | 53 | implemented for ordinary OP-style grids |
| Collisions, tabulated upsilon | 56 | implemented |
| Collisions, Bautista hydrogenic/l-mixing branches | 63 | implemented for validated branches |
| Collisions, Burgess--Tully | 51, 98 | implemented for representative branches |
| Recombination totals | 1, 30, 38, 39 | implemented for total rates |
| Charge exchange | 2 | implemented when explicitly requested |
| Full local radiation-field parity | several | in development |
| Production replacement for XSTAR transfer/thermal balance | combined | not a package goal |

## 5. Local context objects

### 5.1 `LocalPlasmaState`

`LocalPlasmaState` stores local gas quantities:

```python
from xstar_atomic import LocalPlasmaState

state = LocalPlasmaState(
    temperature_K=1.0e6,
    electron_density_cm3=1.0e8,
    log_xi=3.0,
    ion_fraction=0.25,
)
```

A state can also be built from a row dictionary, including rows from local-state validation CSV files:

```python
state = LocalPlasmaState.from_mapping(row)
```

### 5.2 `RadiationField`

`RadiationField` stores an XSTAR-like local radiation field and energy grid:

```python
from xstar_atomic import RadiationField

rad = RadiationField.from_pairs([(0.5, 1.0e4), (1.0, 2.0e4)])
print(rad.value_at(0.9))
```

The current nearest-bin helper is only an audit convenience. Exact XSTAR `nbinc` parity is a future development target.

### 5.3 `EscapeContext`

`EscapeContext` stores the line escape and covering-factor terms used by source-aligned rate evaluators:

```python
from xstar_atomic import EscapeContext

escape = EscapeContext(cfrac=0.0, ptmp1=0.1, ptmp2=0.2, flinabs_ptmp1=0.7)
```

For type-50 line pumping, the upward photoexcitation branch is multiplied by `max(0, 1-cfrac)`.

## 6. Source-code-aligned rate evaluators

### 6.1 `RateEvaluation`

`RateEvaluation` is a structured result object. It records:

```text
process
data_type
status
value_s^-1
source_formula
record_id
ion
lower_level
upper_level
terms
warnings
metadata
```

This is intentionally more verbose than a simple scalar rate. It supports source-code-first audits and future matrix-term provenance.

### 6.2 Type-50 bound-bound radiative branch

XSTAR's type-50 branch forms two local quantities before a final branch swap:

```fortran
ans1 = aij * (ptmp1 + ptmp2)
sigma = 0.02655 * flin * elin * 1.d-8 / vtherm
ans2 = sigma * bremsa(nb1) * vtherm / 3.e10 * flinabs(ptmp1)
ans2 = ans2 * max(0., 1.d0-cfrac)
```

After the swap:

```text
ans1 -> lower-to-upper photoexcitation
ans2 -> upper-to-lower escaped decay
```

The v0.3.128 function is:

```python
from xstar_atomic import evaluate_type50_bound_bound

rate = evaluate_type50_bound_bound(...)
```

This function is audit-only and should be used to inspect the missing line-pumping term before any future solver-injection mode is enabled.

## 7. Matrix, solver, and emissivity workflows

The existing solver remains prototype/diagnostic. Current public methods include:

```python
db.emissivity(...)
db.type50_rate(...)
db.audit_type50_line_pumping(...)
```

Future stable APIs should separate:

```text
rate evaluator -> matrix term -> population solution -> emissivity/triplet result
```

Each matrix term should carry provenance: XSTAR data type, record id, source-code formula, local context terms, and treatment mode.

### 7.1 Solver step profiling

Use `examples/12_profile_solver_steps.py` to profile ATDB opening, index building, level/line/collision extraction, collision evaluation, matrix assembly, linear solving, and output writing:

```bash
PYTHONPATH=src python examples/12_profile_solver_steps.py \
  ../xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperature 1e6 --electron-density 1.0 \
  --linear-solver sparse \
  --index-cache \
  --index-cache-format npz \
  --out-dir solver_profile_npz_arrays_hit
```

### 7.2 Prototype O VII recombination/cascade workflow

Use `examples/13_o7_recombination_cascade_workflow.py` for the Stage-6 prototype source/cascade workflow. It evaluates total O VIII -> O VII recombination, redistributes source terms through an approximate radiative-branching cascade, feeds the source CSV into the sparse solver, and computes prototype `R=f/i` and `G=(f+i)/r` diagnostics:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_recomb_cascade_workflow \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

This remains a source-interface and sensitivity workflow, not a final level-resolved recombination/cascade model.

### 7.3 O VII density-grid source-fit diagnostic

Use `examples/21_o7_solver_source_fit_density_grid.py` to run the O VII density-grid source-fit diagnostic:

```bash
PYTHONPATH=src python examples/21_o7_solver_source_fit_density_grid.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_density_grid_source_fit \
  --print-summary
```

## 8. XSTAR-output readers and same-run validation

`xstar_atomic.xstar_outputs` reads selected XSTAR output FITS files, including local abundance/state tables and line lists. The local-state validation examples use these readers to select the same local temperature, electron density, and same-run triplet targets before comparing solver output.

Typical workflow:

```bash
PYTHONPATH=src python examples/51_run_helike_local_state_validation.py \
  --xstar-runs-root xstar_runs \
  --target-root xstar_atomic_v0.3.111_results \
  --atdb ../xstar/data/atdb.fits \
  --selection-mode max \
  --target-electron-density 1e8 \
  --nearest-density \
  --out-dir helike_local_state_validation_v03130_ne1e8_allions \
  --print-summary
```

## 9. Audit workflows

### 9.1 Type-50 line-pumping audit

In v0.3.128 the previous example-55 logic is available as a Python API:

```python
from xstar_atomic.audit import type50_line_pumping

audit = type50_line_pumping(
    "helike_local_state_validation_v03130_ne1e8_allions/helike_local_state_cases.csv",
    solver_root=".",
    xstar_source_root="../xstar",
    out_dir="helike_type50_line_pumping_audit_v03130",
    print_summary=True,
)
```

The CLI wrapper remains:

```bash
PYTHONPATH=src python examples/55_audit_helike_type50_line_pumping.py \
  --cases-csv helike_local_state_validation_v03130_ne1e8_allions/helike_local_state_cases.csv \
  --solver-root . \
  --xstar-source-root ../xstar \
  --out-dir helike_type50_line_pumping_audit_v03130 \
  --print-summary
```

The audit writes:

```text
helike_type50_line_pumping_audit.csv
helike_type50_line_pumping_audit.md
helike_type50_line_pumping_audit.json
```

### 9.2 Audit policy

Development policy:

```text
1. No empirical triplet scale factors as final physics.
2. New physics starts as audit-only.
3. Solver-changing modes must be opt-in until validated.
4. Every solver-changing rate must have source-code and record provenance.
5. Radiation-dependent rates must expose the radiation context.
6. Escape-dependent rates must expose cfrac, tau/ptmp, and escape treatment.
7. Same-run XSTAR outputs are preferred over generic target CSVs.
```

## 10. Examples and source-module migration

The package contains many examples because the XSTAR-alignment work is still exploratory. As workflows stabilize, reusable logic should move into `src/xstar_atomic/`, leaving examples as short wrappers.

High-priority migrations:

| Example(s) | Candidate source module/API |
|---|---|
| `51_run_helike_local_state_validation.py` | `xstar_atomic.runs.select_local_states(...)` |
| `52_summarize_helike_local_state_comparison.py` | `xstar_atomic.validate.summarize_local_state_comparison(...)` |
| `53_audit_helike_resonance_deficit.py` | `xstar_atomic.audit.resonance_deficit(...)` |
| `54_audit_helike_resonance_population_flux.py` | `xstar_atomic.audit.resonance_population_flux(...)` |
| `55_audit_helike_type50_line_pumping.py` | `xstar_atomic.audit.type50_line_pumping(...)` |
| `43_compare_xstar_detail_populations.py` | `xstar_atomic.validate.compare_detail_populations(...)` |
| `42_xstar_like_element_solver_demo.py` | `xstar_atomic.solve.element(...)` and CLI wrapper |
| `47_prepare_mg_ca_xstar_triplet_targets.py` | `xstar_atomic.xout.convert_triplet_targets(...)` |

See `examples/README.md` for grouped example usage and `docs/example_to_source_api_map.md` for a broader migration plan.

## 11. Validation and tests

Recommended local checks:

```bash
PYTHONPATH=src python -m compileall -q src examples tests
PYTHONPATH=src pytest -q tests/test_api_infrastructure_v03128.py
PYTHONPATH=src pytest -q \
  tests/test_type50_line_escape.py \
  tests/test_helike_triplet_balance_diagnostics.py \
  tests/test_xstar_detail_population_compare_example.py \
  tests/test_package_metadata.py \
  tests/test_cli_smoke.py
```

Some tests are skipped unless `XSTAR_ATDB_FITS` or `XSTAR_ATDB` points to a local `atdb.fits`.

## 12. Roadmap

Near-term:

```text
v0.3.128: API infrastructure and audit-only type-50 evaluator.
v0.3.129: examples README, expanded API cookbook, and LaTeX table of contents/documentation polish.
v0.3.130: examples README command-completeness update with one bash block for every example script.
v0.3.131: workflow-first public API, expert namespaces, and context-based helper functions.
v0.3.132: documentation consistency across Markdown, LaTeX, and Sphinx for the public API.
v0.3.133: add function-by-function API examples to Markdown/LaTeX/Sphinx docs and fix the LaTeX migration table layout.
v0.3.134: exact same-run XSTAR local-output reproduction targets.
v0.3.135: one-command standard C V / O VII / Mg XI / Ca XIX benchmark suite.
v0.3.136: stricter solver-triplet extraction and benchmark status reporting.
v0.3.139: strengthened C/O/Mg/Ca benchmark comparison by adding XSTAR/solver R, G, L2 residuals, recording the solver triplet source, and adding `--solver-preset xstar-local-state`.

v0.3.138: strengthened ATDB datapath fallback. If `XSTAR_ATDB`/`XSTAR_ATDB_FITS` are unset, the resolver uses configured `datapath` files, skips stale candidates, and then checks package data.
Future: XSTAR radiation-field reader and exact line-energy bin mapping.
Future: type-50 matrix-injection preview, still audit-only.
Future: optional solver mode for xstar-line-escape-and-pumping.
```

Longer-term:

```text
- stable context/rate/matrix/solve/emissivity APIs
- broader data-type evaluator parity
- stronger same-run XSTAR validation suite
- source-code provenance for every matrix term
- documentation organized by workflow rather than version history
```

## Python XSTAR-output recreation planning

`xstar-atomic` is not yet a full replacement for the XSTAR thermal/ionization/radiative-transfer driver.  However, the package now includes a planning API for building that replacement in a source-code-parity way.  The first step is to parse the exact XSTAR command and identify which live arrays are needed to recreate each standard FITS product.

```python
import xstar_atomic as xa

params = xa.parse_xstar_command(
    "xstar spectrum='pow' nsteps=10 density=1 rlogxi=1.5 cfrac=1.0 vturbi=100"
)
plan = xa.xstar_recreation_plan(params)
paths = xa.write_xstar_recreation_plan(params, "xstar_python_recreation_plan")
```

The same workflow can parse a run script:

```bash
PYTHONPATH=src python examples/58_plan_xstar_output_recreation.py \
  --command-file xstar_runs/helike_type69/o7_ne1e8/run_xstar.sh \
  --out-dir xstar_python_recreation_plan_o7 \
  --print-summary
```

The plan explicitly covers the standard products:

- `xo01_detail.fits`
- `xo01_detal2.fits`
- `xo01_detal3.fits`
- `xo01_detal4.fits`
- `xout_abund1.fits`
- `xout_lines1.fits`
- `xout_rrc1.fits`
- `xout_cont1.fits`
- `xout_spect1.fits`

Exact recreation from input parameters alone requires the same live internal state used by XSTAR, including `epi(:)`, `bremsa(:)`, `bremsint(:)`, `tau0(1:2,line)`, `tauc/dpthc(1:2,continuum)`, `cfrac`, `vturbi`, ion fractions, and level populations.  The current implementation writes a recreation plan and source-code-parity checklist; the full solver/transfer loop and FITS writers are future work.

## Python XSTAR live-state skeleton

The recreation plan identifies the products and phases.  The live-state skeleton creates the Python containers that later source-code-parity loops must populate.  These objects are the future single source of truth for writing `xo01_detail.fits`, `xo01_detal2.fits`, `xo01_detal3.fits`, `xo01_detal4.fits`, `xout_abund1.fits`, `xout_lines1.fits`, `xout_rrc1.fits`, `xout_cont1.fits`, and `xout_spect1.fits`.

```python
import xstar_atomic as xa

params = xa.parse_xstar_command(
    "xstar spectrum='pow' nsteps=10 density=1 rlogxi=1.5 cfrac=1.0 vturbi=100"
)
state = xa.create_initial_xstar_run_state_from_input(params)

zone = state.zones[0]
print(zone.cfrac, zone.vturbi, zone.temperature, zone.electron_density)
print(zone.missing_core_fields())
```

The required live fields are available programmatically:

```python
for field in xa.required_live_state_fields():
    print(field["name"], "->", field["python_field"])
```

Command-line skeleton writer:

```bash
PYTHONPATH=src python examples/59_create_xstar_live_state_skeleton.py \
  --command-file xstar_runs/helike_type69/o7_ne1e8/run_xstar.sh \
  --out-dir xstar_live_state_skeleton_o7 \
  --print-summary
```

The current skeleton is input-seeded, not a full XSTAR calculation.  It explicitly carries `epi(:)`, `bremsa(:)`, `bremsint(:)`, `tau0(1:2,line)`, `tauc/dpthc(1:2,continuum)`, `cfrac`, `vturbi`, local `T/ne`, ion fractions, and level populations so that future Python and C++ backends can populate the same arrays used by the XSTAR Fortran path.
