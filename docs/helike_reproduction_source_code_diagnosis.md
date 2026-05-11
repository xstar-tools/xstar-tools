# He-like local-output reproduction source-code diagnosis

This note records the v0.3.141 interpretation of the C V / O VII / Mg XI / Ca XIX same-run XSTAR reproduction benchmark.

## Benchmark status

The benchmark now compares the same-run XSTAR targets extracted from `xout_abund1.fits` and `xout_lines1.fits` with the full-global local-state solver path using the `xstar-local-state` preset.
The comparison table includes `f/i/r`, `R=f/i`, `G=(f+i)/r`, L2 distance, residuals, solver-to-XSTAR ratios, and a lightweight source-code-gap diagnosis.

The current residual pattern from the user run is common across all four ions:

```text
solver forbidden fraction is too high
solver intercombination fraction is generally too low
solver resonance fraction is too low
```

This is the same qualitative residual reported before the API cleanup.  The recent API reorganization did not intentionally change `xstar_element_solver.py`; the solver physics file is unchanged between the v0.3.127 baseline and v0.3.140.  The new benchmark releases changed plumbing, path resolution, line-table conversion, and reporting so the discrepancy is now visible in one four-ion table.

## XSTAR source-code path that matters

The relevant XSTAR source-code path is:

```text
calc_hmc_ion.f90  -> population matrix rates
ucalc.f90 type 50 -> bound-bound escaped decay and photoexcitation
calc_emis_ion.f90 -> emergent local line output
pescl.f90         -> line escape probability from tau0
```

For type-50 bound-bound line radiation, `ucalc.f90` computes an escaped downward rate and a lower-to-upper photoexcitation rate.  The branch then swaps the returned rates so that the final matrix-facing roles are:

```text
ans1 = lower-to-upper photoexcitation
ans2 = upper-to-lower escaped decay
```

The line-pumping term depends on the local XSTAR radiation field and line escape context:

```text
sigma = 0.02655 * flin * wavelength_cm / vtherm
ans_photo = sigma * bremsa(nb1) * vtherm / c * flinabs(ptmp1) * max(0,1-cfrac)
```

The escaped decay term uses directional escape probabilities:

```text
ans_decay = A * (ptmp1 + ptmp2)
ptmp1 = pescl(tau1) * (1-cfrac)
ptmp2 = pescl(tau2) * (1-cfrac) + 2*pescl(tau1+tau2)*cfrac
```

For emergent local line output, `calc_emis_ion.f90` uses the same swapped roles:

```text
fline(1) = max((ans2*upper_population - ans1*lower_population) * E * ptmp1, 0)
fline(2) = max((ans2*upper_population - ans1*lower_population) * E * ptmp2, 0)
```

## Current source-code gaps in xstar-atomic

The benchmark exposes three likely source-code gaps.

1. **Type-50 photoexcitation is still audit-only.**
   The population matrix does not yet inject the real XSTAR lower-to-upper type-50 photoexcitation term based on `bremsa(nb1)`, `flinabs(ptmp1)`, and `cfrac`.

2. **The matrix still uses a scalar type-50 escape fallback for many transitions.**
   The `xstar-local-state` preset uses `type50_bound_bound_treatment=xstar-line-escape-and-pumping` with `type50_escape_factor=0.35` when a true per-line tau context is not available in the matrix transition row.  The same-run `xout_lines1.fits` resonance depths imply very different escape probabilities for C V, Mg XI, and Ca XIX, so one scalar cannot reproduce all ions or all physical conditions.

3. **The local radiation field is still a proxy.**
   The preset uses an `xstar-powerlaw` proxy radiation field.  XSTAR `ucalc.f90` uses the local `epi` grid and `bremsa(nb1)` array.  To reproduce arbitrary `Te`, `ne`, and `xi`, the API must ingest or reconstruct the same-run local radiation field, not only an approximate power-law proxy.

## Why the old discrepancy looked fixed before

Earlier improvements matched some cases using XSTAR reference-depth post-processing, escape-factor scans, or diagnostic scale searches.  Those were useful audits, but they were not yet a complete source-code-equivalent matrix implementation.  The current benchmark is stricter: it compares one common four-ion workflow against exact same-run XSTAR line targets and prints the remaining residuals.

## Next implementation targets

The next physics releases should be audit-first, then opt-in:

1. Add a benchmark/matrix audit that maps same-run `xout_lines1.fits` triplet depths into the type-50 matrix rows and reports the effect before solving.
2. Port real XSTAR type-50 photoexcitation into the population matrix using `epi`, `bremsa(nb1)`, `flinabs(ptmp1)`, `cfrac`, and `vtherm`.
3. Replace `xstar-powerlaw` proxy radiation with a same-run radiation-field reader from XSTAR outputs where possible.
4. Re-run the four-ion suite over C V, O VII, Mg XI, and Ca XIX and require the output table to report `f/i/r`, `R`, `G`, and L2 for both XSTAR and solver.
