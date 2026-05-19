"""Bounded XSTAR instrumentation for fixed-state ``calc_hmc_all`` parity.

The generated helper is diagnostic only.  It captures the first-pass
``calc_ion_rates -> istruc -> mml/mmu`` products inside ``calc_hmc_element``
and the complete element-loop state in ``calc_hmc_all`` immediately before
``comp2``.  No rates, populations, or source arrays are modified.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict


def calc_hmc_all_probe_helper() -> str:
    """Return a compile-safe free-form Fortran helper with bounded capture."""
    return r'''! xstar-atomic v0.4.30 calc_hmc_all pre-continuum and matrix probe.
!
! Diagnostic only: this helper never changes rates, populations, or state.
module xap_calc_hmc_probe_state
  implicit none
  integer, save :: xap_hmc_call_counter = 0
  integer, save :: xap_hmc_current_call = 0
  integer, save :: xap_hmc_capture = 0
  integer, save :: xap_hmc_target_element = 8
  integer, save :: xap_hmc_current_element_index = 0
  integer, save :: xap_hmc_current_element_z = 0
contains
  subroutine xap_read_int_env(name, value)
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
  end subroutine xap_read_int_env

  subroutine xap_read_real_env(name, value)
    character(len=*), intent(in) :: name
    real(8), intent(inout) :: value
    character(len=128) :: env
    integer :: ios, stat
    real(8) :: trial
    env = ''
    call get_environment_variable(name, value=env, status=stat)
    if (stat .eq. 0 .and. len_trim(env) .gt. 0) then
      read(env, *, iostat=ios) trial
      if (ios .eq. 0) value = trial
    endif
  end subroutine xap_read_real_env
end module xap_calc_hmc_probe_state

subroutine xap_hmc_begin_call(t4, xee, xpx)
  use xap_calc_hmc_probe_state
  implicit none
  real(8), intent(in) :: t4, xee, xpx
  integer :: target_call
  real(8) :: target_t4, target_xee, target_xpx
  real(8) :: rtol, atol

  xap_hmc_call_counter = xap_hmc_call_counter + 1
  xap_hmc_current_call = xap_hmc_call_counter
  xap_hmc_capture = 0

  target_call = 0
  target_t4 = 7.665518557758832d0
  target_xee = 1.2046560563936872d0
  target_xpx = 1.d8
  rtol = 1.d-10
  atol = 1.d-12
  xap_hmc_target_element = 8

  call xap_read_int_env('XSTAR_ATOMIC_HMC_TARGET_CALL', target_call)
  call xap_read_int_env('XSTAR_ATOMIC_HMC_TARGET_ELEMENT', &
       xap_hmc_target_element)
  call xap_read_real_env('XSTAR_ATOMIC_HMC_TARGET_T4', target_t4)
  call xap_read_real_env('XSTAR_ATOMIC_HMC_TARGET_XEE', target_xee)
  call xap_read_real_env('XSTAR_ATOMIC_HMC_TARGET_XPX', target_xpx)
  call xap_read_real_env('XSTAR_ATOMIC_HMC_TARGET_RTOL', rtol)
  call xap_read_real_env('XSTAR_ATOMIC_HMC_TARGET_ATOL', atol)

  if (target_call .gt. 0) then
    if (xap_hmc_current_call .eq. target_call) xap_hmc_capture = 1
  else
    if (abs(t4-target_t4) .le. atol+rtol*abs(target_t4) .and. &
        abs(xee-target_xee) .le. atol+rtol*abs(target_xee) .and. &
        abs(xpx-target_xpx) .le. atol+rtol*abs(target_xpx)) then
      xap_hmc_capture = 1
    endif
  endif
end subroutine xap_hmc_begin_call

subroutine xap_hmce_pre_matrix(element_z, nnz, pirt, rrrt, xitp, &
                               mml, mmu, critf)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: element_z, nnz, mml, mmu
  real(8), intent(in) :: pirt(*), rrrt(*), xitp(*), critf
  integer :: lun, ios, stage
  logical :: exists

  if (xap_hmc_capture .ne. 1) return
  if (element_z .ne. xap_hmc_target_element) return
  inquire(file='xstar_calc_hmc_element_pre_matrix_probe.csv', &
          exist=exists)
  open(newunit=lun, file='xstar_calc_hmc_element_pre_matrix_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,element_z,ion_stage,pirt,rrrt,xitp,mml,mmu,critf'
  do stage=1,nnz+1
    if (stage .le. nnz) then
      write(lun,9001) xap_hmc_current_call, element_z, stage, &
        pirt(stage), rrrt(stage), xitp(stage), mml, mmu, critf
    else
      write(lun,9001) xap_hmc_current_call, element_z, stage, &
        0.d0, 0.d0, xitp(stage), mml, mmu, critf
    endif
  enddo
  close(lun)
9001 format(i12,',',i12,',',i12,',',es26.16e3,',',es26.16e3,',', &
            es26.16e3,',',i12,',',i12,',',es26.16e3)
end subroutine xap_hmce_pre_matrix


subroutine xap_hmc_element_post(element_index, element_z, abundance, &
    mml, mmu, htt, cll, htt2, cll2)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: element_index, element_z, mml, mmu
  real(8), intent(in) :: abundance, htt, cll, htt2, cll2
  integer :: lun, ios
  logical :: exists

  if (xap_hmc_capture .ne. 1) return
  inquire(file='xstar_calc_hmc_all_pre_continuum_elements_probe.csv', &
          exist=exists)
  open(newunit=lun, &
       file='xstar_calc_hmc_all_pre_continuum_elements_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,element_index,element_z,abundance,mml,mmu,'// &
    'htt,cll,htt2,cll2'
  write(lun,9005) xap_hmc_current_call, element_index, element_z, &
    abundance, mml, mmu, htt, cll, htt2, cll2
  close(lun)
9005 format(i12,',',i12,',',i12,',',es26.16e3,',',i12,',',i12,4(',',es26.16e3))
end subroutine xap_hmc_element_post

subroutine xap_hmc_matrix_terms(element_index, element_z, ipmat, nindb, &
    ajisb, cjisb, cjisb2, indb, ltpsv, x)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: element_index, element_z, ipmat, nindb
  real(8), intent(in) :: ajisb(2,*), cjisb(*), cjisb2(*), x(*)
  integer, intent(in) :: indb(2,*), ltpsv(*)
  integer :: lun, ios, ll, row_raw, column_raw, row_compact
  integer :: column_compact
  logical :: exists

  xap_hmc_current_element_index = element_index
  xap_hmc_current_element_z = element_z
  if (xap_hmc_capture .ne. 1) return
  if (element_z .ne. xap_hmc_target_element) return

  inquire(file='xstar_calc_hmc_all_matrix_terms_probe.csv', &
          exist=exists)
  open(newunit=lun, file='xstar_calc_hmc_all_matrix_terms_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,element_index,element_z,compact_dimension,'// &
    'n_matrix_terms,term_index,source_record,row_raw,column_raw,'// &
    'row_compact,column_compact,aj1,aj2,cj,cj2,row_population,'// &
    'column_population'
  do ll=1,nindb
    row_raw=indb(1,ll)
    column_raw=indb(2,ll)
    row_compact=min(ipmat,row_raw)
    column_compact=min(ipmat,column_raw)
    write(lun,9006) xap_hmc_current_call, element_index, element_z, &
      ipmat, nindb, ll, ltpsv(ll), row_raw, column_raw, row_compact, &
      column_compact, ajisb(1,ll), ajisb(2,ll), cjisb(ll), cjisb2(ll), &
      x(row_compact), x(column_compact)
  enddo
  close(lun)
9006 format(11(i12,','),5(es26.16e3,','),es26.16e3)
end subroutine xap_hmc_matrix_terms

subroutine xap_hmc_thermal_families(ntyp_local, rntpsv, rltpsv)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: ntyp_local
  real(8), intent(in) :: rntpsv(ntyp_local,4), rltpsv(ntyp_local,4)
  integer :: lun, ios, idx
  logical :: exists
  real(8) :: scale

  if (xap_hmc_capture .ne. 1) return
  if (xap_hmc_current_element_z .ne. xap_hmc_target_element) return

  inquire(file='xstar_calc_hmc_all_thermal_data_type_probe.csv', &
          exist=exists)
  open(newunit=lun, &
       file='xstar_calc_hmc_all_thermal_data_type_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,element_index,element_z,data_type,'// &
      'heating,cooling,heating2,cooling2'
    do idx=1,ntyp_local
      scale=sum(abs(rntpsv(idx,1:4)))
      if (scale .gt. 0.d0) write(lun,9007) xap_hmc_current_call, &
        xap_hmc_current_element_index, xap_hmc_current_element_z, idx, &
        rntpsv(idx,1), rntpsv(idx,2), rntpsv(idx,3), rntpsv(idx,4)
    enddo
    close(lun)
  endif

  inquire(file='xstar_calc_hmc_all_thermal_rate_type_probe.csv', &
          exist=exists)
  open(newunit=lun, &
       file='xstar_calc_hmc_all_thermal_rate_type_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,element_index,element_z,rate_type,'// &
      'heating,cooling,heating2,cooling2'
    do idx=1,ntyp_local
      scale=sum(abs(rltpsv(idx,1:4)))
      if (scale .gt. 0.d0) write(lun,9007) xap_hmc_current_call, &
        xap_hmc_current_element_index, xap_hmc_current_element_z, idx, &
        rltpsv(idx,1), rltpsv(idx,2), rltpsv(idx,3), rltpsv(idx,4)
    enddo
    close(lun)
  endif
9007 format(4(i12,','),3(es26.16e3,','),es26.16e3)
end subroutine xap_hmc_thermal_families

subroutine xap_hmc_pre_continuum(t4, xee, xpx, httot, cltot, httot2, &
    cltot2, enelec, elcter, nion, nlevel, xiin, rrrt, pirt, htt, cll, &
    htt2, cll2, stotg, atotg, xtotg, xilevg, rnisg, bilevg, gammag, &
    alphag, igammamaxg, ialphamaxg)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: nion, nlevel
  real(8), intent(in) :: t4, xee, xpx, httot, cltot, httot2, cltot2
  real(8), intent(in) :: enelec, elcter
  real(8), intent(in) :: xiin(*), rrrt(*), pirt(*), htt(*), cll(*)
  real(8), intent(in) :: htt2(*), cll2(*), stotg(*), atotg(*), xtotg(*)
  real(8), intent(in) :: xilevg(*), rnisg(*), bilevg(*), gammag(*)
  real(8), intent(in) :: alphag(*)
  integer, intent(in) :: igammamaxg(*), ialphamaxg(*)
  integer :: lun, ios, idx
  logical :: exists
  real(8) :: scale

  if (xap_hmc_capture .ne. 1) return

  inquire(file='xstar_calc_hmc_all_pre_continuum_summary_probe.csv', &
          exist=exists)
  open(newunit=lun, &
       file='xstar_calc_hmc_all_pre_continuum_summary_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,temperature_t4,temperature_k,xee,xpx,'// &
      'httot,cltot,httot2,cltot2,enelec,elcter'
    write(lun,9002) xap_hmc_current_call, t4, 1.d4*t4, xee, xpx, &
      httot, cltot, httot2, cltot2, enelec, elcter
    close(lun)
  endif

  inquire(file='xstar_calc_hmc_all_pre_continuum_ions_probe.csv', &
          exist=exists)
  open(newunit=lun, &
       file='xstar_calc_hmc_all_pre_continuum_ions_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,global_ion_index,xiin,rrrt,pirt,htt,cll,'// &
      'htt2,cll2,stotg,atotg,xtotg'
    do idx=1,nion
      scale = abs(xiin(idx))+abs(rrrt(idx))+abs(pirt(idx))+abs(htt(idx))+ &
        abs(cll(idx))+abs(htt2(idx))+abs(cll2(idx))+abs(stotg(idx))+ &
        abs(atotg(idx))+abs(xtotg(idx))
      if (scale .gt. 0.d0) then
        write(lun,9003) xap_hmc_current_call, idx, xiin(idx), rrrt(idx), &
          pirt(idx), htt(idx), cll(idx), htt2(idx), cll2(idx), &
          stotg(idx), atotg(idx), xtotg(idx)
      endif
    enddo
    close(lun)
  endif

  inquire(file='xstar_calc_hmc_all_pre_continuum_levels_probe.csv', &
          exist=exists)
  open(newunit=lun, &
       file='xstar_calc_hmc_all_pre_continuum_levels_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,global_level_index,xilevg,rnisg,bilevg,'// &
      'gammag,alphag,igammamax_record,ialphamax_record'
    do idx=1,nlevel
      scale = abs(xilevg(idx))+abs(rnisg(idx))+abs(bilevg(idx))+ &
        abs(gammag(idx))+abs(alphag(idx))
      if (scale .gt. 0.d0 .or. igammamaxg(idx) .ne. 0 .or. &
          ialphamaxg(idx) .ne. 0) then
        write(lun,9004) xap_hmc_current_call, idx, xilevg(idx), &
          rnisg(idx), bilevg(idx), gammag(idx), alphag(idx), &
          igammamaxg(idx), ialphamaxg(idx)
      endif
    enddo
    close(lun)
  endif

9002 format(i12,10(',',es26.16e3))
9003 format(i12,',',i12,10(',',es26.16e3))
9004 format(i12,',',i12,5(',',es26.16e3),',',i12,',',i12)
end subroutine xap_hmc_pre_continuum
'''


def calc_hmc_all_insertion_snippets() -> Dict[str, str]:
    """Return exact source-local insertion snippets."""
    return {
        "calc_hmc_all_begin_call": """! Insert after the lcdd density branches and before xh0/xh1.
      call xap_hmc_begin_call(t,xee,xpx)
""",
        "calc_hmc_element_pre_matrix": """! Insert immediately after mml/mmu are finalized, before levwkelement.
      call xap_hmce_pre_matrix(jk,nnz,pirti,rrrti,xitp,                &
     &                         mml(jk),mmu(jk),critf)
""",
        "calc_hmc_all_element_post": """! Insert after htt(jk),cll(jk),htt2(jk),cll2(jk) are assigned.
      call xap_hmc_element_post(jk,nnz,xeltp,mml(jk),mmu(jk),        &
     &     htt(jk),cll(jk),htt2(jk),cll2(jk))
""",
        "calc_hmc_element_matrix_terms": """! Insert immediately before call msolvelucy in calc_hmc_element.
      call xap_hmc_matrix_terms(jk,nnz,ipmat2,nindbe,ajise,cjise,    &
     &     cjise2,indbe,ltpsve,x)
""",
        "msolvelucy_thermal_families": """! Insert after the thermal accumulation loop and before the lpri print block.
      call xap_hmc_thermal_families(ntyp,rntpsv,rltpsv)
""",
        "calc_hmc_all_pre_continuum": """! Insert after elcter=-enelec+xee and before call comp2.
      call xap_hmc_pre_continuum(t,xee,xpx,httot,cltot,httot2,cltot2, &
     &     enelec,elcter,nni,nnml,xiin,rrrt,pirt,htt,cll,htt2,cll2,  &
     &     stotg,atotg,xtotg,xilevg,rnisg,bilevg,gammag,alphag,      &
     &     igammamaxg,ialphamaxg)
""",
    }


def write_calc_hmc_all_probe_products(out_dir: str | Path) -> Dict[str, Path]:
    """Write helper source, insertion snippets, schemas, and build notes."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    outputs: Dict[str, Path] = {}

    helper = out / "xstar_atomic_calc_hmc_all_probe_helpers.f90"
    helper.write_text(calc_hmc_all_probe_helper())
    outputs["helper_fortran"] = helper

    for name, snippet in calc_hmc_all_insertion_snippets().items():
        path = out / f"{name}_insertion.f90"
        path.write_text(snippet)
        outputs[f"{name}_insertion"] = path

    readme = out / "README_calc_hmc_all_probe.md"
    readme.write_text(
        "# Bounded XSTAR `calc_hmc_all` pre-continuum probe\n\n"
        "This diagnostic instrumentation captures the source first pass and "
        "the state immediately before `comp2`; it never changes rates or populations.\n\n"
        "1. Add `xstar_atomic_calc_hmc_all_probe_helpers.f90` before "
        "`calc_hmc_element.f90`, `msolvelucy.f90`, and `calc_hmc_all.f90` "
        "in the XSTAR build source list.\n"
        "2. Apply the six insertion snippets at their documented locations.\n"
        "3. Delete prior `xstar_calc_hmc_*_probe.csv` files before the run.\n"
        "4. By default the helper captures the call at `T=76655.18557758832 K`, "
        "`xpx=1e8 cm^-3`, `xee=1.2046560563936872`, and element Z=8.\n"
        "5. To select by call number, set `XSTAR_ATOMIC_HMC_TARGET_CALL`. "
        "Other controls are `XSTAR_ATOMIC_HMC_TARGET_ELEMENT`, `_T4`, `_XEE`, "
        "`_XPX`, `_RTOL`, and `_ATOL`.\n\n"
        "Outputs:\n\n"
        "- `xstar_calc_hmc_element_pre_matrix_probe.csv`\n"
        "- `xstar_calc_hmc_all_pre_continuum_summary_probe.csv`\n"
        "- `xstar_calc_hmc_all_pre_continuum_ions_probe.csv`\n"
        "- `xstar_calc_hmc_all_pre_continuum_levels_probe.csv`\n"
        "- `xstar_calc_hmc_all_pre_continuum_elements_probe.csv`\n"
        "- `xstar_calc_hmc_all_matrix_terms_probe.csv`\n"
        "- `xstar_calc_hmc_all_thermal_data_type_probe.csv`\n"
        "- `xstar_calc_hmc_all_thermal_rate_type_probe.csv`\n"
    )
    outputs["readme"] = readme
    return outputs


__all__ = [
    "calc_hmc_all_probe_helper",
    "calc_hmc_all_insertion_snippets",
    "write_calc_hmc_all_probe_products",
]
