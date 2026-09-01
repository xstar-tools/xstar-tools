# macOS native build link closure — 0.6.88.3.2

## Scope

This is a narrow host-discovered portability closure on top of the historical `0.6.88.3.1` HOST REJECT. The formally accepted Linux/science baseline remains `0.6.88.2.2`. The Apple-only Type-77 exact-value fix from `.88.3.1` is carried forward byte-for-byte in `local_zone_engine.cpp`.

## Production build closure

`local_zone_engine.cpp` directly calls `xstar_opacity_apply_line_profile_v1`, whose definition is in `libxstar_opacity`. Darwin rejected `.88.3.1` because `libxstar_local_zone.dylib` did not name that provider on its link line.

For `PLATFORM=macos` only, the Makefile now adds `-lxstar_opacity` to the `libxstar_local_zone.dylib` link. The target also declares `$(OPACITY_TARGET)` as an explicit prerequisite. Linux leaves `LOCAL_ZONE_LINK_LIBS` set to the historical engine/emissivity pair so the accepted Linux link command remains equivalent after version normalization.

No scientific C/C++ source is changed relative to `.88.3.1`. No ABI number, controller decision, traversal order, contribution order, accumulation order, cutoff, publication rule, or output schema is changed.

## Qualification interpreter closure

The `.88.3.1` checker re-resolved a literal `python3`, which selected Homebrew Python 3.14 on both macOS runners even though the workflow had installed `pytest` into the `actions/setup-python` Python 3.12 environment. `.88.3.2` uses `sys.executable` when the host runner launches the source checker and when the checker launches focused pytest. The workflow uses `python -m pip` and `python ...runner.py`, keeping installation and qualification on the same setup-python interpreter.

## Acceptance

Formal acceptance still requires native host `ACCEPT` on both `macos-15` and `macos-15-intel`, including build, Mach-O/install-name/rpath/dependency inspection, sibling/plugin loading, package versions, and the full macOS regression suite.
