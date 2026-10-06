# `xstar-cpp` native executable contract — 0.6.69

`xstar-cpp` is the first-class, Python-free command-line frontend for the frozen
native XSTAR production implementation.  It is a productization layer only; it
does not implement scientific algorithms.

## Normal use

```bash
xstar-cpp --input xstar.par --data-dir /path/to/xstar/data --output run1
```

A HEASoft/IRAF-style parameter file is read as
`name,type,mode,value,min,max,prompt`.  The value field is preserved as text and
written to the same JSON parameter envelope consumed by the qualified
`xstar_cpp run-production` path.  XSTAR-style `name=value` tokens can be used
instead of a `.par` file and command-line tokens override values read from the
file.

`--data-dir DIR` resolves `DIR/atdb.fits` and `DIR/coheat.dat`; explicit
`--atomic-db` and `--coheat` paths override those defaults.  The frontend does
not download scientific data.

## `xstar-cpp` extensions

The following are orchestration extensions, not canonical XSTAR parameters:

- `--json-summary FILE` — final machine-readable status/products summary;
- `--provenance FILE` — additional provenance JSON path;
- `--progress {none,text,json}` — frontend orchestration events;
- `--threads N` — run-scoped `OMP_NUM_THREADS`;
- `--profile FILE` — frontend wall-time/profile JSON;
- `--deterministic` — record reproducible-run intent in provenance;
- `--print-option N` — read-only extraction from the completed `xout_step.log`;
- `--parameters-out FILE` — retain the generated JSON parameter envelope. Without this option, the envelope is an ephemeral system-temporary orchestration file and is removed after native execution; it is never placed in the science output directory;
- `--abi` — print expected and runtime ABI identities.

`--print-option` never changes STEP generation.  It only reads a completed log.

## Scientific-control architecture

The frontend delegates to the sibling compatibility executable:

```text
xstar-cpp
  -> xstar_cpp run-production
       -> command_run_standalone_production()
```

The two Python-facing shared production modes use the same frozen operator:

```text
zone-all
  -> xstar_production_zone_run_all_v0648110()
       -> command_run_standalone_production()

zone-cpp
  -> xstar_production_zone_context_create_v0648110()
       -> worker -> command_run_standalone_production()
```

Thus the frontend, `zone-all`, and `zone-cpp` do not carry independent scientific
control implementations.

## ABI behavior

`xstar-cpp` links to `libxstar_api.so` and `libxstar_production_zone.so` for
runtime identity queries.  Before a scientific run it requires:

```text
C API ABI             60487
production-zone ABI   6048110
science revision      0.6.90.5.5
```

A mismatch fails before science with exit status `70` and a diagnostic naming
the expected and observed ABI.

Package version, science revision, C API ABI, and production-zone ABI are
separate identifiers.  A productization release does not change science or ABI.

## Qualification

The first-class native frontend was established during the earlier productization campaign. Current releases no longer ship its closed milestone checker; the active release boundary uses the compact parity-freeze/source-concordance gates plus the retained behavioral regression tests.

```bash
python tools/qualification/check_parity_freeze.py
python tools/qualification/check_source_concordance.py
```

The scientific cross-mode authority remains the accepted frozen qualification campaign; productization-only changes must not silently alter the standalone/production-zone scientific implementation.
