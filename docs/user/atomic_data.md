# Atomic-data setup

A stable run requires an explicit local scientific-data directory. `XStarData.validate()` checks:

- `atdb.fits` in the selected data directory;
- `coheat.dat` in the selected data directory;
- the package `xstar/cpp/constants.def`;
- any optional cache paths supplied to `XStarData`.

Validation is local-only and never downloads scientific data as a side effect.

```python
from xstar_tools.data import XStarData

data = XStarData.from_directory("/path/to/xstar/data")
print(data.validate().as_dict())
print(data.identity())  # includes SHA-256 identities
```

For normal runs, the clearest contract is to pass the directory explicitly:

```bash
xstar-tools run xstar.par --mode pure-python --data-dir /path/to/xstar/data
```

The legacy/configuration helper behind `xstar-tools data` can show or set a configured `atdb.fits` path and can perform an explicit download when the user requests it. Normal scientific execution does not trigger that download helper automatically.

Because `atdb.fits` is a large external scientific input, release archives do not bundle it.

## Installed-package locations

Installed wheels do not write configuration or the large atomic database into `site-packages`. By default, configured data paths are stored at `~/.config/xstar-tools/datapath` and explicit downloads default to `~/.local/share/xstar-tools` (or the corresponding `XDG_CONFIG_HOME` / `XDG_DATA_HOME` locations). Source-tree development keeps the existing repository-level `datapath` / `data/` behavior.
