# xstar_tools 0.6.48.11.6

0.6.48.11.6 is a focused C Type50 scalar-provenance correction built on 0.6.48.11.5.

The 11.5 first-STEP audit identified the C V `c5_ne1e10` radial blocker as Type50 source position 8740 / record 5740 (C III, rows 29 -> 33) near 12.709136 eV. Direct product comparison showed the native line opacity was about 3.53e5 too large. The corresponding C III lower-level population was also about 3.53e5 too large (`~0.782` native versus `~2.2144e-6` FORTRAN), while the Type50 atomic/profile scalar was not implicated.

The source-faithful correction is therefore population ownership, not a line-specific rescale. For carbon runtime seeds, 11.6 copies selected `xilevg` values into the compact solve basis without normalizing the selected slice and forces the terminal normalization-row seed to zero, matching `calc_hmc_element.f90`; the existing solve remains responsible for conservation. O/Ca generic seed behavior is intentionally unchanged in this release.

A diagnostic-only record-5740 provenance sidecar records `lower_population -> abund1 -> sigvtherm -> opakb1` and verifies that the carbon runtime seed was loaded without renormalization. The 11.5 first-STEP opacity-family and top-producer diagnostics are retained. No STEP, GSSMOOTH, bound-free, Type50 kernel, or ABI formula is otherwise changed.

Frozen contracts remain: canonical `mg11_ne1e8` all-nine-FITS bit exact, production-zone ABI 6048110, runtime `critf=1e-6` for generic models, and the frozen Mg compatibility threshold.

Run only the 11-model standalone smoke first:

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.11.6)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=$(realpath original_xstar_benchmark_run.tar.gz)
FORTRAN=$(realpath original_xstar.tar.gz)
MGREF=$(realpath v0648102112_reanalysis.tar.gz)
OUT=$(pwd)/v0648116_multimodel
rm -rf "$OUT"

"$PACKAGE/run_v0648116_multimodel.sh" \
  "$PACKAGE" "$DATA" "$RUNS" "$FORTRAN" "$MGREF" "$OUT" standalone-smoke \
  2>&1 | tee v0648116_standalone_smoke.host.log
```

Do not run `standalone-all` unless the smoke is 11/11 ACCEPT.

### 0.6.48.11.7 carbon preliminary ion-balance qualification

The 11.7 standalone smoke adds source-faithful call-1 carbon audits for the preliminary ionization equilibrium. Rate-type-7 contributions to `pirti` obey the literal XSTAR `calc_ion_rates.f90` endpoint rule `idest1 == 1 && idest2 <= nlev + 2`. Diagnostic CSVs expose record ownership and the stagewise `pirti/rrrti -> xitp -> mml/mmu` chain. No stage is manually widened and no Type50 opacity is rescaled.
