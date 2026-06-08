from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import types

import numpy as np

if "astropy.io.fits" not in sys.modules:
    astropy = types.ModuleType("astropy")
    astropy_io = types.ModuleType("astropy.io")
    astropy_fits = types.ModuleType("astropy.io.fits")
    astropy_io.fits = astropy_fits
    astropy.io = astropy_io
    sys.modules.update({"astropy": astropy, "astropy.io": astropy_io, "astropy.io.fits": astropy_fits})

from xstar_tools.xstar import ion_balance as ib
from xstar_tools.xstar.ion_balance import CalcIonRatesContext
from xstar_tools.xstar.ucalc import UCalcStatus


class _Master:
    def __init__(self) -> None:
        self.headers = {
            101: SimpleNamespace(data_type=49, rate_type=7),
            102: SimpleNamespace(data_type=1, rate_type=1),
            103: SimpleNamespace(data_type=53, rate_type=7),
        }
        self.ints = {key: np.asarray([1, 1], dtype=int) for key in self.headers}

    def header(self, record: int):
        return self.headers[record]

    def record_integers(self, record: int):
        return self.ints[record]


class _Dispatcher:
    def __init__(self) -> None:
        self.records: list[int] = []

    def evaluate_record_number(self, master, record, context, **kwargs):
        self.records.append(int(record))
        return SimpleNamespace(
            status=UCalcStatus.EVALUATED,
            idest1=1,
            idest2=2,
            ans1=1.0,
            ans2=0.0,
            ans3=0.0,
            ans4=0.0,
            ans5=0.0,
            ans6=0.0,
            reason="",
            diagnostics={},
        )


def _cpp_rows(record: int, ans1: float):
    return [{
        "record": record, "data_type": 49 if record == 101 else 53,
        "rate_type": 7, "role": "scalar_pirt", "idest1": 1, "idest2": 2,
        "aj1": ans1, "aj2": 0.0, "cj": 0.0, "cj2": 0.0,
    }]


def test_coarse_product_commits_cpp_results_at_source_positions(monkeypatch) -> None:
    monkeypatch.setattr(ib, "build_level_table", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(ib, "_parent_destination_context", lambda *args, **kwargs: ({}, {}))
    import xstar_tools.xstar.cpp_backend_matrix as cbm
    monkeypatch.setattr(
        cbm, "accumulate_mg_ion_rate7_type49_terms_cpp_detailed",
        lambda **kwargs: (_cpp_rows(101, 1.0e16), "ok", {"cpp_calls": 1.0, "packing_seconds": 0.1, "cpp_kernel_seconds": 0.2}),
    )
    monkeypatch.setattr(
        cbm, "accumulate_mg_ion_rate7_type53_terms_cpp_detailed",
        lambda **kwargs: (_cpp_rows(103, -1.0e16), "ok", {"cpp_calls": 1.0, "packing_seconds": 0.1, "cpp_kernel_seconds": 0.2}),
    )
    for key, value in {
        "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_CPP": "1",
        "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_PRODUCT_CANDIDATE": "1",
        "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_PRODUCT": "1",
        "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_SHADOW": "0",
        "XSTAR_ATOMIC_PRE_MATRIX_MG_RATE7_TYPE53_CPP": "1",
        "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_TYPE53": "1",
        "XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP": "1",
    }.items():
        monkeypatch.setenv(key, value)

    npfi = np.zeros((8, 2), dtype=int)
    npfi[1, 1] = 101
    npfi[2, 1] = 102
    npfi[3, 1] = 103
    npar = np.zeros(104, dtype=int)
    npar[101:104] = 900
    derived = SimpleNamespace(
        n_ions=1, ion_records=np.asarray([0, 900]),
        ion_element_z=np.asarray([0, 12]), ion_stage=np.asarray([0, 1]),
        nlevs=np.asarray([0, 2]), npfi=npfi, npnxt=np.zeros(104, dtype=int), npar=npar,
    )
    control: dict[str, object] = {"profile_components": "none"}
    dispatcher = _Dispatcher()
    result = ib.calc_ion_rates(
        _Master(), derived, ion_index=1,
        context=CalcIonRatesContext(
            temperature_k=1.0e6, hydrogen_density_cm3=1.0e8,
            electron_fraction_xee=1.0, retain_contributions=False,
            reusable_work_arrays={}, profile_control=control,
        ),
        dispatcher=dispatcher,
    )
    # Literal source order: ((1e16 + 1.0) + -1e16) is 0.0 in binary64.
    # The retired family-grouped pre-sum would have produced 1.0.
    assert result.pirti == 0.0
    assert dispatcher.records == [102]
    summary = control["mg_pre_matrix_coarse_cpp_summary"]
    assert summary["cpp_committed_records"] == 2
    assert summary["python_fallback_records"] == 1
    assert summary["source_order_commit"] is True


def test_topology_cache_reuses_source_classification() -> None:
    master = _Master(); cache: dict[object, object] = {}
    selected = [(1, 101), (2, 102), (3, 103)]
    a49, a53, hit1 = ib._mg_pre_matrix_candidate_topology(
        master, ion_index=1, selected_records=selected, cache=cache, enable_type53=True
    )
    b49, b53, hit2 = ib._mg_pre_matrix_candidate_topology(
        master, ion_index=1, selected_records=selected, cache=cache, enable_type53=True
    )
    assert hit1 is False and hit2 is True
    assert a49 == b49 == ((101, 0.5, 0.5),)
    assert a53 == b53 == ((103, 0.5, 0.5),)


def test_v06431_runner_enables_coarse_candidate() -> None:
    root = Path(__file__).parents[1]
    runner = (root / "run_v0431_xstar_tools_mg_prematrix_candidate.sh").read_text()
    assert "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_CPP=1" in runner
    assert "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_PRODUCT_CANDIDATE=1" in runner
    assert "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_PRODUCT=1" in runner
    assert "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_SHADOW=0" in runner
    assert "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_TYPE53=0" in runner


def test_v06431_type53_defaults_to_python_fallback(monkeypatch) -> None:
    monkeypatch.setattr(ib, "build_level_table", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(ib, "_parent_destination_context", lambda *args, **kwargs: ({}, {}))
    import xstar_tools.xstar.cpp_backend_matrix as cbm
    calls = {"type49": 0, "type53": 0}
    def _type49(**kwargs):
        calls["type49"] += 1
        return _cpp_rows(101, 2.0), "ok", {"cpp_calls": 1.0}
    def _type53(**kwargs):
        calls["type53"] += 1
        return _cpp_rows(103, 9.0), "ok", {"cpp_calls": 1.0}
    monkeypatch.setattr(cbm, "accumulate_mg_ion_rate7_type49_terms_cpp_detailed", _type49)
    monkeypatch.setattr(cbm, "accumulate_mg_ion_rate7_type53_terms_cpp_detailed", _type53)
    for key, value in {
        "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_CPP": "1",
        "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_PRODUCT_CANDIDATE": "1",
        "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_PRODUCT": "1",
        "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_SHADOW": "0",
        "XSTAR_ATOMIC_PRE_MATRIX_MG_RATE7_TYPE53_CPP": "1",
        "XSTAR_ATOMIC_PRE_MATRIX_MG_COARSE_TYPE53": "0",
        "XSTAR_ATOMIC_MATRIX_MG_ION_DIRECT_ACCUM_CPP": "1",
    }.items():
        monkeypatch.setenv(key, value)

    npfi = np.zeros((8, 2), dtype=int)
    npfi[1, 1] = 101; npfi[2, 1] = 102; npfi[3, 1] = 103
    npar = np.zeros(104, dtype=int); npar[101:104] = 900
    derived = SimpleNamespace(
        n_ions=1, ion_records=np.asarray([0, 900]),
        ion_element_z=np.asarray([0, 12]), ion_stage=np.asarray([0, 1]),
        nlevs=np.asarray([0, 2]), npfi=npfi, npnxt=np.zeros(104, dtype=int), npar=npar,
    )
    control: dict[str, object] = {"profile_components": "none"}
    dispatcher = _Dispatcher()
    result = ib.calc_ion_rates(
        _Master(), derived, ion_index=1,
        context=CalcIonRatesContext(
            temperature_k=1.0e6, hydrogen_density_cm3=1.0e8,
            electron_fraction_xee=1.0, retain_contributions=False,
            reusable_work_arrays={}, profile_control=control,
        ), dispatcher=dispatcher,
    )
    assert result.pirti == 4.0  # Type-49 C++ 2.0 + two Python records 1.0 each.
    assert dispatcher.records == [102, 103]
    assert calls == {"type49": 1, "type53": 0}
    summary = control["mg_pre_matrix_coarse_cpp_summary"]
    assert summary["cpp_committed_records"] == 1
    assert summary["python_fallback_records"] == 2
    assert summary["selected_type53_records"] == 1
    assert summary["cpp_type53_supported_records"] == 0
    assert summary["type53_product_enabled"] is False
    assert summary["type53_excluded_from_product"] is True
