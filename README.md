## v0.6.48.7.46.25.5.2 exact-source retention foundation

This release retains native committed line/RRC/continuum/profile workspaces and ATDB-derived public identities, but deliberately blocks public FITS and `xout_step.log` writing until all exact radial-transfer and legacy-print state is retained. Its metadata exporter uses `PprintElementMetadata.element_label` and the canonical normalized `vturbi` parameter. See `V06487462552_NATIVE_SOURCE_WORKSPACE_RETENTION_FOUNDATION.md`.

## v0.6.48.7.46.25.4 native output-grid depth closure

This release fixes the v25.3 state-finalization failure that prevented every public product from being written.  The native controller's 301,301-value internal continuum workspace is retained only as source-state provenance; it is no longer treated as a 9,999-bin FITS depth array.  `xstar_cpp` derives output-grid inward and outward continuum depths from native opacity across the five accepted radial boundaries, then writes all nine FITS products and `xout_step.log`.  The runner accepts no public-product oracle path and prints its internal native log on any failure.  Native construction is qualified separately from scientific parity.

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

### v0.6.48.7.46.25.5.15.9.7 developer preview mode

Set `XSTAR_V0487462551597_WRITE_SCHEMA_PREVIEW=1` with `run_v0487462551597_native_product_state_completion.sh` to write schema-only preview products (`xo01_*.fits`, `xout_*.fits`, and `xout_step.log`).  These files are marked as previews and `PARITY=NOT_CLAIMED`; they are not production products and are not compared to the v0.6.47.2 oracle.
