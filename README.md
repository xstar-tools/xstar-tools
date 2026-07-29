# xstar_tools 0.6.48.11.4.1 — frozen-Mg regression and STEP-diagnostic hotfix

0.6.48.11.4.1 is a narrow hotfix on top of 0.6.48.11.4. It does **not** change the variable-zone architecture, generic runtime `critf` science, or the successful 11.4 source-publication predicates.

It corrects two qualification regressions found by the 11.4 standalone smoke:

1. The explicit frozen `mg11_ne1e8` reference trajectory again receives the historical effective active-ion threshold `critf=1e-7`, while every autonomous/non-reference model continues to receive the parsed runtime `critf` (normally `1e-6` in this benchmark suite). This is intended to restore the accepted all-nine-FITS bit-exact Mg regression contract without undoing the 11.4 generalization.
2. Compact first-STEP attribution is emitted to `stderr` only when `XSTAR_V06481141_STEP_DIAGNOSTICS=1`. The qualification runner enables that flag only for `helike_type69/c5_ne1e10`, so the markers remain visible even though the historical controller `stdout` stream is production-silenced. Normal production remains quiet.

The 11.4 generic publication changes are frozen unchanged, including the strong Mg XI3 improvements in detailed lines and RRC inventories.

## Next qualification

Run only the 11-model standalone smoke:

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.11.4.1)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=$(realpath original_xstar_benchmark_run.tar.gz)
FORTRAN=$(realpath original_xstar.tar.gz)
MGREF=$(realpath v0648102112_reanalysis.tar.gz)
OUT=$(pwd)/v06481141_multimodel

rm -rf "$OUT"

"$PACKAGE/run_v06481141_multimodel.sh" \
  "$PACKAGE" "$DATA" "$RUNS" "$FORTRAN" "$MGREF" "$OUT" standalone-smoke \
  2>&1 | tee v06481141_standalone_smoke.host.log
```

The hotfix-specific gates are:

```text
V06481141_MG_FROZEN_ALL_FITS_DATA_BIT_EXACT=ACCEPT
V06481141_RUNTIME_CRITF_1E6_OBSERVED=ACCEPT
V06481141_FIRST_STEP_LIMIT_DIAGNOSTICS_PRESENT=ACCEPT
```

The first C-V STEP record should additionally expose the selected limiting bin, energy, opacity, tau, radiation, radius/column limits, final `delr`, and effective `critf` in `standalone-smoke/helike_type69__c5_ne1e10/cpp_standalone.host.log`.

Do not run `standalone-all` unless the smoke ends with 11 accepted / 0 rejected.
