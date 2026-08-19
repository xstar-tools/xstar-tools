# xstar_tools 0.6.82.30.2 - permanent all-Table-1 conformance gate

## Status

`0.6.82.30.2` supersedes the host-rejected qualification-harness candidate `0.6.82.30.1`. The correction is qualification-only: no numerical/science production file changes relative to the host-closed `0.6.82.29.3.10` baseline.

The rejected `.30` candidate used a mixed all-non-default parameter vector; `.30.1` corrected that to the literal Manual Table-1 baseline and one-parameter-at-a-time (OAT) probes. Host testing then exposed a separate `.30.1` harness defect: it used `pquery`, which follows XPI query-mode semantics and prompted for parameters such as `temperature`. `.30.2` keeps the corrected Table-1/OAT design and replaces query readback with noninteractive `pget`.

## Literal Manual Table-1 baseline

The 57 parameters displayed in XSTAR Manual Table 1 are initialized exactly from that table. Key defaults are:

```text
temperature=400
pressure=0.03
density=1.0e4
spectrum='pow'
spectrum_file='spct.dat'
spectun=0
trad=-1.0
rlrad38=1.0e-6
column=1.0e17
rlogxi=5.0
abundtbl='xdef'
modelname='XSTAR Default'
cfrac=1.0
lcpres=0
nsteps=3
niter=0
lwrite=0
lprint=0
emult=0.5
taumax=5.0
xeemin=0.1
critf=1.0e-7
vturbi=1.0
radexp=0.0
ncn2=9999
loopcontrol=0
npass=1
mode='ql'
```

Table-1 abundance defaults are H=1, He=1, Li=0, Be=0, B=0, and C through Zn=1 for the elements displayed by the table.

`naabund=1` and `lstep=0` are retained separately as public/source extensions because they are present in the stock parameter/source contract but omitted from the displayed Manual Table 1. They are never labeled as Table-1 defaults.

## OAT public-surface policy

Every normal surface probe starts from the complete baseline above and changes exactly one public parameter. For example:

```text
baseline: spectrum='pow'
spectrum probe only: spectrum='bbody'

baseline: spectrum_file='spct.dat'
spectrum_file probe only: spectrum_file='spect.dat'

baseline: cfrac=1
cfrac probe only: cfrac=0.4
```

Thus a log line showing `spectrum='bbody'` means only the dedicated `spectrum` sensitivity case is being tested; all other ordinary cases retain `spectrum='pow'`.

## Noninteractive FORTRAN XPI readback

The `.30.2` surface runner never asks the host user to type a parameter value. For each probe it creates a private PFILES copy containing the complete baseline, switches query modes to hidden only in that temporary qualification copy, applies the single override with `pset`, and reads it back with non-query `pget`. `pquery` is explicitly forbidden because query-mode parameters can prompt. If `pget` is unavailable, the runner parses the private `xstar.par` written by `pset`; invalid stock-XPI probes are checked against the stock `xstar.par` envelope.

## Permanent gate layers

1. **Source/scope gate** - verifies package version, frozen science/ABI identifiers, exact 57+2 parameter inventory, literal Table-1 baseline, `.29` formal closure, and byte identity of all 137 tracked numerical/science files.
2. **Public surface gate** - 59 OAT public-value probes: 57 Manual Table-1 parameters plus `naabund` and `lstep` source extensions.
3. **Fresh representative science** - FORTRAN/C++/pure-Python comparisons from the same baseline. Ordinary scalar/control/abundance cases are OAT; isolated H+He+C/O/Ca/Fe cases are explicitly multi-parameter representative science cases.
4. **Source-specific hard-contract replays** - retained focused qualification for `cfrac/emult`, `niter`, `lcpres`, `radexp/density.dat`, `npass`, and spectrum/`spectun` semantics.
5. **Output/control closure** - inherited exact `0.6.82.29.3.10` closure plus fresh control-invariance cases.

## Source/XPI exceptions

The gate records rather than hides source-vs-stock-XPI distinctions:

- `spectun=2`: source-supported and exercised by the `.28.1` spectrum replay; stock 2.59g XPI declares 0..1.
- `radexp<-99`: source `density.dat` sentinel branch exercised by the `.26.3` replay; stock XPI declares -3..3.
- `lwrite=-1`: source-supported output branch closed by `.29`; stock XPI declares 0..1. C++/Python therefore accept this source branch while the stock-XPI surface rejects it.

## Required release axes

The permanent gate retains:

```text
cfrac      0, 0.4, 1
emult      0.1, 0.25, 0.5, 1
niter      0, -99, 1, 99
lcpres     0, 1
radexp     analytic + density.dat
npass      1, 3, 5
spectrum   pow, bbody, bremss, file
spectun    0, 1, 2
ncn2       999, 9999, 19999
elements   C, O, Ca, Fe
```

All 30 abundance multipliers H through Zn also receive OAT full-science probes.

## Frozen identifiers

```text
science revision       0.6.48.12.3.45.3.3.8
C API ABI              60487
production-zone ABI    6048110
fixed-state ABI        60488
```

These remain frozen. Passing `.30.2` does not by itself advance the accepted science revision; the broader reopened element/density campaign must also pass.
