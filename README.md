# xstar_tools 0.6.48.11.1 — multi-model native science closure

0.6.48.11.1 is the first science-generalization follow-up to the 0.6.48.11.0 variable-zone benchmark scaffold. The accepted `mg11_ne1e8` 0.6.48.10.2.1.1.2 baseline remains the regression anchor.

The first 11-model standalone smoke run showed three independent gaps: C/O/Ca runs aborted on active ATDB Types 7/10/59/66, the public option-17 writer still contained a four-zone reconstruction assumption for non-anchor trajectories, and public detail/line/RRC inventories could retain source-inactive ion stages. This release addresses those gaps while keeping the three production modes unchanged:

```text
--zone-backend python
--zone-backend cpp-all
--zone-backend cpp-zone
```

`cpp-zone` remains a persistent native controller with `run_next_zone()` / `done()` semantics and does not reconstruct native state in Python.

## Native record-family additions

- Type 7: source dielectronic-recombination formula.
- Type 10: source ionized-H charge-transfer formula.
- Type 59: analytic Verner bound-free cross section plus source `phintfo` scalar integration and direct continuum opacity.
- Type 66: source `calt66` collision-strength representation and excitation/de-excitation rates.

The Type 59 implementation intentionally does not add direct RRC-emission arrays: the corresponding source `phintfo.f90` update statements are commented out.

## Qualification order

Do not run the expensive Python stages yet. The required order is:

1. `standalone-smoke` — 11 diverse models spanning C V, O VII, Mg XI, Ca XIX and all observed 2/3/4/5/6/9-zone regimes.
2. `standalone-all` — all 62 models, only after smoke is fully accepted.
3. `python-cpp-modes` — all 62 through Python-hosted `cpp-all` and `cpp-zone`, only after all standalone models pass.
4. `python-selective` — a representative subset through pure Python and accelerated Python with `--zone-backend python`.

Run the smoke stage with:

```bash
PACKAGE=$(realpath ../xstar_tools-0.6.48.11.1)
DATA=/media/linux/mhd/xstar/xstar/data
RUNS=$(realpath original_xstar_benchmark_run.tar.gz)
FORTRAN=$(realpath original_xstar.tar.gz)
OUT=$(pwd)/v0648111_multimodel

rm -rf "$OUT"

"$PACKAGE/run_v0648111_multimodel.sh" \
  "$PACKAGE" \
  "$DATA" \
  "$RUNS" \
  "$FORTRAN" \
  "$OUT" \
  standalone-smoke \
  2>&1 | tee v0648111_standalone_smoke.host.log
```

The desired blocking result is `V0648111_STAGE_ACCEPTED_MODELS=11`, `V0648111_STAGE_REJECTED_MODELS=0`, and `V0648111_STAGE_RESULT=ACCEPT`. A failure is expected to be diagnostic: each model retains its standalone host log, products, FORTRAN comparison JSON, and comparison log.
