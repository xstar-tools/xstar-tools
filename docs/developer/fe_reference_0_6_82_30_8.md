# 0.6.82.30.8 — isolated Fe reference correction

## Scope

`0.6.82.30.8` addresses only the rejected `fe_reference_ne1e8` C++ model from the
`0.6.82.30.6` eight-model gate.  It does not rerun FORTRAN and does not replay
already accepted C/O/Ca/C5, parameter-axis, spectrum, `ncn2`, density, or
`npass` cases.

Canonical retained reference:

```text
0.6.82.30.6/run_final_qualification_models_0682306/fortran/fe_reference_ne1e8
```

The rejected state was qualitatively large, not a publication-only difference:
FORTRAN reached approximately `log(T)=5.60`, `ntotit=13,1,1`, while C++ reached
approximately `log(T)=5.29`, `ntotit=24,8,8`.

## Atomic-data/source audit

The audit compared three authorities:

1. XSTAR Manual 2.5x Section 12.1.2;
2. Mendoza et al. (2021), *Atoms* 9, 12, Appendix A;
3. the supplied canonical FORTRAN 2.59g `ucalc.f90` and `calc_hmc_ion.f90`.

The C++ active-type set already contains the executable Fe-specific physical
families relevant to the canonical source: 37, 75, 81, 82, 85, 86, 96 and 97.
Type 80 enters `ucalc` and immediately exits; Type 83 is level metadata and its
`ucalc` branch immediately exits; Type 84 also exits before the dormant
spectator-Auger calculation.  Type 85 is implemented through the Fe-K
`pexs`/`phintfo` path, and Type 86 has a dedicated Auger/radiative-width path.
Thus no missing executable Fe-specific data-type branch was found.

For rate type 41, canonical `calc_hmc_ion.f90` deliberately skips the generic
energy-ordering rule (`lrtyp.ne.7 .and. lrtyp.ne.41`), so literal Auger endpoint
direction must be retained.  Existing Type-86 lowering already follows that
contract.

## Root cause

The concrete mismatch is the packed endpoint identity for Type 75 and the same
historical convention in Type 96.

Canonical Type 75:

```fortran
idest3=idat(np1i+nidt-1)
idest4=idat(np1i+nidt-3)
idest2=idat(np1i+nidt-2)+nlev-1
idest1=idat(np1i-1+nidt-3)
```

Because `np1i` is the first packed integer and FORTRAN indexing is one-based,
`idest1` is packed integer `i2`.  Appendix A identifies the Type-75 payload as:

```text
i1 = ion_N
i2 = k_N
i3 = ion_(N-1)
i4 = i_(N-1)
i5 = ion_N
```

Therefore C++ must read:

```text
idest1 = ii[nidt-4] = k_N
idest2 = nlev + ii[nidt-2] - 1
```

The old C++ lowerer instead used `ii[nidt-3]`, which is `ion_(N-1)`: a global
ion identity incorrectly treated as a local level endpoint.  In the compact
basis this can route satellite rates into an unrelated/terminal row and is
consistent with the excessive retained-state population seen in the failed Fe
run.

Canonical Type 96 uses the same endpoint expressions, so it receives the same
correction.

## Production change

Only `src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp` changes numerically:

- Type 75 `idest1`: `ii[size-3] -> ii[size-4]`;
- Type 96 `idest1`: `ii[size-3] -> ii[size-4]`;
- the private literal source-UCalc endpoint helper uses the same pair for Types
  75 and 96.

No rate coefficient, exponential, heating/cooling equation, Type-85/86 kernel,
controller, DSEC ordering, transport, or solver logic is changed.

## Host qualification

Build C++ and run only the Fe candidate against the retained FORTRAN directory:

```bash
make -C src/xstar_tools/xstar/cpp -j2 xstar-cpp

python tools/qualification/run_fe_reference_host_smoke_0_6_82_30_8.py cpp-compare \
  --package "$PWD" \
  --data-dir ../xstar/data \
  --fortran-reference-root ../xstar_tools-0.6.82.30.6/run_final_qualification_models_0682306/fortran \
  --output-root "$PWD/run_fe_reference_0682308" \
  --replace
```

Required final closure is `FE_REFERENCE_0682308_RESULT=ACCEPT`.  If it remains
rejected, preserve `.30.8` unchanged and diagnose `.30.8.1` at the first
matched-temperature fixed-state/rate divergence rather than adding speculative
Fe formula changes to this candidate.
