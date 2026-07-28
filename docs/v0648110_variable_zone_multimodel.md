# 0.6.48.11.0 variable-zone multi-model qualification

## Purpose

0.6.48.11.0 moves qualification beyond the fully closed `mg11_ne1e8` fixture.  The
new authority set is the 62-run benchmark collection in
`original_xstar_benchmark_run.tar.gz`, with the corresponding FORTRAN XSTAR
products in `original_xstar.tar.gz`.

The release keeps the three production modes:

- `--zone-backend python`
- `--zone-backend cpp-all`
- `--zone-backend cpp-zone`

`cpp-all` remains the one-shot shared standalone-production controller.  `cpp-zone`
uses the same controller in one persistent native context but exposes one accepted
radial shell at a time through `run_next_zone()` and a `done()` query.  Python does
not reconstruct or feed back native controller state between calls.

## Variable radial topology

The previous Mg XI qualification had four physical radial shells with DSEC counts
`20,1,17,16`.  That topology is benchmark-specific.  The 62-model FORTRAN suite
contains 2, 3, 4, 5, 6, and 9-shell first-pass trajectories.

0.6.48.11.0 therefore removes the fixed four-call production loop.  For ordinary
models the native controller continues according to the literal first-pass source
predicate:

```text
xcol < xpxcol
and xee > xeemin
and t > tinf*0.99
and numrec > 0
and ierr == 0
```

The benchmark suite uses positive `nsteps`/`numrec`, analytic radial density, and
`npass=1`; controller errors are already fail-closed.  The accepted Mg XI reference
case retains its exact historical `20,1,17,16` prefix under the existing explicit
reference-trajectory mode so 10.2 closure remains a regression gate.

The persistent ABI is 6048110.  Its native context API is:

```text
create()
while not done():
    run_next_zone()
finalize()
destroy()
```

Each returned zone summary is read-only and reports zone index, DSEC count, source
sequence, wall time, temperature, electron fraction, `hmctot`, and whether the
radial loop is complete.

## Benchmark authority inventory

`tools/qualification/v0648110/benchmark_manifest.json` records all 62 named runs,
their FORTRAN radial zone count and DSEC vector, species, density, ionization
parameter, run-script path, reference-product path, and line-window metadata.

The suite consists of:

- 50 `helike_type69` runs
- 12 `mg_ca_triplet_targets` runs
- C V, O VII, Mg XI, and Ca XIX targets
- observed physical-zone counts 2, 3, 4, 5, 6, and 9

The FORTRAN archive is the scientific authority.  Candidate products are required
to retain identity/order semantics and have no aligned physical numeric cells more
than 1% from the reference.  The radial table must reproduce the reference zone
count, DSEC vector, and printed physical trajectory.  Target line inventories in
the C V, O VII, Mg XI, and Ca XIX triplet windows are also compared.

## Qualification order

The stages deliberately make the slowest paths last.

### 1. `standalone-smoke`

Run standalone C++ only on an 11-model matrix covering all four species and every
observed zone-count regime.  Python is used only to translate `run_xstar.sh` into
native parameter JSON and to compare products after the executable exits; Python
does not execute XSTAR science.

Smoke models include the 2-zone and 9-zone extremes plus representative 3/4/5/6
zone cases.

### 2. `standalone-all`

Blocked unless stage 1 is ACCEPT.  Run standalone C++ against all 62 FORTRAN
references.  All 62 must pass before any Python-hosted backend stage is enabled.

### 3. `python-cpp-modes`

Blocked unless all 62 standalone models are ACCEPT.  Run all 62 twice through the
Python CLI:

- accelerated Python host + `--zone-backend cpp-all`
- accelerated Python host + `--zone-backend cpp-zone`

Both outputs are compared with FORTRAN, and `cpp-zone` must be FITS-data-bit-exact
and normalized-step-log-identical to `cpp-all` for each model.

### 4. `python-selective`

Blocked unless stage 3 is ACCEPT.  Only five representative models are run through
the expensive science paths:

- pure Python
- accelerated Python modular C++ kernels with `--zone-backend python`

The default selective set spans C V, O VII, Mg XI, Ca XIX and 2/3/4/5/9-zone
reference trajectories.  It can be expanded in a later release if failures reveal
a missing regime; it is intentionally not an all-62 Python qualification.

## Host runner

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.11.0)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=$(realpath original_xstar_benchmark_run.tar.gz)
FORTRAN=$(realpath original_xstar.tar.gz)
OUT=$(pwd)/v0648110_multimodel

rm -rf "$OUT"

"$PACKAGE/run_v0648110_multimodel.sh" \
  "$PACKAGE" "$DATA" "$RUNS" "$FORTRAN" "$OUT" standalone-smoke
```

Run subsequent stages only when the preceding `summary.json` is ACCEPT:

```bash
"$PACKAGE/run_v0648110_multimodel.sh" "$PACKAGE" "$DATA" "$RUNS" "$FORTRAN" "$OUT" standalone-all
"$PACKAGE/run_v0648110_multimodel.sh" "$PACKAGE" "$DATA" "$RUNS" "$FORTRAN" "$OUT" python-cpp-modes
"$PACKAGE/run_v0648110_multimodel.sh" "$PACKAGE" "$DATA" "$RUNS" "$FORTRAN" "$OUT" python-selective
```

## Development policy

The first host run should be `standalone-smoke` only.  A rejection there is useful
new cross-element evidence and should be fixed before spending time on the other
51 native models or any Python path.  Passing the smoke stage is not permission to
skip `standalone-all`; all 62 standalone C++ models are the next blocking gate.
