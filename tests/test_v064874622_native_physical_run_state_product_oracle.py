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
    assert RELEASE == "0.6.48.7.46.22.3"
    assert 'version = "0.6.48.7.46.22.3"' in (ROOT / "pyproject.toml").read_text()
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.7.46.22.3"' in api


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


def test_physical_run_resolves_accepted_sibling_assets_without_manual_overrides() -> None:
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    runner = (ROOT / "run_v04874622_native_physical_run_state_product_oracle.sh").read_text()
    assert "sibling_release_roots" in source
    assert "xstar_tools-0.6.48.7.46.21.17.2/v048746227_source_order_electron_controller_closure/native_case_v048746227" in source
    assert "xstar_tools-0.6.48.7.46.21.17.2/v048746227_source_order_electron_controller_closure/v0472_call_start_workspaces" in source
    assert "xstar_tools-0.6.48.7.46.21.17.2/v048746227_source_order_electron_controller_closure/v048746227_coherent_source_trajectory.csv" in source
    assert 'arg == "--resolve-only"' in source
    assert "native_physical_run_asset_resolution.json" in source
    assert "--resolve-only" in runner
    assert "asset_resolution_return_code" in runner


def test_physical_run_activates_complete_accepted_controller_profile() -> None:
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "accepted-v21.17.2-source-faithful-controller" in source
    for flag in (
        "XSTAR_QUALIFICATION_REPLACEMENT",
        "XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_SYSTEM",
        "XSTAR_QUALIFICATION_INDEPENDENT_THERMAL_PARITY",
        "XSTAR_QUALIFICATION_CONTINUUM_WORKSPACE_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_REDUCTION",
    ):
        assert flag in source
    for asset in (
        "v0472_all61_element_solve_rows.csv",
        "v0472_hydrogen_type50_line_index_map.csv",
        "v0472_magnesium_type50_line_index_map.csv",
        "v0472_all61_magnesium_type50_endpoint_escape.csv",
        "v0472_magnesium_type50_endpoint_energy_map.csv",
        "v0472_all61_magnesium_type99_primary_thermal_ledger.csv",
        "v0472_all61_magnesium_primary_cooling_source_order_ledger.csv",
        "v04874610_matrix_construction_closure/v04874610_matrix_closure",
    ):
        assert asset in source
    assert "qualification_flags" in source
    assert "qualification_paths" in source


def test_controller_qualification_uses_canonical_e7_and_separates_product_reject() -> None:
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    runner = (ROOT / "run_v04874622_native_physical_run_state_product_oracle.sh").read_text()
    assert "reference_state_canonical_e7" in source
    assert "controller_qualification_result" in source
    assert "canonical_digits_after_decimal=7" in source
    assert "canonical_zero_floor=1e-30" in source
    assert "controller-canonical-e7-self-test" in source
    assert '[ "$COMPARE_RC" -eq 2 ]' in runner
    assert "COMPARE_EXECUTED" in runner
    assert "product_comparison_return_code_semantics" in runner
    assert 'NATIVE_PHYSICAL_RUN_INFRASTRUCTURE=$INFRA' in runner
    assert 'PRODUCT_LEVEL_PARITY=$PRODUCT_LEVEL_PARITY' in runner
