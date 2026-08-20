# 0.6.82.30.8.1 - Fe Type-57 packed-shell ownership correction

## Why `.30.8` is rejected

The host result for `0.6.82.30.8` is scientifically unchanged from the earlier
Fe failure:

```text
C++:     log(T)=5.29, ntotit=24,8,8
FORTRAN: log(T)=5.60, ntotit=13,1,1
```

STEP science, material, spectrum, and `ntotit` all reject.  The Type-75/96
endpoint correction in `.30.8` is source-correct, but it is not the controlling
error for this model.  `.30.8` is therefore immutable and `.30.8.1` supersedes
it.

## Atomic-data inventory conclusion

Review of XSTAR Manual 2.5x, Mendoza et al. (2021) Appendix A, and the supplied
canonical FORTRAN source finds no missing executable Fe-specific family that
should simply be enabled in C++:

- Type 80 enters `ucalc.f90` and immediately exits;
- Type 83 is Fe UTA **level metadata** (rate type 13); its `ucalc` branch exits,
  while `calc_rates_level_lte.f90` copies the raw level payload into
  `leveltemp`;
- Type 84 exits before its dormant spectator-Auger implementation;
- the active Fe-specific physical families 37/75/81/82/85/86/96/97 are already
  represented in C++.

Adding a Type-80 or Type-84 physical kernel would therefore depart from this
FORTRAN oracle.

## Source mismatch isolated in Type 57

Canonical `ucalc.f90` Type 57 reads

```fortran
i57=masterdata%idat1(np1i)
call calt57(tz,xnx,e1,ep,i57,cion,crec,lun11,lpri)
```

so `calt57` receives the first packed INTEGER of the **Type-57 record**.
Mendoza et al. Appendix A defines Type 57 as

```text
i1=n, i2=L, i3=2J, i4=level, i5=ion
```

and defines Type 83 Fe UTA level metadata as

```text
i1=1, i2=level, i3=ion
```

The `.30.8` C++ lowerer retained both values but the evaluator called
`type57_coefficients()` with the reconstructed `principal_n` from the Type-13
level table.  That is not source-equivalent: for a Type-83 UTA level the first
integer is the fixed metadata value `1`, not the Type-57 shell `n`.

The retained FORTRAN Fe final evaluation reports 16,948 Type-57 evaluations,
so this is a materially exercised path rather than a dead branch.

## `.30.8.1` production correction

`local_zone_engine.cpp` now passes the literal Type-57 packed `i1` to the
translated `calt57` kernel.  The duplicated Type-13 value remains available for
provenance but can no longer override the Type-57 record.

No Type-57 formula, endpoint, energy difference, statistical weight,
heating/cooling sign, matrix placement, controller, DSEC ordering, solver,
transport, science revision, or ABI changes.

## Host gate

Build and run only the Fe candidate against retained `.30.6` FORTRAN:

```bash
make -C src/xstar_tools/xstar/cpp -j2 xstar-cpp

python tools/qualification/run_fe_reference_host_smoke_0_6_82_30_8_1.py cpp-compare \
  --package "$PWD" \
  --data-dir ../xstar/data \
  --fortran-reference-root ../xstar_tools-0.6.82.30.6/run_final_qualification_models_0682306/fortran \
  --output-root "$PWD/run_fe_reference_06823081" \
  --replace
```

`--fortran-reference-root` must be the parent `fortran` directory; the runner
appends `fe_reference_ne1e8` itself.

If this source correction does not close Fe, preserve `.30.8.1` unchanged and
make `.30.8.2` with matched-temperature fixed-state rate instrumentation.  Do
not rerun already accepted C/O/Ca/C5, parameter, spectrum, `ncn2`, density, or
`npass` cases.

## Performance work after correctness

The rejected `.30.8` C++ host run is roughly 5.1x slower than retained FORTRAN
(352.69 s internal C++ timing versus 68.54 s FORTRAN).  Fixed-record traversal
(~187.53 s) and science-FITS/publication (~129.6/~130.0 s) dominate; fixed-rate
arithmetic itself is only ~12.90 s.  After Fe science closes, optimize these
surfaces with precomputed source-ordered active-record schedules, reuse of
lowered descriptors/geometry, and reduced writer work while preserving exact
science/output order.  Do not combine such performance changes with the
`.30.8.1` correctness candidate.
