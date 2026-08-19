# 0.6.82.30.6.2 Python-only continuation qualification

This revision adds two independent pure-Python qualification runners. It does not change production science. Both runners compare new pure-Python outputs against retained canonical FORTRAN XSTAR 2.59g outputs and never execute FORTRAN or C++.

## Test 1 — 26 parameter-axis models

- niter: 4
- lcpres: 4
- radexp: 6
- npass: 1, 3, 5 (3)
- spectrum/spectun: 6
- ncn2: 3

`npass=1` is intentionally included even though the current C++ final gate rejects its SAVD/raw-RRC publication ownership. The purpose is to determine whether pure-Python exhibits the same single-pass defect.

References:

- `.30.5` `run_final_qualification_axes_0682305` for niter/lcpres/radexp/npass
- accepted `.30.6.1` `run_remaining_qualification_06823061` for spectrum/ncn2

## Test 2 — 6 representative models

- c5_reference_ne1e8
- c5_lowxi_cf04_ne1e12
- o7_reference_ne1e10
- ca19_reference_ne1e8
- c5_low_density_ne1
- c5_high_density_ne1e12

References:

- `.30.6` `run_final_qualification_models_0682306` for the first four
- accepted `.30.6.1` `run_remaining_qualification_06823061` for the two density endpoints

Fe and multi-element are deliberately excluded pending C++ repair/qualification. Output-control Python continuation is also deferred.
