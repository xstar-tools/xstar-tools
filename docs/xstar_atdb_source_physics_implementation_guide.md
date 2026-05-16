# XSTAR atomic database, source architecture, physics, and implementation roadmap

**Document version:** 0.3.200  
**Package:** `xstar-atomic`  
**Primary validation case:** the same-run He-like C V, O VII, Mg XI, and Ca XIX benchmark suite

## 1. Purpose and scope

This document is the technical bridge between three representations of the same calculation:

1. the packed records in XSTAR's `atdb.fits` atomic database;
2. the XSTAR Fortran routines that interpret those records and assemble local rate equations;
3. the Python objects, audit products, and prototype solvers in `xstar-atomic`.

It is intended both as a reference for understanding XSTAR and as an implementation plan for a source-code-equivalent Python package with a later C++ backend. It records the findings through `xstar-atomic` v0.3.199, including the direct `ucalc`, matrix-insertion, population-vector, compact-basis, and row-balance probes.

The current package is not yet a complete replacement for XSTAR. It can decode the database, evaluate and audit many individual processes, reconstruct selected local matrices, and compare them with instrumented XSTAR. A complete implementation still requires the full element basis, native source and normalization closure, thermal/ionization iteration, radial transfer, and output writers.

## 2. Executive model of how XSTAR works

For each radial zone, XSTAR performs a coupled calculation:

```text
input spectrum and shell state
  -> local transferred continuum (epi, bremsa, bremsint, depths)
  -> temperature/electron-fraction iteration
  -> ionization rates and element compact population matrices
  -> level and superlevel populations
  -> line, RRC, continuum emissivity and opacity
  -> heating/cooling and optical-depth updates
  -> next zone/pass
  -> xout_* and xoNN_detail/detal* products
```

The central source-code path is:

```text
src/xstar/xstar.f90
  -> xstarsetup / readtbl / setptrs
  -> radial shell and pass loop
       -> step
       -> trnfrc
       -> xstarcalc
            -> bremsmap
            -> dsec (when temperature/electron fraction are iterated)
            -> calc_hmc_all
                 -> calc_hmc_element
                      -> levwkelement
                      -> calc_hmc_ion
                           -> ucalc
                      -> msolvelucy
            -> calc_emisab_all
            -> calc_emis_all
       -> heatt / stpcut / savd
  -> pprint / writespectra*
```

The important architectural lesson is that final `xout_*` products are not a substitute for the live local arrays used by `ucalc`. Source-equivalent rates require the same local temperature, density, populations, optical depths, covering fraction, and radiation grid.

## 3. `atdb.fits`: physical FITS layout

### 3.1 Primary HDU and four packed vector extensions

`atdb.fits` is not organized as one semantic table per atomic process. The primary HDU stores metadata such as creation date and creator. Four vector extensions store all records:

| FITS extension | Fortran/Python representation | Contents |
|---|---|---|
| `POINTERS` | `masterdata%nptrs`, `ATDB.pointers` | Ten integers per record describing type, payload lengths, and offsets. |
| `REALS` | `masterdata%rdat1`, `ATDB.reals` | Concatenated single-precision real payloads. |
| `INTEGERS` | `masterdata%idat1`, `ATDB.integers` | Concatenated integer payloads, including level and ion identifiers. |
| `CHARS` | `masterdata%kdat1`, `ATDB.chars` | Concatenated character payloads such as labels/configurations. |

The FITS `LENGTH` keyword of each extension gives the logical vector length. XSTAR reads these arrays in `readtbl.f90`; `xstar-atomic` mirrors this layout in `inspect.py` and `hierarchy.py` with memory mapping and lazy loading of the large real vector.

### 3.2 Ten-integer record header

Every record has the following pointer/header block:

| Pointer index | Fortran meaning | Python field | Notes |
|---:|---|---|---|
| 1 | original record pointer/index | `raw0` | Database-defined identifier. |
| 2 | data type (`ltyp`) | `data_type` | Selects the payload schema/formula family. |
| 3 | rate type (`lrtyp`) | `rate_type` | Selects the physical role and parent traversal. |
| 4 | continuation flag | `continuation` | Retained for provenance; current `dread` logic rarely uses it. |
| 5 | number of real values | `nreal` | Slice length in `REALS`. |
| 6 | number of integer values | `nint` | Slice length in `INTEGERS`. |
| 7 | number of character bytes | `nchar` | Slice length in `CHARS`. |
| 8 | 1-based pointer into `REALS` | `real_ptr` | Python subtracts one before slicing. |
| 9 | 1-based pointer into `INTEGERS` | `int_ptr` | Python subtracts one before slicing. |
| 10 | 1-based pointer into `CHARS` | `char_ptr` | Python subtracts one before slicing. |

A raw record is therefore:

```text
RecordHeader + real slice + integer slice + character slice
```

The record header does not by itself define the semantic meaning of each payload position. That interpretation is selected by the `(data_type, rate_type)` pair and the relevant `ucalc`, `calt*`, or decoder branch.

### 3.3 Hierarchical record order

`setptrs.f90` and `xstar_atomic.hierarchy` reconstruct the database hierarchy from record order:

```text
element record (rate type 11)
  -> ion records (rate type 12)
       -> level records (rate type 13)
       -> ionization/recombination records
       -> collision records
       -> radiative line records
       -> superlevel and satellite records
```

The second-to-last integer in a level or many level-resolved records is commonly the local level number used by `setptrs` (`nclev`). This is a database convention, not a universal promise for every data type; each decoder must preserve the raw payload and document its interpretation.

### 3.4 Derived pointer structures built by `setptrs.f90`

XSTAR converts the sequential packed records into navigation arrays. The most important are:

| Derived pointer | Purpose |
|---|---|
| `npar(record)` | Parent element or ion record. |
| `npnxt(record)` | Next record of the same rate type under the same parent. |
| `npfirst(rate_type)` | First database record of a rate type. |
| `npfi(rate_type, ion)` | First record of a rate type for an ion. |
| `npfe(rate_type, element)` | First record of a rate type for an element. |
| `npilev(level, ion)` | Database record for a local level. |
| `npilini` / `nplin` families | Maps line records and line-emissivity indices. |
| `npcon`, `npconi`, `npconi2` | Connect photoionization records to continuum-emissivity indices. |
| `nlevs(ion)` | Number of local rows associated with an ion record, including its compact parent/continuum convention. |
| `npnxt` chains | Allow `calc_hmc_ion` to iterate records without scanning the full database. |

`xstar-atomic` preserves the same hierarchy in `ATDBIndexArrays`: record number, data/rate types, payload counts and pointers, element, global ion index, spectroscopic ion stage, local level index, and parent-kind code. The NPZ hierarchy cache stores numeric arrays so a targeted selection does not require reconstructing more than a million Python objects.

### 3.5 Rate-type catalog

| Code | XSTAR rate-type meaning |
|---:|---|
| 1 | ground state ionization |
| 2 | level ionization/recombination |
| 3 | bound-bound collision |
| 4 | bound-bound radiative |
| 5 | bound-free collision (level) |
| 6 | total recombination |
| 7 | bound-free radiative (level) |
| 8 | total recombination |
| 9 | 2 photon decay |
| 11 | element data |
| 12 | ion data |
| 13 | level data |
| 14 | radiative superlevel->spectroscopic level |
| 15 | CI total rate |
| 23 | collisional superlevel->spectroscopic level |
| 40 | CI from superlevels |
| 41 | Auger decay / Fe K Auger |
| 42 | fluorescence / Auger-related |

### 3.6 Data-type catalog

The following labels are those currently carried by `xstar_atomic.hierarchy`. Some codes are historical or database-version dependent; unlabeled codes are deliberately kept as such instead of assigning an unsupported interpretation.

| Code | XSTAR data-type label used by `xstar-atomic` |
|---:|---|
| 1 | radiative recombination: Aldrovandi & Pequignot |
| 2 | charge exchange H0: Kingdon & Ferland |
| 3 | autoionization: Hamilton, Sarazin, Chevalier |
| 4 | line data radiative: Mendoza; Raymond & Smith |
| 5 | 2 photon transition collisional |
| 6 | level data |
| 7 | dielectronic recombination: Aldrovandi & Pequignot |
| 8 | dielectronic recombination: Arnaud & Raymond |
| 9 | charge exchange H0 Kingdon & Ferland |
| 10 | charge exchange H+ Kingdon & Ferland |
| 11 | 2 photon radiative |
| 12 | photoionization, excited levels: hydrogenic |
| 13 | element data |
| 14 | ion data |
| 15 | photoionization: Barfield, Koontz & Huebner |
| 16 | Arnaud & Raymond collisional ionization |
| 17 | collisional excitation hydrogenic: Cota |
| 18 | radiative recombination hydrogenic: Cota |
| 19 | photoionization: HULLAC |
| 20 | charge exchange H+ Kingdon & Ferland |
| 21 | PI cross section continued |
| 22 | dielectronic recombination: Storey |
| 23 | photoionization, excited levels: Clark |
| 24 | PI cross section Clark continued |
| 25 | collisional ionization: Raymond & Smith |
| 26 | collisional ionization hydrogenic: Cota |
| 27 | photoionization: hydrogenic |
| 28 | line data collisional: Mendoza; Raymond & Smith |
| 29 | collisional ionization data: scaled hydrogenic |
| 30 | radiative recombination hydrogenic: Gould & Thakur |
| 31 | line data no levels |
| 32 | collisional ionization: Cota |
| 33 | line data collisional: HULLAC |
| 34 | line data radiative: Mendoza; Raymond & Smith |
| 35 | photoionization: table from BKH |
| 36 | photoionization, excited levels: hydrogenic no level |
| 49 | OP PI cross sections for inner shells |
| 50 | OP line radiative rates |
| 51 | OP and CHIANTI line collisional rates |
| 52 | same as 59 but rate type 7 |
| 53 | OP PI cross sections |
| 54 | H-like Cij, Bautista, H-like ion |
| 55 | hydrogenic PI cross sections, Bautista format |
| 56 | tabulated collision strength, Bautista |
| 57 | effective charge for collisional ionization |
| 58 | H-like recombination rates, Bautista |
| 59 | Verner PI cross sections |
| 60 | Calloway H-like collision strength |
| 61 | H-like Cij, Bautista, non-H-like ion |
| 62 | Calloway H-like collision strength |
| 63 | H-like Cij, Bautista, H-like ion |
| 64 | hydrogenic PI cross sections, Bautista format |
| 65 | effective charge for collisional ionization |
| 66 | like type 69 but fine-structure data |
| 67 | effective collision strengths from Keenan et al. |
| 68 | He-like collision strengths by Zhang & Sampson |
| 69 | Kato & Nakazaki fit to He-like collision strengths |
| 70 | coefficients for photoionization cross sections of superlevels |
| 71 | transition rates from superlevel to spectroscopic levels |
| 72 | autoionization rates for satellite levels |
| 73 | fit to collisional strengths, satellite levels, He-like ions |
| 74 | delta functions added to photoionization cross sections for DR |
| 75 | autoionization data for Fe XXIV satellites |
| 76 | 2 photon decay |
| 77 | collisional rates from 71 |
| 78 | Auger level data |
| 79 | fluorescence line data |
| 80 | collisional ionization rates, ground of Fe and Ni |
| 81 | Bhatia Fe XIX collision strengths |
| 82 | Fe UTA radiative rates |
| 83 | Fe UTA level data |
| 84 | Iron K PI cross sections, spectator Auger binned |
| 85 | Iron K PI cross sections, spectator Auger summed |
| 86 | Iron K Auger data |
| 88 | unlabeled XSTAR data type 88 |
| 91 | unlabeled XSTAR data type 91 |
| 92 | unlabeled XSTAR data type 92 |
| 95 | Bryans collisional ionization / CI total rates |
| 98 | CHIANTI 2016 collisional excitation rates |
| 99 | unlabeled XSTAR data type 99 |

### 3.7 Key record layouts used in the current implementation

| Data/rate type | Process | Important payload interpretation | Main source routine |
|---|---|---|---|
| 13/11 | Element metadata | abundance, atomic weight, element identity | `setptrs`, `levwkelement` |
| 14/12 | Ion metadata | global ion index, ion stage, number of levels, labels | `setptrs`, `levwk`, `levwkelement` |
| 6/13, 83/13 | Level data | energy, statistical weight, level number, configuration | `setptrs`, `levwk*` |
| 50/4 | Bound-bound radiative line | wavelength/energy, oscillator strength, A value, upper/lower level indices | `ucalc` type 50, `calc_hmc_ion` |
| 53/7 | OP bound-free photoionization | threshold, energy-offset grid, cross-section grid, destination levels | `ucalc` type 53, `phint53` |
| 56/3 | Tabulated effective collision strengths | temperature grid, upsilon values, level pair | `upsil*`, collision decoder |
| 63/3 | Bautista hydrogenic collisions and same-n l mixing | quantum numbers, fit/control integers, level pair | `amcrs`, `anl1`, `erc`, `velimp` |
| 68/3 | He-like collision strengths | Zhang-Sampson parameters and transition indices | `calt68` |
| 69/3 | He-like fitted collision strengths | Kato-Nakazaki fit parameters and transition indices | `calt69`, `calc_kato` |
| 70/7 | Superlevel photoionization | superlevel cross-section coefficients and parent mapping | `calt70`, `phint53hunt` |
| 71/14 | Superlevel radiative cascade | A value and superlevel-to-spectroscopic destination | `calt71` |
| 74/7 | Dielectronic-recombination resonance contribution | delta-function resonance strength and destination mapping | `calt74` |
| 77/23 | Superlevel collisional cascade | density-scaled collisional partner of type 71 | `calt77` |
| 99/7 | Superlevel source/sink closure | recombination normalization plus photoionization search | `calt99`, `phint53hunt` |

## 4. XSTAR source-code layout

### 4.1 Top-level directories

| Path | Role |
|---|---|
| `src/xstar/xstar.f90` | Executable driver, input handling, radial shell/pass loop, final products. |
| `xstarlib/src/` | Atomic data, local plasma solve, transfer, emissivity, matrix, numerical routines. |
| `data/` | Runtime auxiliary data; the large `atdb.fits` is normally distributed/installed separately. |
| `manual/` and `doc/` | XSTAR manual and supporting documentation. |
| `utils/`, `scripts/` | Conversion, setup, and operational helpers. |

### 4.2 Functional source map

| Stage | Principal routines | Live data produced/consumed |
|---|---|---|
| Database read | `readtbl`, `dread`, `setptrs`, `globaldata` | `nptrs`, `rdat1`, `idat1`, `kdat1`, derived pointers. |
| Continuum setup | `ener`, incident-spectrum routines | high-resolution `epi`, incident/diffuse spectral arrays. |
| Transfer | `trnfrc`, `trnfrn`, `bremsmap` | `bremsa`, `bremsint`, mapped `epim`, `bremsam`. |
| Thermal/charge iteration | `dsec`, `heatf`, `heatt` | temperature, electron fraction, heating/cooling. |
| Ion rates | `calc_ion_rates`, `istruc`, `ioneqm` | total ionization/recombination rates and ion fractions. |
| Element basis | `calc_hmc_all`, `calc_hmc_element`, `levwkelement` | compact `ipmat2` basis, ion/superlevel maps, initial populations. |
| Record rates | `calc_hmc_ion`, `ucalc`, `calt*`, `phint53*` | `ans1..ans6`, rate provenance, opacity/emissivity contributions. |
| Matrix solve | `msolvelucy`, `leqt2f`, LU helpers | level/superlevel population vector `x`. |
| Emissivity/opacity | `calc_emis*`, `calc_emisab*`, `linopac` | lines, RRCs, continuum emissivity and opacity. |
| Depth update | `stpcut` | direction-dependent `tau0`, `tauc`, continuum depths. |
| Output | `savd`, `fstepr*`, `pprint`, `writespectra*` | `xoNN_detail/detal*` and `xout_*` products. |

### 4.3 Output products and their debugging value

| Product | Main contents | Parity use |
|---|---|---|
| `xout_abund1.fits` | zone temperature, electron fraction/density information, ion fractions | local-state selection and ionization closure. |
| `xout_lines1.fits` | final line luminosities/emissivities | f/i/r benchmark target, not a live rate field. |
| `xout_rrc1.fits`, `xout_cont1.fits`, `xout_spect1.fits` | RRC/continuum/final spectrum | output-layer validation. |
| `xoNN_detail.fits` | level populations by zone | post-solve population parity. |
| `xoNN_detal2.fits` | line emissivity, opacity, inward/outward optical depths | type-50 escape and line-transfer audits. |
| `xoNN_detal3.fits` | RRC emissivity, opacity, depths | bound-free escape audits. |
| `xoNN_detal4.fits` | continuum emissivity/opacity/depth arrays | reconstruction aid, but not identical to live `bremsam`. |

## 5. From an ATDB record to a matrix coefficient

The record-to-solution path is:

```text
ATDB record number
  -> POINTERS header
  -> REALS/INTEGERS/CHARS payload slices
  -> setptrs parent and rate-type chains
  -> calc_hmc_ion chooses local destinations and escape context
  -> ucalc dispatches by data type
  -> ans1..ans6 raw physical outputs
  -> possible branch-specific swaps/sign changes
  -> four ajisi/indbi insertions for a two-way transition
  -> calc_hmc_element adds ion-block ipmat2 offsets
  -> msolvelucy solves the compact element system
```

For a matrix-active two-way process, `calc_hmc_ion` typically emits four entries: two off-diagonal gains and two diagonal losses. A rate comparison is incomplete unless both the numeric values and these row/column placements agree.

### 5.1 Compact element basis and parent-continuum aliases

XSTAR does not concatenate independent ion level lists naively. Within `calc_hmc_element`, the compact basis advances approximately as:

```fortran
ipmat2 = ipmat2 + nlev - 1
```

and adds a final parent/continuum slot after the ion loop. Consequently, the last row of one ion block can be the same compact unknown as the ground/parent role of the adjacent ion. One compact `ipmat2` row may therefore have multiple physical role labels.

The v0.3.192--v0.3.198 probes established the exact O-element topology for the selected O VII benchmark:

- 607 compact XSTAR population rows;
- six ion blocks in the selected element solve;
- six shared alias rows;
- all matrix endpoints mapped by `compact_ipmat2 = ion_ipmat2_offset + indbi`;
- all unrelated-element records filtered before compact mapping.

## 6. Physical equations and their source-code roles

### 6.1 Radiation and ionization parameter

XSTAR commonly characterizes the incident radiation by

\[
\xi = \frac{L_{\mathrm{ion}}}{n\,r^2}
\quad [\mathrm{erg\,cm\,s^{-1}}],
\]

where the exact density convention follows the run definition. The local rate calculation does not use only \(\xi\); it uses the transferred spectral field. In the current source path:

- `epi(:)` is an energy grid;
- `bremsa(:)` is the live high-resolution ionizing field used by transfer;
- `epim(:)`, `bremsam(:)`, and `bremsint(:)` are the mapped rate grid passed to atomic calculations.

`bremsmap.f90` primarily maps the high-resolution field to the rate grid by bin lookup and constructs its cumulative integral. It does not contain a hidden factor near 44.

### 6.2 Atomic levels and wavelengths

For levels \(i\) and \(j\),

\[
\Delta E_{ij} = E_j-E_i, \qquad
\lambda_{ji} = \frac{hc}{|\Delta E_{ij}|}.
\]

Each level also carries a statistical weight \(g_i\). XSTAR uses level energies and weights for transition ordering, detailed balance, LTE ratios, continuum thresholds, and matrix destinations. The database wavelength may be retained for line identification, while energy differences can be used for energy conservation in emissivity calculations.

### 6.3 Statistical equilibrium of level populations

For each compact population row \(i\), steady state requires

\[
0 = \sum_{j\ne i} n_j R_{j\rightarrow i}
    -n_i\sum_{j\ne i}R_{i\rightarrow j}
    +S_i,
\]

where \(S_i\) includes processes represented through adjacent-ion and source closure. In matrix form,

\[
\mathbf{{A}}\,\mathbf{{x}}=\mathbf{{b}},
\]

with one row replaced by a normalization condition such as

\[
\sum_i x_i=1.
\]

`calc_hmc_ion` creates sparse transition entries, `calc_hmc_element` maps them into compact element coordinates, and `msolvelucy` solves through a superlevel condensation/fixed-point procedure. The row-balance audit evaluates

\[
r_i=\sum_j A_{{ij}}x_j
\]

against the captured post-`msolvelucy` vector.

### 6.4 Ionization equilibrium

A simplified adjacent-stage balance is

\[
n_q\,\Gamma_q = n_{{q+1}}\,n_e\,\alpha_{{q+1}},
\]

but XSTAR assembles all included stages and channels. In a general steady-state form,

\[
0=\sum_{{q'\ne q}} n_{{q'}} I_{{q'\rightarrow q}}
  -n_q\sum_{{q'\ne q}} I_{{q\rightarrow q'}},
\qquad
\sum_q f_q=1.
\]

`calc_ion_rates` accumulates total photoionization and recombination terms; `istruc`/`ioneqm` solve the ion fractions. Level-resolved and superlevel source terms then couple the ion solution to the element population matrix.

### 6.5 Photoionization and heating: type 53

For a level with threshold \(E_0\), the physical forward rate is represented by

\[
\Gamma_{{\rm PI}} = \int_{{E_0}}^\infty
\sigma(E)\,\frac{F_E}{E}\,dE,
\]

and the corresponding photoelectron heating is

\[
H_{{\rm PI}} = n_i\int_{{E_0}}^\infty
(E-E_0)\,\sigma(E)\,\frac{F_E}{E}\,dE.
\]

`phint53.f90` maps the OP cross-section grid onto the XSTAR energy grid and trapezoid-integrates the rate and heating terms. Its code contains paired factors of 12.56 that cancel in the forward photoionization integrand. The reverse branch uses a Milne/detailed-balance construction, statistical-weight/LTE factors, and the local temperature.

#### The unresolved approximately 44 scale

The instrumented live-rate-grid audit found

```text
preserved Python type-53 proxy matrix rate / XSTAR live phint53 ans1 ≈ 44.2
```

This is not a hidden `bremsmap` or `phint53` constant. It is currently interpreted as the ratio of the legacy diagnostic `xstar-powerlaw` normalization to the source-code-equivalent live `bremsam` rate. Replaying exact XSTAR `ucalc` type-53 rates changed the O VII triplet population fractions by only about \(8.4\times10^{{-7}}\), so this scale is real but was not the dominant cause of the earlier triplet population mismatch.

The planned fix is not an empirical division by 44. The production path must:

1. carry the exact local `epim`, `bremsam`, and `bremsint` state;
2. port the complete type-53 threshold mapping and `phint53` integral;
3. compare native Python `ans1..ans6` with the same XSTAR `ucalc` capture;
4. replace proxy matrix terms only after branch-level and matrix-placement parity pass.

### 6.6 Recombination and the Milne relation

Radiative recombination is the inverse of photoionization. Schematically,

\[
\alpha_i(T) = \int_0^\infty v\,f_M(v,T)\,
\sigma_{{\rm RR},i}(v)\,dv,
\]

where the recombination cross section is related to the photoionization cross section by detailed balance. XSTAR's implementation uses statistical-weight factors, an LTE population ratio, the Maxwell factor \(\exp[-(E-E_0)/kT]\), and the same cross-section grid. The `phint53` reverse side also generates RRC emissivity and recombination cooling.

Total recombination data types provide fitted rates, while types 70, 74, and 99 participate in explicit superlevel and dielectronic-recombination closure. A full implementation must not replace these with arbitrary source vectors.

### 6.7 Electron-impact excitation and de-excitation

For an effective collision strength \(\Upsilon_{{ij}}(T)\), the common Maxwellian form is

\[
q_{{ij}} = \frac{{8.629\times10^{{-6}}}}{{g_i T^{{1/2}}}}
\Upsilon_{{ij}}(T)\exp\left(-\frac{{\Delta E_{{ij}}}}{{kT}}\right)
\quad \mathrm{{cm^3\,s^{{-1}}}},
\]

\[
q_{{ji}} = \frac{{8.629\times10^{{-6}}}}{{g_j T^{{1/2}}}}
\Upsilon_{{ij}}(T).
\]

Matrix rates are \(C_{{ij}}=n_e q_{{ij}}\). In the current He-like work:

- type 56 carries tabulated effective collision strengths;
- type 63 implements Bautista hydrogenic transitions and same-\(n\) \(l\)-mixing branches;
- type 68 uses Zhang-Sampson He-like collision strengths;
- type 69 uses Kato-Nakazaki fits;
- type 77 provides superlevel-to-spectroscopic collisional coupling.

Direct probes established near-unity record/matrix parity for types 63, 68, and 69 in the selected O VII local state.

### 6.8 Radiative decay, escape, and line pumping: type 50

For a line with spontaneous rate \(A_{{ul}}\), XSTAR first constructs direction/covering factors

\[
p_1=P_{{\rm esc}}(\tau_{{\rm in}})(1-C_f),
\]

\[
p_2=P_{{\rm esc}}(\tau_{{\rm out}})(1-C_f)
 +2P_{{\rm esc}}(\tau_{{\rm in}}+\tau_{{\rm out}})C_f.
\]

The escaped decay rate before the final branch swap is

\[
R_{{u\rightarrow l}}^{{\rm esc}}=A_{{ul}}(p_1+p_2).
\]

The line-center velocity-integrated cross-section factor is represented in the source as

\[
\sigma_v = 0.02655\,f_{{lu}}\,\frac{{\lambda_{{\rm cm}}}}{{v_{{\rm th/turb}}}},
\]

and the photoexcitation/pumping rate is approximately

\[
R_{{l\rightarrow u}} = \sigma_v\,
\mathrm{{bremsa}}(E_{{ul}})\,\frac{{v_{{\rm th/turb}}}}{{c}}
\,f_{{\rm linabs}}\,(1-C_f).
\]

`ucalc` finally swaps `ans1` and `ans2` so the returned forward branch is excitation and the reverse branch is escaped decay. For \(C_f=1\), pumping is suppressed and the escape term uses the combined inward+outward optical depth. The v0.3.156 detail-state audit verified all five O VII triplet type-50 rows and the matrix insertions.

### 6.9 Line width, opacity, and emissivity

`linopac.f90` combines thermal and turbulent widths in quadrature:

\[
\Delta E_D = \sqrt{{\Delta E_{{\rm th}}^2+\Delta E_{{\rm turb}}^2}},
\]

with \(v_{{\rm th}}\propto\sqrt{{T/A}}\) and \(\Delta E/E=v/c\). It deposits a Gaussian/Voigt line profile into the continuum opacity grid or uses a single-bin approximation in fast mode.

For a radiative transition, the optically modified emissivity is proportional to

\[
\epsilon_{{ul}} = n_u A_{{ul}} h\nu\,P_{{\rm esc}},
\]

with inward/outward pieces separated by the escape factors. Net line output may also subtract radiative excitation/absorption, as in the `calc_emis_ion` expression involving `ans2*abund2 - ans1*abund1`.

### 6.10 Superlevels and compact closure

Superlevels reduce a large level system by grouping rows through `nsup`. `msolvelucy` computes within-superlevel fractions

\[
r_i=\frac{{x_i}}{{p_{{s(i)}}}},
\qquad
p_s=\sum_{{i\in s}}x_i,
\]

constructs a condensed superlevel matrix, imposes number conservation, solves for \(p_s\), and reconstructs \(x_i=r_i p_{{s(i)}}\). Fixed-point iterations then update level fractions and superlevel totals.

Types 71 and 77 connect superlevels to spectroscopic levels radiatively and collisionally. Types 70, 74, and 99 couple photoionization, dielectronic recombination, parent continua, and superlevel source/sink closure. These branches are essential for a physical full-element solution.

### 6.11 Thermal balance

The local temperature is determined by

\[
H(T,n_e,\{{f_q\}},J_E)-C(T,n_e,\{{f_q\}},J_E)=0,
\]

with charge/electron consistency solved simultaneously or iteratively. Heating includes photoelectrons, Compton and other channels; cooling includes line emission, recombination, free-free emission, and other atomic channels. `dsec` repeatedly calls the population/ionization calculation while adjusting temperature and electron fraction.

### 6.12 Radial transfer and optical-depth evolution

The transferred field at a zone depends on incident radiation, attenuation, and diffuse emission. XSTAR uses direction-dependent continuum/line depths and a single-stream approximation in the current transfer path. `trnfrc` constructs the local continuum used by the rates; `stpcut` updates line and continuum optical depths after the local solution. A full replacement must therefore iterate transfer and plasma state rather than solve isolated zones only.

## 7. He-like C V, O VII, Mg XI, and Ca XIX calculations

### 7.1 Triplet diagnostics

The principal He-like lines are:

- forbidden \(f\): \(1s2s\,^3S_1\rightarrow1s^2\,^1S_0\);
- intercombination \(i\): \(1s2p\,^3P_{{1,2}}\rightarrow1s^2\,^1S_0\), often summed;
- resonance \(r\): \(1s2p\,^1P_1\rightarrow1s^2\,^1S_0\).

The standard diagnostics are

\[
R=\frac{{f}}{{i}},
\qquad
G=\frac{{f+i}}{{r}}.
\]

\(R\) responds strongly to density and radiation-driven transfer between \(^3S\) and \(^3P\); \(G\) responds to the balance of recombination/cascade feeding, collision excitation, and resonance-line transfer.

### 7.2 Canonical same-run benchmark suite

| Ion | Atomic number | Default wavelength window | Run directory |
|---|---:|---:|---|
| C V | 6 | 40.0--42.0 Å | `helike_type69/c5_ne1e8` |
| O VII | 8 | 21.0--23.0 Å | `helike_type69/o7_ne1e8` |
| Mg XI | 12 | 9.0--9.4 Å | `helike_type69/mg11_ne1e8` |
| Ca XIX | 20 | 3.0--3.35 Å | `helike_type69/ca19_xi3_ne1e8` |

These cases test the same atomic architecture across increasing nuclear charge and line energy. The exact local temperature, electron density, ion fraction, and \(\log\xi\) are extracted from each same-run XSTAR output rather than imposed from one universal model.

### 7.3 Physical processes that control the four-ion benchmark

| Process | Main data/source branches | Effect on f/i/r |
|---|---|---|
| Spontaneous decay and escape | type 50, `pescl`, `calc_hmc_ion` | Direct line drain; optical depth changes apparent resonance strength. |
| Line pumping | type 50 plus live radiation and `cfrac` | Transfers population upward; suppressed for `cfrac=1`. |
| Direct electron excitation | types 63, 68, 69 | Feeds triplet and resonance upper levels with strong temperature/density dependence. |
| Radiative cascades | type 71 | Feeds spectroscopic levels from superlevels. |
| Collisional superlevel coupling | type 77 | Redistributes superlevel populations. |
| Photoionization/RR | type 53 | Couples levels to parent continuum and produces RRC/heating/cooling. |
| DR/source closure | types 70, 74, 99 | Supplies and drains superlevels/parent continua. |
| Adjacent-ion compact aliases | `calc_hmc_element` topology | Ensures ion-stage and level-population normalization are solved consistently. |

### 7.4 Current benchmark interpretation

O VII is the deepest source-code parity case because it has direct rate-grid, `ucalc`, matrix, population, basis, and balance probes. C V, Mg XI, and Ca XIX are retained as cross-ion regression cases. The aim is not to tune each ion separately; it is to implement one source-equivalent data/rate/basis pipeline that reproduces all four under their own local XSTAR states.

## 8. New findings established by the validation sequence

### 8.1 Type-50 escape and pumping

- The exact `cfrac`-dependent `ptmp1/ptmp2` formulas are required.
- For the O VII benchmark with `cfrac=1`, line pumping is zero.
- Five selected O VII triplet type-50 records match `ucalc` and matrix insertions.
- A global diagnostic escape factor such as 0.35 must not be used as the production source-equivalent treatment.

### 8.2 Matrix-family parity

At the selected O VII local state:

- type 63, 68, and 69 collision matrix terms are essentially at unity parity;
- type 71 cascade terms are at approximately 0.998 median parity;
- type 50 contains exact triplet matches but older non-triplet proxy treatments remain in historical products;
- type 77 showed a moderate historical difference and remains a native-port target;
- type 53 historical proxy rows differ strongly from live `phint53` rates.

### 8.3 The type-53 scale is real but not the main population lever

Live `epim/bremsam` recomputation confirmed the approximately 44 scale. Controlled replay of exact XSTAR `ucalc` rates for type 53, 50, 77, and 99 moved O VII triplet population fractions by at most about \(8.36\times10^{{-7}}\). This established that population/source closure and basis mapping had to be fixed before interpreting rate-family changes end to end.

### 8.4 Direct Fortran probes

The instrumentation now captures:

- per-record `ucalc ans1..ans6`;
- the four `calc_hmc_ion` matrix insertions and shared capture IDs;
- live `epim`, `bremsam`, and `bremsint` rate grids;
- paired before/after-`msolvelucy` population vectors;
- exact `calc_hmc_element` compact-basis roles and ion-block offsets.

These probes convert implementation questions into direct record/row comparisons rather than inferred fits to final line ratios.

### 8.5 Exact O-element compact basis

The selected O-element solve has:

- 607 compact population rows;
- 352 nonzero post-solve rows;
- six compact ion blocks and shared parent-continuum aliases.

The original sequential Python `xstar_ipmat2_index` mapping was wrong. Physical remapping by `(ion_stage, level_index)` maps all 114 current Python population identities to 113 unique compact rows and raises captured XSTAR population coverage from about \(2.6\times10^{{-6}}\) to

\[
0.991904690445624.
\]

### 8.6 Six-row priority expansion

Adding compact rows

```text
293, 241, 244, 242, 80, 79
```

raises represented solved-population coverage to

\[
0.9999999463123856.
\]

Three are ordinary rows and three are shared parent-continuum/next-ion-ground aliases. The active staged basis contains 119 unique compact rows represented by 120 physical Python identities.

### 8.7 Complete priority-row matrix manifest and balance

After correcting endpoint translation and element filtering:

- all six priority rows have Fortran matrix coverage;
- 1,260 matrix-active records have four rows;
- nine intentional non-matrix metadata records have zero rows;
- no compact matrix endpoints are unmapped;
- the six selected row equations pass a 0.5% relative residual threshold against the captured XSTAR population vector;
- the maximum row residual is approximately \(1.7471\times10^{{-3}}\).

This is the strongest current evidence that the reconstructed topology and probed terms are correct for the staged subset.

## 9. `xstar-atomic` data and software structures

| Python structure/module | Purpose |
|---|---|
| `ATDB`, `RecordHeader`, `RawRecord` | Low-level packed FITS access. |
| `ATDBIndexArrays`, `IndexedRecord`, `ElementInfo`, `IonInfo` | Array-backed element/ion/level hierarchy and targeted selection. |
| `XSTARAtomic` | Reusable high-level database object and workflow namespaces. |
| `LocalPlasmaState` | Temperature, density, ionization and local abundance state. |
| `RadiationField` | Energy grid and local radiation samples; future source-equivalent rate-grid carrier. |
| `EscapeContext` | `cfrac`, line/continuum optical depths, velocity/escape data. |
| `XSTARContext` | Combined state/radiation/escape object. |
| `RateEvaluation` | Numeric rate plus raw/interpreted branch provenance. |
| `XSTARContinuumState`, `XSTARZoneState`, `XSTARRunState` | Skeleton for future full radial calculations and output recreation. |
| Record-level parity products | Join Python records to XSTAR `ucalc` and four matrix rows. |
| Element-basis probe/remap/scaffold | Reconstructs compact `ipmat2` topology and aliases. |
| Priority expansion/closure/balance products | Staged native implementation manifest and consistency gates. |

## 10. Current implementation status

### Source-equivalent or strongly validated

- packed FITS vector reader and hierarchy;
- level and line extraction;
- selected photoionization and recombination decoders;
- type 56 and validated type 63 collision branches;
- type 68 and 69 He-like collision evaluation/matrix placement;
- type 50 triplet detail-state escape/pumping calculation;
- type 71 cascade evaluation/matrix placement;
- raw record-level `ucalc` and matrix probe association;
- exact O-element compact-basis reconstruction and physical remapping;
- six-row priority matrix manifest and row-balance validation.

### Diagnostic or incomplete

- historical proxy `xstar-powerlaw` type-53 matrix normalization;
- native type 77 implementation over the expanded basis;
- native type 70/74/99 parent/superlevel source closure;
- expanded-basis RHS and normalization assembly;
- complete 607-row native element solve;
- coupled ionization/temperature iteration;
- radial transfer and output reproduction.

## 11. Roadmap to a full XSTAR implementation

### Phase A: controlled 119-row compact solve

1. Instantiate the corrected 113 mapped compact rows plus the six priority rows.
2. Preserve all parent-continuum aliases as one unknown with multiple role labels.
3. Assemble probed matrix entries and explicit RHS/normalization terms.
4. Solve the 119-row system and compare every population and selected row residual with XSTAR.
5. Keep this as a replay/parity mode until native formulas reproduce it.

**Acceptance gates:** no unmapped endpoints; normalization exactly one; priority rows below the residual tolerance; mapped population fractions agree within declared tolerances.

### Phase B: native rates for the priority subset

Port only the rate families actually touching the six selected rows. Every native branch must reproduce:

```text
raw ATDB payload -> ans1..ans6 -> four matrix rows -> row balance
```

No empirical source weights or scale factors should be accepted in production mode.

### Phase C: eliminate the type-53 approximately 44 scale

1. Promote `epim`, `bremsam`, `bremsint` to first-class live-state arrays.
2. Port complete `phint53` and `phint53hunt` behavior.
3. Validate threshold binning, cross-section mapping, forward rate, reverse rate, heating/cooling, opacity, and RRC emissivity.
4. Replace proxy type-53 terms only after record-level parity.
5. Repeat across C V, O VII, Mg XI, and Ca XIX.

### Phase D: expand from 119 to all 607 compact rows

Use the population-ranked scaffold to add remaining rows in tiers. For each tier:

- add row identities and aliases;
- add all touching records and endpoints;
- verify row balance;
- compare population coverage and line emissivities;
- retain a deterministic mapping from physical roles to compact rows.

### Phase E: full ionization and thermal closure

Port and validate:

- total ionization/recombination rates;
- `istruc`/`ioneqm` ion fractions;
- `levwkelement` source construction;
- `msolvelucy` superlevel iteration;
- heating/cooling and electron-fraction closure;
- `dsec` convergence behavior.

### Phase F: radial transfer and output products

Implement the zone/pass driver, continuum transfer, optical-depth update, and output writers. Validate detail products first, then final spectra:

```text
xoNN_detail/detal2/detal3/detal4
  -> xout_abund/lines/rrc/cont/spect
```

### Phase G: C++ backend

The Python implementation remains the readable reference and audit layer. Performance-critical kernels should expose stable array-oriented interfaces suitable for C++:

- cross-section mapping and `phint53/phint53hunt` integrals;
- collision-rate grid evaluation;
- sparse matrix assembly;
- Lucy/sparse linear solves;
- transfer and optical-depth loops;
- thermal iteration.

The backend must consume and return the same typed Python state objects and provenance IDs. Python tests and direct XSTAR probes remain the correctness oracle.

## 12. Conditional compact solve milestone (v0.3.201)

For the six activated rows, partition the compact steady-state equations into selected and external blocks,

\[
A_{SS}x_S + A_{SE}x_E = 0,
\qquad
A_{SS}x_S = -A_{SE}x_E.
\]

Here, `x_E` is fixed to the captured XSTAR post-`msolvelucy` population vector. This isolates compact matrix assembly and source/sink closure without yet claiming an autonomous Python element solve. For O VII rows `79,80,241,242,244,293`, the row-scaled selected matrix is full rank, its condition number is about 5.8545, and all six solved populations agree with XSTAR within 0.5%. The maximum relative difference is about `3.0341e-3`; the linear-system residual is below `4e-16`.

This validates the selected compact topology and external source closure. The coefficients are still XSTAR-probed. The next implementation replaces them family by family with native Python rates, then expands the same partitioned solve to all 119 active rows before introducing a fully autonomous normalization and ionization closure.

## 12.1. Native-assembly readiness milestone (v0.3.202)

The six-row conditional solve separates the internal compact block from its external closure. Ranking the population-weighted terms gives a concrete native port order:

- type 51 contributes about 97.77% of the internal selected-block coupling;
- type 50 contributes about 99.06% of the external right-hand side;
- type 71 contributes about 0.861% of the external right-hand side;
- type 53 contributes about 0.0795% of the external right-hand side in this state, but remains mandatory for source equivalence and for other radiation-dominated states.

Therefore the minimum controlled implementation sequence is: native type-51 internal coupling, native type-50/type-71 external closure, exact live-radiation type-53, then the smaller parent/superlevel and residual families. The approximately 44 type-53 scale must disappear through the `epim`/`bremsam`/`phint53` path; it must not be absorbed into a fitted multiplier.

## 13. Validation policy

A feature becomes a production default only after passing all applicable layers:

1. **Database parity:** raw payload and level/ion identity are correct.
2. **Rate parity:** native `ans1..ans6` match the same XSTAR capture.
3. **Matrix parity:** row/column/sign and diagonal partners match.
4. **Basis parity:** compact index and alias roles match.
5. **Population parity:** pre/post solve vectors and normalization match.
6. **Emissivity parity:** lines/RRC/continuum match from the same populations.
7. **Cross-ion regression:** C V, O VII, Mg XI, and Ca XIX pass without ion-specific tuning.
8. **End-to-end parity:** radial/detail/final products agree within documented tolerances.

## 14. Practical source-to-Python map

| XSTAR source | Python counterpart or target |
|---|---|
| `readtbl.f90`, `dread.f90` | `inspect.py`, `hierarchy.ATDB` |
| `setptrs.f90` | `ATDBIndexArrays`, hierarchy cache, process-specific joins |
| `trnfrc.f90`, `bremsmap.f90` | `RadiationField`, live rate-grid probes, future transfer backend |
| `calc_ion_rates.f90`, `istruc.f90` | current audits; future native ionization closure |
| `levwkelement.f90` | basis/source probes; future element-state constructor |
| `calc_hmc_ion.f90` | record-level parity, compact matrix manifests |
| `ucalc.f90`, `calt*.f90` | process-specific rate evaluators and provenance |
| `phint53.f90`, `phint53hunt.f90` | live type-53 audits; future native PI/RR kernels |
| `calc_hmc_element.f90` | element-basis probes/remap/scaffold/priority expansion |
| `msolvelucy.f90` | `xstar-lucy` prototype and future source-equivalent solver |
| `calc_emis*`, `linopac.f90` | emissivity/export modules and future opacity parity |
| `stpcut.f90` | future line/RRC depth evolution |
| `fstepr*`, `writespectra*` | output readers now; future writers |

## 15. References and source provenance

Primary code reference: the XSTAR Fortran source distributed with the reviewed package, especially `readtbl.f90`, `setptrs.f90`, `xstarcalc.f90`, `calc_hmc_all.f90`, `calc_hmc_element.f90`, `calc_hmc_ion.f90`, `ucalc.f90`, `phint53.f90`, `calt68.f90`, `calt69.f90`, `calt71.f90`, `calt74.f90`, `calt77.f90`, `calt99.f90`, `msolvelucy.f90`, `trnfrc.f90`, `stpcut.f90`, and the output routines.

Scientific references carried with the development review:

- Kallman et al. (1996), *ApJ*, 465, 994.
- Kallman & Bautista (2001), *ApJS*, 133, 221.
- Bautista & Kallman (2001), *ApJS*, 134, 139.
- Kallman et al. (2004), *ApJS*, 155, 675.

The numerical findings in this document are from same-run XSTAR debug probes and `xstar-atomic` audit products through v0.3.202. They should be regenerated when the XSTAR source/database version, benchmark inputs, or compact-basis selection changes.
