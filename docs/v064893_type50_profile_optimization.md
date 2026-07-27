# 0.6.48.9.3 Type50 profile-kernel optimization

## Baseline

The accepted 0.6.48.9.2 three-run series measured:

- median total runtime: 82.976367 s
- median controller runtime: 81.728516 s
- median controller broad apply: 56.448910 s
- median Type50/profile-kernel runtime: 56.417535 s
- controller Type50 profiles: 152,782
- controller updated bins: 749,226,884

Type50 accounts for 100% of measured profile-family time.

## Optimization

`opacity_kernels.cpp` retains the accepted translated linopac/voigte algorithm and source-order accumulation, but removes two implementation costs:

1. On `FLT_EVAL_METHOD==0` platforms, ordinary scalar binary64 operations are used instead of volatile store/load barriers around every translated arithmetic operation. The opacity translation remains compiled with `-ffp-contract=off` and rejects `-ffast-math`. On targets with excess evaluation precision, the historical volatile barriers remain active automatically.
2. The two 20,000-double temporary Type50 planes are retained in per-thread scratch storage rather than allocated and zero-filled for every profile. Every slot in the used contiguous source-grid interval is overwritten before it is read.

The optimization does not change profile formulas, temporary-grid traversal, rebin order, continuum-bin accumulation order, Type50 source-real constants, or the 0.6.48.9.2 diagnostics ABI.

## Qualification

`check_profile_kernel_equivalence.py` compiles the same 9.3 source twice: once with the fast binary64 path and once with `XSTAR_V064893_LEGACY_FP_BARRIERS=1`. Randomized Type50 cases must be bit-exact before the normal FORTRAN/Python/C++ product qualification starts.

The host qualification must still close energy-grid parity, detal4, spectrum, Type99/RRC, structural product parity, final thermal/HMCTOT, trajectory, and publication gates.

## Performance acceptance

The three-run analyzer requires the frozen Type50 workload (152,782 profiles and 749,226,884 updated bins) and requires both median Type50 profile time and median total time to improve over the accepted 9.2 baseline.
