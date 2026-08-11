# 0.6.82.1 `xstar-cpp` parameter-envelope / file-silent closure

## Problem

The public `xstar-cpp` frontend historically wrote its generated native JSON
parameter envelope to:

```text
<output>/.xstar-cpp-parameters.json
```

before invoking the sibling `xstar_cpp run-production` executable.  Native
production with `artifact_profile=none` intentionally verifies that the output
directory contains only XSTAR science products at the publication boundary.
Consequently a scientifically successful run could be rejected after writing
its products because the frontend's own orchestration envelope was already in
the output directory:

```text
file-silent production created a non-product artifact: .xstar-cpp-parameters.json
```

This is a frontend/productization defect, not an XSTAR science failure.

## 0.6.82.1 contract

When `--parameters-out` is **not** supplied, `xstar-cpp` writes the generated
parameter envelope to the system temporary directory, passes that path to
`xstar_cpp run-production`, and removes the temporary envelope after the native
run.  The science output directory is therefore clean when the native
`artifact_profile=none` validator runs.

When `--parameters-out FILE` **is** supplied, that path remains an explicit
opt-in retained orchestration artifact and is not deleted.

The normal frontend provenance file `xstar_execution_provenance.json` is written
only after native production returns, so it cannot invalidate the native
file-silent publication boundary.

## Regression

`tests/test_xstar_cpp_first_class_0_6_69.py` contains a 0.6.82.1 regression in
which the sibling native stub fails if the output directory contains any file
before it starts.  The test requires:

- no default `.xstar-cpp-parameters.json` in the output directory;
- the temporary parameter envelope to be outside the output directory;
- successful native execution;
- removal of the temporary envelope after execution;
- retained `--parameters-out` behavior in the existing structured-extension
  test.

No atomic, matrix, rate, emissivity, opacity, transport, FITS science, or ABI
semantics are changed by this repair.
