from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src" / "xstar_tools" / "xstar" / "cpp"


def test_first_evaluation_ntotit_diagnostics_are_debug_gated():
    text = (CPP / "xstar_standalone.cpp").read_text(encoding="utf-8")
    assert "terminal_diagnostics_enabled_v069056() &&\n        data.call_index == 1u" in text
    assert "terminal_diagnostics_enabled_v069056() &&\n            snapshot.call_index == 1u" in text


def test_profiling_console_summary_is_debug_only_but_artifact_path_remains():
    text = (CPP / "xstar_standalone.cpp").read_text(encoding="utf-8")
    assert text.count("if (terminal_diagnostics_enabled_v069056()) write(std::cout);") >= 2
    assert "DETAIL_POPULATION_SECONDS=" in text
    assert "PUBLIC_SPECT_SECONDS=" in text
    assert 'output/"standalone_diagnostics"/"timing"' in text


def test_legacy_stdio_diagnostics_are_suppressed_in_normal_production():
    text = (CPP / "xstar_standalone.cpp").read_text(encoding="utf-8")
    assert '"XSTAR_SUPPRESS_LEGACY_CONSOLE_DIAGNOSTICS", "1", 1' in text
    opacity = (CPP / "opacity_kernels.cpp").read_text(encoding="utf-8")
    assert "XSTAR_SUPPRESS_LEGACY_CONSOLE_DIAGNOSTICS" in opacity
    assert "V064896_TYPE50_MODE=OPTIMIZED_STANDALONE" in opacity
