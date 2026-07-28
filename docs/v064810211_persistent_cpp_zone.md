# 0.6.48.10.2.1.1 persistent `cpp-zone` backend

The release exposes three radial-controller modes:

- `--zone-backend python`: authoritative 0.6.48.10.1.1 accelerated-Python trajectory.
- `--zone-backend cpp-all`: one native call owns the complete four-zone production trajectory.
- `--zone-backend cpp-zone`: one persistent native context, released one physical zone at a time.

## Why `cpp-zone` is different from rejected 10.2.0/10.2.0.1

The rejected prototypes reconstructed a DSEC controller around `fixed_state_engine` and projected state between Python and C++.  The persistent mode does not reconstruct controller state.  A native worker runs the exact `command_run_standalone_production_v67` path from `xstar_standalone.cpp`.  Synchronization gates are placed immediately before each production zone and immediately after each accepted zone boundary.  Python only grants permission for the next zone and reads a scalar summary.

The native stack therefore remains alive across calls and retains xilevg/bilevg/rnisg, active-stage windows, hydrogen lifetime, radiation, tau workspaces, STEP/TRNFRC state, prepared bound-free state, and whole-run product state.

## C ABI

ABI `604810211` provides:

- `xstar_production_zone_run_all_v064810211` (`cpp-all`)
- `xstar_production_zone_context_create_v064810211`
- `xstar_production_zone_context_run_zone_v064810211`
- `xstar_production_zone_context_finalize_v064810211`
- `xstar_production_zone_context_destroy_v064810211`

`run_zone` must be called in order 1, 2, 3, 4.  It returns a read-only scalar result; that result is never fed back into the native controller.

## Qualification

Candidate-first qualification runs `cpp-all`, then `cpp-zone`.  Both must be data-bit-exact to the accepted standalone C++ reference and to one another, with DSEC counts 20/1/17/16 and source boundary sequences 58/59/60/61.  Only after both native modes pass does the runner execute the expensive `python` fallback and compare it with accepted 10.1.1.
