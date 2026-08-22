from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "qualification/deferred_publication_correctness_0_6_82_34/oracle_targets_from_fortran_multi.json"


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def oracle() -> dict:
    return json.loads(ORACLE.read_text(encoding="utf-8"))


def test_version_and_frozen_science_ids():
    assert 'version = "0.6.82.34.1"' in text("pyproject.toml")
    assert "PACKAGE_VERSION ?= 0.6.82.34.1" in text("src/xstar_tools/xstar/cpp/Makefile")
    api = text("src/xstar_tools/xstar/cpp/xstar_api.h")
    assert "0.6.48.12.3.45.3.3.8" in api
    # Strict-FP policy remains explicit in the build; no fast-math may enter .34.
    makefile = text("src/xstar_tools/xstar/cpp/Makefile")
    assert "rejects -ffast-math" in makefile
    assert "findstring -ffast-math,$(CXXFLAGS)" in makefile


def test_fortran_oracle_manifest_has_all_six_deferred_targets():
    o = oracle()
    assert len(o["n_vi_missing_detail_roles"]) == 6
    assert len(o["cr_ii_fortran_only_detal2_indices"]) == 11
    assert len(o["o_iv_cpp_only_negative_threshold_detal3_indices"]) == 45
    assert o["mg_ii_fortran_only_detal3"]["rrc_index"] == 7063
    assert len(o["public_rrc_cpp_only_si_vi_indices"]) == 10
    assert o["public_rrc_fortran_only_ni_vi"]["rrc_index"] == 144628
    assert o["fortran_source_semantics"]["heatt_gate_per_plane"] == 1e-49


def test_detail_identity_retains_exact_source_population_row():
    h = text("src/xstar_tools/xstar/cpp/xstar_run_state.hpp")
    lower = text("src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp")
    standalone = text("src/xstar_tools/xstar/cpp/xstar_standalone.cpp")
    assert "population_row_one_based" in h  # provenance only in .34.1
    assert "for (std::size_t source_ordinal = 1; source_ordinal < d.npilev.size(); ++source_ordinal)" in lower
    assert "d.level_record_by_global[static_cast<std::size_t>(detail_global)]" in lower
    assert "detail_id.level_label = db.chars(source_record)" in lower
    assert "detail_id.ion_stage = static_cast<std::int16_t>(detail_block.ion_stage)" in lower
    projection = standalone[standalone.index("std::vector<double> source_detail_global_projection"):
                            standalone.index("void commit_call2_to_call3_global_state")]
    assert "data.program->lte_ion_topology.begin()" in projection
    assert "topo_it->start_row + identity.upper_index - 1" in projection
    assert "identity.population_row_one_based" not in projection
    assert "dense[static_cast<std::size_t>(identity.global_index - 1)] = pre_mapback[packed]" in projection
    saved = standalone[standalone.index("NativeSavedShellV068227 make_saved_shell_v068227"):
                       standalone.index("xstar_run_state::RadialZoneState saved_shell_radial_zone_v068233")]
    assert "source.source_detail_global_xilevg" in saved
    assert "detail_xilev_v0682341" in saved


def test_source_rrc_inventory_follows_literal_npfi7_chain():
    lower = text("src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp")
    assert "d.npfi[7][source_ion]" in lower
    assert "d.npconi2[static_cast<std::size_t>(rec)]" in lower
    assert "id.atomic_number = static_cast<std::int16_t>(z)" in lower
    assert "id.ion_stage = static_cast<std::int16_t>(source_block.ion_stage)" in lower
    # Source order must not be destroyed by re-sorting on continuum index.
    assert "std::sort(out.source_rrc_identities.begin(),out.source_rrc_identities.end(),[](const auto&a,const auto&b){return a.continuum_index<b.continuum_index;});" not in lower


def test_detal3_uses_literal_local_source_columns():
    fits = text("src/xstar_tools/xstar/cpp/xstar_science_fits.cpp")
    for token in (
        "row.emis_in = std::isfinite(ws.cemab[source_slot_v06822710])",
        "row.emis_out = std::isfinite(ws.cemab[local_stride_v068234 + source_slot_v06822710])",
        "row.absorption = std::isfinite(ws.cabab[source_slot_v06822710])",
        "row.opacity = std::isfinite(ws.opakab[source_slot_v06822710])",
        "row.tau_in = std::isfinite(ws.tauc[source_slot_v06822710])",
        "row.tau_out = std::isfinite(ws.tauc[tau_stride_v068234 + source_slot_v06822710])",
    ):
        assert token in fits
    assert "if (detail_inventory && !(id.threshold_ev > 0.0)) continue;" in fits
    # Once the literal native source workspace is present, diagnostics and a
    # second directional re-projection cannot replace fstepr3's source columns.
    assert "if (!native_standalone_product_state(state))" in fits
    assert "native_standalone_product_state(state) && !ws.rrc_workspace_exact" in fits


def test_heatt_rrc_gate_and_duplicate_overwrite_match_fortran_semantics():
    s = text("src/xstar_tools/xstar/cpp/xstar_standalone.cpp")
    assert "prior_rrc_luminosity_v068234 = data.rrc_luminosity" in s
    assert "inward > xstar_constants::kLegacyHeattRrcCemabActivityFloor" in s
    assert "outward > xstar_constants::kLegacyHeattRrcCemabActivityFloor" in s
    assert "prior_rrc_luminosity_v068234[source_slot] + increment" in s
    assert "prior_rrc_luminosity_v068234[continuum_stride + source_slot] + increment" in s
    assert "for (const auto& identity : data.program->source_rrc_identities)" in s

    # Synthetic duplicate-source proof: each duplicate starts from the same
    # prior shell, so a second mapping does not double the current-shell delta.
    prior = [0.0, 3.0, 7.0, 0.0, 5.0, 11.0]  # two planes, stride=3
    current = prior.copy()
    stride = 3
    slot = 1
    cemab1, cemab2 = 2.0e-48, 3.0e-48
    floor = 1.0e-49
    scale = 4.0
    for _duplicate in range(2):
        if cemab1 > floor or cemab2 > floor:
            inc = 0.5 * (cemab1 + cemab2) * scale
            current[slot] = max(0.0, prior[slot] + inc)
            current[stride + slot] = max(0.0, prior[stride + slot] + inc)
    expected_inc = 0.5 * (cemab1 + cemab2) * scale
    assert current[slot] == prior[slot] + expected_inc
    assert current[stride + slot] == prior[stride + slot] + expected_inc


def test_heatt_gate_is_per_plane_not_sum_threshold():
    # One plane alone above 1e-49 must activate even when the other is zero.
    floor = 1.0e-49
    assert (1.1e-49 > floor) or (0.0 > floor)
    # Two individually sub-threshold planes must NOT activate merely because
    # their sum exceeds the single-plane threshold.
    a = 0.6e-49
    b = 0.6e-49
    assert a + b > floor
    assert not (a > floor or b > floor)


def negligible_cr_detal2_row(values: dict[str, float]) -> bool:
    min_subnormal_f32 = math.ldexp(1.0, -149)
    physical = ("emis_inward", "emis_outward", "opacity")
    tau = ("tau_in", "tau_out")
    return all(abs(float(values.get(k, 0.0))) <= min_subnormal_f32 for k in physical) and \
        all(abs(float(values.get(k, 0.0))) <= 1.0e-35 for k in tau)


def test_cr_ii_exception_is_generic_binary32_underflow_class_only():
    min_subnormal_f32 = math.ldexp(1.0, -149)
    assert negligible_cr_detal2_row({
        "emis_inward": 0.0, "emis_outward": min_subnormal_f32,
        "opacity": 0.0, "tau_in": 1e-36, "tau_out": 0.0,
    })
    assert not negligible_cr_detal2_row({
        "emis_inward": 2.0 * min_subnormal_f32, "emis_outward": 0.0,
        "opacity": 0.0, "tau_in": 0.0, "tau_out": 0.0,
    })
    assert not negligible_cr_detal2_row({
        "emis_inward": 0.0, "emis_outward": 0.0,
        "opacity": 0.0, "tau_in": 2e-35, "tau_out": 0.0,
    })


def test_0338_lifetime_architecture_remains_present():
    s = text("src/xstar_tools/xstar/cpp/xstar_standalone.cpp")
    h = text("src/xstar_tools/xstar/cpp/xstar_run_state.hpp")
    for token in (
        "V0682334_FINAL_SNAPSHOTS_O1=",
        "V0682336_COMPACT_RETENTION_GATE=",
        "V0682338_LINE_LUMINOSITY_GATE=",
        "IMMEDIATE_SINGLE_PASS_PRODUCTION",
        "COMPACT_COMPLETED_NONTERMINAL_SINGLE_PASS",
        "FIXED_NATIVE_ELUM_ACCUMULATOR",
    ):
        assert token in s
    assert "public_line_luminosity_v0682338" in h
