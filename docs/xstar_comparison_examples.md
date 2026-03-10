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
