from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.rates_type53 import Type53LiveRadiationState, evaluate_type53_ucalc_record
from xstar_atomic.xstar_type53_live_native_parity import (
    _infer_type53_nlevp_from_probe_endpoint,
    build_type53_live_native_parity_audit,
)


def _state() -> Type53LiveRadiationState:
    return Type53LiveRadiationState.from_sequences(
        [1, 2, 4, 8, 16, 32, 64, 128, 256, 512],
        [1.0e-2] * 10, [0.0] * 10,
        metadata={
            "capture_index": 7, "zone_index": 3, "pass_index": 1, "ldir": 1,
            "temperature_K": 1.0e5, "xpx": 1.0e8,
            "electron_density_cm^-3": 1.0e8, "cfrac": 1.0,
        },
    )


def _record() -> dict:
    return {
        "record": 53001, "bound_level": 1, "destination_level": 2,
        "energy_above_threshold_ryd": [0, 1, 2, 4, 8, 16, 32],
        "cross_section_cm2": [1e-18, 8e-19, 6e-19, 4e-19, 2e-19, 1e-19, 5e-20],
        "threshold_eV": 10.0, "base_threshold_eV": 10.0,
        "parent_excitation_eV": 0.0, "bound_statistical_weight": 2.0,
        "continuum_statistical_weight": 1.0, "destination_statistical_weight": 1.0,
        "continuum_energy_eV": 10.0, "bound_energy_eV": 0.0,
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


def _make_closure(root: Path, native: dict) -> None:
    root.mkdir()
    ans = [native[f"ans{i}_{name}"] for i, name in [
        (1, "photoionization_s^-1"), (2, "milne_recombination_s^-1"),
        (3, "cooling_signed_erg_s^-1"), (4, "heating_signed_erg_s^-1"),
        (5, "electron_pov_cooling_signed_erg_s^-1"),
        (6, "electron_pov_heating_signed_erg_s^-1"),
    ]]
    probe = {
        "ltyp": 53, "lrtyp": 7, "ml_data": 53001, "capture_index": 17,
        "jkk_ion": 8, "idest1": 1, "idest2": 2, "t_xstar_1e4K": 10.0,
        "xpx": 1e8, "xnx": 1.0, "ptmp1": 0.5, "ptmp2": 0.5, "cfrac": 1.0,
    }
    for i, value in enumerate(ans, 1):
        probe[f"ans{i}"] = value
    _write_csv(root / "xstar_priority_matrix_closure_audit_ucalc_records.csv", [probe])
    terms = []
    for kind, row, col, value in [
        ("forward_offdiag", 1, 2, ans[0]), ("reverse_offdiag", 2, 1, ans[1]),
        ("forward_diag_loss", 2, 2, -ans[0]), ("reverse_diag_loss", 1, 1, -ans[1]),
    ]:
        terms.append({
            "ltyp": 53, "lrtyp": 7, "ml_data": 53001, "capture_index": 17,
            "insertion_kind": kind, "compact_row_ipmat2": row,
            "compact_col_ipmat2": col, "row_endpoint_selected": True,
            "col_endpoint_selected": True, "ajisi_1": value,
        })
    _write_csv(root / "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv", terms)
    (root / "xstar_priority_matrix_closure_audit.json").write_text(json.dumps({
        "summary": {"ion": "O VII", "selected_xstar_ipmat2_indices": "1;2"}
    }), encoding="utf-8")


def test_type53_nlevp_is_inferred_from_probe_endpoint_not_max_level() -> None:
    assert _infer_type53_nlevp_from_probe_endpoint(
        xstar_idest2=79, packed_parent_offset=1,
    ) == 79
    assert _infer_type53_nlevp_from_probe_endpoint(
        xstar_idest2=80, packed_parent_offset=2,
    ) == 79
    assert _infer_type53_nlevp_from_probe_endpoint(
        xstar_idest2=0, packed_parent_offset=1,
    ) is None


def test_type53_gate_requires_consistent_xstar_nlevp_context(tmp_path: Path) -> None:
    record = _record()
    native = evaluate_type53_ucalc_record(
        record, _state(), temperature_k=1e5, xpx_cm3=1e8,
        electron_fraction_xee=1.0, ptmp1=0.5, ptmp2=0.5,
    )
    closure = tmp_path / "closure"
    _make_closure(closure, native)
    record["nlevp_inference_consistent"] = False
    audit = build_type53_live_native_parity_audit(
        priority_matrix_closure_audit=closure, decoded_type53_rows=[record],
        live_state=_state(),
    )
    assert audit["summary"]["audit_version"] == "v0.3.209"
    assert audit["summary"]["type53_decoder_context_ready"] is False
    assert audit["summary"]["native_type53_selected_system_parity_ready"] is False
