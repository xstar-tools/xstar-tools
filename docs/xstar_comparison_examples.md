# XSTAR comparison validation examples

This page documents saved validation comparisons between `xstar-atomic` and direct XSTAR model outputs.
The comparison files are included under:

```text
docs/validation/xstar_outputs/
examples/reference_outputs/
```

The reference XSTAR outputs were generated from `xout_lines1.fits` files and converted to CSV with:

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xout_lines1.fits \
  --out-csv xstar_lines.csv \
  --print-summary
```

The comparison examples use `examples/08_compare_xstar_outputs.py`. Two modes are important:

- `--mode wavelength`: validates line identification and wavelengths.
- `--mode both`: also reports diagnostic ratios between local `xstar-atomic` emissivity coefficients and XSTAR model output columns.

The absolute ratios in `--mode both` are not expected to be unity because `xstar-atomic` reports local atomic coefficients, while XSTAR `emit_inward`/`emit_outward` columns are full model outputs that include ion fractions, geometry, column, density, and radiative-transfer effects.


## Included XSTAR test-run archive

The package also includes a small reproducibility directory:

```text
xstar_test_run/
  README.md
  o_ne_xi3/xout_lines1.fits
  o7_xi15/xout_lines1.fits
  o7_xi15_highdens/xout_lines1.fits
  ne_xi25/xout_lines1.fits
  ne_xi35/xout_lines1.fits
  xstar_o_ne_xi3_lines.csv
  xstar_o8_lya_lines.csv
  xstar_o7_triplet_lines.csv
  xstar_ne9_triplet_lines.csv
  xstar_ne10_lya_lines.csv
```

The README in `xstar_test_run/` records the exact direct-XSTAR commands used
for the O VIII/Ne IX high-ionization run, the O VII triplet runs, the Ne IX/Ne X
focused runs, and validated Mg/Si/Fe Stage-5 comparison artifacts. It also records the
`xstar_atomic.xstar_outputs` commands used to convert each `xout_lines1.fits`
file into CSV.

For example, using the included O VII triplet CSV:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_test_run/xstar_o7_triplet_lines.csv \
  --ion "O VII" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_o7_triplet_wavelength.csv \
  --out-json compare_o7_triplet_wavelength.json \
  --print-summary
```

## O VIII Ly-alpha wavelength validation

Saved files:

```text
docs/validation/xstar_outputs/compare_o8_lya_wavelength.csv
docs/validation/xstar_outputs/compare_o8_lya_wavelength.json
```

Command used:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_o8_lya_lines.csv \
  --ion "O VIII" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_o8_lya_wavelength.csv \
  --out-json compare_o8_lya_wavelength.json \
  --print-summary
```

Result summary:

| XSTAR wavelength (Angstrom) | xstar-atomic wavelength (Angstrom) | Difference (Angstrom) | Transition |
|---:|---:|---:|---|
| 18.9671 | 18.96710968 | `~9.7e-6` | `1s1.2S_1/2 -> 1s0.2p1.2P_3/2` |
| 18.9725 | 18.97251701 | `~1.7e-5` | `1s1.2S_1/2 -> 1s0.2p1.2P_1/2` |

This validates that `xstar-atomic` recovers the same O VIII Ly-alpha line wavelengths and level identifications as XSTAR's `xout_lines1.fits` output.

## O VIII Ly-alpha wavelength plus emissivity diagnostic

Saved files:

```text
docs/validation/xstar_outputs/compare_o8_lya_both.csv
docs/validation/xstar_outputs/compare_o8_lya_both.json
```

This example uses `--mode both`. It is useful for tracking the local atomic coefficient associated with each matched line, but the ratio to XSTAR `emit_outward` is only diagnostic.

## O VII triplet wavelength validation

Saved files:

```text
docs/validation/xstar_outputs/compare_o7_triplet_wavelength.csv
docs/validation/xstar_outputs/compare_o7_triplet_wavelength.json
```

Command used:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_o7_triplet_lines.csv \
  --ion "O VII" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_o7_triplet_wavelength.csv \
  --out-json compare_o7_triplet_wavelength.json \
  --print-summary
```

Result summary:

| XSTAR wavelength (Angstrom) | xstar-atomic wavelength (Angstrom) | Difference (Angstrom) |
|---:|---:|---:|
| 22.1012 | 22.10120010 | `~1.0e-7` |
| 21.8070 | 21.80699921 | `~8.0e-7` |
| 21.6020 | 21.60199928 | `~7.2e-7` |
| 21.8044 | 21.80439949 | `~5.1e-7` |

This validates the decoded O VII triplet/near-triplet wavelengths and level identification. The current direct-emissivity join does not produce local collisional emissivity coefficients for all O VII triplet lines; XSTAR emits these lines through its full plasma model, including population, recombination, cascade, and radiative-transfer physics.


## Ne IX / Ne X Stage-5 wavelength validation

Saved files:

```text
docs/validation/xstar_outputs/compare_ne9_triplet_wavelength.csv
docs/validation/xstar_outputs/compare_ne9_triplet_wavelength.json
docs/validation/xstar_outputs/compare_ne10_lya_wavelength.csv
docs/validation/xstar_outputs/compare_ne10_lya_wavelength.json
```

The package now includes the direct-XSTAR neon-only runs used to make these
comparisons:

```text
xstar_test_run/ne_xi25/xout_lines1.fits
xstar_test_run/ne_xi35/xout_lines1.fits
xstar_test_run/xstar_ne9_triplet_lines.csv
xstar_test_run/xstar_ne10_lya_lines.csv
```

The Ne IX run (`xstar_atomic_ne_xi25`, `rlogxi=2.5`) produces five He-like
triplet/near-triplet lines between 13.3 and 13.8 Angstrom. All five lines match
`xstar-atomic` within the 0.02 Angstrom tolerance. The maximum wavelength
difference is approximately `4.41e-05` Angstrom.

| XSTAR wavelength (Angstrom) | xstar-atomic wavelength (Angstrom) | Difference (Angstrom) | Transition |
|---:|---:|---:|---|
| 13.6987 | 13.69874287 | `4.29e-05` | `1s2.1S_0 -> 1s1.2s1.3S_1` |
| 13.4470 | 13.44699955 | `4.50e-07` | `1s2.1S_0 -> 1s1.2p1.1P_1` |
| 13.5500 | 13.55004406 | `4.41e-05` | `1s2.1S_0 -> 1s1.2p1.3P_2` |
| 13.5529 | 13.55288982 | `1.02e-05` | `1s2.1S_0 -> 1s1.2p1.3P_1` |
| 13.5534 | 13.55344105 | `4.10e-05` | `1s2.1S_0 -> 1s1.2p1.3P_0` |

The Ne X run (`xstar_atomic_ne_xi35`, `rlogxi=3.5`) produces the two Ly-alpha
fine-structure components near 12.13 Angstrom. Both components match
`xstar-atomic` within the 0.02 Angstrom tolerance. The maximum wavelength
difference is approximately `1.52e-05` Angstrom.

| XSTAR wavelength (Angstrom) | xstar-atomic wavelength (Angstrom) | Difference (Angstrom) | Transition |
|---:|---:|---:|---|
| 12.1321 | 12.13208485 | `1.52e-05` | `1s1.2S_1/2 -> 1s0.2p1.2P_3/2` |
| 12.1375 | 12.13749313 | `6.87e-06` | `1s1.2S_1/2 -> 1s0.2p1.2P_1/2` |

Example reproduction command for the Ne IX comparison:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_test_run/xstar_ne9_triplet_lines.csv \
  --ion "Ne IX" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_ne9_triplet_wavelength.csv \
  --out-json compare_ne9_triplet_wavelength.json \
  --print-summary
```

Example reproduction command for the Ne X comparison:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_test_run/xstar_ne10_lya_lines.csv \
  --ion "Ne X" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_ne10_lya_wavelength.csv \
  --out-json compare_ne10_lya_wavelength.json \
  --print-summary
```


## Mg, Si, and Fe Stage-5 wavelength validation

The Mg/Si/Fe Stage-5 validation targets are now included as reproducible XSTAR run recipes and saved comparison artifacts:

```text
Mg XI  He-like triplet region: 9.0--9.4 Angstrom
Mg XII Ly-alpha region:        8.35--8.50 Angstrom
Si XIII He-like triplet region: 6.55--6.80 Angstrom
Si XIV Ly-alpha region:        6.10--6.25 Angstrom
Fe XXV K-alpha region:         1.83--1.88 Angstrom
Fe XXVI Ly-alpha region:       1.76--1.80 Angstrom
```

For each ion, the completed workflow was:

1. Run the documented direct-XSTAR command in a clean `xstar_runs/<model>/` directory.
2. Save `xout_lines1.fits` under `xstar_test_run/<model>/`.
3. Convert the selected line region to CSV with `python -m xstar_atomic.xstar_outputs`.
4. Compare with `examples/08_compare_xstar_outputs.py` in `--mode wavelength`.
5. Save the comparison CSV/JSON outputs under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.

These Mg/Si/Fe comparisons are now part of the validation archive. The wavelength mode validates line identification and wavelength decoding; XSTAR `emit_outward` remains a model-output column and is not directly normalized to local emissivity coefficients.

Validated Mg/Si/Fe wavelength results included in this release:

```text
Mg XI   5/5 matched, max |Delta lambda| = 4.52e-6 Angstrom
Mg XII  2/2 matched, max |Delta lambda| = 1.96e-6 Angstrom
Si XIII 5/5 matched, max |Delta lambda| = 3.51e-6 Angstrom
Si XIV  2/2 matched, max |Delta lambda| = 3.89e-6 Angstrom
Fe XXV  4/4 matched, max |Delta lambda| = 4.10e-6 Angstrom
Fe XXVI 2/2 matched, max |Delta lambda| = 3.55e-6 Angstrom
```

## How to reproduce from XSTAR outputs

1. Run XSTAR in a separate directory for each model.
2. Convert `xout_lines1.fits` to CSV:

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xout_lines1.fits \
  --out-csv xstar_lines.csv \
  --print-summary
```

3. Compare selected lines:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  /path/to/atdb.fits \
  xstar_lines.csv \
  --ion "O VIII" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_lines.csv \
  --out-json compare_lines.json
```


### O VII type-69 mode comparison (v0.2.81)

`examples/30_o7_density_grid_type69_mode_compare.py` runs the density-dependent O VII source-fit grid twice: once with the original type-69 handling (`include`) and once with the diagnostic/experimental `suppress-resonance` mode.  It merges the two grid outputs into `o7_density_grid_type69_mode_compare.csv`, including density, XSTAR R/G targets, include-mode R/G and reachability, suppress-resonance R/G and reachability, mismatch-improvement factors, source-weight L1 changes, and top fitted source levels.

The `suppress-resonance` mode suppresses type-69 excitation from the ground level into the He-like resonance upper level while preserving de-excitation.  For the O VII benchmark this corresponds to record 22490 (`1s2.1S_0 -> 1s.2p 1P_1`).  This mode is diagnostic/experimental: it is validated for the O VII high-density benchmark and should not be treated as a general physical default.

#### O VII high-density benchmark result snapshot (v0.2.82)

The v0.2.81 comparison output is now packaged as a reference validation snapshot under `examples/reference_outputs/` and `docs/validation/xstar_outputs/`:

```text
o7_density_grid_type69_mode_compare.csv
o7_density_grid_type69_mode_compare_summary.json
```

The snapshot records the side-by-side result for the density-specific XSTAR grid.  In the default `include` mode, all rows through `ne=1e10 cm^-3` remain reachable, but the `ne=1e12 cm^-3` row fails with approximately `R/G = 0.0378 / 3.202`.  In the diagnostic/experimental `suppress-resonance` mode, the high-density row becomes reachable with approximately `R/G = 0.08307 / 4.5197`, matching the XSTAR target `R/G = 0.083064 / 4.51966`.

This is a benchmark validation result for O VII only.  The `suppress-resonance` option should remain explicitly diagnostic/experimental until tested against additional He-like ions, temperatures, and full XSTAR model configurations.


Example command:

```bash
PYTHONPATH=src python examples/30_o7_density_grid_type69_mode_compare.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_density_grid_type69_mode_compare \
  --print-summary
```
