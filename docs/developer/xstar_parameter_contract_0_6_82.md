# XSTAR public parameter contract closure — 0.6.82

## Scope

Release 0.6.82 closes four public XSTAR input contracts needed before native
`xstinitable` can safely generate XSTAR2XSPEC grids: `abundtbl`, `lwrite`,
`lprint`, and `loopcontrol`.  The work is source-concordance and public-interface
work; it does not change the frozen atomic/rate/matrix science revision.

Canonical references used for this milestone are the XSTAR 2.59g sources
`xstarlib/src/xstarsetup.f90`, `xstarlib/src/rread1.f90`,
`src/xstar/xstar.f90`, `src/xstar/xstar.par`,
`src/xstar2table/xstar2table.c`, and `xstarlib/src/xstartablelib.c`, together
with XSTAR Manual Chapters 4, 5, and 6.

## `abundtbl`

XSTAR selects a 30-element H-through-Zn cosmic abundance base in
`xstarsetup.f90` and then applies the public `habund` ... `znabund`
multipliers.  0.6.82 implements the ten tables documented by the manual:

- `xdef`
- `angr`
- `aspl`
- `feld`
- `aneb`
- `grsa`
- `wilm`
- `lodd`
- `lpgp`
- `lpgs`

The supplied XSTAR 2.59g source spells the two Lodders, Palme & Gail (2009)
selectors `lgpp` and `lgps`.  xstar_tools accepts both the documented
`lpgp`/`lpgs` spellings and the source `lgpp`/`lgps` spellings; each pair maps
to the same source abundance array.  Unknown selectors follow XSTAR's fallback
policy and use `xdef` (with a Python warning on the Python normalization path).

The element parameters remain *multipliers*, not absolute abundances:

```text
physical_abundance[Z] = abundance_base(abundtbl)[Z] * element_multiplier[Z]
```

The same rule is applied by Python normalization and by the native production
parameter reader when it is given raw XSTAR-style parameters rather than an
already-normalized `physical_abundances` vector.

## `lwrite`

`src/xstar/xstar.par` exposes `lwrite` as integer 0..1.  The manual describes
`lwrite=1` as enabling the four pass-specific detailed FITS families.  The
literal `xstar.f90` condition is slightly more general:

```fortran
if ((lwri.gt.0).or.(npass.gt.1)) then
    ... detail FITS open/save/close ...
endif
```

Therefore 0.6.82 uses the source condition:

```text
write detail FITS = (lwrite > 0) OR (npass > 1)
```

For the common `npass=1` case:

- `lwrite=0`: do **not** publish `xo01_detail.fits`, `xo01_detal2.fits`,
  `xo01_detal3.fits`, or `xo01_detal4.fits`;
- `lwrite=1`: publish those four products.

The standard final products (`xout_abund1.fits`, `xout_lines1.fits`,
`xout_rrc1.fits`, `xout_cont1.fits`, `xout_spect1.fits`, and
`xout_step.log`) remain part of the normal run contract.  Therefore the
native public acceptance count is also control-dependent: `lwrite=0,npass=1`
requires five FITS products plus `xout_step.log`, while `lwrite>0` or
`npass>1` requires nine FITS products plus `xout_step.log`.  Python and native
publication now use the same conditional detail-product rule; no placeholder
detail FITS are emitted merely to satisfy an old fixed count.

The manual also mentions a historical `lwrite=-1` mode, but the supplied
2.59g `xstar.par` constrains the public XPI parameter to 0..1.  0.6.82 follows
the actual public 2.59g parameter-file range and records this documentation/
XPI discrepancy rather than inventing an extra public value.

## `lprint`

The supplied `xstar.par` permits `lprint=-1..6`.  Manual section 4.3.17 defines
its role as an ASCII/log verbosity control and explicitly states that the
standard FITS products are unaffected:

- `-1`: minimal final-zone printout intended for large XSTAR2XSPEC grids;
- `0`: default, including the brightest line/RRC summaries;
- `1`: additional line/RRC luminosity/depth tables;
- `2`: additional local ion fractions, thermal rates, and level populations;
- `3`: continuum luminosities and emissivities;
- `4`: line/level/transition metadata;
- `5`: detailed internal rates;
- `6`: accepted by the public parameter file and follows the high-verbosity
  source branches (`lpri>=4` / `lpri>=5`) where applicable.

0.6.82 validates the canonical range and preserves the requested value in the
run state and published parameter metadata.  The already-qualified
comparator-visible `xout_step.log` science remains unchanged.  The complete
optional historical terminal/log formatting for nonzero `lprint` is
**characterized but is not claimed bit-for-bit complete**; normal runs report
that limitation in provenance/warnings.  This avoids reopening the 0.6.80
production-diagnostics cleanup merely to reproduce developer/verbose ASCII.

## `loopcontrol`

The supplied XSTAR parameter file defines:

```text
loopcontrol = 0..30000, default 0, "0=standalone"
```

0.6.82 validates and preserves this range.  `loopcontrol=0` remains the
standalone XSTAR value.  Positive values are the 1-based XSTAR2XSPEC grid job
identities written into each `xout_spect1.fits` PARAMETERS extension.

The canonical 2x3 MPI_XSTAR fixture has exactly:

```text
column=1e20 rlogxi=1 loopcontrol=1
column=1e20 rlogxi=2 loopcontrol=2
column=1e20 rlogxi=3 loopcontrol=3
column=1e21 rlogxi=1 loopcontrol=4
column=1e21 rlogxi=2 loopcontrol=5
column=1e21 rlogxi=3 loopcontrol=6
```

Canonical `xstar2table.c` maps loop control to XSPEC table placement as:

```text
row    = 1 + (loopcontrol - 1) / (NADDPARM + 1)
column =     (loopcontrol - 1) % (NADDPARM + 1)
```

and `xstartablelib.c::Write_FITS_Spectra` checks `LASTSPEC+1==loopcontrol`.
The 0.6.81/0.6.82 compatibility table path intentionally retains that
historical sequential rule.  Completion-order-independent assembly belongs to
the later native parallel grid engine.

## XSTAR2XSPEC C++ source comments

`xstar_xspec_table.cpp` and `xstar_xspec_table_writer.cpp` now carry explicit
file-level and function-level source-concordance comments.  They state that the
native compatibility implementation was developed from XSTAR Manual Chapter 6
and by direct comparison with `xstar2table.c` and `xstartablelib.c`.  This is
important provenance: those files reproduce XSTAR2XSPEC serialization and
transform semantics; they do not define new atomic physics.

## Scientific boundary

0.6.82 preserves:

- accepted Python science revision `0.6.48.12.3.45.3.3.8`;
- frozen all-62 C++ science baseline `0.6.48.12.3.44`;
- C API ABI `60487`;
- production-zone ABI `6048110`;
- fixed-state ABI `60488`;
- XSPEC-table ABI `1`.

No atomic rate, matrix, opacity, emissivity, transfer, or accepted scientific
threshold is changed by this milestone.
