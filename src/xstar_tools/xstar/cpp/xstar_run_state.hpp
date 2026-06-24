#ifndef XSTAR_RUN_STATE_HPP
#define XSTAR_RUN_STATE_HPP

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace xstar_run_state {

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
    bool runtime_state_abi = false;
    std::vector<double> populations;
    std::vector<double> continuum_spectrum;
    std::vector<double> spectrum;
    std::vector<double> opacity;
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
    double radius_cm = 0.0;             // Python-oracle RINNER
    double outer_radius_cm = 0.0;       // Python-oracle ROUTER
    double delta_radius_cm = 0.0;       // Python-oracle RDEL
    double density_cm3 = 0.0;
    double pressure_dyn_cm2 = 0.0;
    double ionization_parameter = 0.0;  // retained compatibility alias for LOGXI
    double log_ionization_parameter = 0.0;
    double column_density_cm2 = 0.0;
    double temperature_t4 = 0.0;
    double electron_fraction = 0.0;
    bool provisional_from_controller = false;
    bool python_oracle_radial_exact = false;
    AcceptedControllerState accepted_controller;
};


struct XstarRadialPayloadState {
    std::string product;
    std::size_t zone_index = 0;
    std::size_t hdu_index = 0;
    std::size_t row_width = 0;
    std::size_t row_count = 0;
    std::size_t field_count = 0;
    std::string payload_sha256;
    std::filesystem::path payload_path;
    std::vector<unsigned char> payload;
    bool benchmark_exact = false;
};

struct WholeRunAccumulatedState {
    std::string release;
    std::string backend;
    std::filesystem::path parameters_path;
    std::filesystem::path atomic_database_path;
    std::filesystem::path native_case_path;
    std::filesystem::path source_trajectory_path;
    std::filesystem::path product_schema_path;
    std::vector<FixedEvaluationState> fixed_evaluations;
    std::vector<AcceptedControllerState> accepted_controller_states;
    std::vector<RadialZoneState> radial_zones;
    std::vector<ParameterRowState> parameter_rows;
    std::vector<AbundanceRadialRowState> abundance_radial_rows;
    std::vector<XstarRadialPayloadState> xstar_radial_payloads;
    std::size_t python_callbacks = 0;
    bool controller_trajectory_qualified = false;
    bool product_schema_complete = false;
    bool radial_state_complete = false;
    bool xstar_radial_payloads_complete = false;
    bool product_payload_complete = false;
};

struct ProductWritingState {
    std::string release;
    std::string backend;
    std::filesystem::path parameters_path;
    std::filesystem::path atomic_database_path;
    std::filesystem::path schema_path;
    std::vector<RadialZoneState> radial_zones;
    std::vector<ParameterRowState> parameter_rows;
    std::vector<AbundanceRadialRowState> abundance_radial_rows;
    std::vector<XstarRadialPayloadState> xstar_radial_payloads;
    bool run_state_layers_distinct = true;
    bool product_schema_complete = false;
    bool radial_state_complete = false;
    bool xstar_radial_payloads_complete = false;
    bool product_payload_complete = false;
    bool product_state_complete = false;
    bool product_parity_qualified = false;
};

void load_python_product_schema(
    WholeRunAccumulatedState& state,
    const std::filesystem::path& schema_path);
ProductWritingState build_product_writing_state(const WholeRunAccumulatedState& state);
void write_run_state_manifest(
    const std::filesystem::path& path,
    const WholeRunAccumulatedState& whole,
    const ProductWritingState& product);

} // namespace xstar_run_state

#endif
