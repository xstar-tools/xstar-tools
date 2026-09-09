# `xstar-xspec`

`xstar-xspec` is the complete native serial/local-process XSTAR2XSPEC driver:

```text
xstar-xspec-initable -> bounded xstar-cpp grid -> loopcontrol gather -> xstar-xspec-table
```

## From `xstinitable.par`

Serial:

```bash
xstar-xspec --input xstinitable.par --output-dir run_serial --processes 1
```

Two simultaneous XSTAR processes:

```bash
xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_local2 \
  --processes 2
```

`--processes N` means independent **OS processes**, not C++ threads. `--workers N` and `-j N` are compatibility aliases. `-np` is reserved for MPI launchers.

## Direct grid parameters

`--input` is optional when the full `xstinitable` parameter set is supplied as trailing `key=value` values:

```bash
xstar-xspec --output-dir run_direct --processes 2 \
  rlogxityp=2 rlogxisof=0 rlogxi=5 rlogxinst=6 rlogxiint=0 \
  columntyp=2 columnsof=1e20 column=1e24 columnnst=9 columnint=1
```

Trailing values override `--input` values.

## Options

| Option | Meaning |
|---|---|
| `--input PATH` | `xstinitable.par` |
| `--data-dir DIR`, `-data-dir DIR` | explicit atomic-data directory |
| `--output-dir DIR`, `--output DIR` | final XSTAR2XSPEC output directory |
| `--processes N` | maximum simultaneous `xstar-cpp` OS processes |
| `--workers N`, `-j N` | compatibility aliases for `--processes` |
| `--save` | compatibility flag; work/products are already preserved by default |
| `--cleanup-work` | remove `xstar2xspec-work/` only after full success |
| `--restart` | reuse completed jobs with required success products |
| `--verbose` | replay child output while assembling deterministic root log |
| `--initable-bin PATH` | override `xstar-xspec-initable` executable |
| `--xstar-cpp PATH` | override `xstar-cpp` executable |
| `--table-bin PATH` | override `xstar-xspec-table` executable |
| `--version` | package version |
| `--help`, `-h` | help |

If `--data-dir` is omitted, each `xstar-cpp` child applies normal native data discovery.

## Restart and work directory

With `--restart`, a job is reusable only when `xout_spect1.fits`, `xout_step.log`, and `xstar-cpp.success` exist. Partial/failed products remain available for inspection.

The work tree is:

```text
xstar2xspec-work/jobs/NNNNNN/
```

Final root products are `xout_ain.fits`, `xout_aout.fits`, `xout_mtable.fits`, `xout_etable.fits`, and the canonical concatenated `xout_step.log`.
