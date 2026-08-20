from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"

def test_version():
    assert 'version = "0.6.82.30.8.6"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.30.8.6' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()

def test_deferred_revisit_retention_is_elided():
    text = CPP.read_text()
    assert 'if (!defer_product_projection && record.data_type == 53 && record.rate_type == 7)' in text
    assert 'else if (!defer_product_projection && record.data_type == 49 && record.rate_type == 7)' in text

def test_deferred_errc_maps_are_elided():
    text = CPP.read_text()
    needle = 'if (!defer_product_projection) {\n            for (std::size_t k = 0; k < evaluated.size() && k < evaluated_records.size(); ++k) {'
    assert needle in text

def test_deferred_spectral_publication_is_elided():
    text = CPP.read_text()
    assert 'Skip constructing the line/RRC publication stream in that hot path.' in text
    assert 'if (!defer_product_projection) {\n        for (std::size_t k = 0; k < evaluated.size(); ++k) {' in text

def test_reuses_context_identity_index():
    text = CPP.read_text()
    assert 'pprint4_record_by_identity_v06823086' in text
    assert 'ctx.record_index_by_identity_v064895.find' in text
    assert 'pprint4_record_by_identity_v068229338;' not in text

def test_unused_contribution_copy_removed():
    text = CPP.read_text()
    assert 'preclosure_contributions' not in text
