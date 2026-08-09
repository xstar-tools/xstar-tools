# `xstar-cpp`

`xstar-cpp` is the first-class native frontend for the frozen production implementation. Normal direct runs require no Python runtime.

```bash
xstar-cpp --input xstar.par --data-dir /path/to/xstar/data --output run1
```

The positional form is also accepted:

```bash
xstar-cpp xstar.par --data-dir /path/to/xstar/data --output run1
```

XSTAR-style `name=value` inputs can be supplied without a parameter file.

## Core options

```text
--input PATH
--data-dir DIR
--output DIR / --output-dir DIR
--atomic-db PATH
--coheat PATH
```

## xstar-cpp extensions

```text
--json-summary FILE
--provenance FILE
--progress {none,text,json}
--threads N
--profile FILE
--deterministic
--print-option N
--parameters-out FILE
--abi
--version
```

These extensions are orchestration/provenance features, not required canonical XSTAR parameters. `--print-option` reads a requested section from the completed `xout_step.log`; it does not modify STEP generation.

The public frontend delegates scientific execution to the compatibility native `xstar_cpp run-production` path. `zone-cpp` and `zone-all` converge on the same frozen production operator rather than maintaining separate science implementations.

The detailed Milestone-6 architecture record remains available in `docs/developer/xstar_cpp.md`.
