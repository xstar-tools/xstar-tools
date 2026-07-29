# xstar_tools 0.6.48.11.3 — focused multi-model smoke corrections

0.6.48.11.3 is a deliberately narrow correction release on top of 0.6.48.11.2. It does **not** redesign the variable-call radial controller. The accepted 0.6.48.10.2.1.1.2 `mg11_ne1e8` standalone products remain the hard all-nine-FITS bit-exact regression anchor.

The production modes remain unchanged:

```text
--zone-backend python
--zone-backend cpp-all
--zone-backend cpp-zone
```

`cpp-zone` remains the same persistent native controller with `run_next_zone()` / `done()` semantics. Production-zone ABI **6048110** is retained.

## 11.3 focused corrections

The 11.2 host smoke was `1/11 ACCEPT`, but it established that the frozen Mg anchor and call-5+ infrastructure are sound. 11.3 addresses only the concrete failures attributed by that smoke:

- **Ca Type51 record 160243:** accept a finite signed five-point spline result exactly as source `upsil.f90` does; remove the extra native `upsilon >= 0` rejection. Existing BT5/BT6 support remains.
- **Public lines:** treat source `nlplmx=600` as a maximum, not an exact required count. Internally consistent ranked inventories of `<=600` rows are valid, including the 578-row Ca reference surface.
- **Generic active-stage projection:** suppress stages absent from lowered level metadata and stages whose known terminal populations are all zero. The frozen Mg identity templates are untouched.
- **Type59:** retain the 11.2 modern source constants and analytic Verner/Milne implementation, but use source `expo()` clamping and enforce the source `bremsint(nb1) < 1e-20` skip before Type59 spectral/opacity ownership.
- **Type10:** use source `expo()` clamping while retaining the 11.2 endpoint-resolution correction.
- **Qualification diagnostics:** report candidate/reference science-HDU row counts and explicit no-abort markers for Ca Type51 record 160243, Ca sub-600 public lines, and O VII Type10 execution.

No radial termination predicate, DSEC architecture, persistent-zone ABI, or accepted Mg science path is intentionally changed.

## Required qualification order

Run only the 11-model standalone smoke first. `standalone-all` remains blocked unless all 11 smoke models pass; only after all 62 standalone models pass should the Python-hosted `cpp-all`/`cpp-zone` stage run, followed last by selective expensive Python qualification.

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.11.3)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=$(realpath original_xstar_benchmark_run.tar.gz)
FORTRAN=$(realpath original_xstar.tar.gz)
MGREF=$(realpath v0648102112_reanalysis.tar.gz)
OUT=$(pwd)/v0648113_multimodel

rm -rf "$OUT"

"$PACKAGE/run_v0648113_multimodel.sh" \
  "$PACKAGE" \
  "$DATA" \
  "$RUNS" \
  "$FORTRAN" \
  "$MGREF" \
  "$OUT" \
  standalone-smoke \
  2>&1 | tee v0648113_standalone_smoke.host.log
```

Do **not** run `standalone-all` unless the result is:

```text
V0648113_STAGE_ACCEPTED_MODELS=11
V0648113_STAGE_REJECTED_MODELS=0
V0648113_STAGE_RESULT=ACCEPT
```

Also inspect these focused gates:

```text
V0648113_MG_FROZEN_ALL_FITS_DATA_BIT_EXACT=ACCEPT
V0648113_CA_TYPE51_RECORD160243_NO_ABORT=ACCEPT
V0648113_CA_PUBLIC_LINE_LT600_NO_ABORT=ACCEPT
V0648113_O7_TYPE10_EXECUTION=ACCEPT
V0648113_C6_CALLS_5_6_EXECUTED=ACCEPT
V0648113_CA9_CALLS_5_9_EXECUTED=ACCEPT
```

The row-count diagnostics should show whether the active-stage fix moves Mg XI3 detail/RRC and Ca detail/line/RRC inventories toward their FORTRAN source counts before any additional writer work is attempted.
