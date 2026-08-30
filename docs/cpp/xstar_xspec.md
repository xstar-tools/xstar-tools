# `xstar-xspec`

`xstar-xspec` is the complete native serial/local-process XSTAR2XSPEC driver:

```text
xstar-xspec-initable -> xstar-cpp grid -> loopcontrol-ordered gather -> xstar-xspec-table
```

## With `xstinitable.par`

Serial:

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --output-dir run_serial \
  --processes 1
```

Two simultaneous XSTAR processes:

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --output-dir run_local2 \
  --processes 2
```

`--processes N` counts independent **OS processes**, not C++ threads. The operating system or batch scheduler maps runnable processes to logical CPUs. The program does not pin processes to physical cores.

`--workers N` and `-j N` remain compatibility aliases. New commands should use `--processes N`. The spelling `-np` is reserved for MPI launchers.

## Without `xstinitable.par`

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --output-dir run_xspec_direct \
  --processes 2 cfrac=0.4 \
  temperature=100. lcpres=0 pressure=0.03 spectrum='pow' \
  spectun=0 trad=-1. density=1.0e+12 densitytyp=0 \
  columnsof=1.0e+20 columntyp=2 column=1.e+24 columnnst=9 columnint=1 \
  rlrad38=1.e+6 rlogxityp=2 rlogxisof=0 rlogxi=5 rlogxinst=6 rlogxiint=0 \
  habund=1 heabund=1 liabund=0 beabund=0 babund=0 cabund=1 \
  nabund=1 oabund=1 fabund=0 neabund=1 naabund=0 mgabund=1 \
  alabund=1 siabund=1 pabund=0 sabund=1 clabund=0 arabund=1 \
  kabund=0 caabund=1 scabund=0 tiabund=0 vabund=0 crabund=1 \
  mnabund=0 feabund=1 coabund=0 niabund=1 cuabund=0 znabund=0 \
  modelname='xstar_pg1211' abundtbl='xdef' nsteps=10 niter=99 \
  lwrite=0 lprint=1 lstep=0 emult=0.5 taumax=5. radexp=0. \
  xeemin=0.1 critf=1.e-6 vturbi=100. npass=1 ncn2=9999
```

If `--data-dir` is omitted, each `xstar-cpp` child independently applies the native atomic-data search contract (`XSTAR_DATA`, then `$HEADAS/refdata`, then legacy/package fallbacks after direct overrides).

## Restart

```bash
src/xstar_tools/xstar/cpp/xstar-xspec \
  --input xstinitable.par \
  --output-dir run_local2 \
  --processes 2 \
  --restart
```

A job is reusable only when `xout_spect1.fits`, `xout_step.log`, and `xstar-cpp.success` are present. Failed/partial products are retained for forensic inspection.

## Outputs

The visible work tree is `xstar2xspec-work/jobs/NNNNNN/`. Final root products are `xout_ain.fits`, `xout_aout.fits`, `xout_mtable.fits`, `xout_etable.fits`, and the canonical concatenated `xout_step.log`.
