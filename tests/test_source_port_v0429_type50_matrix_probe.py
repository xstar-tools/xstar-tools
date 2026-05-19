from __future__ import annotations

from types import SimpleNamespace
import math

import numpy as np
import pytest

from xstar_atomic.rates_type50 import evaluate_type50_ucalc_record
from xstar_atomic.source_port.element_equilibrium import MatrixTerm
from xstar_atomic.source_port import (
    SourceFaithfulUCalc, UCalcContext, UCalcLevel, UCalcLevelTable,
    UCalcRecord, UCalcStatus,
)
from xstar_atomic.source_port.calc_hmc_all_matrix_parity import (
    compare_same_call_matrix_terms,
    compare_thermal_families,
)
from xstar_atomic.xstar_calc_hmc_all_probe import (
    calc_hmc_all_probe_helper,
    calc_hmc_all_insertion_snippets,
)


def test_type50_post_swap_energy_channels_follow_source() -> None:
    decoded = {
        "A_s^-1": 10.0,
        "f_osc_from_A": 0.25,
        "wavelength_A": 100.0,
    }
    result = evaluate_type50_ucalc_record(
        decoded,
        ptmp1=0.2,
        ptmp2=0.3,
        cfrac=1.0,
        hydrogen_density_cm3=1.0e8,
        endpoint_energy_eV=100.0,
    )
    erg_per_ev = 1.602176634e-12
    escaped = 5.0
    assert result["status"] == "evaluated"
    assert result["energy_channel_status"] == "evaluated"
    assert result["ans1_photoexcitation_s^-1"] == 0.0
    assert result["ans2_escaped_decay_s^-1"] == escaped
    assert math.isclose(
        result["ans3_cooling_signed_erg_s^-1"],
        -escaped * 100.0 * erg_per_ev,
        rel_tol=1.0e-15,
    )
    assert result["ans4_heating_signed_erg_s^-1"] == 0.0
    assert result["decay_energy_source"] == "endpoint_energy_difference"
    assert result["source_erg_per_eV"] == pytest.approx(1.602176634e-12, rel=0.0, abs=0.0)
    assert result["energy_eV"] == pytest.approx(123.984016)

    # Historical population-rate callers remain valid without endpoint context.
    legacy = evaluate_type50_ucalc_record(
        decoded,
        ptmp1=0.2,
        ptmp2=0.3,
        cfrac=1.0,
        hydrogen_density_cm3=1.0e8,
    )
    assert legacy["status"] == "evaluated"
    assert legacy["energy_channel_status"] != "evaluated"



def test_source_port_type50_returns_energy_channels() -> None:
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0),
            2: UCalcLevel(2, energy_ev=100.0, statistical_weight=4.0),
            3: UCalcLevel(3, energy_ev=200.0, statistical_weight=1.0),
        },
        nlev=3,
    )
    context = UCalcContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        covering_fraction=1.0,
        ptmp1=0.2,
        ptmp2=0.3,
        nlev=3,
        levels=levels,
        extras={"element_z": 8, "ion_stage": 7},
    )
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(50, 50, 4, 0, (100.0, 0.0, 10.0), (2, 1, 1)),
        context,
    )
    assert result.status is UCalcStatus.EVALUATED
    assert result.ans1 == 0.0
    assert result.ans2 == 5.0
    assert result.ans3 == pytest.approx(-5.0 * 100.0 * 1.602176634e-12)
    assert result.ans4 == 0.0


def _term(index: int, row: int, column: int, value: float) -> MatrixTerm:
    return MatrixTerm(
        term_index=index,
        record=100 + index,
        data_type=50,
        rate_type=4,
        ion_index=1,
        ion_stage=7,
        role="test",
        row=row,
        column=column,
        aj1=value,
        aj2=0.0,
        cj=0.0,
        cj2=0.0,
        idest1=1,
        idest2=2,
        lower_endpoint=1,
        upper_endpoint=2,
        ucalc_status="evaluated",
        source_row_unclamped=row,
        source_column_unclamped=column,
    )


def _matrix_fixture():
    terms = [
        _term(1, 1, 1, -1.0),
        _term(2, 1, 2, 1.0),
        _term(3, 2, 1, 1.0),
        _term(4, 2, 2, -1.0),
    ]
    assembly = SimpleNamespace(
        terms=terms,
        dense_matrix=np.array([[-1.0, 1.0], [1.0, -1.0]]),
        basis=SimpleNamespace(n_rows=2),
    )
    element = SimpleNamespace(
        request=SimpleNamespace(element_z=8),
        equilibrium=SimpleNamespace(assembly=assembly),
    )
    result = SimpleNamespace(element_results=[element])
    closure_element = SimpleNamespace(
        element_z=8,
        row_rows=[
            {"compact_row": 1, "xstar_population": 0.5, "representative_global_level_index": 11},
            {"compact_row": 2, "xstar_population": 0.5, "representative_global_level_index": 12},
        ],
        thermal_rows=[
            {
                "element_z": 8,
                "thermal_channel": "cooling",
                "python_contribution_per_abundance": 2.0,
                "data_type": 50,
                "rate_type": 4,
            }
        ],
    )
    closure = SimpleNamespace(elements=[closure_element])
    rows = []
    for term in terms:
        rows.append({
            "element_z": "8",
            "term_index": str(term.term_index),
            "source_record": str(term.record),
            "row_raw": str(term.source_row_unclamped),
            "column_raw": str(term.source_column_unclamped),
            "row_compact": str(term.row),
            "column_compact": str(term.column),
            "aj1": repr(term.aj1),
            "aj2": "0",
            "cj": "0",
            "cj2": "0",
        })
    return result, closure, rows


def test_same_call_matrix_and_thermal_family_parity() -> None:
    result, closure, rows = _matrix_fixture()
    parity = compare_same_call_matrix_terms(
        result,
        matrix_probe_rows=rows,
        closure=closure,
        rtol=1.0e-12,
        atol=1.0e-14,
    )
    assert parity.ready is True
    assert parity.n_matched_terms == 4
    assert parity.n_active_rows_outside_tolerance == 0

    altered = [dict(row) for row in rows]
    altered[0]["aj1"] = "-0.8"
    failed = compare_same_call_matrix_terms(
        result,
        matrix_probe_rows=altered,
        closure=closure,
        rtol=1.0e-12,
        atol=1.0e-14,
    )
    assert failed.coefficient_ready is False
    assert failed.n_coefficient_rows_outside_tolerance >= 1

    # A thermal-only coefficient mismatch remains strict evidence but does not
    # alter the active population operator gate.
    thermal_only = [dict(row) for row in rows]
    thermal_only[0]["cj"] = "1e-6"
    separated = compare_same_call_matrix_terms(
        result,
        matrix_probe_rows=thermal_only,
        closure=closure,
        rtol=1.0e-12,
        atol=1.0e-14,
    )
    assert separated.topology_ready is True
    assert separated.active_closure_ready is True
    assert separated.ready is True
    assert separated.coefficient_ready is False

    thermal = compare_thermal_families(
        closure=closure,
        data_type_probe_rows=[{
            "element_z": "8", "data_type": "50",
            "heating": "0", "cooling": "2", "heating2": "0", "cooling2": "0",
        }],
        rate_type_probe_rows=[{
            "element_z": "8", "rate_type": "4",
            "heating": "0", "cooling": "2", "heating2": "0", "cooling2": "0",
        }],
        rtol=1.0e-12,
        atol=1.0e-14,
    )
    assert thermal.ready is True



def test_same_call_matrix_requires_captured_xstar_vector_for_acceptance() -> None:
    result, _closure, rows = _matrix_fixture()
    parity = compare_same_call_matrix_terms(
        result,
        matrix_probe_rows=rows,
        closure=None,
        rtol=1.0e-12,
        atol=1.0e-14,
    )
    assert parity.coefficient_ready is True
    assert parity.active_closure_ready is None
    assert parity.ready is False
    assert parity.status == "not_comparable_missing_xstar_vector"


def test_v0429_probe_contains_matrix_and_thermal_hooks() -> None:
    helper = calc_hmc_all_probe_helper()
    snippets = calc_hmc_all_insertion_snippets()
    assert "subroutine xap_hmc_matrix_terms" in helper
    assert "subroutine xap_hmc_thermal_families" in helper
    assert "xstar_calc_hmc_all_matrix_terms_probe.csv" in helper
    assert "xstar_calc_hmc_all_thermal_data_type_probe.csv" in helper
    assert "xstar_calc_hmc_all_thermal_rate_type_probe.csv" in helper
    assert "calc_hmc_element_matrix_terms" in snippets
    assert "msolvelucy_thermal_families" in snippets
