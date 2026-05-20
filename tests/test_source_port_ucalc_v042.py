from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from xstar_atomic.source_port import (
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcStatus,
    load_atomic_database_state,
    write_ucalc_subsystem_products,
)


def _vector_hdu(name: str, values: np.ndarray, code: str) -> fits.BinTableHDU:
    values = np.asarray(values)
    col = fits.Column(name="DATA", format=f"{len(values)}{code}", array=[values])
    hdu = fits.BinTableHDU.from_columns([col], name=name)
    hdu.header["LENGTH"] = len(values)
    return hdu


def _write_ucalc_atdb(path: Path) -> None:
    records = [
        dict(dt=13, rt=11, reals=[1.0, 1.0], ints=[1, 1], chars=b"H"),
        dict(dt=14, rt=12, reals=[13.6], ints=[1, 1], chars=b"H I"),
        dict(dt=6, rt=13, reals=[0.0, 2.0, 13.6, 13.6], ints=[1, 101], chars=b"1s"),
        dict(dt=6, rt=13, reals=[10.2, 6.0, 13.6, 13.6], ints=[2, 102], chars=b"2p"),
        dict(dt=1, rt=1, reals=[2.0, 0.5], ints=[1, 1], chars=b"rr"),
        dict(dt=50, rt=4, reals=[1215.67, 0.0, 6.265e8, 1.0], ints=[2, 1, 1], chars=b"lya"),
        dict(dt=0, rt=0, reals=[], ints=[], chars=b""),
    ]
    pointers = []
    reals: list[float] = []
    integers: list[int] = []
    chars: list[int] = []
    for recno, rec in enumerate(records, start=1):
        rp, ip, kp = len(reals) + 1, len(integers) + 1, len(chars) + 1
        reals.extend(rec["reals"])
        integers.extend(rec["ints"])
        chars.extend(rec["chars"])
        pointers.append(
            [
                recno,
                rec["dt"],
                rec["rt"],
                0,
                len(rec["reals"]),
                len(rec["ints"]),
                len(rec["chars"]),
                rp,
                ip,
                kp,
            ]
        )
    primary = fits.PrimaryHDU()
    primary.header["DATE"] = "2026-06-17"
    primary.header["CREATOR"] = "pytest-ucalc-atdb"
    hdul = fits.HDUList(
        [
            primary,
            _vector_hdu("POINTERS", np.asarray(pointers, np.int32).reshape(-1), "J"),
            _vector_hdu("REALS", np.asarray(reals, np.float32), "E"),
            _vector_hdu("INTEGERS", np.asarray(integers, np.int32), "J"),
            _vector_hdu("CHARS", np.asarray(chars, np.uint8), "B"),
        ]
    )
    hdul["POINTERS"].header["LENGTH"] = len(records)
    hdul.writeto(path)


def _levels() -> UCalcLevelTable:
    return UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0, ionization_potential_ev=13.6),
            2: UCalcLevel(2, energy_ev=10.2, statistical_weight=6.0, ionization_potential_ev=13.6),
        },
        nlev=2,
    )


def test_complete_catalog_has_every_source_label_and_no_untranslated_branch():
    ucalc = SourceFaithfulUCalc()
    coverage = ucalc.coverage()
    assert ucalc.registered_data_types == tuple(range(1, 103))
    assert len(ucalc.native_data_types) == 76
    assert len(ucalc.source_noop_data_types) == 26
    assert ucalc.untranslated_data_types == ()
    assert coverage["complete_source_branch_translation_ready"] is True
    assert coverage["n_untranslated"] == 0
    assert set(ucalc.native_data_types).isdisjoint(ucalc.source_noop_data_types)


def test_every_label_returns_structured_result_without_silent_fallback():
    ucalc = SourceFaithfulUCalc()
    context = UCalcContext(temperature_k=1.0e6)
    for data_type in range(1, 103):
        record = UCalcRecord(data_type, data_type, 0, 0, (), ())
        result = ucalc.evaluate(record, context, strict=False)
        assert result.data_type == data_type
        assert result.provenance.source_label == data_type
        assert result.provenance.implementation in {"native_python", "source_noop"}
        assert result.status is not UCalcStatus.UNTRANSLATED


def test_source_noop_precedes_indonly_like_fortran_goto_9000():
    ucalc = SourceFaithfulUCalc()
    context = UCalcContext(temperature_k=1.0e6, nlev=79, indonly=True)
    for data_type in (13, 14, 84, 93, 94, 100):
        result = ucalc.evaluate(
            UCalcRecord(data_type, data_type, 7, 0, (), (1, 2, 3, 4)),
            context,
        )
        assert result.status is UCalcStatus.SOURCE_NOOP
        assert (result.idest1, result.idest2) == (0, 0)


def test_type1_executes_formula_and_returns_full_fortran_contract():
    ucalc = SourceFaithfulUCalc()
    context = UCalcContext(
        temperature_k=1.0e4,
        hydrogen_density_cm3=10.0,
        electron_fraction_xee=2.0,
    )
    result = ucalc.evaluate(UCalcRecord(5, 1, 1, 0, (2.0, 0.5), (1, 1)), context)
    assert result.status is UCalcStatus.EVALUATED
    assert result.ans1 == pytest.approx(40.0)
    assert (result.ans2, result.ans3, result.ans4, result.ans5, result.ans6) == (0, 0, 0, 0, 0)
    assert (result.idest1, result.idest2, result.idest3, result.idest4) == (1, 0, 1, 2)
    row = result.to_dict()
    assert row["source_file"].endswith("ucalc.f90")
    assert row["implementation"] == "native_python"
    assert "temperature_k" in row["context_fields_used"]


def test_type12_uses_type36_endpoint_rule_in_index_only_mode():
    ucalc = SourceFaithfulUCalc()
    context = UCalcContext(temperature_k=1.0e6, nlev=9, indonly=True)
    result = ucalc.evaluate(UCalcRecord(12, 12, 7, 0, (), (1, 1, 7)), context)
    assert result.status is UCalcStatus.INDEX_ONLY
    assert result.idest1 == 1
    assert result.idest2 == 9


def test_context_required_branch_is_explicitly_blocked_not_approximated():
    ucalc = SourceFaithfulUCalc()
    context = UCalcContext(temperature_k=1.0e6, nlev=2, levels=_levels())
    result = ucalc.evaluate(
        UCalcRecord(53, 53, 7, 0, (1.0, 1.0), (1, 1, 1, 1)),
        context,
        strict=False,
    )
    assert result.status is UCalcStatus.CONTEXT_BLOCKED
    assert result.ready is False
    assert result.ans1 == result.ans2 == 0.0
    assert "radiation" in result.reason or "cross-section" in result.reason


def test_packed_decode_and_product_writer_cover_active_data_types(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_ucalc_atdb(atdb)
    built = load_atomic_database_state(atdb)
    try:
        dispatcher = SourceFaithfulUCalc()
        decoded = dispatcher.decode_record(built.master, 5, parent_record=2)
        assert (decoded.data_type, decoded.rate_type) == (1, 1)
        assert decoded.reals == pytest.approx((2.0, 0.5))
        assert decoded.parent_record == 2

        outputs = write_ucalc_subsystem_products(
            built.master, built.derived, tmp_path / "products", dispatcher
        )
        summary = json.loads(outputs["json"].read_text())
        assert summary["n_registered_data_types"] == 102
        assert summary["n_untranslated_data_types"] == 0
        assert summary["packed_record_decode_ready"] is True
        assert summary["complete_ucalc_control_flow_ready"] is True
        assert summary["full_atdb_numerical_evaluation_performed"] is False
        assert outputs["branch_catalog_csv"].is_file()
        assert outputs["data_type_inventory_csv"].is_file()
        assert outputs["index_only_samples_csv"].is_file()
    finally:
        built.atomic_state.close()


def test_ucalc_cli_writes_products_and_public_api(tmp_path: Path, capsys):
    from xstar_atomic.source_port_ucalc_cli import main
    import xstar_atomic as xa

    atdb = tmp_path / "atdb.fits"
    _write_ucalc_atdb(atdb)
    out = tmp_path / "ucalc"
    assert main(["--atdb", str(atdb), "--out-dir", str(out), "--print-summary"]) == 0
    text = capsys.readouterr().out
    assert "n_registered_data_types=102" in text
    assert "n_untranslated_data_types=0" in text
    assert "complete_ucalc_control_flow_ready=True" in text
    assert (out / "xstar_ucalc_branch_catalog.csv").is_file()
    assert (out / "xstar_ucalc_subsystem_summary.json").is_file()
    assert xa.__version__ == "0.4.37"
    assert xa.SourceFaithfulUCalc is SourceFaithfulUCalc
    assert "SourceFaithfulUCalc" in xa.__all__


def test_legacy_default_dispatcher_delegates_to_complete_authoritative_path():
    from xstar_atomic.source_port import default_ucalc_dispatcher

    legacy = default_ucalc_dispatcher()
    assert legacy.supported_data_types == tuple(range(1, 103))
    result = legacy.evaluate(1, UCalcRecord(1, 1, 1, 0, (2.0, 0.5), (1, 1)),
                             UCalcContext(temperature_k=1.0e4, hydrogen_density_cm3=2.0, electron_fraction_xee=3.0))
    assert result.status is UCalcStatus.EVALUATED
    assert result.ans1 == pytest.approx(12.0)


def test_type74_uses_live_radiation_accepts_zero_alpha_and_source_endpoints():
    from types import SimpleNamespace

    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0),
            2: UCalcLevel(2, energy_ev=10.0, statistical_weight=4.0),
            3: UCalcLevel(3, energy_ev=100.0, statistical_weight=6.0),
            41: UCalcLevel(41, energy_ev=20.0, statistical_weight=2.0),
        },
        nlev=3,
    )
    radiation = SimpleNamespace(
        epim_eV=np.asarray([100.0, 500.0, 1000.0]),
        bremsam=np.asarray([1.0e10, 2.0e10, 3.0e10]),
        bremsint=np.zeros(3),
    )
    context = UCalcContext(
        temperature_k=7.665518557758832e4,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2046560563936872,
        nlev=3,
        levels=levels,
        radiation=radiation,
    )
    # xt, two resonance energies in Ryd, then two delta heights.  At this
    # temperature both DR exponent arguments exceed the source cutoff, so
    # alpha=0 is a legitimate evaluated result, not a rejected record.
    record = UCalcRecord(21769, 74, 7, 0, (1.0, 30.0, 40.0, 2.0, 3.0), (41, 7))
    result = SourceFaithfulUCalc().evaluate(record, context)

    e1 = (30.0 + 1.0) * 13.60569253
    e2 = (40.0 + 1.0) * 13.60569253
    b1 = 1.0e10 + (2.0e10 - 1.0e10) * (e1 - 100.0) / 400.0
    b2 = 2.0e10 + (3.0e10 - 2.0e10) * (e2 - 500.0) / 500.0
    expected_rate = (2.0 * b1 + 3.0 * b2) * 4.752e-22

    assert result.status is UCalcStatus.EVALUATED
    assert result.ans1 == pytest.approx(expected_rate)
    assert result.ans2 == 0.0
    assert (result.idest1, result.idest2, result.idest3, result.idest4) == (41, 3, 7, 8)
    assert result.diagnostics["source_zero_reverse_rate"] is True


def test_type95_uses_eint_e1_not_scaled_expint_em1():
    from xstar_atomic.xstar_element_solver import _xstar_eint

    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0),
            2: UCalcLevel(2, energy_ev=13.6, statistical_weight=4.0),
        },
        nlev=2,
    )
    context = UCalcContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2,
        nlev=2,
        levels=levels,
    )
    # ee, tmin, three transformed-temperature knots, three rho knots.
    reals = (10.0, 0.0, 0.0, 0.5, 0.9, 1.0, 2.0, 3.0)
    record = UCalcRecord(17362, 95, 5, 0, reals, (1, 1, 7))
    result = SourceFaithfulUCalc().evaluate(record, context)

    tt = (0.861707 * 100.0) / 10.0
    xx = 1.0 - 0.693147 / math.log(tt + 2.0)
    rho = 2.0 + (xx - 0.5) * (3.0 - 2.0) / (0.9 - 0.5)
    e1, _, _ = _xstar_eint(1.0 / tt)
    expected = 1.0e-6 * e1 * rho / math.sqrt(tt * 10.0**3) * context.electron_density_cm3

    assert result.status is UCalcStatus.EVALUATED
    assert result.ans1 == pytest.approx(expected)
    assert result.diagnostics["e1"] == pytest.approx(e1)
    assert (result.idest1, result.idest2) == (1, 2)


def test_type57_uses_literal_ucalc_eth_and_ground_gate(monkeypatch):
    """Label 57 passes ep=eth, not the absolute parent continuum energy."""
    import xstar_atomic.xstar_element_solver as solver

    calls = []

    def fake_calt57(te, den2, e, ep, n):
        calls.append((te, den2, e, ep, n))
        return {
            "python_eval_status": "evaluated_type57_calt57_diagnostic",
            "type57_cion_cm3_s": 2.0e-9,
            "type57_crec_cm6_s": 5.0e-20,
        }

    monkeypatch.setattr(solver, "_xstar_calt57", fake_calt57)
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0, principal_n=1),
            2: UCalcLevel(2, energy_ev=60.0, statistical_weight=4.0, principal_n=3),
            3: UCalcLevel(
                3,
                energy_ev=100.0,
                continuum_energy_ev=999.0,
                statistical_weight=2.0,
            ),
        },
        nlev=3,
    )
    context = UCalcContext(
        temperature_k=7.665518557758832e4,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2,
        nlev=3,
        levels=levels,
    )
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(9001, 57, 5, 0, (), (3, 2, 8)), context
    )

    assert calls == [pytest.approx((context.temperature_k, 1.2e8, 60.0, 40.0, 3))]
    assert result.status is UCalcStatus.EVALUATED
    assert (result.idest1, result.idest2) == (2, 3)
    assert result.ans1 == pytest.approx(2.0e-9 * 1.2e8)
    assert result.ans2 == pytest.approx(5.0e-20 * (4.0 / 2.0) * (1.2e8**2))
    assert result.diagnostics["type57_ucalc_energy_convention"] == "e1_rlev1_ep_eth"
    assert result.diagnostics["type57_ep_ev"] == pytest.approx(40.0)

    # ucalc exits before calt57 for idest1 <= 1.  The endpoint contract remains
    # visible, but both rates are exactly zero and the kernel is not called.
    ground = SourceFaithfulUCalc().evaluate(
        UCalcRecord(9002, 57, 5, 0, (), (1, 1, 8)), context
    )
    assert len(calls) == 1
    assert ground.status is UCalcStatus.EVALUATED
    assert (ground.idest1, ground.idest2) == (1, 3)
    assert ground.ans1 == ground.ans2 == 0.0
    assert ground.diagnostics["python_eval_status"] == "type57_ucalc_gate_zero"
