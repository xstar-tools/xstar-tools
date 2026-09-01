# 0.6.88.4 — PORTABLE_PROCESS_LAYER

## Scope

This release is an infrastructure-only portability step on top of formally accepted `0.6.88.3.2`.
It introduces `src/xstar_tools/xstar/cpp/xstar_process.hpp` and routes the following native operations through it:

- `fork`
- `execv` / `execvp`
- `waitpid`
- `kill`
- `getpid`
- `setenv` / `unsetenv`

The Linux/macOS branch delegates directly to the same POSIX calls, preserving arguments, `errno`, wait-status decoding, termination signals, environment overwrite behavior, and orchestration order. Windows process creation/wait/termination is deliberately left as an explicit `ENOSYS` backend for the later MinGW native-build release; `_getpid` and `_putenv_s` provide the already-portable Windows process-id/environment pieces.

## Scientific boundary

No XSTAR arithmetic, controller decision, traversal/contribution/accumulation order, cutoff, row/record membership, publication rule, output schema, or public ABI is intentionally changed. Environment-call edits in science-adjacent translation units are mechanical substitutions only.

## Linux-first acceptance

Before any Windows backend is promoted, qualification requires:

1. named POSIX process/environment calls occur only inside `xstar_process.hpp`;
2. predecessor sources normalize exactly after reversing only the mechanical abstraction substitutions and package-version changes;
3. Linux `make -Bn all` command lines remain equivalent after package-version normalization;
4. a real Linux `make all` succeeds;
5. `make test` succeeds;
6. package/science/API ABI version reporting remains correct.
