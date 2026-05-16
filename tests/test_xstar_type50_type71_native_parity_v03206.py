from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from xstar_atomic.rates_type50 import evaluate_type50_ucalc_record
from xstar_atomic.rates_type71 import evaluate_calt71_record, evaluate_type71_ucalc_record
from xstar_atomic.xstar_type50_type71_native_parity import (
    build_type50_type71_native_parity_audit,
    write_type50_type71_native_parity_audit,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _type50_decoded(record: int = 501) -> dict:
    return {
        "record": record,
        "element": "O",
        "ion_stage": 7,
        "ion_roman": "VII",
        "lower_level": 1,
        "upper_level": 2,
        "A_s^-1": 10.0,
        "f_osc_from_A": 0.25,
        "wavelength_A": 20.0,
        "energy_eV": 12398.4016 / 20.0,
    }


def _type71_single_decoded(record: int = 700) -> dict:
    # calt71 single-point branch: rdat(3)=log10(A), rdat(4)=wavelength.
    return {
        "record": record, "lower_level": 3, "upper_level": 4,
        "nden": 1, "ntem": 1, "ints": [1, 1, 3, 4],
        "reals": [0.0, 0.0, math.log10(4.0), 10.0],
    }


def _type71_decoded(record: int = 701) -> dict:
    # Density-sensitive grid: the parity probe must use den=xpx=1e8, not
    # physical ne=xpx*xee=1.2e8.
    return {
        "record": record, "lower_level": 3, "upper_level": 4,
        "nden": 2, "ntem": 2, "ints": [2, 2, 3, 4],
        "reals": [8.0, 10.0, 5.0, 7.0, 0.0, 2.0, 2.0, 4.0, 10.0],
    }


def _make_closure(root: Path, *, cfrac: float = 1.0, bremsa: float | None = None) -> None:
    root.mkdir()
    t50 = evaluate_type50_ucalc_record(
        _type50_decoded(), ptmp1=0.2, ptmp2=0.3, cfrac=cfrac, bremsa_nb1=bremsa
    )
    t71 = evaluate_type71_ucalc_record(
        _type71_decoded(), temperature_k=1.0e6, electron_density_cm3=1.0e8,
        ptmp1=0.25, ptmp2=0.75,
    )
    ucalc = [
        {
            "capture_index": 11, "ml_data": 501, "ltyp": 50, "lrtyp": 4,
            "jkk_ion": 31, "idest1": 2, "idest2": 1,
            "ans1": t50["ans1_photoexcitation_s^-1"],
            "ans2": t50["ans2_escaped_decay_s^-1"],
            "ptmp1": 0.2, "ptmp2": 0.3,
            "xpx": 1.0e8, "xnx": 1.2, "t_xstar_1e4K": 100.0,
            "cfrac": cfrac,
        },
        {
            "capture_index": 12, "ml_data": 701, "ltyp": 71, "lrtyp": 14,
            "jkk_ion": 31, "idest1": 4, "idest2": 3,
            "ans1": t71["ans1_upward_s^-1"],
            "ans2": t71["ans2_downward_s^-1"],
            "ptmp1": 0.25, "ptmp2": 0.75,
            "xpx": 1.0e8, "xnx": 1.2, "t_xstar_1e4K": 100.0,
            "cfrac": cfrac,
        },
    ]
    matrix: list[dict] = []
    for capture, record, ltyp, lrtyp, ans1, ans2, lo, hi in [
        (11, 501, 50, 4, t50["ans1_photoexcitation_s^-1"], t50["ans2_escaped_decay_s^-1"], 79, 80),
        (12, 701, 71, 14, t71["ans1_upward_s^-1"], t71["ans2_downward_s^-1"], 79, 80),
    ]:
        for kind, row_ip, col_ip, value, rs, cs in [
            ("forward_offdiag", hi, lo, ans1, True, True),
            ("reverse_offdiag", lo, hi, ans2, True, True),
            ("forward_diag_loss", lo, lo, -ans1, True, True),
            ("reverse_diag_loss", hi, hi, -ans2, True, True),
            # Reciprocal insertion in an external equation: retained for scope.
            ("reverse_offdiag", 900 + record, hi, ans2, False, True),
        ]:
            matrix.append({
                "capture_index": capture, "ml_data": record,
                "ltyp": ltyp, "lrtyp": lrtyp,
                "insertion_kind": kind,
                "compact_row_ipmat2": row_ip,
                "compact_col_ipmat2": col_ip,
                "row_endpoint_selected": rs,
                "col_endpoint_selected": cs,
                "ajisi_1": value,
            })
    _write_csv(root / "xstar_priority_matrix_closure_audit_ucalc_records.csv", ucalc)
    _write_csv(root / "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv", matrix)
    (root / "xstar_priority_matrix_closure_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII", "selected_basis_solve_call_id": 219,
            "selection": "latest-per-record", "occurrence_rank": -1,
            "selected_xstar_ipmat2_indices": "79;80",
        }
    }), encoding="utf-8")


def test_type50_exact_zero_and_explicit_radiation_context() -> None:
    full = evaluate_type50_ucalc_record(
        _type50_decoded(), ptmp1=0.2, ptmp2=0.3, cfrac=1.0, hydrogen_density_cm3=1.0e8
    )
    assert full["status"] == "evaluated"
    assert full["ans1_photoexcitation_s^-1"] == 0.0
    assert full["ans2_escaped_decay_s^-1"] == 5.0
    assert full["source_equivalent_rate_context"] is True
    assert full["radiation_context_required"] is False

    missing = evaluate_type50_ucalc_record(
        _type50_decoded(), ptmp1=0.2, ptmp2=0.3, cfrac=0.5, hydrogen_density_cm3=1.0e8
    )
    assert missing["status"] == "not_evaluated"
    assert "bremsa_nb1" in missing["reason"]

    supplied = evaluate_type50_ucalc_record(
        _type50_decoded(), ptmp1=0.2, ptmp2=0.3, cfrac=0.5,
        bremsa_nb1=2.0e20, hydrogen_density_cm3=1.0e8,
    )
    expected = 0.02655 * 0.25 * 20.0e-8 * 2.0e20 / 3.0e10 * 0.5
    assert supplied["status"] == "evaluated"
    assert math.isclose(supplied["ans1_photoexcitation_s^-1"], expected, rel_tol=1.0e-15)

    weak = _type50_decoded(502)
    weak["A_s^-1"] = 1.0e-30
    floored = evaluate_type50_ucalc_record(
        weak, ptmp1=0.5, ptmp2=0.5, cfrac=1.0, hydrogen_density_cm3=1.0e8
    )
    assert floored["density_floor_applied"] is True
    assert floored["ans2_escaped_decay_s^-1"] == 1.0e-12


def test_type71_single_and_grid_branches() -> None:
    single = evaluate_calt71_record(
        _type71_single_decoded(), temperature_k=1.0e6, electron_density_cm3=1.0e8
    )
    assert single["status"] == "evaluated"
    assert single["branch"] == "single_point"
    assert math.isclose(single["aij_s^-1"], 4.0, rel_tol=1.0e-15)

    grid = {
        "record": 702, "lower_level": 3, "upper_level": 4,
        "ints": [2, 2, 3, 4],
        # logne grid, logT grid, row-major log10(A) table, wavelength
        "reals": [8.0, 10.0, 5.0, 7.0, 0.0, 2.0, 2.0, 4.0, 15.0],
    }
    result = evaluate_calt71_record(
        grid, temperature_k=1.0e6, electron_density_cm3=1.0e9
    )
    assert result["status"] == "evaluated"
    assert result["branch"] == "logne_logT_grid"
    # Bilinear midpoint of 0,2,2,4 is log10(A)=2.
    assert math.isclose(result["aij_s^-1"], 100.0, rel_tol=1.0e-15)

    ca = _type71_single_decoded(703)
    ca["ints"] = [1, 1, 3, 4, 20, 96]
    ca["reals"] = [0.0, 0.0, 11.0, 10.0]
    capped = evaluate_type71_ucalc_record(
        ca, temperature_k=1.0e4, electron_density_cm3=1.0, ptmp1=0.5, ptmp2=0.5
    )
    assert capped["ans2_downward_s^-1"] == 1.0e10
    assert capped["special_ca_i_ca_ii_cap_applied"] is True


def test_native_type50_type71_parity_matches_synthetic_probe(tmp_path: Path) -> None:
    closure = tmp_path / "closure"
    _make_closure(closure)
    audit = build_type50_type71_native_parity_audit(
        priority_matrix_closure_audit=closure,
        decoded_type50_rows=[_type50_decoded()],
        decoded_type71_rows=[_type71_decoded()],
        relative_rate_tolerance=1.0e-12,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.206"
    assert summary["n_type50_records_rate_parity_pass"] == 1
    assert summary["n_type71_records_rate_parity_pass"] == 1
    assert summary["n_type50_compact_matrix_terms_match"] == 5
    assert summary["n_type71_compact_matrix_terms_match"] == 5
    assert summary["native_type50_selected_system_parity_ready"] is True
    assert summary["native_type71_selected_system_parity_ready"] is True
    assert summary["native_type50_type71_selected_system_parity_ready"] is True

    paths = write_type50_type71_native_parity_audit(tmp_path / "out", audit)
    assert all(Path(path).exists() for path in paths.values())


def test_native_type50_parity_requires_explicit_radiation_when_not_full_cover(tmp_path: Path) -> None:
    closure = tmp_path / "closure"
    _make_closure(closure, cfrac=0.5, bremsa=2.0e20)
    failed = build_type50_type71_native_parity_audit(
        priority_matrix_closure_audit=closure,
        decoded_type50_rows=[_type50_decoded()],
        decoded_type71_rows=[_type71_decoded()],
    )
    assert failed["summary"]["native_type50_selected_system_parity_ready"] is False

    passed = build_type50_type71_native_parity_audit(
        priority_matrix_closure_audit=closure,
        decoded_type50_rows=[_type50_decoded()],
        decoded_type71_rows=[_type71_decoded()],
        type50_context_rows=[{
            "capture_index": 11, "record": 501,
            "bremsa_nb1": 2.0e20, "flinabs_ptmp1": 1.0,
        }],
        relative_rate_tolerance=1.0e-12,
    )
    assert passed["summary"]["native_type50_selected_system_parity_ready"] is True
