# Current references and release-candidate boundary

Milestone 11 creates a stable metadata layer for current scientific/reference
fixtures without rewriting the parity campaign's historical evidence.

## Current catalog

`references/current/reference_manifest.json` is the entry point. It pins the
accepted science revision, C++ baseline, ABIs, the 62-case registry, current
acceptance policy, structural exceptions, external benchmark assets, and local
content hashes.

The 62-case registry is derived from the already-qualified frozen C++44 exact
comparison. It records element, density regime, ionization regime, default smoke
status, routine-smoke eligibility, and any qualified Fortran publication
exception class. It is metadata only; it does not redefine model science.

Large all-62 products remain external. The known frozen C++44 archive SHA-256 is
required exactly. Historical archive hashes that were never recorded are kept as
unknown rather than reconstructed or guessed.

## Structural exceptions

`references/current/structural_exceptions.json` makes the accepted exceptions
first-class metadata:

- Ca `ca19_xi2_ne1` and O `o7_ne1e10` detail3 inventory differences remain
  accepted under the frozen <1% material criterion;
- C5 709/762 behavior remains frozen and is not a default smoke prerequisite;
- Fortran Option 24's stale-local publication quirk remains quarantined rather
  than propagated into Python/C++;
- frozen C++/Fortran publication-only semantic classes remain diagnostics and
  do not override material numerical science.

## Historical data

Historical fixture bytes stay at their qualified locations, including
`tests/fixtures/historical/` and `historical/qualification/`. The current catalog
points to current compatibility inputs such as `xstar_test_run/` by exact hash
instead of moving them and perturbing frozen source/runtime assumptions.

## Public release-candidate boundary

A release-candidate tag (`v<package-version>rcN`) triggers
`.github/workflows/release-candidate.yml`. The static boundary requires:

1. clean source tree and package metadata;
2. parity-freeze integrity;
3. Milestone-10 layered-CI integrity;
4. Milestone-11 current-reference integrity;
5. package version/tag compatibility;
6. required release workflows for packaging, conda, docs, and Tier-3 all-62.

The release-candidate workflow is not a substitute for the dynamic evidence.
A candidate is publishable only after the tag's sibling CI workflows complete:

- Tier 0 contracts;
- selected Tier 1 science smoke when applicable;
- Tier 2 five-backend parity;
- Tier 3 all-62 release qualification;
- sdist, wheels, clean wheel install, editable install, conda, and docs;
- changelog/citation/license/data audit;
- performance report when controlled hardware is available (report-only,
  separate from science acceptance).

No global runtime average is a scientific release gate.
