# Reference data and release candidates

Current release candidates use a compact reference boundary.

- `references/current/` catalogs the small active local/external reference policy.
- `qualification/frozen/` contains frozen comparator/reference code required to enforce accepted science.
- `qualification/parity_freeze_current_source_hashes.json` pins exact active science-critical source bytes.
- `xstar_test_run/` retains small reference CSVs still consumed by runtime/regression code.
- `atdb.fits` remains external and must not be bundled.

Closed milestone reports, forensic scripts, and predecessor replay manifests are
not release inputs after `0.6.90.3`; version-control history and tags preserve
those records.

Before producing a release candidate run:

```bash
python tools/ci/check_tree_clean.py
python tools/ci/check_package_metadata.py
python tools/qualification/check_parity_freeze.py
python tools/qualification/check_source_concordance.py
python tools/release/check_release_candidate.py
```
