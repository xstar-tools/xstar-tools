## 0.6.48.11.9.4.1 Type50 publication-shadow `abel` ownership hotfix

11.9.4 regressed the previously-qualified `xo01_detal2` zero/negligible-row inventory because its new raw Type50 shadow used `state.plasma.abundances` (`ababs=abel*abcosmic`) in the source `calc_emisab_ion` abundance gate.  FORTRAN passes `xeltp=abel(jk)`, the user abundance multiplier.  For the Ca xi=2 case that distinction is `1` versus `2.1e-6`, enough to suppress thousands of source rows and to push line 88440 below the default-REAL `1.e-34` call gate.

11.9.4.1 changes only the output-publication shadow: it reads `state.control["abel"]`, preserves raw Type50 caller-local `opakb1` evolution, applies the caller's literal `oplin=opakb1*abund1` signal test, and enforces the source endpoint-validity predicate before stale state can be consumed.  Physical `rcem`, `oplin`, `opakc`, rates, equilibrium, continuum/RRC arrays, radial transport, and C++ science are unchanged.

Run only `helike_type69/ca19_xi2_ne1` with `run_v064811941_multimodel.sh ... python-one`.  Do not rerun the full smoke yet.

## 0.6.48.11.9.3 detail-line inventory / comparator closure

Pure-Python detail-line output now carries a source-only Type50/rate-4 publication activity shadow so FORTRAN-compatible zero/negligible rows can be retained in exact ATDB/source order without contaminating physical opacity. Qualification compares repeated `XSTAR_RADIAL` extensions by occurrence. Continue using `python-one <model-id>` and qualify the Ca XIX xi=2, xi=3.5, and xi=4 models individually before rerunning the full smoke.

# xstar_tools 0.6.48.11.8

### 0.6.48.11.9.2 pure-Python smoke

Use `run_v06481191_multimodel.sh ... python-smoke` to run the canonical 11-model smoke set using only the Python source-port backends. This stage is intentionally independent of standalone-C++ qualification and compares each Python result directly with the FORTRAN authority.


0.6.48.11.8 is a diagnostic-only follow-up to the accepted 0.6.48.11.7.1 frozen-Mg hotfix. The 11.7.1 host smoke restored all nine frozen `mg11_ne1e8` FITS products bit-exact while leaving the carbon trajectory unchanged. The remaining C V problem is therefore attributed downstream of preliminary active-window selection: the call-1 compact carbon solve converges to a C III lower-level population near 0.782, which drives Type50 record 5740 and the 12.709136 eV first-STEP opacity.

This release does **not** change the carbon matrix, Lucy-style normalization, Type50, GSSMOOTH, STEP, or generic Type7 physics. It adds a call-1 carbon solve attribution surface after the solve has completed.

## Standalone smoke

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.11.8)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=$(realpath original_xstar_benchmark_run.tar.gz)
FORTRAN=$(realpath original_xstar.tar.gz)
MGREF=$(realpath v0648102112_reanalysis.tar.gz)
OUT=$(pwd)/v0648118_multimodel

rm -rf "$OUT"

"$PACKAGE/run_v0648118_multimodel.sh" \
  "$PACKAGE" \
  "$DATA" \
  "$RUNS" \
  "$FORTRAN" \
  "$MGREF" \
  "$OUT" \
  standalone-smoke \
  2>&1 | tee v0648118_standalone_smoke.host.log
```

Do not run `standalone-all` until the smoke reaches 11/11 ACCEPT.

## C call-1 compact solve attribution

For `helike_type69/c5_ne1e10`, the runner sets `XSTAR_V0648118_C_SOLVE_ATTRIBUTION_DIR` and the fixed-state engine writes the final call-1 carbon diagnostic state into six CSV files:

- `manifest.csv`: active rows/superlevels/ions, normalization row, solve method/status, residuals, fixed-point iteration counts, and contribution inventory.
- `rows.csv`: compact/full/global identity, source ion stage, superlevel, stage-ground and normalization flags, and populations at each solve phase.
- `stage_totals.csv`: preliminary `xitp` versus final solved population by carbon ion stage, including the fully stripped state.
- `matrix_terms.csv`: exact native committed matrix terms with source position, record, rate/data type, row/stage/superlevel endpoints, coefficients, fixed-point branch, and high-ion/terminal ownership flags.
- `fixed_point_rows.csv`: reconstructed `riu/rui/ril/rli` budgets, raw and normalized fixed-point candidates, and final row deltas.
- `condensed_matrix.csv`: final condensed superlevel matrix after normalization-row replacement, including stage/terminal ownership of each superlevel.

The writer runs only after the carbon element solve has completed and never mutates production arrays.

## Frozen contracts

- Frozen `mg11_ne1e8` retains the 11.7.1 reference-only preliminary-Type7 compatibility path.
- Generic models retain the literal Type7 source endpoint predicate from 11.7.
- The frozen Mg all-nine-FITS bit-exact comparator remains blocking.
- Production-zone ABI remains 6048110.
- The runtime STEP diagnostic marker prefix remains `V0648117_STEP_*`; 11.8 qualification parses that intentionally frozen prefix.

## 0.6.48.11.9.2 single-model pure-Python qualification

The Python radial controller now preserves source default-REAL precision for the input column limit.  Iterative multi-element repair should use `run_v06481192_multimodel.sh ... python-one <model-id>` rather than rerunning the full 11-model smoke after each patch.  `XSTAR_QUALIFICATION_CACHE_DIR` may point at an accepted existing `python_cache` directory.
