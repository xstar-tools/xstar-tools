from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from xstar_atomic.rates_type53 import (
    Type53LiveRadiationState,
    evaluate_phint53_exact,
    evaluate_type53_ucalc_record,
)
from xstar_atomic.xstar_type53_live_native_parity import (
    build_type53_live_native_parity_audit,
    write_type53_live_native_parity_audit,
)


def _state() -> Type53LiveRadiationState:
    return Type53LiveRadiationState.from_sequences(
        [1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
        [1.0e-2] * 10,
        [0.0] * 10,
        metadata={
            "capture_index": 7,
            "zone_index": 3,
            "pass_index": 1,
            "ldir": 1,
            "temperature_K": 1.0e5,
            "xpx": 1.0e8,
            "electron_density_cm^-3": 1.0e8,
            "cfrac": 1.0,
        },
    )


def _record() -> dict:
    return {
        "record": 53001,
        "bound_level": 1,
        "destination_level": 2,
        "energy_above_threshold_ryd": [0, 1, 2, 4, 8, 16, 32],
        "cross_section_cm2": [1e-18, 8e-19, 6e-19, 4e-19, 2e-19, 1e-19, 5e-20],
        "threshold_eV": 10.0,
        "base_threshold_eV": 10.0,
        "parent_excitation_eV": 0.0,
        "bound_statistical_weight": 2.0,
        "continuum_statistical_weight": 1.0,
        "destination_statistical_weight": 1.0,
        "continuum_energy_eV": 10.0,
        "bound_energy_eV": 0.0,
        "destination_energy_eV": 10.0,
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def test_phint53_exact_kernel_regression_values() -> None:
    result = evaluate_phint53_exact(
        energy_above_threshold_ryd=_record()["energy_above_threshold_ryd"],
        cross_section_cm2=_record()["cross_section_cm2"],
        threshold_eV=10.0,
        live_radiation=_state(),
        temperature_1e4K=10.0,
        rnist=1.0e-20,
        ptmp1=0.5,
        ptmp2=0.5,
        lfast=2,
    )
    assert result.diagnostics["status"] == "evaluated_source_aligned_phint53"
    assert result.diagnostics["mapping_status"] == "mapped"
    # Reference values come from a standalone gfortran build of the exact
    # XSTAR phint53.f90 source with the same arrays and scalar inputs.
    assert result.pirt_s_inv == pytest.approx(1.4435344541279428e-20, rel=5e-8)
    assert result.rrrt_s_inv == pytest.approx(1.2029839116329308e-11, rel=5e-8)
    assert result.piht_erg_s_inv == pytest.approx(6.2345315532402878e-31, rel=5e-8)
    assert result.rrcl_erg_s_inv == pytest.approx(4.8188335308318710e-22, rel=5e-8)


def test_ucalc_type53_uses_continuum_weight_not_excited_destination_weight() -> None:
    a = evaluate_type53_ucalc_record(
        _record(), _state(), temperature_k=1e5, xpx_cm3=1e8,
        electron_fraction_xee=1.0, ptmp1=0.5, ptmp2=0.5,
    )
    changed = dict(_record())
    changed["destination_statistical_weight"] = 99.0
    b = evaluate_type53_ucalc_record(
        changed, _state(), temperature_k=1e5, xpx_cm3=1e8,
        electron_fraction_xee=1.0, ptmp1=0.5, ptmp2=0.5,
    )
    assert a["status"] == "evaluated"
    assert a["rnist"] == pytest.approx(b["rnist"], rel=0, abs=0)
    assert a["ans2_milne_recombination_s^-1"] == pytest.approx(b["ans2_milne_recombination_s^-1"], rel=0, abs=0)


def _make_closure(root: Path, native: dict) -> None:
    root.mkdir()
    ans = [
        native["ans1_photoionization_s^-1"], native["ans2_milne_recombination_s^-1"],
        native["ans3_cooling_signed_erg_s^-1"], native["ans4_heating_signed_erg_s^-1"],
        native["ans5_electron_pov_cooling_signed_erg_s^-1"], native["ans6_electron_pov_heating_signed_erg_s^-1"],
    ]
    probe = {
        "ltyp": 53, "lrtyp": 7, "ml_data": 53001, "capture_index": 17,
        "jkk_ion": 8, "idest1": 1, "idest2": 2,
        "t_xstar_1e4K": 10.0, "xpx": 1e8, "xnx": 1.0,
        "ptmp1": 0.5, "ptmp2": 0.5, "cfrac": 1.0,
    }
    for i, value in enumerate(ans, 1):
        probe[f"ans{i}"] = value
    _write_csv(root / "xstar_priority_matrix_closure_audit_ucalc_records.csv", [probe])
    terms = []
    for kind, row, col, value, rs, cs in [
        ("forward_offdiag", 1, 2, ans[0], True, True),
        ("reverse_offdiag", 2, 1, ans[1], True, True),
        ("forward_diag_loss", 2, 2, -ans[0], True, True),
        ("reverse_diag_loss", 1, 1, -ans[1], True, True),
    ]:
        terms.append({
            "ltyp": 53, "lrtyp": 7, "ml_data": 53001, "capture_index": 17,
            "insertion_kind": kind, "compact_row_ipmat2": row,
            "compact_col_ipmat2": col, "row_endpoint_selected": rs,
            "col_endpoint_selected": cs, "ajisi_1": value,
        })
    _write_csv(root / "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv", terms)
    (root / "xstar_priority_matrix_closure_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII", "selected_basis_solve_call_id": 219,
            "selection": "latest-per-record", "occurrence_rank": -1,
            "selected_xstar_ipmat2_indices": "1;2",
        }
    }), encoding="utf-8")


def test_exact_live_type53_parity_gate_passes_all_channels(tmp_path: Path) -> None:
    native = evaluate_type53_ucalc_record(
        _record(), _state(), temperature_k=1e5, xpx_cm3=1e8,
        electron_fraction_xee=1.0, ptmp1=0.5, ptmp2=0.5,
    )
    closure = tmp_path / "closure"
    _make_closure(closure, native)
    audit = build_type53_live_native_parity_audit(
        priority_matrix_closure_audit=closure,
        decoded_type53_rows=[_record()],
        live_state=_state(),
        relative_rate_tolerance=1e-12,
        live_context_relative_tolerance=1e-12,
    )
    s = audit["summary"]
    assert s["native_type53_exact_live_rate_parity_ready"] is True
    assert s["native_type53_heating_cooling_parity_ready"] is True
    assert s["native_type53_compact_matrix_parity_ready"] is True
    assert s["native_type53_selected_system_parity_ready"] is True
    assert s["type53_scale44_resolved_by_exact_live_state"] is True
    assert s["empirical_type53_scale_applied"] is False
    assert s["native_type53_opacity_rrc_parity_ready"] is False
    paths = write_type53_live_native_parity_audit(tmp_path / "out", audit)
    assert all(Path(v).exists() for v in paths.values())


def test_exact_live_type53_parity_rejects_wrong_live_context(tmp_path: Path) -> None:
    native = evaluate_type53_ucalc_record(
        _record(), _state(), temperature_k=1e5, xpx_cm3=1e8,
        electron_fraction_xee=1.0, ptmp1=0.5, ptmp2=0.5,
    )
    closure = tmp_path / "closure"
    _make_closure(closure, native)
    bad = Type53LiveRadiationState.from_sequences(
        _state().epim_eV, _state().bremsam, _state().bremsint,
        metadata={**dict(_state().metadata), "temperature_K": 2e5},
    )
    audit = build_type53_live_native_parity_audit(
        priority_matrix_closure_audit=closure,
        decoded_type53_rows=[_record()], live_state=bad,
    )
    assert audit["summary"]["live_state_context_ready"] is False
    assert audit["summary"]["native_type53_selected_system_parity_ready"] is False
