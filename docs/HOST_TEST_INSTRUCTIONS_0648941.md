# Host qualification for xstar_tools 0.6.48.9.4.1

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.9.4.1)
DATA=/media/linux/mhd/xstar/xstar/data
CACHE=v82_patch520154_all61_solve_stage_cache.tar.gz
FORTRAN=mg11_ne1e8.tar.gz
PYACCEL=v064882_full_test.python_accel_reference.tar.gz

"$PACKAGE/run_v0648941_cpp_against_reference.sh" \
  "$PACKAGE" "$DATA" "$CACHE" "$FORTRAN" "$PYACCEL" \
  v0648941_cpp_test 2>&1 | tee v0648941_cpp_test.host.log

"$PACKAGE/run_v0648941_performance_benchmark.sh" \
  "$PACKAGE" "$DATA" "$CACHE" v0648941_performance 3 \
  2>&1 | tee v0648941_performance.host.log
```

Do not enable `XSTAR_ENABLE_RCCEMIS_ATTRIBUTION` for routine qualification.

Blocking correction gate:

```text
V0648941_BOUNDARY_FITS_DATA_BIT_EXACT=ACCEPT
V0648941_BOUNDARY_STEP_SCIENCE_LOG_IDENTICAL=ACCEPT
V0648941_BOUNDARY_REUSE_EQUIVALENCE=ACCEPT
V0648941_RESULT=ACCEPT_TERMINAL_DSEC_BOUNDARY_REUSE_FIX
V0648941_FINAL_RETURN_CODE=0
```
