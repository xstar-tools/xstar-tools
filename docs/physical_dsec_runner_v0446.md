# Physical `dsec` runner (v0.4.46)

`examples/119_validate_xstar_dsec_complete.py` is the turnkey bounded runner
that was intentionally absent from v0.4.45. It executes the real translated
`calc_hmc_all` for every `dsec` trial and retains the final fixed-state object
for the complete acceptance gate.

The selected XSTAR trajectory supplies only the initial/control state and the
comparison oracle. The Python calculation does not read XSTAR temperatures,
residuals, rates, or populations during iteration.

## Preparation-only check

```bash
PYTHONPATH=src python examples/119_validate_xstar_dsec_complete.py \
  --atdb /media/linux/mhd/xstar/xstar/data/atdb.fits \
  --pointer-cache xstar_atomic_database_port_v041/xstar_atomic_derived_pointers.npz \
  --live-rate-grid-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_live_rate_grid_probe.csv \
  --live-rate-grid-state last \
  --escape-npz xstar_o7_escape_state_v045.npz \
  --xstar-calc-hmc-probe-dir xstar_runs/helike_type69/o7_ne1e8_all_elements_v0443_complete \
  --xstar-calc-hmc-call-id 73 \
  --oxygen-call73-regression-dir oxygen_call73_v0434_acceptance/xstar_o_calc_hmc_all_fixed_state_v0434 \
  --xstar-dsec-trajectory xstar_runs/helike_type69/o7_ne1e8_dsec_v0445/xstar_dsec_trajectory_probe.csv \
  --xstar-dsec-call-id 1 \
  --coheat-data /media/linux/mhd/xstar/xstar/data/coheat.dat \
  --initial-population-policy require-all \
  --prepare-only \
  --out-dir xstar_dsec_complete_v0446_prepare \
  --print-summary
```

## Physical run

Remove `--prepare-only` and use a new output directory:

```bash
PYTHONPATH=src python examples/119_validate_xstar_dsec_complete.py \
  --atdb /media/linux/mhd/xstar/xstar/data/atdb.fits \
  --pointer-cache xstar_atomic_database_port_v041/xstar_atomic_derived_pointers.npz \
  --live-rate-grid-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_live_rate_grid_probe.csv \
  --live-rate-grid-state last \
  --escape-npz xstar_o7_escape_state_v045.npz \
  --xstar-calc-hmc-probe-dir xstar_runs/helike_type69/o7_ne1e8_all_elements_v0443_complete \
  --xstar-calc-hmc-call-id 73 \
  --oxygen-call73-regression-dir oxygen_call73_v0434_acceptance/xstar_o_calc_hmc_all_fixed_state_v0434 \
  --xstar-dsec-trajectory xstar_runs/helike_type69/o7_ne1e8_dsec_v0445/xstar_dsec_trajectory_probe.csv \
  --xstar-dsec-call-id 1 \
  --coheat-data /media/linux/mhd/xstar/xstar/data/coheat.dat \
  --initial-population-policy require-all \
  --runtime-rtol 5.0e-12 \
  --runtime-atol 1.0e-30 \
  --residual-rtol 5.0e-3 \
  --thermal-residual-atol 1.0e-8 \
  --charge-residual-atol 1.0e-10 \
  --out-dir xstar_dsec_complete_v0446 \
  --print-summary
```

By default the runner adopts `T4`, `xee`, `xpx`, `nlim`, and `tinf` from the
selected XSTAR `begin` row. `--dsec-runtime-policy check` can be used when the
same values are also supplied explicitly.

After the internal `dsec` trajectory completes, the runner performs the additional `calc_hmc_all` call made by `xstarcalc.f90`. The frozen call-73 fixed-state oracle is compared with this post-`dsec` result, while the recorded `dsec` call count and trajectory remain unchanged.

The final gate is:

```text
v0445_bounded_dsec_acceptance_ready=True
```

A false gate is a diagnostic result, not a packaging failure. Inspect
`xstar_dsec_trajectory_parity.csv` to identify the first event and quantity
that diverge.
