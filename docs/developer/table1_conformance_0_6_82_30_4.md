# xstar_tools 0.6.82.30.4 - benchmark-style FORTRAN Table-1 surface gate

`0.6.82.30.4` supersedes the host-rejected `0.6.82.30.3` qualification harness. It changes no numerical/science production source.

## Why `.30.3` was rejected

`.30.3` attempted to materialize a private `xstar.par` and then read it through HEASoft parameter tools. On the host, the FORTRAN readback resolved the untouched stock/default state instead of the intended one-parameter override: all 59 FORTRAN targets returned baseline values. C++ and Python propagation were correct. This proved that parameter-file readback is not the right permanent oracle for the FORTRAN public invocation path.

## Correct FORTRAN invocation

The XSTAR manual and the accepted benchmark invoke canonical FORTRAN directly:

```bash
xstar name=value name=value ...
```

`.30.4` therefore supplies the complete 59-value command vector directly to `xstar` for every ordinary surface case. Exactly one command-line value differs from the permanent baseline.

The permanent baseline remains the literal Manual Table-1 defaults (`spectrum=pow`, `spectrum_file=spct.dat`, `temperature=400`, `density=1e4`, `cfrac=1`, `niter=0`, `critf=1e-7`, `ncn2=9999`, `modelname='XSTAR Default'`) plus the two explicitly labeled public/source extensions `naabund=1` and `lstep=0`.

## Actual FORTRAN runtime evidence

After `rread1`, canonical XSTAR 2.59g unconditionally writes an `input parameters:` block to `xout_step.log`. `.30.4` waits for that block through the final `radexp=` row, parses the actual runtime state, and then terminates that surface-only XSTAR process. This keeps the 59-parameter intake gate fast while exercising the real executable/XPI/RREAD1 path. Full science is still run by the representative matrix and inherited core replays.

Source-faithful conditional ownership is explicit:

- `pressure`: at the Table-1 baseline `lcpres=0`, `rread1` does not read `pressure`; runtime remains the source baseline `0.03`. Active pressure semantics are covered by the lcpres replay.
- `spectrum_file`: at `spectrum=pow`, `rread1` does not read it and runtime `specfile` is blank. File-spectrum semantics are covered by the spectrum replay.
- `spectun`: at `spectrum=pow`, `rread1` does not read it and runtime remains `0`. File-spectrum unit modes are covered by the spectrum replay.
- `mode`: this is an XPI interface parameter, not an `rread1` science consumer. Its surface evidence is successful direct command acceptance through the runtime snapshot.

No normal surface probe uses `pset`, `pget`, `pquery`, or a hand-written private `xstar.par`.

## Frozen science boundary

- canonical oracle: FORTRAN XSTAR 2.59g
- science revision: `0.6.48.12.3.45.3.3.8`
- C API ABI: `60487`
- production-zone ABI: `6048110`
- fixed-state ABI: `60488`
- tracked numerical/science files: 137
- changed numerical/science files: 0
