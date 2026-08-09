# Reproducibility and provenance

The distribution version and scientific revision are intentionally independent. A productization-only release can change documentation or interfaces without changing accepted science.

Record both when publishing or comparing a run:

```bash
xstar-tools version
```

Stable provenance can include:

- requested and actual execution mode;
- package version and science revision;
- C API and production-zone ABI;
- C++ library/executable identity;
- CPU feature/dispatch information;
- fallback events;
- atomic database, `coheat.dat`, and package-constant paths/hashes.

CLI execution can persist the stable result object and event stream:

```bash
xstar-tools run xstar.par \
  --mode zone-python \
  --data-dir /path/to/xstar/data \
  --output-dir run1 \
  --summary-json run1-summary.json \
  --json-log run1-events.jsonl
```

Run-scoped thread/reproducibility environment settings are restored after each stable Python API run.
