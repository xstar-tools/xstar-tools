# 0.6.82.30.7 — `npass=1` SAVD/detail ownership repair

This is a narrow publication/ownership correction. The accepted `npass=1`
controller, DSEC, transport, STEP, final material science, spectrum, line tau,
RRC tau, and continuum tau are not changed.

The defect was that the native SAVD snapshot machinery was retained only when
`npass>1`. For the source-valid `npass=1,lwrite>0` case, native detail FITS
therefore fell back to reconstructed live/final state. That bypassed both the
source REAL(4)+FITS-E3 scalar-keyword round trip and the sparse `fstepr3` RRC
inventory used by the already-accepted repeated-pass path.

`.30.7` retains the same source SAVD snapshot whenever the source detail stream
exists (`lwrite>0 || npass>1`) and routes single-pass detail publication through
the same saved-state writer path used by `npass=3/5`.

Host acceptance targets:

- SAVD scalar mismatches: `0`
- raw `xo01_detal3.fits` first data HDU: `346/346` rows
- RRC identity `209`: present in candidate and FORTRAN
- complete established `.27.16.5` `npass=1` comparison: `ACCEPT`

Only C++ `npass=1` is rerun. Retained FORTRAN `.30.5` output is reused. `npass=3`
and `npass=5` are not rerun.
