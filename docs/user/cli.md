# Command-line interfaces

The preferred general entry point is:

```text
xstar-tools <command>
```

The preferred native XSTAR/XSTAR2XSPEC entry points are `xstar-cpp`, `xstar-xspec-initable`, `xstar-xspec-table`, and `xstar-xspec`. True MPI is built explicitly as `xstar-xspec-mpi` and is not part of the ordinary install contract.

## Unified `xstar-tools` commands

```text
xstar-tools run
xstar-tools inspect
xstar-tools data
xstar-tools backends
xstar-tools compare
xstar-tools doctor
xstar-tools version
```

### Run one model

```bash
xstar-tools run xstar.par \
  --mode zone-cpp \
  --data-dir /path/to/xstar/data \
  --output-dir run1
```

`run` accepts these options:

| Option | Meaning |
|---|---|
| `INPUT` | XSTAR `.par`, `run_xstar.sh`, or `.cmd` input |
| `--mode` | `pure-python`, `zone-python`, `zone-cpp`, `zone-all`, or `xstar-cpp` |
| `--data-dir DIR` | directory containing `atdb.fits` and `coheat.dat` |
| `--output-dir DIR` | output directory, default `run1` |
| `--threads N` | run-scoped thread count |
| `--overwrite` | replace a non-empty output directory |
| `--no-progress` | suppress human-readable science progress |
| `--log-level LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `--json-log FILE` | write JSONL run events/provenance |
| `--summary-json FILE` | write the final `XStarResult` as JSON |
| `--cache-dir DIR` | explicit cache location |
| `--no-cache` | disable cache use |
| `--rebuild-cache` | rebuild cache data |
| `--no-reproducible` | disable reproducible-run intent |

### Runtime/status commands

```bash
xstar-tools backends
xstar-tools doctor --require zone-cpp --data-dir /path/to/xstar/data
xstar-tools version --json
```

`xstar-tools data` delegates to the explicit atomic-data configurator:

```bash
xstar-tools data --show
xstar-tools data --set-path /path/to/atdb.fits
```

Normal model execution never downloads scientific data implicitly. `xstar-tools data --destination ... --yes` is an explicit download action.

## Installed console scripts

The distribution installs 30 console scripts. Use the primary commands above unless a specialist or compatibility interface is specifically needed.

### Primary public commands

| Command | Purpose |
|---|---|
| `xstar-tools` | unified user/developer command tree |
| `xstar-cpp` | one standalone native XSTAR calculation |
| `xstar-xspec-initable` | plan an XSTAR2XSPEC grid |
| `xstar-xspec-table` | assemble final XSPEC tables from spectra |
| `xstar-xspec` | complete serial/local-process XSTAR2XSPEC workflow |

### Specialist atomic-data/output utilities

These are retained direct tools for focused work: `xstar-tools-inspect`, `xstar-tools-hierarchy`, `xstar-tools-lines`, `xstar-tools-photoionization`, `xstar-tools-collisions`, `xstar-tools-recombination`, `xstar-tools-emissivity`, `xstar-tools-solver`, `xstar-tools-xstar-outputs`, and `xstar-tools-download-data`.

### Compatibility/older convenience frontends

The following remain installed for compatibility with earlier xstar-tools workflows: `xstar-tools-run-xstar`, `xstar-tools-inspect-atdb`, `xstar-tools-xstinitable`, `xstar-tools-xstar2table`, `xstar-tools-xstar2xspec`, `xstar-tools-mpixstar`, and `xstar-tools-plan-xstar-run`. New XSTAR2XSPEC commands should prefer the native names. `xstar-tools-mpixstar --np N` is a local-process compatibility wrapper; true MPI uses `mpirun -np N xstar-xspec-mpi`.

### Development/qualification-oriented commands

`xstar-tools-benchmark`, `xstar-tools-run-python`, `xstar-tools-original-parity-gate`, `xstar-tools-cpp-parity-gate`, `xstar-tools-qualification`, `xstar-tools-validate-collisions`, `xstar-tools-export`, and `xstar-tools-export-superwind` are retained for benchmark, qualification, validation, export, or advanced development workflows rather than as the default user front door.

The unified equivalents for active development/qualification work are:

```text
xstar-tools dev ...
xstar-tools qualify ...
```
