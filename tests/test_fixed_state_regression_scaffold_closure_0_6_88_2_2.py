from __future__ import annotations

import csv
import json
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
HISTORICAL_60485 = ROOT / "tests/fixtures/historical/v06485_active_family_phase2_fixture"
INVALID_60486 = ROOT / "tests/fixtures/historical/v06486_active_family_phase2_fixture"
SCAFFOLD = ROOT / "tests/fixtures/scaffold/v06486_fixed_state_regression_scaffold"
EXCLUDED_TYPES = {49, 53, 57, 88, 99}
EXPECTED_TYPES = {1, 2, 3, 9, 30, 38, 39, 50, 54, 56, 60, 62, 63, 68, 69, 71, 72, 73, 74, 76, 77, 86, 95}
CALLERS = [
    CPP / "xstar_api.cpp",
    CPP / "xstar_backend_cpp.cpp",
    CPP / "xstar_standalone.cpp",
    CPP / "xstar_standalone_internal.hpp",
]


def make_config() -> dict[str, str]:
    cp = subprocess.run(
        ["make", "-s", "print-config", "PLATFORM=linux"],
        cwd=CPP, text=True, capture_output=True, check=True,
    )
    out: dict[str, str] = {}
    for line in cp.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
    return out


def test_version_and_closure_files_present() -> None:
    assert 'version = "0.6.88.2.2"' in (ROOT / "pyproject.toml").read_text()
    makefile = (CPP / "Makefile").read_text()
    assert "PACKAGE_VERSION ?= 0.6.88.2.2" in makefile
    assert (ROOT / "fixed_state_regression_scaffold_closure_0_6_88_2_2.md").is_file()
    assert (ROOT / "portable_dynamic_library_layer_qualification_closure_0_6_88_2_1_host_rejection.md").is_file()
    assert SCAFFOLD.is_dir()
    assert HISTORICAL_60485.is_dir()
    assert not INVALID_60486.exists()


def test_dynamic_library_contract_remains_present() -> None:
    platform = (CPP / "xstar_platform.hpp").read_text()
    wrapper = (CPP / "xstar_dynamic_library.cpp").read_text()
    assert 'kSharedLibraryExtension = ".so"' in platform
    assert 'kSharedLibraryExtension = ".dylib"' in platform
    assert 'kSharedLibraryExtension = ".dll"' in platform
    assert "LoadLibraryW" in wrapper
    assert "GetProcAddress" in wrapper
    assert "FreeLibrary" in wrapper
    for path in CALLERS:
        text = path.read_text()
        for token in ("dlopen(", "dlsym(", "dlclose(", "dlerror(", "dladdr("):
            assert token not in text
        assert '.so"' not in text


def test_linux_loader_smoke_uses_platform_filesystem_libraries() -> None:
    cfg = make_config()
    filesystem_libs = shlex.split(cfg.get("FILESYSTEM_LIBS", ""))
    assert filesystem_libs == ["-lstdc++fs"], cfg
    with tempfile.TemporaryDirectory(prefix="xstar_dyn_08822_") as td:
        td_path = Path(td)
        plugin = td_path / "plugin.cpp"
        test = td_path / "test.cpp"
        library = td_path / "libxstar_test.so"
        exe = td_path / "test"
        plugin.write_text('extern "C" int xstar_test_symbol(void) { return 8822; }\n')
        test.write_text(
            '#include "xstar_platform.hpp"\n'
            '#include "xstar_dynamic_library.hpp"\n'
            'using fn = int (*)();\n'
            'int main(int argc, char** argv) {\n'
            '  if (argc != 2) return 2;\n'
            '  if (xstar_platform::shared_library_filename("xstar_test") != "libxstar_test.so") return 3;\n'
            "  if (xstar_platform::path_list_separator() != ':') return 4;\n"
            '  auto h = xstar_platform::dynamic_library_open(argv[1], xstar_platform::DynamicLibraryVisibility::local);\n'
            '  if (!h) return 5;\n'
            '  auto f = reinterpret_cast<fn>(xstar_platform::dynamic_library_symbol(h, "xstar_test_symbol"));\n'
            '  if (!f || f() != 8822) return 6;\n'
            '  if (xstar_platform::module_directory(reinterpret_cast<const void*>(&main)).empty()) return 7;\n'
            '  xstar_platform::dynamic_library_close(h);\n'
            '  return 0;\n'
            '}\n'
        )
        subprocess.run(
            ["g++", "-std=c++17", "-fPIC", "-shared", "-o", str(library), str(plugin)],
            check=True, text=True, capture_output=True,
        )
        subprocess.run(
            ["g++", "-std=c++17", f"-I{CPP}", "-o", str(exe), str(test),
             str(CPP / "xstar_dynamic_library.cpp"), "-ldl", *filesystem_libs],
            check=True, text=True, capture_output=True,
        )
        cp = subprocess.run([str(exe), str(library)], text=True, capture_output=True)
        assert cp.returncode == 0, cp.stderr


def test_scaffold_is_current_self_contained_and_nonhistorical() -> None:
    manifest = dict(
        line.split("=", 1) for line in (SCAFFOLD / "manifest.txt").read_text().splitlines()
        if line and "=" in line
    )
    assert manifest["program_abi"] == "60486"
    assert manifest["program_id"] == "v06486_fixed_state_regression_scaffold"
    assert manifest["program_kind"] == "qualification_scaffold"
    assert manifest["active_atdb_lowered"] == "false"
    assert int(manifest["record_count"]) == 23
    assert int(manifest["native_line_count"]) == 23
    assert int(manifest["native_continuum_count"]) == 63

    coverage = json.loads((SCAFFOLD / "coverage.json").read_text())
    assert coverage["record_count"] == 23
    assert set(coverage["included_data_types"]) == EXPECTED_TYPES
    assert set(coverage["excluded_contract_dependent_data_types"]) == EXCLUDED_TYPES
    assert coverage["synthetic_single_ion_topology"] is True

    with (SCAFFOLD / "elements.csv").open() as f:
        elements = list(csv.DictReader(f))
    assert len(elements) == 1
    assert elements[0]["n_ions"] == "1"
    assert elements[0]["n_rows"] == "4"
    assert elements[0]["normalization_row"] == "4"
    assert elements[0]["record_head"] == "0"
    assert elements[0]["record_count"] == "23"

    with (SCAFFOLD / "rows.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4
    assert all(row["ion"] == "1" and row["ion_charge"] == "0" for row in rows)

    with (SCAFFOLD / "records.csv").open() as f:
        reader = csv.DictReader(f)
        records = list(reader)
        assert reader.fieldnames is not None and len(reader.fieldnames) == 21
    assert len(records) == 23
    types = {int(row["data_type"]) for row in records}
    assert types == EXPECTED_TYPES
    assert not (types & EXCLUDED_TYPES)
    assert [int(row["line_index"]) for row in records] == list(range(1, 24))
    assert all(int(row["continuum_index"]) == 0 for row in records)
    assert [int(row["next_index"]) for row in records] == list(range(1, 23)) + [-1]

    # The retained coefficient arrays are unchanged historical source material;
    # the scaffold transformation is topology/record-selection metadata only.
    assert (SCAFFOLD / "reals.txt").read_bytes() == (HISTORICAL_60485 / "reals.txt").read_bytes()
    assert (SCAFFOLD / "ints.txt").read_bytes() == (HISTORICAL_60485 / "ints.txt").read_bytes()


def test_make_test_uses_only_the_scaffold() -> None:
    text = (CPP / "Makefile").read_text()
    test_block = text[text.index("test: all"):text.index("\ninstall: all")]
    assert "tests/fixtures/scaffold/v06486_fixed_state_regression_scaffold" in test_block
    assert "v06486_active_family_phase2_fixture" not in test_block
    assert "v06485_active_family_phase2_fixture" not in test_block
    assert ".v06486_scaffold_output" in test_block
