# 0.6.82.40.2.46.1 formal acceptance record

Date: 2026-09-23

## Decision

`xstar_tools-0.6.82.40.2.46.1` is **formally accepted as the C++ production base by explicit maintainer promotion**.

This acceptance does **not** rewrite the fresh low-`xi` qualification output. The authoritative runner result remains:

```text
SAVD_FIRST_MATERIALIZATION_PROMOTION_CLOSURE_0682402461_LOWXI_PERFORMANCE_GATE=REJECT
SAVD_FIRST_MATERIALIZATION_PROMOTION_CLOSURE_0682402461_LOWXI_RESULT=REJECT
```

The distinction is intentional: automated preregistered gate result = REJECT; maintainer promotion decision = ACCEPT.

## Fresh `.46.1` evidence retained verbatim

```text
same-host science                         EXACT
canonical science                         ACCEPT
fixed work                                ACCEPT
accepted modes                            ACCEPT
path                                      ACCEPT

historical materialization geomean        4.802184401 s
optimized materialization geomean         2.986023960 s
materialization ratio                     0.621805351629
materialization saving                    1.816160441 s
old <=0.50 diagnostic                     REJECT
ZONE_SAVD_DETAIL ratio                    0.788421612437
internal ratio                            0.990213030805
wall ratio                                0.990063615000
RSS ratio                                 1.000159175230
internal saving                           1.145390577 s
wall saving                               1.194948850 s
paired materialization wins               2/2
```

The corrected local `.46.1` materialization contract passes (`ratio <= 0.65`, local saving >= `1.5 s`), as do the zone-SAVD/detail, RSS, paired-win, and all science/work/path requirements. The fresh run narrowly misses the frozen whole-run ratio limits and the `1.5 s` absolute whole-run saving guards. Those misses are not hidden or relabeled.

For context, the byte-identical `.46` production implementation previously measured about `2.57 s` internal and `2.63 s` wall saving on the same host while preserving exact science/work/path and flat RSS. The `.46.1` source change is qualification/version metadata only, so the difference is treated as same-host run variability rather than a production-code change.

## Acceptance scope

- Accepted production base: `0.6.82.40.2.46.1`.
- C/C++ production/science implementation: byte-identical to `.46` apart from version metadata already part of the `.46.1` release.
- Historical `.46` and `.46.1` automated REJECT markers remain part of the audit trail.
- No rejected `.43` or `.44` production code is introduced.
- The separately planned C5 `xi=+1,+4` closure is waived for this explicit promotion decision; no claim is made that it was freshly rerun for `.46.1`.
- The next broad validation is the single expensive `multi_element_xi1_ne1e12` C++ run against the supplied existing FORTRAN XSTAR 2.59g oracle.

## Multi-element policy

The broad run must not rerun FORTRAN. The supplied FORTRAN reference is authoritative for this fixture and records:

```text
FORTRAN internal total     926.430935025 s
FORTRAN wall               940.90 s
FORTRAN peak RSS           2,513,224 kB
```

The C++ run is executed once with all accepted production modes frozen optimized, including `.34`, `.41/.42`, and `.46` SAVD behavior. Exact nine-FITS payload parity and exact STEP rows are the broad science gate. Runtime and RSS versus FORTRAN are reported separately.
