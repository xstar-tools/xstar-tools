from __future__ import annotations

from pathlib import Path

from xstar_tools.xstar.call2_helium_solve_state_rate_matrix_decomposition import (
    RELEASE,
    canonical_role,
    indexed_terms,
    term_base_key,
)


def row(**updates: str) -> dict[str, str]:
    value = {
        "record": "100",
        "data_type": "53",
        "rate_type": "7",
        "role": "forward_offdiag",
        "compact_row": "2",
        "compact_column": "1",
    }
    value.update(updates)
    return value


def test_metadata_key_normalizes_roles_and_occurrences():
    assert RELEASE == "0.6.48.7.31.3"
    source = row()
    native = row(role="forward_gain")
    assert canonical_role(source["role"]) == native["role"]
    assert term_base_key(source) == term_base_key(native)
    indexed = indexed_terms([source, source])
    keys = sorted(indexed)
    assert keys[0][-1] == 1
    assert keys[1][-1] == 2


def test_new_runner_and_audit_contract():
    runner = Path("run_v0487313_helium_term_alignment_seed_semantics_audit.sh").read_text()
    audit = Path(
        "src/xstar_tools/xstar/call2_helium_solve_state_rate_matrix_decomposition.py"
    ).read_text()
    assert "XSTAR_QUALIFICATION_SOLVE_RESPONSE=1" in runner
    assert "call2_he_unmatched_source_terms.csv" in audit
    assert "call2_he_unmatched_native_terms.csv" in audit
    assert "CALL2_HE_SOURCE_ORDER_POSITIONAL_COMPARISON" in audit
    assert "NOT_EVALUATED_TERM_STREAM_ALIGNMENT" in audit
    assert "raw_global_workspace_value" in audit
    assert "normalized_native_solver_seed" in audit


def test_no_physics_source_is_modified_by_new_runner():
    runner = Path("run_v0487313_helium_term_alignment_seed_semantics_audit.sh").read_text()
    assert "native_fixed_program lower-atdb" in runner
    assert "call2_helium_solve_state_rate_matrix_decomposition" in runner
    assert "source budget substitution" not in runner.lower()
