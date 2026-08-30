# 0.6.85 — Parallel/MPI-style native XSTAR2XSPEC

> **Historical note:** this page describes `0.6.85`. `0.6.85.1` is the formally accepted corrective successor: work products are preserved by default, failure is non-destructive, and restart additionally requires `xstar-cpp.success`. `0.6.86` adds a separate true-MPI candidate; local `xstar-xspec --workers N` remains process-based and non-MPI.

## Scope

`0.6.85` extends the formally accepted `0.6.84` native XSTAR2XSPEC pipeline with bounded process parallelism. It does **not** modify XSTAR scientific arithmetic, the native xstinitable grid semantics, or the native xstar2table spectral transform.

The production path is:

```text
xstar-xspec-initable
        |
        v
canonical xstinitable.lis + xstinitable.fits
        |
        v
bounded xstar-cpp worker pool
        |
        +-- xstar2xspec-work/jobs/000001/
        +-- xstar2xspec-work/jobs/000002/
        +-- ...
        |
        v
canonical loopcontrol-ordered gather
        |
        +-- concatenate xout_step.log by loopcontrol
        +-- pass xout_spect1.fits by loopcontrol
        v
xstar-xspec-table
        |
        +-- xout_ain.fits
        +-- xout_aout.fits
        +-- xout_mtable.fits
        +-- xout_etable.fits
```

## Worker contract

Parallel execution is explicit:

```bash
xstar-xspec --input xstinitable.par --output-dir run --workers 4 --save
```

`--workers 1` remains the default and is the serial reference mode. This is deliberate because an XSTAR worker can consume substantial memory; the program does not guess a safe concurrency level.

The Python wrapper exposes the same option:

```bash
xstar-tools-xstar2xspec --input xstinitable.par --output-dir run --workers 4
```

The historical MPI_XSTAR-facing command is now implemented as a compatibility-style wrapper over the same native engine:

```bash
xstar-tools-mpixstar --input xstinitable.par --output-dir run --np 4
```

`0.6.85` has no MPI library/runtime dependency. The phrase “MPI-style” refers to master/worker grid semantics: independent jobs can finish in arbitrary order, but scientific placement is controlled by deterministic job identity.

## Deterministic placement invariant

Before any job is launched, the orchestrator verifies that generated plan row `i` contains:

```text
loopcontrol=i
```

Each job is assigned to:

```text
xstar2xspec-work/jobs/NNNNNN/
```

where `NNNNNN` is the zero-padded `loopcontrol` value.

Completion order is recorded only as scheduler telemetry. It never controls:

- STEP concatenation order;
- spectrum order passed to `xstar-xspec-table`;
- `PARAMVAL` placement;
- final `INTPSPEC` row placement.

This is the central correctness difference from completion-order-sensitive implementations.

## Visible work directory

Starting with `0.6.85`, the work directory is intentionally no longer hidden:

```text
0.6.84: .xstar2xspec-work/
0.6.85:  xstar2xspec-work/
```

With `--save`, all per-job XSTAR products remain available, including:

```text
xout_abund1.fits
xout_cont1.fits
xout_lines1.fits
xout_rrc1.fits
xout_spect1.fits
xout_step.log
xstar_execution_provenance.json
xstar-cpp.stdout.log
```

Without `--save`, `xstar2xspec-work/` is removed only after successful final-table assembly.

## Logging

Two root logs are written:

- `xstar2xspec.log`: deterministic canonical-order content suitable for reproducible inspection;
- `xstar2xspec_scheduler.log`: launch/completion telemetry, which may reflect out-of-order completion.

Per-job stdout/stderr is captured in `xstar-cpp.stdout.log`. In `--verbose` mode it is replayed in canonical job order when the root log is assembled, preventing parallel output interleaving from changing the deterministic root log.

## Restart

`--restart` reuses a job only when both of these exist:

```text
xstar2xspec-work/jobs/NNNNNN/xout_spect1.fits
xstar2xspec-work/jobs/NNNNNN/xout_step.log
```

Reused and newly executed jobs are gathered identically by `loopcontrol`. A fully completed restart executes zero solver jobs and rebuilds the root STEP log and final tables from the retained products.

## Failure behavior

If any worker exits nonzero:

1. the master stops launching new jobs;
2. active sibling workers are terminated;
3. final XSPEC tables are not newly published;
4. retained work products remain available when `--save` was requested.

## Local qualification

The frozen six-spectrum MPI_XSTAR fixture is used without rerunning physics. The qualification deliberately assigns unequal mock worker delays so completion is out of order. Required closure includes:

- bounded worker count;
- observed non-canonical completion order;
- canonical STEP concatenation;
- canonical root-log ordering;
- visible work directory;
- parallel four-table payloads bit-exact to the accepted fixture;
- `--workers 1` reference equivalence;
- restart reuse;
- fail-fast no-table publication;
- unchanged `.84` XSTAR science/planner/table sources.

## Host qualification

Build:

```bash
make -C src/xstar_tools/xstar/cpp -j2 \
  xstar-cpp xstar-xspec-initable xstar-xspec-table xstar-xspec
```

Then run:

```bash
python3 tools/qualification/check_parallel_native_xstar2xspec_0_6_85.py \
  --package "$PWD" \
  --baseline-package ../xstar_tools-0.6.84.tar.gz

python3 tools/qualification/run_parallel_native_xstar2xspec_host_0_6_85.py \
  --package "$PWD" \
  --output-root "$PWD/run_parallel_native_xstar2xspec_0685_host" \
  --workers 2 \
  --replace
```

Formal promotion requires:

```text
PARALLEL_NATIVE_XSTAR2XSPEC_0685_RESULT=ACCEPT
PARALLEL_NATIVE_XSTAR2XSPEC_0685_HOST_RESULT=ACCEPT
```
