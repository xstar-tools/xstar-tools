from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp"
STATE = ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp"
STEP = ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp"
MANIFEST = ROOT / "qualification/npass_0_6_82_27/npass_source_scope_0_6_82_27.json"


def _function(text: str, signature: str, next_marker: str) -> str:
    start = text.index(signature)
    end = text.index(next_marker, start)
    return text[start:end]


def test_068227_version_and_frozen_identifiers():
    pyproject = (ROOT / "pyproject.toml").read_text()
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    current_027 = 'version = "0.6.82.27"' in pyproject
    current_0271 = 'version = "0.6.82.27.1"' in pyproject
    current_0272 = 'version = "0.6.82.27.3"' in pyproject or 'version = "0.6.82.27.4"' in pyproject or 'version = "0.6.82.27.5"' in pyproject or ('version = "0.6.82.27.6"' in pyproject or ('version = "0.6.82.27.7"' in pyproject or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject)) or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject))
    assert current_027 or current_0271 or current_0272
    assert any(f"PACKAGE_VERSION ?= {v}" in makefile for v in ("0.6.82.27","0.6.82.27.1","0.6.82.27.3","0.6.82.27.4","0.6.82.27.5","0.6.82.27.6", "0.6.82.27.7", "0.6.82.27.8", "0.6.82.27.9"))
    # Frozen science/ABI values remain source-visible through the accepted contract.
    all_text = "\n".join(
        p.read_text(errors="ignore")
        for p in (ROOT / "src/xstar_tools/xstar/cpp").glob("*.h")
    ) + "\n" + "\n".join(
        p.read_text(errors="ignore")
        for p in (ROOT / "src/xstar_tools/xstar/cpp").glob("*.hpp")
    )
    assert "60487" in all_text
    assert "6048110" in all_text
    assert "60488" in all_text


def test_068227_numerical_change_scope_is_three_native_files_only():
    manifest = json.loads(MANIFEST.read_text())
    expected = [
        "src/xstar_tools/xstar/cpp/xstar_run_state.hpp",
        "src/xstar_tools/xstar/cpp/xstar_standalone.cpp",
        "src/xstar_tools/xstar/cpp/xstar_step_log.cpp",
    ]
    assert manifest["numerical_source_count_predecessor"] == 137
    assert manifest["intentional_numerical_source_changes"] == expected
    pyproject = (ROOT / "pyproject.toml").read_text()
    hotfix = ('version = "0.6.82.27.1"' in pyproject) or ('version = "0.6.82.27.3"' in pyproject) or ('version = "0.6.82.27.4"' in pyproject) or ('version = "0.6.82.27.5"' in pyproject) or (('version = "0.6.82.27.6"' in pyproject or ('version = "0.6.82.27.7"' in pyproject or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject)) or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject)))
    if hotfix:
        successor = json.loads((ROOT / "qualification/npass_0_6_82_27_1/npass_hotfix_source_scope_0_6_82_27_1.json").read_text())
        # Preserve the historical .27 chain without pretending its rejected
        # SAVD ordering is still the candidate: the .27 candidate byte hashes
        # must exactly be the .27.1 predecessor hashes.
        current_0272 = 'version = "0.6.82.27.3"' in pyproject or 'version = "0.6.82.27.4"' in pyproject or 'version = "0.6.82.27.5"' in pyproject or ('version = "0.6.82.27.6"' in pyproject or ('version = "0.6.82.27.7"' in pyproject or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject)) or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject))
        successor2 = json.loads((ROOT / "qualification/npass_0_6_82_27_2/npass_hotfix_source_scope_0_6_82_27_2.json").read_text()) if current_0272 else None
        for rel, old_hash in manifest["predecessor_sha256"].items():
            expected_027 = manifest["candidate_changed_sha256"].get(rel, old_hash)
            assert successor["predecessor_sha256"][rel] == expected_027, rel
            expected_0271 = successor["candidate_changed_sha256"].get(rel, expected_027)
            if successor2 is not None:
                assert successor2["predecessor_sha256"][rel] == expected_0271, rel
    else:
        predecessor = manifest["predecessor_sha256"]
        changed = set(expected)
        for rel, old_hash in predecessor.items():
            path = ROOT / rel
            current = hashlib.sha256(path.read_bytes()).hexdigest()
            if rel in changed:
                assert current == manifest["candidate_changed_sha256"][rel]
                assert current != old_hash
            else:
                assert current == old_hash, rel


def test_068227_native_outer_pass_schedule_and_source_numrec_contract():
    text = CPP.read_text()
    assert "const std::size_t effective_npass_v068227 = requested_npass_v068227;" in text
    assert "Fresh xstar.f90 runs initialize numrec=2" in text
    assert "kk_v068227 <= effective_npass_v068227" in text
    assert "data.radial_direction_v068227 = (kk_v068227 % 2u == 1u) ? -1 : 1;" in text
    assert "source_numrec_v068227 = finals.size() + 1u;" in text
    assert "call < source_numrec_v068227 && density_iostat_v068226 == 0" in text
    assert "continue_after_zone_v0648110 && kk_v068227 == 1u" in text


def test_068227_native_unsavd_reverse_hdu_and_direction_owned_tau_restore():
    text = CPP.read_text()
    assert "const std::size_t jk_v068227 = source_numrec_v068227 + 1u - call;" in text
    assert "const std::size_t restore_hdu_v068227 = jk_v068227 + 2u;" in text
    restore = _function(text, "void restore_saved_shell_v068227(", "void project_source_trnfrc_direction_v068227(")
    assert "const std::size_t plane = radial_direction > 0 ? 0u : 1u;" in restore
    if 'version = "0.6.82.27.9"' in (ROOT / "pyproject.toml").read_text():
        # .27.9 corrects the earlier interpretation: literal rstepr2/rstepr3
        # restore both saved line/RRC tau columns; dpthc remains direction-owned.
        assert restore.count("for (std::size_t plane = 0u; plane < 2u; ++plane)") >= 2
        assert "literal rstepr2.f90 restores BOTH tau0 columns" in restore
        assert "rstepr3.f90 likewise restores both tauc columns" in restore
    else:
        assert "radial_direction > 0 ? data.product_line_tau_in : data.product_line_tau_out" in restore
        assert "radial_direction > 0 ? data.product_rrc_tau_in : data.product_rrc_tau_out" in restore
    assert "radial_direction > 0 ? data.grid_tau_in : data.grid_tau_out" in restore
    # Source UNSAVD reads zrems into a local temporary and intentionally does not restore it.
    assert "data.accumulated_zrems = snap.zrems" not in restore
    assert "dpthcont is not written by savd.f90/rstepr4.f90" in restore


def test_068227_native_savd_models_real4_and_cfitsio_hdu_insertion():
    text = CPP.read_text()
    saved = _function(text, "struct NativeSavedPassV068227", "void initialize_native_radial_pass_v068227(")
    pyproject = (ROOT / "pyproject.toml").read_text()
    if ('version = "0.6.82.27.1"' in pyproject) or ('version = "0.6.82.27.3"' in pyproject) or ('version = "0.6.82.27.4"' in pyproject) or ('version = "0.6.82.27.5"' in pyproject) or (('version = "0.6.82.27.6"' in pyproject or ('version = "0.6.82.27.7"' in pyproject or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject)) or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject))):
        assert "hdus.push_back(std::move(shell));" in saved
        assert "hdus.insert(hdus.begin()" not in saved
    else:
        assert "hdus.insert(hdus.begin() + static_cast<std::ptrdiff_t>(hdu + 1u)" in saved
    assert "static_cast<double>(static_cast<float>(value))" in saved
    for name in (
        "source_global_xilevg", "source_global_rnisg", "rcem", "oplin", "tau0",
        "cemab", "cabab", "opakab", "tauc", "zrems", "dpthc", "opakc", "rccemis",
    ):
        assert f"source_real4_vector_v068227(out.snapshot.{name})" in saved
    # Boundary SAVD precedes geometry/STPCUT, and the terminal duplicate SAVD is retained.
    first_save = text.index("saved_passes_v068227[kk_v068227].insert_after_hdu(\n                    call + 1u")
    geometry = text.index("double source_geometry_segment_v068226 = segment;", first_save)
    stpcut = text.index("advance_stpcut_depths(", geometry)
    assert first_save < geometry < stpcut
    assert "saved_passes_v068227[kk_v068227].insert_after_hdu(\n                    finals.size() + 1u" in text


def test_068227_native_init_trnfrc_stpcut_and_nlimdt_follow_direction():
    text = CPP.read_text()
    init = _function(text, "void initialize_native_radial_pass_v068227(", "void restore_saved_shell_v068227(")
    for field in (
        "source_tau_in", "source_tau_out", "line_tau_in", "line_tau_out",
        "grid_tau_in", "grid_tau_out", "line_luminosity", "rrc_luminosity",
    ):
        assert f"std::fill(data.{field}.begin(), data.{field}.end(), 0.0);" in init
    assert "data.accumulated_zrems.assign(5u * n, 0.0);" in init
    assert "data.accumulated_zrems[i] = data.source_incident[i];" in init

    trnfrc = _function(text, "void project_source_trnfrc_direction_v068227(", "std::size_t source_pprint_nry_zero_based_v068227(")
    assert "if (radial_direction > 0)" in trnfrc
    assert "data.accumulated_zremsz[i] * std::exp(-tau) / fpr2" in trnfrc
    assert "data.accumulated_zrems[i] / fpr2" in trnfrc

    assert "(kk_v068227 > 1u && data.radial_direction_v068227 > 0) ? 0 : params.niter" in text
    assert "advance_stpcut_depths(\n                    data, boundary, source_geometry_segment_v068226, post_geometry_density_cm3_v068226,\n                    data.radial_direction_v068227)" in text


def test_068227_final_products_are_final_pass_only_but_step_keeps_all_passes():
    cpp = CPP.read_text()
    state = STATE.read_text()
    step = STEP.read_text()
    assert "if (kk_v068227 > 1u) {\n                finals.clear();" in cpp
    assert "zone.pass_index = data.radial_pass_index_v068227;" in cpp
    assert "LegacyPprintRadialRowState" in state
    assert "radial_pass_trajectory_exact" in state
    assert "for (std::size_t pass = 1u; pass <= requested_passes; ++pass)" in step
    assert "if (r.pass_index != pass) continue;" in step
    assert "Preserve the already-qualified npass=1 serializer unchanged." in step


def test_068227_python_secondary_oracle_already_has_literal_multipass_contract():
    control = (ROOT / "src/xstar_tools/xstar/radial_control.py").read_text()
    transfer = (ROOT / "src/xstar_tools/xstar/radial_transfer.py").read_text()
    driver = (ROOT / "src/xstar_tools/xstar/driver.py").read_text()
    saved = (ROOT / "src/xstar_tools/xstar/saved_radial_state.py").read_text()
    assert "effective = 1 if initial_numrec <= 0 else requested" in control
    assert "directions = tuple(int((-1) ** kk) for kk in range(1, effective + 1))" in control
    assert "jk = numrec + 1 - jkp" in driver
    assert "result.control[\"unsavd_jkstep\"] = jk + 2" in driver
    assert 'result.control["nlimdt"] = 0 if ldir > 0 else nlimd' in driver
    assert "values written by the ``fstepr*`` helpers are rounded through REAL(4)" in saved
    assert "saved ``zrems`` table is deliberately read into a local temporary" in saved
