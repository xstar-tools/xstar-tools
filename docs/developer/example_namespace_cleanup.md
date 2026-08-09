# Active example cleanup (0.6.63)

The active `examples/` directory now contains only examples for the stable public `xstar_tools` productization surface.

The former numbered example suite was created during the `xstar_atomic` and source-parity development campaign. Those scripts are valuable historical evidence, but most are not runnable against the current package namespace and many depend on other retired example scripts. They are preserved byte-for-byte under:

```text
historical/examples/legacy_pre_productization/
```

The 35 tests whose sole purpose was to exercise those legacy scripts are preserved under:

```text
historical/tests/legacy_examples/
```

Current active examples are:

```text
examples/01_backend_capabilities.py
examples/02_run_public_mode.py
examples/03_run_xstar_cpp.sh
examples/04_run_public_benchmark.sh
examples/README.md
```

`examples/reference_outputs/` remains active because current characterization tests and documentation still consume those validation CSV/JSON fixtures.

The cleanup is enforced by `tools/qualification/check_example_history_cleanup.py` and `qualification/example_history_cleanup_0_6_63.json`.
