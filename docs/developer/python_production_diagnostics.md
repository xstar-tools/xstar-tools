# Production diagnostics policy for Python execution modes

## Scope

`0.6.80` separates normal public output from the historical diagnostics used to
qualify and debug the source-faithful Python implementation.

The scientific boundary is unchanged:

- accepted Python science revision: `0.6.48.12.3.45.3.3.8`;
- frozen C++ baseline: `0.6.48.12.3.44`;
- C API ABI: `60487`;
- production-zone ABI: `6048110`.

## Public production behavior

Stable `run_xstar(...)`, `XStarConfig`, and `xstar-tools run` executions in
`pure-python` and `zone-python` keep the accepted internal
`diagnostics_mode="full"` computational/orchestration path, but diagnostic file
capture/emission is disabled by default.

Normal production runs therefore do not create:

- `xstar_tools_continuum_diagnostics_summary.json`;
- `xstar_tools_phase_snapshots.csv`;
- `xstar_tools_phase_snapshots.jsonl`;
- `xstar_tools_ucalc_continuum_side_effects.csv`;
- `xstar_tools_ucalc_continuum_side_effects.jsonl`;
- `radial_spectrum_diagnostics_v0500/` (or the older internal v0499 spelling).

`runner_summary.json` contains stable execution/data/backend provenance rather
than serializing the historical Mg/DSEC/shadow/forensic attribution maps.

This is intentionally **not** implemented by switching to
`diagnostics_mode="none"`.  That expert mode has independent retention/ownership
semantics inside the source-faithful solver and requires separate scientific
qualification before it can become a production optimization.

## Explicit debugging

Development/qualification diagnostics remain available through the existing
advanced interface:

```bash
xstar-tools dev legacy-run ... --diagnostics full
```

The compatibility Python interface can also explicitly request both output
surfaces:

```python
run_xstar(
    mode="pure-python",
    ...,
    write_diagnostic_files=True,
    include_debug_provenance=True,
)
```

These controls are deliberately not promoted into `XStarConfig`; ordinary users
should receive production outputs by default.

## 0.6.75 three-model benchmark review

The user-supplied `benchmark_0675_python` archive contains successful
`pure-python` and `zone-python` runs for:

- `helike_type69/ca19_xi2_ne1`;
- `helike_type69/mg11_ne1e8`;
- `helike_type69/o7_ne1e10`.

The six benchmark subprocesses completed successfully.  Direct comparison of
the two Python modes gives:

| Model | STEP science | FITS material result |
|---|---|---|
| Ca XIX `ca19_xi2_ne1` | ACCEPT | 8 products exact; `xout_spect1` material NL1 about `4.03e-17` |
| Mg XI `mg11_ne1e8` | ACCEPT | all product schemas/identities match; worst material NL1 about `2.45616e-4` (`0.0246%`) in `xout_abund1` |
| O VII `o7_ne1e10` | ACCEPT | all 9 FITS table payloads numerically/structurally identical |

These results show no material `pure-python` versus `zone-python` scientific
problem under the frozen `<1%` policy.  The uploaded archive does not contain
the canonical `original_xstar.tar.gz` Fortran product reference, so this review
does not claim a new independent Fortran comparison.
