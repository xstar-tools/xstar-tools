# xstar-atomic

Latest package note: **v0.3.128** adds the first public API-infrastructure layer for source-code-first XSTAR alignment.

New public objects and functions:

```python
from xstar_atomic import (
    LocalPlasmaState,
    RadiationField,
    EscapeContext,
    RateEvaluation,
    evaluate_type50_bound_bound,
    type50_line_pumping,
)
```

v0.3.128 adds:

- `src/xstar_atomic/context.py` with `LocalPlasmaState`, `RadiationField`, and `EscapeContext`.
- `src/xstar_atomic/rates_type50.py` with the audit-only `RateEvaluation` result class and `evaluate_type50_bound_bound(...)` source-code-aligned type-50 evaluator.
- `src/xstar_atomic/audit.py` with reusable `type50_line_pumping(...)` audit logic.
- A converted `examples/55_audit_helike_type50_line_pumping.py` wrapper, preserving the CLI while moving reusable logic into the package.
- Reorganized Markdown and LaTeX user guides modeled after workflow-first `chianti-tools` documentation.
- `docs/example_to_source_api_map.md`, mapping examples that should migrate into stable source modules.

The type-50 evaluator records the XSTAR `ucalc.f90` source-code formula:

```fortran
ans1 = aij * (ptmp1 + ptmp2)
sigma = 0.02655 * flin * elin * 1.d-8 / vtherm
ans2 = sigma * bremsa(nb1) * vtherm / 3.e10 * flinabs(ptmp1)
ans2 = ans2 * max(0., 1.d0-cfrac)
! final swap: ans1 is lower->upper photoexcitation; ans2 is upper->lower escaped decay
```

No solver physics changed in v0.3.128. The type-50 photoexcitation/line-pumping path remains **audit-only**; no empirical triplet scale fitting was added.


## Examples

See `examples/README.md` for grouped runnable examples and recommended learning paths. The most advanced validation examples remain diagnostic/source-code-first workflows and may require same-run XSTAR outputs.
