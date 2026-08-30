# 0.6.84 — complete serial native XSTAR2XSPEC

## Scope

`0.6.84` composes the already-qualified native components into one serial XSTAR2XSPEC workflow:

```text
xstinitable.par / key=value input
        |
        v
xstar-xspec-initable
        |
        +-- xstinitable.lis
        +-- xstinitable.fits
        |
        v
serial xstar-cpp jobs (loopcontrol 1..N)
        |
        +-- isolated per-job xout_spect1.fits
        +-- isolated per-job xout_step.log
        |
        v
xstar-xspec-table --initable xstinitable.fits
        |
        +-- xout_ain.fits
        +-- xout_aout.fits
        +-- xout_mtable.fits
        +-- xout_etable.fits
        +-- concatenated xout_step.log
        +-- xstar2xspec.log
```

This is an orchestration/table-metadata release. XSTAR physics, controller decisions, accumulation order, publication science, and the accepted native xstinitable grid semantics are unchanged.

## Native command

```bash
xstar-xspec \
  --input xstinitable.par \
  --output-dir run_xstar2xspec
```

`--data-dir` is optional. If omitted, every child `xstar-cpp` performs its established data discovery (`XSTAR_DATA`, then `$HEADAS/refdata`, then legacy fallbacks).

Trailing `key=value` values override the `.par` file just as they do for `xstar-xspec-initable`.

## Work isolation

Each serial job writes into:

```text
<output>/.xstar2xspec-work/jobs/000001
<output>/.xstar2xspec-work/jobs/000002
...
```

The final tables are not assembled until all jobs have returned success and each job has both `xout_spect1.fits` and `xout_step.log`.

By default the work tree is removed after successful table assembly. `--save` retains it. On a failed run the work tree remains available for diagnosis/restart.

## Restart

`--restart` reuses a job only if both its `xout_spect1.fits` and `xout_step.log` already exist. Jobs are still consumed in deterministic `loopcontrol` order. The root `xout_step.log` is reconstructed from the job logs, so restart cannot duplicate STEP content.

## Direct native table metadata

`xstar-xspec-table` now accepts:

```bash
xstar-xspec-table --initable xstinitable.fits --output-dir OUT spectrum1.fits ...
```

The historical `--metadata metadata.txt` interface remains available for 0.6.81 regression replay, but it is no longer used by the production XSTAR2XSPEC path.

The direct `xstinitable.fits` path was tested against the frozen canonical MPI_XSTAR 2x3 fixture and preserves:

- 3414 table energy bins;
- bit-exact `PARAMVAL`;
- bit-exact `INTPSPEC` payloads for AIN, AOUT, MTABLE, and ETABLE.

## Deferred scope

`0.6.84` is intentionally serial. Parallel/MPI-style dispatch and deterministic out-of-order completion handling remain the `0.6.85` milestone.
