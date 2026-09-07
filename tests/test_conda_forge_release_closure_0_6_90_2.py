from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASED_VERSION = "0.6.89.5"
RELEASED_SHA256 = "961b66b0ce0b3bc966a6322a3bef05e65879e1f09d50e8d4b9527030ad7a91b2"


def test_qualification_version_and_frozen_license() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.6.90.2"' in pyproject
    assert 'license = "GPL-3.0-only"' in pyproject
    assert 'description = "Python/C++ tools for XSTAR atomic data and high-performance runtimes"' in pyproject
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text(encoding="utf-8")
    assert "PACKAGE_VERSION ?= 0.6.90.2" in makefile


def test_embedded_recipe_remains_exact_released_package_contract() -> None:
    recipe = (ROOT / "conda/recipe/recipe.yaml").read_text(encoding="utf-8")
    assert recipe.startswith("schema_version: 1\n")
    assert f'version: "{RELEASED_VERSION}"' in recipe
    assert RELEASED_SHA256 in recipe
    assert "https://pypi.org/packages/source/x/xstar-tools/xstar_tools-${{ version }}.tar.gz" in recipe
    assert "skip: win" in recipe
    assert "license: GPL-3.0-only" in recipe
    assert "  number: 1\n" in recipe
    assert "summary: Python/C++ tools for XSTAR atomic data and high-performance runtimes" in recipe
    assert "xstar-tools provides Python/C++ tools for XSTAR atomic data, and the native" in recipe
    assert "The atomic database `atdb.fits` is not bundled with the package" in recipe


def test_readme_documents_conda_and_keeps_project_links_user_facing() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "conda install -c conda-forge xstar-tools" in readme
    tail = readme.split("Project links:\n", 1)[1]
    block = tail.split("\n\n", 1)[0]
    lines = [line for line in block.splitlines() if line.startswith("- ")]
    assert lines == [
        "- GitHub: <https://github.com/xstar-tools/xstar-tools>",
        "- PyPI: <https://pypi.org/project/xstar-tools/>",
        "- Conda-forge: <https://anaconda.org/conda-forge/xstar-tools>",
    ]
    assert "Feedstock:" not in block
    assert "TestPyPI" not in block
    assert "Windows conda packages are not supported" in readme
    assert "no planned MSVC or Windows MPI implementation" in readme
    assert "Windows MPI is not planned" in readme


def test_release_closure_manifest_freezes_science_and_abis() -> None:
    import json

    manifest = json.loads((ROOT / "qualification/conda_forge_release_closure_0_6_90_2.json").read_text(encoding="utf-8"))
    assert manifest["distribution_version"] == "0.6.90.2"
    assert manifest["predecessor_version"] == "0.6.90.1"
    assert manifest["released_conda_package_version"] == RELEASED_VERSION
    assert manifest["released_conda_source_sha256"] == RELEASED_SHA256
    assert manifest["released_conda_feedstock_build_number"] == 1
    assert manifest["released_source_recipe_build_number"] == 1
    assert manifest["osx_arm64_publication_required"] is True
    assert manifest["windows_conda_native"] == "unsupported"
    assert manifest["windows_msvc"] == "not-planned"
    assert manifest["windows_mpi"] == "not-planned"
    assert manifest["windows_native_distribution"] == "pypi-msys2-ucrt64-mingw"
    assert manifest["science_change"] is False
    assert manifest["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert manifest["abi_change"] is False
    assert (manifest["c_api_abi"], manifest["production_zone_abi"], manifest["fixed_state_abi"], manifest["xspec_table_abi"]) == (60487, 6048110, 60486, 1)


def test_host_runner_installs_public_conda_package_and_checks_runtime_contract() -> None:
    runner = (ROOT / "tools/qualification/run_conda_forge_release_closure_host_0_6_90_2.py").read_text(encoding="utf-8")
    for token in (
        'RELEASED_VERSION = "0.6.89.5"',
        'RELEASED_CONDA_BUILD_NUMBER = 1',
        RELEASED_SHA256,
        "micromamba",
        "xstar-tools=0.6.89.5",
        "xstar-cpp",
        "xstar-xspec",
        "doctor",
        "bremsstrahlung",
        "NO_VENDORED_CFITSIO",
        "NO_MPI_EXECUTABLE",
        "NO_PYTHON_EMBED_PLUGIN",
        "ATDB_EXTERNAL",
        "LICENSE_GPL_3_0_ONLY",
        "parse_micromamba_list",
        'payload.get("packages", [])',
    ):
        assert token in runner


def test_host_runner_verifies_live_feedstock() -> None:
    runner = (ROOT / "tools/qualification/run_conda_forge_release_closure_host_0_6_90_2.py").read_text(encoding="utf-8")
    assert "https://raw.githubusercontent.com/conda-forge/xstar-tools-feedstock/main/recipe/recipe.yaml" in runner
    assert "https://raw.githubusercontent.com/conda-forge/xstar-tools-feedstock/main/recipe/build.sh" in runner
    assert "LIVE_FEEDSTOCK_RECIPE" in runner
    assert "canonical_recipe_text" in runner
    assert "live_feedstock_recipe.diff" in runner
    assert "LIVE_FEEDSTOCK_RECIPE_LOCAL_SHA256" in runner
    assert "LIVE_FEEDSTOCK_RECIPE_REMOTE_SHA256" in runner
    assert "LIVE_FEEDSTOCK_BUILD_SH" in runner
    assert "canonical_live_recipe == canonical_local_recipe" in runner
    assert "normalize_feedstock_recipe_build_number" not in runner


def test_three_host_public_conda_workflow() -> None:
    workflow = (ROOT / ".github/workflows/conda-forge-release-closure.yml").read_text(encoding="utf-8")
    for token in ("ubuntu-24.04", "macos-15", "macos-15-intel", "linux-64", "osx-arm64", "osx-64"):
        assert token in workflow
    assert "mamba-org/setup-micromamba@v3" in workflow
    assert "run_conda_forge_release_closure_host_0_6_90_2.py" in workflow
    assert "rattler-build" not in workflow
    assert "windows-latest" not in workflow
    assert "!run_conda_forge_release_closure_06902_${{ matrix.target-platform }}/public-conda-env/**" in workflow


def test_micromamba_json_contract_uses_packages_array_and_platform_field() -> None:
    runner = (ROOT / "tools/qualification/run_conda_forge_release_closure_host_0_6_90_2.py").read_text(encoding="utf-8")
    assert 'payload.get("packages", [])' in runner
    assert 'xstar_meta.get("platform", xstar_meta.get("subdir"))' in runner
    assert 'xstar_meta.get("build_number") == RELEASED_CONDA_BUILD_NUMBER' in runner


def test_recipe_canonicalizer_ignores_transport_only_whitespace() -> None:
    import importlib.util

    path = ROOT / "tools/qualification/run_conda_forge_release_closure_host_0_6_90_2.py"
    spec = importlib.util.spec_from_file_location("conda_release_closure_06902_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    canonical = module.canonical_recipe_text
    base = "schema_version: 1\n\nbuild:\n  number: 1\n"
    transported = "schema_version: 1  \r\n\r\nbuild:\r\n  number: 1   \r\n\r\n"
    assert canonical(base) == canonical(transported)
    assert canonical(base) != canonical(base.replace("number: 1", "number: 2"))
