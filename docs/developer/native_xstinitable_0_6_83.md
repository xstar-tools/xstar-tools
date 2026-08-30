# 0.6.83 native xstinitable

`0.6.83` branches from formally accepted `0.6.82.40.2.46.1` and adds the missing serial XSTAR2XSPEC grid planner without changing accepted XSTAR science.

## Canonical sources

Implementation behavior is transcribed from XSTAR 2.59g `src/xstinitable/xstinitable.c`, `xstinitable.par`, `xstartablelib.h`, the XSTAR manual Chapters 6 and 14.3, and is checked against the supplied MPI_XSTAR 2x3 fixture. MPI_XSTAR itself confirms the consumer contract: rank 0 runs `xstinitable`, requires `xstinitable.lis` and `xstinitable.fits`, copies the FITS skeleton to the four table outputs, and distributes the job list.

## First frozen fixture

The canonical fixture has interpolated `column` (logarithmic, `1e20..1e21`, 2 values) and `rlogxi` (linear, `1..3`, 3 values). The highest interpolated index varies fastest, producing six jobs and `loopcontrol=1..6`.

Required closure:

```text
NINTPARM=2
NADDPARM=0
jobs=6
loopcontrol=1..6
xstinitable.lis=BYTE_EXACT
xstinitable.fits stable PRIMARY/PARAMETERS semantics=EXACT
xstinitable.fits PARAMETERS raw payload=BYTE_EXACT
```

`DATE` is creation-time metadata and is excluded from file equality.

## Scope boundary

`.83` plans only. It does not execute XSTAR, call xstar2table, schedule MPI workers, or bypass intermediate FITS. Those belong to `.84`, `.85`, and the later in-memory optimization respectively.

## Fail-closed legacy edge cases

Canonical `Generate_Combinations()` indexes `numpars-1`, so zero interpolated parameters is undefined. Interpolation formulas divide by `nst-1`, and log interpolation reads `VALUE[1]`; therefore `nst<2` is also undefined. `.83` rejects these inputs explicitly rather than manufacturing new behavior.
