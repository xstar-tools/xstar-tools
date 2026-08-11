# zone-python legacy console diagnostics cleanup (0.6.80.1)

`0.6.80.1` is a science-neutral console-output hotfix on top of `0.6.80`.
Normal public `zone-python` execution suppresses six historical parity-campaign
`V...` markers emitted by the modular C++ kernels. The scientific calculations,
FITS products, STEP output, production provenance, C API ABI `60487`, and
production-zone ABI `6048110` are unchanged.

The suppression boundary is `XSTAR_SUPPRESS_LEGACY_CONSOLE_DIAGNOSTICS=1`,
installed automatically only for normal public `zone-python` execution. The
native `zone-cpp`, `zone-all`, and `xstar-cpp` modes retain their prior console
behavior. Developers can restore the old `zone-python` markers explicitly with:

```bash
export XSTAR_SUPPRESS_LEGACY_CONSOLE_DIAGNOSTICS=0
```

The six suppressed normal-output markers are:

- `V064896_TYPE50_MODE`
- `V048746255172582_PATCH520144_CALC_EMIS_REVISIT_SOURCE_SEQUENCE`
- `V048746255172582_PATCH520144_TYPE53_SELECTED_REVISIT_SELECTED`
- `V048746255172582_PATCH520144_TYPE53_SELECTED_REVISIT_PUBLISHED`
- `V048746255172582_PATCH520144_TYPE49_SELECTED_REVISIT_SELECTED`
- `V048746255172582_PATCH520144_TYPE49_SELECTED_REVISIT_PUBLISHED`

No other diagnostic switch or historical qualification path is changed.
