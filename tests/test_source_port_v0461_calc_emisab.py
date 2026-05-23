from __future__ import annotations

import numpy as np

import xstar_atomic as xa
from xstar_atomic.rates_type53 import Type53LiveRadiationState, evaluate_type53_ucalc_record
from xstar_atomic.source_port import (
    XSTARPythonDriver,
    XSTARSourceRoutine,
    register_calc_emisab_all_source_routine,
    resolve_calc_emisab_density,
    run_calc_emisab_source_order_validation,
)


def test_v0461_source_order_validation_passes():
    summary = run_calc_emisab_source_order_validation()
    assert summary["calc_emisab_all_source_acceptance_ready"] is True
    assert summary["shared_continuum_alias_mapping_ready"] is True
    assert summary["inactive_ion_offset_ready"] is True
    assert summary["record_source_order"] == [10, 12, 11, 13]


def test_v0461_all_rate_type_branches_pass():
    summary = run_calc_emisab_source_order_validation()
    for key in (
        "rate_type_4_ready", "rate_type_7_ready",
        "rate_type_9_no_output_ready", "rate_type_14_ready",
        "ucalc_continuum_side_effects_ready",
    ):
        assert summary[key] is True


def test_v0461_density_branches_preserve_source_literals():
    assert resolve_calc_emisab_density(xpx=9.0, pressure=2.0, t_1e4=4.0, xee=2.0, lcdd=1) == 9.0
    assert resolve_calc_emisab_density(xpx=9.0, pressure=6.0, t_1e4=4.0, xee=2.0, lcdd=2) == 3.0
    expected = 6.0 / float(np.float32(1.38e-12)) / 4.0
    assert resolve_calc_emisab_density(xpx=9.0, pressure=6.0, t_1e4=4.0, xee=2.0, lcdd=0) == expected


def test_v0461_type53_exposes_ucalc_mutable_continuum_channels():
    radiation = Type53LiveRadiationState.from_sequences(
        [1.0, 2.0, 4.0, 8.0, 16.0],
        [1.0e10, 8.0e9, 5.0e9, 2.0e9, 1.0e9],
        [0.0] * 5,
    )
    result = evaluate_type53_ucalc_record(
        {
            "energy_above_threshold_ryd": [0.0, 0.25, 0.75, 1.5],
            "cross_section_cm2": [1.0e-18, 8.0e-19, 4.0e-19, 1.0e-19],
            "threshold_eV": 1.0,
            "bound_statistical_weight": 1.0,
            "continuum_statistical_weight": 2.0,
            "destination_statistical_weight": 2.0,
            "continuum_energy_eV": 1.0,
            "bound_energy_eV": 0.0,
            "destination_energy_eV": 1.0,
        },
        radiation,
        temperature_k=1.0e5,
        xpx_cm3=1.0e8,
        electron_fraction_xee=1.0,
        ptmp1=1.0,
        ptmp2=0.0,
        lfast=2,
        abund1=0.25,
        abund2=0.1,
    )
    assert result["status"] == "evaluated"
    for key in ("opakc_cm^-1", "opakcont_cm^-1", "rccemis_inward", "rccemis_outward"):
        assert len(result[key]) == 5


def test_v0461_driver_registration():
    driver = XSTARPythonDriver()
    register_calc_emisab_all_source_routine(driver)
    assert XSTARSourceRoutine.CALC_EMISAB_ALL in driver.implemented_source_routines()


def test_v0461_version():
    assert xa.__version__ == "0.4.71"
