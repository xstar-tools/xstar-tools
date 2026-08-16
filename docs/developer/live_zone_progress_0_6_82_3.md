# 0.6.82.3 live XSTAR-style radial-zone progress

## Scope

Public `xstar-cpp --progress text` now streams an XSTAR-style row when each radial zone is accepted instead of waiting for the entire controller to return.  This observability surface is part of the broader `0.6.82.3` multi-element source-concordance release; the live-print mechanism itself is science-neutral.

The frontend exports `XSTAR_CPP_PROGRESS_MODE=text`.  The standalone process prints the normal XSTAR-style progress header before entering the quiet controller and prints one row from the already accepted boundary immediately after `production_zone_mark_complete`.

The row is written through `std::cerr` because normal production redirects `std::cout` to suppress historical qualification diagnostics.  The row is flushed immediately.  No printed quantity is written back into controller, transport, rate, matrix, opacity, emissivity, convergence, or product state.

When live text progress is active, the old post-controller full-table printer is skipped so physical zone rows are not duplicated.  Other progress modes retain their previous behavior.

## Host runner

`tools/qualification/run_multi_element_host_smoke_0_6_82_3.py` is version-locked to package `0.6.82.3` and uses a line-buffered `subprocess.Popen` tee with `stderr=STDOUT`.  Long broad-mixture runs therefore show each native progress line immediately while the same combined transcript is retained in `run_xstar_example_06823/host_smoke.log`.

The host runner is also the external end-to-end gate for the radius/Fe fixes described in `broad_multi_element_science_0_6_82_3.md`; local source qualification does not substitute for canonical-ATDB execution.
