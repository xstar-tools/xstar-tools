# First run

## Native `xstar-cpp`

Commands below use the Unix executable spelling. In an MSYS2 UCRT64 Windows build, use `xstar-cpp.exe` / `xstar-xspec.exe`.

Using an XSTAR parameter file:

```bash
xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output run1
```

Without a parameter file:

```bash
xstar-cpp \
  --data-dir /path/to/xstar/data \
  --output run_direct \
  spectrum=pow temperature=100 density=1e8 column=1e20 rlogxi=1 \
  cfrac=1 niter=0 ncn2=9999 modelname=direct_example
```

Values after `--input` override the file:

```bash
xstar-cpp --input xstar.par --output run_override density=1e10 rlogxi=2
```

For a realistic direct single-model parameter set including abundances, pressure, convergence, and output controls, see {doc}`../cpp/xstar_cpp`.

If `--data-dir` is omitted, native atomic-data discovery is used; see {doc}`atomic_data`.

## Native XSTAR2XSPEC

Serial:

```bash
xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_serial \
  --processes 1
```

Two simultaneous local processes:

```bash
xstar-xspec \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_local2 \
  --processes 2
```

`--processes` counts **OS processes**, not threads. Each process slot launches a distinct `xstar-cpp`. The operating system schedules those processes on available logical CPUs; physical-core pinning is external to `xstar-xspec`.

A direct four-job 2 x 2 grid can be created without `xstinitable.par`:

```bash
xstar-xspec \
  --data-dir /path/to/xstar/data \
  --output-dir run_grid \
  --processes 2 \
  column=1e21 columntyp=2 columnsof=1e20 columnnst=2 columnint=1 \
  rlogxi=2 rlogxityp=2 rlogxisof=1 rlogxinst=2 rlogxiint=0
```

For a realistic direct XSTAR2XSPEC grid with many physical and grid-control parameters, see {doc}`../cpp/xstar_xspec`.

Restart:

```bash
xstar-xspec --input xstinitable.par --output-dir run_local2 --processes 2 --restart
```

The visible `xstar2xspec-work/` tree is preserved by default. Failed XSTAR products are retained for inspection and are never automatically deleted.

## True MPI XSTAR2XSPEC (`0.6.86` accepted)

MPI is opt-in at build time:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

Run one grid over four MPI ranks:

```bash
mpirun -np 4 src/xstar_tools/xstar/cpp/xstar-xspec-mpi \
  --input xstinitable.par \
  --data-dir /shared/xstar/data \
  --output-dir /shared/run_mpi
```

There is no local `--processes` option in `xstar-xspec-mpi`; `mpirun/mpiexec -np N` supplies the MPI rank count. The initial implementation requires a shared filesystem for executable, atomic-data, work, and output paths.

## Python API

The established Python interface remains available:

```python
from xstar_tools import XStarConfig, BackendMode, run_xstar

config = XStarConfig(
    input_file="xstar.par",
    data_dir="/path/to/xstar/data",
    output_dir="run_python",
    mode=BackendMode.PURE_PYTHON,
)
result = run_xstar(config)

if not result.success:
    raise RuntimeError(result.status)
```
