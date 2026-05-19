"""Generate safe XSTAR instrumentation for iteration-level ``msolvelucy`` parity.

The generated helper owns an independent call counter, captures only the
requested solve (or matching dimensions), uses ``newunit=`` file units, and
accepts the true leading dimension of ``ajissup``. It is diagnostic only and
does not alter rates or populations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict


def msolvelucy_state_probe_helper() -> str:
    """Return the compile-safe free-form Fortran helper."""
    return "! xstar-atomic v0.4.28 msolvelucy state probe (diagnostic only).\n!\n! This revision owns an independent msolvelucy call counter and writes only\n! the requested call or the configured target dimensions.  It does not share\n! COMMON state with the older population-closure probe.\n\nsubroutine xap_msl_begin_call(ipmat, nspmx, solve_call_id, capture)\n  implicit none\n  integer, intent(in) :: ipmat, nspmx\n  integer, intent(out) :: solve_call_id, capture\n  integer, save :: call_counter = 0\n  integer :: target_call, target_ipmat, target_nspmx\n  integer :: ios, stat\n  character(len=64) :: env\n\n  call_counter = call_counter + 1\n  solve_call_id = call_counter\n\n  target_call = 0\n  target_ipmat = 607\n  target_nspmx = 13\n\n  env = ''\n  call get_environment_variable('XSTAR_ATOMIC_MSOLVELUCY_TARGET_CALL', &\n       value=env, status=stat)\n  if (stat .eq. 0 .and. len_trim(env) .gt. 0) then\n    read(env, *, iostat=ios) target_call\n    if (ios .ne. 0) target_call = 0\n  endif\n\n  env = ''\n  call get_environment_variable('XSTAR_ATOMIC_MSOLVELUCY_TARGET_IPMAT', &\n       value=env, status=stat)\n  if (stat .eq. 0 .and. len_trim(env) .gt. 0) then\n    read(env, *, iostat=ios) target_ipmat\n    if (ios .ne. 0) target_ipmat = 607\n  endif\n\n  env = ''\n  call get_environment_variable('XSTAR_ATOMIC_MSOLVELUCY_TARGET_NSPMX', &\n       value=env, status=stat)\n  if (stat .eq. 0 .and. len_trim(env) .gt. 0) then\n    read(env, *, iostat=ios) target_nspmx\n    if (ios .ne. 0) target_nspmx = 13\n  endif\n\n  capture = 0\n  if (target_call .gt. 0) then\n    if (solve_call_id .eq. target_call) capture = 1\n  else\n    if (ipmat .eq. target_ipmat .and. nspmx .eq. target_nspmx) capture = 1\n  endif\nend subroutine xap_msl_begin_call\n\nsubroutine xap_msl_levels(fname, solve_call_id, phase, niter, nit2, nit3, &\n                          ipmat, x, nsup, nion, diff, diff2)\n  implicit none\n  character(len=*), intent(in) :: fname, phase\n  integer, intent(in) :: solve_call_id, niter, nit2, nit3, ipmat\n  real*8, intent(in) :: x(*), diff, diff2\n  integer, intent(in) :: nsup(*), nion(*)\n  integer :: lun, ios, mm\n  logical :: exists\n\n  inquire(file=fname, exist=exists)\n  open(newunit=lun, file=fname, status='unknown', position='append', &\n       action='write', iostat=ios)\n  if (ios .ne. 0) return\n  if (.not. exists) write(lun,'(A)') &\n    'solve_call_id,phase,outer_iteration,fixed_iteration,global_fixed_iteration,'// &\n    'compact_index,population,superlevel,ion_counter,diff,diff2'\n  do mm=1,ipmat\n    write(lun,9001) solve_call_id, trim(phase), niter, nit2, nit3, mm, x(mm), &\n      nsup(mm), nion(mm), diff, diff2\n  enddo\n  close(lun)\n9001 format(i12,',',a,',',i12,',',i12,',',i12,',',i12,',',1pe24.16,',', &\n  i12,',',i12,',',1pe24.16,',',1pe24.16)\nend subroutine xap_msl_levels\n\nsubroutine xap_msl_rr(fname, solve_call_id, niter, ipmat, x, rr, nsup, nion)\n  implicit none\n  character(len=*), intent(in) :: fname\n  integer, intent(in) :: solve_call_id, niter, ipmat\n  real*8, intent(in) :: x(*), rr(*)\n  integer, intent(in) :: nsup(*), nion(*)\n  integer :: lun, ios, mm\n  logical :: exists\n\n  inquire(file=fname, exist=exists)\n  open(newunit=lun, file=fname, status='unknown', position='append', &\n       action='write', iostat=ios)\n  if (ios .ne. 0) return\n  if (.not. exists) write(lun,'(A)') &\n    'solve_call_id,outer_iteration,compact_index,population,rr,superlevel,ion_counter'\n  do mm=1,ipmat\n    write(lun,9002) solve_call_id, niter, mm, x(mm), rr(mm), nsup(mm), nion(mm)\n  enddo\n  close(lun)\n9002 format(i12,',',i12,',',i12,',',1pe24.16,',',1pe24.16,',',i12,',',i12)\nend subroutine xap_msl_rr\n\nsubroutine xap_msl_superlevels(fname, solve_call_id, phase, niter, nspmx, p)\n  implicit none\n  character(len=*), intent(in) :: fname, phase\n  integer, intent(in) :: solve_call_id, niter, nspmx\n  real*8, intent(in) :: p(*)\n  integer :: lun, ios, mm\n  logical :: exists\n\n  inquire(file=fname, exist=exists)\n  open(newunit=lun, file=fname, status='unknown', position='append', &\n       action='write', iostat=ios)\n  if (ios .ne. 0) return\n  if (.not. exists) write(lun,'(A)') &\n    'solve_call_id,phase,outer_iteration,superlevel,population'\n  do mm=1,nspmx\n    write(lun,9003) solve_call_id, trim(phase), niter, mm, p(mm)\n  enddo\n  close(lun)\n9003 format(i12,',',a,',',i12,',',i12,',',1pe24.16)\nend subroutine xap_msl_superlevels\n\nsubroutine xap_msl_matrix(fname, solve_call_id, niter, nspmx, lda, a)\n  implicit none\n  character(len=*), intent(in) :: fname\n  integer, intent(in) :: solve_call_id, niter, nspmx, lda\n  real*8, intent(in) :: a(lda,*)\n  integer :: lun, ios, mm, nn\n  logical :: exists\n\n  inquire(file=fname, exist=exists)\n  open(newunit=lun, file=fname, status='unknown', position='append', &\n       action='write', iostat=ios)\n  if (ios .ne. 0) return\n  if (.not. exists) write(lun,'(A)') &\n    'solve_call_id,outer_iteration,row_superlevel,column_superlevel,matrix_value'\n  do mm=1,nspmx\n    do nn=1,nspmx\n      write(lun,9004) solve_call_id, niter, mm, nn, a(mm,nn)\n    enddo\n  enddo\n  close(lun)\n9004 format(i12,',',i12,',',i12,',',i12,',',1pe24.16)\nend subroutine xap_msl_matrix\n\nsubroutine xap_msl_fixed(fname, solve_call_id, niter, nit2, nit3, ipmat, &\n                         xold, riu, rui, ril, rli, x, nsup, nion, diff2)\n  implicit none\n  character(len=*), intent(in) :: fname\n  integer, intent(in) :: solve_call_id, niter, nit2, nit3, ipmat\n  real*8, intent(in) :: xold(*), riu(*), rui(*), ril(*), rli(*), x(*), diff2\n  integer, intent(in) :: nsup(*), nion(*)\n  integer :: lun, ios, mm\n  logical :: exists\n\n  inquire(file=fname, exist=exists)\n  open(newunit=lun, file=fname, status='unknown', position='append', &\n       action='write', iostat=ios)\n  if (ios .ne. 0) return\n  if (.not. exists) write(lun,'(A)') &\n    'solve_call_id,outer_iteration,fixed_iteration,global_fixed_iteration,'// &\n    'compact_index,population_before,riu,rui,ril,rli,population_after,'// &\n    'superlevel,ion_counter,diff2'\n  do mm=1,ipmat\n    write(lun,9005) solve_call_id, niter, nit2, nit3, mm, xold(mm), riu(mm), &\n      rui(mm), ril(mm), rli(mm), x(mm), nsup(mm), nion(mm), diff2\n  enddo\n  close(lun)\n9005 format(i12,',',i12,',',i12,',',i12,',',i12,',',1pe24.16,',', &\n  1pe24.16,',',1pe24.16,',',1pe24.16,',',1pe24.16,',',1pe24.16,',', &\n  i12,',',i12,',',1pe24.16)\nend subroutine xap_msl_fixed\n"


def msolvelucy_insertion_snippets() -> Dict[str, str]:
    """Return source-local insertion snippets keyed by placement."""
    return {
        "declarations": """! Add with the other integer declarations.
      integer xap_msl_solve_call_id, xap_msl_capture
""",
        "begin_call": """! Insert after rnhb/rnhb2 allocation, before the first remtms call.
      call xap_msl_begin_call(ipmat,nspmx,xap_msl_solve_call_id,        &
     &                        xap_msl_capture)
""",
        "outer_start": """! Insert immediately after: niter=niter+1
        if (xap_msl_capture.eq.1) then
          call xap_msl_levels('xstar_msolvelucy_levels_probe.csv',      &
     &        xap_msl_solve_call_id,'outer_start',niter,0,nit3,ipmat,  &
     &        x,nsup,nion,diff,0.d0)
          endif
""",
        "after_rr_and_condensed": """! Insert after the condensed-matrix nindb loop, before number conservation.
        if (xap_msl_capture.eq.1) then
          call xap_msl_rr('xstar_msolvelucy_rr_probe.csv',              &
     &        xap_msl_solve_call_id,niter,ipmat,x,rr,nsup,nion)
          call xap_msl_superlevels(                                     &
     &        'xstar_msolvelucy_superlevels_probe.csv',                 &
     &        xap_msl_solve_call_id,'before_condensed_solve',niter,    &
     &        nspmx,p)
          call xap_msl_matrix(                                          &
     &        'xstar_msolvelucy_condensed_matrix_probe.csv',           &
     &        xap_msl_solve_call_id,niter,nspmx,ndss,ajissup)
          endif
""",
        "after_condensed_population_update": """! Insert after the complete do mm=1,ipmat redistribution loop, before nit2=0.
        if (xap_msl_capture.eq.1) then
          call xap_msl_superlevels(                                     &
     &        'xstar_msolvelucy_superlevels_probe.csv',                 &
     &        xap_msl_solve_call_id,'after_condensed_solve',niter,     &
     &        nspmx,p)
          call xap_msl_levels('xstar_msolvelucy_levels_probe.csv',      &
     &        xap_msl_solve_call_id,'after_condensed_solve',niter,0,   &
     &        nit3,ipmat,x,nsup,nion,diff,0.d0)
          endif
""",
        "fixed_point_end": """! Insert after diff2 accumulation, before the fixed-point loop enddo.
          if (xap_msl_capture.eq.1) then
            call xap_msl_fixed('xstar_msolvelucy_fixed_probe.csv',      &
     &          xap_msl_solve_call_id,niter,nit2,nit3,ipmat,xoo,riu,   &
     &          rui,ril,rli,x,nsup,nion,diff2)
            endif
""",
        "outer_end": """! Insert after diff accumulation, before the outer loop enddo.
        if (xap_msl_capture.eq.1) then
          call xap_msl_levels('xstar_msolvelucy_levels_probe.csv',      &
     &        xap_msl_solve_call_id,'outer_end',niter,nit2,nit3,ipmat, &
     &        x,nsup,nion,diff,diff2)
          endif
""",
    }


def write_msolvelucy_state_probe_products(out_dir: str | Path) -> Dict[str, Path]:
    """Write the safe helper, insertion snippets, and patch notes."""
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
        "# Safe XSTAR `msolvelucy` state probe\n\n"
        "This is diagnostic-only instrumentation. It does not alter rates or populations.\n\n"
        "1. Add the helper before `msolvelucy.f90` in `HD_LIBRARY_SRC_f90`.\n"
        "2. Add the declaration and begin-call snippets once per routine.\n"
        "3. Apply the remaining snippets exactly at their documented loop boundaries.\n"
        "4. The post-condensed calls must be outside the complete `do mm=1,ipmat` loop.\n"
        "5. The matrix call passes `ndss` as the actual leading dimension.\n"
        "6. Set `XSTAR_ATOMIC_MSOLVELUCY_TARGET_CALL=219` for the validated oxygen solve, "
        "or omit it to select the default `ipmat=607`, `nspmx=13` dimensions.\n"
        "7. Delete old state CSVs before rerunning XSTAR.\n\n"
        "The run writes `xstar_msolvelucy_levels_probe.csv`, `xstar_msolvelucy_rr_probe.csv`, "
        "`xstar_msolvelucy_superlevels_probe.csv`, `xstar_msolvelucy_condensed_matrix_probe.csv`, "
        "and `xstar_msolvelucy_fixed_probe.csv`.\n\n"
        "The helper owns an independent solve-call counter and uses dynamically allocated file units.\n"
    )
    outputs["patch_notes"] = notes
    return outputs
