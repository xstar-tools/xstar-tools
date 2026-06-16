from __future__ import annotations

from pathlib import Path

from xstar_tools.xstar.call2_helium_source_faithful_compact_seed import RELEASE


def test_release_and_cpp_seed_contract():
    assert RELEASE == "0.6.48.7.32"
    text = Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    start = text.index("RuntimeInitialSeed source_faithful_runtime_initial_seed")
    end = text.index("void bind_output", start)
    block = text[start:end]
    assert "compact_row == e.normalization_row" in block
    assert "seed.global_level_index = 0" in block
    assert "seed.value = 0.0" in block
    assert "e.rows[compact_index - 1].ion_charge == row.ion_charge" in block
    assert "++global_level_index" in block
    assert "if (!source_faithful_runtime_seed)" in block
    assert "source_faithful_runtime_seed = true" in block


def test_new_audit_gates_and_runner_contract():
    audit = Path(
        "src/xstar_tools/xstar/call2_helium_source_faithful_compact_seed.py"
    ).read_text()
    runner = Path("run_v048732_source_faithful_helium_compact_seed.sh").read_text()
    assert "CALL2_HE_SHARED_BOUNDARY_OVERWRITE" in audit
    assert "CALL2_HE_TERMINAL_NORMALIZATION_SEED_ZERO" in audit
    assert "CALL2_HE_PRE_SOLVE_NORMALIZATION_REMOVED" in audit
    assert "CALL2_HE_TRANSFORMED_INITIAL_STATE" in audit
    assert "call2_helium_source_faithful_compact_seed" in runner
    assert "XSTAR_QUALIFICATION_SOLVE_RESPONSE=1" in runner


def test_diagnostic_uses_effective_source_faithful_seed():
    text = Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "source_faithful_runtime_initial_seed(active.element, compact_index, &input)" in text
    assert "active_loaded_global_level_indices[compact_index] = seed.global_level_index" in text
    assert "active_loaded_call_start_xilevg[compact_index] = seed.value" in text
