from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tarfile

from xstar_tools.xstar.product_oracle_v04874622 import bundled_oracle_root, compare_output

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "src/xstar_tools/benchmarks/v064874623_python_fits_schema"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def table_rows(name: str) -> list[dict[str, str]]:
    with (SCHEMA_ROOT / name).open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def test_release_version_and_abi() -> None:
    assert 'version = "0.6.48.7.46.23.1"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "0.6.48.7.46.23.1"' in (ROOT / "src/xstar_tools/__init__.py").read_text()
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.7.46.23.1"' in api
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api


def test_frozen_schema_assets_are_complete_and_hash_exact() -> None:
    manifest = json.loads((SCHEMA_ROOT / "manifest.json").read_text())
    assert len(manifest["products"]) == 9
    assert sum(len(item["hdus"]) for item in manifest["products"].values()) == 45
    assert len(list((SCHEMA_ROOT / "headers").glob("*/hdu_*.bin"))) == 45
    for product, info in manifest["products"].items():
        for hdu in info["hdus"]:
            path = SCHEMA_ROOT / "headers" / product / hdu["file"]
            assert sha256(path) == hdu["header_sha256"]
    assert len(table_rows("parameters.tsv")) == 56
    assert len(table_rows("radial_zones.tsv")) == 5
    assert len(table_rows("abundance_radial_rows.tsv")) == 5
    assert manifest["metadata"]["header_comparison_excludes"] == ["CHECKSUM", "DATASUM"]


def test_exact_parameter_and_radial_state_layers_are_real() -> None:
    header = (ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp").read_text()
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.cpp").read_text()
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    for name in ("ParameterRowState", "AbundanceRadialRowState", "RadialZoneState"):
        assert f"struct {name}" in header
    for field in (
        "radius_cm", "outer_radius_cm", "delta_radius_cm", "column",
        "log_ionization_parameter", "density_cm3", "pressure_dyn_cm2",
        "column_density_cm2", "temperature_t4", "electron_fraction",
    ):
        assert field in header
    assert "load_python_product_schema" in source
    assert "parameter_rows" in source
    assert "abundance_radial_rows" in source
    assert "radial_state_complete" in source
    assert "product_payload_complete" in source
    assert "--product-schema-dir" in standalone
    assert "v0648746231_python_fits_schema" in standalone


def test_writer_uses_canonical_schema_and_no_development_cards() -> None:
    writer = (ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.cpp").read_text()
    assert "apply_python_header_templates" in writer
    assert "fits_write_chksum" in writer
    assert '{"I","20A","E","10A","30A"}' in writer
    for key in ("RINNER", "ROUTER", "RDEL", "COLUMN", "LOGXI", "XEE", "DENSITY", "PRESSURE", "TEMPERAT"):
        assert key in writer
    for forbidden in ('"QUALSTAT"', '"COMPUTED"', '"REPLAY"', '"PRODUCT"', '"SPECMODE"'):
        assert forbidden not in writer


def test_comparator_reports_card_and_column_differences_and_closure_gates() -> None:
    source = (ROOT / "src/xstar_tools/xstar/product_oracle_v04874622.py").read_text()
    for token in (
        "first_header_card_difference", "first_column_difference",
        "FITS_HDU_COUNTS_EXACT", "FITS_EXTENSION_ORDER_EXACT",
        "FITS_ROW_COUNTS_EXACT", "FITS_ROW_WIDTHS_EXACT",
        "FITS_COLUMN_METADATA_EXACT", "FITS_HEADERS_EXACT",
        "FITS_HEADER_BYTES_EXACT", "PARAMETER_TABLE_EXACT",
        "RADIAL_ZONE_STATE_COMPLETE", "FITS_NUMERIC_ARRAYS_EXACT",
        "XOUT_STEP_PARITY", "schema_header_radial_closure",
    ):
        assert token in source


def test_python_oracle_self_comparison_has_exact_schema_and_parameter_tables(tmp_path: Path) -> None:
    oracle = bundled_oracle_root("python_physical_run")
    with tarfile.open(oracle / "bundle.tar.gz", "r:gz") as archive:
        archive.extractall(tmp_path, filter="data")
    output = tmp_path
    # Add a complete run-state manifest so the closure gate can be exercised.
    (output / "native_physical_run_state.json").write_text(json.dumps({
        "layers": {"radial_zone_state": {"count": 5, "complete": True}},
        "radial_zones": [{"python_oracle_exact": True} for _ in range(5)],
    }))
    report = compare_output(output, oracle)
    gates = report["gates"]
    assert gates["TEN_PRODUCTS_PRESENT"] == "ACCEPT"
    assert gates["FITS_HDU_COUNTS_EXACT"] == "ACCEPT"
    assert gates["FITS_EXTENSION_ORDER_EXACT"] == "ACCEPT"
    assert gates["FITS_ROW_COUNTS_EXACT"] == "ACCEPT"
    assert gates["FITS_ROW_WIDTHS_EXACT"] == "ACCEPT"
    assert gates["FITS_COLUMN_METADATA_EXACT"] == "ACCEPT"
    assert gates["FITS_HEADERS_EXACT"] == "ACCEPT"
    assert gates["PARAMETER_TABLE_EXACT"] == "ACCEPT"
    assert gates["RADIAL_ZONE_STATE_COMPLETE"] == "ACCEPT"
    assert report["schema_header_radial_closure"] == "ACCEPT"


def test_v23_runner_requires_schema_closure_but_allows_payload_reject() -> None:
    runner = (ROOT / "run_v04874623_python_fits_schema_header_radial_state_closure.sh").read_text()
    assert "SCHEMA_CLOSURE" in runner
    assert '[ "$COMPARE_RC" -eq 2 ]' in runner
    for gate in (
        "TEN_PRODUCTS_PRESENT", "FITS_HDU_COUNTS_EXACT", "FITS_EXTENSION_ORDER_EXACT",
        "FITS_ROW_COUNTS_EXACT", "FITS_ROW_WIDTHS_EXACT", "FITS_COLUMN_METADATA_EXACT",
        "FITS_HEADERS_EXACT", "PARAMETER_TABLE_EXACT", "RADIAL_ZONE_STATE_COMPLETE",
        "FITS_NUMERIC_ARRAYS_EXACT", "XOUT_STEP_PARITY", "PRODUCT_LEVEL_PARITY",
    ):
        assert gate in runner
    assert "ACCEPT_SCHEMA_HEADER_RADIAL" in runner


def test_unused_record_warning_is_removed() -> None:
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_engine.cpp").read_text()
    assert "const long long record=m[0],rt=m[1],dt=m[2]" not in source
