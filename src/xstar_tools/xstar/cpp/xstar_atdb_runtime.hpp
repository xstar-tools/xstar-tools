#ifndef XSTAR_ATDB_RUNTIME_HPP
#define XSTAR_ATDB_RUNTIME_HPP

#include "xstar_fixed_state_engine.h"
#include "xstar_run_state.hpp"

#include <cstdint>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace xstar_atdb_runtime {

struct ResolvedAtomicData {
    std::filesystem::path atdb;
    std::filesystem::path coheat;
    std::vector<std::filesystem::path> atdb_candidates;
    std::vector<std::filesystem::path> coheat_candidates;
};

struct ProductionParameters {
    std::filesystem::path source_path;
    std::string raw_json;
    std::map<int,double> abundances_by_z;
    double density_cm3 = 1.0e8;
    double pressure_dyn_cm2 = 0.03;
    double temperature_k = 1.0e6;
    double column_cm2 = 1.0e20;
    double log_xi = 1.5;
    double initial_radius_cm = 1.0e11;
    double covering_fraction = 1.0;
    double emission_multiplier = 0.5;
    double maximum_optical_depth = 5.0;
    double turbulent_velocity_km_s = 0.0;
    double initial_electron_fraction = 1.0;
    double minimum_electron_fraction = 0.1;
    double luminosity_1e38 = 1.0e6;
    double spectral_index = -1.0;
    double radial_density_exponent = 0.0;
    int pressure_mode = 0;
    int spectrum_units = 0;
    std::string spectrum_file = "spect.dat";
    double critical_fraction = 1.0e-6;
    double controller_charge_tolerance = 0.0;
    double controller_thermal_tolerance = 0.0;
    int ncn2 = 9999;
    int nsteps = 10;
    int npass = 1;
    int niter = 99;
    std::string spectrum = "pow";
};

struct ProgramStorage {
    std::string program_id;
    std::vector<xstar_fixed_program_element_v1> elements;
    std::vector<xstar_fixed_program_row_v1> rows;
    std::vector<xstar_fixed_program_record_v1> records;
    std::vector<xstar_fixed_lte_ion_topology_v1> lte_ion_topology;
    std::vector<xstar_fixed_lte_level_v1> lte_levels;
    std::vector<double> reals;
    std::vector<std::int64_t> ints;
    std::vector<xstar_run_state::LevelIdentityState> level_identities;
    std::vector<xstar_run_state::LineIdentityState> line_identities;
    std::vector<xstar_run_state::RrcIdentityState> rrc_identities;
    std::vector<xstar_run_state::ElementMetadataState> element_metadata;
    std::vector<xstar_run_state::CompactRowMetadataState> row_metadata;
    // v82 patch 5.2: compact XSTAR rows can carry more than one source global
    // level role because adjacent ion blocks share their continuum/ground
    // boundary row.  Preserve every source global identity and whether that
    // identity is the terminal-continuum role of its ion.
    std::vector<std::vector<std::int32_t>> row_global_level_aliases;
    std::vector<std::vector<std::uint8_t>> row_global_level_terminal_roles;
    std::uint64_t topology_record_count = 0;
    std::uint64_t unsupported_record_count = 0;
    std::size_t native_line_count = 0;
    std::size_t native_continuum_count = 0;
    std::vector<int> unsupported_data_types;

    xstar_fixed_program_bundle_v1 bundle() const;
};

ProductionParameters read_production_parameters(const std::filesystem::path& path);
ResolvedAtomicData resolve_atomic_data(
    const std::filesystem::path& parameters_path,
    const std::string& parameters_json,
    const std::filesystem::path& executable_path = {});
ProgramStorage lower_atdb_in_memory(
    const std::filesystem::path& atdb,
    const ProductionParameters& parameters);

std::string format_search_candidates(const std::vector<std::filesystem::path>& candidates);

} // namespace xstar_atdb_runtime

#endif
