"""Generate one-time XSTAR instrumentation for iteration-level ``msolvelucy`` parity.

The production Python solver can emit the same outer-level, superlevel,
condensed-matrix, and fixed-point state.  These helpers instrument a debug
XSTAR build so those states can be compared without changing any rate or solve
logic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict


def msolvelucy_state_probe_helper() -> str:
    """Return a free-form Fortran helper used by the insertion snippets."""
    return r'''! xstar-atomic v0.4.7 msolvelucy state probe (diagnostic only).
subroutine xap_msl_levels(fname, phase, niter, nit2, nit3, ipmat, x, nsup, nion, diff, diff2)
  implicit none
  character(len=*), intent(in) :: fname, phase
  integer, intent(in) :: niter, nit2, nit3, ipmat
  real*8, intent(in) :: x(*), diff, diff2
  integer, intent(in) :: nsup(*), nion(*)
  integer :: lun, ios, mm, solve_call_id
  integer :: xap_pop_solve_call_id
  logical :: exists
  common /xap_pop_probe_state/ xap_pop_solve_call_id
  save /xap_pop_probe_state/
  if (xap_pop_solve_call_id .le. 0) xap_pop_solve_call_id = 1
  solve_call_id = xap_pop_solve_call_id
  lun = 935
  inquire(file=fname, exist=exists)
  open(unit=lun, file=fname, status='unknown', position='append', action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) write(lun,'(A)') &
    'solve_call_id,phase,outer_iteration,fixed_iteration,global_fixed_iteration,'// &
    'compact_index,population,superlevel,ion_counter,diff,diff2'
  do mm=1,ipmat
    write(lun,9001) solve_call_id, trim(phase), niter, nit2, nit3, mm, x(mm), &
      nsup(mm), nion(mm), diff, diff2
  enddo
  close(lun)
9001 format(i12,',',a,',',i12,',',i12,',',i12,',',i12,',',1pe24.16,',', &
  i12,',',i12,',',1pe24.16,',',1pe24.16)
end subroutine xap_msl_levels

subroutine xap_msl_rr(fname, niter, ipmat, x, rr, nsup, nion)
  implicit none
  character(len=*), intent(in) :: fname
  integer, intent(in) :: niter, ipmat
  real*8, intent(in) :: x(*), rr(*)
  integer, intent(in) :: nsup(*), nion(*)
  integer :: lun, ios, mm, solve_call_id
  integer :: xap_pop_solve_call_id
  logical :: exists
  common /xap_pop_probe_state/ xap_pop_solve_call_id
  save /xap_pop_probe_state/
  if (xap_pop_solve_call_id .le. 0) xap_pop_solve_call_id = 1
  solve_call_id = xap_pop_solve_call_id
  lun = 936
  inquire(file=fname, exist=exists)
  open(unit=lun, file=fname, status='unknown', position='append', action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) write(lun,'(A)') &
    'solve_call_id,outer_iteration,compact_index,population,rr,superlevel,ion_counter'
  do mm=1,ipmat
    write(lun,9002) solve_call_id, niter, mm, x(mm), rr(mm), nsup(mm), nion(mm)
  enddo
  close(lun)
9002 format(i12,',',i12,',',i12,',',1pe24.16,',',1pe24.16,',',i12,',',i12)
end subroutine xap_msl_rr

subroutine xap_msl_superlevels(fname, phase, niter, nspmx, p)
  implicit none
  character(len=*), intent(in) :: fname, phase
  integer, intent(in) :: niter, nspmx
  real*8, intent(in) :: p(*)
  integer :: lun, ios, mm, solve_call_id
  integer :: xap_pop_solve_call_id
  logical :: exists
  common /xap_pop_probe_state/ xap_pop_solve_call_id
  save /xap_pop_probe_state/
  if (xap_pop_solve_call_id .le. 0) xap_pop_solve_call_id = 1
  solve_call_id = xap_pop_solve_call_id
  lun = 937
  inquire(file=fname, exist=exists)
  open(unit=lun, file=fname, status='unknown', position='append', action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) write(lun,'(A)') &
    'solve_call_id,phase,outer_iteration,superlevel,population'
  do mm=1,nspmx
    write(lun,9003) solve_call_id, trim(phase), niter, mm, p(mm)
  enddo
  close(lun)
9003 format(i12,',',a,',',i12,',',i12,',',1pe24.16)
end subroutine xap_msl_superlevels

subroutine xap_msl_matrix(fname, niter, nspmx, a)
  implicit none
  character(len=*), intent(in) :: fname
  integer, intent(in) :: niter, nspmx
  real*8, intent(in) :: a(nspmx,nspmx)
  integer :: lun, ios, mm, nn, solve_call_id
  integer :: xap_pop_solve_call_id
  logical :: exists
  common /xap_pop_probe_state/ xap_pop_solve_call_id
  save /xap_pop_probe_state/
  if (xap_pop_solve_call_id .le. 0) xap_pop_solve_call_id = 1
  solve_call_id = xap_pop_solve_call_id
  lun = 938
  inquire(file=fname, exist=exists)
  open(unit=lun, file=fname, status='unknown', position='append', action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) write(lun,'(A)') &
    'solve_call_id,outer_iteration,row_superlevel,column_superlevel,matrix_value'
  do mm=1,nspmx
    do nn=1,nspmx
      write(lun,9004) solve_call_id, niter, mm, nn, a(mm,nn)
    enddo
  enddo
  close(lun)
9004 format(i12,',',i12,',',i12,',',i12,',',1pe24.16)
end subroutine xap_msl_matrix

subroutine xap_msl_fixed(fname, niter, nit2, nit3, ipmat, xold, riu, rui, ril, rli, x, nsup, nion, diff2)
  implicit none
  character(len=*), intent(in) :: fname
  integer, intent(in) :: niter, nit2, nit3, ipmat
  real*8, intent(in) :: xold(*), riu(*), rui(*), ril(*), rli(*), x(*), diff2
  integer, intent(in) :: nsup(*), nion(*)
  integer :: lun, ios, mm, solve_call_id
  integer :: xap_pop_solve_call_id
  logical :: exists
  common /xap_pop_probe_state/ xap_pop_solve_call_id
  save /xap_pop_probe_state/
  if (xap_pop_solve_call_id .le. 0) xap_pop_solve_call_id = 1
  solve_call_id = xap_pop_solve_call_id
  lun = 939
  inquire(file=fname, exist=exists)
  open(unit=lun, file=fname, status='unknown', position='append', action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) write(lun,'(A)') &
    'solve_call_id,outer_iteration,fixed_iteration,global_fixed_iteration,'// &
    'compact_index,population_before,riu,rui,ril,rli,population_after,'// &
    'superlevel,ion_counter,diff2'
  do mm=1,ipmat
    write(lun,9005) solve_call_id, niter, nit2, nit3, mm, xold(mm), riu(mm), &
      rui(mm), ril(mm), rli(mm), x(mm), nsup(mm), nion(mm), diff2
  enddo
  close(lun)
9005 format(i12,',',i12,',',i12,',',i12,',',i12,',',1pe24.16,',', &
  1pe24.16,',',1pe24.16,',',1pe24.16,',',1pe24.16,',',1pe24.16,',', &
  i12,',',i12,',',1pe24.16)
end subroutine xap_msl_fixed
'''


def msolvelucy_insertion_snippets() -> Dict[str, str]:
    """Return source-local insertion snippets keyed by placement."""
    return {
        "outer_start": r'''! Insert immediately after: niter=niter+1
        call xap_msl_levels('xstar_msolvelucy_levels_probe.csv', 'outer_start', &
     &      niter, 0, nit3, ipmat, x, nsup, nion, diff, 0.d0)
''',
        "after_rr_and_condensed": r'''! Insert after the condensed-matrix nindb loop, before number conservation.
        call xap_msl_rr('xstar_msolvelucy_rr_probe.csv', niter, ipmat, x, rr, nsup, nion)
        call xap_msl_superlevels('xstar_msolvelucy_superlevels_probe.csv', &
     &      'before_condensed_solve', niter, nspmx, p)
        call xap_msl_matrix('xstar_msolvelucy_condensed_matrix_probe.csv', &
     &      niter, nspmx, ajissup)
''',
        "after_condensed_population_update": r'''! Insert after x(mm)=rr(mm)*p(nsp), before nit2=0.
        call xap_msl_superlevels('xstar_msolvelucy_superlevels_probe.csv', &
     &      'after_condensed_solve', niter, nspmx, p)
        call xap_msl_levels('xstar_msolvelucy_levels_probe.csv', &
     &      'after_condensed_solve', niter, 0, nit3, ipmat, x, nsup, nion, diff, 0.d0)
''',
        "fixed_point_end": r'''! Insert after diff2 has been accumulated, before the fixed-point loop enddo.
        call xap_msl_fixed('xstar_msolvelucy_fixed_probe.csv', niter, nit2, nit3, &
     &      ipmat, xoo, riu, rui, ril, rli, x, nsup, nion, diff2)
''',
        "outer_end": r'''! Insert after diff has been accumulated, before the outer loop enddo.
        call xap_msl_levels('xstar_msolvelucy_levels_probe.csv', 'outer_end', &
     &      niter, nit2, nit3, ipmat, x, nsup, nion, diff, diff2)
''',
    }


def write_msolvelucy_state_probe_products(out_dir: str | Path) -> Dict[str, Path]:
    """Write the helper, insertion snippets, and patch notes."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    helper = out / "xstar_atomic_msolvelucy_state_probe_helpers.f90"
    helper.write_text(msolvelucy_state_probe_helper())
    outputs: Dict[str, Path] = {"helper_fortran": helper}
    for name, text in msolvelucy_insertion_snippets().items():
        path = out / f"msolvelucy_{name}_insertion.f90"
        path.write_text(text)
        outputs[f"{name}_insertion"] = path
    notes = out / "README_msolvelucy_state_probe.md"
    notes.write_text(
        "# XSTAR `msolvelucy` state probe\n\n"
        "This is a diagnostic-only patch for a debug XSTAR build. It does not alter rates or populations.\n\n"
        "1. Keep the existing paired population probe in `calc_hmc_element.f90`; its shared `solve_call_id` is reused.\n"
        "2. Add `xstar_atomic_msolvelucy_state_probe_helpers.f90` to `HD_LIBRARY_SRC_f90`.\n"
        "3. Apply each insertion snippet at the location named in its first comment.\n"
        "4. Delete all old `xstar_msolvelucy_*_probe.csv` files before rerunning the same O VII case.\n"
        "5. Run the Python element command with `--xstar-population-probe-csv` and `--write-msolvelucy-trace`.\n\n"
        "The debug run writes `xstar_msolvelucy_levels_probe.csv`, `xstar_msolvelucy_rr_probe.csv`, "
        "`xstar_msolvelucy_superlevels_probe.csv`, `xstar_msolvelucy_condensed_matrix_probe.csv`, and "
        "`xstar_msolvelucy_fixed_probe.csv`.\n\n"
        "The Python output names mirror the XSTAR probe phases, enabling direct row-by-row comparison of "
        "`x`, `p`, `rr`, `ajissup`, `riu`, `rui`, `ril`, and `rli`.\n"
    )
    outputs["patch_notes"] = notes
    return outputs
