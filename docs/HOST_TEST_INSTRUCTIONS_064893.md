# Host test instructions — 0.6.48.9.3

Qualification:

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.9.3)
DATA=/media/linux/mhd/xstar/xstar/data
CACHE=v82_patch520154_all61_solve_stage_cache.tar.gz
FORTRAN=mg11_ne1e8.tar.gz
PYACCEL=v064882_full_test.python_accel_reference.tar.gz

"$PACKAGE/run_v064893_cpp_against_reference.sh" \
  "$PACKAGE" "$DATA" "$CACHE" "$FORTRAN" "$PYACCEL" \
  v064893_cpp_test \
  2>&1 | tee v064893_cpp_test.host.log
```

Performance series:

```bash
"$PACKAGE/run_v064893_performance_benchmark.sh" \
  "$PACKAGE" "$DATA" "$CACHE" v064893_performance 3 \
  2>&1 | tee v064893_performance.host.log
```

Expected final markers are `V064893_RESULT=ACCEPT_TYPE50_PROFILE_OPTIMIZATION` for qualification and `V064893_RESULT=ACCEPT_TYPE50_OPTIMIZATION_SERIES` for the performance series.
