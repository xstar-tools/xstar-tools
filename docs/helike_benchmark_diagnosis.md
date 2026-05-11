# He-like local-state benchmark diagnosis after the API reorganization

This note documents the benchmark interpretation for the C V, O VII, Mg XI, and
Ca XIX same-run XSTAR comparisons.  The goal is to separate three different
questions:

1. What target values did the same XSTAR run write to `xout_abund1.fits` and
   `xout_lines1.fits`?
2. Which `xstar-atomic` solver branch is being compared to those targets?
3. Which XSTAR source-code paths are still not fully ported into the Python
   population matrix and emissivity construction?

## Same-run target extraction

The benchmark target is defined by XSTAR output files, not by a generic target
CSV from another run.

- `xout_abund1.fits` supplies local `T`, `ne`, `log xi`, and the selected ion
  fraction.
- `xout_lines1.fits` supplies the same-run He-like triplet line strengths.
- `R=f/i`, `G=(f+i)/r`, and `L2=0` for the XSTAR target are now written beside
  the XSTAR `f/i/r` fractions.

## XSTAR source-code path that matters

The relevant source-code chain in the uploaded XSTAR tree is:

```text
calc_hmc_ion.f90 -> ucalc.f90 -> matrix rates
calc_emis_ion.f90 -> emergent line channels / fline construction
```

Important details from `calc_hmc_ion.f90`:

- For line rate type 4, XSTAR derives inward and outward optical depths
  (`tau1`, `tau2`) for the line.
- It computes escape probabilities
  `ptmp1=pescl(tau1)*(1-cfrac)` and
  `ptmp2=pescl(tau2)*(1-cfrac)+2*pescl(tau1+tau2)*cfrac`.
- These escape probabilities are passed directly into `ucalc`.

Important details from `ucalc.f90` type 50:

- The escaped radiative decay branch is computed as
  `ans1 = A * (ptmp1 + ptmp2)` before the final branch swap.
- The line-pumping/photoexcitation branch uses the line cross section,
  continuum bin mapping, and local radiation field:
  `ans2 = sigma * bremsa(nb1) * vtherm / c * flinabs(ptmp1)`.
- It is multiplied by `max(0, 1-cfrac)`.
- At the end of the branch, XSTAR swaps the rates so the final returned
  `ans1` is lower-to-upper photoexcitation and the final returned `ans2` is
  upper-to-lower escaped decay.

Important details from `calc_emis_ion.f90` and the existing Python audits:

- XSTAR line output is not just raw `population * A * energy`.
- The emitted line channel depends on the net `ucalc` ans1/ans2 terms,
  escape probabilities, optical depths, abundance factors, and the selected
  strong-line/output channel.

## Why the v0.3.137 quick benchmark looked different from older local-state validation

The v0.3.137 `--run-solver` benchmark successfully reached the solver, but it
extracted `summary["he_like_triplet"]`.  That is a lightweight public workflow
summary from the current He-like ion line rows.  It is useful as a quick API
check, but it is not the same source-code-first path used by the earlier
local-state validation sequence.

The earlier v0.3.123--v0.3.127 all-ion local-state validation used the generated
solver commands from `examples/51_run_helike_local_state_validation.py`, including
settings such as:

```text
--full-global-linear-solver xstar-lucy
--full-global-topology xstar-continuum-alias-superlevels
--inverse-recombination-mode xstar-ucalc
--ion-fraction-closure xstar-calc-ion-rates
--type50-bound-bound-treatment xstar-line-escape
--type50-escape-factor 0.35
--radiation-field-mode xstar-powerlaw
--radiation-bremsa-scale 1e18
```

Those settings exercise a more complete diagnostic branch and produce different
residuals from the quick workflow defaults.  Therefore the severe resonance
collapse seen for O VII, Mg XI, and Ca XIX in the v0.3.137 quick benchmark is
not evidence that recent API reorganization removed working physics.  It shows
that the benchmark was comparing XSTAR targets against the wrong solver branch.

## v0.3.139 benchmark rule

`examples/56_reproduce_xstar_local_outputs.py` now has two clear solver modes:

```bash
--solver-preset workflow-default
```

uses the simple public workflow solver.  This is useful for API smoke tests but
is not the preferred physics benchmark.

```bash
--solver-preset xstar-local-state
```

uses the source-code-first local-state validation settings from example 51 and
should be used for the C V / O VII / Mg XI / Ca XIX physics benchmark.

The benchmark CSV and Markdown outputs now include:

```text
xstar_f_fraction, xstar_i_fraction, xstar_r_fraction
xstar_R_f_over_i, xstar_G_f_plus_i_over_r, xstar_L2_to_xstar
solver_f_fraction, solver_i_fraction, solver_r_fraction
solver_R_f_over_i, solver_G_f_plus_i_over_r, solver_L2_to_xstar
solver_triplet_source
```

## Remaining physics work

No solver physics was changed in v0.3.139.  The following source-code paths still
need careful implementation or validation before claiming exact XSTAR agreement
under arbitrary `T`, `ne`, and `xi`:

1. Exact local radiation-field reconstruction: `epi`, `nbinc`, and
   `bremsa(nb1)` from the same XSTAR zone.
2. Full type-50 line pumping: final swapped ans1/ans2 with `flinabs`, `cfrac`,
   `vtherm`, and local continuum normalization.
3. `calc_emis_ion` net line-output construction, including optical-depth
   escape, abundance factors, and strong-line selection.
4. Ion-fraction and adjacent-ion source closure matching XSTAR `calc_ion_rates`
   and `istruc` behavior.
5. Regression tests over multiple physical conditions, not only the current
   four local-state reference zones.
