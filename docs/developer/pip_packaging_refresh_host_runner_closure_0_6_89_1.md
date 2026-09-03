# 0.6.89.1 — PIP_PACKAGING_REFRESH_HOST_RUNNER_CLOSURE

`0.6.89.1` closes the false native-artifact rejection in the `0.6.89` pip packaging host runner.

## Predecessor result

`0.6.89` remains a historical Linux host REJECT at:

```text
PIP_PACKAGING_REFRESH_0689_HOST_NATIVE_ARTIFACTS=REJECT
```

The native `cp313-cp313-linux_x86_64` wheel itself built successfully and inspection of the uploaded host artifact confirmed every required native payload member was present. The failure was solely in the qualification runner's ZIP-member prefix test.

## Root cause

The old runner tested for `"/xstar_tools/xstar/cpp/"` inside wheel member names. Wheel member names are POSIX paths that begin directly with `xstar_tools/xstar/cpp/`, so the leading-slash condition matched nothing.

## Fix

The new host runner:

- treats wheel member names as POSIX archive paths with `PurePosixPath`;
- selects members with `name.startswith("xstar_tools/xstar/cpp/")`;
- checks required basenames against the actual wheel payload;
- cross-checks the same required artifacts against `native_build.json`;
- preserves all `0.6.89` packaging implementation, MPI exclusion, and external-`atdb.fits` policy.

No scientific arithmetic, traversal, publication, ABI, native runtime discovery, or native build behavior is changed.

## Host command

```bash
python3 tools/qualification/run_pip_packaging_refresh_host_runner_closure_host_0_6_89_1.py \
  --package "$PWD" \
  --output-root "$PWD/run_pip_packaging_refresh_host_runner_closure_06891_host"
```

A formal `0.6.89.1` acceptance requires that command to finish with:

```text
PIP_PACKAGING_REFRESH_HOST_RUNNER_CLOSURE_06891_HOST_RESULT=ACCEPT
```
