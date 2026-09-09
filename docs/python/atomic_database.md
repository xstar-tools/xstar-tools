# Atomic database API

`XSTARAtomic` is the high-level Python interface to XSTAR's packed `atdb.fits` database:

```python
from xstar_tools.api import XSTARAtomic

with XSTARAtomic("/path/to/atdb.fits") as atomic:
    print(atomic.summary())
```

By default the record/element/ion index is built at construction time. For repeated work, an NPZ index cache can be enabled:

```python
atomic = XSTARAtomic(
    "/path/to/atdb.fits",
    index_cache=True,
    index_cache_format="npz",
)
```

## Ion selection

Ion selectors accept normal element/ion notation supported by `parse_ion`. Typical calls are:

```python
levels = atomic.levels("O VII")
lines = atomic.lines("O VIII", wavelength=(18.8, 19.1), slim=True)
wavelengths = atomic.get_wavelengths("Ne IX")
line = atomic.match_line("O VIII", wavelength=18.97)
```

## Photoionization

```python
photo = atomic.photoionization(
    "O VII",
    threshold_ev=(500.0, 1000.0),
    include_grid=True,
)
```

With `include_grid=True`, the result contains `summary` and matching raw grid rows.

## Collisions

```python
collision = atomic.collisions(
    "O VII",
    temperatures=[1.0e5, 1.0e6, 1.0e7],
    include_grid=True,
)
print(collision["summary"])
print(collision["evaluated"])
```

The returned mapping also retains the earlier aliases `matches` and `evaluated_rates`.

## Recombination and emissivity

```python
recomb = atomic.recombination("O VIII", temperatures=[1.0e5, 1.0e6])
emis = atomic.emissivity("O VII", temperature=1.0e6, electron_density=1.0e10)
```

For convenience, the high-level object also exposes `get_recombination`, `calc_emissivity`, and `calc_triplet` compatibility helpers.

## Population/matrix tools

```python
matrix = atomic.build_matrix("O VII", temperature=1.0e6, electron_density=1.0e10)
pop = atomic.solve_populations("O VII", temperature=1.0e6, electron_density=1.0e10)
```

These methods delegate to the maintained matrix/solver modules; they do not replace the source-faithful XSTAR run controller.

## Type-50 and XSTAR-run diagnostics

Advanced APIs include:

```python
atomic.type50_rate(...)
atomic.audit_type50_line_pumping(...)
atomic.reproduce_xstar_run("/path/to/run", ...)
atomic.build_xstar_local_target("/path/to/run", ...)
```

These are intended for detailed atomic/rate validation and comparison work. Use the stable execution API in {doc}`execution` for ordinary full XSTAR calculations.
