# 0.6.82.17 standalone publication-memory closure

## Scope

`0.6.82.17` is a production memory/ownership release. It does not change the
scientific kernels, DSEC arithmetic, accepted radial-boundary states, source
constants, science revision, or public ABIs.

The host symptom in exact `0.6.82.16` was return code 137 after all 77 physical
H+He+C `rlogxi=-3` STEP rows had been computed, but before `final print`,
`xout_step.log`, and FITS publication. This localized the failure to the
end-of-run retained-state/publication transition rather than to the radial
science calculation.

## Root cause

Generic standalone production retained every controller/DSEC trial, retained
accepted full boundary snapshots in multiple containers, copied them again into
`WholeRunAccumulatedState`, and then deep-copied that state into
`ProductWritingState`. Low-ionization trajectories carry large exact source
workspaces per accepted boundary, so peak memory grew sharply at publication.

## Repair

- Generic production does not retain non-publication DSEC trial history after
  the controller decision.
- Explicit reference-trajectory and qualification-diagnostic modes preserve
  their historical full retention.
- Accepted boundaries are transferred into canonical `radial_zones`; generic
  source snapshots are released immediately after transfer.
- Generic production does not duplicate accepted boundaries into
  `accepted_controller_states`.
- A move overload transfers `WholeRunAccumulatedState` into
  `ProductWritingState` without a second deep copy.
- One compatibility fixed evaluation is retained for incident-grid consumers;
  publication lookup by sequence falls back to accepted radial zones.

## Qualification policy

For the reopened broad all-element campaign:

- material STEP/FITS numerical quantities: `<1%`;
- already-percent STEP fields such as `h-c(%)`: `<1` absolute percentage point;
- `ntotit`: convergence diagnostic only, not an acceptance veto.

Do not force `ntotit` equality with output overrides or controller changes.

## 0.6.82.16 rlogxi=-3 evidence

Exact `0.6.82.16` produced 77/77 physical rows before SIGKILL. At printed STEP
precision all physical fields except `h-c(%)` were exact. Maximum absolute
`h-c` difference was 0.10 percentage point. Three `ntotit` values differed,
with maximum absolute delta 6. Under the current policy the STEP trajectory is
accepted; FITS/material qualification remains pending because the process died
before publication.

## Frozen predecessor science

- 0.6.82.13 all-element atomic-data-type generalization;
- 0.6.82.14 canonical high-tau `pescl` pi;
- 0.6.82.15 ATDB source-parent Type-50 mass;
- 0.6.82.16 canonical `ispec4` normalization.

Science revision remains `0.6.48.12.3.45.3.3.8`; C API ABI remains `60487`;
production-zone ABI remains `6048110`.
