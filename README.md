# xstar_tools 0.6.48.11.5

This is a focused first-STEP opacity-producer attribution release built on 0.6.48.11.4.1.

The accepted Mg XI reference behavior, runtime critical-fraction semantics, variable-zone controller, Type51/Type10/Type59 corrections, and 11.4 source-publication work are frozen. 0.6.48.11.5 does not change production opacity, thermal, matrix, transport, or STEP decisions.

For the C V `c5_ne1e10` smoke model, 11.4.1 showed that the first STEP interval is limited by bin 3124 at 12.70913639927371 eV, where native `opakc` is 5.6061198940153781e-09 cm^-1 and the resulting shell is 8.9188245962016955e7 cm. This release attributes that exact limiting opacity.

The diagnostic records the already-computed additive opacity families before and after source-order GSSMOOTH: bound-free, free-free, selected-line/profile, and Thomson. It also reuses the existing native per-record opacity kernels to write a call-1 producer inventory and reports the largest pre-GSSMOOTH bound-free and line owners at the actual STEP-limiting bin. Record identities are labeled pre-GSSMOOTH because GSSMOOTH redistributes opacity between bins.

The frozen `mg11_ne1e8` path remains required to pass all-nine-FITS bit-exact comparison. The production-zone ABI remains 6048110.

Run only the 11-model standalone smoke first:

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.11.5)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=$(realpath original_xstar_benchmark_run.tar.gz)
FORTRAN=$(realpath original_xstar.tar.gz)
MGREF=$(realpath v0648102112_reanalysis.tar.gz)
OUT=$(pwd)/v0648115_multimodel
rm -rf "$OUT"

"$PACKAGE/run_v0648115_multimodel.sh" \
  "$PACKAGE" "$DATA" "$RUNS" "$FORTRAN" "$MGREF" "$OUT" standalone-smoke \
  2>&1 | tee v0648115_standalone_smoke.host.log
```

Do not run `standalone-all` unless the smoke is 11/11 ACCEPT.
