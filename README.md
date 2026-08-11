# xstar-tools

`xstar-tools` is a source-faithful Python/C++ productization of XSTAR photoionization calculations. It preserves an accepted scientific baseline tied to XSTAR Fortran 2.59g while providing a stable Python API, one primary CLI, accelerated/shared C++ modes, and a native standalone `xstar-cpp` executable.

**Distribution:** `0.6.82.13`  

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
