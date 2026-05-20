"""Shared diagnostic state correlating XSTAR ``dsec`` and ``calc_hmc_all`` calls.

The generated Fortran module is diagnostic only.  It records which global
``calc_hmc_all`` invocation belongs to which ``dsec`` invocation/evaluation and
classifies the first call after ``dsec`` as the source-order post-``dsec`` call
made by ``xstarcalc.f90``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict


def call_correlation_probe_helper() -> str:
    return r'''! xstar-atomic v0.4.48 dsec/calc_hmc_all call-correlation state.
!
! Diagnostic only.  No scientific state is modified.
module xap_call_correlation_state
  implicit none
  integer, save :: xap_corr_dsec_call_id = 0
  integer, save :: xap_corr_dsec_evaluation = 0
  integer, save :: xap_corr_inside_dsec = 0
  integer, save :: xap_corr_post_dsec_pending = 0
  integer, save :: xap_corr_last_calc_hmc_call_id = 0
  character(len=32), save :: xap_corr_last_phase = 'outside_dsec'
contains
  subroutine xap_corr_begin_dsec(dsec_call_id)
    integer, intent(in) :: dsec_call_id
    xap_corr_dsec_call_id = dsec_call_id
    xap_corr_dsec_evaluation = 0
    xap_corr_inside_dsec = 0
    xap_corr_post_dsec_pending = 0
    xap_corr_last_phase = 'dsec_begin'
  end subroutine xap_corr_begin_dsec

  subroutine xap_corr_before_dsec_evaluation(evaluation_index)
    integer, intent(in) :: evaluation_index
    xap_corr_dsec_evaluation = evaluation_index
    xap_corr_inside_dsec = 1
    xap_corr_last_phase = 'dsec_internal'
  end subroutine xap_corr_before_dsec_evaluation

  subroutine xap_corr_after_dsec_evaluation()
    xap_corr_inside_dsec = 0
  end subroutine xap_corr_after_dsec_evaluation

  subroutine xap_corr_mark_post_dsec(dsec_call_id)
    integer, intent(in) :: dsec_call_id
    xap_corr_dsec_call_id = dsec_call_id
    xap_corr_dsec_evaluation = 0
    xap_corr_inside_dsec = 0
    xap_corr_post_dsec_pending = 1
    xap_corr_last_phase = 'post_dsec_pending'
  end subroutine xap_corr_mark_post_dsec

  subroutine xap_corr_classify_calc_hmc(calc_hmc_call_id, dsec_call_id, &
      evaluation_index, phase)
    integer, intent(in) :: calc_hmc_call_id
    integer, intent(out) :: dsec_call_id, evaluation_index
    character(len=*), intent(out) :: phase
    xap_corr_last_calc_hmc_call_id = calc_hmc_call_id
    if (xap_corr_inside_dsec .eq. 1) then
      dsec_call_id = xap_corr_dsec_call_id
      evaluation_index = xap_corr_dsec_evaluation
      phase = 'dsec_internal'
    else if (xap_corr_post_dsec_pending .eq. 1) then
      dsec_call_id = xap_corr_dsec_call_id
      evaluation_index = 0
      phase = 'post_dsec'
      xap_corr_post_dsec_pending = 0
    else
      dsec_call_id = 0
      evaluation_index = 0
      phase = 'outside_dsec'
    endif
    xap_corr_last_phase = phase
  end subroutine xap_corr_classify_calc_hmc

  subroutine xap_corr_current(calc_hmc_call_id, dsec_call_id, &
      evaluation_index, phase)
    integer, intent(out) :: calc_hmc_call_id, dsec_call_id, evaluation_index
    character(len=*), intent(out) :: phase
    calc_hmc_call_id = xap_corr_last_calc_hmc_call_id
    dsec_call_id = xap_corr_dsec_call_id
    evaluation_index = xap_corr_dsec_evaluation
    phase = xap_corr_last_phase
  end subroutine xap_corr_current
end module xap_call_correlation_state
'''


def write_call_correlation_probe_products(out_dir: str | Path) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    helper = out / "xstar_atomic_call_correlation_helpers.f90"
    helper.write_text(call_correlation_probe_helper(), encoding="utf-8")
    readme = out / "README_call_correlation.md"
    readme.write_text(
        "# XSTAR `dsec` / `calc_hmc_all` call correlation\n\n"
        "Compile `xstar_atomic_call_correlation_helpers.f90` before both the "
        "calc_hmc_all and dsec probe helpers. The module is diagnostic only.\n",
        encoding="utf-8",
    )
    return {"correlation_helper_fortran": helper, "correlation_readme": readme}


__all__ = ["call_correlation_probe_helper", "write_call_correlation_probe_products"]
