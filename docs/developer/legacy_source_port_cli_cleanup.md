# Legacy source-port CLI cleanup

Starting with distribution version `0.6.65`, the active top-level package no longer ships the one-off source-port attribution, DSEC replay/validation, and probe-generation commands that were used during the parity campaign.

Those commands had no active source caller, current test, current tool, or current documentation surface. Their only non-historical reachability was through legacy console-script aliases in `pyproject.toml`. The source files are preserved byte-for-byte in the full history archive under:

```text
historical/python/source_port_cli_campaign/
```

The stable public execution path is not part of this retirement. `src/xstar_tools/source_port_physical_runner_cli.py` remains active because `xstar-tools run` and the public execution-mode characterization layer still use it.

For new work, prefer the stable surfaces:

```text
xstar-tools run --mode pure-python|zone-python|zone-cpp|zone-all|xstar-cpp
xstar-tools backends
xstar-tools doctor
xstar-tools benchmark ...
```

Historical qualification reports may continue to mention the retired commands. Those names are provenance, not supported active interfaces.

## Retired command aliases

The cleanup removes 37 console aliases including the old `xstar-tools-port-*`, `xstar-tools-validate-dsec-*`, and probe preparation/analysis commands. Historical scripts that require them should be run from the archived historical source tree, not from a normal installation.
