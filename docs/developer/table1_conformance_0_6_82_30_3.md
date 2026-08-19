# xstar_tools 0.6.82.30.3 - permanent Table-1 conformance gate hotfix

`0.6.82.30.3` supersedes the host-rejected `0.6.82.30.2` qualification harness. No numerical/science production source is changed.

## Host failure reproduced

The `.30.2` target readbacks were correct for FORTRAN, C++, and Python, but its FORTRAN context verifier failed 58 later probes with `cfrac` observed as stock `0` instead of Manual Table-1 `1`.

The cause is a real source/XPI default conflict: the permanent gate intentionally uses the literal Manual Table-1 baseline (`cfrac=1`), while stock HEASoft `xstar.par` uses `cfrac=0`. `.30.2` first wrote the Table-1 private file and then called `pset`; on the host, `pset` rematerialized/synchronized the private file from stock XPI defaults. Therefore an unrelated probe such as `temperature=100` retained its target value but silently reset the surrounding `cfrac` context to `0`.

## Corrected contract

For each of the 59 public parameters:

1. start from a new temporary PFILES directory;
2. copy the stock parameter *schema/ranges* while directly writing the complete expected 59-value case state;
3. hide query modes only in that private qualification copy;
4. change exactly one value relative to the documented baseline;
5. use `pget` only as non-query readback when available, otherwise read the private file directly;
6. parse the same private file after readback and verify all 58 unaffected values remained at baseline;
7. discard that temporary PFILES directory before the next parameter.

Normal surface qualification never invokes `pset` or `pquery`.

The 57 displayed Manual Table-1 parameters retain their literal Table-1 defaults. `naabund=1` and `lstep=0` remain explicitly classified as public/source extensions omitted from the displayed table.

## Science freeze

- canonical oracle: FORTRAN XSTAR 2.59g
- science revision: `0.6.48.12.3.45.3.3.8`
- C API ABI: `60487`
- production-zone ABI: `6048110`
- fixed-state ABI: `60488`
- tracked numerical/science files: 137
- expected changed numerical/science files: 0
