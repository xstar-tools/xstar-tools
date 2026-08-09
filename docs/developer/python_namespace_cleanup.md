# Active Python namespace cleanup

**Productization version:** `0.6.56`  
**Science revision:** `0.6.48.12.3.45.3.3.8`

The long parity campaign accumulated one-off audit, attribution, closure, replay, and oracle utilities directly beside the production Python implementation in `src/xstar_tools/xstar/`. Distribution `0.6.56` separates that historical tooling from the installed runtime namespace.

## Decision rule

A module was archived only when all of the following held:

1. it was a parity/qualification campaign utility rather than a production scientific implementation;
2. it had no live runtime caller in the active Python source graph;
3. its remaining active references were dedicated historical/versioned tests or an obsolete audit-only console command;
4. moving it did not modify any shared active `src/` file or any parity-pinned scientific source.

Files that merely *look* diagnostic but still have live callers were retained. Examples include `continuum_diagnostics.py`, `physical_output_parity.py`, `radial_spectrum_parity.py`, `type50_profile_provenance.py`, `zone1_dsec_diagnostic.py`, and `diagnostic_v0648123452.py`.

## Archived modules

The 51 modules are preserved byte-for-byte under:

`historical/python/xstar_parity_campaign/src/xstar_tools/xstar/`

They comprise:

- 5 `all61_*` parity-campaign diagnostics;
- 2 call-1 thermal audits;
- 19 call-2 helium attribution/correction utilities;
- 5 obsolete installed audit commands (`fixed_state_parity`, `he_bound_free_audit`, `type53_semantics`, `helium_family_isolation`, `type50_manifold_audit`);
- 20 other qualification-only matrix/thermal/solver closure, attribution, parity, or oracle utilities.

The exact path map and SHA-256 values are in `qualification/python_history_cleanup_0_6_56.json` and `historical/relocation_manifest.json`.

## Archived tests and commands

Thirty-six tests whose purpose was to exercise the archived modules moved with them under `historical/python/xstar_parity_campaign/tests/`. Five obsolete console commands were removed from `pyproject.toml`:

- `xstar-tools-fixed-state-parity`
- `xstar-tools-he-bound-free-audit`
- `xstar-tools-type53-semantics`
- `xstar-tools-helium-family-isolation`
- `xstar-tools-type50-manifold-audit`

These were qualification tools for superseded pre-freeze campaigns, not current runtime/public commands.

## Remaining ambiguous/facade modules

A second-pass orphan scan still finds a small set of modules with no static inbound import in the current tree, including facade/source-port surfaces such as `runtime.py`, `standalone.py`, `thermal.py`, `transfer.py`, `opacity.py`, `ionization.py`, `stepping.py`, `inventory.py`, and `complete_local_zone.py`. They are deliberately retained in `0.6.56`: absence of an internal caller is not enough to prove that an intended public/source-port facade is dead. Removing those should be part of the later public API/CLI consolidation, where external compatibility can be considered explicitly.

## Gate

Run:

```bash
python tools/qualification/check_python_history_cleanup.py
```

The gate requires:

- 51 archived modules absent from the active namespace;
- 36 dedicated tests absent from active tests;
- byte-exact historical copies when the full historical tree is present;
- zero active imports from `src/`, `tests/`, or `tools/` to archived modules;
- the five obsolete console commands absent;
- exactly 81 active top-level Python modules under `src/xstar_tools/xstar/`;
- `historical/` pruned from normal distributions.
