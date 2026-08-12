> **Current 0.6.82.24.3 qualification note:** the C5 covering-fraction axis is closed at `cfrac=0`, `0.4`, and `1.0`, and the practical `emult=0.1/0.25/0.5/1.0` science sweep is ACCEPT under 0.6.82.22. 0.6.82.23 established the public Table-1 parameter contract: stock `xstar.par`/XPI defaults and ranges, complete 59-parameter provenance, and consumer/sensitivity gates. The low-ionization speed baseline remains frozen for 0.6.82.31-0.6.82.33.

# xstar-tools

`xstar-tools` is a source-faithful Python/C++ productization of XSTAR photoionization calculations. It preserves an accepted scientific baseline tied to XSTAR Fortran 2.59g while providing a stable Python API, one primary CLI, accelerated/shared C++ modes, and a native standalone `xstar-cpp` executable.

**Distribution:** `0.6.82.24.3`  


**0.6.82.24.3 pure-Python first `h-c(%)` stage:** the `niter` parameter campaign is closed after C++ `0/-99/1/99` and pure-Python `0/-99/1/99` reproduce stock FORTRAN science. This successor changes only the first legacy STEP/progress `h-c(%)` display value in pure Python: it now publishes `hmctot` from `xstarcalc`'s unconditional final `calc_hmc_all`, matching FORTRAN `pprint(9)`. The second `h-c(%)` transport residual and all physical products are frozen.

**0.6.82.24.2 niter publication ownership:** the `niter=0` and finite-iteration `niter=1` source branches retain the accepted controller `xee` through persisted STEP/FITS and pprint(22).  The fixed-state computed electron fraction remains diagnostic only.  This is a narrow publication-state ownership hotfix; DSEC, rates, matrix, cfrac, and convergence arithmetic are unchanged.


**0.6.82.19 Type-50 `cfrac<1` full-grid `calc_emis` ownership:** the exact 0.6.82.18 H+He+C, `ne=1e12`, `column=1e20`, `cfrac=1`, `rlogxi=-5..5` campaign is frozen 11/11 ACCEPT under the `<1%` material policy. Fresh original-FORTRAN `cfrac=0.4` qualification exposed large transmitted/reflected Option-1 and heating/cooling differences because Type-50 continuum pumping, proportional to `(1-cfrac)`, had never been exercised at `cfrac=1`. Canonical FORTRAN evaluates Type-50 on reduced `epim/bremsam` during `calc_hmc_all`/`calc_emisab_all` and calls `ucalc` again on full `epi/bremsa` from `calc_emis_ion` before forming `fline/rcem`; C++ had reused the reduced-grid answer and Python had analogous caller-grid/binning errors. 0.6.82.19 restores the reduced-vs-full ownership split and live `abs(eeup-eelo)` `nbinc` sampling. The `cfrac=0.4` and `cfrac=0.0` host gates are pending; use original unmodified FORTRAN XSTAR 2.59g for qualification and patched FORTRAN only for diagnostics. Science revision and ABIs remain frozen.

**0.6.82.18 terminal-writer ownership repair:** `0.6.82.17` successfully removed the end-of-run duplicate-history memory spike, but released the temporary terminal `FixedDsecSnapshot` before the legacy patch5.20.14.5 final writer recompute consumed it. `0.6.82.18` keeps that snapshot released and reads the exact terminal publication workspace from the already-retained canonical `radial_zones.back().accepted_controller.evaluation`. This is publication ownership only; science kernels, frozen science revision, and ABIs are unchanged.


**0.6.82.17 publication-memory completion and qualification policy:** generic native production now releases non-publication DSEC histories and transferred accepted-boundary snapshots instead of retaining/deep-copying the complete low-`xi` controller history at end of run. `WholeRunAccumulatedState` is moved into product-writing state, removing the memory spike that caused return code 137 after the final physical STEP row but before `xout_step.log`/FITS publication. This release intentionally makes no science-kernel change. For the current broad FORTRAN campaign, `ntotit` is diagnostic-only; material STEP/FITS quantities must remain within the established `<1%` criterion, and percentage-valued STEP columns use `<1` absolute percentage point. The exact 0.6.82.16 `rlogxi=-3` host run produced all 77 physical rows with max printed `h-c` difference 0.10 percentage point and only three isolated `ntotit` differences before the publication SIGKILL. FITS closure is pending the 0.6.82.17 host run. Science revision and public ABIs remain frozen.

**0.6.82.16 source-faithful `ispec4` normalization:** canonical `ispec4.f90` uses `constants.f90` `ergsev`, whose unsuffixed default-REAL initializer `1.602176634e-12` is rounded before promotion to `REAL(8)`. Python and C++ built-in power-law normalization now use that source-executed value while preserving the separate historical `ispcg2` reporting literal. The 0.6.82.15 host run is exact through row 67 in printed `h-c` and `ntotit`; only three isolated late `ntotit` differences remain before the host SIGKILL near completion. `rlogxi=-3,-2` remain host gates and the science revision/ABIs remain frozen.

**0.6.82.15 source-parent Type-50 mass repair:** canonical FORTRAN obtains the nuclear mass used by Type-50 Doppler broadening from the rate-type-11 element parent reached through `line -> ion -> element`; C++ and Python previously replaced that source-owned value with hard-coded periodic-table masses. Production lowering/profile metadata now use the ATDB parent value for every applicable element, with the old tables retained only for incomplete synthetic fixtures. This is the next focused correction after 0.6.82.14 moved the serious `rlogxi=-3` divergence from row 3 to row 12. `rlogxi=-3,-2` remain host gates; the accepted science revision and public ABIs remain frozen.

**0.6.82.14 source-faithful `pescl` high-tau repair:** canonical `pescl.f90` stores `pi` from the default-REAL literal `3.1415927`; native C++ accidentally used `3.145165358979...`, biasing every `tau >= 1` line escape probability by about -5.68e-4. The correction uses the source-rounded default-REAL value in C++ and Python. H+He+C host qualification remains required at `rlogxi=-3,-2` before low-xi closure is claimed. Science revision and public ABIs remain frozen.

**0.6.82.13 all-element atomic-data-type generalization:** the production atomic-rate contract removes remaining H/He/C/Mg target-element selection where FORTRAN is generic while preserving genuine source ion-sequence/data-family applicability. C++ covers all 78 physical labels (including 44/44 generic opcode-200 evaluators), and the Python compact/native lowerer now accepts the same 78/78 labels with Z=1-30 mass/`xdef` defaults. Type-99 persistent `leveltemp` state is extended through Z=30, Type-70 now keys its H-only density cap to global source `jkion==1`, and Python's legacy Mg-only product accelerators are retired from science ownership. The thermal ledger is a separate open milestone. H+He+C `rlogxi=-3,-2,-5` remain host qualification gates; this release does not claim broad science closure.

**0.6.82.11 all-element Type-49 source-faithful bound-free promotion:**
canonical Type-49 `phint53`/Milne rate commitment now applies to every active
element in native production, removing the remaining historical H/He/C/Mg
compatibility split for this rate family. This release preserves the 0.6.82.10
all-element Type-53 live `tauc/cfrac` escape-state correction and the 0.6.82.9
Lucy-loop repair. H+He+C `cfrac=1` host qualification remains open at
`rlogxi=-3,-2` and technically at `-5` until the exact `ntotit` sequence closes;
`cfrac<1` has not yet been qualified. The accepted science revision and public
ABIs remain intentionally frozen until broad all-element concordance closes.
**Accepted science revision:** `0.6.48.12.3.45.3.3.8`  
**Frozen C++ all-62 baseline:** `0.6.48.12.3.44`  
**C API ABI:** `60487`  
**Production-zone ABI:** `6048110`

Product/package versions can advance without changing the frozen science revision. Use `xstar-tools version` to see both.


## 1. What `xstar-tools` is

The project exposes the qualified XSTAR implementation through five stable execution modes:

| Mode | What runs the calculation | Typical use |
|---|---|---|
| `pure-python` | Python controller, local-zone solve, and Python science kernels | Reference/debugging |
| `zone-python` | Python controller with qualified modular C++ kernels | Accelerated Python |
| `zone-cpp` | Shared C++ production-zone evaluator, invoked from Python | Production shared-zone path |
| `zone-all` | Shared C++ full production path, invoked from Python | Production shared-all path |
| `xstar-cpp` | Native standalone executable | Python-free native runs |

The stable public API and CLI are productization layers. They do not duplicate the qualified scientific algorithms in `xstar_tools.xstar` and the native C++ core.

## 2. Relationship to XSTAR

XSTAR Fortran 2.59g remains the canonical executable source authority when new source behavior needs interpretation. Accepted qualification evidence is the authority for behavior that has already been closed. XSTAR papers and manuals provide the scientific explanation and context.

The accepted parity boundary is documented in [`PARITY_FREEZE.md`](PARITY_FREEZE.md) and `qualification/parity_freeze.json`. Productization work must not silently change that boundary.

## 3. Installation

`pyproject.toml` is the authoritative build configuration. Install a release normally with:

```bash
python -m pip install xstar-tools
```

Linux builds compile and bundle the qualified native runtime when the C++17/Make/CFITSIO prerequisites are available. To require native support explicitly:

```bash
XSTAR_TOOLS_NATIVE=required python -m pip install .
```

For a Python-only installation:

```bash
XSTAR_TOOLS_NATIVE=off python -m pip install .
```

A conda-forge-ready recipe is also maintained under `conda/recipe/`. After the
feedstock is accepted and published, installation is:

```bash
conda install -c conda-forge xstar-tools
```

The conda recipe follows the same Linux-native / macOS-Windows Python-only
capability policy and keeps `atdb.fits` external.

For development:

```bash
python -m pip install -e '.[dev]'
```

The native wheel build retains the qualified Makefile/compiler defaults and stages only runtime artifacts; it does not package C++ source/object/cache debris. Native packaging is Linux-first in 0.6.72; macOS and Windows use the explicit Python-only capability path.

Check the installation:

```bash
xstar-tools version
xstar-tools backends
xstar-tools doctor
```

## 3.1 XSTAR parameter compatibility added in 0.6.82

The public XSTAR parameter contract now includes all ten documented abundance
bases for `abundtbl`: `xdef`, `angr`, `aspl`, `feld`, `aneb`, `grsa`, `wilm`,
`lodd`, `lpgp`, and `lpgs`. The supplied XSTAR 2.59g source uses `lgpp` and
`lgps` for the last two tables; those source spellings are accepted as aliases.
The element inputs (`habund` through `znabund`) remain multipliers of the
selected base, matching `xstarsetup.f90`.

`lwrite` follows the literal XSTAR source condition for the four pass-specific
detail products: they are produced when `lwrite>0` **or** `npass>1`. Thus a
normal one-pass run with `lwrite=0` produces the five standard final FITS
products (`xout_abund1`, `xout_cont1`, `xout_lines1`, `xout_rrc1`, and
`xout_spect1`) plus `xout_step.log`, but not `xo01_detail.fits`,
`xo01_detal2.fits`, `xo01_detal3.fits`, or `xo01_detal4.fits`. Native
standalone acceptance uses the same control-derived product count rather than
requiring nine FITS files unconditionally.

`lprint` accepts the XSTAR 2.59g parameter-file range `-1..6`. It is an ASCII/log
verbosity control; standard FITS science is unaffected. The accepted
comparator-visible STEP science is retained, while complete optional historical
verbose formatting for nonzero `lprint` is characterized rather than claimed
bit-for-bit complete. `loopcontrol` accepts `0..30000`: zero means standalone,
and positive values are preserved as 1-based XSTAR2XSPEC job identities.

See [`docs/developer/xstar_parameter_contract_0_6_82.md`](docs/developer/xstar_parameter_contract_0_6_82.md)
for the source-level contract and known documentation/source discrepancies.

## 3.2 XSTAR2TABLE compatibility

The native `xstar-xspec-table` converter reads ordinary `xout_spect1.fits` and
produces `xout_ain.fits`, `xout_aout.fits`, `xout_mtable.fits`, and
`xout_etable.fits`. Its implementation is explicitly source-concordant with
XSTAR Manual Chapter 6, `src/xstar2table/xstar2table.c`, and
`xstarlib/src/xstartablelib.c`. The sealed 0.6.81.1 canonical 2x3 MPI_XSTAR
fixture is bit-exact for energy bins, `PARAMVAL`, and all four `INTPSPEC`
payloads. Native `xstinitable` is not yet part of 0.6.82.

## 3.2 Constant-pressure semantics in 0.6.82.25

`lcpres=0` is the canonical density-controlled branch. `lcpres=1` activates the FORTRAN constant-pressure branch: the input `rlogxi` is interpreted as pressure-form Xi for the initial radius, and the live hydrogen density is recomputed from `pressure` and the current temperature inside local evaluations. The accepted live density is retained in radial STEP/FITS products. See `docs/developer/lcpres_pressure_0_6_82_25.md` and the packaged host qualification runner for the source equations and acceptance procedure.


## 4. Atomic-data setup

Runs are local-data-only: they do not silently download scientific data. Point the run at an XSTAR data directory containing at least:

```text
atdb.fits
coheat.dat
```

The package also validates its shipped `src/xstar_tools/xstar/cpp/constants.def`.

```bash
DATA=/path/to/xstar/data
xstar-tools doctor --data-dir "$DATA"
```

In Python:

```python
from xstar_tools.data import XStarData

data = XStarData.from_directory("/path/to/xstar/data")
validation = data.validate()
print(validation.valid)
```

See the [atomic-data guide](docs/user/atomic_data.md) for validation, configured paths, and the explicit download helper.

## 5. Five-minute Python example

```python
from xstar_tools import XStarConfig, BackendMode, run_xstar

config = XStarConfig(
    input_file="xstar.par",
    data_dir="/path/to/xstar/data",
    output_dir="run1",
    mode=BackendMode.ZONE_PYTHON,
)

result = run_xstar(config)
print(result.success)
print(result.products.spectrum)
print(result.step_log)
```

`XStarConfig.from_mapping(...)` and `XStarConfig.from_fortran_run_directory(...)` are also supported. The API rejects a non-empty output directory by default; set `overwrite=True` when replacement is intentional.

## 6. Five-minute CLI example

The primary CLI is:

```text
xstar-tools run
xstar-tools inspect
xstar-tools data
xstar-tools backends
xstar-tools compare
xstar-tools doctor
xstar-tools version
```

Run a parameter file:

```bash
xstar-tools run xstar.par \
  --mode zone-python \
  --data-dir /path/to/xstar/data \
  --output-dir run1
```

Other stable modes use the same command:

```bash
xstar-tools run xstar.par --mode pure-python --data-dir "$DATA" --output-dir run-py
xstar-tools run xstar.par --mode zone-cpp   --data-dir "$DATA" --output-dir run-zcpp
xstar-tools run xstar.par --mode zone-all   --data-dir "$DATA" --output-dir run-zall
xstar-tools run xstar.par --mode xstar-cpp  --data-dir "$DATA" --output-dir run-native
```

The CLI constructs `XStarConfig` and calls the same `run_xstar(config)` orchestration layer as the Python API.

## 7. Backend modes

Use `xstar-tools backends` to see which modes are available on the current host. Use `xstar-tools doctor --require MODE` when a workflow requires a specific native capability.

`pure-python` is the reference/debug path. `zone-python` is the normal accelerated Python path. `zone-cpp` and `zone-all` expose the frozen shared C++ production paths. `xstar-cpp` is the standalone native frontend.

See [choosing a backend](docs/user/backends.md) for selection guidance and compatibility aliases.

## 8. `xstar-cpp` example

After a native Linux wheel install, `xstar-cpp` is available directly:

```bash
xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output run-native
```

A source checkout can still run `src/xstar_tools/xstar/cpp/xstar-cpp` after `make`.

XSTAR-style `name=value` inputs are also accepted. Optional `xstar-cpp` extensions include `--json-summary`, `--provenance`, `--progress`, `--threads`, `--profile`, `--deterministic`, `--print-option`, and `--abi`.

The frontend contains no independent scientific implementation: it delegates to the same frozen native production operator used by the shared production paths.

## 9. Output products

`XStarResult.products` provides deterministic paths for the nine principal FITS products plus `xout_step.log`:

```text
xout_abund1.fits
xout_lines1.fits
xout_rrc1.fits
xout_cont1.fits
xout_spect1.fits
xo01_detail.fits
xo01_detal2.fits
xo01_detal3.fits
xo01_detal4.fits
xout_step.log
```

See [output products](docs/user/outputs.md) for typed accessors and output-directory behavior.

## 10. Reproducibility and provenance

Stable runs record, where applicable, the requested/actual mode, package and science revisions, C/zone ABI versions, native identities, CPU dispatch information, fallback events, and scientific-data paths/hashes.

CLI runs can emit both a stable result summary and structured event log:

```bash
xstar-tools run xstar.par \
  --mode zone-python \
  --data-dir "$DATA" \
  --output-dir run1 \
  --summary-json run1-summary.json \
  --json-log run1-events.jsonl
```

## 11. Documentation

The documentation is layered by audience:

- [User guide](docs/user/index.md) — installation, first run, configuration, backends, outputs, performance, troubleshooting;
- [Python API](docs/api/index.md) — generated stable Python API reference;
- [C++/CLI reference](docs/cpp/index.md) — `xstar-cpp`, C ABI, and native build reference;
- [Developer guide](docs/developer/index.md) — architecture, source concordance, qualification, performance, and version/freeze policy;
- [Science guide](docs/science/index.md) — algorithm overview, XSTAR literature, and data/rate semantics;
- [Historical guide](docs/history/index.md) — how to find preserved historical qualification evidence.

Build the Sphinx site with:

```bash
python -m pip install -e '.[docs]'
make -C docs/sphinx html
```

Release documentation uses warnings-as-errors. Link checking is available with `make -C docs/sphinx linkcheck`.

## 12. Development and qualification

Advanced interfaces are grouped under:

```text
xstar-tools dev ...
xstar-tools qualify ...
```

Legacy console scripts remain for the current deprecation cycle. Release/science qualification lives under `tools/qualification/`; historical attribution evidence lives under `historical/` and is intentionally separate from normal user documentation.

The accepted all-62 C++ baseline established exact cross-mode C++ products before productization. Do not reopen frozen scientific behavior unless a new material discrepancy is demonstrated.

## 13. Citation and license

The package metadata declares the project under the **MIT** license. This source tree does not assert a project DOI. When publishing science produced with `xstar-tools`, record the package version and science revision and cite the relevant XSTAR literature listed in the [XSTAR references](docs/science/xstar_references.md).

For the exact software identity used in a run:

```bash
xstar-tools version
```
### Realistic multi-element native example

`examples/xstar_example.par` is a ready-to-run broad-composition parameter file for `xstar-cpp`.  It enables H, He, C, N, O, Ne, Mg, Al, Si, S, Ar, Ca, Cr, Fe, and Ni and exercises the general native ATDB lowering path rather than a single-metal smoke case.  See `examples/README.md` for the command.
For the 0.6.82.1 physical acceptance on a host with canonical XSTAR data, `tools/qualification/run_multi_element_host_smoke_0_6_82_2.py --data-dir /path/to/xstar/data --replace` verifies the full 15-element path and the public `xstar-cpp` file-silent frontend boundary.



### 0.6.82.3 broad multi-element science closure and live progress

`0.6.82.3` addresses two source-concordance defects exposed by the first completed 15-element `0.6.82.2` host comparison.  Retained products now keep the radius already derived by the controller from the XSTAR `rread1` semantics instead of substituting a historical benchmark fallback when the public JSON envelope omits `initial_radius_cm`.  Fe Type-85 photoionization heating now follows the XSTAR 2.59g `ucalc.f90` post-`phintfo` channel mapping (`ans4=-piht`, `ans6=-piht2`) rather than selecting recombination-cooling channels.

Long native runs are also observable: with `xstar-cpp --progress text`, the XSTAR-style header is emitted before the controller starts and each accepted radial-zone row is flushed immediately when that zone completes.  The version-locked broad-mixture host runner tees the native transcript live while retaining `host_smoke.log`.  The canonical broad FORTRAN fixture remains an external acceptance gate; this release does not claim host parity until that run is returned.

### 0.6.82.2 broad-element Type-51 closure

`0.6.82.2` keeps the accepted `0.6.82.1` multi-element lowering and file-silent frontend repairs, and closes the downstream Type-51 production abort exposed by the real 15-element host run. Finite legacy Type-51 results remain the compatibility result; source-faithful Type-51 is used only when that legacy evaluator cannot represent an otherwise valid canonical record. The physical broad-mixture gate is version-locked through `tools/qualification/run_multi_element_host_smoke_0_6_82_2.py`.

### 0.6.82.6 canonical terminal STEP endpoint restoration

`0.6.82.6` restores the canonical post-loop `pprint(9)` endpoint to native
STEP Option 17 and to live `--progress text` output.  XSTAR 2.59g prints this
physical post-transport boundary after the radial loop; it is distinct from the
later zero-thickness `xstarcalc`/`pprint(22)` final evaluation.  The correction
restores the final `log(N)=20.00` row in the historical C5 H+He+C cases without
changing their already-matching common-row thermal science.  The newly exposed
H+He+C `rlogxi=1.0` thermal discrepancy remains an open, separate science
investigation and is not altered by this release.

### 0.6.82.5 Type-85/DSEC/STEP physical-trajectory closure

`0.6.82.5` is the next broad-mixture host candidate after the rejected
`0.6.82.4` run.  It restores the source Type-85 post-`phintfo` channel
rearrangement while retaining energy-ordered endpoint ownership, moves DSEC
HMC-only execution into the actual production evaluator, retains the thermal
engine's literal `stats.ntotit`, and limits STEP Option 17 to physical radial
boundaries.  The canonical FORTRAN 2.59g broad fixture remains an external
science (`<1%`) and performance gate.

### 0.6.82.4 broad multi-element FORTRAN-oracle closure

`0.6.82.4` is the next host-qualification candidate after the completed
15-element `0.6.82.3` run exposed remaining Fe thermal, STEP convergence, and
performance differences.  Type-85 endpoints now follow XSTAR's universal
energy ordering before thermal accumulation; live/STEP iteration counts use the
literal DSEC count; and production DSEC trials no longer execute the
`calc_emisab`/`calc_emis` spectral projection that source `dsec.f90` does not
call.  Use the version-locked runner:

```bash
python3 tools/qualification/run_multi_element_host_smoke_0_6_82_4.py \
    --data-dir ../xstar/data \
    --replace
```

The runner compares the broad fixture to the preserved FORTRAN 2.59g STEP and
thermal oracles, requires material discrepancies below 1%, and reports the
runtime ratio separately.
