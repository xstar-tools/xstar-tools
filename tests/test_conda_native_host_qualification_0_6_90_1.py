from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RELEASED_VERSION = "0.6.89.5"
RELEASED_SHA256 = "961b66b0ce0b3bc966a6322a3bef05e65879e1f09d50e8d4b9527030ad7a91b2"


def test_active_qualification_version_license_and_future_conda_profile() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.6.90.1"' in pyproject
    assert 'license = "GPL-3.0-only"' in pyproject
    support = (ROOT / "build_support.py").read_text(encoding="utf-8")
    assert '"conda"' in support
    assert 'return "conda"' in support


def test_conda_recipe_is_exact_released_0_6_89_5_contract() -> None:
    recipe = (ROOT / "conda/recipe/recipe.yaml").read_text(encoding="utf-8")
    assert recipe.startswith("schema_version: 1\n")
    assert f'version: "{RELEASED_VERSION}"' in recipe
    assert RELEASED_SHA256 in recipe
    assert "https://pypi.org/packages/source/x/xstar-tools/xstar_tools-${{ version }}.tar.gz" in recipe
    assert "number: 0" in recipe
    assert "skip: win" in recipe
    assert "compiler('cxx')" in recipe
    assert "stdlib('c')" in recipe
    assert "cfitsio" in recipe
    assert "astropy-base" in recipe
    assert "python_min" not in recipe
    assert "license: GPL-3.0-only" in recipe
    assert "Atomic data file atdb.fits remains external" in recipe
    assert "- atdb.fits" not in recipe and "path: atdb.fits" not in recipe


def test_released_build_script_keeps_0_6_89_5_compatibility_fallback() -> None:
    text = (ROOT / "conda/recipe/build.sh").read_text(encoding="utf-8")
    assert "XSTAR_TOOLS_NATIVE=required" in text
    assert 'build_support._native_make_target("conda") == "conda"' in text
    assert "XSTAR_TOOLS_NATIVE_PROFILE=conda" in text
    assert "XSTAR_TOOLS_NATIVE_PROFILE=pypi-linux" in text
    assert "XSTAR_TOOLS_NATIVE_PROFILE=pypi-macos" in text
    assert "-Wl,-rpath-link,${PREFIX}/lib" in text
    assert "pip install . --no-deps --no-build-isolation" in text


def test_released_recipe_native_test_contract() -> None:
    recipe = (ROOT / "conda/recipe/recipe.yaml").read_text(encoding="utf-8")
    for token in (
        "xstar-tools version",
        "xstar-cpp --version",
        "xstar-cpp --abi",
        "xstar-xspec --version",
        "xstar-tools doctor --require zone-cpp --json",
    ):
        assert token in recipe


def test_host_runner_uses_released_recipe_and_explicit_rattler_variants() -> None:
    runner = (ROOT / "tools/qualification/run_conda_native_host_qualification_host_0_6_90_1.py").read_text(encoding="utf-8")
    assert 'RELEASED_VERSION = "0.6.89.5"' in runner
    assert RELEASED_SHA256 in runner
    assert "variants.yaml" in runner
    assert '"--variant-config"' in runner
    assert "c_stdlib" in runner
    assert "c_stdlib_version" in runner
    assert "sysroot" in runner
    assert "macosx_deployment_target" in runner
    assert "python -m build" not in runner


def test_three_host_workflow_contract() -> None:
    workflow = (ROOT / ".github/workflows/conda-native-host-qualification.yml").read_text(encoding="utf-8")
    for token in ("ubuntu-24.04", "macos-15", "macos-15-intel", "linux-64", "osx-arm64", "osx-64"):
        assert token in workflow
    assert "prefix-dev/rattler-build-action@v0.2.39" in workflow
    assert "windows-latest" not in workflow
    assert '"pytest>=7"' in workflow
    assert '"build>=1"' not in workflow


def test_makefile_conda_target_and_frontend_cfitsio_link() -> None:
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text(encoding="utf-8")
    assert "conda: $(CONDA_TARGETS)" in makefile
    assert "CONDA_STANDALONE_TARGETS" in makefile
    assert "-lxstar_production_zone $(CFITSIO_LIBS) $(CFITSIO_RPATH)" in makefile
