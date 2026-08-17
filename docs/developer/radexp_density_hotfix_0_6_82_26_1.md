# 0.6.82.26.1 radexp / density.dat host hotfix

`0.6.82.26` correctly evolved the live native analytic/table density, but host qualification exposed publication and harness defects after that evolution.

The `.26.1` correction is intentionally narrow:

- preserve `RadialZoneState::density_cm3`, live radial xi, and retained cumulative `column_density_cm2` for `lcpres=0` when `radexp != 0`;
- keep legacy input-density reconstruction only for literal `lcpres=0, radexp=0`;
- make live pprint(9)-style rows use the source initial radius and retained cumulative xcol for variable density;
- allow the canonical source input `density.dat` in the file-silent artifact check when `radexp < -99`;
- keep host input files in separate input directories;
- exclude XSTAR's all-zero terminal ABUNDANCES row from the analytic-law self-check;
- preserve the source-stale terminal ionization scalar in both live and persisted STEP publication after the final variable-density geometry update.

No analytic/table controller arithmetic, atomic rates, DSEC, thermal/matrix logic, pressure logic, science revision, or ABI is changed.
