from __future__ import annotations

import csv
from pathlib import Path

import xstar_atomic as xa
from xstar_atomic.source_port import zone1_dsec_probe_analysis as analysis
from xstar_atomic.source_port.dsec import DsecPortError
import pytest


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_v0480_raw_probe_fingerprints_stream_without_read_materialization(
    tmp_path: Path, monkeypatch
) -> None:
    call = 10
    unrelated = 99
    _write(
        tmp_path / "xstar_calc_hmc_all_input_continuum_probe.csv",
        [
            {"calc_hmc_all_call_id": call, "grid_index": 1, "epi_eV": 1.0, "bremsa": 2.0, "bremsint": 3.0},
            {"calc_hmc_all_call_id": call, "grid_index": 2, "epi_eV": 4.0, "bremsa": 5.0, "bremsint": 6.0},
            {"calc_hmc_all_call_id": unrelated, "grid_index": 1, "epi_eV": 100.0, "bremsa": 100.0, "bremsint": 100.0},
        ],
    )
    _write(
        tmp_path / "xstar_calc_hmc_all_input_tau0_probe.csv",
        [{"calc_hmc_all_call_id": call, "line_index": 1, "tau_in": 0.1, "tau_out": 0.2}],
    )
    _write(
        tmp_path / "xstar_calc_hmc_all_input_tauc_probe.csv",
        [{"calc_hmc_all_call_id": call, "continuum_index": 1, "tau_in": 0.3, "tau_out": 0.4}],
    )
    _write(
        tmp_path / "xstar_calc_hmc_all_input_global_levels_probe.csv",
        [{"calc_hmc_all_call_id": call, "global_level_index": 1, "xilevg": 0.5, "bilevg": 0.6, "rnisg": 0.7}],
    )
    _write(
        tmp_path / "xstar_calc_hmc_all_input_leveltemp_probe.csv",
        [{"calc_hmc_all_call_id": call, "row_index": 1, "column_index": 2, "slot": 3, "rlev": 8.0, "ilev": 9}],
    )
    _write(
        tmp_path / "xstar_zone1_calc_hmc_all_input_elements_probe.csv",
        [{"calc_hmc_all_call_id": call, "element_index": 6, "abundance": 1.0e-4, "mml": 4, "mmu": 6}],
    )
    _write(
        tmp_path / "xstar_zone1_calc_hmc_all_input_klev_probe.csv",
        [{"calc_hmc_all_call_id": call, "column_index": 1, "klev_hex": "414243"}],
    )
    summary = {
        "calc_hmc_all_call_id": call,
        "temperature_t4": 7.0,
        "temperature_k": 70000.0,
        "trad": 1.0,
        "radius_cm": 2.0,
        "zone_thickness_cm": 3.0,
        "electron_fraction_xee": 1.2,
        "hydrogen_density_cm3": 1.0e8,
        "covering_fraction": 1.0,
        "pressure": 0.0,
        "lcdd": 1,
        "zeta": 0.0,
        "turbulent_velocity_km_s": 0.0,
        "critf": 1.0e-6,
        "ncn2": 9999,
    }
    _write(tmp_path / "xstar_calc_hmc_all_input_summary_probe.csv", [summary])

    # The old v0.4.79 implementation reached this path through _read(), which
    # materialized each complete CSV.  The streaming implementation must not.
    monkeypatch.setattr(
        analysis,
        "_read",
        lambda path: (_ for _ in ()).throw(AssertionError(f"_read used for {path}")),
    )
    progress: list[str] = []
    rows = analysis._numeric_fingerprint_rows(
        tmp_path, {call: 1}, progress=progress.append
    )
    assert len(rows) == 17
    by_name = {row["name"]: row for row in rows}
    expected = analysis._fingerprint(
        call=call,
        evaluation=1,
        name="radiation.epim",
        values=[(1, 1.0), (2, 4.0)],
    )
    assert by_name["radiation.epim"] == expected
    assert by_name["leveltemp_workspace.klev"]["sha256"] == analysis._fingerprint(
        call=call,
        evaluation=1,
        name="leveltemp_workspace.klev",
        values=[(1, "414243")],
    )["sha256"]
    assert any(item.startswith("fingerprint_file_start") for item in progress)
    assert any(item.startswith("fingerprint_file_done") for item in progress)
    assert xa.__version__ == "0.4.82"


def test_v0481_type15_probe_files_are_optional_when_no_selected_data_type15_record(
    tmp_path: Path,
) -> None:
    progress: list[str] = []
    shells, effective = analysis._load_type15_probe_rows(
        tmp_path,
        target_call=10,
        civ_raw=[{
            "record": "6077",
            "data_type": "59",
        }, {
            "record": "6176",
            "data_type": "95",
        }],
        progress=progress.append,
    )
    assert shells == {}
    assert effective == {}
    assert progress == [
        "type15_probe_not_applicable selected_civ_data_type15_records=0"
    ]


def test_v0481_type15_probe_files_remain_required_when_data_type15_is_selected(
    tmp_path: Path,
) -> None:
    with pytest.raises(DsecPortError, match="xstar_zone1_type15_shell_probe.csv"):
        analysis._load_type15_probe_rows(
            tmp_path,
            target_call=10,
            civ_raw=[{
                "record": "123",
                "data_type": "15",
            }],
        )
