from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

import xstar_atomic as xa
from xstar_atomic.source_port import load_atomic_database_state, run_bounded_radial_multipass
from xstar_atomic.source_port import physical_runner as runner
from xstar_atomic.source_port.physical_output_parity import _physical_header_values
from xstar_atomic.source_port.output_writers import (
    LevelOutputMetadata,
    SourceOutputMetadata,
    _detail_level_vector,
    _state_temperature_t4,
)
from xstar_atomic.source_port.physical_output_parity import _step_log_vectors
from xstar_atomic.source_port.radial_transfer import _build_radial_validation_state

_HELPER_PATH = Path(__file__).with_name("test_source_port_atomic_database_v041.py")
_HELPER_SPEC = importlib.util.spec_from_file_location(
    "xstar_atomic_test_source_port_atomic_database_v041_v0476", _HELPER_PATH
)
assert _HELPER_SPEC is not None and _HELPER_SPEC.loader is not None
_HELPER_MODULE = importlib.util.module_from_spec(_HELPER_SPEC)
_HELPER_SPEC.loader.exec_module(_HELPER_MODULE)
_write_mini_atdb = _HELPER_MODULE._write_mini_atdb


def test_v0476_production_analytic_first_pass_uses_source_stop_predicate():
    state = _build_radial_validation_state(zone_index=1)
    state.control["bounded_radial_validation_mode"] = False
    state.control["xpxcol"] = 1.0
    result = run_bounded_radial_multipass(
        state,
        first_pass_shell_count=1,  # nsteps is not a physical shell cap.
        pass_count=1,
    )
    radial_pass = result.pass_results[0]
    assert len(radial_pass.shell_results) > 1
    assert radial_pass.termination_reason == "column_limit"
    assert "xcol<xpxcol" in radial_pass.source_loop_predicate



def test_v0476_first_pass_temperature_predicate_converts_kelvin_to_t4():
    from xstar_atomic.source_port.radial_control import first_pass_shell_condition

    state = _build_radial_validation_state(zone_index=1)
    state.control.update({"tinf": 0.099, "xpxcol": 1.0e40, "xeemin": -1.0})
    state.plasma.temperature = 990.0
    assert first_pass_shell_condition(state) is True
    state.plasma.temperature = 970.0
    assert first_pass_shell_condition(state) is False

def test_v0476_detail_adapter_strips_exactly_one_source_guard():
    metadata = SourceOutputMetadata(
        levels=(
            LevelOutputMetadata(1, 1, 0.0, "h_i", 1, "ground", 1),
            LevelOutputMetadata(3, 1, 2.0, "h_i", 1, "upper", 3),
        ),
        lines=(),
        rrcs=(),
    )
    guarded = np.asarray([0.0, 11.0, 22.0, 33.0])
    assert _detail_level_vector(guarded, metadata).tolist() == [11.0, 22.0, 33.0]
    guardless = np.asarray([11.0, 22.0, 33.0])
    assert _detail_level_vector(guardless, metadata).tolist() == [11.0, 22.0, 33.0]


def test_v0476_metadata_pairs_global_rows_with_source_local_ordinals(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    built = load_atomic_database_state(atdb, llinabs=True)
    try:
        # Swap the two packed local level IDs while retaining the setptrs global
        # record-order mapping.  Source fstepr pairs npilev(mm,ion) with the
        # leveltemp slot mm, so global row 1 must now carry the record-4 label.
        for recno, new_local in ((3, 2), (4, 1)):
            header = built.master.header(recno)
            built.master.idat1[header.int_ptr + header.nint - 2] = new_local
        metadata = runner.build_source_output_metadata(built.master, built.derived)
        first = next(row for row in metadata.levels if row.global_index == 1)
        second = next(row for row in metadata.levels if row.global_index == 2)
        assert (first.level_label, first.upper_index) == ("2p", 1)
        assert (second.level_label, second.upper_index) == ("1s", 2)
        assert metadata.provenance["metadata_builder"] == "vectorized_numpy_v3_source_local_ordinals_rrc_thresholds"
        assert runner.OUTPUT_METADATA_CACHE_FORMAT_VERSION == 3
    finally:
        built.atomic_state.close()


def test_v0476_step_log_parser_accepts_current_one_integer_source_row():
    row = " " + " ".join(["1.00"] * 11) + "  7"
    zones, finals = _step_log_vectors(row)
    assert len(zones) == 1
    assert zones[0].shape == (12,)
    assert zones[0][-1] == 7.0
    assert finals == []


def test_v0476_step_log_parser_normalizes_optional_legacy_second_integer():
    one = " " + " ".join(["1.00"] * 11) + "  7"
    two = one + " -2"
    zones_one, _ = _step_log_vectors(one)
    zones_two, _ = _step_log_vectors(two)
    assert np.array_equal(zones_one[0], zones_two[0])


def test_v0476_version():
    assert xa.__version__ == "0.4.87"


def test_v0476_rrc_threshold_uses_source_level_limit_minus_excitation():
    level = LevelOutputMetadata(2, 1, 10.2, "h_i", 1, "2p", 2)
    assert runner._source_rrc_threshold_eV(level, 13.6, 99.0) == pytest.approx(3.4)
    assert runner._source_rrc_threshold_eV(None, None, 24.6) == pytest.approx(24.6)


def test_v0476_physical_temperature_unit_does_not_misrender_990_kelvin():
    state = _build_radial_validation_state(zone_index=1)
    state.control["plasma_temperature_unit"] = "K"
    state.plasma.temperature = 990.0
    assert _state_temperature_t4(state) == pytest.approx(0.099)


def test_v0476_comparator_excludes_fits_tbcol_layout_keywords():
    from astropy.io import fits

    header = fits.Header()
    header["TBCOL1"] = 1
    header["TBCOL2"] = 9
    header["PHYSVAL"] = 2.5
    assert _physical_header_values(header) == {"PHYSVAL": 2.5}


def test_v0476_compact_dsec_diagnostics_retains_python_thermal_trials():
    from types import SimpleNamespace

    state = _build_radial_validation_state(zone_index=3)
    state.transfer.zone_index = 3
    state.transfer.pass_index = 2
    fixed = SimpleNamespace(
        temperature_k=73198.4,
        electron_fraction_xee=1.20207,
        elcter=1.0e-8,
        hmctot=-6.3e-3,
        httot=1.422e-23,
        cltot=1.431e-23,
        htt={6: 2.77e-24},
        cll={6: 2.15e-24},
        htt2={6: 2.77e-24},
        cll2={6: 2.15e-24},
        element_results=[],
        ion_fractions={(6, 5): 0.0178, (6, 6): 0.2689, (6, 7): 0.7133},
    )
    evaluator = SimpleNamespace(evaluations=[SimpleNamespace(fixed_state_result=fixed)])
    dsec_result = SimpleNamespace(
        lnerr=0,
        ntotit=1,
        charge_converged=True,
        thermal_converged=False,
        state=SimpleNamespace(temperature_k=73198.4),
        final_hmctot=-6.3e-3,
        final_elcter=1.0e-8,
    )
    runner._compact_dsec_diagnostics(state, evaluator, dsec_result)
    compact = state.control["physical_dsec_compact_diagnostics"]
    assert compact["evaluations"][0]["temperature_K"] == pytest.approx(73198.4)
    assert compact["evaluations"][0]["carbon_cooling"] == pytest.approx(2.15e-24)
    assert compact["shells"][0]["pass_index"] == 2
    assert compact["shells"][0]["zone_index"] == 3
