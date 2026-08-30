# 0.6.87 — PROCESS_COUNT_CLI_AND_DOCUMENTATION

## Scope

`0.6.87` is an interface/documentation successor to formally accepted `0.6.86`. It does not reopen XSTAR scientific arithmetic or the accepted MPI scheduling model.

The local XSTAR2XSPEC executable launches independent `xstar-cpp` **OS processes**, so the canonical option is renamed from:

```text
--workers N
```

to:

```text
--processes N
```

`--workers N` and `-j N` remain compatibility aliases so existing `.85/.85.1/.86` scripts keep working.

## Why not `-np` for local mode?

`-np` is reserved for the MPI launcher contract:

```bash
mpirun -np N xstar-xspec-mpi ...
```

Using the same spelling for local-process concurrency would make commands ambiguous: local `xstar-xspec --processes N` starts N child processes from one orchestrator, while MPI `-np N` creates N MPI ranks, each of which may run one XSTAR child.

## CPU meaning

`xstar-xspec --processes 2` means at most two independent `xstar-cpp` processes can run simultaneously. It does not create two C++ threads and does not explicitly select two physical CPU cores. The operating system or batch scheduler maps the runnable processes onto available logical CPUs unless external CPU affinity/pinning is configured.

`xstar-cpp --threads N` remains a separate per-model thread/environment control.

## Compatibility

Production CLI parsing accepts:

```text
--processes N     canonical
--workers N       legacy compatibility alias
-j N              legacy compatibility alias
```

Python `run_xstar2xspec(..., processes=N)` is canonical. The older `workers=N` keyword remains an alias. If both are supplied with conflicting non-default values, the call fails rather than silently choosing one.

The legacy `xstar-tools-mpixstar` wrapper also exposes `--processes` canonically while retaining its historical aliases for old scripts. True MPI users should invoke `xstar-xspec-mpi` with `mpirun/mpiexec -np N`.

## Documentation

Current README/user documentation uses `--processes`. Historical `.85/.85.1` acceptance documents retain the wording `--workers` because those records describe the interfaces that actually existed at the time.
