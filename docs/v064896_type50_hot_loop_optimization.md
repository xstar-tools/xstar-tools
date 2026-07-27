# 0.6.48.9.6 standalone Type50 hot-loop optimization

## Scope

0.6.48.9.6 starts directly from 0.6.48.9.5.1. It intentionally changes only the standalone-native Type50 full-profile opacity kernel in `src/xstar_tools/xstar/cpp/opacity_kernels.cpp` plus release/qualification plumbing. The accepted 9.5 Type49/53 prepared engine, the 9.4.2 exact accepted-boundary recomputation, Type99/RRC closure, thermal/HMCTOT behavior, product writers, and Python source-port runtime are frozen.

The optimization is selected only when the standalone controller has set `XSTAR_NATIVE_SOURCE_SEQUENCE`. Python source-port execution (including modular C++ backends) therefore continues through the 0.6.48.9.5.1 Type50 implementation.

## Exact transformations

1. **Remove full-profile `rccemis += 0.0` stores.** Literal `linopac.f90` modifies `rccemis` only in the single-bin `lfast > 2` branch. The full-profile branch only updates `opakc`.
2. **Direct source-order `opakc` update.** Production `opakc` is already a finite nonnegative continuum workspace. The optimized path performs the literal `opakc(ml1m)=opakc(ml1m)+optp2` order instead of the 9.5.1 defensive finite/positive reload.
3. **Fuse temporary-profile construction with rebin consumption.** In literal `linopac.f90`, `ml1min` and `ml1max` are not updated until after the temporary-grid construction loop. Consequently the `ldon` early-stop predicate cannot become true during that loop. The only temporary profile values that can affect public output are the monotonically ordered values later consumed by the rebin loop. 9.6 computes those same values at their point of use and preserves the trapezoid and public-bin accumulation order.
4. **Elide exact integer conversion round trips.** `ncut <= 2000` and temporary-grid offsets are within `[-9999,10000]`. Every such integer is exactly representable in IEEE binary32, so `double(float(i)) == double(i)` exactly. 9.6 uses direct integer-to-double conversion in the optimized path.
5. **Small-damping Voigt specialization.** The `0 < a <= 0.2` branch is copied from the accepted `voigte` implementation with only invariant tests removed. Arithmetic association is unchanged.

The source `linopac.f90` early-stop behavior is not activated or reinterpreted.

## A/B contract

Set:

```bash
XSTAR_V064896_FORCE_LEGACY_TYPE50=1
```

to force the exact 0.6.48.9.5.1 Type50 full-profile implementation in the same standalone executable. The 9.6 host qualifier requires:

- randomized kernel bit identity;
- untouched full-profile `rccemis`;
- unchanged Type50 profile/update workload;
- all nine FITS HDU data payloads bit-exact between optimized and forced-legacy runs;
- normalized scientific `xout_step.log` identity;
- all nine FITS payloads bit-exact against the supplied 0.6.48.9.5.1 C++ reference;
- public FORTRAN/Python/C++ science closure against both supplied 9.5.1 Python references.

## Reference archives

The 9.6 reference verifier freezes the user-supplied archives by SHA-256:

```text
FORTRAN mg11_ne1e8
00473b048776df81c35ed5f913d9161490692a9de2286b236f7b4bc87ceedcc3

0.6.48.9.5.1 pure Python
3dd798eb9627dd59d8a38633266398baaa99f721fa5d325bac88cd261f71aaf9

0.6.48.9.5.1 accelerated Python
92fd73867e3fe4937415568c81a86197f2fddb1060899f9356cdfd7e1606ae63

0.6.48.9.5.1 standalone C++
182347f179ac51f9b1c1db6ca65b0f5080f93d270158204c5caa88f83102b573
```

## Local qualification

Before host qualification, the release must pass `tools/qualification/v064896/check_readiness.py` and `check_type50_kernel_equivalence.py`. The development build passed 600 randomized Type50 cases bit-for-bit and measured a representative micro-kernel speedup of approximately 1.44x. This performance number is diagnostic; host Mg XI controller timing is authoritative.

## Host acceptance target

Expected final markers:

```text
V064896_TYPE50_NOOP_WRITES_REMOVED=ACCEPT
V064896_TYPE50_DIRECT_OPAKC_UPDATE=ACCEPT
V064896_TYPE50_PROFILE_REBIN_OPTIMIZED=ACCEPT
V064896_TYPE50_KERNEL_BIT_EXACT=ACCEPT
V064896_TYPE50_WORKLOAD_FROZEN=ACCEPT
V064896_BOUND_FREE_095_FROZEN=ACCEPT
V064896_BOUNDARY_CORRECTNESS_0942=FROZEN
V064896_PUBLIC_SCIENCE_CLOSURE=ACCEPT
V064896_RESULT=ACCEPT_TYPE50_HOT_LOOP_OPTIMIZATION
V064896_FINAL_RETURN_CODE=0
```

The intended runtime target remains approximately 21.5–23 s for the full standalone Mg XI run. Promotion depends on host qualification, not the local microbenchmark.
