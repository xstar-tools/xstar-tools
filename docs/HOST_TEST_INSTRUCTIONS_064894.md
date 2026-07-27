# Host test — xstar_tools 0.6.48.9.4

Run the full science + boundary A/B qualification first:

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

If it is accepted, run one warm-up plus three measured standalone-C++ runs:

```bash
"$PACKAGE/run_v064894_performance_benchmark.sh" \
  "$PACKAGE" "$DATA" "$CACHE" v064894_performance 3 \
  2>&1 | tee v064894_performance.host.log
```

The qualification run intentionally executes one extra forced-legacy boundary product run.  The performance series does not.
