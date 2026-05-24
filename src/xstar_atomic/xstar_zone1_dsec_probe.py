"""Diagnostic-only original-XSTAR probe bundle for complete zone-1 DSEC.

The generated helpers add observations only.  They do not alter XSTAR rates,
populations, work arrays, root-finder branches, or tolerances.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

from .xstar_calc_hmc_all_probe import write_calc_hmc_all_probe_products
from .xstar_dsec_probe import write_dsec_probe_products


def zone1_extra_helper() -> str:
    return r'''! xstar-atomic v0.4.79 bounded zone-1 DSEC/type-15 detail probe.
!
! Diagnostic only.  No caller-owned value is modified.
module xap_zone1_preliminary_rate_state
  implicit none
  integer, save :: xap_zone1_preliminary_active = 0
  integer, save :: xap_zone1_preliminary_element_z = 0
  integer, save :: xap_zone1_preliminary_ion_stage = 0
  integer, save :: xap_zone1_preliminary_record = 0
contains
  subroutine xap_zone1_set_preliminary_rate(element_z,ion_stage,record)
    integer,intent(in) :: element_z,ion_stage,record
    xap_zone1_preliminary_element_z = element_z
    xap_zone1_preliminary_ion_stage = ion_stage
    xap_zone1_preliminary_record = record
    xap_zone1_preliminary_active = 1
  end subroutine xap_zone1_set_preliminary_rate

  subroutine xap_zone1_clear_preliminary_rate()
    xap_zone1_preliminary_active = 0
    xap_zone1_preliminary_element_z = 0
    xap_zone1_preliminary_ion_stage = 0
    xap_zone1_preliminary_record = 0
  end subroutine xap_zone1_clear_preliminary_rate
end module xap_zone1_preliminary_rate_state

subroutine xap_zone1_entry_arrays(nelem,abel,mml,mmu,nlevel,klev)
  use xap_calc_hmc_probe_state
  implicit none
  integer, intent(in) :: nelem,nlevel,mml(*),mmu(*)
  real(8), intent(in) :: abel(*)
  character(1), intent(in) :: klev(100,*)
  integer :: lun,ios,idx,slot
  logical :: exists
  character(len=100) :: label
  if (xap_hmc_capture .ne. 1) return
  inquire(file='xstar_zone1_calc_hmc_all_input_elements_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_calc_hmc_all_input_elements_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.eq.0) then
    if (.not.exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,element_index,abundance,mml,mmu'
    do idx=1,nelem
      write(lun,9001) xap_hmc_current_call,idx,abel(idx),mml(idx),mmu(idx)
    enddo
    close(lun)
  endif
  inquire(file='xstar_zone1_calc_hmc_all_input_klev_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_calc_hmc_all_input_klev_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.eq.0) then
    if (.not.exists) write(lun,'(A)') &
      'calc_hmc_all_call_id,column_index,klev_hex'
    do idx=1,nlevel
      label=''
      do slot=1,100
        label(slot:slot)=klev(slot,idx)
      enddo
      write(lun,'(i12,",",i12,",",100(z2.2))') &
        xap_hmc_current_call,idx,(iachar(label(slot:slot)),slot=1,100)
    enddo
    close(lun)
  endif
9001 format(i12,',',i12,',',es26.16e3,',',i12,',',i12)
end subroutine xap_zone1_entry_arrays

subroutine xap_zone1_rate_record(element_z,ion_stage,ion_index,nlev,record, &
    data_type,rate_type,idest1,idest2,lower_endpoint,upper_endpoint, &
    ptmp1,ptmp2,xpx,ans1,ans2,ans3,ans4,ans5,ans6)
  use xap_calc_hmc_probe_state
  implicit none
  integer,intent(in) :: element_z,ion_stage,ion_index,nlev,record
  integer,intent(in) :: data_type,rate_type,idest1,idest2
  integer,intent(in) :: lower_endpoint,upper_endpoint
  real(8),intent(in) :: ptmp1,ptmp2,xpx,ans1,ans2,ans3,ans4,ans5,ans6
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  if (xap_hmc_target_element.gt.0 .and. element_z.ne.xap_hmc_target_element) return
  inquire(file='xstar_zone1_calc_hmc_all_rate_records_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_calc_hmc_all_rate_records_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) return
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,element_z,ion_stage,ion_index,nlev,record,'// &
    'data_type,rate_type,idest1,idest2,lower_endpoint,upper_endpoint,'// &
    'escape_factor_in,escape_factor_out,density_scale,ans1,ans2,ans3,'// &
    'ans4,ans5,ans6,forward_diag_cj,forward_diag_cj2,'// &
    'reverse_diag_cj,reverse_diag_cj2'
  write(lun,9002) xap_hmc_current_call,element_z,ion_stage,ion_index,nlev, &
    record,data_type,rate_type,idest1,idest2,lower_endpoint,upper_endpoint, &
    ptmp1,ptmp2,xpx,ans1,ans2,ans3,ans4,ans5,ans6,ans4*xpx,ans6*xpx, &
    -ans3*xpx,-ans5*xpx
  close(lun)
9002 format(12(i12,','),12(es26.16e3,','),es26.16e3)
end subroutine xap_zone1_rate_record

subroutine xap_zone1_second_pass_rate(element_z,ion_stage,ion_index,pirt,rrrt)
  use xap_calc_hmc_probe_state
  implicit none
  integer,intent(in) :: element_z,ion_stage,ion_index
  real(8),intent(in) :: pirt,rrrt
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  if (xap_hmc_target_element.gt.0 .and. element_z.ne.xap_hmc_target_element) return
  inquire(file='xstar_zone1_calc_hmc_all_second_pass_rates_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_calc_hmc_all_second_pass_rates_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) return
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,element_z,ion_stage,ion_index,pirt,rrrt'
  write(lun,9003) xap_hmc_current_call,element_z,ion_stage,ion_index,pirt,rrrt
  close(lun)
9003 format(4(i12,','),es26.16e3,',',es26.16e3)
end subroutine xap_zone1_second_pass_rate

subroutine xap_zone1_thermal_term(term_index,record,row_index,column_index, &
    data_type,rate_type,population,cj,cj2)
  use xap_calc_hmc_probe_state
  implicit none
  integer,intent(in) :: term_index,record,row_index,column_index
  integer,intent(in) :: data_type,rate_type
  real(8),intent(in) :: population,cj,cj2
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  if (xap_hmc_target_element.gt.0 .and. &
      xap_hmc_current_element_z.ne.xap_hmc_target_element) return
  inquire(file='xstar_zone1_calc_hmc_all_thermal_terms_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_calc_hmc_all_thermal_terms_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) return
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,element_index,element_z,term_index,record,'// &
    'row,column,data_type,rate_type,population,cj,cj2,'// &
    'cooling_contribution,cooling2_contribution'
  write(lun,9004) xap_hmc_current_call,xap_hmc_current_element_index, &
    xap_hmc_current_element_z,term_index,record,row_index,column_index, &
    data_type,rate_type,population,cj,cj2,population*cj,population*cj2
  close(lun)
9004 format(9(i12,','),4(es26.16e3,','),es26.16e3)
end subroutine xap_zone1_thermal_term

subroutine xap_zone1_begin_calc_ion_rate_record(element_z,ion_stage,record)
  use xap_calc_hmc_probe_state
  use xap_zone1_preliminary_rate_state
  implicit none
  integer,intent(in) :: element_z,ion_stage,record
  if (xap_hmc_capture.ne.1) then
    call xap_zone1_clear_preliminary_rate()
    return
  endif
  if (element_z.eq.6 .and. ion_stage.eq.4) then
    call xap_zone1_set_preliminary_rate(element_z,ion_stage,record)
  else
    call xap_zone1_clear_preliminary_rate()
  endif
end subroutine xap_zone1_begin_calc_ion_rate_record

subroutine xap_zone1_type15_shell(record,parent_record,parent_threshold, &
    n_shells,shell_index,shell_threshold,shell_d,is_final)
  use xap_calc_hmc_probe_state
  use xap_zone1_preliminary_rate_state
  implicit none
  integer,intent(in) :: record,parent_record,n_shells,shell_index,is_final
  real(8),intent(in) :: parent_threshold,shell_threshold,shell_d
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  if (xap_zone1_preliminary_active.ne.1) return
  if (xap_zone1_preliminary_element_z.ne.6 .or. &
      xap_zone1_preliminary_ion_stage.ne.4) return
  if (record.ne.xap_zone1_preliminary_record) return
  inquire(file='xstar_zone1_type15_shell_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_type15_shell_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) return
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,record,parent_record,parent_threshold_ev,'// &
    'n_shells,shell_index,shell_threshold_ev,shell_d,is_final'
  write(lun,9005) xap_hmc_current_call,record,parent_record,parent_threshold, &
    n_shells,shell_index,shell_threshold,shell_d,is_final
  close(lun)
9005 format(3(i12,','),es26.16e3,',',2(i12,','),2(es26.16e3,','),i12)
end subroutine xap_zone1_type15_shell

subroutine xap_zone1_type15_effective(record,parent_record,phase, &
    effective_threshold,effective_d)
  use xap_calc_hmc_probe_state
  use xap_zone1_preliminary_rate_state
  implicit none
  integer,intent(in) :: record,parent_record,phase
  real(8),intent(in) :: effective_threshold,effective_d
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  if (xap_zone1_preliminary_active.ne.1) return
  if (xap_zone1_preliminary_element_z.ne.6 .or. &
      xap_zone1_preliminary_ion_stage.ne.4) return
  if (record.ne.xap_zone1_preliminary_record) return
  inquire(file='xstar_zone1_type15_effective_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_type15_effective_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) return
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,record,parent_record,phase,'// &
    'effective_threshold_ev,effective_d'
  write(lun,9009) xap_hmc_current_call,record,parent_record,phase, &
    effective_threshold,effective_d
  close(lun)
9009 format(4(i12,','),es26.16e3,',',es26.16e3)
end subroutine xap_zone1_type15_effective

subroutine xap_zone1_calc_ion_rate_record(element_z,ion_stage,ion_index, &
    record,data_type,rate_type,parent_record,parent_threshold, &
    ans1,ans2,ans3,ans4,ans5,ans6,pirti_before,pirti_contribution, &
    pirti_after,rrrti_before,rrrti_contribution,rrrti_after,idest1,idest2)
  use xap_calc_hmc_probe_state
  use xap_zone1_preliminary_rate_state
  implicit none
  integer,intent(in) :: element_z,ion_stage,ion_index,record,data_type
  integer,intent(in) :: rate_type,parent_record,idest1,idest2
  real(8),intent(in) :: parent_threshold,ans1,ans2,ans3,ans4,ans5,ans6
  real(8),intent(in) :: pirti_before,pirti_contribution,pirti_after
  real(8),intent(in) :: rrrti_before,rrrti_contribution,rrrti_after
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) then
    call xap_zone1_clear_preliminary_rate()
    return
  endif
  if (element_z.ne.6 .or. ion_stage.ne.4) then
    call xap_zone1_clear_preliminary_rate()
    return
  endif
  inquire(file='xstar_zone1_civ_calc_ion_rates_records_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_civ_calc_ion_rates_records_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) then
    call xap_zone1_clear_preliminary_rate()
    return
  endif
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,element_z,ion_stage,ion_index,record,data_type,'// &
    'rate_type,parent_record,parent_threshold_ev,ans1,ans2,ans3,ans4,'// &
    'ans5,ans6,pirti_before,pirti_contribution,pirti_after,rrrti_before,'// &
    'rrrti_contribution,rrrti_after,idest1,idest2'
  write(lun,9006) xap_hmc_current_call,element_z,ion_stage,ion_index,record, &
    data_type,rate_type,parent_record,parent_threshold,ans1,ans2,ans3,ans4, &
    ans5,ans6,pirti_before,pirti_contribution,pirti_after,rrrti_before, &
    rrrti_contribution,rrrti_after,idest1,idest2
  close(lun)
  call xap_zone1_clear_preliminary_rate()
9006 format(8(i12,','),13(es26.16e3,','),i12,',',i12)
end subroutine xap_zone1_calc_ion_rate_record

subroutine xap_zone1_normalization_row(outer_iteration,nspmx,nspcon, &
    ajissup,bmatsup)
  use xap_calc_hmc_probe_state
  use globaldata, only: ndss
  implicit none
  integer,intent(in) :: outer_iteration,nspmx,nspcon
  real(8),intent(in) :: ajissup(ndss,*),bmatsup(*)
  integer :: lun,ios,column
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  if (xap_hmc_target_element.gt.0 .and. &
      xap_hmc_current_element_z.ne.xap_hmc_target_element) return
  inquire(file='xstar_zone1_msolvelucy_normalization_row_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_msolvelucy_normalization_row_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) return
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,element_index,element_z,outer_iteration,'// &
    'condensed_dimension,normalization_row,column,matrix_value,rhs_value'
  do column=1,nspmx
    write(lun,9007) xap_hmc_current_call,xap_hmc_current_element_index, &
      xap_hmc_current_element_z,outer_iteration,nspmx,nspcon,column, &
      ajissup(nspcon,column),bmatsup(nspcon)
  enddo
  close(lun)
9007 format(7(i12,','),es26.16e3,',',es26.16e3)
end subroutine xap_zone1_normalization_row

subroutine xap_zone1_level_population(element_z,ion_stage,ion_index, &
    local_level,compact_index,population)
  use xap_calc_hmc_probe_state
  implicit none
  integer,intent(in) :: element_z,ion_stage,ion_index,local_level
  integer,intent(in) :: compact_index
  real(8),intent(in) :: population
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  if (element_z.ne.6) return
  inquire(file='xstar_zone1_carbon_level_population_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_carbon_level_population_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) return
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,element_z,ion_stage,ion_index,local_level,'// &
    'compact_index,population'
  write(lun,9008) xap_hmc_current_call,element_z,ion_stage,ion_index, &
    local_level,compact_index,population
  close(lun)
9008 format(6(i12,','),es26.16e3)
end subroutine xap_zone1_level_population

! ----------------------------------------------------------------------
! xstar-atomic v0.4.87 diagnostic-only source-order state-path build hotfix.
! These routines observe caller-owned values and never modify production
! rates, matrices, populations, or solver control.

module xap_zone1_alias_probe_state
  implicit none
  integer, save :: xap_alias_valid = 0
  integer, save :: xap_alias_ion_index = 0
  integer, save :: xap_alias_ion_stage = 0
  integer, save :: xap_alias_local_level = 0
  integer, save :: xap_alias_global_index = 0
  real(8), save :: xap_alias_population = 0.d0
end module xap_zone1_alias_probe_state

subroutine xap_zone1_alias_reset()
  use xap_zone1_alias_probe_state
  implicit none
  xap_alias_valid = 0
  xap_alias_ion_index = 0
  xap_alias_ion_stage = 0
  xap_alias_local_level = 0
  xap_alias_global_index = 0
  xap_alias_population = 0.d0
end subroutine xap_zone1_alias_reset

subroutine xap_zone1_hydrogen_state(xilevg1,abel1,xpx,xh0,xh1)
  use xap_calc_hmc_probe_state
  implicit none
  real(8),intent(in) :: xilevg1,abel1,xpx,xh0,xh1
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  inquire(file='xstar_zone1_hydrogen_state_path_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_hydrogen_state_path_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) return
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,xilevg1,abel1,xpx,xh0,xh1'
  write(lun,9101) xap_hmc_current_call,xilevg1,abel1,xpx,xh0,xh1
  close(lun)
9101 format(i12,5(',',es26.16e3))
end subroutine xap_zone1_hydrogen_state

subroutine xap_zone1_carbon_state_path(phase_code,outer_iteration, &
    fixed_iteration,compact_index,superlevel,ion_counter,ion_stage, &
    ion_index,local_level,global_index,full_element_index,population)
  use xap_calc_hmc_probe_state
  implicit none
  integer,intent(in) :: phase_code,outer_iteration,fixed_iteration
  integer,intent(in) :: compact_index,superlevel,ion_counter,ion_stage
  integer,intent(in) :: ion_index,local_level,global_index,full_element_index
  real(8),intent(in) :: population
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  if (xap_hmc_current_element_z.ne.6 .and. phase_code.ge.30) return
  inquire(file='xstar_zone1_carbon_state_path_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_carbon_state_path_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) return
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,phase_code,outer_iteration,fixed_iteration,'// &
    'compact_index,superlevel,ion_counter,ion_stage,ion_index,'// &
    'local_level,global_index,full_element_index,population'
  write(lun,9102) xap_hmc_current_call,phase_code,outer_iteration, &
    fixed_iteration,compact_index,superlevel,ion_counter,ion_stage, &
    ion_index,local_level,global_index,full_element_index,population
  close(lun)
9102 format(12(i12,','),es26.16e3)
end subroutine xap_zone1_carbon_state_path

subroutine xap_zone1_carbon_stage_total(phase_code,outer_iteration, &
    ion_counter,ion_stage,population_total)
  use xap_calc_hmc_probe_state
  implicit none
  integer,intent(in) :: phase_code,outer_iteration,ion_counter,ion_stage
  real(8),intent(in) :: population_total
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  if (xap_hmc_current_element_z.ne.6) return
  inquire(file='xstar_zone1_carbon_stage_totals_probe.csv',exist=exists)
  open(newunit=lun,file='xstar_zone1_carbon_stage_totals_probe.csv', &
       status='unknown',position='append',action='write',iostat=ios)
  if (ios.ne.0) return
  if (.not.exists) write(lun,'(A)') &
    'calc_hmc_all_call_id,phase_code,outer_iteration,ion_counter,'// &
    'ion_stage,population_total'
  write(lun,9103) xap_hmc_current_call,phase_code,outer_iteration, &
    ion_counter,ion_stage,population_total
  close(lun)
9103 format(5(i12,','),es26.16e3)
end subroutine xap_zone1_carbon_stage_total

subroutine xap_zone1_alias_candidate(ion_index,ion_stage,local_level,nlev, &
    global_index,population)
  use xap_calc_hmc_probe_state
  use xap_zone1_alias_probe_state
  implicit none
  integer,intent(in) :: ion_index,ion_stage,local_level,nlev,global_index
  real(8),intent(in) :: population
  integer :: lun,ios
  logical :: exists
  if (xap_hmc_capture.ne.1) return
  if (xap_hmc_current_element_z.ne.6) return
  if (local_level.eq.1 .and. xap_alias_valid.eq.1) then
    inquire(file='xstar_zone1_carbon_alias_boundaries_probe.csv',exist=exists)
    open(newunit=lun,file='xstar_zone1_carbon_alias_boundaries_probe.csv', &
         status='unknown',position='append',action='write',iostat=ios)
    if (ios.eq.0) then
      if (.not.exists) write(lun,'(A)') &
        'calc_hmc_all_call_id,lower_ion_index,lower_ion_stage,'// &
        'lower_local_level,lower_global_index,lower_population,'// &
        'upper_ion_index,upper_ion_stage,upper_local_level,'// &
        'upper_global_index,upper_population'
      write(lun,9104) xap_hmc_current_call,xap_alias_ion_index, &
        xap_alias_ion_stage,xap_alias_local_level,xap_alias_global_index, &
        xap_alias_population,ion_index,ion_stage,local_level,global_index, &
        population
      close(lun)
    endif
  endif
  if (local_level.eq.nlev) then
    xap_alias_valid = 1
    xap_alias_ion_index = ion_index
    xap_alias_ion_stage = ion_stage
    xap_alias_local_level = local_level
    xap_alias_global_index = global_index
    xap_alias_population = population
  endif
9104 format(5(i12,','),es26.16e3,',',4(i12,','),es26.16e3)
end subroutine xap_zone1_alias_candidate
'''


def zone1_insertion_snippets() -> Dict[str, str]:
    return {
        "calc_hmc_all_entry_arrays": """! Insert immediately after call xap_hmc_input_state in calc_hmc_all.f90.
      call xap_zone1_entry_arrays(nl,abel,mml,mmu,ndl,leveltemp%klev)
""",
        "calc_hmc_ion_record": """! Insert after llo/lup are finalized and immediately before airtmp=ans2.
              call xap_zone1_rate_record(nnzz,nnzz-nnnn+1,jkk_ion,nlev, &
     &          ml_data,ltyp,lrtyp,idest1,idest2,llo,lup,ptmp1,ptmp2, &
     &          xpx,ans1,ans2,ans3,ans4,ans5,ans6)
""",
        "calc_hmc_element_second_pass_rate": """! Insert immediately after pirti(klion)=pirttmp and rrrti(klion)=rrrttmp.
            call xap_zone1_second_pass_rate(nnz,klion,jkk_ion, &
     &           pirttmp,rrrttmp)
""",
        "msolvelucy_thermal_term": """! Insert inside the mm.eq.nn thermal loop after cj/cj2 accumulation and before the lpri write.
          call xap_zone1_thermal_term(ll,ltpsv(ll),mm,nn,ltyp,lrtyp, &
     &         x(mm),cjisb(ll),cjisb2(ll))
""",
        "calc_ion_rates_record": """! In calc_ion_rates.f90, save pirti/rrrti and mark the selected record immediately before ucalc.
            pirti_before=pirti
            rrrti_before=rrrti
            call xap_zone1_begin_calc_ion_rate_record(nnzz, &
     &        nnzz-nnnn+1,ml_data)
! Then insert after the source accumulation branches.
            call xap_zone1_calc_ion_rate_record(nnzz,nnzz-nnnn+1, &
     &        jkk_ion,ml_data,ltyp,lrtyp,ml_ion,parent_threshold, &
     &        ans1,ans2,ans3,ans4,ans5,ans6,pirti_before, &
     &        pirti-pirti_before,pirti,rrrti_before, &
     &        rrrti-rrrti_before,rrrti,idest1,idest2)
""",
        "ucalc_type15_shell": """! In ucalc.f90 label 15, preserve the parent threshold before the shell loop and insert after ett/ddd are assigned.
        call xap_zone1_type15_shell(ml,nilin,xap_parent_threshold,na, &
     &       lk,ett,ddd,merge(1,0,lk.eq.na))
! Insert immediately before call bkhsgo.
      call xap_zone1_type15_effective(ml,nilin,1,ett,ddd)
! Insert immediately before call phintfo.
      call xap_zone1_type15_effective(ml,nilin,2,ett,ddd)
""",
        "msolvelucy_normalization_row": """! Insert after number conservation is imposed and before call leqt2f.
        call xap_zone1_normalization_row(niter,nspmx,nspcon, &
     &       ajissup,bmatsup)
""",
        "calc_hmc_element_level_population": """! Insert in the active-ion post-solve writeback loop immediately after xileve(mm+ipmat)=x(mm+ipmat2).
              call xap_zone1_level_population(nnz,klion,jkk_ion,mm, &
     &             mm+ipmat2,x(mm+ipmat2))
""",
        "calc_hmc_all_live_hydrogen_state": """! Insert immediately after the literal xh0/xh1 assignments in calc_hmc_all.f90.
      call xap_zone1_hydrogen_state(xilevg(1),abel(1),xpx,xh0,xh1)
""",
        "calc_hmc_all_carbon_incoming_state": """! Insert in the global-to-element population mapping loop after xileve(mm+ipmat)=xilevg(mmtmp).
                  if (jk.eq.6) call xap_zone1_carbon_state_path(20,0,0, &
     &              0,0,0,klion,jkk,mm,mmtmp,mm+ipmat,                 &
     &              xileve(mm+ipmat))
""",
        "calc_hmc_all_carbon_global_writeback": """! Before the carbon global save loop, reset alias tracking.
          if (jk.eq.6) call xap_zone1_alias_reset()
! After each xilevg(mmtmp)=xileve(...) assignment, record phase 120 and the alias candidate.
                  if (jk.eq.6) then
                    call xap_zone1_carbon_state_path(120,0,0,0,0,0,   &
     &                klion,jkk,mm,mmtmp,mm+ipmatsv,xilevg(mmtmp))
                    call xap_zone1_alias_candidate(jkk,klion,mm,nlev,  &
     &                mmtmp,xilevg(mmtmp))
                    endif
""",
        "calc_hmc_element_carbon_pre_solve": """! Insert immediately before call msolvelucy.
      if (nnz.eq.6) then
        do mm=1,ipmat2
          call xap_zone1_carbon_state_path(30,0,0,mm,nsup(mm),         &
     &      nion(mm),nion(mm),0,0,0,0,x(mm))
          enddo
        endif
""",
        "calc_hmc_element_carbon_writeback_and_xii": """! After each active-ion xileve writeback, record phase 110.
              if (nnz.eq.6) call xap_zone1_carbon_state_path(110,     &
     &          nit,0,mm+ipmat2,nsup(mm+ipmat2),nion(mm+ipmat2),      &
     &          klion,jkk_ion,mm,0,mm+ipmat,xileve(mm+ipmat))
! After each ion-stage xii sum, record phase 100.
            if (nnz.eq.6) call xap_zone1_carbon_stage_total(100,nit,  &
     &          nion(ipmat2+1),klion,xii(klion))
""",
        "msolvelucy_source_order_state_path": """! Inside msolvelucy, record phases in source order:
! 40 outer-start x, 41 outer-start xtot, 50 post-condensed x,
! 60 each fixed-point normalized x, 70 post-fixed-point x,
! 80 final x, and 90 final outer-start xtot.
          call xap_zone1_carbon_state_path(40,niter,0,mm,nsup(mm), &
     &      nion(mm),nion(mm),0,0,0,0,x(mm))
          call xap_zone1_carbon_stage_total(41,niter,mm,mm,xtot(mm))
          call xap_zone1_carbon_state_path(50,niter,0,mm,nsup(mm), &
     &      nion(mm),nion(mm),0,0,0,0,x(mm))
          call xap_zone1_carbon_state_path(60,niter,nit2,mm,nsup(mm), &
     &      nion(mm),nion(mm),0,0,0,0,x(mm))
          call xap_zone1_carbon_state_path(70,niter,nit2,mm,nsup(mm), &
     &      nion(mm),nion(mm),0,0,0,0,x(mm))
          call xap_zone1_carbon_state_path(80,niter,0,mm,nsup(mm), &
     &      nion(mm),nion(mm),0,0,0,0,x(mm))
          call xap_zone1_carbon_stage_total(90,niter,mm,mm,xtot(mm))
""",
    }


def write_zone1_probe_products(out_dir: str | Path) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    products: Dict[str, Path] = {}
    for prefix, generated in (
        ("calc_hmc", write_calc_hmc_all_probe_products(out)),
        ("dsec", write_dsec_probe_products(out)),
    ):
        for key, value in generated.items():
            products[f"{prefix}_{key}"] = Path(value)
    helper = out / "xstar_atomic_zone1_dsec_probe_helpers.f90"
    helper.write_text(zone1_extra_helper(), encoding="utf-8")
    snippets = out / "xstar_atomic_zone1_dsec_insertion_snippets.md"
    text = ["# v0.4.87 zone-1 DSEC/source-order state-path insertion snippets", ""]
    for name, snippet in zone1_insertion_snippets().items():
        text.extend((f"## {name}", "", "```fortran", snippet.rstrip(), "```", ""))
        snippet_path = out / f"{name}_insertion.f90"
        snippet_path.write_text(snippet.rstrip() + "\n", encoding="utf-8")
        products[f"zone1_{name}_insertion"] = snippet_path
    snippets.write_text("\n".join(text), encoding="utf-8")
    manifest = out / "README_v0487_zone1_state_path_probe.md"
    manifest.write_text(
        "# XSTAR v0.4.87 diagnostic-only source-order state-path probe build hotfix\n\n"
        "Compile the correlation, calc_hmc_all, dsec, and zone-1 helper modules "
        "before the instrumented XSTAR sources. Apply the existing insertion "
        "snippets plus the source-order state-path snippets in this directory.\n\n"
        "Run only the first physical benchmark with:\n\n"
        "```bash\n"
        "export XSTAR_ATOMIC_DSEC_TARGET_CALL=1\n"
        "export XSTAR_ATOMIC_HMC_TARGET_DSEC_CALL=1\n"
        "export XSTAR_ATOMIC_HMC_TARGET_DSEC_EVALUATION=0\n"
        "export XSTAR_ATOMIC_HMC_TARGET_DSEC_PHASE=dsec_internal\n"
        "export XSTAR_ATOMIC_HMC_TARGET_ELEMENT=6\n"
        "```\n\n"
        "Evaluation zero means every internal calc_hmc_all evaluation in DSEC "
        "call 1. Delete old probe CSVs before running. The helpers are "
        "observation-only. v0.4.87 fixes only the alias-reset helper linkage; it adds no production-physics correction.\n",
        encoding="utf-8",
    )
    products.update({"zone1_helper": helper, "zone1_snippets": snippets, "zone1_manifest": manifest})
    return products


__all__ = ["zone1_extra_helper", "zone1_insertion_snippets", "write_zone1_probe_products"]
