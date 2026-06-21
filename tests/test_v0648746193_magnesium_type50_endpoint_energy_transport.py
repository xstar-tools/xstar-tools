from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_endpoint_capture_contract():
    text = (
        ROOT / "src/xstar_tools/xstar/"
        "v0472_all61_magnesium_type50_endpoint_capture.py"
    ).read_text()
    assert 'RELEASE = "0.6.48.7.46.21.5"' in text
    assert 'ENDPOINT_MAP_NAME = "v0472_magnesium_type50_endpoint_energy_map.csv"' in text
    assert '"source_endpoint1_energy_ev"' in text
    assert '"source_endpoint2_energy_ev"' in text
    assert '"source_endpoint_energy_ev"' in text
    assert "source_ans3_endpoint_identity_rows" in text
    assert "source_ans4_endpoint_identity_rows" in text


def test_cpp_endpoint_transport_and_closure():
    text = (
        ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp"
    ).read_text()
    assert "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_ENERGY_TRANSPORT" in text
    assert "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_MAP_CSV" in text
    assert "endpoint_by_record.find(record.record)" in text
    assert "endpoint_by_record.find(contribution.record)" in text
    assert "c.ans3 = -escaped * endpoint_energy_ev * kErgPerEv" in text
    assert "contribution.ans3 = -contribution.ans2 * endpoint_energy_ev * kErgPerEv" in text
    assert "type50_magnesium_source_endpoint_energy_applied" in text


def test_audit_requires_exact_endpoint_and_cooling_domains():
    text = (
        ROOT / "src/xstar_tools/xstar/"
        "magnesium_type50_endpoint_energy_v048746193.py"
    ).read_text()
    for gate in (
        "MAGNESIUM_TYPE50_SOURCE_ENDPOINT_MAP_EXACT_2420",
        "MAGNESIUM_TYPE50_SOURCE_ENDPOINT_ROWS_EXACT_146286",
        "MAGNESIUM_TYPE50_ENDPOINT_IDS_EXACT_146286",
        "MAGNESIUM_TYPE50_ENDPOINT_ENERGIES_EXACT_438858",
        "MAGNESIUM_TYPE50_ANS3_EXACT_146286",
        "MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286",
        "MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286",
        "MAGNESIUM_COOLING_ALL61_EXACT",
        "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127",
    ):
        assert gate in text


def test_causal_gate_is_narrow():
    text = (
        ROOT / "src/xstar_tools/xstar/"
        "v46192_endpoint_energy_gate_v048746193.py"
    ).read_text()
    assert "V46192_ONLY_ANS3_MISMATCHES" in text
    assert "V46192_ANS3_MISMATCH_ROWS_50955" in text
    assert "V46192_ANS3_MISMATCH_RECORDS_857" in text
    assert "V46192_COMMITTED_CJ_EXACT_88637" in text
    assert "V46192_COMMITTED_COOLING_EXACT_100781" in text


def test_runner_uses_endpoint_capture_and_transport():
    text = (
        ROOT / "run_v048746193_magnesium_type50_endpoint_energy_transport.sh"
    ).read_text()
    assert "v0472_all61_magnesium_type50_endpoint_capture" in text
    assert "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_ENERGY_TRANSPORT=1" in text
    assert "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_MAP_CSV" in text
    assert "v46192_endpoint_energy_gate_v048746193" in text
    assert "magnesium_type50_endpoint_energy_v048746193" in text
