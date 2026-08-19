# `0.6.82.30` — permanent all-Table-1 conformance gate

## Purpose

This milestone is the release-candidate gate for the public XSTAR parameter
contract.  Canonical science remains FORTRAN XSTAR 2.59g.  `0.6.82.30` is
science-frozen relative to the exact host-closed `0.6.82.29.3.10` archive: the
137 tracked numerical/science production files must be byte-identical.

The gate covers all **59 stock public parameters** in source order.  Of these,
57 appear in the Manual Table 1; `naabund` and `lstep` are public stock
`xstar.par`/`rread1` parameters that the displayed Table 1 omits.

For every parameter the permanent matrix records:

- stock default and an explicit away-from-default probe;
- FORTRAN, C++, and Python consumers;
- supplied/runtime public value;
- expected effect surface;
- classification as active science/radial/output control or intentionally
  metadata/interface-only;
- source milestone that established its semantics;
- full-science or parameter-surface coverage used by the `.30` release gate.

No supplied public parameter may be silently ignored or replaced by a fixed
fallback.  An unsupported/out-of-contract value must fail explicitly.

## Required release-candidate axes

The `.30` host matrix includes:

```text
cfrac       0, 0.4, 1
emult       0.1, 0.25, 0.5, 1.0
niter       0, -99, 1, 99
lcpres      0, 1
radexp      analytic + density.dat
npass       1, 3, 5
spectrum    pow, bbody, bremss, file
spectun     0, 1, 2
ncn2        999, 9999, 19999
controls    lwrite, lprint, lstep, modelname, loopcontrol, mode
elements    isolated H+He+C, H+He+O, H+He+Ca, H+He+Fe
```

The material numerical criterion remains the established exclusive `<1%`
FORTRAN-concordance surface unless a narrower predecessor gate applies.  STEP
printed physical coordinates retain the `0.011` absolute printed-value gate.
Metadata/interface-only and output-only cases additionally require science
invariance against the corresponding backend baseline.

## Evidence layering

`0.6.82.30` deliberately reuses source-specific qualification logic that was
already host-developed during `.22-.29` rather than replacing it with a less
specific generic comparator.  The core replay layer covers the difficult
contracts (`cfrac/emult`, `niter`, `lcpres`, `radexp`, `npass`, spectrum).  A
new representative layer covers remaining scalar controls, continuum
resolution, metadata/output invariance, and C/O/Ca/Fe models. It also carries
30 individual abundance-multiplier science probes (H through Zn), each run
against FORTRAN in both C++ and pure Python, so abundance parameters are not
merely parser-surface checked.  A parameter
surface probe exercises all 59 public parameters away from default through
FORTRAN XPI, the native frontend envelope, and Python normalization.

The already-host-closed `.29.3.10` verbose evidence is an inherited immutable
boundary because `.30` changes no numerical/science production file.  Fresh
representative output/control cases remain in the `.30` matrix as an additional
regression layer.

## Source/XPI exceptions retained explicitly

The permanent matrix does not hide known source/XPI differences:

- source `spectun=2` is reached for FORTRAN through a temporary local `xstar.par`
  range shadow; the executable is unmodified;
- the source `radexp<-99` `density.dat` branch is reached the same way;
- the gap `-99 <= radexp < -3`, `spectun>2`, `ncn2<999`, `cfrac>1`, unknown
  parameters, and stock-2.59g public `lwrite=-1` are explicit hard-error
  probes rather than silent fallbacks.

## Release rule

Passing `.30` closes the parameter-contract release-candidate gate.  It does
**not** by itself advance the accepted science revision.  The science revision
may move only after this matrix **and** the broader reopened element/density
campaign pass.  ABI identifiers remain frozen unless the public binary
interface actually changes.
