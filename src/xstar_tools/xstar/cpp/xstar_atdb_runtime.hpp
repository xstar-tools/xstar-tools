// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: xstarsetup.f90; readtbl.f90; setptrs.f90; rread1.f90
// Role: Native atomic-data/parameter structures exposing the source database topology to production
//   engines.
// Relation: Storage/interface representation of the source reader and setptrs relationships.
// Concordance: DB-001; INPUT-001
// Qualification: C++ baseline 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_ATDB_RUNTIME_HPP
#define XSTAR_ATDB_RUNTIME_HPP

#include "xstar_local_zone_engine.h"
#include "xstar_run_state.hpp"
#include "xstar_parameter_contract.hpp"

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
    // User-facing density is retained separately because stock rread1 does
    // not consume it in the public lcpres=1 constant-pressure branch.  The
    // live density_cm3 member is the source-resolved initial xpx and is then
    // recomputed from pressure/current T4 at each fixed-state evaluation.
    double input_density_cm3 = 1.0e4;
    double density_cm3 = 1.0e4;
    double pressure_dyn_cm2 = 0.03;
    double temperature_k = 4.0e6;
    double column_cm2 = 1.0e17;
    double log_xi = 5.0;
    double initial_radius_cm = 1.0e11;
    double covering_fraction = 0.0;
    double emission_multiplier = 0.5;
    double maximum_optical_depth = 5.0;
    double turbulent_velocity_km_s = 1.0;
    double initial_electron_fraction = 1.0;
    double minimum_electron_fraction = 0.1;
    double luminosity_1e38 = 1.0e-6;
    double spectral_index = -1.0;
    double radial_density_exponent = 0.0;
    int pressure_mode = 0;
    int spectrum_units = 0;
    std::string spectrum_file = "spct.dat";
    double critical_fraction = 1.0e-7;
    double controller_charge_tolerance = 0.0;
    double controller_thermal_tolerance = 0.0;
    int ncn2 = 9999;
    int nsteps = 3;
    int npass = 1;
    int niter = 0;
    int requested_niter = 0;
    int lwrite = 0;
    int lprint = 0;
    int lstep = 0;
    int loopcontrol = 0;
    std::string model_name = "XSTAR Default";
    std::string abundance_table = "xdef";
    std::string mode = "ql";
    std::string spectrum = "pow";
};

// ProgramStorage carries the lowered form of heterogeneous ATDB records.  The
// source database deliberately permits different real/integer/character payload
// layouts per data type; lowering must therefore be driven by the record's data
// type before rate-type consumers attach physical ownership.
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
    std::vector<xstar_run_state::LevelIdentityState> detail_level_identities;
    std::vector<xstar_run_state::LineIdentityState> line_identities;
    std::vector<xstar_run_state::RrcIdentityState> rrc_identities;
    // 0.6.48.12.3.43.1.1.1: publication-only, literal npcon continuum ownership
    // inventory.  It is enumerated from setptrs-style npcon(jkkl) continuum
    // ownership and then restricted to source rate type 7.  Unlike
    // rrc_identities this is not restricted to executable kActiveTypes and is
    // never supplied to a rate/matrix kernel.
    std::vector<xstar_run_state::RrcIdentityState> source_rrc_identities;
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
// Literal public-lcpres/source-lcdd mapping and calc_hmc_all density rule.
// These are internal C++ orchestration helpers, not public ABI surfaces.
int source_lcdd_from_lcpres(int lcpres);
double source_runtime_density_cm3(
    const ProductionParameters& parameters,
    double temperature_t4,
    double electron_fraction_xee);
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Resolve and validate the atomic-data location used by native ATDB readers without silently changing or downloading the scientific database.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
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
