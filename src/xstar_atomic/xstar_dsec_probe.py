"""Diagnostic-only trajectory probe for the XSTAR ``dsec`` routine.

The generated helper records the source control-flow trajectory without
changing temperature, electron fraction, populations, rates, or work arrays.
It is intentionally separate from the production Python implementation: probe
values are regression oracles only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict


def dsec_probe_helper() -> str:
    """Return the compile-safe free-form Fortran trajectory helper."""

    return r'''! xstar-atomic v0.4.45 bounded dsec trajectory probe.
!
! Diagnostic only.  This helper writes source state and never modifies the
! caller's temperature, electron fraction, populations, rates, or work arrays.
module xap_dsec_probe_state
  implicit none
  integer, save :: xap_dsec_call_counter = 0
  integer, save :: xap_dsec_current_call = 0
  integer, save :: xap_dsec_event_counter = 0
  integer, save :: xap_dsec_capture = 0
contains
  subroutine xap_dsec_read_int_env(name, value)
    character(len=*), intent(in) :: name
    integer, intent(inout) :: value
    character(len=128) :: env
    integer :: ios, stat, trial
    env = ''
    call get_environment_variable(name, value=env, status=stat)
    if (stat .eq. 0 .and. len_trim(env) .gt. 0) then
      read(env, *, iostat=ios) trial
      if (ios .eq. 0) value = trial
    endif
  end subroutine xap_dsec_read_int_env

  subroutine xap_dsec_write(event, evaluation_index, ntotit, nnx, nnxx, &
      nnt, nntt, nlim, nlimt, nlimx, nlimtt, nlimxx, t, tinf, xee, xpx, &
      tl, th, xeel, xeeh, elcter, elctrl, elctrh, hmctot, hmcttl, hmctth, &
      to, tst, testt, lnerr, iht, ilt, iuht, iult, ihx, ilx)
    character(len=*), intent(in) :: event
    integer, intent(in) :: evaluation_index, ntotit, nnx, nnxx, nnt, nntt
    integer, intent(in) :: nlim, nlimt, nlimx, nlimtt, nlimxx, lnerr
    integer, intent(in) :: iht, ilt, iuht, iult, ihx, ilx
    real(8), intent(in) :: t, tinf, xee, xpx, tl, th, xeel, xeeh
    real(8), intent(in) :: elcter, elctrl, elctrh, hmctot, hmcttl, hmctth
    real(8), intent(in) :: to, tst, testt
    integer :: lun, ios
    logical :: exists

    if (xap_dsec_capture .ne. 1) return
    xap_dsec_event_counter = xap_dsec_event_counter + 1
    inquire(file='xstar_dsec_trajectory_probe.csv', exist=exists)
    open(newunit=lun, file='xstar_dsec_trajectory_probe.csv', &
         status='unknown', position='append', action='write', iostat=ios)
    if (ios .ne. 0) return
    if (.not. exists) write(lun,'(A)') &
      'dsec_call_id,event_index,event,evaluation_index,ntotit,nnx,nnxx,'// &
      'nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx,temperature_t4,'// &
      'temperature_k,tinf_t4,electron_fraction_xee,'// &
      'hydrogen_density_cm3,tl,th,xeel,xeeh,elcter,elctrl,elctrh,'// &
      'hmctot,hmcttl,hmctth,previous_temperature_t4,'// &
      'normalized_charge_residual,temperature_stagnation_metric,'// &
      'lnerr,iht,ilt,iuht,iult,ihx,ilx'
    write(lun,9001) xap_dsec_current_call, xap_dsec_event_counter, &
      trim(event), evaluation_index, ntotit, nnx, nnxx, nnt, nntt, nlim, &
      nlimt, nlimx, nlimtt, nlimxx, t, t*1.d4, tinf, xee, xpx, tl, th, &
      xeel, xeeh, elcter, elctrl, elctrh, hmctot, hmcttl, hmctth, to, &
      tst, testt, lnerr, iht, ilt, iuht, iult, ihx, ilx
    close(lun)
9001 format(i12,',',i12,',',a,11(',',i12),18(',',es26.16e3),7(',',i12))
  end subroutine xap_dsec_write
end module xap_dsec_probe_state

subroutine xap_dsec_begin(nlim, nlimt, nlimx, nlimtt, nlimxx, t, tinf, &
    xee, xpx, tl, th, xeel, xeeh, elctrl, elctrh, hmcttl, hmctth, to, &
    lnerr, iht, ilt, iuht, iult)
  use xap_dsec_probe_state
  implicit none
  integer, intent(in) :: nlim, nlimt, nlimx, nlimtt, nlimxx, lnerr
  integer, intent(in) :: iht, ilt, iuht, iult
  real(8), intent(in) :: t, tinf, xee, xpx, tl, th, xeel, xeeh
  real(8), intent(in) :: elctrl, elctrh, hmcttl, hmctth, to
  integer :: target_call
  real(8) :: missing

  xap_dsec_call_counter = xap_dsec_call_counter + 1
  xap_dsec_current_call = xap_dsec_call_counter
  xap_dsec_event_counter = 0
  xap_dsec_capture = 0
  target_call = 1
  call xap_dsec_read_int_env('XSTAR_ATOMIC_DSEC_TARGET_CALL', target_call)
  if (target_call .le. 0 .or. xap_dsec_current_call .eq. target_call) &
    xap_dsec_capture = 1
  missing = huge(1.d0)
  call xap_dsec_write('begin', 0, 0, 0, 0, 0, 0, nlim, nlimt, nlimx, &
    nlimtt, nlimxx, t, tinf, xee, xpx, tl, th, xeel, xeeh, missing, &
    elctrl, elctrh, missing, hmcttl, hmctth, to, missing, missing, &
    lnerr, iht, ilt, iuht, iult, 0, 0)
end subroutine xap_dsec_begin

subroutine xap_dsec_event(event, evaluation_index, ntotit, nnx, nnxx, &
    nnt, nntt, nlim, nlimt, nlimx, nlimtt, nlimxx, t, tinf, xee, xpx, &
    tl, th, xeel, xeeh, elcter, elctrl, elctrh, hmctot, hmcttl, hmctth, &
    to, tst, testt, lnerr, iht, ilt, iuht, iult, ihx, ilx)
  use xap_dsec_probe_state
  implicit none
  character(len=*), intent(in) :: event
  integer, intent(in) :: evaluation_index, ntotit, nnx, nnxx, nnt, nntt
  integer, intent(in) :: nlim, nlimt, nlimx, nlimtt, nlimxx, lnerr
  integer, intent(in) :: iht, ilt, iuht, iult, ihx, ilx
  real(8), intent(in) :: t, tinf, xee, xpx, tl, th, xeel, xeeh
  real(8), intent(in) :: elcter, elctrl, elctrh, hmctot, hmcttl, hmctth
  real(8), intent(in) :: to, tst, testt
  call xap_dsec_write(event, evaluation_index, ntotit, nnx, nnxx, nnt, &
    nntt, nlim, nlimt, nlimx, nlimtt, nlimxx, t, tinf, xee, xpx, tl, &
    th, xeel, xeeh, elcter, elctrl, elctrh, hmctot, hmcttl, hmctth, to, &
    tst, testt, lnerr, iht, ilt, iuht, iult, ihx, ilx)
end subroutine xap_dsec_event
'''


def dsec_insertion_snippets() -> Dict[str, str]:
    """Return source-local insertion snippets for ``dsec.f90``."""

    common = (
        "ntotit,nnx,nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx," \
        "t,tinf,xee,xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh," \
        "hmctot,hmcttl,hmctth,to,tst,testt,lnerr,iht,ilt,iuht,iult,ihx,ilx"
    )
    # Written explicitly to make source review straightforward.
    return {
        "dsec_begin": """! Insert after iht/ilt/iuht/iult are initialized and before label 100.
! The test variables are diagnostics only until the source assigns them.
      tst=huge(1.d0)
      testt=huge(1.d0)
      call xap_dsec_begin(nlim,nlimt,nlimx,nlimtt,nlimxx,t,tinf,     &
     & xee,xpx,tl,th,xeel,xeeh,elctrl,elctrh,hmcttl,hmctth,to,      &
     & lnerr,iht,ilt,iuht,iult)
""",
        "after_calc_hmc_all": """! Insert after ntotit/nnx/nnxx increments and before the nnxx limit test.
      call xap_dsec_event('after_calc_hmc_all',ntotit,              &
     & ntotit,nnx,nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx,   &
     & t,tinf,xee,xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh,        &
     & hmctot,hmcttl,hmctth,to,abs(elcter)/max(1.d-48,xee),testt,  &
     & lnerr,iht,ilt,iuht,iult,ihx,ilx)
""",
        "charge_multiply": """! Insert immediately after xee=xee*facx and before goto 200.
               call xap_dsec_event('charge_multiply_xee',ntotit,    &
     & ntotit,nnx,nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx,   &
     & t,tinf,xee,xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh,        &
     & hmctot,hmcttl,hmctth,to,tst,testt,lnerr,iht,ilt,iuht,iult,  &
     & ihx,ilx)
""",
        "charge_divide": """! Insert immediately after xee=xee/facx and before goto 200.
               call xap_dsec_event('charge_divide_xee',ntotit,      &
     & ntotit,nnx,nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx,   &
     & t,tinf,xee,xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh,        &
     & hmctot,hmcttl,hmctth,to,tst,testt,lnerr,iht,ilt,iuht,iult,  &
     & ihx,ilx)
""",
        "charge_secant": """! Insert immediately after the xee secant assignment and before goto 200.
         call xap_dsec_event('charge_secant',ntotit,ntotit,nnx,    &
     & nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx,t,tinf,xee,   &
     & xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh,hmctot,hmcttl,     &
     & hmctth,to,tst,testt,lnerr,iht,ilt,iuht,iult,ihx,ilx)
""",
        "charge_loop_exit": """! Insert at label 300 after nntt/nnt are incremented.
      call xap_dsec_event('charge_loop_exit',ntotit,ntotit,nnx,    &
     & nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx,t,tinf,xee,   &
     & xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh,hmctot,hmcttl,     &
     & hmctth,to,abs(elcter)/max(1.d-48,xee),testt,lnerr,iht,ilt, &
     & iuht,iult,ihx,ilx)
""",
        "temperature_divide": """! Insert after both possible t=t/fact operations and before goto 100.
               call xap_dsec_event('temperature_divide',ntotit,    &
     & ntotit,nnx,nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx,   &
     & t,tinf,xee,xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh,        &
     & hmctot,hmcttl,hmctth,to,tst,testt,lnerr,iht,ilt,iuht,iult,  &
     & ihx,ilx)
""",
        "temperature_multiply": """! Insert after both possible t=t*fact operations and before goto 100.
               call xap_dsec_event('temperature_multiply',ntotit,  &
     & ntotit,nnx,nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx,   &
     & t,tinf,xee,xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh,        &
     & hmctot,hmcttl,hmctth,to,tst,testt,lnerr,iht,ilt,iuht,iult,  &
     & ihx,ilx)
""",
        "temperature_stagnation": """! Insert after lnerr=-2 and before the print/goto 500 block.
            call xap_dsec_event('temperature_stagnation',ntotit,   &
     & ntotit,nnx,nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx,   &
     & t,tinf,xee,xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh,        &
     & hmctot,hmcttl,hmctth,to,tst,testt,lnerr,iht,ilt,iuht,iult,  &
     & ihx,ilx)
""",
        "temperature_secant": """! Insert after the t secant assignment and before goto 100.
            call xap_dsec_event('temperature_secant',ntotit,       &
     & ntotit,nnx,nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,nlimxx,   &
     & t,tinf,xee,xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh,        &
     & hmctot,hmcttl,hmctth,to,tst,testt,lnerr,iht,ilt,iuht,iult,  &
     & ihx,ilx)
""",
        "too_many_iterations": """! Insert after lnerr=2 and before the warning writes.
      call xap_dsec_event('temperature_too_many_iterations',       &
     & ntotit,ntotit,nnx,nnxx,nnt,nntt,nlim,nlimt,nlimx,nlimtt,   &
     & nlimxx,t,tinf,xee,xpx,tl,th,xeel,xeeh,elcter,elctrl,elctrh,&
     & hmctot,hmcttl,hmctth,to,tst,testt,lnerr,iht,ilt,iuht,iult,  &
     & ihx,ilx)
""",
        "finish": """! Insert at label 500 before the existing print and lppri restore.
  500 call xap_dsec_event('finish',ntotit,ntotit,nnx,nnxx,nnt,nntt,&
     & nlim,nlimt,nlimx,nlimtt,nlimxx,t,tinf,xee,xpx,tl,th,xeel,   &
     & xeeh,elcter,elctrl,elctrh,hmctot,hmcttl,hmctth,to,        &
     & abs(elcter)/max(1.d-48,xee),testt,lnerr,iht,ilt,iuht,iult,ihx, &
     & ilx)
! Replace the original label-500 statement with the call above followed by:
      if ( lppri.ne.0 ) write (lun11,99007) testt,epst,hmctot
""",
    }


def write_dsec_probe_products(out_dir: str | Path) -> Dict[str, Path]:
    """Write helper source, insertion snippets, and build/run instructions."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    outputs: Dict[str, Path] = {}
    helper = out / "xstar_atomic_dsec_probe_helpers.f90"
    helper.write_text(dsec_probe_helper(), encoding="utf-8")
    outputs["helper_fortran"] = helper
    for name, snippet in dsec_insertion_snippets().items():
        path = out / f"{name}_insertion.f90"
        path.write_text(snippet, encoding="utf-8")
        outputs[f"{name}_insertion"] = path

    readme = out / "README_dsec_probe.md"
    readme.write_text(
        "# Bounded XSTAR `dsec` trajectory probe\n\n"
        "This v0.4.45 helper records every branch-relevant `dsec.f90` state "
        "transition. It is diagnostic only and does not supply any value to "
        "the Python production calculation.\n\n"
        "1. Compile `xstar_atomic_dsec_probe_helpers.f90` before `dsec.f90`.\n"
        "2. Apply the insertion snippets at the documented source locations.\n"
        "3. Delete any old `xstar_dsec_trajectory_probe.csv`.\n"
        "4. Set `XSTAR_ATOMIC_DSEC_TARGET_CALL` to the desired `dsec` call "
        "(default: 1). A value <=0 captures every call.\n"
        "5. Rebuild and run the same bounded XSTAR model used for Python.\n\n"
        "Output: `xstar_dsec_trajectory_probe.csv`.\n\n"
        "The inserted initialization of `tst` and `testt` uses `huge(1.d0)` "
        "only to make otherwise undefined diagnostic fields deterministic; "
        "neither variable is read by the physical algorithm before the "
        "source assigns it.\n",
        encoding="utf-8",
    )
    outputs["readme"] = readme
    return outputs


__all__ = ["dsec_probe_helper", "dsec_insertion_snippets", "write_dsec_probe_products"]
