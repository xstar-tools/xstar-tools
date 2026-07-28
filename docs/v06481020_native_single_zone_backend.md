# v0.6.48.10.2.0 native C++ single-zone backend

## Goal

Remove the dominant Python orchestration cost inside each radial-shell DSEC convergence solve without changing the accepted Python boundary/transport/product ownership. The new CLI switch is `--zone-backend python|cpp`.

## Qualified scope

- Benchmark: `mg11_ne1e8`.
- `--zone-backend python`: frozen 0.6.48.10.1.1 behavior.
- `--zone-backend cpp`: persistent native context, one C ABI call per radial-shell DSEC solve.
- Canonical DSEC counts: 20, 1, 17, 16.
- Python retains the post-DSEC boundary `calc_hmc_all`, HEATT/source-order boundary work, STEP/TRNFRC transport, final recompute, C++ `binemis` product promotion, and FITS writers.
- Active ATDB subset and complete modular C++ backend set are required.

## Source identities

The native DSEC evaluations use source positions:

- zone 1: 1-20;
- zone 2: 22;
- zone 3: 23-39;
- zone 4: 41-56.

Positions 21, 40, and 57 are structural non-evaluation positions. Native-only boundary synchronization mirrors identities 58-61 to retain hidden active-stage/repeated-H state across zone calls; Python still performs the externally visible boundary evaluation.

## State crossing the Python/C++ boundary

Inputs include temperature, electron fraction, H density, incident/full DSEC radiation, continuum and line optical depths, abundance/covering/turbulence configuration, and global `xilevg/bilevg/rnisg`. The native context keeps lowered ATDB program state and fixed-state lifetime state persistent across the four calls. Outputs are the converged DSEC state and updated global level workspaces.

## Qualification

The host runner performs two accelerated runs from the same package. The Python-zone fallback must be raw-FITS-data exact to the 10.1.1 reference. The C++-zone candidate must preserve 20/1/17/16 topology, stay within the existing <=1% public product gate relative to 10.1.1, and pass the established structural, detal4, and spectrum analyzers. Per-zone wall times are recorded for both runs; <=120 s for the four native-zone calls is a reported performance target, not a substitute for science closure.

The baseline 10.1.1 result is scientifically accepted: all nine FITS payloads match accepted 10.0 exactly and public science closure passes. Its 10.340630 s final recompute exceeds the former 10 s timing threshold by 0.340630 s only, so 10.2.0 treats that threshold as diagnostic.
