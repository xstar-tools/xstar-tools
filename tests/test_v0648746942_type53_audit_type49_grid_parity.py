from __future__ import annotations

import math
from pathlib import Path

import xstar_tools
from xstar_tools.xstar import mg_milne_excited_threshold_attribution as audit
from xstar_tools.xstar import native_fixed_program as lowerer


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_release_and_api_version() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.19"
    assert audit.RELEASE == "0.6.48.7.46.19"
    api = (root() / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.19"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api


def test_type49_reduced_grid_capacity_contract() -> None:
    assert lowerer.TYPE49_PHEXTRAP_MAX_POINTS == 999
    energy = [float(i) / 10.0 for i in range(993)]
    sigma = [1.0e-18 / (i + 1.0) for i in range(993)]
    out_energy, out_sigma = audit._reference_phextrap(energy, sigma, 80.0, 999)
    assert len(out_energy) == len(out_sigma) == 999

    long_energy = [float(i) / 10.0 for i in range(1173)]
    long_sigma = [1.0e-18 / (i + 1.0) for i in range(1173)]
    held_energy, held_sigma = audit._reference_phextrap(long_energy, long_sigma, 80.0, 999)
    assert held_energy == long_energy
    assert held_sigma == long_sigma


def test_binary64_hash_is_stable_and_order_sensitive() -> None:
    values = [0.0, 1.0, -2.5, math.nextafter(1.0, math.inf)]
    assert audit._binary64_sequence_fnv1a(values) == audit._binary64_sequence_fnv1a(tuple(values))
    assert audit._binary64_sequence_fnv1a(values) != audit._binary64_sequence_fnv1a(reversed(values))
    assert audit._binary64_sequence_fnv1a(()) == 1469598103934665603


def test_mg_ieee_envelope_accepts_three_ulps_only() -> None:
    value = 1.5
    for _ in range(3):
        value = math.nextafter(value, math.inf)
    accepted, ulps, _, relative = audit._mg_binary64_ieee_equivalent(1.5, value)
    assert accepted
    assert ulps == 3
    assert relative <= audit.MAX_RELATIVE_DELTA
    value = math.nextafter(value, math.inf)
    assert not audit._mg_binary64_ieee_equivalent(1.5, value)[0]
    assert not audit._mg_binary64_ieee_equivalent(0.0, math.nextafter(0.0, 1.0))[0]
    assert not audit._mg_binary64_ieee_equivalent(1.0, -1.0)[0]


def test_type53_uses_ordinary_prefix_for_context_flags() -> None:
    assert audit._prefixes(49) == ("type49_", "type49_", "type49_")
    assert audit._prefixes(53) == ("mg_type53_", "type53_shadow_", "type53_")
    text = (root() / "src/xstar_tools/xstar/mg_milne_excited_threshold_attribution.py").read_text()
    assert 'flag_prefix + "milne_partition_context_used"' in text
    assert 'flag_prefix + "excited_threshold_context_used"' in text
    assert 'flag_prefix + "corrected_threshold_before_mapping"' in text


def test_native_uses_lowered_phextrap_capacity_and_hashes() -> None:
    lowerer_text = (root() / "src/xstar_tools/xstar/native_fixed_program.py").read_text()
    cpp = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "payload_ints.append(TYPE49_PHEXTRAP_MAX_POINTS)" in lowerer_text
    assert "record_context.phextrap_max_points" in cpp
    assert "pair_energy_ryd.size()) < phextrap_max_points" in cpp
    assert "pair_energy_ryd.size()) < n_grid" not in cpp
    for marker in (
        "phextrap_input_energy_hash", "phextrap_input_sigma_hash",
        "phextrap_output_energy_hash", "phextrap_output_sigma_hash",
        "XSTAR_QUALIFICATION_TYPE49_EXTRAPOLATED_GRID_PARITY",
    ):
        assert marker in cpp


def test_release_gates_are_fail_closed() -> None:
    text = (root() / "src/xstar_tools/xstar/mg_milne_excited_threshold_attribution.py").read_text()
    for marker in (
        "MG_TYPE53_AUDIT_PREFIX_CORRECT",
        "MG_TYPE49_PHEXTRAP_MAX_POINTS_EXACT",
        "MG_TYPE49_PHEXTRAP_INPUT_HASH_EXACT",
        "MG_TYPE49_PHEXTRAP_OUTPUT_HASH_EXACT",
        "MG_TYPE49_FIRST_DIVERGENT_GRID_POINT_COUNT_ZERO",
        "MG_TYPE49_EXTRAPOLATED_GRID_PARITY",
        "MG_BOUND_FREE_IEEE_ROUNDOFF_ENVELOPE",
    ):
        assert marker in text


def test_type50_block_is_unchanged() -> None:
    cpp = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    block = cpp.split("case XSTAR_FIXED_OPCODE_TYPE50_RADIATIVE_LINE", 1)[1].split(
        "case XSTAR_FIXED_OPCODE_TYPE51_BT_COLLISION", 1
    )[0]
    assert "TYPE49_EXTRAPOLATED_GRID_PARITY" not in block
    assert "phextrap_max_points" not in block
