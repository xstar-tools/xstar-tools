// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: savd.f90; unsavd.f90; rstepr*.f90; pprint.f90; writespectra*.f90
// Role: Structures for accepted controller state, radial snapshots, exact source workspaces, STEP state,
//   and final product-writing state.
// Relation: C++ storage model for source lifetimes and publication ownership.
// Concordance: STATE-001; DETAIL-001; STEP-001; FINAL-001; TERMINAL-001
// Qualification: 12.3.43-45 lifetime/publication qualification
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_RUN_STATE_HPP
#define XSTAR_RUN_STATE_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <tuple>
#include <vector>

namespace xstar_run_state {


struct ElementMetadataState {
    std::int32_t element_index = 0;
    std::int32_t atomic_number = 0;
    double abundance = 0.0;
    std::int32_t row_offset = 0;
    std::int32_t row_count = 0;
    std::int32_t ion_count = 0;
};

struct CompactRowMetadataState {
    std::int32_t element_index = 0;
    std::int32_t row = 0;
    std::int32_t superlevel = 0;
    std::int32_t ion = 0;
    std::int32_t ion_charge = 0;
    double energy_ev = 0.0;
    double statistical_weight = 1.0;
    std::int32_t principal_n = 0;
    std::int32_t orbital_l = 0;
    std::int32_t global_level_index = 0;
    std::string ion_label;
    std::string level_label;
};

struct LevelIdentityState {
    std::int32_t global_index = 0;
    std::int16_t ion_index = 0;
    double excitation_ev = 0.0;
    std::string ion_label;
    std::int16_t atomic_number = 0;
    std::string level_label;
    std::int16_t upper_index = 0;
};

// `data_type` and `rate_type` retain the two independent atomic-database
// classifications described in XSTAR Manual Chapter 12: data type determines
// record interpretation/rate calculation; rate type determines physical use of
// that returned rate.  Do not collapse them into a single transition-family tag.
struct LineIdentityState {
    std::int32_t line_index = 0;
    double wavelength_angstrom = 0.0;
    std::string ion_label;
    std::string lower_level;
    std::string upper_level;
    std::int32_t rate_type = 0;
    std::int32_t data_type = 0;
    double atomic_mass = 0.0;
    double natural_rate_s = 0.0;
    double auger_width_ev = 0.0;
    double auger_rate_s = 0.0;
    std::int64_t source_record = 0;
    std::int32_t lower_local_index = 0;
    std::int32_t upper_local_index = 0;
    // 0.6.82.29.3.5: pprint(18) publishes the literal Type-13 level
    // metadata returned by calc_rates_level_lte for each line endpoint.
    // These fields are publication metadata only and do not feed solver state.
    double lower_excitation_ev = 0.0;
    double upper_excitation_ev = 0.0;
    double lower_statistical_weight = 0.0;
    double upper_statistical_weight = 0.0;
    double lower_effective_n = 0.0;
    double upper_effective_n = 0.0;
    std::int32_t lower_principal_n = 0;
    std::int32_t upper_principal_n = 0;
    std::int32_t lower_spin_multiplicity = 0;
    std::int32_t upper_spin_multiplicity = 0;
    std::int32_t lower_orbital_l = 0;
    std::int32_t upper_orbital_l = 0;
};

// 0.6.82.29.3.6: publication-only literal calc_hmc_ion/UCalc endpoint
// identity retained for pprint(29).  The two local endpoints are the values
// returned by UCalc before calc_hmc_ion performs any matrix-facing ordering;
// nlev is the current-ion calc_rates_level_lte extent.  This is not part of
// the public fixed-state ABI and never feeds solver, transport, or FITS science.
struct RateIdentityState {
    std::int64_t source_record = 0;
    std::int16_t atomic_number = 0;
    std::int16_t ion_stage = 0;
    std::int16_t nlev = 0;
    std::int32_t data_type = 0;
    std::int32_t rate_type = 0;
    std::int32_t source_idest1 = 0;
    std::int32_t source_idest2 = 0;
};

struct RrcIdentityState {
    std::int32_t continuum_index = 0;
    std::int32_t level_global_index = 0;
    double threshold_ev = 0.0;
    std::string ion_label;
    std::string lower_level;
    std::string upper_level;
    std::int32_t lower_local_index = 0;
    std::int32_t upper_local_index = 0;
    // v0648123421: source publication ownership retained for pprint(19/24).
    // Zero is reserved for legacy/synthetic metadata that predates this field.
    std::int32_t rate_type = 0;
    std::int64_t source_record = 0;
};

struct ExactSourceWorkspaceState {
    std::vector<double> lte_populations;
    std::vector<double> rcem;
    std::vector<double> oplin;
    std::vector<double> tau0;
    std::vector<double> elum;
    std::vector<double> cemab;
    std::vector<double> cabab;
    std::vector<double> opakab;
    std::vector<double> tauc;
    std::vector<double> elumab;
    std::vector<double> zrems;
    std::vector<double> opakc;
    std::vector<double> opakcont;
    // 0.6.82.29.3.3: operational final source flinel continuum array.
    std::vector<double> flinel;
    std::vector<double> rccemis;
    // 0.6.82.29.3.3.1: publication-only pre-GSSMOOTH pprint(4) surfaces.
    // These mirror the post-loop xstarcalc/bremem state consumed by FORTRAN
    // pprint(4) without changing the operational transport workspaces.
    std::vector<double> pprint4_opakc;
    std::vector<double> pprint4_rccemis;
    std::vector<double> pprint4_brcems;
    std::vector<double> pprint4_flinel;
    std::vector<double> dpthc;
    std::vector<double> dpthcont;
    std::vector<double> zremsz;
    std::vector<double> line_profile_workspace;
    std::size_t native_line_count = 0;
    std::size_t native_continuum_count = 0;
    bool level_identity_exact = false;
    bool lte_populations_exact = false;
    bool line_workspace_exact = false;
    bool line_tau_workspace_exact = false;
    bool rrc_workspace_exact = false;
    bool rrc_tau_workspace_exact = false;
    bool continuum_workspace_exact = false;
    bool accumulated_output_workspace_exact = false;
    bool line_profile_workspace_exact = false;

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Report whether complete has all required retained fields for final product publication and terminal-state reconstruction.
    // Reference context: XSTAR Manual ch14 (state lifetime/iteration flow) and ch5 (final products).
    // XSTAR-FUNCTION-COMMENT-END
    bool complete() const {
        return level_identity_exact && lte_populations_exact && line_workspace_exact &&
            line_tau_workspace_exact && rrc_workspace_exact && rrc_tau_workspace_exact &&
            continuum_workspace_exact &&
            accumulated_output_workspace_exact && line_profile_workspace_exact;
    }
};

struct LegacyPprintEventState {
    std::size_t ordinal = 0;
    std::size_t option = 0;
    std::size_t pass_index = 0;
    std::size_t zone_index = 0;
    std::string phase;
    std::string payload;
};

// 0.6.82.27: compact source-pprint(9) trajectory retained across whole-shell
// passes.  The full FixedEvaluationState for old passes is intentionally not
// kept here: FORTRAN persists SAVD/UNSAVD detail state in per-pass FITS files,
// while xout_step.log only needs these scalar/reference-bin surfaces.
struct LegacyPprintRadialRowState {
    std::size_t pass_index = 0;
    int direction = 0;
    std::size_t zone_index = 0;
    double radius_cm = 0.0;
    double radial_depth_cm = 0.0;
    double column_density_cm2 = 0.0;
    double log_ionization_parameter = 0.0;
    double electron_fraction = 0.0;
    double density_cm3 = 0.0;
    double temperature_t4 = 0.0;
    double hmctot = 0.0;
    double radiation_balance_percent = 0.0;
    double forward_reference_tau = 0.0;
    double reverse_reference_tau = 0.0;
    std::size_t dsec_ntotit = 0;
    bool terminal_row = false;
};

struct LegacyIspecg2PassState {
    std::size_t pass_index = 0;
    double u_1_1p8 = 0.0;
    double u_1p8_4 = 0.0;
    double lbol = 0.0;
};

struct LegacyPprintState {
    std::vector<LegacyPprintEventState> events;
    std::vector<LegacyIspecg2PassState> ispcg2_passes;
    std::vector<std::string> buffered_lines;
    std::vector<LegacyPprintRadialRowState> radial_rows;
    bool initialized_from_native_controller = false;
    bool option_sequence_exact = false;
    bool finalized_from_native_controller = false;
    bool radial_pass_trajectory_exact = false;
    // Literal xstar.f90 post-radial block: one zero-thickness xstarcalc with
    // nlimd=0, followed by heatt/stpcut and a 4(1pe16.8) scalar write before
    // pprint(22).  These are computed native values, never oracle inputs.
    bool final_zero_thickness_evaluation_present = false;
    double final_temperature_t4 = 0.0;
    double final_total_heating = 0.0;
    double final_total_cooling = 0.0;
    double final_hmctot = 0.0;

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Report whether complete has all required retained fields for final product publication and terminal-state reconstruction.
    // Reference context: XSTAR Manual ch14 (state lifetime/iteration flow) and ch5 (final products).
    // XSTAR-FUNCTION-COMMENT-END
    bool complete() const {
        return initialized_from_native_controller && option_sequence_exact &&
            finalized_from_native_controller;
    }
};


struct RecordProductDiagnosticState {
    std::int64_t source_position = 0;
    std::int64_t record = 0;
    std::int32_t element_index = 0;
    std::int32_t element_z = 0;
    std::int32_t data_type = 0;
    std::int32_t rate_type = 0;
    std::int32_t ion_stage = 0;
    std::int32_t lower_row = 0;
    std::int32_t upper_row = 0;
    bool spectral = false;
    std::array<double,6> ans{};
    double line_energy_ev = 0.0;
    double atomic_mass_amu = 1.0;
    double density_scale = 1.0;
    double natural_width_ev = 0.0;
    double opakab = 0.0;
    bool type50_valid = false;
    std::int32_t type50_line_index_one_based = 0;
    double type50_wavelength_a = 0.0;
    double type50_ptmp1 = 1.0;
    double type50_ptmp2 = 1.0;
    double type50_tau_in = 0.0;
    double type50_tau_out = 0.0;
    bool type53_valid = false;
    bool type49_valid = false;
    bool type99_valid = false;
    std::int32_t continuum_index_one_based = 0;
    double type53_threshold_ev = 0.0;
    double type53_base_threshold_ev = 0.0;
    double type49_threshold_ev = 0.0;
    double type99_threshold_ev = 0.0;
    double threshold_abs_sigma_cm2 = 0.0;
    double threshold_stimulated_sigma_cm2 = 0.0;
    double type53_ptmp1 = 1.0;
    double type53_ptmp2 = 0.0;
    double type53_tau_in = 0.0;
    double type53_tau_out = 0.0;
};

struct ContinuumProductDiagnosticState {
    std::int32_t full_bin_one_based = 0;
    double energy_ev = 0.0;
    double comp_sum1_contribution = 0.0;
    double comp_sum2_contribution = 0.0;
    double comp_sum3_contribution = 0.0;
    double free_free_opacity_increment = 0.0;
    double brcems = 0.0;
    double running_htcomp = 0.0;
    double running_clcomp = 0.0;
    double running_htfreef = 0.0;
    double running_clbrems = 0.0;
};

struct ElementThermalProductState {
    std::int32_t element_z = 0;
    double heating = 0.0;
    double cooling = 0.0;
    double heating2 = 0.0;
    double cooling2 = 0.0;
};

struct FixedEvaluationState {
    std::string kind;
    std::size_t sequence = 0;
    std::size_t call_index = 0;
    std::size_t evaluation_index = 0;
    double temperature_t4 = 0.0;
    double hydrogen_density_cm3 = 0.0;
    double electron_fraction_input = 0.0;
    double computed_electron_fraction = 0.0;
    double charge_residual = 0.0;
    double hmctot = 0.0;
    double total_heating = 0.0;
    double total_cooling = 0.0;
    double element_heating = 0.0;
    double element_cooling = 0.0;
    double continuum_heating = 0.0;
    double continuum_cooling = 0.0;
    double hydrogen_heating = 0.0;
    double hydrogen_cooling = 0.0;
    double hydrogen_heating2 = 0.0;
    double hydrogen_cooling2 = 0.0;
    double helium_heating = 0.0;
    double helium_cooling = 0.0;
    double helium_heating2 = 0.0;
    double helium_cooling2 = 0.0;
    double magnesium_heating = 0.0;
    double magnesium_cooling = 0.0;
    double magnesium_heating2 = 0.0;
    double magnesium_cooling2 = 0.0;
    double compton_heating = 0.0;
    double compton_cooling = 0.0;
    double free_free_heating = 0.0;
    double brems_cooling = 0.0;
    bool thermal_families_native = false;
    bool runtime_state_abi = false;
    // Dense source xilevg retained at the accepted boundary for publication.
    // This is a writer/addressing surface only; the compact solver population
    // vector remains unchanged.
    std::vector<double> source_global_xilevg;
    std::vector<double> source_global_rnisg;
    // 0.6.82.29.3.1: source pprint(7) publication-only state.  The dense
    // bilevg surface is the already-computed final global departure
    // coefficient; the rate maps are keyed by {Z, ion_stage, local_level}.
    std::vector<double> source_global_bilevg;
    std::map<std::tuple<int,int,int>, double> source_global_gammag;
    std::map<std::tuple<int,int,int>, double> source_global_alphag;
    std::map<std::tuple<int,int,int>, std::int64_t> source_global_igammamaxg;
    std::map<std::tuple<int,int,int>, std::int64_t> source_global_ialphamaxg;
    // Source pprint(12) xii values by atomic number and ion stage.  Unlike
    // full level populations, this surface excludes the compact normalization
    // row when it aliases the next ion ground at a truncated active window.
    std::map<int, std::vector<double>> source_ion_stage_fractions;
    // 0.6.82.29.2: literal calc_ion_rates/pprint(10) full-stage rates.
    // These include source stages outside the compact active matrix window.
    std::map<int, std::vector<double>> source_ionization_rates;
    std::map<int, std::vector<double>> source_recombination_rates;
    // v0.6.48.12.3.18: source fstepr publication lifetime.  Retain the
    // solved compact/full-row surface so the controller can reconstruct the
    // literal calc_hmc_all per-ion global map-back independently of the C++
    // all-row alias expansion.  The tuple is {min_stage,max_stage,full_row_start,full_row_end}.
    std::vector<double> source_detail_pre_mapback_populations;
    std::map<int, std::array<int,4>> source_detail_active_windows;
    // Dense global-level projection used only by fstepr/xo01_detail.
    std::vector<double> source_detail_global_xilevg;
    std::vector<double> populations;
    std::vector<double> radiation_energy_ev;
    std::vector<double> radiation_flux;
    // Size of the source-faithful internal continuum workspace supplied to
    // the fixed-state engine.  This workspace is not the ncn2 output-grid
    // dpthc array and must never be serialized as one.
    std::size_t source_continuum_tau_workspace_count = 0;
    // Output-grid continuum depths derived from the accepted native opacity
    // snapshots during WholeRunAccumulatedState finalization.
    std::vector<double> continuum_tau_in;
    std::vector<double> continuum_tau_out;
    std::vector<double> continuum_spectrum;
    std::vector<double> spectrum;
    std::vector<double> opacity;
    ExactSourceWorkspaceState source_workspace;
    std::vector<RecordProductDiagnosticState> record_product_diagnostics;
    std::vector<ContinuumProductDiagnosticState> continuum_product_diagnostics;
    std::vector<ElementThermalProductState> element_thermal_products;
};

struct AcceptedControllerState {
    std::size_t call_index = 0;
    std::size_t accepted_sequence = 0;
    std::string acceptance_reason;
    FixedEvaluationState evaluation;
};

struct ParameterRowState {
    std::uint16_t index = 0;
    std::string parameter;
    std::uint32_t value_bits = 0;
    std::string type;
    std::string comment;
};

struct AbundanceRadialRowState {
    std::size_t row_index = 0;
    double radius_cm = 0.0;
    double delta_radius_cm = 0.0;
    double log_ionization_parameter = 0.0;
    double electron_fraction = 0.0;
    double density_cm3 = 0.0;
    double pressure_dyn_cm2 = 0.0;
    double temperature_t4 = 0.0;
    double fractional_heat_error = 0.0;
    bool terminal_row = false;
};

// 0.6.82.33.2: compact provenance for detal2 cells whose published value
// depends on the deferred whole-run terminal ion-stage gate.  Incremental
// SAVD publication writes the source-workspace base value immediately and
// records only diagnostic refinements that must be applied after the terminal
// publication state exists.  This preserves the accepted .32 payload without
// retaining the full SAVD history.
struct IncrementalDetal2TerminalPatchStateV0682332 {
    std::size_t pass_index = 0;
    std::size_t hdu_number = 0;
    std::size_t row_number = 0;
    std::int32_t element_z = 0;
    std::int32_t ion_stage = 0;
    bool emis_inward_from_diagnostic = false;
    bool emis_outward_from_diagnostic = false;
    bool opacity_from_diagnostic = false;
    double diagnostic_emis_inward = 0.0;
    double diagnostic_emis_outward = 0.0;
    double diagnostic_opacity = 0.0;
};

// 0.6.82.33.6: production-only compact retained radial state.  Once the
// source SAVD detail HDUs for a completed nonterminal zone have been streamed,
// the whole-run owner no longer needs the dense line/RRC/detail workspaces.
// Keep only the continuum/thermal surfaces still consumed by final STEP and
// product projection.  Diagnostic/reference/multipass paths never use this
// record and continue retaining the full RadialZoneState.
struct CompactSourceWorkspaceStateV0682336 {
    std::vector<double> rccemis;
    std::vector<double> zrems;
    std::vector<double> opakc;
    std::vector<double> opakcont;
    std::vector<double> dpthc;
    std::vector<double> dpthcont;
    std::vector<double> zremsz;
    std::size_t native_line_count = 0;
    std::size_t native_continuum_count = 0;
    bool continuum_workspace_exact = false;
    bool accumulated_output_workspace_exact = false;
};

struct CompactFixedEvaluationStateV0682336 {
    std::string kind;
    std::size_t sequence = 0;
    std::size_t call_index = 0;
    std::size_t evaluation_index = 0;
    double temperature_t4 = 0.0;
    double hydrogen_density_cm3 = 0.0;
    double electron_fraction_input = 0.0;
    double computed_electron_fraction = 0.0;
    double charge_residual = 0.0;
    double hmctot = 0.0;
    double total_heating = 0.0;
    double total_cooling = 0.0;
    // 0.6.82.33.7: xout_abund1 is deferred whole-run publication, so
    // historical compact zones must retain the tiny source xii and thermal
    // surfaces consumed by ABUNDANCES/COLUMNS/HEATING/COOLING.  These are
    // publication values only; dense line/RRC/detail workspaces stay dropped.
    double hydrogen_heating = 0.0;
    double hydrogen_cooling = 0.0;
    double helium_heating = 0.0;
    double helium_cooling = 0.0;
    double magnesium_heating = 0.0;
    double magnesium_cooling = 0.0;
    double compton_heating = 0.0;
    double compton_cooling = 0.0;
    double free_free_heating = 0.0;
    double brems_cooling = 0.0;
    bool thermal_families_native = false;
    std::map<int, std::vector<double>> source_ion_stage_fractions;
    std::vector<ElementThermalProductState> element_thermal_products;
    std::vector<double> radiation_energy_ev;
    std::vector<double> radiation_flux;
    std::vector<double> continuum_tau_in;
    std::vector<double> continuum_tau_out;
    std::vector<double> continuum_spectrum;
    std::vector<double> spectrum;
    std::vector<double> opacity;
    CompactSourceWorkspaceStateV0682336 source_workspace;
};

struct CompactRadialZoneStateV0682336 {
    std::size_t zone_index = 0;
    std::size_t pass_index = 0;
    double radius_cm = 0.0;
    double outer_radius_cm = 0.0;
    double delta_radius_cm = 0.0;
    double density_cm3 = 0.0;
    double pressure_dyn_cm2 = 0.0;
    double ionization_parameter = 0.0;
    double log_ionization_parameter = 0.0;
    double column_density_cm2 = 0.0;
    double temperature_t4 = 0.0;
    double electron_fraction = 0.0;
    std::size_t dsec_ntotit = 0;
    bool provisional_from_controller = false;
    bool accepted_boundary_exact = false;
    std::string boundary_provenance;
    std::size_t accepted_call_index = 0;
    std::size_t accepted_sequence = 0;
    std::string acceptance_reason;
    CompactFixedEvaluationStateV0682336 evaluation;
};

struct RadialZoneState {
    std::size_t zone_index = 0;
    std::size_t pass_index = 0;
    double radius_cm = 0.0;
    double outer_radius_cm = 0.0;
    double delta_radius_cm = 0.0;
    double density_cm3 = 0.0;
    double pressure_dyn_cm2 = 0.0;
    double ionization_parameter = 0.0;  // retained compatibility alias for LOGXI
    double log_ionization_parameter = 0.0;
    double column_density_cm2 = 0.0;
    double temperature_t4 = 0.0;
    double electron_fraction = 0.0;
    // Literal thermal-engine DSEC ntotit retained at the accepted physical
    // boundary for both live pprint-style output and xout_step.log.
    std::size_t dsec_ntotit = 0;
    bool provisional_from_controller = false;
    bool accepted_boundary_exact = false;
    // 0.6.82.33.6: true only for a completed nonterminal ordinary-production
    // zone materialized from CompactRadialZoneStateV0682336.  Its streamed
    // detail workspaces are intentionally absent; continuum/STEP surfaces
    // remain exact.
    bool compact_retained_v0682336 = false;
    std::string boundary_provenance;
    AcceptedControllerState accepted_controller;
};


struct WholeRunAccumulatedState {
    std::string release;
    std::string backend;
    std::filesystem::path parameters_path;
    std::filesystem::path atomic_database_path;
    std::filesystem::path native_case_path;
    std::filesystem::path source_trajectory_path;
    std::filesystem::path product_schema_path;
    std::filesystem::path product_metadata_path;
    std::filesystem::path native_diagnostics_path;
    std::string native_run_id;
    std::vector<FixedEvaluationState> fixed_evaluations;
    // v82 patch 5.20.14.4: literal xstar.f90 performs one additional
    // zero-thickness local recomputation after the radial loop and uses that
    // local HEATT state for writespectra/writespectra3.  It is deliberately
    // separate from the canonical fixed-state/DSEC trajectory.
    std::optional<FixedEvaluationState> final_writer_evaluation;
    std::vector<AcceptedControllerState> accepted_controller_states;
    std::vector<RadialZoneState> radial_zones;
    // 0.6.82.27.3: source SAVD detail surfaces retained per whole-shell pass.
    // Each inner vector is physical FITS-HDU order for pass index outer+1.
    std::vector<std::vector<RadialZoneState>> multipass_detail_radial_zones;
    std::vector<ParameterRowState> parameter_rows;
    std::vector<ElementMetadataState> element_metadata;
    std::vector<CompactRowMetadataState> row_metadata;
    std::vector<AbundanceRadialRowState> abundance_radial_rows;
    std::vector<LevelIdentityState> level_identities;
    // v0.6.48.12.3.19: literal fstepr identity inventory.  Adjacent ion
    // blocks share one compact continuum/next-ground row, but fstepr walks
    // the source npilev roles separately and therefore publishes both global
    // identities when the shared population passes the source threshold.
    std::vector<LevelIdentityState> detail_level_identities;
    // 0.6.82.29.3.6: literal UCalc endpoint sidecar for pprint(29).
    std::vector<RateIdentityState> source_rate_identities;
    std::vector<LineIdentityState> line_identities;
    std::vector<RrcIdentityState> rrc_identities;
    // v0.6.48.12.3.42.1.2: preserve the exact ATDB/source RRC identity
    // inventory before the legacy 1849-slot FITS compatibility padding.
    // STEP pprint(19/24) must walk this source inventory; FITS continues to
    // use rrc_identities unchanged.
    std::vector<RrcIdentityState> source_rrc_identities;
    LegacyPprintState legacy_pprint;
    bool embedded_public_fits_payloads_absent = false;
    bool embedded_full_xout_step_payload_absent = false;
    std::size_t python_callbacks = 0;
    bool controller_trajectory_qualified = false;
    bool product_schema_complete = false;
    bool radial_state_complete = false;
    bool native_product_inputs_complete = false;
    bool native_detail_state_retained = false;
    // 0.6.82.33: npass=1 source-SAVD detail products can be serialized at
    // the canonical radial event and released immediately rather than retained
    // for whole-run publication.
    bool incremental_detail_products_complete_v068233 = false;
    // 0.6.82.33.6: ordinary single-pass production retained completed
    // nonterminal zones in compact form after their SAVD detail products were
    // streamed.  This is a publication-lifetime marker only.
    bool compact_radial_retention_v0682336 = false;
    // 0.6.82.33.2: bounded patch ledger for the one detail-line dependency
    // that is not knowable at the live SAVD event: the final terminal
    // ion-stage activity gate used by the accepted .32 detal2 writer.
    std::vector<IncrementalDetal2TerminalPatchStateV0682332>
        incremental_detal2_terminal_patches_v0682332;
    bool continuum_depths_derived_from_native_opacity = false;
    bool exact_source_metadata_retained = false;
    bool exact_source_workspaces_retained = false;
    bool exact_accepted_radial_boundaries_retained = false;
    bool exact_legacy_pprint_state_retained = false;
    // v82 patch 5.15: distinguish real physical boundaries from the
    // source terminal synthetic abundance-reset row in diagnostic previews.
    bool diagnostic_preview_partial = false;
    std::size_t physical_radial_boundaries_expected = 0;
    std::size_t physical_radial_boundaries_retained = 0;
    std::size_t physical_transport_intervals_completed = 0;
    bool terminal_synthetic_row_present = false;
};

struct ProductWritingState {
    std::string release;
    std::string backend;
    std::filesystem::path parameters_path;
    std::filesystem::path atomic_database_path;
    std::filesystem::path schema_path;
    std::filesystem::path product_metadata_path;
    std::filesystem::path native_diagnostics_path;
    std::string native_run_id;
    std::vector<FixedEvaluationState> fixed_evaluations;
    std::optional<FixedEvaluationState> final_writer_evaluation;
    std::vector<RadialZoneState> radial_zones;
    // 0.6.82.27.3: source SAVD detail surfaces retained per whole-shell pass.
    // Each inner vector is physical FITS-HDU order for pass index outer+1.
    std::vector<std::vector<RadialZoneState>> multipass_detail_radial_zones;
    std::vector<ParameterRowState> parameter_rows;
    std::vector<ElementMetadataState> element_metadata;
    std::vector<CompactRowMetadataState> row_metadata;
    std::vector<AbundanceRadialRowState> abundance_radial_rows;
    std::vector<LevelIdentityState> level_identities;
    // v0.6.48.12.3.19: literal fstepr identity inventory.  Adjacent ion
    // blocks share one compact continuum/next-ground row, but fstepr walks
    // the source npilev roles separately and therefore publishes both global
    // identities when the shared population passes the source threshold.
    std::vector<LevelIdentityState> detail_level_identities;
    // 0.6.82.29.3.6: literal UCalc endpoint sidecar for pprint(29).
    std::vector<RateIdentityState> source_rate_identities;
    std::vector<LineIdentityState> line_identities;
    std::vector<RrcIdentityState> rrc_identities;
    // v0.6.48.12.3.42.1.2: preserve the exact ATDB/source RRC identity
    // inventory before the legacy 1849-slot FITS compatibility padding.
    // STEP pprint(19/24) must walk this source inventory; FITS continues to
    // use rrc_identities unchanged.
    std::vector<RrcIdentityState> source_rrc_identities;
    LegacyPprintState legacy_pprint;
    bool embedded_public_fits_payloads_absent = false;
    bool embedded_full_xout_step_payload_absent = false;
    bool run_state_layers_distinct = true;
    bool product_schema_complete = false;
    bool radial_state_complete = false;
    bool native_product_inputs_complete = false;
    bool native_detail_state_retained = false;
    // 0.6.82.33: npass=1 source-SAVD detail products can be serialized at
    // the canonical radial event and released immediately rather than retained
    // for whole-run publication.
    bool incremental_detail_products_complete_v068233 = false;
    // 0.6.82.33.6 compact historical radial-zone retention marker copied
    // from WholeRunAccumulatedState.
    bool compact_radial_retention_v0682336 = false;
    // 0.6.82.33.2: bounded patch ledger for the one detail-line dependency
    // that is not knowable at the live SAVD event: the final terminal
    // ion-stage activity gate used by the accepted .32 detal2 writer.
    std::vector<IncrementalDetal2TerminalPatchStateV0682332>
        incremental_detal2_terminal_patches_v0682332;
    bool continuum_depths_derived_from_native_opacity = false;
    bool exact_source_metadata_retained = false;
    bool exact_source_workspaces_retained = false;
    bool exact_accepted_radial_boundaries_retained = false;
    bool exact_legacy_pprint_state_retained = false;
    bool product_state_complete = false;
    bool product_parity_qualified = false;
    bool xout_abund1_computed_from_native_state = false;
    bool xout_cont1_computed_from_native_state = false;
    bool xout_lines1_computed_from_native_state = false;
    bool xout_rrc1_computed_from_native_state = false;
    bool xout_spect1_computed_from_native_state = false;
    bool xout_step_computed_from_native_state = false;
    bool xout_step_timing_values_measured = false;
    // Legacy pre-publication/controller timing retained for compatibility.
    double measured_run_seconds = 0.0;
    // 0.6.82.30.8.8: explicit timing ownership for STEP publication.
    double measured_controller_seconds = 0.0;
    double measured_publication_before_step_seconds = 0.0;
    double measured_end_to_end_before_step_seconds = 0.0;
    // v82 patch 5.20.17.2: file-silent production carries the exact
    // product-write arrays in memory.  Diagnostic/replay modes may still
    // persist the same arrays through exact_product_state_bridge.
    std::map<std::string,std::vector<double>> retained_product_arrays;
    // v82 patch 5.15: copied from WholeRunAccumulatedState.
    bool diagnostic_preview_partial = false;
    std::size_t physical_radial_boundaries_expected = 0;
    std::size_t physical_radial_boundaries_retained = 0;
    std::size_t physical_transport_intervals_completed = 0;
    bool terminal_synthetic_row_present = false;
};

void prepare_native_product_state(
    WholeRunAccumulatedState& state,
    const std::filesystem::path& diagnostics_path);
ProductWritingState build_product_writing_state(const WholeRunAccumulatedState& state);
ProductWritingState build_product_writing_state(WholeRunAccumulatedState&& state);
void write_run_state_manifest(
    const std::filesystem::path& path,
    const WholeRunAccumulatedState& whole,
    const ProductWritingState& product);

} // namespace xstar_run_state

#endif
