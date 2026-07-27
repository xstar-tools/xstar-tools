# xstar_tools 0.6.48.9.0 — measurement-only standalone C++ baseline

## Frozen inputs

0.6.48.9.0 starts from the accepted 0.6.48.8.3.1 science/runtime state. The following artifacts are frozen by SHA-256 and must not be regenerated during routine C++ performance work:

- `xstar_tools-0.6.48.8.3.1.tar.gz` — `614d7eedd574eb925edcc8807ee9a8e2b5c72754e0e6839575fa1ae0bb3921e8`
- `v064882_full_test.python_pure_reference.tar.gz` — `4f469a3be15587b7fcd38160f7a30997e3232b0af636d887d0ee529f59e577e0`
- `v064882_full_test.python_accel_reference.tar.gz` — `dd4eadba1471a400295b8bb1e238958941cc06afb0966b2cabc200c64a845227`
- `mg11_ne1e8.tar.gz` — `00473b048776df81c35ed5f913d9161490692a9de2286b236f7b4bc87ceedcc3`

FORTRAN remains the canonical scientific oracle. The accelerated 0.6.48.8.2 Python products are the routine reusable Python reference. Pure Python is retained as the canonical Python validation artifact and is not rerun unless Python behavior changes.

## Scope

0.6.48.9.0 changes measurement/reporting only. It does not intentionally change arithmetic, source ordering, controller topology, state ownership, transport, line/RRC selection, `binemis` semantics, or FITS values.

The non-standalone physics kernels and Python science files are hash-frozen to the 0.6.48.8.3.1 versions by `check_v064890_readiness.py`.

## Instrumentation

The standalone executable reports `V064890_PERF_*` metrics for:

- ATDB lowering;
- each of four DSEC controller-call wall times and evaluation counts;
- the native fixed-state sub-timers already maintained by the engine: traversal, rate, element/solve, continuum, spectral, and total;
- each accepted boundary projection;
- continuum transport, atomic luminosity accumulation, STPCUT, and STEP;
- post-loop zero-thickness final recomputation;
- ProductWritingState construction;
- retained writer-schema construction;
- writer-time `binemis`, including far boundary-event writes and ranked slots;
- science FITS writing, abundance FITS writing, `xout_step.log`, and total publication;
- retained product-array value and byte counts;
- static source-program counts for record types 49, 50, 53, 86, 88, and 99;
- top-level and controller-attributed coverage/residual time.

`binemis` time is a subcomponent of retained-schema time and is not double-counted in controller coverage.

Per-record-family wall timing is deliberately not implemented with a clock call around every record, because that would materially perturb the benchmark. Record-family counts are emitted directly; detailed family attribution should use `perf record -g` sampling or later coarse-grained source-family timers after the baseline identifies the dominant call stacks.

## Benchmark protocol

Use `run_v064890_performance_benchmark.sh`. It:

1. verifies all frozen input hashes;
2. checks 0.6.48.9.0 readiness;
3. builds standalone C++ once;
4. performs one complete warm-up production run;
5. performs three measured runs by default;
6. writes per-run and median timing tables;
7. requires the top-level instrumentation to explain at least 90% of measured wall time;
8. optionally captures `perf stat` with `V064890_USE_PERF_STAT=1`;
9. optionally captures a separate sampling run with `V064890_PERF_RECORD=1`.

Compilation is excluded from measured production time.

## Qualification protocol

Use `run_v064890_cpp_against_reference.sh` for the science gate. It verifies the frozen references, performs one standalone C++ production run, and reruns the existing energy-grid, detal4, spectrum, Type99/RRC, three-way product, and final-HMCTOT analyzers.

No Python calculation is launched by this runner.

## Initial performance hypotheses

The accepted 0.6.48.8.3.1 host run reported about 83.0 s in `CONTROLLER_SECONDS` and 84.2 s total. The source-faithful 0.6.48.8.2 `binemis` path reports 11,476,421 far boundary-event writes, so writer-time `binemis` remains the first hypothesis, but 0.6.48.9.0 is intended to measure rather than assume the cause.
