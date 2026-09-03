# 0.6.89.1.1 — WINDOWS_PIP_PYTHON_CONFIG_DISCOVERY_CLOSURE

`0.6.89.1.1` closes the Windows-only native pip-wheel prerequisite-discovery failure exposed by the four-host `0.6.89.1` GitHub Actions run.

## Predecessor evidence

`0.6.89.1` completed with:

```text
Linux x86_64        ACCEPT
macOS arm64         ACCEPT
macOS Intel x86_64  ACCEPT
Windows UCRT64      REJECT
```

The Windows Python-only wheel accepted. The native-required wheel failed before native compilation at:

```text
PIP_PACKAGING_REFRESH_HOST_RUNNER_CLOSURE_06891_HOST_WHEEL_BUILD_REQUIRED=REJECT
```

The build hook diagnostic was:

```text
RuntimeError: native xstar-tools wheel build requires python_config
```

## Root cause

MSYS2 UCRT64 installs `python3-config` and `python-config` as extensionless shell scripts beside the active Python interpreter. The build hook used native Windows `shutil.which()` to discover them. Windows executable lookup can miss extensionless scripts even though GNU Make's MSYS2 shell can execute the same files.

This is a packaging prerequisite-discovery defect, not a C++ compiler, linker, runtime, science, or ABI failure.

## Closure

The normal discovery order is retained:

1. explicit `PYTHON_CONFIG` environment override;
2. normal `shutil.which("python3-config")`;
3. normal `shutil.which("python-config")`;
4. same-interpreter sibling `python3-config`;
5. same-interpreter sibling `python-config`.

The sibling fallback is resolved from `sys.executable` and returned with forward slashes so the retained MSYS2/GNU Make shell can execute it. The Makefile interface remains unchanged: packaging still supplies the discovered value through `PYTHON_CONFIG`.

## Frozen boundaries

This closure does not change:

- science revision `0.6.48.12.3.45.3.3.8`;
- C API ABI `60487`;
- production-zone ABI `6048110`;
- native wheel artifact set;
- ordinary-wheel MPI exclusion;
- external `atdb.fits` policy;
- accepted atomic-data discovery order.

## Host qualification

Run on the Windows MSYS2 UCRT64 host:

```bash
python tools/qualification/run_windows_pip_python_config_discovery_closure_host_0_6_89_1_1.py \
  --package "$PWD" \
  --output-root "$PWD/run_windows_pip_python_config_discovery_closure_068911_host"
```

Formal Windows closure requires:

```text
WINDOWS_PIP_PYTHON_CONFIG_DISCOVERY_CLOSURE_068911_HOST_PYTHON_CONFIG_DISCOVERY=ACCEPT
WINDOWS_PIP_PYTHON_CONFIG_DISCOVERY_CLOSURE_068911_HOST_WINDOWS_EXTENSIONLESS_CONFIG_FILE=ACCEPT
WINDOWS_PIP_PYTHON_CONFIG_DISCOVERY_CLOSURE_068911_HOST_WHEEL_BUILD_REQUIRED=ACCEPT
WINDOWS_PIP_PYTHON_CONFIG_DISCOVERY_CLOSURE_068911_HOST_NATIVE_ARTIFACTS=ACCEPT
WINDOWS_PIP_PYTHON_CONFIG_DISCOVERY_CLOSURE_068911_HOST_NATIVE_METADATA_ARTIFACTS=ACCEPT
WINDOWS_PIP_PYTHON_CONFIG_DISCOVERY_CLOSURE_068911_HOST_RESULT=ACCEPT
```
