from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
from types import SimpleNamespace
import zipfile

import numpy as np
import pytest

import xstar_atomic.source_port.ion_balance as ib
import xstar_atomic.source_port.ucalc as ucalc_module
from xstar_atomic.source_port import (
    CalcIonRatesContext,
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcStatus,
    default_derived_pointer_cache_path,
    load_atomic_database_state,
)
from xstar_atomic.source_port import physical_runner as runner

_HELPER_PATH = Path(__file__).with_name("test_source_port_atomic_database_v041.py")
_HELPER_SPEC = importlib.util.spec_from_file_location(
    "xstar_atomic_test_source_port_atomic_database_v041_v0484", _HELPER_PATH
)
assert _HELPER_SPEC is not None and _HELPER_SPEC.loader is not None
_HELPER_MODULE = importlib.util.module_from_spec(_HELPER_SPEC)
_HELPER_SPEC.loader.exec_module(_HELPER_MODULE)
_write_mini_atdb = _HELPER_MODULE._write_mini_atdb


def _corrupt_npz_member(path: Path, member: str) -> None:
    """Flip one stored .npy payload byte without updating its ZIP CRC."""
    with zipfile.ZipFile(path, "r") as archive:
        info = archive.getinfo(member)
    with path.open("r+b") as handle:
        handle.seek(info.header_offset)
        local_header = handle.read(30)
        assert local_header[:4] == b"PK\x03\x04"
        name_len, extra_len = struct.unpack_from("<HH", local_header, 26)
        data_offset = info.header_offset + 30 + name_len + extra_len
        # Keep the NPY header intact and corrupt numeric payload bytes.
        offset = data_offset + min(max(128, info.file_size // 2), info.file_size - 1)
        handle.seek(offset)
        original = handle.read(1)
        assert original
        handle.seek(offset)
        handle.write(bytes([original[0] ^ 0x01]))


class _Master:
    def __init__(self) -> None:
        self.headers = {101: SimpleNamespace(data_type=53, rate_type=7)}
        self.ints = {101: np.asarray([1, 0], dtype=int)}

    def header(self, record: int):
        return self.headers[record]

    def record_integers(self, record: int):
        return self.ints[record]

    def record_reals(self, record: int):
        return np.asarray([13.6], dtype=float)


class _CaptureDispatcher:
    def __init__(self) -> None:
        self.lfast_values: list[int] = []

    def evaluate_record_number(self, master, record, context, **kwargs):
        self.lfast_values.append(int(context.lfast))
        return SimpleNamespace(
            status=UCalcStatus.EVALUATED,
            idest1=1,
            idest2=2,
            ans1=2.0,
            ans2=3.0,
            ans3=4.0,
            ans4=5.0,
            ans5=6.0,
            ans6=7.0,
            reason="",
            diagnostics={"observed_lfast": int(context.lfast)},
        )


def test_calc_ion_rates_owns_literal_lfpi_one(monkeypatch):
    monkeypatch.setattr(ib, "build_level_table", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(ib, "_parent_destination_context", lambda *args, **kwargs: ({}, {}))
    npfi = np.zeros((16, 2), dtype=int)
    npfi[7, 1] = 101
    derived = SimpleNamespace(
        n_ions=1,
        ion_records=np.asarray([0, 900]),
        ion_element_z=np.asarray([0, 6]),
        ion_stage=np.asarray([0, 4]),
        nlevs=np.asarray([0, 2]),
        npfi=npfi,
        npnxt=np.zeros(102, dtype=int),
        npar=np.pad(np.asarray([900]), (101, 0)),
    )
    derived.npar[101] = 900
    dispatcher = _CaptureDispatcher()
    result = ib.calc_ion_rates(
        _Master(), derived, ion_index=1,
        context=CalcIonRatesContext(
            temperature_k=73198.4,
            hydrogen_density_cm3=1.0e8,
            electron_fraction_xee=1.2,
            lfast=2,
        ),
        dispatcher=dispatcher,
    )
    assert dispatcher.lfast_values == [1]
    assert result.contributions[0].diagnostics["observed_lfast"] == 1


def _type59_context_with_excited_parent() -> UCalcContext:
    epi = np.geomspace(10.0, 2.0e3, 257)
    return UCalcContext(
        temperature_k=73198.407060,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2020726184,
        nlev=22,
        levels=UCalcLevelTable(
            levels={
                1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0),
                22: UCalcLevel(22, energy_ev=64.5, statistical_weight=4.0),
            },
            nlev=22,
        ),
        radiation=SimpleNamespace(
            epim_eV=epi,
            bremsam=np.full(epi.size, 2.5e10),
            bremsint=np.full(epi.size, 1.0),
        ),
        lfast=4,
        extras={
            "parent_level_energy_ev_by_destination": {26: 12.5},
            "parent_level_stat_weight_by_destination": {26: 8.0},
        },
    )


def _type59_excited_parent_record(threshold: float) -> UCalcRecord:
    # -4 offset=5 maps nlevp=22 to destination 26.
    return UCalcRecord(
        6077, 59, 1, 19,
        (threshold, 30.0, 2.0, 1.5, 2.5, 0.2),
        (0, 0, 2, 5, 3, 1, 4),
    )


def test_type59_uses_literal_nbinc_bin_and_excited_parent_weight(monkeypatch):
    context = _type59_context_with_excited_parent()
    epi = context.radiation.epim_eV
    # Select a threshold for which huntf's nearest bin is below the threshold.
    threshold = None
    nb1 = None
    for left, right in zip(epi[:-1], epi[1:]):
        candidate = float(left * 1.01)
        found = ucalc_module._xstar_nbinc_fortran_value(candidate, epi)
        if float(epi[found - 1]) < candidate:
            threshold, nb1 = candidate, found
            break
    assert threshold is not None and nb1 is not None
    captured: dict[str, np.ndarray | float | int] = {}
    original = ucalc_module._phintfo_exact

    def capture(*, sigma_cm2, threshold_ev, context, swrat):
        captured["sigma"] = np.asarray(sigma_cm2).copy()
        captured["swrat"] = float(swrat)
        captured["lfast"] = int(context.lfast)
        return original(
            sigma_cm2=sigma_cm2,
            threshold_ev=threshold_ev,
            context=context,
            swrat=swrat,
        )

    monkeypatch.setattr(ucalc_module, "_phintfo_exact", capture)
    result = SourceFaithfulUCalc().evaluate(
        _type59_excited_parent_record(float(threshold)), context
    )
    assert result.status is UCalcStatus.EVALUATED
    assert result.idest2 == 26
    assert np.asarray(captured["sigma"])[nb1 - 1] > 0.0
    assert captured["swrat"] == pytest.approx(2.0 / 8.0)
    assert captured["lfast"] == 1
    assert result.diagnostics["type59_ggup"] == pytest.approx(8.0)
    assert result.diagnostics["type59_excited_parent_destination"] is True
    assert result.diagnostics["type59_sigma_grid_policy"] == "literal_nbinc_enxt_one_based"


def test_corrupt_pointer_npz_member_is_rebuilt_atomically(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    cache = default_derived_pointer_cache_path(atdb)
    first = load_atomic_database_state(atdb, pointer_cache=cache, use_pointer_cache=True)
    first.atomic_state.close()
    _corrupt_npz_member(cache, "npfi.npy")

    rebuilt = load_atomic_database_state(atdb, pointer_cache=cache, use_pointer_cache=True)
    try:
        assert rebuilt.derived.provenance["pointer_cache_status"] == "corrupt_rebuilt"
        assert rebuilt.derived.provenance["pointer_cache_failure"] == "BadZipFile"
    finally:
        rebuilt.atomic_state.close()
    hit = load_atomic_database_state(atdb, pointer_cache=cache, use_pointer_cache=True)
    try:
        assert hit.derived.provenance["pointer_cache_status"] == "hit"
    finally:
        hit.atomic_state.close()


def test_corrupt_output_metadata_npz_member_is_rebuilt_atomically(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    built = load_atomic_database_state(atdb, llinabs=True)
    try:
        cache = runner.default_output_metadata_cache_path(atdb)
        metadata = runner._load_or_build_source_output_metadata(
            built.master, built.derived,
            cache_path=cache, use_cache=True, rebuild_cache=False,
        )
        assert metadata.provenance["metadata_cache_status"] == "miss_written"
        _corrupt_npz_member(cache, "line_upper_level.npy")
        rebuilt = runner._load_or_build_source_output_metadata(
            built.master, built.derived,
            cache_path=cache, use_cache=True, rebuild_cache=False,
        )
        assert rebuilt.provenance["metadata_cache_status"] == "corrupt_rebuilt"
        assert rebuilt.provenance["metadata_cache_failure"] == "BadZipFile"
        hit = runner._load_or_build_source_output_metadata(
            built.master, built.derived,
            cache_path=cache, use_cache=True, rebuild_cache=False,
        )
        assert hit.provenance["metadata_cache_status"] == "hit"
    finally:
        built.atomic_state.close()
