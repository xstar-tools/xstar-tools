# xstar_tools 0.6.48.11.2 — full variable-call multi-model closure candidate

0.6.48.11.2 continues the standalone-first 62-model qualification branch from 0.6.48.11.1. The fully accepted 0.6.48.10.2.1.1.2 `mg11_ne1e8` C++ products remain a mandatory bit-exact regression anchor.

The three execution modes remain unchanged:

```text
--zone-backend python
--zone-backend cpp-all
--zone-backend cpp-zone
```

`cpp-zone` remains a persistent native context with `run_next_zone()` / `done()` semantics. ABI 6048110 is retained.

## 11.2 changes

- Autonomous native controller calls are no longer limited to 1..4. Four-call source-sequence arrays survive only inside the explicit frozen Mg XI reference-trajectory path.
- The standalone smoke runner explicitly proves calls 5-6 for the six-zone C V model and calls 5-9 for the nine-zone Ca XIX model.
- Type 59 `phintfo` now uses the source thermodynamic constants (`kBoltzmannErgPerK` and `kModernErgPerEv`) instead of the legacy Mg-benchmark conversion introduced in 11.1.
- Five-point Type 51 supports Burgess-Tully transition types 5 and 6 in native and Python reference evaluators, with richer record-level failure diagnostics.
- Type 10 lowering resolves source `idest`-style endpoints that do not have a literal local Type-13 row.
- Generic detail, line and RRC products derive identities from the live terminal-active source inventory. The frozen Mg templates are used only for the accepted Mg anchor. Public line output is `min(600, live-ranked-lines)` rather than always 600.
- The Mg anchor is checked bit-exactly against an accepted 10.2.1.1.2 C++ product archive before it can pass the smoke stage.

## Required qualification order

Do not run the 62-model stage yet. Run only `standalone-smoke` first. If and only if all 11 models ACCEPT, run `standalone-all`, then all 62 Python-hosted `cpp-all`/`cpp-zone`, and finally the selective pure/Python-zone set.

Example smoke command:

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.11.2)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=$(realpath original_xstar_benchmark_run.tar.gz)
FORTRAN=$(realpath original_xstar.tar.gz)
MGREF=$(realpath v0648102112_reanalysis.tar.gz)
OUT=$(pwd)/v0648112_multimodel

rm -rf "$OUT"

"$PACKAGE/run_v0648112_multimodel.sh" \
  "$PACKAGE" "$DATA" "$RUNS" "$FORTRAN" "$MGREF" "$OUT" standalone-smoke \
  2>&1 | tee v0648112_standalone_smoke.host.log
```

Blocking targets include: frozen Mg XI all-nine-FITS bit-exact ACCEPT; C six-zone calls 5-6 executed; Ca nine-zone calls 5-9 executed; C V call-1 DSEC 24; Type51 and Type10 no longer abort; Mg XI3 detail rows 243; Ca XIX detail rows 168; Ca public lines 578; RRC inventories equal the FORTRAN source products.
