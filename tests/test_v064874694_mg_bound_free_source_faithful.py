from __future__ import annotations

import csv
import gzip
from pathlib import Path
from types import SimpleNamespace

import xstar_tools
from xstar_tools.xstar import mg_bound_free_source_faithful_attribution as audit
from xstar_tools.xstar import native_fixed_program as lowerer


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_release_and_api_version() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.17.2"
    api = (root() / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.17.2"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api


def test_source_leveltemp_replay_retains_higher_columns(monkeypatch) -> None:
    energies = {
        1: {1: 11.0, 2: 12.0, 3: 13.0, 4: 14.0},
        2: {1: 21.0, 2: 22.0},
        3: {1: 31.0, 2: 32.0, 3: 33.0},
    }

    def payload(_master, _derived, ion_index, local_level):
        return 0, energies[ion_index][local_level], 1.0, "", 0, 0

    monkeypatch.setattr(lowerer, "_level_payload", payload)
    blocks = [
        SimpleNamespace(ion_index=1, ion_stage=1, nlev=4),
        SimpleNamespace(ion_index=2, ion_stage=2, nlev=2),
        SimpleNamespace(ion_index=3, ion_stage=3, nlev=3),
    ]
    snapshots, owners = lowerer._build_source_leveltemp_energy_snapshots(
        object(), object(), SimpleNamespace(blocks=blocks)
    )
    assert snapshots[1][4] == 14.0
    assert snapshots[2][1] == 21.0
    assert snapshots[2][2] == 22.0
    assert snapshots[2][3] == 13.0
    assert snapshots[2][4] == 14.0
    assert snapshots[3][1] == 31.0
    assert snapshots[3][3] == 33.0
    assert snapshots[3][4] == 14.0
    assert owners[2][4]["ion_index"] == 1
    assert owners[2][4]["phase"] == "calc_hmc_ion"



def test_type49_lowering_uses_signed_threshold_and_retained_mg_energy(monkeypatch) -> None:
    import numpy as np

    rows = [
        {"energy_ev": 5.0, "statistical_weight": 2.0, "principal_n": 1, "orbital_l": 0},
        {"energy_ev": 20.0, "statistical_weight": 1.0, "principal_n": 0, "orbital_l": 0},
        {"energy_ev": 0.0, "statistical_weight": 4.0, "principal_n": 2, "orbital_l": 1},
    ]
    current = SimpleNamespace(ion_index=1, ion_stage=1, ion_counter=1, nlev=2, compact_start=1)
    parent = SimpleNamespace(ion_index=2, ion_stage=2, ion_counter=2, nlev=2, compact_start=2)
    basis = SimpleNamespace(
        n_rows=3, blocks=[current, parent], role_to_row={(1, 1): 1, (1, 2): 2}
    )
    derived = SimpleNamespace(
        npar=np.asarray([0, 100], dtype=np.int64),
        ion_stage=np.asarray([0, 1, 2], dtype=np.int64),
        ion_element_z=np.asarray([0, 12, 12], dtype=np.int64),
        npconi2=np.asarray([0, 77], dtype=np.int64),
    )
    subset = SimpleNamespace(ion_record_to_index={100: 1})

    class Master:
        def header(self, _rec): return SimpleNamespace(data_type=49, rate_type=7, raw_pointer=1)
        def record_reals(self, _rec): return [0.1, 1.0, 0.2, 0.5]
        def record_integers(self, _rec): return [2, 0, 1, 0]

    def payload(_master, _derived, ion_index, local_level):
        table = {(1, 1): (5.0, 2.0), (1, 2): (20.0, 1.0), (2, 2): (3.0, 4.0)}
        energy, weight = table[(ion_index, local_level)]
        return 0, energy, weight, "", 0, 0

    monkeypatch.setattr(lowerer, "_level_payload", payload)
    monkeypatch.setattr(lowerer, "_level_ionization_potential", lambda *_: 4.0)
    result = lowerer._lower_record(
        Master(), derived, 1, 2, rows, basis, {1: current, 2: parent}, subset,
        {1: {3: 13.5}}, {1: {3: {"ion_index": 99}}},
    )
    context = result["reals"][-7:]
    assert context[0] == -1.0
    assert context[5] == 4.0
    assert context[6] == 13.5
    assert result["ints"] == [77, 999]

def test_type49_signed_threshold_and_source_zero_gate() -> None:
    py = (root() / "src/xstar_tools/xstar/native_fixed_program.py").read_text()
    cpp = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "threshold_ev = float(bound_ionization_potential) - float(bound_energy)" in py
    assert "const bool source_zero_gate = source_threshold <= 0.0;" in cpp
    assert "type49_shadow.source_zero_gate = true" in cpp
    assert "source_zero_nonzero_commit" in (
        root() / "src/xstar_tools/xstar/mg_bound_free_source_faithful_attribution.py"
    ).read_text()


def test_type49_and_type53_use_retained_destination_energy() -> None:
    text = (root() / "src/xstar_tools/xstar/native_fixed_program.py").read_text()
    assert text.count("leveltemp_energy_snapshots.get(ion_index, {}).get(id2, 0.0)") >= 2
    assert "leveltemp_destination_energy = 0.0" not in text


def test_mg_source_faithful_mode_is_separate_and_type50_untouched() -> None:
    text = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "XSTAR_QUALIFICATION_MG_BOUND_FREE_SOURCE_FAITHFUL" in text
    assert "source_faithful_mode" in text
    block = text.split("case XSTAR_FIXED_OPCODE_TYPE50_RADIATIVE_LINE", 1)[1].split(
        "case XSTAR_FIXED_OPCODE_TYPE54_HYDROGENIC_DECAY", 1
    )[0]
    assert "MG_BOUND_FREE_SOURCE_FAITHFUL" not in block
    assert "magnesium_source_faithful" not in block


def _write_diagnostic_files(tmp_path: Path) -> None:
    directory = tmp_path / "native_all61" / "qualification_diagnostics"
    directory.mkdir(parents=True)
    fields = [
        "element_z", "data_type", "record", "ion_index", "ion_stage",
        "lower_row", "upper_row", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
        "type49_threshold_ev", "type49_bound_energy_ev", "type49_continuum_energy_ev",
        "type49_destination_energy_ev", "type49_bound_g", "type49_continuum_g",
        "type49_destination_g", "type49_rnist", "type49_exponent_energy_ev",
        "type49_exponent_dimensionless", "type49_electron_density_cm3",
        "type49_hydrogen_density_cm3", "type49_matrix_density_scale",
        "type49_source_zero_gate", "type49_phextrap_applied",
        "type49_source_faithful_mode", "type49_replacement_applied",
        "type49_runtime_state_abi_used", "type49_committed_nonfinite",
        "type49_committed_implausible", "type49_legacy_max_abs",
        "type49_committed_max_abs", "type49_continuum_index_one_based",
        "type49_dsec_radiation_bin_count", "type49_continuum_tau_count",
        *[f"type49_shadow_ans{i}" for i in range(1, 7)],
        "type53_shadow_threshold_ev", "type53_shadow_bound_energy_ev",
        "type53_shadow_continuum_energy_ev", "type53_shadow_destination_energy_ev",
        "type53_shadow_bound_g", "type53_shadow_continuum_g", "type53_shadow_destination_g",
        "type53_shadow_rnist", "mg_type53_exponent_energy_ev",
        "mg_type53_exponent_dimensionless", "mg_type53_electron_density_cm3",
        "mg_type53_hydrogen_density_cm3", "mg_type53_matrix_density_scale",
        "mg_type53_source_faithful_mode", "mg_type53_replacement_applied",
        "type53_runtime_state_abi_used", "mg_type53_committed_nonfinite",
        "mg_type53_committed_implausible", "mg_type53_legacy_max_abs",
        "mg_type53_committed_max_abs", "type53_continuum_index_one_based",
        "type53_dsec_radiation_bin_count", "type53_continuum_tau_count",
    ]
    base = {
        "element_z": "12", "record": "1", "ion_index": "1", "ion_stage": "1",
        "lower_row": "1", "upper_row": "2", "ans1": "0", "ans2": "0",
        "ans3": "0", "ans4": "0", "ans5": "0", "ans6": "0",
    }
    rows = []
    r49 = dict(base, data_type="49")
    for key in fields:
        if key.startswith("type49_") and key not in r49:
            r49[key] = "0"
    for key in ("type49_bound_g", "type49_continuum_g", "type49_destination_g"):
        r49[key] = "1"
    for key in ("type49_source_zero_gate", "type49_source_faithful_mode", "type49_replacement_applied", "type49_runtime_state_abi_used"):
        r49[key] = "1"
    r49["type49_continuum_index_one_based"] = "1"
    r49["type49_dsec_radiation_bin_count"] = "9999"
    r49["type49_continuum_tau_count"] = "301301"
    rows.append(r49)
    r53 = dict(base, data_type="53", record="2")
    for key in fields:
        if (key.startswith("type53_") or key.startswith("mg_type53_")) and key not in r53:
            r53[key] = "0"
    for key in ("type53_shadow_bound_g", "type53_shadow_continuum_g", "type53_shadow_destination_g"):
        r53[key] = "1"
    for key in ("mg_type53_source_faithful_mode", "mg_type53_replacement_applied", "type53_runtime_state_abi_used"):
        r53[key] = "1"
    r53["type53_continuum_index_one_based"] = "1"
    r53["type53_dsec_radiation_bin_count"] = "9999"
    r53["type53_continuum_tau_count"] = "301301"
    rows.append(r53)
    for sequence in range(1, 62):
        path = directory / f"evaluation_{sequence:04d}_records.csv"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            if sequence == 1:
                writer.writerows(rows)


def _write_empty_causal(tmp_path: Path, extra_row: dict[str, str] | None = None) -> None:
    fields = [
        "sequence", "element_z", "record", "data_type", "ion_stage", "role",
        "classification", "source_present", "native_present", "source_value",
        "native_value", "delta",
    ]
    with gzip.open(tmp_path / "all61_dense_matrix_causal_records.csv.gz", "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        if extra_row:
            writer.writerow(extra_row)


def test_source_faithful_audit_accepts_closed_synthetic_case(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "EXPECTED", {49: 1, 53: 1})
    _write_diagnostic_files(tmp_path)
    _write_empty_causal(tmp_path)
    report = audit.analyze(tmp_path)
    assert report["result"] == "ACCEPT"
    assert report["source_zero_counts"]["49"] == 1
    assert report["gates"]["MG_BOUND_FREE_UNEXPLAINED_RATE_DELTAS_ZERO"] == "ACCEPT"


def test_source_faithful_audit_rejects_material_delta(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "EXPECTED", {49: 1, 53: 1})
    _write_diagnostic_files(tmp_path)
    _write_empty_causal(tmp_path, {
        "sequence": "1", "element_z": "12", "record": "1", "data_type": "49",
        "ion_stage": "1", "role": "forward_diag_loss",
        "classification": "RATE_VALUE_DELTA", "source_present": "1",
        "native_present": "1", "source_value": "1", "native_value": "1.001",
        "delta": "0.001",
    })
    report = audit.analyze(tmp_path)
    assert report["result"] == "REJECT"
    assert report["unexplained_rows"] == 1


def test_runner_enables_source_faithful_mode_and_defers_type50() -> None:
    runner = (root() / "run_v04874694_mg_type49_type53_source_faithful_residual_closure.sh").read_text()
    assert "XSTAR_QUALIFICATION_MG_BOUND_FREE_SOURCE_FAITHFUL=1" in runner
    assert "source_capture_replayed=false" in runner
    assert "native_replay_replayed=true" in runner
    assert '"release":"0.6.48.7.46.17.2"' in runner
    checker = (root() / "check_v04874694_mg_type49_type53_source_faithful.py").read_text()
    assert '"MG_TYPE50_ORIENTATION_CORRECTION": "DEFERRED"' in checker
