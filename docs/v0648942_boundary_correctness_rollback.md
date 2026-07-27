# 0.6.48.9.4.2 boundary correctness rollback

`0.6.48.9.4` and `0.6.48.9.4.1` attempted to remove the four accepted-boundary fixed-state recomputations by reusing final-DSEC source workspaces. Host qualification showed that both reuse designs changed public science. In 9.4, the reused deferred workspace lost continuum transport opacity (`DPTHCONT_MAX=0`). In 9.4.1, moving the full projection into the terminal DSEC evaluation restored the visible option-17 continuum depth but still changed all nine FITS payloads relative to the accepted boundary calculation.

The 9.4.1 A/B harness also had a separate flaw: its forced-legacy run left the terminal-DSEC full projection enabled and then performed the legacy accepted-boundary full projection again, so the forced side executed the public projection twice. This amplified differences, but comparison of the 9.4.1 reuse products directly against the 9.4 forced-legacy/9.3 accepted products proved that the reuse path itself was still not byte-exact.

9.4.2 therefore restores the accepted 9.3 ownership contract as the production/default behavior:

- all 54 DSEC evaluations use deferred public-product projection;
- each of the four accepted boundaries performs the exact full boundary recomputation;
- the terminal post-transport zero-thickness evaluation remains a full evaluation;
- the 9.3 Type50 fast path remains unchanged;
- the 9.4 traversal prevalidation and rate evaluation-context hoist remain unchanged;
- boundary reuse can be enabled only for diagnostics with `XSTAR_V0648942_EXPERIMENTAL_BOUNDARY_REUSE=1`.

Qualification runs the default production path and an explicitly forced exact-boundary path and requires all nine FITS data payloads plus the non-timing `xout_step.log` scientific content to be identical. The old `V0648941_BOUNDARY_*` marker names are emitted as compatibility aliases so the previously rejected gates can be seen closing explicitly.
