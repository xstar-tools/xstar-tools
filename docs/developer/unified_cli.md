# Unified CLI contract

The primary application CLI is:

```text
xstar-tools <command>
```

It is an orchestration/productization surface; it does not redefine XSTAR science.

## User commands

```text
xstar-tools run
xstar-tools inspect
xstar-tools data
xstar-tools backends
xstar-tools compare
xstar-tools doctor
xstar-tools version
```

`xstar-tools run INPUT --mode MODE --data-dir DATA --output-dir OUT` constructs `XStarConfig` and calls the same `run_xstar(config)` public API used by Python applications. CLI and Python therefore share input validation, backend mapping, output policy, environment isolation, result paths, and provenance.

The stable mode names are `pure-python`, `zone-python`, `zone-cpp`, `zone-all`, and `xstar-cpp`.

## Development and qualification namespaces

```text
xstar-tools dev legacy-run ...
xstar-tools dev benchmark ...

xstar-tools qualify benchmark ...
xstar-tools qualify original-parity ...
xstar-tools qualify cpp-parity ...
xstar-tools qualify reference ...
```

The older top-level `xstar-tools benchmark ...` alias is retained as a deprecated compatibility route.

## Logging

A normal `run` can expose human-readable progress, Python logging, JSONL events via `--json-log`, and a final result document via `--summary-json`. Qualification marker strings are not required for normal application use.

The complete user-facing command reference, including all installed compatibility/specialist console scripts, is {doc}`../user/cli`.
