from __future__ import annotations

import sys
import types

import numpy as np
import pytest

# output_writers imports Astropy at module import time even though these policy
# tests never perform FITS I/O.  Keep this unit test independent of the optional
# local Astropy installation.
if "astropy.io.fits" not in sys.modules:
    _astropy = types.ModuleType("astropy")
    _astropy_io = types.ModuleType("astropy.io")
    _fits = types.ModuleType("astropy.io.fits")
    _astropy.io = _astropy_io
    _astropy_io.fits = _fits
    sys.modules.setdefault("astropy", _astropy)
    sys.modules.setdefault("astropy.io", _astropy_io)
    sys.modules.setdefault("astropy.io.fits", _fits)

from xstar_tools.xstar import cpp_backend_emissivity
from xstar_tools.xstar.output_writers import (
    OutputWriterPortError,
    _binemis_validation_fixture,
    build_binemis_spectrum,
)


_POLICY_ENV = (
    "XSTAR_ATOMIC_BACKEND",
    "XSTAR_ATOMIC_EMISSIVITY_BACKEND",
    "XSTAR_ATOMIC_EMISSIVITY_BINEMIS_CPP",
    "XSTAR_ATOMIC_EMISSIVITY_BINEMIS_PRODUCT_CPP",
    "XSTAR_ATOMIC_EMISSIVITY_BINEMIS_SHADOW_CPP",
    "XSTAR_V064810_FORCE_PYTHON_BINEMIS",
    "XSTAR_V064810_ALLOW_PYTHON_BINEMIS_FALLBACK",
)


def _clear_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _POLICY_ENV:
        monkeypatch.delenv(name, raising=False)


def _call(timing: dict[str, float] | None = None) -> np.ndarray:
    metadata, a = _binemis_validation_fixture()
    return build_binemis_spectrum(
        metadata=metadata,
        xlum=1.0e10,
        temperature_1e4K=100.0,
        turbulent_velocity_km_s=50.0,
        epi_eV=a["epi"],
        ncn2=a["ncn2"],
        dpthc=a["dpthc"],
        elum=a["elum"],
        zrems=a["zrems"],
        zremsz=a["zremsz"],
        timing=timing,
    )


def test_v064810_cpp_backend_auto_promotes_product(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_policy(monkeypatch)
    monkeypatch.setenv("XSTAR_ATOMIC_BACKEND", "cpp")
    called = {"count": 0}

    def fake_cpp(**kwargs):
        called["count"] += 1
        original = np.asarray(kwargs["zrems"], dtype=float)
        out = original.copy()
        out[2, 7] = 123.5
        return out, {"cpp_profile_lines_attempted": 1.0, "cpp_profile_lines_applied": 1.0, "cpp_profile_slots": 1.0}, "ok"

    monkeypatch.setattr(cpp_backend_emissivity, "build_binemis_profile_cpp", fake_cpp)
    timing: dict[str, float] = {}
    out = _call(timing)
    assert called["count"] == 1
    assert out[2, 7] == 123.5
    assert timing["final_product_build.spectrum.binemis_v064810_accelerated_cpp_selected"] == 1.0
    assert timing["final_product_build.spectrum.binemis_v064810_auto_product_promotion"] == 1.0
    assert timing["final_product_build.spectrum.binemis_cpp_product_enabled"] == 1.0


def test_v064810_pure_python_does_not_auto_promote(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_policy(monkeypatch)
    monkeypatch.setenv("XSTAR_ATOMIC_BACKEND", "python")

    def forbidden(**kwargs):
        raise AssertionError("pure Python must not call C++ binemis")

    monkeypatch.setattr(cpp_backend_emissivity, "build_binemis_profile_cpp", forbidden)
    timing: dict[str, float] = {}
    out = _call(timing)
    assert np.isfinite(out).all()
    assert timing["final_product_build.spectrum.binemis_v064810_accelerated_cpp_selected"] == 0.0
    assert timing["final_product_build.spectrum.binemis_v064810_auto_product_promotion"] == 0.0


def test_v064810_force_python_is_same_process_ab_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_policy(monkeypatch)
    monkeypatch.setenv("XSTAR_ATOMIC_BACKEND", "cpp")
    monkeypatch.setenv("XSTAR_V064810_FORCE_PYTHON_BINEMIS", "1")

    def forbidden(**kwargs):
        raise AssertionError("force-Python switch must bypass C++ binemis")

    monkeypatch.setattr(cpp_backend_emissivity, "build_binemis_profile_cpp", forbidden)
    timing: dict[str, float] = {}
    out = _call(timing)
    assert np.isfinite(out).all()
    assert timing["final_product_build.spectrum.binemis_v064810_force_python"] == 1.0


def test_v064810_required_cpp_product_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_policy(monkeypatch)
    monkeypatch.setenv("XSTAR_ATOMIC_EMISSIVITY_BACKEND", "cpp")

    def broken(**kwargs):
        raise RuntimeError("synthetic backend failure")

    monkeypatch.setattr(cpp_backend_emissivity, "build_binemis_profile_cpp", broken)
    with pytest.raises(OutputWriterPortError, match="accelerated Python selected the C\\+\\+ binemis"):
        _call({})
