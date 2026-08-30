# Stable public execution modes

Milestone 3 introduces five stable execution modes above the older backend flags. The old flags remain advanced compatibility aliases; scientific kernels and the accepted controller paths are unchanged.

| Public mode | Controller / radial owner | Zone implementation | Modular science backends | Frozen internal path |
|---|---|---|---|---|
| `pure-python` | Python | Python | Python | `--zone-backend python --backend python --solver-backend python` |
| `zone-python` | Python | Python source-faithful orchestration | qualified C++ kernels | `--zone-backend python --backend cpp --solver-backend cpp` |
| `zone-cpp` | Python invocation, persistent C++ controller context | shared C++ production-zone evaluator | C++ | legacy `cpp-zone` |
| `zone-all` | Python invocation, one C++ trajectory call | shared C++ production path | C++ | legacy `cpp-all` |
| `xstar-cpp` | native C++ | native C++ | C++ | `xstar_cpp run-production`; public executable alias `xstar-cpp` |

## Public Python API

```python
from xstar_tools import BackendMode, run_xstar

result = run_xstar(
    mode=BackendMode.PURE_PYTHON,
    run_script="run_xstar.sh",
    atdb_path="/path/to/atdb.fits",
    output_dir="run-py",
)
```

The capability API is intentionally inspection-only:

```python
from xstar_tools import backends

backends.available()
backends.describe()
```

`available()` returns availability for all five public modes. `describe()` adds component library paths, backend/ABI identities, standalone executable identity, CPU feature information, package version, science revision, C API ABI, and production-zone ABI.

## CLI

```bash
xstar-tools backends
xstar-tools doctor
xstar-tools doctor --require zone-python

xstar-tools run \
  --mode pure-python \
  --run-script run_xstar.sh \
  --atdb /path/to/atdb.fits \
  --output-dir run-py

xstar-tools run \
  --mode zone-python \
  --run-script run_xstar.sh \
  --atdb /path/to/atdb.fits \
  --output-dir run-accelerated
```

`zone-cpp` and `zone-all` currently require `--run-script`, because the public names deliberately route through the already-qualified shared-production `cpp-zone` / `cpp-all` adapters rather than creating a new parameter normalization path.

For `xstar-cpp`, normal direct production is Python-free and accepts XSTAR-style `name=value` arguments:

```bash
make -C src/xstar_tools/xstar/cpp xstar-cpp
src/xstar_tools/xstar/cpp/xstar-cpp \
  --atomic-db /path/to/atdb.fits \
  --coheat /path/to/coheat.dat \
  --output-dir native-run \
  cfrac=1 temperature=100 density=1e8 spectrum=pow column=1e22 rlogxi=1.5 \
  habund=1 heabund=0.1 mgabund=3.5e-5
```

The frontend preserves the literal values as strings in a small native parameter envelope and then `execv`s the already-qualified `xstar_cpp run-production` implementation. This keeps source/default-REAL interpretation in the frozen native reader and requires no Python runtime. The machine-readable interface remains available explicitly:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp run-production \
  --parameters parameters.json \
  --output-dir native-run
```

The compatibility executable name `xstar_cpp` remains built. The generated JSON parameter envelope is ephemeral and outside the science output directory unless `--parameters-out FILE` explicitly requests retention. After each public native production run, `xstar-cpp` writes `xstar_execution_provenance.json` in the output directory with requested/actual mode, package/science versions, C API and zone ABIs, native executable identity, CPU/Type50 dispatch capability, native return code, fallback events, and SHA-256 identities for the resolved atomic-data files supplied to the frontend. `xstar-tools run --mode xstar-cpp` is an optional Python convenience boundary that converts an ordinary `run_xstar.sh` or literal XSTAR command into the same qualified machine-readable native parameter envelope.

## Provenance contract

Every stable-mode run, and every mixed legacy run reported as `advanced`, reports an `execution` provenance object containing:

- requested mode and actual mode;
- package version and accepted science revision;
- C API ABI (`60487`) and production-zone ABI (`6048110`);
- C++ library/executable identity and version where present;
- CPU feature information and the Type50 runtime dispatch policy;
- fallback events observed at backend boundaries;
- `atdb.fits` and `coheat.dat` resolved paths and SHA-256 hashes when available.

`pure-python` explicitly installs Python for every modular backend for the duration of the run. This prevents ambient `XSTAR_ATOMIC_*` environment variables from silently introducing a C++ dependency into the reference/debug mode.

## Advanced compatibility aliases

The older flags remain available for development and exact historical scripts:

- `--backend python|cpp|auto`
- `--solver-backend python|cpp|auto`
- `--zone-backend python|cpp-zone|cpp-all`
- `--rates-backend`, `--matrix-backend`, `--emissivity-backend`

Exact legacy combinations are identified with their stable public mode in provenance. Mixed/custom combinations are reported as `advanced`. A stable `--mode` cannot be combined with these advanced flags in the same invocation; this prevents ambiguous ownership.

## Refactor gate

`qualification/public_execution_modes_0_6_60.json` is the mode-mapping contract. `tools/qualification/check_public_execution_modes.py` and `tests/test_public_execution_modes.py` prove that public names select the same internal paths as the frozen aliases. A future backend refactor must update characterization first and must not change a public mapping silently.


## Native XSTAR2XSPEC process and MPI modes

The standalone table pipeline is separate from the five single-model backend modes above.

`xstar-xspec --workers N` uses a bounded pool of **OS child processes**. It does not create threads or MPI ranks. Each worker launches one independent `xstar-cpp`, so `--workers 2` permits two concurrent XSTAR processes. The operating system may schedule them on two logical CPUs when available; CPU affinity/pinning is external.

`0.6.86` adds the opt-in true-MPI candidate `xstar-xspec-mpi`. Its concurrency is selected by `mpirun/mpiexec -np N`; it deliberately rejects `--workers`. Every rank may run one `xstar-cpp` at a time, and rank 0 performs the final loopcontrol-ordered table gather. See `true_mpi_xstar2xspec_0_6_86.md`.
