from pathlib import Path


def test_native_xstinitable_sources_and_fixture_present():
    root = Path(__file__).resolve().parents[1]
    cpp = root / "src/xstar_tools/xstar/cpp"
    assert (cpp / "xstar_xspec_initable.cpp").is_file()
    assert (cpp / "xstar_xspec_initable_cli.cpp").is_file()
    assert (cpp / "xstar_xspec_initable_internal.hpp").is_file()
    fixture = root / "references/xstinitable_0_6_83"
    assert (fixture / "xstinitable.lis").is_file()
    assert (fixture / "xstinitable.fits").is_file()


def test_native_xstinitable_version_and_make_target():
    root = Path(__file__).resolve().parents[1]
    assert 'version = "0.6.83.2"' in (root / "pyproject.toml").read_text()
    makefile = (root / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    assert "XSPEC_INITABLE_EXECUTABLE := xstar-xspec-initable" in makefile
    assert "xstar_xspec_initable.cpp" in makefile


def test_xstinitable_python_cli_is_no_longer_placeholder():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src/xstar_tools/cli/xstinitable.py").read_text()
    assert "NotImplementedError" not in text
    assert "build_xstinitable" in text
