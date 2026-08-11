# 0.6.82.8 LTE `rnisi` workspace lifetime

Canonical XSTAR 2.59g `levwkelement.f90` declares `real(8) rnisi(nd)` and the
source `PARAM` file sets `nd=20000`.  `levwk.f90` overwrites and normalizes only
`rnisi(1:nlev)` for active ions.  Inactive ions zero their `rnise` projection
but do not call `levwk` and therefore do not modify `rnisi`.

The post-ion-loop fully stripped recurrence nevertheless uses
`rnisi(nlev)/rnisi(nlev-1)`, where `nlev` belongs to the final source ion even
when that ion lies outside the active `mml:mmu` window.  With the canonical
large fixed local array, gfortran gives this workspace static storage lifetime:
it is initially zero-filled and retains untouched entries across calls.

`0.6.82.7` translated `rnisi` as an element-local vector and resized it to every
active ion.  The wide H+He+C qualification exposed the mismatch at `rlogxi=-5`:

```text
Z=6
active=1:4
last_active_nlev=26
max_active_nlev=26
final_source_nlev=33
rnisi_size=27
```

The source topology itself is valid.  The C++ vector had discarded source
workspace entries 27..20000 and rejected before the first physical STEP row.

`0.6.82.8` models the source lifetime explicitly with one 20,000-entry,
1-based workspace owned by the reusable fixed-state context.  Active `levwk`
translations overwrite only `1:nlev`; inactive ions leave it untouched; the
workspace persists across elements and fixed-state/DSEC evaluations.  A
context reset zeroes it, corresponding to a fresh canonical process/model
state.

No Type-63, DSEC-controller, matrix-solver, terminal-STEP, ATDB-lowering, or
public ABI change is included in this release.

Host qualification order:

1. rerun only H+He+C `density=1e12`, `cfrac=1`, `column=1e20`, `xdef`,
   `rlogxi=-5`;
2. if it completes, compare against the preserved canonical FORTRAN `-5`
   products;
3. resume C++ at `-4..+5` using the already completed canonical FORTRAN grid;
4. stop at the first material `<1%` or structural-trajectory failure.
