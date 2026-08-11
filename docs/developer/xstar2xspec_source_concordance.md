# XSTAR2XSPEC / xstar2table source concordance — 0.6.81

This document records the canonical XSTAR source semantics used by the
`xstar_tools 0.6.81` native characterization layer.  It is a product-layer
port only; it does not change XSTAR atomic or plasma science.

## Canonical sources reviewed

The supplied XSTAR Release 2.5x source archive was mapped against the manual,
especially Chapter 6 and Chapter 14.3.

| Canonical source | 0.6.81 responsibility | SHA-256 of supplied source |
| --- | --- | --- |
| `xstar/src/xstar2table/xstar2table.c` | reads `xout_spect1.fits`, slices energy, computes AIN/AOUT/MTABLE/ETABLE, maps `loopcontrol` to table row/column | `5a69fba776f8644f55718f49a75743b1e88c44fd648bcfeedecddb3b6709bdb9` |
| `xstar/xstarlib/src/xstartablelib.c` | writes `ENERGIES` and `SPECTRA` extensions, `PARAMVAL`, `INTPSPEC`, `ADDSPnnn`, `LASTSPEC`, OGIP keywords | `0f99aea6f73f7f13a4e85f4957e4979714b96e4666de72b2628afdf89bcb13de` |
| `xstar/src/xstinitable/xstinitable.c` | writes PRIMARY/PARAMETERS table metadata; interpolated rows precede additive rows | `eece9d4ce052eca976710dd2f45a4ab3353e423bfc8f654668784dacf0c3e741` |
| `xstar/scripts/xstar2xspec` | orchestration order and one `xstar2table` call per XSTAR model | `fb4593724ed10b9e0eb671cfcb5c530d501b4cdcb50cfb08cd4543a73f4f943a` |

## Canonical pipeline

```text
xstinitable
  -> PRIMARY/PARAMETERS table template
  -> xstinitable.lis XSTAR command list

xstar2xspec
  -> run XSTAR for each grid point/additive case
  -> call xstar2table after each run

xstar2table
  -> read xout_spect1.fits
  -> fill xout_ain.fits
  -> fill xout_aout.fits
  -> fill xout_mtable.fits
  -> fill xout_etable.fits
```

The manual describes the same three-component division.  `xstinitable` creates
the parameter grid/table skeleton, while `xstar2table` post-processes each
`xout_spect1.fits` into the XSPEC table products.

## FITS input contract

The historical `Read_XSTAR_Spectra` routine moves to `XSTAR_SPECTRA` and reads
all five columns with CFITSIO `TFLOAT`:

```text
energy
incident
transmitted
emit_inward
emit_outward
```

Therefore the 0.6.81 compatibility reader intentionally stores these as
32-bit `float` arrays.  The compatibility transform also uses `float`
intermediate/output storage to preserve historical rounding behavior.

`rlrad38`, `loopcontrol`, and interpolated parameter values are read from the
ordinary XSTAR `PARAMETERS` extension.

## Energy slicing

The historical `SliceEnergySpectra` behavior is unusual and is preserved for
normal interior ranges:

- the low side includes the interval that straddles `ELOW`;
- the high side keeps the last interval whose upper edge is not above `EHIGH`;
- table edges are written in keV, while XSTAR input spectral energies are eV.

For example, with source energies

```text
50, 100, 200, 400, 800, 1600 eV
```

and `ELOW=150`, `EHIGH=900`, the historical selection is

```text
100-200
200-400
400-800 eV
```

The original C function can read `energy[j+1]` at the final array element and
leaves some state undefined if a boundary is exactly the first grid value.
0.6.81 makes only those endpoint cases bounds-safe; the canonical interior
selection semantics are unchanged.

## Spectral transforms

For selected source bin `i`, the historical additive normalization is:

```text
enorm = 8.356e-7 * (energy[i+1] - energy[i])
        / (rlrad38 * energy[i])

AIN[i]  = enorm * emit_inward[i]
AOUT[i] = enorm * emit_outward[i]
```

`AIN` and `AOUT` are written as XSPEC additive spectra in
`photons/cm^2/s` per table bin.

The multiplicative model is:

```text
if incident[i] == 0:
    MTABLE[i] = 0
else:
    MTABLE[i] = transmitted[i] / incident[i]
```

The historical code diagnoses ratios outside `[0,1]` but does not clamp them.
0.6.81 preserves the numerical value.

The exponential model reuses the multiplicative spectrum and applies only the
historical floor used for the logarithm:

```text
transmission = max(MTABLE[i], 1e-32)
ETABLE[i] = -ln(transmission)
```

Consequences deliberately covered by the 0.6.81 fixture:

- exact zero incident flux -> `MTABLE=0`;
- tiny positive transmission -> `ETABLE=-ln(1e-32)`;
- transmission greater than one remains greater than one in MTABLE and gives a
  negative ETABLE optical depth, matching the historical arithmetic.

## XSPEC table schema

The 0.6.81 writer reproduces the legacy table organization:

```text
PRIMARY
PARAMETERS
ENERGIES
SPECTRA
```

`PARAMETERS` columns:

```text
NAME      12A
METHOD    J
INITIAL   E
DELTA     E
MINIMUM   E
BOTTOM    E
TOP       E
MAXIMUM   E
NUMBVALS  J
VALUE     nE
```

Interpolated parameters are written before additive parameters.  An
interpolated row has positive `NUMBVALS`; an additive row has zero
`NUMBVALS`.

`ENERGIES` uses 32-bit float columns:

```text
ENERG_LO  E  keV
ENERG_HI  E  keV
```

`SPECTRA` contains:

```text
PARAMVAL
INTPSPEC
ADDSP001
ADDSP002
...
```

with 32-bit float vector columns.  `ADDMODEL` is true for `xout_ain.fits` and
`xout_aout.fits`, false for `xout_mtable.fits` and `xout_etable.fits`.
`REDSHIFT` is retained as the primary-header logical metadata flag.

## Parameter and job ordering

Legacy `xstar2table` maps:

```text
row    = 1 + (loopcontrol - 1) / (NADDPARM + 1)
column =     (loopcontrol - 1) % (NADDPARM + 1)
```

column zero is `INTPSPEC`; positive columns are `ADDSPnnn`.

0.6.81 deliberately keeps the sequential `LASTSPEC`/positive-loopcontrol
contract because this release is characterization, not the parallel-grid
redesign.  For an ordinary standalone XSTAR file that records
`loopcontrol=0`, explicitly supplied file order is accepted as the
compatibility job order.

The later parallel milestone will replace completion-order dependence with a
stable job-ID destination mapping.

## Energy-grid consistency improvement

The canonical source contains a placeholder asking whether later spectra match
the first `ENERGIES` extension; it does not actually perform the check.
0.6.81 makes exact selected-energy-grid equality a hard error.  This does not
change a valid canonical table but prevents silently combining incompatible
spectra.

## Scope boundary

0.6.81 does **not** implement the full native `xstinitable` planner.  A compact
metadata file supplies the table definition while ordinary
`xout_spect1.fits` files supply the spectra and parameter values.  Full
constant/additive/interpolated grid generation is scheduled for 0.6.83.

0.6.81 also does not yet consume `ProductWritingState` directly; the in-memory
bridge is the 0.6.82 milestone.

## 0.6.81.1 canonical 2x3-grid closure

A real XSTAR 2.59g / MPI_XSTAR grid with `column=(1e20,1e21)` and `rlogxi=(1,2,3)` exposed two characterization defects in 0.6.81 that the synthetic fixture did not catch.

1. Historical `SliceEnergySpectra` reports `eBinHigh` as an **energy-edge index** while `nEnergyBins` counts intervals. For the canonical `(4452-7866)` edge range the correct number of XSPEC bins is therefore `7866-4452 = 3414`, not 3415.
2. The source literal `8.356e-7` is a C double literal. Canonical AIN/AOUT arithmetic evaluates that constant in double precision and stores the final `enorm` in `float`; changing the literal itself to `8.356e-7f` produces small but real last-bit differences.

0.6.81.1 corrects only those two table-conversion details. The permanent compressed regression fixture contains the six canonical `xout_spect1.fits` inputs, `xstinitable.fits`/`.lis`, the four canonical table outputs, and the characterized metadata. Qualification requires bit-exact `ENERG_LO`, `ENERG_HI`, `PARAMVAL`, and all four `INTPSPEC` arrays. XSTAR scientific kernels and XSPEC-table ABI 1 are unchanged.

