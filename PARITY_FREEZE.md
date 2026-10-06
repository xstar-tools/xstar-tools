# Scientific parity freeze

The scientific behavior of `xstar-tools` is frozen at science revision
`0.6.90.5.5`. The canonical scientific oracle remains **FORTRAN XSTAR 2.59g**.
Repository/package version numbers may advance independently of this science
revision.

The science revision is `0.6.90.5.5` because that is the milestone where the
scientific behavior changed: native Type-49 lowering was corrected to honor the
FORTRAN source-side early-return contract for source-inactive records, including
the Mn record that previously caused a `short payload` failure. Versions
`0.6.90.5.6` and `0.6.90.5.7` changed terminal diagnostics only. The corrected
science was explicitly requalified and re-frozen in package `0.6.90.5.8`.

## Frozen contracts

- science revision: `0.6.90.5.5`
- C API ABI: `60487`
- production-zone ABI: `6048110`
- fixed-state program ABI: `60486`
- fixed-state engine ABI: `60488`
- XSPEC-table ABI: `1`
- no `-ffast-math` or `-Ofast`
- preserve `-ffp-contract=off`
- `atdb.fits` remains external and is never bundled

## 0.6.90.5.8 science requalification

The requalification uses an all-elements standalone model with every elemental
multiplier from H through Zn set to `1`, including `mnabund=1`. The same input
was run through FORTRAN XSTAR 2.59g and `xstar-cpp`.

The accepted evidence is recorded in
`qualification/mn_type49_science_refreeze_0_6_90_5_8.json`. Important gates are:

- the three formatted STEP/progress rows are exact, including `ntotit = 12, 6, 6`;
- Mn ionic fractions have maximum normalized L1 `4.59931087e-3`;
- Mn heating normalized L1 is `8.78536108e-4` and Mn cooling is `7.22863175e-4`;
- total heating/cooling normalized L1 values are approximately `6.5e-4`;
- public continuum and spectrum emitted arrays are below `7.4e-4` normalized L1;
- RRC emitted arrays are `6.99e-4` normalized L1 with identical row count and energy grid;
- 599 of the 600 strongest line identities are common at the rank cutoff; common-line wavelengths are exact and emitted luminosities are about `1.15e-3` normalized L1;
- first-zone detailed-product inventory differences are retained as structural diagnostics; later-zone row inventories agree, and these structural differences are not treated as a material-science failure.

The material acceptance envelope remains normalized L1 `< 0.01`, consistent
with the established comparator policy.

Run the focused acceptance gate with:

```bash
python tools/qualification/check_mn_type49_science_refreeze.py
```

## Local freeze enforcement

`qualification/parity_freeze.json` is the compact policy record.
`qualification/parity_freeze_current_source_hashes.json` stores exact raw
SHA-256 hashes of all active science-critical source files in the accepted
`0.6.90.5.8` refreeze tree.

Run:

```bash
python tools/qualification/check_mn_type49_science_refreeze.py
python tools/qualification/check_source_concordance.py
python tools/qualification/check_parity_freeze.py
```

The parity gate verifies the compact policy, frozen comparator/reference hashes,
all current science-critical source hashes, ABI constants, compiler
floating-point policy, the Python/native science revision, the external
`atdb.fits` policy, and the bound Mn/Type-49 requalification record.

## Preserved frozen references

The release tree retains the compact historical material needed to enforce and
interpret the accepted boundary:

- `qualification/frozen/cpp44/production_source_hashes_44.json`
- `qualification/frozen/option15/compare_step_log_science.py`
- `qualification/frozen/option23/compare_step_log_science.py`
- `qualification/frozen/option23/selftest_option23_comparator.py`
- `qualification/parity_freeze_science_hashes.json` (historical/original science hashes)
- `qualification/parity_freeze_current_source_hashes.json` (current refrozen source hashes)
- `qualification/mn_type49_science_refreeze_0_6_90_5_8.json`

Closed milestone reports, one-off forensic scripts, and predecessor replay
checkers remain in repository history/tags rather than being copied into every
future source release.

## Change control

Packaging, documentation, diagnostics, CI, repository-layout, and non-science
refactors may advance the package version only when the parity-freeze gate
remains exact. Any further intentional science change must create a new
explicit FORTRAN-concordance qualification record and then rebaseline the
current source hashes under a new real science milestone; it must not silently
modify this freeze record.
