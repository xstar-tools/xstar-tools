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

## XSTAR2XSPEC products

A successful native `xstar-xspec` or `xstar-xspec-mpi` run publishes:

```text
xout_ain.fits
xout_aout.fits
xout_mtable.fits
xout_etable.fits
xout_step.log
xstinitable.lis
xstinitable.fits
```

Per-job products remain under `xstar2xspec-work/jobs/NNNNNN/` by default. Each successfully completed job includes `xstar-cpp.success`; failed/partial products are deliberately retained without that success marker.

Local-process orchestration writes `xstar2xspec.log` and `xstar2xspec_scheduler.log`. True MPI writes `xstar2xspec-mpi.log`, `xstar2xspec-mpi-scheduler.log`, and one `xstar2xspec-mpi-rank-NNNNNN.log` per rank.
