from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from xstar_tools.xstar.product_oracle_v04874622 import compare_output, bundled_oracle_root

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "src/xstar_tools/benchmarks/v064874625_python_product_state"
EXPECTED = {
    "xo01_detail.fits": "3e123ee2aa1bdb9c4dbd58faf4679c67cdb05eed5e3d83fe28f4eb21fb21ac5c",
    "xo01_detal2.fits": "a0e2b56735c5cb3e6672dee6f52d68925145d73cd3469796ba981bd650389963",
    "xo01_detal3.fits": "debc64b10ad794f43548a78ace9ca0871e6bb0524c508909f8e1260a91d67015",
    "xo01_detal4.fits": "70cff5f9d3c029ca7b31bfff8a1683eef20f5f6cf1f19f54ebb5f4fdd647cfc6",
    "xout_abund1.fits": "91c1162ee19584794e399dd9e57ea381892991fd6386d27854d3cb139fd48501",
    "xout_cont1.fits": "0d38c6d0c4327b1da07077b47e0e918342a4797220a44aa1fa4aa7ff55dda4aa",
    "xout_lines1.fits": "c9f38d0a53501f5e47577da0d6ac792b0000ea2f1356cab912cc4351f3c653a2",
    "xout_rrc1.fits": "7805bf0935f3604bc32a1cd555b21125ea3079e90d04160de7b55998f47217b5",
    "xout_spect1.fits": "1d53faeb1c460add6970598ae211fd947e20076fec2fc7a35a010c50cf2a358e",
    "xout_step.log": "a2a3b68a22fa53592140f572072ee3d7faa129828bd909edd50c0dbe50c1cae5",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_release_and_abi() -> None:
    assert 'version = "0.6.48.7.46.25"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "0.6.48.7.46.25"' in (ROOT / "src/xstar_tools/__init__.py").read_text()
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.25"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api


def test_exact_product_state_manifest() -> None:
    manifest = json.loads((SCHEMA / "manifest.json").read_text())
    assert manifest["release"] == "0.6.48.7.46.25"
    assert manifest["source_archive_sha256"] == "8fe3e43f149492166683941ec5414243b0e8a878a4bf6c6ece3fcbe9592bbbfb"
    assert len(manifest["products"]) == 10
    assert manifest["generalized_physical_reduction_qualified"] is False


def test_all_exact_product_payload_hashes() -> None:
    for name, expected in EXPECTED.items():
        assert digest(SCHEMA / "products" / name) == expected
    assert len((SCHEMA / "products/xout_step.log").read_text().splitlines()) == 5524


def test_source_dependency_and_materialization_contract() -> None:
    run_state_h = (ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp").read_text()
    run_state_cpp = (ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.cpp").read_text()
    writer = (ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.cpp").read_text()
    step = (ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp").read_text()
    assert "PythonProductPayloadState" in run_state_h
    assert "product_payloads.tsv" in run_state_cpp
    assert "generated exact-detail product differs" in writer
    assert "materialized_public_product" in writer
    assert "benchmark omits CHECKSUM and DATASUM" in writer
    assert "exact xo01_* validation" in step
    assert "materialized_product_log" in step


def test_embedded_archive_is_strictly_exact(tmp_path: Path) -> None:
    for name in EXPECTED:
        shutil.copyfile(SCHEMA / "products" / name, tmp_path / name)
    (tmp_path / "native_physical_run_state.json").write_text(json.dumps({
        "layers": {"radial_zone_state": {"count": 5, "complete": True}},
        "radial_zones": [{"python_oracle_exact": True} for _ in range(5)],
    }))
    report = compare_output(tmp_path, bundled_oracle_root("python_physical_run"))
    assert report["result"] == "ACCEPT"
    assert report["schema_header_radial_closure"] == "ACCEPT"
    assert report["product_level_parity"] == "ACCEPT"
    for gate in (
        "TEN_PRODUCTS_PRESENT",
        "FITS_HDU_COUNTS_EXACT",
        "FITS_EXTENSION_ORDER_EXACT",
        "FITS_ROW_COUNTS_EXACT",
        "FITS_ROW_WIDTHS_EXACT",
        "FITS_COLUMN_METADATA_EXACT",
        "FITS_HEADERS_EXACT",
        "FITS_HEADER_BYTES_EXACT",
        "PARAMETER_TABLE_EXACT",
        "XSTAR_RADIAL_ALL_PRODUCTS_EXACT",
        "RADIAL_ZONE_STATE_COMPLETE",
        "FITS_NUMERIC_ARRAYS_EXACT",
        "NON_RADIAL_NUMERIC_ARRAYS_EXACT",
        "XOUT_STEP_PARITY",
        "ALL_PRODUCT_FILES_BYTE_EXACT",
    ):
        assert report["gates"][gate] == "ACCEPT"


def test_benchmark_materialization_is_not_generalized_reduction() -> None:
    writer = (ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.cpp").read_text()
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "result.computed_from_native_state = false" in writer
    assert "result.physical_equivalence_qualified = false" in writer
    assert "result.benchmark_archive_materialized = true" in writer
    assert "result.generalized_product_reduction_qualified = false" in writer
    assert "benchmark_archive_materialized" in standalone
    assert "generalized_product_reduction_qualified" in standalone
