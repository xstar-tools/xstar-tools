## v0.6.48.7.46.25.3 genuine native public products

This release creates all nine public FITS files and `xout_step.log` inside the
native `xstar_cpp` process.  The native runner accepts no public-product oracle
argument.  FITS headers are generated during the current run and share a native
run ID; `ATDATA` is read from the supplied atomic database.  Construction and
anti-copy provenance are locally accepted, while numerical/byte parity and
production promotion remain separate, unaccepted gates.

## v0.6.48.7.46.25.2 public-product provenance closure

This corrective release invalidates the v25/v25.1 native-public-product claim.

The previous implementation embedded exact benchmark `xo01_*` FITS data blocks,
FITS header blocks, radial payloads, radial coordinates, and an `xout_step` prefix
inside the package.  CFITSIO rewrote those stored bytes, but that was benchmark
materialization rather than native product construction.

v25.2 therefore:

- retains the corrected direct `libxstar_emissivity.so` Makefile dependency;
- removes all packaged `xo*.fits`, `xout*.fits`, public FITS HDU/header `.bin`
  blocks, radial payload blocks, and stored `xout_step*.log` content;
- removes the benchmark-payload readers from `xstar_science_fits.cpp` and
  `xstar_step_log.cpp`;
- runs the 61-evaluation C++ controller with `--skip-fits`;
- deliberately creates no `xo01_*`, `xout_*`, or `xout_step.log` artifacts;
- reports native product parity as rejected until the controller retains the
  required binary64 detail, line, RRC, directional-transport, continuum-channel,
  and line-profile workspaces.

This is a provenance and false-positive-gate correction, not production
promotion and not completion of the v25 scientific milestone.
