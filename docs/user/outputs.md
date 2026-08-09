# Output products

`XStarProducts` provides typed paths for the principal products:

| Accessor | File |
|---|---|
| `abundances` | `xout_abund1.fits` |
| `lines` | `xout_lines1.fits` |
| `rrc` | `xout_rrc1.fits` |
| `continuum` | `xout_cont1.fits` |
| `spectrum` | `xout_spect1.fits` |
| `detail` | `xo01_detail.fits` |
| `detail_lines` | `xo01_detal2.fits` |
| `detail_rates` | `xo01_detal3.fits` |
| `detail_continuum` | `xo01_detal4.fits` |
| `step_log` | `xout_step.log` |

Example:

```python
result = run_xstar(config)
print(result.products.lines)
print(result.products.produced_fits)
print(result.step_log)
```

`XStarResult` also reports status, return code, runtime, timings, diagnostics, warnings, and provenance.
