# 0.6.82.30.8.9 C++ public-line publication fast path

`0.6.82.30.8.9` is a publication-only successor to host-accepted `0.6.82.30.8.8`.

## Accepted `.30.8.8` baseline

The returned `.30.8.8` Fe host run preserved canonical FORTRAN science (`STEP`, material, spectrum, and `ntotit=13,1,1` all ACCEPT; `LOGT_MAX_ABS=0`) while reducing publication from `99.684676 s` to `77.680234 s`.  The controller remained preserved at `53.264775 s`.  Bulk serialization handled `3,932,404` scalar cells with `196` column writes and `24` flushes.

## Public-line fast path

Before `.30.8.9`, `write_public_lines()` constructed the terminal line inventory, terminal depth inventory, record maps/search lambdas, and every-zone diagnostic maps before checking whether the retained writer-owned public-line arrays were already complete.  True production already retains five 600-row arrays:

- `product_write_public_line_index`;
- `product_write_public_line_emit_inward`;
- `product_write_public_line_emit_outward`;
- `product_write_public_line_depth_inward`;
- `product_write_public_line_depth_outward`.

`.30.8.9` checks those arrays immediately.  If every array has exactly 600 values and all 600 retained indices resolve through the existing `.30.8.8` indexed line-identity lookup, the writer:

1. builds only the 600 label rows;
2. creates the unchanged `XSTAR_LINES` table;
3. directly serializes the retained emission/depth arrays through the unchanged `.30.8.8` bulk CFITSIO layer;
4. returns immediately.

That path does not construct `terminal_list`, `terminal_depth_list`, `terminal_by_record`, `terminal_depth_by_record`, or `diagnostics_by_zone`.

If any retained array is incomplete or any identity cannot be resolved, the writer falls through to the complete pre-`.30.8.9` reconstruction path.  No reconstruction formula, fallback ordering, threshold, or science value was changed.

## Per-product timing

The standalone performance report now emits the requested product clocks directly from `steady_clock` measurements around the existing writer calls:

```text
DETAIL_POPULATION_SECONDS=...
DETAIL_LINE_SECONDS=...
DETAIL_RRC_SECONDS=...
DETAIL_SPECTRUM_SECONDS=...
PUBLIC_LINES_SECONDS=...
PUBLIC_RRC_SECONDS=...
PUBLIC_CONT_SECONDS=...
PUBLIC_SPECT_SECONDS=...
```

For multipass detail publication the four detail clocks accumulate all pass-specific files.  Public clocks measure the individual final public products.  The existing aggregate `V064890_PERF_SCIENCE_FITS_SECONDS` and `V064890_PERF_PUBLICATION_SECONDS` remain unchanged.

The log also reports:

```text
V06823089_PUBLIC_LINES_RETAINED_FAST_PATH=YES
```

for the intended production path.

## Frozen `.30.8.8` publication layer

This release does not alter `BulkFitsBufferV06823088`, its type projection rules, flush boundaries, or the same-binary escape hatch:

```bash
XSTAR_DISABLE_BULK_FITS_06823088=1
```

REAL(4), integer, string, row order, HDU layout, keywords, checksum handling, and public schemas therefore retain `.30.8.8` semantics.

## Qualification

Acceptance requires unchanged Fe science against the retained canonical `.30.6` FORTRAN reference, `.30.8.8` bulk FITS enabled, the retained public-line fast path active, all eight product timers present, and publication time below the accepted `.30.8.8` `77.680234 s` baseline on the host run.
