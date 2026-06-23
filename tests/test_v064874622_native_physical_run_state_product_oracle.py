from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tarfile

from xstar_tools.xstar.product_oracle_v04874622 import (
    EXPECTED_PRODUCTS,
    RELEASE,
    bundled_oracle_root,
    compare_output,
    normalize_log_text,
)

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def test_release_and_abi_are_retained() -> None:
    assert RELEASE == "0.6.48.7.46.22"
    assert 'version = "0.6.48.7.46.22"' in (ROOT / "pyproject.toml").read_text()
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.7.46.22"' in api


def test_oracles_are_frozen_separately() -> None:
    py = json.loads((bundled_oracle_root("python_physical_run") / "manifest.json").read_text())
    ft = json.loads((bundled_oracle_root("fortran_reference") / "manifest.json").read_text())
    assert py["source_kind"] == "python"
    assert ft["source_kind"] == "fortran"
    assert py["archive"]["sha256"] != ft["archive"]["sha256"]
    assert set(py["files"]) == set(EXPECTED_PRODUCTS)
    assert set(ft["files"]) == set(EXPECTED_PRODUCTS)
    for manifest, name in ((py, "python_physical_run"), (ft, "fortran_reference")):
        bundle = bundled_oracle_root(name) / "bundle.tar.gz"
        assert sha256(bundle) == manifest["archive"]["sha256"]
        for product in EXPECTED_PRODUCTS:
            assert len(manifest["files"][product]["sha256"]) == 64
        for product in [p for p in EXPECTED_PRODUCTS if p.endswith(".fits")]:
            assert manifest["files"][product]["hdus"]
            for hdu in manifest["files"][product]["hdus"]:
                assert len(hdu["header_sha256"]) == 64
                assert len(hdu["data_sha256"]) == 64
                assert len(hdu["hdu_sha256"]) == 64


def test_python_oracle_self_comparison_accepts(tmp_path: Path) -> None:
    oracle = bundled_oracle_root("python_physical_run")
    with tarfile.open(oracle / "bundle.tar.gz", "r:gz") as archive:
        archive.extractall(tmp_path, filter="data")
    report = compare_output(tmp_path, oracle)
    assert report["result"] == "ACCEPT"
    assert report["product_level_parity"] == "ACCEPT"
    assert all(value == "ACCEPT" for value in report["gates"].values())


def test_fortran_is_not_substituted_for_python_oracle(tmp_path: Path) -> None:
    oracle = bundled_oracle_root("fortran_reference")
    with tarfile.open(oracle / "bundle.tar.gz", "r:gz") as archive:
        archive.extractall(tmp_path, filter="data")
    output = tmp_path / "mg11_ne1e8"
    report = compare_output(output, bundled_oracle_root("python_physical_run"))
    assert report["result"] == "REJECT"
    assert report["product_level_parity"] == "REJECT"


def test_log_normalization_preserves_science_and_removes_only_provenance() -> None:
    source = (
        "xstar_tools version 0.6.47.2\n"
        "input=/tmp/example/parameters.json\n"
        "temperature=6.561529885564275\n"
        "Total runtime: 123.45 seconds\n"
    )
    normalized = normalize_log_text(source)
    assert "<VERSION>" in normalized
    assert "<PATH>" in normalized
    assert "<RUNTIME>" in normalized
    assert "temperature=6.561529885564275" in normalized


def test_native_state_layers_and_run_command_are_real_source_boundaries() -> None:
    header = (ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp").read_text()
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    writer = (ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.hpp").read_text()
    for name in (
        "FixedEvaluationState", "AcceptedControllerState", "RadialZoneState",
        "WholeRunAccumulatedState", "ProductWritingState",
    ):
        assert f"struct {name}" in header
    assert "ProductWritingState& product_state" in writer
    assert 'options.command == "run"' in source
    assert 'arg == "--parameters"' in source
    assert 'arg == "--atomic-db"' in source
    assert "native_dsec_trace.log" in source
    assert "native_physical_run_state.json" in source
    assert "product_level_parity=NOT_RUN" in source
