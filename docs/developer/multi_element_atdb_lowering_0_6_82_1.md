# 0.6.82.1 multi-element native ATDB/lowering closure

## Scope

`0.6.82.1` closes a native ATDB-lowering rejection exposed by a realistic
multi-element XSTAR composition.  The failing 0.6.82 run stopped during ATDB
lowering with `destination outside compact element basis` before any zone
science was evaluated.

The repair is structural and element-independent.  It does not add per-element
exceptions and it does not change the accepted in-bounds C/O/Mg/Ca arithmetic.

## Canonical XSTAR source contract

The implementation was checked directly against the supplied XSTAR 2.59g
sources:

- `xstarlib/src/calc_hmc_ion.f90`
- `xstarlib/src/calc_hmc_element.f90`
- `xstarlib/src/msolvelucy.f90`
- `xstarlib/src/levwkelement.f90`
- `xstarlib/src/ucalc.f90`
- `xstarlib/src/setptrs.f90`

`calc_hmc_ion` retains ion-local `idest1`/`idest2`.  `calc_hmc_element` shifts
those endpoints into the element matrix with the current `ipmat2` offset.  The
shifted endpoint is not required to be less than or equal to the active compact
matrix dimension at this stage.  `msolvelucy` applies the terminal-row alias
when it consumes the matrix, using source expressions of the form
`min(ipmat,indb(...))`.

The native 0.6.82 lowerer applied the compact-range check too early.  This was
benign for previously qualified small element subsets but rejected ordinary
source-valid records in a broad composition.

## Native repair

`xstar_atdb_runtime.cpp` now preserves the positive shifted source endpoint.
For records whose raw endpoint lies beyond the element compact dimension,
source `leveltemp` snapshots remain available for scalar energy/statistical
weight metadata.  For every endpoint already inside the compact dimension, the
previous compact-row value is used unchanged.

`local_zone_engine.cpp` now performs the source-equivalent matrix alias at the
consumption boundary:

```text
native_matrix_row = min(raw_source_endpoint, compact_element_rows)
```

The raw endpoint remains attached to the record for source identity,
publication, and diagnostics; only the matrix row is aliased.

## Multi-element capability target

The lowering rule is independent of atomic number and is intended for the
complete supported XSTAR element domain Z=1..30.  The packaged realistic
`examples/xstar_example.par` enables the broad mixture used in the
XSTAR2XSPEC/MPI_XSTAR characterization:

```text
H He C N O Ne Mg Al Si S Ar Ca Cr Fe Ni
```

The remaining elements are legal with zero abundance, and the abundance-table
contract from 0.6.82 remains unchanged.

## Qualification policy

The package-local gate proves:

1. exact source-concordance hashes for the supplied canonical routines;
2. element-independent raw endpoint preservation for Z=1..30;
3. non-positive endpoint rejection remains active;
4. matrix-consumption clamping is present at the runtime boundary;
5. in-bounds endpoint behavior remains the same as 0.6.82;
6. the realistic public example is packaged and has the expected broad active
   element inventory;
7. the sealed 0.6.81.1 canonical XSTAR2TABLE fixture remains bit-exact;
8. all frozen ABI/revision boundaries remain unchanged.

The canonical `atdb.fits` is intentionally not bundled with xstar_tools.  A
host with the XSTAR data installation should additionally run
`examples/xstar_example.par` as the physical end-to-end broad-mixture smoke.
The package-local source/structural gate does not pretend that this external
831-MB scientific database is present when it is not.

## Frozen boundaries

- accepted science revision: `0.6.48.12.3.45.3.3.8`
- frozen C++ reference: `0.6.48.12.3.44`
- C API ABI: `60487`
- production-zone ABI: `6048110`
- fixed-state ABI: `60488`
- XSPEC-table ABI: `1`
