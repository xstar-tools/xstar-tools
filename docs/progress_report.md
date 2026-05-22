# XSTAR `atdb.fits` Python Reader Progress Report

> **v0.4.64 update:** translated `step`, `trnfrc`, `stpcut`, and `trnfrn`, validated them against direct compilation of the original Fortran, and composed the bounded first-pass radial shell around the accepted local `xstarcalc`. Zone 1 skips `step`; later first-pass zones execute it. `heatt` remains an explicit source-state handler. Reverse passes fail at missing `unsavd`, turbulent runs fail at missing `gsmooth`, and output writers remain blocked.

> **v0.3.208 update:** added a source-aligned live-state type-53 implementation (`epim`, `bremsam`, `bremsint`), complete `phint53` rate/heating/cooling evaluation, record/matrix parity, and selected-system integration after native types 51/50/71. The kernel agrees with a standalone compiled original `phint53.f90` case within `5e-8`. Real O VII acceptance, `phint53hunt`, and opacity/RRC-emissivity parity remain open.


> **v0.3.207 update:** the native type-71 parity gate now follows the source-specific endpoint order: `idest1` is the lower spectroscopic destination and `idest2` is the upper superlevel source. The user-provided O VII v0.3.206 audit showed exact native/probed type-71 rates and matrix coefficients; only the reused type-50 endpoint validator caused the false failure. No rate formula or production solver behavior changed.

> **v0.3.206 update:** `examples/95_audit_xstar_type50_type71_native_parity.py` adds source-code native parity for type 50 and type 71, and `examples/96_integrate_xstar_priority_native_type50_type71.py` replaces their validated selected-row coefficients after the v0.3.205 native-type-51 gate. Type-50 photoexcitation is accepted only from an explicit same-capture `bremsa(nb1)` context unless it is exactly zero from full covering or the XSTAR high-wavelength sentinel. The integration audit covers both selected-internal coefficients and fixed-external RHS terms, preserves all other families as probe-backed, and does not change the production expanded-basis solver.


> **v0.3.205 update:** `examples/94_integrate_xstar_priority_native_type51.py` now distinguishes the 636 type-51 terms in the six selected matrix rows from 310 reciprocal insertions in external matrix rows. All 636 selected-row terms are replaced natively; the 310 external-row terms are retained as explicit out-of-scope parity coverage and no longer block the selected-system readiness flag. The real O VII audit passes with a maximum hybrid/all-probe population change of approximately `2.75e-8`. Non-type-51 families remain probe-backed and the production expanded-basis solver is unchanged.

## 1. Project goal

The goal is to develop a Python reader for the large XSTAR atomic database FITS file:

```text
./xstar/data/atdb.fits
```

The file is used internally by XSTAR for atomic data needed in photoionization, recombination, line emission, continuum opacity, and X-ray spectral calculations. Because the file is too large to upload directly, the development approach has been:

1. Inspect the FITS structure locally.
2. Use the XSTAR Fortran source code to decode the packed data model.
3. Build Python readers that reproduce the XSTAR record hierarchy.
4. Add physics-specific decoders gradually.
5. Validate each decoder against known X-ray atomic features.

The large FITS file never needs to leave the local machine.

---

## 2. FITS file structure discovered

The first inspection showed that `atdb.fits` is **not** organized as many semantic FITS table extensions. Instead, it is a compact packed database with only five HDUs:

| HDU | Name | Meaning | Size / rows |
|---:|---|---|---:|
| 0 | `PRIMARY` | Empty primary HDU | — |
| 1 | `POINTERS` | Packed record headers and offsets | 1 row, vector length 12,167,920 |
| 2 | `REALS` | Packed real-valued record payloads | 1 row, vector length 199,199,476 |
| 3 | `INTEGERS` | Packed integer-valued record payloads | 1 row, vector length 6,205,274 |
| 4 | `CHARS` | Packed byte/string payloads | 1 row, vector length 753,844 |

The inspected file size was approximately:

```text
830.709 MB
```

The key conclusion is that `atdb.fits` must be read as an XSTAR-specific packed binary database, not as a normal FITS table database.

---

## 3. Packed record layout decoded

From the FITS inspection and XSTAR Fortran routines, especially the packed-table reader logic, each record is represented by a 10-integer pointer/header block:

```text
POINTERS[0]  original record pointer/index
POINTERS[1]  data type
POINTERS[2]  rate type
POINTERS[3]  continuation flag
POINTERS[4]  number of real values
POINTERS[5]  number of integer values
POINTERS[6]  number of character bytes
POINTERS[7]  1-based pointer into REALS
POINTERS[8]  1-based pointer into INTEGERS
POINTERS[9]  1-based pointer into CHARS
```

This was validated using `data_type=13`, element records. Example records:

```text
Record 1
  data_type=13, rate_type=11
  reals    = [1.0, 1.01]
  integers = [1, 1]
  chars    = 'hydrogen'

Record 588
  data_type=13, rate_type=11
  reals    = [0.1, 4.0]
  integers = [2, 2]
  chars    = 'helium'
```

---

## 4. Database inventory found

The packed database contains:

```text
n_records   = 1,216,792
n_reals     = 199,199,476
n_integers  = 6,205,274
n_chars     = 753,844
n_elements  = 30
n_ions      = 465
```

The maximum number of level records found for a single ion is:

```text
max_levels_per_ion_from_level_records = 744
```

---

## 5. Elements decoded

There are 30 element records, `data_type=13`, `rate_type=11`.

The element record format is now understood as:

```text
reals[0]    abundance relative to H
reals[1]    atomic weight
integers[0] atomic number Z
integers[1] atomic number Z, repeated
chars       element name
```

Decoded elements include:

| Z | Symbol | Name | Abundance | Atomic weight |
|---:|---|---|---:|---:|
| 1 | H | hydrogen | 1.0 | 1.01 |
| 2 | He | helium | 0.1 | 4.0 |
| 6 | C | carbon | 3.70e-4 | 12.01 |
| 7 | N | nitrogen | 1.10e-4 | 14.01 |
| 8 | O | oxygen | 6.80e-4 | 16.0 |
| 10 | Ne | neon | 2.80e-5 | 20.18 |
| 12 | Mg | magnesium | 3.50e-5 | 24.31 |
| 14 | Si | silicon | 3.50e-5 | 28.09 |
| 16 | S | sulfur | 1.60e-5 | 32.06 |
| 18 | Ar | argon | 4.50e-6 | 39.95 |
| 20 | Ca | calcium | 2.10e-6 | 40.08 |
| 26 | Fe | iron | 2.50e-5 | 55.85 |
| 28 | Ni | nickel | 2.00e-6 | 58.71 |

The database also contains low-abundance elements such as Li, Be, B, F, Na, Al, P, Cl, K, Sc, Ti, V, Cr, Mn, Co, Cu, and Zn.

---

## 6. Important data types found

The database contains many data types. The most important decoded or partially decoded types are:

| Data type | Count | Current interpretation |
|---:|---:|---|
| 1 | 181 | Radiative recombination: Aldrovandi & Pequignot |
| 2 | 80 | Charge exchange with H0: Kingdon & Ferland |
| 6 | 38,235 | Level data |
| 7 | 163 | Dielectronic recombination: Aldrovandi & Pequignot |
| 13 | 30 | Element data |
| 14 | 465 | Ion data |
| 22 | 3 | Dielectronic recombination: Storey |
| 30 | 30 | Hydrogenic radiative recombination: Gould & Thakur |
| 49 | 287,180 | OP inner-shell photoionization cross sections |
| 50 | 730,369 | OP line radiative rates |
| 51 | 23,232 | OP/CHIANTI line collisional rates |
| 53 | 12,091 | OP photoionization cross sections |
| 54 | 1,266 | H-like radiative rates / Bautista H-like ion data |
| 56 | 87,231 | Tabulated effective collision strengths |
| 57 | 5,608 | Effective charge for collisional ionization |
| 59 | 379 | Verner photoionization cross sections |
| 60 | 342 | Calloway H-like collision strength |
| 62 | 72 | Calloway H-like collision strength |
| 63 | 6,015 | Bautista n,l algorithmic collision data |
| 68 | 52 | He-like collision strengths by Zhang & Sampson |
| 69 | 120 | Kato & Nakazaki fit to He-like collision strengths |
| 70 | 35 | Photoionization coefficients for superlevels |
| 71 | 2,343 | Radiative superlevel-to-spectroscopic-level rates |
| 72 | 63 | Autoionization rates for satellite levels |
| 73 | 427 | Satellite-level collision strengths, He-like ions |
| 74 | 1,114 | Delta functions added to PI cross sections for DR |
| 75 | 16 | Autoionization data for Fe XXIV satellites |
| 76 | 85 | Two-photon decay |
| 77 | 2,182 | Collisional rates from type 71 |
| 81 | 240 | Bhatia Fe XIX collision strengths |
| 82 | 986 | Fe UTA radiative rates |
| 83 | 986 | Fe UTA level data |
| 85 | 42 | Iron K PI cross sections, spectator Auger summed |
| 86 | 8,882 | Iron K Auger data |
| 95 | 982 | Bryans collisional ionization / CI total rates |
| 98 | 841 | CHIANTI 2016 collisional excitation rates |
| 99 | 458 | Superlevel / newer bound-free style records, still under investigation |

---

## 7. Important rate types found

Important rate types include:

| Rate type | Count | Interpretation |
|---:|---:|---|
| 1 | 411 | Ground-state ionization |
| 3 | 119,892 | Bound-bound collision |
| 4 | 733,824 | Bound-bound radiative |
| 5 | 6,199 | Bound-free collision from levels |
| 7 | 300,890 | Bound-free radiative from levels |
| 8 | 915 | Total recombination |
| 9 | 89 | Two-photon decay |
| 11 | 30 | Element data |
| 12 | 465 | Ion data |
| 13 | 39,221 | Level data |
| 14 | 2,343 | Radiative superlevel to spectroscopic level |
| 15 | 492 | Collisional ionization total rate |
| 23 | 2,182 | Collisional superlevel to spectroscopic level |
| 40 | 79 | Collisional ionization from superlevels |
| 41 | 8,882 | Auger decay / Fe K Auger |
| 42 | 877 | Fluorescence / Auger-related |

---

## 8. Atomic hierarchy decoded

A second script built the hierarchy:

```text
element → ion → level records → process records
```

This follows the same logic as XSTAR’s internal pointer setup: element records contain ion records, and ion records contain level and rate/process records until the next ion or element header.

### O VIII example

O VIII was decoded as:

```text
element: O
Z = 8
ion_stage = 8
charge = O7p
ion record = 22629
ion record integers = [8, 8, 36]
ion string = 'o_viii'
```

This confirms:

```text
ion_stage = first integer in ion record
ion_index = last integer in ion record
```

---

## 9. Level records decoded

Level records are `data_type=6`, `rate_type=13`.

The current decoded level interpretation is:

```text
rdat[0] = level energy above ground, eV
rdat[1] = statistical weight g
rdat[2] = effective n-like quantity
rdat[3] = ionization potential / continuum reference energy, eV

idat[0] = principal n
idat[1] = multiplicity-like value
idat[2] = orbital angular momentum l
idat[3] = Z
idat[4] = level index
idat[5] = ion/global ion index
chars   = level label
```

### O VIII level validation

O VIII level 1:

```text
record = 22630
data_type = 6
rate_type = 13
integers = [1, 2, 0, 8, 1, 36]
chars = '1s1.2S_1/2'
```

This is correctly identified as the O VIII ground level.

O VIII has 33 decoded level records.

---

## 10. Radiative line records decoded

Radiative line records are primarily `data_type=50`, `rate_type=4`.

The current decoded interpretation is:

```text
idat[0] = lower level
idat[1] = upper level
idat[2] = Z
idat[3] = ion index

rdat[0] = wavelength, Angstrom
rdat[2] = A_ul, s^-1
chars   = transition label
```

The code also computes:

```text
energy_eV = 12398.419843 / wavelength_A
f_osc_from_A = oscillator-strength estimate from A_ul and wavelength
```

### O VIII Lyα validation

Search:

```bash
python xstar_atomic_extract_lines_v2.py ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --line-search --wavelength-min 18.8 --wavelength-max 19.1
```

Recovered:

| Ion | Lower | Upper | Wavelength Å | Energy keV | A s^-1 |
|---|---|---|---:|---:|---:|
| O VIII | 1s1.2S_1/2 | 2p 2P_3/2 | 18.9671097 | 0.653679 | 2.56616e12 |
| O VIII | 1s1.2S_1/2 | 2p 2P_1/2 | 18.9725170 | 0.653493 | 2.56616e12 |

The wavelength from the record agrees with the wavelength reconstructed from level-energy differences at the level of about `3.4e-5 Å`.

### Other line validations

The same decoder recovered:

| Ion | Feature | Wavelengths |
|---|---|---|
| O VII | He-like triplet / nearby components | 21.602, 21.804, 21.807, 22.101 Å |
| Ne X | Lyα doublet | 12.1321, 12.1375 Å |
| Fe XXVI | Lyα doublet | 1.7780, 1.7834 Å |

This validates the line decoder across H-like, He-like, low-Z, and high-Z ions.

---

## 11. Photoionization records decoded

Photoionization records decoded so far:

```text
data_type=53, rate_type=7
```

These are OP photoionization cross-section records.

The current decoded format is:

```text
rdat = [E_1, sigma_1, E_2, sigma_2, ...]

E_i          = energy above threshold, Rydberg
sigma_i      = raw cross section in megabarns
sigma_cm2    = sigma_i × 1e-18
threshold_eV = ionization_potential_eV - level_energy_eV
photon_E_eV  = threshold_eV + E_i × 13.605692
```

### O VIII ground-state photoionization validation

Search:

```bash
python xstar_atomic_extract_photoionization_v1.py ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --search --data-type 53 --rate-type 7 --lower-level 1
```

Result:

```text
record = 22664
lower_level = 1
lower_label = 1s1.2S_1/2
threshold_eV_from_level = 871.4000 eV
n_grid_points = 72
sigma_threshold_cm2 = 9.85e-20 cm2
```

This is physically consistent with the hydrogenic scaling:

```text
sigma_H / Z^2 ≈ 6.3e-18 / 8^2 ≈ 9.84e-20 cm2
```

### O VII ground-state photoionization validation

For O VII, ground-level search over all `rate_type=7` records returned six `data_type=53` components with the same threshold:

```text
lower_level = 1
lower_label = 1s2.1S_0
threshold_eV_from_level = 739.3000 eV
```

The dominant component has:

```text
record = 21634
sigma_threshold_cm2 = 2.545e-19 cm2
n_grid_points = 42
```

The other components are weaker, with threshold cross sections around `10^-22–10^-23 cm2`.

Conclusion: type-53 can represent multiple photoionization components for the same level. They should be preserved separately until XSTAR’s exact summation behavior is reproduced.

---

## 12. Collisional excitation records decoded

Collisional excitation work is currently divided into several cases.

### 12.1 Type 56: tabulated effective collision strengths

`data_type=56`, `rate_type=3` is decoded as tabulated effective collision strengths:

```text
first half of rdat  = log10(T/K) grid
second half of rdat = effective collision strength Υ(T)
```

The excitation/de-excitation rates are computed as:

```text
q_ij(T) = 8.626e-6 Υ(T) exp(-ΔE/kT) / [g_i sqrt(T)]
q_ji(T) = 8.626e-6 Υ(T)              / [g_j sqrt(T)]
```

with `T` in K and rates in `cm3 s-1`.

#### O VIII Lyα validation

O VIII has:

```text
n_collision_records = 322
counts_by_data_type:
  type 56 = 3
  type 63 = 319
```

The O VIII Lyα region gives three type-56 records:

| Transition | Type | Upper | Wavelength Å |
|---|---:|---|---:|
| 1s → 2p 2P_3/2 | 56 | level 3 | 18.9671 |
| 1s → 2s 2S_1/2 | 56 | level 4 | 18.9722 |
| 1s → 2p 2P_1/2 | 56 | level 2 | 18.9725 |

For `1s → 2p 2P_3/2`:

| T K | Υ | q_exc cm3 s^-1 | q_deexc cm3 s^-1 |
|---:|---:|---:|---:|
| 1e6 | 0.0308667 | 6.76e-14 | 6.66e-11 |
| 3e6 | 0.720699 | 1.43e-10 | 8.97e-10 |
| 1e7 | 1.74571 | 1.12e-9 | 1.19e-9 |

The strong temperature dependence of `q_exc` is physically sensible because the excitation energy is about 654 eV.

### 12.2 Type 63: Bautista n,l algorithmic collision records

`data_type=63`, `rate_type=3` records are compact algorithmic collision records. They store no real-valued grid.

The record contains only integer-level mapping such as:

```text
[idat[0], idat[1], idat[2], idat[3], idat[4]]
≈ [ion_stage, lower_level, upper_level, Z, ion_index]
```

The source format has been renamed from the misleading:

```text
hydrogenic_Bautista_type63_metadata_only
```

to:

```text
bautista_nl_algorithm_type63
```

because this format also appears for O VII, not only H-like ions.

### 12.3 Type 63 evaluator implemented for nf != ni and |Δl| = 1

A patched script, `xstar_atomic_extract_collisions_v2b.py`, implements the `nf != ni`, `|Δl| = 1` branch by porting the relevant logic from:

```text
anl1.f90
erc.f90
impactn.f90
impcfn.f90
expint.f90
eint.f90
szcoll.f90
```

Because the literal Fortran branch selector gave zero for some resolved-level records, an explicit lower/upper angular-momentum branch selector was added. The diagnostic fields include:

```text
type63_aa1
type63_aa1_fortran_selector
type63_lower_shell_l
type63_upper_shell_l
type63_angular_sum
type63_se_shell_cm3_s
type63_sd_shell_cm3_s
eval_diagnostic
```

### 12.4 O VII type-63 validation

O VII collision summary:

```text
n_collision_records = 211
counts_by_data_type:
  type 63 = 211
```

O VII direct ground excitations found:

| Transition | Wavelength Å | Type |
|---|---:|---:|
| 1s2.1S_0 → 1s1.3p1.1P_1 | 18.6270 | 63 |
| 1s2.1S_0 → 1s1.4p1.1P_1 | 17.7680 | 63 |
| 1s2.1S_0 → 1s1.5p1.1P_1 | 17.3960 | 63 |

With the patched v2b script, O VII type-63 rates are now evaluated. Example:

```text
O VII: 1s2.1S_0 → 1s1.5p1.1P_1
wavelength = 17.396 Å

T = 1e6 K:   q_exc = 4.08e-14 cm3 s-1
T = 3e6 K:   q_exc = 1.81e-11 cm3 s-1
T = 1e7 K:   q_exc = 1.21e-10 cm3 s-1
```

The method is marked:

```text
eval_method = type63_anl1_erc_nf_ne_ni_delta_l_1
eval_diagnostic = evaluated_with_explicit_branch_selector
```

### 12.5 Type 63 diagnostics

For transitions that do not meet `|Δl| = 1`, the script correctly leaves the rate unevaluated and reports:

```text
eval_method = delta_l_not_equal_1
```

For same-n l-changing records, the code keeps:

```text
eval_method = type63_same_n_lmixing_not_yet_implemented
```

because that requires the `amcrs` branch and density/impact-parameter physics.

---

## 13. Emissivity table builder started

A first emissivity-table builder was created:

```text
xstar_atomic_make_emissivity_table_v1.py
```

It joins:

```text
levels + radiative lines + collision evaluations
```

and produces one row per:

```text
radiative line × matching collision record × temperature
```

It computes direct-excitation coronal approximation coefficients:

```text
line_photon_emissivity_coeff_cm3_s
    = q_excitation_cm3_s × branching_ratio

line_energy_emissivity_coeff_erg_cm3_s
    = q_excitation_cm3_s × branching_ratio × hν
```

The volume emissivity can then be computed as:

```text
j_line = n_e n_ion × line_energy_emissivity_coeff_erg_cm3_s
```

The branching ratio is currently computed as:

```text
branching_ratio = A_ul / Σ_l A_ul
```

where the denominator is the sum of decoded radiative A-values from the same upper level.

This is not yet a full level-population solver. It is a first direct-excitation emissivity product.

---

## 14. Python scripts created so far

The following scripts have been created during this development:

| Script | Purpose |
|---|---|
| `inspect_xstardb_fits.py` | Generic FITS schema inspector for large files |
| `xstar_atomic_reader_inspect.py` | Low-level packed FITS reader for POINTERS/REALS/INTEGERS/CHARS |
| `xstar_atomic_hierarchy.py` | Builds element → ion → record hierarchy |
| `xstar_atomic_extract_basic.py` | First basic level/line/continuum extraction |
| `xstar_atomic_extract_lines_v2.py` | Validated level and radiative-line decoder with line search |
| `xstar_atomic_extract_photoionization_v1.py` | Type-53 photoionization cross-section decoder |
| `xstar_atomic_extract_collisions_v1.py` | First collision extractor: type 56 and metadata for type 63 |
| `xstar_atomic_extract_collisions_v2.py` | First attempted type-63 evaluator |
| `xstar_atomic_extract_collisions_v2b.py` | Patched type-63 evaluator with explicit angular branch selector |
| `xstar_atomic_make_emissivity_table_v1.py` | First direct-excitation emissivity table builder |

---

## 15. Main findings about `atdb.fits`

1. `atdb.fits` is a packed XSTAR internal database, not a normal semantic FITS table set.
2. It contains 1,216,792 records spread across four packed arrays.
3. The record type and rate type are the essential keys to decoding the database.
4. Element, ion, level, line, photoionization, and several collision formats are now partly or fully decoded.
5. Level records (`type=6`) are decoded and validated.
6. Radiative line records (`type=50`) are decoded and validated using O VIII, O VII, Ne X, and Fe XXVI X-ray lines.
7. Photoionization grids (`type=53`) are decoded and validated using O VIII and O VII ground thresholds.
8. Tabulated collision strengths (`type=56`) are decoded and validated using O VIII and Ne X Lyα excitation.
9. Algorithmic collision records (`type=63`) are now partially evaluated for the `nf != ni`, `|Δl| = 1` branch.
10. Full collisional excitation support still requires additional work for type 51, type 98, special He-like records, and same-n l-mixing.
11. A first emissivity-ready table builder now exists for direct-excitation lines.

---

## 16. Current limitations

The code is not yet a complete replacement for XSTAR’s internal atomic database machinery. Current limitations include:

1. Type-63 same-n l-mixing branch is not implemented.
2. Type-51 Burgess-Tully OP/CHIANTI collision records need more validation.
3. Type-98 CHIANTI 2016 collision records need more validation.
4. Type-49 inner-shell photoionization is not yet fully decoded.
5. Type-59 Verner photoionization is not yet evaluated into cross-section curves.
6. Recombination data types are not yet decoded into usable rates.
7. Collisional ionization records are not yet fully decoded.
8. Fe UTA and Fe K Auger/fluorescence records are not yet fully decoded.
9. The emissivity table is direct-excitation only and does not solve full level populations.
10. The explicit type-63 branch selector needs comparison against native XSTAR outputs for a controlled test case.

### v0.3.209 active type-53 continuum-index correction

The first real O VII v0.3.208 run selected the correct live radiation state but failed every type-53 endpoint and rate comparison. The failure was traced to the ATDB decoder, not to `phint53`: it used the maximum extracted type-13 level index (`110`) as `nlevp`, while the direct XSTAR relation `idest2=nlevp+idat(nidt-3)-1` gives `nlevp=79` for the selected records. This created a false 57.919 eV parent excitation and corrupted the threshold, continuum statistical weight, Milne factor, and endpoint mapping. v0.3.209 derives `nlevp` from the probed endpoint and packed parent offset and requires explicit decoder-context readiness. The numerical `phint53` kernel and no-empirical-scale policy are unchanged.

## v0.4.3 complete element statistical-equilibrium source port

The primary population-solver path is now the translated source sequence
`levwk/levwkelement -> calc_hmc_ion -> calc_hmc_element -> msolvelucy`.  The
compact basis is built from the v0.4.1 pointers, with each ion adding `nlev-1`
new unknowns so parent-continuum rows are identical to the next ion's ground
row.  The production O III--O VIII level counts produce 607 rows and five
shared aliases.

Every ion record is traversed through `npfi`, `npar`, and `npnxt`, evaluated by
the unified v0.4.2 `ucalc` dispatcher, and inserted into the four source matrix
positions.  The subsystem returns the raw rate matrix, normalization-constrained
matrix and RHS, heating/cooling matrices, complete source provenance, blocker
records, populations, and solver diagnostics.  `msolvelucy`, `leqt2f`,
`ludcmp`, `lubksb`, and `mprove` are translated in the same subsystem.

The six-row and 119-row products are regression subsets only.  Strict production
acceptance is the full 607-row oxygen matrix and population vector with matching
live-radiation and line/RRC optical-depth state; missing context blocks readiness
and is not replaced with probe coefficients.

