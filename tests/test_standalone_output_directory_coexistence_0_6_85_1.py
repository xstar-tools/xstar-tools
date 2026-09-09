from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"




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


