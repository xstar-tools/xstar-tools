# `xstar-xspec`

`xstar-xspec` is the accepted native XSTAR2XSPEC orchestrator. It composes:

```text
xstar-xspec-initable
    -> one or more xstar-cpp processes
    -> canonical loopcontrol gather
    -> xstar-xspec-table
    -> xout_ain.fits / xout_aout.fits / xout_mtable.fits / xout_etable.fits
```

## With `xstinitable.par`

Serial:

```bash
xstar-xspec --input xstinitable.par --output-dir run_serial --workers 1
```

Local parallel:

```bash
xstar-xspec --input xstinitable.par --output-dir run_local --workers 2
```

`--workers N` counts simultaneous child **processes**, not C++ threads. Each worker is a separate `xstar-cpp`. The OS may schedule N runnable workers on N logical CPUs when capacity is available, but `xstar-xspec` does not pin workers to physical cores.

## Without `xstinitable.par`

```bash
xstar-xspec \
  --output-dir run_grid \
  --workers 2 \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0
```

The example creates four jobs. Planner defaults supply parameters not explicitly overridden.

## Data discovery

With:

```bash
--data-dir /path/to/xstar/data
```

that directory is emitted into every `xstar-cpp` plan row. Without it, each child uses normal `xstar-cpp` discovery, including `XSTAR_DATA` and `HEADAS/refdata` fallbacks.

## Restart and failure products

```bash
xstar-xspec --input xstinitable.par --output-dir run_local --workers 2 --restart
```

Restart reuses a job only if these all exist:

```text
xout_spect1.fits
xout_step.log
xstar-cpp.success
```

The work tree is preserved by default. A failed calculation reports failure but does not automatically delete XSTAR products. `--cleanup-work` is explicit and applies only after complete success.

## Deterministic placement

Workers may complete in arbitrary order. Scientific placement never follows completion order; final STEP concatenation and spectrum/table placement always follow ascending `loopcontrol`.
