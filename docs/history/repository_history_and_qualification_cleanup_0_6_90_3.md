# 0.6.90.3 — REPOSITORY_HISTORY_AND_QUALIFICATION_CLEANUP

`0.6.90.3` is a structural repository cleanup following the formally closed
`0.6.90` conda campaign. It changes no XSTAR science, science-critical source
bytes, ABI values, atomic-data policy, or production runtime behavior.

The milestone removes closed one-off qualification machinery and historical
reports from active release trees, consolidates the scientific freeze into a
compact current gate, simplifies packaging/release utilities, removes generated
cache/build artifacts, and keeps only current/frozen reference assets needed by
active regression checks. Historical detail remains available through
version-control history and release tags.

## Cleanup result

Relative to the accepted `0.6.90.2` source archive:

| Area | `0.6.90.2` | `0.6.90.3` |
|---|---:|---:|
| root Markdown files | 757 | 5 |
| top-level test Python files | 224 | 61 |
| `qualification/` files | 258 | 19 |
| `tools/` files | 638 | 22 |
| `tools/qualification/` files | 615 | 4 |
| `references/` files | 14 | 11 |
| `docs/` files | 201 | 93 |
| total active source-tree files | 2452 | 565 |

The remaining `tests/` files are current behavioral/regression tests rather
than closed runner/manifests replay tests. Historical fixtures are retained
only where active tests or runtime reference paths still consume them.

## Frozen scientific boundary

The exact active science-critical bytes are pinned in
`qualification/parity_freeze_current_source_hashes.json`, captured from the
accepted `0.6.90.2` predecessor. The compact parity gate additionally pins the
frozen comparator/reference artifacts, public ABI values, compiler
floating-point policy, science revision, and external `atdb.fits` contract.

Preserved contracts include:

- science revision `0.6.48.12.3.45.3.3.8`;
- C API ABI `60487`;
- production-zone ABI `6048110`;
- fixed-state program/engine ABIs `60486` / `60488`;
- XSPEC-table ABI `1`;
- no `-ffast-math` / `-Ofast`, with `-ffp-contract=off` retained;
- `atdb.fits` external;
- normal build non-MPI, with MPI explicit.

## Acceptance

The cleaned tree passes:

```bash
python tools/ci/check_tree_clean.py
python tools/ci/check_package_metadata.py
python tools/ci/check_python_contract.py
python tools/ci/check_text_policy.py
python tools/qualification/check_parity_freeze.py
python tools/qualification/check_source_concordance.py
python tools/release/check_release_candidate.py
```

The compact parity gate verifies all 51 pinned active science-critical source
files byte-for-byte. The source-concordance gate validates all 18 current
Fortran/Python/C++ correspondence entries.

In the available build environment, the dependency-light pytest pass completed
with `258 passed, 5 skipped`. Two retained test modules (six tests total) require
`astropy`, which was not installed in that environment; an attempted dependency
installation could not reach PyPI because the environment had no network/name
resolution. Those tests remain in the suite and are exercised by normal CI,
which installs project dependencies.
