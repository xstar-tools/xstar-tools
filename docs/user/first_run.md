# First run

## Python

```python
from xstar_tools import XStarConfig, BackendMode, run_xstar

config = XStarConfig(
    input_file="xstar.par",
    data_dir="/path/to/xstar/data",
    output_dir="run1",
    mode=BackendMode.PURE_PYTHON,
)
result = run_xstar(config)

if not result.success:
    raise RuntimeError(result.status)

print(result.products.spectrum)
```

## CLI

```bash
xstar-tools run xstar.par \
  --mode pure-python \
  --data-dir /path/to/xstar/data \
  --output-dir run1
```

The positional input can also be a source-faithful `run_xstar.sh`/`.cmd` parameter source. The file is parsed as data; it is not sourced into the current shell.

The default output policy rejects an already non-empty output directory. Use `--overwrite` only when replacement is intentional.
