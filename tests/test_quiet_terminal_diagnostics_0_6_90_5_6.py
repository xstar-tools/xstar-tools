from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src" / "xstar_tools" / "xstar" / "cpp"


def test_public_frontend_exposes_debug_opt_in_without_changing_text_progress_default():
    source = (CPP / "xstar_cpp_frontend.cpp").read_text()
    assert 'std::string progress{"text"};' in source
    assert 'else if(arg=="--debug") input.debug=true;' in source
    assert 'XSTAR_CPP_DEBUG' in source
    assert 'XSTAR_V064897_VERBOSE_CONTROLLER_DIAGNOSTICS' in source
    assert 'if(input.progress=="text" && !frontend_debug_enabled_v069056(input)) return;' in source


def test_run_production_filters_version_tagged_terminal_lines_only_by_default():
    source = (CPP / "xstar_standalone.cpp").read_text()
    assert 'terminal_diagnostics_enabled_v069056' in source
    assert 'VersionDiagnosticFilterBufferV069056' in source
    assert "line[i] == 'V'" in source
    assert "line[i + 1u] >= '0'" in source
    assert 'ScopedVersionDiagnosticFilterV069056 version_filter_v069056' in source
    assert '!terminal_diagnostics_enabled_v069056()' in source


def test_fortran_style_user_progress_and_publication_messages_remain_present():
    source = (CPP / "xstar_standalone.cpp").read_text()
    assert 'pass number=' in source
    assert 'log(r) delr/r log(N) log(xi)' in source
    assert 'final print:           1' in source
    assert 'xstar: Prepping to write spectral data' in source
    assert 'xstar: Done writing spectral data' in source
    assert 'total time' in source
