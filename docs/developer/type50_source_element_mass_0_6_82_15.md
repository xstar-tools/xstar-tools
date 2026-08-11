# 0.6.82.15 Type-50 source-parent element mass

## Scope

`0.6.82.15` corrects the ownership of the nuclear mass used by the Type-50 line-profile calculation. It does not change the accepted science revision or any public ABI.

Canonical XSTAR 2.59g `ucalc.f90` label 50 resolves the line's ion parent with `npar(line)`, resolves the element parent with `npar(ion)`, reads that element record, and sets the nuclear mass from its second REAL (`rdat1(np1r2+1)`). `binemislin.f90` performs the same source traversal for line-profile publication.

The previous port instead selected a modern periodic-table mass by atomic number during ATDB lowering. That is not source-faithful, and the mass enters

```text
vtherm = sqrt((vturb*1e5)^2 + (1.29e6/sqrt(a/t4))^2)
sigma  = 0.02655 * f * wavelength * 1e-8 / vtherm
```

so ppm-scale mass differences propagate directly into Type-50 line-center opacity, transported optical depth, high-`tau` escape probability, and ultimately DSEC convergence.

## Implementation

- C++ `xstar_atdb_runtime.cpp` follows `ion_record -> element_record` and reads the second source REAL for every lowered record and line identity.
- Python `type50_profile_provenance.py`, `native_fixed_program.py`, and `physical_runner.py` use the same source parent value.
- Historical Z=1--30 mass tables remain only as guarded fallbacks for compact synthetic fixtures without a valid element parent record.
- The `0.6.82.14` source-rounded `pescl` pi repair remains unchanged.

## Qualification

Run:

```bash
python tools/qualification/check_type50_source_element_mass_0_6_82_15.py
```

With `XSTAR_SOURCE_ROOT` set, the checker also verifies the literal FORTRAN Type-50 parent traversal and mass read. Host H+He+C `rlogxi=-3` and `-2` remain required before scientific closure is claimed.
