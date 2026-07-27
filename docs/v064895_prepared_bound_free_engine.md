# 0.6.48.9.5 prepared Type49/53 bound-free engine

## Scope

This release is a C++ performance candidate based on the accepted 0.6.48.9.4.2 correctness baseline. Boundary ownership, Type50 arithmetic, thermal state, matrix physics, and public writers are frozen.

## Optimization

For Type49 and Type53 records, immutable `phint53` geometry is prepared once per record and radiation-energy grid: source cross-section interpolation, `sgbar`, threshold-bin addressing, exact threshold-publication geometry, and Type49 phextrap metadata. Dynamic temperature, density, radiation amplitude, populations, and escape terms are still evaluated on every call.

The reduced-grid matrix/source call and `calc_emisab` call use the same 999-bin `epim`/`bremsam` workspace, so the second dynamic integral reuses the first result. The 9999-bin `calc_emis` revisit is evaluated only after the existing source `rlbin`/`ncbin` selection chooses a Type49/53 record for publication.

## A/B switch

`XSTAR_V064895_FORCE_LEGACY_BOUND_FREE=1` restores the pre-9.5 eager behavior in the same executable. `run_v064895_cpp_against_reference.sh` requires all nine FITS data payloads and scientific `xout_step.log` content to be identical between prepared and forced-legacy modes.

## Production invariants

- DSEC: 20 / 1 / 17 / 16 = 54.
- Retained controller evaluations: 58.
- Accepted boundaries: four exact legacy recomputations; boundary reuse remains disabled.
- Final zero-thickness evaluation remains a genuine full evaluation.
- Type50 0.6.48.9.3 strict-FP fast path is unchanged.

## Host commands

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.9.5)
DATA=/media/linux/mhd/xstar/xstar/data
CACHE=v82_patch520154_all61_solve_stage_cache.tar.gz
FORTRAN=mg11_ne1e8.tar.gz
PYACCEL=v064882_full_test.python_accel_reference.tar.gz

"$PACKAGE/run_v064895_cpp_against_reference.sh" \
  "$PACKAGE" "$DATA" "$CACHE" "$FORTRAN" "$PYACCEL" v064895_cpp_test

"$PACKAGE/run_v064895_performance_benchmark.sh" \
  "$PACKAGE" "$DATA" "$CACHE" v064895_performance 3
```

The release must not be promoted until the host A/B and frozen FORTRAN/Python science gates pass.
