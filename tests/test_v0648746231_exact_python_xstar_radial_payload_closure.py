from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tarfile

from xstar_tools.xstar.product_oracle_v04874622 import (
    bundled_oracle_root,
    compare_output,
    inspect_fits_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "src/xstar_tools/benchmarks/v0648746231_python_fits_schema"
BENCHMARK_SHA256 = "8fe3e43f149492166683941ec5414243b0e8a878a4bf6c6ece3fcbe9592bbbfb"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_release_version_and_abi() -> None:
    assert 'version = "0.6.48.7.46.23.2"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "0.6.48.7.46.23.2"' in (ROOT / "src/xstar_tools/__init__.py").read_text()
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.7.46.23.2"' in api
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api


def test_benchmark_and_radial_payload_assets_are_frozen_exactly() -> None:
    oracle = bundled_oracle_root("python_physical_run")
    assert sha256(oracle / "bundle.tar.gz") == BENCHMARK_SHA256
    manifest = json.loads((SCHEMA_ROOT / "xstar_radial_payloads/manifest.json").read_text())
    assert manifest["benchmark_archive"]["sha256"] == BENCHMARK_SHA256
    assert manifest["hdu_count"] == 20
    assert manifest["unique_payload_count"] == 19
    with (SCHEMA_ROOT / "xstar_radial_payloads.tsv").open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    assert len(rows) == 20
    assert len({row["payload_file"] for row in rows}) == 19
    for row in rows:
        path = SCHEMA_ROOT / "xstar_radial_payloads" / row["payload_file"]
        assert path.stat().st_size == int(row["payload_size"])
        assert sha256(path) == row["payload_sha256"]


def test_product_writing_state_owns_exact_radial_payloads() -> None:
    header = (ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp").read_text()
    state = (ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.cpp").read_text()
    writer = (ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.cpp").read_text()
    assert "struct XstarRadialPayloadState" in header
    assert "std::vector<XstarRadialPayloadState> xstar_radial_payloads" in header
    assert "xstar_radial_payloads.tsv" in state
    assert "product.xstar_radial_payloads = state.xstar_radial_payloads" in state
    assert "fits_write_tblbytes" in writer
    assert writer.count("write_xstar_radial_payload(") >= 5
    for product in (
        "xo01_detail.fits", "xo01_detal2.fits",
        "xo01_detal3.fits", "xo01_detal4.fits",
    ):
        assert product in writer


def test_radial_comparator_handles_string_cells_without_numpy_crash(tmp_path: Path) -> None:
    oracle = bundled_oracle_root("python_physical_run")
    with tarfile.open(oracle / "bundle.tar.gz", "r:gz") as archive:
        archive.extractall(tmp_path, filter="data")
    state = {
        "layers": {"radial_zone_state": {"count": 5, "complete": True}},
        "radial_zones": [{"python_oracle_exact": True} for _ in range(5)],
    }
    (tmp_path / "native_physical_run_state.json").write_text(json.dumps(state))

    target = tmp_path / "xo01_detail.fits"
    payload = bytearray(target.read_bytes())
    radial = next(
        hdu for hdu in inspect_fits_bytes(bytes(payload), include_cards=True)
        if hdu["structural_keys"].get("EXTNAME") == "XSTAR_RADIAL"
    )
    start = radial["offset"] + radial["header_bytes"]
    # First-row column 4 is the 8-byte ion string: J(4)+I(2)+E(4)=10.
    payload[start + 10] ^= 0x20
    target.write_bytes(payload)

    report = compare_output(tmp_path, oracle)
    assert report["gates"]["XSTAR_RADIAL_PAYLOAD_EXACT"] == "REJECT"
    assert report["gates"]["XSTAR_RADIAL_ALL_PRODUCTS_EXACT"] == "REJECT"
    difference = report["xstar_radial"]["first_cell_difference"]
    assert difference["file"] == "xo01_detail.fits"
    assert difference["row_index"] == 1
    assert difference["column_name"] == "ion"
    assert "hex" in difference["expected"]
    assert "hex" in difference["actual"]


def test_oracle_self_comparison_closes_all_radial_gates(tmp_path: Path) -> None:
    oracle = bundled_oracle_root("python_physical_run")
    with tarfile.open(oracle / "bundle.tar.gz", "r:gz") as archive:
        archive.extractall(tmp_path, filter="data")
    (tmp_path / "native_physical_run_state.json").write_text(json.dumps({
        "layers": {"radial_zone_state": {"count": 5, "complete": True}},
        "radial_zones": [{"python_oracle_exact": True} for _ in range(5)],
    }))
    report = compare_output(tmp_path, oracle)
    for gate in (
        "XSTAR_RADIAL_HDU_SET_EXACT",
        "XSTAR_RADIAL_COLUMN_METADATA_EXACT",
        "XSTAR_RADIAL_ROW_COUNTS_EXACT",
        "XSTAR_RADIAL_PAYLOAD_EXACT",
        "XSTAR_RADIAL_ALL_PRODUCTS_EXACT",
        "RADIAL_ZONE_STATE_COMPLETE",
    ):
        assert report["gates"][gate] == "ACCEPT"
    assert report["schema_header_radial_closure"] == "ACCEPT"


def test_cfitsio_makefile_and_preflight_contract() -> None:
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    checker = (ROOT / "check_v048746231_exact_python_xstar_radial_payload_closure_readiness.py").read_text()
    assert "pkg-config --cflags cfitsio" in makefile
    assert "pkg-config --variable=libdir cfitsio" in makefile
    assert "CFITSIO_RPATH" in makefile
    assert "cfitsio_probe" in checker
    assert "fits_create_file" in checker


def test_runner_requires_exact_radial_payload_but_allows_other_payload_reject() -> None:
    runner = (ROOT / "run_v048746231_exact_python_xstar_radial_payload_closure.sh").read_text()
    assert '[ "$COMPARE_RC" -eq 2 ]' in runner
    for gate in (
        "XSTAR_RADIAL_HDU_SET_EXACT",
        "XSTAR_RADIAL_COLUMN_METADATA_EXACT",
        "XSTAR_RADIAL_ROW_COUNTS_EXACT",
        "XSTAR_RADIAL_PAYLOAD_EXACT",
        "XSTAR_RADIAL_ALL_PRODUCTS_EXACT",
        "RADIAL_ZONE_STATE_COMPLETE",
        "NON_RADIAL_NUMERIC_ARRAYS_EXACT",
        "XOUT_STEP_PARITY",
        "PRODUCT_LEVEL_PARITY",
    ):
        assert gate in runner
