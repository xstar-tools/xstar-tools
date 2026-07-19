#ifndef XSTAR_RUN_STATE_HPP
#define XSTAR_RUN_STATE_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
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
    std::vector<double> rccemis;
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

struct LegacyPprintState {
    std::vector<LegacyPprintEventState> events;
    std::vector<std::string> buffered_lines;
    bool initialized_from_native_controller = false;
    bool option_sequence_exact = false;
    bool finalized_from_native_controller = false;

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
};

struct FixedEvaluationState {
    std::string kind;
    std::size_t sequence = 0;
    std::size_t call_index = 0;
    std::size_t evaluation_index = 0;
    double temperature_t4 = 0.0;
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
    double brems_cooling = 0.0;
    bool thermal_families_native = false;
    bool runtime_state_abi = false;
    std::vector<double> source_global_rnisg;
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
    bool provisional_from_controller = false;
    bool accepted_boundary_exact = false;
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
    std::vector<AcceptedControllerState> accepted_controller_states;
    std::vector<RadialZoneState> radial_zones;
    std::vector<ParameterRowState> parameter_rows;
    std::vector<ElementMetadataState> element_metadata;
    std::vector<CompactRowMetadataState> row_metadata;
    std::vector<AbundanceRadialRowState> abundance_radial_rows;
    std::vector<LevelIdentityState> level_identities;
    std::vector<LineIdentityState> line_identities;
    std::vector<RrcIdentityState> rrc_identities;
    LegacyPprintState legacy_pprint;
    bool embedded_public_fits_payloads_absent = false;
    bool embedded_full_xout_step_payload_absent = false;
    std::size_t python_callbacks = 0;
    bool controller_trajectory_qualified = false;
    bool product_schema_complete = false;
    bool radial_state_complete = false;
    bool native_product_inputs_complete = false;
    bool native_detail_state_retained = false;
    bool continuum_depths_derived_from_native_opacity = false;
    bool exact_source_metadata_retained = false;
    bool exact_source_workspaces_retained = false;
    bool exact_accepted_radial_boundaries_retained = false;
    bool exact_legacy_pprint_state_retained = false;
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
    std::vector<RadialZoneState> radial_zones;
    std::vector<ParameterRowState> parameter_rows;
    std::vector<ElementMetadataState> element_metadata;
    std::vector<CompactRowMetadataState> row_metadata;
    std::vector<AbundanceRadialRowState> abundance_radial_rows;
    std::vector<LevelIdentityState> level_identities;
    std::vector<LineIdentityState> line_identities;
    std::vector<RrcIdentityState> rrc_identities;
    LegacyPprintState legacy_pprint;
    bool embedded_public_fits_payloads_absent = false;
    bool embedded_full_xout_step_payload_absent = false;
    bool run_state_layers_distinct = true;
    bool product_schema_complete = false;
    bool radial_state_complete = false;
    bool native_product_inputs_complete = false;
    bool native_detail_state_retained = false;
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
    double measured_run_seconds = 0.0;
};

void prepare_native_product_state(
    WholeRunAccumulatedState& state,
    const std::filesystem::path& diagnostics_path);
ProductWritingState build_product_writing_state(const WholeRunAccumulatedState& state);
void write_run_state_manifest(
    const std::filesystem::path& path,
    const WholeRunAccumulatedState& whole,
    const ProductWritingState& product);

} // namespace xstar_run_state

#endif
