# 0.6.48.10.2.1 shared standalone-production native zone engine

## Design

The rejected 10.2.0 and 10.2.0.1 prototypes constructed a second controller around `fixed_state_engine`. They omitted controller-owned lifetime/workspace state and diverged in call 1. 10.2.1 is restarted from 10.1.1 and shares the accepted controller directly.

`libxstar_production_zone.so` is compiled from the same `xstar_standalone.cpp` translation unit used by the standalone executable. Its C ABI calls `command_run_standalone_production_v67`. Therefore the C++ zone mode and standalone production share DSEC convergence, call-start state, active-stage/H lifetime, accepted-boundary recomputation, STEP/TRNFRC, source-workspace retention, final state, and ProductWritingState.

In this first safe shared-engine release, `--zone-backend cpp-all` gives C++ ownership of the complete radial trajectory rather than returning partially projected zone workspaces to Python. Python supplies normalized parameters and changes only FITS provenance headers after native publication. `--zone-backend python` remains the unmodified 10.1.1 controller path.

## Acceptance

1. Candidate must execute 20/1/17/16 DSEC evaluations.
2. Candidate nine FITS data payloads must be bit-exact to the accepted standalone C++ reference.
3. Only after candidate acceptance, run `--zone-backend python` and require its nine FITS data payloads to be bit-exact to accepted 10.1.1 plus normalized step-log identity.
4. Report exact native zone wall times.
