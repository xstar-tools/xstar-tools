# xstar_tools 0.6.48.9.4 — accepted-boundary reuse and rate hot-path preparation

## Purpose

0.6.48.9.4 follows the accepted 0.6.48.9.3 Type50 optimization.  The 9.3 three-run host median is 32.724905 s total.  The four accepted product-boundary recomputations cost 4.209864 s total, while fixed traversal costs 10.628351 s and nested rate evaluation costs 9.553384 s.

## Accepted-boundary reuse

The controller's last accepted DSEC evaluation already computes the local fixed-state source workspaces needed by the product boundary.  Earlier releases immediately reran `xstar_fixed_state_run_with_source_workspaces_v1()` after every controller call to rebuild those local workspaces.

9.4 retains the exact source workspaces produced by the most recent fixed-state evaluation in the persistent fixed-state context.  Once a DSEC state is accepted, the standalone controller copies those retained workspaces without a physics reevaluation, reconstructs the deferred public spectral projection in the same source order, and then overlays the caller-owned cumulative radial state exactly where the historical boundary finalizer did.

The four accepted boundaries therefore remain four retained controller events, but no longer require four redundant fixed-state physics passes.  The terminal zero-thickness final evaluation remains a real fixed-state evaluation.

## Fail-closed A/B gate

`XSTAR_V064894_FORCE_LEGACY_BOUNDARY_RECOMPUTE=1` preserves the historical full-recompute path for qualification only.  The qualification runner produces both normal-reuse and forced-legacy products from the same executable and requires:

- all nine FITS HDU data payloads bit-identical;
- `xout_step.log` identical after removing timing-only lines;
- normal run boundary counters `reuse=4, legacy=0, fallback=0`;
- forced-legacy counters `reuse=0, legacy=4, fallback=0`;
- unchanged 54 DSEC + 4 final = 58 retained controller events.

Fallback from reuse is permitted only during non-mutating preparation.  Once controller bookkeeping starts committing a prepared boundary, failures propagate instead of retrying and risking double accounting.

## Traversal/rate hot-path preparation

9.4 also performs two low-risk structural hoists:

1. The immutable linked record order is validated and materialized once when the fixed-state context is created.  Each evaluation traverses that prepared order rather than allocating a whole-program visited bitmap and revalidating links.
2. Temperature/electron-density rate scalars and the reduced `epim/bremsam` caller input are built once per fixed-state evaluation and passed by const reference to every record.  The complete input ABI structure is no longer copied for every atomic record.

No record formulas, rate kernels, matrix equations, source constants, Type50 arithmetic, FITS writers, or controller convergence rules are changed.

## Host qualification

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.9.4)
DATA=/media/linux/mhd/xstar/xstar/data
CACHE=v82_patch520154_all61_solve_stage_cache.tar.gz
FORTRAN=mg11_ne1e8.tar.gz
PYACCEL=v064882_full_test.python_accel_reference.tar.gz

"$PACKAGE/run_v064894_cpp_against_reference.sh" \
  "$PACKAGE" "$DATA" "$CACHE" "$FORTRAN" "$PYACCEL" \
  v064894_cpp_test \
  2>&1 | tee v064894_cpp_test.host.log
```

Expected final markers:

```text
V064894_BOUNDARY_REUSE_EQUIVALENCE=ACCEPT
V064894_SPECTRUM_CLOSURE=ACCEPT
V064894_DETAL4_CLOSURE=ACCEPT
V064894_TYPE99_RCCEMIS_CLOSURE=ACCEPT
V064894_HMCTOT_CLOSURE=ACCEPT
V064894_RESULT=ACCEPT_BOUNDARY_REUSE_AND_RATE_HOTPATH_PREP
V064894_FINAL_RETURN_CODE=0
```

## Host performance series

```bash
"$PACKAGE/run_v064894_performance_benchmark.sh" \
  "$PACKAGE" "$DATA" "$CACHE" v064894_performance 3 \
  2>&1 | tee v064894_performance.host.log
```

The performance analyzer requires the same Type50 workload and controller trajectory, four reused boundaries with no fallback, and improvement over the accepted 9.3 median total and accepted-boundary time.
