# xstar_tools 0.6.48.11.4 — runtime critf and literal source-publication closure

0.6.48.11.4 is a focused source-faithfulness release on top of 11.3. It does not redesign the variable-zone controller. The accepted 0.6.48.10.2.1.1.2 `mg11_ne1e8` standalone products remain the mandatory all-nine-FITS bit-exact anchor, and production-zone ABI **6048110** remains frozen.

The production modes remain:

```text
--zone-backend python
--zone-backend cpp-all
--zone-backend cpp-zone
```

## 11.4 focused corrections

- **Runtime `critf`:** the native preliminary ion balance now consumes the model `critf` (`1e-6` in the supplied benchmark suite) instead of a hard-coded `1e-7`.
- **Literal `mml/mmu`:** active ion stages are selected with the same crossing search and one-stage expansion as `calc_hmc_element.f90`.
- **STEP attribution:** each selected next-shell width reports its initial radius/column limit, limiting continuum bin, energy, opacity, `tau_in`, `zrems(1)`, `emult/opakc`, remaining-column limit, and runtime `critf`. The STEP equation itself is unchanged.
- **`xo01_detail`:** generic rows require live `xilev > 1e-34` per `fstepr.f90`.
- **`xo01_detal2`:** generic line rows require source `rcem/oplin` signal and the `fstepr2.f90` type/wavelength eligibility.
- **`xo01_detal3`:** generic RRC rows require `cemab/cabab/opakab > 1e-36` per `fstepr3.f90`.
- **`xout_lines1`:** generic lines are filtered with the `writespectra2.f90` type, wavelength, and luminosity gates before source-style luminosity ranking up to 600 rows.

## Required qualification order

Run only the 11-model standalone smoke first:

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.11.4)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=$(realpath original_xstar_benchmark_run.tar.gz)
FORTRAN=$(realpath original_xstar.tar.gz)
MGREF=$(realpath v0648102112_reanalysis.tar.gz)
OUT=$(pwd)/v0648114_multimodel

rm -rf "$OUT"

"$PACKAGE/run_v0648114_multimodel.sh" \
  "$PACKAGE" \
  "$DATA" \
  "$RUNS" \
  "$FORTRAN" \
  "$MGREF" \
  "$OUT" \
  standalone-smoke \
  2>&1 | tee v0648114_standalone_smoke.host.log
```

Do **not** run `standalone-all` unless:

```text
V0648114_STAGE_ACCEPTED_MODELS=11
V0648114_STAGE_REJECTED_MODELS=0
V0648114_STAGE_RESULT=ACCEPT
```

Also inspect:

```text
V0648114_MG_FROZEN_ALL_FITS_DATA_BIT_EXACT=ACCEPT
V0648114_RUNTIME_CRITF_1E6_OBSERVED=ACCEPT
V0648114_FIRST_STEP_LIMIT_DIAGNOSTICS_PRESENT=ACCEPT
V0648114_C6_CALLS_5_6_EXECUTED=ACCEPT
V0648114_CA9_CALLS_5_9_EXECUTED=ACCEPT
V0648114_CA_TYPE51_RECORD160243_NO_ABORT=ACCEPT
V0648114_CA_PUBLIC_LINE_LT600_NO_ABORT=ACCEPT
V0648114_O7_TYPE10_EXECUTION=ACCEPT
```

