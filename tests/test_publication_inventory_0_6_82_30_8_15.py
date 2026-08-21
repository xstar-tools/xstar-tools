from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FROZEN_814_HASHES = {
    "src/xstar_tools/xstar/cpp/local_zone_engine.cpp": "ae753d8070e3b1bcb51040daf2fac9aa6b1500eb80e91d15e2e87f1dea18b3b5",
    "src/xstar_tools/xstar/cpp/element_engine.cpp": "10e40730577920a23d0885bfeb7efce2c0a566140f56a0303f2cd2bcf4bf55ee",
    "src/xstar_tools/xstar/cpp/level_population.cpp": "2fe4dd203c42063fc71e9d7e955094471de0fd874426d5a59ca4da83d9b75b0b",
    "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp": "811f21ad7a5da7e6466809b776e7fc561301a1a1386c962a8f9ca07a94d4a506",
    "src/xstar_tools/rates_type50.py": "da88d8dea9a249ef9a36abfc8074db12457c261205c21957a5b583082e408dc4",
    "src/xstar_tools/collisions.py": "53a19283b9907d9cd16f10c832bb6fe0dd61aed48a7fa796b69e99854714c294",
    "src/xstar_tools/xstar/ucalc.py": "3e3cd8e3a4bfa4b75d0719f4d4aa4c8ff0cd65e9c8bd6d851b0aa30a29142e64",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_815_package_version():
    pyproject = (ROOT / "pyproject.toml").read_text()
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    assert 'version = "0.6.82.30.8.15"' in pyproject
    assert "PACKAGE_VERSION ?= 0.6.82.30.8.15" in makefile


def test_814_science_kernels_are_byte_frozen():
    for rel, expected in FROZEN_814_HASHES.items():
        assert _sha256(ROOT / rel) == expected, rel


def test_detail_population_fix_is_generic_not_nvi_hardcoded():
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    begin = source.index("0.6.82.30.8.15 publication-only fstepr ownership repair")
    end = source.index("return dense;", begin)
    block = source[begin:end]
    assert "detail_level_identities" in block
    assert "row_metadata" in block
    assert "pre_mapback" in block
    assert "detail.atomic_number" in block
    assert "detail.global_index == 839" not in block
    assert "detail.global_index == 844" not in block
    assert 'detail.ion_label == "n_vi"' not in block.lower()


def test_detail_rrc_uses_literal_source_slot_or_compact_ordinal_by_representation():
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.cpp").read_text()
    assert "rrc_two_plane_workspace_value_v068230815" in source
    assert "values.size() == 2u * canonical_identity_count" in source
    assert "plane * stride + source_index_one_based" in source
    assert "retained_rrc_compact_v068230815" in source
    assert "state.rrc_identities.size()" in source
    assert "literal fstepr3.f90" in source


def test_public_rrc_inventory_uses_exact_source_identity_chain():
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    begin = source.index("0.6.82.30.8.15 publication-only writespectra4 ownership repair")
    end = source.index("for (std::size_t source_slot = 1; source_slot < continuum_stride;", begin)
    block = source[begin:end]
    assert "source_rrc_identities" in block
    assert "identity.rate_type != 7" in block
    assert "identity.continuum_index" in block


def test_public_rrc_writer_has_no_non_source_threshold_sign_gate():
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.cpp").read_text()
    begin = source.index("void write_public_rrc(")
    end = source.index("void write_public_spectrum", begin)
    block = source[begin:end]
    assert "identity.rate_type != 7" in block
    assert "identity.threshold_ev > 0.0" not in block


def test_product_inventory_qualifier_contract_present():
    checker = ROOT / "tools/qualification/compare_multi_element_product_inventory_0_6_82_30_8_15.py"
    text = checker.read_text()
    assert "NVI_GLOBALS = set(range(839, 845))" in text
    assert "REQUIRED_DETAIL_RRC = 7063" in text
    assert "REQUIRED_PUBLIC_RRC = 144628" in text
    assert "range(10329, 10334)" in text
    assert "range(10339, 10344)" in text
    assert "XO01_DETAL2_EXCEPTION" in text
