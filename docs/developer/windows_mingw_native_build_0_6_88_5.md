# 0.6.88.5 — WINDOWS_MINGW_NATIVE_BUILD

## Scope

This release branches from formally accepted `0.6.88.4.2` and implements the first native Windows build/runtime target with **MSYS2 UCRT64 + MinGW-w64 GCC**. It does not reopen XSTAR scientific arithmetic, controller choices, traversal/contribution/accumulation order, cutoffs, publication semantics, output schemas, or frozen ABI values.

The supported Windows contract is deliberately native MinGW/UCRT64, not MSVC/CMake and not the MSYS POSIX runtime. Windows MPI remains out of scope.

## Native process layer

`xstar_process.hpp` retains the accepted POSIX implementation unchanged for Linux/macOS. Native Windows orchestration uses:

- `CreateProcessW` for child creation;
- explicit Windows command-line quoting and UTF-8 → UTF-16 conversion;
- inheritable Win32 file handles for child stdout/stderr redirection, with an inheritable `NUL` stdin fallback for non-interactive CI hosts;
- `WaitForSingleObject` plus a small registered-process wait-any loop for scheduler completion;
- `TerminateProcess` for graceful/forced scheduler cleanup exit codes;
- `_getpid` and `_putenv_s` for PID/environment operations;
- `_execv`/`_execvp` only for the existing xstar-cpp process-image-replacement passthrough.

There is no attempt to emulate POSIX `fork()` on Windows. `fork_process()` remains fail-closed with `ENOSYS`; Windows call sites use `spawn_program()` explicitly.

## PE/DLL build contract

For `PLATFORM=windows`:

- shared libraries are `libxstar_*.dll`;
- executables use `.exe`;
- every DLL build emits a matching `libxstar_*.dll.a` import library;
- MinGW auto-export is enabled for the existing C ABI definitions without changing Linux/macOS visibility behavior;
- no ELF/Mach-O rpath flags are emitted;
- `xstar_platform::executable_filename()` supplies `.exe` for sibling discovery;
- `libxstar_local_zone.dll` links directly to opacity, matching the already-required Darwin direct dependency;
- Windows backend/Python bridge export declarations no longer misuse the `libxstar_api` import/export macro;
- Windows MPI remains an explicit unsupported target.

## Acceptance strategy

Linux remains the preservation oracle. Before Windows host promotion:

1. Linux `make -Bn all` must be command-equivalent to `0.6.88.4.2` after package-version normalization.
2. Full Linux build/regression and fixed-state outputs must remain accepted.
3. Source qualification must show that scientific `.cpp` translation units are unchanged.
4. GitHub Actions `windows-latest` under MSYS2 UCRT64 must build all native DLL/executable targets.
5. PE/import-library/export checks, sibling/plugin loading, `xstar-cpp`/`xstar-xspec` versions, the full regression suite, a direct Win32 process/environment smoke, and a synthetic two-process `xstar-xspec` scheduler smoke must all pass.

The Windows synthetic XSTAR2XSPEC smoke tests orchestration only; the normal fixed-state regression remains the scientific/runtime regression gate.
