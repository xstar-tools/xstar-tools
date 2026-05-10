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
3. [Public API cookbook](#3-public-api-cookbook)
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

In v0.3.128 this evaluator is **audit-only**. It records the XSTAR `ucalc.f90` type-50 branch and returns a `RateEvaluation` object; it does not inject photoexcitation into the population solver.

## 3. Public API cookbook

This section summarizes the most useful public API calls. The goal is to make common workflows discoverable without reading the internal example scripts.

### 3.1 Open and summarize an XSTAR database

```python
import xstar_atomic as xa
from xstar_atomic import XSTARAtomic

xa.set_data_path("/path/to/xstar/data/atdb.fits")
db = XSTARAtomic()             # uses the configured datapath
summary = db.summary()
print(summary["n_records"] if "n_records" in summary else summary)
```

### 3.2 Query lines, levels, and wavelength windows

```python
levels = db.levels("O VII")
triplet_lines = db.lines("O VII", wavelength=(21.4, 22.2), slim=True)
lya = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)

for line in triplet_lines:
    print(line.get("wavelength_A"), line.get("lower_level"), line.get("upper_level"))
```

Use this layer for quick inspection and for building small validation tables. Use the lower-level record objects only when you need raw ATDB indices.

### 3.3 Evaluate collisional and recombination products

```python
coll = db.collisions(
    "O VIII",
    temperatures=[1.0e6, 3.0e6, 1.0e7],
    wavelength=(18.8, 19.1),
)

rr = db.recombination(
    "O VII",
    temperatures=[1.0e6],
    electron_densities=[1.0e8],
    source_mode="none",
)

print(len(coll["summary"]), len(coll["evaluated"]))
print(rr["summary"])
```

### 3.4 Build a local XSTAR-style context

```python
from xstar_atomic import LocalPlasmaState, RadiationField, EscapeContext

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
```

These objects are intentionally explicit. XSTAR rate terms can depend on local temperature, electron density, radiation-field binning, covering factor, and escape probabilities, so those values should not be hidden inside scalar helper functions.

### 3.5 Evaluate the audit-only type-50 bound-bound branch

```python
from xstar_atomic import evaluate_type50_bound_bound

rate = evaluate_type50_bound_bound(
    aij_s_inv=3.0e12,
    oscillator_strength=0.7,
    wavelength_A=21.602,
    vtherm_cm_s=1.0e7,
    bremsa_nb1=2.5e4,
    plasma_state=state,
    radiation_field=rad,
    escape_context=escape,
    ion="O VII",
    lower_level=1,
    upper_level=7,
)

print(rate.lower_to_upper_photoexcitation_s_inv)
print(rate.upper_to_lower_escaped_decay_s_inv)
print(rate.terms)
```

In v0.3.128 and v0.3.129 this evaluator remains audit-only. It records the XSTAR `ucalc.f90` type-50 branch and branch swap but does not modify the level-population solver.

### 3.6 Use the high-level `XSTARAtomic` convenience methods

```python
rate = db.type50_rate(
    aij_s_inv=3.0e12,
    oscillator_strength=0.7,
    wavelength_A=21.602,
    vtherm_cm_s=1.0e7,
    bremsa_nb1=2.5e4,
    plasma_state=state,
    escape_context=escape,
    ion="O VII",
)
```

The method delegates to the same source-code-aligned evaluator, so it is convenient for notebooks while preserving provenance.

### 3.7 Run a source-code audit from Python

```python
from xstar_atomic.audit import type50_line_pumping

audit = type50_line_pumping(
    cases_csv="helike_local_state_validation_v03129/helike_local_state_cases.csv",
    solver_root=".",
    xstar_source_root="../xstar",
    out_dir="helike_type50_line_pumping_audit_v03129",
    print_summary=True,
)

print(audit.summary)
```

The corresponding command-line wrapper is `examples/55_audit_helike_type50_line_pumping.py`.

### 3.8 Export line-emissivity products

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

## 4. Atomic database access

### 3.1 Packed XSTAR database structure

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

### 3.2 Public database functions

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

### 3.3 Current decoder status

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

### 4.1 `LocalPlasmaState`

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

### 4.2 `RadiationField`

`RadiationField` stores an XSTAR-like local radiation field and energy grid:

```python
from xstar_atomic import RadiationField

rad = RadiationField.from_pairs([(0.5, 1.0e4), (1.0, 2.0e4)])
print(rad.value_at(0.9))
```

The current nearest-bin helper is only an audit convenience. Exact XSTAR `nbinc` parity is a future development target.

### 4.3 `EscapeContext`

`EscapeContext` stores the line escape and covering-factor terms used by source-aligned rate evaluators:

```python
from xstar_atomic import EscapeContext

escape = EscapeContext(cfrac=0.0, ptmp1=0.1, ptmp2=0.2, flinabs_ptmp1=0.7)
```

For type-50 line pumping, the upward photoexcitation branch is multiplied by `max(0, 1-cfrac)`.

## 6. Source-code-aligned rate evaluators

### 5.1 `RateEvaluation`

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

### 5.2 Type-50 bound-bound radiative branch

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
  --out-dir helike_local_state_validation_v03129_ne1e8_allions \
  --print-summary
```

## 9. Audit workflows

### 9.1 Type-50 line-pumping audit

In v0.3.128 the previous example-55 logic is available as a Python API:

```python
from xstar_atomic.audit import type50_line_pumping

audit = type50_line_pumping(
    "helike_local_state_validation_v03129_ne1e8_allions/helike_local_state_cases.csv",
    solver_root=".",
    xstar_source_root="../xstar",
    out_dir="helike_type50_line_pumping_audit_v03129",
    print_summary=True,
)
```

The CLI wrapper remains:

```bash
PYTHONPATH=src python examples/55_audit_helike_type50_line_pumping.py \
  --cases-csv helike_local_state_validation_v03129_ne1e8_allions/helike_local_state_cases.csv \
  --solver-root . \
  --xstar-source-root ../xstar \
  --out-dir helike_type50_line_pumping_audit_v03129 \
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

Some tests are skipped unless `XSTAR_ATDB_FITS` points to a local `atdb.fits`.

## 12. Roadmap

Near-term:

```text
v0.3.128: API infrastructure and audit-only type-50 evaluator.
v0.3.129: examples README, expanded API cookbook, and LaTeX table of contents/documentation polish.
v0.3.130: XSTAR radiation-field reader and exact line-energy bin mapping.
v0.3.131: type-50 matrix-injection preview, still audit-only.
v0.3.132: optional solver mode for xstar-line-escape-and-pumping.
```

Longer-term:

```text
- stable context/rate/matrix/solve/emissivity APIs
- broader data-type evaluator parity
- stronger same-run XSTAR validation suite
- source-code provenance for every matrix term
- documentation organized by workflow rather than version history
```
