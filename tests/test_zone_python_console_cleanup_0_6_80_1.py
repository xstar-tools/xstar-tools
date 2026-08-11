from __future__ import annotations

import os
from pathlib import Path

from xstar_tools import execution

ROOT = Path(__file__).resolve().parents[1]
SUPPRESS = "XSTAR_SUPPRESS_LEGACY_CONSOLE_DIAGNOSTICS"


def test_zone_python_public_environment_suppresses_legacy_console(monkeypatch):
    monkeypatch.delenv(SUPPRESS, raising=False)
    with execution._backend_environment(execution.resolve_mode("zone-python")):
        assert os.environ[SUPPRESS] == "1"
    assert SUPPRESS not in os.environ


def test_zone_python_explicit_debug_override_is_preserved(monkeypatch):
    monkeypatch.setenv(SUPPRESS, "0")
    with execution._backend_environment(execution.resolve_mode("zone-python")):
        assert os.environ[SUPPRESS] == "0"
    assert os.environ[SUPPRESS] == "0"


def test_other_public_modes_do_not_install_console_suppression(monkeypatch):
    monkeypatch.delenv(SUPPRESS, raising=False)
    for mode in ("pure-python", "zone-cpp", "zone-all", "xstar-cpp"):
        with execution._backend_environment(execution.resolve_mode(mode)):
            assert SUPPRESS not in os.environ


def test_exact_six_legacy_markers_are_guarded():
    opacity = (ROOT / "src/xstar_tools/xstar/cpp/opacity_kernels.cpp").read_text(encoding="utf-8")
    local = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text(encoding="utf-8")
    assert 'standalone_native && !env_truthy("XSTAR_SUPPRESS_LEGACY_CONSOLE_DIAGNOSTICS")' in opacity
    assert local.count('if (!environment_flag("XSTAR_SUPPRESS_LEGACY_CONSOLE_DIAGNOSTICS"))') == 2
    markers = (
        "V064896_TYPE50_MODE=",
        "V048746255172582_PATCH520144_CALC_EMIS_REVISIT_SOURCE_SEQUENCE=",
        "V048746255172582_PATCH520144_TYPE53_SELECTED_REVISIT_SELECTED=",
        "V048746255172582_PATCH520144_TYPE53_SELECTED_REVISIT_PUBLISHED=",
        "V048746255172582_PATCH520144_TYPE49_SELECTED_REVISIT_SELECTED=",
        "V048746255172582_PATCH520144_TYPE49_SELECTED_REVISIT_PUBLISHED=",
    )
    combined = opacity + local
    assert combined.count(markers[0]) == 2  # optimized vs forced-legacy values
    for marker in markers[1:]:
        assert combined.count(marker) == 1
