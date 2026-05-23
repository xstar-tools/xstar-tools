from __future__ import annotations

import numpy as np

import xstar_atomic as xa
from xstar_atomic.source_port import (
    XSTARPythonDriver,
    XSTARSourceRoutine,
    register_calc_emis_all_source_routine,
    resolve_calc_emis_density,
    run_calc_emis_source_order_validation,
)


def test_v0462_source_order_validation_passes():
    summary = run_calc_emis_source_order_validation()
    assert summary["calc_emis_all_source_acceptance_ready"] is True
    assert summary["next_source_target"] == "complete_local_xstarcalc"


def test_v0462_ranking_and_source_limit_semantics():
    summary = run_calc_emis_source_order_validation()
    assert summary["precomputed_calc_emisab_ranking_ready"] is True
    assert summary["rlbin_source_rank_limit_ready"] is True


def test_v0462_compact_alias_and_inactive_offset_semantics():
    summary = run_calc_emis_source_order_validation()
    assert summary["shared_continuum_alias_mapping_ready"] is True
    assert summary["inactive_ion_offset_ready"] is True


def test_v0462_rate9_double_call_and_rate42_pointer_reuse():
    summary = run_calc_emis_source_order_validation()
    assert summary["rate_type_9_double_ucalc_ready"] is True
    assert summary["rate_type_42_retained_continuum_pointer_ready"] is True
    assert summary["record_source_order"] == [10, 12, 11, 11, 15]


def test_v0462_fline_and_flinel_ownership_semantics():
    summary = run_calc_emis_source_order_validation()
    assert summary["strong_line_fline_ready"] is True
    assert summary["flinel_source_accumulation_ready"] is True
    assert summary["caller_owned_fline_flinel_nonreset_ready"] is True


def test_v0462_continuum_reset_and_final_slots():
    summary = run_calc_emis_source_order_validation()
    assert summary["thomson_continuum_reset_ready"] is True
    assert summary["ucalc_continuum_side_effects_ready"] is True
    assert summary["freef_source_slot_ready"] is True
    assert summary["bremem_source_slot_ready"] is True


def test_v0462_density_branches_reuse_source_literals():
    assert resolve_calc_emis_density(xpx=9.0, pressure=6.0, t_1e4=4.0, xee=2.0, lcdd=2) == 3.0
    expected = 6.0 / float(np.float32(1.38e-12)) / 4.0
    assert resolve_calc_emis_density(xpx=9.0, pressure=6.0, t_1e4=4.0, xee=2.0, lcdd=0) == expected


def test_v0462_driver_registration():
    driver = XSTARPythonDriver()
    register_calc_emis_all_source_routine(driver)
    assert XSTARSourceRoutine.CALC_EMIS_ALL in driver.implemented_source_routines()


def test_v0462_version():
    assert xa.__version__ == "0.4.84"
