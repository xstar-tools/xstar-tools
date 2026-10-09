"""Packaging-only regressions: no frozen XSTAR science source is modified."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/packaging/prepare_conda_linux_aarch64.py'


def helper():
    spec = importlib.util.spec_from_file_location('conda_arm64_prepare', SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_sdist(tmp_path):
    name = 'xstar_tools-0.6.91.5.tar.gz'
    path = tmp_path / name
    path.write_bytes(b'validating conda recipe pinning only')
    return path


def test_exact_local_recipe_uses_current_package_version_and_checksum(tmp_path):
    module = helper()
    sdist = make_sdist(tmp_path)
    info = module.prepare_recipe(ROOT, sdist, tmp_path / 'recipe', 'local')
    recipe = (tmp_path / 'recipe/recipe.yaml').read_text()
    assert info['version'] == '0.6.91.5'
    assert sdist.resolve().as_uri() in recipe
    assert 'version: "0.6.91.5"' in recipe
    assert hashlib.sha256(sdist.read_bytes()).hexdigest() in recipe
    assert '  skip: win' in recipe
    assert '    - cfitsio' in recipe
    assert '  number: 0' in recipe


def test_feedstock_recipe_retains_public_url_without_fake_hash(tmp_path):
    module = helper()
    sdist = make_sdist(tmp_path)
    approved_sha = hashlib.sha256(sdist.read_bytes()).hexdigest()
    info = module.prepare_recipe(ROOT, sdist, tmp_path / 'recipe', 'feedstock', approved_sha)
    recipe = (tmp_path / 'recipe/recipe.yaml').read_text()
    assert 'https://pypi.org/packages/source/x/xstar-tools/xstar_tools-${{ version }}.tar.gz' in recipe
    assert info['sha256'] in recipe
    assert 'version: "0.6.91.5"' in recipe


def test_feedstock_mode_requires_verified_public_digest(tmp_path):
    module = helper()
    sdist = make_sdist(tmp_path)
    with pytest.raises(ValueError, match='independently verified'):
        module.prepare_recipe(ROOT, sdist, tmp_path / 'recipe', 'feedstock')


def test_bad_sdist_name_fails_closed(tmp_path):
    module = helper()
    wrong = tmp_path / 'xstar_tools-0.6.91.4.tar.gz'
    wrong.write_bytes(b'old release')
    with pytest.raises(ValueError, match='sdist filename'):
        module.prepare_recipe(ROOT, wrong, tmp_path / 'recipe', 'local')


def test_feedstock_provider_enablement_preserves_existing_host(tmp_path):
    module = helper()
    source = tmp_path / 'conda-forge.yml'
    source.write_text('conda_build_tool: rattler-build\nprovider:\n  osx_arm64: azure\n')
    output = tmp_path / 'enabled.yml'
    module.enable_feedstock(source, output)
    text = output.read_text()
    assert '  linux_aarch64: default' in text
    assert '  osx_arm64: azure' in text
    assert text.count('linux_aarch64:') == 1


def test_explicitly_disabled_provider_is_enabled_only_in_proposal(tmp_path):
    module = helper()
    source = tmp_path / 'conda-forge.yml'
    source.write_text('provider:\n  linux_aarch64: None\n  osx_arm64: azure\n')
    output = tmp_path / 'proposal.yml'
    module.enable_feedstock(source, output)
    assert 'linux_aarch64: default' in output.read_text()
    assert 'linux_aarch64: None' in source.read_text()


def test_provider_missing_rejected(tmp_path):
    module = helper()
    source = tmp_path / 'conda-forge.yml'
    source.write_text('github:\n  branch_name: main\n')
    with pytest.raises(ValueError, match='no top-level provider'):
        module.enable_feedstock(source, tmp_path / 'proposal.yml')


def test_architecture_and_data_contracts_are_explicit():
    science = (ROOT / 'tools/qualification/run_conda_linux_arm64_host_0_6_91_5.py').read_text()
    assert "int.from_bytes(e[18:20], 'little')==183" in science
    assert "'atdb.fits'" in science
    assert 'libcfitsio.so' in science
    assert "result['host_result']='ACCEPT'" in science
    assert 'check_parity_freeze.py' in science


def test_github_workflow_is_native_and_does_not_publish():
    workflow = (ROOT / '.github/workflows/conda-linux-aarch64.yml').read_text()
    assert 'runs-on: ubuntu-24.04-arm' in workflow
    assert 'rattler-build build' in workflow
    assert 'python=3.13' in workflow
    assert '--target-platform linux-aarch64' in workflow
    assert 'twine upload' not in workflow
    assert 'anaconda upload' not in workflow
    assert 'atdb.fits' not in workflow


def test_science_revision_stays_independent_of_package_version():
    code = (ROOT / 'src/xstar_tools/__init__.py').read_text()
    assert '__version__ = "0.6.90.5.5"' in code
    assert 'version = "0.6.91.5"' in (ROOT / 'pyproject.toml').read_text()
