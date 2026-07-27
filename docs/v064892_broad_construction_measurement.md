# 0.6.48.9.2 broad spectral construction measurement

## Purpose

0.6.48.9.2 is measurement-only. It follows the accepted 0.6.48.9.1 result, which localized controller fixed-state spectral time to `BROAD_APPLY_SECONDS` (~56.39 s in the qualification run, 99.69% of controller fixed spectral time).

The 9.2 question is narrower: how much of broad apply is spent inside the existing line-profile/opacity kernel, and which source data-type family owns that profile time?

## Instrumentation design

The implementation adds a separate `xstar_spectral_perf_v064892` diagnostic ABI. It does not change `xstar_spectral_stats_v1` or any science product ABI.

No new clock read is added per contribution or per line profile. The code reuses the `opacity_elapsed` value already returned by `xstar_opacity_apply_exact_grid_v1` / `xstar_opacity_apply_line_profile_v1`, and aggregates it by source `data_type`.

Measured values include:

- controller broad-apply time;
- exact-grid profile-kernel time;
- native/generated profile-kernel time;
- scalar/non-profile remainder (`broad apply - profile kernel`);
- contribution and profile counts by Type49/50/53/76/86/88/99/other;
- updated continuum-bin counts by family;
- exact-grid valid-point workload;
- all-call totals including the five projected/final spectral calls.

## Acceptance gates

- accepted controller topology remains 20/1/17/16 DSEC evaluations (54 total);
- broad apply must account for 95-101% of legacy controller fixed-spectral time;
- exact-grid + native profile timing must close to profile-kernel timing within 99-101%;
- family profile timing must close to profile-kernel timing within 99-101%;
- all established science gates remain unchanged against canonical FORTRAN and accepted accelerated-Python products.

## Routine reference policy

8.3.1 and canonical pure-Python 8.2 remain frozen provenance anchors but are no longer required runner inputs. Routine 9.2 qualification takes only canonical FORTRAN plus the accepted accelerated-Python reference. The timing-only series takes neither reference because it follows a successful qualification and does not regenerate Python.
