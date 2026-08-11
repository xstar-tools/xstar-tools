# 0.6.82.11 all-element Type-49 source-faithful promotion

Canonical `ucalc.f90` Type 49 evaluates the same `phextrap` + `phint53` / Milne path for every element. The native implementation already computes that source-faithful result and retains the live continuum optical-depth and covering-fraction state, but historical compatibility logic committed the approximate legacy answer for H, He, and C while committing the source result for Mg and elements outside the historical H/He/C/Mg set.

`0.6.82.11` removes that production-science element split. If the source-faithful Type-49 evaluation succeeds, its six answer channels are committed for every element. Native production additionally requires lowered Type-49 context, live continuum `tauc` arrays, and successful source evaluation; it fails closed rather than silently falling back. Small historical unit fixtures that intentionally omit lowered source context may still exercise the compatibility evaluator outside native production.

This is aimed first at the H+He+C `cfrac=1` low-ionization qualification. Before this release, `rlogxi=-3` first diverged at the first finite radial zone, `rlogxi=-2` first diverged deep in the slab, and `rlogxi=-5` retained two small `ntotit` mismatches while remaining material-acceptable. These are external host gates; source-only validation does not declare them closed.

Frozen predecessor corrections remain: 0.6.82.10 all-element Type-53 live escape state, 0.6.82.9 source-faithful `msolvelucy` loop control, 0.6.82.8 persistent `rnisi(nd=20000)`, 0.6.82.7 Type-63 `delt>50`, and 0.6.82.6 terminal STEP endpoint.
