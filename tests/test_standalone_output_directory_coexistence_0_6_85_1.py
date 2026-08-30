from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_06851_version_and_scope():
    assert 'version = "0.6.86"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.86" in (CPP / "Makefile").read_text()


def test_06851_standalone_allows_unrelated_files():
    text = (CPP / "xstar_standalone.cpp").read_text()
    assert "file-silent production created a non-product artifact:" not in text
    assert "true production created a non-product artifact:" not in text
    assert "STANDALONE_OUTPUT_DIRECTORY_COEXISTENCE" in text
    assert "publication did not create the XSTAR control-required public products" in text


def test_06851_failure_is_non_destructive():
    text = (CPP / "xstar_standalone.cpp").read_text()
    assert "FAILURE_PRODUCTS_PRESERVED=YES" in text
    assert "PRODUCTS_AUTODELETED=0" in text
    assert "if (!preserve_failure_products_v0682331) remove_native_products(output);" not in text
    assert text.count("remove_native_products(output)") == 0


def test_06851_parallel_orchestrator_preserves_products_by_default():
    text = (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert 'constexpr const char *kPackageVersion = "0.6.86";' in text
    assert "--cleanup-work" in text
    assert "if (opt.cleanup_work)" in text
    assert "XSTAR products are never auto-deleted" in text
    assert "cannot remove stale output" not in text
    assert 'job_dir / "xstar-cpp.success"' in text
    assert "is_regular_file(success_markers[i])" in text
    assert "XSTAR_XSPEC_06851_RESULT=ACCEPT" in text
