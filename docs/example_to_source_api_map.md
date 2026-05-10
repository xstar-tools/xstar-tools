# Example-to-source API migration map

This note records which current `examples/` workflows are good candidates for moving reusable logic into `src/xstar_atomic/`.  The goal is to keep examples as short, reproducible command-line wrappers while making the science workflows available through a stable Python API.

## Migration priorities

| Priority | Examples | Proposed source module | Rationale |
|---:|---|---|---|
| 1 | `55_audit_helike_type50_line_pumping.py` | `xstar_atomic.audit.type50_line_pumping` | Completed in v0.3.128. This is the immediate API-infrastructure path for source-code-first line-pumping work. |
| 1 | `51_run_helike_local_state_validation.py` | `xstar_atomic.runs.select_local_states` | Local XSTAR state discovery and same-run target selection are reusable for all ions and future validations. |
| 1 | `52_summarize_helike_local_state_comparison.py` | `xstar_atomic.validate.summarize_local_state_comparison` | Combines standard comparison products; should become a stable validation report API. |
| 1 | `53_audit_helike_resonance_deficit.py` | `xstar_atomic.audit.resonance_deficit` | Shares helpers with type-50 and population-flux audits. |
| 1 | `54_audit_helike_resonance_population_flux.py` | `xstar_atomic.audit.resonance_population_flux` | Useful population-weighted matrix-term budget for future solver changes. |
| 2 | `43_compare_xstar_detail_populations.py` | `xstar_atomic.validate.compare_detail_populations` | Central comparison tool used by multiple workflows. |
| 2 | `42_xstar_like_element_solver_demo.py` | `xstar_atomic.solve.element` | Core solver orchestration should become public API; demo can stay as CLI. |
| 2 | `47_prepare_mg_ca_xstar_triplet_targets.py` | `xstar_atomic.xout.convert_triplet_targets` | Same-run line target conversion is broadly reusable. |
| 2 | `50_mg_ca_xstar_local_state_audit.py` | `xstar_atomic.audit.local_state` | Local-state audit logic overlaps with example 51. |
| 3 | `15`--`22` O VII source-fit/cascade scans | `xstar_atomic.source_models` or `xstar_atomic.cascade` | Useful but still diagnostic/empirical; move only stable helpers. |
| 3 | `27`--`31` type-69 diagnostics | `xstar_atomic.audit.type69` | Useful after rate-evaluator API is generalized. |
| 3 | `33`--`41` response-matrix/source-basis tools | `xstar_atomic.response` and `xstar_atomic.audit.response` | Large experimental suite; migrate incrementally. |

## Proposed source package layout

```text
xstar_atomic.context          LocalPlasmaState, RadiationField, EscapeContext
xstar_atomic.rates_type50     RateEvaluation and type-50 source-code evaluator
xstar_atomic.rates            future public evaluator dispatch
xstar_atomic.audit            reusable source-code-first audits
xstar_atomic.runs             XSTAR run-tree discovery and local-state selection
xstar_atomic.validate         XSTAR comparison summaries
xstar_atomic.xout             XSTAR output conversion helpers
xstar_atomic.matrix           provenance-rich population matrix assembly
xstar_atomic.solve            stable element/ion solver orchestration
xstar_atomic.emissivity       line and triplet products
```

## API migration rule

A workflow is ready to move from `examples/` to `src/` when:

1. it is useful for more than one example or ion;
2. its inputs and outputs can be represented by typed objects or stable dictionaries;
3. it has regression tests that do not require the full external XSTAR run tree;
4. it does not depend on empirical fitted scale factors as final physics;
5. any solver-changing option is audit-only or opt-in until same-run XSTAR validation is complete.

## v0.3.128 status

Implemented:

```text
xstar_atomic.context.LocalPlasmaState
xstar_atomic.context.RadiationField
xstar_atomic.context.EscapeContext
xstar_atomic.rates_type50.RateEvaluation
xstar_atomic.rates_type50.evaluate_type50_bound_bound
xstar_atomic.audit.type50_line_pumping
```

Converted:

```text
examples/55_audit_helike_type50_line_pumping.py
```

The example is now a CLI wrapper and the reusable audit is available from Python.
