# XSTAR Table-1 parameter contract - xstar_tools 0.6.82.23

`0.6.82.23` creates the parameter-contract layer without changing atomic, thermal, matrix, transport, or controller science.

## Authority and conflict policy

The validation envelope and fresh executable defaults are taken from the supplied stock XSTAR 2.59g `src/xstar/xstar.par`, because those are the limits/defaults enforced by XPI before `rread1.f90`. The XSTAR Manual Release 2.5x Table 1 and section 4.3 are retained separately in `qualification/table1_parameter_contract_0_6_82_23.json`.

Known conflicts are not hidden:

- `cfrac`: Table 1/detailed manual `1.0`; stock `xstar.par` `0.0`.
- `column`: Table 1/`xstar.par` `1e17`; detailed section 4.3.9 says `1e21`.
- `nsteps`: Table 1/`xstar.par` `3`; detailed section 4.3.15 says `2`.
- `loopcontrol`: Table 1/`xstar.par` `0`; detailed section 4.3.27 says `1`.
- `lwrite`: detailed manual documents `-1`, while stock XPI range is `0..1`.
- `radexp`: source/manual describe a `radexp<-100` `density.dat` branch, while stock XPI range is `-3..3`.
- `spectun`: `rread1.f90` contains a `specunit==2` file-spectrum branch while stock XPI range is `0..1`; `0.6.82.28` intentionally exposes `0..2` in the modern public contract and host-tests the unchanged executable through a temporary XPI metadata shadow.
- `naabund` and `lstep` exist in stock `xstar.par`/`rread1` but are omitted from manual Table 1.

The supplied environment for building this candidate has no HEASoft executable, so `probe_stock_xstar_defaults_0_6_82_23.py` must be run after `heainit` on a host. It creates an empty local PFILES directory and queries `$HEADAS/syspfiles` to avoid learned user values.

## Contract changes

- C++ production defaults no longer contain benchmark-model values (`density=1e8`, `rlrad38=1e6`, `column=1e20`, `rlogxi=1.5`, `nsteps=10`, `niter=99`, `critf=1e-6`, `vturbi=100`, etc.).
- C++ and Python use the same 59-rule stock `xstar.par` type/default/range contract.
- Invalid public values are rejected rather than silently clamped (`ncn2` is exactly `999..999999`; `cfrac` exactly `0..1`; `nsteps` `1..1000`, etc.).
- All 30 abundance multipliers are represented with source defaults (Li/Be/B zero; all others one).
- The historical first 56 FORTRAN `fparmlist` rows remain in source order; `radexp`, `ncn2`, and `mode` are appended as provenance rows so all 59 stock public parameters are retained.
- Standard `xstar-cpp` commands fill omitted public keys from fresh stock defaults before writing the JSON envelope; execution provenance records the resulting complete public parameter mapping.

## Deliberately deferred physics

This release does not implement the already-planned physics successors:

- `0.6.82.24`: `niter=0`, negative, positive source semantics. C++ retains `requested_niter` but keeps the pre-existing effective floor until that milestone.
- `0.6.82.25`: `lcpres` / constant-pressure evolution.
- `0.6.82.26`: `radexp` / `density.dat` physics.
- `0.6.82.27`: full `npass` multipass transport.
- `0.6.82.28`: full spectrum/`spectun` contract.
- `0.6.82.29`: output-control completion.
- `0.6.82.30`: permanent all-Table-1 conformance gate.
- `0.6.82.31-.33`: frozen `.22` low-ionization performance baseline and later speed closure.
