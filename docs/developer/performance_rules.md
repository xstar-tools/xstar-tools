# Performance rules

Performance optimization must preserve the accepted scientific implementation.

Rules:

- measure before optimizing;
- keep science acceptance separate from runtime acceptance;
- use the same model/input/data/compiler when comparing timings;
- record CPU features and thread settings;
- prefer generic source-equivalent optimizations over element/model-specific shortcuts;
- do not reopen frozen Type50, trajectory, matrix, or transport semantics merely for speed;
- after a behavior-affecting optimization, qualify one fast model before broadening coverage.

Historical performance reports remain available through version-control history and release tags. They are useful attribution evidence, not current user-facing performance guarantees.
