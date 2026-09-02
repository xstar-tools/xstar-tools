# 0.6.88.6.1.2.1 — WINDOWS_GIT_PREFLIGHT_SHELL_CLOSURE

## Purpose

Close the Windows-only GitHub Actions orchestration failure in `0.6.88.6.1.2`. That candidate's Windows job never launched the host qualification because `git check-attr` was executed in the MSYS2 UCRT64 shell, where GitHub's native Windows Git executable was not on `PATH`.

## Scope

This is qualification/workflow-only apart from normal package-version metadata. Scientific arithmetic, traversal/order, fixed-state equivalence tolerances, loader/process implementations, Python backend behavior, XSTAR2XSPEC scheduling, public ABIs, and the Windows-MPI-out-of-scope policy are unchanged.

The Windows preflight runs **before MSYS2 setup** using native `pwsh`, where the Git installed by `actions/checkout` is available. It is an assertion rather than an informational command:

- `xout_step.log` must resolve to `text: unset`;
- `visited_records.csv` must resolve to `text: unset`;
- `xout_native_state.fits` must resolve to `binary: set`;
- nonzero `git check-attr` status is a hard failure.

After this preflight, the existing MSYS2 UCRT64 toolchain and `.6.1.2` host qualification contract run unchanged.

## Formal acceptance

`0.6.88.6.1.2.1` is **formally accepted** on the complete four-host matrix:

| Host | Architecture | Result |
|---|---|---|
| Linux GCC | x86_64 | ACCEPT |
| macOS Apple Clang | arm64 | ACCEPT |
| macOS Apple Clang | x86_64 | ACCEPT |
| Windows MSYS2 UCRT64 / MinGW-w64 GCC | AMD64 | ACCEPT |

Every host returned:

```text
WINDOWS_GIT_PREFLIGHT_SHELL_CLOSURE_06886121_HOST_RESULT=ACCEPT
```

The fixed-state results also confirmed the intended cross-platform contract: Linux/macOS Intel were canonical byte-exact; Windows FITS was byte-exact with text differing only by CRLF serialization; macOS arm64 was same-host deterministic and cross-platform equivalent with maximum observed relative difference `4.5635339780748665e-15` and maximum `39 ULP`.

Windows MPI remains out of scope.
