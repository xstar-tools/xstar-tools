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
  xstar_o_ne_xi3_lines.csv
  xstar_o8_lya_lines.csv
  xstar_o7_triplet_lines.csv
```

The README in `xstar_test_run/` records the exact direct-XSTAR commands used
for the O VIII/Ne IX high-ionization run, the O VII triplet run, and the
high-density O VII triplet run. It also records the `xstar_atomic.xstar_outputs`
commands used to convert each `xout_lines1.fits` file into CSV.

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


## Planned Ne IX / Ne X Stage-5 comparison runs

Stage 5 extends the existing O VIII and O VII wavelength comparisons to neon.
The package README under `xstar_test_run/README.md` now includes two direct-XSTAR
commands for this purpose:

- `xstar_atomic_ne_xi25`: a neon-only, moderately high-ionization run intended
  for Ne IX He-like triplet/near-triplet validation.
- `xstar_atomic_ne_xi35`: a neon-only, higher-ionization run intended for
  Ne X Ly-alpha validation.

After running XSTAR, convert the line-output FITS files and compare wavelengths:

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/ne_xi25/xout_lines1.fits \
  --ion "Ne IX" \
  --wavelength-min 13.3 \
  --wavelength-max 13.8 \
  --out-csv xstar_ne9_triplet_lines.csv \
  --print-summary \
  --print-rows

PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_ne9_triplet_lines.csv \
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

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/ne_xi35/xout_lines1.fits \
  --ion "Ne X" \
  --wavelength-min 12.0 \
  --wavelength-max 12.3 \
  --out-csv xstar_ne10_lya_lines.csv \
  --print-summary \
  --print-rows

PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_ne10_lya_lines.csv \
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

These commands define the next Stage-5 validation products. Once the XSTAR
outputs are generated, the resulting FITS, converted CSV, and comparison
CSV/JSON files should be saved and documented in the same way as the existing
O VIII and O VII examples.

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
