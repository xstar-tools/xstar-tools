from __future__ import annotations

import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXED = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"


def test_type68_native_branch_uses_named_source_constants():
    text = FIXED.read_text()
    block = text.split("case XSTAR_FIXED_OPCODE_TYPE68_HELIKE_COLLISION", 1)[1].split(
        "case XSTAR_FIXED_OPCODE_TYPE63_ALGORITHMIC_COLLISION", 1
    )[0]
    assert "XSTAR_QUALIFICATION_TYPE68_SOURCE_CONSTANTS" in block
    assert "kLegacyBoltzmannEvPerT4" in block
    assert "kCollisionRateCoefficientPerSqrtT4" in block
    assert "kLegacyCollisionErgPerEv" in block
    assert "TYPE68_COOLING_OVERRIDE" not in block


def test_type68_representative_record_reproduces_frozen_source_e10():
    # Production-host v21.13 sequence-1 Mg Type-68 record 46513.
    native_ans5 = 3.5529920888446737e-13
    native_ans6 = 1.0217305863270666e-13
    source_ans5 = 3.5530372525521853e-13
    source_ans6 = 1.021738964114119e-13
    delta_ev = 1343.837646484375 - 1331.111572265625
    temperature_k = 1.0e6
    legacy_erg = 1.602197e-12
    modern_erg = 1.602176634e-12
    legacy_kt = 0.861707 * (temperature_k / 1.0e4)
    modern_kt = 8.617333262145e-5 * temperature_k

    corrected_ans5 = native_ans5 * legacy_erg / modern_erg
    corrected_ans6 = (
        native_ans6
        * legacy_erg / modern_erg
        * math.exp(-delta_ev / legacy_kt)
        / math.exp(-delta_ev / modern_kt)
    )
    assert format(corrected_ans5, ".10e") == format(source_ans5, ".10e")
    assert format(corrected_ans6, ".10e") == format(source_ans6, ".10e")


def test_prior_release_analyzers_use_named_gate_sets():
    checks = {
        "magnesium_type57_thermal_closure_v048746220.py": "v21_9_required",
        "magnesium_type53_leveltemp_closure_v048746221.py": "v21_10_required",
        "magnesium_type49_leveltemp_closure_v048746222.py": "v21_11_required",
        "magnesium_type99_leveltemp_closure_v048746223.py": "v21_12_required",
    }
    base = ROOT / "src/xstar_tools/xstar"
    for filename, token in checks.items():
        text = (base / filename).read_text()
        assert token in text


def test_runner_stages_case_and_uses_lock():
    text = (ROOT / "run_v0487462231_type68_source_constants_residual_attribution.sh").read_text()
    assert ".v0487462231_run_lock" in text
    assert ".native_case_v0487462231.$$.tmp" in text
    assert 'mv "$CASE_TMP" "$CASE"' in text
    assert "run_v0487462231_native_fixed_replay.sh" in text


def test_residual_analyzer_tracks_requested_families_and_gates():
    text = (ROOT / "src/xstar_tools/xstar/post_type99_type68_residual_audit_v0487462231.py").read_text()
    for token in ("(12, 68)", "(12, 73)", "(12, 95)", "(2, 53)"):
        assert token in text
    for gate in (
        "V21_11_TYPE53_TYPE57_AND_V21_9_REGRESSION",
        "V21_12_TYPE49_REGRESSION",
        "MAGNESIUM_TYPE68_ANS5_ANS6_IEEE_E10",
        "MAGNESIUM_COOLING2_ALL_SELECTED_IEEE_E10",
    ):
        assert gate in text
