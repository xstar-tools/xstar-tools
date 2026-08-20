from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"


def test_version():
    assert 'version = "0.6.82.30.8.7"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.30.8.7' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()


def test_bound_free_payload_is_lazy_copy_on_write():
    text = CPP.read_text()
    assert "struct BoundFreeEvaluatedPayloadV06823087" in text
    assert "std::shared_ptr<BoundFreeEvaluatedPayloadV06823087> bound_free_payload_v06823087" in text
    assert "else if (!bound_free_payload_v06823087.unique())" in text
    assert "std::make_shared<BoundFreeEvaluatedPayloadV06823087>(*bound_free_payload_v06823087)" in text


def test_large_type53_shadows_are_not_inline_in_evaluated_record():
    text = CPP.read_text()
    start = text.index("struct EvaluatedRecord {")
    end = text.index("struct PreliminaryCachedRecordV064812337", start)
    block = text[start:end]
    assert "Type53SourceShadow type53_shadow{};" not in block
    assert "Type53SourceShadow type49_shadow{};" not in block
    assert "bound_free_payload_v06823087" in block


def test_deferred_native_production_element_diagnostics_are_elided():
    text = CPP.read_text()
    assert "retain_element_diagnostics_v06823087" in text
    assert "!defer_product_projection || !native_production_v064897" in text
    assert "if (retain_element_diagnostics_v06823087) {" in text
    assert 'XSTAR_V06823087_FORCE_ELEMENT_DIAGNOSTICS' in text


def test_accepted_type82_orientation_remains_present():
    runtime = (ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp").read_text()
    assert "case 82:" in runtime
    assert "energy_order_pair(ii[0],ii[1]);" in runtime
