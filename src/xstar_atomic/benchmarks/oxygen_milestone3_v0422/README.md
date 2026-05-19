# Frozen oxygen Milestone-3 benchmark (v0.4.22)

This snapshot freezes the accepted solve-call-219 oxygen O III--O VIII
Milestone-3 benchmark.  Acceptance is based on complete source-faithful matrix
assembly, native Lucy convergence, and 607/607 final-population parity.

The bundled v0.4.21 products are immutable evidence of the accepted population
result.  v0.4.22 closes type 56 by reproducing the literal `hunt3` edge
extrapolation and `max(0,cijpp)` source behavior.  Because the original XSTAR
probes are external, a user rerun is still required to refresh the complete
record-level matrix comparison after the type-56 correction.

Strict residual matrix-family and raw `msolvelucy` state parity are deferred
diagnostics and do not invalidate the accepted Milestone-3 population solver.
