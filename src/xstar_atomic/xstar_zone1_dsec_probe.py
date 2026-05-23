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
    return r'''! xstar-atomic v0.4.78 bounded zone-1 DSEC detail probe.
!
! Diagnostic only.  No caller-owned value is modified.
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
    text = ["# v0.4.78 zone-1 DSEC extra insertion snippets", ""]
    for name, snippet in zone1_insertion_snippets().items():
        text.extend((f"## {name}", "", "```fortran", snippet.rstrip(), "```", ""))
    snippets.write_text("\n".join(text), encoding="utf-8")
    manifest = out / "README_v0478_zone1_dsec_probe.md"
    manifest.write_text(
        "# XSTAR v0.4.78 bounded zone-1 DSEC probe\n\n"
        "Compile the correlation, calc_hmc_all, dsec, and zone-1 helper modules "
        "before the instrumented XSTAR sources. Apply the existing insertion "
        "snippets plus the four extra snippets in this directory.\n\n"
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
        "observation-only and do not modify production physics.\n",
        encoding="utf-8",
    )
    products.update({"zone1_helper": helper, "zone1_snippets": snippets, "zone1_manifest": manifest})
    return products


__all__ = ["zone1_extra_helper", "zone1_insertion_snippets", "write_zone1_probe_products"]
