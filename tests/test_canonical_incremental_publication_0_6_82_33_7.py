from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def text(rel:str)->str: return (ROOT/rel).read_text()
def load_runner():
 p=ROOT/'tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_7.py'
 spec=importlib.util.spec_from_file_location('runner_0682337',p); assert spec and spec.loader
 mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def test_version_and_baseline():
 assert 'version = "0.6.82.33.7"' in text('pyproject.toml')
 assert 'PACKAGE_VERSION ?= 0.6.82.33.7' in text('src/xstar_tools/xstar/cpp/Makefile')
 r=text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_7.py')
 assert 'BASELINE_VERSION = "0.6.82.32"' in r and 'CANDIDATE_VERSION = "0.6.82.33.7"' in r

def test_zero_preserving_parser_retained():
 r=load_runner(); assert r.metric_int({'x':0},'x',999)==0; assert r.metric_int({},'x',999)==999

def test_0335_pending_snapshot_mechanism_is_retained():
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 assert 'std::optional<FixedDsecSnapshot> pending_final_snapshot_v0682334;' in s
 assert 'V0682334_FINAL_SNAPSHOTS_O1=' in s
 assert 'final_snapshots_peak_count_v0682334 <= 1u' in s

def test_compact_scope_is_single_pass_streamed_production_only():
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 assert 'compact_radial_retention_v0682336 =\n            immediate_final_transfer_v0682334 && incremental_detail_stream_v068233;' in s
 assert 'effective_npass_v068227 == 1u' in s
 assert '!data.reference_diagnostics_enabled' in s and '!data.diagnostic_full_trajectory_continue' in s

def test_completed_historical_zone_uses_compact_record():
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 assert 'append_compact_zone_v0682336' in s
 assert 'copy_compact_real_native_snapshot_v0682336' in s
 assert 'standalone C++ compact completed nonterminal boundary' in s

def test_dense_historical_line_rrc_workspaces_are_not_reexpanded():
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 assert 'if (i > 0u && !zone.compact_retained_v0682336)' in s
 assert 'ws.line_workspace_exact = false;' in s
 assert 'ws.rrc_workspace_exact = false;' in s

def test_compact_contract_keeps_continuum_step_surfaces():
 h=text('src/xstar_tools/xstar/cpp/xstar_run_state.hpp')
 for f in ('rccemis','zrems','opakc','opakcont','dpthc','dpthcont','zremsz','radiation_energy_ev','radiation_flux'):
  assert f in h
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 assert 'ws.continuum_workspace_exact && ws.accumulated_output_workspace_exact' in s

def test_terminal_two_full_zone_bound_and_compact_gate():
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 assert 'compact_radial_zones_v0682336.size() + 2u' in s
 assert 'perf.full_radial_zones_peak_count_v0682336 <= 2u' in s
 assert 'V0682336_COMPACT_RETENTION_GATE=' in s

def test_runner_requires_compact_gate_and_tighter_c5_memory():
 r=text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_7.py')
 assert 'compact_marker == "ACCEPT"' in r
 assert 'full_radial_peak_count <= 2' in r
 assert 'compact_materialized == max(accepted_boundaries - 1, 0)' in r
 assert 'rss_ratio <= 0.20' in r
 assert 'compare_fits_payloads' in r and 'hashlib.sha256(payload)' in r

def test_deferred_034_scope_is_unchanged():
 c=text('CHANGELOG.md')
 for x in ('0.6.82.34','N VI','Cr II','O IV','Mg II','cemab/cabab/opakab/tauc','Si VI / Ni VI','1e-49'):
  assert x in c


def test_compact_history_retains_deferred_abundance_publication_surfaces():
 h=text('src/xstar_tools/xstar/cpp/xstar_run_state.hpp')
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 for token in ('source_ion_stage_fractions','element_thermal_products','hydrogen_heating','helium_heating','magnesium_heating','compton_heating','compton_cooling','brems_cooling','thermal_families_native'):
  assert token in h
 assert 'target.source_ion_stage_fractions = source.source_ion_stage_fractions;' in s
 assert 'target.element_thermal_products = source.element_thermal_products;' in s
 assert 'target.source_ion_stage_fractions = std::move(source.source_ion_stage_fractions);' in s
 assert 'target.element_thermal_products = std::move(source.element_thermal_products);' in s
 assert 'add_map_vector_memory_v068233(out, e.source_ion_stage_fractions);' in s
 assert 'add_vector_memory_v068233(out, e.element_thermal_products);' in s

def test_dense_detail_state_stays_dropped_in_compact_history():
 h=text('src/xstar_tools/xstar/cpp/xstar_run_state.hpp')
 start=h.index('struct CompactFixedEvaluationStateV0682336')
 end=h.index('struct CompactRadialZoneStateV0682336')
 block=h[start:end]
 for forbidden in ('source_global_xilevg','source_global_bilevg','source_global_gammag','source_detail_pre_mapback_populations','populations','record_product_diagnostics'):
  assert forbidden not in block
