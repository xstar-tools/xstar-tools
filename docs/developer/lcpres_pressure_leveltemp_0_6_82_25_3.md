# xstar_tools 0.6.82.25.3 — pure-Python persistent `leveltemp` ownership

## Host trigger

`0.6.82.25.2` is **not** the final pressure milestone. C++ accepts all four pressure cases and pure Python accepts `cp_xim2`, `cp_xi0`, and `cp_xi2`, but pure-Python `cd_xi1` rejects. The observed STEP iteration sequence is `26/9/9` versus canonical FORTRAN `27/1/1`; final temperature also drifts and Option-1 carbon lines reach about 3.81% relative error.

## Canonical source ownership

In `xstar.f90`, one `TYPE(level_temp) :: leveltemp` object is passed to every radial `xstarcalc` call and to `heatt`. Inside `xstarcalc.f90`, that same object is passed to `dsec`, the unconditional final `calc_hmc_all`, `calc_emisab_all`, and `calc_emis_all`. `dsec.f90` repeatedly calls `calc_hmc_all` with the same object. `calc_hmc_all.f90` passes it into `calc_hmc_element`; `calc_hmc_element.f90` passes it into `calc_ion_rates`, `levwkelement`, and `calc_hmc_ion`. It therefore participates in live rate/matrix science and is not merely diagnostic output.

The native C++ implementation already documents and retains this source-wide mutable workspace (`source_leveltemp_energy_workspace_v06481231`).

## Python defect

The public Python runtime created each DSEC state with `leveltemp_workspace=None` and `reset_leveltemp_each_calc_hmc_all=True`. It also constructed `calc_emisab_all` and `calc_emis_all` from the same pre-emission snapshot rather than passing the updated workspace sequentially. The `heatt` result was not committed back to the DSEC runtime for the next radial zone.

## Correction

`.25.3` carries one mutable source-equivalent workspace through:

`DSEC calc_hmc_all trials -> final calc_hmc_all -> calc_emisab_all -> calc_emis_all -> heatt -> next zone`

No convergence tolerance, DSEC branch, rate formula, matrix ordering, pressure equation, C++ science, or ABI changes.

## Host qualification

Run only pure-Python `cd_xi1` first. Required target is FORTRAN-like `ntotit=27/1/1` and material `<1%` comparison. Only after that passes should the remaining three pure-Python pressure cases be rerun because this correction changes Python source-state lifetime globally. C++ does not need rerunning.
