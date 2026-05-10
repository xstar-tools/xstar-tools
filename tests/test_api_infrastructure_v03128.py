from pathlib import Path

from xstar_atomic import EscapeContext, LocalPlasmaState, RadiationField, RateEvaluation, evaluate_type50_bound_bound
from xstar_atomic.audit import type50_line_pumping


def test_context_objects_are_serializable():
    state = LocalPlasmaState.from_mapping({
        "xstar_temperature_K": "76655.2",
        "xstar_electron_density_cm^-3": "1.20466e8",
        "xstar_log_xi_local": "1.5",
        "xstar_helike_fraction": "0.255926",
    })
    assert state.temperature_K == 76655.2
    assert state.electron_density_cm3 == 1.20466e8
    assert state.log_xi == 1.5

    rad = RadiationField.from_pairs([(1.0, 2.0), (2.0, 4.0)])
    assert rad.bin_index(1.8) == 1
    assert rad.value_at(1.8) == 4.0

    esc = EscapeContext(cfrac=0.25, ptmp1=0.1, ptmp2=0.2, flinabs_ptmp1=0.5)
    assert esc.covering_multiplier == 0.75
    assert esc.ptmp_sum == 0.30000000000000004


def test_type50_rate_evaluator_source_formula_and_swap():
    result = evaluate_type50_bound_bound(
        aij_s_inv=10.0,
        oscillator_strength=0.7,
        wavelength_A=20.0,
        vtherm_cm_s=1.0e7,
        bremsa_nb1=3.0e5,
        ptmp1=0.2,
        ptmp2=0.3,
        flinabs_ptmp1=0.8,
        cfrac=0.1,
        ion="O VII",
    )
    assert isinstance(result, RateEvaluation)
    assert result.status == "ok"
    assert result.upper_to_lower_escaped_decay_s_inv == 5.0
    assert result.lower_to_upper_photoexcitation_s_inv is not None
    assert result.terms["pre_swap_ans1_escaped_decay_s^-1"] == 5.0
    assert result.terms["post_swap_ans2_escaped_decay_s^-1"] == 5.0
    assert "ucalc.f90:type50" in result.source_formula


def test_type50_rate_evaluator_reports_incomplete_context():
    result = evaluate_type50_bound_bound(aij_s_inv=1.0, ptmp1=0.1, ptmp2=0.1)
    assert result.status == "incomplete_context"
    assert "missing inputs" in result.warnings[-1]


def test_type50_audit_function_can_write_empty_outputs(tmp_path: Path):
    cases = tmp_path / "cases.csv"
    cases.write_text("ion,tag,status\nO VII,o7,not_selected\n", encoding="utf-8")
    out_dir = tmp_path / "audit"
    audit = type50_line_pumping(cases, out_dir=out_dir, write_outputs=True)
    assert audit.metadata["n_cases"] == 0
    assert (out_dir / "helike_type50_line_pumping_audit.csv").exists()
    assert (out_dir / "helike_type50_line_pumping_audit.md").exists()
    assert (out_dir / "helike_type50_line_pumping_audit.json").exists()
