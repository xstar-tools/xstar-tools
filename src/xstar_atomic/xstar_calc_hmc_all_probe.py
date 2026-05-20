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
    return r'''! xstar-atomic v0.4.43 complete fixed-state calc_hmc_all thermal/charge, continuum, leveltemp, matrix, and final-solve probe.
!
! Diagnostic only: this helper never changes rates, populations, or state.
module xap_calc_hmc_probe_state
  implicit none
  integer, save :: xap_hmc_call_counter = 0
  integer, save :: xap_hmc_current_call = 0
  integer, save :: xap_hmc_capture = 0
  integer, save :: xap_hmc_target_element = 8
  integer, save :: xap_hmc_target_record = 0
  integer, save :: xap_hmc_current_element_index = 0
  integer, save :: xap_hmc_current_element_z = 0
  integer, save :: xap_hmc_freef_ncn2 = 0
  real(8), save :: xap_hmc_freef_t4 = 0.d0
  real(8), save :: xap_hmc_freef_xee = 0.d0
  real(8), save :: xap_hmc_freef_xpx = 0.d0
  real(8), allocatable, save :: xap_hmc_freef_opakc_before(:)
  integer, save :: xap_hmc_bremem_ncn2 = 0
  real(8), save :: xap_hmc_bremem_t4 = 0.d0
  real(8), save :: xap_hmc_bremem_xee = 0.d0
  real(8), save :: xap_hmc_bremem_xpx = 0.d0
  real(8), allocatable, save :: xap_hmc_bremem_opakc_before(:)
  real(8), allocatable, save :: xap_hmc_bremem_brcems_before(:)
  integer, save :: xap_hmc_heatf_ncn2 = 0
  real(8), save :: xap_hmc_heatf_t4 = 0.d0
  real(8), save :: xap_hmc_heatf_r = 0.d0
  real(8), save :: xap_hmc_heatf_delr = 0.d0
  real(8), save :: xap_hmc_heatf_xee = 0.d0
  real(8), save :: xap_hmc_heatf_xpx = 0.d0
  real(8), save :: xap_hmc_heatf_htfreef = 0.d0
  real(8), save :: xap_hmc_heatf_cmp1 = 0.d0
  real(8), save :: xap_hmc_heatf_cmp2 = 0.d0
  real(8), save :: xap_hmc_heatf_httot_before = 0.d0
  real(8), save :: xap_hmc_heatf_cltot_before = 0.d0
  real(8), save :: xap_hmc_heatf_httot2_before = 0.d0
  real(8), save :: xap_hmc_heatf_cltot2_before = 0.d0
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
  call xap_read_int_env('XSTAR_ATOMIC_HMC_TARGET_RECORD', &
       xap_hmc_target_record)
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

subroutine xap_hmc_comp2(t4, xee, xpx, ncn2, epi, bremsa, cmp1, cmp2)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: ncn2
  real(8), intent(in) :: t4, xee, xpx, epi(*), bremsa(*), cmp1, cmp2
  integer :: lun, ios, idx
  logical :: exists
  real(8) :: ekt, xnx, htcomp, clcomp

  if (xap_hmc_capture .ne. 1) return
  ekt = t4*0.861707
  xnx = xpx*xee
  htcomp = cmp1*xnx*1.602176634e-12
  clcomp = ekt*cmp2*xnx*1.602176634e-12

  inquire(file='xstar_calc_hmc_all_comp2_summary_probe.csv', exist=exists)
  open(newunit=lun, file='xstar_calc_hmc_all_comp2_summary_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,ncn2,temperature_t4,electron_fraction_xee,'// &
      'hydrogen_density_cm3,ekt_ev,cmp1,cmp2,htcomp,clcomp'
    write(lun,9012) xap_hmc_current_call, ncn2, t4, xee, xpx, ekt, &
      cmp1, cmp2, htcomp, clcomp
    close(lun)
  endif

  inquire(file='xstar_calc_hmc_all_comp2_grid_probe.csv', exist=exists)
  open(newunit=lun, file='xstar_calc_hmc_all_comp2_grid_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,grid_index,ncn2,epi_eV,bremsa'
    do idx=1,ncn2
      write(lun,9013) xap_hmc_current_call, idx, ncn2, epi(idx), bremsa(idx)
    enddo
    close(lun)
  endif
9012 format(i12,',',i12,8(',',es26.16e3))
9013 format(i12,',',i12,',',i12,2(',',es26.16e3))
end subroutine xap_hmc_comp2

subroutine xap_hmc_freef_pre(t4, xee, xpx, ncn2, opakc)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: ncn2
  real(8), intent(in) :: t4, xee, xpx, opakc(*)
  integer :: idx, ios

  if (xap_hmc_capture .ne. 1) return
  if (allocated(xap_hmc_freef_opakc_before)) &
    deallocate(xap_hmc_freef_opakc_before)
  allocate(xap_hmc_freef_opakc_before(ncn2), stat=ios)
  if (ios .ne. 0) then
    xap_hmc_freef_ncn2 = 0
    return
  endif
  xap_hmc_freef_ncn2 = ncn2
  xap_hmc_freef_t4 = t4
  xap_hmc_freef_xee = xee
  xap_hmc_freef_xpx = xpx
  do idx=1,ncn2
    xap_hmc_freef_opakc_before(idx) = opakc(idx)
  enddo
end subroutine xap_hmc_freef_pre

subroutine xap_hmc_freef_bin(kk, ncn2, epi, bremsa, temp, gam, gau, &
    opaff, opakc_after, htfreef)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: kk, ncn2
  real(8), intent(in) :: epi, bremsa, temp, gam, gau
  real(8), intent(in) :: opaff, opakc_after, htfreef
  integer :: lun, ios
  logical :: exists
  real(8) :: opakc_before, ekt, t6, xnx, enz2, cc

  if (xap_hmc_capture .ne. 1) return
  if (.not. allocated(xap_hmc_freef_opakc_before)) return
  if (ncn2 .ne. xap_hmc_freef_ncn2) return
  if (kk .lt. 1 .or. kk .gt. ncn2) return
  opakc_before = xap_hmc_freef_opakc_before(kk)

  inquire(file='xstar_calc_hmc_all_freef_grid_probe.csv', exist=exists)
  open(newunit=lun, file='xstar_calc_hmc_all_freef_grid_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,grid_index,ncn2,epi_eV,bremsa,temp,gam,'// &
      'gau,opakc_before,opaff,opakc_after,cumulative_htfreef'
    write(lun,9015) xap_hmc_current_call, kk, ncn2, epi, bremsa, &
      temp, gam, gau, opakc_before, opaff, opakc_after, htfreef
    close(lun)
  endif

  if (kk .eq. ncn2) then
    ekt = xap_hmc_freef_t4*0.861707
    t6 = xap_hmc_freef_t4/100.
    xnx = xap_hmc_freef_xpx*xap_hmc_freef_xee
    enz2 = 1.4*xnx
    cc = 2.614e-37
    inquire(file='xstar_calc_hmc_all_freef_summary_probe.csv', exist=exists)
    open(newunit=lun, file='xstar_calc_hmc_all_freef_summary_probe.csv', &
         status='unknown', position='append', action='write', iostat=ios)
    if (ios .eq. 0) then
      if (.not. exists) write(lun,'(A)') &
        'calc_hmc_all_call_id,ncn2,temperature_t4,electron_fraction_xee,'// &
        'hydrogen_density_cm3,ekt_ev,t6,electron_density_cm3,enz2_cm3,'// &
        'cc,htfreef'
      write(lun,9014) xap_hmc_current_call, ncn2, xap_hmc_freef_t4, &
        xap_hmc_freef_xee, xap_hmc_freef_xpx, ekt, t6, xnx, enz2, cc, &
        htfreef
      close(lun)
    endif
  endif
9014 format(i12,',',i12,9(',',es26.16e3))
9015 format(i12,',',i12,',',i12,9(',',es26.16e3))
end subroutine xap_hmc_freef_bin

subroutine xap_hmc_bremem_pre(t4, xee, xpx, ncn2, opakc, brcems)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: ncn2
  real(8), intent(in) :: t4, xee, xpx, opakc(*), brcems(*)
  integer :: idx, ios1, ios2

  if (xap_hmc_capture .ne. 1) return
  if (allocated(xap_hmc_bremem_opakc_before)) &
    deallocate(xap_hmc_bremem_opakc_before)
  if (allocated(xap_hmc_bremem_brcems_before)) &
    deallocate(xap_hmc_bremem_brcems_before)
  allocate(xap_hmc_bremem_opakc_before(ncn2), stat=ios1)
  allocate(xap_hmc_bremem_brcems_before(ncn2), stat=ios2)
  if (ios1 .ne. 0 .or. ios2 .ne. 0) then
    xap_hmc_bremem_ncn2 = 0
    return
  endif
  xap_hmc_bremem_ncn2 = ncn2
  xap_hmc_bremem_t4 = t4
  xap_hmc_bremem_xee = xee
  xap_hmc_bremem_xpx = xpx
  do idx=1,ncn2
    xap_hmc_bremem_opakc_before(idx) = opakc(idx)
    xap_hmc_bremem_brcems_before(idx) = brcems(idx)
  enddo
end subroutine xap_hmc_bremem_pre

subroutine xap_hmc_bremem_bin(kk, ncn2, epi, temp, gam, gau, brtmp, &
    bbee, brcems_after, opakc_after)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: kk, ncn2
  real(8), intent(in) :: epi, temp, gam, gau, brtmp, bbee
  real(8), intent(in) :: brcems_after, opakc_after
  integer :: lun, ios
  logical :: exists
  real(8) :: brcems_before, opakc_before, ekt, t6, xnx, enz2, cc, zz

  if (xap_hmc_capture .ne. 1) return
  if (.not. allocated(xap_hmc_bremem_opakc_before)) return
  if (.not. allocated(xap_hmc_bremem_brcems_before)) return
  if (ncn2 .ne. xap_hmc_bremem_ncn2) return
  if (kk .lt. 1 .or. kk .gt. ncn2) return
  opakc_before = xap_hmc_bremem_opakc_before(kk)
  brcems_before = xap_hmc_bremem_brcems_before(kk)

  inquire(file='xstar_calc_hmc_all_bremem_grid_probe.csv', exist=exists)
  open(newunit=lun, file='xstar_calc_hmc_all_bremem_grid_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,grid_index,ncn2,epi_eV,temp,gam,gau,'// &
      'brcems_before,brtmp,brcems_after,bbee,opakc_before,opakc_after'
    write(lun,9017) xap_hmc_current_call, kk, ncn2, epi, temp, gam, gau, &
      brcems_before, brtmp, brcems_after, bbee, opakc_before, opakc_after
    close(lun)
  endif

  if (kk .eq. ncn2) then
    ekt = xap_hmc_bremem_t4*0.861707
    t6 = xap_hmc_bremem_t4/100.
    xnx = xap_hmc_bremem_xpx*xap_hmc_bremem_xee
    enz2 = 1.4*xnx
    cc = 1.032e-13
    zz = 1.
    inquire(file='xstar_calc_hmc_all_bremem_summary_probe.csv', exist=exists)
    open(newunit=lun, file='xstar_calc_hmc_all_bremem_summary_probe.csv', &
         status='unknown', position='append', action='write', iostat=ios)
    if (ios .eq. 0) then
      if (.not. exists) write(lun,'(A)') &
        'calc_hmc_all_call_id,ncn2,temperature_t4,electron_fraction_xee,'// &
        'hydrogen_density_cm3,ekt_ev,t6,electron_density_cm3,enz2_cm3,'// &
        'cc,ion_charge'
      write(lun,9016) xap_hmc_current_call, ncn2, xap_hmc_bremem_t4, &
        xap_hmc_bremem_xee, xap_hmc_bremem_xpx, ekt, t6, xnx, enz2, &
        cc, zz
      close(lun)
    endif
  endif
9016 format(i12,',',i12,9(',',es26.16e3))
9017 format(i12,',',i12,',',i12,10(',',es26.16e3))
end subroutine xap_hmc_bremem_bin

subroutine xap_hmc_heatf_pre(t4, r, delr, xee, xpx, ncn2, htfreef, &
    cmp1, cmp2, httot, cltot, httot2, cltot2)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: ncn2
  real(8), intent(in) :: t4, r, delr, xee, xpx, htfreef
  real(8), intent(in) :: cmp1, cmp2, httot, cltot, httot2, cltot2

  if (xap_hmc_capture .ne. 1) return
  xap_hmc_heatf_ncn2 = ncn2
  xap_hmc_heatf_t4 = t4
  xap_hmc_heatf_r = r
  xap_hmc_heatf_delr = delr
  xap_hmc_heatf_xee = xee
  xap_hmc_heatf_xpx = xpx
  xap_hmc_heatf_htfreef = htfreef
  xap_hmc_heatf_cmp1 = cmp1
  xap_hmc_heatf_cmp2 = cmp2
  xap_hmc_heatf_httot_before = httot
  xap_hmc_heatf_cltot_before = cltot
  xap_hmc_heatf_httot2_before = httot2
  xap_hmc_heatf_cltot2_before = cltot2
end subroutine xap_hmc_heatf_pre

subroutine xap_hmc_heatf_bin(kl, ncn2, epi, brcems, tmp2o, tmp2, clbrems)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: kl, ncn2
  real(8), intent(in) :: epi, brcems, tmp2o, tmp2, clbrems
  integer :: lun, ios
  logical :: exists

  if (xap_hmc_capture .ne. 1) return
  if (ncn2 .ne. xap_hmc_heatf_ncn2) return
  if (kl .lt. 1 .or. kl .gt. ncn2) return
  inquire(file='xstar_calc_hmc_all_heatf_grid_probe.csv', exist=exists)
  open(newunit=lun, file='xstar_calc_hmc_all_heatf_grid_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,grid_index,ncn2,epi_eV,brcems,'// &
      'previous_brcems,current_brcems,cumulative_clbrems'
    write(lun,9019) xap_hmc_current_call, kl, ncn2, epi, brcems, &
      tmp2o, tmp2, clbrems
    close(lun)
  endif
9019 format(i12,',',i12,',',i12,5(',',es26.16e3))
end subroutine xap_hmc_heatf_bin

subroutine xap_hmc_heatf_post(ncn2, httot, cltot, httot2, cltot2, &
    hmctot, htcomp, clcomp, clbrems)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: ncn2
  real(8), intent(in) :: httot, cltot, httot2, cltot2
  real(8), intent(in) :: hmctot, htcomp, clcomp, clbrems
  integer :: lun, ios
  logical :: exists
  real(8) :: xnx, ekt

  if (xap_hmc_capture .ne. 1) return
  if (ncn2 .ne. xap_hmc_heatf_ncn2) return
  xnx = xap_hmc_heatf_xpx*xap_hmc_heatf_xee
  ekt = xap_hmc_heatf_t4*0.861707
  inquire(file='xstar_calc_hmc_all_heatf_summary_probe.csv', exist=exists)
  open(newunit=lun, file='xstar_calc_hmc_all_heatf_summary_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,ncn2,temperature_t4,radius_cm,'// &
      'zone_thickness_cm,electron_fraction_xee,hydrogen_density_cm3,'// &
      'electron_density_cm3,ekt_ev,htfreef,cmp1,cmp2,httot_before,'// &
      'cltot_before,httot2_before,cltot2_before,htcomp,clcomp,clbrems,'// &
      'httot_after,cltot_after,httot2_after,cltot2_after,hmctot'
    write(lun,9018) xap_hmc_current_call, ncn2, xap_hmc_heatf_t4, &
      xap_hmc_heatf_r, xap_hmc_heatf_delr, xap_hmc_heatf_xee, &
      xap_hmc_heatf_xpx, xnx, ekt, xap_hmc_heatf_htfreef, &
      xap_hmc_heatf_cmp1, xap_hmc_heatf_cmp2, &
      xap_hmc_heatf_httot_before, xap_hmc_heatf_cltot_before, &
      xap_hmc_heatf_httot2_before, xap_hmc_heatf_cltot2_before, &
      htcomp, clcomp, clbrems, httot, cltot, httot2, cltot2, hmctot
    close(lun)
  endif
9018 format(i12,',',i12,22(',',es26.16e3))
end subroutine xap_hmc_heatf_post

subroutine xap_hmc_final_state(t4, xee, xpx, enelec, elcter, htfreef, &
    cmp1, cmp2, htcomp, clcomp, clbrems, httot, cltot, httot2, cltot2, &
    hmctot)
  use xap_calc_hmc_probe_state
  implicit none
  real(8), intent(in) :: t4, xee, xpx, enelec, elcter, htfreef
  real(8), intent(in) :: cmp1, cmp2, htcomp, clcomp, clbrems
  real(8), intent(in) :: httot, cltot, httot2, cltot2, hmctot
  integer :: lun, ios
  logical :: exists
  real(8) :: xnx

  if (xap_hmc_capture .ne. 1) return
  xnx = xpx*xee
  inquire(file='xstar_calc_hmc_all_final_state_probe.csv', exist=exists)
  open(newunit=lun, file='xstar_calc_hmc_all_final_state_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,temperature_t4,temperature_k,'// &
    'electron_fraction_xee,hydrogen_density_cm3,electron_density_cm3,'// &
    'enelec,elcter,htfreef,cmp1,cmp2,htcomp,clcomp,clbrems,httot,cltot,'// &
    'httot2,cltot2,hmctot'
  write(lun,9020) xap_hmc_current_call, t4, 1.d4*t4, xee, xpx, xnx, &
    enelec, elcter, htfreef, cmp1, cmp2, htcomp, clcomp, clbrems, &
    httot, cltot, httot2, cltot2, hmctot
  close(lun)
9020 format(i12,18(',',es26.16e3))
end subroutine xap_hmc_final_state

subroutine xap_hmce_pre_matrix(element_z, nnz, pirt, rrrt, xitp, &
                               mml, mmu, critf)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: element_z, nnz, mml, mmu
  real(8), intent(in) :: pirt(*), rrrt(*), xitp(*), critf
  integer :: lun, ios, stage
  logical :: exists

  if (xap_hmc_capture .ne. 1) return
  if (xap_hmc_target_element .gt. 0 .and. element_z .ne. xap_hmc_target_element) return
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
  if (xap_hmc_target_element .gt. 0 .and. element_z .ne. xap_hmc_target_element) return

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

  ! Capture the complete source input vector.  Matrix terms do not
  ! necessarily touch every compact row, so row/column population columns in
  ! the term file are insufficient to reconstruct xileve exactly.
  inquire(file='xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv', &
          exist=exists)
  open(newunit=lun, &
       file='xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,element_index,element_z,compact_dimension,'// &
      'compact_index,population'
    do ll=1,ipmat
      write(lun,9011) xap_hmc_current_call, element_index, element_z, &
        ipmat, ll, x(ll)
    enddo
    close(lun)
  endif
9006 format(11(i12,','),5(es26.16e3,','),es26.16e3)
9011 format(5(i12,','),es26.16e3)
end subroutine xap_hmc_matrix_terms

subroutine xap_hmc_msolvelucy_final_snapshot(ipmat, nindb, ajisb, &
    cjisb, cjisb2, indb, ltpsv, x, xo, nsup, nion, niter, nit2, nit3, &
    diff, diff2)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: ipmat, nindb, niter, nit2, nit3
  real(8), intent(in) :: ajisb(2,*), cjisb(*), cjisb2(*), x(*), xo(*)
  real(8), intent(in) :: diff, diff2
  integer, intent(in) :: indb(2,*), ltpsv(*), nsup(*), nion(*)
  integer :: lun, ios, ll, mm, row_raw, column_raw
  integer :: row_compact, column_compact
  logical :: exists

  if (xap_hmc_capture .ne. 1) return
  if (xap_hmc_target_element .gt. 0 .and. &
      xap_hmc_current_element_z .ne. xap_hmc_target_element) return

  inquire(file='xstar_calc_hmc_all_msolvelucy_final_matrix_probe.csv', &
          exist=exists)
  open(newunit=lun, &
       file='xstar_calc_hmc_all_msolvelucy_final_matrix_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,element_index,element_z,outer_iteration,'// &
      'fixed_iteration,global_fixed_iteration,final_outer_difference,'// &
      'final_fixed_difference,compact_dimension,n_matrix_terms,'// &
      'term_index,source_record,row_raw,column_raw,row_compact,'// &
      'column_compact,operator_coefficient,aj1,aj2,cj,cj2,'// &
      'row_population,column_population,row_outer_start_population,'// &
      'column_outer_start_population'
    do ll=1,nindb
      row_raw=indb(1,ll)
      column_raw=indb(2,ll)
      row_compact=min(ipmat,row_raw)
      column_compact=min(ipmat,column_raw)
      write(lun,9008) xap_hmc_current_call, &
        xap_hmc_current_element_index, xap_hmc_current_element_z, &
        niter, nit2, nit3, diff, diff2, ipmat, nindb, ll, ltpsv(ll), &
        row_raw, column_raw, row_compact, column_compact, &
        ajisb(1,ll), ajisb(1,ll), ajisb(2,ll), cjisb(ll), cjisb2(ll), &
        x(row_compact), x(column_compact), xo(row_compact), &
        xo(column_compact)
    enddo
    close(lun)
  endif

  inquire(file='xstar_calc_hmc_all_msolvelucy_final_population_probe.csv', &
          exist=exists)
  open(newunit=lun, &
       file='xstar_calc_hmc_all_msolvelucy_final_population_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .eq. 0) then
    if (.not. exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,element_index,element_z,outer_iteration,'// &
      'fixed_iteration,global_fixed_iteration,compact_dimension,'// &
      'compact_index,population,final_outer_start_population,'// &
      'superlevel,ion_counter,'// &
      'final_outer_difference,final_fixed_difference'
    do mm=1,ipmat
      write(lun,9009) xap_hmc_current_call, &
        xap_hmc_current_element_index, xap_hmc_current_element_z, &
        niter, nit2, nit3, ipmat, mm, x(mm), xo(mm), nsup(mm), &
        nion(mm), diff, diff2
    enddo
    close(lun)
  endif

9008 format(6(i12,','),2(es26.16e3,','),8(i12,','),8(es26.16e3,','), &
            es26.16e3)
9009 format(8(i12,','),2(es26.16e3,','),2(i12,','),es26.16e3,',', &
            es26.16e3)
end subroutine xap_hmc_msolvelucy_final_snapshot

subroutine xap_hmc_leveltemp_energy(element_z, ion_stage, ion_index, &
    record, data_type, rate_type, nlev, idest1, idest2, e1, e2, ans1, &
    ans2, ans3, ans4, ans5, ans6)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: element_z, ion_stage, ion_index, record
  integer, intent(in) :: data_type, rate_type, nlev, idest1, idest2
  real(8), intent(in) :: e1, e2, ans1, ans2, ans3, ans4, ans5, ans6
  integer :: lun, ios
  logical :: exists

  if (xap_hmc_capture .ne. 1) return
  if (xap_hmc_target_element .gt. 0 .and. element_z .ne. xap_hmc_target_element) return
  if (rate_type .ne. 7) return
  if (.not. (data_type .eq. 49 .or. data_type .eq. 53 .or. &
             data_type .eq. 99)) return
  if (xap_hmc_target_record .gt. 0 .and. &
      record .ne. xap_hmc_target_record) return

  inquire(file='xstar_calc_hmc_all_leveltemp_energy_probe.csv', &
          exist=exists)
  open(newunit=lun, &
       file='xstar_calc_hmc_all_leveltemp_energy_probe.csv', &
       status='unknown', position='append', action='write', iostat=ios)
  if (ios .ne. 0) return
  if (.not. exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,element_z,ion_stage,ion_index,record,'// &
    'data_type,rate_type,nlev,idest1,idest2,leveltemp_e1_ev,'// &
    'leveltemp_e2_ev,ans1,ans2,ans3,ans4,ans5,ans6'
  write(lun,9010) xap_hmc_current_call, element_z, ion_stage, &
    ion_index, record, data_type, rate_type, nlev, idest1, idest2, &
    e1, e2, ans1, ans2, ans3, ans4, ans5, ans6
  close(lun)
9010 format(10(i12,','),7(es26.16e3,','),es26.16e3)
end subroutine xap_hmc_leveltemp_energy

subroutine xap_hmc_thermal_families(ntyp_local, rntpsv, rltpsv)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: ntyp_local
  real(8), intent(in) :: rntpsv(ntyp_local,4), rltpsv(ntyp_local,4)
  integer :: lun, ios, idx
  logical :: exists
  real(8) :: scale

  if (xap_hmc_capture .ne. 1) return
  if (xap_hmc_target_element .gt. 0 .and. &
      xap_hmc_current_element_z .ne. xap_hmc_target_element) return

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
        "calc_hmc_ion_leveltemp_energy": """! Insert immediately after call ucalc and before rates(1,ml_data)=ans1.
            if ((lrtyp.eq.7).and.((ltyp.eq.49).or.(ltyp.eq.53).or.   &
     &          (ltyp.eq.99)).and.(idest1.gt.0).and.(idest2.gt.0))  &
     &        call xap_hmc_leveltemp_energy(nnzz,nnzz-nnnn+1,       &
     &          jkk_ion,ml_data,ltyp,lrtyp,nlev,idest1,idest2,      &
     &          leveltemp%rlev(1,idest1),leveltemp%rlev(1,idest2),  &
     &          ans1,ans2,ans3,ans4,ans5,ans6)
""",
        "calc_hmc_element_matrix_terms": """! Insert immediately before call msolvelucy in calc_hmc_element.
      call xap_hmc_matrix_terms(jk,nnz,ipmat2,nindbe,ajise,cjise,    &
     &     cjise2,indbe,ltpsve,x)
""",
        "msolvelucy_final_snapshot": """! Insert after the outer Lucy loop enddo and before heating-cooling accumulation.
      call xap_hmc_msolvelucy_final_snapshot(ipmat,nindb,ajisb,      &
     &     cjisb,cjisb2,indb,ltpsv,x,xo,nsup,nion,niter,nit2,nit3,  &
     &     diff,diff2)
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
        "calc_hmc_all_comp2": """! Insert immediately after call comp2 and before call freef.
      call xap_hmc_comp2(t,xee,xpx,ncn2,epi,bremsa,cmp1,cmp2)
""",
        "calc_hmc_all_freef_pre": """! Insert immediately before call freef.
      call xap_hmc_freef_pre(t,xee,xpx,ncn2,opakc)
""",
        "freef_bin": """! Insert in freef after opakc(kk)=opakc(kk)+opaff and before enddo.
         call xap_hmc_freef_bin(kk,numcon,epi(kk),bremsa(kk),temp,    &
     &        gam,gau,opaff,opakc(kk),htfreef)
""",
        "calc_hmc_all_bremem_pre": """! Insert immediately after call freef and before call bremem.
      call xap_hmc_bremem_pre(t,xee,xpx,ncn2,opakc,brcems)
""",
        "bremem_bin": """! Insert in bremem after bbee=0. and before the lpri print block.
         call xap_hmc_bremem_bin(kk,numcon,epi(kk),temp,gam,gau,     &
     &        brtmp,bbee,brcems(kk),opakc(kk))
""",
        "calc_hmc_all_heatf_pre": """! Insert immediately after call bremem and before call heatf.
      call xap_hmc_heatf_pre(t,r,delr,xee,xpx,ncn2,htfreef,cmp1,    &
     &     cmp2,httot,cltot,httot2,cltot2)
""",
        "heatf_bin": """! Insert in heatf inside the clbrems loop immediately before enddo.
        call xap_hmc_heatf_bin(kl,numcon,epi(kl),brcems(kl),tmp2o,  &
     &       tmp2,clbrems)
""",
        "calc_hmc_all_heatf_post": """! Insert immediately after call heatf.
      call xap_hmc_heatf_post(ncn2,httot,cltot,httot2,cltot2,      &
     &     hmctot,htcomp,clcomp,clbrems)
""",
        "calc_hmc_all_final_state": """! Insert after the heatf post probe and before the final lpri block.
      call xap_hmc_final_state(t,xee,xpx,enelec,elcter,htfreef,    &
     &     cmp1,cmp2,htcomp,clcomp,clbrems,httot,cltot,httot2,    &
     &     cltot2,hmctot)
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
        "# Bounded XSTAR complete fixed-state `calc_hmc_all` probe\n\n"
        "This diagnostic instrumentation captures the source first pass and "
        "the pre-continuum element state, exact same-call Compton, free-free, bremsstrahlung, and heatf inputs/outputs, and the final thermal/charge return state; it never changes rates, populations, or continuum state.\n\n"
        "1. Add `xstar_atomic_calc_hmc_all_probe_helpers.f90` before "
        "`freef.f90`, `bremem.f90`, `heatf.f90`, `calc_hmc_ion.f90`, `calc_hmc_element.f90`, `msolvelucy.f90`, and `calc_hmc_all.f90` "
        "in the XSTAR build source list.\n"
        "2. Apply the seventeen insertion snippets at their documented locations.\n"
        "3. Delete prior `xstar_calc_hmc_*_probe.csv` files before the run.\n"
        "4. By default the helper captures the call at `T=76655.18557758832 K`, "
        "`xpx=1e8 cm^-3`, `xee=1.2046560563936872`, and element Z=8.\n"
        "5. To select by call number, set `XSTAR_ATOMIC_HMC_TARGET_CALL`. "
        "Set `XSTAR_ATOMIC_HMC_TARGET_ELEMENT=0` to capture detailed products "
        "for every positive-abundance element in the selected call. Other "
        "controls are `_T4`, `_XEE`, "
        "`_XPX`, `_RTOL`, and `_ATOL`.\n\n"
        "Outputs:\n\n"
        "- `xstar_calc_hmc_element_pre_matrix_probe.csv`\n"
        "- `xstar_calc_hmc_all_pre_continuum_summary_probe.csv`\n"
        "- `xstar_calc_hmc_all_pre_continuum_ions_probe.csv`\n"
        "- `xstar_calc_hmc_all_pre_continuum_levels_probe.csv`\n"
        "- `xstar_calc_hmc_all_pre_continuum_elements_probe.csv`\n"
        "- `xstar_calc_hmc_all_comp2_summary_probe.csv`\n"
        "- `xstar_calc_hmc_all_comp2_grid_probe.csv`\n"
        "- `xstar_calc_hmc_all_freef_summary_probe.csv`\n"
        "- `xstar_calc_hmc_all_freef_grid_probe.csv`\n"
        "- `xstar_calc_hmc_all_bremem_summary_probe.csv`\n"
        "- `xstar_calc_hmc_all_bremem_grid_probe.csv`\n"
        "- `xstar_calc_hmc_all_heatf_summary_probe.csv`\n"
        "- `xstar_calc_hmc_all_heatf_grid_probe.csv`\n"
        "- `xstar_calc_hmc_all_final_state_probe.csv`\n"
        "- `xstar_calc_hmc_all_matrix_terms_probe.csv`\n"
        "- `xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv`\n"
        "- `xstar_calc_hmc_all_leveltemp_energy_probe.csv`\n"
        "- `xstar_calc_hmc_all_msolvelucy_final_matrix_probe.csv`\n"
        "- `xstar_calc_hmc_all_msolvelucy_final_population_probe.csv`\n"
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
