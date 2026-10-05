# `xstar-cpp`

`xstar-cpp` runs one native XSTAR calculation. It accepts an XSTAR parameter file or direct `key=value` parameters.

## With `xstar.par`

```bash
xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

The parameter file may also be positional:

```bash
xstar-cpp xstar.par --data-dir /path/to/xstar/data --output run_xstar
```

Trailing `key=value` values override values loaded from the file.

## Without a parameter file

```bash
xstar-cpp \
  --data-dir /path/to/xstar/data \
  --output-dir run_direct \
  spectrum=pow density=1e12 column=1e20 rlogxi=1 \
  temperature=100 pressure=0.03 npass=1 modelname=direct_example
```

Supply the full parameter contract required by the selected model when using direct values.

## Options

| Option | Meaning |
|---|---|
| `--input PATH` | HEASoft/IRAF-style `.par` file |
| `--data-dir DIR` | directory containing `atdb.fits` and `coheat.dat` |
| `--input-dir DIR` | source directory for fixed-name inputs such as `density.dat` |
| `--output DIR`, `--output-dir DIR` | output directory |
| `--atomic-db PATH` | explicit `atdb.fits` |
| `--coheat PATH` | explicit `coheat.dat` |
| `--json-summary FILE` | machine-readable run summary |
| `--provenance FILE` | additional provenance JSON |
| `--progress none|text|json` | progress format; default `text` |
| `--debug` | show internal version-tagged development/qualification diagnostics |
| `--threads N` | set `OMP_NUM_THREADS` for this model |
| `--profile FILE` | frontend wall-time/profile JSON |
| `--deterministic` | record reproducible-run intent in provenance |
| `--print-option N` | print the requested completed `xout_step.log` section |
| `--parameters-out PATH` | retain/write the generated parameter envelope |
| `--abi` | print compiled/runtime ABI identities |
| `--version` | print package/science/ABI versions |
| `--help`, `-h` | help |

`run-production --parameters parameters.json --output-dir DIR` is the low-level production-envelope entry point used internally by the frontend; ordinary users should prefer the parameter-file/direct-value forms above.

## Terminal output

With the default `--progress text`, `xstar-cpp` prints the FORTRAN-style pass header and accepted radial-zone rows, followed by `final print`, the spectral-publication messages, and total runtime. Internal version-tagged lines such as `V064895_...` are suppressed in ordinary runs.

Use `--debug` to restore the full diagnostic stream, or set `XSTAR_CPP_DEBUG=1` when invoking either `xstar-cpp` or the low-level `xstar_cpp run-production` executable. `--progress json` is an explicit machine-readable frontend mode and continues to emit JSON lifecycle events.

## Atomic-data discovery

Explicit paths have priority. If omitted, native discovery considers direct parameter/envelope paths, `XSTAR_ATOMIC_DB`/`XSTAR_ATDB_FITS`, `XSTAR_COHEAT`, `XSTAR_DATA`, `$HEADAS/refdata`, `$XSTAR_HOME/data`, executable/package-relative fallbacks, and the current directory as documented in {doc}`../user/atomic_data`.

## Threads versus processes

`xstar-cpp --threads N` controls thread-related environment for one model. `xstar-xspec --processes N` instead launches up to N independent `xstar-cpp` OS processes.
