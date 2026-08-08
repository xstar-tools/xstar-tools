# XSTAR scientific references and implementation correspondence

This bibliography/concordance was built from the supplied reference bundle (`xstar_references.tar.gz`, SHA-256 `a66718cf3b3d831906ed640c3bb9a2d8e81ac3bcdbfd4878d09fc680e6616e84`) and the supplied XSTAR 2.59g Fortran source.

## Evidence hierarchy

For this project, references are interpreted in the following order:

1. **accepted qualification evidence** for behavior already closed in `xstar_tools`;
2. **canonical XSTAR 2.59g executable semantics** for source behavior;
3. **papers/manuals** for equations, assumptions, physical interpretation, and provenance.

A paper is therefore not used to “correct” already qualified executable behavior merely because it presents an idealized or older formulation differently.

## Core references

### XSTAR Team, *XSTAR Manual*, Release 2.5x, 20 Dec 2025

**Role:** primary current explanatory manual supplied with the project references.

Important sections for the port:

| Manual section | Topic / algorithm | Fortran correspondence | Python/C++ correspondence | Implementation relation |
|---|---|---|---|---|
| 4.1-4.3 | user parameters, hidden controls, density/pressure, ionization parameter, step/print controls | `rread1.f90`, top of `xstar.f90` | parameter normalization in `physical_runner.py`; native parameter/default-real helpers | source-exact for executable conversions/default-kind effects; UI representation may differ |
| 5 | output products and `xout_step.log` | `pprint.f90`, `fstepr*`, `writespectra*` | `pprint_legacy.py`, `output_writers.py`, `xstar_step_log.cpp`, `xstar_science_fits.cpp` | source-equivalent publication; comparator policy is qualification metadata |
| 11.1 | spherical point-source geometry, steady state, inward/outward diffuse radiation, local escape probabilities | radial/transfer caller in `xstar.f90`, escape factors in rate/emission routines | radial transfer and escape-state modules; native run state | mathematically/source equivalent within XSTAR's stated approximation |
| 11.3 | ionization parameter, including `xi = L/(n R^2)` in the optically thin limit | parameter/radius/radiation calculation in `rread1` and radial state | parameter normalization/radiation state | source-exact numerical semantics where source kinds matter |
| 11.4.1 | two-step population algorithm: preliminary ion fractions then full multilevel kinetic matrix | `calc_ion_rates`, `istruc/ioneqm`, `levwk*`, `calc_hmc_ion/element`, `msolvelucy` | `ion_balance.py`, `element_equilibrium.py`, fixed-state C++ | source-equivalent; compact representation optimized/translated |
| 11.4.4 | thermal equilibrium from heating/cooling balance | `calc_hmc_all`, `dsec`, `comp2/freef/bremem/heatf` | `local_zone.py`, `dsec.py`, thermal modules/kernels | source-exact controller; equivalent/optimized leaves |
| 11.5 | recombination-continuum emission and escape | RRC branches in `ucalc`, `calc_emisab_*`, `calc_emis_*`, `fstepr3`, `writespectra4` | emissivity/publication modules and native FITS path | source-equivalent; terminal publication lifetime explicitly qualified |
| 11.5.1 | line emission and escape probabilities; upper-level population times net decay with trapping/destruction | line rate/emission paths, `pescl/pescv`, Type50/line transfer | `element_equilibrium`, `emergent_emissivity`, C++ line/opacity kernels | source-equivalent, Type50 optimized-equivalent |
| 11.6 | continuum emission | `freef`, `bremem`, recombination/two-photon branches | free-free/brems/emission modules and C++ kernels | mathematically/source equivalent |
| 11.6.1 | photoabsorption and Thomson-scattering opacity | bound-free opacity/rate paths and continuum opacity assembly | opacity/emergent-emissivity/native opacity paths | source-equivalent |
| 11.6.2-11.6.5 | shell-by-shell two-stream transfer and iterative passes | `step`, `trnfrc`, `trnfrn`, `stpcut`, radial loop in `xstar.f90` | `radial_transfer.py`, `radial_control.py`, native controller | source-exact control/predicate intent; object storage differs |
| 11.7 | atomic-process summary | `ucalc` data/rate-type branches and thermal/rate consumers | `ucalc.py`, rate kernels | source-exact/equivalent per qualified data/rate type |
| 12.1-12.1.2 | atomic database records; separation of data type from rate type | `readtbl`, `setptrs`, `drd`, `ucalc` | `atomic_database.py`, `ucalc.py`, native ATDB reader/rate kernels | source-exact record identity/traversal, optimized storage |
| 12.5 | atomic-data provenance | database content rather than one calculation routine | provenance/reporting layer | explanatory/provenance only |
| 14.1-14.2 | programming philosophy and flow charts | whole source tree | architecture/concordance docs | explanatory; executable source remains authoritative |

The manual's population description is especially important: XSTAR first estimates ion fractions using total ionization/recombination rates, filters/selects an adjacent set of significant ions (controlled by `critf`), then solves the full kinetic matrix for levels in those ions. That directly corresponds to the split between `ion_balance.py` and `element_equilibrium.py`.

The manual also makes the publication/transfer distinction explicit: local radiation used for rates is not identical to every spectrum ultimately exposed to an observer. This supports preserving distinct local, persisted-shell, and final-output ownership in the port.

### T. Kallman & M. Bautista (2001), “Photoionization and High-Density Gas,” *ApJS* 133, 221-253

**Scientific topic:** XSTAR v2 computational model, high-density physics, level populations, heating/cooling, recombination continuum and line escape, and LTE consistency.

Important correspondence:

| Paper topic | Equation/algorithm content | Fortran routine(s) | Python/C++ implementation | Relation |
|---|---|---|---|---|
| basic model assumptions | steady-state photoionized gas with simplified diffuse transfer/escape treatment | radial caller, transfer and escape routines | radial/escape modules | source model implements the paper's approximation; current source details prevail |
| multilevel populations | simultaneous excitation/ionization through explicit levels plus superlevels/continuum levels | `levwk*`, `calc_hmc_ion/element`, `msolvelucy` | `element_equilibrium.py`, native fixed-state engine | mathematically/source equivalent |
| Compton heating/cooling | paper equation (1) gives the nonrelativistic Compton energy exchange form | `comp2.f90` | `compton.py`, native thermal kernel | mathematically equivalent and qualified |
| bremsstrahlung cooling | paper equation (2) summarizes free-free cooling | `freef.f90`, `bremem.f90` | `free_free.py`, `bremsstrahlung.py` | mathematically/source equivalent |
| recombination/RRC | Milne-relation recombination rates and emissivity (paper equations 3-4) | photoionization/recombination `ucalc` branches, `calc_emisab_*`, `calc_emis_*` | `ucalc.py`, emissivity modules, C++ rate/spectral kernels | source-equivalent; current ATDB/data types govern details |
| continuum escape | escape suppression for optically thick recombination continua (paper equation 5) | escape-probability use in rate/emission routines | escape context and equilibrium/emissivity modules | mathematically/source equivalent |
| resonance-line escape/destruction | paper equations 6-11 and associated discussion | line escape/rate paths and `linopac` context | `pescl/pescv`, Type50/full-grid line path | source-equivalent; native Type50 traversal optimized-equivalent |
| thermal balance | heating/cooling terms assembled into a local equilibrium solution | `calc_hmc_all`, `dsec` | `local_zone.py`, `dsec.py`, thermal kernels | source-exact controller/equivalent kernels |

This paper explains *why* the code is organized around level-specific atomic data and a coupled ionization/excitation solve. The 2.59g source is used for exact data-type/rate-type branching and current control flow.

### M. A. Bautista & T. R. Kallman (2001), “The XSTAR Atomic Database,” *ApJS* 134, 139-149

**Scientific topic:** database organization, multilevel ion models, level-specific rates, detailed balance, and LTE convergence.

The paper describes a database containing level energies, wavelengths, radiative probabilities, collision rates, photoionization cross sections, recombination, collisional ionization, and fluorescence/Auger information. It emphasizes level-specific processes and multilevel models designed to approach LTE under appropriate conditions.

Correspondence:

| Paper concept | Fortran | Python/C++ | Relation |
|---|---|---|---|
| database record families and level-specific rates | packed ATDB + `readtbl`, `setptrs`, `drd`, `ucalc` | `atomic_database.py`, `ucalc.py`, native ATDB/rate kernels | source-exact identity/traversal; storage optimized |
| statistical-equilibrium balance over level transitions | `calc_hmc_ion/element`, `msolvelucy` | `element_equilibrium.py`, matrix/fixed-state engine | mathematically/source equivalent |
| continuum level representing the adjacent ion/ionization channel | compact level topology and parent/continuum pointers | derived pointers + compact basis | source-exact identities are required; 12.3.25 endpoint repair is part of qualification |
| detailed-balance/LTE design | `calc_rates_level_lte`, `levwk*`, inverse-rate branches | level/LTE/rate modules | source-equivalent |
| state-specific recombination/photoionization | ATDB data types and `ucalc` | `ucalc.py`, native rate kernels | current Fortran/data records are canonical |

This paper is the principal scientific context for treating `setptrs`/record attachment and compact level topology as part of the scientific contract rather than as disposable implementation detail.

### C. Mendoza et al. (2021), “The XSTAR Atomic Database,” *Atoms* 9, 12, DOI 10.3390/atoms9010012

**Scientific topic:** two decades of XSTAR atomic-database updates, K-line support through Z <= 30, high-density extensions, and data provenance/curation.

Use in the concordance:

- confirms that the atomic database and code are designed for broad, systematically updated data coverage rather than a fixed small set of ions;
- motivates preserving atomic-data provenance and explicit database identity/hash reporting during productization;
- provides scientific context for high-density and inner-shell/K-line data now represented in the ATDB;
- does **not** override the supplied 2.59g `setptrs`/`ucalc` executable behavior.

Related implementation: `atomic_database.py`, ATDB fingerprint/cache metadata, native ATDB reader, rate kernels, future public data/provenance API.

**Relation:** database/provenance context; source-exact behavior comes from current Fortran + ATDB.

#### Atomic-data record semantics used by the native comments

The 0.6.54 C++ comments and 0.6.55 Python comments use two source-specific distinctions from **XSTAR Manual Chapter 12** and **Mendoza et al. (2021), Appendix A**. A record's **data type** determines the formula/layout by which its constants are interpreted to calculate a rate or cross section; its **rate type** determines how XSTAR uses the returned quantity in the physical calculation. The ASCII database record header described by the manual contains six integers: data type, rate type, continuation flag, number of real values, number of integer values, and number of character values. The current `ucalc.f90` remains the executable dispatcher and therefore the final authority for present branching.

The Appendix-A families called out directly in the native implementation are:

| Data type | Source description used by the concordance | Native relevance |
|---|---|---|
| 49 | level-resolved partial photoionization cross section represented by energy/cross-section pairs | bound-free lowering and matrix/continuum ownership |
| 50 | bound-bound radiative line record containing wavelength/radiative information and lower/upper level identities | line rates, Type50 opacity/profile path, DSEC/manifold oracles |
| 51 | CHIANTI/Burgess-Tully effective collision strength for a bound-bound transition | collision-strength lowering/evaluation |
| 53 | resonance-averaged TOPbase partial photoionization cross section represented by energy/cross-section pairs | bound-free lowering and Type53 DSEC attribution |
| 63 | collisional transition probability reconstructed from quantum-defect/hydrogenic information | bound-bound collision path |
| 70 | superlevel recombination/photoionization data over density/temperature with a photoionization curve | superlevel bound-free path |
| 71 | radiative transitions from superlevels to spectroscopic levels | superlevel line path |
| 72 | satellite-level autoionization data | autoionization path |
| 76 | two-photon radiative decay | two-photon radiative branch |
| 85 | Fe K-edge photoionization parameterization | inner-shell bound-free path |
| 86 | Auger/radiative widths of a K-vacancy level | K-vacancy width/rate path |
| 88 | damped-excess photoionization cross section to a K-shell superlevel | K-shell bound-free path |
| 91 | APED radiative line data | routed by current `ucalc.f90` through Type-50 radiative handling |
| 95 | level collisional-ionization fit | collisional-ionization path |
| 98 | variable-length CHIANTI/Burgess-Tully effective collision-strength record | general collision-strength evaluator |
| 99 | newer superlevel recombination/photoionization table | superlevel bound-free/recombination path |

Types **89, 96, and 97** are present in the supplied current `ucalc.f90` but are not enumerated in the requested Appendix-A/Chapter-12 data-type snapshots. Comments for those branches therefore identify the **current executable Fortran source**, not the two reference tables, as their semantic basis.

### T. R. Kallman, D. Liedahl, A. Osterheld, W. Goldstein & S. Kahn (1996), “Photoionization Equilibrium Modeling of Iron L Line Emission,” *ApJ* 465, 994-1009

**Scientific topic:** detailed Fe L emission in photoionized gas, including the importance of recombination cascades and multilevel line formation.

Use in the concordance:

- supports the need for explicit excited-level populations and recombination cascades in photoionized spectra;
- provides scientific context for line/RRC emissivity products and for high-lying/superlevel treatment;
- is not used as the exact current control-flow specification because the modern XSTAR 2.59g implementation and 2001/2025 descriptions supersede its software details.

Related Fortran: level/rate solve, recombination and line emissivity paths.  
Related Python/C++: `element_equilibrium.py`, emissivity/line kernels.  
**Relation:** scientific context; current implementation is source-equivalent to modern Fortran, not asserted to be a line-by-line implementation of the 1996 model.

### T. R. Kallman, P. Palmeri, M. A. Bautista, C. Mendoza & J. H. Krolik (2004), “Photoionization Modeling and the K Lines of Iron,” *ApJS* 155, 675-701

**Scientific topic:** Fe K-shell line emission/absorption using improved inner-shell atomic data, fluorescence/Auger processes, and damped photoionization resonances.

Use in the concordance:

- provides physical context for inner-shell photoionization/Auger branches and K-vacancy line formation;
- reinforces that line/edge observables depend on detailed level populations and source atomic data, not just total ion fractions;
- supports keeping database/data-type provenance visible in future APIs.

Related Fortran: inner-shell/fluorescence/Auger `ucalc` data types, level population solve, line/opacity paths.  
Related Python/C++: `ucalc.py` typed rate families, matrix/rate kernels, line/full-grid spectral code.  
**Relation:** scientific/data context; exact modern branching is governed by XSTAR 2.59g and the supplied ATDB.

## Equations and algorithm ownership

The literature describes physics in continuous mathematical notation, while the source defines discrete grids, record traversal, numerical kinds, cutoffs, and publication ordering. The project therefore uses the following correspondence rules.

### Ionization parameter

The manual states the optically thin scaling with `xi = L/(n R^2)`, with `L` integrated over 1-1000 Ry. The implementation relation is **mathematically equivalent**, subject to source-specific units, spectrum integration, and default-REAL radius semantics.

### Statistical equilibrium

The papers/database descriptions express each level equation as total population flow in equals total flow out, with a conservation equation replacing one row. `calc_hmc_ion/element` plus `msolvelucy` are the executable realization. Python/C++ are considered **source-equivalent**, not merely equation-equivalent, because endpoint topology, record order, active ion selection, and normalization are part of qualification.

### Recombination and RRC emission

Kallman & Bautista (2001) relate recombination rates/emissivities to photoionization cross sections through the Milne relation and describe escape suppression. In the implementation, the current ATDB data types and `ucalc` branches determine the exact quadratures/fits and inverse-rate construction. `calc_emisab_*` and `calc_emis_*` then expose integrated and full-grid products.

### Line escape and Type50

The manual and 2001 paper describe complete-redistribution/escape-probability line treatment and continuum destruction. The source additionally specifies discrete line profile/bin accumulation (`linopac`) and source ordering. The C++ Type50 implementation is therefore classified **optimized-equivalent**, with equivalence established by the accepted Type50 and downstream product gates rather than by the analytic escape formula alone.

### Continuum transfer

The manual describes shell-by-shell transfer with inward/outward diffuse radiation and iterative passes. The source implements the discrete realization in `xstar.f90`, `trnfrc`, `trnfrn`, `step`, and `stpcut`. Python factors these into explicit workspaces and functions but is classified **source-exact in control/predicate semantics**.

## What the papers do not define for this port

The supplied papers/manuals do not, by themselves, define:

- exact Python/C++ object layout;
- exact floating-point kind/promotion for every source literal;
- fixed-capacity STEP rank identity behavior;
- the accepted comparator distinction between material numerical science and structural inventory;
- the exact 45.3.3.8 C5/Ca/O publication policy;
- the frozen C++ production ABI or optimization implementation.

Those are governed by accepted qualification evidence and the canonical source.

## Reference bundle inventory

The Milestone 2 review used these supplied PDFs:

- XSTAR Team, *XSTAR Manual*, Release 2.5x, 20 Dec 2025.
- Kallman, T. & Bautista, M. (2001), *Photoionization and High-Density Gas*, ApJS 133, 221-253.
- Bautista, M. A. & Kallman, T. R. (2001), *The XSTAR Atomic Database*, ApJS 134, 139-149.
- Kallman, T. R., Liedahl, D., Osterheld, A., Goldstein, W. & Kahn, S. (1996), *Photoionization Equilibrium Modeling of Iron L Line Emission*, ApJ 465, 994-1009.
- Kallman, T. R., Palmeri, P., Bautista, M. A., Mendoza, C. & Krolik, J. H. (2004), *Photoionization Modeling and the K Lines of Iron*, ApJS 155, 675-701.
- Mendoza, C. et al. (2021), *The XSTAR Atomic Database*, Atoms 9, 12, DOI 10.3390/atoms9010012.

The PDFs are reference inputs; they are not copied into the normal `xstar_tools` distribution by this milestone.
