# xstar_tools 0.6.82.30.6 final qualification models

`0.6.82.30.6` replaces the broad 38-model `.30.5` final-axis replay with a deliberately small eight-model FORTRAN-to-C++ release-candidate gate.

The parameter-family campaigns completed in `0.6.82.20` through `0.6.82.29` are treated as accepted predecessor qualification and are not replayed here. The `ncn2` axis is deferred to a separate focused follow-up; all eight models in this gate use `ncn2=9999`.

The eight models are:

1. H+He+C standard/reference: `density=1e8`, `rlogxi=1.5`, `cfrac=1`.
2. H+He+C difficult low-xi: `density=1e12`, `rlogxi=-3`, `cfrac=0.4`.
3. H+He+O: `density=1e10`, `rlogxi=1.5`, `cfrac=1`.
4. H+He+Ca: `density=1e8`, `rlogxi=2.5`, `cfrac=1`.
5. H+He+Fe: `density=1e8`, `rlogxi=2.5`, `cfrac=1`.
6. Broad multi-element mixture: H/He/C/N/O/Ne/Mg/Al/Si/S/Ar/Ca/Cr/Fe/Ni, `density=1e12`, `rlogxi=1`, `cfrac=0.4`.
7. H+He+C low-density endpoint: `density=1`, `rlogxi=1.5`, `cfrac=1`.
8. H+He+C high-density endpoint: `density=1e12`, `rlogxi=1.5`, `cfrac=1`.

Each case runs canonical FORTRAN XSTAR 2.59g and `xstar-cpp`, then compares spectrum, STEP structure/science, ionic columns, and heating/cooling through the established material `<1%` and printed-coordinate policies. FORTRAN outputs are retained for the later Python-to-FORTRAN phase.

A complete run therefore performs **8 FORTRAN + 8 C++ = 16 model executions**.
