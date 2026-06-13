from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_tools.xstar import type53_runtime_state_independent_capture as capture
from xstar_tools.xstar.type53_runtime_state_abi_audit import ABI_VERSION, PROGRAM_ABI_VERSION


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def test_runtime_state_abi_header_is_appended() -> None:
    root = Path(__file__).resolve().parents[1]
    header = (root / 'src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h').read_text()
    assert ABI_VERSION == 60487
    assert PROGRAM_ABI_VERSION == 60485
    for field in (
        'dsec_radiation_energy_ev', 'dsec_bremsa', 'dsec_radiation_bin_count',
        'continuum_tau_in', 'continuum_tau_out', 'continuum_tau_count',
        'runtime_state_flags', 'dsec_covering_fraction',
    ):
        assert field in header


def test_probe_captures_full_runtime_workspaces() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / 'src/xstar_tools/xstar/v0472_dsec_row46_runtime_capture.py').read_text()
    assert 'dsec_radiation_workspace.csv' in text
    assert 'dsec_continuum_tau_workspace.csv' in text
    assert 'context.escape, "continuum_tau_in"' in text
    assert 'getattr(radiation, "bremsa"' in text


def test_independent_capture_verifier_accepts_complete_synthetic_bundle(tmp_path: Path) -> None:
    records = []
    terms = []
    for i in range(44):
        record = 1000 + i
        source = 2000 + i
        escape = i + 1
        records.append({
            'global_evaluation_ordinal': 60, 'source_position': source, 'record': record,
            'data_type': 53, 'rate_type': 7, 'escape_index': escape,
            'tau_in': i / 100.0, 'tau_out': 0.0, 'ptmp1': 0.0, 'ptmp2': 1.0,
            'covering_fraction': 1.0, 'temperature_k': 60000.0,
            'hydrogen_density_cm3': 1.0e8, 'electron_fraction_xee': 1.2,
            'ans1': 1.0+i, 'ans2': 2.0+i, 'ans3': 3.0+i,
            'ans4': 4.0+i, 'ans5': 5.0+i, 'ans6': 6.0+i,
        })
        for j, role in enumerate(('forward_offdiag','forward_diag','reverse_offdiag','reverse_diag')):
            terms.append({
                'global_evaluation_ordinal': 60, 'source_order_index': i*4+j+1,
                'source_position': source, 'record': record, 'data_type': 53,
                'rate_type': 7, 'role': role, 'aj1': 1.0, 'aj2': 1.0,
                'cj': 0.0, 'cj2': 0.0,
            })
    radiation = [
        {'global_evaluation_ordinal': 60, 'grid_index': i, 'energy_ev': float(i), 'bremsa': float(i)*10}
        for i in range(1, 5)
    ]
    tau = [
        {'global_evaluation_ordinal': 60, 'continuum_index': i+1, 'tau_in': i/100.0, 'tau_out': 0.0}
        for i in range(44)
    ]
    trace = [
        {'global_evaluation_ordinal': i, 'dsec_call_id': 1, 'dsec_local_evaluation_index': i,
         'temperature_k': 60000.0, 'hydrogen_density_cm3': 1.0e8, 'electron_fraction_xee': 1.2}
        for i in range(1, 61)
    ]
    _write_csv(tmp_path / capture.RECORDS_NAME, records)
    _write_csv(tmp_path / capture.TERMS_NAME, terms)
    _write_csv(tmp_path / capture.RADIATION_NAME, radiation)
    _write_csv(tmp_path / capture.TAU_NAME, tau)
    _write_csv(tmp_path / capture.TRACE_NAME, trace)
    (tmp_path / capture.REPORT_NAME).write_text(json.dumps({
        'actual_dsec_runtime_capture': True,
        'capture_kind': 'actual_v06472_dsec_type53_row46_independent_runtime_state_capture',
        'target_evaluation_ordinal': 60,
    }))
    result = capture.verify(tmp_path)
    assert result['result'] == 'ACCEPT'
    assert result['records'] == 44
    assert result['matrix_terms'] == 176
    assert result['record_tau_workspace_ieee_exact'] == 44
