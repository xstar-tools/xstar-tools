from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp"
STEP = ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp"
RUNSTATE = ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp"
PY_TRANSFER = ROOT / "src/xstar_tools/xstar/radial_transfer.py"
PY_PPRINT = ROOT / "src/xstar_tools/xstar/pprint_legacy.py"
RUNNER = ROOT / "tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_3.py"
CURRENT_0274 = any(f'version = "{v}"' in (ROOT / "pyproject.toml").read_text() for v in ("0.6.82.27.4", "0.6.82.27.5", "0.6.82.27.6", "0.6.82.27.7", "0.6.82.27.8", "0.6.82.27.9", "0.6.82.27.10", "0.6.82.27.12"))


def _runner():
    spec = importlib.util.spec_from_file_location("npass0273_runner", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_0682273_cpp_repeated_pass_source_order_ispec_init_unsavd():
    if CURRENT_0274:
        # .27.4 deliberately supersedes the rejected .27.3 INIT/source implementation.
        obj=json.loads((ROOT / "qualification/npass_0_6_82_27_4/npass_hotfix_source_scope_0_6_82_27_4.json").read_text())
        assert obj["predecessor"] == "0.6.82.27.3"
        return
    text = CPP.read_text()
    loop = text[text.index("for (std::size_t kk_v068227 = 1u;"):]
    pos_repeat = loop.index("advance_source_powerlaw_pass_v0682273(data, params)")
    pos_init = loop.index("initialize_native_radial_pass_v068227(data, fixed, message)")
    pos_level_init = loop.index("source_init_repeated_global_workspaces_v0682273(data, program)")
    pos_unsavd = loop.index("restore_saved_shell_v068227")
    assert pos_repeat < pos_init < pos_level_init < pos_unsavd


def test_0682273_cpp_savd_is_sparse_not_dense_checkpoint():
    text = CPP.read_text()
    save = text[text.index("NativeSavedShellV068227 make_saved_shell_v068227"):text.index("void initialize_native_radial_pass_v068227")]
    restore_start = text.index("void restore_saved_shell_v068227(\n    StandaloneControllerDataV67& data")
    restore = text[restore_start:text.index("void project_source_trnfrc_direction_v068227", restore_start)]
    for token in (
        "saved_level_slots_v0682273",
        "saved_line_slots_v0682273",
        "saved_rrc_slots_v0682273",
        "> 1.0e-34",
        "> 1.0e-64",
        "> 1.0e-36",
        "rate_type == 14",
        "rate_type == 9",
    ):
        assert token in save
    assert "for (const std::size_t slot_v0682273 : saved.saved_level_slots_v0682273)" in restore
    assert "for (const std::size_t source_slot : saved.saved_line_slots_v0682273)" in restore
    assert "for (const std::size_t source_slot : saved.saved_rrc_slots_v0682273)" in restore
    assert "data.global_xilevg = snap.source_global_xilevg" not in restore


def test_0682273_cpp_init_seeds_level1_and_preserves_rnist_bilevg():
    if CURRENT_0274:
        # .27.4 deliberately supersedes the rejected .27.3 INIT/source implementation.
        obj=json.loads((ROOT / "qualification/npass_0_6_82_27_4/npass_hotfix_source_scope_0_6_82_27_4.json").read_text())
        assert obj["predecessor"] == "0.6.82.27.3"
        return
    text = CPP.read_text()
    block = text[text.index("void source_init_repeated_global_workspaces_v0682273"):text.index("void restore_saved_shell_v068227")]
    assert "std::fill(data.global_xilevg.begin(), data.global_xilevg.end(), 0.0)" in block
    assert "id_v0682273.upper_index != 1" in block
    assert "1.0 / static_cast<double>(id_v0682273.atomic_number)" in block
    assert "global_rnisg" not in block
    assert "global_bilevg" not in block


def test_0682273_per_pass_source_spectrum_and_lbol_are_retained():
    if CURRENT_0274:
        # .27.4 deliberately supersedes the rejected .27.3 INIT/source implementation.
        obj=json.loads((ROOT / "qualification/npass_0_6_82_27_4/npass_hotfix_source_scope_0_6_82_27_4.json").read_text())
        assert obj["predecessor"] == "0.6.82.27.3"
        return
    cpp = CPP.read_text()
    state = RUNSTATE.read_text()
    step = STEP.read_text()
    assert "next[i] += component[i]" in cpp
    assert "ispecgg.f90 renormalizes the accumulated zremsz" in cpp
    assert "ispcg2_passes.push_back" in cpp
    assert "std::vector<LegacyIspecg2PassState> ispcg2_passes" in state
    assert "std::scientific << std::setprecision(16)" in step
    assert "print_ispcg2_v0682273(pass)" in step


def test_0682273_python_mirrors_sparse_init_and_repeated_spectrum():
    if CURRENT_0274:
        # .27.4 deliberately supersedes the rejected .27.3 INIT/source implementation.
        obj=json.loads((ROOT / "qualification/npass_0_6_82_27_4/npass_hotfix_source_scope_0_6_82_27_4.json").read_text())
        assert obj["predecessor"] == "0.6.82.27.3"
        return
    text = PY_TRANSFER.read_text()
    assert "def _source_sparse_saved_indices_v0682273" in text
    assert "float(xilev[zero]) > 1.0e-34" in text
    assert "rate_type in (9, 14)" in text
    assert "float(opakab[zero]) > 1.0e-36" in text
    assert "def _repeat_source_powerlaw_pass_v0682273" in text
    assert "next_source = current + component" in text
    assert "if kk > 1:\n        _repeat_source_powerlaw_pass_v0682273(state)" in text
    init = text[text.index("def initialize_bounded_radial_pass_state"):text.index("def apply_stpcut_to_state")]
    assert "zero[one - 1] = 1.0 / float(z)" in init
    assert "global_bilevg_by_index" not in init


def test_0682273_python_pprint_uses_scientific_lbol_per_pass():
    text = PY_PPRINT.read_text()
    assert "ispcg2_passes_v0682273" in text
    assert "Lbol=   {float(row['lbol']):.16e}" in text
    assert "Lbol=   {float(state.control['ispcg2_lbol']):.16e}" in text


def test_0682273_runner_uses_correct_detail_surfaces(monkeypatch):
    runner = _runner()
    calls = []

    def fake(path, *, key_candidates, plane_columns):
        calls.append((tuple(key_candidates), tuple(plane_columns)))
        return [{1: (1.0, 2.0)}]

    monkeypatch.setattr(runner, "_detail_two_plane_hdus", fake)
    dummy = Path("dummy.fits")
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    assert runner.compare_detail_tau(dummy, dummy, kind="line")["accept"]
    assert runner.compare_detail_tau(dummy, dummy, kind="rrc")["accept"]
    assert runner.compare_detail_tau(dummy, dummy, kind="continuum")["accept"]
    assert calls == [
        (("index",), ("tau_in", "tau_out")),
        (("index",), ("tau_in", "tau_out")),
        (("rrc index", "index"), ("tau_in", "tau_out")),
        (("rrc index", "index"), ("tau_in", "tau_out")),
        (("index",), ("fwd dpth", "bck dpth")),
        (("index",), ("fwd dpth", "bck dpth")),
    ]


def test_0682273_runner_lbol_parser_accepts_scientific_notation(tmp_path):
    runner = _runner()
    p = tmp_path / "xout_step.log"
    p.write_text(
        " U(1-1.8),U(1.8-4):   2.9e3 2.0e3\n"
        " Lbol=   2.3400564756336129e-06\n"
    )
    assert runner.parse_ispcg2_blocks(p) == [(2900.0, 2000.0, 2.3400564756336129e-06)]
