from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_serial_native_sources_present_and_versioned():
    assert 'version = "0.6.84"' in (ROOT / "pyproject.toml").read_text()
    assert (CPP / "xstar_xspec_serial.cpp").is_file()
    make = (CPP / "Makefile").read_text()
    assert "XSPEC_SERIAL_EXECUTABLE := xstar-xspec" in make
    assert "PACKAGE_VERSION ?= 0.6.84" in make


def test_serial_driver_uses_cpp_and_direct_initable_contract():
    text = (CPP / "xstar_xspec_serial.cpp").read_text()
    assert '"--xstar", "cpp"' in text
    assert '"--initable", initable_path.string()' in text
    assert '"--output", job_dir.string()' in text
    assert "concatenate_step_logs" in text
    assert "--restart" in text and "--save" in text


def test_table_cli_keeps_legacy_metadata_and_adds_initable():
    text = (CPP / "xstar_xspec_table_cli.cpp").read_text()
    assert 'arg == "--initable"' in text
    assert 'arg == "--metadata"' in text
    writer = (CPP / "xstar_xspec_table_writer.cpp").read_text()
    assert "Config parse_initable_fits" in writer


def test_science_transform_is_not_modified_by_serial_orchestrator():
    table = (CPP / "xstar_xspec_table.cpp").read_text()
    assert "constexpr double kLegacyNormalization = 8.356e-7;" in table
    assert "slice->bin_count = high - low;" in table
