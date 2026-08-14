from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
PY = ROOT / "src/xstar_tools/xstar/emergent_emissivity.py"
RUNNER = ROOT / "tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_5.py"
MAN = ROOT / "qualification/npass_0_6_82_27_5/npass_hotfix_source_scope_0_6_82_27_5.json"


def runner():
    spec = importlib.util.spec_from_file_location("npass0275_runner", RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_0682275_version_abis_and_narrow_scope():
    assert any(f'version = "{v}"' in (ROOT / "pyproject.toml").read_text() for v in ("0.6.82.27.5", "0.6.82.27.6", "0.6.82.27.7", "0.6.82.27.8", "0.6.82.27.9", "0.6.82.27.10"))
    assert any(f'PACKAGE_VERSION ?= {v}' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text() for v in ("0.6.82.27.5", "0.6.82.27.6", "0.6.82.27.7", "0.6.82.27.8", "0.6.82.27.9", "0.6.82.27.10"))
    obj = json.loads(MAN.read_text())
    assert obj["predecessor"] == "0.6.82.27.4"
    assert obj["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert (obj["c_api_abi"], obj["production_zone_abi"], obj["fixed_state_abi"]) == (60487, 6048110, 60488)
    assert obj["numerical_source_count_predecessor"] == 137
    assert obj["intentional_numerical_source_changes"] == ["src/xstar_tools/xstar/cpp/local_zone_engine.cpp"]


def test_0682275_cpp_resolves_final_rate7_owner_before_type88_replay():
    text = CPP.read_text()
    marker = text.index("0.6.82.27.5: calc_emis_ion.f90 is rate-type-major")
    owner = text.index("for (const auto& pr : ctx.program.records) {", marker)
    type88_vec = text.index("std::vector<const ProgramRecord*> type88_source_order_v0682275", owner)
    replay = text.index("for (const ProgramRecord* prp : type88_source_order_v0682275)", type88_vec)
    assert owner < type88_vec < replay
    assert "if (pr.rate_type != 7 || pr.continuum_index_one_based <= 0) continue;" in text[owner:type88_vec]
    assert "pr.source_position > static_cast<std::int64_t>(found->second.source_position)" in text[owner:type88_vec]
    assert "const int slot_one_based = rit->second.slot_one_based;" in text[replay:]
    assert "source_order_v82_patch52010" not in text


def test_0682275_synthetic_source_major_and_rate_type_major_differ_as_expected():
    records = [(10, 7, 208), (20, 42, 0), (30, 7, 209), (40, 42, 0)]
    retained = 0
    old_owners = []
    for _pos, rate_type, slot in records:
        if rate_type == 7:
            retained = slot
        elif rate_type == 42:
            old_owners.append(retained)
    final_rate7 = [slot for _pos, rate_type, slot in records if rate_type == 7][-1]
    source_owners = [final_rate7 for _pos, rate_type, _slot in records if rate_type == 42]
    assert old_owners == [208, 209]
    assert source_owners == [209, 209]


def test_0682275_python_already_rate_type_major_and_not_rewritten():
    text = PY.read_text()
    seq = text[text.index("def _calc_emis_record_sequence_for_ion"):text.index("def _compact_mg_line_emissivity_table")]
    assert "for rate_type in range(1, max_rate_type + 1):" in seq
    assert "seq.append((int(rate_type), int(rec)))" in seq
    body = text[text.index("retained_kkkl = 0"):]
    assert body.index("retained_kkkl = int(context.derived.npconi2[rec])") < body.index("if rate_type == 42")
    assert "context.workspace.base.opakab[retained_kkkl] = result.opakab" in body


def test_0682275_runner_has_raw_rrc_workspace_gate(monkeypatch):
    mod = runner()
    assert mod.EXPECTED_VERSION == "0.6.82.27.5"
    assert mod.RRC_OWNERSHIP_SENTINELS
    calls = []
    def fake(path, *, include_opacity=False):
        calls.append((path.name, include_opacity))
        return [{idx: (1.0, 2.0, 3.0) for idx in mod.RRC_OWNERSHIP_SENTINELS}]
    monkeypatch.setattr(mod, "_detail_rrc_workspace_hdus", fake)
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Path, "stat", lambda self: type("S", (), {"st_size": 1})())
    out = mod.compare_rrc_workspace_all_passes(Path("candidate"), Path("reference"), 1)
    assert out["accept"]
    assert calls == [("xo01_detal3.fits", True), ("xo01_detal3.fits", True)]


def test_0682275_runner_keeps_all_pass_detail_gate():
    text = RUNNER.read_text()
    assert "compare_all_pass_detail_tau" in text
    assert "compare_rrc_workspace_all_passes" in text
    assert 'C5_NPASS_MULTIPASS_0682275_{b.upper()}_RESULT' in text
