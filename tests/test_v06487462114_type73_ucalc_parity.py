from pathlib import Path
import math
import struct

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
UCALC = ROOT / "src/xstar_tools/xstar/ucalc.py"
LOWERER = ROOT / "src/xstar_tools/xstar/native_fixed_program.py"


def _branch(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def _bits(value: float) -> bytes:
    return struct.pack("!d", float(value))


def test_release_version():
    assert 'version = "0.6.48.7.46.21.14"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "0.6.48.7.46.21.14"' in (ROOT / "src/xstar_tools/__init__.py").read_text()


def test_type73_python_source_contract_is_literal_wavelength_energy():
    text = UCALC.read_text()
    body = _branch(text, "    def _eval_type73", "    def _eval_type101")
    assert "wav=abs(r.reals[0])" in body
    assert "de=12398.4016/max(wav,1e-48)" in body
    assert "z=float(r.integers[2])" in body
    assert "XSTAR_KT_EV_PER_1E4K*c.t" in body
    assert "ans5=qd*ne*de*ERG_PER_EV" in body
    assert "ans6=qe*ne*de*ERG_PER_EV" in body


def test_type73_lowerer_compacts_only_z_after_endpoint_rows_are_resolved():
    text = LOWERER.read_text()
    body = _branch(text, "    elif dt == 73:", "    elif dt == 74:")
    assert "local_pair(int(raw_ints[0]), int(raw_ints[1]))" in body
    assert "payload_ints = [int(raw_ints[2])]" in body
    assert "payload_reals = list(raw_reals[:7])" in body


def test_type73_cpp_matches_ucalc_operation_order_and_constants():
    text = CPP.read_text()
    body = _branch(
        text,
        "        case XSTAR_FIXED_OPCODE_TYPE73_HELIKE_COLLISION: {",
        "        case XSTAR_FIXED_OPCODE_TYPE76_TWO_PHOTON: {",
    )
    assert "source_energy_ev=12398.4016/std::max(wavelength_a,1.0e-48)" in body
    assert "kLegacyBoltzmannEvPerT4*t4" in body
    assert "kCollisionRateCoefficientPerSqrtT4" in body
    assert "kLegacyCollisionErgPerEv" in body
    assert "const double qd=" in body
    assert "const double qe=qd*gu*excitation_factor/std::max(gl,1.0e-48)" in body
    assert "delta_ev" not in body
    assert "kModernErgPerEv" not in body
    assert "kBoltzmannEvK" not in body


def test_type73_literal_energy_changes_large_mg_ans5_ans6_case():
    # This isolates the post-calt73 ucalc operation order.  The collision
    # coefficient itself is held fixed because the historical failure was the
    # use of endpoint DeltaE instead of the literal wavelength energy.
    crate = 2.75e-8
    temperature_k = 8.0e6
    t4 = temperature_k / 1.0e4
    tsq = math.sqrt(t4)
    ne = 1.2e8
    gl = 2.0
    gu = 4.0
    wavelength_a = 10.0
    endpoint_delta_ev = 1000.0
    source_energy_ev = 12398.4016 / wavelength_a
    omega = crate / max(gl, 1.0e-48)
    expo = lambda x: math.exp(min(max(x, -60.0), 60.0))
    excitation = expo(-source_energy_ev / (0.861707 * t4))
    qd = 8.626e-8 * omega / tsq / max(gu, 1.0e-48)
    qe = qd * gu * excitation / max(gl, 1.0e-48)
    ans1 = qe * ne
    ans2 = qd * ne
    source_ans5 = ans2 * source_energy_ev * 1.602197e-12
    source_ans6 = ans1 * source_energy_ev * 1.602197e-12
    old_ans5 = ans2 * endpoint_delta_ev * 1.602176634e-12
    old_ans6 = ans1 * endpoint_delta_ev * 1.602176634e-12
    assert _bits(source_ans5) != _bits(old_ans5)
    assert _bits(source_ans6) != _bits(old_ans6)
    assert format(source_ans5, ".8e") != format(old_ans5, ".8e")
    assert format(source_ans6, ".8e") != format(old_ans6, ".8e")


def test_type72_neighbor_uses_same_legacy_temperature_constant_as_ucalc():
    cpp = CPP.read_text()
    body = _branch(
        cpp,
        "        case XSTAR_FIXED_OPCODE_TYPE72_DIELECTRONIC_CAPTURE: {",
        "        case XSTAR_FIXED_OPCODE_TYPE73_HELIKE_COLLISION: {",
    )
    assert "kLegacyBoltzmannEvPerT4 * t4" in body
    assert "kModernBoltzmannEvPerT4" not in body
    assert "limited_exp(r[1]/input.temperature_k)" in body


def test_adjacent_active_branches_retain_ucalc_constants():
    text = CPP.read_text()
    type69 = _branch(text, "        case XSTAR_FIXED_OPCODE_TYPE69_HELIKE_COLLISION: {", "        case XSTAR_FIXED_OPCODE_TYPE71_SUPERLEVEL_CASCADE: {")
    type76 = _branch(text, "        case XSTAR_FIXED_OPCODE_TYPE76_TWO_PHOTON: {", "        case XSTAR_FIXED_OPCODE_TYPE95_SPLINE_IONIZATION: {")
    type95 = _branch(text, "        case XSTAR_FIXED_OPCODE_TYPE95_SPLINE_IONIZATION: {", "        case XSTAR_FIXED_OPCODE_TYPE74_DELTA_RESONANCE: {")
    assert "kLegacyCollisionErgPerEv" in type69
    assert "kLegacyCollisionErgPerEv" in type76
    assert "kLegacyBoltzmannEvPerT4" in type95
    assert "kLegacyCollisionErgPerEv" in type95


def test_other_active_collision_branches_match_ucalc_constant_domains():
    text = CPP.read_text()
    type6062 = _branch(
        text,
        "        case XSTAR_FIXED_OPCODE_TYPE60_CALLAWAY_COLLISION:",
        "        case XSTAR_FIXED_OPCODE_TYPE68_HELIKE_COLLISION: {",
    )
    type68 = _branch(
        text,
        "        case XSTAR_FIXED_OPCODE_TYPE68_HELIKE_COLLISION: {",
        "        case XSTAR_FIXED_OPCODE_TYPE63_ALGORITHMIC_COLLISION: {",
    )
    type69 = _branch(
        text,
        "        case XSTAR_FIXED_OPCODE_TYPE69_HELIKE_COLLISION: {",
        "        case XSTAR_FIXED_OPCODE_TYPE71_SUPERLEVEL_CASCADE: {",
    )
    type77 = _branch(
        text,
        "        case XSTAR_FIXED_OPCODE_TYPE77_SUPERLEVEL_COLLISION: {",
        "        case XSTAR_FIXED_OPCODE_TYPE72_DIELECTRONIC_CAPTURE: {",
    )
    assert "kLegacyBoltzmannEvPerT4" in type6062
    assert "kModernErgPerEv" in type6062
    assert "kLegacyCollisionErgPerEv" in type68
    assert "kLegacyCollisionErgPerEv" in type69
    assert "kLegacyCollisionErgPerEv" in type77
