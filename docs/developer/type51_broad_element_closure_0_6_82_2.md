# 0.6.82.2 broad-element Type-51 production closure

`0.6.82.1` proved on the canonical host ATDB that the generic multi-element
lowerer can lower a realistic 15-element mixture (`LOWERED_ACTIVE_ELEMENTS=15`,
20,435 rows, 533,396 records).  The run then terminated in the first production
evaluation on the retained legacy Type-51 compatibility calculation.

Canonical XSTAR `ucalc.f90` label 51 evaluates only `nrdt=7` and `nrdt=11`.
Other real-payload lengths follow the normal no-contribution `goto 9000` path.
The five-point evaluator is `upsil.f90`; the nine-point evaluator is
`upsiln.f90`.  Neither source routine imposes a positivity gate on the final
finite upsilon value.

`0.6.82.2` therefore keeps the frozen legacy calculation wherever it returns a
finite value, preserving previously accepted outputs.  When that compatibility
evaluator cannot represent a source-valid record, production commits the
source-faithful Type-51 answer instead of aborting the whole element/model.
Unsupported payload lengths are skipped exactly as in `ucalc.f90`.

The source-faithful Burgess-Tully transform no longer requires the scaling
parameter to be positive for rational transform types 2/3/5/6; it only requires
the mathematical denominator to be finite and non-zero.  Logarithmic types
1/4 retain their positive-domain requirements.

No accepted atomic-rate, transport, matrix, opacity, emissivity, publication,
or threshold policy is reopened.  The accepted science revision remains
`0.6.48.12.3.45.3.3.8`; the production-zone ABI remains `6048110`.

The physical host gate is version-locked:

```bash
python3 tools/qualification/run_multi_element_host_smoke_0_6_82_2.py \
    --data-dir /path/to/xstar/data \
    --replace
```

The runner first requires `xstar-cpp --version` to report package version
`0.6.82.2`; this prevents stale binaries from being mistaken for the current
source tree.
