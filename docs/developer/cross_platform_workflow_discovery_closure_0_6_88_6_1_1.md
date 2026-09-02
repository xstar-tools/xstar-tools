# 0.6.88.6.1.1 — CROSS_PLATFORM_WORKFLOW_DISCOVERY_CLOSURE

`0.6.88.6.1.1` removes the filename dependency from the cross-platform source qualification checker.

The predecessor `0.6.88.6.1` completed all four native host builds and all fixed-state equivalence checks successfully, but every host was formally rejected because the source checker attempted to read `.github/workflows/cross-platform-qualification.yml` directly. The active GitHub Actions workflow used another filename, so source qualification terminated with `FileNotFoundError`.

The new checker enumerates both `*.yml` and `*.yaml` below `.github/workflows`, then identifies the qualifying workflow by required content: Linux, macOS arm64, macOS Intel, Windows UCRT64, and the current unified host-runner invocation. Missing or non-matching workflows become ordinary qualification gate failures rather than Python exceptions.

No scientific implementation, fixed-state comparator, tolerance, reference payload, ABI, process, loader, Python-backend, or scheduler behavior changes in this closure. Windows MPI remains out of scope.
