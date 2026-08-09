# Unified CLI contract — 0.6.68

Milestone 5 consolidates normal command-line use behind one executable:

```text
xstar-tools <command>
```

This is a productization layer. It does not implement or modify XSTAR science.
The accepted science revision remains `0.6.48.12.3.45.3.3.8`; the frozen C++
baseline remains `0.6.48.12.3.44`; the C API ABI remains `60487`; and the
production-zone ABI remains `6048110`.

## User-facing command tree

```text
xstar-tools run
xstar-tools inspect
xstar-tools data
xstar-tools backends
xstar-tools compare
xstar-tools doctor
xstar-tools version
```

`xstar-tools run INPUT --mode MODE --data-dir DATA --output-dir OUT` is the
normal execution interface. `INPUT` may be a canonical `.par` file or a
source-faithful `run_xstar.sh`/`.cmd` input.

The stable modes remain:

```text
pure-python
zone-python
zone-cpp
zone-all
xstar-cpp
```

## One orchestration layer

The CLI run path does not call the historical physical-runner CLI. It performs
exactly these product-layer operations:

1. `XStarConfig.from_par_file(...)`;
2. `run_xstar(config)`;
3. render the returned `XStarResult` for the terminal/JSON outputs.

Therefore CLI and Python applications share configuration validation, backend
mapping, output-directory policy, run-scoped environment handling, product
paths, and provenance. Scientific control remains in the already-qualified
execution layer below that API.

The historical source-port CLI remains reachable as:

```text
xstar-tools dev legacy-run ...
```

and through its existing console script during the deprecation cycle.

## Other public commands

`xstar-tools inspect` delegates to the existing packed-ATDB inspector.

`xstar-tools data` delegates to the existing data locator/configurator. Normal
model execution never downloads scientific data as a side effect.

`xstar-tools compare` exposes the accepted public-suite Fortran/C++ comparison
path, including the 0.6.67 Option-24 Fortran stale-local semantic quarantine.

`xstar-tools backends` and `xstar-tools doctor` retain the Milestone-3 backend
capability contract. `doctor --data-dir DIR` additionally validates local
scientific data.

`xstar-tools version` reports package version, science revision, C API ABI, and
production-zone ABI as separate values.

## Development and qualification namespaces

New structured namespaces are:

```text
xstar-tools dev legacy-run ...
xstar-tools dev benchmark ...

xstar-tools qualify benchmark ...
xstar-tools qualify original-parity ...
xstar-tools qualify cpp-parity ...
xstar-tools qualify reference ...
```

The old top-level `xstar-tools benchmark ...` alias remains available for one
deprecation cycle and emits a deprecation message. Existing legacy
`[project.scripts]` console commands remain installed in 0.6.68; they are not
removed by this milestone.

## Logging contract

A normal run has three complementary surfaces:

- human-readable scientific progress, controlled by `--no-progress`;
- standard Python `logging`, controlled by `--log-level`;
- optional structured JSONL events/provenance through `--json-log FILE`.

The JSONL schema is `xstar-tools-cli-event-v1`. At minimum a successful run
contains `run_started` and `run_completed`; a failed run contains
`run_started` and `run_failed`. The completion event embeds final provenance
from `XStarResult`.

For a single JSON result document rather than an event stream, use
`--summary-json FILE`.

Qualification marker strings remain in qualification tools. Normal `run`
users do not need them.

## Compatibility and freeze statement

Relative to 0.6.67, only these active source files change:

```text
src/xstar_tools/cli/main.py
src/xstar_tools/inspect.py
```

The `inspect.py` change only allows its existing parser to receive an explicit
`argv` list so it can be delegated by the unified CLI. The entire
`src/xstar_tools/xstar/` tree is byte-identical to 0.6.67 under the Milestone-5
source-tree hash used by `check_unified_cli.py`.
