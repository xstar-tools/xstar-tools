# `0.6.82.26.2`: radexp/density.dat publication hotfix

`0.6.82.26.1` host qualification exposed four residual C++ failures. Source inspection and the host products separate them into three ownership defects.

First, `pprint.f90` option 9 recomputes `zeta=log10(xlum/(xpx*(r*1.e-19)^2))` on every call, including the post-loop terminal row. The `.26.1` terminal stale-xi exception was therefore incorrect and is removed.

Second, the final physical abundance row is emitted after the source has advanced radius and, for variable-density runs, density. Its ion populations and thermal quantities still belong to the last evaluated shell, but the published radius/density/xi are post-geometry owners. `.26.2` uses the terminal geometry density only for `lcpres=0, radexp!=0`, leaving constant-density and pressure behavior unchanged.

Third, hidden `density.dat` mode has two different shell widths in one iteration. HEATT uses the STEP-selected `delr`; only afterward does the source read `density.dat`, replace `delr` with `rnew-r`, and use that geometry width for `xcol`, STPCUT and TRNFRN. `.26.1` reconstructed public line luminosity from radial-zone/table-radius differences, which cannot represent HEATT widths and drops the final HEATT shell when EOF retains the same radius. The native controller already retains the literal cumulative `elum`; `.26.2` publishes that retained owner for the tabulated branch.

The obsolete terminal `std::optional<double>` override is removed, also eliminating the GCC `-Wmaybe-uninitialized` warning. Science revision and public ABIs remain frozen.
