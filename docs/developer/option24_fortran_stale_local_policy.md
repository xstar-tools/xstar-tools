# Option 24 Fortran stale-local publication policy (0.6.67)

`xstar_tools 0.6.67` is a productization/comparator patch. It does **not**
change Python or C++ Option-24 science or publication identities.

## Canonical source defect

In XSTAR Fortran 2.59g `pprint.f90`, Option 24 reads the current ion record with
`drd(..., nidti, ...)`, but then resolves the ion pointer with:

```fortran
jkk=masterdata%idat1(nidt+np1i-1)
```

Here `nidt` is stale from a different record. The analogous Option-19 path uses
the current ion-record length correctly:

```fortran
jkk=masterdata%idat1(nidti+np1i-1)
```

The Option-24 typo can therefore print He II using stale H I continuum/level
locals. This is a Fortran text-publication defect, not missing C++/Python RRC
science. The clean port metadata must not be corrupted to reproduce it.

## Public benchmark gate

The immutable frozen comparator remains at
`qualification/frozen/option23/compare_step_log_science.py`. The public harness
now calls `qualification/current/compare_step_log_science.py`, which imports the
frozen comparator and changes only the Option-24 final semantic gate:

1. Common-row Option-24 numeric and energy science must satisfy the frozen <1%
   tolerance.
2. Exact inventory is accepted.
3. Non-exact inventory is accepted only when every candidate-only identity is
   clean `he_ii` and the largest reference-only absolute tail is `<1e-15`.
4. Any candidate-only non-He-II identity or material reference-only tail still
   rejects Option 24.

The public output now reports:

```text
V064812345332_STEP_OPTION24_NUMERIC_SCIENCE=ACCEPT
V064812345332_STEP_OPTION24_INVENTORY_EXACT=NO
V064812345332_STEP_OPTION24_FORTRAN_STALE_LOCAL_QUIRK=ACCEPT
V064812345332_STEP_OPTION24_SCIENCE=ACCEPT
```

## Version labeling

The Python-controller host output now labels the two versions independently:

```text
xstar_tools package version 0.6.67
xstar_tools science revision 0.6.48.12.3.45.3.3.8
```

The frozen science revision and ABIs are unchanged.
