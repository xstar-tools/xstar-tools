# Windows native installation and usage

`xstar-tools` supports a native Windows build through **MSYS2 UCRT64**, MinGW-w64 GCC, GNU Make, CFITSIO, and pkg-config. The current accepted portability baseline, `0.6.88.6.1.2.1`, qualifies this toolchain as part of the full four-host matrix. Windows passes warning-free native compilation, PE DLL/import-library/export checks, shared-library discovery, the Win32 process layer, local-process XSTAR2XSPEC scheduling, fixed-state same-host determinism and cross-platform reference equivalence, the embedded Python backend, the Python bridge, and the existing regression suite.

Windows MPI is not part of the accepted Windows contract. Use `xstar-xspec --processes N` for local parallel XSTAR2XSPEC work on Windows. Do not expect `xstar-xspec-mpi` to be produced by the Windows build.

The accepted Windows fixed-state run reproduces the canonical FITS payload byte-exactly. Its text products may use CRLF line endings; the qualified cross-platform comparison normalizes line endings and requires exact discrete state plus strict numerical equivalence.

## 1. Install MSYS2 and open UCRT64

Install MSYS2 from its normal Windows installer, then open the **MSYS2 UCRT64** terminal. The shell must report:

```bash
echo "$MSYSTEM"
```

with:

```text
UCRT64
```

Do not use the plain MSYS shell for the native XSTAR build.

Update the package database and base installation as needed:

```bash
pacman -Syu
```

If MSYS2 asks you to close and reopen the terminal during a full update, do that and rerun the update command until it completes normally.

## 2. Install native build dependencies

For `xstar-cpp` and the native C++ runtime:

```bash
pacman -S --needed \
  make \
  mingw-w64-ucrt-x86_64-gcc \
  mingw-w64-ucrt-x86_64-binutils \
  mingw-w64-ucrt-x86_64-cfitsio \
  mingw-w64-ucrt-x86_64-pkgconf
```

For the complete build, embedded Python backend, and qualification tests, also install:

```bash
pacman -S --needed \
  mingw-w64-ucrt-x86_64-python \
  mingw-w64-ucrt-x86_64-python-pytest
```

Verify the environment:

```bash
echo "$MSYSTEM"
g++ --version
make --version
python --version
pkg-config --modversion cfitsio
pkg-config --cflags --libs cfitsio
```

## 3. Extract a source release

Windows drive `C:` is visible in MSYS2 as `/c`. For example, if the source archive is in `C:\Users\you\Downloads`:

```bash
cd /c/Users/you/Downloads
tar -xzf xstar_tools-<version>.tar.gz
cd xstar_tools-<version>/src/xstar_tools/xstar/cpp
```

For a Git checkout, enter the same `src/xstar_tools/xstar/cpp` directory.

## 4. Inspect the Windows build contract

```bash
make PLATFORM=windows print-config
```

The important values include:

```text
PLATFORM=windows
SHLIB_EXT=.dll
EXEEXT=.exe
V0682401_PRODUCTION_COMPILER=MINGW64
```

CFITSIO should normally report `CFITSIO_DISCOVERY=pkg-config` in the qualified MSYS2 UCRT64 environment.

## 5. Build `xstar-cpp`

To build only the standalone native XSTAR frontend and its required DLLs:

```bash
make -j4 PLATFORM=windows xstar-cpp.exe
```

To build the complete non-MPI Windows native target set:

```bash
make -j4 PLATFORM=windows
```

The build produces executables such as:

```text
xstar-cpp.exe
xstar_cpp.exe
xstar-xspec-initable.exe
xstar-xspec-table.exe
xstar-xspec.exe
```

and XSTAR DLLs such as:

```text
libxstar_api.dll
libxstar_production_zone.dll
libxstar_local_zone.dll
libxstar_engine.dll
libxstar_solver.dll
libxstar_emissivity.dll
libxstar_opacity.dll
libxstar_thermal.dll
```

MinGW import libraries use the `.dll.a` suffix.

Check the frontend version:

```bash
./xstar-cpp.exe --version
./xstar-cpp.exe --abi
```

For an initial source-tree run, keep `xstar-cpp.exe` in the same build directory as the generated `libxstar_*.dll` files.

## 6. Configure XSTAR atomic data

A real XSTAR calculation requires `atdb.fits` and `coheat.dat`. They are external data and are not bundled into the source archive.

For example, if the files are stored in:

```text
C:\xstar\data\atdb.fits
C:\xstar\data\coheat.dat
```

then the MSYS2 path is:

```text
/c/xstar/data
```

Verify them:

```bash
ls -lh /c/xstar/data/atdb.fits
ls -lh /c/xstar/data/coheat.dat
```

The clearest first run uses an explicit directory:

```bash
./xstar-cpp.exe --data-dir /c/xstar/data ...
```

You can instead set:

```bash
export XSTAR_DATA=/c/xstar/data
```

Native discovery also honors the established explicit-file and environment-variable precedence, including `XSTAR_ATOMIC_DB`, `XSTAR_ATDB_FITS`, `XSTAR_COHEAT`, `XSTAR_DATA`, and `HEADAS/refdata` when those locations are configured.

## 7. Run a small included example

From `src/xstar_tools/xstar/cpp`, a useful first real calculation is the included C5 parameter file:

```bash
./xstar-cpp.exe \
  --input ../../../../qualification/c5_terminal_step_0_6_82_6/params/c5_ne1e8.par \
  --data-dir /c/xstar/data \
  --output-dir run_c5_windows
```

Inspect the output directory:

```bash
find run_c5_windows -maxdepth 1 -type f -print
```

Depending on the input output-control parameters, products can include files such as `xout_step.log`, `xout_abund1.fits`, `xout_lines1.fits`, `xout_rrc1.fits`, and `xout_spect1.fits`.

The broader example file can be run in the same way:

```bash
./xstar-cpp.exe \
  --input ../../../../examples/xstar_example.par \
  --data-dir /c/xstar/data \
  --output-dir run_example_windows
```

That example is a more substantial multi-element calculation and is not intended as the fastest smoke test.

## 8. Run without a parameter file

`xstar-cpp` also accepts `name=value` parameters directly. For example:

```bash
./xstar-cpp.exe \
  --data-dir /c/xstar/data \
  --output-dir run_direct_windows \
  spectrum=pow spectun=0 trad=-1 \
  temperature=100 pressure=0.03 density=1e12 \
  column=1e20 rlrad38=1e6 rlogxi=1 cfrac=0.4 \
  habund=1 heabund=1 cabund=1 \
  nabund=0 oabund=0 neabund=0 mgabund=0 \
  siabund=0 sabund=0 arabund=0 caabund=0 \
  crabund=0 feabund=0 niabund=0 \
  modelname=windows_test abundtbl=xdef \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 \
  emult=0.5 taumax=5 xeemin=0.1 critf=1e-6 \
  vturbi=100 radexp=0 npass=1 ncn2=9999
```

For reproducible science runs, keeping the parameters in a file is usually easier to audit.

## 9. Run local-process XSTAR2XSPEC

Build the complete native target set first:

```bash
make -j4 PLATFORM=windows
```

Then run a serial/local grid with `xstar-xspec.exe`:

```bash
./xstar-xspec.exe \
  --input /c/path/to/xstinitable.par \
  --data-dir /c/xstar/data \
  --output-dir run_xspec_windows \
  --processes 2
```

`--processes 2` means two independent `xstar-cpp` **OS processes** may run at the same time. It does not create two XSTAR threads. The Windows process backend uses the qualified Win32 process layer.

Windows MPI remains out of scope. Do not run `mpirun xstar-xspec.exe`; `xstar-xspec-mpi` is the separate POSIX/MPI frontend and is opt-in on supported MPI platforms.

## 10. Clean and rebuild

```bash
make clean PLATFORM=windows
make -j4 PLATFORM=windows
```

A strict Windows qualification build is expected to be warning-free.

## 11. Common Windows problems

### `pkg-config` cannot find CFITSIO

Confirm you are in the UCRT64 shell and that the UCRT64 packages are installed:

```bash
echo "$MSYSTEM"
pacman -Q mingw-w64-ucrt-x86_64-cfitsio
pkg-config --modversion cfitsio
```

### A XSTAR DLL cannot be found

For source-tree use, run the executable with the generated sibling `libxstar_*.dll` files still present in the C++ build directory. `XSTAR_PLUGIN_PATH` may also point to that directory when explicitly testing plugin discovery.

### Atomic data cannot be found

Use an explicit path first:

```bash
./xstar-cpp.exe --data-dir /c/xstar/data ...
```

Then verify both required files exist in that directory.

### Embedded Python cannot import `ctypes`

The accepted Windows embedder registers the initialized Python runtime DLL directory before importing the `xstar_tools` Python package. Use the UCRT64 Python package and keep the Python installation consistent with the compiler environment.

### Path syntax

Inside MSYS2 commands, prefer POSIX-style paths such as `/c/xstar/data`. The native code contains explicit Windows path-boundary handling for existing narrow CFITSIO/XSTAR C APIs, but shell commands are easier to reproduce when written in MSYS2 form.

## 12. Current qualification checks

The historical `0.6.88.6.1.2.1` host runner established the accepted Windows portability baseline, but that closed milestone runner is no longer shipped in the lean release tree. Current source releases keep compact active gates instead:

```bash
python tools/qualification/check_parity_freeze.py
python tools/qualification/check_source_concordance.py
python tools/release/check_release_candidate.py
```

Run the ordinary pytest suite in the same UCRT64 environment for platform/runtime regression coverage. The accepted policy remains: Windows native support uses MSYS2 UCRT64/MinGW-w64; Windows conda packages are unsupported; MSVC and Windows MPI are not planned. Local parallel XSTAR2XSPEC execution remains available through `xstar-xspec --processes N`.
