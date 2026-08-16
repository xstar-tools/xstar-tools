# 0.6.82.6 canonical terminal STEP endpoint restoration

## Scope

`0.6.82.6` is a publication/control-surface correction only.  It restores the
final XSTAR `pprint(9)` row that canonical XSTAR 2.59g emits after the radial
loop.  It does **not** change HMC rates, matrix construction, level populations,
thermal reduction, DSEC convergence, transport, or spectral products.

The newly exposed H+He+C `rlogxi=1.0` thermal discrepancy remains a separate,
open science investigation.  Historical C5 `rlogxi=1.5` common-row science is
kept unchanged.

## Canonical source ownership

The supplied XSTAR 2.59g `xstar.f90` performs, for each radial shell:

1. `xstarcalc`/`heatt` and `pprint(9)` for the current boundary;
2. radius/column update;
3. `stpcut` and `trnfrn`;
4. loop termination test.

After the loop exits, source `xstar.f90` explicitly executes:

```fortran
!       another printout to get the last step
        call pprint(9,...)
```

That post-loop row is therefore the physical post-transport endpoint.  It is
separate from the later zero-thickness `xstarcalc` followed by `pprint(22)`.

## 0.6.82.5 regression

The `0.6.82.5` native controller already retained the post-transport boundary
in `radial_zones`, but then set:

```text
physical_radial_boundaries_retained = finals.size()
```

where `finals` contains only the pre-transport DSEC boundaries.  STEP Option 17
therefore omitted the retained endpoint.  The historical C5 reruns showed that
all common rows, including `ntotit`, were exact to frozen C++44; only the final
row was missing in every density case.

## 0.6.82.6 correction

The native controller now counts `radial_event_count = finals.size() + 1` as the
physical Option-17 trajectory and retains all `radial_zones` for STEP.  Live
`--progress text` also emits the post-loop endpoint.  Because the post-loop
`pprint(9)` does not call DSEC again, the endpoint repeats the final DSEC
`ntotit`, matching the canonical C5 references.

The later zero-thickness final evaluation remains stored only in
`legacy_pprint.final_*` and does not become an Option-17 row.

## Historical C5 host qualification

Run:

```bash
python3 tools/qualification/run_c5_terminal_step_host_smoke_0_6_82_6.py \
  --data-dir ../xstar/data --replace
```

The gate runs the five H+He+C `rlogxi=1.5` C5 cases and requires the complete
displayed STEP trajectory to equal the frozen `0.6.48.12.3.44` references,
including the terminal endpoint.

## Separate low-xi science investigation

The H+He+C `rlogxi=1.0` comparison remains rejected in local thermal balance.
The `cfrac=1` control isolates the first-row material discrepancy primarily to
carbon cooling while H/He heating/cooling and carbon heating are already close.
This release intentionally does not alter that physics path; it keeps the
terminal-row correction independently testable before the next science change.
