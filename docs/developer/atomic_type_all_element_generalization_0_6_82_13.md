# xstar_tools 0.6.82.13 - all-element atomic-data-type generalization

## Scope and source rule

`0.6.82.13` is an architectural/source-concordance successor to exact `0.6.82.12`. Canonical FORTRAN XSTAR 2.59g (`ucalc.f90`, `calc_hmc_ion.f90`, `calc_hmc_element.f90`, `levwk*.f90`, and the ATDB pointer/topology routines) is the implementation oracle. The XSTAR manual and atomic-data papers are used to identify the intended data-family and ion-sequence applicability, not to override executable source semantics.

The release rule is:

> Preserve restrictions that are defined by FORTRAN/ATDB record or ion-sequence semantics; eliminate target-element H/He/C/Mg restrictions introduced by the port.

This does **not** mean every data type is applied to every ion. H-like families remain H-like at every applicable Z, He-like families remain He-like, and Fe/Fe-Ni/source-record families retain their source-defined applicability.

## Catalog closure

The canonical 1-102 catalog is accounted for as 78 physical labels and 24 source no-op/metadata labels. C++ `kActiveTypes` contains the same 78 physical labels. Python `ucalc.py` retains the complete source catalog, and `native_fixed_program.py` now accepts the same 78/78 physical labels rather than the historical H/He/Mg-era subset.

The C++ executable partition is explicit and closed:

- direct native kernels: the established high-use/source-specialized opcode set;
- aliases: Type 91 -> Type 50 and Type 52 -> Type 59, matching source branch ownership;
- generic source UCalc opcode 200: all remaining 44 physical labels, with a concrete C++ evaluator case for every one.

The qualification gate verifies the partition mechanically so a future catalog edit cannot silently create an accepted-but-unevaluated physical label.

## Python all-element lowering

The compact/native Python lowerer is no longer limited to the early H/He/Mg subset. It now provides:

- the full 78-label physical catalog;
- Z=1-30 atomic masses;
- the canonical `xdef` abundance base for Z=1-30;
- direct/alias/generic opcode routing matching C++;
- source endpoint energy/statistical-weight ownership for generic records;
- Z=1-30 persistent `leveltemp` candidate context for Types 49, 53, and 99;
- global source-ion identity for Type 70.

Legacy Mg-only optional Python matrix/rate/emissivity accelerators remain available only as diagnostic/performance archaeology. They are retired from science-product ownership, so they cannot select Mg-specific physics over the generic source evaluator.

## C++ source-semantic generalization

### Type 50

Mutable `leveltemp` endpoint ownership and live line `tau/cfrac` escape state are generic for all applicable elements. The old Mg low-ion endpoint selection is removed from normal ATDB lowering.

### Types 49, 51, and 53

Type 49 retains the canonical all-element bound-free commit. Type 51's canonical Burgess-Tully evaluator is authoritative for every C++ backend rather than being selected by a qualification flag. Type 53 normal production uses the lowered-record/live-continuum source path independent of H/He/C/Mg identity; the historical He row-46 oracle cannot own native production.

### Type 57

Canonical source energy/statistical-weight semantics are unconditional for every applicable record.

### Types 60 and 62

Canonical operation order and guards are unconditional wherever the ATDB supplies these H-like records. The H-like sequence restriction is retained; there is no target-element restriction.

### Type 68

Canonical constants/order are unconditional wherever the ATDB supplies this He-like family. The He-like sequence restriction is retained.

### Type 70

A separate all-element source-identity defect was found while completing the draft. Canonical FORTRAN caps density only when global ATDB `jkion == 1` (the hydrogen source ion). The port had tested compact per-element `record.ion_index == 1`, which incorrectly applied the cap to the first ion of every element. The lowerer now serializes the global source-ion identity and the evaluator consumes that identity; compatibility fallback is restricted to the physical hydrogen first-ion case.

### Type 99

Persistent `leveltemp` energy **and statistical-weight** ownership is expanded from the old Mg/12-stage representation to Z=1-30 / 30 stages, with old-layout read compatibility. Source destination-identity correction is no longer Mg-gated. Direct Type-99 opacity publication is source-zero for every element, because canonical `ucalc` Type 99 computes scalar `calt99 -> phint53hunt` channels without assigning direct `opakab`; the former H/He-only source-zero publication gate is removed.

## Publication/default-data cleanup

The C++ science-FITS fallback `xdef` abundance table is now Z=1-30 instead of H/He/Mg-only. The optional C++ element engine defaults to Z=1-30 when explicitly enabled, while an explicit environment subset can still narrow the requested elements.

## Deliberately separate work

The thermal source-order/ledger reduction remains a separate milestone. Existing H/He/Mg-specific thermal ownership branches are not presented as atomic-data-type closure here. Combining rate-family generalization and thermal-ledger changes in one release would make FORTRAN discrepancies harder to localize.

The historical science revision remains `0.6.48.12.3.45.3.3.8`; C API ABI `60487`, production-zone ABI `6048110`, and fixed-state ABI `60488` remain frozen because this release does not change those public binary interfaces.

## Qualification status

The static/source gate requires:

- 102/102 catalog accounting;
- C++ 78/78 physical coverage;
- C++ generic opcode-200 44/44 evaluator coverage;
- Python lowerer 78/78 physical coverage and Z=1-30 default tables;
- source-semantic checks for Types 49/50/51/53/57/60/62/68/70/99;
- predecessor repairs from 0.6.82.6 through 0.6.82.12 to remain accepted.

Host science remains open. In particular, this release does **not** claim that H+He+C `rlogxi=-3`, `-2`, or the two remaining `ntotit` differences at `-5` are fixed. Those must be rerun against canonical FORTRAN before any broad science acceptance claim. After `cfrac=1` low-xi closure, the campaign must include new `cfrac=0.4` and `cfrac=0` FORTRAN/C++ comparisons and then H+He+X element-by-element qualification through the supported element set.
