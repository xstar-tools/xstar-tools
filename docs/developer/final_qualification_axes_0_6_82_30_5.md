# 0.6.82.30.5 final qualification axes

This candidate supersedes the experimental 59-parameter runtime-surface probe as the release decision layer. The permanent release test now runs real FORTRAN XSTAR 2.59g cases and compares C++ products using the already-qualified science comparators.

The gate covers: `cfrac=0,0.4,1`; `emult=0.1,0.25,0.5,1`; `niter=0,-99,1,99`; `lcpres=0,1`; analytic and `density.dat` `radexp`; `npass=1,3,5`; `pow`, `bbody`, `bremss`, and file spectra with `spectun=0,1,2`; `ncn2=999,9999,19999`; representative output controls; and H+He+C/O/Ca/Fe science.

FORTRAN case directories are retained as the canonical reference tree. A later Python phase must compare pure-Python outputs to these same FORTRAN references rather than regenerate a different oracle set.

Run:

```bash
heainit
make -C src/xstar_tools/xstar/cpp -j2 xstar-cpp
python tools/qualification/run_final_qualification_axes_host_smoke_0_6_82_30_5.py fortran-cpp \
  --package "$PWD" --data-dir ../xstar/data --fortran-bin xstar \
  --output-root "$PWD/run_final_qualification_axes_0682305" --replace
```

Required final marker:

```text
FINAL_QUALIFICATION_0682305_RESULT=ACCEPT
```
