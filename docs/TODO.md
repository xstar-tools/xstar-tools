# XSTAR `atdb.fits` Python Reader TODO / Development Roadmap

## 1. Overall target

The long-term target is a fully developed Python package for reading, decoding, querying, and exporting the XSTAR atomic database FITS file:

```text
./xstar/data/atdb.fits
```

The final product should support:

```python
from xstar_atomic import XSTARATDB

db = XSTARATDB("./xstar/data/atdb.fits")

levels = db.levels(element="O", ion_stage=8)
lines = db.lines(element="O", ion_stage=8)
pi = db.photoionization(element="O", ion_stage=8)
coll = db.collisions(element="O", ion_stage=8, temperatures=[1e6, 3e6, 1e7])
emis = db.emissivity_table(element="O", ion_stage=8, temperatures=[1e6, 3e6, 1e7])
```

It should also provide command-line tools for exporting compact atomic tables for X-ray/superwind calculations.

---

## 2. Immediate next steps

### 2.1 Validate the emissivity table builder

Run:

```bash
python xstar_atomic_make_emissivity_table_v1.py ./xstar/data/atdb.fits \
  --element O \
  --ion-stage 8 \
  --wavelength-min 18.8 \
  --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7 \
  --out-csv o8_lya_emissivity.csv \
  --summary-json o8_lya_emissivity_summary.json \
  --print-summary
```

Check:

1. O VIII Lyα has matched collision records.
2. The strongest line coefficient is for the `2p 2P_3/2 → 1s` component.
3. The emissivity coefficient increases strongly from `1e6` to `1e7 K`.
4. Branching ratios are close to 1 for simple two-level decays where appropriate.

Then run:

```bash
python xstar_atomic_make_emissivity_table_v1.py ./xstar/data/atdb.fits \
  --element Ne \
  --ion-stage 10 \
  --wavelength-min 12.0 \
  --wavelength-max 12.3 \
  --temperatures 1e6 1e7 \
  --out-csv ne10_lya_emissivity.csv \
  --print-summary
```

### 2.2 Validate O VII direct-excitation type-63 emissivities

Run:

```bash
python xstar_atomic_make_emissivity_table_v1.py ./xstar/data/atdb.fits \
  --element O \
  --ion-stage 7 \
  --lower-level 1 \
  --temperatures 1e6 3e6 1e7 \
  --out-csv o7_direct_emissivity.csv \
  --summary-json o7_direct_emissivity_summary.json \
  --print-summary
```

Check whether the type-63 evaluated rates are properly joined to radiative decays from the same upper levels.

### 2.3 Add a better unmatched-line diagnostic

For important lines such as the O VII triplet:

```bash
python xstar_atomic_make_emissivity_table_v1.py ./xstar/data/atdb.fits \
  --element O \
  --ion-stage 7 \
  --wavelength-min 21.4 \
  --wavelength-max 22.2 \
  --temperatures 1e6 3e6 1e7 \
  --include-unmatched-lines \
  --out-csv o7_triplet_line_status.csv \
  --print-summary
```

The script should clearly report:

```text
line present in radiative table
collision record present / absent
recombination or cascade may be required
```

---

## 3. Refactor scripts into a package

The current work is split into separate scripts. The next engineering step is to refactor them into a package:

```text
xstar_atomic/
  __init__.py
  core.py                 # XSTARATDB class
  packed.py               # low-level POINTERS/REALS/INTEGERS/CHARS reader
  hierarchy.py            # element/ion/record hierarchy
  labels.py               # element symbols, Roman numerals, charge labels
  levels.py               # type 6 decoder
  lines.py                # type 50 decoder
  photoionization.py      # type 53/49/59/99 decoders
  collisions.py           # type 56/63/51/98 decoders
  recombination.py        # type 1/7/22/30/38/39 decoders
  ionization.py           # type 57/95 etc.
  auger.py                # Fe K / Auger / fluorescence records
  emissivity.py           # direct excitation and later level-population emissivity
  export.py               # CSV/Parquet/HDF5 exporters
  cli.py                  # command-line entry point
  tests/
```

### 3.1 Central class

Create:

```python
class XSTARATDB:
    def __init__(self, path, memmap=True): ...
    def summary(self): ...
    def elements(self): ...
    def ions(self, element=None, Z=None): ...
    def levels(self, element, ion_stage): ...
    def lines(self, element, ion_stage, wavelength=None, energy=None): ...
    def photoionization(self, element, ion_stage, level=None): ...
    def collisions(self, element, ion_stage, temperatures=None): ...
    def emissivity_table(self, element, ion_stage, temperatures): ...
```

### 3.2 Avoid duplicated decoding

Currently, each script imports or reproduces some logic. Refactor shared functions into reusable modules:

```text
read_record()
decode_level_record()
decode_line_record()
decode_pi_record_type53()
decode_collision_record_type56()
decode_collision_record_type63()
```

---

## 4. Extend physical decoders

## 4.1 Photoionization decoders

### Type 53: OP photoionization cross sections

Status: partially validated and usable.

Next steps:

1. Confirm how XSTAR sums multiple type-53 components for the same lower level.
2. Add optional merged cross-section output.
3. Add interpolation onto user-provided photon-energy grids.
4. Add threshold and resonance diagnostics.
5. Validate against O VII, O VIII, Ne IX, Ne X, Fe ions.

Deliverables:

```text
photoionization_components.csv
photoionization_grid.csv
photoionization_merged_grid.csv
```

### Type 49: OP inner-shell photoionization

Status: identified, not fully decoded.

Next steps:

1. Inspect representative type-49 records for O, Ne, Mg, Si, S, Fe.
2. Compare with `ucalc.f90` logic for type 49.
3. Decode threshold, level mapping, cross-section grid, and inner-shell flags.
4. Validate near K-shell edges.

Priority: high for X-ray opacity and inner-shell features.

### Type 59: Verner photoionization cross sections

Status: coefficient records identified, not fully evaluated.

Next steps:

1. Port the Verner formula used in XSTAR.
2. Export coefficients and evaluated grids.
3. Validate threshold and high-energy behavior.

### Type 99: newer/superlevel photoionization records

Status: identified, not decoded.

Next steps:

1. Inspect `ucalc.f90` and `calt99` logic.
2. Decode coefficients.
3. Decide whether type 99 should be exported as coefficients or evaluated grid.

---

## 4.2 Collisional excitation decoders

### Type 56: tabulated effective collision strengths

Status: validated.

Next steps:

1. Confirm interpolation behavior exactly matches XSTAR.
2. Add optional extrapolation policy flags:
   ```text
   clamp
   extrapolate
   return NaN
   ```
3. Validate additional ions and transitions.

### Type 63: Bautista n,l algorithmic collisions

Status: partially implemented.

Implemented:

```text
nf != ni and |Δl| = 1
```

Next steps:

1. Compare `v2b` explicit-branch output against native XSTAR for a controlled model.
2. Implement same-n l-changing branch using `amcrs`.
3. Add support for density-dependent parameters if needed.
4. Clarify whether `q_deexcitation_cm3_s` should use shell or resolved-level degeneracy in all branches.
5. Add unit tests against known values.

### Type 51: OP/CHIANTI Burgess-Tully collisions

Status: identified, needs full validation.

Next steps:

1. Inspect representative type-51 records.
2. Port `upsil.f90` / `upsiln.f90` logic.
3. Decode transition type, scaling parameter, BT grid, and Υ(T).
4. Validate using non-H-like ions with known CHIANTI transitions.

### Type 98: CHIANTI 2016 collisions

Status: identified, needs validation.

Next steps:

1. Inspect type-98 records.
2. Port the type-98 branch from `ucalc.f90`.
3. Compare with CHIANTI values where possible.

### Type 68, 69, 73: He-like and satellite collision strengths

Status: identified, not implemented.

Next steps:

1. Decode type 68: Zhang & Sampson He-like collision strengths.
2. Decode type 69: Kato & Nakazaki He-like collision strengths.
3. Decode type 73: satellite-level collisional strengths.
4. Validate O VII, Ne IX, Mg XI, Si XIII He-like features.

Priority: high for He-like X-ray triplets.

---

## 4.3 Radiative line and level decoders

### Type 6: levels

Status: validated for common ions.

Next steps:

1. Improve parsing of level labels into configuration, term, J.
2. Add parity if present or inferable.
3. Add robust quantum-number validation.
4. Add level-group/superlevel flags.

### Type 50: radiative lines

Status: validated.

Next steps:

1. Validate weaker transitions and forbidden/intercombination lines.
2. Handle type-50 records with `rate_type=9` two-photon style records separately.
3. Confirm oscillator-strength formula for all line classes.
4. Add wavelength-vacuum/air convention note, likely vacuum for X-ray.

### Type 76: two-photon decay

Status: identified, not implemented.

Next steps:

1. Decode type-76 records.
2. Add continuum/two-photon emissivity output.

### Type 82/83: Fe UTA lines and levels

Status: identified, not implemented.

Next steps:

1. Decode Fe UTA levels, type 83.
2. Decode Fe UTA radiative rates, type 82.
3. Validate Fe M-shell UTA wavelengths.

---

## 4.4 Recombination decoders

Important recombination data types:

```text
type 1   radiative recombination: Aldrovandi & Pequignot
type 7   dielectronic recombination: Aldrovandi & Pequignot
type 22  dielectronic recombination: Storey
type 30  hydrogenic radiative recombination: Gould & Thakur
type 38  recombination-like, label still incomplete
type 39  recombination-like, label still incomplete
type 74  DR delta-function additions to photoionization cross sections
```

Next steps:

1. Decode total recombination rates.
2. Decode level-resolved recombination where possible.
3. Add recombination contributions to line emissivity.
4. Validate against known recombination coefficients.
5. Add recombination/cascade contribution for O VII triplet lines.

Priority: high for photoionized plasma emissivities.

---

## 4.5 Collisional ionization decoders

Important data types:

```text
type 57  effective charge for collisional ionization
type 95  Bryans collisional ionization / CI total rates
rate type 15  CI total rate
rate type 5   bound-free collision from level
```

Next steps:

1. Decode total CI rates.
2. Decode level-specific collisional ionization rates.
3. Validate against Bryans et al. or XSTAR outputs.

---

## 4.6 Auger, fluorescence, and Fe K decoders

Important data types:

```text
type 85  Iron K photoionization cross sections, spectator Auger summed
type 86  Iron K Auger data
rate 41  Auger decay / Fe K Auger
rate 42  fluorescence / Auger-related
type 88  unlabeled but likely related to newer Auger/fluorescence channels
```

Next steps:

1. Decode type 85 Fe K PI cross sections.
2. Decode type 86 Auger yields/rates.
3. Decode rate types 41 and 42.
4. Validate Fe K edge and Kα/Kβ fluorescence channels.

Priority: high for X-ray reflection/absorption models.

---

## 5. Build validation suite

Create a validation directory:

```text
validation/
  validate_lines.py
  validate_photoionization.py
  validate_collisions.py
  validate_emissivity.py
  reference_cases.yaml
```

### 5.1 Line validation cases

Use known strong lines:

| Ion | Feature | Expected wavelength |
|---|---|---:|
| O VII | He-like triplet | 21.60–22.10 Å |
| O VIII | Lyα | 18.97 Å |
| Ne IX | He-like triplet | 13.45–13.70 Å |
| Ne X | Lyα | 12.13 Å |
| Mg XI | He-like triplet | 9.17–9.31 Å |
| Mg XII | Lyα | 8.42 Å |
| Si XIII | He-like triplet | 6.65–6.74 Å |
| Si XIV | Lyα | 6.18 Å |
| S XV | He-like triplet | 5.04–5.10 Å |
| Fe XXV | Kα complex | ~1.85 Å |
| Fe XXVI | Lyα | ~1.78 Å |

### 5.2 Photoionization validation cases

Use thresholds:

| Ion | Level | Expected threshold |
|---|---|---:|
| O VII | ground | ~739 eV |
| O VIII | ground | ~871 eV |
| Ne X | ground | ~1360 eV |
| Fe XXVI | ground | high-Z hydrogenic threshold |

### 5.3 Collision validation cases

Validated cases so far:

```text
O VIII Lyα type-56
Ne X Lyα type-56
O VII 1s2 → np type-63
```

Need additional cases:

```text
He-like triplet special collision channels
CHIANTI type-51 or type-98 transitions
Fe transitions
```

### 5.4 Native XSTAR comparison

Run a small XSTAR model and compare:

1. Selected level populations.
2. Selected line emissivities.
3. Selected ionization/recombination rates.
4. Heating/cooling contributions if possible.

This is necessary before claiming exact XSTAR parity.

---

## 6. Improve emissivity model

### 6.1 Current model

The current emissivity table uses direct excitation plus branching ratio:

```text
j_ul / (n_e n_ion) = q_excitation_to_upper × branching_ratio × hν
```

This is useful but incomplete.

### 6.2 Next emissivity improvements

Add:

1. Multiple collision paths feeding the same upper level.
2. Cascades from higher levels.
3. Recombination into excited levels.
4. Dielectronic recombination satellite emission.
5. Two-photon continua.
6. Density-sensitive collisional coupling.
7. Full statistical equilibrium solver.

### 6.3 Full level-population solver

Eventually solve:

```text
Σ_j n_j R_ji - n_i Σ_j R_ij = 0
Σ_i n_i = n_ion
```

where rates include:

```text
radiative decay
collisional excitation/de-excitation
photoexcitation
photoionization
recombination
collisional ionization
Auger/autoionization
```

For a first collisional-radiative model, include only:

```text
radiative decay + electron collisions
```

Then extend to photoionized plasma terms.

---

## 7. Export formats

Support multiple outputs:

### 7.1 CSV

Good for inspection and debugging:

```text
levels.csv
lines.csv
photoionization_components.csv
photoionization_grid.csv
collisions_summary.csv
collision_rates.csv
emissivity_table.csv
```

### 7.2 Parquet

Recommended for large tables:

```text
atomic/xstar_levels.parquet
atomic/xstar_lines.parquet
atomic/xstar_photoionization.parquet
atomic/xstar_collisions.parquet
```

### 7.3 HDF5

Useful for Athena++ / superwind pipeline integration:

```text
atomic/xstar_atomic_subset.h5
```

Suggested HDF5 layout:

```text
/elements
/ions
/levels
/lines
/photoionization/components
/photoionization/grids
/collisions/summary
/collisions/rates
/emissivity/direct_excitation
```

---

## 8. Command-line interface roadmap

Create one unified CLI:

```bash
xstar-atomic summary ./xstar/data/atdb.fits
xstar-atomic elements ./xstar/data/atdb.fits
xstar-atomic ions ./xstar/data/atdb.fits --element O
xstar-atomic levels ./xstar/data/atdb.fits --element O --ion-stage 8
xstar-atomic lines ./xstar/data/atdb.fits --element O --ion-stage 8 --wavelength 18.8 19.1
xstar-atomic photoionization ./xstar/data/atdb.fits --element O --ion-stage 8 --level 1
xstar-atomic collisions ./xstar/data/atdb.fits --element O --ion-stage 8 --temperatures 1e6 3e6 1e7
xstar-atomic emissivity ./xstar/data/atdb.fits --element O --ion-stage 8 --temperatures 1e6 3e6 1e7
```

---

## 9. Testing and quality control

### 9.1 Unit tests

Add tests for:

```text
record pointer decoding
string decoding
level decoding
line decoding
photoionization type 53 decoding
collision type 56 interpolation
collision type 63 nf != ni branch
Roman numeral conversion
energy/wavelength conversion
branching ratio calculation
```

### 9.2 Regression tests

Save small JSON reference outputs for:

```text
O VIII Lyα lines
O VIII ground PI
O VIII type-56 collisions
O VII type-63 direct excitation
Ne X Lyα lines/collisions
Fe XXVI Lyα lines
```

### 9.3 Performance tests

Measure:

```text
time to load header/pointers only
time to build hierarchy
time to extract one ion
time to export all lines
time to export all photoionization grids
memory usage with memmap
```

---

## 10. Documentation to write

Create:

```text
docs/
  atdb_format.md
  record_types.md
  rate_types.md
  examples_lines.md
  examples_photoionization.md
  examples_collisions.md
  examples_emissivity.md
  validation.md
```

### 10.1 `atdb_format.md`

Explain:

```text
POINTERS/REALS/INTEGERS/CHARS layout
record header format
1-based Fortran pointers
memmap strategy
```

### 10.2 `record_types.md`

Maintain a table of every data type:

```text
data type
rate type
label
count
decoder status
Fortran routines involved
Python implementation status
```

### 10.3 `examples_emissivity.md`

Show how to create emissivity-ready tables for:

```text
O VIII Lyα
Ne X Lyα
O VII direct-excitation lines
Fe XXVI Lyα
```

---

## 11. Suggested priority order

### Priority A: make current useful product robust

1. Validate `xstar_atomic_make_emissivity_table_v1.py`.
2. Package low-level reader, hierarchy, levels, lines, type-53 PI, type-56/type-63 collisions.
3. Add tests for O VIII, O VII, Ne X, Fe XXVI.
4. Export compact tables for H, He, C, N, O, Ne, Mg, Si, S, Fe.

### Priority B: improve X-ray line emissivity coverage

1. Implement type-51 collisions.
2. Implement type-98 collisions.
3. Implement He-like type-68/type-69 collision records.
4. Add recombination contributions for He-like triplets.
5. Add cascade handling.

### Priority C: improve opacity/photoionization

1. Finish type-49 inner-shell PI.
2. Finish type-59 Verner PI.
3. Finish type-99 superlevel PI.
4. Add merged cross-section grids.

### Priority D: special high-energy features

1. Implement Fe UTA type 82/83.
2. Implement Fe K PI type 85.
3. Implement Auger/fluorescence type 86/rate 41/42.

### Priority E: full XSTAR-like model support

1. Recombination rates.
2. Collisional ionization rates.
3. Statistical equilibrium solver.
4. Comparison to native XSTAR outputs.
5. Heating/cooling contributions.

---

## 12. Current definition of “done” for the full reader

The Python reader can be considered fully developed when it can:

1. Open `atdb.fits` with low memory usage.
2. Decode all element, ion, level, line, photoionization, collision, recombination, ionization, Auger, and fluorescence records.
3. Query by element, ion, level, wavelength, energy, data type, and rate type.
4. Evaluate temperature-dependent rates for supported physical processes.
5. Export compact subsets for simulation/post-processing pipelines.
6. Reproduce known X-ray wavelengths, thresholds, and rates.
7. Match selected native XSTAR outputs within numerical tolerance.
8. Provide a documented public Python API and CLI.
## Post-0.6.48.9.5.1 performance/generalization order

1. 0.6.48.9.6 — Type50 hot-loop cleanup (`rccemis += 0.0` removal, direct source-order `opakc`, deeper exact profile/rebin optimization), target ~21.5–23 s.
2. 0.6.48.9.7 — compact record state plus PGO/native build tuning, target ~20–22 s.
3. Only after 9.6/9.7: multi-element qualification and systematic replacement of runtime `element_z == 12` specializations with record/ATDB-driven semantics where source behavior permits.



## Post-0.6.48.9.7 Python+C++ product optimization

1. **0.6.48.10.0** — automatically promote the accepted native C++ final `binemis` product kernel for accelerated Python; target ~254.8 s -> ~1 s while freezing zone/controller science.
2. **0.6.48.10.1** — expose the accepted native final zero-thickness recomputation to accelerated Python; current Python reference cost ~71.75 s.
3. **0.6.48.10.2** — profile any remaining Python-side product/state construction only after 10.0/10.1 are accepted.
4. Multi-element qualification/generalization remains separate from these performance-only writer changes.
