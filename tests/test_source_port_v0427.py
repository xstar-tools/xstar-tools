from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.source_port import (
    FixedStateElementRequest,
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcStatus,
    calc_hmc_all,
)


def _pre_matrix(master, derived, *, element_z, context, critf, dispatcher=None):
    rates = {
        1: SimpleNamespace(ready=True, pirti=1.0, rrrti=2.0, contributions=[], ion_index=1),
    }
    preliminary = SimpleNamespace(
        n_rates=1,
        fractions=np.array([0.0, 0.8, 0.2]),
    )
    limits = SimpleNamespace(mml=1, mmu=1)
    return rates, preliminary, limits


def _element_two_levels(master, derived, *, element_z, context, dispatcher=None):
    rows = [
        SimpleNamespace(compact_index=1, roles=[{"ion_stage": 1, "local_level": 1}]),
        SimpleNamespace(compact_index=2, roles=[{"ion_stage": 1, "local_level": 2}]),
    ]
    block = SimpleNamespace(
        ion_index=1,
        ion_stage=1,
        nlev=2,
        compact_index=lambda level: int(level),
        second_pass_pirt=3.0,
        second_pass_rrrt=4.0,
    )
    assembly = SimpleNamespace(
        basis=SimpleNamespace(rows=rows, blocks=[block]),
        initial_populations=np.array([0.0, 1.0e-40, 2.0e-40]),
        ion_summaries=[block],
        record_results=[
            {
                "record": 77001,
                "data_type": 77,
                "rate_type": 23,
                "status": "evaluated",
                "ion_index": 1,
                "ion_stage": 1,
                "idest1": 1,
                "idest2": 2,
                "ans1": 5.0,
                "ans2": 7.0,
                "diag_type77_legacy_record_floor_clu_s^-1": 2.0,
                "diag_type77_legacy_record_floor_cul_s^-1": 3.0,
                "diag_type77_endpoint_energy_difference_eV": 10.0,
                "diag_type77_source_floor_wavelength_A": 1239.84016,
                "diag_type77_calt77_wavelength_A": 100.0,
                "diag_type77_calt77_log10_temperature_used": 5.0,
                "diag_type77_legacy_record_floor_log10_temperature_used": 4.0,
            }
        ],
    )
    solve = SimpleNamespace(
        heating=0.0,
        cooling=0.0,
        heating2=0.0,
        cooling2=0.0,
        ion_population_totals=np.array([1.0]),
        ionization_totals=np.array([5.0]),
        recombination_totals=np.array([6.0]),
        ionization_components=np.zeros((5, 1)),
        recombination_components=np.zeros((5, 1)),
        populations=np.array([2.0e-40, 4.0e-40]),
        gamma=np.array([1.0, 2.0]),
        alpha=np.array([3.0, 4.0]),
        fgamma=np.zeros((5, 2)),
        falpha=np.zeros((5, 2)),
        igammamax_record=np.array([101, 102]),
        ialphamax_record=np.array([201, 202]),
    )
    return SimpleNamespace(
        assembly=assembly,
        solve=solve,
        full_element_direct_solve_ready=True,
    )


def test_two_floor_bilevg_and_final_continuum_record_semantics():
    derived = SimpleNamespace(
        n_ions=1,
        ion_records=np.array([0, 11]),
        ion_element_z=np.array([0, 1]),
        ion_stage=np.array([0, 1]),
        nlevs=np.array([0, 2]),
        npilev=np.array([[0, 0], [0, 10], [0, 11]]),
        element_records=np.array([0]),
    )
    result = calc_hmc_all(
        object(),
        derived,
        elements=[FixedStateElementRequest(1, 1, 1, abundance=1.0)],
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.0,
        element_solver=_element_two_levels,
        pre_matrix_solver=_pre_matrix,
    )
    spectroscopic = (1, 1, 1)
    continuum = (1, 1, 2)
    assert result.bilevg[spectroscopic] == pytest.approx(2.0e-40 / (1.0e-40 + 1.0e-37))
    assert result.bilevg[continuum] == pytest.approx(4.0e-40 / (2.0e-40 + 1.0e-48))
    assert result.igammamaxg[spectroscopic] == 101
    assert result.ialphamaxg[spectroscopic] == 201
    assert result.igammamaxg[continuum] == 0
    assert result.ialphamaxg[continuum] == 0


def test_type77_uses_endpoint_energy_wavelength_for_ucalc_temperature_floor():
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(index=1, energy_ev=0.0, statistical_weight=2.0),
            2: UCalcLevel(index=2, energy_ev=1239.84016, statistical_weight=4.0),
        },
        nlev=2,
    )
    # nden=2, ntem=2, nll=1, idest2=2.  The grid increases with log T.
    # The record-tail wavelength is 100 A, while the endpoint energy gives 10 A.
    record = UCalcRecord(
        record=77001,
        data_type=77,
        rate_type=23,
        continuation=0,
        reals=(0.0, 10.0, 4.0, 6.0, 0.0, 2.0, 0.0, 2.0, 100.0),
        integers=(2, 2, 1, 2, 0, 1),
    )
    result = SourceFaithfulUCalc().evaluate(
        record,
        UCalcContext(
            temperature_k=1.0e4,
            hydrogen_density_cm3=1.0e8,
            electron_fraction_xee=1.0,
            levels=levels,
            nlev=2,
        ),
    )
    assert result.status is UCalcStatus.EVALUATED
    assert result.idest1 == 1
    assert result.idest2 == 2
    assert result.diagnostics["type77_source_floor_wavelength_A"] == pytest.approx(10.0)
    assert result.diagnostics["type77_temperature_floor_wavelength_source"] == "ucalc_endpoint_energy_difference"
    assert result.diagnostics["type77_calt77_log10_temperature_used"] > result.diagnostics["type77_legacy_record_floor_log10_temperature_used"]
    assert result.ans2 > result.diagnostics["type77_legacy_record_floor_cul_s^-1"]
    assert result.diagnostics["type77_impact_audit_role"] == "diagnostic_fixed_population_source_vs_legacy_floor"


def test_type77_fixed_population_impact_audit_is_diagnostic_only():
    from xstar_atomic.source_port.local_zone import _type77_floor_impact_rows

    derived = SimpleNamespace(
        n_ions=1,
        ion_records=np.array([0, 11]),
        ion_element_z=np.array([0, 1]),
        ion_stage=np.array([0, 1]),
        nlevs=np.array([0, 2]),
        npilev=np.array([[0, 0], [0, 10], [0, 11]]),
        element_records=np.array([0]),
    )
    result = calc_hmc_all(
        object(),
        derived,
        elements=[FixedStateElementRequest(1, 1, 1, abundance=1.0)],
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.0,
        element_solver=_element_two_levels,
        pre_matrix_solver=_pre_matrix,
    )
    rows = _type77_floor_impact_rows(result)
    assert len(rows) == 1
    row = rows[0]
    assert row["record"] == 77001
    assert row["source_minus_legacy_clu_s_inv"] == pytest.approx(3.0)
    assert row["source_minus_legacy_cul_s_inv"] == pytest.approx(4.0)
    assert row["production_operator_uses"] == "source_endpoint_floor"
    assert row["legacy_branch_role"] == "diagnostic_only"
