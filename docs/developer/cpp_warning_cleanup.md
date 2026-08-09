# C++ warning-clean build boundary

Distribution `0.6.58` makes the active native build warning-clean under the
Makefile's `-Wall -Wextra -Wpedantic` policy without suppressing warning classes.

The touched sources are:

- `opacity_kernels.cpp`: compile-time-unused Type50 experiment/template values are marked `[[maybe_unused]]`.
- `fixed_state_engine.cpp`: nonzero-bin bookkeeping is written with explicit braces and statements.
- `xstar_atdb_runtime.cpp`: loop/throw and environment-candidate checks use explicit independent control flow; one retained helper is marked `[[maybe_unused]]`.
- `xstar_standalone.cpp`: unread locals are removed; retained legacy/diagnostic helpers and unused parameters are marked `[[maybe_unused]]`.
- `xstar_science_fits.cpp`: retained but currently uncalled publication/oracle helpers and unused parameters are marked `[[maybe_unused]]`.
- `xstar_step_log.cpp`: an unread scratch value is removed and retained uncalled helpers are marked `[[maybe_unused]]`.

No warning-suppression compiler flags are added.  The exact before/after hashes
and science-baseline links live in `qualification/cpp_warning_cleanup_0_6_58.json`.

Run the fast structural gate with:

```bash
python tools/qualification/check_cpp_warning_cleanup.py
```

Run the full compiler gate with:

```bash
python tools/qualification/check_cpp_warning_cleanup.py --compile
```
