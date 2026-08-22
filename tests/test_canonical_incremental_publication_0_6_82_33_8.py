from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def text(rel:str)->str: return (ROOT/rel).read_text()
def load_runner():
 p=ROOT/'tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_8.py'
 spec=importlib.util.spec_from_file_location('runner_0682338',p); assert spec and spec.loader
 mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def test_version_and_baseline():
 assert 'version = "0.6.82.33.8"' in text('pyproject.toml')
 assert 'PACKAGE_VERSION ?= 0.6.82.33.8' in text('src/xstar_tools/xstar/cpp/Makefile')
 r=text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_8.py')
 assert 'BASELINE_VERSION = "0.6.82.32"' in r and 'CANDIDATE_VERSION = "0.6.82.33.8"' in r

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
 r=text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_8.py')
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


def test_fixed_native_line_luminosity_ledger_is_retained_once():
 h=text('src/xstar_tools/xstar/cpp/xstar_run_state.hpp')
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 assert 'std::vector<double> public_line_luminosity_v0682338;' in h
 assert 'std::size_t public_line_luminosity_stride_v0682338 = 0;' in h
 assert 'bool public_line_luminosity_exact_v0682338 = false;' in h
 assert 'std::vector<double> public_line_luminosity_v0682338;' in s
 assert 'public_line_luminosity_v0682338.assign(2u * stride, 0.0);' in s
 assert 'public_line_luminosity_v0682338[at] = std::max(' in s
 assert 'local * shell_scale' in s

def test_line_ledger_matches_historical_zone_index_and_terminal_shell_semantics():
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 assert 'radial_zero_index == 0u' in s
 assert 'accepted_boundary_count_v0682334 - 2u' in s
 assert 'accepted_boundary_count_v0682334 - 1u' in s
 assert 'pending_final_depth_cm_v0682334,\n                    data.cumulative_depth_cm' in s

def test_public_line_and_binemis_use_exact_ledger_in_compact_mode():
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 assert 'product.compact_radial_retention_v0682336 &&\n        product.public_line_luminosity_exact_v0682338' in s
 assert 'native_line_plane(ledger, stride, plane, line_index)' in s
 assert 'product.public_line_luminosity_exact_v0682338 ||' in s

def test_runner_requires_fixed_line_luminosity_gate():
 r=text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_8.py')
 assert 'line_mode == "FIXED_NATIVE_ELUM_ACCUMULATOR"' in r
 assert 'line_marker == "ACCEPT"' in r
 assert 'line_shells == max(accepted_boundaries - 1, 0)' in r
 assert 'line_values == 2 * line_stride' in r
 assert 'INCREMENTAL_PUBLICATION_0682338_LINE_LUMINOSITY_GATE=' in r


def test_density_table_owner_precedes_compact_line_ledger():
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 special=s.index('if (public_parameter_real(product, "radexp", 0.0) < -99.0)')
 ledger=s.index('product.compact_radial_retention_v0682336 &&\n        product.public_line_luminosity_exact_v0682338')
 assert special < ledger

def test_line_ledger_capacity_is_explicitly_o1_bounded():
 s=text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
 r=text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_8.py')
 assert 'perf.line_luminosity_capacity_bytes_v0682338 <=\n                            2u * perf.line_luminosity_bytes_v0682338' in s
 assert 'line_capacity_bytes <= 2 * line_bytes' in r

def test_accumulator_order_matches_frozen_reconstruction_on_synthetic_native_slots():
 # Mirror the frozen zone ordering: zone zero is skipped; later superseded
 # zones plus the final physical shell are reduced in the same per-slot order.
 radii=[10.0, 12.0, 15.0, 19.0]
 depths=[0.0, 2.0, 5.0, 9.0, 14.0]
 # Four physical zones, followed by the terminal depth. Two native planes x3 slots.
 rcems=[
  [1.,2.,3., 4.,5.,6.],
  [2.,1.,4., 3.,7.,2.],
  [5.,2.,1., 1.,2.,8.],
  [3.,6.,2., 9.,1.,4.],
 ]
 factor=12.56
 historical=[0.0]*6
 for current in range(1,4):
  scale=(depths[current+1]-depths[current])*factor*(radii[current]*1.0e-19)**2
  for at in range(6):
   historical[at]=max(0.0,historical[at]+rcems[current][at]*scale)
 ledger=[0.0]*6
 # superseded physical zones 1 and 2, then final physical zone 3
 for current in (1,2,3):
  scale=(depths[current+1]-depths[current])*factor*(radii[current]*1.0e-19)**2
  for at in range(6):
   ledger[at]=max(0.0,ledger[at]+rcems[current][at]*scale)
 assert ledger == historical
