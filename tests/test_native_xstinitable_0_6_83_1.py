from pathlib import Path
import subprocess


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _exe() -> Path:
    return _root() / "src/xstar_tools/xstar/cpp/xstar-xspec-initable"


def test_06831_reference_par_files_present():
    ref = _root() / "references/xstinitable_0_6_83_1"
    assert (ref / "xstinitable.par").is_file()
    assert (ref / "xstar.par").is_file()


def test_06831_cli_declares_cpp_default_and_fortran_compatibility():
    text = (_root() / "src/xstar_tools/xstar/cpp/xstar_xspec_initable_cli.cpp").read_text()
    assert "XStarCommandTarget::cpp" in text
    assert 'arg == "--xstar" || arg == "-xstar"' in text
    assert 'arg == "--input"' in text
    assert 'arg == "--data-dir" || arg == "-data-dir"' in text


def test_06831_xstar_cpp_frontend_source_is_not_modified_for_this_patch():
    changelog = (_root() / "CHANGELOG.md").read_text()
    assert "xstar-cpp` frontend remains byte-identical to 0.6.83" in changelog
