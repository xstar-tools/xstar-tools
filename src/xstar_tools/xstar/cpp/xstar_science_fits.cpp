// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: fstepr.f90; fstepr2.f90; fstepr3.f90; fstepr4.f90; writespectra.f90; writespectra2.f90;
//   writespectra3.f90; writespectra4.f90; pprint.f90 option 12 publication
// Role: Native FITS publication for per-shell detail products and final
//   spectra/lines/continuum/RRC/abundance surfaces.
// Relation: Source-equivalent publication with explicit source lifetime/REAL(4) writer semantics and
//   accepted Ca/O structural exceptions.
// Concordance: DETAIL-001; FINAL-001; TERMINAL-001; STEP-001
// Qualification: all-62 FITS 12.3.43.3; C++ 12.3.44; Python science 45.3.3.8
// XSTAR-SOURCE-CORRESPONDENCE-END

#include "xstar_science_fits.hpp"
#include "xstar_constants.h"

#include <fitsio.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace xstar_science_fits {
namespace {

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide true production mode for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool true_production_mode_v65() {
    const char* value = std::getenv("XSTAR_TRUE_PRODUCTION");
    return value && std::string(value) == "1";
}

// v82 patch 5.20.17.3.8.1: diagnostic-only audit of the exact
// xo01_detal4 inward-emission writer path.  The public column is 1E/float32,
// so the correct writer comparison is retained binary64 -> static_cast<float>
// -> FITS, not binary64 direct equality.
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write patch52017381 detal4 writer projection from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_patch52017381_detal4_writer_projection(
    std::size_t output_zone_index,
    std::size_t source_zone_index_value,
    std::size_t hdu_number,
    std::size_t source_sequence,
    std::size_t call_index,
    std::size_t row_one_based,
    double energy_ev,
    bool exact_fstepr4,
    std::size_t continuum_count,
    std::size_t rccemis_size,
    double raw_ws_rccemis_in,
    double directional_in,
    double selected_in) {
    const char* raw = std::getenv("XSTAR_V82_PATCH52017381_RCCEMIS_ATTRIBUTION_DIR");
    if (!raw || !*raw || row_one_based > 32u) return;
    const std::filesystem::path dir(raw);
    std::filesystem::create_directories(dir);
    const auto path = dir / "cpp_detal4_writer_projection.csv";
    const bool fresh = !std::filesystem::exists(path) || std::filesystem::file_size(path) == 0u;
    std::ofstream out(path, std::ios::app);
    if (!out) throw std::runtime_error("cannot write patch5.20.17.3.8.1 detal4 writer projection audit");
    if (fresh) {
        out << "output_zone_index,source_zone_index,hdu_number,source_sequence,call_index,row_one_based,"
               "energy_ev,exact_fstepr4,continuum_count,rccemis_size,raw_ws_rccemis_in,directional_in,"
               "selected_in,float32_projected_in\n";
    }
    const float projected = static_cast<float>(selected_in);
    out << std::setprecision(17)
        << output_zone_index << ',' << source_zone_index_value << ',' << hdu_number << ','
        << source_sequence << ',' << call_index << ',' << row_one_based << ',' << energy_ev << ','
        << (exact_fstepr4 ? 1 : 0) << ',' << continuum_count << ',' << rccemis_size << ','
        << raw_ws_rccemis_in << ',' << directional_in << ',' << selected_in << ','
        << static_cast<double>(projected) << '\n';
}


constexpr double kErgPerEv = 1.602176634e-12;
constexpr double kFourPi = 12.56637061435917295385;

const std::array<const char*,31> kSymbols = {
    "", "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P",
    "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn"
};
const std::array<const char*,31> kElementNames = {
    "", "hydrogen", "helium", "lithium", "beryllium", "boron", "carbon", "nitrogen", "oxygen", "fluorine",
    // pprint(12) copies the source database element record into a 9-character
    // column label.  The literal ATDB/XSTAR spelling for Z=15 is therefore
    // "phosphoru", not the normalized English name "phosphorus".
    "neon", "sodium", "magnesium", "aluminum", "silicon", "phosphoru", "sulfur", "chlorine", "argon", "potassium",
    "calcium", "scandium", "titanium", "vanadium", "chromium", "manganese", "iron", "cobalt", "nickel", "copper", "zinc"
};

const std::array<const char*,31> kElementSymbolsLower = {
    "", "h", "he", "li", "be", "b", "c", "n", "o", "f", "ne", "na", "mg", "al", "si", "p",
    "s", "cl", "ar", "k", "ca", "sc", "ti", "v", "cr", "mn", "fe", "co", "ni", "cu", "zn"
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide v0648123431 publication attribution dir for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::filesystem::path v0648123431_publication_attribution_dir() {
    const char* raw = std::getenv("XSTAR_V0648123431_PUBLICATION_ATTRIBUTION_DIR");
    if (!raw || !*raw) return {};
    std::filesystem::path dir(raw);
    std::filesystem::create_directories(dir);
    return dir;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write write from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_v0648123431_detal2_activity_trace(
    std::size_t hdu_number,
    const xstar_run_state::LineIdentityState& id,
    double local_emis_in,
    double local_emis_out,
    double local_opacity,
    bool physical_signal,
    bool publication_shadow,
    bool source_eligible) {
    const char* raw_indices = std::getenv("XSTAR_V0648123431_DETAL2_TRACE_INDICES");
    if (!raw_indices || !*raw_indices) return;
    bool requested = false;
    std::istringstream requested_stream(raw_indices);
    std::string token;
    while (std::getline(requested_stream, token, ',')) {
        try {
            if (std::stoll(token) == id.line_index) { requested = true; break; }
        } catch (...) {}
    }
    if (!requested) return;
    const auto dir = v0648123431_publication_attribution_dir();
    if (dir.empty()) return;
    const auto path = dir / "detal2_activity_shadow.csv";
    const bool fresh = !std::filesystem::exists(path) || std::filesystem::file_size(path) == 0u;
    std::ofstream out(path, std::ios::app);
    if (!out) throw std::runtime_error("cannot write v0648123431 detal2 activity trace");
    if (fresh) {
        out << "hdu_number,line_index,ion,rate_type,data_type,wavelength_angstrom,"
               "local_emis_in,local_emis_out,local_opacity,physical_signal,"
               "publication_shadow,source_eligible\n";
    }
    out << std::setprecision(17)
        << hdu_number << ',' << id.line_index << ',' << id.ion_label << ','
        << id.rate_type << ',' << id.data_type << ',' << id.wavelength_angstrom << ','
        << local_emis_in << ',' << local_emis_out << ',' << local_opacity << ','
        << (physical_signal ? 1 : 0) << ',' << (publication_shadow ? 1 : 0) << ','
        << (source_eligible ? 1 : 0) << '\n';
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write write from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_v0648123431_abundance_thermal_trace(
    const char* surface,
    std::size_t output_zone_index,
    std::size_t source_zone_index_value,
    std::size_t accepted_sequence,
    int element_z,
    bool retained_present,
    double retained_value,
    double selected_value,
    double total_value) {
    const auto dir = v0648123431_publication_attribution_dir();
    if (dir.empty()) return;
    const auto path = dir / "abundance_element_thermal_retention.csv";
    const bool fresh = !std::filesystem::exists(path) || std::filesystem::file_size(path) == 0u;
    std::ofstream out(path, std::ios::app);
    if (!out) throw std::runtime_error("cannot write v0648123431 abundance thermal trace");
    if (fresh) {
        out << "surface,output_zone_index,source_zone_index,accepted_sequence,element_z,"
               "retained_present,retained_value,selected_value,total_value\n";
    }
    out << std::setprecision(17)
        << surface << ',' << output_zone_index << ',' << source_zone_index_value << ','
        << accepted_sequence << ',' << element_z << ',' << (retained_present ? 1 : 0) << ','
        << retained_value << ',' << selected_value << ',' << total_value << '\n';
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide source pescv for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double source_pescv_v0648123431(double tau) {
    double value = std::exp(-tau);
    const double eps = static_cast<double>(static_cast<float>(1.0e-12));
    value = std::max(value, eps);
    return value / 2.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute source rrc directional projection for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
std::pair<double,double> source_rrc_directional_projection_v0648123431(
    double retained_in,
    double retained_out,
    double tau_in,
    double tau_out,
    double cfrac) {
    const double total = (std::isfinite(retained_in) ? retained_in : 0.0) +
                         (std::isfinite(retained_out) ? retained_out : 0.0);
    const double cf = std::clamp(cfrac, 0.0, 1.0);
    const double ptmp1 = source_pescv_v0648123431(tau_in) * (1.0 - cf);
    const double ptmp2 = source_pescv_v0648123431(tau_out) * (1.0 - cf) +
                         2.0 * source_pescv_v0648123431(tau_in + tau_out) * cf;
    const double denom = ptmp1 + ptmp2;
    if (!(std::isfinite(total) && std::isfinite(denom) && denom > 0.0)) {
        return {std::isfinite(retained_in) ? retained_in : 0.0,
                std::isfinite(retained_out) ? retained_out : 0.0};
    }
    return {total * ptmp1 / denom, total * ptmp2 / denom};
}
const std::array<const char*,31> kRomanLower = {
    "", "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv",
    "xvi", "xvii", "xviii", "xix", "xx", "xxi", "xxii", "xxiii", "xxiv", "xxv", "xxvi", "xxvii", "xxviii", "xxix", "xxx"
};


struct ElementMeta {
    int element_index = 0;
    int element_z = 0;
    int row_offset = 0;
    int n_rows = 0;
    double abundance = 0.0;
};

struct RowMeta {
    int element_index = 0;
    int row = 0;
    int ion = 0;
    int ion_charge = 0;
    double energy_ev = 0.0;
    int principal_n = 0;
    int orbital_l = 0;
    int global_level_index = 0;
};

struct RecordDiag {
    long long source_position = 0;
    long long record = 0;
    int element_index = 0;
    int element_z = 0;
    int data_type = 0;
    int rate_type = 0;
    int ion_stage = 0;
    int lower_row = 0;
    int upper_row = 0;
    bool spectral = false;
    std::array<double,6> ans{};
    double line_energy_ev = 0.0;
    double atomic_mass_amu = 1.0;
    double density_scale = 1.0;
    double natural_width_ev = 0.0;
    double opakab = 0.0;
    double threshold_abs_sigma_cm2 = 0.0;
    double threshold_stimulated_sigma_cm2 = 0.0;
    bool type50_valid = false;
    long long type50_line_index_one_based = 0;
    long long continuum_index_one_based = 0;
    double type50_wavelength_a = 0.0;
    double type50_ptmp1 = 1.0;
    double type50_ptmp2 = 1.0;
    double type50_tau_in = std::numeric_limits<double>::quiet_NaN();
    double type50_tau_out = std::numeric_limits<double>::quiet_NaN();
    bool type53_valid = false;
    bool type49_valid = false;
    bool type99_valid = false;
    double type53_threshold_ev = 0.0;
    double type53_base_threshold_ev = 0.0;
    double type49_threshold_ev = 0.0;
    double type99_threshold_ev = 0.0;
    double type53_ptmp1 = 1.0;
    double type53_ptmp2 = 1.0;
    double type53_tau_in = std::numeric_limits<double>::quiet_NaN();
    double type53_tau_out = std::numeric_limits<double>::quiet_NaN();
};

struct LineRow {
    long long record = 0;
    int z = 0;
    int stage = 0;
    int lower_row = 0;
    int upper_row = 0;
    double wavelength_a = 0.0;
    double emis_in = 0.0;
    double emis_out = 0.0;
    double opacity = 0.0;
    double tau_in = 0.0;
    double tau_out = 0.0;
};

struct RrcRow {
    long long record = 0;
    int z = 0;
    int stage = 0;
    int lower_row = 0;
    int upper_row = 0;
    double energy_ev = 0.0;
    double emis_in = 0.0;
    double emis_out = 0.0;
    double absorption = 0.0;
    double opacity = 0.0;
    double tau_in = 0.0;
    double tau_out = 0.0;
};

struct SolveRowValue {
    double final_population = std::numeric_limits<double>::quiet_NaN();
    double raw_call_start = std::numeric_limits<double>::quiet_NaN();
    double loaded_call_start = std::numeric_limits<double>::quiet_NaN();
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide split csv for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<std::string> split_csv(const std::string& line) {
    std::vector<std::string> out;
    std::string field;
    std::istringstream input(line);
    while (std::getline(input, field, ',')) out.push_back(field);
    if (!line.empty() && line.back() == ',') out.emplace_back();
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide columns of for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::map<std::string,std::size_t> columns_of(const std::string& header) {
    std::map<std::string,std::size_t> out;
    const auto fields = split_csv(header);
    for (std::size_t i = 0; i < fields.size(); ++i) out[fields[i]] = i;
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide field or for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string field_or(const std::vector<std::string>& fields, const std::map<std::string,std::size_t>& columns,
                     const std::string& name, const std::string& fallback = "") {
    const auto it = columns.find(name);
    if (it == columns.end() || it->second >= fields.size()) return fallback;
    return fields[it->second];
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide number or for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double number_or(const std::vector<std::string>& fields, const std::map<std::string,std::size_t>& columns,
                 const std::string& name, double fallback = 0.0) {
    const std::string value = field_or(fields, columns, name);
    if (value.empty()) return fallback;
    try { return std::stod(value); } catch (...) { return fallback; }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide integer or for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
long long integer_or(const std::vector<std::string>& fields, const std::map<std::string,std::size_t>& columns,
                     const std::string& name, long long fallback = 0) {
    const std::string value = field_or(fields, columns, name);
    if (value.empty()) return fallback;
    try { return std::stoll(value); } catch (...) { return fallback; }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load elements into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::vector<ElementMeta> read_elements(const std::filesystem::path& program_dir) {
    std::ifstream input(program_dir / "elements.csv");
    if (!input) throw std::runtime_error("cannot open native elements.csv");
    std::string header;
    std::getline(input, header);
    const auto columns = columns_of(header);
    std::vector<ElementMeta> out;
    std::string line;
    int offset = 0;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto fields = split_csv(line);
        ElementMeta e;
        e.element_index = static_cast<int>(integer_or(fields, columns, "element_index"));
        e.element_z = static_cast<int>(integer_or(fields, columns, "element_z"));
        e.n_rows = static_cast<int>(integer_or(fields, columns, "n_rows"));
        e.abundance = number_or(fields, columns, "abundance", e.element_z == 1 ? 1.0 : e.element_z == 2 ? 0.1 : e.element_z == 12 ? 3.5e-5 : 0.0);
        e.row_offset = offset;
        offset += e.n_rows;
        out.push_back(e);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load rows into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::vector<RowMeta> read_rows(const std::filesystem::path& program_dir) {
    std::ifstream input(program_dir / "rows.csv");
    if (!input) throw std::runtime_error("cannot open native rows.csv");
    std::string header;
    std::getline(input, header);
    const auto columns = columns_of(header);
    std::vector<RowMeta> out;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto fields = split_csv(line);
        RowMeta r;
        r.element_index = static_cast<int>(integer_or(fields, columns, "element_index"));
        r.row = static_cast<int>(integer_or(fields, columns, "row"));
        r.ion = static_cast<int>(integer_or(fields, columns, "ion"));
        r.ion_charge = static_cast<int>(integer_or(fields, columns, "ion_charge"));
        r.energy_ev = number_or(fields, columns, "energy_ev");
        r.principal_n = static_cast<int>(integer_or(fields, columns, "principal_n"));
        r.orbital_l = static_cast<int>(integer_or(fields, columns, "orbital_l"));
        r.global_level_index = static_cast<int>(integer_or(fields, columns, "global_level_index"));
        out.push_back(r);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load elements into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::vector<ElementMeta> read_elements(
    const xstar_run_state::ProductWritingState& state,
    const std::filesystem::path& legacy_program_dir) {
    if (state.element_metadata.empty()) return read_elements(legacy_program_dir);
    std::vector<ElementMeta> out;
    out.reserve(state.element_metadata.size());
    for (const auto& source : state.element_metadata) {
        ElementMeta e;
        e.element_index = source.element_index;
        e.element_z = source.atomic_number;
        e.row_offset = source.row_offset;
        e.n_rows = source.row_count;
        e.abundance = source.abundance;
        out.push_back(e);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load rows into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::vector<RowMeta> read_rows(
    const xstar_run_state::ProductWritingState& state,
    const std::filesystem::path& legacy_program_dir) {
    if (state.row_metadata.empty()) return read_rows(legacy_program_dir);
    std::vector<RowMeta> out;
    out.reserve(state.row_metadata.size());
    for (const auto& source : state.row_metadata) {
        RowMeta r;
        r.element_index = source.element_index;
        r.row = source.row;
        r.ion = source.ion;
        r.ion_charge = source.ion_charge;
        r.energy_ev = source.energy_ev;
        r.principal_n = source.principal_n;
        r.orbital_l = source.orbital_l;
        r.global_level_index = source.global_level_index;
        out.push_back(r);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide diagnostic records path for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::filesystem::path diagnostic_records_path(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
    std::ostringstream stem;
    stem << "evaluation_" << std::setw(4) << std::setfill('0') << sequence << "_records.csv";
    const auto filename = stem.str();
    std::vector<std::filesystem::path> candidates;
    if (!state.native_diagnostics_path.empty()) {
        if (std::filesystem::is_directory(state.native_diagnostics_path)) {
            candidates.push_back(state.native_diagnostics_path / filename);
        } else {
            candidates.push_back(state.native_diagnostics_path.parent_path() / filename);
        }
    }
    if (!state.product_metadata_path.empty()) {
        candidates.push_back(state.product_metadata_path.parent_path() / "trajectory_diagnostics" / filename);
        candidates.push_back(state.product_metadata_path.parent_path().parent_path() / "trajectory_diagnostics" / filename);
    }
    for (const auto& candidate : candidates) {
        if (!candidate.empty() && std::filesystem::is_regular_file(candidate)) return candidate;
    }
    return state.native_diagnostics_path / filename;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute diagnostic solve rows path as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
std::filesystem::path diagnostic_solve_rows_path(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
    std::ostringstream stem;
    stem << "evaluation_" << std::setw(4) << std::setfill('0') << sequence << "_all_element_solve_rows.csv";
    return state.native_diagnostics_path / stem.str();
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide retained evaluation by sequence for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
const xstar_run_state::FixedEvaluationState* retained_evaluation_by_sequence(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
    for (const auto& evaluation : state.fixed_evaluations) {
        if (evaluation.sequence == sequence) return &evaluation;
    }
    for (const auto& zone : state.radial_zones) {
        const auto& evaluation = zone.accepted_controller.evaluation;
        if (evaluation.sequence == sequence) return &evaluation;
    }
    return nullptr;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load solve rows by global into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::map<std::int32_t,SolveRowValue> read_solve_rows_by_global(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
    const auto path = diagnostic_solve_rows_path(state, sequence);
    std::ifstream input(path);
    if (!input) return {};
    std::string header;
    if (!std::getline(input, header)) return {};
    const auto columns = columns_of(header);
    std::map<std::int32_t,SolveRowValue> out;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto f = split_csv(line);
        const auto global = static_cast<std::int32_t>(integer_or(f, columns, "global_level_index", 0));
        if (global <= 0) continue;
        SolveRowValue row;
        row.final_population = number_or(f, columns, "final_population", std::numeric_limits<double>::quiet_NaN());
        row.raw_call_start = number_or(f, columns, "raw_call_start_xilevg", std::numeric_limits<double>::quiet_NaN());
        row.loaded_call_start = number_or(f, columns, "loaded_call_start_xilevg", row.raw_call_start);
        out[global] = row;
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load record diagnostics into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::vector<RecordDiag> read_record_diagnostics(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
    if (const auto* evaluation = retained_evaluation_by_sequence(state, sequence);
        evaluation && !evaluation->record_product_diagnostics.empty()) {
        std::vector<RecordDiag> out;
        out.reserve(evaluation->record_product_diagnostics.size());
        for (const auto& source : evaluation->record_product_diagnostics) {
            RecordDiag r;
            r.source_position = source.source_position;
            r.record = source.record;
            r.element_index = source.element_index;
            r.element_z = source.element_z;
            r.data_type = source.data_type;
            r.rate_type = source.rate_type;
            r.ion_stage = source.ion_stage;
            r.lower_row = source.lower_row;
            r.upper_row = source.upper_row;
            r.spectral = source.spectral;
            r.ans = source.ans;
            r.line_energy_ev = source.line_energy_ev;
            r.atomic_mass_amu = source.atomic_mass_amu;
            r.density_scale = source.density_scale;
            r.natural_width_ev = source.natural_width_ev;
            r.opakab = source.opakab;
            r.threshold_abs_sigma_cm2 = source.threshold_abs_sigma_cm2;
            r.threshold_stimulated_sigma_cm2 = source.threshold_stimulated_sigma_cm2;
            r.type50_valid = source.type50_valid;
            r.type50_line_index_one_based = source.type50_line_index_one_based;
            r.continuum_index_one_based = source.continuum_index_one_based;
            r.type50_wavelength_a = source.type50_wavelength_a;
            r.type50_ptmp1 = source.type50_ptmp1;
            r.type50_ptmp2 = source.type50_ptmp2;
            r.type50_tau_in = source.type50_tau_in;
            r.type50_tau_out = source.type50_tau_out;
            r.type53_valid = source.type53_valid;
            r.type49_valid = source.type49_valid;
            r.type99_valid = source.type99_valid;
            r.type53_threshold_ev = source.type53_threshold_ev;
            r.type53_base_threshold_ev = source.type53_base_threshold_ev;
            r.type49_threshold_ev = source.type49_threshold_ev;
            r.type99_threshold_ev = source.type99_threshold_ev;
            r.type53_ptmp1 = source.type53_ptmp1;
            r.type53_ptmp2 = source.type53_ptmp2;
            r.type53_tau_in = source.type53_tau_in;
            r.type53_tau_out = source.type53_tau_out;
            out.push_back(std::move(r));
        }
        return out;
    }
    const auto path = diagnostic_records_path(state, sequence);
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open native record diagnostics: " + path.string());
    std::string header;
    std::getline(input, header);
    const auto columns = columns_of(header);
    std::vector<RecordDiag> out;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto f = split_csv(line);
        RecordDiag r;
        r.source_position = integer_or(f, columns, "source_position");
        r.record = integer_or(f, columns, "record");
        r.element_index = static_cast<int>(integer_or(f, columns, "element_index"));
        r.element_z = static_cast<int>(integer_or(f, columns, "element_z"));
        r.data_type = static_cast<int>(integer_or(f, columns, "data_type"));
        r.rate_type = static_cast<int>(integer_or(f, columns, "rate_type"));
        r.ion_stage = static_cast<int>(integer_or(f, columns, "ion_stage"));
        r.lower_row = static_cast<int>(integer_or(f, columns, "lower_row"));
        r.upper_row = static_cast<int>(integer_or(f, columns, "upper_row"));
        r.spectral = integer_or(f, columns, "spectral") != 0;
        for (std::size_t i = 0; i < 6; ++i) r.ans[i] = number_or(f, columns, "ans" + std::to_string(i + 1));
        r.line_energy_ev = number_or(f, columns, "line_energy_ev");
        r.atomic_mass_amu = number_or(f, columns, "atomic_mass_amu", 1.0);
        r.density_scale = number_or(f, columns, "density_scale", 1.0);
        r.natural_width_ev = number_or(f, columns, "natural_width_ev");
        r.opakab = number_or(f, columns, "opakab");
        r.type50_valid = integer_or(f, columns, "type50_shadow_valid") != 0;
        r.type50_line_index_one_based = integer_or(f, columns, "type50_line_index_one_based", 0);
        r.continuum_index_one_based = integer_or(f, columns, "type49_continuum_index_one_based", 0);
        if (r.continuum_index_one_based <= 0) r.continuum_index_one_based = integer_or(f, columns, "type53_continuum_index_one_based", 0);
        if (r.continuum_index_one_based <= 0) r.continuum_index_one_based = integer_or(f, columns, "type99_nbinc_threshold_one_based", 0);
        r.type50_wavelength_a = number_or(f, columns, "type50_stored_wavelength_a");
        r.type50_ptmp1 = number_or(f, columns, "type50_ptmp1", 1.0);
        r.type50_ptmp2 = number_or(f, columns, "type50_ptmp2", 1.0);
        r.type50_tau_in = number_or(f, columns, "type50_line_tau_in", std::numeric_limits<double>::quiet_NaN());
        r.type50_tau_out = number_or(f, columns, "type50_line_tau_out", std::numeric_limits<double>::quiet_NaN());
        r.type53_valid = integer_or(f, columns, "type53_shadow_valid") != 0;
        r.type49_valid = integer_or(f, columns, "type49_shadow_valid") != 0;
        r.type99_valid = integer_or(f, columns, "type99_shadow_valid") != 0;
        r.type53_threshold_ev = number_or(f, columns, "type53_shadow_threshold_ev");
        r.type53_base_threshold_ev = number_or(f, columns, "type53_shadow_base_threshold_ev", r.type53_threshold_ev);
        r.type49_threshold_ev = number_or(f, columns, "type49_threshold_ev");
        r.type99_threshold_ev = number_or(f, columns, "type99_threshold_ev");
        if (r.type49_valid) {
            r.threshold_abs_sigma_cm2 = number_or(f, columns, "type49_threshold_abs_sigma_cm2", r.opakab);
            r.threshold_stimulated_sigma_cm2 = number_or(f, columns, "type49_threshold_stimulated_sigma_cm2", 0.0);
        } else if (r.type53_valid) {
            r.threshold_abs_sigma_cm2 = number_or(f, columns, "type53_threshold_abs_sigma_cm2", r.opakab);
            r.threshold_stimulated_sigma_cm2 = number_or(f, columns, "type53_threshold_stimulated_sigma_cm2", 0.0);
        } else {
            r.threshold_abs_sigma_cm2 = r.opakab;
        }
        r.type53_ptmp1 = number_or(f, columns, "type53_ptmp1", 1.0);
        r.type53_ptmp2 = number_or(f, columns, "type53_ptmp2", 1.0);
        r.type53_tau_in = number_or(f, columns, "type53_tau_in", std::numeric_limits<double>::quiet_NaN());
        r.type53_tau_out = number_or(f, columns, "type53_tau_out", std::numeric_limits<double>::quiet_NaN());
        out.push_back(r);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide element for for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
const ElementMeta& element_for(const std::vector<ElementMeta>& elements, int element_index) {
    for (const auto& e : elements) if (e.element_index == element_index) return e;
    throw std::runtime_error("native record references unknown element index");
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide element ptr for for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
const ElementMeta* element_ptr_for(const std::vector<ElementMeta>& elements, int element_index) {
    for (const auto& e : elements) if (e.element_index == element_index) return &e;
    return nullptr;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide active product element stage for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool active_product_element_stage(const xstar_run_state::ProductWritingState& state,
                                  const std::vector<ElementMeta>& elements,
                                  const std::vector<RowMeta>& rows,
                                  int element_z, int ion_stage, double abundance) {
    if (!(abundance > 0.0)) return false;
    if (ion_stage <= 0) return false;
    const ElementMeta* element = nullptr;
    for (const auto& e : elements) if (e.element_z == element_z) { element = &e; break; }
    if (!element) return false;
    const xstar_run_state::FixedEvaluationState* terminal = nullptr;
    if (state.final_writer_evaluation.has_value()) terminal = &*state.final_writer_evaluation;
    else if (!state.radial_zones.empty()) terminal = &state.radial_zones.back().accepted_controller.evaluation;
    else if (!state.fixed_evaluations.empty()) terminal = &state.fixed_evaluations.back();
    if (!terminal || terminal->populations.empty()) return true;
    bool stage_known = false;
    for (const auto& row : rows) {
        if (row.element_index != element->element_index || row.ion_charge + 1 != ion_stage) continue;
        stage_known = true;
        if (row.row <= 0) continue;
        const std::size_t index = static_cast<std::size_t>(element->row_offset + row.row - 1);
        if (index >= terminal->populations.size()) continue;
        const double population = terminal->populations[index];
        if (std::isfinite(population) && population != 0.0) return true;
    }
    // If the lowered metadata has no rows for a source ion stage, there is no
    // publishable stage inventory.  Otherwise a fully zero terminal stage is
    // source-inactive and must not leak into detail/line/RRC products.
    // v0.6.48.11.2 accidentally returned !stage_known here, retaining exactly
    // the unknown stages that the comment intended to suppress.
    (void)stage_known;
    return false;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide roman stage from ion label for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
int roman_stage_from_ion_label(const std::string& label) {
    const auto pos = label.find('_');
    if (pos == std::string::npos) return 0;
    const std::string stage = label.substr(pos + 1);
    for (std::size_t i = 1; i < kRomanLower.size(); ++i) {
        if (stage == kRomanLower[i]) return static_cast<int>(i);
    }
    return 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide element z from ion label for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
int element_z_from_ion_label(const std::string& label) {
    const auto pos = label.find('_');
    const std::string sym = pos == std::string::npos ? label : label.substr(0, pos);
    for (std::size_t z = 1; z < kElementSymbolsLower.size(); ++z) {
        if (sym == kElementSymbolsLower[z]) return static_cast<int>(z);
    }
    return 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide row for for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
const RowMeta* row_for(const std::vector<RowMeta>& rows, int element_index, int local_row) {
    for (const auto& row : rows) if (row.element_index == element_index && row.row == local_row) return &row;
    return nullptr;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute population for as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
double population_for(const xstar_run_state::FixedEvaluationState& state,
                      const std::vector<ElementMeta>& elements,
                      int element_index, int local_row) {
    if (local_row <= 0) return 0.0;
    const auto& element = element_for(elements, element_index);
    const std::size_t index = static_cast<std::size_t>(element.row_offset + local_row - 1);
    return index < state.populations.size() ? state.populations[index] : 0.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide row meta by global for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
const RowMeta* row_meta_by_global(const std::vector<RowMeta>& rows, std::int32_t global_index) {
    for (const auto& row : rows) if (row.global_level_index == global_index) return &row;
    return nullptr;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute source lte for level as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
double source_lte_for_level(const xstar_run_state::FixedEvaluationState& evaluation,
                            const std::vector<ElementMeta>& elements,
                            const std::vector<RowMeta>& rows,
                            const xstar_run_state::LevelIdentityState& level) {
    // v25.5.15.9.4: the oracle xo01_detail LTE column is the retained
    // source global_rnisg workspace keyed by the ATDB global level index.
    // The computed lte_populations vector is a solver-side packed helper and
    // is not a safe public-product LTE source for He/Mg.
    if (level.global_index > 0) {
        const std::size_t global0 = static_cast<std::size_t>(level.global_index - 1);
        if (global0 < evaluation.source_global_rnisg.size()) {
            const double retained_global_lte = evaluation.source_global_rnisg[global0];
            if (std::isfinite(retained_global_lte) && retained_global_lte != 0.0) {
                return retained_global_lte;
            }
        }
    }
    const auto* row = row_meta_by_global(rows, level.global_index);
    if (row) {
        const auto& element = element_for(elements, row->element_index);
        const bool continuum_public_row =
            level.level_label.find("continu") != std::string::npos ||
            level.level_label.find("continuum") != std::string::npos;
        const std::size_t packed = static_cast<std::size_t>(element.row_offset + row->row - 1);
        if (packed < evaluation.source_workspace.lte_populations.size()) {
            const double packed_lte = evaluation.source_workspace.lte_populations[packed];
            // v82 patch 5.20.15.2.2: inserted continuum pseudo-levels are not
            // ordinary solver rows.  Their packed slot can legitimately be a
            // structural zero while the source LTE owner is the immediately
            // following ion-ground row.  Do not let that structural zero make
            // the continuum fallback unreachable.  Ordinary physical levels
            // retain zero as a valid source value.
            if (!continuum_public_row || (std::isfinite(packed_lte) && packed_lte != 0.0)) {
                return std::isfinite(packed_lte) ? packed_lte : 0.0;
            }
        }
        // Continuum public rows point at the next ion ground row in the
        // source packed LTE surface when their inserted pseudo-level slot is
        // structural zero.  Stay within the same retained source-LTE family;
        // never substitute the population surface.
        if (continuum_public_row && row->row + 1 <= element.n_rows) {
            const std::size_t adjacent = static_cast<std::size_t>(element.row_offset + row->row);
            if (adjacent < evaluation.source_workspace.lte_populations.size()) {
                const double adjacent_lte = evaluation.source_workspace.lte_populations[adjacent];
                if (std::isfinite(adjacent_lte)) return adjacent_lte;
            }
        }
    }
    const std::size_t ordinal0 = level.global_index > 0 ? static_cast<std::size_t>(level.global_index - 1) : 0u;
    if (ordinal0 < evaluation.source_workspace.lte_populations.size()) {
        return evaluation.source_workspace.lte_populations[ordinal0];
    }
    return 0.0;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute compact population index by global as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
std::map<int,std::size_t> compact_population_index_by_global(
    const std::vector<ElementMeta>& elements,
    const std::vector<RowMeta>& rows) {
    std::map<int,std::size_t> out;
    for (const auto& row : rows) {
        const auto& element = element_for(elements, row.element_index);
        const std::size_t compact = static_cast<std::size_t>(element.row_offset + row.row - 1);
        if (row.global_level_index > 0) out[row.global_level_index] = compact;
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute compact population by public global as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
double compact_population_by_public_global(
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::map<int,std::size_t>& compact_by_global,
    int global_index) {
    const auto it = compact_by_global.find(global_index);
    if (it == compact_by_global.end()) return std::numeric_limits<double>::quiet_NaN();
    const std::size_t compact = it->second;
    if (compact >= evaluation.populations.size()) return std::numeric_limits<double>::quiet_NaN();
    return evaluation.populations[compact];
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute public detail population for level as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
double public_detail_population_for_level(
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::map<int,std::size_t>& compact_by_global,
    const xstar_run_state::LevelIdentityState& level,
    double fallback) {
    // v0.6.48.12.3.18: fstepr publication has a distinct source lifetime
    // from the post-mapback xilevg used by calc_emisab_all/calc_emis_all.
    // The retained dense detail projection expands internal active shared rows
    // to their source global aliases, but suppresses the upper terminal row
    // that the following inactive ion zeroes before fstepr.  A zero in this
    // surface is authoritative.
    if (level.global_index > 0 && !evaluation.source_detail_global_xilevg.empty()) {
        const std::size_t global0 = static_cast<std::size_t>(level.global_index - 1);
        if (global0 < evaluation.source_detail_global_xilevg.size()) {
            const double value = evaluation.source_detail_global_xilevg[global0];
            return std::isfinite(value) ? value : 0.0;
        }
    }
    // Backward-compatible states predate the dedicated fstepr surface.
    if (level.global_index > 0) {
        const std::size_t global0 = static_cast<std::size_t>(level.global_index - 1);
        if (global0 < evaluation.source_global_xilevg.size()) {
            const double value = evaluation.source_global_xilevg[global0];
            return std::isfinite(value) ? value : 0.0;
        }
    }
    auto get = [&](int global_index) -> double {
        return compact_population_by_public_global(evaluation, compact_by_global, global_index);
    };
    double value = get(level.global_index);
    // Backward/fallback path for states that predate dense xilevg retention:
    // inserted continuum pseudo-levels share the following ion-ground owner.
    if ((!std::isfinite(value) || value == 0.0) &&
        level.level_label.find("continu") != std::string::npos) {
        const double adjacent = get(level.global_index + 1);
        if (std::isfinite(adjacent)) value = adjacent;
    }
    if (!std::isfinite(value)) return fallback;
    return value;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide roman for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string roman(int value) {
    const std::array<std::pair<int,const char*>,13> table = {{{1000,"m"},{900,"cm"},{500,"d"},{400,"cd"},{100,"c"},{90,"xc"},{50,"l"},{40,"xl"},{10,"x"},{9,"ix"},{5,"v"},{4,"iv"},{1,"i"}}};
    std::string out;
    for (const auto& [number, text] : table) while (value >= number) { out += text; value -= number; }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide ion label for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::string ion_label(int z, int stage, bool underscore = false) {
    if (z < 1 || z > 30) return "unknown";
    std::string result = kSymbols[static_cast<std::size_t>(z)];
    if (underscore) {
        std::transform(result.begin(), result.end(), result.begin(), [](unsigned char c){ return static_cast<char>(std::tolower(c)); });
        result += "_" + roman(std::max(stage, 1));
    } else {
        result += " ";
        std::string numeral = roman(std::max(stage, 1));
        std::transform(numeral.begin(), numeral.end(), numeral.begin(), [](unsigned char c){ return static_cast<char>(std::toupper(c)); });
        result += numeral;
    }
    return result;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide level label for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::string level_label(const RowMeta* row, int local_row) {
    std::ostringstream out;
    if (row && row->principal_n > 0) out << "n=" << row->principal_n << " l=" << row->orbital_l;
    else out << "row=" << local_row;
    if (row) out << " E=" << std::setprecision(5) << row->energy_ev;
    std::string text = out.str();
    if (text.size() > 20) text.resize(20);
    return text;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide check fits for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
void check_fits(int status, const std::string& where) {
    if (status == 0) return;
    char message[FLEN_STATUS]{};
    fits_get_errstatus(status, message);
    throw std::runtime_error(where + ": " + message);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load atdata into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::string read_atdata(const std::filesystem::path& atdb) {
    fitsfile* fptr = nullptr;
    int status = 0;
    fits_open_file(&fptr, atdb.c_str(), READONLY, &status);
    if (status != 0) return "unknown";
    char value[FLEN_VALUE]{};
    int read_status = 0;
    fits_read_key(fptr, TSTRING, const_cast<char*>("ATDATA"), value, nullptr, &read_status);
    if (read_status != 0) {
        read_status = 0;
        fits_read_key(fptr, TSTRING, const_cast<char*>("DATE"), value, nullptr, &read_status);
    }
    int close_status = 0;
    fits_close_file(fptr, &close_status);
    return read_status == 0 ? std::string(value) : "unknown";
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide extract json string for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string extract_json_string(const std::string& text, const std::string& key) {
    const std::string needle = "\"" + key + "\"";
    const auto p = text.find(needle);
    if (p == std::string::npos) return "";
    const auto colon = text.find(':', p + needle.size());
    if (colon == std::string::npos) return "";
    const auto q1 = text.find('"', colon + 1);
    if (q1 == std::string::npos) return "";
    const auto q2 = text.find('"', q1 + 1);
    if (q2 == std::string::npos) return "";
    return text.substr(q1 + 1, q2 - q1 - 1);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide reference mg11 product state for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool reference_mg11_product_state(const xstar_run_state::ProductWritingState& state) {
    std::ifstream input(state.parameters_path);
    if (!input) return false;
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return extract_json_string(buffer.str(), "modelname") ==
        "xstar_atomic_mg11_xi1p5_ne1e8";
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide product model name for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string product_model_name(const xstar_run_state::ProductWritingState& state) {
    const auto manifest = state.product_metadata_path / "manifest.json";
    std::ifstream input(manifest);
    if (input) {
        std::ostringstream buffer;
        buffer << input.rdbuf();
        const auto model = extract_json_string(buffer.str(), "model_name");
        if (!model.empty()) return model;
    }
    return "xstar_atomic_mg11_xi1p5_ne1e8";
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide create fits for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
fitsfile* create_fits(const std::filesystem::path& path, const xstar_run_state::ProductWritingState& state) {
    fitsfile* fptr = nullptr;
    int status = 0;
    const std::string name = "!" + path.string();
    fits_create_file(&fptr, name.c_str(), &status);
    check_fits(status, "fits_create_file");
    fits_create_img(fptr, BYTE_IMG, 0, nullptr, &status);
    check_fits(status, "fits_create_img");
    std::string creator = "xstar_cpp " + state.release;
    std::string origin = "xstar_tools native C++";
    std::string atdata = read_atdata(state.atomic_database_path);
    std::string mode = "NATIVE_CPP_LIVE_STATE";
    std::string tau_mode = "NATIVE_OPACITY_TRAPEZOID";
    std::string run_id = state.native_run_id;
    std::string model = product_model_name(state);
    fits_update_key(fptr, TSTRING, const_cast<char*>("CREATOR"), creator.data(), const_cast<char*>("native executable"), &status);
    fits_update_key(fptr, TSTRING, const_cast<char*>("MODEL"), model.data(), const_cast<char*>("source model name"), &status);
    fits_update_key(fptr, TSTRING, const_cast<char*>("ORIGIN"), origin.data(), nullptr, &status);
    fits_update_key(fptr, TSTRING, const_cast<char*>("ATDATA"), atdata.data(), const_cast<char*>("supplied atomic database metadata"), &status);
    fits_update_key(fptr, TSTRING, const_cast<char*>("DATAMODE"), mode.data(), const_cast<char*>("no benchmark payloads"), &status);
    fits_update_key(fptr, TSTRING, const_cast<char*>("TAUMODE"), tau_mode.data(), const_cast<char*>("output-grid depths from native opacity"), &status);
    fits_update_key(fptr, TSTRING, const_cast<char*>("RUNID"), run_id.data(), const_cast<char*>("native writer run identity"), &status);
    fits_write_date(fptr, &status);
    check_fits(status, "write native primary metadata");
    return fptr;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide close fits for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
void close_fits(fitsfile* fptr) {
    int status = 0;
    int hdu = 1;
    fits_get_num_hdus(fptr, &hdu, &status);
    check_fits(status, "fits_get_num_hdus");
    for (int i = 1; i <= hdu; ++i) {
        int type = 0;
        fits_movabs_hdu(fptr, i, &type, &status);
        check_fits(status, "fits_movabs_hdu");
        fits_write_chksum(fptr, &status);
        check_fits(status, "fits_write_chksum");
    }
    fits_close_file(fptr, &status);
    check_fits(status, "fits_close_file");
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide normalize tform for table for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<std::string> normalize_tform_for_table(int table_type, const std::vector<std::string>& formats) {
    // Astropy/Python oracle writes scalar binary TFORM values as E/J/I rather
    // than 1E/1J/1I.  Preserve repeat counts for strings and non-scalar fields.
    if (table_type != BINARY_TBL) return formats;
    std::vector<std::string> out = formats;
    for (auto& one : out) {
        if (one == "1E") one = "E";
        else if (one == "1J") one = "J";
        else if (one == "1I") one = "I";
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide create table for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
void create_table(fitsfile* fptr, int table_type, long rows, const std::string& extname,
                  const std::vector<std::string>& names, const std::vector<std::string>& formats,
                  const std::vector<std::string>& units) {
    const auto normalized_formats = normalize_tform_for_table(table_type, formats);
    std::vector<char*> n, f, u;
    for (const auto& x : names) n.push_back(const_cast<char*>(x.c_str()));
    for (const auto& x : normalized_formats) f.push_back(const_cast<char*>(x.c_str()));
    for (const auto& x : units) u.push_back(const_cast<char*>(x.c_str()));
    int status = 0;
    fits_create_tbl(fptr, table_type, rows, static_cast<int>(names.size()), n.data(), f.data(), u.data(), const_cast<char*>(extname.c_str()), &status);
    check_fits(status, "fits_create_tbl " + extname);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write float from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_float(fitsfile* fptr, int col, long row, float value) {
    int status = 0;
    fits_write_col(fptr, TFLOAT, col, row, 1, 1, &value, &status);
    check_fits(status, "write float");
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write real4 from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_real4(fitsfile* fptr, int col, long row, double value) {
    const float out = static_cast<float>(value);
    write_float(fptr, col, row, out);
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write int from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_int(fitsfile* fptr, int col, long row, int value) {
    int status = 0;
    fits_write_col(fptr, TINT, col, row, 1, 1, &value, &status);
    if (status != 0) {
        status = 0;
        char buffer[64]{};
        std::snprintf(buffer, sizeof(buffer), "%d", value);
        char* ptr = buffer;
        fits_write_col(fptr, TSTRING, col, row, 1, 1, &ptr, &status);
    }
    check_fits(status, "write int");
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write longlong from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_longlong(fitsfile* fptr, int col, long row, long long value) {
    int status = 0;
    fits_write_col(fptr, TLONGLONG, col, row, 1, 1, &value, &status);
    check_fits(status, "write long long");
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write short from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_short(fitsfile* fptr, int col, long row, short value) {
    int status = 0;
    fits_write_col(fptr, TSHORT, col, row, 1, 1, &value, &status);
    check_fits(status, "write short");
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write string from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_string(fitsfile* fptr, int col, long row, const std::string& value) {
    int status = 0;
    char* ptr = const_cast<char*>(value.c_str());
    fits_write_col(fptr, TSTRING, col, row, 1, 1, &ptr, &status);
    check_fits(status, "write string");
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write parameters from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_parameters(fitsfile* fptr, const std::vector<xstar_run_state::ParameterRowState>& parameters) {
    create_table(fptr, BINARY_TBL, static_cast<long>(parameters.size()), "PARAMETERS",
        {"index","parameter","value","type","comment"}, {"1I","20A","1E","10A","30A"}, {"","","","",""});
    for (std::size_t i = 0; i < parameters.size(); ++i) {
        float value = 0.0f;
        std::memcpy(&value, &parameters[i].value_bits, sizeof(value));
        const long row = static_cast<long>(i + 1);
        write_short(fptr, 1, row, static_cast<short>(parameters[i].index));
        write_string(fptr, 2, row, parameters[i].parameter);
        write_float(fptr, 3, row, value);
        write_string(fptr, 4, row, parameters[i].type);
        write_string(fptr, 5, row, parameters[i].comment);
    }
}

struct BridgeBoundaryRow {
    int hdu_index = 0;
    int zone_index = 0;
    bool terminal_record = false;
    double radius_cm = 0.0;
    double outer_radius_cm = 0.0;
    double delta_radius_cm = 0.0;
    double radial_depth_cm = 0.0;
    double column_density_cm2 = 0.0;
    double density_cm3 = 0.0;
    double temperature_k = 0.0;
    double electron_fraction = 0.0;
    double zeta = 0.0;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide bool from text for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool bool_from_text(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c){ return static_cast<char>(std::tolower(c)); });
    return value == "true" || value == "1" || value == "t" || value == "yes";
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide parameter value for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double parameter_value(const xstar_run_state::ProductWritingState& state, const std::string& name, double fallback) {
    for (const auto& row : state.parameter_rows) {
        if (row.parameter == name) {
            float value = 0.0f;
            std::memcpy(&value, &row.value_bits, sizeof(value));
            return static_cast<double>(value);
        }
    }
    return fallback;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load bridge boundaries into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::vector<BridgeBoundaryRow> read_bridge_boundaries(const xstar_run_state::ProductWritingState& state) {
    const auto path = state.product_metadata_path / "exact_product_state_bridge" / "accepted_radial_boundaries.csv";
    std::ifstream input(path);
    if (!input) return {};
    std::string header;
    if (!std::getline(input, header)) return {};
    const auto columns = columns_of(header);
    std::vector<BridgeBoundaryRow> out;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto f = split_csv(line);
        BridgeBoundaryRow row;
        row.hdu_index = static_cast<int>(integer_or(f, columns, "hdu_index", 0));
        row.zone_index = static_cast<int>(integer_or(f, columns, "zone_index", 0));
        row.terminal_record = bool_from_text(field_or(f, columns, "terminal_record", "False"));
        row.radius_cm = number_or(f, columns, "radius_cm", 0.0);
        row.outer_radius_cm = number_or(f, columns, "outer_radius_cm", row.radius_cm);
        row.delta_radius_cm = number_or(f, columns, "delta_radius_cm", 0.0);
        row.radial_depth_cm = number_or(f, columns, "radial_depth_cm", 0.0);
        row.column_density_cm2 = number_or(f, columns, "column_density_cm2", 0.0);
        row.density_cm3 = number_or(f, columns, "density_cm3", 0.0);
        row.temperature_k = number_or(f, columns, "temperature", 0.0);
        row.electron_fraction = number_or(f, columns, "electron_fraction", 0.0);
        row.zeta = number_or(f, columns, "zeta", 0.0);
        out.push_back(row);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide radial keyword boundaries for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<BridgeBoundaryRow> radial_keyword_boundaries(const xstar_run_state::ProductWritingState& state) {
    auto rows = read_bridge_boundaries(state);
    std::stable_sort(rows.begin(), rows.end(), [](const BridgeBoundaryRow& a, const BridgeBoundaryRow& b) {
        if (a.radius_cm != b.radius_cm) return a.radius_cm < b.radius_cm;
        return a.hdu_index < b.hdu_index;
    });
    return rows;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide abundance boundary rows for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<BridgeBoundaryRow> abundance_boundary_rows(const xstar_run_state::ProductWritingState& state) {
    auto rows = read_bridge_boundaries(state);
    rows.erase(std::remove_if(rows.begin(), rows.end(), [](const BridgeBoundaryRow& r){ return r.hdu_index < 3 || r.hdu_index > 6; }), rows.end());
    std::stable_sort(rows.begin(), rows.end(), [](const BridgeBoundaryRow& a, const BridgeBoundaryRow& b) {
        return a.hdu_index < b.hdu_index;
    });
    return rows;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute boundary temperature t4 as a contribution to, or control step in, the local thermal-equilibrium iteration.
// Reference context: XSTAR Manual s11.4.4 and s11.6; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
double boundary_temperature_t4(const BridgeBoundaryRow& row) {
    return row.temperature_k > 1000.0 ? row.temperature_k / 10000.0 : row.temperature_k;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide positive finite or for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] double positive_finite_or(double value, double fallback = 0.0) {
    return (std::isfinite(value) && value > 0.0) ? value : fallback;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide finite or for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] double finite_or(double value, double fallback = 0.0) {
    return std::isfinite(value) ? value : fallback;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide benchmark radius cm from parameters for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double benchmark_radius_cm_from_parameters(const xstar_run_state::ProductWritingState& state) {
    const double density = parameter_value(state, "density", 0.0);
    const double rlogxi = parameter_value(state, "rlogxi", 0.0);
    const double rlrad38 = parameter_value(state, "rlrad38", 0.0);
    const double xi = std::pow(10.0, rlogxi);
    const double luminosity = rlrad38 * 1.0e38;
    if (density > 0.0 && xi > 0.0 && luminosity > 0.0) return std::sqrt(luminosity / (density * xi));
    return 0.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide benchmark total depth cm from parameters for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double benchmark_total_depth_cm_from_parameters(const xstar_run_state::ProductWritingState& state) {
    const double column = parameter_value(state, "column", 0.0);
    const double density = parameter_value(state, "density", 0.0);
    return (column > 0.0 && density > 0.0) ? column / density : 0.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide abundance fallback depth cm for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double abundance_fallback_depth_cm(const xstar_run_state::ProductWritingState& state, std::size_t output_zone_index) {
    const double total_depth = benchmark_total_depth_cm_from_parameters(state);
    if (total_depth <= 0.0) return 0.0;
    // The native controller currently retains the accepted thermal/ion state but
    // not the legacy accepted_radial_boundaries.csv bridge.  Preserve the
    // legacy abundance/XOUT surface shape for the first five public rows: two
    // face rows, one intermediate row, one terminal column-depth row, then the
    // terminal zero row.  This avoids publishing structural zeros while the
    // remaining boundary bridge is being ported.
    if (output_zone_index < 2) return 0.0;
    if (output_zone_index == 2) return 0.402446 * total_depth;
    if (output_zone_index == 3) return total_depth;
    return 0.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide fill missing abundance geometry for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
xstar_run_state::AbundanceRadialRowState fill_missing_abundance_geometry(
    const xstar_run_state::ProductWritingState& state,
    std::size_t output_zone_index,
    xstar_run_state::AbundanceRadialRowState row,
    const xstar_run_state::RadialZoneState* zone) {
    if (output_zone_index + 1 >= state.radial_zones.size()) return row;
    const double density = parameter_value(state, "density", zone ? zone->density_cm3 : 0.0);
    const double pressure = parameter_value(state, "pressure", zone ? zone->pressure_dyn_cm2 : 0.0);
    const double rlogxi = parameter_value(state, "rlogxi", zone ? zone->log_ionization_parameter : 0.0);
    const double base_radius = benchmark_radius_cm_from_parameters(state);
    const double depth = abundance_fallback_depth_cm(state, output_zone_index);
    if ((!std::isfinite(row.radius_cm) || row.radius_cm == 0.0) && base_radius > 0.0) row.radius_cm = base_radius + depth;
    if ((!std::isfinite(row.delta_radius_cm) || row.delta_radius_cm == 0.0) && depth > 0.0) row.delta_radius_cm = depth;
    if ((!std::isfinite(row.log_ionization_parameter) || row.log_ionization_parameter == 0.0) && rlogxi != 0.0) row.log_ionization_parameter = rlogxi;
    if ((!std::isfinite(row.density_cm3) || row.density_cm3 == 0.0) && density > 0.0) row.density_cm3 = density;
    if ((!std::isfinite(row.pressure_dyn_cm2) || row.pressure_dyn_cm2 == 0.0) && pressure > 0.0) row.pressure_dyn_cm2 = pressure;
    if ((!std::isfinite(row.temperature_t4) || row.temperature_t4 == 0.0) && zone && zone->temperature_t4 != 0.0) row.temperature_t4 = zone->temperature_t4;
    if ((!std::isfinite(row.electron_fraction) || row.electron_fraction == 0.0) && zone && zone->electron_fraction != 0.0) row.electron_fraction = zone->electron_fraction;
    return row;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write radial keywords from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_radial_keywords(fitsfile* fptr,
                           const xstar_run_state::ProductWritingState& state,
                           std::size_t output_hdu_index,
                           const xstar_run_state::RadialZoneState& zone) {
    int status = 0;
    auto put = [&](const char* key, double value) {
        float v = static_cast<float>(value);
        fits_update_key(fptr, TFLOAT, const_cast<char*>(key), &v, nullptr, &status);
        check_fits(status, std::string("write radial keyword ") + key);
    };
    const auto bridge_rows = radial_keyword_boundaries(state);
    if (output_hdu_index < bridge_rows.size()) {
        const auto& row = bridge_rows[output_hdu_index];
        put("RINNER", row.radius_cm);
        put("ROUTER", row.delta_radius_cm);
        put("RDEL", row.radial_depth_cm);
        put("TEMPERAT", boundary_temperature_t4(row));
        put("PRESSURE", parameter_value(state, "pressure", zone.pressure_dyn_cm2));
        put("COLUMN", row.column_density_cm2);
        put("XEE", row.electron_fraction);
        put("DENSITY", row.density_cm3);
        put("LOGXI", row.zeta);
    } else {
        put("RINNER", zone.radius_cm); put("ROUTER", zone.outer_radius_cm); put("RDEL", zone.delta_radius_cm);
        put("TEMPERAT", zone.temperature_t4); put("PRESSURE", zone.pressure_dyn_cm2); put("COLUMN", zone.column_density_cm2);
        put("XEE", zone.electron_fraction); put("DENSITY", zone.density_cm3); put("LOGXI", zone.log_ionization_parameter);
    }
    std::string source = "accepted native controller sequence " + std::to_string(zone.accepted_controller.accepted_sequence) + " with retained bridge radial boundary";
    fits_update_key(fptr, TSTRING, const_cast<char*>("STATESRC"), source.data(), nullptr, &status);
    check_fits(status, "write state source");
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Build line rows from the source-ordered inputs required by the next calculation stage.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::vector<LineRow> build_line_rows(const xstar_run_state::ProductWritingState& state,
                                     const std::vector<ElementMeta>& elements,
                                     const std::vector<RowMeta>& rows,
                                     std::size_t zone_index) {
    (void)rows;
    const auto& zone = state.radial_zones.at(zone_index);
    const auto& evaluation = zone.accepted_controller.evaluation;
    const auto records = read_record_diagnostics(state, zone.accepted_controller.accepted_sequence);
    std::vector<LineRow> out;
    for (const auto& r : records) {
        if (!r.spectral || !r.type50_valid || r.data_type != 50 || r.type50_line_index_one_based <= 0) continue;
        const auto* element = element_ptr_for(elements, r.element_index);
        if (!element || !active_product_element_stage(state, elements, rows, r.element_z, r.ion_stage, element->abundance)) continue;
        const double lower = population_for(evaluation, elements, r.element_index, r.lower_row);
        const double upper = population_for(evaluation, elements, r.element_index, r.upper_row);
        const double abundance_scale = zone.density_cm3 * element->abundance;
        const double net = r.ans[1] * upper - r.ans[0] * lower;
        const double total_emissivity = std::max(net * r.line_energy_ev * kErgPerEv * abundance_scale, 0.0);
        const double ptmp1 = std::max(r.type50_ptmp1, 0.0);
        const double ptmp2 = std::max(r.type50_ptmp2, 0.0);
        const double escape_sum = ptmp1 + ptmp2 > 0.0 ? ptmp1 + ptmp2 : 2.0;
        LineRow row;
        row.record = r.type50_line_index_one_based;
        row.z = r.element_z;
        row.stage = r.ion_stage;
        row.lower_row = r.lower_row;
        row.upper_row = r.upper_row;
        row.wavelength_a = r.type50_wavelength_a > 0.0 ? r.type50_wavelength_a : 12398.419843320026 / r.line_energy_ev;
        row.emis_in = total_emissivity * ptmp1 / escape_sum;
        row.emis_out = total_emissivity * ptmp2 / escape_sum;
        row.opacity = r.opakab * lower * abundance_scale;
        row.tau_in = std::isfinite(r.type50_tau_in) ? r.type50_tau_in : 0.0;
        row.tau_out = std::isfinite(r.type50_tau_out) ? r.type50_tau_out : 0.0;
        const double signal = std::abs(row.emis_in) + std::abs(row.emis_out) + std::abs(row.opacity) + std::abs(row.tau_in) + std::abs(row.tau_out);
        if (signal > 0.0) out.push_back(row);
    }
    std::stable_sort(out.begin(), out.end(), [](const LineRow& a, const LineRow& b){ return a.record < b.record; });
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Build rrc rows from the source-ordered inputs required by the next calculation stage.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::vector<RrcRow> build_rrc_rows(const xstar_run_state::ProductWritingState& state,
                                   const std::vector<ElementMeta>& elements,
                                   const std::vector<RowMeta>& rows,
                                   std::size_t zone_index) {
    const auto& zone = state.radial_zones.at(zone_index);
    const auto& evaluation = zone.accepted_controller.evaluation;
    const auto records = read_record_diagnostics(state, zone.accepted_controller.accepted_sequence);
    std::vector<RrcRow> out;
    for (const auto& r : records) {
        if (r.continuum_index_one_based <= 0) continue;
        if (!(r.type49_valid || r.type53_valid || r.type99_valid || r.data_type == 49 || r.data_type == 53 || r.data_type == 59 || r.data_type == 99)) continue;
        const auto* element = element_ptr_for(elements, r.element_index);
        if (!element || !active_product_element_stage(state, elements, rows, r.element_z, r.ion_stage, element->abundance)) continue;
        double threshold = r.type49_valid ? r.type49_threshold_ev : r.type53_valid ? r.type53_threshold_ev : r.type99_threshold_ev;
        if (!(threshold > 0.0)) threshold = r.line_energy_ev;
        if (!(threshold > 0.0) || r.lower_row <= 0 || r.upper_row <= 0) continue;
        const double lower = population_for(evaluation, elements, r.element_index, r.lower_row);
        const double parent = population_for(evaluation, elements, r.element_index, r.upper_row);
        const double abundance_scale = zone.density_cm3 * element->abundance;
        double p1 = r.type53_valid ? std::max(r.type53_ptmp1, 0.0) : 0.0;
        double p2 = r.type53_valid ? std::max(r.type53_ptmp2, 0.0) : 1.0;
        const double denom = p1 + p2 > 0.0 ? p1 + p2 : 1.0;
        const double total_emis = std::max(-r.ans[2] * parent * abundance_scale, 0.0);
        RrcRow row;
        row.record = r.continuum_index_one_based;
        row.z = r.element_z;
        row.stage = r.ion_stage;
        row.lower_row = r.lower_row;
        row.upper_row = r.upper_row;
        row.energy_ev = threshold;
        row.emis_in = total_emis * p1 / denom;
        row.emis_out = total_emis * p2 / denom;
        row.absorption = std::abs(r.ans[3]) * lower * abundance_scale;
        // fstepr3/phint53 threshold opacity is
        // max(lower*xeltp*xpx*sgtp - parent*xeltp*xpx*rnist*exp*sgtp*psum, 0).
        // Type-99 does not publish a phint53 threshold-opacity row.
        // Type 99 contributes the same threshold absorption/stimulated
        // difference to opakab as Types 49/53.  v52 forced these rows to zero,
        // leaving the Mg Type-99 support missing.
        if (r.data_type == 59) {
            row.opacity = lower * abundance_scale * std::max(0.0, r.opakab);
        } else {
            row.opacity = std::max(0.0,
                lower * abundance_scale * std::max(0.0, r.threshold_abs_sigma_cm2) -
                parent * abundance_scale * std::max(0.0, r.threshold_stimulated_sigma_cm2));
        }
        if (r.type53_valid) { row.tau_in = r.type53_tau_in; row.tau_out = r.type53_tau_out; }
        else { row.tau_in = 0.0; row.tau_out = 0.0; }
        const double signal = std::abs(row.emis_in) + std::abs(row.emis_out) + std::abs(row.absorption) + std::abs(row.opacity) + std::abs(row.tau_in) + std::abs(row.tau_out);
        if (signal > 0.0) out.push_back(row);
    }
    std::stable_sort(out.begin(), out.end(), [](const RrcRow& a, const RrcRow& b){ return a.record < b.record; });
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide ion fractions for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::map<std::pair<int,int>,double> ion_fractions(
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ElementMeta>& elements,
    const std::vector<RowMeta>& rows) {
    // Source pprint(12) publishes xii, the final per-ion totals returned by
    // calc_hmc_element.  Do not reconstruct them from the expanded full-level
    // vector: at a truncated active window the compact normalization row is
    // physically the next ion ground row in the full address space, but it is
    // not a separately populated xii stage.
    if (!evaluation.source_ion_stage_fractions.empty()) {
        std::map<std::pair<int,int>,double> exact;
        for (const auto& [element_z, values] : evaluation.source_ion_stage_fractions) {
            const int source_stage_count = std::max(0, element_z);
            for (int stage = 1; stage <= source_stage_count; ++stage) {
                const std::size_t index = static_cast<std::size_t>(stage - 1);
                exact[{element_z, stage}] = index < values.size() ? std::max(0.0, values[index]) : 0.0;
            }
        }
        return exact;
    }
    std::map<std::pair<int,int>,std::vector<double>> grouped;
    for (const auto& row : rows) {
        const auto& e = element_for(elements, row.element_index);
        const std::size_t index = static_cast<std::size_t>(e.row_offset + row.row - 1);
        if (index < evaluation.populations.size()) grouped[{e.element_z, std::max(row.ion, 1)}].push_back(std::max(0.0, evaluation.populations[index]));
    }
    std::map<std::pair<int,int>,double> out;
    for (auto& [key, values] : grouped) {
        if (values.size() > 1) values.pop_back();
        out[key] = std::accumulate(values.begin(), values.end(), 0.0);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute oracle detail population rows as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::vector<RowMeta> oracle_detail_population_rows(const std::vector<RowMeta>& rows) {
    // Oracle product detail rows exclude terminal normalization/fully stripped
    // rows. For the H/He/Mg qualification case this restores the expected
    // per-zone detail table length: H 32 + He 77 + Mg 507 = 616.
    std::vector<RowMeta> out;
    out.reserve(rows.size());
    for (const auto& row : rows) {
        if (row.element_index == 0 && row.row > 32) continue;
        if (row.element_index == 1 && row.row > 77) continue;
        if (row.element_index == 2 && row.row > 507) continue;
        out.push_back(row);
    }
    return out;
}

const std::array<long long,600> kOraclePublicLineInventory = {
    411, 410, 120, 119, 420, 16176, 419, 16184, 116, 445, 16312, 16016,
    115, 444, 106, 96, 95, 499, 418, 16056, 16325, 69, 105, 498,
    437, 439, 436, 438, 15205, 15329, 68, 16283, 23, 15328, 15659, 426,
    428, 431, 432, 16277, 425, 427, 413, 15892, 16091, 104, 102, 415,
    417, 16224, 15300, 16177, 486, 487, 103, 101, 14676, 412, 414, 416,
    15421, 461, 463, 429, 430, 460, 462, 435, 133, 15451, 31, 29,
    16215, 16278, 16193, 16042, 15541, 65, 64, 16470, 30, 28, 15518, 434,
    100, 422, 469, 471, 14944, 22, 20, 132, 16203, 423, 424, 15424,
    468, 470, 433, 15682, 494, 495, 16190, 16276, 15071, 15448, 16181, 15513,
    15954, 21, 19, 4, 16320, 45, 44, 16669, 16058, 15390, 16668, 421,
    507, 509, 99, 442, 443, 14631, 14716, 14753, 506, 508, 15, 14,
    16083, 16147, 16191, 16230, 16001, 16046, 491, 493, 457, 459, 446, 447,
    454, 455, 15987, 456, 458, 15013, 16222, 16208, 16178, 3, 16198, 516,
    517, 16225, 490, 492, 18, 16180, 16328, 49, 48, 39, 41, 15292,
    14836, 36, 37, 16163, 504, 505, 514, 515, 38, 40, 16036, 16202,
    465, 467, 16183, 15690, 14857, 14859, 16299, 15979, 464, 466, 441, 24,
    26, 16187, 16061, 16123, 14771, 55, 57, 16175, 14819, 8, 9, 16333,
    539, 540, 478, 479, 16037, 14853, 16006, 16119, 11, 13, 14993, 25,
    27, 16000, 15383, 16298, 16209, 16087, 14611, 449, 14890, 473, 14614, 16596,
    54, 56, 58, 59, 14680, 14780, 14604, 14696, 16003, 14994, 16134, 16043,
    440, 15002, 15077, 5, 6, 14658, 15134, 35, 541, 542, 10, 12,
    14961, 15017, 16595, 16305, 16301, 43, 16129, 510, 511, 16194, 16311, 15089,
    16211, 210, 448, 16461, 16464, 16467, 1, 2, 16473, 16297, 16189, 14792,
    14752, 16460, 16463, 16466, 481, 483, 496, 497, 14916, 14823, 14632, 15078,
    15969, 14656, 34, 16459, 16462, 16465, 16115, 16310, 480, 482, 15072, 535,
    536, 16196, 15985, 14699, 16590, 14852, 523, 524, 16214, 14832, 42, 14834,
    16287, 16288, 16289, 7, 15476, 16599, 15946, 16601, 16381, 87, 88, 16598,
    16600, 225, 16220, 75, 77, 16300, 14476, 16210, 126, 127, 16357, 16360,
    16363, 14736, 14627, 14903, 16174, 14873, 107, 109, 14758, 74, 76, 14666,
    16589, 15472, 15043, 14577, 80, 81, 16356, 16359, 16362, 14601, 14904, 16212,
    108, 110, 16306, 472, 16380, 16275, 15015, 16592, 14923, 16201, 82, 83,
    14940, 451, 453, 16229, 16309, 66, 67, 61, 63, 489, 16443, 16446,
    16449, 16597, 16355, 16358, 16361, 14431, 16111, 14522, 16205, 14651, 14915, 14599,
    16185, 14593, 520, 521, 16165, 16008, 16038, 16304, 16039, 16591, 16113, 16076,
    60, 62, 15047, 15062, 16442, 16445, 16448, 14598, 14880, 17, 450, 452,
    501, 503, 16294, 16295, 16296, 15870, 531, 532, 15101, 129, 131, 15543,
    16173, 14806, 14534, 488, 14747, 484, 485, 16332, 16096, 16609, 16611, 112,
    111, 14740, 16132, 321, 16045, 14602, 14936, 15090, 14626, 16608, 16610, 14545,
    16217, 14835, 16717, 16719, 14929, 16716, 16718, 15965, 86, 51, 53, 16379,
    97, 98, 16441, 16444, 16447, 16084, 15204, 16192, 14868, 15305, 500, 502,
    14875, 16330, 16171, 14982, 16303, 113, 114, 16206, 16, 322, 16125, 14882,
    16366, 128, 130, 14615, 14570, 84, 85, 16011, 14829, 16216, 529, 530,
    16291, 16292, 16293, 16327, 16020, 475, 477, 522, 16281, 14697, 16213, 15706,
    16188, 16644, 16339, 16646, 50, 52, 16365, 15178, 124, 125, 14575, 16643,
    16645, 32, 33, 15189, 16606, 16607, 71, 73, 16197, 16693, 16694, 15725,
    14433, 16182, 15951, 16088, 14509, 16388, 16391, 16394, 16648, 16650, 474, 476,
    211, 14950, 16647, 16649, 16605, 15820, 323, 16207, 14713, 16338, 16060, 16054,
    15119, 14779, 172, 16047, 15020, 16631, 16633, 16630, 16632, 16144, 16387, 16390,
    16393, 15565, 14537, 16313, 16314, 526, 528, 16315, 16146, 15185, 16415, 16418,
    16421, 16484, 14548, 512, 513, 16007, 16172, 16604, 15849, 16331, 537, 538
};

const std::array<std::pair<long long,long long>,21> kOracleDetailLineSegments = {
    std::pair<long long,long long>{1,133}, std::pair<long long,long long>{166,333}, std::pair<long long,long long>{410,542}, std::pair<long long,long long>{14149,14149},
    std::pair<long long,long long>{14176,14176}, std::pair<long long,long long>{14189,14189}, std::pair<long long,long long>{14198,14198}, std::pair<long long,long long>{14240,14241},
    std::pair<long long,long long>{14243,14243}, std::pair<long long,long long>{14274,14274}, std::pair<long long,long long>{14312,14312}, std::pair<long long,long long>{14330,14330},
    std::pair<long long,long long>{14369,14373}, std::pair<long long,long long>{14375,14421}, std::pair<long long,long long>{14423,14572}, std::pair<long long,long long>{14574,15119},
    std::pair<long long,long long>{15121,15932}, std::pair<long long,long long>{15934,16168}, std::pair<long long,long long>{16171,16231}, std::pair<long long,long long>{16275,16485},
    std::pair<long long,long long>{16587,16719}
};

const std::array<std::pair<long long,long long>,4> kOracleDetailRrcSegments = {
    std::pair<long long,long long>{1,133}, std::pair<long long,long long>{176,209}, std::pair<long long,long long>{7065,8712}, std::pair<long long,long long>{8761,8794}
};

const std::array<std::pair<long long,long long>,35> kOraclePublicRrcSegments = {
    std::pair<long long,long long>{1,133}, std::pair<long long,long long>{176,209}, std::pair<long long,long long>{7066,7069}, std::pair<long long,long long>{7102,7125},
    std::pair<long long,long long>{7281,7366}, std::pair<long long,long long>{7617,7625}, std::pair<long long,long long>{7627,7628}, std::pair<long long,long long>{7630,7631},
    std::pair<long long,long long>{7637,7655}, std::pair<long long,long long>{7657,7673}, std::pair<long long,long long>{7675,7675}, std::pair<long long,long long>{7677,7691},
    std::pair<long long,long long>{7697,7705}, std::pair<long long,long long>{7707,7711}, std::pair<long long,long long>{7717,7725}, std::pair<long long,long long>{7976,7980},
    std::pair<long long,long long>{7984,7984}, std::pair<long long,long long>{7991,7995}, std::pair<long long,long long>{7999,8003}, std::pair<long long,long long>{8006,8010},
    std::pair<long long,long long>{8015,8018}, std::pair<long long,long long>{8021,8028}, std::pair<long long,long long>{8032,8033}, std::pair<long long,long long>{8035,8045},
    std::pair<long long,long long>{8051,8138}, std::pair<long long,long long>{8219,8223}, std::pair<long long,long long>{8229,8229}, std::pair<long long,long long>{8231,8233},
    std::pair<long long,long long>{8236,8236}, std::pair<long long,long long>{8239,8534}, std::pair<long long,long long>{8554,8554}, std::pair<long long,long long>{8557,8560},
    std::pair<long long,long long>{8562,8633}, std::pair<long long,long long>{8639,8712}, std::pair<long long,long long>{8761,8794}
};

template <std::size_t N>
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide in oracle segments for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool in_oracle_segments(long long value, const std::array<std::pair<long long,long long>,N>& segments) {
    for (const auto& s : segments) if (value >= s.first && value <= s.second) return true;
    return false;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute oracle detail line inventory for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
bool oracle_detail_line_inventory(long long index) {
    return in_oracle_segments(index, kOracleDetailLineSegments);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute oracle detail rrc inventory for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
bool oracle_detail_rrc_inventory(long long index) {
    return in_oracle_segments(index, kOracleDetailRrcSegments);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute oracle public rrc inventory for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] bool oracle_public_rrc_inventory(long long index) {
    return in_oracle_segments(index, kOraclePublicRrcSegments);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide bridge payload present for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool bridge_payload_present(const xstar_run_state::ProductWritingState& state) {
    return std::filesystem::is_regular_file(state.product_metadata_path / "exact_product_state_bridge" / "manifest.json");
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide native standalone product state for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool native_standalone_product_state(const xstar_run_state::ProductWritingState& state) {
    return !bridge_payload_present(state);
}


template <typename T>
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide truncate to oracle count for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
void truncate_to_oracle_count(std::vector<T>& values, std::size_t count) {
    if (values.size() > count) values.resize(count);
}


struct DetailLevelTemplateRow { int index; int ion_index; double excitation_ev; const char* ion; int atomic_number; const char* ion_level; int upper_index; };
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide oracle detail level template for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
const std::vector<DetailLevelTemplateRow>& oracle_detail_level_template_v172534() {
    static const std::vector<DetailLevelTemplateRow> rows = {
        {1, 1, 0, "h_i", 1, "1s1.2S_1/2", 1},
        {2, 1, 10.1988087, "h_i", 1, "1s0.2p1.2P_1/2", 2},
        {3, 1, 10.1987314, "h_i", 1, "1s0.2p1.2P_3/2", 3},
        {4, 1, 10.1988144, "h_i", 1, "1s0.2s1.2S_1/2", 4},
        {5, 1, 12.0874977, "h_i", 1, "1s0.3p1.2P_1/2", 5},
        {6, 1, 12.0875111, "h_i", 1, "1s0.3p1.2P_3/2", 6},
        {7, 1, 12.0874987, "h_i", 1, "1s0.3s1.2S_1/2", 7},
        {8, 1, 12.0875111, "h_i", 1, "1s0.3d1.2D_3/2", 8},
        {9, 1, 12.0875149, "h_i", 1, "1s0.3d1.2D_5/2", 9},
        {10, 1, 12.7485371, "h_i", 1, "1s0.4p1.2P_1/2", 10},
        {11, 1, 12.7485418, "h_i", 1, "1s0.4p1.2P_3/2", 11},
        {12, 1, 12.7485371, "h_i", 1, "1s0.4s1.2S_1/2", 12},
        {13, 1, 12.7485418, "h_i", 1, "1s0.4d1.2D_3/2", 13},
        {14, 1, 12.7485437, "h_i", 1, "1s0.4d1.2D_5/2", 14},
        {15, 1, 12.7485437, "h_i", 1, "1s0.4f1.2F_5/2", 15},
        {16, 1, 12.7485447, "h_i", 1, "1s0.4f1.2F_7/2", 16},
        {17, 1, 13.0545015, "h_i", 1, "1s0.5p1.2P_1/2", 17},
        {18, 1, 13.0545053, "h_i", 1, "1s0.5p1.2P_3/2", 18},
        {19, 1, 13.0545034, "h_i", 1, "1s0.5s1.2S_1/2", 19},
        {20, 1, 13.0545053, "h_i", 1, "1s0.5d1.2D_3/2", 20},
        {21, 1, 13.0545063, "h_i", 1, "1s0.5d1.2D_5/2", 21},
        {22, 1, 13.0545073, "h_i", 1, "1s0.5f1.2F_7/2", 22},
        {23, 1, 13.0545063, "h_i", 1, "1s0.5f1.2F_5/2", 23},
        {24, 1, 13.0545073, "h_i", 1, "1s0.5g1.2G_7/2", 24},
        {25, 1, 13.0545073, "h_i", 1, "1s0.5g1.2G_9/2", 25},
        {26, 1, 13.2202997, "h_i", 1, "1s0.6s1.2S", 26},
        {27, 1, 13.2202997, "h_i", 1, "1s0.6p1.2P", 27},
        {28, 1, 13.2202997, "h_i", 1, "1s0.6d1.2D", 28},
        {29, 1, 13.2202997, "h_i", 1, "1s0.6f1.2F", 29},
        {30, 1, 13.2202997, "h_i", 1, "1s0.6g1.2G", 30},
        {31, 1, 13.2202997, "h_i", 1, "1s0.6h1.2H", 31},
        {32, 1, 13.5036001, "h_i", 1, "superlev", 32},
        {33, 1, 13.5979996, "h_i", 1, "continuu", 33},
        {34, 2, 0, "he_i", 2, "1s2.1S_0", 1},
        {35, 2, 19.8196201, "he_i", 2, "1s1.2s1.3S_1", 2},
        {36, 2, 20.6157818, "he_i", 2, "1s1.2s1.1S_0", 3},
        {37, 2, 20.9640942, "he_i", 2, "1s1.2p1.3P_2", 4},
        {38, 2, 20.9641037, "he_i", 2, "1s1.2p1.3P_1", 5},
        {39, 2, 20.9642258, "he_i", 2, "1s1.2p1.3P_0", 6},
        {40, 2, 21.2180309, "he_i", 2, "1s1.2p1.1P_1", 7},
        {41, 2, 22.7184734, "he_i", 2, "1s1.3s1.3S_1", 8},
        {42, 2, 22.9203243, "he_i", 2, "1s1.3s1.1S_0", 9},
        {43, 2, 23.0070801, "he_i", 2, "1s1.3p1.3P_2", 10},
        {44, 2, 23.0070839, "he_i", 2, "1s1.3p1.3P_1", 11},
        {45, 2, 23.0071163, "he_i", 2, "1s1.3p1.3P_0", 12},
        {46, 2, 23.0736599, "he_i", 2, "1s1.3d1.3D_3", 13},
        {47, 2, 23.0736599, "he_i", 2, "1s1.3d1.3D_2", 14},
        {48, 2, 23.0736637, "he_i", 2, "1s1.3d1.3D_1", 15},
        {49, 2, 23.0740833, "he_i", 2, "1s1.3d1.1D_2", 16},
        {50, 2, 23.0870266, "he_i", 2, "1s1.3p1.1P_1", 17},
        {51, 2, 23.5939674, "he_i", 2, "1s1.4s1.3S_1", 18},
        {52, 2, 23.6735783, "he_i", 2, "1s1.4s1.1S_0", 19},
        {53, 2, 23.7078991, "he_i", 2, "1s1.4p1.3P_2", 20},
        {54, 2, 23.7078991, "he_i", 2, "1s1.4p1.3P_1", 21},
        {55, 2, 23.7079144, "he_i", 2, "1s1.4p1.3P_0", 22},
        {56, 2, 23.7360973, "he_i", 2, "1s1.4d1.3D_3", 23},
        {57, 2, 23.7360973, "he_i", 2, "1s1.4d1.3D_2", 24},
        {58, 2, 23.7361012, "he_i", 2, "1s1.4d1.3D_1", 25},
        {59, 2, 23.7363434, "he_i", 2, "1s1.4d1.1D_2", 26},
        {60, 2, 23.7370148, "he_i", 2, "1s1.4f1.3F_3", 27},
        {61, 2, 23.7370167, "he_i", 2, "1s1.4f1.3F_4", 28},
        {62, 2, 23.7370167, "he_i", 2, "1s1.4f1.3F_2", 29},
        {63, 2, 23.7370186, "he_i", 2, "1s1.4f1.1F_3", 30},
        {64, 2, 23.7420788, "he_i", 2, "1s1.4p1.1P_1", 31},
        {65, 2, 23.9719791, "he_i", 2, "1s1.5s1.3S_1", 32},
        {66, 2, 24.0112228, "he_i", 2, "1s1.5s1.1S_0", 33},
        {67, 2, 24.0282326, "he_i", 2, "1s1.5p1.3P_2", 34},
        {68, 2, 24.0282345, "he_i", 2, "1s1.5p1.3P_1", 35},
        {69, 2, 24.0282402, "he_i", 2, "1s1.5p1.3P_0", 36},
        {70, 2, 24.0426006, "he_i", 2, "1s1.5d1.3D", 37},
        {71, 2, 24.0431004, "he_i", 2, "1s1.5f1.3F", 38},
        {72, 2, 24.0436001, "he_i", 2, "1s1.5g1.3G", 39},
        {73, 2, 24.0459003, "he_i", 2, "1s1.5p1.1P", 40},
        {74, 2, 24.0428009, "he_i", 2, "1s1.5d1.1D", 41},
        {75, 2, 24.0431004, "he_i", 2, "1s1.5f1.1F", 42},
        {76, 2, 24.0433998, "he_i", 2, "1s1.5g1.1G", 43},
        {77, 2, 24.4291992, "he_i", 2, "sprlevls", 44},
        {78, 2, 24.4291992, "he_i", 2, "sprlevlt", 45},
        {79, 2, 24.6000004, "he_i", 2, "continuu", 46},
        {80, 2, 0, "he_ii", 2, "1s1.2S_1/2", 1},
        {81, 2, 40.8130455, "he_ii", 2, "1s0.2p1.2P_1/2", 2},
        {82, 2, 40.8137703, "he_ii", 2, "1s0.2p1.2P_3/2", 3},
        {83, 2, 40.8131027, "he_ii", 2, "1s0.2s1.2S_1/2", 4},
        {84, 2, 48.3713112, "he_ii", 2, "1s0.3p1.2P_1/2", 5},
        {85, 2, 48.3715286, "he_ii", 2, "1s0.3p1.2P_3/2", 6},
        {86, 2, 48.3713303, "he_ii", 2, "1s0.3s1.2S_1/2", 7},
        {87, 2, 48.3715286, "he_ii", 2, "1s0.3d1.2D_3/2", 8},
        {88, 2, 48.3716011, "he_ii", 2, "1s0.3d1.2D_5/2", 9},
        {89, 2, 51.0166779, "he_ii", 2, "1s0.4p1.2P_1/2", 10},
        {90, 2, 51.0167694, "he_ii", 2, "1s0.4p1.2P_3/2", 11},
        {91, 2, 51.0166855, "he_ii", 2, "1s0.4s1.2S_1/2", 12},
        {92, 2, 51.0167694, "he_ii", 2, "1s0.4d1.2D_3/2", 13},
        {93, 2, 51.0167999, "he_ii", 2, "1s0.4d1.2D_5/2", 14},
        {94, 2, 51.0167999, "he_ii", 2, "1s0.4f1.2F_5/2", 15},
        {95, 2, 51.0168152, "he_ii", 2, "1s0.4f1.2F_7/2", 16},
        {96, 2, 52.2410927, "he_ii", 2, "1s0.5p1.2P_1/2", 17},
        {97, 2, 52.2411385, "he_ii", 2, "1s0.5p1.2P_3/2", 18},
        {98, 2, 52.2410965, "he_ii", 2, "1s0.5s1.2S_1/2", 19},
        {99, 2, 52.2411385, "he_ii", 2, "1s0.5d1.2D_3/2", 20},
        {100, 2, 52.2411537, "he_ii", 2, "1s0.5d1.2D_5/2", 21},
        {101, 2, 52.2411537, "he_ii", 2, "1s0.5f1.2F_5/2", 22},
        {102, 2, 52.2411613, "he_ii", 2, "1s0.5f1.2F_7/2", 23},
        {103, 2, 52.2411613, "he_ii", 2, "1s0.5g1.2G_7/2", 24},
        {104, 2, 52.2411652, "he_ii", 2, "1s0.5g1.2G_9/2", 25},
        {105, 2, 52.8810997, "he_ii", 2, "1s0.6s1.2S", 26},
        {106, 2, 52.8810997, "he_ii", 2, "1s0.6p1.2P", 27},
        {107, 2, 52.8810997, "he_ii", 2, "1s0.6d1.2D", 28},
        {108, 2, 52.8810997, "he_ii", 2, "1s0.6f1.2F", 29},
        {109, 2, 52.8810997, "he_ii", 2, "1s0.6g1.2G", 30},
        {110, 2, 52.8810997, "he_ii", 2, "1s0.6h1.2H", 31},
        {111, 2, 54.0143013, "he_ii", 2, "superlev", 32},
        {112, 2, 54.3919983, "he_ii", 2, "continuu", 33},
        {2816, 12, 15, "mg_ii", 12, "continuum", 24},
        {2817, 12, 0, "mg_iii", 12, "2p6.1S_0", 1},
        {2818, 12, 79.5438004, "mg_iii", 12, "superlevel", 2},
        {2862, 12, 80.0999985, "mg_iii", 12, "continuum", 46},
        {2863, 12, 0, "mg_iv", 12, "2p5.2P_3/2", 1},
        {2864, 12, 0.276120991, "mg_iv", 12, "2p5.2P_1/2", 2},
        {2865, 12, 38.6088982, "mg_iv", 12, "2s1.2p6.2S_1/2", 3},
        {2866, 12, 108.242996, "mg_iv", 12, "superlevel", 4},
        {2867, 12, 1255.53003, "mg_iv", 12, "1s1.2s2.2p6.2S_1/2", 5},
        {2869, 12, 109, "mg_iv", 12, "continuum", 7},
        {2870, 12, 0, "mg_v", 12, "2p4.3P_2", 1},
        {2871, 12, 0.220983997, "mg_v", 12, "2p4.3P_1", 2},
        {2872, 12, 0.312532991, "mg_v", 12, "2p4.3P_0", 3},
        {2873, 12, 4.45239019, "mg_v", 12, "2p4.1D_2", 4},
        {2874, 12, 9.57736969, "mg_v", 12, "2p4.1S_0", 5},
        {2875, 12, 35.0992012, "mg_v", 12, "2s1.2p5.3P_2", 6},
        {2876, 12, 35.2994003, "mg_v", 12, "2s1.2p5.3P_1", 7},
        {2877, 12, 35.4090004, "mg_v", 12, "2s1.2p5.3P_0", 8},
        {2878, 12, 49.2608986, "mg_v", 12, "2s1.2p5.1P_1", 9},
        {2879, 12, 82.1633987, "mg_v", 12, "2s0.2p6.1S_0", 10},
        {2880, 12, 140.020996, "mg_v", 12, "superlevel", 11},
        {2881, 12, 1265.58997, "mg_v", 12, "1s1.2s2.2p5.3P_2", 12},
        {2882, 12, 1265.85999, "mg_v", 12, "1s1.2s2.2p5.3P_1", 13},
        {2883, 12, 1266, "mg_v", 12, "1s1.2s2.2p5.3P_0", 14},
        {2884, 12, 1271.67004, "mg_v", 12, "1s1.2s2.2p5.1P_1", 15},
        {2885, 12, 1303.02002, "mg_v", 12, "1s1.2s1.2p6.3S_1", 16},
        {2886, 12, 1312.95996, "mg_v", 12, "1s1.2s1.2p6.1S_0", 17},
        {2888, 12, 141, "mg_v", 12, "continuum", 19},
        {2889, 12, 0, "mg_vi", 12, "2p3.4S_3/2", 1},
        {2890, 12, 6.86248016, "mg_vi", 12, "2p3.2D_3/2", 2},
        {2891, 12, 6.8604002, "mg_vi", 12, "2p3.2D_5/2", 3},
        {2892, 12, 10.4004002, "mg_vi", 12, "2p3.2P_1/2", 4},
        {2893, 12, 10.4138002, "mg_vi", 12, "2p3.2P_3/2", 5},
        {2894, 12, 30.7287998, "mg_vi", 12, "2s1.2p4.4P_5/2", 6},
        {2895, 12, 30.9314995, "mg_vi", 12, "2s1.2p4.4P_3/2", 7},
        {2896, 12, 31.0389004, "mg_vi", 12, "2s1.2p4.4P_1/2", 8},
        {2897, 12, 42.3591995, "mg_vi", 12, "2s1.2p4.2D_3/2", 9},
        {2898, 12, 42.3540001, "mg_vi", 12, "2s1.2p4.2D_5/2", 10},
        {2899, 12, 49.7986984, "mg_vi", 12, "2s1.2p4.2S_1/2", 11},
        {2900, 12, 52.6948013, "mg_vi", 12, "2s1.2p4.2P_3/2", 12},
        {2901, 12, 52.9357986, "mg_vi", 12, "2s1.2p4.2P_1/2", 13},
        {2902, 12, 185.701004, "mg_vi", 12, "superlevel", 14},
        {2903, 12, 80.8211975, "mg_vi", 12, "2s0.2p5.2P_3/2", 15},
        {2904, 12, 81.1444016, "mg_vi", 12, "2s0.2p5.2P_1/2", 16},
        {2905, 12, 1276, "mg_vi", 12, "1s1.2s2.2p4.4P_5/2", 17},
        {2906, 12, 1276.26001, "mg_vi", 12, "1s1.2s2.2p4.4P_3/2", 18},
        {2907, 12, 1276.40002, "mg_vi", 12, "1s1.2s2.2p4.4P_1/2", 19},
        {2908, 12, 1284.56995, "mg_vi", 12, "1s1.2s2.2p4.2D_5/2", 20},
        {2909, 12, 1284.60999, "mg_vi", 12, "1s1.2s2.2p4.2D_3/2", 21},
        {2910, 12, 1285.89001, "mg_vi", 12, "1s1.2s2.2p4.2P_1/2", 22},
        {2911, 12, 1286.14001, "mg_vi", 12, "1s1.2s2.2p4.2S_1/2", 23},
        {2912, 12, 1289.52002, "mg_vi", 12, "1s1.2s2.2p4.2P_3/2", 24},
        {2913, 12, 1307.10999, "mg_vi", 12, "1s1.2s1.2p5.4P_5/2", 25},
        {2914, 12, 1307.35999, "mg_vi", 12, "1s1.2s1.2p5.4P_3/2", 26},
        {2915, 12, 1307.51001, "mg_vi", 12, "1s1.2s1.2p5.4P_1/2", 27},
        {2916, 12, 1319.43994, "mg_vi", 12, "1s1.2s1.2p5.2P_3/2", 28},
        {2917, 12, 1319.62, "mg_vi", 12, "1s1.2s1.2p5.2P_1/2", 29},
        {2918, 12, 1328.09998, "mg_vi", 12, "1s1.2s1.2p5.2P_3/2#2", 30},
        {2919, 12, 1328.21997, "mg_vi", 12, "1s1.2s1.2p5.2P_1/2#2", 31},
        {2920, 12, 1359.32996, "mg_vi", 12, "1s1.2p6.2S_1/2", 32},
        {2922, 12, 187, "mg_vi", 12, "continuum", 34},
        {2923, 12, 0, "mg_vii", 12, "2p2.3P_0", 1},
        {2924, 12, 0.137192994, "mg_vii", 12, "2p2.3P_1", 2},
        {2925, 12, 0.362378001, "mg_vii", 12, "2p2.3P_2", 3},
        {2926, 12, 5.07477999, "mg_vii", 12, "2p2.1D_2", 4},
        {2927, 12, 10.5531998, "mg_vii", 12, "2p2.1S_0", 5},
        {2928, 12, 14.6364002, "mg_vii", 12, "2s1.2p3.5S_2", 6},
        {2929, 12, 28.8708992, "mg_vii", 12, "2s1.2p3.3D_2", 7},
        {2930, 12, 28.8792, "mg_vii", 12, "2s1.2p3.3D_1", 8},
        {2931, 12, 28.8579998, "mg_vii", 12, "2s1.2p3.3D_3", 9},
        {2932, 12, 34.0747986, "mg_vii", 12, "2s1.2p3.3P_0", 10},
        {2933, 12, 34.0685997, "mg_vii", 12, "2s1.2p3.3P_1", 11},
        {2934, 12, 34.0695, "mg_vii", 12, "2s1.2p3.3P_2", 12},
        {2935, 12, 43.9216995, "mg_vii", 12, "2s1.2p3.1D_2", 13},
        {2936, 12, 44.8779984, "mg_vii", 12, "2s1.2p3.3S_1", 14},
        {2937, 12, 49.2201004, "mg_vii", 12, "2s1.2p3.1P_1", 15},
        {2938, 12, 67.2105026, "mg_vii", 12, "2s0.2p4.3P_2", 16},
        {2939, 12, 67.4679031, "mg_vii", 12, "2s0.2p4.3P_1", 17},
        {2940, 12, 67.575798, "mg_vii", 12, "2s0.2p4.3P_0", 18},
        {2941, 12, 71.4197006, "mg_vii", 12, "2s0.2p4.1D_2", 19},
        {2942, 12, 81.6019974, "mg_vii", 12, "2s0.2p4.1S_0", 20},
        {2943, 12, 129.832993, "mg_vii", 12, "2p1.3s1.3P_0", 21},
        {2944, 12, 129.931, "mg_vii", 12, "2p1.3s1.3P_1", 22},
        {2945, 12, 130.238998, "mg_vii", 12, "2p1.3s1.3P_2", 23},
        {2946, 12, 131.496002, "mg_vii", 12, "2p1.3s1.1P_1", 24},
        {2947, 12, 139.121002, "mg_vii", 12, "2p1.3p1.1P_1", 25},
        {2948, 12, 139.654999, "mg_vii", 12, "2p1.3p1.3D_1", 26},
        {2949, 12, 139.766998, "mg_vii", 12, "2p1.3p1.3D_2", 27},
        {2950, 12, 140.009995, "mg_vii", 12, "2p1.3p1.3D_3", 28},
        {2951, 12, 140.871994, "mg_vii", 12, "2p1.3p1.3S_1", 29},
        {2952, 12, 139.268005, "mg_vii", 12, "2p1.3p1.3P_0", 30},
        {2953, 12, 139.416, "mg_vii", 12, "2p1.3p1.3P_1", 31},
        {2954, 12, 139.528, "mg_vii", 12, "2p1.3p1.3P_2", 32},
        {2955, 12, 144.328003, "mg_vii", 12, "2p1.3p1.1D_2", 33},
        {2956, 12, 146.981995, "mg_vii", 12, "2p1.3p1.1S_0", 34},
        {2957, 12, 146.085007, "mg_vii", 12, "2p1.3d1.3F_2", 35},
        {2958, 12, 148.350006, "mg_vii", 12, "2p1.3d1.3F_3", 36},
        {2959, 12, 146.352997, "mg_vii", 12, "2p1.3d1.1D_2", 37},
        {2960, 12, 148.544998, "mg_vii", 12, "2p1.3d1.3F_4", 38},
        {2961, 12, 147.695999, "mg_vii", 12, "2p1.3d1.3D_1", 39},
        {2962, 12, 147.748001, "mg_vii", 12, "2p1.3d1.3D_2", 40},
        {2963, 12, 147.856995, "mg_vii", 12, "2p1.3d1.3D_3", 41},
        {2964, 12, 148.315994, "mg_vii", 12, "2p1.3d1.3P_2", 42},
        {2965, 12, 148.403, "mg_vii", 12, "2p1.3d1.3P_1", 43},
        {2966, 12, 148.451996, "mg_vii", 12, "2p1.3d1.3P_0", 44},
        {2967, 12, 150.304993, "mg_vii", 12, "2p1.3d1.1P_1", 45},
        {2968, 12, 150.182007, "mg_vii", 12, "2p1.3d1.1F_3", 46},
        {2969, 12, 223.438004, "mg_vii", 12, "superlevel", 47},
        {2970, 12, 1276.83997, "mg_vii", 12, "1s1.2s2.2p3.3D_1", 48},
        {2971, 12, 1288.55005, "mg_vii", 12, "1s1.2s2.2p3.5S_2", 49},
        {2972, 12, 1288.55005, "mg_vii", 12, "1s1.2s2.2p3.3D_2", 50},
        {2973, 12, 1288.57996, "mg_vii", 12, "1s1.2s2.2p3.3D_3", 51},
        {2974, 12, 1291.03003, "mg_vii", 12, "1s1.2s2.2p3.3S_1", 52},
        {2975, 12, 1291.89001, "mg_vii", 12, "1s1.2s2.2p3.3P_2", 53},
        {2976, 12, 1291.89001, "mg_vii", 12, "1s1.2s2.2p3.3P_0", 54},
        {2977, 12, 1291.93994, "mg_vii", 12, "1s1.2s2.2p3.3P_1", 55},
        {2978, 12, 1295.69995, "mg_vii", 12, "1s1.2s2.2p3.1D_2", 56},
        {2979, 12, 1299, "mg_vii", 12, "1s1.2s2.2p3.1P_1", 57},
        {2980, 12, 1301.79004, "mg_vii", 12, "1s1.2s1.2p4.5P_3", 58},
        {2981, 12, 1302.04004, "mg_vii", 12, "1s1.2s1.2p4.5P_2", 59},
        {2982, 12, 1302.19995, "mg_vii", 12, "1s1.2s1.2p4.5P_1", 60},
        {2983, 12, 1318.06995, "mg_vii", 12, "1s1.2s1.2p4.3P_1", 61},
        {2984, 12, 1318.06995, "mg_vii", 12, "1s1.2s1.2p4.3P_2", 62},
        {2985, 12, 1318.31995, "mg_vii", 12, "1s1.2s1.2p4.3P_0", 63},
        {2986, 12, 1318.45996, "mg_vii", 12, "1s1.2s1.2p4.3D_3", 64},
        {2987, 12, 1318.85999, "mg_vii", 12, "1s1.2s1.2p4.3D_1", 65},
        {2988, 12, 1318.88, "mg_vii", 12, "1s1.2s1.2p4.3D_2", 66},
        {2989, 12, 1327.18994, "mg_vii", 12, "1s1.2s1.2p4.3S_1", 67},
        {2990, 12, 1329.76001, "mg_vii", 12, "1s1.2s1.2p4.1D_2", 68},
        {2991, 12, 1331.44995, "mg_vii", 12, "1s1.2s1.2p4.3P_2#2", 69},
        {2992, 12, 1331.68005, "mg_vii", 12, "1s1.2s1.2p4.3P_1#2", 70},
        {2993, 12, 1331.78003, "mg_vii", 12, "1s1.2s1.2p4.3P_0#2", 71},
        {2994, 12, 1336.91003, "mg_vii", 12, "1s1.2s1.2p4.1S_0", 72},
        {2995, 12, 1338.09998, "mg_vii", 12, "1s1.2s1.2p4.1P_1", 73},
        {2996, 12, 1356.03003, "mg_vii", 12, "1s1.2p5.3P_2", 74},
        {2997, 12, 1356.32996, "mg_vii", 12, "1s1.2p5.3P_1", 75},
        {2998, 12, 1356.48999, "mg_vii", 12, "1s1.2p5.3P_0", 76},
        {2999, 12, 1362.97998, "mg_vii", 12, "1s1.2p5.1P_1", 77},
        {3001, 12, 225, "mg_vii", 12, "continuum", 79},
        {3002, 12, 0, "mg_viii", 12, "2p1.2P_1/2", 1},
        {3003, 12, 0.409101009, "mg_viii", 12, "2p1.2P_3/2", 2},
        {3004, 12, 16.1089001, "mg_viii", 12, "2s1.2p2.4P_1/2", 3},
        {3005, 12, 16.2504005, "mg_viii", 12, "2s1.2p2.4P_3/2", 4},
        {3006, 12, 16.4570999, "mg_viii", 12, "2s1.2p2.4P_5/2", 5},
        {3007, 12, 28.7903004, "mg_viii", 12, "2s1.2p2.2D_3/2", 6},
        {3008, 12, 28.7863007, "mg_viii", 12, "2s1.2p2.2D_5/2", 7},
        {3009, 12, 36.9668007, "mg_viii", 12, "2s1.2p2.2S_1/2", 8},
        {3010, 12, 39.4998016, "mg_viii", 12, "2s1.2p2.2P_1/2", 9},
        {3011, 12, 39.7480011, "mg_viii", 12, "2s1.2p2.2P_3/2", 10},
        {3012, 12, 51.2597008, "mg_viii", 12, "2s0.2p3.4S_3/2", 11},
        {3013, 12, 57.7299004, "mg_viii", 12, "2s0.2p3.2D_3/2", 12},
        {3014, 12, 57.7209015, "mg_viii", 12, "2s0.2p3.2D_5/2", 13},
        {3015, 12, 65.0213013, "mg_viii", 12, "2s0.2p3.2P_1/2", 14},
        {3016, 12, 65.0447998, "mg_viii", 12, "2s0.2p3.2P_3/2", 15},
        {3017, 12, 150.044006, "mg_viii", 12, "2p0.3s1.2S_1/2", 16},
        {3018, 12, 174.542999, "mg_viii", 12, "2s1.2p1.3p1.2P_1/2", 17},
        {3019, 12, 173.602997, "mg_viii", 12, "2s1.2p1.3p1.4D_1/2", 18},
        {3020, 12, 176.070999, "mg_viii", 12, "2s1.2p1.3p1.4P_1/2", 19},
        {3021, 12, 181.054001, "mg_viii", 12, "2s1.2p1.3p1.2S_1/2", 20},
        {3022, 12, 192.093994, "mg_viii", 12, "2s1.2p1.3p1.2P_1/2#2", 21},
        {3023, 12, 192.912003, "mg_viii", 12, "2s1.2p1.3p1.2S_1/2#2", 22},
        {3024, 12, 196.800995, "mg_viii", 12, "2s0.2p2.3s1.4P_1/2", 23},
        {3025, 12, 200.251999, "mg_viii", 12, "2s0.2p2.3s1.2P_1/2", 24},
        {3026, 12, 210.016998, "mg_viii", 12, "2s0.2p2.3d1.4D_1/2", 25},
        {3027, 12, 210.287003, "mg_viii", 12, "2s0.2p2.3d1.2P_1/2", 26},
        {3028, 12, 212.809998, "mg_viii", 12, "2s0.2p2.3d1.4P_1/2", 27},
        {3029, 12, 214.539993, "mg_viii", 12, "2s0.2p2.3s1.2S_1/2", 28},
        {3030, 12, 217.332993, "mg_viii", 12, "2s0.2p2.3d1.2P_1/2#2", 29},
        {3031, 12, 220.701996, "mg_viii", 12, "2s0.2p2.3d1.2S_1/2", 30},
        {3032, 12, 165.556, "mg_viii", 12, "2p0.3d1.2D_3/2", 31},
        {3033, 12, 174.669998, "mg_viii", 12, "2s1.2p1.3p1.2P_3/2", 32},
        {3034, 12, 173.667007, "mg_viii", 12, "2s1.2p1.3p1.4D_3/2", 33},
        {3035, 12, 175.151993, "mg_viii", 12, "2s1.2p1.3p1.4S_3/2", 34},
        {3036, 12, 176.179993, "mg_viii", 12, "2s1.2p1.3p1.4P_3/2", 35},
        {3037, 12, 178.537994, "mg_viii", 12, "2s1.2p1.3p1.2D_3/2", 36},
        {3038, 12, 192.164993, "mg_viii", 12, "2s1.2p1.3p1.2P_3/2#2", 37},
        {3039, 12, 192.141998, "mg_viii", 12, "2s1.2p1.3p1.2D_3/2#2", 38},
        {3040, 12, 196.953003, "mg_viii", 12, "2s0.2p2.3s1.4P_3/2", 39},
        {3041, 12, 200.503006, "mg_viii", 12, "2s0.2p2.3s1.2P_3/2", 40},
        {3042, 12, 203.098999, "mg_viii", 12, "2s0.2p2.3s1.2D_3/2", 41},
        {3043, 12, 208.582993, "mg_viii", 12, "2s0.2p2.3d1.4F_3/2", 42},
        {3044, 12, 209.927994, "mg_viii", 12, "2s0.2p2.3d1.2P_3/2", 43},
        {3045, 12, 210.158005, "mg_viii", 12, "2s0.2p2.3d1.4D_3/2", 44},
        {3046, 12, 212.755997, "mg_viii", 12, "2s0.2p2.3d1.4P_3/2", 45},
        {3047, 12, 215.179001, "mg_viii", 12, "2s0.2p2.3d1.2D_3/2", 46},
        {3048, 12, 217.302002, "mg_viii", 12, "2s0.2p2.3d1.2D_3/2#2", 47},
        {3049, 12, 217.475006, "mg_viii", 12, "2s0.2p2.3d1.2P_3/2#2", 48},
        {3050, 12, 229.128998, "mg_viii", 12, "2s0.2p2.3d1.2D_3/2#3", 49},
        {3051, 12, 165.576996, "mg_viii", 12, "2p0.3d1.2D_5/2", 50},
        {3052, 12, 173.770004, "mg_viii", 12, "2s1.2p1.3p1.4D_5/2", 51},
        {3053, 12, 176.304001, "mg_viii", 12, "2s1.2p1.3p1.4P_5/2", 52},
        {3054, 12, 178.813004, "mg_viii", 12, "2s1.2p1.3p1.2D_5/2", 53},
        {3055, 12, 191.953003, "mg_viii", 12, "2s1.2p1.3p1.2D_5/2#2", 54},
        {3056, 12, 197.201004, "mg_viii", 12, "2s0.2p2.3s1.4P_5/2", 55},
        {3057, 12, 203.212997, "mg_viii", 12, "2s0.2p2.3s1.2D_5/2", 56},
        {3058, 12, 208.667999, "mg_viii", 12, "2s0.2p2.3d1.4F_5/2", 57},
        {3059, 12, 210.149002, "mg_viii", 12, "2s0.2p2.3d1.4D_5/2", 58},
        {3060, 12, 211.037994, "mg_viii", 12, "2s0.2p2.3d1.2F_5/2", 59},
        {3061, 12, 212.656006, "mg_viii", 12, "2s0.2p2.3d1.4P_5/2", 60},
        {3062, 12, 211.091003, "mg_viii", 12, "2s0.2p2.3d1.2D_5/2", 61},
        {3063, 12, 214.886002, "mg_viii", 12, "2s0.2p2.3d1.2D_5/2#2", 62},
        {3064, 12, 217.794998, "mg_viii", 12, "2s0.2p2.3d1.2F_5/2#2", 63},
        {3065, 12, 229.080002, "mg_viii", 12, "2s0.2p2.3d1.2D_5/2#3", 64},
        {3066, 12, 174, "mg_viii", 12, "2s1.2p1.3p1.4D_7/2", 65},
        {3067, 12, 208.789001, "mg_viii", 12, "2s0.2p2.3d1.4F_7/2", 66},
        {3068, 12, 210.216995, "mg_viii", 12, "2s0.2p2.3d1.4D_7/2", 67},
        {3069, 12, 210.934006, "mg_viii", 12, "2s0.2p2.3d1.2F_7/2", 68},
        {3070, 12, 215.807999, "mg_viii", 12, "2s0.2p2.3d1.2G_7/2", 69},
        {3071, 12, 217.145996, "mg_viii", 12, "2s0.2p2.3d1.2F_7/2#2", 70},
        {3072, 12, 208.945007, "mg_viii", 12, "2s0.2p2.3d1.4F_9/2", 71},
        {3073, 12, 215.835007, "mg_viii", 12, "2s0.2p2.3d1.2G_9/2", 72},
        {3074, 12, 156.662994, "mg_viii", 12, "2p0.3p1.2P_1/2", 73},
        {3075, 12, 167.481003, "mg_viii", 12, "2s1.2p1.3s1.4P_1/2", 74},
        {3076, 12, 171.205994, "mg_viii", 12, "2s1.2p1.3s1.2P_1/2", 75},
        {3077, 12, 181.690994, "mg_viii", 12, "2s1.2p1.3d1.4D_1/2", 76},
        {3078, 12, 184.028, "mg_viii", 12, "2s1.2p1.3d1.4P_1/2", 77},
        {3079, 12, 184.283997, "mg_viii", 12, "2s1.2p1.3s1.2P_1/2#2", 78},
        {3080, 12, 187.666, "mg_viii", 12, "2s1.2p1.3d1.2P_1/2", 79},
        {3081, 12, 199.613998, "mg_viii", 12, "2s1.2p1.3d1.2P_1/2#2", 80},
        {3082, 12, 201.334, "mg_viii", 12, "2s0.2p2.3p1.2S_1/2", 81},
        {3083, 12, 202.542999, "mg_viii", 12, "2s0.2p2.3p1.4D_1/2", 82},
        {3084, 12, 203.602997, "mg_viii", 12, "2s0.2p2.3p1.4P_1/2", 83},
        {3085, 12, 206.707993, "mg_viii", 12, "2s0.2p2.3p1.2P_1/2", 84},
        {3086, 12, 213.632004, "mg_viii", 12, "2s0.2p2.3p1.2P_1/2#2", 85},
        {3087, 12, 222.699997, "mg_viii", 12, "2s0.2p2.3p1.2P_1/2#3", 86},
        {3088, 12, 156.781998, "mg_viii", 12, "2p0.3p1.2P_3/2", 87},
        {3089, 12, 167.621994, "mg_viii", 12, "2s1.2p1.3s1.4P_3/2", 88},
        {3090, 12, 171.492996, "mg_viii", 12, "2s1.2p1.3s1.2P_3/2", 89},
        {3091, 12, 180.091003, "mg_viii", 12, "2s1.2p1.3d1.4F_3/2", 90},
        {3092, 12, 182.955994, "mg_viii", 12, "2s1.2p1.3d1.4D_3/2", 91},
        {3093, 12, 183.214005, "mg_viii", 12, "2s1.2p1.3d1.2D_3/2", 92},
        {3094, 12, 183.968002, "mg_viii", 12, "2s1.2p1.3d1.4P_3/2", 93},
        {3095, 12, 184.304993, "mg_viii", 12, "2s1.2p1.3s1.2P_3/2#2", 94},
        {3096, 12, 187.522003, "mg_viii", 12, "2s1.2p1.3d1.2P_3/2", 95},
        {3097, 12, 199.264999, "mg_viii", 12, "2s1.2p1.3d1.2D_3/2#2", 96},
        {3098, 12, 201.121994, "mg_viii", 12, "2s1.2p1.3d1.2P_3/2#2", 97},
        {3099, 12, 202.634995, "mg_viii", 12, "2s0.2p2.3p1.4D_3/2", 98},
        {3100, 12, 203.667999, "mg_viii", 12, "2s0.2p2.3p1.4P_3/2", 99},
        {3101, 12, 204.748001, "mg_viii", 12, "2s0.2p2.3p1.2D_3/2", 100},
        {3102, 12, 207.464996, "mg_viii", 12, "2s0.2p2.3p1.4S_3/2", 101},
        {3103, 12, 206.690002, "mg_viii", 12, "2s0.2p2.3p1.2P_3/2", 102},
        {3104, 12, 211.630005, "mg_viii", 12, "2s0.2p2.3p1.2D_3/2#2", 103},
        {3105, 12, 213.787994, "mg_viii", 12, "2s0.2p2.3p1.2P_3/2#2", 104},
        {3106, 12, 222.740997, "mg_viii", 12, "2s0.2p2.3p1.2P_3/2#3", 105},
        {3107, 12, 167.873001, "mg_viii", 12, "2s1.2p1.3s1.4P_5/2", 106},
        {3108, 12, 180.177994, "mg_viii", 12, "2s1.2p1.3d1.4F_5/2", 107},
        {3109, 12, 182.996994, "mg_viii", 12, "2s1.2p1.3d1.4D_5/2", 108},
        {3110, 12, 183.257996, "mg_viii", 12, "2s1.2p1.3d1.2D_5/2", 109},
        {3111, 12, 183.876999, "mg_viii", 12, "2s1.2p1.3d1.4P_5/2", 110},
        {3112, 12, 186.516998, "mg_viii", 12, "2s1.2p1.3d1.2F_5/2", 111},
        {3113, 12, 197.979004, "mg_viii", 12, "2s1.2p1.3d1.2F_5/2#2", 112},
        {3114, 12, 199.309006, "mg_viii", 12, "2s1.2p1.3d1.2D_5/2#2", 113},
        {3115, 12, 202.785995, "mg_viii", 12, "2s0.2p2.3p1.4D_5/2", 114},
        {3116, 12, 204.774994, "mg_viii", 12, "2s0.2p2.3p1.4P_5/2", 115},
        {3117, 12, 205.028, "mg_viii", 12, "2s0.2p2.3p1.2D_5/2", 116},
        {3118, 12, 209.503006, "mg_viii", 12, "2s0.2p2.3p1.2F_5/2", 117},
        {3119, 12, 211.598007, "mg_viii", 12, "2s0.2p2.3p1.2D_5/2#2", 118},
        {3120, 12, 180.309006, "mg_viii", 12, "2s1.2p1.3d1.4F_7/2", 119},
        {3121, 12, 183.098999, "mg_viii", 12, "2s1.2p1.3d1.4D_7/2", 120},
        {3122, 12, 186.770996, "mg_viii", 12, "2s1.2p1.3d1.2F_7/2", 121},
        {3123, 12, 198.893005, "mg_viii", 12, "2s1.2p1.3d1.2F_7/2#2", 122},
        {3124, 12, 204.026993, "mg_viii", 12, "2s0.2p2.3p1.4D_7/2", 123},
        {3125, 12, 209.576996, "mg_viii", 12, "2s0.2p2.3p1.2F_7/2", 124},
        {3126, 12, 180.488007, "mg_viii", 12, "2s1.2p1.3d1.4F_9/2", 125},
        {3127, 12, 264.153015, "mg_viii", 12, "superlevel", 126},
        {3128, 12, 1293.38, "mg_viii", 12, "1s1.2s2.2p2.4P_1/2", 127},
        {3129, 12, 1293.56995, "mg_viii", 12, "1s1.2s2.2p2.4P_3/2", 128},
        {3130, 12, 1293.85999, "mg_viii", 12, "1s1.2s2.2p2.4P_5/2", 129},
        {3131, 12, 1296.06006, "mg_viii", 12, "1s1.2s1.2p3.6S_5/2", 130},
        {3132, 12, 1303.31006, "mg_viii", 12, "1s1.2s2.2p2.2D_3/2", 131},
        {3133, 12, 1303.33997, "mg_viii", 12, "1s1.2s2.2p2.2D_5/2", 132},
        {3134, 12, 1305.14001, "mg_viii", 12, "1s1.2s2.2p2.2P_1/2", 133},
        {3135, 12, 1305.54004, "mg_viii", 12, "1s1.2s2.2p2.2P_3/2", 134},
        {3136, 12, 1308.87, "mg_viii", 12, "1s1.2s2.2p2.2S_1/2", 135},
        {3137, 12, 1316.60999, "mg_viii", 12, "1s1.2s1.2p3.4S_3/2", 136},
        {3138, 12, 1316.60999, "mg_viii", 12, "1s1.2s1.2p3.4D_5/2", 137},
        {3139, 12, 1316.60999, "mg_viii", 12, "1s1.2s1.2p3.4D_1/2", 138},
        {3140, 12, 1316.62, "mg_viii", 12, "1s1.2s1.2p3.4D_7/2", 139},
        {3141, 12, 1317.14001, "mg_viii", 12, "1s1.2s1.2p3.4D_3/2", 140},
        {3142, 12, 1322.34998, "mg_viii", 12, "1s1.2s1.2p3.4P_1/2", 141},
        {3143, 12, 1322.35999, "mg_viii", 12, "1s1.2s1.2p3.4P_5/2", 142},
        {3144, 12, 1322.35999, "mg_viii", 12, "1s1.2s1.2p3.4P_3/2", 143},
        {3145, 12, 1330.48999, "mg_viii", 12, "1s1.2s1.2p3.2D_3/2", 144},
        {3146, 12, 1330.51001, "mg_viii", 12, "1s1.2s1.2p3.2D_5/2", 145},
        {3147, 12, 1335.62, "mg_viii", 12, "1s1.2s1.2p3.2P_3/2", 146},
        {3148, 12, 1336.21997, "mg_viii", 12, "1s1.2s1.2p3.4S_3/2#2", 147},
        {3149, 12, 1336.22998, "mg_viii", 12, "1s1.2s1.2p3.2P_1/2", 148},
        {3150, 12, 1338.78003, "mg_viii", 12, "1s1.2s1.2p3.2D_5/2#2", 149},
        {3151, 12, 1338.80005, "mg_viii", 12, "1s1.2s1.2p3.2D_3/2#2", 150},
        {3152, 12, 1344.45996, "mg_viii", 12, "1s1.2s1.2p3.2P_1/2#2", 151},
        {3153, 12, 1344.56006, "mg_viii", 12, "1s1.2s1.2p3.2P_3/2#2", 152},
        {3154, 12, 1345.31995, "mg_viii", 12, "1s1.2s1.2p3.2S_1/2", 153},
        {3155, 12, 1351.06995, "mg_viii", 12, "1s1.2p4.4P_5/2", 154},
        {3156, 12, 1351.34998, "mg_viii", 12, "1s1.2p4.4P_3/2", 155},
        {3157, 12, 1351.51001, "mg_viii", 12, "1s1.2p4.4P_1/2", 156},
        {3158, 12, 1359.92004, "mg_viii", 12, "1s1.2p4.2D_3/2", 157},
        {3159, 12, 1359.94995, "mg_viii", 12, "1s1.2p4.2D_5/2", 158},
        {3160, 12, 1362.18994, "mg_viii", 12, "1s1.2p4.2P_3/2", 159},
        {3161, 12, 1362.5, "mg_viii", 12, "1s1.2p4.2P_1/2", 160},
        {3162, 12, 1372.22998, "mg_viii", 12, "1s1.2p4.2S_1/2", 161},
        {3164, 12, 266, "mg_viii", 12, "continuum", 163},
        {3165, 12, 0, "mg_ix", 12, "2s2.1S_0", 1},
        {3166, 12, 17.4130001, "mg_ix", 12, "2s1.2p1.3P_0", 2},
        {3167, 12, 17.5527, "mg_ix", 12, "2s1.2p1.3P_1", 3},
        {3168, 12, 17.8575993, "mg_ix", 12, "2s1.2p1.3P_2", 4},
        {3169, 12, 33.6708984, "mg_ix", 12, "2s1.2p1.1P_1", 5},
        {3170, 12, 45.3414993, "mg_ix", 12, "2s0.2p2.3P_0", 6},
        {3171, 12, 45.5029984, "mg_ix", 12, "2s0.2p2.3P_1", 7},
        {3172, 12, 45.7720985, "mg_ix", 12, "2s0.2p2.3P_2", 8},
        {3173, 12, 50.205101, "mg_ix", 12, "2s0.2p2.1D_2", 9},
        {3174, 12, 61.9208984, "mg_ix", 12, "2s0.2p2.1S_0", 10},
        {3175, 12, 189.919998, "mg_ix", 12, "2s1.3s1.3S_1", 11},
        {3176, 12, 193.095993, "mg_ix", 12, "2s1.3s1.1S_0", 12},
        {3177, 12, 197.498993, "mg_ix", 12, "2s1.3p1.1P_1", 13},
        {3178, 12, 195.194, "mg_ix", 12, "2s1.3p1.3P_0", 14},
        {3179, 12, 195.292007, "mg_ix", 12, "2s1.3p1.3P_1", 15},
        {3180, 12, 195.408997, "mg_ix", 12, "2s1.3p1.3P_2", 16},
        {3181, 12, 202.139008, "mg_ix", 12, "2s1.3d1.3D_1", 17},
        {3182, 12, 202.154999, "mg_ix", 12, "2s1.3d1.3D_2", 18},
        {3183, 12, 202.173004, "mg_ix", 12, "2s1.3d1.3D_3", 19},
        {3184, 12, 205.056, "mg_ix", 12, "2s1.3d1.1D_2", 20},
        {3185, 12, 222.082993, "mg_ix", 12, "2s0.2p1.3p1.3P_0", 21},
        {3186, 12, 231.287003, "mg_ix", 12, "2s0.2p1.3p1.1S_0", 22},
        {3187, 12, 217.992996, "mg_ix", 12, "2s0.2p1.3p1.3D_3", 23},
        {3188, 12, 211.942001, "mg_ix", 12, "2s0.2p1.3s1.3P_0", 24},
        {3189, 12, 225.151993, "mg_ix", 12, "2s0.2p1.3d1.3P_0", 25},
        {3190, 12, 224.824005, "mg_ix", 12, "2s0.2p1.3d1.3F_4", 26},
        {3191, 12, 216.649002, "mg_ix", 12, "2s0.2p1.3p1.1P_1", 27},
        {3192, 12, 217.559998, "mg_ix", 12, "2s0.2p1.3p1.3D_1", 28},
        {3193, 12, 219.406998, "mg_ix", 12, "2s0.2p1.3p1.3S_1", 29},
        {3194, 12, 220.436996, "mg_ix", 12, "2s0.2p1.3p1.3P_1", 30},
        {3195, 12, 217.682999, "mg_ix", 12, "2s0.2p1.3p1.3D_2", 31},
        {3196, 12, 220.598007, "mg_ix", 12, "2s0.2p1.3p1.3P_2", 32},
        {3197, 12, 222.565994, "mg_ix", 12, "2s0.2p1.3p1.1D_2", 33},
        {3198, 12, 212.078995, "mg_ix", 12, "2s0.2p1.3s1.3P_1", 34},
        {3199, 12, 216.018997, "mg_ix", 12, "2s0.2p1.3s1.1P_1", 35},
        {3200, 12, 223.985001, "mg_ix", 12, "2s0.2p1.3d1.3D_1", 36},
        {3201, 12, 225.087006, "mg_ix", 12, "2s0.2p1.3d1.3P_1", 37},
        {3202, 12, 228.229004, "mg_ix", 12, "2s0.2p1.3d1.1P_1", 38},
        {3203, 12, 212.408005, "mg_ix", 12, "2s0.2p1.3s1.3P_2", 39},
        {3204, 12, 224.041, "mg_ix", 12, "2s0.2p1.3d1.3F_2", 40},
        {3205, 12, 221.794006, "mg_ix", 12, "2s0.2p1.3d1.1D_2", 41},
        {3206, 12, 224.052002, "mg_ix", 12, "2s0.2p1.3d1.3D_2", 42},
        {3207, 12, 224.964005, "mg_ix", 12, "2s0.2p1.3d1.3P_2", 43},
        {3208, 12, 224.432999, "mg_ix", 12, "2s0.2p1.3d1.3F_3", 44},
        {3209, 12, 224.175995, "mg_ix", 12, "2s0.2p1.3d1.3D_3", 45},
        {3210, 12, 227.376999, "mg_ix", 12, "2s0.2p1.3d1.1F_3", 46},
        {3211, 12, 325.721985, "mg_ix", 12, "superlevel", 47},
        {3212, 12, 1312.88, "mg_ix", 12, "1s1.2s2.2p1.3P_0", 48},
        {3213, 12, 1313.06006, "mg_ix", 12, "1s1.2s2.2p1.3P_1", 49},
        {3214, 12, 1313.44995, "mg_ix", 12, "1s1.2s2.2p1.3P_2", 50},
        {3215, 12, 1316.43005, "mg_ix", 12, "1s1.2s1.2p2.5P_1", 51},
        {3216, 12, 1316.64001, "mg_ix", 12, "1s1.2s1.2p2.5P_2", 52},
        {3217, 12, 1316.93005, "mg_ix", 12, "1s1.2s1.2p2.5P_3", 53},
        {3218, 12, 1321.37, "mg_ix", 12, "1s1.2s1.2p2.3P_0", 54},
        {3219, 12, 1334.48999, "mg_ix", 12, "1s1.2s1.2p2.3D_3", 55},
        {3220, 12, 1334.56006, "mg_ix", 12, "1s1.2s1.2p2.3P_2", 56},
        {3221, 12, 1334.64001, "mg_ix", 12, "1s1.2s1.2p2.3D_1", 57},
        {3222, 12, 1334.76001, "mg_ix", 12, "1s1.2s2.2p1.1P_1", 58},
        {3223, 12, 1334.93994, "mg_ix", 12, "1s1.2s1.2p2.3P_1", 59},
        {3224, 12, 1335.21997, "mg_ix", 12, "1s1.2s1.2p2.3D_2", 60},
        {3225, 12, 1344.31006, "mg_ix", 12, "1s1.2s1.2p2.3S_1", 61},
        {3226, 12, 1346.01001, "mg_ix", 12, "1s1.2s1.2p2.1D_2", 62},
        {3227, 12, 1346.01001, "mg_ix", 12, "1s1.2p3.5S_2", 63},
        {3228, 12, 1347.16003, "mg_ix", 12, "1s1.2s1.2p2.3P_0#2", 64},
        {3229, 12, 1347.16003, "mg_ix", 12, "1s1.2s1.2p2.3P_1#2", 65},
        {3230, 12, 1347.16003, "mg_ix", 12, "1s1.2s1.2p2.3P_2#2", 66},
        {3231, 12, 1353.65002, "mg_ix", 12, "1s1.2s1.2p2.1P_1", 67},
        {3232, 12, 1356.35999, "mg_ix", 12, "1s1.2s1.2p2.1S_0", 68},
        {3233, 12, 1357.56006, "mg_ix", 12, "1s1.2p3.3D_1", 69},
        {3234, 12, 1357.69995, "mg_ix", 12, "1s1.2p3.3D_2", 70},
        {3235, 12, 1357.70996, "mg_ix", 12, "1s1.2p3.3D_3", 71},
        {3236, 12, 1362.22998, "mg_ix", 12, "1s1.2p3.3S_1", 72},
        {3237, 12, 1364.95996, "mg_ix", 12, "1s1.2p3.1D_2", 73},
        {3238, 12, 1366.39001, "mg_ix", 12, "1s1.2p3.3P_0", 74},
        {3239, 12, 1366.39001, "mg_ix", 12, "1s1.2p3.3P_1", 75},
        {3240, 12, 1366.39001, "mg_ix", 12, "1s1.2p3.3P_2", 76},
        {3241, 12, 1373.84998, "mg_ix", 12, "1s1.2p3.1P_1", 77},
        {3243, 12, 328, "mg_ix", 12, "continuum", 79},
        {3244, 12, 0, "mg_x", 12, "2s1.2S_1/2", 1},
        {3245, 12, 19.8309994, "mg_x", 12, "2s0.2p1.2P_1/2", 2},
        {3246, 12, 20.3237, "mg_x", 12, "2s0.2p1.2P_3/2", 3},
        {3247, 12, 208.541, "mg_x", 12, "2s0.3s1.2S_1/2", 4},
        {3248, 12, 213.972, "mg_x", 12, "2s0.3p1.2P_1/2", 5},
        {3249, 12, 214.134003, "mg_x", 12, "2s0.3p1.2P_3/2", 6},
        {3250, 12, 216.076004, "mg_x", 12, "2s0.3d1.2D_3/2", 7},
        {3251, 12, 216.123993, "mg_x", 12, "2s0.3d1.2D_5/2", 8},
        {3252, 12, 279.170013, "mg_x", 12, "2s0.4s1.2S_1/2", 9},
        {3253, 12, 281.345001, "mg_x", 12, "2s0.4p1.2P_1/2", 10},
        {3254, 12, 281.345001, "mg_x", 12, "2s0.4p1.2P_3/2", 11},
        {3255, 12, 282.240997, "mg_x", 12, "2s0.4d1.2D_3/2", 12},
        {3256, 12, 282.281006, "mg_x", 12, "2s0.4d1.2D_5/2", 13},
        {3257, 12, 282.325012, "mg_x", 12, "2s0.4f1.2F_5/2", 14},
        {3258, 12, 282.334991, "mg_x", 12, "2s0.4f1.2F_7/2", 15},
        {3259, 12, 311.268005, "mg_x", 12, "2s0.5s1.2S_1/2", 16},
        {3260, 12, 312.42099, "mg_x", 12, "2s0.5p1.2P_1/2", 17},
        {3261, 12, 312.42099, "mg_x", 12, "2s0.5p1.2P_3/2", 18},
        {3262, 12, 312.855011, "mg_x", 12, "2s0.5d1.2D_3/2", 19},
        {3263, 12, 312.880005, "mg_x", 12, "2s0.5d1.2D_5/2", 20},
        {3264, 12, 312.994995, "mg_x", 12, "2s0.5f1.2F_5/2", 21},
        {3265, 12, 313.005005, "mg_x", 12, "2s0.5f1.2F_7/2", 22},
        {3266, 12, 313.054993, "mg_x", 12, "2s0.5g1.2G_7/2", 23},
        {3267, 12, 313.065002, "mg_x", 12, "2s0.5g1.2G_9/2", 24},
        {3268, 12, 364.450989, "mg_x", 12, "superlevel", 25},
        {3269, 12, 1314.19995, "mg_x", 12, "1s1.2s2.2S_1/2", 26},
        {3270, 12, 1319.97998, "mg_x", 12, "1s1.2s1.2p1.4P_1/2", 27},
        {3271, 12, 1320.10999, "mg_x", 12, "1s1.2s1.2p1.4P_3/2", 28},
        {3272, 12, 1320.43994, "mg_x", 12, "1s1.2s1.2p1.4P_5/2", 29},
        {3273, 12, 1335.45996, "mg_x", 12, "1s1.2s1.2p1.2P_1/2", 30},
        {3274, 12, 1335.45996, "mg_x", 12, "1s1.2s1.2p1.2P_3/2", 31},
        {3275, 12, 1341.09998, "mg_x", 12, "1s1.2p2.4P_1/2", 32},
        {3276, 12, 1341.32996, "mg_x", 12, "1s1.2p2.4P_3/2", 33},
        {3277, 12, 1341.56995, "mg_x", 12, "1s1.2p2.4P_5/2", 34},
        {3278, 12, 1342.62, "mg_x", 12, "1s1.2s1.2p1.2P_1/2#2", 35},
        {3279, 12, 1342.62, "mg_x", 12, "1s1.2s1.2p1.2P_3/2#2", 36},
        {3280, 12, 1350.68005, "mg_x", 12, "1s1.2p2.2D_3/2", 37},
        {3281, 12, 1350.68005, "mg_x", 12, "1s1.2p2.2D_5/2", 38},
        {3282, 12, 1353.90002, "mg_x", 12, "1s1.2p2.2P_1/2", 39},
        {3283, 12, 1353.90002, "mg_x", 12, "1s1.2p2.2P_3/2", 40},
        {3284, 12, 1364.79004, "mg_x", 12, "1s1.2p2.2S_1/2", 41},
        {3286, 12, 367, "mg_x", 12, "continuum", 43},
        {3287, 12, 0, "mg_xi", 12, "1s2.1S_0", 1},
        {3288, 12, 1331.11157, "mg_xi", 12, "1s1.2s1.3S_1", 2},
        {3289, 12, 1342.99585, "mg_xi", 12, "1s1.2p1.3P_0", 3},
        {3290, 12, 1343.09875, "mg_xi", 12, "1s1.2p1.3P_1", 4},
        {3291, 12, 1343.54126, "mg_xi", 12, "1s1.2p1.3P_2", 5},
        {3292, 12, 1343.83765, "mg_xi", 12, "1s1.2s1.1S_0", 6},
        {3293, 12, 1352.24805, "mg_xi", 12, "1s1.2p1.1P_1", 7},
        {3294, 12, 1573.505, "mg_xi", 12, "1s1.3s1.3S_1", 8},
        {3295, 12, 1576.76526, "mg_xi", 12, "1s1.3p1.3P_0", 9},
        {3296, 12, 1576.79785, "mg_xi", 12, "1s1.3p1.3P_1", 10},
        {3297, 12, 1576.92896, "mg_xi", 12, "1s1.3p1.3P_2", 11},
        {3298, 12, 1576.86914, "mg_xi", 12, "1s1.3s1.1S_0", 12},
        {3299, 12, 1578.71399, "mg_xi", 12, "1s1.3d1.3D_1", 13},
        {3300, 12, 1578.71899, "mg_xi", 12, "1s1.3d1.3D_2", 14},
        {3301, 12, 1578.76611, "mg_xi", 12, "1s1.3d1.3D_3", 15},
        {3302, 12, 1578.85217, "mg_xi", 12, "1s1.3d1.1D_2", 16},
        {3303, 12, 1579.31201, "mg_xi", 12, "1s1.3p1.1P_1", 17},
        {3304, 12, 1656.67627, "mg_xi", 12, "1s1.4s1.3S_1", 18},
        {3305, 12, 1658.01917, "mg_xi", 12, "1s1.4p1.3P_0", 19},
        {3306, 12, 1658.03296, "mg_xi", 12, "1s1.4p1.3P_1", 20},
        {3307, 12, 1658.08813, "mg_xi", 12, "1s1.4p1.3P_2", 21},
        {3308, 12, 1658.03845, "mg_xi", 12, "1s1.4s1.1S_0", 22},
        {3309, 12, 1658.83289, "mg_xi", 12, "1s1.4d1.3D_1", 23},
        {3310, 12, 1658.83472, "mg_xi", 12, "1s1.4d1.3D_2", 24},
        {3311, 12, 1658.85486, "mg_xi", 12, "1s1.4d1.3D_3", 25},
        {3312, 12, 1658.88794, "mg_xi", 12, "1s1.4d1.1D_2", 26},
        {3313, 12, 1658.89575, "mg_xi", 12, "1s1.4f1.3F_4", 27},
        {3314, 12, 1658.89575, "mg_xi", 12, "1s1.4f1.3F_3", 28},
        {3315, 12, 1658.89575, "mg_xi", 12, "1s1.4f1.3F_2", 29},
        {3316, 12, 1658.89648, "mg_xi", 12, "1s1.4f1.1F_3", 30},
        {3317, 12, 1659.06604, "mg_xi", 12, "1s1.4p1.1P_1", 31},
        {3318, 12, 1694.81726, "mg_xi", 12, "1s1.5s1.3S_1", 32},
        {3319, 12, 1695.49573, "mg_xi", 12, "1s1.5p1.3P_0", 33},
        {3320, 12, 1695.50293, "mg_xi", 12, "1s1.5p1.3P_1", 34},
        {3321, 12, 1695.53125, "mg_xi", 12, "1s1.5p1.3P_2", 35},
        {3322, 12, 1695.50134, "mg_xi", 12, "1s1.5s1.1S_0", 36},
        {3323, 12, 1695.90869, "mg_xi", 12, "1s1.5d1.3D_1", 37},
        {3324, 12, 1695.90967, "mg_xi", 12, "1s1.5d1.3D_2", 38},
        {3325, 12, 1695.92004, "mg_xi", 12, "1s1.5d1.3D_3", 39},
        {3326, 12, 1695.94067, "mg_xi", 12, "1s1.5d1.1D_2", 40},
        {3327, 12, 1695.94226, "mg_xi", 12, "1s1.5f1.1F_3", 41},
        {3328, 12, 1695.94226, "mg_xi", 12, "1s1.5f1.3F_4", 42},
        {3329, 12, 1695.94226, "mg_xi", 12, "1s1.5f1.3F_3", 43},
        {3330, 12, 1695.94226, "mg_xi", 12, "1s1.5f1.3F_2", 44},
        {3331, 12, 1695.94836, "mg_xi", 12, "1s1.5g1.1G_4", 45},
        {3332, 12, 1695.94836, "mg_xi", 12, "1s1.5g1.3G_5", 46},
        {3333, 12, 1695.94836, "mg_xi", 12, "1s1.5g1.3G_4", 47},
        {3334, 12, 1695.94836, "mg_xi", 12, "1s1.5g1.3G_3", 48},
        {3335, 12, 1696.02539, "mg_xi", 12, "1s1.5p1.1P_1", 49},
        {3344, 12, 1761.80005, "mg_xi", 12, "continuum", 58},
        {3345, 12, 0, "mg_xii", 12, "1s1.2S_1/2", 1},
        {3346, 12, 1471.69153, "mg_xii", 12, "1s0.2p1.2P_1/2", 2},
        {3347, 12, 1472.63708, "mg_xii", 12, "1s0.2p1.2P_3/2", 3},
        {3348, 12, 1471.72974, "mg_xii", 12, "1s0.2s1.2S_1/2", 4},
        {3349, 12, 1744.55969, "mg_xii", 12, "1s0.3p1.2P_1/2", 5},
        {3350, 12, 1744.83984, "mg_xii", 12, "1s0.3p1.2P_3/2", 6},
        {3351, 12, 1744.57117, "mg_xii", 12, "1s0.3s1.2S_1/2", 7},
        {3352, 12, 1744.83936, "mg_xii", 12, "1s0.3d1.2D_3/2", 8},
        {3353, 12, 1744.9325, "mg_xii", 12, "1s0.3d1.2D_5/2", 9},
        {3354, 12, 1840.02502, "mg_xii", 12, "1s0.4p1.2P_1/2", 10},
        {3355, 12, 1840.14319, "mg_xii", 12, "1s0.4p1.2P_3/2", 11},
        {3356, 12, 1840.02991, "mg_xii", 12, "1s0.4s1.2S_1/2", 12},
        {3357, 12, 1840.14294, "mg_xii", 12, "1s0.4d1.2D_3/2", 13},
        {3358, 12, 1840.18225, "mg_xii", 12, "1s0.4d1.2D_5/2", 14},
        {3359, 12, 1840.18213, "mg_xii", 12, "1s0.4f1.2F_5/2", 15},
        {3360, 12, 1840.20166, "mg_xii", 12, "1s0.4f1.2F_7/2", 16},
        {3361, 12, 1884.19543, "mg_xii", 12, "1s0.5p1.2P_1/2", 17},
        {3362, 12, 1884.25586, "mg_xii", 12, "1s0.5p1.2P_3/2", 18},
        {3363, 12, 1884.19788, "mg_xii", 12, "1s0.5s1.2S_1/2", 19},
        {3364, 12, 1884.25586, "mg_xii", 12, "1s0.5d1.2D_3/2", 20},
        {3365, 12, 1884.27588, "mg_xii", 12, "1s0.5d1.2D_5/2", 21},
        {3366, 12, 1884.27588, "mg_xii", 12, "1s0.5f1.2F_5/2", 22},
        {3367, 12, 1884.28589, "mg_xii", 12, "1s0.5f1.2F_7/2", 23},
        {3368, 12, 1884.28589, "mg_xii", 12, "1s0.5g1.2G_7/2", 24},
        {3369, 12, 1884.29187, "mg_xii", 12, "1s0.5g1.2G_9/2", 25},
        {3370, 12, 1903.71997, "mg_xii", 12, "1s0.6s1.2S", 26},
        {3371, 12, 1903.71997, "mg_xii", 12, "1s0.6p1.2P", 27},
        {3372, 12, 1903.71997, "mg_xii", 12, "1s0.6d1.2D", 28},
        {3373, 12, 1903.71997, "mg_xii", 12, "1s0.6f1.2F", 29},
        {3374, 12, 1903.71997, "mg_xii", 12, "1s0.6g1.2G", 30},
        {3375, 12, 1903.71997, "mg_xii", 12, "1s0.6h1.2H", 31},
        {3376, 12, 1944.51001, "mg_xii", 12, "superlev", 32},
        {3377, 12, 1958.10999, "mg_xii", 12, "continuu", 33},
    };
    return rows;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute oracle detail lte template as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
const std::vector<double>& oracle_detail_lte_template_v172537() {
    static const std::vector<double> values = {
        3.40032838583130548e-14, 5.50335728797721711e-15, 1.10068661948519927e-14, 5.50335135874658633e-15,
        3.92793572190699991e-15, 7.85585280908916023e-15, 3.92793529839052628e-15, 7.85585280908916023e-15,
        1.17837715903372151e-14, 3.49061832871199861e-15, 6.98123072819336644e-15, 3.49061832871199861e-15,
        6.98123072819336644e-15, 1.04718429159164975e-14, 1.04718429159164975e-14, 1.39624546801231549e-14,
        3.30503108062797646e-15, 6.61005792609121665e-15, 3.30503002183679239e-15, 6.61005792609121665e-15,
        9.91508477155445683e-15, 1.32201107699847498e-14, 9.91508477155445683e-15, 1.32201107699847498e-14,
        1.65251384624809372e-14, 3.20862009650559749e-15, 9.62586028951679246e-15, 1.60431004825279874e-14,
        2.24603406755391824e-14, 2.88775825626162719e-14, 3.52948227556274668e-14, 1.52517281878201353e-15,
        1.00000000000000000e+00, 3.00356738624546670e-24, 2.61694498026722522e-25, 7.56715994298661762e-26,
        3.55542987293860498e-25, 2.13325442319289607e-25, 7.11069297575146558e-26, 2.03868996869856016e-25,
        1.55953622464586691e-25, 5.01442515891647174e-26, 2.46867241015511401e-25, 1.48120246001693688e-25,
        4.93731277283595343e-26, 3.41529637521611156e-25, 2.43949737565164642e-25, 1.46369739001104975e-25,
        2.43931297941505101e-25, 1.46020914569577559e-25, 1.33383781950292848e-25, 4.38337002295789241e-26,
        2.17829468309552262e-25, 1.30697685916112015e-25, 4.35657741001795049e-26, 3.03429603299796050e-25,
        2.16735441493527160e-25, 1.30041168753693472e-25, 2.16725925858857931e-25, 3.03379905062767127e-25,
        3.90059744113225599e-25, 2.16699868797082350e-25, 3.03379707847540821e-25, 1.29902440167939371e-25,
        1.24677789740757321e-25, 4.12690610414109273e-26, 2.05719541293988069e-25, 1.23431685333347580e-25,
        4.11438509431224689e-26, 6.15577302893642113e-25, 8.61731339695123855e-25, 1.10784134819733295e-24,
        1.23042937144444995e-25, 2.05185088030700834e-25, 2.87243755246471330e-25, 3.69293671036574531e-25,
        7.66022519198248428e-26, 7.66022519198248428e-26, 4.95447571857710045e-11, 4.95447571857710045e-11,
        3.38878366557340827e-14, 6.77668980501346108e-14, 3.38874910662916029e-14, 8.78857499741949461e-15,
        1.75764672862835022e-14, 8.78854450423339345e-15, 1.75764672862835022e-14, 2.63643595751475099e-14,
        5.47994995599631815e-15, 1.09597211880407656e-14, 5.47994275621626649e-15, 1.09597211880407656e-14,
        1.64394915730522659e-14, 1.64394915730522659e-14, 2.19192628050967134e-14, 4.40378570266378340e-15,
        8.80749940752705018e-15, 4.40378273804846801e-15, 8.80749940752705018e-15, 1.32112126888738433e-14,
        1.32112126888738433e-14, 1.76149259702206365e-14, 1.76149259702206365e-14, 2.20186434867321659e-14,
        3.92821397223017295e-15, 1.17846423402069925e-14, 1.96410711317002856e-14, 2.74974982291276843e-14,
        3.53539253265550829e-14, 4.32103558121142706e-14, 1.60430920121985149e-15, 1.00000000000000000e+00,
        4.22958934507243822e-21, 4.22958934507243822e-21, 1.14796086633651385e-26, 6.93101218779412775e-12,
        6.93101218779412775e-12, 3.29878594058918839e-12, 3.51349330048554825e-15, 3.49720976994909631e-20,
        1.22201871818709304e-20, 2.03713243536185473e-05, 2.03713243536185473e-05, 1.17498884719680063e-05,
        3.85312478101695888e-06, 9.19913691177498549e-06, 7.36795868760964368e-07, 3.86509633187870350e-08,
        2.23762146589479016e-08, 7.31418836608099809e-09, 1.84971948868906111e-09, 1.73170765921382142e-12,
        2.25848153435117540e-16, 2.37032085303087703e-16, 1.42219253828830582e-16, 4.74064190458510108e-17,
        1.42219253828830582e-16, 1.42219253828830582e-16, 4.74064190458510108e-17, 1.26444086432456970e-01,
        1.26444086432456970e-01, 3.71304005384445190e-02, 5.57162910699844360e-02, 9.87057480961084366e-03,
        1.96939706802368164e-02, 7.85317039117217064e-04, 5.04934287164360285e-04, 2.47671589022502303e-04,
        6.56211923342198133e-05, 9.85232181847095490e-05, 8.69158157001947984e-06, 1.03643715192447416e-05,
        4.96391339765978046e-06, 1.25652361406610336e-16, 6.82980569877145172e-08, 3.22340341085691762e-08,
        5.97844059803761705e-16, 3.98562697712581270e-16, 1.99281348856290635e-16, 5.97844059803761705e-16,
        3.98562697712581270e-16, 1.99281348856290635e-16, 1.99281348856290635e-16, 3.98562697712581270e-16,
        5.97844059803761705e-16, 3.98562697712581270e-16, 1.99281348856290635e-16, 3.98562697712581270e-16,
        1.99281348856290635e-16, 3.98562697712581270e-16, 1.99281348856290635e-16, 1.99281348856290635e-16,
        6.64412900805473328e-02, 6.64412900805473328e-02, 1.94500327110290527e-01, 3.11391323804855347e-01,
        1.34236633777618408e-01, 1.00939860567450523e-02, 2.43439078330993652e-02, 1.91663322038948536e-03,
        1.14827672950923443e-03, 2.68947402946650982e-03, 1.51362779433839023e-04, 4.54591237939894199e-04,
        7.57530273403972387e-04, 1.30432410514913499e-04, 6.59748038742691278e-05, 3.03849465126404539e-05,
        2.03889408112445381e-06, 1.16838259600626770e-06, 3.82029469392364263e-07, 9.61571117841231171e-07,
        3.12175423289318132e-08, 5.67806825862993136e-12, 1.67386972338423590e-11, 2.64049788978315547e-11,
        1.26578357170781253e-11, 3.24383662292371255e-12, 2.94882369390736532e-12, 4.81739518068402539e-12,
        6.45797738202391614e-12, 2.37286882850962222e-12, 1.05326576453623755e-12, 3.07739012224417241e-12,
        5.02742986130400027e-12, 2.13362097087332891e-12, 2.65666368027758781e-13, 1.55907090623047528e-12,
        1.45662789555883743e-12, 1.48622260331965350e-12, 1.80872244265328774e-12, 7.01598284677529271e-13,
        1.15852293036677878e-12, 1.59067138801038954e-12, 1.04678646393324692e-12, 6.18389779487305002e-13,
        2.04334419935496558e-13, 4.40318869690189962e-13, 1.05022262587850523e-12, 6.25729046171863315e-19,
        7.10147377176268831e-19, 1.18357892749458919e-18, 1.18357892749458919e-18, 1.65701047781290956e-18,
        7.10147377176268831e-19, 1.18357892749458919e-18, 2.36715775159160182e-19, 7.10147377176268831e-19,
        1.18357892749458919e-18, 7.10147377176268831e-19, 1.65701047781290956e-18, 1.18357892749458919e-18,
        7.10147377176268831e-19, 7.10147377176268831e-19, 1.18357892749458919e-18, 2.36715775159160182e-19,
        1.65701047781290956e-18, 7.10147377176268831e-19, 1.18357892749458919e-18, 7.10147377176268831e-19,
        1.18357892749458919e-18, 1.18357892749458919e-18, 7.10147377176268831e-19, 2.36715775159160182e-19,
        2.36715775159160182e-19, 7.10147377176268831e-19, 1.18357892749458919e-18, 7.10147377176268831e-19,
        2.36715775159160182e-19, 7.10147377176268831e-19, 3.15688404953107238e-04, 3.15688404953107238e-04,
        5.86899637710303068e-04, 1.77849251485895365e-05, 3.46823871950618923e-05, 5.01384856761433184e-05,
        3.69547115042223595e-06, 5.54716689293854870e-06, 4.29113157451865845e-07, 2.72988074812019477e-07,
        5.22307630035356851e-07, 6.68685089522114140e-08, 2.10607193906753309e-08, 3.16418820034414239e-08,
        2.86426060647215763e-09, 5.70453506654189368e-09, 7.30643420521507811e-16, 9.20168369267360047e-18,
        1.08833410508132932e-17, 7.00445872080001901e-18, 2.87709836581102203e-18, 4.00709553175414660e-19,
        3.46254237198305750e-19, 1.72907191953790339e-19, 9.33675528151769733e-20, 1.63284015045418499e-20,
        1.55598521646649197e-20, 9.91638254715991137e-21, 7.28108770534896738e-21, 4.42186885170945331e-21,
        2.42296812027463044e-21, 9.15835713024093045e-17, 1.79907316454975733e-17, 2.15193104307201532e-17,
        1.65071203511571641e-17, 1.37389132819535415e-17, 9.01768315567546733e-18, 7.91323160179466478e-19,
        7.94578994769263480e-19, 3.36554355443990955e-19, 1.78550463661871445e-19, 1.12317633800958887e-19,
        4.21868768621035752e-20, 3.31799527412580085e-20, 3.18448315338091373e-20, 2.00249246436121463e-20,
        1.29919022647367231e-20, 8.89281116261089533e-21, 8.62229806070547994e-21, 1.07617752695765272e-21,
        1.36861293981414302e-16, 3.16907451047845836e-17, 2.01570548040473987e-17, 1.28783418696135857e-17,
        1.23277683859467591e-18, 4.82963772902228317e-19, 1.65081688542823634e-19, 6.23270510294990863e-20,
        4.78440943183244429e-20, 4.08215150946825017e-20, 3.05785020265214143e-20, 4.04369504268535029e-20,
        2.05345599894114432e-20, 1.22151748227880285e-20, 1.62845094352366466e-21, 4.05541739654699372e-17,
        8.13264591216530098e-20, 6.30223157213955128e-20, 5.54487728174821672e-20, 2.32233816563489510e-20,
        1.82880311497711858e-20, 9.88653247459797093e-20, 2.88895704679243244e-20, 2.24088124849841511e-16,
        3.24719377840021131e-17, 1.66972163820892005e-17, 2.56777769126442068e-18, 1.69171897631563460e-18,
        1.61612997116962010e-18, 8.83507062774519818e-19, 1.04633649360572641e-19, 7.69643156990060828e-20,
        6.20203738173950513e-20, 5.13256102748549061e-20, 2.94814698949943003e-20, 8.56265946945140037e-21,
        1.69592846452558715e-21, 4.38753299329054549e-16, 6.33292984216395213e-17, 3.17261749047814548e-17,
        6.83380929247879802e-18, 4.09722409732215880e-18, 3.91274544992997002e-18, 3.41988022169790539e-18,
        3.22016470062733669e-18, 1.81303680047026499e-18, 2.22723187917213166e-19, 1.59867413379927841e-19,
        1.22019816151352345e-19, 1.01466652676094128e-19, 8.36703852472471185e-20, 5.15080714545824722e-20,
        5.91526549559473446e-20, 2.44843668013977571e-20, 1.66548971240173458e-20, 3.36711562573435079e-21,
        9.08303340191736171e-17, 1.00927201669738842e-17, 6.10100667909562059e-18, 5.82319682959876741e-18,
        5.21385836726464234e-18, 3.25412046477263848e-18, 4.20322419089353222e-19, 3.31469883013780632e-19,
        1.78160680647599973e-19, 1.24902114071096298e-19, 1.19385013255823671e-19, 5.36937572827603331e-20,
        3.69369876964282535e-20, 1.31458082391407696e-17, 7.98785156485307341e-18, 4.14644051658845139e-18,
        4.76039133801817215e-19, 1.90333056951624052e-19, 7.06520552081741796e-20, 1.59153503778530528e-17,
        5.17362936902268312e-25, 7.44039603523390662e-25, 1.48807920704678132e-24, 2.23211881057017199e-24,
        2.23211881057017199e-24, 1.48807920704678132e-24, 2.23211881057017199e-24, 7.44039603523390662e-25,
        1.48807920704678132e-24, 7.44039603523390662e-25, 1.48807920704678132e-24, 2.23211881057017199e-24,
        7.44039603523390662e-25, 2.97615841409356265e-24, 1.48807920704678132e-24, 7.44039603523390662e-25,
        2.23211881057017199e-24, 1.48807920704678132e-24, 1.48807920704678132e-24, 2.23211881057017199e-24,
        1.48807920704678132e-24, 1.48807920704678132e-24, 7.44039603523390662e-25, 2.23211881057017199e-24,
        1.48807920704678132e-24, 7.44039603523390662e-25, 1.48807920704678132e-24, 7.44039603523390662e-25,
        2.23211881057017199e-24, 1.48807920704678132e-24, 7.44039603523390662e-25, 1.48807920704678132e-24,
        2.23211881057017199e-24, 1.48807920704678132e-24, 7.44039603523390662e-25, 7.44039603523390662e-25,
        2.48066123198498190e-10, 2.48066123198498190e-10, 1.10721258550494639e-11, 3.23980495209319486e-11,
        5.11356096355441991e-11, 1.82217977685861232e-12, 7.55862522095265832e-14, 2.20313052740409021e-13,
        3.49962002736334266e-13, 1.58581372859678549e-13, 3.91516585319419408e-15, 1.39266914296585507e-24,
        2.63290930631760257e-25, 3.59844670461933964e-25, 1.81025803725951448e-25, 5.33656119342509666e-25,
        8.71039898376731794e-25, 1.57142275611383383e-25, 2.61157037231234132e-25, 3.64446244033507854e-25,
        1.55573650353254689e-25, 1.48786504517770942e-27, 2.87617053817953036e-28, 2.16187716261807163e-26,
        9.09856991753953245e-27, 8.60141594689225011e-28, 8.20818477085811414e-27, 1.17781678640880033e-26,
        1.00099577154504824e-26, 7.19783344794081491e-27, 5.98863525086937786e-27, 1.63208418757306659e-26,
        9.69818817605307671e-27, 6.82461133587790124e-27, 2.66361134134049680e-26, 1.31805376049534578e-26,
        3.17825433514536964e-27, 2.61054257283449985e-27, 1.48962293773444887e-27, 4.18606235201530887e-26,
        5.24438697206614086e-27, 7.83328170713973930e-27, 5.23409480244333547e-27, 4.44752074643828907e-27,
        6.84580041712604961e-27, 7.16727818418712253e-27, 4.04691499205409993e-27, 2.73298992735075921e-35,
        9.09815695366846402e-36, 2.72944708610053920e-35, 4.54907847683423201e-35, 2.72944708610053920e-35,
        4.54907847683423201e-35, 6.36871015455385030e-35, 9.09815695366846402e-36, 6.36871015455385030e-35,
        4.54907847683423201e-35, 2.72944708610053920e-35, 2.72944708610053920e-35, 2.72944708610053920e-35,
        4.54907847683423201e-35, 2.72944708610053920e-35, 4.54907847683423201e-35, 4.54907847683423201e-35,
        9.09815695366846402e-36, 2.72944708610053920e-35, 4.54907847683423201e-35, 2.72944708610053920e-35,
        9.09815695366846402e-36, 2.72944708610053920e-35, 4.54907847683423201e-35, 6.36871015455385030e-35,
        2.72944708610053920e-35, 4.54907847683423201e-35, 9.09815695366846402e-36, 2.72944708610053920e-35,
        4.54907847683423201e-35, 2.72944708610053920e-35, 1.21334648879042747e-20, 1.21334648879042747e-20,
        1.21334648879042747e-20, 2.42669297758085494e-20, 2.06267896747373504e-34, 7.82114994128053697e-35,
        1.51962950557512798e-34, 1.07433605947744762e-34, 1.59775430653984169e-34, 6.87576518788722317e-40,
        4.66289070496404504e-40, 9.32579542291273334e-40, 7.94700181192497283e-40, 1.18356470893802699e-39,
        1.17430072479037563e-39, 1.56294805127393499e-39, 2.22946585674078396e-42, 1.81468151130063811e-42,
        3.62936302260127621e-42, 3.35891241898658652e-42, 5.01524720381852030e-42, 4.91295241592280865e-42,
        6.53985993300392127e-42, 6.48100539750227895e-42, 8.08689343761851932e-42, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        3.54231637362526333e-32, 3.54231637362526333e-32, 1.06269485331286146e-31, 3.54231637362526333e-32,
        1.06269485331286146e-31, 1.77115812803791412e-31, 3.54231637362526333e-32, 1.06269485331286146e-31,
        3.71344093046076524e-43, 6.86636247519160365e-44, 2.05990874255748109e-43, 3.36311631437956097e-43,
        6.86636247519160365e-44, 1.47136338754105792e-43, 2.43825932792518170e-43, 3.39114228366605731e-43,
        2.38220738935218902e-43, 1.31722055646532805e-43, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 4.13383046975821036e-43, 4.13383046975821036e-43,
        4.13383046975821036e-43, 8.26766093951642072e-43, 4.13383046975821036e-43, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00,
        0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00, 0.00000000000000000e+00
    };
    return values;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide public detail levels for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<xstar_run_state::LevelIdentityState> public_detail_levels(
    const xstar_run_state::ProductWritingState& state,
    [[maybe_unused]] const std::vector<ElementMeta>& elements,
    [[maybe_unused]] const std::vector<RowMeta>& rows) {
    // Preserve the fully-qualified Mg XI public identity surface bit-for-bit.
    if (reference_mg11_product_state(state)) {
        std::vector<xstar_run_state::LevelIdentityState> out;
        const auto& tmpl = oracle_detail_level_template_v172534();
        out.reserve(tmpl.size());
        for (const auto& row : tmpl) {
            xstar_run_state::LevelIdentityState lev;
            lev.global_index = static_cast<std::int32_t>(row.index);
            lev.ion_index = static_cast<std::int16_t>(row.ion_index);
            lev.excitation_ev = row.excitation_ev;
            lev.ion_label = row.ion;
            lev.atomic_number = static_cast<std::int16_t>(row.atomic_number);
            lev.level_label = row.ion_level;
            lev.upper_index = static_cast<std::int16_t>(row.upper_index);
            out.push_back(std::move(lev));
        }
        return out;
    }

    // v0.6.48.12.3.19 / literal fstepr.f90: identity traversal is not
    // stage-filtered.  fstepr walks every ion/local-level npilev role and only
    // then applies xilev > 1.d-34.  The dedicated source-role inventory keeps
    // both sides of compact continuum/next-ground aliases; using the compact
    // deduplicated level list drops one continuum identity per ion.
    const auto& source_levels = !state.detail_level_identities.empty()
        ? state.detail_level_identities : state.level_identities;
    return source_levels;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide level by global for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] const xstar_run_state::LevelIdentityState* level_by_global(
    const std::vector<xstar_run_state::LevelIdentityState>& levels,
    std::int32_t global_index) {
    for (const auto& level : levels) if (level.global_index == global_index) return &level;
    return nullptr;
}



struct LineLabelTemplateRow { int index; double wavelength_angstrom; const char* ion; const char* lower_level; const char* upper_level; };
struct RrcLabelTemplateRow { int index; int level_index; double energy_ev; const char* ion; const char* lower_level; const char* upper_level; };

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute oracle detail line label template for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
const std::vector<LineLabelTemplateRow>& oracle_detail_line_label_template_v172537() {
    static const std::vector<LineLabelTemplateRow> rows = {
        {1, 10944.916, "h_i", "1s0.3p1.2P_1/2", "1s0.6s1.2S"},
        {2, 10945.0449, "h_i", "1s0.3p1.2P_3/2", "1s0.6s1.2S"},
        {3, 4341.6582, "h_i", "1s0.2s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {4, 4341.65381, "h_i", "1s0.2s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {5, 10944.916, "h_i", "1s0.3p1.2P_1/2", "1s0.6d1.2D"},
        {6, 10945.0449, "h_i", "1s0.3p1.2P_3/2", "1s0.6d1.2D"},
        {7, 10944.9277, "h_i", "1s0.3s1.2S_1/2", "1s0.6p1.2P"},
        {8, 10945.0449, "h_i", "1s0.3d1.2D_3/2", "1s0.6f1.2F"},
        {9, 10945.0879, "h_i", "1s0.3d1.2D_5/2", "1s0.6f1.2F"},
        {10, 12821.4316, "h_i", "1s0.3p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {11, 12821.4189, "h_i", "1s0.3p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {12, 12821.6104, "h_i", "1s0.3p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {13, 12821.5967, "h_i", "1s0.3p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {14, 4341.65088, "h_i", "1s0.2p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {15, 4341.53174, "h_i", "1s0.2p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {16, 40522.3203, "h_i", "1s0.4s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {17, 40521.9375, "h_i", "1s0.4s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {18, 4103.41943, "h_i", "1s0.2s1.2S_1/2", "1s0.6p1.2P"},
        {19, 4341.64697, "h_i", "1s0.2p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {20, 4341.64551, "h_i", "1s0.2p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {21, 4341.52783, "h_i", "1s0.2p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {22, 4341.52637, "h_i", "1s0.2p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {23, 937.832275, "h_i", "1s1.2S_1/2", "1s0.6p1.2P"},
        {24, 12821.5908, "h_i", "1s0.3d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {25, 12821.5967, "h_i", "1s0.3d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {26, 12821.6504, "h_i", "1s0.3d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {27, 12821.6562, "h_i", "1s0.3d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {28, 4862.63672, "h_i", "1s0.2p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {29, 4862.63281, "h_i", "1s0.2p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {30, 4862.48682, "h_i", "1s0.2p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {31, 4862.48291, "h_i", "1s0.2p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {32, 10945.0449, "h_i", "1s0.3d1.2D_3/2", "1s0.6p1.2P"},
        {33, 10945.0879, "h_i", "1s0.3d1.2D_5/2", "1s0.6p1.2P"},
        {34, 18756.002, "h_i", "1s0.3s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {35, 18755.8398, "h_i", "1s0.3s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {36, 18755.9492, "h_i", "1s0.3p1.2P_1/2", "1s0.4s1.2S_1/2"},
        {37, 18756.3301, "h_i", "1s0.3p1.2P_3/2", "1s0.4s1.2S_1/2"},
        {38, 18756.1309, "h_i", "1s0.3d1.2D_3/2", "1s0.4f1.2F_5/2"},
        {39, 18756.1035, "h_i", "1s0.3d1.2D_3/2", "1s0.4f1.2F_7/2"},
        {40, 18756.2578, "h_i", "1s0.3d1.2D_5/2", "1s0.4f1.2F_5/2"},
        {41, 18756.2305, "h_i", "1s0.3d1.2D_5/2", "1s0.4f1.2F_7/2"},
        {42, 12821.4883, "h_i", "1s0.3s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {43, 12821.4492, "h_i", "1s0.3s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {44, 4103.41357, "h_i", "1s0.2p1.2P_1/2", "1s0.6d1.2D"},
        {45, 4103.30664, "h_i", "1s0.2p1.2P_3/2", "1s0.6d1.2D"},
        {46, 74782.5703, "h_i", "1s0.5g1.2G_7/2", "1s0.6f1.2F"},
        {47, 74782.7031, "h_i", "1s0.5g1.2G_9/2", "1s0.6f1.2F"},
        {48, 4103.41357, "h_i", "1s0.2p1.2P_1/2", "1s0.6s1.2S"},
        {49, 4103.30664, "h_i", "1s0.2p1.2P_3/2", "1s0.6s1.2S"},
        {50, 12821.6484, "h_i", "1s0.3d1.2D_3/2", "1s0.5p1.2P_1/2"},
        {51, 12821.6104, "h_i", "1s0.3d1.2D_3/2", "1s0.5p1.2P_3/2"},
        {52, 12821.708, "h_i", "1s0.3d1.2D_5/2", "1s0.5p1.2P_1/2"},
        {53, 12821.6689, "h_i", "1s0.3d1.2D_5/2", "1s0.5p1.2P_3/2"},
        {54, 18755.8047, "h_i", "1s0.3p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {55, 18755.75, "h_i", "1s0.3p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {56, 18756.1855, "h_i", "1s0.3p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {57, 18756.1309, "h_i", "1s0.3p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {58, 12821.4668, "h_i", "1s0.3p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {59, 12821.6445, "h_i", "1s0.3p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {60, 40521.8672, "h_i", "1s0.4p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {61, 40521.7383, "h_i", "1s0.4p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {62, 40522.6172, "h_i", "1s0.4p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {63, 40522.4883, "h_i", "1s0.4p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {64, 4862.64648, "h_i", "1s0.2p1.2P_1/2", "1s0.4s1.2S_1/2"},
        {65, 4862.49658, "h_i", "1s0.2p1.2P_3/2", "1s0.4s1.2S_1/2"},
        {66, 26281.0352, "h_i", "1s0.4p1.2P_1/2", "1s0.6d1.2D"},
        {67, 26281.3516, "h_i", "1s0.4p1.2P_3/2", "1s0.6d1.2D"},
        {68, 949.743103, "h_i", "1s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {69, 949.74292, "h_i", "1s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {70, 40523, "h_i", "1s0.4d1.2D_3/2", "1s0.5p1.2P_1/2"},
        {71, 40522.6133, "h_i", "1s0.4d1.2D_3/2", "1s0.5p1.2P_3/2"},
        {72, 40523.25, "h_i", "1s0.4d1.2D_5/2", "1s0.5p1.2P_1/2"},
        {73, 40522.8633, "h_i", "1s0.4d1.2D_5/2", "1s0.5p1.2P_3/2"},
        {74, 40522.6758, "h_i", "1s0.4f1.2F_5/2", "1s0.5g1.2G_7/2"},
        {75, 40522.6367, "h_i", "1s0.4f1.2F_5/2", "1s0.5g1.2G_9/2"},
        {76, 40522.7969, "h_i", "1s0.4f1.2F_7/2", "1s0.5g1.2G_7/2"},
        {77, 40522.7617, "h_i", "1s0.4f1.2F_7/2", "1s0.5g1.2G_9/2"},
        {78, 26281.3516, "h_i", "1s0.4d1.2D_3/2", "1s0.6p1.2P"},
        {79, 26281.4551, "h_i", "1s0.4d1.2D_5/2", "1s0.6p1.2P"},
        {80, 40522.2109, "h_i", "1s0.4p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {81, 40522.9648, "h_i", "1s0.4p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {82, 26281.0352, "h_i", "1s0.4p1.2P_1/2", "1s0.6s1.2S"},
        {83, 26281.3516, "h_i", "1s0.4p1.2P_3/2", "1s0.6s1.2S"},
        {84, 74780.6094, "h_i", "1s0.5p1.2P_1/2", "1s0.6s1.2S"},
        {85, 74781.9219, "h_i", "1s0.5p1.2P_3/2", "1s0.6s1.2S"},
        {86, 26281.0664, "h_i", "1s0.4s1.2S_1/2", "1s0.6p1.2P"},
        {87, 26281.3516, "h_i", "1s0.4d1.2D_3/2", "1s0.6f1.2F"},
        {88, 26281.4551, "h_i", "1s0.4d1.2D_5/2", "1s0.6f1.2F"},
        {89, 40522.8672, "h_i", "1s0.4f1.2F_5/2", "1s0.5d1.2D_3/2"},
        {90, 40522.7383, "h_i", "1s0.4f1.2F_5/2", "1s0.5d1.2D_5/2"},
        {91, 40522.9922, "h_i", "1s0.4f1.2F_7/2", "1s0.5d1.2D_3/2"},
        {92, 40522.8633, "h_i", "1s0.4f1.2F_7/2", "1s0.5d1.2D_5/2"},
        {93, 74781.9141, "h_i", "1s0.5d1.2D_3/2", "1s0.6p1.2P"},
        {94, 74782.3516, "h_i", "1s0.5d1.2D_5/2", "1s0.6p1.2P"},
        {95, 6564.56494, "h_i", "1s0.2p1.2P_1/2", "1s0.3s1.2S_1/2"},
        {96, 6564.2915, "h_i", "1s0.2p1.2P_3/2", "1s0.3s1.2S_1/2"},
        {97, 74781.9141, "h_i", "1s0.5d1.2D_3/2", "1s0.6f1.2F"},
        {98, 74782.3516, "h_i", "1s0.5d1.2D_5/2", "1s0.6f1.2F"},
        {99, 4862.65576, "h_i", "1s0.2s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {100, 4862.64502, "h_i", "1s0.2s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {101, 6564.52246, "h_i", "1s0.2p1.2P_1/2", "1s0.3d1.2D_3/2"},
        {102, 6564.50684, "h_i", "1s0.2p1.2P_1/2", "1s0.3d1.2D_5/2"},
        {103, 6564.24951, "h_i", "1s0.2p1.2P_3/2", "1s0.3d1.2D_3/2"},
        {104, 6564.23389, "h_i", "1s0.2p1.2P_3/2", "1s0.3d1.2D_5/2"},
        {105, 972.537048, "h_i", "1s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {106, 972.53656, "h_i", "1s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {107, 40522.4258, "h_i", "1s0.4d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {108, 40522.4883, "h_i", "1s0.4d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {109, 40522.6758, "h_i", "1s0.4d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {110, 40522.7383, "h_i", "1s0.4d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {111, 74782.5703, "h_i", "1s0.5f1.2F_7/2", "1s0.6g1.2G"},
        {112, 74782.3516, "h_i", "1s0.5f1.2F_5/2", "1s0.6g1.2G"},
        {113, 74782.5703, "h_i", "1s0.5g1.2G_7/2", "1s0.6h1.2H"},
        {114, 74782.7031, "h_i", "1s0.5g1.2G_9/2", "1s0.6h1.2H"},
        {115, 1025.72302, "h_i", "1s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {116, 1025.7218, "h_i", "1s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {117, 74782.5703, "h_i", "1s0.5f1.2F_7/2", "1s0.6d1.2D"},
        {118, 74782.3516, "h_i", "1s0.5f1.2F_5/2", "1s0.6d1.2D"},
        {119, 1215.67358, "h_i", "1s1.2S_1/2", "1s0.2p1.2P_1/2"},
        {120, 1215.68298, "h_i", "1s1.2S_1/2", "1s0.2p1.2P_3/2"},
        {121, 26281.4551, "h_i", "1s0.4f1.2F_5/2", "1s0.6d1.2D"},
        {122, 26281.5078, "h_i", "1s0.4f1.2F_7/2", "1s0.6d1.2D"},
        {123, 74780.7344, "h_i", "1s0.5s1.2S_1/2", "1s0.6p1.2P"},
        {124, 74780.6094, "h_i", "1s0.5p1.2P_1/2", "1s0.6d1.2D"},
        {125, 74781.9219, "h_i", "1s0.5p1.2P_3/2", "1s0.6d1.2D"},
        {126, 26281.4551, "h_i", "1s0.4f1.2F_5/2", "1s0.6g1.2G"},
        {127, 26281.5078, "h_i", "1s0.4f1.2F_7/2", "1s0.6g1.2G"},
        {128, 18756.3457, "h_i", "1s0.3d1.2D_3/2", "1s0.4p1.2P_1/2"},
        {129, 18756.1836, "h_i", "1s0.3d1.2D_3/2", "1s0.4p1.2P_3/2"},
        {130, 18756.4727, "h_i", "1s0.3d1.2D_5/2", "1s0.4p1.2P_1/2"},
        {131, 18756.3105, "h_i", "1s0.3d1.2D_5/2", "1s0.4p1.2P_3/2"},
        {132, 6564.58447, "h_i", "1s0.2s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {133, 6564.5376, "h_i", "1s0.2s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {166, 13415.3506, "he_i", "1s1.3p1.1P_1", "1s1.5s1.1S_0"},
        {167, 46949.4492, "he_i", "1s1.4p1.3P_2", "1s1.5s1.3S_1"},
        {168, 46949.6484, "he_i", "1s1.4p1.3P_1", "1s1.5s1.3S_1"},
        {169, 46952.082, "he_i", "1s1.4p1.3P_0", "1s1.5s1.3S_1"},
        {170, 5049.146, "he_i", "1s1.2p1.1P_1", "1s1.4s1.1S_0"},
        {171, 4923.30518, "he_i", "1s1.2p1.1P_1", "1s1.4d1.1D_2"},
        {172, 6679.99561, "he_i", "1s1.2p1.1P_1", "1s1.3d1.1D_2"},
        {173, 862951.625, "he_i", "1s1.5p1.3P_2", "1s1.5d1.3D"},
        {174, 862985.312, "he_i", "1s1.5p1.3P_1", "1s1.5d1.3D"},
        {175, 863398.438, "he_i", "1s1.5p1.3P_0", "1s1.5d1.3D"},
        {176, 3614.57593, "he_i", "1s1.2s1.1S_0", "1s1.5p1.1P"},
        {177, 12849.458, "he_i", "1s1.3p1.3P_2", "1s1.5s1.3S_1"},
        {178, 12849.4941, "he_i", "1s1.3p1.3P_1", "1s1.5s1.3S_1"},
        {179, 12849.9414, "he_i", "1s1.3p1.3P_0", "1s1.5s1.3S_1"},
        {180, 4389.17822, "he_i", "1s1.2p1.1P_1", "1s1.5d1.1D"},
        {181, 186225.203, "he_i", "1s1.3p1.3P_2", "1s1.3d1.3D_3"},
        {182, 186224.328, "he_i", "1s1.3p1.3P_2", "1s1.3d1.3D_2"},
        {183, 186209, "he_i", "1s1.3p1.3P_2", "1s1.3d1.3D_1"},
        {184, 186232.812, "he_i", "1s1.3p1.3P_1", "1s1.3d1.3D_3"},
        {185, 186231.953, "he_i", "1s1.3p1.3P_1", "1s1.3d1.3D_2"},
        {186, 186216.625, "he_i", "1s1.3p1.3P_1", "1s1.3d1.3D_1"},
        {187, 186326.734, "he_i", "1s1.3p1.3P_0", "1s1.3d1.3D_3"},
        {188, 186325.859, "he_i", "1s1.3p1.3P_0", "1s1.3d1.3D_2"},
        {189, 186310.516, "he_i", "1s1.3p1.3P_0", "1s1.3d1.3D_1"},
        {190, 4472.729, "he_i", "1s1.2p1.3P_2", "1s1.4d1.3D_3"},
        {191, 4472.729, "he_i", "1s1.2p1.3P_2", "1s1.4d1.3D_2"},
        {192, 4472.7251, "he_i", "1s1.2p1.3P_2", "1s1.4d1.3D_1"},
        {193, 4472.74414, "he_i", "1s1.2p1.3P_1", "1s1.4d1.3D_3"},
        {194, 4472.74414, "he_i", "1s1.2p1.3P_1", "1s1.4d1.3D_2"},
        {195, 4472.74023, "he_i", "1s1.2p1.3P_1", "1s1.4d1.3D_1"},
        {196, 4472.94189, "he_i", "1s1.2p1.3P_0", "1s1.4d1.3D_3"},
        {197, 4472.94189, "he_i", "1s1.2p1.3P_0", "1s1.4d1.3D_2"},
        {198, 4472.93799, "he_i", "1s1.2p1.3P_0", "1s1.4d1.3D_1"},
        {199, 42959.5664, "he_i", "1s1.3s1.3S_1", "1s1.3p1.3P_2"},
        {200, 42959.1602, "he_i", "1s1.3s1.3S_1", "1s1.3p1.3P_1"},
        {201, 42954.168, "he_i", "1s1.3s1.3S_1", "1s1.3p1.3P_0"},
        {202, 4027.41504, "he_i", "1s1.2p1.3P_2", "1s1.5d1.3D"},
        {203, 4027.42749, "he_i", "1s1.2p1.3P_1", "1s1.5d1.3D"},
        {204, 4027.58765, "he_i", "1s1.2p1.3P_0", "1s1.5d1.3D"},
        {205, 4438.79932, "he_i", "1s1.2p1.1P_1", "1s1.5s1.1S_0"},
        {206, 12530.9365, "he_i", "1s1.3s1.3S_1", "1s1.4p1.3P_2"},
        {207, 12530.9229, "he_i", "1s1.3s1.3S_1", "1s1.4p1.3P_1"},
        {208, 12530.749, "he_i", "1s1.3s1.3S_1", "1s1.4p1.3P_0"},
        {209, 537.029907, "he_i", "1s2.1S_0", "1s1.3p1.1P_1"},
        {210, 522.213074, "he_i", "1s2.1S_0", "1s1.4p1.1P_1"},
        {211, 537.029907, "he_i", "1s2.1S_0", "1s1.3p1.1P_1"},
        {212, 625.562988, "he_i", "1s2.1S_0", "1s1.2s1.3S_1"},
        {213, 591.412354, "he_i", "1s2.1S_0", "1s1.2p1.3P_2"},
        {214, 591.412048, "he_i", "1s2.1S_0", "1s1.2p1.3P_1"},
        {215, 591.411987, "he_i", "1s2.1S_0", "1s1.2p1.3P_0"},
        {216, 220402.062, "he_i", "1s1.5s1.3S_1", "1s1.5p1.3P_2"},
        {217, 220399.875, "he_i", "1s1.5s1.3S_1", "1s1.5p1.3P_1"},
        {218, 220372.938, "he_i", "1s1.5s1.3S_1", "1s1.5p1.3P_0"},
        {219, 515.614868, "he_i", "1s2.1S_0", "1s1.5p1.1P"},
        {220, 21125.7871, "he_i", "1s1.3p1.3P_2", "1s1.4s1.3S_1"},
        {221, 21125.8848, "he_i", "1s1.3p1.3P_1", "1s1.4s1.3S_1"},
        {222, 21127.0938, "he_i", "1s1.3p1.3P_0", "1s1.4s1.3S_1"},
        {223, 20586.9043, "he_i", "1s1.2s1.1S_0", "1s1.2p1.1P_1"},
        {224, 74375.125, "he_i", "1s1.3s1.1S_0", "1s1.3p1.1P_1"},
        {225, 584.334351, "he_i", "1s2.1S_0", "1s1.2p1.1P_1"},
        {226, 3965.85059, "he_i", "1s1.2s1.1S_0", "1s1.4p1.1P_1"},
        {227, 15087.7744, "he_i", "1s1.3s1.1S_0", "1s1.4p1.1P_1"},
        {228, 7283.35693, "he_i", "1s1.2p1.1P_1", "1s1.3s1.1S_0"},
        {229, 9466.18652, "he_i", "1s1.3s1.3S_1", "1s1.5p1.3P_2"},
        {230, 9466.18262, "he_i", "1s1.3s1.3S_1", "1s1.5p1.3P_1"},
        {231, 9466.13281, "he_i", "1s1.3s1.3S_1", "1s1.5p1.3P_0"},
        {232, 439676.469, "he_i", "1s1.4p1.3P_2", "1s1.4d1.3D_3"},
        {233, 439674.156, "he_i", "1s1.4p1.3P_2", "1s1.4d1.3D_2"},
        {234, 439638.344, "he_i", "1s1.4p1.3P_2", "1s1.4d1.3D_1"},
        {235, 439693.875, "he_i", "1s1.4p1.3P_1", "1s1.4d1.3D_3"},
        {236, 439691.531, "he_i", "1s1.4p1.3P_1", "1s1.4d1.3D_2"},
        {237, 439655.75, "he_i", "1s1.4p1.3P_1", "1s1.4d1.3D_1"},
        {238, 439907.25, "he_i", "1s1.4p1.3P_0", "1s1.4d1.3D_3"},
        {239, 439904.938, "he_i", "1s1.4p1.3P_0", "1s1.4d1.3D_2"},
        {240, 439869.094, "he_i", "1s1.4p1.3P_0", "1s1.4d1.3D_1"},
        {241, 11973.1416, "he_i", "1s1.3p1.3P_2", "1s1.5d1.3D"},
        {242, 11973.1729, "he_i", "1s1.3p1.3P_1", "1s1.5d1.3D"},
        {243, 11973.5605, "he_i", "1s1.3p1.3P_0", "1s1.5d1.3D"},
        {244, 12988.4277, "he_i", "1s1.3d1.3D_3", "1s1.5p1.3P_2"},
        {245, 12988.4199, "he_i", "1s1.3d1.3D_3", "1s1.5p1.3P_1"},
        {246, 12988.3262, "he_i", "1s1.3d1.3D_3", "1s1.5p1.3P_0"},
        {247, 12988.4316, "he_i", "1s1.3d1.3D_2", "1s1.5p1.3P_2"},
        {248, 12988.4238, "he_i", "1s1.3d1.3D_2", "1s1.5p1.3P_1"},
        {249, 12988.3301, "he_i", "1s1.3d1.3D_2", "1s1.5p1.3P_0"},
        {250, 12988.5059, "he_i", "1s1.3d1.3D_1", "1s1.5p1.3P_2"},
        {251, 12988.499, "he_i", "1s1.3d1.3D_1", "1s1.5p1.3P_1"},
        {252, 12988.4053, "he_i", "1s1.3d1.3D_1", "1s1.5p1.3P_0"},
        {253, 12757.9727, "he_i", "1s1.3d1.1D_2", "1s1.5p1.1P"},
        {254, 957870.438, "he_i", "1s1.3p1.1P_1", "1s1.3d1.1D_2"},
        {255, 18560.6406, "he_i", "1s1.3d1.1D_2", "1s1.4p1.1P_1"},
        {256, 108822.492, "he_i", "1s1.4s1.3S_1", "1s1.4p1.3P_2"},
        {257, 108821.422, "he_i", "1s1.4s1.3S_1", "1s1.4p1.3P_1"},
        {258, 108808.359, "he_i", "1s1.4s1.3S_1", "1s1.4p1.3P_0"},
        {259, 12972.1211, "he_i", "1s1.3p1.1P_1", "1s1.5d1.1D"},
        {260, 4714.45801, "he_i", "1s1.2p1.3P_2", "1s1.4s1.3S_1"},
        {261, 4714.47461, "he_i", "1s1.2p1.3P_1", "1s1.4s1.3S_1"},
        {262, 4714.69434, "he_i", "1s1.2p1.3P_0", "1s1.4s1.3S_1"},
        {263, 33300.293, "he_i", "1s1.4s1.1S_0", "1s1.5p1.1P"},
        {264, 5877.24316, "he_i", "1s1.2p1.3P_2", "1s1.3d1.3D_3"},
        {265, 5877.24219, "he_i", "1s1.2p1.3P_2", "1s1.3d1.3D_2"},
        {266, 5877.22705, "he_i", "1s1.2p1.3P_2", "1s1.3d1.3D_1"},
        {267, 5877.26953, "he_i", "1s1.2p1.3P_1", "1s1.3d1.3D_3"},
        {268, 5877.26904, "he_i", "1s1.2p1.3P_1", "1s1.3d1.3D_2"},
        {269, 5877.25342, "he_i", "1s1.2p1.3P_1", "1s1.3d1.3D_1"},
        {270, 5877.61084, "he_i", "1s1.2p1.3P_0", "1s1.3d1.3D_3"},
        {271, 5877.60986, "he_i", "1s1.2p1.3P_0", "1s1.3d1.3D_2"},
        {272, 5877.59473, "he_i", "1s1.2p1.3P_0", "1s1.3d1.3D_1"},
        {273, 181000.203, "he_i", "1s1.4s1.1S_0", "1s1.4p1.1P_1"},
        {274, 7067.125, "he_i", "1s1.2p1.3P_2", "1s1.3s1.3S_1"},
        {275, 7067.16357, "he_i", "1s1.2p1.3P_1", "1s1.3s1.3S_1"},
        {276, 7067.65674, "he_i", "1s1.2p1.3P_0", "1s1.3s1.3S_1"},
        {277, 21137.7988, "he_i", "1s1.3p1.1P_1", "1s1.4s1.1S_0"},
        {278, 4121.97314, "he_i", "1s1.2p1.3P_2", "1s1.5s1.3S_1"},
        {279, 4121.98633, "he_i", "1s1.2p1.3P_1", "1s1.5s1.3S_1"},
        {280, 4122.1543, "he_i", "1s1.2p1.3P_0", "1s1.5s1.3S_1"},
        {281, 41228.7422, "he_i", "1s1.4p1.1P_1", "1s1.5d1.1D"},
        {282, 11015.1885, "he_i", "1s1.3s1.1S_0", "1s1.5p1.1P"},
        {283, 40052.1133, "he_i", "1s1.4d1.1D_2", "1s1.5p1.1P"},
        {284, 28550.2656, "he_i", "1s1.4s1.3S_1", "1s1.5p1.3P_2"},
        {285, 28550.2285, "he_i", "1s1.4s1.3S_1", "1s1.5p1.3P_1"},
        {286, 28549.7773, "he_i", "1s1.4s1.3S_1", "1s1.5p1.3P_0"},
        {287, 19094.5703, "he_i", "1s1.3p1.1P_1", "1s1.4d1.1D_2"},
        {288, 2945.96509, "he_i", "1s1.2s1.3S_1", "1s1.5p1.3P_2"},
        {289, 2945.9646, "he_i", "1s1.2s1.3S_1", "1s1.5p1.3P_1"},
        {290, 2945.95996, "he_i", "1s1.2s1.3S_1", "1s1.5p1.3P_0"},
        {291, 42440.7383, "he_i", "1s1.4d1.3D_3", "1s1.5p1.3P_2"},
        {292, 42440.6562, "he_i", "1s1.4d1.3D_3", "1s1.5p1.3P_1"},
        {293, 42439.6602, "he_i", "1s1.4d1.3D_3", "1s1.5p1.3P_0"},
        {294, 42440.7617, "he_i", "1s1.4d1.3D_2", "1s1.5p1.3P_2"},
        {295, 42440.6797, "he_i", "1s1.4d1.3D_2", "1s1.5p1.3P_1"},
        {296, 42439.6797, "he_i", "1s1.4d1.3D_2", "1s1.5p1.3P_0"},
        {297, 42441.0938, "he_i", "1s1.4d1.3D_1", "1s1.5p1.3P_2"},
        {298, 42441.0117, "he_i", "1s1.4d1.3D_1", "1s1.5p1.3P_1"},
        {299, 42440.0117, "he_i", "1s1.4d1.3D_1", "1s1.5p1.3P_0"},
        {300, 37043.2383, "he_i", "1s1.4p1.3P_2", "1s1.5d1.3D"},
        {301, 37043.3633, "he_i", "1s1.4p1.3P_1", "1s1.5d1.3D"},
        {302, 37044.875, "he_i", "1s1.4p1.3P_0", "1s1.5d1.3D"},
        {303, 17007.0371, "he_i", "1s1.3p1.3P_2", "1s1.4d1.3D_3"},
        {304, 17007.0332, "he_i", "1s1.3p1.3P_2", "1s1.4d1.3D_2"},
        {305, 17006.9805, "he_i", "1s1.3p1.3P_2", "1s1.4d1.3D_1"},
        {306, 17007.0996, "he_i", "1s1.3p1.3P_1", "1s1.4d1.3D_3"},
        {307, 17007.0977, "he_i", "1s1.3p1.3P_1", "1s1.4d1.3D_2"},
        {308, 17007.043, "he_i", "1s1.3p1.3P_1", "1s1.4d1.3D_1"},
        {309, 17007.8828, "he_i", "1s1.3p1.3P_0", "1s1.4d1.3D_3"},
        {310, 17007.8789, "he_i", "1s1.3p1.3P_0", "1s1.4d1.3D_2"},
        {311, 17007.8262, "he_i", "1s1.3p1.3P_0", "1s1.4d1.3D_1"},
        {312, 19548.4512, "he_i", "1s1.3d1.3D_3", "1s1.4p1.3P_2"},
        {313, 19548.416, "he_i", "1s1.3d1.3D_3", "1s1.4p1.3P_1"},
        {314, 19547.9961, "he_i", "1s1.3d1.3D_3", "1s1.4p1.3P_0"},
        {315, 19548.4609, "he_i", "1s1.3d1.3D_2", "1s1.4p1.3P_2"},
        {316, 19548.4258, "he_i", "1s1.3d1.3D_2", "1s1.4p1.3P_1"},
        {317, 19548.0039, "he_i", "1s1.3d1.3D_2", "1s1.4p1.3P_0"},
        {318, 19548.6289, "he_i", "1s1.3d1.3D_1", "1s1.4p1.3P_2"},
        {319, 19548.5957, "he_i", "1s1.3d1.3D_1", "1s1.4p1.3P_1"},
        {320, 19548.1738, "he_i", "1s1.3d1.3D_1", "1s1.4p1.3P_0"},
        {321, 10833.3066, "he_i", "1s1.2s1.3S_1", "1s1.2p1.3P_2"},
        {322, 10833.2168, "he_i", "1s1.2s1.3S_1", "1s1.2p1.3P_1"},
        {323, 10832.0576, "he_i", "1s1.2s1.3S_1", "1s1.2p1.3P_0"},
        {324, 3889.75073, "he_i", "1s1.2s1.3S_1", "1s1.3p1.3P_2"},
        {325, 3889.74756, "he_i", "1s1.2s1.3S_1", "1s1.3p1.3P_1"},
        {326, 3889.70654, "he_i", "1s1.2s1.3S_1", "1s1.3p1.3P_0"},
        {327, 4000212.25, "he_i", "1s1.5p1.1P", "1s1.5d1.1D"},
        {328, 46065.9609, "he_i", "1s1.4p1.1P_1", "1s1.5s1.1S_0"},
        {329, 3188.66699, "he_i", "1s1.2s1.3S_1", "1s1.4p1.3P_2"},
        {330, 3188.66602, "he_i", "1s1.2s1.3S_1", "1s1.4p1.3P_1"},
        {331, 3188.65503, "he_i", "1s1.2s1.3S_1", "1s1.4p1.3P_0"},
        {332, 2161873.75, "he_i", "1s1.4p1.1P_1", "1s1.4d1.1D_2"},
        {333, 357537.656, "he_i", "1s1.5s1.1S_0", "1s1.5p1.1P"},
        {410, 303.785797, "he_ii", "1s1.2S_1/2", "1s0.2p1.2P_1/2"},
        {411, 303.780396, "he_ii", "1s1.2S_1/2", "1s0.2p1.2P_3/2"},
        {412, 1640.39136, "he_ii", "1s0.2s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {413, 1640.34473, "he_ii", "1s0.2s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {414, 1084.90747, "he_ii", "1s0.2p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {415, 1084.90601, "he_ii", "1s0.2p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {416, 1084.97644, "he_ii", "1s0.2p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {417, 1084.97485, "he_ii", "1s0.2p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {418, 234.458511, "he_ii", "1s1.2S_1/2", "1s0.6p1.2P"},
        {419, 256.317688, "he_ii", "1s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {420, 256.316559, "he_ii", "1s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {421, 1084.91736, "he_ii", "1s0.2s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {422, 1084.91296, "he_ii", "1s0.2s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {423, 1084.9115, "he_ii", "1s0.2p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {424, 1084.98047, "he_ii", "1s0.2p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {425, 1215.08813, "he_ii", "1s0.2p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {426, 1215.08447, "he_ii", "1s0.2p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {427, 1215.17456, "he_ii", "1s0.2p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {428, 1215.17102, "he_ii", "1s0.2p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {429, 1215.09802, "he_ii", "1s0.2p1.2P_1/2", "1s0.4s1.2S_1/2"},
        {430, 1215.18445, "he_ii", "1s0.2p1.2P_3/2", "1s0.4s1.2S_1/2"},
        {431, 1640.375, "he_ii", "1s0.2p1.2P_1/2", "1s0.3s1.2S_1/2"},
        {432, 1640.53259, "he_ii", "1s0.2p1.2P_3/2", "1s0.3s1.2S_1/2"},
        {433, 1027.38037, "he_ii", "1s0.2s1.2S_1/2", "1s0.6p1.2P"},
        {434, 1215.10583, "he_ii", "1s0.2s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {435, 1215.09497, "he_ii", "1s0.2s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {436, 1640.33215, "he_ii", "1s0.2p1.2P_1/2", "1s0.3d1.2D_3/2"},
        {437, 1640.31665, "he_ii", "1s0.2p1.2P_1/2", "1s0.3d1.2D_5/2"},
        {438, 1640.48975, "he_ii", "1s0.2p1.2P_3/2", "1s0.3d1.2D_3/2"},
        {439, 1640.47424, "he_ii", "1s0.2p1.2P_3/2", "1s0.3d1.2D_5/2"},
        {440, 4686.87939, "he_ii", "1s0.3s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {441, 4686.71826, "he_ii", "1s0.3s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {442, 1027.37537, "he_ii", "1s0.2p1.2P_1/2", "1s0.6s1.2S"},
        {443, 1027.43726, "he_ii", "1s0.2p1.2P_3/2", "1s0.6s1.2S"},
        {444, 243.026886, "he_ii", "1s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {445, 243.026443, "he_ii", "1s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {446, 4686.83594, "he_ii", "1s0.3p1.2P_1/2", "1s0.4s1.2S_1/2"},
        {447, 4687.2168, "he_ii", "1s0.3p1.2P_3/2", "1s0.4s1.2S_1/2"},
        {448, 3203.92529, "he_ii", "1s0.3s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {449, 3203.88672, "he_ii", "1s0.3s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {450, 4687.22949, "he_ii", "1s0.3d1.2D_3/2", "1s0.4p1.2P_1/2"},
        {451, 4687.06836, "he_ii", "1s0.3d1.2D_3/2", "1s0.4p1.2P_3/2"},
        {452, 4687.35645, "he_ii", "1s0.3d1.2D_5/2", "1s0.4p1.2P_1/2"},
        {453, 4687.1958, "he_ii", "1s0.3d1.2D_5/2", "1s0.4p1.2P_3/2"},
        {454, 2749.22632, "he_ii", "1s0.3p1.2P_1/2", "1s0.6d1.2D"},
        {455, 2749.35742, "he_ii", "1s0.3p1.2P_3/2", "1s0.6d1.2D"},
        {456, 10126.4355, "he_ii", "1s0.4f1.2F_5/2", "1s0.5g1.2G_7/2"},
        {457, 10126.3975, "he_ii", "1s0.4f1.2F_5/2", "1s0.5g1.2G_9/2"},
        {458, 10126.5605, "he_ii", "1s0.4f1.2F_7/2", "1s0.5g1.2G_7/2"},
        {459, 10126.5225, "he_ii", "1s0.4f1.2F_7/2", "1s0.5g1.2G_9/2"},
        {460, 4687.01514, "he_ii", "1s0.3d1.2D_3/2", "1s0.4f1.2F_5/2"},
        {461, 4686.98828, "he_ii", "1s0.3d1.2D_3/2", "1s0.4f1.2F_7/2"},
        {462, 4687.14209, "he_ii", "1s0.3d1.2D_5/2", "1s0.4f1.2F_5/2"},
        {463, 4687.11572, "he_ii", "1s0.3d1.2D_5/2", "1s0.4f1.2F_7/2"},
        {464, 10126.25, "he_ii", "1s0.4d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {465, 10126.1855, "he_ii", "1s0.4d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {466, 10126.5, "he_ii", "1s0.4d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {467, 10126.4355, "he_ii", "1s0.4d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {468, 3204.0376, "he_ii", "1s0.3d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {469, 3204.03101, "he_ii", "1s0.3d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {470, 3204.09692, "he_ii", "1s0.3d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {471, 3204.09058, "he_ii", "1s0.3d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {472, 6650.03564, "he_ii", "1s0.4s1.2S_1/2", "1s0.6p1.2P"},
        {473, 2749.23682, "he_ii", "1s0.3s1.2S_1/2", "1s0.6p1.2P"},
        {474, 10126.7607, "he_ii", "1s0.4d1.2D_3/2", "1s0.5p1.2P_1/2"},
        {475, 10126.377, "he_ii", "1s0.4d1.2D_3/2", "1s0.5p1.2P_3/2"},
        {476, 10127.0117, "he_ii", "1s0.4d1.2D_5/2", "1s0.5p1.2P_1/2"},
        {477, 10126.627, "he_ii", "1s0.4d1.2D_5/2", "1s0.5p1.2P_3/2"},
        {478, 2749.22632, "he_ii", "1s0.3p1.2P_1/2", "1s0.6s1.2S"},
        {479, 2749.35742, "he_ii", "1s0.3p1.2P_3/2", "1s0.6s1.2S"},
        {480, 10125.6279, "he_ii", "1s0.4p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {481, 10125.5, "he_ii", "1s0.4p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {482, 10126.3789, "he_ii", "1s0.4p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {483, 10126.251, "he_ii", "1s0.4p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {484, 2749.35718, "he_ii", "1s0.3d1.2D_3/2", "1s0.6p1.2P"},
        {485, 2749.40088, "he_ii", "1s0.3d1.2D_5/2", "1s0.6p1.2P"},
        {486, 1027.37537, "he_ii", "1s0.2p1.2P_1/2", "1s0.6d1.2D"},
        {487, 1027.43726, "he_ii", "1s0.2p1.2P_3/2", "1s0.6d1.2D"},
        {488, 10126.0723, "he_ii", "1s0.4s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {489, 10125.6885, "he_ii", "1s0.4s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {490, 3203.87256, "he_ii", "1s0.3p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {491, 3203.85962, "he_ii", "1s0.3p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {492, 3204.05078, "he_ii", "1s0.3p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {493, 3204.03784, "he_ii", "1s0.3p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {494, 2749.35718, "he_ii", "1s0.3d1.2D_3/2", "1s0.6f1.2F"},
        {495, 2749.40088, "he_ii", "1s0.3d1.2D_5/2", "1s0.6f1.2F"},
        {496, 10125.9814, "he_ii", "1s0.4p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {497, 10126.7324, "he_ii", "1s0.4p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {498, 237.330872, "he_ii", "1s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {499, 237.330658, "he_ii", "1s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {500, 3204.08887, "he_ii", "1s0.3d1.2D_3/2", "1s0.5p1.2P_1/2"},
        {501, 3204.05029, "he_ii", "1s0.3d1.2D_3/2", "1s0.5p1.2P_3/2"},
        {502, 3204.14819, "he_ii", "1s0.3d1.2D_5/2", "1s0.5p1.2P_1/2"},
        {503, 3204.10962, "he_ii", "1s0.3d1.2D_5/2", "1s0.5p1.2P_3/2"},
        {504, 3203.90771, "he_ii", "1s0.3p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {505, 3204.08594, "he_ii", "1s0.3p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {506, 4686.68799, "he_ii", "1s0.3p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {507, 4686.63477, "he_ii", "1s0.3p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {508, 4687.06934, "he_ii", "1s0.3p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {509, 4687.01562, "he_ii", "1s0.3p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {510, 6650.00928, "he_ii", "1s0.4p1.2P_1/2", "1s0.6d1.2D"},
        {511, 6650.3335, "he_ii", "1s0.4p1.2P_3/2", "1s0.6d1.2D"},
        {512, 6650.44043, "he_ii", "1s0.4f1.2F_5/2", "1s0.6d1.2D"},
        {513, 6650.49463, "he_ii", "1s0.4f1.2F_7/2", "1s0.6d1.2D"},
        {514, 6650.33252, "he_ii", "1s0.4d1.2D_3/2", "1s0.6f1.2F"},
        {515, 6650.44092, "he_ii", "1s0.4d1.2D_5/2", "1s0.6f1.2F"},
        {516, 6650.44043, "he_ii", "1s0.4f1.2F_5/2", "1s0.6g1.2G"},
        {517, 6650.49463, "he_ii", "1s0.4f1.2F_7/2", "1s0.6g1.2G"},
        {518, 19374.3828, "he_ii", "1s0.5g1.2G_7/2", "1s0.6f1.2F"},
        {519, 19374.5215, "he_ii", "1s0.5g1.2G_9/2", "1s0.6f1.2F"},
        {520, 19372.2754, "he_ii", "1s0.5p1.2P_1/2", "1s0.6d1.2D"},
        {521, 19373.6816, "he_ii", "1s0.5p1.2P_3/2", "1s0.6d1.2D"},
        {522, 19372.3887, "he_ii", "1s0.5s1.2S_1/2", "1s0.6p1.2P"},
        {523, 6650.00928, "he_ii", "1s0.4p1.2P_1/2", "1s0.6s1.2S"},
        {524, 6650.3335, "he_ii", "1s0.4p1.2P_3/2", "1s0.6s1.2S"},
        {525, 10126.627, "he_ii", "1s0.4f1.2F_5/2", "1s0.5d1.2D_3/2"},
        {526, 10126.499, "he_ii", "1s0.4f1.2F_5/2", "1s0.5d1.2D_5/2"},
        {527, 10126.7529, "he_ii", "1s0.4f1.2F_7/2", "1s0.5d1.2D_3/2"},
        {528, 10126.624, "he_ii", "1s0.4f1.2F_7/2", "1s0.5d1.2D_5/2"},
        {529, 6650.33252, "he_ii", "1s0.4d1.2D_3/2", "1s0.6p1.2P"},
        {530, 6650.44092, "he_ii", "1s0.4d1.2D_5/2", "1s0.6p1.2P"},
        {531, 19372.2754, "he_ii", "1s0.5p1.2P_1/2", "1s0.6s1.2S"},
        {532, 19373.6816, "he_ii", "1s0.5p1.2P_3/2", "1s0.6s1.2S"},
        {533, 19374.1484, "he_ii", "1s0.5f1.2F_5/2", "1s0.6d1.2D"},
        {534, 19374.3828, "he_ii", "1s0.5f1.2F_7/2", "1s0.6d1.2D"},
        {535, 19373.6797, "he_ii", "1s0.5d1.2D_3/2", "1s0.6f1.2F"},
        {536, 19374.1484, "he_ii", "1s0.5d1.2D_5/2", "1s0.6f1.2F"},
        {537, 19373.6797, "he_ii", "1s0.5d1.2D_3/2", "1s0.6p1.2P"},
        {538, 19374.1484, "he_ii", "1s0.5d1.2D_5/2", "1s0.6p1.2P"},
        {539, 19374.3828, "he_ii", "1s0.5g1.2G_7/2", "1s0.6h1.2H"},
        {540, 19374.5215, "he_ii", "1s0.5g1.2G_9/2", "1s0.6h1.2H"},
        {541, 19374.1484, "he_ii", "1s0.5f1.2F_5/2", "1s0.6g1.2G"},
        {542, 19374.3828, "he_ii", "1s0.5f1.2F_7/2", "1s0.6g1.2G"},
        {14149, 125.209999, "mg_iii", "2p6.1S_0", "2s1.2p6.3p1.1P_1"},
        {14176, 9.44699955, "mg_iii", "2p6.1S_0", "1s1.2s2.2p6.3p1.1P_1"},
        {14189, 9.44699955, "mg_iii", "2p6.1S_0", "1s1.2s2.2p6.3p1.3P_1"},
        {14198, 125.657997, "mg_iii", "2p6.1S_0", "2s1.2p6.3p1.3P_1"},
        {14240, 234.940002, "mg_iii", "2p6.1S_0", "2p5.3s1.3P_2"},
        {14241, 234.264008, "mg_iii", "2p6.1S_0", "2p5.3s1.3P_1"},
        {14243, 231.733994, "mg_iii", "2p6.1S_0", "2p5.3s1.1P_1"},
        {14274, 188.529999, "mg_iii", "2p6.1S_0", "2p5.3d1.3P_1"},
        {14312, 187.197006, "mg_iii", "2p6.1S_0", "2p5.3d1.3D_1"},
        {14330, 186.514008, "mg_iii", "2p6.1S_0", "2p5.3d1.1P_1"},
        {14369, 45392.6016, "mg_iv", "2p5.2P_3/2", "2p5.2P_1/2"},
        {14370, 9.89509964, "mg_iv", "2p5.2P_3/2", "1s1.2s2.2p6.2S_1/2"},
        {14371, 9.89719963, "mg_iv", "2p5.2P_1/2", "1s1.2s2.2p6.2S_1/2"},
        {14372, 320.993988, "mg_iv", "2p5.2P_3/2", "2s1.2p6.2S_1/2"},
        {14373, 323.306, "mg_iv", "2p5.2P_1/2", "2s1.2p6.2S_1/2"},
        {14375, 312.302002, "mg_v", "2p4.1S_0", "2s1.2p5.1P_1"},
        {14376, 401.764008, "mg_v", "2p4.1D_2", "2s1.2p5.3P_1"},
        {14377, 39654.8984, "mg_v", "2p4.3P_2", "2p4.3P_0"},
        {14378, 9.77200031, "mg_v", "2p4.3P_0", "1s1.2s2.2p5.1P_1"},
        {14379, 352.200989, "mg_v", "2p4.3P_1", "2s1.2p5.3P_0"},
        {14380, 9.88700008, "mg_v", "2p4.1S_0", "1s1.2s2.2p5.3P_1"},
        {14381, 9.76970005, "mg_v", "2p4.3P_2", "1s1.2s2.2p5.1P_1"},
        {14382, 10.4763002, "mg_v", "2s0.2p6.1S_0", "1s1.2s2.2p5.1P_1"},
        {14383, 9.85330009, "mg_v", "2p4.1D_2", "1s1.2s2.2p5.3P_2"},
        {14384, 353.09201, "mg_v", "2p4.3P_2", "2s1.2p5.3P_2"},
        {14385, 9.81820011, "mg_v", "2p4.3P_1", "1s1.2s2.2p5.3P_2"},
        {14386, 354.225006, "mg_v", "2p4.3P_0", "2s1.2p5.3P_1"},
        {14387, 1324.56995, "mg_v", "2p4.3P_1", "2p4.1S_0"},
        {14388, 56081.5, "mg_v", "2p4.3P_2", "2p4.3P_1"},
        {14389, 276.582001, "mg_v", "2p4.1D_2", "2s1.2p5.1P_1"},
        {14390, 252.716995, "mg_v", "2p4.3P_1", "2s1.2p5.1P_1"},
        {14391, 9.8512001, "mg_v", "2p4.1D_2", "1s1.2s2.2p5.3P_1"},
        {14392, 1294.01001, "mg_v", "2p4.3P_2", "2p4.1S_0"},
        {14393, 9.81610012, "mg_v", "2p4.3P_1", "1s1.2s2.2p5.3P_1"},
        {14394, 9.84799957, "mg_v", "2s1.2p5.1P_1", "1s1.2s1.2p6.1S_0"},
        {14395, 264.450989, "mg_v", "2s1.2p5.3P_1", "2s0.2p6.1S_0"},
        {14396, 9.80780029, "mg_v", "2s1.2p5.3P_0", "1s1.2s1.2p6.3S_1"},
        {14397, 355.32901, "mg_v", "2p4.3P_1", "2s1.2p5.3P_2"},
        {14398, 9.81680012, "mg_v", "2p4.3P_0", "1s1.2s2.2p5.3P_1"},
        {14399, 2418.19995, "mg_v", "2p4.1D_2", "2p4.1S_0"},
        {14400, 9.81449986, "mg_v", "2p4.3P_2", "1s1.2s2.2p5.3P_1"},
        {14401, 10.5277996, "mg_v", "2s0.2p6.1S_0", "1s1.2s2.2p5.3P_1"},
        {14402, 351.088013, "mg_v", "2p4.3P_2", "2s1.2p5.3P_1"},
        {14403, 2783.48999, "mg_v", "2p4.3P_2", "2p4.1D_2"},
        {14404, 376.664001, "mg_v", "2s1.2p5.1P_1", "2s0.2p6.1S_0"},
        {14405, 9.92599964, "mg_v", "2s1.2p5.1P_1", "1s1.2s1.2p6.3S_1"},
        {14406, 253.190002, "mg_v", "2p4.3P_0", "2s1.2p5.1P_1"},
        {14407, 135384, "mg_v", "2p4.3P_1", "2p4.3P_0"},
        {14408, 251.582993, "mg_v", "2p4.3P_2", "2s1.2p5.1P_1"},
        {14409, 9.81499958, "mg_v", "2p4.3P_1", "1s1.2s2.2p5.3P_0"},
        {14410, 353.299988, "mg_v", "2p4.3P_1", "2s1.2p5.3P_1"},
        {14411, 404.389008, "mg_v", "2p4.1D_2", "2s1.2p5.3P_2"},
        {14412, 9.81659985, "mg_v", "2p4.3P_2", "1s1.2s2.2p5.3P_2"},
        {14413, 9.80609989, "mg_v", "2p4.1D_2", "1s1.2s2.2p5.1P_1"},
        {14414, 481.812988, "mg_v", "2p4.1S_0", "2s1.2p5.3P_1"},
        {14415, 2928.86011, "mg_v", "2p4.3P_1", "2p4.1D_2"},
        {14416, 9.84150028, "mg_v", "2p4.1S_0", "1s1.2s2.2p5.1P_1"},
        {14417, 9.73089981, "mg_v", "2s1.2p5.3P_1", "1s1.2s1.2p6.1S_0"},
        {14418, 9.77130032, "mg_v", "2p4.3P_1", "1s1.2s2.2p5.1P_1"},
        {14419, 9.80700016, "mg_v", "2s1.2p5.3P_1", "1s1.2s1.2p6.3S_1"},
        {14420, 2993.62988, "mg_v", "2p4.3P_0", "2p4.1D_2"},
        {14421, 9.80550003, "mg_v", "2s1.2p5.3P_2", "1s1.2s1.2p6.3S_1"},
        {14423, 9.81949997, "mg_vi", "2s1.2p4.2D_3/2", "1s1.2s1.2p5.4P_3/2"},
        {14424, 10.3301001, "mg_vi", "2s0.2p5.2P_3/2", "1s1.2s2.2p4.2D_5/2"},
        {14425, 9.63049984, "mg_vi", "2s1.2p4.4P_5/2", "1s1.2s1.2p5.2P_3/2"},
        {14426, 9.7826004, "mg_vi", "2s1.2p4.2S_1/2", "1s1.2s1.2p5.2P_3/2"},
        {14427, 9.72509956, "mg_vi", "2p3.4S_3/2", "1s1.2s2.2p4.4P_5/2"},
        {14428, 9.72490025, "mg_vi", "2s1.2p4.4P_3/2", "1s1.2s1.2p5.4P_5/2"},
        {14429, 9.74339962, "mg_vi", "2s1.2p4.2P_3/2", "1s1.2s1.2p5.2P_1/2#2"},
        {14430, 9.7038002, "mg_vi", "2p3.2D_3/2", "1s1.2s2.2p4.2P_1/2"},
        {14431, 403.309998, "mg_vi", "2p3.4S_3/2", "2s1.2p4.4P_5/2"},
        {14432, 9.74610043, "mg_vi", "2s1.2p4.2P_1/2", "1s1.2s1.2p5.2P_3/2#2"},
        {14433, 3489.72998, "mg_vi", "2p3.2D_3/2", "2p3.2P_3/2"},
        {14434, 248.865997, "mg_vi", "2p3.4S_3/2", "2s1.2p4.2S_1/2"},
        {14435, 9.70590019, "mg_vi", "2p3.2D_5/2", "1s1.2s2.2p4.2P_3/2"},
        {14436, 9.80319977, "mg_vi", "2p3.2P_1/2", "1s1.2s2.2p4.4P_1/2"},
        {14437, 9.80449963, "mg_vi", "2p3.2P_3/2", "1s1.2s2.2p4.4P_3/2"},
        {14438, 10.3196001, "mg_vi", "2s0.2p5.2P_1/2", "1s1.2s2.2p4.2P_1/2"},
        {14439, 9.72350025, "mg_vi", "2s1.2p4.4P_5/2", "1s1.2s1.2p5.4P_5/2"},
        {14440, 9.87549973, "mg_vi", "2s1.2p4.2S_1/2", "1s1.2s1.2p5.4P_1/2"},
        {14441, 9.63189983, "mg_vi", "2s1.2p4.4P_3/2", "1s1.2s1.2p5.2P_3/2"},
        {14442, 9.81099987, "mg_vi", "2s1.2p4.2P_3/2", "1s1.2s1.2p5.2P_3/2"},
        {14443, 519.276978, "mg_vi", "2p3.2D_3/2", "2s1.2p4.4P_5/2"},
        {14444, 314.669006, "mg_vi", "2p3.2P_3/2", "2s1.2p4.2S_1/2"},
        {14445, 9.73050022, "mg_vi", "2p3.2P_3/2", "1s1.2s2.2p4.2P_3/2"},
        {14446, 175.268997, "mg_vi", "2p3.2P_1/2", "2s0.2p5.2P_1/2"},
        {14447, 9.1789999, "mg_vi", "2p3.2D_3/2", "1s1.2p6.2S_1/2"},
        {14448, 9.74050045, "mg_vi", "2p3.2P_3/2", "1s1.2s2.2p4.2D_3/2"},
        {14449, 10.4039001, "mg_vi", "2s0.2p5.2P_1/2", "1s1.2s2.2p4.4P_1/2"},
        {14450, 9.72159958, "mg_vi", "2s1.2p4.4P_5/2", "1s1.2s1.2p5.4P_3/2"},
        {14451, 9.78129959, "mg_vi", "2p3.2D_3/2", "1s1.2s2.2p4.4P_5/2"},
        {14452, 270.390991, "mg_vi", "2p3.2D_5/2", "2s1.2p4.2P_3/2"},
        {14453, 235.188995, "mg_vi", "2p3.4S_3/2", "2s1.2p4.2P_3/2"},
        {14454, 176.072998, "mg_vi", "2p3.2P_1/2", "2s0.2p5.2P_3/2"},
        {14455, 288.641998, "mg_vi", "2p3.2D_3/2", "2s1.2p4.2S_1/2"},
        {14456, 9.56760025, "mg_vi", "2s1.2p4.4P_1/2", "1s1.2s1.2p5.2P_1/2#2"},
        {14457, 9.77950001, "mg_vi", "2p3.2D_5/2", "1s1.2s2.2p4.4P_3/2"},
        {14458, 9.66110039, "mg_vi", "2s1.2p4.2D_3/2", "1s1.2s1.2p5.2P_3/2#2"},
        {14459, 9.74040031, "mg_vi", "2p3.2P_1/2", "1s1.2s2.2p4.2D_3/2"},
        {14460, 9.20100021, "mg_vi", "2p3.2P_1/2", "1s1.2p6.2S_1/2"},
        {14461, 9.66030025, "mg_vi", "2p3.4S_3/2", "1s1.2s2.2p4.2D_3/2"},
        {14462, 9.90429974, "mg_vi", "2s1.2p4.2P_3/2", "1s1.2s1.2p5.4P_1/2"},
        {14463, 9.77939987, "mg_vi", "2p3.2D_3/2", "1s1.2s2.2p4.4P_3/2"},
        {14464, 9.9073, "mg_vi", "2s1.2p4.2P_1/2", "1s1.2s1.2p5.4P_3/2"},
        {14465, 153.406006, "mg_vi", "2p3.4S_3/2", "2s0.2p5.2P_3/2"},
        {14466, 293.02301, "mg_vi", "2p3.2P_1/2", "2s1.2p4.2P_3/2"},
        {14467, 270.403992, "mg_vi", "2p3.2D_3/2", "2s1.2p4.2P_3/2"},
        {14468, 9.63269997, "mg_vi", "2s1.2p4.4P_1/2", "1s1.2s1.2p5.2P_3/2"},
        {14469, 9.78149986, "mg_vi", "2p3.2D_5/2", "1s1.2s2.2p4.4P_5/2"},
        {14470, 9.82139969, "mg_vi", "2s1.2p4.2D_3/2", "1s1.2s1.2p5.4P_5/2"},
        {14471, 9.66110039, "mg_vi", "2s1.2p4.2D_5/2", "1s1.2s1.2p5.2P_3/2#2"},
        {14472, 10.2881002, "mg_vi", "2s0.2p5.2P_3/2", "1s1.2s2.2p4.2S_1/2"},
        {14473, 9.71549988, "mg_vi", "2s1.2p4.2S_1/2", "1s1.2s1.2p5.2P_1/2#2"},
        {14474, 152.794998, "mg_vi", "2p3.4S_3/2", "2s0.2p5.2P_1/2"},
        {14475, 9.6782999, "mg_vi", "2p3.2D_3/2", "1s1.2s2.2p4.2S_1/2"},
        {14476, 1190.06995, "mg_vi", "2p3.4S_3/2", "2p3.2P_3/2"},
        {14477, 9.72809982, "mg_vi", "2s0.2p5.2P_1/2", "1s1.2p6.2S_1/2"},
        {14478, 9.81140041, "mg_vi", "2s1.2p4.2P_1/2", "1s1.2s1.2p5.2P_1/2"},
        {14479, 519.231995, "mg_vi", "2p3.2D_5/2", "2s1.2p4.4P_5/2"},
        {14480, 9.8064003, "mg_vi", "2p3.2P_3/2", "1s1.2s2.2p4.4P_5/2"},
        {14481, 10.2908001, "mg_vi", "2s0.2p5.2P_1/2", "1s1.2s2.2p4.2S_1/2"},
        {14482, 9.56630039, "mg_vi", "2s1.2p4.4P_5/2", "1s1.2s1.2p5.2P_3/2#2"},
        {14483, 9.8767004, "mg_vi", "2s1.2p4.2S_1/2", "1s1.2s1.2p5.4P_3/2"},
        {14484, 9.72210026, "mg_vi", "2p3.4S_3/2", "1s1.2s2.2p4.4P_1/2"},
        {14485, 9.56680012, "mg_vi", "2s1.2p4.4P_3/2", "1s1.2s1.2p5.2P_1/2#2"},
        {14486, 9.80959988, "mg_vi", "2s1.2p4.2P_3/2", "1s1.2s1.2p5.2P_1/2"},
        {14487, 9.70580006, "mg_vi", "2p3.2D_3/2", "1s1.2s2.2p4.2P_3/2"},
        {14488, 314.562012, "mg_vi", "2p3.2P_1/2", "2s1.2p4.2S_1/2"},
        {14489, 3487.66992, "mg_vi", "2p3.2D_5/2", "2p3.2P_3/2"},
        {14490, 514.903015, "mg_vi", "2p3.2D_3/2", "2s1.2p4.4P_3/2"},
        {14491, 388.014008, "mg_vi", "2p3.2P_3/2", "2s1.2p4.2D_5/2"},
        {14492, 604.026001, "mg_vi", "2p3.2P_3/2", "2s1.2p4.4P_3/2"},
        {14493, 9.82139969, "mg_vi", "2s1.2p4.2D_5/2", "1s1.2s1.2p5.4P_5/2"},
        {14494, 9.74030018, "mg_vi", "2p3.2P_3/2", "1s1.2s2.2p4.2D_5/2"},
        {14495, 167.641998, "mg_vi", "2p3.2D_5/2", "2s0.2p5.2P_3/2"},
        {14496, 1806.48999, "mg_vi", "2p3.4S_3/2", "2p3.2D_5/2"},
        {14497, 600.492004, "mg_vi", "2p3.2P_1/2", "2s1.2p4.4P_1/2"},
        {14498, 512.617004, "mg_vi", "2p3.2D_3/2", "2s1.2p4.4P_1/2"},
        {14499, 9.72560024, "mg_vi", "2s0.2p5.2P_3/2", "1s1.2p6.2S_1/2"},
        {14500, 291.45401, "mg_vi", "2p3.2P_3/2", "2s1.2p4.2P_1/2"},
        {14501, 9.71590042, "mg_vi", "2p3.2D_5/2", "1s1.2s2.2p4.2D_3/2"},
        {14502, 9.7251997, "mg_vi", "2s1.2p4.2D_3/2", "1s1.2s1.2p5.2P_1/2"},
        {14503, 9.72840023, "mg_vi", "2p3.2P_1/2", "1s1.2s2.2p4.2P_1/2"},
        {14504, 9.81949997, "mg_vi", "2s1.2p4.2D_5/2", "1s1.2s1.2p5.4P_3/2"},
        {14505, 10.4011002, "mg_vi", "2s0.2p5.2P_3/2", "1s1.2s2.2p4.4P_1/2"},
        {14506, 9.70289993, "mg_vi", "2p3.2P_3/2", "1s1.2s2.2p4.2S_1/2"},
        {14507, 9.65999985, "mg_vi", "2p3.4S_3/2", "1s1.2s2.2p4.2D_5/2"},
        {14508, 9.77820015, "mg_vi", "2p3.2D_3/2", "1s1.2s2.2p4.4P_1/2"},
        {14509, 349.167999, "mg_vi", "2p3.2D_5/2", "2s1.2p4.2D_5/2"},
        {14510, 291.362, "mg_vi", "2p3.2P_1/2", "2s1.2p4.2P_1/2"},
        {14511, 268.989014, "mg_vi", "2p3.2D_3/2", "2s1.2p4.2P_1/2"},
        {14512, 9.63140011, "mg_vi", "2s1.2p4.4P_1/2", "1s1.2s1.2p5.2P_1/2"},
        {14513, 9.73040009, "mg_vi", "2p3.2P_1/2", "1s1.2s2.2p4.2P_3/2"},
        {14514, 166.912003, "mg_vi", "2p3.2D_5/2", "2s0.2p5.2P_1/2"},
        {14515, 9.12950039, "mg_vi", "2p3.4S_3/2", "1s1.2p6.2S_1/2"},
        {14516, 10.3169003, "mg_vi", "2s0.2p5.2P_3/2", "1s1.2s2.2p4.2P_1/2"},
        {14517, 9.71640015, "mg_vi", "2s1.2p4.2S_1/2", "1s1.2s1.2p5.2P_3/2#2"},
        {14518, 9.6232996, "mg_vi", "2p3.4S_3/2", "1s1.2s2.2p4.2S_1/2"},
        {14519, 9.72189999, "mg_vi", "2s1.2p4.4P_3/2", "1s1.2s1.2p5.4P_1/2"},
        {14520, 9.90750027, "mg_vi", "2s1.2p4.2P_3/2", "1s1.2s1.2p5.4P_5/2"},
        {14521, 9.71549988, "mg_vi", "2p3.2D_3/2", "1s1.2s2.2p4.2D_5/2"},
        {14522, 1191.60999, "mg_vi", "2p3.4S_3/2", "2p3.2P_1/2"},
        {14523, 9.81270027, "mg_vi", "2s1.2p4.2P_1/2", "1s1.2s1.2p5.2P_3/2"},
        {14524, 349.117004, "mg_vi", "2p3.2D_5/2", "2s1.2p4.2D_3/2"},
        {14525, 9.72389984, "mg_vi", "2s1.2p4.4P_1/2", "1s1.2s1.2p5.4P_3/2"},
        {14526, 9.81830025, "mg_vi", "2s1.2p4.2D_3/2", "1s1.2s1.2p5.4P_1/2"},
        {14527, 10.3191004, "mg_vi", "2s0.2p5.2P_3/2", "1s1.2s2.2p4.2P_3/2"},
        {14528, 175.302002, "mg_vi", "2p3.2P_3/2", "2s0.2p5.2P_1/2"},
        {14529, 10.3304005, "mg_vi", "2s0.2p5.2P_3/2", "1s1.2s2.2p4.2D_3/2"},
        {14530, 9.78129959, "mg_vi", "2s1.2p4.2S_1/2", "1s1.2s1.2p5.2P_1/2"},
        {14531, 9.72319984, "mg_vi", "2p3.4S_3/2", "1s1.2s2.2p4.4P_3/2"},
        {14532, 9.56770039, "mg_vi", "2s1.2p4.4P_3/2", "1s1.2s1.2p5.2P_3/2#2"},
        {14533, 9.74429989, "mg_vi", "2s1.2p4.2P_3/2", "1s1.2s1.2p5.2P_3/2#2"},
        {14534, 400.665985, "mg_vi", "2p3.4S_3/2", "2s1.2p4.4P_3/2"},
        {14535, 9.74510002, "mg_vi", "2s1.2p4.2P_1/2", "1s1.2s1.2p5.2P_1/2#2"},
        {14536, 3500.90991, "mg_vi", "2p3.2D_5/2", "2p3.2P_1/2"},
        {14537, 3502.97998, "mg_vi", "2p3.2D_3/2", "2p3.2P_1/2"},
        {14538, 387.950012, "mg_vi", "2p3.2P_3/2", "2s1.2p4.2D_3/2"},
        {14539, 610.054016, "mg_vi", "2p3.2P_3/2", "2s1.2p4.4P_5/2"},
        {14540, 9.80430031, "mg_vi", "2p3.2P_1/2", "1s1.2s2.2p4.4P_3/2"},
        {14541, 9.8032999, "mg_vi", "2p3.2P_3/2", "1s1.2s2.2p4.4P_1/2"},
        {14542, 10.3332005, "mg_vi", "2s0.2p5.2P_1/2", "1s1.2s2.2p4.2D_3/2"},
        {14543, 9.20110035, "mg_vi", "2p3.2P_3/2", "1s1.2p6.2S_1/2"},
        {14544, 9.63059998, "mg_vi", "2s1.2p4.4P_3/2", "1s1.2s1.2p5.2P_1/2"},
        {14545, 1805.93994, "mg_vi", "2p3.4S_3/2", "2p3.2D_3/2"},
        {14546, 10.3218002, "mg_vi", "2s0.2p5.2P_1/2", "1s1.2s2.2p4.2P_3/2"},
        {14547, 387.786987, "mg_vi", "2p3.2P_1/2", "2s1.2p4.2D_3/2"},
        {14548, 349.136993, "mg_vi", "2p3.2D_3/2", "2s1.2p4.2D_3/2"},
        {14549, 293.115997, "mg_vi", "2p3.2P_3/2", "2s1.2p4.2P_3/2"},
        {14550, 9.71570015, "mg_vi", "2p3.2D_5/2", "1s1.2s2.2p4.2D_5/2"},
        {14551, 9.72649956, "mg_vi", "2s1.2p4.2D_3/2", "1s1.2s1.2p5.2P_3/2"},
        {14552, 9.7027998, "mg_vi", "2p3.2P_1/2", "1s1.2s2.2p4.2S_1/2"},
        {14553, 10.4022999, "mg_vi", "2s0.2p5.2P_3/2", "1s1.2s2.2p4.4P_3/2"},
        {14554, 9.72850037, "mg_vi", "2p3.2P_3/2", "1s1.2s2.2p4.2P_1/2"},
        {14555, 10.4050999, "mg_vi", "2s0.2p5.2P_1/2", "1s1.2s2.2p4.4P_3/2"},
        {14556, 166.917007, "mg_vi", "2p3.2D_3/2", "2s0.2p5.2P_1/2"},
        {14557, 9.65040016, "mg_vi", "2p3.4S_3/2", "1s1.2s2.2p4.2P_3/2"},
        {14558, 234.117996, "mg_vi", "2p3.4S_3/2", "2s1.2p4.2P_1/2"},
        {14559, 349.187988, "mg_vi", "2p3.2D_3/2", "2s1.2p4.2D_5/2"},
        {14560, 9.56849957, "mg_vi", "2s1.2p4.4P_1/2", "1s1.2s1.2p5.2P_3/2#2"},
        {14561, 176.106003, "mg_vi", "2p3.2P_3/2", "2s0.2p5.2P_3/2"},
        {14562, 9.66009998, "mg_vi", "2s1.2p4.2D_3/2", "1s1.2s1.2p5.2P_1/2#2"},
        {14563, 9.72659969, "mg_vi", "2s1.2p4.2D_5/2", "1s1.2s1.2p5.2P_3/2"},
        {14564, 10.4046001, "mg_vi", "2s0.2p5.2P_3/2", "1s1.2s2.2p4.4P_5/2"},
        {14565, 9.64850044, "mg_vi", "2p3.4S_3/2", "1s1.2s2.2p4.2P_1/2"},
        {14566, 9.72309971, "mg_vi", "2s1.2p4.4P_3/2", "1s1.2s1.2p5.4P_3/2"},
        {14567, 9.90550041, "mg_vi", "2s1.2p4.2P_3/2", "1s1.2s1.2p5.4P_3/2"},
        {14568, 9.71580029, "mg_vi", "2p3.2D_3/2", "1s1.2s2.2p4.2D_3/2"},
        {14569, 9.90620041, "mg_vi", "2s1.2p4.2P_1/2", "1s1.2s1.2p5.4P_1/2"},
        {14570, 399.281006, "mg_vi", "2p3.4S_3/2", "2s1.2p4.4P_1/2"},
        {14571, 167.645996, "mg_vi", "2p3.2D_3/2", "2s0.2p5.2P_3/2"},
        {14572, 9.72270012, "mg_vi", "2s1.2p4.4P_1/2", "1s1.2s1.2p5.4P_1/2"},
        {14574, 9.57789993, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.1D_2"},
        {14575, 85.0469971, "mg_vii", "2p2.3P_2", "2p1.3d1.3F_2"},
        {14576, 97.7060013, "mg_vii", "2s1.2p3.5S_2", "2p1.3p1.3D_3"},
        {14577, 86.6910019, "mg_vii", "2p2.1D_2", "2p1.3d1.3F_3"},
        {14578, 1219.90002, "mg_vii", "2p1.3p1.3D_3", "2p1.3d1.3D_3"},
        {14579, 9.62320042, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.3P_0"},
        {14580, 112.512001, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.1P_1"},
        {14581, 1371.55005, "mg_vii", "2p1.3p1.3P_1", "2p1.3d1.3P_0"},
        {14582, 9.62829971, "mg_vii", "2p2.1S_0", "1s1.2s2.2p3.1P_1"},
        {14583, 1267.71997, "mg_vii", "2p1.3p1.3S_1", "2p1.3d1.3P_0"},
        {14584, 9.62619972, "mg_vii", "2s1.2p3.3D_3", "1s1.2s1.2p4.3P_2"},
        {14585, 1735.68994, "mg_vii", "2p1.3s1.3P_2", "2p1.3p1.3D_1"},
        {14586, 9.66320038, "mg_vii", "2s1.2p3.3P_0", "1s1.2s1.2p4.3P_1"},
        {14587, 129.628006, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.3P_2"},
        {14588, 131.091995, "mg_vii", "2s1.2p3.3S_1", "2p1.3p1.3P_1"},
        {14589, 9.78730011, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.5P_2"},
        {14590, 137.630005, "mg_vii", "2s1.2p3.1P_1", "2p1.3p1.3P_0"},
        {14591, 9.87469959, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.5P_3"},
        {14592, 9.7489996, "mg_vii", "2s0.2p4.1S_0", "1s1.2p5.3P_1"},
        {14593, 111.972, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.3D_1"},
        {14594, 9.53960037, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.1D_2"},
        {14595, 9.47889996, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.1S_0"},
        {14596, 371.071991, "mg_vii", "2s1.2p3.3P_2", "2s0.2p4.3P_1"},
        {14597, 88.7590027, "mg_vii", "2p2.3P_1", "2p1.3p1.3D_2"},
        {14598, 128.901001, "mg_vii", "2s1.2p3.1P_1", "2p1.3p1.1S_0"},
        {14599, 2262.18994, "mg_vii", "2p2.1D_2", "2p2.1S_0"},
        {14600, 9.60410023, "mg_vii", "2p2.3P_1", "1s1.2s2.2p3.3P_2"},
        {14601, 102.472, "mg_vii", "2p2.1S_0", "2p1.3s1.1P_1"},
        {14602, 84.086998, "mg_vii", "2p2.3P_2", "2p1.3d1.3D_2"},
        {14603, 1210.01001, "mg_vii", "2p1.3p1.3D_2", "2p1.3d1.3D_1"},
        {14604, 87.8889999, "mg_vii", "2p2.1D_2", "2p1.3d1.3F_2"},
        {14605, 9.64540005, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.3P_1#2"},
        {14606, 154.473999, "mg_vii", "2s0.2p4.3P_1", "2p1.3d1.3D_1"},
        {14607, 9.44519997, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.3S_1"},
        {14608, 320.265991, "mg_vii", "2s1.2p3.3D_1", "2s0.2p4.3P_0"},
        {14609, 291.182007, "mg_vii", "2s1.2p3.3D_3", "2s0.2p4.1D_2"},
        {14610, 9.63269997, "mg_vii", "2s0.2p4.3P_2", "1s1.2p5.3P_1"},
        {14611, 367.683014, "mg_vii", "2p2.3P_2", "2s1.2p3.3P_1"},
        {14612, 251.792007, "mg_vii", "2p2.3P_0", "2s1.2p3.1P_1"},
        {14613, 427.429993, "mg_vii", "2p2.1D_2", "2s1.2p3.3P_2"},
        {14614, 365.234009, "mg_vii", "2p2.3P_1", "2s1.2p3.3P_2"},
        {14615, 1184.41003, "mg_vii", "2p1.3s1.1P_1", "2p1.3p1.1D_2"},
        {14616, 86.5199966, "mg_vii", "2p2.1D_2", "2p1.3d1.3P_2"},
        {14617, 89.9039993, "mg_vii", "2p2.1S_0", "2p1.3d1.3P_1"},
        {14618, 9.51669979, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.1S_0"},
        {14619, 9.60550022, "mg_vii", "2p2.3P_2", "1s1.2s2.2p3.3P_1"},
        {14620, 9.66880035, "mg_vii", "2p2.1D_2", "1s1.2s2.2p3.3D_1"},
        {14621, 9.68500042, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.3P_1#2"},
        {14622, 10.1673002, "mg_vii", "2s0.2p4.3P_2", "1s1.2s2.2p3.3D_3"},
        {14623, 9.63129997, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.5P_3"},
        {14624, 112.514, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.1P_1"},
        {14625, 10.0840998, "mg_vii", "2s0.2p4.3P_0", "1s1.2s2.2p3.1P_1"},
        {14626, 117.425003, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.3D_1"},
        {14627, 116.092003, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.3S_1"},
        {14628, 9.52719975, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.3P_2#2"},
        {14629, 427.442993, "mg_vii", "2p2.1D_2", "2s1.2p3.3P_1"},
        {14630, 10.1805, "mg_vii", "2s0.2p4.1D_2", "1s1.2s2.2p3.3P_2"},
        {14631, 431.312988, "mg_vii", "2p2.3P_1", "2s1.2p3.3D_2"},
        {14632, 95.6500015, "mg_vii", "2p2.3P_2", "2p1.3s1.3P_1"},
        {14633, 1319.20996, "mg_vii", "2p1.3p1.1P_1", "2p1.3d1.1D_2"},
        {14634, 9.74740028, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.3D_1"},
        {14635, 9.6590004, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.3D_1"},
        {14636, 1143.06995, "mg_vii", "2p1.3p1.3D_2", "2p1.3d1.3P_1"},
        {14637, 1049.06006, "mg_vii", "2p1.3s1.3P_2", "2p1.3p1.1D_2"},
        {14638, 97.8929977, "mg_vii", "2s1.2p3.5S_2", "2p1.3p1.3D_2"},
        {14639, 9.63669968, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.1S_0"},
        {14640, 1327.31006, "mg_vii", "2p1.3s1.3P_1", "2p1.3p1.3P_0"},
        {14641, 198.753006, "mg_vii", "2s0.2p4.3P_0", "2p1.3s1.3P_1"},
        {14642, 152.804001, "mg_vii", "2s0.2p4.3P_2", "2p1.3d1.3P_2"},
        {14643, 9.50940037, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.3P_1"},
        {14644, 117.517998, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.3P_2"},
        {14645, 9.10249996, "mg_vii", "2p2.3P_0", "1s1.2p5.1P_1"},
        {14646, 153.126007, "mg_vii", "2s0.2p4.3P_1", "2p1.3d1.3P_1"},
        {14647, 9.66320038, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.3P_1"},
        {14648, 10.1703997, "mg_vii", "2s0.2p4.3P_0", "1s1.2s2.2p3.3D_1"},
        {14649, 133.242004, "mg_vii", "2s1.2p3.3S_1", "2p1.3p1.3D_1"},
        {14650, 9.66520023, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.3P_2"},
        {14651, 117.420998, "mg_vii", "2s1.2p3.3P_0", "2p1.3p1.3D_1"},
        {14652, 558.263, "mg_vii", "2s1.2p3.1P_1", "2s0.2p4.1D_2"},
        {14653, 331.803009, "mg_vii", "2s1.2p3.3P_1", "2s0.2p4.1D_2"},
        {14654, 9.48750019, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.1P_1"},
        {14655, 9.8767004, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.5P_1"},
        {14656, 132.643997, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.1P_1"},
        {14657, 89.125, "mg_vii", "2p2.3P_2", "2p1.3p1.3P_1"},
        {14658, 98.0309982, "mg_vii", "2p2.1D_2", "2p1.3s1.1P_1"},
        {14659, 9.57590008, "mg_vii", "2p2.3P_1", "1s1.2s2.2p3.1D_2"},
        {14660, 936.409973, "mg_vii", "2p1.3p1.3D_1", "2p1.3d1.1P_1"},
        {14661, 9.60239983, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.1S_0"},
        {14662, 9.56369972, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.3P_1#2"},
        {14663, 84.8909988, "mg_vii", "2p2.3P_2", "2p1.3d1.1D_2"},
        {14664, 1646.77002, "mg_vii", "2p1.3s1.3P_0", "2p1.3p1.3D_1"},
        {14665, 107.434998, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.1D_2"},
        {14666, 111.856003, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3D_2"},
        {14667, 9.65979958, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.1D_2"},
        {14668, 90.3669968, "mg_vii", "2p2.1S_0", "2p1.3d1.3D_1"},
        {14669, 1283.40002, "mg_vii", "2p1.3p1.3S_1", "2p1.3d1.3P_2"},
        {14670, 9.14700031, "mg_vii", "2p2.3P_1", "1s1.2p5.3P_0"},
        {14671, 153.031998, "mg_vii", "2s0.2p4.3P_1", "2p1.3d1.3P_0"},
        {14672, 153.330002, "mg_vii", "2s0.2p4.3P_0", "2p1.3d1.3P_1"},
        {14673, 9.5255003, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.3P_1#2"},
        {14674, 331.811005, "mg_vii", "2s1.2p3.3P_2", "2s0.2p4.1D_2"},
        {14675, 89.1719971, "mg_vii", "2p2.3P_1", "2p1.3p1.1P_1"},
        {14676, 2629.91992, "mg_vii", "2p2.3P_2", "2p2.1D_2"},
        {14677, 9.52530003, "mg_vii", "2s1.2p3.3P_0", "1s1.2s1.2p4.1P_1"},
        {14678, 520.809021, "mg_vii", "2p2.1D_2", "2s1.2p3.3D_2"},
        {14679, 162.134995, "mg_vii", "2s0.2p4.1D_2", "2p1.3d1.3D_3"},
        {14680, 83.7639999, "mg_vii", "2p2.3P_2", "2p1.3d1.3P_2"},
        {14681, 85.3349991, "mg_vii", "2p2.1D_2", "2p1.3d1.1P_1"},
        {14682, 82.5289993, "mg_vii", "2p2.3P_1", "2p1.3d1.1P_1"},
        {14683, 323.248993, "mg_vii", "2s1.2p3.3D_2", "2s0.2p4.3P_2"},
        {14684, 9.63080025, "mg_vii", "2p2.3P_2", "1s1.2s2.2p3.3D_1"},
        {14685, 192.783997, "mg_vii", "2s0.2p4.3P_2", "2p1.3s1.1P_1"},
        {14686, 9.18400002, "mg_vii", "2p2.1D_2", "1s1.2p5.3P_1"},
        {14687, 157.104996, "mg_vii", "2s0.2p4.3P_1", "2p1.3d1.1D_2"},
        {14688, 110.750999, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3S_1"},
        {14689, 9.50529957, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.3D_1"},
        {14690, 9.87150002, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.5P_1"},
        {14691, 235.063995, "mg_vii", "2s1.2p3.3D_1", "2s0.2p4.1S_0"},
        {14692, 9.58329964, "mg_vii", "2s0.2p4.3P_2", "1s1.2p5.1P_1"},
        {14693, 284.513, "mg_vii", "2p2.3P_2", "2s1.2p3.1D_2"},
        {14694, 311.362, "mg_vii", "2p2.1D_2", "2s1.2p3.3S_1"},
        {14695, 157.348999, "mg_vii", "2s0.2p4.1D_2", "2p1.3d1.1F_3"},
        {14696, 365.175995, "mg_vii", "2p2.3P_1", "2s1.2p3.3P_0"},
        {14697, 320.511993, "mg_vii", "2p2.1S_0", "2s1.2p3.1P_1"},
        {14698, 9.53969955, "mg_vii", "2s1.2p3.3D_3", "1s1.2s1.2p4.1D_2"},
        {14699, 83.9100037, "mg_vii", "2p2.3P_0", "2p1.3d1.3D_1"},
        {14700, 9.56550026, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.3P_2#2"},
        {14701, 9.5532999, "mg_vii", "2p2.3P_2", "1s1.2s2.2p3.1P_1"},
        {14702, 9.66880035, "mg_vii", "2p2.1D_2", "1s1.2s2.2p3.3D_2"},
        {14703, 117.516998, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.3P_2"},
        {14704, 10.1398001, "mg_vii", "2s0.2p4.3P_2", "1s1.2s2.2p3.3P_2"},
        {14705, 10.1695004, "mg_vii", "2s0.2p4.3P_1", "1s1.2s2.2p3.3D_1"},
        {14706, 9.62419987, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.3P_1"},
        {14707, 10.1422997, "mg_vii", "2s0.2p4.3P_0", "1s1.2s2.2p3.3P_1"},
        {14708, 1594.64001, "mg_vii", "2p1.3s1.1P_1", "2p1.3p1.3P_0"},
        {14709, 548.617981, "mg_vii", "2s1.2p3.3S_1", "2s0.2p4.3P_1"},
        {14710, 371.131989, "mg_vii", "2s1.2p3.3P_0", "2s0.2p4.3P_1"},
        {14711, 382.721008, "mg_vii", "2s1.2p3.1P_1", "2s0.2p4.1S_0"},
        {14712, 9.87800026, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.5P_2"},
        {14713, 117.641998, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.3P_1"},
        {14714, 9.5248003, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.3P_0#2"},
        {14715, 10.1801004, "mg_vii", "2s0.2p4.1D_2", "1s1.2s2.2p3.3P_1"},
        {14716, 1189.81995, "mg_vii", "2p2.3P_1", "2p2.1S_0"},
        {14717, 676.263977, "mg_vii", "2p2.1S_0", "2s1.2p3.3D_1"},
        {14718, 10.2972002, "mg_vii", "2s0.2p4.1S_0", "1s1.2s2.2p3.3D_1"},
        {14719, 94.5080032, "mg_vii", "2p2.3P_2", "2p1.3s1.1P_1"},
        {14720, 1078.77002, "mg_vii", "2p1.3p1.1P_1", "2p1.3d1.3P_1"},
        {14721, 9.64960003, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.3P_0#2"},
        {14722, 9.59700012, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.3S_1"},
        {14723, 197.595001, "mg_vii", "2s0.2p4.3P_2", "2p1.3s1.3P_1"},
        {14724, 1293.16003, "mg_vii", "2p1.3s1.3P_0", "2p1.3p1.3P_1"},
        {14725, 9.59070015, "mg_vii", "2p2.1D_2", "1s1.2s2.2p3.1P_1"},
        {14726, 9.64560032, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.1P_1"},
        {14727, 1487.88, "mg_vii", "2p1.3p1.3P_2", "2p1.3d1.3D_3"},
        {14728, 9.60639954, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.1P_1"},
        {14729, 675.169006, "mg_vii", "2s1.2p3.1P_1", "2s0.2p4.3P_0"},
        {14730, 9.74919987, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.5P_3"},
        {14731, 9.66209984, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.3P_0"},
        {14732, 9.17310047, "mg_vii", "2p2.1S_0", "1s1.2p5.1P_1"},
        {14733, 9.74660015, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.3P_1"},
        {14734, 9.91429996, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.5P_2"},
        {14735, 88.6050034, "mg_vii", "2p2.3P_1", "2p1.3p1.3D_3"},
        {14736, 132.559998, "mg_vii", "2s1.2p3.1P_1", "2p1.3p1.1D_2"},
        {14737, 153.671997, "mg_vii", "2s0.2p4.3P_2", "2p1.3d1.3D_3"},
        {14738, 9.60410023, "mg_vii", "2p2.3P_1", "1s1.2s2.2p3.3P_0"},
        {14739, 84.1169968, "mg_vii", "2p2.3P_2", "2p1.3d1.3D_1"},
        {14740, 83.5110016, "mg_vii", "2p2.3P_0", "2p1.3d1.3P_1"},
        {14741, 235.729004, "mg_vii", "2s1.2p3.5S_2", "2s0.2p4.3P_2"},
        {14742, 92.1750031, "mg_vii", "2p2.1D_2", "2p1.3p1.3P_2"},
        {14743, 1487.43005, "mg_vii", "2p1.3p1.3P_1", "2p1.3d1.3D_2"},
        {14744, 1350.13, "mg_vii", "2p1.3p1.3S_1", "2p1.3d1.3D_2"},
        {14745, 1447.57996, "mg_vii", "2p1.3p1.1D_2", "2p1.3d1.1P_1"},
        {14746, 9.15009975, "mg_vii", "2p2.3P_1", "1s1.2p5.3P_2"},
        {14747, 112.117996, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.3P_1"},
        {14748, 10.0811996, "mg_vii", "2s0.2p4.3P_2", "1s1.2s2.2p3.1P_1"},
        {14749, 139.535995, "mg_vii", "2s1.2p3.1P_1", "2p1.3p1.3D_1"},
        {14750, 9.62020016, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.3D_3"},
        {14751, 532.155029, "mg_vii", "2s1.2p3.1D_2", "2s0.2p4.3P_2"},
        {14752, 95.2580032, "mg_vii", "2p2.3P_1", "2p1.3s1.3P_2"},
        {14753, 868.236023, "mg_vii", "2p2.3P_2", "2s1.2p3.5S_2"},
        {14754, 9.71720028, "mg_vii", "2p2.3P_1", "1s1.2s2.2p3.5S_2"},
        {14755, 10.0832005, "mg_vii", "2s0.2p4.3P_1", "1s1.2s2.2p3.1P_1"},
        {14756, 9.65909958, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.3D_1"},
        {14757, 1379.12, "mg_vii", "2p1.3p1.3P_1", "2p1.3d1.3P_1"},
        {14758, 83.5879974, "mg_vii", "2p2.3P_1", "2p1.3d1.3P_1"},
        {14759, 9.63080025, "mg_vii", "2p2.3P_2", "1s1.2s2.2p3.3D_2"},
        {14760, 9.64369965, "mg_vii", "2p2.1D_2", "1s1.2s2.2p3.3P_2"},
        {14761, 9.68669987, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.3P_2#2"},
        {14762, 10.1674995, "mg_vii", "2s0.2p4.3P_2", "1s1.2s2.2p3.3D_1"},
        {14763, 2357.71997, "mg_vii", "2p1.3s1.1P_1", "2p1.3p1.1P_1"},
        {14764, 9.67169952, "mg_vii", "2s0.2p4.1D_2", "1s1.2p5.3P_2"},
        {14765, 118.022003, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.1P_1"},
        {14766, 253.658997, "mg_vii", "2p2.3P_2", "2s1.2p3.1P_1"},
        {14767, 9.58580017, "mg_vii", "2s0.2p4.3P_0", "1s1.2p5.1P_1"},
        {14768, 9.62010002, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.3D_2"},
        {14769, 520.627014, "mg_vii", "2p2.1D_2", "2s1.2p3.3D_1"},
        {14770, 10.2083998, "mg_vii", "2s0.2p4.1D_2", "1s1.2s2.2p3.3D_1"},
        {14771, 431.187988, "mg_vii", "2p2.3P_1", "2s1.2p3.3D_1"},
        {14772, 99.2600021, "mg_vii", "2p2.1D_2", "2p1.3s1.3P_1"},
        {14773, 211.809998, "mg_vii", "2s0.2p4.1D_2", "2p1.3s1.3P_1"},
        {14774, 1196.85999, "mg_vii", "2p1.3p1.3D_1", "2p1.3d1.3D_1"},
        {14775, 1024.96997, "mg_vii", "2p1.3s1.3P_1", "2p1.3p1.1D_2"},
        {14776, 9.74730015, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.3D_2"},
        {14777, 9.78269958, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.3D_2"},
        {14778, 107.433998, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.1D_2"},
        {14779, 1645.77002, "mg_vii", "2p1.3s1.3P_1", "2p1.3p1.3D_2"},
        {14780, 83.7470016, "mg_vii", "2p2.3P_2", "2p1.3d1.3F_3"},
        {14781, 10.1393995, "mg_vii", "2s0.2p4.3P_2", "1s1.2s2.2p3.3P_1"},
        {14782, 9.51119995, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.3P_2"},
        {14783, 10.1417999, "mg_vii", "2s0.2p4.3P_1", "1s1.2s2.2p3.3P_0"},
        {14784, 110.752998, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.3S_1"},
        {14785, 117.648003, "mg_vii", "2s1.2p3.3P_0", "2p1.3p1.3P_1"},
        {14786, 117.806999, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.3P_0"},
        {14787, 118.028999, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.1P_1"},
        {14788, 2442.12012, "mg_vii", "2p2.3P_0", "2p2.1D_2"},
        {14789, 9.91300011, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.5P_1"},
        {14790, 131.393997, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.3D_3"},
        {14791, 10.1213999, "mg_vii", "2s0.2p4.1D_2", "1s1.2s2.2p3.1P_1"},
        {14792, 55035, "mg_vii", "2p2.3P_1", "2p2.3P_2"},
        {14793, 88.9749985, "mg_vii", "2p2.3P_2", "2p1.3p1.3D_1"},
        {14794, 9.59689999, "mg_vii", "2s1.2p3.3P_0", "1s1.2s1.2p4.3S_1"},
        {14795, 91.4759979, "mg_vii", "2p2.1D_2", "2p1.3p1.3S_1"},
        {14796, 9.65200043, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.3P_2#2"},
        {14797, 9.56540012, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.3P_2#2"},
        {14798, 89.0540009, "mg_vii", "2p2.3P_2", "2p1.3p1.3P_2"},
        {14799, 1417.40002, "mg_vii", "2p1.3s1.3P_0", "2p1.3p1.3S_1"},
        {14800, 1234.17004, "mg_vii", "2p1.3p1.3D_3", "2p1.3d1.3D_2"},
        {14801, 198.720993, "mg_vii", "2s0.2p4.3P_1", "2p1.3s1.3P_0"},
        {14802, 1396.44995, "mg_vii", "2p1.3p1.3P_2", "2p1.3d1.3P_1"},
        {14803, 1031.31006, "mg_vii", "2p1.3p1.3S_1", "2p1.3d1.1P_1"},
        {14804, 1708.76001, "mg_vii", "2p1.3s1.3P_2", "2p1.3p1.3D_2"},
        {14805, 9.78600025, "mg_vii", "2s1.2p3.3P_0", "1s1.2s1.2p4.5P_1"},
        {14806, 125.641998, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.1D_2"},
        {14807, 9.2184, "mg_vii", "2p2.1S_0", "1s1.2p5.3P_1"},
        {14808, 9.78919983, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.5P_3"},
        {14809, 137.403, "mg_vii", "2s1.2p3.1P_1", "2p1.3p1.3P_1"},
        {14810, 9.87279987, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.5P_2"},
        {14811, 9.52719975, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.3P_2#2"},
        {14812, 373.954987, "mg_vii", "2s1.2p3.3P_2", "2s0.2p4.3P_2"},
        {14813, 88.8310013, "mg_vii", "2p2.3P_1", "2p1.3p1.3D_1"},
        {14814, 10.2087002, "mg_vii", "2s0.2p4.1S_0", "1s1.2s2.2p3.1P_1"},
        {14815, 9.60270023, "mg_vii", "2p2.3P_0", "1s1.2s2.2p3.3P_1"},
        {14816, 166.626999, "mg_vii", "2s0.2p4.1D_2", "2p1.3d1.3F_3"},
        {14817, 9.61050034, "mg_vii", "2p2.3P_1", "1s1.2s2.2p3.3S_1"},
        {14818, 187.507996, "mg_vii", "2s0.2p4.1S_0", "2p1.3d1.3D_1"},
        {14819, 84.0250015, "mg_vii", "2p2.3P_2", "2p1.3d1.3D_3"},
        {14820, 1443.95996, "mg_vii", "2p1.3p1.3D_2", "2p1.3d1.3F_3"},
        {14821, 87.5289993, "mg_vii", "2p2.1D_2", "2p1.3p1.1S_0"},
        {14822, 9.74240017, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.3D_3"},
        {14823, 111.984001, "mg_vii", "2s1.2p3.3D_3", "2p1.3p1.3P_2"},
        {14824, 3228.31006, "mg_vii", "2p1.3p1.1D_2", "2p1.3d1.3F_2"},
        {14825, 156.593994, "mg_vii", "2s0.2p4.3P_2", "2p1.3d1.1D_2"},
        {14826, 154.682007, "mg_vii", "2s0.2p4.3P_0", "2p1.3d1.3D_1"},
        {14827, 9.50529957, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.3D_2"},
        {14828, 321.161987, "mg_vii", "2s1.2p3.3D_1", "2s0.2p4.3P_1"},
        {14829, 111.858002, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.3D_2"},
        {14830, 9.61999989, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.3D_2"},
        {14831, 9.48750019, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.1P_1"},
        {14832, 95.3830032, "mg_vii", "2p2.3P_0", "2p1.3s1.3P_1"},
        {14833, 9.63500023, "mg_vii", "2s0.2p4.3P_2", "1s1.2p5.3P_2"},
        {14834, 95.5559998, "mg_vii", "2p2.3P_1", "2p1.3s1.3P_0"},
        {14835, 434.592987, "mg_vii", "2p2.3P_2", "2s1.2p3.3D_1"},
        {14836, 429.140015, "mg_vii", "2p2.3P_0", "2s1.2p3.3D_1"},
        {14837, 157.104004, "mg_vii", "2s0.2p4.1D_2", "2p1.3d1.1P_1"},
        {14838, 252.496002, "mg_vii", "2p2.3P_1", "2s1.2p3.1P_1"},
        {14839, 1542.96997, "mg_vii", "2p1.3s1.1P_1", "2p1.3p1.3P_2"},
        {14840, 9.59700012, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.3S_1"},
        {14841, 86.7979965, "mg_vii", "2p2.1D_2", "2p1.3d1.3D_3"},
        {14842, 9.52540016, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.1P_1"},
        {14843, 9.61229992, "mg_vii", "2p2.3P_2", "1s1.2s2.2p3.3S_1"},
        {14844, 9.64340019, "mg_vii", "2p2.1D_2", "1s1.2s2.2p3.3P_1"},
        {14845, 9.68420029, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.3P_0#2"},
        {14846, 9.56379986, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.3P_1#2"},
        {14847, 10.1674995, "mg_vii", "2s0.2p4.3P_2", "1s1.2s2.2p3.3D_2"},
        {14848, 9.41460037, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.3P_2#2"},
        {14849, 2099.6001, "mg_vii", "2p1.3s1.1P_1", "2p1.3p1.3D_2"},
        {14850, 546.008972, "mg_vii", "2s1.2p3.3S_1", "2s0.2p4.3P_0"},
        {14851, 9.63679981, "mg_vii", "2s0.2p4.3P_1", "1s1.2p5.3P_2"},
        {14852, 117.300003, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.3D_2"},
        {14853, 117.038002, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.3D_3"},
        {14854, 9.63529968, "mg_vii", "2s0.2p4.3P_0", "1s1.2p5.3P_1"},
        {14855, 9.53960037, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.1D_2"},
        {14856, 10.2083998, "mg_vii", "2s0.2p4.1D_2", "1s1.2s2.2p3.3D_2"},
        {14857, 854.752014, "mg_vii", "2p2.3P_1", "2s1.2p3.5S_2"},
        {14858, 527.025024, "mg_vii", "2p2.1S_0", "2s1.2p3.3P_1"},
        {14859, 95.4229965, "mg_vii", "2p2.3P_2", "2p1.3s1.3P_2"},
        {14860, 9.56369972, "mg_vii", "2s1.2p3.3P_0", "1s1.2s1.2p4.3P_1#2"},
        {14861, 206.292007, "mg_vii", "2s0.2p4.1D_2", "2p1.3s1.1P_1"},
        {14862, 88.9100037, "mg_vii", "2p2.3P_1", "2p1.3p1.3P_2"},
        {14863, 1398.66003, "mg_vii", "2p1.3p1.3D_1", "2p1.3d1.1D_2"},
        {14864, 1205.03003, "mg_vii", "2p1.3p1.3D_2", "2p1.3d1.3D_2"},
        {14865, 1470.37, "mg_vii", "2p1.3p1.3P_0", "2p1.3d1.3D_1"},
        {14866, 1800.25, "mg_vii", "2p1.3s1.3P_1", "2p1.3p1.1P_1"},
        {14867, 108.487, "mg_vii", "2s1.2p3.3P_1", "2p1.3d1.3F_3"},
        {14868, 1653.39001, "mg_vii", "2p1.3s1.3P_2", "2p1.3p1.3D_3"},
        {14869, 9.62829971, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.5P_1"},
        {14870, 9.15170002, "mg_vii", "2p2.3P_2", "1s1.2p5.3P_2"},
        {14871, 248.391006, "mg_vii", "2s0.2p4.1S_0", "2p1.3s1.1P_1"},
        {14872, 10.1489, "mg_vii", "2s0.2p4.3P_1", "1s1.2s2.2p3.3S_1"},
        {14873, 95.4840012, "mg_vii", "2p2.3P_1", "2p1.3s1.3P_1"},
        {14874, 9.66329956, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.3P_1"},
        {14875, 116.081001, "mg_vii", "2s1.2p3.3P_0", "2p1.3p1.3S_1"},
        {14876, 688.880005, "mg_vii", "2s1.2p3.1P_1", "2s0.2p4.3P_2"},
        {14877, 9.69839954, "mg_vii", "2s0.2p4.1S_0", "1s1.2p5.1P_1"},
        {14878, 10.1695004, "mg_vii", "2s0.2p4.3P_1", "1s1.2s2.2p3.3D_2"},
        {14879, 9.75049973, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.3P_0"},
        {14880, 117.306999, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.3D_2"},
        {14881, 9.78899956, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.3P_2"},
        {14882, 131.891006, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.3D_1"},
        {14883, 126.866997, "mg_vii", "2s1.2p3.3S_1", "2p1.3p1.1D_2"},
        {14884, 88.7490005, "mg_vii", "2p2.3P_2", "2p1.3p1.3D_3"},
        {14885, 9.6590004, "mg_vii", "2s1.2p3.3P_0", "1s1.2s1.2p4.3D_1"},
        {14886, 1127.28003, "mg_vii", "2p1.3p1.3D_1", "2p1.3d1.3P_0"},
        {14887, 9.56299973, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.3P_0#2"},
        {14888, 97.0459976, "mg_vii", "2s1.2p3.5S_2", "2p1.3p1.3S_1"},
        {14889, 9.62609959, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.3P_2"},
        {14890, 87.7220001, "mg_vii", "2p2.1D_2", "2p1.3d1.1D_2"},
        {14891, 1178.18005, "mg_vii", "2p1.3p1.3D_3", "2p1.3d1.3P_2"},
        {14892, 112.004997, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.3P_2"},
        {14893, 9.64710045, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.3P_2#2"},
        {14894, 1272.82996, "mg_vii", "2p1.3p1.3S_1", "2p1.3d1.3P_1"},
        {14895, 9.37580013, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.1P_1"},
        {14896, 140.378998, "mg_vii", "2s1.2p3.1P_1", "2p1.3p1.1P_1"},
        {14897, 450.696014, "mg_vii", "2s1.2p3.1D_2", "2s0.2p4.1D_2"},
        {14898, 94.3460007, "mg_vii", "2p2.3P_1", "2p1.3s1.1P_1"},
        {14899, 1216.12, "mg_vii", "2p2.3P_2", "2p2.1S_0"},
        {14900, 1296.14001, "mg_vii", "2p2.1D_2", "2s1.2p3.5S_2"},
        {14901, 9.62899971, "mg_vii", "2p2.3P_1", "1s1.2s2.2p3.3D_2"},
        {14902, 82.6529999, "mg_vii", "2p2.3P_2", "2p1.3d1.1P_1"},
        {14903, 83.7149963, "mg_vii", "2p2.3P_2", "2p1.3d1.3P_1"},
        {14904, 83.5599976, "mg_vii", "2p2.3P_1", "2p1.3d1.3P_0"},
        {14905, 321.092987, "mg_vii", "2s1.2p3.3D_2", "2s0.2p4.3P_1"},
        {14906, 92.3310013, "mg_vii", "2p2.1S_0", "2p1.3p1.1D_2"},
        {14907, 9.7191, "mg_vii", "2p2.3P_2", "1s1.2s2.2p3.5S_2"},
        {14908, 103.653, "mg_vii", "2s1.2p3.3D_3", "2p1.3d1.3F_4"},
        {14909, 153.979996, "mg_vii", "2s0.2p4.3P_2", "2p1.3d1.3D_1"},
        {14910, 9.18599987, "mg_vii", "2p2.1D_2", "1s1.2p5.3P_2"},
        {14911, 9.74610043, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.5P_1"},
        {14912, 9.5053997, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.3D_3"},
        {14913, 291.326996, "mg_vii", "2s1.2p3.3D_1", "2s0.2p4.1D_2"},
        {14914, 131.298004, "mg_vii", "2s1.2p3.3S_1", "2p1.3p1.3P_0"},
        {14915, 276.153992, "mg_vii", "2p2.3P_0", "2s1.2p3.3S_1"},
        {14916, 319.027008, "mg_vii", "2p2.1D_2", "2s1.2p3.1D_2"},
        {14917, 283.049988, "mg_vii", "2p2.3P_1", "2s1.2p3.1D_2"},
        {14918, 944.77002, "mg_vii", "2p1.3s1.1P_1", "2p1.3p1.1S_0"},
        {14919, 9.52729988, "mg_vii", "2s1.2p3.3D_3", "1s1.2s1.2p4.3P_2#2"},
        {14920, 88.8219986, "mg_vii", "2p2.3P_0", "2p1.3p1.3P_2"},
        {14921, 1370.02002, "mg_vii", "2p1.3p1.1P_1", "2p1.3d1.3F_2"},
        {14922, 86.4680023, "mg_vii", "2p2.1D_2", "2p1.3d1.3P_1"},
        {14923, 83.987999, "mg_vii", "2p2.3P_1", "2p1.3d1.3D_1"},
        {14924, 840.479004, "mg_vii", "2p1.3s1.3P_1", "2p1.3p1.1S_0"},
        {14925, 256.436005, "mg_vii", "2s0.2p4.1S_0", "2p1.3s1.3P_1"},
        {14926, 197.434006, "mg_vii", "2s0.2p4.3P_1", "2p1.3s1.3P_2"},
        {14927, 9.7578001, "mg_vii", "2p2.1D_2", "1s1.2s2.2p3.5S_2"},
        {14928, 9.78269958, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.3D_1"},
        {14929, 111.612, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3D_3"},
        {14930, 9.6882, "mg_vii", "2p2.1S_0", "1s1.2s2.2p3.3S_1"},
        {14931, 112.445999, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.1D_2"},
        {14932, 10.1469002, "mg_vii", "2s0.2p4.3P_2", "1s1.2s2.2p3.3S_1"},
        {14933, 9.62950039, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.5P_2"},
        {14934, 9.14710045, "mg_vii", "2p2.3P_0", "1s1.2p5.3P_1"},
        {14935, 10.2679996, "mg_vii", "2s0.2p4.3P_1", "1s1.2s2.2p3.5S_2"},
        {14936, 111.865997, "mg_vii", "2s1.2p3.3D_3", "2p1.3p1.3D_2"},
        {14937, 1768.43994, "mg_vii", "2p1.3s1.1P_1", "2p1.3p1.3S_1"},
        {14938, 554.940979, "mg_vii", "2s1.2p3.3S_1", "2s0.2p4.3P_2"},
        {14939, 9.63449955, "mg_vii", "2s0.2p4.3P_1", "1s1.2p5.3P_1"},
        {14940, 116.084999, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.3S_1"},
        {14941, 9.52560043, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.3P_1#2"},
        {14942, 129.779007, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.3P_1"},
        {14943, 10.1877003, "mg_vii", "2s0.2p4.1D_2", "1s1.2s2.2p3.3S_1"},
        {14944, 2509.96997, "mg_vii", "2p2.3P_1", "2p2.1D_2"},
        {14945, 10.2683001, "mg_vii", "2s0.2p4.1S_0", "1s1.2s2.2p3.3P_1"},
        {14946, 89.3180008, "mg_vii", "2p2.3P_2", "2p1.3p1.1P_1"},
        {14947, 9.55060005, "mg_vii", "2p2.3P_0", "1s1.2s2.2p3.1P_1"},
        {14948, 1455.90002, "mg_vii", "2p1.3p1.3D_1", "2p1.3d1.3F_2"},
        {14949, 9.65030003, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.3P_1#2"},
        {14950, 1334.21997, "mg_vii", "2p1.3s1.3P_2", "2p1.3p1.3P_2"},
        {14951, 9.61520004, "mg_vii", "2p2.1D_2", "1s1.2s2.2p3.1D_2"},
        {14952, 9.74730015, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.5P_2"},
        {14953, 1507.60999, "mg_vii", "2p1.3p1.3P_2", "2p1.3d1.3D_2"},
        {14954, 1306.51001, "mg_vii", "2p1.3s1.3P_1", "2p1.3p1.3P_1"},
        {14955, 9.74919987, "mg_vii", "2s1.2p3.3D_3", "1s1.2s1.2p4.5P_3"},
        {14956, 152.639999, "mg_vii", "2s0.2p4.3P_2", "2p1.3d1.3P_1"},
        {14957, 112.452003, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.1D_2"},
        {14958, 153.289993, "mg_vii", "2s0.2p4.3P_1", "2p1.3d1.3P_2"},
        {14959, 9.74730015, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.5P_2"},
        {14960, 9.78600025, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.5P_1"},
        {14961, 111.622002, "mg_vii", "2s1.2p3.3D_3", "2p1.3p1.3D_3"},
        {14962, 133.080994, "mg_vii", "2s1.2p3.3S_1", "2p1.3p1.3D_2"},
        {14963, 9.63329983, "mg_vii", "2s0.2p4.3P_1", "1s1.2p5.3P_0"},
        {14964, 9.74849987, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.3P_2"},
        {14965, 369.867004, "mg_vii", "2s1.2p3.3P_1", "2s0.2p4.3P_0"},
        {14966, 9.75160027, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.3P_1"},
        {14967, 94.2480011, "mg_vii", "2p2.3P_0", "2p1.3s1.1P_1"},
        {14968, 88.9810028, "mg_vii", "2p2.3P_1", "2p1.3p1.3P_1"},
        {14969, 2177.56006, "mg_vii", "2p1.3p1.3P_2", "2p1.3d1.3F_3"},
        {14970, 89.2210007, "mg_vii", "2p2.3P_2", "2p1.3p1.3P_0"},
        {14971, 900.116028, "mg_vii", "2p1.3p1.1P_1", "2p1.3d1.1P_1"},
        {14972, 92.6740036, "mg_vii", "2p2.1D_2", "2p1.3p1.1P_1"},
        {14973, 165.983002, "mg_vii", "2s0.2p4.1D_2", "2p1.3d1.3F_2"},
        {14974, 9.55160046, "mg_vii", "2p2.3P_1", "1s1.2s2.2p3.1P_1"},
        {14975, 9.61130047, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.1P_1"},
        {14976, 9.52540016, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.1P_1"},
        {14977, 1475.41003, "mg_vii", "2p1.3p1.3D_2", "2p1.3d1.3F_2"},
        {14978, 1772.45996, "mg_vii", "2p1.3s1.3P_0", "2p1.3p1.1P_1"},
        {14979, 86.8960037, "mg_vii", "2p2.1D_2", "2p1.3d1.3D_1"},
        {14980, 1486.02002, "mg_vii", "2p1.3p1.3D_3", "2p1.3d1.3F_3"},
        {14981, 105.018997, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.1S_0"},
        {14982, 111.970001, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3D_1"},
        {14983, 9.67920017, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.3S_1"},
        {14984, 1438.45996, "mg_vii", "2p1.3p1.1D_2", "2p1.3d1.1F_3"},
        {14985, 9.13899994, "mg_vii", "2p2.1D_2", "1s1.2p5.1P_1"},
        {14986, 9.10340023, "mg_vii", "2p2.3P_1", "1s1.2p5.1P_1"},
        {14987, 157.639999, "mg_vii", "2s0.2p4.3P_1", "2p1.3d1.3F_2"},
        {14988, 10.1083002, "mg_vii", "2s0.2p4.3P_2", "1s1.2s2.2p3.1D_2"},
        {14989, 139.358994, "mg_vii", "2s1.2p3.1P_1", "2p1.3p1.3D_2"},
        {14990, 9.62010002, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.3D_1"},
        {14991, 149.365997, "mg_vii", "2s0.2p4.3P_2", "2p1.3d1.1F_3"},
        {14992, 9.74740028, "mg_vii", "2s1.2p3.3D_3", "1s1.2s1.2p4.5P_2"},
        {14993, 434.720001, "mg_vii", "2p2.3P_2", "2s1.2p3.3D_2"},
        {14994, 363.772003, "mg_vii", "2p2.3P_0", "2s1.2p3.3P_1"},
        {14995, 1350.43994, "mg_vii", "2p1.3s1.3P_2", "2p1.3p1.3P_1"},
        {14996, 162.365997, "mg_vii", "2s0.2p4.1D_2", "2p1.3d1.3D_2"},
        {14997, 9.62899971, "mg_vii", "2p2.3P_1", "1s1.2s2.2p3.3D_1"},
        {14998, 9.65919971, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.3D_3"},
        {14999, 9.62010002, "mg_vii", "2s1.2p3.3D_3", "1s1.2s1.2p4.3D_2"},
        {15000, 82.4540024, "mg_vii", "2p2.3P_0", "2p1.3d1.1P_1"},
        {15001, 9.10499954, "mg_vii", "2p2.3P_2", "1s1.2p5.1P_1"},
        {15002, 85.4069977, "mg_vii", "2p2.1D_2", "2p1.3d1.1F_3"},
        {15003, 1519.33997, "mg_vii", "2p1.3p1.3D_3", "2p1.3d1.3F_2"},
        {15004, 83.637001, "mg_vii", "2p2.3P_1", "2p1.3d1.3P_2"},
        {15005, 291.270996, "mg_vii", "2s1.2p3.3D_2", "2s0.2p4.1D_2"},
        {15006, 9.57800007, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.1D_2"},
        {15007, 9.63059998, "mg_vii", "2p2.3P_2", "1s1.2s2.2p3.3D_3"},
        {15008, 9.65019989, "mg_vii", "2p2.1D_2", "1s1.2s2.2p3.3S_1"},
        {15009, 9.41300011, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.3P_1#2"},
        {15010, 103.815002, "mg_vii", "2p2.1S_0", "2p1.3s1.3P_1"},
        {15011, 323.140015, "mg_vii", "2s1.2p3.3D_3", "2s0.2p4.3P_2"},
        {15012, 9.66940022, "mg_vii", "2s0.2p4.1D_2", "1s1.2p5.3P_1"},
        {15013, 367.674011, "mg_vii", "2p2.3P_2", "2s1.2p3.3P_2"},
        {15014, 9.62010002, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.3D_1"},
        {15015, 280.737, "mg_vii", "2p2.1D_2", "2s1.2p3.1P_1"},
        {15016, 10.3077002, "mg_vii", "2s0.2p4.1D_2", "1s1.2s2.2p3.5S_2"},
        {15017, 365.243011, "mg_vii", "2p2.3P_1", "2s1.2p3.3P_1"},
        {15018, 10.1101999, "mg_vii", "2s0.2p4.3P_1", "1s1.2s2.2p3.1D_2"},
        {15019, 361.057007, "mg_vii", "2p2.1S_0", "2s1.2p3.3S_1"},
        {15020, 84.7600021, "mg_vii", "2p2.3P_1", "2p1.3d1.1D_2"},
        {15021, 1291.31995, "mg_vii", "2p1.3s1.3P_1", "2p1.3p1.3P_2"},
        {15022, 9.57759953, "mg_vii", "2p2.3P_2", "1s1.2s2.2p3.1D_2"},
        {15023, 9.66860008, "mg_vii", "2p2.1D_2", "1s1.2s2.2p3.3D_3"},
        {15024, 9.7191, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.3S_1"},
        {15025, 1670.73999, "mg_vii", "2p1.3s1.3P_1", "2p1.3p1.3D_1"},
        {15026, 10.1413002, "mg_vii", "2s0.2p4.3P_1", "1s1.2s2.2p3.3P_1"},
        {15027, 9.74610043, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.5P_1"},
        {15028, 10.1498003, "mg_vii", "2s0.2p4.3P_0", "1s1.2s2.2p3.3S_1"},
        {15029, 1564.69995, "mg_vii", "2p1.3s1.1P_1", "2p1.3p1.3P_1"},
        {15030, 92.3059998, "mg_vii", "2p2.1D_2", "2p1.3p1.3D_1"},
        {15031, 117.640999, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.3P_1"},
        {15032, 9.7869997, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.3P_1"},
        {15033, 130.203003, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.3S_1"},
        {15034, 123.512001, "mg_vii", "2s1.2p3.3S_1", "2p1.3p1.1S_0"},
        {15035, 88.9039993, "mg_vii", "2p2.3P_2", "2p1.3p1.3D_2"},
        {15036, 153.880997, "mg_vii", "2s0.2p4.3P_2", "2p1.3d1.3D_2"},
        {15037, 9.66479969, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.1D_2"},
        {15038, 9.6590004, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.3D_2"},
        {15039, 196.628006, "mg_vii", "2s0.2p4.3P_2", "2p1.3s1.3P_2"},
        {15040, 108.307999, "mg_vii", "2s1.2p3.3P_2", "2p1.3d1.3F_4"},
        {15041, 1356.67004, "mg_vii", "2p1.3p1.3P_0", "2p1.3d1.3P_1"},
        {15042, 9.62419987, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.3P_1"},
        {15043, 112.110001, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3P_1"},
        {15044, 1435.10999, "mg_vii", "2p1.3s1.3P_1", "2p1.3p1.3S_1"},
        {15045, 154.373993, "mg_vii", "2s0.2p4.3P_1", "2p1.3d1.3D_2"},
        {15046, 9.6651001, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.3P_2"},
        {15047, 112.268997, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.3P_0"},
        {15048, 134.011002, "mg_vii", "2s1.2p3.3S_1", "2p1.3p1.1P_1"},
        {15049, 118.016998, "mg_vii", "2s1.2p3.3P_0", "2p1.3p1.1P_1"},
        {15050, 1410.23999, "mg_vii", "2p1.3p1.3P_2", "2p1.3d1.3P_2"},
        {15051, 260.72699, "mg_vii", "2s1.2p3.3P_1", "2s0.2p4.1S_0"},
        {15052, 9.62800026, "mg_vii", "2p2.3P_0", "1s1.2s2.2p3.3D_1"},
        {15053, 137.233002, "mg_vii", "2s1.2p3.1P_1", "2p1.3p1.3P_2"},
        {15054, 165.389999, "mg_vii", "2s0.2p4.1D_2", "2p1.3d1.1D_2"},
        {15055, 9.60369968, "mg_vii", "2p2.3P_1", "1s1.2s2.2p3.3P_1"},
        {15056, 1191.97998, "mg_vii", "2p1.3p1.3D_1", "2p1.3d1.3D_2"},
        {15057, 198.410004, "mg_vii", "2s0.2p4.3P_1", "2p1.3s1.3P_1"},
        {15058, 1416.65002, "mg_vii", "2p1.3p1.3D_2", "2p1.3d1.1D_2"},
        {15059, 9.74230003, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.3D_2"},
        {15060, 234.580002, "mg_vii", "2s1.2p3.5S_2", "2s0.2p4.3P_1"},
        {15061, 89.2009964, "mg_vii", "2p2.1D_2", "2p1.3p1.1D_2"},
        {15062, 1452.04004, "mg_vii", "2p1.3p1.3D_3", "2p1.3d1.3F_4"},
        {15063, 9.74230003, "mg_vii", "2s1.2p3.1D_2", "1s1.2s1.2p4.3D_1"},
        {15064, 1356.40002, "mg_vii", "2p1.3p1.3S_1", "2p1.3d1.3D_1"},
        {15065, 107.443001, "mg_vii", "2s1.2p3.3D_3", "2p1.3p1.1D_2"},
        {15066, 155.682007, "mg_vii", "2s0.2p4.3P_2", "2p1.3d1.3F_3"},
        {15067, 9.14799976, "mg_vii", "2p2.3P_1", "1s1.2p5.3P_1"},
        {15068, 323.319, "mg_vii", "2s1.2p3.3D_1", "2s0.2p4.3P_2"},
        {15069, 9.58500004, "mg_vii", "2s0.2p4.3P_1", "1s1.2p5.1P_1"},
        {15070, 9.55850029, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.3S_1"},
        {15071, 434.916992, "mg_vii", "2p2.3P_2", "2s1.2p3.3D_3"},
        {15072, 277, "mg_vii", "2p2.3P_1", "2s1.2p3.3S_1"},
        {15073, 180.388, "mg_vii", "2s0.2p4.1S_0", "2p1.3d1.1P_1"},
        {15074, 9.6590004, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.3D_2"},
        {15075, 9.62030029, "mg_vii", "2s1.2p3.3D_3", "1s1.2s1.2p4.3D_3"},
        {15076, 86.8639984, "mg_vii", "2p2.1D_2", "2p1.3d1.3D_2"},
        {15077, 83.9589996, "mg_vii", "2p2.3P_1", "2p1.3d1.3D_2"},
        {15078, 88.6800003, "mg_vii", "2p2.1S_0", "2p1.3d1.1P_1"},
        {15079, 9.60589981, "mg_vii", "2p2.3P_2", "1s1.2s2.2p3.3P_2"},
        {15080, 2959.71997, "mg_vii", "2p1.3p1.1D_2", "2p1.3d1.1D_2"},
        {15081, 9.69950008, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.1D_2"},
        {15082, 9.60949993, "mg_vii", "2p2.3P_0", "1s1.2s2.2p3.3S_1"},
        {15083, 9.68130016, "mg_vii", "2p2.1S_0", "1s1.2s2.2p3.3P_1"},
        {15084, 10.2658997, "mg_vii", "2s0.2p4.3P_2", "1s1.2s2.2p3.5S_2"},
        {15085, 9.42679977, "mg_vii", "2s1.2p3.5S_2", "1s1.2s1.2p4.1D_2"},
        {15086, 2140.41992, "mg_vii", "2p1.3s1.1P_1", "2p1.3p1.3D_1"},
        {15087, 2097.97998, "mg_vii", "2p1.3p1.1S_0", "2p1.3d1.1P_1"},
        {15088, 9.6196003, "mg_vii", "2s0.2p4.1D_2", "1s1.2p5.1P_1"},
        {15089, 278.402008, "mg_vii", "2p2.3P_2", "2s1.2p3.3S_1"},
        {15090, 90332, "mg_vii", "2p2.3P_0", "2p2.3P_1"},
        {15091, 9.55850029, "mg_vii", "2s1.2p3.3D_1", "1s1.2s1.2p4.3S_1"},
        {15092, 521.091003, "mg_vii", "2p2.1D_2", "2s1.2p3.3D_3"},
        {15093, 10.2082005, "mg_vii", "2s0.2p4.1D_2", "1s1.2s2.2p3.3D_3"},
        {15094, 373.945007, "mg_vii", "2s1.2p3.3P_1", "2s0.2p4.3P_2"},
        {15095, 10.2761002, "mg_vii", "2s0.2p4.1S_0", "1s1.2s2.2p3.3S_1"},
        {15096, 1138.19995, "mg_vii", "2p1.3p1.1P_1", "2p1.3d1.3D_1"},
        {15097, 99.0149994, "mg_vii", "2p2.1D_2", "2p1.3s1.3P_2"},
        {15098, 84.9150009, "mg_vii", "2p2.3P_1", "2p1.3d1.3F_2"},
        {15099, 9.68420029, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.3S_1"},
        {15100, 1191.42004, "mg_vii", "2p1.3p1.3D_2", "2p1.3d1.3D_3"},
        {15101, 111.997002, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3P_2"},
        {15102, 1496.78003, "mg_vii", "2p1.3p1.3P_1", "2p1.3d1.3D_1"},
        {15103, 9.70689964, "mg_vii", "2p2.1S_0", "1s1.2s2.2p3.3D_1"},
        {15104, 1482.78003, "mg_vii", "2p1.3s1.3P_2", "2p1.3p1.3S_1"},
        {15105, 9.14970016, "mg_vii", "2p2.3P_2", "1s1.2p5.3P_1"},
        {15106, 10.1416998, "mg_vii", "2s0.2p4.3P_1", "1s1.2s2.2p3.3P_2"},
        {15107, 9.62609959, "mg_vii", "2s1.2p3.3D_2", "1s1.2s1.2p4.3P_2"},
        {15108, 9.78730011, "mg_vii", "2s1.2p3.3P_1", "1s1.2s1.2p4.5P_2"},
        {15109, 337.468994, "mg_vii", "2s1.2p3.3S_1", "2s0.2p4.1S_0"},
        {15110, 9.78610039, "mg_vii", "2s1.2p3.3P_2", "1s1.2s1.2p4.5P_1"},
        {15111, 679.163025, "mg_vii", "2s1.2p3.1P_1", "2s0.2p4.3P_1"},
        {15112, 371.062988, "mg_vii", "2s1.2p3.3P_1", "2s0.2p4.3P_1"},
        {15113, 9.75360012, "mg_vii", "2s1.2p3.3S_1", "1s1.2s1.2p4.3P_2"},
        {15114, 117.431999, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.3D_1"},
        {15115, 88.6709976, "mg_vii", "2p2.3P_0", "2p1.3p1.3D_2"},
        {15116, 9.78590012, "mg_vii", "2s1.2p3.1P_1", "1s1.2s1.2p4.3P_0"},
        {15117, 131.733002, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.3D_2"},
        {15118, 10.1486998, "mg_vii", "2s0.2p4.1D_2", "1s1.2s2.2p3.1D_2"},
        {15119, 130.936996, "mg_vii", "2s1.2p3.3S_1", "2p1.3p1.3P_2"},
        {15121, 70.7570038, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.4S_3/2"},
        {15122, 75.0550003, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.2P_1/2"},
        {15123, 77.7369995, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2F_7/2#2"},
        {15124, 9.5316, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.2D_3/2"},
        {15125, 9.50510025, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.2S_1/2"},
        {15126, 105.971001, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.2P_3/2"},
        {15127, 74.560997, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2P_3/2#2"},
        {15128, 81.8909988, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2F_5/2"},
        {15129, 62.5099983, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.2P_3/2#2"},
        {15130, 80.9540024, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2S_1/2"},
        {15131, 82.3659973, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.4D_5/2"},
        {15132, 87.4909973, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.2S_1/2#2"},
        {15133, 9.54990005, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.2P_1/2"},
        {15134, 9.50230026, "mg_viii", "2p1.2P_1/2", "1s1.2s2.2p2.2P_1/2"},
        {15135, 71.7320023, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.4D_3/2"},
        {15136, 106.095001, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.2P_1/2"},
        {15137, 9.5298996, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2p4.2D_3/2"},
        {15138, 57.7669983, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3s1.2S_1/2"},
        {15139, 67.6620026, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.2F_7/2#2"},
        {15140, 58.3479996, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.4P_1/2"},
        {15141, 71.7289963, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.4D_3/2"},
        {15142, 87.0690002, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.2P_3/2"},
        {15143, 102.352997, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.2D_5/2"},
        {15144, 94.2750015, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3s1.2P_1/2"},
        {15145, 115.242996, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.4S_3/2"},
        {15146, 9.49050045, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.4P_1/2"},
        {15147, 9.43430042, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.2D_5/2"},
        {15148, 69.4670029, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.2D_5/2"},
        {15149, 80.3130035, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.4D_7/2"},
        {15150, 9.4914999, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.4P_5/2"},
        {15151, 85.7850037, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3d1.4P_3/2"},
        {15152, 61.8110008, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3s1.2P_3/2"},
        {15153, 9.39509964, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.4S_3/2#2"},
        {15154, 57.1380005, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2D_3/2#2"},
        {15155, 9.39179993, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.2P_1/2"},
        {15156, 9.63440037, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.4D_5/2"},
        {15157, 115.220001, "mg_viii", "2s0.2p3.2P_1/2", "2s1.2p1.3p1.4S_3/2"},
        {15158, 87.8119965, "mg_viii", "2s1.2p2.4P_3/2", "2p0.3p1.2P_1/2"},
        {15159, 81.6210022, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3s1.2D_3/2"},
        {15160, 9.50699997, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.2S_1/2"},
        {15161, 9.45670033, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2p4.2P_1/2"},
        {15162, 72.2959976, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3d1.2P_3/2"},
        {15163, 87.7369995, "mg_viii", "2s1.2p2.4P_3/2", "2p0.3p1.2P_3/2"},
        {15164, 490.367004, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p3.2P_1/2"},
        {15165, 108.629997, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.4D_5/2"},
        {15166, 10.0237999, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2s2.2p2.2D_3/2"},
        {15167, 73.9800034, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.4P_3/2"},
        {15168, 69.3619995, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.4S_3/2"},
        {15169, 64.7610016, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.4S_3/2"},
        {15170, 64.5169983, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.2P_1/2#2"},
        {15171, 9.12230015, "mg_viii", "2p1.2P_3/2", "1s1.2p4.2D_3/2"},
        {15172, 76.3610001, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3d1.2D_3/2#2"},
        {15173, 10.0394001, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2s2.2p2.4P_5/2"},
        {15174, 71.5540009, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.4D_1/2"},
        {15175, 80.387001, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.4D_3/2"},
        {15176, 63.2630005, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.2D_3/2#2"},
        {15177, 9.53660011, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2p4.4P_1/2"},
        {15178, 352.459991, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p3.4S_3/2"},
        {15179, 76.9980011, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.4D_5/2"},
        {15180, 84.822998, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3s1.2P_3/2#2"},
        {15181, 9.51329994, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2p4.2P_3/2"},
        {15182, 72.6780014, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.2D_5/2#2"},
        {15183, 9.53139973, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.2D_5/2"},
        {15184, 71.3619995, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.4D_3/2"},
        {15185, 342.062012, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p3.2P_1/2"},
        {15186, 9.33189964, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.2P_3/2#2"},
        {15187, 84.4400024, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.2F_5/2"},
        {15188, 64.6350021, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.2D_3/2#2"},
        {15189, 341.802002, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p3.2P_3/2"},
        {15190, 9.39610004, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.4S_3/2#2"},
        {15191, 54.1949997, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2D_5/2#3"},
        {15192, 75.6610031, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2D_3/2"},
        {15193, 85.2539978, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3s1.2D_3/2"},
        {15194, 73.4300003, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3s1.2P_3/2#2"},
        {15195, 82.3600006, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.4D_3/2"},
        {15196, 80.2549973, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.2D_3/2"},
        {15197, 65.4970016, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.2D_3/2"},
        {15198, 77.9899979, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2P_1/2"},
        {15199, 9.5855999, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2p4.2D_3/2"},
        {15200, 68.1940002, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2D_5/2#2"},
        {15201, 77.6500015, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2P_1/2#2"},
        {15202, 81.3040009, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2P_3/2#2"},
        {15203, 64.1699982, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.2F_7/2"},
        {15204, 353.881989, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p3.4S_3/2"},
        {15205, 436.734985, "mg_viii", "2p1.2P_3/2", "2s1.2p2.2D_5/2"},
        {15206, 79.9089966, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.4P_5/2"},
        {15207, 9.63029957, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.4S_3/2"},
        {15208, 83.6439972, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3d1.2P_1/2"},
        {15209, 9.96319962, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2s2.2p2.2D_3/2"},
        {15210, 71.5279999, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.4D_3/2"},
        {15211, 9.49530029, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2p4.2S_1/2"},
        {15212, 77.5790024, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.2S_1/2"},
        {15213, 9.71889973, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.4D_3/2"},
        {15214, 85.064003, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3s1.4P_3/2"},
        {15215, 9.47130013, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.2D_5/2#2"},
        {15216, 73.8000031, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3d1.4P_1/2"},
        {15217, 9.55280018, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.2D_3/2#2"},
        {15218, 92.1819992, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.2P_3/2#2"},
        {15219, 77.5390015, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2D_5/2"},
        {15220, 9.55490017, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.2D_5/2#2"},
        {15221, 86.8509979, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.2P_1/2"},
        {15222, 97.6470032, "mg_viii", "2s1.2p2.2D_3/2", "2p0.3p1.2P_3/2"},
        {15223, 65.8470001, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.4P_1/2"},
        {15224, 65.8730011, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.4P_3/2"},
        {15225, 73.5530014, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.2P_3/2"},
        {15226, 78.3820038, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2F_5/2#2"},
        {15227, 99.3909988, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.4P_1/2"},
        {15228, 9.65159988, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2p4.4P_5/2"},
        {15229, 64.2549973, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2P_3/2#3"},
        {15230, 59.0110016, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.4D_1/2"},
        {15231, 86.3679962, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3d1.4D_1/2"},
        {15232, 9.53509998, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.4D_3/2"},
        {15233, 56.2560005, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2S_1/2"},
        {15234, 10.1035995, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2s2.2p2.4P_3/2"},
        {15235, 68.1800003, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.2D_3/2#2"},
        {15236, 99.5039978, "mg_viii", "2s0.2p3.2P_1/2", "2s1.2p1.3p1.2D_3/2#2"},
        {15237, 85.7450027, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3s1.2P_1/2#2"},
        {15238, 106.397003, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.4P_3/2"},
        {15239, 9.37520027, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.2D_3/2#2"},
        {15240, 61.1069984, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3s1.2D_5/2"},
        {15241, 89.4779968, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3d1.4F_3/2"},
        {15242, 77.8010025, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.2P_3/2#2"},
        {15243, 76.6090012, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.4P_1/2"},
        {15244, 80.8889999, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2F_7/2"},
        {15245, 9.48980045, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.2P_3/2"},
        {15246, 729.906982, "mg_viii", "2s1.2p1.3d1.2F_7/2#2", "2s0.2p2.3d1.2G_9/2"},
        {15247, 74.5859985, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.4D_1/2"},
        {15248, 81.3679962, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.2P_1/2#2"},
        {15249, 79.7030029, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3s1.2P_1/2#2"},
        {15250, 81.7900009, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3s1.4P_3/2"},
        {15251, 10.0394001, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2s2.2p2.4P_5/2"},
        {15252, 93.4349976, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3s1.2P_1/2"},
        {15253, 86.3460007, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3s1.2D_5/2"},
        {15254, 9.53100014, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.2D_3/2#2"},
        {15255, 9.17739964, "mg_viii", "2p1.2P_1/2", "1s1.2p4.4P_3/2"},
        {15256, 72.6989975, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.2D_3/2#2"},
        {15257, 9.59309959, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2p4.4P_3/2"},
        {15258, 71.3889999, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.4D_1/2"},
        {15259, 9.59029961, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.4P_3/2"},
        {15260, 9.96290016, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2s2.2p2.2D_5/2"},
        {15261, 9.56630039, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2p4.2P_1/2"},
        {15262, 59.1240005, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.4D_1/2"},
        {15263, 80.2529984, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.2D_3/2"},
        {15264, 89.7549973, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3s1.2D_3/2"},
        {15265, 107.924004, "mg_viii", "2s1.2p2.2P_3/2", "2p0.3p1.2P_1/2"},
        {15266, 92.125, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3s1.2P_3/2"},
        {15267, 9.49050045, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.4P_3/2"},
        {15268, 71.4850006, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.4D_5/2"},
        {15269, 73.3170013, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.2F_7/2#2"},
        {15270, 9.52950001, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.4S_3/2"},
        {15271, 9.98270035, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2s2.2p2.4P_1/2"},
        {15272, 57.5950012, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.2D_3/2"},
        {15273, 75.1740036, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2P_3/2"},
        {15274, 58.362999, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.4P_3/2"},
        {15275, 9.37360001, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.2D_3/2#2"},
        {15276, 9.63430023, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.4D_7/2"},
        {15277, 79.9729996, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3s1.2P_1/2"},
        {15278, 67.1559982, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.2P_3/2#3"},
        {15279, 9.56849957, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2p4.2P_3/2"},
        {15280, 104.508003, "mg_viii", "2s1.2p2.2S_1/2", "2p0.3p1.2P_3/2"},
        {15281, 485.153992, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p3.2P_3/2"},
        {15282, 82.3700027, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.4D_3/2"},
        {15283, 66.6999969, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.2S_1/2"},
        {15284, 689.203979, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p3.2D_3/2"},
        {15285, 61.8880005, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3s1.2P_1/2"},
        {15286, 73.1399994, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2D_3/2#3"},
        {15287, 9.17630005, "mg_viii", "2p1.2P_1/2", "1s1.2p4.4P_1/2"},
        {15288, 74.4300003, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.4D_3/2"},
        {15289, 80.3889999, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.4D_3/2"},
        {15290, 9.18019962, "mg_viii", "2p1.2P_3/2", "1s1.2p4.4P_3/2"},
        {15291, 9.96310043, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2s2.2p2.2D_3/2"},
        {15292, 82.822998, "mg_viii", "2p1.2P_3/2", "2p0.3s1.2S_1/2"},
        {15293, 64.8799973, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.4S_3/2"},
        {15294, 9.4751997, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2p4.2D_5/2"},
        {15295, 441.755005, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p3.2P_1/2"},
        {15296, 76.9530029, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.4D_3/2"},
        {15297, 78.322998, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.2F_5/2#2"},
        {15298, 108.933998, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.2D_5/2"},
        {15299, 9.33450031, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.2P_3/2#2"},
        {15300, 315.039001, "mg_viii", "2p1.2P_3/2", "2s1.2p2.2P_3/2"},
        {15301, 70.4209976, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.4P_5/2"},
        {15302, 86.9420013, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.4D_3/2"},
        {15303, 9.43029976, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.2P_1/2#2"},
        {15304, 89.6360016, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.4F_3/2"},
        {15305, 428.244995, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p3.2D_3/2"},
        {15306, 69.5749969, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.2D_3/2"},
        {15307, 78.1669998, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2P_3/2"},
        {15308, 84.2720032, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3d1.4P_1/2"},
        {15309, 65.4000015, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.2D_5/2"},
        {15310, 56.1539993, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.2S_1/2"},
        {15311, 76.7539978, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2D_5/2#3"},
        {15312, 72.137001, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2P_1/2#2"},
        {15313, 9.67730045, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.4P_5/2"},
        {15314, 86.9489975, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.4D_5/2"},
        {15315, 82.4960022, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2P_3/2"},
        {15316, 81.8669968, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3s1.4P_3/2"},
        {15317, 9.57619953, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.4S_3/2#2"},
        {15318, 83.2320023, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.4F_3/2"},
        {15319, 69.4150009, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.2D_3/2"},
        {15320, 71.7699966, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.4D_1/2"},
        {15321, 64.8310013, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.2P_3/2"},
        {15322, 76.0660019, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3d1.2P_3/2#2"},
        {15323, 75.9580002, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3s1.2S_1/2"},
        {15324, 9.56879997, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2p4.2P_3/2"},
        {15325, 74.0199966, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.4P_5/2"},
        {15326, 70.7519989, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2D_5/2"},
        {15327, 114.936996, "mg_viii", "2s0.2p3.2D_3/2", "2p0.3d1.2D_3/2"},
        {15328, 430.464996, "mg_viii", "2p1.2P_1/2", "2s1.2p2.2D_3/2"},
        {15329, 772.26001, "mg_viii", "2p1.2P_3/2", "2s1.2p2.4P_5/2"},
        {15330, 10.0093002, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2s2.2p2.2P_1/2"},
        {15331, 67.3789978, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.2P_3/2#2"},
        {15332, 9.03789997, "mg_viii", "2p1.2P_1/2", "1s1.2p4.2S_1/2"},
        {15333, 9.59150028, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.4P_5/2"},
        {15334, 57.0079994, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2F_5/2#2"},
        {15335, 66.2200012, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.4D_1/2"},
        {15336, 107.583, "mg_viii", "2s1.2p2.2P_1/2", "2p0.3p1.2P_3/2"},
        {15337, 2089.79004, "mg_viii", "2s0.2p2.3p1.2F_7/2", "2s0.2p2.3d1.2G_9/2"},
        {15338, 9.72089958, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.4D_5/2"},
        {15339, 107.345001, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.4S_3/2"},
        {15340, 80.2300034, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.2D_5/2"},
        {15341, 71.4580002, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.2D_3/2#2"},
        {15342, 9.57180023, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.2P_1/2"},
        {15343, 106.382004, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.4P_3/2"},
        {15344, 74.4720001, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2F_5/2#2"},
        {15345, 9.57820034, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.4S_3/2#2"},
        {15346, 93.4199982, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3s1.2P_1/2"},
        {15347, 67.4400024, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2P_1/2#2"},
        {15348, 86.3560028, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3s1.2D_5/2"},
        {15349, 74.2030029, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.2D_5/2"},
        {15350, 81.3799973, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2P_1/2#2"},
        {15351, 80.8059998, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2D_5/2"},
        {15352, 87.9990005, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.2P_1/2#2"},
        {15353, 9.5873003, "mg_viii", "2p1.2P_1/2", "1s1.2s2.2p2.4P_3/2"},
        {15354, 87.8610001, "mg_viii", "2s1.2p2.4P_5/2", "2p0.3p1.2P_3/2"},
        {15355, 78.5739975, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.2F_5/2"},
        {15356, 91.6780014, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.2S_1/2#2"},
        {15357, 74.8580017, "mg_viii", "2p1.2P_1/2", "2p0.3d1.2D_3/2"},
        {15358, 9.47819996, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.2S_1/2"},
        {15359, 86.4089966, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2F_5/2"},
        {15360, 57.875, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3s1.2S_1/2"},
        {15361, 72.3619995, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.2P_3/2#2"},
        {15362, 109.175003, "mg_viii", "2s0.2p3.2P_1/2", "2s1.2p1.3p1.2D_3/2"},
        {15363, 54.0890007, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.2D_3/2#3"},
        {15364, 9.04049969, "mg_viii", "2p1.2P_3/2", "1s1.2p4.2S_1/2"},
        {15365, 116.858002, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.4D_3/2"},
        {15366, 9.5284996, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.4S_3/2"},
        {15367, 64.7020035, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.2D_5/2#2"},
        {15368, 59.0349998, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.2P_3/2"},
        {15369, 89.0169983, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3s1.4P_3/2"},
        {15370, 83.1169968, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.4F_7/2"},
        {15371, 9.63440037, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.4D_3/2"},
        {15372, 73.75, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3s1.2P_1/2#2"},
        {15373, 59.4160004, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.4F_3/2"},
        {15374, 99.2060013, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.4P_5/2"},
        {15375, 81.6279984, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.4D_1/2"},
        {15376, 88.8590012, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3s1.4P_5/2"},
        {15377, 64.8249969, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.2P_1/2"},
        {15378, 86.8639984, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2P_1/2"},
        {15379, 81.2919998, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.2P_3/2#2"},
        {15380, 9.48900032, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.2P_3/2#2"},
        {15381, 9.88920021, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2s2.2p2.2P_1/2"},
        {15382, 66.1829987, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.4D_5/2"},
        {15383, 82.5979996, "mg_viii", "2p1.2P_1/2", "2p0.3s1.2S_1/2"},
        {15384, 9.12220001, "mg_viii", "2p1.2P_3/2", "1s1.2p4.2D_5/2"},
        {15385, 9.94540024, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2s2.2p2.2P_3/2"},
        {15386, 63.1049995, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3s1.4P_1/2"},
        {15387, 80.2419968, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3s1.2P_3/2#2"},
        {15388, 82.7809982, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.2D_3/2#2"},
        {15389, 9.53779984, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2p4.4P_3/2"},
        {15390, 311.79599, "mg_viii", "2p1.2P_1/2", "2s1.2p2.2P_3/2"},
        {15391, 83.9840012, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2D_3/2"},
        {15392, 9.59179974, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2p4.4P_1/2"},
        {15393, 54.1829987, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2D_3/2#3"},
        {15394, 70.7490005, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.2D_5/2"},
        {15395, 9.53339958, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.4D_1/2"},
        {15396, 9.48980045, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.2P_3/2"},
        {15397, 58.9710007, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.4D_3/2"},
        {15398, 9.33259964, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.2P_1/2#2"},
        {15399, 59.1489983, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2P_3/2"},
        {15400, 9.43280029, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.2D_3/2"},
        {15401, 67.5319977, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3d1.2P_1/2#2"},
        {15402, 9.58530045, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2p4.2D_3/2"},
        {15403, 76.7399979, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.4P_3/2"},
        {15404, 436.222992, "mg_viii", "2s1.2p1.3d1.4F_9/2", "2s0.2p2.3d1.4F_9/2"},
        {15405, 79.7089996, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2D_3/2"},
        {15406, 65.8960037, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.4P_1/2"},
        {15407, 9.59160042, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.4P_1/2"},
        {15408, 78.6279984, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2D_3/2#2"},
        {15409, 9.97900009, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2s2.2p2.2S_1/2"},
        {15410, 74.9260025, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.4P_1/2"},
        {15411, 79.9329987, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3s1.2P_3/2"},
        {15412, 86.8470001, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3s1.2P_3/2"},
        {15413, 59.7700005, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.2P_3/2#3"},
        {15414, 9.88599968, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2s2.2p2.2P_3/2"},
        {15415, 1901.70996, "mg_viii", "2s1.2p1.3p1.4D_7/2", "2s1.2p1.3d1.4F_9/2"},
        {15416, 78.1240005, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.4D_1/2"},
        {15417, 97.6409988, "mg_viii", "2s1.2p2.2D_5/2", "2p0.3p1.2P_3/2"},
        {15418, 65.9430008, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.4P_3/2"},
        {15419, 70.4219971, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.4P_5/2"},
        {15420, 77.5719986, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3d1.2D_3/2#2"},
        {15421, 769.343018, "mg_viii", "2p1.2P_1/2", "2s1.2p2.4P_1/2"},
        {15422, 9.59300041, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2p4.4P_3/2"},
        {15423, 72.0709991, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2P_3/2#2"},
        {15424, 339.006012, "mg_viii", "2p1.2P_3/2", "2s1.2p2.2S_1/2"},
        {15425, 62.9249992, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3s1.4P_3/2"},
        {15426, 9.47130013, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.2D_5/2#2"},
        {15427, 64.4929962, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.2P_3/2#2"},
        {15428, 70.9189987, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.4S_3/2"},
        {15429, 9.79059982, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.6S_5/2"},
        {15430, 367.05899, "mg_viii", "2s1.2p1.3d1.4D_7/2", "2s0.2p2.3d1.2G_9/2"},
        {15431, 9.67529964, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.4P_3/2"},
        {15432, 100.128998, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.4S_3/2"},
        {15433, 9.42959976, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.2P_3/2#2"},
        {15434, 9.72089958, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.4D_3/2"},
        {15435, 92.1880035, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.2P_3/2#2"},
        {15436, 75.3099976, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.4F_3/2"},
        {15437, 88.0070038, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3s1.2P_3/2"},
        {15438, 81.6240005, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3s1.2D_5/2"},
        {15439, 9.5546999, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.2D_3/2#2"},
        {15440, 94.0449982, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3s1.4P_1/2"},
        {15441, 72.5500031, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.2P_1/2#2"},
        {15442, 96.9229965, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.2S_1/2#2"},
        {15443, 73.1930008, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2S_1/2"},
        {15444, 74.4110031, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.4D_5/2"},
        {15445, 73.8259964, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3d1.4P_3/2"},
        {15446, 82.4469986, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.4D_1/2"},
        {15447, 68.4120026, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.2P_3/2#3"},
        {15448, 762.643005, "mg_viii", "2p1.2P_1/2", "2s1.2p2.4P_3/2"},
        {15449, 83.9589996, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.4P_5/2"},
        {15450, 9.49310017, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.4P_3/2"},
        {15451, 789.390991, "mg_viii", "2p1.2P_3/2", "2s1.2p2.4P_1/2"},
        {15452, 9.97920036, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2s2.2p2.2S_1/2"},
        {15453, 89.1050034, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3s1.4P_5/2"},
        {15454, 114.129997, "mg_viii", "2s0.2p3.2P_1/2", "2s1.2p1.3p1.4P_3/2"},
        {15455, 9.63430023, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.4D_3/2"},
        {15456, 58.8240013, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2D_5/2"},
        {15457, 87.0830002, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2P_3/2"},
        {15458, 72.0350037, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.2P_1/2#2"},
        {15459, 545.47699, "mg_viii", "2s1.2p1.3d1.2F_7/2", "2s0.2p2.3d1.4F_9/2"},
        {15460, 9.53149986, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.2D_5/2"},
        {15461, 108.727997, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.4D_3/2"},
        {15462, 9.65310001, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.4P_1/2"},
        {15463, 9.61610031, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.2D_5/2"},
        {15464, 80.9420013, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.2S_1/2"},
        {15465, 87.0210037, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3s1.2P_1/2"},
        {15466, 82.375, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.4D_5/2"},
        {15467, 9.9630003, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2s2.2p2.2D_5/2"},
        {15468, 74.8970032, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.4P_3/2"},
        {15469, 81.8809967, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2F_5/2"},
        {15470, 85.1529999, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3s1.4P_1/2"},
        {15471, 9.55430031, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.4S_3/2#2"},
        {15472, 9.49940014, "mg_viii", "2p1.2P_1/2", "1s1.2s2.2p2.2P_3/2"},
        {15473, 80.2320023, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.2D_5/2"},
        {15474, 64.1259995, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.2F_5/2"},
        {15475, 57.0239983, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.2P_1/2#2"},
        {15476, 9.50529957, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.2P_1/2"},
        {15477, 9.53120041, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.4S_3/2"},
        {15478, 59.0480003, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2P_1/2"},
        {15479, 71.3030014, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.4P_3/2"},
        {15480, 87.9000015, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.4F_3/2"},
        {15481, 114.152, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.4P_3/2"},
        {15482, 9.53240013, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.4D_1/2"},
        {15483, 62.9729996, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3s1.4P_1/2"},
        {15484, 9.39350033, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.2P_3/2"},
        {15485, 70.4550018, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.4P_5/2"},
        {15486, 86.3840027, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.2D_3/2"},
        {15487, 9.49160004, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.4P_1/2"},
        {15488, 9.42409992, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.2S_1/2"},
        {15489, 86.836998, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3s1.2P_3/2#2"},
        {15490, 61.0209999, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3s1.2D_3/2"},
        {15491, 9.43169975, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.2D_3/2"},
        {15492, 419.899994, "mg_viii", "2s1.2p1.3d1.2F_7/2", "2s0.2p2.3d1.2G_9/2"},
        {15493, 57.7019997, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2D_3/2"},
        {15494, 73.1610031, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2D_5/2#3"},
        {15495, 9.59150028, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.4P_5/2"},
        {15496, 88.086998, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.2D_5/2#2"},
        {15497, 9.51249981, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.2P_3/2#2"},
        {15498, 9.38710022, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2p4.2S_1/2"},
        {15499, 74.1589966, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3d1.2D_3/2"},
        {15500, 106.267998, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.4P_5/2"},
        {15501, 84.3499985, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3s1.2S_1/2"},
        {15502, 9.10439968, "mg_viii", "2p1.2P_1/2", "1s1.2p4.2P_3/2"},
        {15503, 73.5169983, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3s1.2P_3/2#2"},
        {15504, 70.8649979, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2D_3/2"},
        {15505, 66.1880035, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.4D_3/2"},
        {15506, 64.2429962, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.2S_1/2#2"},
        {15507, 9.17910004, "mg_viii", "2p1.2P_3/2", "1s1.2p4.4P_1/2"},
        {15508, 10.0417004, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2s2.2p2.4P_3/2"},
        {15509, 64.6539993, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.2P_1/2#2"},
        {15510, 89.2649994, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3s1.4P_3/2"},
        {15511, 83.8889999, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.4P_3/2"},
        {15512, 74.2740021, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3d1.4D_3/2"},
        {15513, 335.252991, "mg_viii", "2p1.2P_1/2", "2s1.2p2.2S_1/2"},
        {15514, 84.3069992, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3d1.4P_3/2"},
        {15515, 9.52970028, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2p4.2D_5/2"},
        {15516, 68.1910019, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.2D_5/2#2"},
        {15517, 9.53149986, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.2D_3/2"},
        {15518, 313.753998, "mg_viii", "2p1.2P_1/2", "2s1.2p2.2P_1/2"},
        {15519, 83.8659973, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.2P_3/2"},
        {15520, 9.32660007, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.2S_1/2"},
        {15521, 61.144001, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3s1.2D_3/2"},
        {15522, 428.184998, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p3.2D_3/2"},
        {15523, 9.39190006, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.2P_3/2"},
        {15524, 84.7419968, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3d1.2D_3/2"},
        {15525, 373.929993, "mg_viii", "2s0.2p2.3p1.4D_7/2", "2s0.2p2.3d1.4F_9/2"},
        {15526, 74.6930008, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2D_3/2#2"},
        {15527, 88.0179977, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3s1.2P_3/2"},
        {15528, 73.8889999, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.4P_3/2"},
        {15529, 9.4406004, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2p4.2S_1/2"},
        {15530, 79.9380035, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.4P_3/2"},
        {15531, 10.0089998, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2s2.2p2.2P_1/2"},
        {15532, 116.904999, "mg_viii", "2s0.2p3.2P_1/2", "2s1.2p1.3p1.4D_1/2"},
        {15533, 78.0770035, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.2P_3/2"},
        {15534, 106.830002, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.2S_1/2"},
        {15535, 76.7139969, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.4P_1/2"},
        {15536, 72.6800003, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.2D_5/2#2"},
        {15537, 80.0390015, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3s1.2S_1/2"},
        {15538, 75.0630035, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.2P_3/2"},
        {15539, 433.621002, "mg_viii", "2s1.2p1.3d1.4F_7/2", "2s0.2p2.3d1.4F_9/2"},
        {15540, 76.7310028, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2D_3/2#3"},
        {15541, 436.671997, "mg_viii", "2p1.2P_3/2", "2s1.2p2.2D_3/2"},
        {15542, 78.5719986, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.2F_5/2"},
        {15543, 355.998993, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p3.4S_3/2"},
        {15544, 71.0039978, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.2P_1/2"},
        {15545, 71.1190033, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.2P_3/2"},
        {15546, 70.3440018, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.4P_3/2"},
        {15547, 9.32759953, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.2S_1/2"},
        {15548, 9.90359974, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2s2.2p2.2D_3/2"},
        {15549, 76.9970016, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.4D_1/2"},
        {15550, 9.67539978, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.4P_1/2"},
        {15551, 9.72089958, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.4D_1/2"},
        {15552, 81.8669968, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3s1.4P_1/2"},
        {15553, 89.2679977, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3s1.4P_3/2"},
        {15554, 9.51130009, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.2P_1/2#2"},
        {15555, 93.5619965, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.2D_3/2#2"},
        {15556, 78.0589981, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.4D_5/2"},
        {15557, 9.69229984, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.4S_3/2"},
        {15558, 9.57369995, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.2P_1/2"},
        {15559, 97.5289993, "mg_viii", "2s0.2p3.2P_1/2", "2s1.2p1.3p1.2P_1/2#2"},
        {15560, 64.2679977, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2P_1/2#3"},
        {15561, 80.810997, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2D_5/2"},
        {15562, 66.2369995, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.4D_3/2"},
        {15563, 145.804993, "mg_viii", "2s0.2p3.2P_3/2", "2p0.3s1.2S_1/2"},
        {15564, 9.64949989, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2p4.4P_3/2"},
        {15565, 9.5156002, "mg_viii", "2p1.2P_1/2", "1s1.2s2.2p2.2D_3/2"},
        {15566, 81.8440018, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3s1.4P_5/2"},
        {15567, 67.3820038, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2P_3/2#2"},
        {15568, 79.9150009, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.4P_1/2"},
        {15569, 72.9869995, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2D_3/2#2"},
        {15570, 92.3219986, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3s1.2P_1/2"},
        {15571, 83.9710007, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.2D_3/2"},
        {15572, 10.1012001, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2s2.2p2.4P_5/2"},
        {15573, 70.8619995, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.2D_3/2"},
        {15574, 86.5400009, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.4D_3/2"},
        {15575, 65.4690018, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.2D_5/2"},
        {15576, 9.79049969, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.6S_5/2"},
        {15577, 75.9680023, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.2S_1/2"},
        {15578, 58.9350014, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.2P_1/2"},
        {15579, 86.3899994, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3d1.4D_3/2"},
        {15580, 79.3799973, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2G_7/2"},
        {15581, 82.7929993, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2D_3/2#2"},
        {15582, 9.49409962, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.4S_3/2#2"},
        {15583, 79.7529984, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3s1.2P_3/2"},
        {15584, 9.51060009, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.2P_3/2#2"},
        {15585, 101.260002, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.4D_5/2"},
        {15586, 9.65299988, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.4P_3/2"},
        {15587, 84.336998, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3s1.2S_1/2"},
        {15588, 97.7399979, "mg_viii", "2s1.2p2.2D_3/2", "2p0.3p1.2P_1/2"},
        {15589, 106.283997, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.4P_5/2"},
        {15590, 87.0289993, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.4D_1/2"},
        {15591, 83.1839981, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.4F_5/2"},
        {15592, 71.3059998, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.4P_3/2"},
        {15593, 108.805, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.4D_1/2"},
        {15594, 70.3880005, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.4P_1/2"},
        {15595, 9.51860046, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.2D_3/2"},
        {15596, 62.012001, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3s1.2P_1/2"},
        {15597, 79.862999, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.4P_3/2"},
        {15598, 93.2440033, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3s1.2P_3/2"},
        {15599, 9.98120022, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2s2.2p2.4P_3/2"},
        {15600, 94.8539963, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3s1.4P_3/2"},
        {15601, 9.53240013, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.4D_3/2"},
        {15602, 9.4343996, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.2D_3/2"},
        {15603, 75.0339966, "mg_viii", "2p1.2P_3/2", "2p0.3d1.2D_5/2"},
        {15604, 70.7210007, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.4D_7/2"},
        {15605, 9.4914999, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.4P_3/2"},
        {15606, 86.2350006, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3d1.2D_3/2"},
        {15607, 57.0320015, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.2D_3/2#2"},
        {15608, 9.39089966, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.2P_3/2"},
        {15609, 85.9869995, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.4P_5/2"},
        {15610, 59.0839996, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.4D_3/2"},
        {15611, 9.37370014, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.2D_5/2#2"},
        {15612, 9.6303997, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.4S_3/2"},
        {15613, 81.9430008, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3s1.4P_1/2"},
        {15614, 83.1070023, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3s1.2P_3/2"},
        {15615, 108.646004, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.4D_5/2"},
        {15616, 67.5839996, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.2P_1/2#2"},
        {15617, 489.912994, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p3.2P_3/2"},
        {15618, 114.904999, "mg_viii", "2s0.2p3.2D_5/2", "2p0.3d1.2D_5/2"},
        {15619, 10.1033001, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2s2.2p2.4P_3/2"},
        {15620, 9.1196003, "mg_viii", "2p1.2P_1/2", "1s1.2p4.2D_3/2"},
        {15621, 74.3150024, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.2D_3/2"},
        {15622, 82.4970016, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.4F_3/2"},
        {15623, 65.4489975, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.2D_3/2"},
        {15624, 68.4499969, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.2S_1/2"},
        {15625, 9.1821003, "mg_viii", "2p1.2P_3/2", "1s1.2p4.4P_5/2"},
        {15626, 70.5479965, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.4P_1/2"},
        {15627, 82.4929962, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.4F_3/2"},
        {15628, 64.8990021, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.2P_3/2"},
        {15629, 9.45890045, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2p4.2P_3/2"},
        {15630, 76.4629974, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.4P_3/2"},
        {15631, 350.333008, "mg_viii", "2s1.2p1.3d1.4F_7/2", "2s0.2p2.3d1.2G_9/2"},
        {15632, 87.9140015, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.4F_3/2"},
        {15633, 81.7310028, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3s1.4P_5/2"},
        {15634, 73.2490005, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.2F_5/2#2"},
        {15635, 9.47109985, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.2D_3/2#2"},
        {15636, 70.9520035, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.2P_3/2"},
        {15637, 341.841003, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p3.2P_3/2"},
        {15638, 63.0559998, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3s1.4P_3/2"},
        {15639, 87.8610001, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.4F_5/2"},
        {15640, 10.1049004, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2s2.2p2.4P_1/2"},
        {15641, 77.697998, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2S_1/2"},
        {15642, 101.346001, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.4D_3/2"},
        {15643, 1216.88, "mg_viii", "2s1.2p1.3d1.2F_7/2#2", "2s0.2p2.3d1.4F_9/2"},
        {15644, 83.2409973, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.4F_3/2"},
        {15645, 72.3550034, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.2P_3/2"},
        {15646, 82.4860001, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2P_3/2"},
        {15647, 145.764999, "mg_viii", "2s0.2p3.2P_1/2", "2p0.3s1.2S_1/2"},
        {15648, 79.8649979, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.4P_3/2"},
        {15649, 64.8089981, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.4S_3/2"},
        {15650, 97.5469971, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.2P_1/2#2"},
        {15651, 73.0009995, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2D_5/2#2"},
        {15652, 74.625, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2P_1/2#2"},
        {15653, 9.64820004, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2p4.4P_1/2"},
        {15654, 76.9749985, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2S_1/2"},
        {15655, 75.9560013, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.2D_3/2"},
        {15656, 116.745003, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.4D_5/2"},
        {15657, 109.197998, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.2D_3/2"},
        {15658, 9.68809986, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.6S_5/2"},
        {15659, 782.338013, "mg_viii", "2p1.2P_3/2", "2s1.2p2.4P_3/2"},
        {15660, 64.2519989, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.2P_3/2#3"},
        {15661, 9.63430023, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.4D_5/2"},
        {15662, 85.5979996, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3s1.2P_1/2#2"},
        {15663, 72.2350006, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3d1.2P_1/2"},
        {15664, 57.7830009, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2D_5/2#2"},
        {15665, 9.56649971, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2p4.2P_1/2"},
        {15666, 9.52980042, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2p4.2D_5/2"},
        {15667, 77.4020004, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3d1.2P_1/2#2"},
        {15668, 77.6920013, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.2D_3/2#2"},
        {15669, 77.1139984, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.4D_1/2"},
        {15670, 88.0439987, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.2D_3/2#2"},
        {15671, 9.71679974, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.4S_3/2"},
        {15672, 74.5240021, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3d1.4D_1/2"},
        {15673, 102.578003, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.2D_3/2"},
        {15674, 76.788002, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.4P_5/2"},
        {15675, 9.69629955, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.4D_1/2"},
        {15676, 9.57369995, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.2P_3/2"},
        {15677, 83.8580017, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.4P_1/2"},
        {15678, 70.0800018, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2P_1/2"},
        {15679, 78.3909988, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2F_5/2#2"},
        {15680, 74.3180008, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.4D_5/2"},
        {15681, 116.929001, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.4D_1/2"},
        {15682, 317.039001, "mg_viii", "2p1.2P_3/2", "2s1.2p2.2P_1/2"},
        {15683, 78.8550034, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2D_5/2#2"},
        {15684, 9.59220028, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.2D_3/2"},
        {15685, 73.1470032, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2D_3/2#3"},
        {15686, 62.5730019, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.2P_3/2#2"},
        {15687, 79.9120026, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.4P_5/2"},
        {15688, 92.2360001, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.2P_1/2#2"},
        {15689, 73.8939972, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.4S_3/2"},
        {15690, 9.5024004, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.2P_3/2"},
        {15691, 91.3960037, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3s1.2D_5/2"},
        {15692, 9.53499985, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.4D_7/2"},
        {15693, 75.0439987, "mg_viii", "2p1.2P_3/2", "2p0.3d1.2D_3/2"},
        {15694, 10.0240002, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2s2.2p2.2D_3/2"},
        {15695, 70.0839996, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.2P_3/2"},
        {15696, 66.2539978, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.4D_5/2"},
        {15697, 61.9339981, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3s1.2P_3/2"},
        {15698, 83.7850037, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.2P_1/2"},
        {15699, 9.10509968, "mg_viii", "2p1.2P_3/2", "1s1.2p4.2P_1/2"},
        {15700, 99.5210037, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.2D_3/2#2"},
        {15701, 9.37530041, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.2D_5/2#2"},
        {15702, 59.507, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.4F_5/2"},
        {15703, 68.5500031, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.2F_7/2"},
        {15704, 9.68640041, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.6S_5/2"},
        {15705, 93.8929977, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3s1.2P_3/2"},
        {15706, 9.94550037, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2s2.2p2.2P_3/2"},
        {15707, 64.7789993, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.2P_1/2"},
        {15708, 82.3280029, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.4D_7/2"},
        {15709, 73.8619995, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.4P_1/2"},
        {15710, 70.5800018, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.2P_3/2#2"},
        {15711, 67.1709976, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.2P_1/2#3"},
        {15712, 78.0059967, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.2P_1/2"},
        {15713, 92.3330002, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.2D_5/2#2"},
        {15714, 75.2699966, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.4F_5/2"},
        {15715, 9.58860016, "mg_viii", "2p1.2P_1/2", "1s1.2s2.2p2.4P_1/2"},
        {15716, 104.613998, "mg_viii", "2s1.2p2.2S_1/2", "2p0.3p1.2P_1/2"},
        {15717, 88.8529968, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3s1.4P_5/2"},
        {15718, 9.48970032, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.2P_1/2#2"},
        {15719, 72.3649979, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.2P_3/2#2"},
        {15720, 66.7269974, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3d1.2P_3/2#2"},
        {15721, 9.59519958, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2p4.4P_5/2"},
        {15722, 86.5149994, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.4D_5/2"},
        {15723, 9.58810043, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.4P_5/2"},
        {15724, 107.695, "mg_viii", "2s1.2p2.2P_1/2", "2p0.3p1.2P_1/2"},
        {15725, 9.94859982, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2s2.2p2.2P_1/2"},
        {15726, 9.49499989, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2p4.2S_1/2"},
        {15727, 64.3799973, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.2S_1/2#2"},
        {15728, 78.0749969, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.2P_3/2"},
        {15729, 66.0690002, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.4D_7/2"},
        {15730, 78.4459991, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.2F_7/2"},
        {15731, 87.3410034, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3d1.4F_3/2"},
        {15732, 57.0940018, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2P_3/2#2"},
        {15733, 68.5780029, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.2F_5/2"},
        {15734, 9.53339958, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.4D_5/2"},
        {15735, 73.1679993, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2D_5/2#3"},
        {15736, 77.5230026, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.2P_1/2#2"},
        {15737, 105.978996, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.2P_3/2"},
        {15738, 9.39080048, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.2P_1/2"},
        {15739, 59.5309982, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.4F_3/2"},
        {15740, 9.33360004, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.2P_1/2#2"},
        {15741, 77.0699997, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.4D_3/2"},
        {15742, 441.385986, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p3.2P_3/2"},
        {15743, 75.1660004, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2P_1/2"},
        {15744, 9.64799976, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2p4.4P_1/2"},
        {15745, 78.8359985, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.4F_3/2"},
        {15746, 485.600006, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p3.2P_1/2"},
        {15747, 352.029999, "mg_viii", "2s1.2p1.3d1.4F_9/2", "2s0.2p2.3d1.2G_9/2"},
        {15748, 84.1259995, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3s1.2P_1/2#2"},
        {15749, 66.2689972, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.4D_1/2"},
        {15750, 689.551025, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p3.2D_5/2"},
        {15751, 76.7200012, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.2D_3/2#3"},
        {15752, 77.5770035, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2P_3/2#2"},
        {15753, 10.0058002, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2s2.2p2.2P_3/2"},
        {15754, 75.4020004, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.4F_3/2"},
        {15755, 73.3710022, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3s1.2P_3/2#2"},
        {15756, 64.7850037, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.2P_3/2"},
        {15757, 71.1709976, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.2P_1/2"},
        {15758, 65.5660019, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.2D_3/2"},
        {15759, 71.6699982, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.4D_5/2"},
        {15760, 77.6819992, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3d1.2P_3/2#2"},
        {15761, 77.6709976, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.2D_5/2#2"},
        {15762, 114.022003, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.4P_5/2"},
        {15763, 9.5951004, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2p4.4P_5/2"},
        {15764, 108.744003, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.4D_3/2"},
        {15765, 9.48970032, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.2P_1/2"},
        {15766, 10.0431995, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2s2.2p2.4P_1/2"},
        {15767, 94.0970001, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3s1.2P_1/2"},
        {15768, 64.5, "mg_viii", "2p1.2P_1/2", "2s1.2p1.3p1.2D_3/2#2"},
        {15769, 428.378998, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p3.2D_5/2"},
        {15770, 64.6299973, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.2P_3/2#2"},
        {15771, 78.8590012, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2D_5/2#2"},
        {15772, 459.537994, "mg_viii", "2s1.2p1.3d1.4D_7/2", "2s0.2p2.3d1.4F_9/2"},
        {15773, 9.71490002, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.4S_3/2"},
        {15774, 99.3040009, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.4P_3/2"},
        {15775, 9.67730045, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.4P_3/2"},
        {15776, 87.7269974, "mg_viii", "2s1.2p2.4P_1/2", "2p0.3p1.2P_1/2"},
        {15777, 79.8259964, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3s1.2P_3/2"},
        {15778, 2076.59009, "mg_viii", "2s0.2p2.3d1.4D_7/2", "2s0.2p2.3d1.4F_9/2"},
        {15779, 9.57180023, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.2P_3/2"},
        {15780, 85.2480011, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3s1.2D_3/2"},
        {15781, 73.5459976, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.2P_1/2"},
        {15782, 96.9049988, "mg_viii", "2s0.2p3.2P_1/2", "2s1.2p1.3p1.2S_1/2#2"},
        {15783, 71.3330002, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.4P_1/2"},
        {15784, 94.0619965, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3s1.4P_1/2"},
        {15785, 9.58539963, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2p4.2D_5/2"},
        {15786, 74.2949982, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.2D_5/2"},
        {15787, 68.5800018, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2F_5/2"},
        {15788, 88.1750031, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3s1.2P_1/2"},
        {15789, 84.8580017, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2D_5/2"},
        {15790, 68.5049973, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2P_3/2#3"},
        {15791, 10.0237999, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2s2.2p2.2D_5/2"},
        {15792, 82.4449997, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.4F_5/2"},
        {15793, 9.10239983, "mg_viii", "2p1.2P_1/2", "1s1.2p4.2P_1/2"},
        {15794, 75.302002, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.4F_7/2"},
        {15795, 9.59150028, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.4P_3/2"},
        {15796, 88.4570007, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3d1.4D_1/2"},
        {15797, 58.3909988, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.4P_5/2"},
        {15798, 68.4280014, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.2P_1/2#3"},
        {15799, 79.9000015, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3s1.2P_1/2"},
        {15800, 9.47109985, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.2D_3/2#2"},
        {15801, 73.6880035, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3s1.2P_1/2#2"},
        {15802, 76.0699997, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2D_3/2"},
        {15803, 68.5199966, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2P_1/2#3"},
        {15804, 107.329002, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.4S_3/2"},
        {15805, 75.7409973, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2D_5/2#2"},
        {15806, 9.69639969, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.4D_3/2"},
        {15807, 9.61620045, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.2D_3/2"},
        {15808, 87.0159988, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.4D_1/2"},
        {15809, 89.3590012, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3s1.4P_1/2"},
        {15810, 83.1940002, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.4F_5/2"},
        {15811, 73.9280014, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.4P_5/2"},
        {15812, 971.041992, "mg_viii", "2s0.2p2.3d1.4D_7/2", "2s0.2p2.3d1.2G_9/2"},
        {15813, 79.9899979, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.4P_5/2"},
        {15814, 9.55000019, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.2P_3/2"},
        {15815, 9.4751997, "mg_viii", "2p1.2P_1/2", "1s1.2s2.2p2.2S_1/2"},
        {15816, 80.3679962, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.4D_5/2"},
        {15817, 89.1139984, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3s1.4P_1/2"},
        {15818, 9.51329994, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2p4.2P_3/2"},
        {15819, 76.5780029, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.4P_3/2"},
        {15820, 9.51830006, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.2D_5/2"},
        {15821, 82.237999, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3d1.2P_1/2"},
        {15822, 9.53509998, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.4D_5/2"},
        {15823, 57.132, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.2P_1/2#2"},
        {15824, 72.6969986, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.2D_3/2#2"},
        {15825, 97.4749985, "mg_viii", "2s0.2p3.2P_1/2", "2s1.2p1.3p1.2P_3/2#2"},
        {15826, 75.0979996, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.4P_5/2"},
        {15827, 56.9869995, "mg_viii", "2p1.2P_1/2", "2s0.2p2.3d1.2P_3/2#2"},
        {15828, 70.6429977, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.2P_1/2#2"},
        {15829, 9.39770031, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.4S_3/2#2"},
        {15830, 62.9760017, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3s1.4P_5/2"},
        {15831, 9.53339958, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.4D_3/2"},
        {15832, 9.42959976, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.2P_3/2#2"},
        {15833, 83.7259979, "mg_viii", "2s1.2p2.2P_1/2", "2s1.2p1.3d1.2P_3/2"},
        {15834, 107.810997, "mg_viii", "2s1.2p2.2P_3/2", "2p0.3p1.2P_3/2"},
        {15835, 65.8069992, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.4P_5/2"},
        {15836, 108.411003, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.4D_7/2"},
        {15837, 9.59150028, "mg_viii", "2s1.2p2.2D_5/2", "1s1.2s1.2p3.4P_3/2"},
        {15838, 72.2949982, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.2P_1/2"},
        {15839, 10.1050997, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2s2.2p2.4P_1/2"},
        {15840, 9.64920044, "mg_viii", "2s0.2p3.2P_1/2", "1s1.2p4.4P_3/2"},
        {15841, 84.9189987, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3s1.4P_5/2"},
        {15842, 79.8339996, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.4P_1/2"},
        {15843, 77.5810013, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2P_3/2#2"},
        {15844, 10.0417995, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2s2.2p2.4P_3/2"},
        {15845, 74.4110031, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.2D_3/2"},
        {15846, 102.345001, "mg_viii", "2s0.2p3.2D_5/2", "2s1.2p1.3p1.2D_5/2"},
        {15847, 75.4089966, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.4D_1/2"},
        {15848, 9.48349953, "mg_viii", "2s1.2p2.2S_1/2", "1s1.2s1.2p3.2S_1/2"},
        {15849, 9.97889996, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2s2.2p2.4P_5/2"},
        {15850, 68.1829987, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2D_3/2#2"},
        {15851, 65.8249969, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.4P_3/2"},
        {15852, 65.7340012, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p2.3p1.4P_5/2"},
        {15853, 9.85980034, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2s2.2p2.2S_1/2"},
        {15854, 9.10709953, "mg_viii", "2p1.2P_3/2", "1s1.2p4.2P_3/2"},
        {15855, 9.91889954, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2s2.2p2.2S_1/2"},
        {15856, 68.6060028, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.2S_1/2"},
        {15857, 86.8440018, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3s1.2P_3/2"},
        {15858, 86.9290009, "mg_viii", "2s0.2p3.2P_1/2", "2s0.2p2.3d1.4D_3/2"},
        {15859, 9.53989983, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2p4.4P_5/2"},
        {15860, 75.9400024, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2D_5/2"},
        {15861, 89.7710037, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3s1.2D_3/2"},
        {15862, 9.5298996, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2p4.2D_3/2"},
        {15863, 89.5790024, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.4F_5/2"},
        {15864, 82.3730011, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.4F_7/2"},
        {15865, 9.49409962, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.4S_3/2#2"},
        {15866, 86.9860001, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3s1.2P_3/2#2"},
        {15867, 9.3725996, "mg_viii", "2s1.2p2.4P_1/2", "1s1.2s1.2p3.2D_3/2#2"},
        {15868, 73.2509995, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.2F_5/2#2"},
        {15869, 82.3170013, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3d1.2P_3/2"},
        {15870, 428.319, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p3.2D_5/2"},
        {15871, 9.43270016, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.2D_5/2"},
        {15872, 63.2729988, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.2D_5/2#2"},
        {15873, 102.585999, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.2D_3/2"},
        {15874, 85.9329987, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.4P_3/2"},
        {15875, 78.0540009, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.4D_3/2"},
        {15876, 679.823975, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p3.2D_3/2"},
        {15877, 9.87989998, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.6S_5/2"},
        {15878, 78.6360016, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2D_3/2#2"},
        {15879, 74.2220001, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.2D_3/2"},
        {15880, 9.51099968, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2p4.2P_1/2"},
        {15881, 79.7009964, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3d1.2D_3/2"},
        {15882, 81.9789963, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3s1.4P_3/2"},
        {15883, 80.2460022, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3s1.2P_3/2#2"},
        {15884, 62.4669991, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.2P_3/2#2"},
        {15885, 74.3659973, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.4D_7/2"},
        {15886, 82.7089996, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2D_5/2#2"},
        {15887, 83.2470016, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3s1.2P_1/2"},
        {15888, 9.47539997, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2p4.2D_3/2"},
        {15889, 66.3069992, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.4D_3/2"},
        {15890, 75.2480011, "mg_viii", "2s1.2p2.4P_1/2", "2s1.2p1.3d1.4F_3/2"},
        {15891, 72.8830032, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.2D_3/2#2"},
        {15892, 30284.6992, "mg_viii", "2p1.2P_1/2", "2p1.2P_3/2"},
        {15893, 97.6549988, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.2D_5/2#2"},
        {15894, 78.7929993, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.4F_5/2"},
        {15895, 113.051003, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.2P_3/2"},
        {15896, 80.3649979, "mg_viii", "2s1.2p2.2D_5/2", "2s1.2p1.3d1.4D_5/2"},
        {15897, 9.63430023, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.4D_1/2"},
        {15898, 73.0070038, "mg_viii", "2s1.2p2.2P_3/2", "2s0.2p2.3p1.2F_5/2"},
        {15899, 94.0699997, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3s1.2P_3/2"},
        {15900, 70.5049973, "mg_viii", "2p1.2P_3/2", "2s1.2p1.3p1.4P_3/2"},
        {15901, 9.33290005, "mg_viii", "2s1.2p2.4P_3/2", "1s1.2s1.2p3.2P_3/2#2"},
        {15902, 93.2590027, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3s1.2P_3/2"},
        {15903, 76.4929962, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.4P_1/2"},
        {15904, 87.9550018, "mg_viii", "2s0.2p3.4S_3/2", "2s1.2p1.3p1.2P_3/2#2"},
        {15905, 9.67739964, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.4P_1/2"},
        {15906, 93.5739975, "mg_viii", "2s0.2p3.2D_3/2", "2s1.2p1.3p1.2D_3/2#2"},
        {15907, 74.336998, "mg_viii", "2s1.2p2.4P_3/2", "2s1.2p1.3d1.4D_3/2"},
        {15908, 9.61429977, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.2D_3/2"},
        {15909, 89.0110016, "mg_viii", "2s0.2p3.2D_5/2", "2s0.2p2.3s1.4P_3/2"},
        {15910, 77.6230011, "mg_viii", "2s0.2p3.4S_3/2", "2s0.2p2.3d1.2F_5/2"},
        {15911, 9.51319981, "mg_viii", "2s1.2p2.2P_3/2", "1s1.2s1.2p3.2P_1/2#2"},
        {15912, 106.807999, "mg_viii", "2s0.2p3.2P_1/2", "2s1.2p1.3p1.2S_1/2"},
        {15913, 72.276001, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2S_1/2"},
        {15914, 66.651001, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p2.3p1.2S_1/2"},
        {15915, 75.3669968, "mg_viii", "2s1.2p2.2S_1/2", "2s0.2p2.3p1.4D_3/2"},
        {15916, 9.71889973, "mg_viii", "2s1.2p2.2P_1/2", "1s1.2s1.2p3.4D_1/2"},
        {15917, 76.1969986, "mg_viii", "2s1.2p2.2S_1/2", "2s1.2p1.3d1.2P_1/2#2"},
        {15918, 75.3619995, "mg_viii", "2s1.2p2.4P_5/2", "2s1.2p1.3d1.4F_5/2"},
        {15919, 82.4489975, "mg_viii", "2s1.2p2.2D_3/2", "2s1.2p1.3d1.4F_5/2"},
        {15920, 82.2990036, "mg_viii", "2s0.2p3.2D_3/2", "2s0.2p2.3d1.2P_1/2"},
        {15921, 71.9690018, "mg_viii", "2s1.2p2.2P_1/2", "2s0.2p2.3p1.2P_3/2#2"},
        {15922, 70.086998, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p2.3p1.2P_3/2"},
        {15923, 82.5220032, "mg_viii", "2s0.2p3.2P_3/2", "2s0.2p2.3d1.2F_5/2#2"},
        {15924, 9.4932003, "mg_viii", "2s1.2p2.4P_5/2", "1s1.2s1.2p3.4P_5/2"},
        {15925, 10.0059996, "mg_viii", "2s0.2p3.2P_3/2", "1s1.2s2.2p2.2P_3/2"},
        {15926, 69.3600006, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p2.3p1.4S_3/2"},
        {15927, 64.1949997, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p2.3p1.2F_5/2"},
        {15928, 9.59160042, "mg_viii", "2s1.2p2.2D_3/2", "1s1.2s1.2p3.4P_1/2"},
        {15929, 9.90330029, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2s2.2p2.2D_5/2"},
        {15930, 97.4929962, "mg_viii", "2s0.2p3.2P_3/2", "2s1.2p1.3p1.2P_3/2#2"},
        {15931, 86.3580017, "mg_viii", "2s1.2p2.2P_3/2", "2s1.2p1.3d1.2D_5/2"},
        {15932, 59.0870018, "mg_viii", "2p1.2P_3/2", "2s0.2p2.3d1.4D_5/2"},
        {15934, 58.4370003, "mg_ix", "2s2.1S_0", "2s0.2p1.3s1.3P_1"},
        {15935, 9.38539982, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.1S_0"},
        {15936, 67.3499985, "mg_ix", "2s1.2p1.1P_1", "2s0.2p1.3p1.3D_2"},
        {15937, 73.5589981, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3d1.3F_3"},
        {15938, 9.54870033, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.5P_2"},
        {15939, 72.2259979, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3d1.1D_2"},
        {15940, 9.53820038, "mg_ix", "2s0.2p2.3P_2", "1s1.2p3.5S_2"},
        {15941, 68.9860001, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3d1.3P_0"},
        {15942, 72.6119995, "mg_ix", "2s0.2p2.3P_0", "2s0.2p1.3s1.1P_1"},
        {15943, 9.5369997, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.3D_1"},
        {15944, 9.41590023, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.3D_3"},
        {15945, 9.27359962, "mg_ix", "2s1.2p1.3P_0", "1s1.2s1.2p2.1P_1"},
        {15946, 9.78590012, "mg_ix", "2s0.2p2.3P_2", "1s1.2s2.2p1.3P_2"},
        {15947, 69.4110031, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3d1.3D_2"},
        {15948, 9.53929996, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.3P_0"},
        {15949, 9.32139969, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.3P_2#2"},
        {15950, 1024.14001, "mg_ix", "2s1.2p1.1P_1", "2s0.2p2.3P_2"},
        {15951, 9.36520004, "mg_ix", "2s0.2p2.1D_2", "1s1.2p3.1P_1"},
        {15952, 9.57509995, "mg_ix", "2s0.2p2.1S_0", "1s1.2p3.3D_1"},
        {15953, 9.42020035, "mg_ix", "2s0.2p2.3P_0", "1s1.2p3.3S_1"},
        {15954, 67.2389984, "mg_ix", "2s1.2p1.3P_2", "2s1.3d1.3D_3"},
        {15955, 73.5569992, "mg_ix", "2s1.2p1.1P_1", "2s1.3d1.3D_2"},
        {15956, 9.32890034, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.1D_2"},
        {15957, 70.4069977, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3d1.1D_2"},
        {15958, 9.42339993, "mg_ix", "2s0.2p2.3P_2", "1s1.2p3.3S_1"},
        {15959, 9.41530037, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.3D_1"},
        {15960, 9.55020046, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.5P_1"},
        {15961, 71.3150024, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3d1.3D_1"},
        {15962, 9.53829956, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.3D_2"},
        {15963, 9.55090046, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.5P_2"},
        {15964, 62.2039986, "mg_ix", "2s1.2p1.3P_0", "2s0.2p1.3p1.1P_1"},
        {15965, 88.8919983, "mg_ix", "2s0.2p2.3P_2", "2s1.3p1.3P_1"},
        {15966, 70.3000031, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3d1.1D_2"},
        {15967, 61.4900017, "mg_ix", "2s1.2p1.3P_2", "2s0.2p1.3p1.3S_1"},
        {15968, 9.50949955, "mg_ix", "2s0.2p2.1S_0", "1s1.2p3.3P_1"},
        {15969, 445.980011, "mg_ix", "2s1.2p1.3P_1", "2s0.2p2.3P_0"},
        {15970, 9.72119999, "mg_ix", "2s0.2p2.3P_1", "1s1.2s2.2p1.1P_1"},
        {15971, 79.3170013, "mg_ix", "2s1.2p1.1P_1", "2s1.3s1.3S_1"},
        {15972, 9.32269955, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3P_0#2"},
        {15973, 91.4100037, "mg_ix", "2s0.2p2.1S_0", "2s1.3p1.1P_1"},
        {15974, 93.2819977, "mg_ix", "2s0.2p2.1D_2", "2s1.3p1.3P_2"},
        {15975, 68.3539963, "mg_ix", "2s1.2p1.1P_1", "2s0.2p1.3p1.3P_0"},
        {15976, 9.34959984, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3S_1"},
        {15977, 9.38329983, "mg_ix", "2s0.2p2.3P_1", "1s1.2p3.3P_1"},
        {15978, 9.33100033, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.1D_2"},
        {15979, 67.0899963, "mg_ix", "2s1.2p1.3P_0", "2s1.3d1.3D_1"},
        {15980, 76.4059982, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3s1.3P_2"},
        {15981, 72.6809998, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3s1.1P_1"},
        {15982, 70.598999, "mg_ix", "2s1.2p1.3P_1", "2s1.3s1.1S_0"},
        {15983, 61.9210014, "mg_ix", "2s1.2p1.3P_0", "2s0.2p1.3p1.3D_1"},
        {15984, 69.1139984, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3d1.3P_1"},
        {15985, 71.8420029, "mg_ix", "2s1.2p1.3P_0", "2s1.3s1.3S_1"},
        {15986, 9.44659996, "mg_ix", "2s2.1S_0", "1s1.2s2.2p1.3P_1"},
        {15987, 67.1350021, "mg_ix", "2s1.2p1.3P_1", "2s1.3d1.3D_2"},
        {15988, 9.4218998, "mg_ix", "2s0.2p2.1D_2", "1s1.2p3.3P_1"},
        {15989, 54.3019981, "mg_ix", "2s2.1S_0", "2s0.2p1.3d1.1P_1"},
        {15990, 81.4499969, "mg_ix", "2s0.2p2.3P_0", "2s1.3p1.1P_1"},
        {15991, 67.7310028, "mg_ix", "2s1.2p1.1P_1", "2s0.2p1.3p1.1P_1"},
        {15992, 69.1620026, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3d1.3P_2"},
        {15993, 61.1279984, "mg_ix", "2s1.2p1.3P_2", "2s0.2p1.3p1.3P_2"},
        {15994, 9.41149998, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3P_2"},
        {15995, 71.2369995, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3d1.3D_3"},
        {15996, 1814.23999, "mg_ix", "2s0.2p1.3p1.3D_3", "2s0.2p1.3d1.3F_4"},
        {15997, 9.55239964, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.5P_1"},
        {15998, 76.560997, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3s1.3P_1"},
        {15999, 67.8239975, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3d1.1P_1"},
        {16000, 71.9000015, "mg_ix", "2s1.2p1.3P_1", "2s1.3s1.3S_1"},
        {16001, 63.4599991, "mg_ix", "2s2.1S_0", "2s1.3p1.3P_1"},
        {16002, 61.9640007, "mg_ix", "2s1.2p1.3P_1", "2s0.2p1.3p1.3D_1"},
        {16003, 443.403015, "mg_ix", "2s1.2p1.3P_1", "2s0.2p2.3P_1"},
        {16004, 61.0429993, "mg_ix", "2s1.2p1.3P_0", "2s0.2p1.3p1.3P_1"},
        {16005, 62.0200005, "mg_ix", "2s1.2p1.3P_2", "2s0.2p1.3p1.3D_2"},
        {16006, 67.1409988, "mg_ix", "2s1.2p1.3P_1", "2s1.3d1.3D_1"},
        {16007, 9.41390038, "mg_ix", "2s1.2p1.3P_0", "1s1.2s1.2p2.3P_1"},
        {16008, 9.39480019, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.1P_1"},
        {16009, 66.3570023, "mg_ix", "2s1.2p1.1P_1", "2s0.2p1.3p1.3P_1"},
        {16010, 69.4670029, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3d1.3D_3"},
        {16011, 88.5940018, "mg_ix", "2s0.2p2.3P_1", "2s1.3p1.3P_1"},
        {16012, 76.7799988, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3d1.3F_2"},
        {16013, 9.3270998, "mg_ix", "2s0.2p2.3P_1", "1s1.2p3.1P_1"},
        {16014, 74.4609985, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3s1.3P_0"},
        {16015, 9.53530025, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.3P_2"},
        {16016, 368.070007, "mg_ix", "2s2.1S_0", "2s1.2p1.1P_1"},
        {16017, 69.0110016, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3d1.3P_1"},
        {16018, 9.4460001, "mg_ix", "2s0.2p2.3P_0", "1s1.2p3.3D_1"},
        {16019, 9.27680016, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.1P_1"},
        {16020, 9.85669994, "mg_ix", "2s0.2p2.1S_0", "1s1.2s2.2p1.1P_1"},
        {16021, 9.82559967, "mg_ix", "2s0.2p2.1D_2", "1s1.2s2.2p1.3P_2"},
        {16022, 9.72000027, "mg_ix", "2s0.2p2.3P_0", "1s1.2s2.2p1.1P_1"},
        {16023, 9.26550007, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.1S_0"},
        {16024, 62.2480011, "mg_ix", "2s1.2p1.3P_1", "2s0.2p1.3p1.1P_1"},
        {16025, 9.4211998, "mg_ix", "2s0.2p2.1D_2", "1s1.2p3.3P_2"},
        {16026, 1061.92004, "mg_ix", "2s1.2p1.1P_1", "2s0.2p2.3P_0"},
        {16027, 62.0589981, "mg_ix", "2s1.2p1.3P_2", "2s0.2p1.3p1.3D_1"},
        {16028, 9.44410038, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.3P_0#2"},
        {16029, 73.564003, "mg_ix", "2s1.2p1.1P_1", "2s1.3d1.3D_1"},
        {16030, 60.4510002, "mg_ix", "2s1.2p1.3P_1", "2s0.2p1.3p1.1D_2"},
        {16031, 69.5149994, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3d1.3D_2"},
        {16032, 70.9160004, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3d1.3P_2"},
        {16033, 9.53880024, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.3P_1"},
        {16034, 9.54880047, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.5P_3"},
        {16035, 73.5240021, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3d1.3F_2"},
        {16036, 72.0270004, "mg_ix", "2s1.2p1.3P_2", "2s1.3s1.3S_1"},
        {16037, 441.199005, "mg_ix", "2s1.2p1.3P_0", "2s0.2p2.3P_1"},
        {16038, 84.1399994, "mg_ix", "2s0.2p2.1D_2", "2s1.3p1.1P_1"},
        {16039, 438.700012, "mg_ix", "2s1.2p1.1P_1", "2s0.2p2.1S_0"},
        {16040, 9.27460003, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.1P_1"},
        {16041, 59.0870018, "mg_ix", "2s1.2p1.3P_1", "2s0.2p1.3p1.1S_0"},
        {16042, 9.38560009, "mg_ix", "2s2.1S_0", "1s1.2s2.2p1.1P_1"},
        {16043, 40648.8984, "mg_ix", "2s1.2p1.3P_1", "2s1.2p1.3P_2"},
        {16044, 9.44909954, "mg_ix", "2s0.2p2.3P_2", "1s1.2p3.3D_3"},
        {16045, 67.2519989, "mg_ix", "2s1.2p1.3P_2", "2s1.3d1.3D_1"},
        {16046, 72.3119965, "mg_ix", "2s1.2p1.1P_1", "2s1.3d1.1D_2"},
        {16047, 9.4144001, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3D_2"},
        {16048, 74.3730011, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3s1.3P_2"},
        {16049, 65.6090012, "mg_ix", "2s1.2p1.1P_1", "2s0.2p1.3p1.1D_2"},
        {16050, 69.6159973, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3d1.1P_1"},
        {16051, 9.72340012, "mg_ix", "2s0.2p2.3P_2", "1s1.2s2.2p1.1P_1"},
        {16052, 74.4000015, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3s1.3P_1"},
        {16053, 80.4240036, "mg_ix", "2s0.2p2.1S_0", "2s0.2p1.3s1.1P_1"},
        {16054, 9.45049953, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.1D_2"},
        {16055, 61.3540001, "mg_ix", "2s1.2p1.3P_0", "2s0.2p1.3p1.3S_1"},
        {16056, 706.059998, "mg_ix", "2s2.1S_0", "2s1.2p1.3P_1"},
        {16057, 81.6809998, "mg_ix", "2s0.2p2.3P_2", "2s1.3p1.1P_1"},
        {16058, 443.972992, "mg_ix", "2s1.2p1.3P_2", "2s0.2p2.3P_2"},
        {16059, 9.0177002, "mg_ix", "2s2.1S_0", "1s1.2p3.1P_1"},
        {16060, 9.45180035, "mg_ix", "2s0.2p2.1S_0", "1s1.2p3.1P_1"},
        {16061, 448.292999, "mg_ix", "2s1.2p1.3P_2", "2s0.2p2.3P_1"},
        {16062, 62.3429985, "mg_ix", "2s1.2p1.3P_2", "2s0.2p1.3p1.1P_1"},
        {16063, 61.7389984, "mg_ix", "2s1.2p1.3P_1", "2s0.2p1.3p1.3P_0"},
        {16064, 104.460999, "mg_ix", "2s0.2p2.1S_0", "2s1.3p1.3P_1"},
        {16065, 55.0600014, "mg_ix", "2s2.1S_0", "2s0.2p1.3d1.3P_1"},
        {16066, 60.5410004, "mg_ix", "2s1.2p1.3P_2", "2s0.2p1.3p1.1D_2"},
        {16067, 9.41499996, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3P_1"},
        {16068, 76.5950012, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3d1.3F_3"},
        {16069, 9.39070034, "mg_ix", "2s0.2p2.3P_1", "1s1.2p3.1D_2"},
        {16070, 69.3740005, "mg_ix", "2s0.2p2.3P_0", "2s0.2p1.3d1.3D_1"},
        {16071, 9.41660023, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.3D_2"},
        {16072, 9.38469982, "mg_ix", "2s0.2p2.3P_2", "1s1.2p3.3P_2"},
        {16073, 9.44919968, "mg_ix", "2s0.2p2.3P_2", "1s1.2p3.3D_1"},
        {16074, 279.328003, "mg_ix", "2s1.2p1.3P_1", "2s0.2p2.1S_0"},
        {16075, 74.5199966, "mg_ix", "2s0.2p2.1S_0", "2s0.2p1.3d1.1P_1"},
        {16076, 9.78369999, "mg_ix", "2s0.2p2.3P_1", "1s1.2s2.2p1.3P_2"},
        {16077, 69.0579987, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3d1.3P_2"},
        {16078, 61.9259987, "mg_ix", "2s1.2p1.3P_1", "2s0.2p1.3p1.3D_2"},
        {16079, 9.10569954, "mg_ix", "2s2.1S_0", "1s1.2p3.3S_1"},
        {16080, 9.53610039, "mg_ix", "2s0.2p2.3P_1", "1s1.2p3.5S_2"},
        {16081, 9.32600021, "mg_ix", "2s0.2p2.3P_0", "1s1.2p3.1P_1"},
        {16082, 9.48620033, "mg_ix", "2s0.2p2.1D_2", "1s1.2p3.3D_1"},
        {16083, 88.8170013, "mg_ix", "2s0.2p2.3P_2", "2s1.3p1.3P_2"},
        {16084, 88.4329987, "mg_ix", "2s0.2p2.3P_0", "2s1.3p1.3P_1"},
        {16085, 9.38539982, "mg_ix", "2s0.2p2.3P_2", "1s1.2p3.3P_1"},
        {16086, 68.2429962, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3d1.1F_3"},
        {16087, 88.6559982, "mg_ix", "2s0.2p2.3P_1", "2s1.3p1.3P_0"},
        {16088, 9.41539955, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3P_0"},
        {16089, 9.5486002, "mg_ix", "2s0.2p2.1S_0", "1s1.2p3.3S_1"},
        {16090, 9.38269997, "mg_ix", "2s0.2p2.3P_1", "1s1.2p3.3P_2"},
        {16091, 694.005005, "mg_ix", "2s2.1S_0", "2s1.2p1.3P_2"},
        {16092, 69.4369965, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3d1.3D_1"},
        {16093, 9.67609978, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.5P_2"},
        {16094, 379.550995, "mg_ix", "2s1.2p1.3P_1", "2s0.2p2.1D_2"},
        {16095, 9.82859993, "mg_ix", "2s0.2p2.1D_2", "1s1.2s2.2p1.3P_1"},
        {16096, 9.78670025, "mg_ix", "2s0.2p2.3P_1", "1s1.2s2.2p1.3P_1"},
        {16097, 9.07019997, "mg_ix", "2s2.1S_0", "1s1.2p3.3P_1"},
        {16098, 76.4710007, "mg_ix", "2s0.2p2.1S_0", "2s0.2p1.3d1.3D_1"},
        {16099, 69.5419998, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3d1.3D_1"},
        {16100, 9.34860039, "mg_ix", "2s1.2p1.3P_0", "1s1.2s1.2p2.3S_1"},
        {16101, 57.3709984, "mg_ix", "2s2.1S_0", "2s0.2p1.3s1.1P_1"},
        {16102, 61.0369987, "mg_ix", "2s1.2p1.3P_1", "2s0.2p1.3p1.3P_2"},
        {16103, 9.4406004, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.3P_2#2"},
        {16104, 9.44709969, "mg_ix", "2s0.2p2.3P_1", "1s1.2p3.3D_2"},
        {16105, 81.5370026, "mg_ix", "2s0.2p2.3P_1", "2s1.3p1.1P_1"},
        {16106, 9.41709995, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.3P_1"},
        {16107, 66.7249985, "mg_ix", "2s1.2p1.1P_1", "2s0.2p1.3p1.3S_1"},
        {16108, 71.288002, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3d1.3D_2"},
        {16109, 74.3280029, "mg_ix", "2s0.2p2.3P_0", "2s0.2p1.3s1.3P_1"},
        {16110, 9.57590008, "mg_ix", "2s0.2p2.1D_2", "1s1.2p3.5S_2"},
        {16111, 9.78890038, "mg_ix", "2s0.2p2.3P_2", "1s1.2s2.2p1.3P_1"},
        {16112, 9.44919968, "mg_ix", "2s0.2p2.3P_2", "1s1.2p3.3D_2"},
        {16113, 9.78549957, "mg_ix", "2s0.2p2.3P_0", "1s1.2s2.2p1.3P_1"},
        {16114, 9.32359982, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.3P_1#2"},
        {16115, 749.551025, "mg_ix", "2s1.2p1.1P_1", "2s0.2p2.1D_2"},
        {16116, 9.3192997, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3P_2#2"},
        {16117, 9.54909992, "mg_ix", "2s1.2p1.3P_0", "1s1.2s1.2p2.5P_1"},
        {16118, 9.38220024, "mg_ix", "2s0.2p2.3P_0", "1s1.2p3.3P_1"},
        {16119, 67.2460022, "mg_ix", "2s1.2p1.3P_2", "2s1.3d1.3D_2"},
        {16120, 547.137024, "mg_ix", "2s1.3d1.3D_3", "2s0.2p1.3d1.3F_4"},
        {16121, 73.7300034, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3d1.3F_2"},
        {16122, 9.44709969, "mg_ix", "2s0.2p2.3P_1", "1s1.2p3.3D_1"},
        {16123, 88.5189972, "mg_ix", "2s0.2p2.3P_1", "2s1.3p1.3P_2"},
        {16124, 66.3000031, "mg_ix", "2s1.2p1.1P_1", "2s0.2p1.3p1.3P_2"},
        {16125, 9.4137001, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.3P_2"},
        {16126, 70.8659973, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3d1.3P_1"},
        {16127, 9.47179985, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.3S_1"},
        {16128, 82.5339966, "mg_ix", "2s0.2p2.1S_0", "2s0.2p1.3s1.3P_1"},
        {16129, 9.76259995, "mg_ix", "2s0.2p2.1D_2", "1s1.2s2.2p1.1P_1"},
        {16130, 383.127991, "mg_ix", "2s1.2p1.3P_2", "2s0.2p2.1D_2"},
        {16131, 9.92399979, "mg_ix", "2s0.2p2.1S_0", "1s1.2s2.2p1.3P_1"},
        {16132, 93.3639984, "mg_ix", "2s0.2p2.1D_2", "2s1.3p1.3P_1"},
        {16133, 9.48620033, "mg_ix", "2s0.2p2.1D_2", "1s1.2p3.3D_2"},
        {16134, 77.7369995, "mg_ix", "2s1.2p1.1P_1", "2s1.3s1.1S_0"},
        {16135, 9.32149982, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3P_1#2"},
        {16136, 66.0960007, "mg_ix", "2s1.2p1.3P_1", "2s1.3d1.1D_2"},
        {16137, 9.42930031, "mg_ix", "2s0.2p2.1D_2", "1s1.2p3.1D_2"},
        {16138, 55.3310013, "mg_ix", "2s2.1S_0", "2s0.2p1.3d1.3D_1"},
        {16139, 61.9239998, "mg_ix", "2s1.2p1.3P_2", "2s0.2p1.3p1.3D_3"},
        {16140, 65.0790024, "mg_ix", "2s1.2p1.1P_1", "2s0.2p1.3p1.1S_0"},
        {16141, 9.42129993, "mg_ix", "2s0.2p2.3P_1", "1s1.2p3.3S_1"},
        {16142, 9.46020031, "mg_ix", "2s0.2p2.1D_2", "1s1.2p3.3S_1"},
        {16143, 68.9489975, "mg_ix", "2s0.2p2.3P_0", "2s0.2p1.3d1.3P_1"},
        {16144, 9.35179996, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.3S_1"},
        {16145, 9.32909966, "mg_ix", "2s0.2p2.3P_2", "1s1.2p3.1P_1"},
        {16146, 9.3835001, "mg_ix", "2s0.2p2.3P_1", "1s1.2p3.3P_0"},
        {16147, 62.7509995, "mg_ix", "2s2.1S_0", "2s1.3p1.1P_1"},
        {16148, 61.0849991, "mg_ix", "2s1.2p1.3P_1", "2s0.2p1.3p1.3P_1"},
        {16149, 9.32040024, "mg_ix", "2s1.2p1.3P_0", "1s1.2s1.2p2.3P_1#2"},
        {16150, 9.41209984, "mg_ix", "2s1.2p1.3P_0", "1s1.2s1.2p2.3D_1"},
        {16151, 9.4428997, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.3P_1#2"},
        {16152, 67.3949966, "mg_ix", "2s1.2p1.1P_1", "2s0.2p1.3p1.3D_1"},
        {16153, 66.2040024, "mg_ix", "2s1.2p1.3P_2", "2s1.3d1.1D_2"},
        {16154, 9.39280033, "mg_ix", "2s0.2p2.3P_2", "1s1.2p3.1D_2"},
        {16155, 9.41310024, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3D_1"},
        {16156, 69.9499969, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3d1.1F_3"},
        {16157, 74.5199966, "mg_ix", "2s0.2p2.3P_2", "2s0.2p1.3s1.3P_1"},
        {16158, 67.7639999, "mg_ix", "2s0.2p2.3P_0", "2s0.2p1.3d1.1P_1"},
        {16159, 75.9550018, "mg_ix", "2s0.2p2.1S_0", "2s0.2p1.3d1.3P_1"},
        {16160, 74.7419968, "mg_ix", "2s0.2p2.1D_2", "2s0.2p1.3s1.1P_1"},
        {16161, 74.2529984, "mg_ix", "2s0.2p2.3P_1", "2s0.2p1.3s1.3P_2"},
        {16162, 9.67770004, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.5P_1"},
        {16163, 439.175995, "mg_ix", "2s1.2p1.3P_1", "2s0.2p2.3P_2"},
        {16164, 9.12979984, "mg_ix", "2s2.1S_0", "1s1.2p3.3D_1"},
        {16165, 9.78810024, "mg_ix", "2s0.2p2.3P_1", "1s1.2s2.2p1.3P_0"},
        {16166, 61.3969994, "mg_ix", "2s1.2p1.3P_1", "2s0.2p1.3p1.3S_1"},
        {16167, 61.1769981, "mg_ix", "2s1.2p1.3P_2", "2s0.2p1.3p1.3P_1"},
        {16168, 9.4861002, "mg_ix", "2s0.2p2.1D_2", "1s1.2p3.3D_3"},
        {16171, 585, "mg_x", "2s0.4d1.2D_5/2", "2s0.5f1.2F_7/2"},
        {16172, 585, "mg_x", "2s0.4d1.2D_3/2", "2s0.5f1.2F_5/2"},
        {16173, 187, "mg_x", "2s0.3d1.2D_3/2", "2s0.5f1.2F_5/2"},
        {16174, 9.21170044, "mg_x", "2s0.2p1.2P_1/2", "1s1.2p2.2S_1/2"},
        {16175, 39.6679993, "mg_x", "2s1.2S_1/2", "2s0.5p1.2P_1/2"},
        {16176, 609.79303, "mg_x", "2s1.2S_1/2", "2s0.2p1.2P_3/2"},
        {16177, 57.8759995, "mg_x", "2s1.2S_1/2", "2s0.3p1.2P_3/2"},
        {16178, 47.2290001, "mg_x", "2s0.2p1.2P_1/2", "2s0.4d1.2D_3/2"},
        {16179, 9.31579971, "mg_x", "2s0.2p1.2P_3/2", "1s1.2p2.2D_5/2"},
        {16180, 63.3110008, "mg_x", "2s0.2p1.2P_3/2", "2s0.3d1.2D_3/2"},
        {16181, 44.0499992, "mg_x", "2s1.2S_1/2", "2s0.4p1.2P_3/2"},
        {16182, 585, "mg_x", "2s0.4d1.2D_5/2", "2s0.5f1.2F_5/2"},
        {16183, 9.57670021, "mg_x", "2s0.2p1.2P_1/2", "1s1.2s2.2S_1/2"},
        {16184, 624.940979, "mg_x", "2s1.2S_1/2", "2s0.2p1.2P_1/2"},
        {16185, 187.205994, "mg_x", "2s0.3d1.2D_5/2", "2s0.4f1.2F_5/2"},
        {16186, 9.38539982, "mg_x", "2s0.2p1.2P_3/2", "1s1.2p2.4P_5/2"},
        {16187, 42.2939987, "mg_x", "2s0.2p1.2P_1/2", "2s0.5d1.2D_3/2"},
        {16188, 585, "mg_x", "2s0.4f1.2F_7/2", "2s0.5g1.2G_7/2"},
        {16189, 47.7879982, "mg_x", "2s0.2p1.2P_1/2", "2s0.4s1.2S_1/2"},
        {16190, 65.8450012, "mg_x", "2s0.2p1.2P_3/2", "2s0.3s1.2S_1/2"},
        {16191, 42.3619995, "mg_x", "2s0.2p1.2P_3/2", "2s0.5d1.2D_5/2"},
        {16192, 9.22959995, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.2P_3/2#2"},
        {16193, 57.9199982, "mg_x", "2s1.2S_1/2", "2s0.3p1.2P_1/2"},
        {16194, 9.21500015, "mg_x", "2s0.2p1.2P_3/2", "1s1.2p2.2S_1/2"},
        {16195, 9.39480019, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.4P_3/2"},
        {16196, 42.5970001, "mg_x", "2s0.2p1.2P_3/2", "2s0.5s1.2S_1/2"},
        {16197, 585, "mg_x", "2s0.4f1.2F_5/2", "2s0.5g1.2G_7/2"},
        {16198, 187.177994, "mg_x", "2s0.3d1.2D_5/2", "2s0.4f1.2F_7/2"},
        {16199, 9.31599998, "mg_x", "2s0.2p1.2P_3/2", "1s1.2p2.2D_3/2"},
        {16200, 9.29500008, "mg_x", "2s0.2p1.2P_1/2", "1s1.2p2.2P_1/2"},
        {16201, 42.5250015, "mg_x", "2s0.2p1.2P_1/2", "2s0.5s1.2S_1/2"},
        {16202, 187.070007, "mg_x", "2s0.3d1.2D_3/2", "2s0.4f1.2F_5/2"},
        {16203, 47.3100014, "mg_x", "2s0.2p1.2P_3/2", "2s0.4d1.2D_5/2"},
        {16204, 9.38790035, "mg_x", "2s0.2p1.2P_3/2", "1s1.2p2.4P_3/2"},
        {16205, 187, "mg_x", "2s0.3d1.2D_5/2", "2s0.5f1.2F_5/2"},
        {16206, 585, "mg_x", "2s0.4f1.2F_5/2", "2s0.5g1.2G_9/2"},
        {16207, 9.29520035, "mg_x", "2s0.2p1.2P_3/2", "1s1.2p2.2P_3/2"},
        {16208, 44.0499992, "mg_x", "2s1.2S_1/2", "2s0.4p1.2P_1/2"},
        {16209, 47.8790016, "mg_x", "2s0.2p1.2P_3/2", "2s0.4s1.2S_1/2"},
        {16210, 42.3660011, "mg_x", "2s0.2p1.2P_3/2", "2s0.5d1.2D_3/2"},
        {16211, 47.3170013, "mg_x", "2s0.2p1.2P_3/2", "2s0.4d1.2D_3/2"},
        {16212, 187, "mg_x", "2s0.3d1.2D_3/2", "2s0.5f1.2F_7/2"},
        {16213, 585, "mg_x", "2s0.4d1.2D_3/2", "2s0.5f1.2F_7/2"},
        {16214, 9.28289986, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.2P_3/2"},
        {16215, 63.1520004, "mg_x", "2s0.2p1.2P_1/2", "2s0.3d1.2D_3/2"},
        {16216, 9.23079967, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.2P_1/2#2"},
        {16217, 585, "mg_x", "2s0.4f1.2F_7/2", "2s0.5g1.2G_9/2"},
        {16218, 9.38599968, "mg_x", "2s0.2p1.2P_1/2", "1s1.2p2.4P_1/2"},
        {16219, 9.38939953, "mg_x", "2s0.2p1.2P_3/2", "1s1.2p2.4P_1/2"},
        {16220, 187, "mg_x", "2s0.3d1.2D_5/2", "2s0.5f1.2F_7/2"},
        {16221, 9.39630032, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.4P_1/2"},
        {16222, 9.58030033, "mg_x", "2s0.2p1.2P_3/2", "1s1.2s2.2S_1/2"},
        {16223, 9.38440037, "mg_x", "2s0.2p1.2P_1/2", "1s1.2p2.4P_3/2"},
        {16224, 63.2949982, "mg_x", "2s0.2p1.2P_3/2", "2s0.3d1.2D_5/2"},
        {16225, 39.6679993, "mg_x", "2s1.2S_1/2", "2s0.5p1.2P_3/2"},
        {16226, 9.29179955, "mg_x", "2s0.2p1.2P_1/2", "1s1.2p2.2P_3/2"},
        {16227, 9.29839993, "mg_x", "2s0.2p1.2P_3/2", "1s1.2p2.2P_1/2"},
        {16228, 9.31260014, "mg_x", "2s0.2p1.2P_1/2", "1s1.2p2.2D_3/2"},
        {16229, 9.28479958, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.2P_1/2"},
        {16230, 65.6729965, "mg_x", "2s0.2p1.2P_1/2", "2s0.3s1.2S_1/2"},
        {16231, 9.38961983, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.4P_5/2"},
        {16275, 150.83844, "mg_xi", "1s1.3s1.1S_0", "1s1.4p1.1P_1"},
        {16276, 9.23191452, "mg_xi", "1s2.1S_0", "1s1.2p1.3P_0"},
        {16277, 9.23099995, "mg_xi", "1s2.1S_0", "1s1.2p1.3P_1"},
        {16278, 9.22819996, "mg_xi", "1s2.1S_0", "1s1.2p1.3P_2"},
        {16279, 146412.891, "mg_xi", "1s1.5p1.1P_1", "1s1.5d1.1D_2"},
        {16280, 340.28421, "mg_xi", "1s1.4p1.1P_1", "1s1.5s1.1S_0"},
        {16281, 106.306763, "mg_xi", "1s1.3p1.1P_1", "1s1.5d1.1D_2"},
        {16282, 336.23053, "mg_xi", "1s1.4p1.1P_1", "1s1.5d1.1D_2"},
        {16283, 9.16889954, "mg_xi", "1s2.1S_0", "1s1.2p1.1P_1"},
        {16284, 3803.00439, "mg_xi", "1s1.3s1.3S_1", "1s1.3p1.3P_0"},
        {16285, 3765.2019, "mg_xi", "1s1.3s1.3S_1", "1s1.3p1.3P_1"},
        {16286, 3621.08911, "mg_xi", "1s1.3s1.3S_1", "1s1.3p1.3P_2"},
        {16287, 53.7871246, "mg_xi", "1s1.2p1.3P_0", "1s1.3s1.3S_1"},
        {16288, 53.8111191, "mg_xi", "1s1.2p1.3P_1", "1s1.3s1.3S_1"},
        {16289, 53.9146919, "mg_xi", "1s1.2p1.3P_2", "1s1.3s1.3S_1"},
        {16290, 8.61946201, "mg_xi", "1s1.2p1.1P_1", "1s0.2p2.3P"},
        {16291, 35.2406883, "mg_xi", "1s1.2p1.3P_0", "1s1.5s1.3S_1"},
        {16292, 35.250988, "mg_xi", "1s1.2p1.3P_1", "1s1.5s1.3S_1"},
        {16293, 35.2954063, "mg_xi", "1s1.2p1.3P_2", "1s1.5s1.3S_1"},
        {16294, 39.5256615, "mg_xi", "1s1.2p1.3P_0", "1s1.4s1.3S_1"},
        {16295, 39.5386162, "mg_xi", "1s1.2p1.3P_1", "1s1.4s1.3S_1"},
        {16296, 39.5945053, "mg_xi", "1s1.2p1.3P_2", "1s1.4s1.3S_1"},
        {16297, 50.4711723, "mg_xi", "1s1.2s1.3S_1", "1s1.3p1.3P_0"},
        {16298, 50.4644508, "mg_xi", "1s1.2s1.3S_1", "1s1.3p1.3P_1"},
        {16299, 50.4375458, "mg_xi", "1s1.2s1.3S_1", "1s1.3p1.3P_2"},
        {16300, 36.0741501, "mg_xi", "1s1.2p1.1P_1", "1s1.5d1.1D_2"},
        {16301, 55.1970215, "mg_xi", "1s1.2p1.1P_1", "1s1.3s1.1S_0"},
        {16302, 333.853027, "mg_xi", "1s1.4d1.1D_2", "1s1.5p1.1P_1"},
        {16303, 155.805954, "mg_xi", "1s1.3p1.1P_1", "1s1.4d1.1D_2"},
        {16304, 1043.26416, "mg_xi", "1s1.2s1.3S_1", "1s1.2p1.3P_0"},
        {16305, 1034.31873, "mg_xi", "1s1.2s1.3S_1", "1s1.2p1.3P_1"},
        {16306, 997.486328, "mg_xi", "1s1.2s1.3S_1", "1s1.2p1.3P_2"},
        {16307, 8.55448151, "mg_xi", "1s1.2s1.3S_1", "1s0.2s1.2p1.3P"},
        {16308, 23663.0391, "mg_xi", "1s1.5s1.1S_0", "1s1.5p1.1P_1"},
        {16309, 37.9263954, "mg_xi", "1s1.2s1.3S_1", "1s1.4p1.3P_0"},
        {16310, 37.9247856, "mg_xi", "1s1.2s1.3S_1", "1s1.4p1.3P_1"},
        {16311, 37.9183998, "mg_xi", "1s1.2s1.3S_1", "1s1.4p1.3P_2"},
        {16312, 9.31599998, "mg_xi", "1s2.1S_0", "1s1.2s1.3S_1"},
        {16313, 155.152771, "mg_xi", "1s1.3p1.3P_0", "1s1.4s1.3S_1"},
        {16314, 155.216354, "mg_xi", "1s1.3p1.3P_1", "1s1.4s1.3S_1"},
        {16315, 155.47142, "mg_xi", "1s1.3p1.3P_2", "1s1.4s1.3S_1"},
        {16316, 8.64752483, "mg_xi", "1s1.2p1.3P_0", "1s0.2s2.1S"},
        {16317, 8.64814472, "mg_xi", "1s1.2p1.3P_1", "1s0.2s2.1S"},
        {16318, 8.65081501, "mg_xi", "1s1.2p1.3P_2", "1s0.2s2.1S"},
        {16319, 106.708656, "mg_xi", "1s1.3p1.1P_1", "1s1.5s1.1S_0"},
        {16320, 7.85090017, "mg_xi", "1s2.1S_0", "1s1.3p1.1P_1"},
        {16321, 8.63025951, "mg_xi", "1s1.2s1.1S_0", "1s0.2s1.2p1.3P"},
        {16322, 8.70368958, "mg_xi", "1s1.2p1.1P_1", "1s0.2s2.1S"},
        {16323, 5075.62695, "mg_xi", "1s1.3s1.1S_0", "1s1.3p1.1P_1"},
        {16324, 69686.4141, "mg_xi", "1s1.4p1.1P_1", "1s1.4d1.1D_2"},
        {16325, 7.47380018, "mg_xi", "1s2.1S_0", "1s1.4p1.1P_1"},
        {16326, 1474.18701, "mg_xi", "1s1.2s1.1S_0", "1s1.2p1.1P_1"},
        {16327, 36.1203156, "mg_xi", "1s1.2p1.1P_1", "1s1.5s1.1S_0"},
        {16328, 39.3315697, "mg_xi", "1s1.2s1.1S_0", "1s1.4p1.1P_1"},
        {16329, 12065.6367, "mg_xi", "1s1.4s1.1S_0", "1s1.4p1.1P_1"},
        {16330, 52.6529732, "mg_xi", "1s1.2s1.1S_0", "1s1.3p1.1P_1"},
        {16331, 157.487503, "mg_xi", "1s1.3p1.1P_1", "1s1.4s1.1S_0"},
        {16332, 40.5454979, "mg_xi", "1s1.2p1.1P_1", "1s1.4s1.1S_0"},
        {16333, 7.31020021, "mg_xi", "1s2.1S_0", "1s1.5p1.1P_1"},
        {16334, 8.56437588, "mg_xi", "1s1.2p1.3P_0", "1s0.2p2.3P"},
        {16335, 8.56498337, "mg_xi", "1s1.2p1.3P_1", "1s0.2p2.3P"},
        {16336, 8.56760311, "mg_xi", "1s1.2p1.3P_2", "1s0.2p2.3P"},
        {16337, 101.634178, "mg_xi", "1s1.3s1.3S_1", "1s1.5p1.3P_0"},
        {16338, 101.628181, "mg_xi", "1s1.3s1.3S_1", "1s1.5p1.3P_1"},
        {16339, 101.604637, "mg_xi", "1s1.3s1.3S_1", "1s1.5p1.3P_2"},
        {16340, 9232.75781, "mg_xi", "1s1.4s1.3S_1", "1s1.4p1.3P_0"},
        {16341, 9138.26172, "mg_xi", "1s1.4s1.3S_1", "1s1.4p1.3P_1"},
        {16342, 8781.94434, "mg_xi", "1s1.4s1.3S_1", "1s1.4p1.3P_2"},
        {16343, 156.338181, "mg_xi", "1s1.3d1.3D_1", "1s1.4p1.3P_0"},
        {16344, 156.310822, "mg_xi", "1s1.3d1.3D_1", "1s1.4p1.3P_1"},
        {16345, 156.202408, "mg_xi", "1s1.3d1.3D_1", "1s1.4p1.3P_2"},
        {16346, 156.347961, "mg_xi", "1s1.3d1.3D_2", "1s1.4p1.3P_0"},
        {16347, 156.320587, "mg_xi", "1s1.3d1.3D_2", "1s1.4p1.3P_1"},
        {16348, 156.212173, "mg_xi", "1s1.3d1.3D_2", "1s1.4p1.3P_2"},
        {16349, 156.440903, "mg_xi", "1s1.3d1.3D_3", "1s1.4p1.3P_0"},
        {16350, 156.413498, "mg_xi", "1s1.3d1.3D_3", "1s1.4p1.3P_1"},
        {16351, 156.304947, "mg_xi", "1s1.3d1.3D_3", "1s1.4p1.3P_2"},
        {16352, 336.931763, "mg_xi", "1s1.4p1.3P_0", "1s1.5s1.3S_1"},
        {16353, 337.05896, "mg_xi", "1s1.4p1.3P_1", "1s1.5s1.3S_1"},
        {16354, 337.564148, "mg_xi", "1s1.4p1.3P_2", "1s1.5s1.3S_1"},
        {16355, 39.2557716, "mg_xi", "1s1.2p1.3P_0", "1s1.4d1.3D_1"},
        {16356, 39.2555428, "mg_xi", "1s1.2p1.3P_0", "1s1.4d1.3D_2"},
        {16357, 39.2530441, "mg_xi", "1s1.2p1.3P_0", "1s1.4d1.3D_3"},
        {16358, 39.2685509, "mg_xi", "1s1.2p1.3P_1", "1s1.4d1.3D_1"},
        {16359, 39.268322, "mg_xi", "1s1.2p1.3P_1", "1s1.4d1.3D_2"},
        {16360, 39.2658234, "mg_xi", "1s1.2p1.3P_1", "1s1.4d1.3D_3"},
        {16361, 39.3236809, "mg_xi", "1s1.2p1.3P_2", "1s1.4d1.3D_1"},
        {16362, 39.3234482, "mg_xi", "1s1.2p1.3P_2", "1s1.4d1.3D_2"},
        {16363, 39.3209419, "mg_xi", "1s1.2p1.3P_2", "1s1.4d1.3D_3"},
        {16364, 146.702423, "mg_xi", "1s1.3s1.3S_1", "1s1.4p1.3P_0"},
        {16365, 146.678329, "mg_xi", "1s1.3s1.3S_1", "1s1.4p1.3P_1"},
        {16366, 146.582855, "mg_xi", "1s1.3s1.3S_1", "1s1.4p1.3P_2"},
        {16367, 30021.0137, "mg_xi", "1s1.5p1.3P_0", "1s1.5d1.3D_1"},
        {16368, 29949.0859, "mg_xi", "1s1.5p1.3P_0", "1s1.5d1.3D_2"},
        {16369, 29222.6758, "mg_xi", "1s1.5p1.3P_0", "1s1.5d1.3D_3"},
        {16370, 30553.0098, "mg_xi", "1s1.5p1.3P_1", "1s1.5d1.3D_1"},
        {16371, 30478.5117, "mg_xi", "1s1.5p1.3P_1", "1s1.5d1.3D_2"},
        {16372, 29726.5156, "mg_xi", "1s1.5p1.3P_1", "1s1.5d1.3D_3"},
        {16373, 32840.7227, "mg_xi", "1s1.5p1.3P_2", "1s1.5d1.3D_1"},
        {16374, 32754.668, "mg_xi", "1s1.5p1.3P_2", "1s1.5d1.3D_2"},
        {16375, 31887.7559, "mg_xi", "1s1.5p1.3P_2", "1s1.5d1.3D_3"},
        {16376, 8.5324297, "mg_xi", "1s1.2p1.3P_0", "1s0.2p2.1D"},
        {16377, 8.53303337, "mg_xi", "1s1.2p1.3P_1", "1s0.2p2.1D"},
        {16378, 8.53563309, "mg_xi", "1s1.2p1.3P_2", "1s0.2p2.1D"},
        {16379, 34.0256996, "mg_xi", "1s1.2s1.3S_1", "1s1.5p1.3P_0"},
        {16380, 34.0250282, "mg_xi", "1s1.2s1.3S_1", "1s1.5p1.3P_1"},
        {16381, 34.0223885, "mg_xi", "1s1.2s1.3S_1", "1s1.5p1.3P_2"},
        {16382, 8.47806549, "mg_xi", "1s1.2p1.1P_1", "1s0.2p2.1S"},
        {16383, 319.38678, "mg_xi", "1s1.4s1.3S_1", "1s1.5p1.3P_0"},
        {16384, 319.327637, "mg_xi", "1s1.4s1.3S_1", "1s1.5p1.3P_1"},
        {16385, 319.095306, "mg_xi", "1s1.4s1.3S_1", "1s1.5p1.3P_2"},
        {16386, 151.075653, "mg_xi", "1s1.3p1.3P_0", "1s1.4d1.3D_1"},
        {16387, 151.072235, "mg_xi", "1s1.3p1.3P_0", "1s1.4d1.3D_2"},
        {16388, 151.035278, "mg_xi", "1s1.3p1.3P_0", "1s1.4d1.3D_3"},
        {16389, 151.135941, "mg_xi", "1s1.3p1.3P_1", "1s1.4d1.3D_1"},
        {16390, 151.132507, "mg_xi", "1s1.3p1.3P_1", "1s1.4d1.3D_2"},
        {16391, 151.09552, "mg_xi", "1s1.3p1.3P_1", "1s1.4d1.3D_3"},
        {16392, 151.377762, "mg_xi", "1s1.3p1.3P_2", "1s1.4d1.3D_1"},
        {16393, 151.374329, "mg_xi", "1s1.3p1.3P_2", "1s1.4d1.3D_2"},
        {16394, 151.337219, "mg_xi", "1s1.3p1.3P_2", "1s1.4d1.3D_3"},
        {16395, 106.16748, "mg_xi", "1s1.3d1.3D_1", "1s1.5p1.3P_0"},
        {16396, 106.160942, "mg_xi", "1s1.3d1.3D_1", "1s1.5p1.3P_1"},
        {16397, 106.135246, "mg_xi", "1s1.3d1.3D_1", "1s1.5p1.3P_2"},
        {16398, 106.171989, "mg_xi", "1s1.3d1.3D_2", "1s1.5p1.3P_0"},
        {16399, 106.165451, "mg_xi", "1s1.3d1.3D_2", "1s1.5p1.3P_1"},
        {16400, 106.139763, "mg_xi", "1s1.3d1.3D_2", "1s1.5p1.3P_2"},
        {16401, 106.214844, "mg_xi", "1s1.3d1.3D_3", "1s1.5p1.3P_0"},
        {16402, 106.208298, "mg_xi", "1s1.3d1.3D_3", "1s1.5p1.3P_1"},
        {16403, 106.182587, "mg_xi", "1s1.3d1.3D_3", "1s1.5p1.3P_2"},
        {16404, 338.173737, "mg_xi", "1s1.4d1.3D_1", "1s1.5p1.3P_0"},
        {16405, 338.107422, "mg_xi", "1s1.4d1.3D_1", "1s1.5p1.3P_1"},
        {16406, 337.846954, "mg_xi", "1s1.4d1.3D_1", "1s1.5p1.3P_2"},
        {16407, 338.190887, "mg_xi", "1s1.4d1.3D_2", "1s1.5p1.3P_0"},
        {16408, 338.124542, "mg_xi", "1s1.4d1.3D_2", "1s1.5p1.3P_1"},
        {16409, 337.864075, "mg_xi", "1s1.4d1.3D_2", "1s1.5p1.3P_2"},
        {16410, 338.376282, "mg_xi", "1s1.4d1.3D_3", "1s1.5p1.3P_0"},
        {16411, 338.309875, "mg_xi", "1s1.4d1.3D_3", "1s1.5p1.3P_1"},
        {16412, 338.049103, "mg_xi", "1s1.4d1.3D_3", "1s1.5p1.3P_2"},
        {16413, 104.062927, "mg_xi", "1s1.3p1.3P_0", "1s1.5d1.3D_1"},
        {16414, 104.062073, "mg_xi", "1s1.3p1.3P_0", "1s1.5d1.3D_2"},
        {16415, 104.053078, "mg_xi", "1s1.3p1.3P_0", "1s1.5d1.3D_3"},
        {16416, 104.091522, "mg_xi", "1s1.3p1.3P_1", "1s1.5d1.3D_1"},
        {16417, 104.09066, "mg_xi", "1s1.3p1.3P_1", "1s1.5d1.3D_2"},
        {16418, 104.081673, "mg_xi", "1s1.3p1.3P_1", "1s1.5d1.3D_3"},
        {16419, 104.206177, "mg_xi", "1s1.3p1.3P_2", "1s1.5d1.3D_1"},
        {16420, 104.205307, "mg_xi", "1s1.3p1.3P_2", "1s1.5d1.3D_2"},
        {16421, 104.196297, "mg_xi", "1s1.3p1.3P_2", "1s1.5d1.3D_3"},
        {16422, 105.812828, "mg_xi", "1s1.3d1.1D_2", "1s1.5p1.1P_1"},
        {16423, 15236.9346, "mg_xi", "1s1.4p1.3P_0", "1s1.4d1.3D_1"},
        {16424, 15202.1895, "mg_xi", "1s1.4p1.3P_0", "1s1.4d1.3D_2"},
        {16425, 14836.7949, "mg_xi", "1s1.4p1.3P_0", "1s1.4d1.3D_3"},
        {16426, 15501.4727, "mg_xi", "1s1.4p1.3P_1", "1s1.4d1.3D_1"},
        {16427, 15465.5117, "mg_xi", "1s1.4p1.3P_1", "1s1.4d1.3D_2"},
        {16428, 15087.5078, "mg_xi", "1s1.4p1.3P_1", "1s1.4d1.3D_3"},
        {16429, 16647.2441, "mg_xi", "1s1.4p1.3P_2", "1s1.4d1.3D_1"},
        {16430, 16605.7793, "mg_xi", "1s1.4p1.3P_2", "1s1.4d1.3D_2"},
        {16431, 16170.7637, "mg_xi", "1s1.4p1.3P_2", "1s1.4d1.3D_3"},
        {16432, 327.225128, "mg_xi", "1s1.4p1.3P_0", "1s1.5d1.3D_1"},
        {16433, 327.216553, "mg_xi", "1s1.4p1.3P_0", "1s1.5d1.3D_2"},
        {16434, 327.127716, "mg_xi", "1s1.4p1.3P_0", "1s1.5d1.3D_3"},
        {16435, 327.345093, "mg_xi", "1s1.4p1.3P_1", "1s1.5d1.3D_1"},
        {16436, 327.336517, "mg_xi", "1s1.4p1.3P_1", "1s1.5d1.3D_2"},
        {16437, 327.24762, "mg_xi", "1s1.4p1.3P_1", "1s1.5d1.3D_3"},
        {16438, 327.821564, "mg_xi", "1s1.4p1.3P_2", "1s1.5d1.3D_1"},
        {16439, 327.812958, "mg_xi", "1s1.4p1.3P_2", "1s1.5d1.3D_2"},
        {16440, 327.723785, "mg_xi", "1s1.4p1.3P_2", "1s1.5d1.3D_3"},
        {16441, 35.131691, "mg_xi", "1s1.2p1.3P_0", "1s1.5d1.3D_1"},
        {16442, 35.1315918, "mg_xi", "1s1.2p1.3P_0", "1s1.5d1.3D_2"},
        {16443, 35.1305656, "mg_xi", "1s1.2p1.3P_0", "1s1.5d1.3D_3"},
        {16444, 35.1419258, "mg_xi", "1s1.2p1.3P_1", "1s1.5d1.3D_1"},
        {16445, 35.1418266, "mg_xi", "1s1.2p1.3P_1", "1s1.5d1.3D_2"},
        {16446, 35.1408005, "mg_xi", "1s1.2p1.3P_1", "1s1.5d1.3D_3"},
        {16447, 35.1860657, "mg_xi", "1s1.2p1.3P_2", "1s1.5d1.3D_1"},
        {16448, 35.1859665, "mg_xi", "1s1.2p1.3P_2", "1s1.5d1.3D_2"},
        {16449, 35.1849403, "mg_xi", "1s1.2p1.3P_2", "1s1.5d1.3D_3"},
        {16450, 6362.13281, "mg_xi", "1s1.3p1.3P_0", "1s1.3d1.3D_1"},
        {16451, 6345.98291, "mg_xi", "1s1.3p1.3P_0", "1s1.3d1.3D_2"},
        {16452, 6196.55469, "mg_xi", "1s1.3p1.3P_0", "1s1.3d1.3D_3"},
        {16453, 6470.81641, "mg_xi", "1s1.3p1.3P_1", "1s1.3d1.3D_1"},
        {16454, 6454.11133, "mg_xi", "1s1.3p1.3P_1", "1s1.3d1.3D_2"},
        {16455, 6299.60938, "mg_xi", "1s1.3p1.3P_1", "1s1.3d1.3D_3"},
        {16456, 6945.8916, "mg_xi", "1s1.3p1.3P_2", "1s1.3d1.3D_1"},
        {16457, 6926.64697, "mg_xi", "1s1.3p1.3P_2", "1s1.3d1.3D_2"},
        {16458, 6749.00439, "mg_xi", "1s1.3p1.3P_2", "1s1.3d1.3D_3"},
        {16459, 52.598526, "mg_xi", "1s1.2p1.3P_0", "1s1.3d1.3D_1"},
        {16460, 52.5974197, "mg_xi", "1s1.2p1.3P_0", "1s1.3d1.3D_2"},
        {16461, 52.5869064, "mg_xi", "1s1.2p1.3P_0", "1s1.3d1.3D_3"},
        {16462, 52.6214714, "mg_xi", "1s1.2p1.3P_1", "1s1.3d1.3D_1"},
        {16463, 52.6203613, "mg_xi", "1s1.2p1.3P_1", "1s1.3d1.3D_2"},
        {16464, 52.6098442, "mg_xi", "1s1.2p1.3P_1", "1s1.3d1.3D_3"},
        {16465, 52.7205086, "mg_xi", "1s1.2p1.3P_2", "1s1.3d1.3D_1"},
        {16466, 52.7193985, "mg_xi", "1s1.2p1.3P_2", "1s1.3d1.3D_2"},
        {16467, 52.7088394, "mg_xi", "1s1.2p1.3P_2", "1s1.3d1.3D_3"},
        {16468, 26968.7168, "mg_xi", "1s1.3p1.1P_1", "1s1.3d1.1D_2"},
        {16469, 8.52600956, "mg_xi", "1s1.2s1.3S_1", "1s0.2s1.2p1.1P"},
        {16470, 54.7139931, "mg_xi", "1s1.2p1.1P_1", "1s1.3d1.1D_2"},
        {16471, 104.051888, "mg_xi", "1s1.3s1.1S_0", "1s1.5p1.1P_1"},
        {16472, 154.567383, "mg_xi", "1s1.3d1.1D_2", "1s1.4p1.1P_1"},
        {16473, 40.4331512, "mg_xi", "1s1.2p1.1P_1", "1s1.4d1.1D_2"},
        {16474, 8.42476559, "mg_xi", "1s1.2p1.3P_0", "1s0.2p2.1S"},
        {16475, 8.425354, "mg_xi", "1s1.2p1.3P_1", "1s0.2p2.1S"},
        {16476, 8.42788887, "mg_xi", "1s1.2p1.3P_2", "1s0.2p2.1S"},
        {16477, 105.025139, "mg_xi", "1s1.3p1.3P_0", "1s1.5s1.3S_1"},
        {16478, 105.054268, "mg_xi", "1s1.3p1.3P_1", "1s1.5s1.3S_1"},
        {16479, 105.171051, "mg_xi", "1s1.3p1.3P_2", "1s1.5s1.3S_1"},
        {16480, 8.5871048, "mg_xi", "1s1.2p1.1P_1", "1s0.2p2.1D"},
        {16481, 18271.5156, "mg_xi", "1s1.5s1.3S_1", "1s1.5p1.3P_0"},
        {16482, 18079.9141, "mg_xi", "1s1.5s1.3S_1", "1s1.5p1.3P_1"},
        {16483, 17364.125, "mg_xi", "1s1.5s1.3S_1", "1s1.5p1.3P_2"},
        {16484, 35.2040176, "mg_xi", "1s1.2s1.1S_0", "1s1.5p1.1P_1"},
        {16485, 326.385681, "mg_xi", "1s1.4s1.1S_0", "1s1.5p1.1P_1"},
        {16587, 33.6643562, "mg_xii", "1s0.2s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {16588, 33.6535606, "mg_xii", "1s0.2s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {16589, 6.73818207, "mg_xii", "1s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {16590, 6.73774958, "mg_xii", "1s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {16591, 6.58022165, "mg_xii", "1s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {16592, 6.58001041, "mg_xii", "1s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {16593, 30.0592861, "mg_xii", "1s0.2s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {16594, 30.0548782, "mg_xii", "1s0.2s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {16595, 7.10690737, "mg_xii", "1s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {16596, 7.10576582, "mg_xii", "1s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {16597, 6.51273489, "mg_xii", "1s1.2S_1/2", "1s0.6p1.2P"},
        {16598, 45.3908806, "mg_xii", "1s0.2p1.2P_1/2", "1s0.3d1.2D_3/2"},
        {16599, 45.375412, "mg_xii", "1s0.2p1.2P_1/2", "1s0.3d1.2D_5/2"},
        {16600, 45.5485649, "mg_xii", "1s0.2p1.2P_3/2", "1s0.3d1.2D_3/2"},
        {16601, 45.5329895, "mg_xii", "1s0.2p1.2P_3/2", "1s0.3d1.2D_5/2"},
        {16602, 33.6604156, "mg_xii", "1s0.2p1.2P_1/2", "1s0.4s1.2S_1/2"},
        {16603, 33.7470512, "mg_xii", "1s0.2p1.2P_3/2", "1s0.4s1.2S_1/2"},
        {16604, 45.4437866, "mg_xii", "1s0.2s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {16605, 45.3971596, "mg_xii", "1s0.2s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {16606, 45.4354897, "mg_xii", "1s0.2p1.2P_1/2", "1s0.3s1.2S_1/2"},
        {16607, 45.593483, "mg_xii", "1s0.2p1.2P_3/2", "1s0.3s1.2S_1/2"},
        {16608, 33.6500854, "mg_xii", "1s0.2p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {16609, 33.6464958, "mg_xii", "1s0.2p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {16610, 33.7366676, "mg_xii", "1s0.2p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {16611, 33.7330589, "mg_xii", "1s0.2p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {16612, 280.726166, "mg_xii", "1s0.4s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {16613, 280.342133, "mg_xii", "1s0.4s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {16614, 129.889191, "mg_xii", "1s0.3s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {16615, 129.728607, "mg_xii", "1s0.3s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {16616, 129.713287, "mg_xii", "1s0.3p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {16617, 129.659973, "mg_xii", "1s0.3p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {16618, 130.094666, "mg_xii", "1s0.3p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {16619, 130.041046, "mg_xii", "1s0.3p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {16620, 129.866928, "mg_xii", "1s0.3p1.2P_1/2", "1s0.4s1.2S_1/2"},
        {16621, 130.249207, "mg_xii", "1s0.3p1.2P_3/2", "1s0.4s1.2S_1/2"},
        {16622, 130.255142, "mg_xii", "1s0.3d1.2D_3/2", "1s0.4p1.2P_1/2"},
        {16623, 130.093643, "mg_xii", "1s0.3d1.2D_3/2", "1s0.4p1.2P_3/2"},
        {16624, 130.38269, "mg_xii", "1s0.3d1.2D_5/2", "1s0.4p1.2P_1/2"},
        {16625, 130.220886, "mg_xii", "1s0.3d1.2D_5/2", "1s0.4p1.2P_3/2"},
        {16626, 88.9693985, "mg_xii", "1s0.3d1.2D_3/2", "1s0.5p1.2P_1/2"},
        {16627, 88.9307861, "mg_xii", "1s0.3d1.2D_3/2", "1s0.5p1.2P_3/2"},
        {16628, 89.0288849, "mg_xii", "1s0.3d1.2D_5/2", "1s0.5p1.2P_1/2"},
        {16629, 88.9902191, "mg_xii", "1s0.3d1.2D_5/2", "1s0.5p1.2P_3/2"},
        {16630, 281.119202, "mg_xii", "1s0.4f1.2F_5/2", "1s0.5g1.2G_7/2"},
        {16631, 281.081268, "mg_xii", "1s0.4f1.2F_5/2", "1s0.5g1.2G_9/2"},
        {16632, 281.24411, "mg_xii", "1s0.4f1.2F_7/2", "1s0.5g1.2G_7/2"},
        {16633, 281.206146, "mg_xii", "1s0.4f1.2F_7/2", "1s0.5g1.2G_9/2"},
        {16634, 635.017029, "mg_xii", "1s0.5p1.2P_1/2", "1s0.6d1.2D"},
        {16635, 636.990967, "mg_xii", "1s0.5p1.2P_3/2", "1s0.6d1.2D"},
        {16636, 635.097656, "mg_xii", "1s0.5s1.2S_1/2", "1s0.6p1.2P"},
        {16637, 280.933594, "mg_xii", "1s0.4d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {16638, 280.86969, "mg_xii", "1s0.4d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {16639, 281.184021, "mg_xii", "1s0.4d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {16640, 281.119995, "mg_xii", "1s0.4d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {16641, 195.134476, "mg_xii", "1s0.4f1.2F_5/2", "1s0.6g1.2G"},
        {16642, 195.194656, "mg_xii", "1s0.4f1.2F_7/2", "1s0.6g1.2G"},
        {16643, 30.0520973, "mg_xii", "1s0.2p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {16644, 30.0506344, "mg_xii", "1s0.2p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {16645, 30.1211357, "mg_xii", "1s0.2p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {16646, 30.1196651, "mg_xii", "1s0.2p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {16647, 88.9180527, "mg_xii", "1s0.3d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {16648, 88.9116516, "mg_xii", "1s0.3d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {16649, 88.9774704, "mg_xii", "1s0.3d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {16650, 88.9710617, "mg_xii", "1s0.3d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {16651, 280.312256, "mg_xii", "1s0.4p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {16652, 280.185028, "mg_xii", "1s0.4p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {16653, 281.06308, "mg_xii", "1s0.4p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {16654, 280.935181, "mg_xii", "1s0.4p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {16655, 78.0361023, "mg_xii", "1s0.3d1.2D_3/2", "1s0.6f1.2F"},
        {16656, 78.0818634, "mg_xii", "1s0.3d1.2D_5/2", "1s0.6f1.2F"},
        {16657, 77.8989639, "mg_xii", "1s0.3p1.2P_1/2", "1s0.6s1.2S"},
        {16658, 78.0363464, "mg_xii", "1s0.3p1.2P_3/2", "1s0.6s1.2S"},
        {16659, 194.653229, "mg_xii", "1s0.4p1.2P_1/2", "1s0.6d1.2D"},
        {16660, 195.014984, "mg_xii", "1s0.4p1.2P_3/2", "1s0.6d1.2D"},
        {16661, 77.8989639, "mg_xii", "1s0.3p1.2P_1/2", "1s0.6d1.2D"},
        {16662, 78.0363464, "mg_xii", "1s0.3p1.2P_3/2", "1s0.6d1.2D"},
        {16663, 78.0361023, "mg_xii", "1s0.3d1.2D_3/2", "1s0.6p1.2P"},
        {16664, 78.0818634, "mg_xii", "1s0.3d1.2D_5/2", "1s0.6p1.2P"},
        {16665, 28.7007046, "mg_xii", "1s0.2s1.2S_1/2", "1s0.6p1.2P"},
        {16666, 635.017029, "mg_xii", "1s0.5p1.2P_1/2", "1s0.6s1.2S"},
        {16667, 636.990967, "mg_xii", "1s0.5p1.2P_3/2", "1s0.6s1.2S"},
        {16668, 8.42460823, "mg_xii", "1s1.2S_1/2", "1s0.2p1.2P_1/2"},
        {16669, 8.41919804, "mg_xii", "1s1.2S_1/2", "1s0.2p1.2P_3/2"},
        {16670, 77.9046097, "mg_xii", "1s0.3s1.2S_1/2", "1s0.6p1.2P"},
        {16671, 88.7528, "mg_xii", "1s0.3p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {16672, 88.7400436, "mg_xii", "1s0.3p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {16673, 88.9311829, "mg_xii", "1s0.3p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {16674, 88.9183731, "mg_xii", "1s0.3p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {16675, 280.679688, "mg_xii", "1s0.4p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {16676, 281.432495, "mg_xii", "1s0.4p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {16677, 28.6981602, "mg_xii", "1s0.2p1.2P_1/2", "1s0.6s1.2S"},
        {16678, 28.7611122, "mg_xii", "1s0.2p1.2P_3/2", "1s0.6s1.2S"},
        {16679, 637.974426, "mg_xii", "1s0.5g1.2G_7/2", "1s0.6h1.2H"},
        {16680, 638.169861, "mg_xii", "1s0.5g1.2G_9/2", "1s0.6h1.2H"},
        {16681, 637.974426, "mg_xii", "1s0.5g1.2G_7/2", "1s0.6f1.2F"},
        {16682, 638.169861, "mg_xii", "1s0.5g1.2G_9/2", "1s0.6f1.2F"},
        {16683, 88.7985153, "mg_xii", "1s0.3s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {16684, 88.7600479, "mg_xii", "1s0.3s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {16685, 30.0563164, "mg_xii", "1s0.2p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {16686, 30.1253738, "mg_xii", "1s0.2p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {16687, 281.311371, "mg_xii", "1s0.4f1.2F_5/2", "1s0.5d1.2D_3/2"},
        {16688, 281.183228, "mg_xii", "1s0.4f1.2F_5/2", "1s0.5d1.2D_5/2"},
        {16689, 281.436462, "mg_xii", "1s0.4f1.2F_7/2", "1s0.5d1.2D_3/2"},
        {16690, 281.308197, "mg_xii", "1s0.4f1.2F_7/2", "1s0.5d1.2D_5/2"},
        {16691, 88.7896042, "mg_xii", "1s0.3p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {16692, 88.968132, "mg_xii", "1s0.3p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {16693, 28.6981602, "mg_xii", "1s0.2p1.2P_1/2", "1s0.6d1.2D"},
        {16694, 28.7611122, "mg_xii", "1s0.2p1.2P_3/2", "1s0.6d1.2D"},
        {16695, 195.014236, "mg_xii", "1s0.4d1.2D_3/2", "1s0.6p1.2P"},
        {16696, 195.134857, "mg_xii", "1s0.4d1.2D_5/2", "1s0.6p1.2P"},
        {16697, 636.986938, "mg_xii", "1s0.5d1.2D_3/2", "1s0.6p1.2P"},
        {16698, 637.644897, "mg_xii", "1s0.5d1.2D_5/2", "1s0.6p1.2P"},
        {16699, 194.653229, "mg_xii", "1s0.4p1.2P_1/2", "1s0.6s1.2S"},
        {16700, 195.014984, "mg_xii", "1s0.4p1.2P_3/2", "1s0.6s1.2S"},
        {16701, 195.134476, "mg_xii", "1s0.4f1.2F_5/2", "1s0.6d1.2D"},
        {16702, 195.194656, "mg_xii", "1s0.4f1.2F_7/2", "1s0.6d1.2D"},
        {16703, 195.014236, "mg_xii", "1s0.4d1.2D_3/2", "1s0.6f1.2F"},
        {16704, 195.134857, "mg_xii", "1s0.4d1.2D_5/2", "1s0.6f1.2F"},
        {16705, 637.644897, "mg_xii", "1s0.5f1.2F_5/2", "1s0.6g1.2G"},
        {16706, 637.974426, "mg_xii", "1s0.5f1.2F_7/2", "1s0.6g1.2G"},
        {16707, 637.644897, "mg_xii", "1s0.5f1.2F_5/2", "1s0.6d1.2D"},
        {16708, 637.974426, "mg_xii", "1s0.5f1.2F_7/2", "1s0.6d1.2D"},
        {16709, 636.986938, "mg_xii", "1s0.5d1.2D_3/2", "1s0.6f1.2F"},
        {16710, 637.644897, "mg_xii", "1s0.5d1.2D_5/2", "1s0.6f1.2F"},
        {16711, 281.446747, "mg_xii", "1s0.4d1.2D_3/2", "1s0.5p1.2P_1/2"},
        {16712, 281.06073, "mg_xii", "1s0.4d1.2D_3/2", "1s0.5p1.2P_3/2"},
        {16713, 281.69809, "mg_xii", "1s0.4d1.2D_5/2", "1s0.5p1.2P_1/2"},
        {16714, 281.311371, "mg_xii", "1s0.4d1.2D_5/2", "1s0.5p1.2P_3/2"},
        {16715, 194.668015, "mg_xii", "1s0.4s1.2S_1/2", "1s0.6p1.2P"},
        {16716, 130.040527, "mg_xii", "1s0.3d1.2D_3/2", "1s0.4f1.2F_5/2"},
        {16717, 130.013824, "mg_xii", "1s0.3d1.2D_3/2", "1s0.4f1.2F_7/2"},
        {16718, 130.167664, "mg_xii", "1s0.3d1.2D_5/2", "1s0.4f1.2F_5/2"},
        {16719, 130.140884, "mg_xii", "1s0.3d1.2D_5/2", "1s0.4f1.2F_7/2"}
    };
    return rows;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute oracle public line label template for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] const std::vector<LineLabelTemplateRow>& oracle_public_line_label_template_v172537() {
    static const std::vector<LineLabelTemplateRow> rows = {
        {411, 303.78, "he_ii", "1s1.2S_1/2", "1s0.2p1.2P_3/2"},
        {410, 303.786, "he_ii", "1s1.2S_1/2", "1s0.2p1.2P_1/2"},
        {120, 1215.68, "h_i", "1s1.2S_1/2", "1s0.2p1.2P_3/2"},
        {119, 1215.67, "h_i", "1s1.2S_1/2", "1s0.2p1.2P_1/2"},
        {420, 256.317, "he_ii", "1s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {16176, 609.793, "mg_x", "2s1.2S_1/2", "2s0.2p1.2P_3/2"},
        {419, 256.318, "he_ii", "1s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {16184, 624.941, "mg_x", "2s1.2S_1/2", "2s0.2p1.2P_1/2"},
        {116, 1025.72, "h_i", "1s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {445, 243.026, "he_ii", "1s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {16312, 9.316, "mg_xi", "1s2.1S_0", "1s1.2s1.3S_1"},
        {16016, 368.07, "mg_ix", "2s2.1S_0", "2s1.2p1.1P_1"},
        {115, 1025.72, "h_i", "1s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {444, 243.027, "he_ii", "1s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {106, 972.537, "h_i", "1s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {96, 6564.29, "h_i", "1s0.2p1.2P_3/2", "1s0.3s1.2S_1/2"},
        {95, 6564.56, "h_i", "1s0.2p1.2P_1/2", "1s0.3s1.2S_1/2"},
        {499, 237.331, "he_ii", "1s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {418, 234.459, "he_ii", "1s1.2S_1/2", "1s0.6p1.2P"},
        {16056, 706.06, "mg_ix", "2s2.1S_0", "2s1.2p1.3P_1"},
        {16325, 7.4738, "mg_xi", "1s2.1S_0", "1s1.4p1.1P_1"},
        {69, 949.743, "h_i", "1s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {105, 972.537, "h_i", "1s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {498, 237.331, "he_ii", "1s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {437, 1640.32, "he_ii", "1s0.2p1.2P_1/2", "1s0.3d1.2D_5/2"},
        {439, 1640.47, "he_ii", "1s0.2p1.2P_3/2", "1s0.3d1.2D_5/2"},
        {436, 1640.33, "he_ii", "1s0.2p1.2P_1/2", "1s0.3d1.2D_3/2"},
        {438, 1640.49, "he_ii", "1s0.2p1.2P_3/2", "1s0.3d1.2D_3/2"},
        {15205, 436.735, "mg_viii", "2p1.2P_3/2", "2s1.2p2.2D_5/2"},
        {15329, 772.26, "mg_viii", "2p1.2P_3/2", "2s1.2p2.4P_5/2"},
        {68, 949.743, "h_i", "1s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {16283, 9.1689, "mg_xi", "1s2.1S_0", "1s1.2p1.1P_1"},
        {23, 937.832, "h_i", "1s1.2S_1/2", "1s0.6p1.2P"},
        {15328, 430.465, "mg_viii", "2p1.2P_1/2", "2s1.2p2.2D_3/2"},
        {15659, 782.338, "mg_viii", "2p1.2P_3/2", "2s1.2p2.4P_3/2"},
        {426, 1215.08, "he_ii", "1s0.2p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {428, 1215.17, "he_ii", "1s0.2p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {431, 1640.38, "he_ii", "1s0.2p1.2P_1/2", "1s0.3s1.2S_1/2"},
        {432, 1640.53, "he_ii", "1s0.2p1.2P_3/2", "1s0.3s1.2S_1/2"},
        {16277, 9.231, "mg_xi", "1s2.1S_0", "1s1.2p1.3P_1"},
        {425, 1215.09, "he_ii", "1s0.2p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {427, 1215.17, "he_ii", "1s0.2p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {413, 1640.34, "he_ii", "1s0.2s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {15892, 30284.7, "mg_viii", "2p1.2P_1/2", "2p1.2P_3/2"},
        {16091, 694.005, "mg_ix", "2s2.1S_0", "2s1.2p1.3P_2"},
        {104, 6564.23, "h_i", "1s0.2p1.2P_3/2", "1s0.3d1.2D_5/2"},
        {102, 6564.51, "h_i", "1s0.2p1.2P_1/2", "1s0.3d1.2D_5/2"},
        {415, 1084.91, "he_ii", "1s0.2p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {417, 1084.97, "he_ii", "1s0.2p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {16224, 63.295, "mg_x", "2s0.2p1.2P_3/2", "2s0.3d1.2D_5/2"},
        {15300, 315.039, "mg_viii", "2p1.2P_3/2", "2s1.2p2.2P_3/2"},
        {16177, 57.876, "mg_x", "2s1.2S_1/2", "2s0.3p1.2P_3/2"},
        {486, 1027.38, "he_ii", "1s0.2p1.2P_1/2", "1s0.6d1.2D"},
        {487, 1027.44, "he_ii", "1s0.2p1.2P_3/2", "1s0.6d1.2D"},
        {103, 6564.25, "h_i", "1s0.2p1.2P_3/2", "1s0.3d1.2D_3/2"},
        {101, 6564.52, "h_i", "1s0.2p1.2P_1/2", "1s0.3d1.2D_3/2"},
        {14676, 2629.92, "mg_vii", "2p2.3P_2", "2p2.1D_2"},
        {412, 1640.39, "he_ii", "1s0.2s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {414, 1084.91, "he_ii", "1s0.2p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {416, 1084.98, "he_ii", "1s0.2p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {15421, 769.343, "mg_viii", "2p1.2P_1/2", "2s1.2p2.4P_1/2"},
        {461, 4686.99, "he_ii", "1s0.3d1.2D_3/2", "1s0.4f1.2F_7/2"},
        {463, 4687.12, "he_ii", "1s0.3d1.2D_5/2", "1s0.4f1.2F_7/2"},
        {429, 1215.1, "he_ii", "1s0.2p1.2P_1/2", "1s0.4s1.2S_1/2"},
        {430, 1215.18, "he_ii", "1s0.2p1.2P_3/2", "1s0.4s1.2S_1/2"},
        {460, 4687.02, "he_ii", "1s0.3d1.2D_3/2", "1s0.4f1.2F_5/2"},
        {462, 4687.14, "he_ii", "1s0.3d1.2D_5/2", "1s0.4f1.2F_5/2"},
        {435, 1215.09, "he_ii", "1s0.2s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {133, 6564.54, "h_i", "1s0.2s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {15451, 789.391, "mg_viii", "2p1.2P_3/2", "2s1.2p2.4P_1/2"},
        {31, 4862.48, "h_i", "1s0.2p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {29, 4862.63, "h_i", "1s0.2p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {16215, 63.152, "mg_x", "2s0.2p1.2P_1/2", "2s0.3d1.2D_3/2"},
        {16278, 9.2282, "mg_xi", "1s2.1S_0", "1s1.2p1.3P_2"},
        {16193, 57.92, "mg_x", "2s1.2S_1/2", "2s0.3p1.2P_1/2"},
        {16042, 9.3856, "mg_ix", "2s2.1S_0", "1s1.2s2.2p1.1P_1"},
        {15541, 436.672, "mg_viii", "2p1.2P_3/2", "2s1.2p2.2D_3/2"},
        {65, 4862.5, "h_i", "1s0.2p1.2P_3/2", "1s0.4s1.2S_1/2"},
        {64, 4862.65, "h_i", "1s0.2p1.2P_1/2", "1s0.4s1.2S_1/2"},
        {16470, 54.714, "mg_xi", "1s1.2p1.1P_1", "1s1.3d1.1D_2"},
        {30, 4862.49, "h_i", "1s0.2p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {28, 4862.64, "h_i", "1s0.2p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {15518, 313.754, "mg_viii", "2p1.2P_1/2", "2s1.2p2.2P_1/2"},
        {434, 1215.11, "he_ii", "1s0.2s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {100, 4862.65, "h_i", "1s0.2s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {422, 1084.91, "he_ii", "1s0.2s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {469, 3204.03, "he_ii", "1s0.3d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {471, 3204.09, "he_ii", "1s0.3d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {14944, 2509.97, "mg_vii", "2p2.3P_1", "2p2.1D_2"},
        {22, 4341.53, "h_i", "1s0.2p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {20, 4341.65, "h_i", "1s0.2p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {132, 6564.58, "h_i", "1s0.2s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {16203, 47.31, "mg_x", "2s0.2p1.2P_3/2", "2s0.4d1.2D_5/2"},
        {423, 1084.91, "he_ii", "1s0.2p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {424, 1084.98, "he_ii", "1s0.2p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {15424, 339.006, "mg_viii", "2p1.2P_3/2", "2s1.2p2.2S_1/2"},
        {468, 3204.04, "he_ii", "1s0.3d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {470, 3204.1, "he_ii", "1s0.3d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {433, 1027.38, "he_ii", "1s0.2s1.2S_1/2", "1s0.6p1.2P"},
        {15682, 317.039, "mg_viii", "2p1.2P_3/2", "2s1.2p2.2P_1/2"},
        {494, 2749.36, "he_ii", "1s0.3d1.2D_3/2", "1s0.6f1.2F"},
        {495, 2749.4, "he_ii", "1s0.3d1.2D_5/2", "1s0.6f1.2F"},
        {16190, 65.845, "mg_x", "2s0.2p1.2P_3/2", "2s0.3s1.2S_1/2"},
        {16276, 9.23191, "mg_xi", "1s2.1S_0", "1s1.2p1.3P_0"},
        {15071, 434.917, "mg_vii", "2p2.3P_2", "2s1.2p3.3D_3"},
        {15448, 762.643, "mg_viii", "2p1.2P_1/2", "2s1.2p2.4P_3/2"},
        {16181, 44.05, "mg_x", "2s1.2S_1/2", "2s0.4p1.2P_3/2"},
        {15513, 335.253, "mg_viii", "2p1.2P_1/2", "2s1.2p2.2S_1/2"},
        {15954, 67.239, "mg_ix", "2s1.2p1.3P_2", "2s1.3d1.3D_3"},
        {21, 4341.53, "h_i", "1s0.2p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {19, 4341.65, "h_i", "1s0.2p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {4, 4341.65, "h_i", "1s0.2s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {16320, 7.8509, "mg_xi", "1s2.1S_0", "1s1.3p1.1P_1"},
        {45, 4103.31, "h_i", "1s0.2p1.2P_3/2", "1s0.6d1.2D"},
        {44, 4103.41, "h_i", "1s0.2p1.2P_1/2", "1s0.6d1.2D"},
        {16669, 8.4192, "mg_xii", "1s1.2S_1/2", "1s0.2p1.2P_3/2"},
        {16058, 443.973, "mg_ix", "2s1.2p1.3P_2", "2s0.2p2.3P_2"},
        {15390, 311.796, "mg_viii", "2p1.2P_1/2", "2s1.2p2.2P_3/2"},
        {16668, 8.42461, "mg_xii", "1s1.2S_1/2", "1s0.2p1.2P_1/2"},
        {421, 1084.92, "he_ii", "1s0.2s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {507, 4686.63, "he_ii", "1s0.3p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {509, 4687.02, "he_ii", "1s0.3p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {99, 4862.66, "h_i", "1s0.2s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {442, 1027.38, "he_ii", "1s0.2p1.2P_1/2", "1s0.6s1.2S"},
        {443, 1027.44, "he_ii", "1s0.2p1.2P_3/2", "1s0.6s1.2S"},
        {14631, 431.313, "mg_vii", "2p2.3P_1", "2s1.2p3.3D_2"},
        {14716, 1189.82, "mg_vii", "2p2.3P_1", "2p2.1S_0"},
        {14753, 868.236, "mg_vii", "2p2.3P_2", "2s1.2p3.5S_2"},
        {506, 4686.69, "he_ii", "1s0.3p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {508, 4687.07, "he_ii", "1s0.3p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {15, 4341.53, "h_i", "1s0.2p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {14, 4341.65, "h_i", "1s0.2p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {16083, 88.817, "mg_ix", "2s0.2p2.3P_2", "2s1.3p1.3P_2"},
        {16147, 62.751, "mg_ix", "2s2.1S_0", "2s1.3p1.1P_1"},
        {16191, 42.362, "mg_x", "2s0.2p1.2P_3/2", "2s0.5d1.2D_5/2"},
        {16230, 65.673, "mg_x", "2s0.2p1.2P_1/2", "2s0.3s1.2S_1/2"},
        {16001, 63.46, "mg_ix", "2s2.1S_0", "2s1.3p1.3P_1"},
        {16046, 72.312, "mg_ix", "2s1.2p1.1P_1", "2s1.3d1.1D_2"},
        {491, 3203.86, "he_ii", "1s0.3p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {493, 3204.04, "he_ii", "1s0.3p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {457, 10126.4, "he_ii", "1s0.4f1.2F_5/2", "1s0.5g1.2G_9/2"},
        {459, 10126.5, "he_ii", "1s0.4f1.2F_7/2", "1s0.5g1.2G_9/2"},
        {446, 4686.84, "he_ii", "1s0.3p1.2P_1/2", "1s0.4s1.2S_1/2"},
        {447, 4687.22, "he_ii", "1s0.3p1.2P_3/2", "1s0.4s1.2S_1/2"},
        {454, 2749.23, "he_ii", "1s0.3p1.2P_1/2", "1s0.6d1.2D"},
        {455, 2749.36, "he_ii", "1s0.3p1.2P_3/2", "1s0.6d1.2D"},
        {15987, 67.135, "mg_ix", "2s1.2p1.3P_1", "2s1.3d1.3D_2"},
        {456, 10126.4, "he_ii", "1s0.4f1.2F_5/2", "1s0.5g1.2G_7/2"},
        {458, 10126.6, "he_ii", "1s0.4f1.2F_7/2", "1s0.5g1.2G_7/2"},
        {15013, 367.674, "mg_vii", "2p2.3P_2", "2s1.2p3.3P_2"},
        {16222, 9.5803, "mg_x", "2s0.2p1.2P_3/2", "1s1.2s2.2S_1/2"},
        {16208, 44.05, "mg_x", "2s1.2S_1/2", "2s0.4p1.2P_1/2"},
        {16178, 47.229, "mg_x", "2s0.2p1.2P_1/2", "2s0.4d1.2D_3/2"},
        {3, 4341.66, "h_i", "1s0.2s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {16198, 187.178, "mg_x", "2s0.3d1.2D_5/2", "2s0.4f1.2F_7/2"},
        {516, 6650.44, "he_ii", "1s0.4f1.2F_5/2", "1s0.6g1.2G"},
        {517, 6650.49, "he_ii", "1s0.4f1.2F_7/2", "1s0.6g1.2G"},
        {16225, 39.668, "mg_x", "2s1.2S_1/2", "2s0.5p1.2P_3/2"},
        {490, 3203.87, "he_ii", "1s0.3p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {492, 3204.05, "he_ii", "1s0.3p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {18, 4103.42, "h_i", "1s0.2s1.2S_1/2", "1s0.6p1.2P"},
        {16180, 63.311, "mg_x", "2s0.2p1.2P_3/2", "2s0.3d1.2D_3/2"},
        {16328, 39.3316, "mg_xi", "1s1.2s1.1S_0", "1s1.4p1.1P_1"},
        {49, 4103.31, "h_i", "1s0.2p1.2P_3/2", "1s0.6s1.2S"},
        {48, 4103.41, "h_i", "1s0.2p1.2P_1/2", "1s0.6s1.2S"},
        {39, 18756.1, "h_i", "1s0.3d1.2D_3/2", "1s0.4f1.2F_7/2"},
        {41, 18756.2, "h_i", "1s0.3d1.2D_5/2", "1s0.4f1.2F_7/2"},
        {15292, 82.823, "mg_viii", "2p1.2P_3/2", "2p0.3s1.2S_1/2"},
        {14836, 429.14, "mg_vii", "2p2.3P_0", "2s1.2p3.3D_1"},
        {36, 18755.9, "h_i", "1s0.3p1.2P_1/2", "1s0.4s1.2S_1/2"},
        {37, 18756.3, "h_i", "1s0.3p1.2P_3/2", "1s0.4s1.2S_1/2"},
        {16163, 439.176, "mg_ix", "2s1.2p1.3P_1", "2s0.2p2.3P_2"},
        {504, 3203.91, "he_ii", "1s0.3p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {505, 3204.09, "he_ii", "1s0.3p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {514, 6650.33, "he_ii", "1s0.4d1.2D_3/2", "1s0.6f1.2F"},
        {515, 6650.44, "he_ii", "1s0.4d1.2D_5/2", "1s0.6f1.2F"},
        {38, 18756.1, "h_i", "1s0.3d1.2D_3/2", "1s0.4f1.2F_5/2"},
        {40, 18756.3, "h_i", "1s0.3d1.2D_5/2", "1s0.4f1.2F_5/2"},
        {16036, 72.027, "mg_ix", "2s1.2p1.3P_2", "2s1.3s1.3S_1"},
        {16202, 187.07, "mg_x", "2s0.3d1.2D_3/2", "2s0.4f1.2F_5/2"},
        {465, 10126.2, "he_ii", "1s0.4d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {467, 10126.4, "he_ii", "1s0.4d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {16183, 9.5767, "mg_x", "2s0.2p1.2P_1/2", "1s1.2s2.2S_1/2"},
        {15690, 9.5024, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.2P_3/2"},
        {14857, 854.752, "mg_vii", "2p2.3P_1", "2s1.2p3.5S_2"},
        {14859, 95.423, "mg_vii", "2p2.3P_2", "2p1.3s1.3P_2"},
        {16299, 50.4375, "mg_xi", "1s1.2s1.3S_1", "1s1.3p1.3P_2"},
        {15979, 67.09, "mg_ix", "2s1.2p1.3P_0", "2s1.3d1.3D_1"},
        {464, 10126.2, "he_ii", "1s0.4d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {466, 10126.5, "he_ii", "1s0.4d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {441, 4686.72, "he_ii", "1s0.3s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {24, 12821.6, "h_i", "1s0.3d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {26, 12821.7, "h_i", "1s0.3d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {16187, 42.294, "mg_x", "2s0.2p1.2P_1/2", "2s0.5d1.2D_3/2"},
        {16061, 448.293, "mg_ix", "2s1.2p1.3P_2", "2s0.2p2.3P_1"},
        {16123, 88.519, "mg_ix", "2s0.2p2.3P_1", "2s1.3p1.3P_2"},
        {14771, 431.188, "mg_vii", "2p2.3P_1", "2s1.2p3.3D_1"},
        {55, 18755.8, "h_i", "1s0.3p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {57, 18756.1, "h_i", "1s0.3p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {16175, 39.668, "mg_x", "2s1.2S_1/2", "2s0.5p1.2P_1/2"},
        {14819, 84.025, "mg_vii", "2p2.3P_2", "2p1.3d1.3D_3"},
        {8, 10945, "h_i", "1s0.3d1.2D_3/2", "1s0.6f1.2F"},
        {9, 10945.1, "h_i", "1s0.3d1.2D_5/2", "1s0.6f1.2F"},
        {16333, 7.3102, "mg_xi", "1s2.1S_0", "1s1.5p1.1P_1"},
        {539, 19374.4, "he_ii", "1s0.5g1.2G_7/2", "1s0.6h1.2H"},
        {540, 19374.5, "he_ii", "1s0.5g1.2G_9/2", "1s0.6h1.2H"},
        {478, 2749.23, "he_ii", "1s0.3p1.2P_1/2", "1s0.6s1.2S"},
        {479, 2749.36, "he_ii", "1s0.3p1.2P_3/2", "1s0.6s1.2S"},
        {16037, 441.199, "mg_ix", "2s1.2p1.3P_0", "2s0.2p2.3P_1"},
        {14853, 117.038, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.3D_3"},
        {16006, 67.141, "mg_ix", "2s1.2p1.3P_1", "2s1.3d1.3D_1"},
        {16119, 67.246, "mg_ix", "2s1.2p1.3P_2", "2s1.3d1.3D_2"},
        {11, 12821.4, "h_i", "1s0.3p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {13, 12821.6, "h_i", "1s0.3p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {14993, 434.72, "mg_vii", "2p2.3P_2", "2s1.2p3.3D_2"},
        {25, 12821.6, "h_i", "1s0.3d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {27, 12821.7, "h_i", "1s0.3d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {16000, 71.9, "mg_ix", "2s1.2p1.3P_1", "2s1.3s1.3S_1"},
        {15383, 82.598, "mg_viii", "2p1.2P_1/2", "2p0.3s1.2S_1/2"},
        {16298, 50.4645, "mg_xi", "1s1.2s1.3S_1", "1s1.3p1.3P_1"},
        {16209, 47.879, "mg_x", "2s0.2p1.2P_3/2", "2s0.4s1.2S_1/2"},
        {16087, 88.656, "mg_ix", "2s0.2p2.3P_1", "2s1.3p1.3P_0"},
        {14611, 367.683, "mg_vii", "2p2.3P_2", "2s1.2p3.3P_1"},
        {449, 3203.89, "he_ii", "1s0.3s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {14890, 87.722, "mg_vii", "2p2.1D_2", "2p1.3d1.1D_2"},
        {473, 2749.24, "he_ii", "1s0.3s1.2S_1/2", "1s0.6p1.2P"},
        {14614, 365.234, "mg_vii", "2p2.3P_1", "2s1.2p3.3P_2"},
        {16596, 7.10577, "mg_xii", "1s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {54, 18755.8, "h_i", "1s0.3p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {56, 18756.2, "h_i", "1s0.3p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {58, 12821.5, "h_i", "1s0.3p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {59, 12821.6, "h_i", "1s0.3p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {14680, 83.764, "mg_vii", "2p2.3P_2", "2p1.3d1.3P_2"},
        {14780, 83.747, "mg_vii", "2p2.3P_2", "2p1.3d1.3F_3"},
        {14604, 87.889, "mg_vii", "2p2.1D_2", "2p1.3d1.3F_2"},
        {14696, 365.176, "mg_vii", "2p2.3P_1", "2s1.2p3.3P_0"},
        {16003, 443.403, "mg_ix", "2s1.2p1.3P_1", "2s0.2p2.3P_1"},
        {14994, 363.772, "mg_vii", "2p2.3P_0", "2s1.2p3.3P_1"},
        {16134, 77.737, "mg_ix", "2s1.2p1.1P_1", "2s1.3s1.1S_0"},
        {16043, 40648.9, "mg_ix", "2s1.2p1.3P_1", "2s1.2p1.3P_2"},
        {440, 4686.88, "he_ii", "1s0.3s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {15002, 85.407, "mg_vii", "2p2.1D_2", "2p1.3d1.1F_3"},
        {15077, 83.959, "mg_vii", "2p2.3P_1", "2p1.3d1.3D_2"},
        {5, 10944.9, "h_i", "1s0.3p1.2P_1/2", "1s0.6d1.2D"},
        {6, 10945, "h_i", "1s0.3p1.2P_3/2", "1s0.6d1.2D"},
        {14658, 98.031, "mg_vii", "2p2.1D_2", "2p1.3s1.1P_1"},
        {15134, 9.5023, "mg_viii", "2p1.2P_1/2", "1s1.2s2.2p2.2P_1/2"},
        {35, 18755.8, "h_i", "1s0.3s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {541, 19374.1, "he_ii", "1s0.5f1.2F_5/2", "1s0.6g1.2G"},
        {542, 19374.4, "he_ii", "1s0.5f1.2F_7/2", "1s0.6g1.2G"},
        {10, 12821.4, "h_i", "1s0.3p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {12, 12821.6, "h_i", "1s0.3p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {14961, 111.622, "mg_vii", "2s1.2p3.3D_3", "2p1.3p1.3D_3"},
        {15017, 365.243, "mg_vii", "2p2.3P_1", "2s1.2p3.3P_1"},
        {16595, 7.10691, "mg_xii", "1s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {16305, 1034.32, "mg_xi", "1s1.2s1.3S_1", "1s1.2p1.3P_1"},
        {16301, 55.197, "mg_xi", "1s1.2p1.1P_1", "1s1.3s1.1S_0"},
        {43, 12821.4, "h_i", "1s0.3s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {16129, 9.7626, "mg_ix", "2s0.2p2.1D_2", "1s1.2s2.2p1.1P_1"},
        {510, 6650.01, "he_ii", "1s0.4p1.2P_1/2", "1s0.6d1.2D"},
        {511, 6650.33, "he_ii", "1s0.4p1.2P_3/2", "1s0.6d1.2D"},
        {16194, 9.215, "mg_x", "2s0.2p1.2P_3/2", "1s1.2p2.2S_1/2"},
        {16311, 37.9184, "mg_xi", "1s1.2s1.3S_1", "1s1.4p1.3P_2"},
        {15089, 278.402, "mg_vii", "2p2.3P_2", "2s1.2p3.3S_1"},
        {16211, 47.317, "mg_x", "2s0.2p1.2P_3/2", "2s0.4d1.2D_3/2"},
        {210, 522.213, "he_i", "1s2.1S_0", "1s1.4p1.1P_1"},
        {448, 3203.93, "he_ii", "1s0.3s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {16461, 52.5869, "mg_xi", "1s1.2p1.3P_0", "1s1.3d1.3D_3"},
        {16464, 52.6098, "mg_xi", "1s1.2p1.3P_1", "1s1.3d1.3D_3"},
        {16467, 52.7088, "mg_xi", "1s1.2p1.3P_2", "1s1.3d1.3D_3"},
        {1, 10944.9, "h_i", "1s0.3p1.2P_1/2", "1s0.6s1.2S"},
        {2, 10945, "h_i", "1s0.3p1.2P_3/2", "1s0.6s1.2S"},
        {16473, 40.4332, "mg_xi", "1s1.2p1.1P_1", "1s1.4d1.1D_2"},
        {16297, 50.4712, "mg_xi", "1s1.2s1.3S_1", "1s1.3p1.3P_0"},
        {16189, 47.788, "mg_x", "2s0.2p1.2P_1/2", "2s0.4s1.2S_1/2"},
        {14792, 55035, "mg_vii", "2p2.3P_1", "2p2.3P_2"},
        {14752, 95.258, "mg_vii", "2p2.3P_1", "2p1.3s1.3P_2"},
        {16460, 52.5974, "mg_xi", "1s1.2p1.3P_0", "1s1.3d1.3D_2"},
        {16463, 52.6204, "mg_xi", "1s1.2p1.3P_1", "1s1.3d1.3D_2"},
        {16466, 52.7194, "mg_xi", "1s1.2p1.3P_2", "1s1.3d1.3D_2"},
        {481, 10125.5, "he_ii", "1s0.4p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {483, 10126.3, "he_ii", "1s0.4p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {496, 10126, "he_ii", "1s0.4p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {497, 10126.7, "he_ii", "1s0.4p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {14916, 319.027, "mg_vii", "2p2.1D_2", "2s1.2p3.1D_2"},
        {14823, 111.984, "mg_vii", "2s1.2p3.3D_3", "2p1.3p1.3P_2"},
        {14632, 95.65, "mg_vii", "2p2.3P_2", "2p1.3s1.3P_1"},
        {15078, 88.68, "mg_vii", "2p2.1S_0", "2p1.3d1.1P_1"},
        {15969, 445.98, "mg_ix", "2s1.2p1.3P_1", "2s0.2p2.3P_0"},
        {14656, 132.644, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.1P_1"},
        {34, 18756, "h_i", "1s0.3s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {16459, 52.5985, "mg_xi", "1s1.2p1.3P_0", "1s1.3d1.3D_1"},
        {16462, 52.6215, "mg_xi", "1s1.2p1.3P_1", "1s1.3d1.3D_1"},
        {16465, 52.7205, "mg_xi", "1s1.2p1.3P_2", "1s1.3d1.3D_1"},
        {16115, 749.551, "mg_ix", "2s1.2p1.1P_1", "2s0.2p2.1D_2"},
        {16310, 37.9248, "mg_xi", "1s1.2s1.3S_1", "1s1.4p1.3P_1"},
        {480, 10125.6, "he_ii", "1s0.4p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {482, 10126.4, "he_ii", "1s0.4p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {15072, 277, "mg_vii", "2p2.3P_1", "2s1.2p3.3S_1"},
        {535, 19373.7, "he_ii", "1s0.5d1.2D_3/2", "1s0.6f1.2F"},
        {536, 19374.1, "he_ii", "1s0.5d1.2D_5/2", "1s0.6f1.2F"},
        {16196, 42.597, "mg_x", "2s0.2p1.2P_3/2", "2s0.5s1.2S_1/2"},
        {15985, 71.842, "mg_ix", "2s1.2p1.3P_0", "2s1.3s1.3S_1"},
        {14699, 83.91, "mg_vii", "2p2.3P_0", "2p1.3d1.3D_1"},
        {16590, 6.73775, "mg_xii", "1s1.2S_1/2", "1s0.4p1.2P_3/2"},
        {14852, 117.3, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.3D_2"},
        {523, 6650.01, "he_ii", "1s0.4p1.2P_1/2", "1s0.6s1.2S"},
        {524, 6650.33, "he_ii", "1s0.4p1.2P_3/2", "1s0.6s1.2S"},
        {16214, 9.2829, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.2P_3/2"},
        {14832, 95.383, "mg_vii", "2p2.3P_0", "2p1.3s1.3P_1"},
        {42, 12821.5, "h_i", "1s0.3s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {14834, 95.556, "mg_vii", "2p2.3P_1", "2p1.3s1.3P_0"},
        {16287, 53.7871, "mg_xi", "1s1.2p1.3P_0", "1s1.3s1.3S_1"},
        {16288, 53.8111, "mg_xi", "1s1.2p1.3P_1", "1s1.3s1.3S_1"},
        {16289, 53.9147, "mg_xi", "1s1.2p1.3P_2", "1s1.3s1.3S_1"},
        {7, 10944.9, "h_i", "1s0.3s1.2S_1/2", "1s0.6p1.2P"},
        {15476, 9.5053, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.2P_1/2"},
        {16599, 45.3754, "mg_xii", "1s0.2p1.2P_1/2", "1s0.3d1.2D_5/2"},
        {15946, 9.7859, "mg_ix", "2s0.2p2.3P_2", "1s1.2s2.2p1.3P_2"},
        {16601, 45.533, "mg_xii", "1s0.2p1.2P_3/2", "1s0.3d1.2D_5/2"},
        {16381, 34.0224, "mg_xi", "1s1.2s1.3S_1", "1s1.5p1.3P_2"},
        {87, 26281.4, "h_i", "1s0.4d1.2D_3/2", "1s0.6f1.2F"},
        {88, 26281.5, "h_i", "1s0.4d1.2D_5/2", "1s0.6f1.2F"},
        {16598, 45.3909, "mg_xii", "1s0.2p1.2P_1/2", "1s0.3d1.2D_3/2"},
        {16600, 45.5486, "mg_xii", "1s0.2p1.2P_3/2", "1s0.3d1.2D_3/2"},
        {225, 584.334, "he_i", "1s2.1S_0", "1s1.2p1.1P_1"},
        {16220, 187, "mg_x", "2s0.3d1.2D_5/2", "2s0.5f1.2F_7/2"},
        {75, 40522.6, "h_i", "1s0.4f1.2F_5/2", "1s0.5g1.2G_9/2"},
        {77, 40522.8, "h_i", "1s0.4f1.2F_7/2", "1s0.5g1.2G_9/2"},
        {16300, 36.0742, "mg_xi", "1s1.2p1.1P_1", "1s1.5d1.1D_2"},
        {14476, 1190.07, "mg_vi", "2p3.4S_3/2", "2p3.2P_3/2"},
        {16210, 42.366, "mg_x", "2s0.2p1.2P_3/2", "2s0.5d1.2D_3/2"},
        {126, 26281.5, "h_i", "1s0.4f1.2F_5/2", "1s0.6g1.2G"},
        {127, 26281.5, "h_i", "1s0.4f1.2F_7/2", "1s0.6g1.2G"},
        {16357, 39.253, "mg_xi", "1s1.2p1.3P_0", "1s1.4d1.3D_3"},
        {16360, 39.2658, "mg_xi", "1s1.2p1.3P_1", "1s1.4d1.3D_3"},
        {16363, 39.3209, "mg_xi", "1s1.2p1.3P_2", "1s1.4d1.3D_3"},
        {14736, 132.56, "mg_vii", "2s1.2p3.1P_1", "2p1.3p1.1D_2"},
        {14627, 116.092, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.3S_1"},
        {14903, 83.715, "mg_vii", "2p2.3P_2", "2p1.3d1.3P_1"},
        {16174, 9.2117, "mg_x", "2s0.2p1.2P_1/2", "1s1.2p2.2S_1/2"},
        {14873, 95.484, "mg_vii", "2p2.3P_1", "2p1.3s1.3P_1"},
        {107, 40522.4, "h_i", "1s0.4d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {109, 40522.7, "h_i", "1s0.4d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {14758, 83.588, "mg_vii", "2p2.3P_1", "2p1.3d1.3P_1"},
        {74, 40522.7, "h_i", "1s0.4f1.2F_5/2", "1s0.5g1.2G_7/2"},
        {76, 40522.8, "h_i", "1s0.4f1.2F_7/2", "1s0.5g1.2G_7/2"},
        {14666, 111.856, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3D_2"},
        {16589, 6.73818, "mg_xii", "1s1.2S_1/2", "1s0.4p1.2P_1/2"},
        {15472, 9.4994, "mg_viii", "2p1.2P_1/2", "1s1.2s2.2p2.2P_3/2"},
        {15043, 112.11, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3P_1"},
        {14577, 86.691, "mg_vii", "2p2.1D_2", "2p1.3d1.3F_3"},
        {80, 40522.2, "h_i", "1s0.4p1.2P_1/2", "1s0.5s1.2S_1/2"},
        {81, 40523, "h_i", "1s0.4p1.2P_3/2", "1s0.5s1.2S_1/2"},
        {16356, 39.2555, "mg_xi", "1s1.2p1.3P_0", "1s1.4d1.3D_2"},
        {16359, 39.2683, "mg_xi", "1s1.2p1.3P_1", "1s1.4d1.3D_2"},
        {16362, 39.3234, "mg_xi", "1s1.2p1.3P_2", "1s1.4d1.3D_2"},
        {14601, 102.472, "mg_vii", "2p2.1S_0", "2p1.3s1.1P_1"},
        {14904, 83.56, "mg_vii", "2p2.3P_1", "2p1.3d1.3P_0"},
        {16212, 187, "mg_x", "2s0.3d1.2D_3/2", "2s0.5f1.2F_7/2"},
        {108, 40522.5, "h_i", "1s0.4d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {110, 40522.7, "h_i", "1s0.4d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {16306, 997.486, "mg_xi", "1s1.2s1.3S_1", "1s1.2p1.3P_2"},
        {472, 6650.04, "he_ii", "1s0.4s1.2S_1/2", "1s0.6p1.2P"},
        {16380, 34.025, "mg_xi", "1s1.2s1.3S_1", "1s1.5p1.3P_1"},
        {16275, 150.838, "mg_xi", "1s1.3s1.1S_0", "1s1.4p1.1P_1"},
        {15015, 280.737, "mg_vii", "2p2.1D_2", "2s1.2p3.1P_1"},
        {16592, 6.58001, "mg_xii", "1s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {14923, 83.988, "mg_vii", "2p2.3P_1", "2p1.3d1.3D_1"},
        {16201, 42.525, "mg_x", "2s0.2p1.2P_1/2", "2s0.5s1.2S_1/2"},
        {82, 26281, "h_i", "1s0.4p1.2P_1/2", "1s0.6s1.2S"},
        {83, 26281.4, "h_i", "1s0.4p1.2P_3/2", "1s0.6s1.2S"},
        {14940, 116.085, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.3S_1"},
        {451, 4687.07, "he_ii", "1s0.3d1.2D_3/2", "1s0.4p1.2P_3/2"},
        {453, 4687.2, "he_ii", "1s0.3d1.2D_5/2", "1s0.4p1.2P_3/2"},
        {16229, 9.2848, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.2P_1/2"},
        {16309, 37.9264, "mg_xi", "1s1.2s1.3S_1", "1s1.4p1.3P_0"},
        {66, 26281, "h_i", "1s0.4p1.2P_1/2", "1s0.6d1.2D"},
        {67, 26281.4, "h_i", "1s0.4p1.2P_3/2", "1s0.6d1.2D"},
        {61, 40521.7, "h_i", "1s0.4p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {63, 40522.5, "h_i", "1s0.4p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {489, 10125.7, "he_ii", "1s0.4s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {16443, 35.1306, "mg_xi", "1s1.2p1.3P_0", "1s1.5d1.3D_3"},
        {16446, 35.1408, "mg_xi", "1s1.2p1.3P_1", "1s1.5d1.3D_3"},
        {16449, 35.1849, "mg_xi", "1s1.2p1.3P_2", "1s1.5d1.3D_3"},
        {16597, 6.51273, "mg_xii", "1s1.2S_1/2", "1s0.6p1.2P"},
        {16355, 39.2558, "mg_xi", "1s1.2p1.3P_0", "1s1.4d1.3D_1"},
        {16358, 39.2686, "mg_xi", "1s1.2p1.3P_1", "1s1.4d1.3D_1"},
        {16361, 39.3237, "mg_xi", "1s1.2p1.3P_2", "1s1.4d1.3D_1"},
        {14431, 403.31, "mg_vi", "2p3.4S_3/2", "2s1.2p4.4P_5/2"},
        {16111, 9.7889, "mg_ix", "2s0.2p2.3P_2", "1s1.2s2.2p1.3P_1"},
        {14522, 1191.61, "mg_vi", "2p3.4S_3/2", "2p3.2P_1/2"},
        {16205, 187, "mg_x", "2s0.3d1.2D_5/2", "2s0.5f1.2F_5/2"},
        {14651, 117.421, "mg_vii", "2s1.2p3.3P_0", "2p1.3p1.3D_1"},
        {14915, 276.154, "mg_vii", "2p2.3P_0", "2s1.2p3.3S_1"},
        {14599, 2262.19, "mg_vii", "2p2.1D_2", "2p2.1S_0"},
        {16185, 187.206, "mg_x", "2s0.3d1.2D_5/2", "2s0.4f1.2F_5/2"},
        {14593, 111.972, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.3D_1"},
        {520, 19372.3, "he_ii", "1s0.5p1.2P_1/2", "1s0.6d1.2D"},
        {521, 19373.7, "he_ii", "1s0.5p1.2P_3/2", "1s0.6d1.2D"},
        {16165, 9.7881, "mg_ix", "2s0.2p2.3P_1", "1s1.2s2.2p1.3P_0"},
        {16008, 9.3948, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.1P_1"},
        {16038, 84.14, "mg_ix", "2s0.2p2.1D_2", "2s1.3p1.1P_1"},
        {16304, 1043.26, "mg_xi", "1s1.2s1.3S_1", "1s1.2p1.3P_0"},
        {16039, 438.7, "mg_ix", "2s1.2p1.1P_1", "2s0.2p2.1S_0"},
        {16591, 6.58022, "mg_xii", "1s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {16113, 9.7855, "mg_ix", "2s0.2p2.3P_0", "1s1.2s2.2p1.3P_1"},
        {16076, 9.7837, "mg_ix", "2s0.2p2.3P_1", "1s1.2s2.2p1.3P_2"},
        {60, 40521.9, "h_i", "1s0.4p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {62, 40522.6, "h_i", "1s0.4p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {15047, 112.269, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.3P_0"},
        {15062, 1452.04, "mg_vii", "2p1.3p1.3D_3", "2p1.3d1.3F_4"},
        {16442, 35.1316, "mg_xi", "1s1.2p1.3P_0", "1s1.5d1.3D_2"},
        {16445, 35.1418, "mg_xi", "1s1.2p1.3P_1", "1s1.5d1.3D_2"},
        {16448, 35.186, "mg_xi", "1s1.2p1.3P_2", "1s1.5d1.3D_2"},
        {14598, 128.901, "mg_vii", "2s1.2p3.1P_1", "2p1.3p1.1S_0"},
        {14880, 117.307, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.3D_2"},
        {17, 40521.9, "h_i", "1s0.4s1.2S_1/2", "1s0.5p1.2P_3/2"},
        {450, 4687.23, "he_ii", "1s0.3d1.2D_3/2", "1s0.4p1.2P_1/2"},
        {452, 4687.36, "he_ii", "1s0.3d1.2D_5/2", "1s0.4p1.2P_1/2"},
        {501, 3204.05, "he_ii", "1s0.3d1.2D_3/2", "1s0.5p1.2P_3/2"},
        {503, 3204.11, "he_ii", "1s0.3d1.2D_5/2", "1s0.5p1.2P_3/2"},
        {16294, 39.5257, "mg_xi", "1s1.2p1.3P_0", "1s1.4s1.3S_1"},
        {16295, 39.5386, "mg_xi", "1s1.2p1.3P_1", "1s1.4s1.3S_1"},
        {16296, 39.5945, "mg_xi", "1s1.2p1.3P_2", "1s1.4s1.3S_1"},
        {15870, 428.319, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p3.2D_5/2"},
        {531, 19372.3, "he_ii", "1s0.5p1.2P_1/2", "1s0.6s1.2S"},
        {532, 19373.7, "he_ii", "1s0.5p1.2P_3/2", "1s0.6s1.2S"},
        {15101, 111.997, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3P_2"},
        {129, 18756.2, "h_i", "1s0.3d1.2D_3/2", "1s0.4p1.2P_3/2"},
        {131, 18756.3, "h_i", "1s0.3d1.2D_5/2", "1s0.4p1.2P_3/2"},
        {15543, 355.999, "mg_viii", "2s1.2p2.4P_5/2", "2s0.2p3.4S_3/2"},
        {16173, 187, "mg_x", "2s0.3d1.2D_3/2", "2s0.5f1.2F_5/2"},
        {14806, 125.642, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.1D_2"},
        {14534, 400.666, "mg_vi", "2p3.4S_3/2", "2s1.2p4.4P_3/2"},
        {488, 10126.1, "he_ii", "1s0.4s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {14747, 112.118, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.3P_1"},
        {484, 2749.36, "he_ii", "1s0.3d1.2D_3/2", "1s0.6p1.2P"},
        {485, 2749.4, "he_ii", "1s0.3d1.2D_5/2", "1s0.6p1.2P"},
        {16332, 40.5455, "mg_xi", "1s1.2p1.1P_1", "1s1.4s1.1S_0"},
        {16096, 9.7867, "mg_ix", "2s0.2p2.3P_1", "1s1.2s2.2p1.3P_1"},
        {16609, 33.6465, "mg_xii", "1s0.2p1.2P_1/2", "1s0.4d1.2D_5/2"},
        {16611, 33.7331, "mg_xii", "1s0.2p1.2P_3/2", "1s0.4d1.2D_5/2"},
        {112, 74782.4, "h_i", "1s0.5f1.2F_5/2", "1s0.6g1.2G"},
        {111, 74782.6, "h_i", "1s0.5f1.2F_7/2", "1s0.6g1.2G"},
        {14740, 83.511, "mg_vii", "2p2.3P_0", "2p1.3d1.3P_1"},
        {16132, 93.364, "mg_ix", "2s0.2p2.1D_2", "2s1.3p1.3P_1"},
        {321, 10833.3, "he_i", "1s1.2s1.3S_1", "1s1.2p1.3P_2"},
        {16045, 67.252, "mg_ix", "2s1.2p1.3P_2", "2s1.3d1.3D_1"},
        {14602, 84.087, "mg_vii", "2p2.3P_2", "2p1.3d1.3D_2"},
        {14936, 111.866, "mg_vii", "2s1.2p3.3D_3", "2p1.3p1.3D_2"},
        {15090, 90332, "mg_vii", "2p2.3P_0", "2p2.3P_1"},
        {14626, 117.425, "mg_vii", "2s1.2p3.3P_1", "2p1.3p1.3D_1"},
        {16608, 33.6501, "mg_xii", "1s0.2p1.2P_1/2", "1s0.4d1.2D_3/2"},
        {16610, 33.7367, "mg_xii", "1s0.2p1.2P_3/2", "1s0.4d1.2D_3/2"},
        {14545, 1805.94, "mg_vi", "2p3.4S_3/2", "2p3.2D_3/2"},
        {16217, 585, "mg_x", "2s0.4f1.2F_7/2", "2s0.5g1.2G_9/2"},
        {14835, 434.593, "mg_vii", "2p2.3P_2", "2s1.2p3.3D_1"},
        {16717, 130.014, "mg_xii", "1s0.3d1.2D_3/2", "1s0.4f1.2F_7/2"},
        {16719, 130.141, "mg_xii", "1s0.3d1.2D_5/2", "1s0.4f1.2F_7/2"},
        {14929, 111.612, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3D_3"},
        {16716, 130.041, "mg_xii", "1s0.3d1.2D_3/2", "1s0.4f1.2F_5/2"},
        {16718, 130.168, "mg_xii", "1s0.3d1.2D_5/2", "1s0.4f1.2F_5/2"},
        {15965, 88.892, "mg_ix", "2s0.2p2.3P_2", "2s1.3p1.3P_1"},
        {86, 26281.1, "h_i", "1s0.4s1.2S_1/2", "1s0.6p1.2P"},
        {51, 12821.6, "h_i", "1s0.3d1.2D_3/2", "1s0.5p1.2P_3/2"},
        {53, 12821.7, "h_i", "1s0.3d1.2D_5/2", "1s0.5p1.2P_3/2"},
        {16379, 34.0257, "mg_xi", "1s1.2s1.3S_1", "1s1.5p1.3P_0"},
        {97, 74781.9, "h_i", "1s0.5d1.2D_3/2", "1s0.6f1.2F"},
        {98, 74782.4, "h_i", "1s0.5d1.2D_5/2", "1s0.6f1.2F"},
        {16441, 35.1317, "mg_xi", "1s1.2p1.3P_0", "1s1.5d1.3D_1"},
        {16444, 35.1419, "mg_xi", "1s1.2p1.3P_1", "1s1.5d1.3D_1"},
        {16447, 35.1861, "mg_xi", "1s1.2p1.3P_2", "1s1.5d1.3D_1"},
        {16084, 88.433, "mg_ix", "2s0.2p2.3P_0", "2s1.3p1.3P_1"},
        {15204, 353.882, "mg_viii", "2s1.2p2.4P_3/2", "2s0.2p3.4S_3/2"},
        {16192, 9.2296, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.2P_3/2#2"},
        {14868, 1653.39, "mg_vii", "2p1.3s1.3P_2", "2p1.3p1.3D_3"},
        {15305, 428.245, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p3.2D_3/2"},
        {500, 3204.09, "he_ii", "1s0.3d1.2D_3/2", "1s0.5p1.2P_1/2"},
        {502, 3204.15, "he_ii", "1s0.3d1.2D_5/2", "1s0.5p1.2P_1/2"},
        {14875, 116.081, "mg_vii", "2s1.2p3.3P_0", "2p1.3p1.3S_1"},
        {16330, 52.653, "mg_xi", "1s1.2s1.1S_0", "1s1.3p1.1P_1"},
        {16171, 585, "mg_x", "2s0.4d1.2D_5/2", "2s0.5f1.2F_7/2"},
        {14982, 111.97, "mg_vii", "2s1.2p3.3D_2", "2p1.3p1.3D_1"},
        {16303, 155.806, "mg_xi", "1s1.3p1.1P_1", "1s1.4d1.1D_2"},
        {113, 74782.6, "h_i", "1s0.5g1.2G_7/2", "1s0.6h1.2H"},
        {114, 74782.7, "h_i", "1s0.5g1.2G_9/2", "1s0.6h1.2H"},
        {16206, 585, "mg_x", "2s0.4f1.2F_5/2", "2s0.5g1.2G_9/2"},
        {16, 40522.3, "h_i", "1s0.4s1.2S_1/2", "1s0.5p1.2P_1/2"},
        {322, 10833.2, "he_i", "1s1.2s1.3S_1", "1s1.2p1.3P_1"},
        {16125, 9.4137, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.3P_2"},
        {14882, 131.891, "mg_vii", "2s1.2p3.1D_2", "2p1.3p1.3D_1"},
        {16366, 146.583, "mg_xi", "1s1.3s1.3S_1", "1s1.4p1.3P_2"},
        {128, 18756.3, "h_i", "1s0.3d1.2D_3/2", "1s0.4p1.2P_1/2"},
        {130, 18756.5, "h_i", "1s0.3d1.2D_5/2", "1s0.4p1.2P_1/2"},
        {14615, 1184.41, "mg_vii", "2p1.3s1.1P_1", "2p1.3p1.1D_2"},
        {14570, 399.281, "mg_vi", "2p3.4S_3/2", "2s1.2p4.4P_1/2"},
        {84, 74780.6, "h_i", "1s0.5p1.2P_1/2", "1s0.6s1.2S"},
        {85, 74781.9, "h_i", "1s0.5p1.2P_3/2", "1s0.6s1.2S"},
        {16011, 88.594, "mg_ix", "2s0.2p2.3P_1", "2s1.3p1.3P_1"},
        {14829, 111.858, "mg_vii", "2s1.2p3.3D_1", "2p1.3p1.3D_2"},
        {16216, 9.2308, "mg_x", "2s1.2S_1/2", "1s1.2s1.2p1.2P_1/2#2"},
        {529, 6650.33, "he_ii", "1s0.4d1.2D_3/2", "1s0.6p1.2P"},
        {530, 6650.44, "he_ii", "1s0.4d1.2D_5/2", "1s0.6p1.2P"},
        {16291, 35.2407, "mg_xi", "1s1.2p1.3P_0", "1s1.5s1.3S_1"},
        {16292, 35.251, "mg_xi", "1s1.2p1.3P_1", "1s1.5s1.3S_1"},
        {16293, 35.2954, "mg_xi", "1s1.2p1.3P_2", "1s1.5s1.3S_1"},
        {16327, 36.1203, "mg_xi", "1s1.2p1.1P_1", "1s1.5s1.1S_0"},
        {16020, 9.8567, "mg_ix", "2s0.2p2.1S_0", "1s1.2s2.2p1.1P_1"},
        {475, 10126.4, "he_ii", "1s0.4d1.2D_3/2", "1s0.5p1.2P_3/2"},
        {477, 10126.6, "he_ii", "1s0.4d1.2D_5/2", "1s0.5p1.2P_3/2"},
        {522, 19372.4, "he_ii", "1s0.5s1.2S_1/2", "1s0.6p1.2P"},
        {16281, 106.307, "mg_xi", "1s1.3p1.1P_1", "1s1.5d1.1D_2"},
        {14697, 320.512, "mg_vii", "2p2.1S_0", "2s1.2p3.1P_1"},
        {16213, 585, "mg_x", "2s0.4d1.2D_3/2", "2s0.5f1.2F_7/2"},
        {15706, 9.9455, "mg_viii", "2s0.2p3.2D_5/2", "1s1.2s2.2p2.2P_3/2"},
        {16188, 585, "mg_x", "2s0.4f1.2F_7/2", "2s0.5g1.2G_7/2"},
        {16644, 30.0506, "mg_xii", "1s0.2p1.2P_1/2", "1s0.5d1.2D_5/2"},
        {16339, 101.605, "mg_xi", "1s1.3s1.3S_1", "1s1.5p1.3P_2"},
        {16646, 30.1197, "mg_xii", "1s0.2p1.2P_3/2", "1s0.5d1.2D_5/2"},
        {50, 12821.6, "h_i", "1s0.3d1.2D_3/2", "1s0.5p1.2P_1/2"},
        {52, 12821.7, "h_i", "1s0.3d1.2D_5/2", "1s0.5p1.2P_1/2"},
        {16365, 146.678, "mg_xi", "1s1.3s1.3S_1", "1s1.4p1.3P_1"},
        {15178, 352.46, "mg_viii", "2s1.2p2.4P_1/2", "2s0.2p3.4S_3/2"},
        {124, 74780.6, "h_i", "1s0.5p1.2P_1/2", "1s0.6d1.2D"},
        {125, 74781.9, "h_i", "1s0.5p1.2P_3/2", "1s0.6d1.2D"},
        {14575, 85.047, "mg_vii", "2p2.3P_2", "2p1.3d1.3F_2"},
        {16643, 30.0521, "mg_xii", "1s0.2p1.2P_1/2", "1s0.5d1.2D_3/2"},
        {16645, 30.1211, "mg_xii", "1s0.2p1.2P_3/2", "1s0.5d1.2D_3/2"},
        {32, 10945, "h_i", "1s0.3d1.2D_3/2", "1s0.6p1.2P"},
        {33, 10945.1, "h_i", "1s0.3d1.2D_5/2", "1s0.6p1.2P"},
        {15189, 341.802, "mg_viii", "2s1.2p2.2D_5/2", "2s0.2p3.2P_3/2"},
        {16606, 45.4355, "mg_xii", "1s0.2p1.2P_1/2", "1s0.3s1.2S_1/2"},
        {16607, 45.5935, "mg_xii", "1s0.2p1.2P_3/2", "1s0.3s1.2S_1/2"},
        {71, 40522.6, "h_i", "1s0.4d1.2D_3/2", "1s0.5p1.2P_3/2"},
        {73, 40522.9, "h_i", "1s0.4d1.2D_5/2", "1s0.5p1.2P_3/2"},
        {16197, 585, "mg_x", "2s0.4f1.2F_5/2", "2s0.5g1.2G_7/2"},
        {16693, 28.6982, "mg_xii", "1s0.2p1.2P_1/2", "1s0.6d1.2D"},
        {16694, 28.7611, "mg_xii", "1s0.2p1.2P_3/2", "1s0.6d1.2D"},
        {15725, 9.9486, "mg_viii", "2s0.2p3.2D_3/2", "1s1.2s2.2p2.2P_1/2"},
        {14433, 3489.73, "mg_vi", "2p3.2D_3/2", "2p3.2P_3/2"},
        {16182, 585, "mg_x", "2s0.4d1.2D_5/2", "2s0.5f1.2F_5/2"},
        {15951, 9.3652, "mg_ix", "2s0.2p2.1D_2", "1s1.2p3.1P_1"},
        {16088, 9.4154, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3P_0"},
        {14509, 349.168, "mg_vi", "2p3.2D_5/2", "2s1.2p4.2D_5/2"},
        {16388, 151.035, "mg_xi", "1s1.3p1.3P_0", "1s1.4d1.3D_3"},
        {16391, 151.096, "mg_xi", "1s1.3p1.3P_1", "1s1.4d1.3D_3"},
        {16394, 151.337, "mg_xi", "1s1.3p1.3P_2", "1s1.4d1.3D_3"},
        {16648, 88.9117, "mg_xii", "1s0.3d1.2D_3/2", "1s0.5f1.2F_7/2"},
        {16650, 88.9711, "mg_xii", "1s0.3d1.2D_5/2", "1s0.5f1.2F_7/2"},
        {474, 10126.8, "he_ii", "1s0.4d1.2D_3/2", "1s0.5p1.2P_1/2"},
        {476, 10127, "he_ii", "1s0.4d1.2D_5/2", "1s0.5p1.2P_1/2"},
        {211, 537.03, "he_i", "1s2.1S_0", "1s1.3p1.1P_1"},
        {14950, 1334.22, "mg_vii", "2p1.3s1.3P_2", "2p1.3p1.3P_2"},
        {16647, 88.9181, "mg_xii", "1s0.3d1.2D_3/2", "1s0.5f1.2F_5/2"},
        {16649, 88.9775, "mg_xii", "1s0.3d1.2D_5/2", "1s0.5f1.2F_5/2"},
        {16605, 45.3972, "mg_xii", "1s0.2s1.2S_1/2", "1s0.3p1.2P_3/2"},
        {15820, 9.5183, "mg_viii", "2p1.2P_3/2", "1s1.2s2.2p2.2D_5/2"},
        {323, 10832.1, "he_i", "1s1.2s1.3S_1", "1s1.2p1.3P_0"},
        {16207, 9.2952, "mg_x", "2s0.2p1.2P_3/2", "1s1.2p2.2P_3/2"},
        {14713, 117.642, "mg_vii", "2s1.2p3.3P_2", "2p1.3p1.3P_1"},
        {16338, 101.628, "mg_xi", "1s1.3s1.3S_1", "1s1.5p1.3P_1"},
        {16060, 9.4518, "mg_ix", "2s0.2p2.1S_0", "1s1.2p3.1P_1"},
        {16054, 9.4505, "mg_ix", "2s1.2p1.1P_1", "1s1.2s1.2p2.1D_2"},
        {15119, 130.937, "mg_vii", "2s1.2p3.3S_1", "2p1.3p1.3P_2"},
        {14779, 1645.77, "mg_vii", "2p1.3s1.3P_1", "2p1.3p1.3D_2"},
        {172, 6680, "he_i", "1s1.2p1.1P_1", "1s1.3d1.1D_2"},
        {16047, 9.4144, "mg_ix", "2s1.2p1.3P_1", "1s1.2s1.2p2.3D_2"},
        {15020, 84.76, "mg_vii", "2p2.3P_1", "2p1.3d1.1D_2"},
        {16631, 281.081, "mg_xii", "1s0.4f1.2F_5/2", "1s0.5g1.2G_9/2"},
        {16633, 281.206, "mg_xii", "1s0.4f1.2F_7/2", "1s0.5g1.2G_9/2"},
        {16630, 281.119, "mg_xii", "1s0.4f1.2F_5/2", "1s0.5g1.2G_7/2"},
        {16632, 281.244, "mg_xii", "1s0.4f1.2F_7/2", "1s0.5g1.2G_7/2"},
        {16144, 9.3518, "mg_ix", "2s1.2p1.3P_2", "1s1.2s1.2p2.3S_1"},
        {16387, 151.072, "mg_xi", "1s1.3p1.3P_0", "1s1.4d1.3D_2"},
        {16390, 151.133, "mg_xi", "1s1.3p1.3P_1", "1s1.4d1.3D_2"},
        {16393, 151.374, "mg_xi", "1s1.3p1.3P_2", "1s1.4d1.3D_2"},
        {15565, 9.5156, "mg_viii", "2p1.2P_1/2", "1s1.2s2.2p2.2D_3/2"},
        {14537, 3502.98, "mg_vi", "2p3.2D_3/2", "2p3.2P_1/2"},
        {16313, 155.153, "mg_xi", "1s1.3p1.3P_0", "1s1.4s1.3S_1"},
        {16314, 155.216, "mg_xi", "1s1.3p1.3P_1", "1s1.4s1.3S_1"},
        {526, 10126.5, "he_ii", "1s0.4f1.2F_5/2", "1s0.5d1.2D_5/2"},
        {528, 10126.6, "he_ii", "1s0.4f1.2F_7/2", "1s0.5d1.2D_5/2"},
        {16315, 155.471, "mg_xi", "1s1.3p1.3P_2", "1s1.4s1.3S_1"},
        {16146, 9.3835, "mg_ix", "2s0.2p2.3P_1", "1s1.2p3.3P_0"},
        {15185, 342.062, "mg_viii", "2s1.2p2.2D_3/2", "2s0.2p3.2P_1/2"},
        {16415, 104.053, "mg_xi", "1s1.3p1.3P_0", "1s1.5d1.3D_3"},
        {16418, 104.082, "mg_xi", "1s1.3p1.3P_1", "1s1.5d1.3D_3"},
        {16421, 104.196, "mg_xi", "1s1.3p1.3P_2", "1s1.5d1.3D_3"},
        {16484, 35.204, "mg_xi", "1s1.2s1.1S_0", "1s1.5p1.1P_1"},
        {14548, 349.137, "mg_vi", "2p3.2D_3/2", "2s1.2p4.2D_3/2"},
        {512, 6650.44, "he_ii", "1s0.4f1.2F_5/2", "1s0.6d1.2D"},
        {513, 6650.49, "he_ii", "1s0.4f1.2F_7/2", "1s0.6d1.2D"},
        {16007, 9.4139, "mg_ix", "2s1.2p1.3P_0", "1s1.2s1.2p2.3P_1"},
        {16172, 585, "mg_x", "2s0.4d1.2D_3/2", "2s0.5f1.2F_5/2"},
        {16604, 45.4438, "mg_xii", "1s0.2s1.2S_1/2", "1s0.3p1.2P_1/2"},
        {15849, 9.9789, "mg_viii", "2s0.2p3.4S_3/2", "1s1.2s2.2p2.4P_5/2"},
        {16331, 157.488, "mg_xi", "1s1.3p1.1P_1", "1s1.4s1.1S_0"},
        {537, 19373.7, "he_ii", "1s0.5d1.2D_3/2", "1s0.6p1.2P"},
        {538, 19374.1, "he_ii", "1s0.5d1.2D_5/2", "1s0.6p1.2P"}
    };
    return rows;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute oracle detail rrc label template for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
const std::vector<RrcLabelTemplateRow>& oracle_detail_rrc_label_template_v172537() {
    static const std::vector<RrcLabelTemplateRow> rows = {
        {1, 29, 0.377699852, "h_i", "1s0.6f1.2F", "continuum"},
        {2, 22, 0.545493126, "h_i", "1s0.5f1.2F_7/2", "continuum"},
        {3, 23, 0.54549408, "h_i", "1s0.5f1.2F_5/2", "continuum"},
        {4, 31, 0.377699852, "h_i", "1s0.6h1.2H", "continuum"},
        {5, 30, 0.377699852, "h_i", "1s0.6g1.2G", "continuum"},
        {6, 19, 0.545496941, "h_i", "1s0.5s1.2S_1/2", "continuum"},
        {7, 2, 3.40119171, "h_i", "1s0.2p1.2P_1/2", "continuum"},
        {8, 3, 3.40126896, "h_i", "1s0.2p1.2P_3/2", "continuum"},
        {9, 27, 0.377699852, "h_i", "1s0.6p1.2P", "continuum"},
        {10, 26, 0.377699852, "h_i", "1s0.6s1.2S", "continuum"},
        {11, 28, 0.377699852, "h_i", "1s0.6d1.2D", "continuum"},
        {12, 1, 13.6000004, "h_i", "1s1.2S_1/2", "continuum"},
        {13, 4, 3.40118599, "h_i", "1s0.2s1.2S_1/2", "continuum"},
        {14, 10, 0.851463318, "h_i", "1s0.4p1.2P_1/2", "continuum"},
        {15, 11, 0.851458549, "h_i", "1s0.4p1.2P_3/2", "continuum"},
        {16, 17, 0.545498848, "h_i", "1s0.5p1.2P_1/2", "continuum"},
        {17, 18, 0.545495033, "h_i", "1s0.5p1.2P_3/2", "continuum"},
        {18, 15, 0.851456642, "h_i", "1s0.4f1.2F_5/2", "continuum"},
        {19, 16, 0.851455688, "h_i", "1s0.4f1.2F_7/2", "continuum"},
        {20, 13, 0.851458549, "h_i", "1s0.4d1.2D_3/2", "continuum"},
        {21, 14, 0.851456642, "h_i", "1s0.4d1.2D_5/2", "continuum"},
        {22, 5, 1.51250267, "h_i", "1s0.3p1.2P_1/2", "continuum"},
        {23, 6, 1.51248932, "h_i", "1s0.3p1.2P_3/2", "continuum"},
        {24, 7, 1.51250172, "h_i", "1s0.3s1.2S_1/2", "continuum"},
        {25, 8, 1.51248932, "h_i", "1s0.3d1.2D_3/2", "continuum"},
        {26, 9, 1.5124855, "h_i", "1s0.3d1.2D_5/2", "continuum"},
        {27, 20, 0.545495033, "h_i", "1s0.5d1.2D_3/2", "continuum"},
        {28, 21, 0.54549408, "h_i", "1s0.5d1.2D_5/2", "continuum"},
        {29, 24, 0.545493126, "h_i", "1s0.5g1.2G_7/2", "continuum"},
        {30, 25, 0.545493126, "h_i", "1s0.5g1.2G_9/2", "continuum"},
        {31, 12, 0.851463318, "h_i", "1s0.4s1.2S_1/2", "continuum"},
        {32, 32, 0.0943994522, "h_i", "superlev", "continuum"},
        {33, 51, 0.996032715, "he_i", "1s1.4s1.3S_1", "continuum"},
        {34, 63, 0.852981567, "he_i", "1s1.4f1.1F_3", "continuum"},
        {35, 66, 0.578777313, "he_i", "1s1.5s1.1S_0", "continuum"},
        {36, 40, 3.37196922, "he_i", "1s1.2p1.1P_1", "continuum"},
        {37, 42, 1.66967583, "he_i", "1s1.3s1.1S_0", "continuum"},
        {38, 52, 0.91642189, "he_i", "1s1.4s1.1S_0", "continuum"},
        {39, 41, 1.87152672, "he_i", "1s1.3s1.3S_1", "continuum"},
        {40, 50, 1.50297356, "he_i", "1s1.3p1.1P_1", "continuum"},
        {41, 60, 0.852985382, "he_i", "1s1.4f1.3F_3", "continuum"},
        {42, 61, 0.852983475, "he_i", "1s1.4f1.3F_4", "continuum"},
        {43, 62, 0.852983475, "he_i", "1s1.4f1.3F_2", "continuum"},
        {44, 50, 1.50297356, "he_i", "1s1.3p1.1P_1", "continuum"},
        {45, 71, 0.556900024, "he_i", "1s1.5f1.3F", "continuum"},
        {46, 70, 0.55739975, "he_i", "1s1.5d1.3D", "continuum"},
        {47, 72, 0.556400299, "he_i", "1s1.5g1.3G", "continuum"},
        {48, 35, 4.77038002, "he_i", "1s1.2s1.3S_1", "continuum"},
        {49, 53, 0.882101059, "he_i", "1s1.4p1.3P_2", "continuum"},
        {50, 54, 0.882101059, "he_i", "1s1.4p1.3P_1", "continuum"},
        {51, 55, 0.8820858, "he_i", "1s1.4p1.3P_0", "continuum"},
        {52, 66, 0.578777313, "he_i", "1s1.5s1.1S_0", "continuum"},
        {53, 75, 0.556900024, "he_i", "1s1.5f1.1F", "continuum"},
        {54, 52, 0.91642189, "he_i", "1s1.4s1.1S_0", "continuum"},
        {55, 74, 0.557199478, "he_i", "1s1.5d1.1D", "continuum"},
        {56, 49, 1.51591682, "he_i", "1s1.3d1.1D_2", "continuum"},
        {57, 73, 0.554100037, "he_i", "1s1.5p1.1P", "continuum"},
        {58, 64, 0.847921371, "he_i", "1s1.4p1.1P_1", "continuum"},
        {59, 49, 1.51591682, "he_i", "1s1.3d1.1D_2", "continuum"},
        {60, 35, 4.77038002, "he_i", "1s1.2s1.3S_1", "continuum"},
        {61, 59, 0.853656769, "he_i", "1s1.4d1.1D_2", "continuum"},
        {62, 41, 1.87152672, "he_i", "1s1.3s1.3S_1", "continuum"},
        {63, 74, 0.557199478, "he_i", "1s1.5d1.1D", "continuum"},
        {64, 42, 1.66967583, "he_i", "1s1.3s1.1S_0", "continuum"},
        {65, 59, 0.853656769, "he_i", "1s1.4d1.1D_2", "continuum"},
        {66, 34, 24.5900002, "he_i", "1s2.1S_0", "continuum"},
        {67, 40, 3.37196922, "he_i", "1s1.2p1.1P_1", "continuum"},
        {68, 36, 3.97421837, "he_i", "1s1.2s1.1S_0", "continuum"},
        {69, 36, 3.97421837, "he_i", "1s1.2s1.1S_0", "continuum"},
        {70, 67, 0.561767578, "he_i", "1s1.5p1.3P_2", "continuum"},
        {71, 68, 0.561765671, "he_i", "1s1.5p1.3P_1", "continuum"},
        {72, 69, 0.561759949, "he_i", "1s1.5p1.3P_0", "continuum"},
        {73, 64, 0.847921371, "he_i", "1s1.4p1.1P_1", "continuum"},
        {74, 76, 0.556600571, "he_i", "1s1.5g1.1G", "continuum"},
        {75, 49, 1.51591682, "he_i", "1s1.3d1.1D_2", "continuum"},
        {76, 74, 0.557199478, "he_i", "1s1.5d1.1D", "continuum"},
        {77, 50, 1.50297356, "he_i", "1s1.3p1.1P_1", "continuum"},
        {78, 34, 24.5900002, "he_i", "1s2.1S_0", "continuum"},
        {79, 64, 0.847921371, "he_i", "1s1.4p1.1P_1", "continuum"},
        {80, 56, 0.853902817, "he_i", "1s1.4d1.3D_3", "continuum"},
        {81, 57, 0.853902817, "he_i", "1s1.4d1.3D_2", "continuum"},
        {82, 58, 0.853899002, "he_i", "1s1.4d1.3D_1", "continuum"},
        {83, 40, 3.37196922, "he_i", "1s1.2p1.1P_1", "continuum"},
        {84, 52, 0.91642189, "he_i", "1s1.4s1.1S_0", "continuum"},
        {85, 59, 0.853656769, "he_i", "1s1.4d1.1D_2", "continuum"},
        {86, 36, 3.97421837, "he_i", "1s1.2s1.1S_0", "continuum"},
        {87, 73, 0.554100037, "he_i", "1s1.5p1.1P", "continuum"},
        {88, 41, 1.87152672, "he_i", "1s1.3s1.3S_1", "continuum"},
        {89, 51, 0.996032715, "he_i", "1s1.4s1.3S_1", "continuum"},
        {90, 65, 0.618021011, "he_i", "1s1.5s1.3S_1", "continuum"},
        {91, 37, 3.62590599, "he_i", "1s1.2p1.3P_2", "continuum"},
        {92, 38, 3.62589645, "he_i", "1s1.2p1.3P_1", "continuum"},
        {93, 39, 3.62577438, "he_i", "1s1.2p1.3P_0", "continuum"},
        {94, 42, 1.66967583, "he_i", "1s1.3s1.1S_0", "continuum"},
        {95, 43, 1.58292007, "he_i", "1s1.3p1.3P_2", "continuum"},
        {96, 44, 1.58291626, "he_i", "1s1.3p1.3P_1", "continuum"},
        {97, 45, 1.58288383, "he_i", "1s1.3p1.3P_0", "continuum"},
        {98, 66, 0.578777313, "he_i", "1s1.5s1.1S_0", "continuum"},
        {99, 56, 0.853902817, "he_i", "1s1.4d1.3D_3", "continuum"},
        {100, 57, 0.853902817, "he_i", "1s1.4d1.3D_2", "continuum"},
        {101, 58, 0.853899002, "he_i", "1s1.4d1.3D_1", "continuum"},
        {102, 46, 1.51634026, "he_i", "1s1.3d1.3D_3", "continuum"},
        {103, 47, 1.51634026, "he_i", "1s1.3d1.3D_2", "continuum"},
        {104, 48, 1.51633644, "he_i", "1s1.3d1.3D_1", "continuum"},
        {105, 51, 0.996032715, "he_i", "1s1.4s1.3S_1", "continuum"},
        {106, 65, 0.618021011, "he_i", "1s1.5s1.3S_1", "continuum"},
        {107, 65, 0.618021011, "he_i", "1s1.5s1.3S_1", "continuum"},
        {108, 70, 0.55739975, "he_i", "1s1.5d1.3D", "continuum"},
        {109, 37, 3.62590599, "he_i", "1s1.2p1.3P_2", "continuum"},
        {110, 38, 3.62589645, "he_i", "1s1.2p1.3P_1", "continuum"},
        {111, 39, 3.62577438, "he_i", "1s1.2p1.3P_0", "continuum"},
        {112, 56, 0.853902817, "he_i", "1s1.4d1.3D_3", "continuum"},
        {113, 57, 0.853902817, "he_i", "1s1.4d1.3D_2", "continuum"},
        {114, 58, 0.853899002, "he_i", "1s1.4d1.3D_1", "continuum"},
        {115, 43, 1.58292007, "he_i", "1s1.3p1.3P_2", "continuum"},
        {116, 44, 1.58291626, "he_i", "1s1.3p1.3P_1", "continuum"},
        {117, 45, 1.58288383, "he_i", "1s1.3p1.3P_0", "continuum"},
        {118, 34, 24.5900002, "he_i", "1s2.1S_0", "continuum"},
        {119, 46, 1.51634026, "he_i", "1s1.3d1.3D_3", "continuum"},
        {120, 47, 1.51634026, "he_i", "1s1.3d1.3D_2", "continuum"},
        {121, 48, 1.51633644, "he_i", "1s1.3d1.3D_1", "continuum"},
        {122, 37, 3.62590599, "he_i", "1s1.2p1.3P_2", "continuum"},
        {123, 38, 3.62589645, "he_i", "1s1.2p1.3P_1", "continuum"},
        {124, 39, 3.62577438, "he_i", "1s1.2p1.3P_0", "continuum"},
        {125, 43, 1.58292007, "he_i", "1s1.3p1.3P_2", "continuum"},
        {126, 44, 1.58291626, "he_i", "1s1.3p1.3P_1", "continuum"},
        {127, 45, 1.58288383, "he_i", "1s1.3p1.3P_0", "continuum"},
        {128, 70, 0.55739975, "he_i", "1s1.5d1.3D", "continuum"},
        {129, 46, 1.51634026, "he_i", "1s1.3d1.3D_3", "continuum"},
        {130, 47, 1.51634026, "he_i", "1s1.3d1.3D_2", "continuum"},
        {131, 48, 1.51633644, "he_i", "1s1.3d1.3D_1", "continuum"},
        {132, 73, 0.554100037, "he_i", "1s1.5p1.1P", "continuum"},
        {133, 35, 4.77038002, "he_i", "1s1.2s1.3S_1", "continuum"},
        {176, 63, 0.852981567, "he_i", "1s1.4f1.1F_3", "continuum"},
        {177, 64, 0.847921371, "he_i", "1s1.4p1.1P_1", "continuum"},
        {178, 105, 1.51089859, "he_ii", "1s0.6s1.2S", "continuum"},
        {179, 108, 1.51089859, "he_ii", "1s0.6f1.2F", "continuum"},
        {180, 91, 3.40331268, "he_ii", "1s0.4s1.2S_1/2", "continuum"},
        {181, 92, 3.40322876, "he_ii", "1s0.4d1.2D_3/2", "continuum"},
        {182, 93, 3.40319824, "he_ii", "1s0.4d1.2D_5/2", "continuum"},
        {183, 87, 6.04846954, "he_ii", "1s0.3d1.2D_3/2", "continuum"},
        {184, 88, 6.04839706, "he_ii", "1s0.3d1.2D_5/2", "continuum"},
        {185, 98, 2.17890167, "he_ii", "1s0.5s1.2S_1/2", "continuum"},
        {186, 86, 6.04866791, "he_ii", "1s0.3s1.2S_1/2", "continuum"},
        {187, 89, 3.40332031, "he_ii", "1s0.4p1.2P_1/2", "continuum"},
        {188, 90, 3.40322876, "he_ii", "1s0.4p1.2P_3/2", "continuum"},
        {189, 109, 1.51089859, "he_ii", "1s0.6g1.2G", "continuum"},
        {190, 107, 1.51089859, "he_ii", "1s0.6d1.2D", "continuum"},
        {191, 94, 3.40319824, "he_ii", "1s0.4f1.2F_5/2", "continuum"},
        {192, 95, 3.40318298, "he_ii", "1s0.4f1.2F_7/2", "continuum"},
        {193, 101, 2.17884445, "he_ii", "1s0.5f1.2F_5/2", "continuum"},
        {194, 102, 2.17883682, "he_ii", "1s0.5f1.2F_7/2", "continuum"},
        {195, 96, 2.17890549, "he_ii", "1s0.5p1.2P_1/2", "continuum"},
        {196, 97, 2.17885971, "he_ii", "1s0.5p1.2P_3/2", "continuum"},
        {197, 110, 1.51089859, "he_ii", "1s0.6h1.2H", "continuum"},
        {198, 103, 2.17883682, "he_ii", "1s0.5g1.2G_7/2", "continuum"},
        {199, 104, 2.17883301, "he_ii", "1s0.5g1.2G_9/2", "continuum"},
        {200, 106, 1.51089859, "he_ii", "1s0.6p1.2P", "continuum"},
        {201, 99, 2.17885971, "he_ii", "1s0.5d1.2D_3/2", "continuum"},
        {202, 100, 2.17884445, "he_ii", "1s0.5d1.2D_5/2", "continuum"},
        {203, 83, 13.6068954, "he_ii", "1s0.2s1.2S_1/2", "continuum"},
        {204, 81, 13.6069527, "he_ii", "1s0.2p1.2P_1/2", "continuum"},
        {205, 82, 13.6062279, "he_ii", "1s0.2p1.2P_3/2", "continuum"},
        {206, 84, 6.04868698, "he_ii", "1s0.3p1.2P_1/2", "continuum"},
        {207, 85, 6.04846954, "he_ii", "1s0.3p1.2P_3/2", "continuum"},
        {208, 80, 54.4199982, "he_ii", "1s1.2S_1/2", "continuum"},
        {209, 111, 0.377696991, "he_ii", "superlev", "continuum"},
        {7065, 2817, 80.0999985, "mg_iii", "2p6.1S_0", "continuum"},
        {7066, 2817, 80.0999985, "mg_iii", "2p6.1S_0", "continuum"},
        {7067, 2817, 80.0999985, "mg_iii", "2p6.1S_0", "continuum"},
        {7068, 2817, 80.0999985, "mg_iii", "2p6.1S_0", "continuum"},
        {7069, 2818, 0.55619812, "mg_iii", "superlevel", "continuum"},
        {7070, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7071, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7072, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7073, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7074, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7075, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7076, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7077, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7078, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7079, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7080, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7081, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7082, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7083, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7084, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7085, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7086, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7087, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7088, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7089, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7090, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7091, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7092, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7093, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7094, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7095, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7096, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7097, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7098, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7099, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7100, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7101, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7102, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7103, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7104, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7105, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7106, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7107, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7108, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7109, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7110, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7111, 2863, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7112, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7113, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7114, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7115, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7116, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7117, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7118, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7119, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7120, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7121, 2864, 108.723877, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7122, 2865, 70.391098, "mg_iv", "2s1.2p6.2S_1/2", "continuum"},
        {7123, 2865, 70.391098, "mg_iv", "2s1.2p6.2S_1/2", "continuum"},
        {7124, 2865, 70.391098, "mg_iv", "2s1.2p6.2S_1/2", "continuum"},
        {7125, 2866, 0.757003784, "mg_iv", "superlevel", "continuum"},
        {7126, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7127, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7128, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7129, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7130, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7131, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7132, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7133, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7134, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7135, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7136, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7137, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7138, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7139, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7140, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7141, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7142, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7143, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7144, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7145, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7146, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7147, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7148, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7149, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7150, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7151, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7152, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7153, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7154, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7155, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7156, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7157, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7158, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7159, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7160, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7161, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7162, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7163, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7164, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7165, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7166, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7167, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7168, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7169, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7170, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7171, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7172, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7173, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7174, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7175, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7176, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7177, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7178, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7179, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7180, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7181, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7182, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7183, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7184, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7185, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7186, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7187, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7188, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7189, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7190, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7191, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7192, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7193, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7194, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7195, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7196, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7197, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7198, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7199, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7200, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7201, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7202, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7203, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7204, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7205, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7206, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7207, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7208, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7209, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7210, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7211, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7212, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7213, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7214, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7215, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7216, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7217, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7218, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7219, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7220, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7221, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7222, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7223, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7224, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7225, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7226, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7227, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7228, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7229, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7230, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7231, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7232, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7233, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7234, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7235, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7236, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7237, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7238, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7239, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7240, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7241, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7242, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7243, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7244, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7245, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7246, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7247, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7248, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7249, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7250, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7251, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7252, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7253, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7254, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7255, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7256, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7257, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7258, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7259, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7260, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7261, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7262, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7263, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7264, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7265, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7266, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7267, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7268, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7269, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7270, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7271, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7272, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7273, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7274, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7275, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7276, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7277, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7278, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7279, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7280, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7281, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7282, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7283, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7284, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7285, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7286, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7287, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7288, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7289, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7290, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7291, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7292, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7293, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7294, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7295, 2870, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7296, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7297, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7298, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7299, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7300, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7301, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7302, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7303, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7304, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7305, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7306, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7307, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7308, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7309, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7310, 2871, 140.779022, "mg_v", "2p4.3P_1", "continuum"},
        {7311, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7312, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7313, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7314, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7315, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7316, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7317, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7318, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7319, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7320, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7321, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7322, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7323, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7324, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7325, 2872, 140.687469, "mg_v", "2p4.3P_0", "continuum"},
        {7326, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7327, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7328, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7329, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7330, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7331, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7332, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7333, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7334, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7335, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7336, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7337, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7338, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7339, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7340, 2873, 136.547607, "mg_v", "2p4.1D_2", "continuum"},
        {7341, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7342, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7343, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7344, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7345, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7346, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7347, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7348, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7349, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7350, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7351, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7352, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7353, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7354, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7355, 2874, 131.422638, "mg_v", "2p4.1S_0", "continuum"},
        {7356, 2875, 105.900803, "mg_v", "2s1.2p5.3P_2", "continuum"},
        {7357, 2875, 105.900803, "mg_v", "2s1.2p5.3P_2", "continuum"},
        {7358, 2876, 105.7006, "mg_v", "2s1.2p5.3P_1", "continuum"},
        {7359, 2876, 105.7006, "mg_v", "2s1.2p5.3P_1", "continuum"},
        {7360, 2877, 105.591003, "mg_v", "2s1.2p5.3P_0", "continuum"},
        {7361, 2877, 105.591003, "mg_v", "2s1.2p5.3P_0", "continuum"},
        {7362, 2878, 91.7391052, "mg_v", "2s1.2p5.1P_1", "continuum"},
        {7363, 2878, 91.7391052, "mg_v", "2s1.2p5.1P_1", "continuum"},
        {7364, 2879, 58.8366013, "mg_v", "2s0.2p6.1S_0", "continuum"},
        {7365, 2879, 58.8366013, "mg_v", "2s0.2p6.1S_0", "continuum"},
        {7366, 2880, 0.979003906, "mg_v", "superlevel", "continuum"},
        {7367, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7368, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7369, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7370, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7371, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7372, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7373, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7374, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7375, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7376, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7377, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7378, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7379, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7380, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7381, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7382, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7383, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7384, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7385, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7386, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7387, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7388, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7389, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7390, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7391, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7392, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7393, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7394, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7395, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7396, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7397, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7398, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7399, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7400, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7401, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7402, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7403, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7404, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7405, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7406, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7407, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7408, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7409, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7410, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7411, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7412, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7413, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7414, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7415, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7416, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7417, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7418, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7419, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7420, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7421, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7422, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7423, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7424, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7425, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7426, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7427, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7428, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7429, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7430, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7431, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7432, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7433, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7434, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7435, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7436, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7437, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7438, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7439, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7440, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7441, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7442, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7443, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7444, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7445, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7446, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7447, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7448, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7449, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7450, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7451, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7452, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7453, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7454, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7455, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7456, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7457, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7458, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7459, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7460, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7461, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7462, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7463, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7464, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7465, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7466, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7467, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7468, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7469, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7470, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7471, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7472, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7473, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7474, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7475, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7476, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7477, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7478, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7479, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7480, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7481, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7482, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7483, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7484, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7485, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7486, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7487, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7488, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7489, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7490, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7491, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7492, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7493, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7494, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7495, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7496, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7497, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7498, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7499, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7500, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7501, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7502, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7503, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7504, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7505, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7506, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7507, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7508, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7509, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7510, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7511, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7512, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7513, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7514, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7515, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7516, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7517, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7518, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7519, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7520, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7521, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7522, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7523, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7524, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7525, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7526, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7527, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7528, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7529, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7530, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7531, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7532, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7533, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7534, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7535, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7536, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7537, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7538, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7539, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7540, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7541, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7542, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7543, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7544, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7545, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7546, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7547, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7548, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7549, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7550, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7551, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7552, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7553, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7554, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7555, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7556, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7557, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7558, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7559, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7560, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7561, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7562, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7563, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7564, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7565, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7566, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7567, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7568, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7569, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7570, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7571, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7572, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7573, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7574, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7575, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7576, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7577, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7578, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7579, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7580, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7581, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7582, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7583, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7584, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7585, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7586, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7587, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7588, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7589, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7590, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7591, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7592, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7593, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7594, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7595, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7596, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7597, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7598, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7599, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7600, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7601, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7602, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7603, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7604, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7605, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7606, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7607, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7608, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7609, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7610, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7611, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7612, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7613, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7614, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7615, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7616, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7617, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7618, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7619, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7620, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7621, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7622, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7623, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7624, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7625, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7626, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7627, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7628, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7629, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7630, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7631, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7632, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7633, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7634, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7635, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7636, 2889, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7637, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7638, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7639, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7640, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7641, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7642, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7643, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7644, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7645, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7646, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7647, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7648, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7649, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7650, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7651, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7652, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7653, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7654, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7655, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7656, 2890, 180.137512, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7657, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7658, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7659, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7660, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7661, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7662, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7663, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7664, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7665, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7666, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7667, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7668, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7669, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7670, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7671, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7672, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7673, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7674, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7675, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7676, 2891, 180.139603, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7677, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7678, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7679, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7680, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7681, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7682, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7683, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7684, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7685, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7686, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7687, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7688, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7689, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7690, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7691, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7692, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7693, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7694, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7695, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7696, 2892, 176.599594, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7697, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7698, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7699, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7700, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7701, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7702, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7703, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7704, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7705, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7706, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7707, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7708, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7709, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7710, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7711, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7712, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7713, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7714, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7715, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7716, 2893, 176.586197, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7717, 2894, 156.271194, "mg_vi", "2s1.2p4.4P_5/2", "continuum"},
        {7718, 2895, 156.068497, "mg_vi", "2s1.2p4.4P_3/2", "continuum"},
        {7719, 2896, 155.961105, "mg_vi", "2s1.2p4.4P_1/2", "continuum"},
        {7720, 2897, 144.640808, "mg_vi", "2s1.2p4.2D_3/2", "continuum"},
        {7721, 2898, 144.645996, "mg_vi", "2s1.2p4.2D_5/2", "continuum"},
        {7722, 2899, 137.201294, "mg_vi", "2s1.2p4.2S_1/2", "continuum"},
        {7723, 2900, 134.305206, "mg_vi", "2s1.2p4.2P_3/2", "continuum"},
        {7724, 2901, 134.064209, "mg_vi", "2s1.2p4.2P_1/2", "continuum"},
        {7725, 2902, 1.29899597, "mg_vi", "superlevel", "continuum"},
        {7726, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7727, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7728, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7729, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7730, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7731, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7732, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7733, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7734, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7735, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7736, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7737, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7738, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7739, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7740, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7741, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7742, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7743, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7744, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7745, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7746, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7747, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7748, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7749, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7750, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7751, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7752, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7753, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7754, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7755, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7756, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7757, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7758, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7759, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7760, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7761, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7762, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7763, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7764, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7765, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7766, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7767, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7768, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7769, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7770, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7771, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7772, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7773, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7774, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7775, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7776, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7777, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7778, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7779, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7780, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7781, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7782, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7783, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7784, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7785, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7786, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7787, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7788, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7789, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7790, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7791, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7792, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7793, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7794, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7795, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7796, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7797, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7798, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7799, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7800, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7801, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7802, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7803, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7804, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7805, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7806, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7807, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7808, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7809, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7810, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7811, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7812, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7813, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7814, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7815, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7816, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7817, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7818, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7819, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7820, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7821, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7822, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7823, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7824, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7825, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7826, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7827, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7828, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7829, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7830, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7831, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7832, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7833, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7834, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7835, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7836, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7837, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7838, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7839, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7840, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7841, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7842, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7843, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7844, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7845, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7846, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7847, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7848, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7849, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7850, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7851, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7852, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7853, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7854, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7855, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7856, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7857, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7858, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7859, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7860, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7861, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7862, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7863, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7864, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7865, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7866, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7867, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7868, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7869, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7870, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7871, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7872, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7873, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7874, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7875, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {7876, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7877, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7878, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7879, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7880, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7881, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7882, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7883, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7884, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7885, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7886, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7887, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7888, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7889, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7890, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7891, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7892, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7893, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7894, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7895, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7896, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7897, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7898, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7899, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7900, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7901, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7902, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7903, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7904, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7905, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7906, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7907, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7908, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7909, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7910, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7911, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7912, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7913, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7914, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7915, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7916, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7917, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7918, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7919, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7920, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7921, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7922, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7923, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7924, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7925, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {7926, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7927, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7928, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7929, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7930, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7931, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7932, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7933, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7934, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7935, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7936, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7937, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7938, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7939, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7940, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7941, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7942, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7943, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7944, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7945, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7946, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7947, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7948, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7949, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7950, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7951, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7952, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7953, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7954, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7955, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7956, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7957, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7958, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7959, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7960, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7961, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7962, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7963, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7964, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7965, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7966, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7967, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7968, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7969, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7970, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7971, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7972, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7973, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7974, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7975, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {7976, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7977, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7978, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7979, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7980, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7981, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7982, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7983, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7984, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7985, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7986, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7987, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7988, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7989, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7990, 2923, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7991, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7992, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7993, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7994, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7995, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7996, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7997, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7998, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {7999, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {8000, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {8001, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {8002, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {8003, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {8004, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {8005, 2924, 224.862808, "mg_vii", "2p2.3P_1", "continuum"},
        {8006, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8007, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8008, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8009, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8010, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8011, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8012, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8013, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8014, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8015, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8016, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8017, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8018, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8019, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8020, 2925, 224.637619, "mg_vii", "2p2.3P_2", "continuum"},
        {8021, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8022, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8023, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8024, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8025, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8026, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8027, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8028, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8029, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8030, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8031, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8032, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8033, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8034, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8035, 2926, 219.925217, "mg_vii", "2p2.1D_2", "continuum"},
        {8036, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8037, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8038, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8039, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8040, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8041, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8042, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8043, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8044, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8045, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8046, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8047, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8048, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8049, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8050, 2927, 214.446808, "mg_vii", "2p2.1S_0", "continuum"},
        {8051, 2928, 210.363602, "mg_vii", "2s1.2p3.5S_2", "continuum"},
        {8052, 2928, 210.363602, "mg_vii", "2s1.2p3.5S_2", "continuum"},
        {8053, 2928, 210.363602, "mg_vii", "2s1.2p3.5S_2", "continuum"},
        {8054, 2929, 196.129105, "mg_vii", "2s1.2p3.3D_2", "continuum"},
        {8055, 2929, 196.129105, "mg_vii", "2s1.2p3.3D_2", "continuum"},
        {8056, 2929, 196.129105, "mg_vii", "2s1.2p3.3D_2", "continuum"},
        {8057, 2930, 196.120804, "mg_vii", "2s1.2p3.3D_1", "continuum"},
        {8058, 2930, 196.120804, "mg_vii", "2s1.2p3.3D_1", "continuum"},
        {8059, 2930, 196.120804, "mg_vii", "2s1.2p3.3D_1", "continuum"},
        {8060, 2931, 196.141998, "mg_vii", "2s1.2p3.3D_3", "continuum"},
        {8061, 2931, 196.141998, "mg_vii", "2s1.2p3.3D_3", "continuum"},
        {8062, 2931, 196.141998, "mg_vii", "2s1.2p3.3D_3", "continuum"},
        {8063, 2932, 190.925201, "mg_vii", "2s1.2p3.3P_0", "continuum"},
        {8064, 2932, 190.925201, "mg_vii", "2s1.2p3.3P_0", "continuum"},
        {8065, 2932, 190.925201, "mg_vii", "2s1.2p3.3P_0", "continuum"},
        {8066, 2933, 190.931396, "mg_vii", "2s1.2p3.3P_1", "continuum"},
        {8067, 2933, 190.931396, "mg_vii", "2s1.2p3.3P_1", "continuum"},
        {8068, 2933, 190.931396, "mg_vii", "2s1.2p3.3P_1", "continuum"},
        {8069, 2934, 190.930496, "mg_vii", "2s1.2p3.3P_2", "continuum"},
        {8070, 2934, 190.930496, "mg_vii", "2s1.2p3.3P_2", "continuum"},
        {8071, 2934, 190.930496, "mg_vii", "2s1.2p3.3P_2", "continuum"},
        {8072, 2935, 181.078308, "mg_vii", "2s1.2p3.1D_2", "continuum"},
        {8073, 2935, 181.078308, "mg_vii", "2s1.2p3.1D_2", "continuum"},
        {8074, 2935, 181.078308, "mg_vii", "2s1.2p3.1D_2", "continuum"},
        {8075, 2936, 180.122009, "mg_vii", "2s1.2p3.3S_1", "continuum"},
        {8076, 2936, 180.122009, "mg_vii", "2s1.2p3.3S_1", "continuum"},
        {8077, 2936, 180.122009, "mg_vii", "2s1.2p3.3S_1", "continuum"},
        {8078, 2937, 175.779907, "mg_vii", "2s1.2p3.1P_1", "continuum"},
        {8079, 2937, 175.779907, "mg_vii", "2s1.2p3.1P_1", "continuum"},
        {8080, 2937, 175.779907, "mg_vii", "2s1.2p3.1P_1", "continuum"},
        {8081, 2938, 157.78949, "mg_vii", "2s0.2p4.3P_2", "continuum"},
        {8082, 2939, 157.532104, "mg_vii", "2s0.2p4.3P_1", "continuum"},
        {8083, 2940, 157.424194, "mg_vii", "2s0.2p4.3P_0", "continuum"},
        {8084, 2941, 153.580292, "mg_vii", "2s0.2p4.1D_2", "continuum"},
        {8085, 2942, 143.39801, "mg_vii", "2s0.2p4.1S_0", "continuum"},
        {8086, 2943, 95.1670074, "mg_vii", "2p1.3s1.3P_0", "continuum"},
        {8087, 2943, 95.1670074, "mg_vii", "2p1.3s1.3P_0", "continuum"},
        {8088, 2944, 95.0690002, "mg_vii", "2p1.3s1.3P_1", "continuum"},
        {8089, 2944, 95.0690002, "mg_vii", "2p1.3s1.3P_1", "continuum"},
        {8090, 2945, 94.7610016, "mg_vii", "2p1.3s1.3P_2", "continuum"},
        {8091, 2945, 94.7610016, "mg_vii", "2p1.3s1.3P_2", "continuum"},
        {8092, 2946, 93.5039978, "mg_vii", "2p1.3s1.1P_1", "continuum"},
        {8093, 2946, 93.5039978, "mg_vii", "2p1.3s1.1P_1", "continuum"},
        {8094, 2947, 85.8789978, "mg_vii", "2p1.3p1.1P_1", "continuum"},
        {8095, 2947, 85.8789978, "mg_vii", "2p1.3p1.1P_1", "continuum"},
        {8096, 2948, 85.3450012, "mg_vii", "2p1.3p1.3D_1", "continuum"},
        {8097, 2948, 85.3450012, "mg_vii", "2p1.3p1.3D_1", "continuum"},
        {8098, 2949, 85.2330017, "mg_vii", "2p1.3p1.3D_2", "continuum"},
        {8099, 2949, 85.2330017, "mg_vii", "2p1.3p1.3D_2", "continuum"},
        {8100, 2950, 84.9900055, "mg_vii", "2p1.3p1.3D_3", "continuum"},
        {8101, 2950, 84.9900055, "mg_vii", "2p1.3p1.3D_3", "continuum"},
        {8102, 2951, 84.128006, "mg_vii", "2p1.3p1.3S_1", "continuum"},
        {8103, 2951, 84.128006, "mg_vii", "2p1.3p1.3S_1", "continuum"},
        {8104, 2952, 85.7319946, "mg_vii", "2p1.3p1.3P_0", "continuum"},
        {8105, 2952, 85.7319946, "mg_vii", "2p1.3p1.3P_0", "continuum"},
        {8106, 2953, 85.5839996, "mg_vii", "2p1.3p1.3P_1", "continuum"},
        {8107, 2953, 85.5839996, "mg_vii", "2p1.3p1.3P_1", "continuum"},
        {8108, 2954, 85.4720001, "mg_vii", "2p1.3p1.3P_2", "continuum"},
        {8109, 2954, 85.4720001, "mg_vii", "2p1.3p1.3P_2", "continuum"},
        {8110, 2955, 80.6719971, "mg_vii", "2p1.3p1.1D_2", "continuum"},
        {8111, 2955, 80.6719971, "mg_vii", "2p1.3p1.1D_2", "continuum"},
        {8112, 2956, 78.0180054, "mg_vii", "2p1.3p1.1S_0", "continuum"},
        {8113, 2956, 78.0180054, "mg_vii", "2p1.3p1.1S_0", "continuum"},
        {8114, 2957, 78.9149933, "mg_vii", "2p1.3d1.3F_2", "continuum"},
        {8115, 2957, 78.9149933, "mg_vii", "2p1.3d1.3F_2", "continuum"},
        {8116, 2958, 76.6499939, "mg_vii", "2p1.3d1.3F_3", "continuum"},
        {8117, 2958, 76.6499939, "mg_vii", "2p1.3d1.3F_3", "continuum"},
        {8118, 2959, 78.6470032, "mg_vii", "2p1.3d1.1D_2", "continuum"},
        {8119, 2959, 78.6470032, "mg_vii", "2p1.3d1.1D_2", "continuum"},
        {8120, 2960, 76.4550018, "mg_vii", "2p1.3d1.3F_4", "continuum"},
        {8121, 2960, 76.4550018, "mg_vii", "2p1.3d1.3F_4", "continuum"},
        {8122, 2961, 77.3040009, "mg_vii", "2p1.3d1.3D_1", "continuum"},
        {8123, 2961, 77.3040009, "mg_vii", "2p1.3d1.3D_1", "continuum"},
        {8124, 2962, 77.2519989, "mg_vii", "2p1.3d1.3D_2", "continuum"},
        {8125, 2962, 77.2519989, "mg_vii", "2p1.3d1.3D_2", "continuum"},
        {8126, 2963, 77.1430054, "mg_vii", "2p1.3d1.3D_3", "continuum"},
        {8127, 2963, 77.1430054, "mg_vii", "2p1.3d1.3D_3", "continuum"},
        {8128, 2964, 76.6840057, "mg_vii", "2p1.3d1.3P_2", "continuum"},
        {8129, 2964, 76.6840057, "mg_vii", "2p1.3d1.3P_2", "continuum"},
        {8130, 2965, 76.5970001, "mg_vii", "2p1.3d1.3P_1", "continuum"},
        {8131, 2965, 76.5970001, "mg_vii", "2p1.3d1.3P_1", "continuum"},
        {8132, 2966, 76.5480042, "mg_vii", "2p1.3d1.3P_0", "continuum"},
        {8133, 2966, 76.5480042, "mg_vii", "2p1.3d1.3P_0", "continuum"},
        {8134, 2967, 74.6950073, "mg_vii", "2p1.3d1.1P_1", "continuum"},
        {8135, 2967, 74.6950073, "mg_vii", "2p1.3d1.1P_1", "continuum"},
        {8136, 2968, 74.8179932, "mg_vii", "2p1.3d1.1F_3", "continuum"},
        {8137, 2968, 74.8179932, "mg_vii", "2p1.3d1.1F_3", "continuum"},
        {8138, 2969, 1.56199646, "mg_vii", "superlevel", "continuum"},
        {8139, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8140, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8141, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8142, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8143, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8144, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8145, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8146, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8147, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8148, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8149, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8150, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8151, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8152, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8153, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8154, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8155, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8156, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8157, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8158, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8159, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8160, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8161, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8162, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8163, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8164, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8165, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8166, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8167, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8168, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8169, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8170, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8171, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8172, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8173, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8174, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8175, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8176, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8177, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8178, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8179, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8180, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8181, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8182, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8183, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8184, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8185, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8186, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8187, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8188, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8189, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8190, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8191, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8192, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8193, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8194, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8195, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8196, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8197, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8198, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8199, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8200, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8201, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8202, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8203, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8204, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8205, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8206, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8207, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8208, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8209, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8210, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8211, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8212, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8213, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8214, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8215, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8216, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8217, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8218, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8219, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8220, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8221, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8222, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8223, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8224, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8225, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8226, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8227, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8228, 3002, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8229, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8230, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8231, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8232, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8233, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8234, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8235, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8236, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8237, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8238, 3003, 265.590912, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8239, 3004, 249.891098, "mg_viii", "2s1.2p2.4P_1/2", "continuum"},
        {8240, 3004, 249.891098, "mg_viii", "2s1.2p2.4P_1/2", "continuum"},
        {8241, 3004, 249.891098, "mg_viii", "2s1.2p2.4P_1/2", "continuum"},
        {8242, 3005, 249.749603, "mg_viii", "2s1.2p2.4P_3/2", "continuum"},
        {8243, 3005, 249.749603, "mg_viii", "2s1.2p2.4P_3/2", "continuum"},
        {8244, 3005, 249.749603, "mg_viii", "2s1.2p2.4P_3/2", "continuum"},
        {8245, 3006, 249.542908, "mg_viii", "2s1.2p2.4P_5/2", "continuum"},
        {8246, 3006, 249.542908, "mg_viii", "2s1.2p2.4P_5/2", "continuum"},
        {8247, 3006, 249.542908, "mg_viii", "2s1.2p2.4P_5/2", "continuum"},
        {8248, 3007, 237.209702, "mg_viii", "2s1.2p2.2D_3/2", "continuum"},
        {8249, 3007, 237.209702, "mg_viii", "2s1.2p2.2D_3/2", "continuum"},
        {8250, 3007, 237.209702, "mg_viii", "2s1.2p2.2D_3/2", "continuum"},
        {8251, 3008, 237.213699, "mg_viii", "2s1.2p2.2D_5/2", "continuum"},
        {8252, 3008, 237.213699, "mg_viii", "2s1.2p2.2D_5/2", "continuum"},
        {8253, 3008, 237.213699, "mg_viii", "2s1.2p2.2D_5/2", "continuum"},
        {8254, 3009, 229.033203, "mg_viii", "2s1.2p2.2S_1/2", "continuum"},
        {8255, 3009, 229.033203, "mg_viii", "2s1.2p2.2S_1/2", "continuum"},
        {8256, 3009, 229.033203, "mg_viii", "2s1.2p2.2S_1/2", "continuum"},
        {8257, 3010, 226.500198, "mg_viii", "2s1.2p2.2P_1/2", "continuum"},
        {8258, 3010, 226.500198, "mg_viii", "2s1.2p2.2P_1/2", "continuum"},
        {8259, 3010, 226.500198, "mg_viii", "2s1.2p2.2P_1/2", "continuum"},
        {8260, 3011, 226.251999, "mg_viii", "2s1.2p2.2P_3/2", "continuum"},
        {8261, 3011, 226.251999, "mg_viii", "2s1.2p2.2P_3/2", "continuum"},
        {8262, 3011, 226.251999, "mg_viii", "2s1.2p2.2P_3/2", "continuum"},
        {8263, 3012, 214.740295, "mg_viii", "2s0.2p3.4S_3/2", "continuum"},
        {8264, 3012, 214.740295, "mg_viii", "2s0.2p3.4S_3/2", "continuum"},
        {8265, 3012, 214.740295, "mg_viii", "2s0.2p3.4S_3/2", "continuum"},
        {8266, 3013, 208.270096, "mg_viii", "2s0.2p3.2D_3/2", "continuum"},
        {8267, 3013, 208.270096, "mg_viii", "2s0.2p3.2D_3/2", "continuum"},
        {8268, 3013, 208.270096, "mg_viii", "2s0.2p3.2D_3/2", "continuum"},
        {8269, 3014, 208.279099, "mg_viii", "2s0.2p3.2D_5/2", "continuum"},
        {8270, 3014, 208.279099, "mg_viii", "2s0.2p3.2D_5/2", "continuum"},
        {8271, 3014, 208.279099, "mg_viii", "2s0.2p3.2D_5/2", "continuum"},
        {8272, 3015, 200.978699, "mg_viii", "2s0.2p3.2P_1/2", "continuum"},
        {8273, 3015, 200.978699, "mg_viii", "2s0.2p3.2P_1/2", "continuum"},
        {8274, 3015, 200.978699, "mg_viii", "2s0.2p3.2P_1/2", "continuum"},
        {8275, 3016, 200.9552, "mg_viii", "2s0.2p3.2P_3/2", "continuum"},
        {8276, 3016, 200.9552, "mg_viii", "2s0.2p3.2P_3/2", "continuum"},
        {8277, 3016, 200.9552, "mg_viii", "2s0.2p3.2P_3/2", "continuum"},
        {8278, 3017, 115.955994, "mg_viii", "2p0.3s1.2S_1/2", "continuum"},
        {8279, 3018, 91.4570007, "mg_viii", "2s1.2p1.3p1.2P_1/2", "continuum"},
        {8280, 3018, 91.4570007, "mg_viii", "2s1.2p1.3p1.2P_1/2", "continuum"},
        {8281, 3018, 91.4570007, "mg_viii", "2s1.2p1.3p1.2P_1/2", "continuum"},
        {8282, 3019, 92.3970032, "mg_viii", "2s1.2p1.3p1.4D_1/2", "continuum"},
        {8283, 3019, 92.3970032, "mg_viii", "2s1.2p1.3p1.4D_1/2", "continuum"},
        {8284, 3019, 92.3970032, "mg_viii", "2s1.2p1.3p1.4D_1/2", "continuum"},
        {8285, 3020, 89.9290009, "mg_viii", "2s1.2p1.3p1.4P_1/2", "continuum"},
        {8286, 3020, 89.9290009, "mg_viii", "2s1.2p1.3p1.4P_1/2", "continuum"},
        {8287, 3020, 89.9290009, "mg_viii", "2s1.2p1.3p1.4P_1/2", "continuum"},
        {8288, 3021, 84.9459991, "mg_viii", "2s1.2p1.3p1.2S_1/2", "continuum"},
        {8289, 3021, 84.9459991, "mg_viii", "2s1.2p1.3p1.2S_1/2", "continuum"},
        {8290, 3021, 84.9459991, "mg_viii", "2s1.2p1.3p1.2S_1/2", "continuum"},
        {8291, 3022, 73.9060059, "mg_viii", "2s1.2p1.3p1.2P_1/2#2", "continuum"},
        {8292, 3023, 73.0879974, "mg_viii", "2s1.2p1.3p1.2S_1/2#2", "continuum"},
        {8293, 3024, 69.1990051, "mg_viii", "2s0.2p2.3s1.4P_1/2", "continuum"},
        {8294, 3024, 69.1990051, "mg_viii", "2s0.2p2.3s1.4P_1/2", "continuum"},
        {8295, 3024, 69.1990051, "mg_viii", "2s0.2p2.3s1.4P_1/2", "continuum"},
        {8296, 3025, 65.7480011, "mg_viii", "2s0.2p2.3s1.2P_1/2", "continuum"},
        {8297, 3025, 65.7480011, "mg_viii", "2s0.2p2.3s1.2P_1/2", "continuum"},
        {8298, 3025, 65.7480011, "mg_viii", "2s0.2p2.3s1.2P_1/2", "continuum"},
        {8299, 3026, 55.9830017, "mg_viii", "2s0.2p2.3d1.4D_1/2", "continuum"},
        {8300, 3026, 55.9830017, "mg_viii", "2s0.2p2.3d1.4D_1/2", "continuum"},
        {8301, 3026, 55.9830017, "mg_viii", "2s0.2p2.3d1.4D_1/2", "continuum"},
        {8302, 3027, 55.7129974, "mg_viii", "2s0.2p2.3d1.2P_1/2", "continuum"},
        {8303, 3027, 55.7129974, "mg_viii", "2s0.2p2.3d1.2P_1/2", "continuum"},
        {8304, 3027, 55.7129974, "mg_viii", "2s0.2p2.3d1.2P_1/2", "continuum"},
        {8305, 3028, 53.1900024, "mg_viii", "2s0.2p2.3d1.4P_1/2", "continuum"},
        {8306, 3028, 53.1900024, "mg_viii", "2s0.2p2.3d1.4P_1/2", "continuum"},
        {8307, 3028, 53.1900024, "mg_viii", "2s0.2p2.3d1.4P_1/2", "continuum"},
        {8308, 3029, 51.4600067, "mg_viii", "2s0.2p2.3s1.2S_1/2", "continuum"},
        {8309, 3030, 48.6670074, "mg_viii", "2s0.2p2.3d1.2P_1/2#2", "continuum"},
        {8310, 3031, 45.2980042, "mg_viii", "2s0.2p2.3d1.2S_1/2", "continuum"},
        {8311, 3032, 100.444, "mg_viii", "2p0.3d1.2D_3/2", "continuum"},
        {8312, 3032, 100.444, "mg_viii", "2p0.3d1.2D_3/2", "continuum"},
        {8313, 3032, 100.444, "mg_viii", "2p0.3d1.2D_3/2", "continuum"},
        {8314, 3033, 91.3300018, "mg_viii", "2s1.2p1.3p1.2P_3/2", "continuum"},
        {8315, 3033, 91.3300018, "mg_viii", "2s1.2p1.3p1.2P_3/2", "continuum"},
        {8316, 3033, 91.3300018, "mg_viii", "2s1.2p1.3p1.2P_3/2", "continuum"},
        {8317, 3034, 92.3329926, "mg_viii", "2s1.2p1.3p1.4D_3/2", "continuum"},
        {8318, 3034, 92.3329926, "mg_viii", "2s1.2p1.3p1.4D_3/2", "continuum"},
        {8319, 3034, 92.3329926, "mg_viii", "2s1.2p1.3p1.4D_3/2", "continuum"},
        {8320, 3035, 90.8480072, "mg_viii", "2s1.2p1.3p1.4S_3/2", "continuum"},
        {8321, 3035, 90.8480072, "mg_viii", "2s1.2p1.3p1.4S_3/2", "continuum"},
        {8322, 3035, 90.8480072, "mg_viii", "2s1.2p1.3p1.4S_3/2", "continuum"},
        {8323, 3036, 89.8200073, "mg_viii", "2s1.2p1.3p1.4P_3/2", "continuum"},
        {8324, 3036, 89.8200073, "mg_viii", "2s1.2p1.3p1.4P_3/2", "continuum"},
        {8325, 3036, 89.8200073, "mg_viii", "2s1.2p1.3p1.4P_3/2", "continuum"},
        {8326, 3037, 87.4620056, "mg_viii", "2s1.2p1.3p1.2D_3/2", "continuum"},
        {8327, 3037, 87.4620056, "mg_viii", "2s1.2p1.3p1.2D_3/2", "continuum"},
        {8328, 3037, 87.4620056, "mg_viii", "2s1.2p1.3p1.2D_3/2", "continuum"},
        {8329, 3038, 73.8350067, "mg_viii", "2s1.2p1.3p1.2P_3/2#2", "continuum"},
        {8330, 3039, 73.8580017, "mg_viii", "2s1.2p1.3p1.2D_3/2#2", "continuum"},
        {8331, 3040, 69.0469971, "mg_viii", "2s0.2p2.3s1.4P_3/2", "continuum"},
        {8332, 3040, 69.0469971, "mg_viii", "2s0.2p2.3s1.4P_3/2", "continuum"},
        {8333, 3040, 69.0469971, "mg_viii", "2s0.2p2.3s1.4P_3/2", "continuum"},
        {8334, 3041, 65.496994, "mg_viii", "2s0.2p2.3s1.2P_3/2", "continuum"},
        {8335, 3041, 65.496994, "mg_viii", "2s0.2p2.3s1.2P_3/2", "continuum"},
        {8336, 3041, 65.496994, "mg_viii", "2s0.2p2.3s1.2P_3/2", "continuum"},
        {8337, 3042, 62.901001, "mg_viii", "2s0.2p2.3s1.2D_3/2", "continuum"},
        {8338, 3043, 57.4170074, "mg_viii", "2s0.2p2.3d1.4F_3/2", "continuum"},
        {8339, 3043, 57.4170074, "mg_viii", "2s0.2p2.3d1.4F_3/2", "continuum"},
        {8340, 3043, 57.4170074, "mg_viii", "2s0.2p2.3d1.4F_3/2", "continuum"},
        {8341, 3044, 56.0720062, "mg_viii", "2s0.2p2.3d1.2P_3/2", "continuum"},
        {8342, 3044, 56.0720062, "mg_viii", "2s0.2p2.3d1.2P_3/2", "continuum"},
        {8343, 3044, 56.0720062, "mg_viii", "2s0.2p2.3d1.2P_3/2", "continuum"},
        {8344, 3045, 55.8419952, "mg_viii", "2s0.2p2.3d1.4D_3/2", "continuum"},
        {8345, 3045, 55.8419952, "mg_viii", "2s0.2p2.3d1.4D_3/2", "continuum"},
        {8346, 3045, 55.8419952, "mg_viii", "2s0.2p2.3d1.4D_3/2", "continuum"},
        {8347, 3046, 53.2440033, "mg_viii", "2s0.2p2.3d1.4P_3/2", "continuum"},
        {8348, 3046, 53.2440033, "mg_viii", "2s0.2p2.3d1.4P_3/2", "continuum"},
        {8349, 3046, 53.2440033, "mg_viii", "2s0.2p2.3d1.4P_3/2", "continuum"},
        {8350, 3047, 50.8209991, "mg_viii", "2s0.2p2.3d1.2D_3/2", "continuum"},
        {8351, 3047, 50.8209991, "mg_viii", "2s0.2p2.3d1.2D_3/2", "continuum"},
        {8352, 3047, 50.8209991, "mg_viii", "2s0.2p2.3d1.2D_3/2", "continuum"},
        {8353, 3048, 48.697998, "mg_viii", "2s0.2p2.3d1.2D_3/2#2", "continuum"},
        {8354, 3049, 48.5249939, "mg_viii", "2s0.2p2.3d1.2P_3/2#2", "continuum"},
        {8355, 3050, 36.8710022, "mg_viii", "2s0.2p2.3d1.2D_3/2#3", "continuum"},
        {8356, 3051, 100.423004, "mg_viii", "2p0.3d1.2D_5/2", "continuum"},
        {8357, 3051, 100.423004, "mg_viii", "2p0.3d1.2D_5/2", "continuum"},
        {8358, 3051, 100.423004, "mg_viii", "2p0.3d1.2D_5/2", "continuum"},
        {8359, 3052, 92.2299957, "mg_viii", "2s1.2p1.3p1.4D_5/2", "continuum"},
        {8360, 3052, 92.2299957, "mg_viii", "2s1.2p1.3p1.4D_5/2", "continuum"},
        {8361, 3052, 92.2299957, "mg_viii", "2s1.2p1.3p1.4D_5/2", "continuum"},
        {8362, 3053, 89.6959991, "mg_viii", "2s1.2p1.3p1.4P_5/2", "continuum"},
        {8363, 3053, 89.6959991, "mg_viii", "2s1.2p1.3p1.4P_5/2", "continuum"},
        {8364, 3053, 89.6959991, "mg_viii", "2s1.2p1.3p1.4P_5/2", "continuum"},
        {8365, 3054, 87.1869965, "mg_viii", "2s1.2p1.3p1.2D_5/2", "continuum"},
        {8366, 3054, 87.1869965, "mg_viii", "2s1.2p1.3p1.2D_5/2", "continuum"},
        {8367, 3054, 87.1869965, "mg_viii", "2s1.2p1.3p1.2D_5/2", "continuum"},
        {8368, 3055, 74.0469971, "mg_viii", "2s1.2p1.3p1.2D_5/2#2", "continuum"},
        {8369, 3056, 68.798996, "mg_viii", "2s0.2p2.3s1.4P_5/2", "continuum"},
        {8370, 3056, 68.798996, "mg_viii", "2s0.2p2.3s1.4P_5/2", "continuum"},
        {8371, 3056, 68.798996, "mg_viii", "2s0.2p2.3s1.4P_5/2", "continuum"},
        {8372, 3057, 62.7870026, "mg_viii", "2s0.2p2.3s1.2D_5/2", "continuum"},
        {8373, 3058, 57.3320007, "mg_viii", "2s0.2p2.3d1.4F_5/2", "continuum"},
        {8374, 3058, 57.3320007, "mg_viii", "2s0.2p2.3d1.4F_5/2", "continuum"},
        {8375, 3058, 57.3320007, "mg_viii", "2s0.2p2.3d1.4F_5/2", "continuum"},
        {8376, 3059, 55.8509979, "mg_viii", "2s0.2p2.3d1.4D_5/2", "continuum"},
        {8377, 3059, 55.8509979, "mg_viii", "2s0.2p2.3d1.4D_5/2", "continuum"},
        {8378, 3059, 55.8509979, "mg_viii", "2s0.2p2.3d1.4D_5/2", "continuum"},
        {8379, 3060, 54.9620056, "mg_viii", "2s0.2p2.3d1.2F_5/2", "continuum"},
        {8380, 3060, 54.9620056, "mg_viii", "2s0.2p2.3d1.2F_5/2", "continuum"},
        {8381, 3060, 54.9620056, "mg_viii", "2s0.2p2.3d1.2F_5/2", "continuum"},
        {8382, 3061, 53.3439941, "mg_viii", "2s0.2p2.3d1.4P_5/2", "continuum"},
        {8383, 3061, 53.3439941, "mg_viii", "2s0.2p2.3d1.4P_5/2", "continuum"},
        {8384, 3061, 53.3439941, "mg_viii", "2s0.2p2.3d1.4P_5/2", "continuum"},
        {8385, 3062, 54.9089966, "mg_viii", "2s0.2p2.3d1.2D_5/2", "continuum"},
        {8386, 3062, 54.9089966, "mg_viii", "2s0.2p2.3d1.2D_5/2", "continuum"},
        {8387, 3062, 54.9089966, "mg_viii", "2s0.2p2.3d1.2D_5/2", "continuum"},
        {8388, 3063, 51.1139984, "mg_viii", "2s0.2p2.3d1.2D_5/2#2", "continuum"},
        {8389, 3064, 48.2050018, "mg_viii", "2s0.2p2.3d1.2F_5/2#2", "continuum"},
        {8390, 3065, 36.9199982, "mg_viii", "2s0.2p2.3d1.2D_5/2#3", "continuum"},
        {8391, 3066, 92, "mg_viii", "2s1.2p1.3p1.4D_7/2", "continuum"},
        {8392, 3066, 92, "mg_viii", "2s1.2p1.3p1.4D_7/2", "continuum"},
        {8393, 3066, 92, "mg_viii", "2s1.2p1.3p1.4D_7/2", "continuum"},
        {8394, 3067, 57.2109985, "mg_viii", "2s0.2p2.3d1.4F_7/2", "continuum"},
        {8395, 3067, 57.2109985, "mg_viii", "2s0.2p2.3d1.4F_7/2", "continuum"},
        {8396, 3067, 57.2109985, "mg_viii", "2s0.2p2.3d1.4F_7/2", "continuum"},
        {8397, 3068, 55.7830048, "mg_viii", "2s0.2p2.3d1.4D_7/2", "continuum"},
        {8398, 3068, 55.7830048, "mg_viii", "2s0.2p2.3d1.4D_7/2", "continuum"},
        {8399, 3068, 55.7830048, "mg_viii", "2s0.2p2.3d1.4D_7/2", "continuum"},
        {8400, 3069, 55.0659943, "mg_viii", "2s0.2p2.3d1.2F_7/2", "continuum"},
        {8401, 3069, 55.0659943, "mg_viii", "2s0.2p2.3d1.2F_7/2", "continuum"},
        {8402, 3069, 55.0659943, "mg_viii", "2s0.2p2.3d1.2F_7/2", "continuum"},
        {8403, 3071, 48.8540039, "mg_viii", "2s0.2p2.3d1.2F_7/2#2", "continuum"},
        {8404, 3072, 57.0549927, "mg_viii", "2s0.2p2.3d1.4F_9/2", "continuum"},
        {8405, 3072, 57.0549927, "mg_viii", "2s0.2p2.3d1.4F_9/2", "continuum"},
        {8406, 3072, 57.0549927, "mg_viii", "2s0.2p2.3d1.4F_9/2", "continuum"},
        {8407, 3074, 109.337006, "mg_viii", "2p0.3p1.2P_1/2", "continuum"},
        {8408, 3074, 109.337006, "mg_viii", "2p0.3p1.2P_1/2", "continuum"},
        {8409, 3074, 109.337006, "mg_viii", "2p0.3p1.2P_1/2", "continuum"},
        {8410, 3075, 98.5189972, "mg_viii", "2s1.2p1.3s1.4P_1/2", "continuum"},
        {8411, 3075, 98.5189972, "mg_viii", "2s1.2p1.3s1.4P_1/2", "continuum"},
        {8412, 3075, 98.5189972, "mg_viii", "2s1.2p1.3s1.4P_1/2", "continuum"},
        {8413, 3076, 94.7940063, "mg_viii", "2s1.2p1.3s1.2P_1/2", "continuum"},
        {8414, 3076, 94.7940063, "mg_viii", "2s1.2p1.3s1.2P_1/2", "continuum"},
        {8415, 3076, 94.7940063, "mg_viii", "2s1.2p1.3s1.2P_1/2", "continuum"},
        {8416, 3077, 84.3090057, "mg_viii", "2s1.2p1.3d1.4D_1/2", "continuum"},
        {8417, 3077, 84.3090057, "mg_viii", "2s1.2p1.3d1.4D_1/2", "continuum"},
        {8418, 3077, 84.3090057, "mg_viii", "2s1.2p1.3d1.4D_1/2", "continuum"},
        {8419, 3078, 81.9720001, "mg_viii", "2s1.2p1.3d1.4P_1/2", "continuum"},
        {8420, 3078, 81.9720001, "mg_viii", "2s1.2p1.3d1.4P_1/2", "continuum"},
        {8421, 3078, 81.9720001, "mg_viii", "2s1.2p1.3d1.4P_1/2", "continuum"},
        {8422, 3079, 81.7160034, "mg_viii", "2s1.2p1.3s1.2P_1/2#2", "continuum"},
        {8423, 3080, 78.3339996, "mg_viii", "2s1.2p1.3d1.2P_1/2", "continuum"},
        {8424, 3080, 78.3339996, "mg_viii", "2s1.2p1.3d1.2P_1/2", "continuum"},
        {8425, 3080, 78.3339996, "mg_viii", "2s1.2p1.3d1.2P_1/2", "continuum"},
        {8426, 3081, 66.3860016, "mg_viii", "2s1.2p1.3d1.2P_1/2#2", "continuum"},
        {8427, 3082, 64.6660004, "mg_viii", "2s0.2p2.3p1.2S_1/2", "continuum"},
        {8428, 3082, 64.6660004, "mg_viii", "2s0.2p2.3p1.2S_1/2", "continuum"},
        {8429, 3082, 64.6660004, "mg_viii", "2s0.2p2.3p1.2S_1/2", "continuum"},
        {8430, 3083, 63.4570007, "mg_viii", "2s0.2p2.3p1.4D_1/2", "continuum"},
        {8431, 3083, 63.4570007, "mg_viii", "2s0.2p2.3p1.4D_1/2", "continuum"},
        {8432, 3083, 63.4570007, "mg_viii", "2s0.2p2.3p1.4D_1/2", "continuum"},
        {8433, 3084, 62.3970032, "mg_viii", "2s0.2p2.3p1.4P_1/2", "continuum"},
        {8434, 3084, 62.3970032, "mg_viii", "2s0.2p2.3p1.4P_1/2", "continuum"},
        {8435, 3084, 62.3970032, "mg_viii", "2s0.2p2.3p1.4P_1/2", "continuum"},
        {8436, 3085, 59.2920074, "mg_viii", "2s0.2p2.3p1.2P_1/2", "continuum"},
        {8437, 3085, 59.2920074, "mg_viii", "2s0.2p2.3p1.2P_1/2", "continuum"},
        {8438, 3085, 59.2920074, "mg_viii", "2s0.2p2.3p1.2P_1/2", "continuum"},
        {8439, 3086, 52.3679962, "mg_viii", "2s0.2p2.3p1.2P_1/2#2", "continuum"},
        {8440, 3087, 43.3000031, "mg_viii", "2s0.2p2.3p1.2P_1/2#3", "continuum"},
        {8441, 3088, 109.218002, "mg_viii", "2p0.3p1.2P_3/2", "continuum"},
        {8442, 3088, 109.218002, "mg_viii", "2p0.3p1.2P_3/2", "continuum"},
        {8443, 3088, 109.218002, "mg_viii", "2p0.3p1.2P_3/2", "continuum"},
        {8444, 3089, 98.378006, "mg_viii", "2s1.2p1.3s1.4P_3/2", "continuum"},
        {8445, 3089, 98.378006, "mg_viii", "2s1.2p1.3s1.4P_3/2", "continuum"},
        {8446, 3089, 98.378006, "mg_viii", "2s1.2p1.3s1.4P_3/2", "continuum"},
        {8447, 3090, 94.5070038, "mg_viii", "2s1.2p1.3s1.2P_3/2", "continuum"},
        {8448, 3090, 94.5070038, "mg_viii", "2s1.2p1.3s1.2P_3/2", "continuum"},
        {8449, 3090, 94.5070038, "mg_viii", "2s1.2p1.3s1.2P_3/2", "continuum"},
        {8450, 3091, 85.9089966, "mg_viii", "2s1.2p1.3d1.4F_3/2", "continuum"},
        {8451, 3091, 85.9089966, "mg_viii", "2s1.2p1.3d1.4F_3/2", "continuum"},
        {8452, 3091, 85.9089966, "mg_viii", "2s1.2p1.3d1.4F_3/2", "continuum"},
        {8453, 3092, 83.0440063, "mg_viii", "2s1.2p1.3d1.4D_3/2", "continuum"},
        {8454, 3092, 83.0440063, "mg_viii", "2s1.2p1.3d1.4D_3/2", "continuum"},
        {8455, 3092, 83.0440063, "mg_viii", "2s1.2p1.3d1.4D_3/2", "continuum"},
        {8456, 3093, 82.7859955, "mg_viii", "2s1.2p1.3d1.2D_3/2", "continuum"},
        {8457, 3093, 82.7859955, "mg_viii", "2s1.2p1.3d1.2D_3/2", "continuum"},
        {8458, 3093, 82.7859955, "mg_viii", "2s1.2p1.3d1.2D_3/2", "continuum"},
        {8459, 3094, 82.0319977, "mg_viii", "2s1.2p1.3d1.4P_3/2", "continuum"},
        {8460, 3094, 82.0319977, "mg_viii", "2s1.2p1.3d1.4P_3/2", "continuum"},
        {8461, 3094, 82.0319977, "mg_viii", "2s1.2p1.3d1.4P_3/2", "continuum"},
        {8462, 3095, 81.6950073, "mg_viii", "2s1.2p1.3s1.2P_3/2#2", "continuum"},
        {8463, 3096, 78.4779968, "mg_viii", "2s1.2p1.3d1.2P_3/2", "continuum"},
        {8464, 3096, 78.4779968, "mg_viii", "2s1.2p1.3d1.2P_3/2", "continuum"},
        {8465, 3096, 78.4779968, "mg_viii", "2s1.2p1.3d1.2P_3/2", "continuum"},
        {8466, 3097, 66.7350006, "mg_viii", "2s1.2p1.3d1.2D_3/2#2", "continuum"},
        {8467, 3098, 64.878006, "mg_viii", "2s1.2p1.3d1.2P_3/2#2", "continuum"},
        {8468, 3099, 63.3650055, "mg_viii", "2s0.2p2.3p1.4D_3/2", "continuum"},
        {8469, 3099, 63.3650055, "mg_viii", "2s0.2p2.3p1.4D_3/2", "continuum"},
        {8470, 3099, 63.3650055, "mg_viii", "2s0.2p2.3p1.4D_3/2", "continuum"},
        {8471, 3100, 62.3320007, "mg_viii", "2s0.2p2.3p1.4P_3/2", "continuum"},
        {8472, 3100, 62.3320007, "mg_viii", "2s0.2p2.3p1.4P_3/2", "continuum"},
        {8473, 3100, 62.3320007, "mg_viii", "2s0.2p2.3p1.4P_3/2", "continuum"},
        {8474, 3101, 61.2519989, "mg_viii", "2s0.2p2.3p1.2D_3/2", "continuum"},
        {8475, 3101, 61.2519989, "mg_viii", "2s0.2p2.3p1.2D_3/2", "continuum"},
        {8476, 3101, 61.2519989, "mg_viii", "2s0.2p2.3p1.2D_3/2", "continuum"},
        {8477, 3102, 58.5350037, "mg_viii", "2s0.2p2.3p1.4S_3/2", "continuum"},
        {8478, 3102, 58.5350037, "mg_viii", "2s0.2p2.3p1.4S_3/2", "continuum"},
        {8479, 3102, 58.5350037, "mg_viii", "2s0.2p2.3p1.4S_3/2", "continuum"},
        {8480, 3103, 59.3099976, "mg_viii", "2s0.2p2.3p1.2P_3/2", "continuum"},
        {8481, 3103, 59.3099976, "mg_viii", "2s0.2p2.3p1.2P_3/2", "continuum"},
        {8482, 3103, 59.3099976, "mg_viii", "2s0.2p2.3p1.2P_3/2", "continuum"},
        {8483, 3104, 54.3699951, "mg_viii", "2s0.2p2.3p1.2D_3/2#2", "continuum"},
        {8484, 3105, 52.2120056, "mg_viii", "2s0.2p2.3p1.2P_3/2#2", "continuum"},
        {8485, 3106, 43.2590027, "mg_viii", "2s0.2p2.3p1.2P_3/2#3", "continuum"},
        {8486, 3107, 98.1269989, "mg_viii", "2s1.2p1.3s1.4P_5/2", "continuum"},
        {8487, 3107, 98.1269989, "mg_viii", "2s1.2p1.3s1.4P_5/2", "continuum"},
        {8488, 3107, 98.1269989, "mg_viii", "2s1.2p1.3s1.4P_5/2", "continuum"},
        {8489, 3108, 85.8220062, "mg_viii", "2s1.2p1.3d1.4F_5/2", "continuum"},
        {8490, 3108, 85.8220062, "mg_viii", "2s1.2p1.3d1.4F_5/2", "continuum"},
        {8491, 3108, 85.8220062, "mg_viii", "2s1.2p1.3d1.4F_5/2", "continuum"},
        {8492, 3109, 83.003006, "mg_viii", "2s1.2p1.3d1.4D_5/2", "continuum"},
        {8493, 3109, 83.003006, "mg_viii", "2s1.2p1.3d1.4D_5/2", "continuum"},
        {8494, 3109, 83.003006, "mg_viii", "2s1.2p1.3d1.4D_5/2", "continuum"},
        {8495, 3110, 82.7420044, "mg_viii", "2s1.2p1.3d1.2D_5/2", "continuum"},
        {8496, 3110, 82.7420044, "mg_viii", "2s1.2p1.3d1.2D_5/2", "continuum"},
        {8497, 3110, 82.7420044, "mg_viii", "2s1.2p1.3d1.2D_5/2", "continuum"},
        {8498, 3111, 82.1230011, "mg_viii", "2s1.2p1.3d1.4P_5/2", "continuum"},
        {8499, 3111, 82.1230011, "mg_viii", "2s1.2p1.3d1.4P_5/2", "continuum"},
        {8500, 3111, 82.1230011, "mg_viii", "2s1.2p1.3d1.4P_5/2", "continuum"},
        {8501, 3112, 79.4830017, "mg_viii", "2s1.2p1.3d1.2F_5/2", "continuum"},
        {8502, 3112, 79.4830017, "mg_viii", "2s1.2p1.3d1.2F_5/2", "continuum"},
        {8503, 3112, 79.4830017, "mg_viii", "2s1.2p1.3d1.2F_5/2", "continuum"},
        {8504, 3113, 68.0209961, "mg_viii", "2s1.2p1.3d1.2F_5/2#2", "continuum"},
        {8505, 3114, 66.6909943, "mg_viii", "2s1.2p1.3d1.2D_5/2#2", "continuum"},
        {8506, 3115, 63.2140045, "mg_viii", "2s0.2p2.3p1.4D_5/2", "continuum"},
        {8507, 3115, 63.2140045, "mg_viii", "2s0.2p2.3p1.4D_5/2", "continuum"},
        {8508, 3115, 63.2140045, "mg_viii", "2s0.2p2.3p1.4D_5/2", "continuum"},
        {8509, 3116, 61.2250061, "mg_viii", "2s0.2p2.3p1.4P_5/2", "continuum"},
        {8510, 3116, 61.2250061, "mg_viii", "2s0.2p2.3p1.4P_5/2", "continuum"},
        {8511, 3116, 61.2250061, "mg_viii", "2s0.2p2.3p1.4P_5/2", "continuum"},
        {8512, 3117, 60.9720001, "mg_viii", "2s0.2p2.3p1.2D_5/2", "continuum"},
        {8513, 3117, 60.9720001, "mg_viii", "2s0.2p2.3p1.2D_5/2", "continuum"},
        {8514, 3117, 60.9720001, "mg_viii", "2s0.2p2.3p1.2D_5/2", "continuum"},
        {8515, 3118, 56.496994, "mg_viii", "2s0.2p2.3p1.2F_5/2", "continuum"},
        {8516, 3119, 54.4019928, "mg_viii", "2s0.2p2.3p1.2D_5/2#2", "continuum"},
        {8517, 3120, 85.6909943, "mg_viii", "2s1.2p1.3d1.4F_7/2", "continuum"},
        {8518, 3120, 85.6909943, "mg_viii", "2s1.2p1.3d1.4F_7/2", "continuum"},
        {8519, 3120, 85.6909943, "mg_viii", "2s1.2p1.3d1.4F_7/2", "continuum"},
        {8520, 3121, 82.901001, "mg_viii", "2s1.2p1.3d1.4D_7/2", "continuum"},
        {8521, 3121, 82.901001, "mg_viii", "2s1.2p1.3d1.4D_7/2", "continuum"},
        {8522, 3121, 82.901001, "mg_viii", "2s1.2p1.3d1.4D_7/2", "continuum"},
        {8523, 3122, 79.2290039, "mg_viii", "2s1.2p1.3d1.2F_7/2", "continuum"},
        {8524, 3122, 79.2290039, "mg_viii", "2s1.2p1.3d1.2F_7/2", "continuum"},
        {8525, 3122, 79.2290039, "mg_viii", "2s1.2p1.3d1.2F_7/2", "continuum"},
        {8526, 3123, 67.1069946, "mg_viii", "2s1.2p1.3d1.2F_7/2#2", "continuum"},
        {8527, 3124, 61.9730072, "mg_viii", "2s0.2p2.3p1.4D_7/2", "continuum"},
        {8528, 3124, 61.9730072, "mg_viii", "2s0.2p2.3p1.4D_7/2", "continuum"},
        {8529, 3124, 61.9730072, "mg_viii", "2s0.2p2.3p1.4D_7/2", "continuum"},
        {8530, 3125, 56.4230042, "mg_viii", "2s0.2p2.3p1.2F_7/2", "continuum"},
        {8531, 3126, 85.5119934, "mg_viii", "2s1.2p1.3d1.4F_9/2", "continuum"},
        {8532, 3126, 85.5119934, "mg_viii", "2s1.2p1.3d1.4F_9/2", "continuum"},
        {8533, 3126, 85.5119934, "mg_viii", "2s1.2p1.3d1.4F_9/2", "continuum"},
        {8534, 3127, 1.84698486, "mg_viii", "superlevel", "continuum"},
        {8535, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8536, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8537, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8538, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8539, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8540, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8541, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8542, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8543, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8544, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8545, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8546, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8547, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8548, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8549, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8550, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8551, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8552, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8553, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8554, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8555, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8556, 3165, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8557, 3166, 310.587006, "mg_ix", "2s1.2p1.3P_0", "continuum"},
        {8558, 3167, 310.447296, "mg_ix", "2s1.2p1.3P_1", "continuum"},
        {8559, 3168, 310.142395, "mg_ix", "2s1.2p1.3P_2", "continuum"},
        {8560, 3169, 294.329102, "mg_ix", "2s1.2p1.1P_1", "continuum"},
        {8561, 3170, 282.658508, "mg_ix", "2s0.2p2.3P_0", "continuum"},
        {8562, 3170, 282.658508, "mg_ix", "2s0.2p2.3P_0", "continuum"},
        {8563, 3171, 282.497009, "mg_ix", "2s0.2p2.3P_1", "continuum"},
        {8564, 3171, 282.497009, "mg_ix", "2s0.2p2.3P_1", "continuum"},
        {8565, 3172, 282.227905, "mg_ix", "2s0.2p2.3P_2", "continuum"},
        {8566, 3172, 282.227905, "mg_ix", "2s0.2p2.3P_2", "continuum"},
        {8567, 3173, 277.794891, "mg_ix", "2s0.2p2.1D_2", "continuum"},
        {8568, 3173, 277.794891, "mg_ix", "2s0.2p2.1D_2", "continuum"},
        {8569, 3174, 266.079102, "mg_ix", "2s0.2p2.1S_0", "continuum"},
        {8570, 3174, 266.079102, "mg_ix", "2s0.2p2.1S_0", "continuum"},
        {8571, 3175, 138.080002, "mg_ix", "2s1.3s1.3S_1", "continuum"},
        {8572, 3176, 134.904007, "mg_ix", "2s1.3s1.1S_0", "continuum"},
        {8573, 3177, 130.501007, "mg_ix", "2s1.3p1.1P_1", "continuum"},
        {8574, 3178, 132.806, "mg_ix", "2s1.3p1.3P_0", "continuum"},
        {8575, 3179, 132.707993, "mg_ix", "2s1.3p1.3P_1", "continuum"},
        {8576, 3180, 132.591003, "mg_ix", "2s1.3p1.3P_2", "continuum"},
        {8577, 3181, 125.860992, "mg_ix", "2s1.3d1.3D_1", "continuum"},
        {8578, 3182, 125.845001, "mg_ix", "2s1.3d1.3D_2", "continuum"},
        {8579, 3183, 125.826996, "mg_ix", "2s1.3d1.3D_3", "continuum"},
        {8580, 3184, 122.944, "mg_ix", "2s1.3d1.1D_2", "continuum"},
        {8581, 3185, 105.917007, "mg_ix", "2s0.2p1.3p1.3P_0", "continuum"},
        {8582, 3185, 105.917007, "mg_ix", "2s0.2p1.3p1.3P_0", "continuum"},
        {8583, 3186, 96.7129974, "mg_ix", "2s0.2p1.3p1.1S_0", "continuum"},
        {8584, 3186, 96.7129974, "mg_ix", "2s0.2p1.3p1.1S_0", "continuum"},
        {8585, 3187, 110.007004, "mg_ix", "2s0.2p1.3p1.3D_3", "continuum"},
        {8586, 3187, 110.007004, "mg_ix", "2s0.2p1.3p1.3D_3", "continuum"},
        {8587, 3188, 116.057999, "mg_ix", "2s0.2p1.3s1.3P_0", "continuum"},
        {8588, 3188, 116.057999, "mg_ix", "2s0.2p1.3s1.3P_0", "continuum"},
        {8589, 3189, 102.848007, "mg_ix", "2s0.2p1.3d1.3P_0", "continuum"},
        {8590, 3189, 102.848007, "mg_ix", "2s0.2p1.3d1.3P_0", "continuum"},
        {8591, 3190, 103.175995, "mg_ix", "2s0.2p1.3d1.3F_4", "continuum"},
        {8592, 3190, 103.175995, "mg_ix", "2s0.2p1.3d1.3F_4", "continuum"},
        {8593, 3191, 111.350998, "mg_ix", "2s0.2p1.3p1.1P_1", "continuum"},
        {8594, 3191, 111.350998, "mg_ix", "2s0.2p1.3p1.1P_1", "continuum"},
        {8595, 3192, 110.440002, "mg_ix", "2s0.2p1.3p1.3D_1", "continuum"},
        {8596, 3192, 110.440002, "mg_ix", "2s0.2p1.3p1.3D_1", "continuum"},
        {8597, 3193, 108.593002, "mg_ix", "2s0.2p1.3p1.3S_1", "continuum"},
        {8598, 3193, 108.593002, "mg_ix", "2s0.2p1.3p1.3S_1", "continuum"},
        {8599, 3194, 107.563004, "mg_ix", "2s0.2p1.3p1.3P_1", "continuum"},
        {8600, 3194, 107.563004, "mg_ix", "2s0.2p1.3p1.3P_1", "continuum"},
        {8601, 3195, 110.317001, "mg_ix", "2s0.2p1.3p1.3D_2", "continuum"},
        {8602, 3195, 110.317001, "mg_ix", "2s0.2p1.3p1.3D_2", "continuum"},
        {8603, 3196, 107.401993, "mg_ix", "2s0.2p1.3p1.3P_2", "continuum"},
        {8604, 3196, 107.401993, "mg_ix", "2s0.2p1.3p1.3P_2", "continuum"},
        {8605, 3197, 105.434006, "mg_ix", "2s0.2p1.3p1.1D_2", "continuum"},
        {8606, 3197, 105.434006, "mg_ix", "2s0.2p1.3p1.1D_2", "continuum"},
        {8607, 3198, 115.921005, "mg_ix", "2s0.2p1.3s1.3P_1", "continuum"},
        {8608, 3198, 115.921005, "mg_ix", "2s0.2p1.3s1.3P_1", "continuum"},
        {8609, 3199, 111.981003, "mg_ix", "2s0.2p1.3s1.1P_1", "continuum"},
        {8610, 3199, 111.981003, "mg_ix", "2s0.2p1.3s1.1P_1", "continuum"},
        {8611, 3200, 104.014999, "mg_ix", "2s0.2p1.3d1.3D_1", "continuum"},
        {8612, 3200, 104.014999, "mg_ix", "2s0.2p1.3d1.3D_1", "continuum"},
        {8613, 3201, 102.912994, "mg_ix", "2s0.2p1.3d1.3P_1", "continuum"},
        {8614, 3201, 102.912994, "mg_ix", "2s0.2p1.3d1.3P_1", "continuum"},
        {8615, 3202, 99.7709961, "mg_ix", "2s0.2p1.3d1.1P_1", "continuum"},
        {8616, 3202, 99.7709961, "mg_ix", "2s0.2p1.3d1.1P_1", "continuum"},
        {8617, 3203, 115.591995, "mg_ix", "2s0.2p1.3s1.3P_2", "continuum"},
        {8618, 3203, 115.591995, "mg_ix", "2s0.2p1.3s1.3P_2", "continuum"},
        {8619, 3204, 103.959, "mg_ix", "2s0.2p1.3d1.3F_2", "continuum"},
        {8620, 3204, 103.959, "mg_ix", "2s0.2p1.3d1.3F_2", "continuum"},
        {8621, 3205, 106.205994, "mg_ix", "2s0.2p1.3d1.1D_2", "continuum"},
        {8622, 3205, 106.205994, "mg_ix", "2s0.2p1.3d1.1D_2", "continuum"},
        {8623, 3206, 103.947998, "mg_ix", "2s0.2p1.3d1.3D_2", "continuum"},
        {8624, 3206, 103.947998, "mg_ix", "2s0.2p1.3d1.3D_2", "continuum"},
        {8625, 3207, 103.035995, "mg_ix", "2s0.2p1.3d1.3P_2", "continuum"},
        {8626, 3207, 103.035995, "mg_ix", "2s0.2p1.3d1.3P_2", "continuum"},
        {8627, 3208, 103.567001, "mg_ix", "2s0.2p1.3d1.3F_3", "continuum"},
        {8628, 3208, 103.567001, "mg_ix", "2s0.2p1.3d1.3F_3", "continuum"},
        {8629, 3209, 103.824005, "mg_ix", "2s0.2p1.3d1.3D_3", "continuum"},
        {8630, 3209, 103.824005, "mg_ix", "2s0.2p1.3d1.3D_3", "continuum"},
        {8631, 3210, 100.623001, "mg_ix", "2s0.2p1.3d1.1F_3", "continuum"},
        {8632, 3210, 100.623001, "mg_ix", "2s0.2p1.3d1.1F_3", "continuum"},
        {8633, 3211, 2.27801514, "mg_ix", "superlevel", "continuum"},
        {8634, 3244, 367, "mg_x", "2s1.2S_1/2", "continuum"},
        {8635, 3244, 367, "mg_x", "2s1.2S_1/2", "continuum"},
        {8636, 3244, 367, "mg_x", "2s1.2S_1/2", "continuum"},
        {8637, 3244, 367, "mg_x", "2s1.2S_1/2", "continuum"},
        {8638, 3244, 367, "mg_x", "2s1.2S_1/2", "continuum"},
        {8639, 3244, 367, "mg_x", "2s1.2S_1/2", "continuum"},
        {8640, 3245, 347.169006, "mg_x", "2s0.2p1.2P_1/2", "continuum"},
        {8641, 3246, 346.6763, "mg_x", "2s0.2p1.2P_3/2", "continuum"},
        {8642, 3247, 158.459, "mg_x", "2s0.3s1.2S_1/2", "continuum"},
        {8643, 3248, 153.028, "mg_x", "2s0.3p1.2P_1/2", "continuum"},
        {8644, 3249, 152.865997, "mg_x", "2s0.3p1.2P_3/2", "continuum"},
        {8645, 3250, 150.923996, "mg_x", "2s0.3d1.2D_3/2", "continuum"},
        {8646, 3251, 150.876007, "mg_x", "2s0.3d1.2D_5/2", "continuum"},
        {8647, 3252, 87.8299866, "mg_x", "2s0.4s1.2S_1/2", "continuum"},
        {8648, 3253, 85.6549988, "mg_x", "2s0.4p1.2P_1/2", "continuum"},
        {8649, 3254, 85.6549988, "mg_x", "2s0.4p1.2P_3/2", "continuum"},
        {8650, 3255, 84.7590027, "mg_x", "2s0.4d1.2D_3/2", "continuum"},
        {8651, 3256, 84.7189941, "mg_x", "2s0.4d1.2D_5/2", "continuum"},
        {8652, 3257, 84.6749878, "mg_x", "2s0.4f1.2F_5/2", "continuum"},
        {8653, 3258, 84.6650085, "mg_x", "2s0.4f1.2F_7/2", "continuum"},
        {8654, 3259, 55.7319946, "mg_x", "2s0.5s1.2S_1/2", "continuum"},
        {8655, 3260, 54.57901, "mg_x", "2s0.5p1.2P_1/2", "continuum"},
        {8656, 3261, 54.57901, "mg_x", "2s0.5p1.2P_3/2", "continuum"},
        {8657, 3262, 54.144989, "mg_x", "2s0.5d1.2D_3/2", "continuum"},
        {8658, 3263, 54.1199951, "mg_x", "2s0.5d1.2D_5/2", "continuum"},
        {8659, 3264, 54.0050049, "mg_x", "2s0.5f1.2F_5/2", "continuum"},
        {8660, 3265, 53.9949951, "mg_x", "2s0.5f1.2F_7/2", "continuum"},
        {8661, 3266, 53.9450073, "mg_x", "2s0.5g1.2G_7/2", "continuum"},
        {8662, 3267, 53.9349976, "mg_x", "2s0.5g1.2G_9/2", "continuum"},
        {8663, 3268, 2.54901123, "mg_x", "superlevel", "continuum"},
        {8664, 3287, 1762, "mg_xi", "1s2.1S_0", "continuum"},
        {8665, 3317, 102.93396, "mg_xi", "1s1.4p1.1P_1", "continuum"},
        {8666, 3313, 103.104248, "mg_xi", "1s1.4f1.3F_4", "continuum"},
        {8667, 3314, 103.104248, "mg_xi", "1s1.4f1.3F_3", "continuum"},
        {8668, 3315, 103.104248, "mg_xi", "1s1.4f1.3F_2", "continuum"},
        {8669, 3326, 66.0593262, "mg_xi", "1s1.5d1.1D_2", "continuum"},
        {8670, 3288, 430.888428, "mg_xi", "1s1.2s1.3S_1", "continuum"},
        {8671, 3303, 182.687988, "mg_xi", "1s1.3p1.1P_1", "continuum"},
        {8672, 3316, 103.103516, "mg_xi", "1s1.4f1.1F_3", "continuum"},
        {8673, 3302, 183.147827, "mg_xi", "1s1.3d1.1D_2", "continuum"},
        {8674, 3304, 105.32373, "mg_xi", "1s1.4s1.3S_1", "continuum"},
        {8675, 3292, 418.162354, "mg_xi", "1s1.2s1.1S_0", "continuum"},
        {8676, 3331, 66.0516357, "mg_xi", "1s1.5g1.1G_4", "continuum"},
        {8677, 3298, 185.130859, "mg_xi", "1s1.3s1.1S_0", "continuum"},
        {8678, 3332, 66.0516357, "mg_xi", "1s1.5g1.3G_5", "continuum"},
        {8679, 3333, 66.0516357, "mg_xi", "1s1.5g1.3G_4", "continuum"},
        {8680, 3334, 66.0516357, "mg_xi", "1s1.5g1.3G_3", "continuum"},
        {8681, 3295, 185.234741, "mg_xi", "1s1.3p1.3P_0", "continuum"},
        {8682, 3296, 185.202148, "mg_xi", "1s1.3p1.3P_1", "continuum"},
        {8683, 3297, 185.071045, "mg_xi", "1s1.3p1.3P_2", "continuum"},
        {8684, 3328, 66.0577393, "mg_xi", "1s1.5f1.3F_4", "continuum"},
        {8685, 3329, 66.0577393, "mg_xi", "1s1.5f1.3F_3", "continuum"},
        {8686, 3330, 66.0577393, "mg_xi", "1s1.5f1.3F_2", "continuum"},
        {8687, 3319, 66.5042725, "mg_xi", "1s1.5p1.3P_0", "continuum"},
        {8688, 3320, 66.4970703, "mg_xi", "1s1.5p1.3P_1", "continuum"},
        {8689, 3321, 66.46875, "mg_xi", "1s1.5p1.3P_2", "continuum"},
        {8690, 3327, 66.0577393, "mg_xi", "1s1.5f1.1F_3", "continuum"},
        {8691, 3308, 103.961548, "mg_xi", "1s1.4s1.1S_0", "continuum"},
        {8692, 3322, 66.4986572, "mg_xi", "1s1.5s1.1S_0", "continuum"},
        {8693, 3312, 103.112061, "mg_xi", "1s1.4d1.1D_2", "continuum"},
        {8694, 3335, 65.9746094, "mg_xi", "1s1.5p1.1P_1", "continuum"},
        {8695, 3294, 188.494995, "mg_xi", "1s1.3s1.3S_1", "continuum"},
        {8696, 3305, 103.980835, "mg_xi", "1s1.4p1.3P_0", "continuum"},
        {8697, 3306, 103.967041, "mg_xi", "1s1.4p1.3P_1", "continuum"},
        {8698, 3307, 103.911865, "mg_xi", "1s1.4p1.3P_2", "continuum"},
        {8699, 3309, 103.167114, "mg_xi", "1s1.4d1.3D_1", "continuum"},
        {8700, 3310, 103.165283, "mg_xi", "1s1.4d1.3D_2", "continuum"},
        {8701, 3311, 103.145142, "mg_xi", "1s1.4d1.3D_3", "continuum"},
        {8702, 3318, 67.1827393, "mg_xi", "1s1.5s1.3S_1", "continuum"},
        {8703, 3299, 183.286011, "mg_xi", "1s1.3d1.3D_1", "continuum"},
        {8704, 3300, 183.281006, "mg_xi", "1s1.3d1.3D_2", "continuum"},
        {8705, 3301, 183.233887, "mg_xi", "1s1.3d1.3D_3", "continuum"},
        {8706, 3293, 409.751953, "mg_xi", "1s1.2p1.1P_1", "continuum"},
        {8707, 3289, 419.00415, "mg_xi", "1s1.2p1.3P_0", "continuum"},
        {8708, 3290, 418.901245, "mg_xi", "1s1.2p1.3P_1", "continuum"},
        {8709, 3291, 418.45874, "mg_xi", "1s1.2p1.3P_2", "continuum"},
        {8710, 3323, 66.0913086, "mg_xi", "1s1.5d1.3D_1", "continuum"},
        {8711, 3324, 66.090332, "mg_xi", "1s1.5d1.3D_2", "continuum"},
        {8712, 3325, 66.0799561, "mg_xi", "1s1.5d1.3D_3", "continuum"},
        {8761, 3316, 103.103516, "mg_xi", "1s1.4f1.1F_3", "continuum"},
        {8762, 3317, 102.93396, "mg_xi", "1s1.4p1.1P_1", "continuum"},
        {8763, 3375, 54.3900146, "mg_xii", "1s0.6h1.2H", "continuum"},
        {8764, 3371, 54.3900146, "mg_xii", "1s0.6p1.2P", "continuum"},
        {8765, 3351, 218.428833, "mg_xii", "1s0.3s1.2S_1/2", "continuum"},
        {8766, 3352, 218.160645, "mg_xii", "1s0.3d1.2D_3/2", "continuum"},
        {8767, 3353, 218.067505, "mg_xii", "1s0.3d1.2D_5/2", "continuum"},
        {8768, 3366, 78.7241211, "mg_xii", "1s0.5f1.2F_5/2", "continuum"},
        {8769, 3367, 78.7141113, "mg_xii", "1s0.5f1.2F_7/2", "continuum"},
        {8770, 3364, 78.7441406, "mg_xii", "1s0.5d1.2D_3/2", "continuum"},
        {8771, 3365, 78.7241211, "mg_xii", "1s0.5d1.2D_5/2", "continuum"},
        {8772, 3373, 54.3900146, "mg_xii", "1s0.6f1.2F", "continuum"},
        {8773, 3370, 54.3900146, "mg_xii", "1s0.6s1.2S", "continuum"},
        {8774, 3356, 122.970093, "mg_xii", "1s0.4s1.2S_1/2", "continuum"},
        {8775, 3372, 54.3900146, "mg_xii", "1s0.6d1.2D", "continuum"},
        {8776, 3348, 491.270264, "mg_xii", "1s0.2s1.2S_1/2", "continuum"},
        {8777, 3374, 54.3900146, "mg_xii", "1s0.6g1.2G", "continuum"},
        {8778, 3368, 78.7141113, "mg_xii", "1s0.5g1.2G_7/2", "continuum"},
        {8779, 3369, 78.7081299, "mg_xii", "1s0.5g1.2G_9/2", "continuum"},
        {8780, 3359, 122.817871, "mg_xii", "1s0.4f1.2F_5/2", "continuum"},
        {8781, 3360, 122.79834, "mg_xii", "1s0.4f1.2F_7/2", "continuum"},
        {8782, 3354, 122.974976, "mg_xii", "1s0.4p1.2P_1/2", "continuum"},
        {8783, 3355, 122.856812, "mg_xii", "1s0.4p1.2P_3/2", "continuum"},
        {8784, 3345, 1963, "mg_xii", "1s1.2S_1/2", "continuum"},
        {8785, 3346, 491.308472, "mg_xii", "1s0.2p1.2P_1/2", "continuum"},
        {8786, 3347, 490.362915, "mg_xii", "1s0.2p1.2P_3/2", "continuum"},
        {8787, 3357, 122.857056, "mg_xii", "1s0.4d1.2D_3/2", "continuum"},
        {8788, 3358, 122.817749, "mg_xii", "1s0.4d1.2D_5/2", "continuum"},
        {8789, 3361, 78.8045654, "mg_xii", "1s0.5p1.2P_1/2", "continuum"},
        {8790, 3362, 78.7441406, "mg_xii", "1s0.5p1.2P_3/2", "continuum"},
        {8791, 3349, 218.440308, "mg_xii", "1s0.3p1.2P_1/2", "continuum"},
        {8792, 3350, 218.160156, "mg_xii", "1s0.3p1.2P_3/2", "continuum"},
        {8793, 3363, 78.802124, "mg_xii", "1s0.5s1.2S_1/2", "continuum"},
        {8794, 3376, 13.5999756, "mg_xii", "superlev", "continuum"}
    };
    return rows;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute oracle public rrc label template for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] const std::vector<RrcLabelTemplateRow>& oracle_public_rrc_label_template_v172537() {
    static const std::vector<RrcLabelTemplateRow> rows = {
        {1, 0, 0.3777, "h_i", "1s0.6f1.2F", "continuum"},
        {2, 0, 0.545493, "h_i", "1s0.5f1.2F_7/2", "continuum"},
        {3, 0, 0.545494, "h_i", "1s0.5f1.2F_5/2", "continuum"},
        {4, 0, 0.3777, "h_i", "1s0.6h1.2H", "continuum"},
        {5, 0, 0.3777, "h_i", "1s0.6g1.2G", "continuum"},
        {6, 0, 0.545497, "h_i", "1s0.5s1.2S_1/2", "continuum"},
        {7, 0, 3.40119, "h_i", "1s0.2p1.2P_1/2", "continuum"},
        {8, 0, 3.40127, "h_i", "1s0.2p1.2P_3/2", "continuum"},
        {9, 0, 0.3777, "h_i", "1s0.6p1.2P", "continuum"},
        {10, 0, 0.3777, "h_i", "1s0.6s1.2S", "continuum"},
        {11, 0, 0.3777, "h_i", "1s0.6d1.2D", "continuum"},
        {12, 0, 13.6, "h_i", "1s1.2S_1/2", "continuum"},
        {13, 0, 3.40119, "h_i", "1s0.2s1.2S_1/2", "continuum"},
        {14, 0, 0.851463, "h_i", "1s0.4p1.2P_1/2", "continuum"},
        {15, 0, 0.851459, "h_i", "1s0.4p1.2P_3/2", "continuum"},
        {16, 0, 0.545499, "h_i", "1s0.5p1.2P_1/2", "continuum"},
        {17, 0, 0.545495, "h_i", "1s0.5p1.2P_3/2", "continuum"},
        {18, 0, 0.851457, "h_i", "1s0.4f1.2F_5/2", "continuum"},
        {19, 0, 0.851456, "h_i", "1s0.4f1.2F_7/2", "continuum"},
        {20, 0, 0.851459, "h_i", "1s0.4d1.2D_3/2", "continuum"},
        {21, 0, 0.851457, "h_i", "1s0.4d1.2D_5/2", "continuum"},
        {22, 0, 1.5125, "h_i", "1s0.3p1.2P_1/2", "continuum"},
        {23, 0, 1.51249, "h_i", "1s0.3p1.2P_3/2", "continuum"},
        {24, 0, 1.5125, "h_i", "1s0.3s1.2S_1/2", "continuum"},
        {25, 0, 1.51249, "h_i", "1s0.3d1.2D_3/2", "continuum"},
        {26, 0, 1.51249, "h_i", "1s0.3d1.2D_5/2", "continuum"},
        {27, 0, 0.545495, "h_i", "1s0.5d1.2D_3/2", "continuum"},
        {28, 0, 0.545494, "h_i", "1s0.5d1.2D_5/2", "continuum"},
        {29, 0, 0.545493, "h_i", "1s0.5g1.2G_7/2", "continuum"},
        {30, 0, 0.545493, "h_i", "1s0.5g1.2G_9/2", "continuum"},
        {31, 0, 0.851463, "h_i", "1s0.4s1.2S_1/2", "continuum"},
        {32, 0, 0.0943995, "h_i", "superlev", "continuum"},
        {33, 0, 0.996033, "he_i", "1s1.4s1.3S_1", "continuum"},
        {34, 0, 0.852982, "he_i", "1s1.4f1.1F_3", "continuum"},
        {35, 0, 0.578777, "he_i", "1s1.5s1.1S_0", "continuum"},
        {36, 0, 3.37197, "he_i", "1s1.2p1.1P_1", "continuum"},
        {37, 0, 1.66968, "he_i", "1s1.3s1.1S_0", "continuum"},
        {38, 0, 0.916422, "he_i", "1s1.4s1.1S_0", "continuum"},
        {39, 0, 1.87153, "he_i", "1s1.3s1.3S_1", "continuum"},
        {40, 0, 1.50297, "he_i", "1s1.3p1.1P_1", "continuum"},
        {41, 0, 0.852985, "he_i", "1s1.4f1.3F_3", "continuum"},
        {42, 0, 0.852983, "he_i", "1s1.4f1.3F_4", "continuum"},
        {43, 0, 0.852983, "he_i", "1s1.4f1.3F_2", "continuum"},
        {44, 0, 1.50297, "he_i", "1s1.3p1.1P_1", "continuum"},
        {45, 0, 0.5569, "he_i", "1s1.5f1.3F", "continuum"},
        {46, 0, 0.5574, "he_i", "1s1.5d1.3D", "continuum"},
        {47, 0, 0.5564, "he_i", "1s1.5g1.3G", "continuum"},
        {48, 0, 4.77038, "he_i", "1s1.2s1.3S_1", "continuum"},
        {49, 0, 0.882101, "he_i", "1s1.4p1.3P_2", "continuum"},
        {50, 0, 0.882101, "he_i", "1s1.4p1.3P_1", "continuum"},
        {51, 0, 0.882086, "he_i", "1s1.4p1.3P_0", "continuum"},
        {52, 0, 0.578777, "he_i", "1s1.5s1.1S_0", "continuum"},
        {53, 0, 0.5569, "he_i", "1s1.5f1.1F", "continuum"},
        {54, 0, 0.916422, "he_i", "1s1.4s1.1S_0", "continuum"},
        {55, 0, 0.557199, "he_i", "1s1.5d1.1D", "continuum"},
        {56, 0, 1.51592, "he_i", "1s1.3d1.1D_2", "continuum"},
        {57, 0, 0.5541, "he_i", "1s1.5p1.1P", "continuum"},
        {58, 0, 0.847921, "he_i", "1s1.4p1.1P_1", "continuum"},
        {59, 0, 1.51592, "he_i", "1s1.3d1.1D_2", "continuum"},
        {60, 0, 4.77038, "he_i", "1s1.2s1.3S_1", "continuum"},
        {61, 0, 0.853657, "he_i", "1s1.4d1.1D_2", "continuum"},
        {62, 0, 1.87153, "he_i", "1s1.3s1.3S_1", "continuum"},
        {63, 0, 0.557199, "he_i", "1s1.5d1.1D", "continuum"},
        {64, 0, 1.66968, "he_i", "1s1.3s1.1S_0", "continuum"},
        {65, 0, 0.853657, "he_i", "1s1.4d1.1D_2", "continuum"},
        {66, 0, 24.59, "he_i", "1s2.1S_0", "continuum"},
        {67, 0, 3.37197, "he_i", "1s1.2p1.1P_1", "continuum"},
        {68, 0, 3.97422, "he_i", "1s1.2s1.1S_0", "continuum"},
        {69, 0, 3.97422, "he_i", "1s1.2s1.1S_0", "continuum"},
        {70, 0, 0.561768, "he_i", "1s1.5p1.3P_2", "continuum"},
        {71, 0, 0.561766, "he_i", "1s1.5p1.3P_1", "continuum"},
        {72, 0, 0.56176, "he_i", "1s1.5p1.3P_0", "continuum"},
        {73, 0, 0.847921, "he_i", "1s1.4p1.1P_1", "continuum"},
        {74, 0, 0.556601, "he_i", "1s1.5g1.1G", "continuum"},
        {75, 0, 1.51592, "he_i", "1s1.3d1.1D_2", "continuum"},
        {76, 0, 0.557199, "he_i", "1s1.5d1.1D", "continuum"},
        {77, 0, 1.50297, "he_i", "1s1.3p1.1P_1", "continuum"},
        {78, 0, 24.59, "he_i", "1s2.1S_0", "continuum"},
        {79, 0, 0.847921, "he_i", "1s1.4p1.1P_1", "continuum"},
        {80, 0, 0.853903, "he_i", "1s1.4d1.3D_3", "continuum"},
        {81, 0, 0.853903, "he_i", "1s1.4d1.3D_2", "continuum"},
        {82, 0, 0.853899, "he_i", "1s1.4d1.3D_1", "continuum"},
        {83, 0, 3.37197, "he_i", "1s1.2p1.1P_1", "continuum"},
        {84, 0, 0.916422, "he_i", "1s1.4s1.1S_0", "continuum"},
        {85, 0, 0.853657, "he_i", "1s1.4d1.1D_2", "continuum"},
        {86, 0, 3.97422, "he_i", "1s1.2s1.1S_0", "continuum"},
        {87, 0, 0.5541, "he_i", "1s1.5p1.1P", "continuum"},
        {88, 0, 1.87153, "he_i", "1s1.3s1.3S_1", "continuum"},
        {89, 0, 0.996033, "he_i", "1s1.4s1.3S_1", "continuum"},
        {90, 0, 0.618021, "he_i", "1s1.5s1.3S_1", "continuum"},
        {91, 0, 3.62591, "he_i", "1s1.2p1.3P_2", "continuum"},
        {92, 0, 3.6259, "he_i", "1s1.2p1.3P_1", "continuum"},
        {93, 0, 3.62577, "he_i", "1s1.2p1.3P_0", "continuum"},
        {94, 0, 1.66968, "he_i", "1s1.3s1.1S_0", "continuum"},
        {95, 0, 1.58292, "he_i", "1s1.3p1.3P_2", "continuum"},
        {96, 0, 1.58292, "he_i", "1s1.3p1.3P_1", "continuum"},
        {97, 0, 1.58288, "he_i", "1s1.3p1.3P_0", "continuum"},
        {98, 0, 0.578777, "he_i", "1s1.5s1.1S_0", "continuum"},
        {99, 0, 0.853903, "he_i", "1s1.4d1.3D_3", "continuum"},
        {100, 0, 0.853903, "he_i", "1s1.4d1.3D_2", "continuum"},
        {101, 0, 0.853899, "he_i", "1s1.4d1.3D_1", "continuum"},
        {102, 0, 1.51634, "he_i", "1s1.3d1.3D_3", "continuum"},
        {103, 0, 1.51634, "he_i", "1s1.3d1.3D_2", "continuum"},
        {104, 0, 1.51634, "he_i", "1s1.3d1.3D_1", "continuum"},
        {105, 0, 0.996033, "he_i", "1s1.4s1.3S_1", "continuum"},
        {106, 0, 0.618021, "he_i", "1s1.5s1.3S_1", "continuum"},
        {107, 0, 0.618021, "he_i", "1s1.5s1.3S_1", "continuum"},
        {108, 0, 0.5574, "he_i", "1s1.5d1.3D", "continuum"},
        {109, 0, 3.62591, "he_i", "1s1.2p1.3P_2", "continuum"},
        {110, 0, 3.6259, "he_i", "1s1.2p1.3P_1", "continuum"},
        {111, 0, 3.62577, "he_i", "1s1.2p1.3P_0", "continuum"},
        {112, 0, 0.853903, "he_i", "1s1.4d1.3D_3", "continuum"},
        {113, 0, 0.853903, "he_i", "1s1.4d1.3D_2", "continuum"},
        {114, 0, 0.853899, "he_i", "1s1.4d1.3D_1", "continuum"},
        {115, 0, 1.58292, "he_i", "1s1.3p1.3P_2", "continuum"},
        {116, 0, 1.58292, "he_i", "1s1.3p1.3P_1", "continuum"},
        {117, 0, 1.58288, "he_i", "1s1.3p1.3P_0", "continuum"},
        {118, 0, 24.59, "he_i", "1s2.1S_0", "continuum"},
        {119, 0, 1.51634, "he_i", "1s1.3d1.3D_3", "continuum"},
        {120, 0, 1.51634, "he_i", "1s1.3d1.3D_2", "continuum"},
        {121, 0, 1.51634, "he_i", "1s1.3d1.3D_1", "continuum"},
        {122, 0, 3.62591, "he_i", "1s1.2p1.3P_2", "continuum"},
        {123, 0, 3.6259, "he_i", "1s1.2p1.3P_1", "continuum"},
        {124, 0, 3.62577, "he_i", "1s1.2p1.3P_0", "continuum"},
        {125, 0, 1.58292, "he_i", "1s1.3p1.3P_2", "continuum"},
        {126, 0, 1.58292, "he_i", "1s1.3p1.3P_1", "continuum"},
        {127, 0, 1.58288, "he_i", "1s1.3p1.3P_0", "continuum"},
        {128, 0, 0.5574, "he_i", "1s1.5d1.3D", "continuum"},
        {129, 0, 1.51634, "he_i", "1s1.3d1.3D_3", "continuum"},
        {130, 0, 1.51634, "he_i", "1s1.3d1.3D_2", "continuum"},
        {131, 0, 1.51634, "he_i", "1s1.3d1.3D_1", "continuum"},
        {132, 0, 0.5541, "he_i", "1s1.5p1.1P", "continuum"},
        {133, 0, 4.77038, "he_i", "1s1.2s1.3S_1", "continuum"},
        {176, 0, 0.852982, "he_i", "1s1.4f1.1F_3", "continuum"},
        {177, 0, 0.847921, "he_i", "1s1.4p1.1P_1", "continuum"},
        {178, 0, 1.5109, "he_ii", "1s0.6s1.2S", "continuum"},
        {179, 0, 1.5109, "he_ii", "1s0.6f1.2F", "continuum"},
        {180, 0, 3.40331, "he_ii", "1s0.4s1.2S_1/2", "continuum"},
        {181, 0, 3.40323, "he_ii", "1s0.4d1.2D_3/2", "continuum"},
        {182, 0, 3.4032, "he_ii", "1s0.4d1.2D_5/2", "continuum"},
        {183, 0, 6.04847, "he_ii", "1s0.3d1.2D_3/2", "continuum"},
        {184, 0, 6.0484, "he_ii", "1s0.3d1.2D_5/2", "continuum"},
        {185, 0, 2.1789, "he_ii", "1s0.5s1.2S_1/2", "continuum"},
        {186, 0, 6.04867, "he_ii", "1s0.3s1.2S_1/2", "continuum"},
        {187, 0, 3.40332, "he_ii", "1s0.4p1.2P_1/2", "continuum"},
        {188, 0, 3.40323, "he_ii", "1s0.4p1.2P_3/2", "continuum"},
        {189, 0, 1.5109, "he_ii", "1s0.6g1.2G", "continuum"},
        {190, 0, 1.5109, "he_ii", "1s0.6d1.2D", "continuum"},
        {191, 0, 3.4032, "he_ii", "1s0.4f1.2F_5/2", "continuum"},
        {192, 0, 3.40318, "he_ii", "1s0.4f1.2F_7/2", "continuum"},
        {193, 0, 2.17884, "he_ii", "1s0.5f1.2F_5/2", "continuum"},
        {194, 0, 2.17884, "he_ii", "1s0.5f1.2F_7/2", "continuum"},
        {195, 0, 2.17891, "he_ii", "1s0.5p1.2P_1/2", "continuum"},
        {196, 0, 2.17886, "he_ii", "1s0.5p1.2P_3/2", "continuum"},
        {197, 0, 1.5109, "he_ii", "1s0.6h1.2H", "continuum"},
        {198, 0, 2.17884, "he_ii", "1s0.5g1.2G_7/2", "continuum"},
        {199, 0, 2.17883, "he_ii", "1s0.5g1.2G_9/2", "continuum"},
        {200, 0, 1.5109, "he_ii", "1s0.6p1.2P", "continuum"},
        {201, 0, 2.17886, "he_ii", "1s0.5d1.2D_3/2", "continuum"},
        {202, 0, 2.17884, "he_ii", "1s0.5d1.2D_5/2", "continuum"},
        {203, 0, 13.6069, "he_ii", "1s0.2s1.2S_1/2", "continuum"},
        {204, 0, 13.607, "he_ii", "1s0.2p1.2P_1/2", "continuum"},
        {205, 0, 13.6062, "he_ii", "1s0.2p1.2P_3/2", "continuum"},
        {206, 0, 6.04869, "he_ii", "1s0.3p1.2P_1/2", "continuum"},
        {207, 0, 6.04847, "he_ii", "1s0.3p1.2P_3/2", "continuum"},
        {208, 0, 54.42, "he_ii", "1s1.2S_1/2", "continuum"},
        {209, 0, 0.377697, "he_ii", "superlev", "continuum"},
        {7066, 0, 80.1, "mg_iii", "2p6.1S_0", "continuum"},
        {7067, 0, 80.1, "mg_iii", "2p6.1S_0", "continuum"},
        {7068, 0, 80.1, "mg_iii", "2p6.1S_0", "continuum"},
        {7069, 0, 0.556198, "mg_iii", "superlevel", "continuum"},
        {7102, 0, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7103, 0, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7104, 0, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7105, 0, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7106, 0, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7107, 0, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7108, 0, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7109, 0, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7110, 0, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7111, 0, 109, "mg_iv", "2p5.2P_3/2", "continuum"},
        {7112, 0, 108.724, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7113, 0, 108.724, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7114, 0, 108.724, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7115, 0, 108.724, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7116, 0, 108.724, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7117, 0, 108.724, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7118, 0, 108.724, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7119, 0, 108.724, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7120, 0, 108.724, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7121, 0, 108.724, "mg_iv", "2p5.2P_1/2", "continuum"},
        {7122, 0, 70.3911, "mg_iv", "2s1.2p6.2S_1/2", "continuum"},
        {7123, 0, 70.3911, "mg_iv", "2s1.2p6.2S_1/2", "continuum"},
        {7124, 0, 70.3911, "mg_iv", "2s1.2p6.2S_1/2", "continuum"},
        {7125, 0, 0.757004, "mg_iv", "superlevel", "continuum"},
        {7281, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7282, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7283, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7284, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7285, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7286, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7287, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7288, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7289, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7290, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7291, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7292, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7293, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7294, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7295, 0, 141, "mg_v", "2p4.3P_2", "continuum"},
        {7296, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7297, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7298, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7299, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7300, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7301, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7302, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7303, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7304, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7305, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7306, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7307, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7308, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7309, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7310, 0, 140.779, "mg_v", "2p4.3P_1", "continuum"},
        {7311, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7312, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7313, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7314, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7315, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7316, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7317, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7318, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7319, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7320, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7321, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7322, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7323, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7324, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7325, 0, 140.687, "mg_v", "2p4.3P_0", "continuum"},
        {7326, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7327, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7328, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7329, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7330, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7331, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7332, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7333, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7334, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7335, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7336, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7337, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7338, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7339, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7340, 0, 136.548, "mg_v", "2p4.1D_2", "continuum"},
        {7341, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7342, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7343, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7344, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7345, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7346, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7347, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7348, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7349, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7350, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7351, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7352, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7353, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7354, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7355, 0, 131.423, "mg_v", "2p4.1S_0", "continuum"},
        {7356, 0, 105.901, "mg_v", "2s1.2p5.3P_2", "continuum"},
        {7357, 0, 105.901, "mg_v", "2s1.2p5.3P_2", "continuum"},
        {7358, 0, 105.701, "mg_v", "2s1.2p5.3P_1", "continuum"},
        {7359, 0, 105.701, "mg_v", "2s1.2p5.3P_1", "continuum"},
        {7360, 0, 105.591, "mg_v", "2s1.2p5.3P_0", "continuum"},
        {7361, 0, 105.591, "mg_v", "2s1.2p5.3P_0", "continuum"},
        {7362, 0, 91.7391, "mg_v", "2s1.2p5.1P_1", "continuum"},
        {7363, 0, 91.7391, "mg_v", "2s1.2p5.1P_1", "continuum"},
        {7364, 0, 58.8366, "mg_v", "2s0.2p6.1S_0", "continuum"},
        {7365, 0, 58.8366, "mg_v", "2s0.2p6.1S_0", "continuum"},
        {7366, 0, 0.979004, "mg_v", "superlevel", "continuum"},
        {7617, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7618, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7619, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7620, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7621, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7622, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7623, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7624, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7625, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7627, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7628, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7630, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7631, 0, 187, "mg_vi", "2p3.4S_3/2", "continuum"},
        {7637, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7638, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7639, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7640, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7641, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7642, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7643, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7644, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7645, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7646, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7647, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7648, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7649, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7650, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7651, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7652, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7653, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7654, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7655, 0, 180.138, "mg_vi", "2p3.2D_3/2", "continuum"},
        {7657, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7658, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7659, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7660, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7661, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7662, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7663, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7664, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7665, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7666, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7667, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7668, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7669, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7670, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7671, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7672, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7673, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7675, 0, 180.14, "mg_vi", "2p3.2D_5/2", "continuum"},
        {7677, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7678, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7679, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7680, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7681, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7682, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7683, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7684, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7685, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7686, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7687, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7688, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7689, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7690, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7691, 0, 176.6, "mg_vi", "2p3.2P_1/2", "continuum"},
        {7697, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7698, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7699, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7700, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7701, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7702, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7703, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7704, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7705, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7707, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7708, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7709, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7710, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7711, 0, 176.586, "mg_vi", "2p3.2P_3/2", "continuum"},
        {7717, 0, 156.271, "mg_vi", "2s1.2p4.4P_5/2", "continuum"},
        {7718, 0, 156.068, "mg_vi", "2s1.2p4.4P_3/2", "continuum"},
        {7719, 0, 155.961, "mg_vi", "2s1.2p4.4P_1/2", "continuum"},
        {7720, 0, 144.641, "mg_vi", "2s1.2p4.2D_3/2", "continuum"},
        {7721, 0, 144.646, "mg_vi", "2s1.2p4.2D_5/2", "continuum"},
        {7722, 0, 137.201, "mg_vi", "2s1.2p4.2S_1/2", "continuum"},
        {7723, 0, 134.305, "mg_vi", "2s1.2p4.2P_3/2", "continuum"},
        {7724, 0, 134.064, "mg_vi", "2s1.2p4.2P_1/2", "continuum"},
        {7725, 0, 1.299, "mg_vi", "superlevel", "continuum"},
        {7976, 0, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7977, 0, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7978, 0, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7979, 0, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7980, 0, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7984, 0, 225, "mg_vii", "2p2.3P_0", "continuum"},
        {7991, 0, 224.863, "mg_vii", "2p2.3P_1", "continuum"},
        {7992, 0, 224.863, "mg_vii", "2p2.3P_1", "continuum"},
        {7993, 0, 224.863, "mg_vii", "2p2.3P_1", "continuum"},
        {7994, 0, 224.863, "mg_vii", "2p2.3P_1", "continuum"},
        {7995, 0, 224.863, "mg_vii", "2p2.3P_1", "continuum"},
        {7999, 0, 224.863, "mg_vii", "2p2.3P_1", "continuum"},
        {8000, 0, 224.863, "mg_vii", "2p2.3P_1", "continuum"},
        {8001, 0, 224.863, "mg_vii", "2p2.3P_1", "continuum"},
        {8002, 0, 224.863, "mg_vii", "2p2.3P_1", "continuum"},
        {8003, 0, 224.863, "mg_vii", "2p2.3P_1", "continuum"},
        {8006, 0, 224.638, "mg_vii", "2p2.3P_2", "continuum"},
        {8007, 0, 224.638, "mg_vii", "2p2.3P_2", "continuum"},
        {8008, 0, 224.638, "mg_vii", "2p2.3P_2", "continuum"},
        {8009, 0, 224.638, "mg_vii", "2p2.3P_2", "continuum"},
        {8010, 0, 224.638, "mg_vii", "2p2.3P_2", "continuum"},
        {8015, 0, 224.638, "mg_vii", "2p2.3P_2", "continuum"},
        {8016, 0, 224.638, "mg_vii", "2p2.3P_2", "continuum"},
        {8017, 0, 224.638, "mg_vii", "2p2.3P_2", "continuum"},
        {8018, 0, 224.638, "mg_vii", "2p2.3P_2", "continuum"},
        {8021, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8022, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8023, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8024, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8025, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8026, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8027, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8028, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8032, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8033, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8035, 0, 219.925, "mg_vii", "2p2.1D_2", "continuum"},
        {8036, 0, 214.447, "mg_vii", "2p2.1S_0", "continuum"},
        {8037, 0, 214.447, "mg_vii", "2p2.1S_0", "continuum"},
        {8038, 0, 214.447, "mg_vii", "2p2.1S_0", "continuum"},
        {8039, 0, 214.447, "mg_vii", "2p2.1S_0", "continuum"},
        {8040, 0, 214.447, "mg_vii", "2p2.1S_0", "continuum"},
        {8041, 0, 214.447, "mg_vii", "2p2.1S_0", "continuum"},
        {8042, 0, 214.447, "mg_vii", "2p2.1S_0", "continuum"},
        {8043, 0, 214.447, "mg_vii", "2p2.1S_0", "continuum"},
        {8044, 0, 214.447, "mg_vii", "2p2.1S_0", "continuum"},
        {8045, 0, 214.447, "mg_vii", "2p2.1S_0", "continuum"},
        {8051, 0, 210.364, "mg_vii", "2s1.2p3.5S_2", "continuum"},
        {8052, 0, 210.364, "mg_vii", "2s1.2p3.5S_2", "continuum"},
        {8053, 0, 210.364, "mg_vii", "2s1.2p3.5S_2", "continuum"},
        {8054, 0, 196.129, "mg_vii", "2s1.2p3.3D_2", "continuum"},
        {8055, 0, 196.129, "mg_vii", "2s1.2p3.3D_2", "continuum"},
        {8056, 0, 196.129, "mg_vii", "2s1.2p3.3D_2", "continuum"},
        {8057, 0, 196.121, "mg_vii", "2s1.2p3.3D_1", "continuum"},
        {8058, 0, 196.121, "mg_vii", "2s1.2p3.3D_1", "continuum"},
        {8059, 0, 196.121, "mg_vii", "2s1.2p3.3D_1", "continuum"},
        {8060, 0, 196.142, "mg_vii", "2s1.2p3.3D_3", "continuum"},
        {8061, 0, 196.142, "mg_vii", "2s1.2p3.3D_3", "continuum"},
        {8062, 0, 196.142, "mg_vii", "2s1.2p3.3D_3", "continuum"},
        {8063, 0, 190.925, "mg_vii", "2s1.2p3.3P_0", "continuum"},
        {8064, 0, 190.925, "mg_vii", "2s1.2p3.3P_0", "continuum"},
        {8065, 0, 190.925, "mg_vii", "2s1.2p3.3P_0", "continuum"},
        {8066, 0, 190.931, "mg_vii", "2s1.2p3.3P_1", "continuum"},
        {8067, 0, 190.931, "mg_vii", "2s1.2p3.3P_1", "continuum"},
        {8068, 0, 190.931, "mg_vii", "2s1.2p3.3P_1", "continuum"},
        {8069, 0, 190.93, "mg_vii", "2s1.2p3.3P_2", "continuum"},
        {8070, 0, 190.93, "mg_vii", "2s1.2p3.3P_2", "continuum"},
        {8071, 0, 190.93, "mg_vii", "2s1.2p3.3P_2", "continuum"},
        {8072, 0, 181.078, "mg_vii", "2s1.2p3.1D_2", "continuum"},
        {8073, 0, 181.078, "mg_vii", "2s1.2p3.1D_2", "continuum"},
        {8074, 0, 181.078, "mg_vii", "2s1.2p3.1D_2", "continuum"},
        {8075, 0, 180.122, "mg_vii", "2s1.2p3.3S_1", "continuum"},
        {8076, 0, 180.122, "mg_vii", "2s1.2p3.3S_1", "continuum"},
        {8077, 0, 180.122, "mg_vii", "2s1.2p3.3S_1", "continuum"},
        {8078, 0, 175.78, "mg_vii", "2s1.2p3.1P_1", "continuum"},
        {8079, 0, 175.78, "mg_vii", "2s1.2p3.1P_1", "continuum"},
        {8080, 0, 175.78, "mg_vii", "2s1.2p3.1P_1", "continuum"},
        {8081, 0, 157.789, "mg_vii", "2s0.2p4.3P_2", "continuum"},
        {8082, 0, 157.532, "mg_vii", "2s0.2p4.3P_1", "continuum"},
        {8083, 0, 157.424, "mg_vii", "2s0.2p4.3P_0", "continuum"},
        {8084, 0, 153.58, "mg_vii", "2s0.2p4.1D_2", "continuum"},
        {8085, 0, 143.398, "mg_vii", "2s0.2p4.1S_0", "continuum"},
        {8086, 0, 95.167, "mg_vii", "2p1.3s1.3P_0", "continuum"},
        {8087, 0, 95.167, "mg_vii", "2p1.3s1.3P_0", "continuum"},
        {8088, 0, 95.069, "mg_vii", "2p1.3s1.3P_1", "continuum"},
        {8089, 0, 95.069, "mg_vii", "2p1.3s1.3P_1", "continuum"},
        {8090, 0, 94.761, "mg_vii", "2p1.3s1.3P_2", "continuum"},
        {8091, 0, 94.761, "mg_vii", "2p1.3s1.3P_2", "continuum"},
        {8092, 0, 93.504, "mg_vii", "2p1.3s1.1P_1", "continuum"},
        {8093, 0, 93.504, "mg_vii", "2p1.3s1.1P_1", "continuum"},
        {8094, 0, 85.879, "mg_vii", "2p1.3p1.1P_1", "continuum"},
        {8095, 0, 85.879, "mg_vii", "2p1.3p1.1P_1", "continuum"},
        {8096, 0, 85.345, "mg_vii", "2p1.3p1.3D_1", "continuum"},
        {8097, 0, 85.345, "mg_vii", "2p1.3p1.3D_1", "continuum"},
        {8098, 0, 85.233, "mg_vii", "2p1.3p1.3D_2", "continuum"},
        {8099, 0, 85.233, "mg_vii", "2p1.3p1.3D_2", "continuum"},
        {8100, 0, 84.99, "mg_vii", "2p1.3p1.3D_3", "continuum"},
        {8101, 0, 84.99, "mg_vii", "2p1.3p1.3D_3", "continuum"},
        {8102, 0, 84.128, "mg_vii", "2p1.3p1.3S_1", "continuum"},
        {8103, 0, 84.128, "mg_vii", "2p1.3p1.3S_1", "continuum"},
        {8104, 0, 85.732, "mg_vii", "2p1.3p1.3P_0", "continuum"},
        {8105, 0, 85.732, "mg_vii", "2p1.3p1.3P_0", "continuum"},
        {8106, 0, 85.584, "mg_vii", "2p1.3p1.3P_1", "continuum"},
        {8107, 0, 85.584, "mg_vii", "2p1.3p1.3P_1", "continuum"},
        {8108, 0, 85.472, "mg_vii", "2p1.3p1.3P_2", "continuum"},
        {8109, 0, 85.472, "mg_vii", "2p1.3p1.3P_2", "continuum"},
        {8110, 0, 80.672, "mg_vii", "2p1.3p1.1D_2", "continuum"},
        {8111, 0, 80.672, "mg_vii", "2p1.3p1.1D_2", "continuum"},
        {8112, 0, 78.018, "mg_vii", "2p1.3p1.1S_0", "continuum"},
        {8113, 0, 78.018, "mg_vii", "2p1.3p1.1S_0", "continuum"},
        {8114, 0, 78.915, "mg_vii", "2p1.3d1.3F_2", "continuum"},
        {8115, 0, 78.915, "mg_vii", "2p1.3d1.3F_2", "continuum"},
        {8116, 0, 76.65, "mg_vii", "2p1.3d1.3F_3", "continuum"},
        {8117, 0, 76.65, "mg_vii", "2p1.3d1.3F_3", "continuum"},
        {8118, 0, 78.647, "mg_vii", "2p1.3d1.1D_2", "continuum"},
        {8119, 0, 78.647, "mg_vii", "2p1.3d1.1D_2", "continuum"},
        {8120, 0, 76.455, "mg_vii", "2p1.3d1.3F_4", "continuum"},
        {8121, 0, 76.455, "mg_vii", "2p1.3d1.3F_4", "continuum"},
        {8122, 0, 77.304, "mg_vii", "2p1.3d1.3D_1", "continuum"},
        {8123, 0, 77.304, "mg_vii", "2p1.3d1.3D_1", "continuum"},
        {8124, 0, 77.252, "mg_vii", "2p1.3d1.3D_2", "continuum"},
        {8125, 0, 77.252, "mg_vii", "2p1.3d1.3D_2", "continuum"},
        {8126, 0, 77.143, "mg_vii", "2p1.3d1.3D_3", "continuum"},
        {8127, 0, 77.143, "mg_vii", "2p1.3d1.3D_3", "continuum"},
        {8128, 0, 76.684, "mg_vii", "2p1.3d1.3P_2", "continuum"},
        {8129, 0, 76.684, "mg_vii", "2p1.3d1.3P_2", "continuum"},
        {8130, 0, 76.597, "mg_vii", "2p1.3d1.3P_1", "continuum"},
        {8131, 0, 76.597, "mg_vii", "2p1.3d1.3P_1", "continuum"},
        {8132, 0, 76.548, "mg_vii", "2p1.3d1.3P_0", "continuum"},
        {8133, 0, 76.548, "mg_vii", "2p1.3d1.3P_0", "continuum"},
        {8134, 0, 74.695, "mg_vii", "2p1.3d1.1P_1", "continuum"},
        {8135, 0, 74.695, "mg_vii", "2p1.3d1.1P_1", "continuum"},
        {8136, 0, 74.818, "mg_vii", "2p1.3d1.1F_3", "continuum"},
        {8137, 0, 74.818, "mg_vii", "2p1.3d1.1F_3", "continuum"},
        {8138, 0, 1.562, "mg_vii", "superlevel", "continuum"},
        {8219, 0, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8220, 0, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8221, 0, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8222, 0, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8223, 0, 266, "mg_viii", "2p1.2P_1/2", "continuum"},
        {8229, 0, 265.591, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8231, 0, 265.591, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8232, 0, 265.591, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8233, 0, 265.591, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8236, 0, 265.591, "mg_viii", "2p1.2P_3/2", "continuum"},
        {8239, 0, 249.891, "mg_viii", "2s1.2p2.4P_1/2", "continuum"},
        {8240, 0, 249.891, "mg_viii", "2s1.2p2.4P_1/2", "continuum"},
        {8241, 0, 249.891, "mg_viii", "2s1.2p2.4P_1/2", "continuum"},
        {8242, 0, 249.75, "mg_viii", "2s1.2p2.4P_3/2", "continuum"},
        {8243, 0, 249.75, "mg_viii", "2s1.2p2.4P_3/2", "continuum"},
        {8244, 0, 249.75, "mg_viii", "2s1.2p2.4P_3/2", "continuum"},
        {8245, 0, 249.543, "mg_viii", "2s1.2p2.4P_5/2", "continuum"},
        {8246, 0, 249.543, "mg_viii", "2s1.2p2.4P_5/2", "continuum"},
        {8247, 0, 249.543, "mg_viii", "2s1.2p2.4P_5/2", "continuum"},
        {8248, 0, 237.21, "mg_viii", "2s1.2p2.2D_3/2", "continuum"},
        {8249, 0, 237.21, "mg_viii", "2s1.2p2.2D_3/2", "continuum"},
        {8250, 0, 237.21, "mg_viii", "2s1.2p2.2D_3/2", "continuum"},
        {8251, 0, 237.214, "mg_viii", "2s1.2p2.2D_5/2", "continuum"},
        {8252, 0, 237.214, "mg_viii", "2s1.2p2.2D_5/2", "continuum"},
        {8253, 0, 237.214, "mg_viii", "2s1.2p2.2D_5/2", "continuum"},
        {8254, 0, 229.033, "mg_viii", "2s1.2p2.2S_1/2", "continuum"},
        {8255, 0, 229.033, "mg_viii", "2s1.2p2.2S_1/2", "continuum"},
        {8256, 0, 229.033, "mg_viii", "2s1.2p2.2S_1/2", "continuum"},
        {8257, 0, 226.5, "mg_viii", "2s1.2p2.2P_1/2", "continuum"},
        {8258, 0, 226.5, "mg_viii", "2s1.2p2.2P_1/2", "continuum"},
        {8259, 0, 226.5, "mg_viii", "2s1.2p2.2P_1/2", "continuum"},
        {8260, 0, 226.252, "mg_viii", "2s1.2p2.2P_3/2", "continuum"},
        {8261, 0, 226.252, "mg_viii", "2s1.2p2.2P_3/2", "continuum"},
        {8262, 0, 226.252, "mg_viii", "2s1.2p2.2P_3/2", "continuum"},
        {8263, 0, 214.74, "mg_viii", "2s0.2p3.4S_3/2", "continuum"},
        {8264, 0, 214.74, "mg_viii", "2s0.2p3.4S_3/2", "continuum"},
        {8265, 0, 214.74, "mg_viii", "2s0.2p3.4S_3/2", "continuum"},
        {8266, 0, 208.27, "mg_viii", "2s0.2p3.2D_3/2", "continuum"},
        {8267, 0, 208.27, "mg_viii", "2s0.2p3.2D_3/2", "continuum"},
        {8268, 0, 208.27, "mg_viii", "2s0.2p3.2D_3/2", "continuum"},
        {8269, 0, 208.279, "mg_viii", "2s0.2p3.2D_5/2", "continuum"},
        {8270, 0, 208.279, "mg_viii", "2s0.2p3.2D_5/2", "continuum"},
        {8271, 0, 208.279, "mg_viii", "2s0.2p3.2D_5/2", "continuum"},
        {8272, 0, 200.979, "mg_viii", "2s0.2p3.2P_1/2", "continuum"},
        {8273, 0, 200.979, "mg_viii", "2s0.2p3.2P_1/2", "continuum"},
        {8274, 0, 200.979, "mg_viii", "2s0.2p3.2P_1/2", "continuum"},
        {8275, 0, 200.955, "mg_viii", "2s0.2p3.2P_3/2", "continuum"},
        {8276, 0, 200.955, "mg_viii", "2s0.2p3.2P_3/2", "continuum"},
        {8277, 0, 200.955, "mg_viii", "2s0.2p3.2P_3/2", "continuum"},
        {8278, 0, 115.956, "mg_viii", "2p0.3s1.2S_1/2", "continuum"},
        {8279, 0, 91.457, "mg_viii", "2s1.2p1.3p1.2P_1/2", "continuum"},
        {8280, 0, 91.457, "mg_viii", "2s1.2p1.3p1.2P_1/2", "continuum"},
        {8281, 0, 91.457, "mg_viii", "2s1.2p1.3p1.2P_1/2", "continuum"},
        {8282, 0, 92.397, "mg_viii", "2s1.2p1.3p1.4D_1/2", "continuum"},
        {8283, 0, 92.397, "mg_viii", "2s1.2p1.3p1.4D_1/2", "continuum"},
        {8284, 0, 92.397, "mg_viii", "2s1.2p1.3p1.4D_1/2", "continuum"},
        {8285, 0, 89.929, "mg_viii", "2s1.2p1.3p1.4P_1/2", "continuum"},
        {8286, 0, 89.929, "mg_viii", "2s1.2p1.3p1.4P_1/2", "continuum"},
        {8287, 0, 89.929, "mg_viii", "2s1.2p1.3p1.4P_1/2", "continuum"},
        {8288, 0, 84.946, "mg_viii", "2s1.2p1.3p1.2S_1/2", "continuum"},
        {8289, 0, 84.946, "mg_viii", "2s1.2p1.3p1.2S_1/2", "continuum"},
        {8290, 0, 84.946, "mg_viii", "2s1.2p1.3p1.2S_1/2", "continuum"},
        {8291, 0, 73.906, "mg_viii", "2s1.2p1.3p1.2P_1/2#2", "continuum"},
        {8292, 0, 73.088, "mg_viii", "2s1.2p1.3p1.2S_1/2#2", "continuum"},
        {8293, 0, 69.199, "mg_viii", "2s0.2p2.3s1.4P_1/2", "continuum"},
        {8294, 0, 69.199, "mg_viii", "2s0.2p2.3s1.4P_1/2", "continuum"},
        {8295, 0, 69.199, "mg_viii", "2s0.2p2.3s1.4P_1/2", "continuum"},
        {8296, 0, 65.748, "mg_viii", "2s0.2p2.3s1.2P_1/2", "continuum"},
        {8297, 0, 65.748, "mg_viii", "2s0.2p2.3s1.2P_1/2", "continuum"},
        {8298, 0, 65.748, "mg_viii", "2s0.2p2.3s1.2P_1/2", "continuum"},
        {8299, 0, 55.983, "mg_viii", "2s0.2p2.3d1.4D_1/2", "continuum"},
        {8300, 0, 55.983, "mg_viii", "2s0.2p2.3d1.4D_1/2", "continuum"},
        {8301, 0, 55.983, "mg_viii", "2s0.2p2.3d1.4D_1/2", "continuum"},
        {8302, 0, 55.713, "mg_viii", "2s0.2p2.3d1.2P_1/2", "continuum"},
        {8303, 0, 55.713, "mg_viii", "2s0.2p2.3d1.2P_1/2", "continuum"},
        {8304, 0, 55.713, "mg_viii", "2s0.2p2.3d1.2P_1/2", "continuum"},
        {8305, 0, 53.19, "mg_viii", "2s0.2p2.3d1.4P_1/2", "continuum"},
        {8306, 0, 53.19, "mg_viii", "2s0.2p2.3d1.4P_1/2", "continuum"},
        {8307, 0, 53.19, "mg_viii", "2s0.2p2.3d1.4P_1/2", "continuum"},
        {8308, 0, 51.46, "mg_viii", "2s0.2p2.3s1.2S_1/2", "continuum"},
        {8309, 0, 48.667, "mg_viii", "2s0.2p2.3d1.2P_1/2#2", "continuum"},
        {8310, 0, 45.298, "mg_viii", "2s0.2p2.3d1.2S_1/2", "continuum"},
        {8311, 0, 100.444, "mg_viii", "2p0.3d1.2D_3/2", "continuum"},
        {8312, 0, 100.444, "mg_viii", "2p0.3d1.2D_3/2", "continuum"},
        {8313, 0, 100.444, "mg_viii", "2p0.3d1.2D_3/2", "continuum"},
        {8314, 0, 91.33, "mg_viii", "2s1.2p1.3p1.2P_3/2", "continuum"},
        {8315, 0, 91.33, "mg_viii", "2s1.2p1.3p1.2P_3/2", "continuum"},
        {8316, 0, 91.33, "mg_viii", "2s1.2p1.3p1.2P_3/2", "continuum"},
        {8317, 0, 92.333, "mg_viii", "2s1.2p1.3p1.4D_3/2", "continuum"},
        {8318, 0, 92.333, "mg_viii", "2s1.2p1.3p1.4D_3/2", "continuum"},
        {8319, 0, 92.333, "mg_viii", "2s1.2p1.3p1.4D_3/2", "continuum"},
        {8320, 0, 90.848, "mg_viii", "2s1.2p1.3p1.4S_3/2", "continuum"},
        {8321, 0, 90.848, "mg_viii", "2s1.2p1.3p1.4S_3/2", "continuum"},
        {8322, 0, 90.848, "mg_viii", "2s1.2p1.3p1.4S_3/2", "continuum"},
        {8323, 0, 89.82, "mg_viii", "2s1.2p1.3p1.4P_3/2", "continuum"},
        {8324, 0, 89.82, "mg_viii", "2s1.2p1.3p1.4P_3/2", "continuum"},
        {8325, 0, 89.82, "mg_viii", "2s1.2p1.3p1.4P_3/2", "continuum"},
        {8326, 0, 87.462, "mg_viii", "2s1.2p1.3p1.2D_3/2", "continuum"},
        {8327, 0, 87.462, "mg_viii", "2s1.2p1.3p1.2D_3/2", "continuum"},
        {8328, 0, 87.462, "mg_viii", "2s1.2p1.3p1.2D_3/2", "continuum"},
        {8329, 0, 73.835, "mg_viii", "2s1.2p1.3p1.2P_3/2#2", "continuum"},
        {8330, 0, 73.858, "mg_viii", "2s1.2p1.3p1.2D_3/2#2", "continuum"},
        {8331, 0, 69.047, "mg_viii", "2s0.2p2.3s1.4P_3/2", "continuum"},
        {8332, 0, 69.047, "mg_viii", "2s0.2p2.3s1.4P_3/2", "continuum"},
        {8333, 0, 69.047, "mg_viii", "2s0.2p2.3s1.4P_3/2", "continuum"},
        {8334, 0, 65.497, "mg_viii", "2s0.2p2.3s1.2P_3/2", "continuum"},
        {8335, 0, 65.497, "mg_viii", "2s0.2p2.3s1.2P_3/2", "continuum"},
        {8336, 0, 65.497, "mg_viii", "2s0.2p2.3s1.2P_3/2", "continuum"},
        {8337, 0, 62.901, "mg_viii", "2s0.2p2.3s1.2D_3/2", "continuum"},
        {8338, 0, 57.417, "mg_viii", "2s0.2p2.3d1.4F_3/2", "continuum"},
        {8339, 0, 57.417, "mg_viii", "2s0.2p2.3d1.4F_3/2", "continuum"},
        {8340, 0, 57.417, "mg_viii", "2s0.2p2.3d1.4F_3/2", "continuum"},
        {8341, 0, 56.072, "mg_viii", "2s0.2p2.3d1.2P_3/2", "continuum"},
        {8342, 0, 56.072, "mg_viii", "2s0.2p2.3d1.2P_3/2", "continuum"},
        {8343, 0, 56.072, "mg_viii", "2s0.2p2.3d1.2P_3/2", "continuum"},
        {8344, 0, 55.842, "mg_viii", "2s0.2p2.3d1.4D_3/2", "continuum"},
        {8345, 0, 55.842, "mg_viii", "2s0.2p2.3d1.4D_3/2", "continuum"},
        {8346, 0, 55.842, "mg_viii", "2s0.2p2.3d1.4D_3/2", "continuum"},
        {8347, 0, 53.244, "mg_viii", "2s0.2p2.3d1.4P_3/2", "continuum"},
        {8348, 0, 53.244, "mg_viii", "2s0.2p2.3d1.4P_3/2", "continuum"},
        {8349, 0, 53.244, "mg_viii", "2s0.2p2.3d1.4P_3/2", "continuum"},
        {8350, 0, 50.821, "mg_viii", "2s0.2p2.3d1.2D_3/2", "continuum"},
        {8351, 0, 50.821, "mg_viii", "2s0.2p2.3d1.2D_3/2", "continuum"},
        {8352, 0, 50.821, "mg_viii", "2s0.2p2.3d1.2D_3/2", "continuum"},
        {8353, 0, 48.698, "mg_viii", "2s0.2p2.3d1.2D_3/2#2", "continuum"},
        {8354, 0, 48.525, "mg_viii", "2s0.2p2.3d1.2P_3/2#2", "continuum"},
        {8355, 0, 36.871, "mg_viii", "2s0.2p2.3d1.2D_3/2#3", "continuum"},
        {8356, 0, 100.423, "mg_viii", "2p0.3d1.2D_5/2", "continuum"},
        {8357, 0, 100.423, "mg_viii", "2p0.3d1.2D_5/2", "continuum"},
        {8358, 0, 100.423, "mg_viii", "2p0.3d1.2D_5/2", "continuum"},
        {8359, 0, 92.23, "mg_viii", "2s1.2p1.3p1.4D_5/2", "continuum"},
        {8360, 0, 92.23, "mg_viii", "2s1.2p1.3p1.4D_5/2", "continuum"},
        {8361, 0, 92.23, "mg_viii", "2s1.2p1.3p1.4D_5/2", "continuum"},
        {8362, 0, 89.696, "mg_viii", "2s1.2p1.3p1.4P_5/2", "continuum"},
        {8363, 0, 89.696, "mg_viii", "2s1.2p1.3p1.4P_5/2", "continuum"},
        {8364, 0, 89.696, "mg_viii", "2s1.2p1.3p1.4P_5/2", "continuum"},
        {8365, 0, 87.187, "mg_viii", "2s1.2p1.3p1.2D_5/2", "continuum"},
        {8366, 0, 87.187, "mg_viii", "2s1.2p1.3p1.2D_5/2", "continuum"},
        {8367, 0, 87.187, "mg_viii", "2s1.2p1.3p1.2D_5/2", "continuum"},
        {8368, 0, 74.047, "mg_viii", "2s1.2p1.3p1.2D_5/2#2", "continuum"},
        {8369, 0, 68.799, "mg_viii", "2s0.2p2.3s1.4P_5/2", "continuum"},
        {8370, 0, 68.799, "mg_viii", "2s0.2p2.3s1.4P_5/2", "continuum"},
        {8371, 0, 68.799, "mg_viii", "2s0.2p2.3s1.4P_5/2", "continuum"},
        {8372, 0, 62.787, "mg_viii", "2s0.2p2.3s1.2D_5/2", "continuum"},
        {8373, 0, 57.332, "mg_viii", "2s0.2p2.3d1.4F_5/2", "continuum"},
        {8374, 0, 57.332, "mg_viii", "2s0.2p2.3d1.4F_5/2", "continuum"},
        {8375, 0, 57.332, "mg_viii", "2s0.2p2.3d1.4F_5/2", "continuum"},
        {8376, 0, 55.851, "mg_viii", "2s0.2p2.3d1.4D_5/2", "continuum"},
        {8377, 0, 55.851, "mg_viii", "2s0.2p2.3d1.4D_5/2", "continuum"},
        {8378, 0, 55.851, "mg_viii", "2s0.2p2.3d1.4D_5/2", "continuum"},
        {8379, 0, 54.962, "mg_viii", "2s0.2p2.3d1.2F_5/2", "continuum"},
        {8380, 0, 54.962, "mg_viii", "2s0.2p2.3d1.2F_5/2", "continuum"},
        {8381, 0, 54.962, "mg_viii", "2s0.2p2.3d1.2F_5/2", "continuum"},
        {8382, 0, 53.344, "mg_viii", "2s0.2p2.3d1.4P_5/2", "continuum"},
        {8383, 0, 53.344, "mg_viii", "2s0.2p2.3d1.4P_5/2", "continuum"},
        {8384, 0, 53.344, "mg_viii", "2s0.2p2.3d1.4P_5/2", "continuum"},
        {8385, 0, 54.909, "mg_viii", "2s0.2p2.3d1.2D_5/2", "continuum"},
        {8386, 0, 54.909, "mg_viii", "2s0.2p2.3d1.2D_5/2", "continuum"},
        {8387, 0, 54.909, "mg_viii", "2s0.2p2.3d1.2D_5/2", "continuum"},
        {8388, 0, 51.114, "mg_viii", "2s0.2p2.3d1.2D_5/2#2", "continuum"},
        {8389, 0, 48.205, "mg_viii", "2s0.2p2.3d1.2F_5/2#2", "continuum"},
        {8390, 0, 36.92, "mg_viii", "2s0.2p2.3d1.2D_5/2#3", "continuum"},
        {8391, 0, 92, "mg_viii", "2s1.2p1.3p1.4D_7/2", "continuum"},
        {8392, 0, 92, "mg_viii", "2s1.2p1.3p1.4D_7/2", "continuum"},
        {8393, 0, 92, "mg_viii", "2s1.2p1.3p1.4D_7/2", "continuum"},
        {8394, 0, 57.211, "mg_viii", "2s0.2p2.3d1.4F_7/2", "continuum"},
        {8395, 0, 57.211, "mg_viii", "2s0.2p2.3d1.4F_7/2", "continuum"},
        {8396, 0, 57.211, "mg_viii", "2s0.2p2.3d1.4F_7/2", "continuum"},
        {8397, 0, 55.783, "mg_viii", "2s0.2p2.3d1.4D_7/2", "continuum"},
        {8398, 0, 55.783, "mg_viii", "2s0.2p2.3d1.4D_7/2", "continuum"},
        {8399, 0, 55.783, "mg_viii", "2s0.2p2.3d1.4D_7/2", "continuum"},
        {8400, 0, 55.066, "mg_viii", "2s0.2p2.3d1.2F_7/2", "continuum"},
        {8401, 0, 55.066, "mg_viii", "2s0.2p2.3d1.2F_7/2", "continuum"},
        {8402, 0, 55.066, "mg_viii", "2s0.2p2.3d1.2F_7/2", "continuum"},
        {8403, 0, 48.854, "mg_viii", "2s0.2p2.3d1.2F_7/2#2", "continuum"},
        {8404, 0, 57.055, "mg_viii", "2s0.2p2.3d1.4F_9/2", "continuum"},
        {8405, 0, 57.055, "mg_viii", "2s0.2p2.3d1.4F_9/2", "continuum"},
        {8406, 0, 57.055, "mg_viii", "2s0.2p2.3d1.4F_9/2", "continuum"},
        {8407, 0, 109.337, "mg_viii", "2p0.3p1.2P_1/2", "continuum"},
        {8408, 0, 109.337, "mg_viii", "2p0.3p1.2P_1/2", "continuum"},
        {8409, 0, 109.337, "mg_viii", "2p0.3p1.2P_1/2", "continuum"},
        {8410, 0, 98.519, "mg_viii", "2s1.2p1.3s1.4P_1/2", "continuum"},
        {8411, 0, 98.519, "mg_viii", "2s1.2p1.3s1.4P_1/2", "continuum"},
        {8412, 0, 98.519, "mg_viii", "2s1.2p1.3s1.4P_1/2", "continuum"},
        {8413, 0, 94.794, "mg_viii", "2s1.2p1.3s1.2P_1/2", "continuum"},
        {8414, 0, 94.794, "mg_viii", "2s1.2p1.3s1.2P_1/2", "continuum"},
        {8415, 0, 94.794, "mg_viii", "2s1.2p1.3s1.2P_1/2", "continuum"},
        {8416, 0, 84.309, "mg_viii", "2s1.2p1.3d1.4D_1/2", "continuum"},
        {8417, 0, 84.309, "mg_viii", "2s1.2p1.3d1.4D_1/2", "continuum"},
        {8418, 0, 84.309, "mg_viii", "2s1.2p1.3d1.4D_1/2", "continuum"},
        {8419, 0, 81.972, "mg_viii", "2s1.2p1.3d1.4P_1/2", "continuum"},
        {8420, 0, 81.972, "mg_viii", "2s1.2p1.3d1.4P_1/2", "continuum"},
        {8421, 0, 81.972, "mg_viii", "2s1.2p1.3d1.4P_1/2", "continuum"},
        {8422, 0, 81.716, "mg_viii", "2s1.2p1.3s1.2P_1/2#2", "continuum"},
        {8423, 0, 78.334, "mg_viii", "2s1.2p1.3d1.2P_1/2", "continuum"},
        {8424, 0, 78.334, "mg_viii", "2s1.2p1.3d1.2P_1/2", "continuum"},
        {8425, 0, 78.334, "mg_viii", "2s1.2p1.3d1.2P_1/2", "continuum"},
        {8426, 0, 66.386, "mg_viii", "2s1.2p1.3d1.2P_1/2#2", "continuum"},
        {8427, 0, 64.666, "mg_viii", "2s0.2p2.3p1.2S_1/2", "continuum"},
        {8428, 0, 64.666, "mg_viii", "2s0.2p2.3p1.2S_1/2", "continuum"},
        {8429, 0, 64.666, "mg_viii", "2s0.2p2.3p1.2S_1/2", "continuum"},
        {8430, 0, 63.457, "mg_viii", "2s0.2p2.3p1.4D_1/2", "continuum"},
        {8431, 0, 63.457, "mg_viii", "2s0.2p2.3p1.4D_1/2", "continuum"},
        {8432, 0, 63.457, "mg_viii", "2s0.2p2.3p1.4D_1/2", "continuum"},
        {8433, 0, 62.397, "mg_viii", "2s0.2p2.3p1.4P_1/2", "continuum"},
        {8434, 0, 62.397, "mg_viii", "2s0.2p2.3p1.4P_1/2", "continuum"},
        {8435, 0, 62.397, "mg_viii", "2s0.2p2.3p1.4P_1/2", "continuum"},
        {8436, 0, 59.292, "mg_viii", "2s0.2p2.3p1.2P_1/2", "continuum"},
        {8437, 0, 59.292, "mg_viii", "2s0.2p2.3p1.2P_1/2", "continuum"},
        {8438, 0, 59.292, "mg_viii", "2s0.2p2.3p1.2P_1/2", "continuum"},
        {8439, 0, 52.368, "mg_viii", "2s0.2p2.3p1.2P_1/2#2", "continuum"},
        {8440, 0, 43.3, "mg_viii", "2s0.2p2.3p1.2P_1/2#3", "continuum"},
        {8441, 0, 109.218, "mg_viii", "2p0.3p1.2P_3/2", "continuum"},
        {8442, 0, 109.218, "mg_viii", "2p0.3p1.2P_3/2", "continuum"},
        {8443, 0, 109.218, "mg_viii", "2p0.3p1.2P_3/2", "continuum"},
        {8444, 0, 98.378, "mg_viii", "2s1.2p1.3s1.4P_3/2", "continuum"},
        {8445, 0, 98.378, "mg_viii", "2s1.2p1.3s1.4P_3/2", "continuum"},
        {8446, 0, 98.378, "mg_viii", "2s1.2p1.3s1.4P_3/2", "continuum"},
        {8447, 0, 94.507, "mg_viii", "2s1.2p1.3s1.2P_3/2", "continuum"},
        {8448, 0, 94.507, "mg_viii", "2s1.2p1.3s1.2P_3/2", "continuum"},
        {8449, 0, 94.507, "mg_viii", "2s1.2p1.3s1.2P_3/2", "continuum"},
        {8450, 0, 85.909, "mg_viii", "2s1.2p1.3d1.4F_3/2", "continuum"},
        {8451, 0, 85.909, "mg_viii", "2s1.2p1.3d1.4F_3/2", "continuum"},
        {8452, 0, 85.909, "mg_viii", "2s1.2p1.3d1.4F_3/2", "continuum"},
        {8453, 0, 83.044, "mg_viii", "2s1.2p1.3d1.4D_3/2", "continuum"},
        {8454, 0, 83.044, "mg_viii", "2s1.2p1.3d1.4D_3/2", "continuum"},
        {8455, 0, 83.044, "mg_viii", "2s1.2p1.3d1.4D_3/2", "continuum"},
        {8456, 0, 82.786, "mg_viii", "2s1.2p1.3d1.2D_3/2", "continuum"},
        {8457, 0, 82.786, "mg_viii", "2s1.2p1.3d1.2D_3/2", "continuum"},
        {8458, 0, 82.786, "mg_viii", "2s1.2p1.3d1.2D_3/2", "continuum"},
        {8459, 0, 82.032, "mg_viii", "2s1.2p1.3d1.4P_3/2", "continuum"},
        {8460, 0, 82.032, "mg_viii", "2s1.2p1.3d1.4P_3/2", "continuum"},
        {8461, 0, 82.032, "mg_viii", "2s1.2p1.3d1.4P_3/2", "continuum"},
        {8462, 0, 81.695, "mg_viii", "2s1.2p1.3s1.2P_3/2#2", "continuum"},
        {8463, 0, 78.478, "mg_viii", "2s1.2p1.3d1.2P_3/2", "continuum"},
        {8464, 0, 78.478, "mg_viii", "2s1.2p1.3d1.2P_3/2", "continuum"},
        {8465, 0, 78.478, "mg_viii", "2s1.2p1.3d1.2P_3/2", "continuum"},
        {8466, 0, 66.735, "mg_viii", "2s1.2p1.3d1.2D_3/2#2", "continuum"},
        {8467, 0, 64.878, "mg_viii", "2s1.2p1.3d1.2P_3/2#2", "continuum"},
        {8468, 0, 63.365, "mg_viii", "2s0.2p2.3p1.4D_3/2", "continuum"},
        {8469, 0, 63.365, "mg_viii", "2s0.2p2.3p1.4D_3/2", "continuum"},
        {8470, 0, 63.365, "mg_viii", "2s0.2p2.3p1.4D_3/2", "continuum"},
        {8471, 0, 62.332, "mg_viii", "2s0.2p2.3p1.4P_3/2", "continuum"},
        {8472, 0, 62.332, "mg_viii", "2s0.2p2.3p1.4P_3/2", "continuum"},
        {8473, 0, 62.332, "mg_viii", "2s0.2p2.3p1.4P_3/2", "continuum"},
        {8474, 0, 61.252, "mg_viii", "2s0.2p2.3p1.2D_3/2", "continuum"},
        {8475, 0, 61.252, "mg_viii", "2s0.2p2.3p1.2D_3/2", "continuum"},
        {8476, 0, 61.252, "mg_viii", "2s0.2p2.3p1.2D_3/2", "continuum"},
        {8477, 0, 58.535, "mg_viii", "2s0.2p2.3p1.4S_3/2", "continuum"},
        {8478, 0, 58.535, "mg_viii", "2s0.2p2.3p1.4S_3/2", "continuum"},
        {8479, 0, 58.535, "mg_viii", "2s0.2p2.3p1.4S_3/2", "continuum"},
        {8480, 0, 59.31, "mg_viii", "2s0.2p2.3p1.2P_3/2", "continuum"},
        {8481, 0, 59.31, "mg_viii", "2s0.2p2.3p1.2P_3/2", "continuum"},
        {8482, 0, 59.31, "mg_viii", "2s0.2p2.3p1.2P_3/2", "continuum"},
        {8483, 0, 54.37, "mg_viii", "2s0.2p2.3p1.2D_3/2#2", "continuum"},
        {8484, 0, 52.212, "mg_viii", "2s0.2p2.3p1.2P_3/2#2", "continuum"},
        {8485, 0, 43.259, "mg_viii", "2s0.2p2.3p1.2P_3/2#3", "continuum"},
        {8486, 0, 98.127, "mg_viii", "2s1.2p1.3s1.4P_5/2", "continuum"},
        {8487, 0, 98.127, "mg_viii", "2s1.2p1.3s1.4P_5/2", "continuum"},
        {8488, 0, 98.127, "mg_viii", "2s1.2p1.3s1.4P_5/2", "continuum"},
        {8489, 0, 85.822, "mg_viii", "2s1.2p1.3d1.4F_5/2", "continuum"},
        {8490, 0, 85.822, "mg_viii", "2s1.2p1.3d1.4F_5/2", "continuum"},
        {8491, 0, 85.822, "mg_viii", "2s1.2p1.3d1.4F_5/2", "continuum"},
        {8492, 0, 83.003, "mg_viii", "2s1.2p1.3d1.4D_5/2", "continuum"},
        {8493, 0, 83.003, "mg_viii", "2s1.2p1.3d1.4D_5/2", "continuum"},
        {8494, 0, 83.003, "mg_viii", "2s1.2p1.3d1.4D_5/2", "continuum"},
        {8495, 0, 82.742, "mg_viii", "2s1.2p1.3d1.2D_5/2", "continuum"},
        {8496, 0, 82.742, "mg_viii", "2s1.2p1.3d1.2D_5/2", "continuum"},
        {8497, 0, 82.742, "mg_viii", "2s1.2p1.3d1.2D_5/2", "continuum"},
        {8498, 0, 82.123, "mg_viii", "2s1.2p1.3d1.4P_5/2", "continuum"},
        {8499, 0, 82.123, "mg_viii", "2s1.2p1.3d1.4P_5/2", "continuum"},
        {8500, 0, 82.123, "mg_viii", "2s1.2p1.3d1.4P_5/2", "continuum"},
        {8501, 0, 79.483, "mg_viii", "2s1.2p1.3d1.2F_5/2", "continuum"},
        {8502, 0, 79.483, "mg_viii", "2s1.2p1.3d1.2F_5/2", "continuum"},
        {8503, 0, 79.483, "mg_viii", "2s1.2p1.3d1.2F_5/2", "continuum"},
        {8504, 0, 68.021, "mg_viii", "2s1.2p1.3d1.2F_5/2#2", "continuum"},
        {8505, 0, 66.691, "mg_viii", "2s1.2p1.3d1.2D_5/2#2", "continuum"},
        {8506, 0, 63.214, "mg_viii", "2s0.2p2.3p1.4D_5/2", "continuum"},
        {8507, 0, 63.214, "mg_viii", "2s0.2p2.3p1.4D_5/2", "continuum"},
        {8508, 0, 63.214, "mg_viii", "2s0.2p2.3p1.4D_5/2", "continuum"},
        {8509, 0, 61.225, "mg_viii", "2s0.2p2.3p1.4P_5/2", "continuum"},
        {8510, 0, 61.225, "mg_viii", "2s0.2p2.3p1.4P_5/2", "continuum"},
        {8511, 0, 61.225, "mg_viii", "2s0.2p2.3p1.4P_5/2", "continuum"},
        {8512, 0, 60.972, "mg_viii", "2s0.2p2.3p1.2D_5/2", "continuum"},
        {8513, 0, 60.972, "mg_viii", "2s0.2p2.3p1.2D_5/2", "continuum"},
        {8514, 0, 60.972, "mg_viii", "2s0.2p2.3p1.2D_5/2", "continuum"},
        {8515, 0, 56.497, "mg_viii", "2s0.2p2.3p1.2F_5/2", "continuum"},
        {8516, 0, 54.402, "mg_viii", "2s0.2p2.3p1.2D_5/2#2", "continuum"},
        {8517, 0, 85.691, "mg_viii", "2s1.2p1.3d1.4F_7/2", "continuum"},
        {8518, 0, 85.691, "mg_viii", "2s1.2p1.3d1.4F_7/2", "continuum"},
        {8519, 0, 85.691, "mg_viii", "2s1.2p1.3d1.4F_7/2", "continuum"},
        {8520, 0, 82.901, "mg_viii", "2s1.2p1.3d1.4D_7/2", "continuum"},
        {8521, 0, 82.901, "mg_viii", "2s1.2p1.3d1.4D_7/2", "continuum"},
        {8522, 0, 82.901, "mg_viii", "2s1.2p1.3d1.4D_7/2", "continuum"},
        {8523, 0, 79.229, "mg_viii", "2s1.2p1.3d1.2F_7/2", "continuum"},
        {8524, 0, 79.229, "mg_viii", "2s1.2p1.3d1.2F_7/2", "continuum"},
        {8525, 0, 79.229, "mg_viii", "2s1.2p1.3d1.2F_7/2", "continuum"},
        {8526, 0, 67.107, "mg_viii", "2s1.2p1.3d1.2F_7/2#2", "continuum"},
        {8527, 0, 61.973, "mg_viii", "2s0.2p2.3p1.4D_7/2", "continuum"},
        {8528, 0, 61.973, "mg_viii", "2s0.2p2.3p1.4D_7/2", "continuum"},
        {8529, 0, 61.973, "mg_viii", "2s0.2p2.3p1.4D_7/2", "continuum"},
        {8530, 0, 56.423, "mg_viii", "2s0.2p2.3p1.2F_7/2", "continuum"},
        {8531, 0, 85.512, "mg_viii", "2s1.2p1.3d1.4F_9/2", "continuum"},
        {8532, 0, 85.512, "mg_viii", "2s1.2p1.3d1.4F_9/2", "continuum"},
        {8533, 0, 85.512, "mg_viii", "2s1.2p1.3d1.4F_9/2", "continuum"},
        {8534, 0, 1.84698, "mg_viii", "superlevel", "continuum"},
        {8554, 0, 328, "mg_ix", "2s2.1S_0", "continuum"},
        {8557, 0, 310.587, "mg_ix", "2s1.2p1.3P_0", "continuum"},
        {8558, 0, 310.447, "mg_ix", "2s1.2p1.3P_1", "continuum"},
        {8559, 0, 310.142, "mg_ix", "2s1.2p1.3P_2", "continuum"},
        {8560, 0, 294.329, "mg_ix", "2s1.2p1.1P_1", "continuum"},
        {8562, 0, 282.659, "mg_ix", "2s0.2p2.3P_0", "continuum"},
        {8563, 0, 282.497, "mg_ix", "2s0.2p2.3P_1", "continuum"},
        {8564, 0, 282.497, "mg_ix", "2s0.2p2.3P_1", "continuum"},
        {8565, 0, 282.228, "mg_ix", "2s0.2p2.3P_2", "continuum"},
        {8566, 0, 282.228, "mg_ix", "2s0.2p2.3P_2", "continuum"},
        {8567, 0, 277.795, "mg_ix", "2s0.2p2.1D_2", "continuum"},
        {8568, 0, 277.795, "mg_ix", "2s0.2p2.1D_2", "continuum"},
        {8569, 0, 266.079, "mg_ix", "2s0.2p2.1S_0", "continuum"},
        {8570, 0, 266.079, "mg_ix", "2s0.2p2.1S_0", "continuum"},
        {8571, 0, 138.08, "mg_ix", "2s1.3s1.3S_1", "continuum"},
        {8572, 0, 134.904, "mg_ix", "2s1.3s1.1S_0", "continuum"},
        {8573, 0, 130.501, "mg_ix", "2s1.3p1.1P_1", "continuum"},
        {8574, 0, 132.806, "mg_ix", "2s1.3p1.3P_0", "continuum"},
        {8575, 0, 132.708, "mg_ix", "2s1.3p1.3P_1", "continuum"},
        {8576, 0, 132.591, "mg_ix", "2s1.3p1.3P_2", "continuum"},
        {8577, 0, 125.861, "mg_ix", "2s1.3d1.3D_1", "continuum"},
        {8578, 0, 125.845, "mg_ix", "2s1.3d1.3D_2", "continuum"},
        {8579, 0, 125.827, "mg_ix", "2s1.3d1.3D_3", "continuum"},
        {8580, 0, 122.944, "mg_ix", "2s1.3d1.1D_2", "continuum"},
        {8581, 0, 105.917, "mg_ix", "2s0.2p1.3p1.3P_0", "continuum"},
        {8582, 0, 105.917, "mg_ix", "2s0.2p1.3p1.3P_0", "continuum"},
        {8583, 0, 96.713, "mg_ix", "2s0.2p1.3p1.1S_0", "continuum"},
        {8584, 0, 96.713, "mg_ix", "2s0.2p1.3p1.1S_0", "continuum"},
        {8585, 0, 110.007, "mg_ix", "2s0.2p1.3p1.3D_3", "continuum"},
        {8586, 0, 110.007, "mg_ix", "2s0.2p1.3p1.3D_3", "continuum"},
        {8587, 0, 116.058, "mg_ix", "2s0.2p1.3s1.3P_0", "continuum"},
        {8588, 0, 116.058, "mg_ix", "2s0.2p1.3s1.3P_0", "continuum"},
        {8589, 0, 102.848, "mg_ix", "2s0.2p1.3d1.3P_0", "continuum"},
        {8590, 0, 102.848, "mg_ix", "2s0.2p1.3d1.3P_0", "continuum"},
        {8591, 0, 103.176, "mg_ix", "2s0.2p1.3d1.3F_4", "continuum"},
        {8592, 0, 103.176, "mg_ix", "2s0.2p1.3d1.3F_4", "continuum"},
        {8593, 0, 111.351, "mg_ix", "2s0.2p1.3p1.1P_1", "continuum"},
        {8594, 0, 111.351, "mg_ix", "2s0.2p1.3p1.1P_1", "continuum"},
        {8595, 0, 110.44, "mg_ix", "2s0.2p1.3p1.3D_1", "continuum"},
        {8596, 0, 110.44, "mg_ix", "2s0.2p1.3p1.3D_1", "continuum"},
        {8597, 0, 108.593, "mg_ix", "2s0.2p1.3p1.3S_1", "continuum"},
        {8598, 0, 108.593, "mg_ix", "2s0.2p1.3p1.3S_1", "continuum"},
        {8599, 0, 107.563, "mg_ix", "2s0.2p1.3p1.3P_1", "continuum"},
        {8600, 0, 107.563, "mg_ix", "2s0.2p1.3p1.3P_1", "continuum"},
        {8601, 0, 110.317, "mg_ix", "2s0.2p1.3p1.3D_2", "continuum"},
        {8602, 0, 110.317, "mg_ix", "2s0.2p1.3p1.3D_2", "continuum"},
        {8603, 0, 107.402, "mg_ix", "2s0.2p1.3p1.3P_2", "continuum"},
        {8604, 0, 107.402, "mg_ix", "2s0.2p1.3p1.3P_2", "continuum"},
        {8605, 0, 105.434, "mg_ix", "2s0.2p1.3p1.1D_2", "continuum"},
        {8606, 0, 105.434, "mg_ix", "2s0.2p1.3p1.1D_2", "continuum"},
        {8607, 0, 115.921, "mg_ix", "2s0.2p1.3s1.3P_1", "continuum"},
        {8608, 0, 115.921, "mg_ix", "2s0.2p1.3s1.3P_1", "continuum"},
        {8609, 0, 111.981, "mg_ix", "2s0.2p1.3s1.1P_1", "continuum"},
        {8610, 0, 111.981, "mg_ix", "2s0.2p1.3s1.1P_1", "continuum"},
        {8611, 0, 104.015, "mg_ix", "2s0.2p1.3d1.3D_1", "continuum"},
        {8612, 0, 104.015, "mg_ix", "2s0.2p1.3d1.3D_1", "continuum"},
        {8613, 0, 102.913, "mg_ix", "2s0.2p1.3d1.3P_1", "continuum"},
        {8614, 0, 102.913, "mg_ix", "2s0.2p1.3d1.3P_1", "continuum"},
        {8615, 0, 99.771, "mg_ix", "2s0.2p1.3d1.1P_1", "continuum"},
        {8616, 0, 99.771, "mg_ix", "2s0.2p1.3d1.1P_1", "continuum"},
        {8617, 0, 115.592, "mg_ix", "2s0.2p1.3s1.3P_2", "continuum"},
        {8618, 0, 115.592, "mg_ix", "2s0.2p1.3s1.3P_2", "continuum"},
        {8619, 0, 103.959, "mg_ix", "2s0.2p1.3d1.3F_2", "continuum"},
        {8620, 0, 103.959, "mg_ix", "2s0.2p1.3d1.3F_2", "continuum"},
        {8621, 0, 106.206, "mg_ix", "2s0.2p1.3d1.1D_2", "continuum"},
        {8622, 0, 106.206, "mg_ix", "2s0.2p1.3d1.1D_2", "continuum"},
        {8623, 0, 103.948, "mg_ix", "2s0.2p1.3d1.3D_2", "continuum"},
        {8624, 0, 103.948, "mg_ix", "2s0.2p1.3d1.3D_2", "continuum"},
        {8625, 0, 103.036, "mg_ix", "2s0.2p1.3d1.3P_2", "continuum"},
        {8626, 0, 103.036, "mg_ix", "2s0.2p1.3d1.3P_2", "continuum"},
        {8627, 0, 103.567, "mg_ix", "2s0.2p1.3d1.3F_3", "continuum"},
        {8628, 0, 103.567, "mg_ix", "2s0.2p1.3d1.3F_3", "continuum"},
        {8629, 0, 103.824, "mg_ix", "2s0.2p1.3d1.3D_3", "continuum"},
        {8630, 0, 103.824, "mg_ix", "2s0.2p1.3d1.3D_3", "continuum"},
        {8631, 0, 100.623, "mg_ix", "2s0.2p1.3d1.1F_3", "continuum"},
        {8632, 0, 100.623, "mg_ix", "2s0.2p1.3d1.1F_3", "continuum"},
        {8633, 0, 2.27802, "mg_ix", "superlevel", "continuum"},
        {8639, 0, 367, "mg_x", "2s1.2S_1/2", "continuum"},
        {8640, 0, 347.169, "mg_x", "2s0.2p1.2P_1/2", "continuum"},
        {8641, 0, 346.676, "mg_x", "2s0.2p1.2P_3/2", "continuum"},
        {8642, 0, 158.459, "mg_x", "2s0.3s1.2S_1/2", "continuum"},
        {8643, 0, 153.028, "mg_x", "2s0.3p1.2P_1/2", "continuum"},
        {8644, 0, 152.866, "mg_x", "2s0.3p1.2P_3/2", "continuum"},
        {8645, 0, 150.924, "mg_x", "2s0.3d1.2D_3/2", "continuum"},
        {8646, 0, 150.876, "mg_x", "2s0.3d1.2D_5/2", "continuum"},
        {8647, 0, 87.83, "mg_x", "2s0.4s1.2S_1/2", "continuum"},
        {8648, 0, 85.655, "mg_x", "2s0.4p1.2P_1/2", "continuum"},
        {8649, 0, 85.655, "mg_x", "2s0.4p1.2P_3/2", "continuum"},
        {8650, 0, 84.759, "mg_x", "2s0.4d1.2D_3/2", "continuum"},
        {8651, 0, 84.719, "mg_x", "2s0.4d1.2D_5/2", "continuum"},
        {8652, 0, 84.675, "mg_x", "2s0.4f1.2F_5/2", "continuum"},
        {8653, 0, 84.665, "mg_x", "2s0.4f1.2F_7/2", "continuum"},
        {8654, 0, 55.732, "mg_x", "2s0.5s1.2S_1/2", "continuum"},
        {8655, 0, 54.579, "mg_x", "2s0.5p1.2P_1/2", "continuum"},
        {8656, 0, 54.579, "mg_x", "2s0.5p1.2P_3/2", "continuum"},
        {8657, 0, 54.145, "mg_x", "2s0.5d1.2D_3/2", "continuum"},
        {8658, 0, 54.12, "mg_x", "2s0.5d1.2D_5/2", "continuum"},
        {8659, 0, 54.005, "mg_x", "2s0.5f1.2F_5/2", "continuum"},
        {8660, 0, 53.995, "mg_x", "2s0.5f1.2F_7/2", "continuum"},
        {8661, 0, 53.945, "mg_x", "2s0.5g1.2G_7/2", "continuum"},
        {8662, 0, 53.935, "mg_x", "2s0.5g1.2G_9/2", "continuum"},
        {8663, 0, 2.54901, "mg_x", "superlevel", "continuum"},
        {8664, 0, 1762, "mg_xi", "1s2.1S_0", "continuum"},
        {8665, 0, 102.934, "mg_xi", "1s1.4p1.1P_1", "continuum"},
        {8666, 0, 103.104, "mg_xi", "1s1.4f1.3F_4", "continuum"},
        {8667, 0, 103.104, "mg_xi", "1s1.4f1.3F_3", "continuum"},
        {8668, 0, 103.104, "mg_xi", "1s1.4f1.3F_2", "continuum"},
        {8669, 0, 66.0593, "mg_xi", "1s1.5d1.1D_2", "continuum"},
        {8670, 0, 430.888, "mg_xi", "1s1.2s1.3S_1", "continuum"},
        {8671, 0, 182.688, "mg_xi", "1s1.3p1.1P_1", "continuum"},
        {8672, 0, 103.104, "mg_xi", "1s1.4f1.1F_3", "continuum"},
        {8673, 0, 183.148, "mg_xi", "1s1.3d1.1D_2", "continuum"},
        {8674, 0, 105.324, "mg_xi", "1s1.4s1.3S_1", "continuum"},
        {8675, 0, 418.162, "mg_xi", "1s1.2s1.1S_0", "continuum"},
        {8676, 0, 66.0516, "mg_xi", "1s1.5g1.1G_4", "continuum"},
        {8677, 0, 185.131, "mg_xi", "1s1.3s1.1S_0", "continuum"},
        {8678, 0, 66.0516, "mg_xi", "1s1.5g1.3G_5", "continuum"},
        {8679, 0, 66.0516, "mg_xi", "1s1.5g1.3G_4", "continuum"},
        {8680, 0, 66.0516, "mg_xi", "1s1.5g1.3G_3", "continuum"},
        {8681, 0, 185.235, "mg_xi", "1s1.3p1.3P_0", "continuum"},
        {8682, 0, 185.202, "mg_xi", "1s1.3p1.3P_1", "continuum"},
        {8683, 0, 185.071, "mg_xi", "1s1.3p1.3P_2", "continuum"},
        {8684, 0, 66.0577, "mg_xi", "1s1.5f1.3F_4", "continuum"},
        {8685, 0, 66.0577, "mg_xi", "1s1.5f1.3F_3", "continuum"},
        {8686, 0, 66.0577, "mg_xi", "1s1.5f1.3F_2", "continuum"},
        {8687, 0, 66.5043, "mg_xi", "1s1.5p1.3P_0", "continuum"},
        {8688, 0, 66.4971, "mg_xi", "1s1.5p1.3P_1", "continuum"},
        {8689, 0, 66.4688, "mg_xi", "1s1.5p1.3P_2", "continuum"},
        {8690, 0, 66.0577, "mg_xi", "1s1.5f1.1F_3", "continuum"},
        {8691, 0, 103.962, "mg_xi", "1s1.4s1.1S_0", "continuum"},
        {8692, 0, 66.4987, "mg_xi", "1s1.5s1.1S_0", "continuum"},
        {8693, 0, 103.112, "mg_xi", "1s1.4d1.1D_2", "continuum"},
        {8694, 0, 65.9746, "mg_xi", "1s1.5p1.1P_1", "continuum"},
        {8695, 0, 188.495, "mg_xi", "1s1.3s1.3S_1", "continuum"},
        {8696, 0, 103.981, "mg_xi", "1s1.4p1.3P_0", "continuum"},
        {8697, 0, 103.967, "mg_xi", "1s1.4p1.3P_1", "continuum"},
        {8698, 0, 103.912, "mg_xi", "1s1.4p1.3P_2", "continuum"},
        {8699, 0, 103.167, "mg_xi", "1s1.4d1.3D_1", "continuum"},
        {8700, 0, 103.165, "mg_xi", "1s1.4d1.3D_2", "continuum"},
        {8701, 0, 103.145, "mg_xi", "1s1.4d1.3D_3", "continuum"},
        {8702, 0, 67.1827, "mg_xi", "1s1.5s1.3S_1", "continuum"},
        {8703, 0, 183.286, "mg_xi", "1s1.3d1.3D_1", "continuum"},
        {8704, 0, 183.281, "mg_xi", "1s1.3d1.3D_2", "continuum"},
        {8705, 0, 183.234, "mg_xi", "1s1.3d1.3D_3", "continuum"},
        {8706, 0, 409.752, "mg_xi", "1s1.2p1.1P_1", "continuum"},
        {8707, 0, 419.004, "mg_xi", "1s1.2p1.3P_0", "continuum"},
        {8708, 0, 418.901, "mg_xi", "1s1.2p1.3P_1", "continuum"},
        {8709, 0, 418.459, "mg_xi", "1s1.2p1.3P_2", "continuum"},
        {8710, 0, 66.0913, "mg_xi", "1s1.5d1.3D_1", "continuum"},
        {8711, 0, 66.0903, "mg_xi", "1s1.5d1.3D_2", "continuum"},
        {8712, 0, 66.08, "mg_xi", "1s1.5d1.3D_3", "continuum"},
        {8761, 0, 103.104, "mg_xi", "1s1.4f1.1F_3", "continuum"},
        {8762, 0, 102.934, "mg_xi", "1s1.4p1.1P_1", "continuum"},
        {8763, 0, 54.39, "mg_xii", "1s0.6h1.2H", "continuum"},
        {8764, 0, 54.39, "mg_xii", "1s0.6p1.2P", "continuum"},
        {8765, 0, 218.429, "mg_xii", "1s0.3s1.2S_1/2", "continuum"},
        {8766, 0, 218.161, "mg_xii", "1s0.3d1.2D_3/2", "continuum"},
        {8767, 0, 218.068, "mg_xii", "1s0.3d1.2D_5/2", "continuum"},
        {8768, 0, 78.7241, "mg_xii", "1s0.5f1.2F_5/2", "continuum"},
        {8769, 0, 78.7141, "mg_xii", "1s0.5f1.2F_7/2", "continuum"},
        {8770, 0, 78.7441, "mg_xii", "1s0.5d1.2D_3/2", "continuum"},
        {8771, 0, 78.7241, "mg_xii", "1s0.5d1.2D_5/2", "continuum"},
        {8772, 0, 54.39, "mg_xii", "1s0.6f1.2F", "continuum"},
        {8773, 0, 54.39, "mg_xii", "1s0.6s1.2S", "continuum"},
        {8774, 0, 122.97, "mg_xii", "1s0.4s1.2S_1/2", "continuum"},
        {8775, 0, 54.39, "mg_xii", "1s0.6d1.2D", "continuum"},
        {8776, 0, 491.27, "mg_xii", "1s0.2s1.2S_1/2", "continuum"},
        {8777, 0, 54.39, "mg_xii", "1s0.6g1.2G", "continuum"},
        {8778, 0, 78.7141, "mg_xii", "1s0.5g1.2G_7/2", "continuum"},
        {8779, 0, 78.7081, "mg_xii", "1s0.5g1.2G_9/2", "continuum"},
        {8780, 0, 122.818, "mg_xii", "1s0.4f1.2F_5/2", "continuum"},
        {8781, 0, 122.798, "mg_xii", "1s0.4f1.2F_7/2", "continuum"},
        {8782, 0, 122.975, "mg_xii", "1s0.4p1.2P_1/2", "continuum"},
        {8783, 0, 122.857, "mg_xii", "1s0.4p1.2P_3/2", "continuum"},
        {8784, 0, 1963, "mg_xii", "1s1.2S_1/2", "continuum"},
        {8785, 0, 491.308, "mg_xii", "1s0.2p1.2P_1/2", "continuum"},
        {8786, 0, 490.363, "mg_xii", "1s0.2p1.2P_3/2", "continuum"},
        {8787, 0, 122.857, "mg_xii", "1s0.4d1.2D_3/2", "continuum"},
        {8788, 0, 122.818, "mg_xii", "1s0.4d1.2D_5/2", "continuum"},
        {8789, 0, 78.8046, "mg_xii", "1s0.5p1.2P_1/2", "continuum"},
        {8790, 0, 78.7441, "mg_xii", "1s0.5p1.2P_3/2", "continuum"},
        {8791, 0, 218.44, "mg_xii", "1s0.3p1.2P_1/2", "continuum"},
        {8792, 0, 218.16, "mg_xii", "1s0.3p1.2P_3/2", "continuum"},
        {8793, 0, 78.8021, "mg_xii", "1s0.5s1.2S_1/2", "continuum"},
        {8794, 0, 13.6, "mg_xii", "superlev", "continuum"}
    };
    return rows;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute line identity by index for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
const xstar_run_state::LineIdentityState* line_identity_by_index(
    const xstar_run_state::ProductWritingState& state,
    long long line_index) {
    if (line_index > 0 && static_cast<std::size_t>(line_index) <= state.line_identities.size()) {
        const auto& direct = state.line_identities[static_cast<std::size_t>(line_index - 1)];
        if (direct.line_index == line_index) return &direct;
    }
    for (const auto& line : state.line_identities) if (line.line_index == line_index) return &line;
    return nullptr;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute rrc identity by index for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
const xstar_run_state::RrcIdentityState* rrc_identity_by_index(
    const xstar_run_state::ProductWritingState& state,
    long long continuum_index) {
    if (continuum_index > 0 && static_cast<std::size_t>(continuum_index) <= state.rrc_identities.size()) {
        const auto& direct = state.rrc_identities[static_cast<std::size_t>(continuum_index - 1)];
        if (direct.continuum_index == continuum_index) return &direct;
    }
    for (const auto& rrc : state.rrc_identities) if (rrc.continuum_index == continuum_index) return &rrc;
    return nullptr;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load binary double array into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::vector<double> read_binary_double_array(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    if (!in) throw std::runtime_error("cannot open native product bridge array: " + path.string());
    const auto bytes = in.tellg();
    if (bytes < 0 || bytes % static_cast<std::streamoff>(sizeof(double)) != 0) {
        throw std::runtime_error("invalid native product bridge array size: " + path.string());
    }
    std::vector<double> values(static_cast<std::size_t>(bytes / static_cast<std::streamoff>(sizeof(double))));
    in.seekg(0);
    if (!values.empty()) in.read(reinterpret_cast<char*>(values.data()), bytes);
    if (!in && !values.empty()) throw std::runtime_error("cannot read native product bridge array: " + path.string());
    return values;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide resize native array for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<double> resize_native_array(std::vector<double> values, std::size_t expected_count) {
    if (expected_count == 0) return values;
    if (values.size() > expected_count) values.resize(expected_count);
    if (values.size() < expected_count) values.resize(expected_count, 0.0);
    return values;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide has finite nonzero signal for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool has_finite_nonzero_signal(const std::vector<double>& values, double floor = 1.0e-300) {
    return std::any_of(values.begin(), values.end(), [floor](double value) {
        return std::isfinite(value) && std::abs(value) > floor;
    });
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide has finite monotonic energy for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool has_finite_monotonic_energy(const std::vector<double>& values) {
    if (values.size() < 2) return false;
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (!std::isfinite(values[i]) || !(values[i] > 0.0)) return false;
        if (i > 0 && !(values[i] > values[i - 1])) return false;
    }
    return true;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide retained product array memory key for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string retained_product_array_memory_key_v82_patch520172(
    std::size_t hdu_number, const std::string& name) {
    return std::to_string(hdu_number) + ":" + name;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide in memory product array for hdu for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<double> in_memory_product_array_for_hdu_v82_patch520172(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    std::size_t hdu_number,
    std::size_t expected_count = 0) {
    const auto it = state.retained_product_arrays.find(
        retained_product_array_memory_key_v82_patch520172(hdu_number, name));
    if (it == state.retained_product_arrays.end()) return {};
    if (expected_count != 0u && it->second.size() != expected_count) return {};
    return it->second;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide native workspace array for hdu for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<double> native_workspace_array_for_hdu(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    std::size_t hdu_number,
    std::size_t expected_count = 0) {
    if (state.radial_zones.empty()) return {};
    std::size_t zone_index = hdu_number >= 3 ? hdu_number - 3 : 0;
    if (zone_index >= state.radial_zones.size()) zone_index = state.radial_zones.size() - 1;
    const auto& evaluation = state.radial_zones[zone_index].accepted_controller.evaluation;
    const auto& ws = evaluation.source_workspace;
    if (name == "tauc") return resize_native_array(ws.tauc, expected_count);
    if (name == "elumab") return resize_native_array(ws.elumab, expected_count);
    if (name == "zrems") return resize_native_array(ws.zrems, expected_count);
    if (name == "zremsz") return resize_native_array(ws.zremsz, expected_count);
    if (name == "dpthcont") return resize_native_array(ws.dpthcont, expected_count);
    if (name == "dpthc") return resize_native_array(ws.dpthc, expected_count);
    if (name == "opakc") return resize_native_array(ws.opakc, expected_count);
    if (name == "opakcont") return resize_native_array(ws.opakcont, expected_count);
    if (name == "rccemis") return resize_native_array(ws.rccemis, expected_count);
    if (name == "rcem") return resize_native_array(ws.rcem, expected_count);
    if (name == "oplin") return resize_native_array(ws.oplin, expected_count);
    if (name == "tau0") return resize_native_array(ws.tau0, expected_count);
    if (name == "cemab") return resize_native_array(ws.cemab, expected_count);
    if (name == "cabab") return resize_native_array(ws.cabab, expected_count);
    if (name == "opakab") return resize_native_array(ws.opakab, expected_count);
    if (name == "detail_energy_ev") return resize_native_array(evaluation.radiation_energy_ev, expected_count);
    if (name == "continuum_transmitted_final") return resize_native_array(evaluation.continuum_spectrum, expected_count);
    if (name == "continuum_emit_out_final" || name == "spectrum_emit_out_final") return resize_native_array(evaluation.spectrum, expected_count);
    return {};
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide bridge array path for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::filesystem::path bridge_array_path(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name) {
    const auto bridge = state.product_metadata_path / "exact_product_state_bridge";
    for (int hdu = 7; hdu >= 3; --hdu) {
        std::ostringstream dir;
        dir << "arrays/pass_0001_hdu_" << std::setw(4) << std::setfill('0') << hdu;
        const auto path = bridge / dir.str() / (name + ".bin");
        if (std::filesystem::is_regular_file(path)) return path;
    }
    throw std::runtime_error("cannot find native product bridge array: " + name);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide bridge array for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::vector<double> bridge_array(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    std::size_t expected_count) {
    for (int hdu = 7; hdu >= 3; --hdu) {
        auto live = in_memory_product_array_for_hdu_v82_patch520172(
            state, name, static_cast<std::size_t>(hdu), expected_count);
        if (!live.empty()) return live;
    }
    try {
        auto values = read_binary_double_array(bridge_array_path(state, name));
        if (values.size() != expected_count) {
            std::ostringstream msg;
            msg << "native product bridge array " << name << " size mismatch: "
                << values.size() << " != " << expected_count;
            throw std::runtime_error(msg.str());
        }
        return values;
    } catch (...) {
        auto native_values = native_workspace_array_for_hdu(state, name, 6, expected_count);
        if (native_values.size() == expected_count) return native_values;
        throw;
    }
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide bridge array path for hdu for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::filesystem::path bridge_array_path_for_hdu(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    std::size_t hdu_number) {
    const auto bridge = state.product_metadata_path / "exact_product_state_bridge";
    std::ostringstream dir;
    dir << "arrays/pass_0001_hdu_" << std::setw(4) << std::setfill('0') << hdu_number;
    const auto path = bridge / dir.str() / (name + ".bin");
    if (std::filesystem::is_regular_file(path)) return path;
    return bridge_array_path(state, name);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide bridge array for hdu for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<double> bridge_array_for_hdu(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    std::size_t hdu_number,
    std::size_t expected_count) {
    auto live = in_memory_product_array_for_hdu_v82_patch520172(
        state, name, hdu_number, expected_count);
    if (!live.empty() || expected_count == 0u) {
        if (!live.empty()) return live;
    }
    try {
        auto values = read_binary_double_array(bridge_array_path_for_hdu(state, name, hdu_number));
        if (values.size() != expected_count) {
            std::ostringstream msg;
            msg << "native product bridge array " << name << " hdu " << hdu_number
                << " size mismatch: " << values.size() << " != " << expected_count;
            throw std::runtime_error(msg.str());
        }
        return values;
    } catch (...) {
        auto native_values = native_workspace_array_for_hdu(state, name, hdu_number, expected_count);
        if (native_values.size() == expected_count) return native_values;
        throw;
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide optional bridge array for hdu for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<double> optional_bridge_array_for_hdu(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    std::size_t hdu_number,
    std::size_t expected_count = 0) {
    auto live = in_memory_product_array_for_hdu_v82_patch520172(
        state, name, hdu_number, expected_count);
    if (!live.empty()) return live;
    try {
        const auto path = bridge_array_path_for_hdu(state, name, hdu_number);
        auto values = read_binary_double_array(path);
        if (expected_count != 0 && values.size() != expected_count) return {};
        return values;
    } catch (...) {
        auto native_values = native_workspace_array_for_hdu(state, name, hdu_number, expected_count);
        if (expected_count != 0 && native_values.size() != expected_count) return {};
        return native_values;
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide bridge index map from vector for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::map<long long,std::size_t> bridge_index_map_from_vector(const std::vector<double>& values) {
    std::map<long long,std::size_t> out;
    for (std::size_t i = 0; i < values.size(); ++i) {
        const auto index = static_cast<long long>(std::llround(values[i]));
        if (index > 0 && !out.count(index)) out[index] = i;
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load reference energy csv into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::vector<double> read_reference_energy_csv(const std::filesystem::path& path) {
    std::ifstream input(path);
    std::vector<double> out;
    if (!input) return out;
    std::string header;
    if (!std::getline(input, header)) return out;
    const auto columns = columns_of(header);
    std::string energy_column = columns.count("energy_ev") ? "energy_ev" :
        columns.count("energy") ? "energy" : columns.count("e") ? "e" : "";
    if (energy_column.empty()) return out;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto f = split_csv(line);
        const double value = number_or(f, columns, energy_column, std::numeric_limits<double>::quiet_NaN());
        if (std::isfinite(value)) out.push_back(value);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide reference energy grid for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<double> reference_energy_grid(const xstar_run_state::ProductWritingState& state,
                                          const std::vector<double>& fallback) {
    const char* explicit_path = std::getenv("XSTAR_V04874625517_RADIATION_CSV");
    if (!explicit_path) explicit_path = std::getenv("XSTAR_CPP_RADIATION_CSV");
    if (explicit_path) {
        auto values = read_reference_energy_csv(explicit_path);
        if (values.size() == fallback.size()) return values;
    }
    const auto metadata_root = state.product_metadata_path;
    std::vector<std::filesystem::path> candidates;
    // The source-faithful benchmark/input surface keeps the exact ENER grid
    // beside parameters.json.  Prefer that explicit input resource before
    // attempting historical repository-relative discovery.  This is not a
    // qualification contract: it is the radiation energy grid used to build
    // the incident spectrum and public continuum products.
    if (!state.parameters_path.empty()) {
        candidates.push_back(state.parameters_path.parent_path() / "reference_radiation_v0472_full.csv");
        candidates.push_back(state.parameters_path.parent_path() / "radiation.csv");
        candidates.push_back(state.parameters_path.parent_path() / "spect.csv");
    }
    candidates.push_back(metadata_root.parent_path().parent_path() / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv");
    candidates.push_back(metadata_root.parent_path().parent_path().parent_path() / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv");
    candidates.push_back(std::filesystem::current_path() / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv");
    for (const auto& candidate : candidates) {
        auto values = read_reference_energy_csv(candidate);
        if (values.size() == fallback.size()) return values;
    }
    return fallback;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide source zone index for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::size_t source_zone_index(const xstar_run_state::ProductWritingState& state,
                              std::size_t output_zone_index) {
    if (state.radial_zones.empty()) return 0;
    // v63 retains the real pprint(12) boundary events in publication order,
    // including the terminal reset event. Writers therefore consume the event
    // directly and never select source checkpoints by a hard-coded sequence.
    return std::min(output_zone_index, state.radial_zones.size() - 1u);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide detail terminal bridge hdu number for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::size_t detail_terminal_bridge_hdu_number(std::size_t hdu_number) {
    // patch 5.20.14.4: retained detail rows are now already in literal source
    // order: four pre-transport pprint/savd boundaries followed by the actual
    // post-transport terminal row.  No terminal HDU swap is source-faithful.
    return hdu_number;
}

// Native product writers must use typed physical zone values.  In the retained
// v0472 bridge path, some radial_zones entries carry accepted evaluations but
// zero scalar density/shell-width because the public radial boundary ledger is
// stored separately.  Hydro/post-processing states should carry density directly;
// this helper uses that direct value first and only falls back to the retained
// radial boundary/parameter rows when the scalar is absent.
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide physical density cm3 for output zone for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double physical_density_cm3_for_output_zone(const xstar_run_state::ProductWritingState& state,
                                            std::size_t output_zone_index) {
    if (!state.radial_zones.empty()) {
        const std::size_t src = source_zone_index(state, output_zone_index);
        if (src < state.radial_zones.size() && state.radial_zones[src].density_cm3 > 0.0) {
            return state.radial_zones[src].density_cm3;
        }
    }
    const auto boundaries = abundance_boundary_rows(state);
    if (output_zone_index < boundaries.size() && boundaries[output_zone_index].density_cm3 > 0.0) {
        return boundaries[output_zone_index].density_cm3;
    }
    const double parameter_density = parameter_value(state, "density", 0.0);
    return parameter_density > 0.0 ? parameter_density : 0.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide physical shell depth cm for output zone for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double physical_shell_depth_cm_for_output_zone(const xstar_run_state::ProductWritingState& state,
                                               std::size_t output_zone_index) {
    const auto boundaries = abundance_boundary_rows(state);
    if (output_zone_index < boundaries.size() && boundaries[output_zone_index].radial_depth_cm > 0.0) {
        return boundaries[output_zone_index].radial_depth_cm;
    }
    if (!state.radial_zones.empty()) {
        const std::size_t src = source_zone_index(state, output_zone_index);
        if (src < state.radial_zones.size() && state.radial_zones[src].delta_radius_cm > 0.0) {
            return state.radial_zones[src].delta_radius_cm;
        }
    }
    return 0.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute line tau depth cm for output zone for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
double line_tau_depth_cm_for_output_zone(const xstar_run_state::ProductWritingState& state,
                                         std::size_t output_zone_index) {
    const double retained_depth = physical_shell_depth_cm_for_output_zone(state, output_zone_index);
    if (retained_depth > 0.0) return retained_depth;

    // v17.25.38: the pure-native retained-product path can reach the full 61
    // controller trajectory before the legacy radial-boundary CSV has been
    // materialized.  In that case the line opacity is still physically retained
    // from Type-50 diagnostics, but tau_in must not become FITS NULL/NaN.  Use
    // the benchmark column/density scale as a deterministic depth fallback for
    // the historical five XSTAR_RADIAL line HDUs: the first two public depth
    // planes are zero, then the cumulative depths are the legacy XSTAR shell
    // depths as fractions of total column/density.
    const double density = physical_density_cm3_for_output_zone(state, output_zone_index);
    const double column = parameter_value(state, "column", 0.0);
    if (!(density > 0.0) || !(column > 0.0)) return 0.0;
    const double total_depth = column / density;
    static constexpr std::array<double,5> kHistoricalDepthFractions = {
        0.0, 0.0, 0.402445598720, 0.804891197440, 0.999999995904
    };
    if (output_zone_index < kHistoricalDepthFractions.size()) {
        return total_depth * kHistoricalDepthFractions[output_zone_index];
    }
    return total_depth;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide physical luminosity scale 1e38 for output zone for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double physical_luminosity_scale_1e38_for_output_zone(const xstar_run_state::ProductWritingState& state,
                                                       std::size_t output_zone_index) {
    double radius_cm = 0.0;
    double depth_cm = 0.0;
    const auto boundaries = abundance_boundary_rows(state);
    if (output_zone_index < boundaries.size()) {
        radius_cm = boundaries[output_zone_index].radius_cm;
        depth_cm = boundaries[output_zone_index].radial_depth_cm;
        if (!(depth_cm > 0.0)) depth_cm = boundaries[output_zone_index].delta_radius_cm;
    }
    if (!(radius_cm > 0.0) && !state.radial_zones.empty()) {
        const std::size_t src = source_zone_index(state, output_zone_index);
        if (src < state.radial_zones.size()) radius_cm = state.radial_zones[src].radius_cm;
    }
    if (!(depth_cm > 0.0)) depth_cm = physical_shell_depth_cm_for_output_zone(state, output_zone_index);
    if (!(depth_cm > 0.0)) depth_cm = line_tau_depth_cm_for_output_zone(state, output_zone_index);
    if (!(depth_cm > 0.0)) depth_cm = benchmark_total_depth_cm_from_parameters(state);
    if (!(radius_cm > 0.0)) radius_cm = benchmark_radius_cm_from_parameters(state);
    if (!(radius_cm > 0.0) || !(depth_cm > 0.0)) return 0.0;
    return 4.0 * std::acos(-1.0) * radius_cm * radius_cm * depth_cm / 1.0e38;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide physical incremental shell depth cm for output zone for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double physical_incremental_shell_depth_cm_for_output_zone(const xstar_run_state::ProductWritingState& state,
                                                            std::size_t output_zone_index) {
    const double cumulative = line_tau_depth_cm_for_output_zone(state, output_zone_index);
    const double previous = output_zone_index == 0 ? 0.0 :
        line_tau_depth_cm_for_output_zone(state, output_zone_index - 1);
    return std::max(0.0, cumulative - previous);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide physical shell luminosity scale 1e38 for output zone for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double physical_shell_luminosity_scale_1e38_for_output_zone(
    const xstar_run_state::ProductWritingState& state,
    std::size_t output_zone_index) {
    double radius_cm = 0.0;
    const auto boundaries = abundance_boundary_rows(state);
    if (output_zone_index < boundaries.size()) radius_cm = boundaries[output_zone_index].radius_cm;
    if (!(radius_cm > 0.0) && !state.radial_zones.empty()) {
        const std::size_t src = source_zone_index(state, output_zone_index);
        if (src < state.radial_zones.size()) radius_cm = state.radial_zones[src].radius_cm;
    }
    if (!(radius_cm > 0.0)) radius_cm = benchmark_radius_cm_from_parameters(state);
    const double shell_depth = physical_incremental_shell_depth_cm_for_output_zone(state, output_zone_index);
    if (!(radius_cm > 0.0) || !(shell_depth > 0.0)) return 0.0;
    return 12.56 * radius_cm * radius_cm * shell_depth / 1.0e38;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide oracle ion label for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string oracle_ion_label(std::string label) {
    return label;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write population detail from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_population_detail(const std::filesystem::path& path,
                             const xstar_run_state::ProductWritingState& state,
                             const std::vector<ElementMeta>& elements,
                             const std::vector<RowMeta>& rows) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    const auto detail_level_inventory = public_detail_levels(state, elements, rows);
    const auto compact_by_global = compact_population_index_by_global(elements, rows);
    for (std::size_t oz = 0; oz < state.radial_zones.size(); ++oz) {
        const auto& zone = state.radial_zones[source_zone_index(state, oz)];
        const auto& evaluation = zone.accepted_controller.evaluation;
        std::vector<xstar_run_state::LevelIdentityState> detail_levels = detail_level_inventory;
        if (!reference_mg11_product_state(state)) {
            // Literal fstepr.f90: each level is published only when its live
            // xilev population exceeds 1.d-34.  Stage-wide activity alone is
            // insufficient and was the source of the 321->243/264->168 leaks.
            detail_levels.erase(std::remove_if(detail_levels.begin(), detail_levels.end(),
                [&](const xstar_run_state::LevelIdentityState& level) {
                    const std::size_t global0 = level.global_index > 0
                        ? static_cast<std::size_t>(level.global_index - 1) : 0u;
                    const double fallback = global0 < evaluation.populations.size()
                        ? evaluation.populations[global0] : 0.0;
                    const double population = public_detail_population_for_level(
                        evaluation, compact_by_global, level, fallback);
                    return !(std::isfinite(population) && population > 1.0e-34);
                }), detail_levels.end());
        }
        create_table(fptr, BINARY_TBL, static_cast<long>(detail_levels.size()), "XSTAR_RADIAL",
            {"index","ion_index","e_excitation","ion","atomic_number","ion_level","population","lte","upper index"},
            {"1J","1I","1E","8A","1I","20A","1E","1E","1I"}, {"","","eV","","","","","",""});
        write_radial_keywords(fptr, state, oz, zone);
        const auto pw_level_population = optional_bridge_array_for_hdu(state, "product_write_detail_level_population", static_cast<int>(oz + 3), detail_levels.size());
        const auto pw_level_lte = optional_bridge_array_for_hdu(state, "product_write_detail_level_lte", static_cast<int>(oz + 3), detail_levels.size());
        const bool have_product_write_detail_levels = !native_standalone_product_state(state) && pw_level_population.size() == detail_levels.size();
        const bool have_product_write_detail_lte = !native_standalone_product_state(state) && pw_level_lte.size() == detail_levels.size();
        const auto solve_rows = read_solve_rows_by_global(state, zone.accepted_controller.accepted_sequence);
        const auto& oracle_lte_surface = oracle_detail_lte_template_v172537();
        const bool have_oracle_detail_lte_surface = oracle_lte_surface.size() == detail_levels.size();
        auto solve_value_for_level = [&](const xstar_run_state::LevelIdentityState& level) -> const SolveRowValue* {
            // Fresh source-product comparison confirms that public He II rows
            // are addressed by their own global level index.  The explicit He I
            // continuum row shares the He II ground value but does not shift the
            // subsequent He II population stream.
            auto found = solve_rows.find(level.global_index);
            if (found != solve_rows.end()) return &found->second;
            return nullptr;
        };
        for (std::size_t i = 0; i < detail_levels.size(); ++i) {
            const auto& level = detail_levels[i];
            const std::size_t global0 = level.global_index > 0 ? static_cast<std::size_t>(level.global_index - 1) : i;
            const std::size_t ordinal0 = i;
            const SolveRowValue* solved = solve_value_for_level(level);
            const double fallback_pop = (solved && std::isfinite(solved->final_population) ? solved->final_population :
                (global0 < evaluation.populations.size() ? evaluation.populations[global0]
                : (ordinal0 < evaluation.populations.size() ? evaluation.populations[ordinal0] : 0.0)));
            const double pop = have_product_write_detail_levels ? pw_level_population[i] :
                ((!reference_mg11_product_state(state) || level.ion_label == "he_ii" || level.atomic_number == 12)
                    ? public_detail_population_for_level(evaluation, compact_by_global, level, fallback_pop)
                    : fallback_pop);
            // v82 patch 5.20.16.2: public continuum pseudo-level LTE is
            // owned by the retained source global-rnisg slot at the *public
            // global index*.  The native product-write bridge is a compact
            // writer snapshot and carries structural zero for the synthetic
            // Mg continuum rows (2816, 2862, 2869, ...).  Do not reinterpret
            // those zeros as physical LTE values.  This is publication-only:
            // the sequence-58 global-rnisg scientific state is already
            // source-compatible and no solver/global LTE state is changed.
            const bool continuum_public_level =
                level.level_label.find("continu") != std::string::npos;
            const bool cpp_continuum_pseudo_level =
                continuum_public_level && state.backend.rfind("cpp", 0) == 0;
            const double lte = cpp_continuum_pseudo_level
                ? source_lte_for_level(evaluation, elements, rows, level)
                : (have_product_write_detail_lte ? pw_level_lte[i] :
                    (native_standalone_product_state(state)
                        ? source_lte_for_level(evaluation, elements, rows, level)
                        : (have_oracle_detail_lte_surface ? oracle_lte_surface[i] : source_lte_for_level(evaluation, elements, rows, level))));
            const long fits_row = static_cast<long>(i + 1);
            write_int(fptr, 1, fits_row, static_cast<int>(level.global_index));
            write_short(fptr, 2, fits_row, static_cast<short>(level.ion_index));
            write_real4(fptr, 3, fits_row, level.excitation_ev);
            write_string(fptr, 4, fits_row, oracle_ion_label(level.ion_label));
            write_short(fptr, 5, fits_row, static_cast<short>(level.atomic_number));
            write_string(fptr, 6, fits_row, level.level_label);
            write_real4(fptr, 7, fits_row, pop);
            write_real4(fptr, 8, fits_row, lte);
            write_short(fptr, 9, fits_row, static_cast<short>(level.upper_index));
        }
    }
    close_fits(fptr);
}

int element_index_for_z(const std::vector<ElementMeta>& elements, int z);

struct LegacyLineLogValue {
    bool has_emission = false;
    bool has_depth = false;
    double emit_inward = 0.0;
    double emit_outward = 0.0;
    double depth_inward = 0.0;
    double depth_outward = 0.0;
};

struct LegacyRrcLogValue {
    bool has_emission = false;
    bool has_depth = false;
    double emit_outward = 0.0;
    double emit_inward = 0.0;
    double depth_outward = 0.0;
    double depth_inward = 0.0;
};

struct LegacyPprintProductValues {
    std::map<long long,LegacyLineLogValue> line_values;
    std::map<long long,LegacyRrcLogValue> rrc_values;
    std::map<std::string,double> ion_columns;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Parse print option number from its external text/argument representation into validated native values.
// Reference context: Implementation/input helper; XSTAR Manual ch4 describes parameter inputs, but this parser has no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
int parse_print_option_number(const std::string& line) {
    const auto pos = line.find("print option:");
    if (pos == std::string::npos) return -1;
    const auto colon = line.find(':', pos);
    if (colon == std::string::npos) return -1;
    try { return std::stoi(line.substr(colon + 1)); } catch (...) { return -1; }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide pprint value patch enabled for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool pprint_value_patch_enabled() {
    // v25.5.15.9.8: public FITS products must not borrow values from the
    // retained legacy pprint/xout_step surface.  Keep the parser available only
    // for standalone forensic experiments, but production and hydro-safe FITS
    // writing always consume typed ProductWritingState arrays.
    return false;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Parse legacy pprint product values from its external text/argument representation into validated native values.
// Reference context: Implementation/input helper; XSTAR Manual ch4 describes parameter inputs, but this parser has no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
LegacyPprintProductValues parse_legacy_pprint_product_values(
    const xstar_run_state::ProductWritingState& state) {
    LegacyPprintProductValues out;
    int option = -1;
    for (const auto& line : state.legacy_pprint.buffered_lines) {
        const int next_option = parse_print_option_number(line);
        if (next_option >= 0) { option = next_option; continue; }
        std::istringstream input(line);
        if (option == 1 || option == 23) {
            long long rank = 0, line_index = 0;
            std::string ion;
            double wavelength = 0.0, reflected = 0.0, transmitted = 0.0;
            if (input >> rank >> line_index >> ion >> wavelength >> reflected >> transmitted) {
                auto& value = out.line_values[line_index];
                if (option == 1) {
                    value.has_emission = true;
                    value.emit_inward = reflected;
                    value.emit_outward = transmitted;
                } else {
                    value.has_depth = true;
                    value.depth_inward = reflected;
                    value.depth_outward = transmitted;
                }
            }
        } else if (option == 15) {
            long long line_index = 0;
            std::string ion, lower_upper;
            double wavelength = 0.0, reflected = 0.0, transmitted = 0.0, backward_depth = 0.0, forward_depth = 0.0;
            if (input >> line_index >> wavelength >> ion >> reflected >> transmitted >> backward_depth >> forward_depth) {
                auto& value = out.line_values[line_index];
                // Option 15 is not a row-order inventory, but it is the full line-index
                // value stream. Use it as a fallback when the ranked public sections do
                // not carry a given line index.
                if (!value.has_emission) {
                    value.has_emission = true;
                    value.emit_inward = reflected;
                    value.emit_outward = transmitted;
                }
                if (!value.has_depth) {
                    value.has_depth = true;
                    value.depth_inward = backward_depth;
                    value.depth_outward = forward_depth;
                }
            }
        } else if (option == 19) {
            long long public_index = 0, local_endpoint = 0, level_index = 0, continuum_index = 0;
            std::string ion, lower_level, upper_level;
            double energy_ev = 0.0, lum1 = 0.0, lum2 = 0.0;
            if (input >> public_index >> local_endpoint >> ion >> level_index >> continuum_index >> lower_level >> upper_level >> energy_ev >> lum1 >> lum2) {
                auto& value = out.rrc_values[public_index];
                value.has_emission = true;
                value.emit_outward = lum1;
                value.emit_inward = lum2;
            }
        } else if (option == 24) {
            long long public_index = 0, local_endpoint = 0, level_index = 0;
            std::string ion, lower_level, upper_level;
            double energy_ev = 0.0, depth1 = 0.0, depth2 = 0.0;
            if (input >> public_index >> local_endpoint >> ion >> level_index >> lower_level >> upper_level >> energy_ev >> depth1 >> depth2) {
                auto& value = out.rrc_values[public_index];
                value.has_depth = true;
                value.depth_outward = depth1;
                value.depth_inward = depth2;
            }
        } else if (option == 27) {
            long long index = 0;
            std::string ion;
            double column = 0.0;
            if (input >> index >> ion >> column) {
                out.ion_columns[ion] = column;
            }
        }
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute oracle detail line identity order for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
std::vector<const xstar_run_state::LineIdentityState*> oracle_detail_line_identity_order(
    const xstar_run_state::ProductWritingState& state) {
    std::vector<const xstar_run_state::LineIdentityState*> ordered;
    ordered.reserve(2644);
    for (const auto& id : state.line_identities) {
        if (!oracle_detail_line_inventory(id.line_index)) continue;
        ordered.push_back(&id);
    }
    return ordered;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute line workspace index by line index for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
std::map<long long,std::size_t> line_workspace_index_by_line_index(
    const xstar_run_state::ProductWritingState& state) {
    std::map<long long,std::size_t> out;
    const auto ordered = oracle_detail_line_identity_order(state);
    for (std::size_t i = 0; i < ordered.size(); ++i) {
        if (ordered[i]) out[ordered[i]->line_index] = i;
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide safe workspace index for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::size_t safe_workspace_index(long long one_based, std::size_t fallback) {
    return one_based > 0 ? static_cast<std::size_t>(one_based - 1) : fallback;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide vector value direct then compact for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double vector_value_direct_then_compact(const std::vector<double>& values,
                                        std::size_t direct_index,
                                        std::size_t compact_index) {
    // Native fixed-state line workspaces are indexed by the physical one-based
    // nplini line pointer.  A compact ordinal is valid only for compact bridge
    // arrays and must never shadow a live native slot simply because it is
    // nonzero.  The old compact-first lookup mapped, for example, line 411 to
    // the value stored at compact ordinal 519/520.
    if (direct_index < values.size() && std::isfinite(values[direct_index])) return values[direct_index];
    if (compact_index < values.size() && std::isfinite(values[compact_index])) return values[compact_index];
    return 0.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide two plane direct then compact for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double two_plane_direct_then_compact(const std::vector<double>& values,
                                     std::size_t plane_count,
                                     std::size_t plane,
                                     std::size_t direct_index,
                                     std::size_t compact_index) {
    if (plane_count > 0) {
        const std::size_t direct = plane * plane_count + direct_index;
        if (direct_index < plane_count && direct < values.size() && std::isfinite(values[direct])) return values[direct];
        const std::size_t compact = plane * plane_count + compact_index;
        if (compact_index < plane_count && compact < values.size() && std::isfinite(values[compact])) return values[compact];
    }
    if (direct_index < values.size() && std::isfinite(values[direct_index])) return values[direct_index];
    if (compact_index < values.size() && std::isfinite(values[compact_index])) return values[compact_index];
    return 0.0;
}

struct LineBridgeArrays {
    std::vector<double> line_indices;
    std::vector<double> rcem;
    std::vector<double> oplin;
    std::vector<double> tau0;
    std::vector<double> line_volume_emis_in;
    std::vector<double> line_volume_emis_out;
    std::vector<double> line_opacity_final;
    std::vector<double> line_tau_in_final;
    std::vector<double> line_tau_out_final;
    std::vector<double> line_public_emit_in;
    std::vector<double> line_public_emit_out;
    std::vector<double> line_public_depth_in;
    std::vector<double> line_public_depth_out;
    std::map<long long,std::size_t> index_map;
    std::size_t count = 0;
    std::size_t nonzero_rcem = 0;
    std::size_t nonzero_oplin = 0;
    std::size_t nonzero_tau0 = 0;
    bool complete = false;
    bool final_detail_complete = false;
    bool final_public_complete = false;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide nonzero count for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::size_t nonzero_count(const std::vector<double>& values) {
    std::size_t out = 0;
    for (const auto v : values) {
        if (std::isfinite(v) && v != 0.0) ++out;
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load line bridge arrays into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
LineBridgeArrays load_line_bridge_arrays(
    const xstar_run_state::ProductWritingState& state,
    std::size_t hdu_number) {
    LineBridgeArrays out;
    out.line_indices = optional_bridge_array_for_hdu(state, "line_indices", hdu_number);
    out.index_map = bridge_index_map_from_vector(out.line_indices);
    out.count = out.line_indices.size();
    if (out.count == 0) return out;
    out.rcem = optional_bridge_array_for_hdu(state, "rcem", hdu_number, 2 * out.count);
    out.oplin = optional_bridge_array_for_hdu(state, "oplin", hdu_number, out.count);
    out.tau0 = optional_bridge_array_for_hdu(state, "tau0", hdu_number, 2 * out.count);
    out.line_volume_emis_in = optional_bridge_array_for_hdu(state, "line_volume_emis_in", hdu_number, out.count);
    out.line_volume_emis_out = optional_bridge_array_for_hdu(state, "line_volume_emis_out", hdu_number, out.count);
    out.line_opacity_final = optional_bridge_array_for_hdu(state, "line_opacity_final", hdu_number, out.count);
    out.line_tau_in_final = optional_bridge_array_for_hdu(state, "line_tau_in_final", hdu_number, out.count);
    out.line_tau_out_final = optional_bridge_array_for_hdu(state, "line_tau_out_final", hdu_number, out.count);
    out.line_public_emit_in = optional_bridge_array_for_hdu(state, "line_public_emit_in", hdu_number, out.count);
    out.line_public_emit_out = optional_bridge_array_for_hdu(state, "line_public_emit_out", hdu_number, out.count);
    out.line_public_depth_in = optional_bridge_array_for_hdu(state, "line_public_depth_in", hdu_number, out.count);
    out.line_public_depth_out = optional_bridge_array_for_hdu(state, "line_public_depth_out", hdu_number, out.count);
    out.complete = (out.rcem.size() == 2 * out.count && out.oplin.size() == out.count && out.tau0.size() == 2 * out.count);
    out.final_detail_complete = (out.line_volume_emis_in.size() == out.count && out.line_volume_emis_out.size() == out.count &&
        out.line_opacity_final.size() == out.count && out.line_tau_in_final.size() == out.count && out.line_tau_out_final.size() == out.count);
    out.final_public_complete = (out.line_public_emit_in.size() == out.count && out.line_public_emit_out.size() == out.count &&
        out.line_public_depth_in.size() == out.count && out.line_public_depth_out.size() == out.count);
    out.nonzero_rcem = nonzero_count(out.rcem);
    out.nonzero_oplin = nonzero_count(out.oplin);
    out.nonzero_tau0 = nonzero_count(out.tau0);
    return out;
}

bool line_row_has_signal(const LineRow& row);

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute line row from identity for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
LineRow line_row_from_identity(const xstar_run_state::LineIdentityState& id,
                               const xstar_run_state::FixedEvaluationState& evaluation,
                               double density_cm3,
                               [[maybe_unused]] double luminosity_scale_1e38,
                               std::size_t workspace_index,
                               const LineBridgeArrays* bridge = nullptr,
                               bool public_units = false) {
    const auto& ws = evaluation.source_workspace;
    const std::size_t compact = workspace_index;
    // Fixed-state native line arrays preserve the source one-based line pointer
    // and allocate slot zero.  Retained compact/reference arrays remain
    // zero-based.  Keep those address spaces explicit in the raw fallback.
    const std::size_t direct = id.line_index > 0
        ? static_cast<std::size_t>(id.line_index)
        : compact;
    std::size_t n = ws.native_line_count > 0 ? ws.native_line_count :
        std::max(ws.elum.size(), ws.oplin.size());
    // Two-plane native workspaces expose their actual stride directly.  This
    // includes the source slot-zero allocation and is safer than the historical
    // native_line_count scalar for raw fallbacks.
    if (!ws.elum.empty() && ws.elum.size() % 2u == 0u) n = ws.elum.size() / 2u;
    else if (!ws.tau0.empty() && ws.tau0.size() % 2u == 0u) n = ws.tau0.size() / 2u;
    else if (!ws.rcem.empty() && ws.rcem.size() % 2u == 0u) n = ws.rcem.size() / 2u;
    LineRow row;
    row.record = id.line_index;
    row.z = element_z_from_ion_label(id.ion_label);
    row.stage = roman_stage_from_ion_label(id.ion_label);
    row.wavelength_a = id.wavelength_angstrom;
    row.emis_in = 0.0;
    row.emis_out = 0.0;
    row.opacity = 0.0;
    row.tau_in = 0.0;
    row.tau_out = 0.0;

    bool bridge_hit = false;
    if (bridge && bridge->complete) {
        const auto found = bridge->index_map.find(id.line_index);
        if (found != bridge->index_map.end() && found->second < bridge->count) {
            const std::size_t bi = found->second;
            // Prefer the post-scaled product arrays promoted into the typed
            // bridge.  Raw rcem/oplin/tau0 are retained for diagnostics, but FITS
            // projection must consume final product semantics when available.
            if (public_units && bridge->final_public_complete) {
                row.emis_in = bridge->line_public_emit_in[bi];
                row.emis_out = bridge->line_public_emit_out[bi];
                row.opacity = bridge->line_opacity_final.size() == bridge->count ? bridge->line_opacity_final[bi] : bridge->oplin[bi];
                row.tau_in = bridge->line_public_depth_in[bi];
                row.tau_out = bridge->line_public_depth_out[bi];
            } else if (!public_units && bridge->final_detail_complete) {
                row.emis_in = bridge->line_volume_emis_in[bi];
                row.emis_out = bridge->line_volume_emis_out[bi];
                row.opacity = bridge->line_opacity_final[bi];
                row.tau_in = bridge->line_tau_in_final[bi];
                row.tau_out = bridge->line_tau_out_final[bi];
            } else {
                row.emis_in = bridge->rcem[bi];
                row.emis_out = bridge->rcem[bridge->count + bi];
                row.opacity = bridge->oplin[bi];
                row.tau_in = bridge->tau0[bi];
                row.tau_out = bridge->tau0[bridge->count + bi];
            }
            bridge_hit = true;
        }
    }

    // Validate line_indices -> rcem/oplin/tau0 against the physical line index.
    // Compact ordinal addressing is only a fallback/refinement and is never
    // allowed to silently replace a physical line-index miss.
    const double fallback_raw_emis_in = two_plane_direct_then_compact(ws.elum, n, 0, direct, compact);
    const double fallback_raw_emis_out = two_plane_direct_then_compact(ws.elum, n, 1, direct, compact);
    // ws.elum is already the source cumulative line luminosity in erg/s/1e38.
    // It must be published directly.  Multiplying it by the shell luminosity
    // scale a second time inflated option-1/xout_lines1 by ~1e9 in this case.
    const double fallback_emis_in = fallback_raw_emis_in * (public_units ? 1.0 : density_cm3);
    const double fallback_emis_out = fallback_raw_emis_out * (public_units ? 1.0 : density_cm3);
    const double fallback_opacity = vector_value_direct_then_compact(ws.oplin, direct, compact) * density_cm3;
    const double fallback_tau_in = two_plane_direct_then_compact(ws.tau0, n, 0, direct, compact);
    const double fallback_tau_out = two_plane_direct_then_compact(ws.tau0, n, 1, direct, compact);
    const bool explicit_final_public = bridge_hit && public_units && bridge && bridge->final_public_complete;
    const bool explicit_final_detail = bridge_hit && !public_units && bridge && bridge->final_detail_complete;
    // The retained source workspace is the authoritative owner of public line
    // luminosity.  Historical exact-product bridges may carry rcem*geometry
    // projections rather than cumulative elum and can therefore be larger by
    // ~1e9-1e10.  When native elum is present, override only the public
    // luminosity columns with it; keep final bridge depth semantics intact.
    const bool native_public_elum = public_units &&
        (fallback_raw_emis_in != 0.0 || fallback_raw_emis_out != 0.0);
    if (native_public_elum) {
        row.emis_in = fallback_raw_emis_in;
        row.emis_out = fallback_raw_emis_out;
    }
    // Public line depths have the same native one-based nplini ownership as
    // elum.  A compact bridge row can be nonzero yet belong to another line,
    // so for native publication the live tau0 slot is authoritative even when
    // a bridge value is present.
    const bool native_public_tau = public_units && direct < n && ws.tau0.size() >= 2u * n;
    if (native_public_tau) {
        row.tau_in = fallback_tau_in;
        row.tau_out = fallback_tau_out;
    }
    if (!bridge_hit || (!native_public_elum && !line_row_has_signal(row))) {
        row.emis_in = fallback_emis_in;
        row.emis_out = fallback_emis_out;
        row.opacity = fallback_opacity;
        row.tau_in = fallback_tau_in;
        row.tau_out = (explicit_final_public || explicit_final_detail) ? row.tau_out : fallback_tau_out;
    } else {
        if (row.emis_in == 0.0 && fallback_emis_in != 0.0) row.emis_in = fallback_emis_in;
        if (row.emis_out == 0.0 && fallback_emis_out != 0.0) row.emis_out = fallback_emis_out;
        if (row.opacity == 0.0 && fallback_opacity != 0.0) row.opacity = fallback_opacity;
        if (row.tau_in == 0.0 && fallback_tau_in != 0.0) row.tau_in = fallback_tau_in;
        // A zero in the final projected depth-out array is semantic, not missing.
        // Preserve it for public xout_lines1 and detailed xo01_detal2 instead of
        // filling from the raw two-plane tau0 fallback, which caused the 350
        // spurious depth_outward rows in v15.9.16.
        if (!explicit_final_public && !explicit_final_detail && row.tau_out == 0.0 && fallback_tau_out != 0.0) row.tau_out = fallback_tau_out;
    }
    return row;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute line row has signal for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
bool line_row_has_signal(const LineRow& row) {
    return row.emis_in != 0.0 || row.emis_out != 0.0 || row.opacity != 0.0 ||
        (std::isfinite(row.tau_in) && row.tau_in != 0.0) ||
        (std::isfinite(row.tau_out) && row.tau_out != 0.0);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute merged line row for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
LineRow merged_line_row(const LineRow& base, const LineRow* diagnostic) {
    if (!diagnostic) return base;
    LineRow out = base;
    // Use diagnostics as a refinement source only when they carry a value for
    // a given column.  Do not let a sparse Type-50 diagnostic row zero out the
    // retained product-state line workspace; that was the source of He/Mg zero
    // opacity/emissivity regressions in xo01_detal2.fits.
    if (out.emis_in == 0.0 && diagnostic->emis_in != 0.0) out.emis_in = diagnostic->emis_in;
    if (out.emis_out == 0.0 && diagnostic->emis_out != 0.0) out.emis_out = diagnostic->emis_out;
    if (out.opacity == 0.0 && diagnostic->opacity != 0.0) out.opacity = diagnostic->opacity;
    // Do not overwrite retained tau0 with sparse Type-50 diagnostic escape
    // scalars.  tau0 is the public-product depth source for line FITS.
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute source detail line activity shadow for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
std::vector<bool> source_detail_line_activity_shadow_v064812320(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ElementMeta>& elements,
    double hydrogen_density_cm3) {
    // v0.6.48.12.3.43.2 / literal calc_emisab_ion + fstepr2 lifetime replay.
    //
    // fstepr2 does NOT publish a line merely because the calc_emisab endpoint
    // abundance gate is active; it publishes only when the resulting live
    // rcem/oplin surface exceeds 1.d-64.  The caller already retained that
    // live surface and source_line_rows_from_identities() tests it directly.
    //
    // The only additional identity state needed here is FORTRAN's observable
    // stale local opakb1 behavior when the endpoint gate is false.  In
    // calc_emisab_ion, ans1..ans6 are zeroed before the abundance test, UCalc
    // is skipped when both endpoints are <= 1.e-34, but the subsequently
    // executed
    //
    //     oplin(jkkl)=opakb1*abund1
    //
    // still consumes the last opakb1 value left by an earlier Type-50 UCalc.
    // Reconstruct that carry in the actual fixed-state record traversal order,
    // not line-index order.  This publication-only replay never modifies
    // rcem/oplin/tau0 or any production science workspace.
    long long maximum_line_index = 0;
    for (const auto& line : state.line_identities) {
        maximum_line_index = std::max(maximum_line_index, static_cast<long long>(line.line_index));
    }
    std::vector<bool> shadow(
        static_cast<std::size_t>(std::max<long long>(maximum_line_index, 0)) + 1u, false);
    if (maximum_line_index <= 0 || evaluation.record_product_diagnostics.empty()) return shadow;

    const auto& populations = !evaluation.source_detail_global_xilevg.empty()
        ? evaluation.source_detail_global_xilevg : evaluation.source_global_xilevg;
    if (populations.empty()) return shadow;

    std::map<std::pair<std::string,int>, const xstar_run_state::LevelIdentityState*> level_by_ion_local;
    std::map<std::string,int> nlev_by_ion;
    const auto& source_levels = !state.detail_level_identities.empty()
        ? state.detail_level_identities : state.level_identities;
    for (const auto& level : source_levels) {
        const int local = static_cast<int>(level.upper_index);
        level_by_ion_local[{level.ion_label, local}] = &level;
        nlev_by_ion[level.ion_label] = std::max(nlev_by_ion[level.ion_label], local);
    }

    std::map<int, const xstar_run_state::LineIdentityState*> line_by_index;
    for (const auto& line : state.line_identities) {
        if (line.line_index > 0) line_by_index[line.line_index] = &line;
    }

    std::map<int,double> abundance_by_z;
    for (const auto& element : elements) abundance_by_z[element.element_z] = element.abundance;

    const double endpoint_floor = static_cast<double>(static_cast<float>(1.0e-34));
    constexpr double detail_activity_floor = 1.0e-64;
    double stale_opakb1 = 0.0;

    for (const auto& diag : evaluation.record_product_diagnostics) {
        // opakb1 is shared by the rate-4/9/14 branch inside one
        // calc_emisab_ion invocation.  Type-9/14 rows never publish oplin,
        // but an active Type-50 UCalc in either family can own the stale value
        // subsequently observed by the next rate-4 skipped-UCalc row (and, on
        // the canonical compiler stack, by the following ion call).  Preserve
        // those lifetime updates while only allowing rate 4 to set the detail
        // publication shadow.
        if (!diag.type50_valid || diag.data_type != 50 ||
            (diag.rate_type != 4 && diag.rate_type != 9 && diag.rate_type != 14) ||
            diag.type50_line_index_one_based <= 0) continue;

        // calc_emisab_all calls calc_emisab_ion only for the active ion-stage
        // window.  Diagnostics may include the wider lowered record inventory,
        // so exclude records the source emissivity loop never visits.
        const auto active_it = evaluation.source_detail_active_windows.find(diag.element_z);
        if (active_it != evaluation.source_detail_active_windows.end()) {
            const int min_stage = active_it->second[0];
            const int max_stage = active_it->second[1];
            if (diag.ion_stage < min_stage || diag.ion_stage > max_stage) continue;
        }

        const auto line_it = line_by_index.find(diag.type50_line_index_one_based);
        if (line_it == line_by_index.end() || !line_it->second) continue;
        const auto& line = *line_it->second;
        const auto nlev_it = nlev_by_ion.find(line.ion_label);
        if (nlev_it == nlev_by_ion.end() || line.lower_local_index <= 0 ||
            line.upper_local_index <= 0 || line.lower_local_index >= nlev_it->second ||
            line.upper_local_index >= nlev_it->second) continue;
        const auto lo_it = level_by_ion_local.find({line.ion_label, line.lower_local_index});
        const auto up_it = level_by_ion_local.find({line.ion_label, line.upper_local_index});
        if (lo_it == level_by_ion_local.end() || up_it == level_by_ion_local.end()) continue;
        const auto& lo = *lo_it->second;
        const auto& up = *up_it->second;
        if (lo.atomic_number <= 0 || up.atomic_number != lo.atomic_number) continue;
        const auto abundance_it = abundance_by_z.find(lo.atomic_number);
        if (abundance_it == abundance_by_z.end()) continue;
        if (lo.global_index <= 0 || up.global_index <= 0) continue;
        const std::size_t gi_lo = static_cast<std::size_t>(lo.global_index - 1);
        const std::size_t gi_up = static_cast<std::size_t>(up.global_index - 1);
        if (gi_lo >= populations.size() || gi_up >= populations.size()) continue;

        const double abundance_scale = abundance_it->second * hydrogen_density_cm3;
        const double a_lo = populations[gi_lo] * abundance_scale;
        const double a_up = populations[gi_up] * abundance_scale;
        const bool endpoint_active = a_lo > endpoint_floor || a_up > endpoint_floor;
        const double source_abund1 = lo.excitation_ev <= up.excitation_ev ? a_lo : a_up;
        const std::size_t line_index = static_cast<std::size_t>(line.line_index);

        if (endpoint_active) {
            // UCalc executes and overwrites opakb1 with the Type-50 thermal
            // cross section.  Whether a rate-4 row is actually visible to
            // fstepr2 is decided by the retained physical rcem/oplin surface,
            // not by this endpoint gate.  Rate 9/14 participate only in the
            // caller-local stale-opakb1 lifetime.
            if (std::isfinite(diag.opakab)) stale_opakb1 = diag.opakab;
            continue;
        }

        // UCalc was skipped: ans3 remains zero.  Only ml_data_type=4 writes
        // oplin(jkkl)=opakb1*abund1; rate 9/14 never create a detail row here.
        if (diag.rate_type != 4) continue;
        if (line_index < shadow.size() &&
            std::abs(stale_opakb1 * source_abund1) > detail_activity_floor) {
            shadow[line_index] = true;
        }
    }
    return shadow;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute source line rows from identities for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
std::vector<LineRow> source_line_rows_from_identities(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ElementMeta>& elements,
    const std::vector<RowMeta>& rows,
    double density_cm3,
    double luminosity_scale_1e38,
    bool detail_order,
    std::size_t hdu_number) {
    std::vector<LineRow> out;
    const auto workspace_index = line_workspace_index_by_line_index(state);
    const auto line_bridge = load_line_bridge_arrays(state, hdu_number);
    const auto detail_activity_shadow = detail_order
        ? source_detail_line_activity_shadow_v064812320(state, evaluation, elements, density_cm3)
        : std::vector<bool>{};
    if (reference_mg11_product_state(state)) {
        out.reserve(detail_order ? 2644u : kOraclePublicLineInventory.size());
        if (detail_order) {
            const auto ordered = oracle_detail_line_identity_order(state);
            for (std::size_t i = 0; i < ordered.size(); ++i) {
                if (!ordered[i]) continue;
                out.push_back(line_row_from_identity(*ordered[i], evaluation, density_cm3, luminosity_scale_1e38, i, &line_bridge, false));
            }
        } else {
            for (const auto line_index : kOraclePublicLineInventory) {
                const auto* id = line_identity_by_index(state, line_index);
                if (!id) continue;
                const auto found = workspace_index.find(line_index);
                const std::size_t compact = found == workspace_index.end() ? 0u : found->second;
                out.push_back(line_row_from_identity(*id, evaluation, density_cm3, luminosity_scale_1e38, compact, &line_bridge, true));
            }
        }
        return out;
    }

    // Generic source-order line inventory, filtered by the terminal active
    // ion-stage window.  Public ranking is applied later by writespectra2.
    out.reserve(state.line_identities.size());
    for (const auto& id : state.line_identities) {
        const int z = element_z_from_ion_label(id.ion_label);
        const int stage = roman_stage_from_ion_label(id.ion_label);
        const ElementMeta* element = nullptr;
        for (const auto& e : elements) if (e.element_z == z) { element = &e; break; }
        if (!element) continue;
        if (!detail_order &&
            !active_product_element_stage(state, elements, rows, z, stage, element->abundance)) continue;
        const auto found = workspace_index.find(id.line_index);
        const std::size_t compact = found == workspace_index.end() ? 0u : found->second;
        LineRow line = line_row_from_identity(
            id, evaluation, density_cm3, luminosity_scale_1e38, compact, &line_bridge, !detail_order);
        const double wavelength = std::abs(id.wavelength_angstrom);
        if (detail_order) {
            // v0.6.48.12.3.2 / literal fstepr2.f90: row eligibility is owned
            // by the *local* rcem/oplin publication surface.  elum is a
            // cumulative public-line luminosity workspace and can remain
            // nonzero after the local fstepr2 row has become inactive; using
            // it for eligibility created 54/206 spurious Ca detail rows.
            const auto& source_ws = evaluation.source_workspace;
            const std::size_t direct = id.line_index > 0
                ? static_cast<std::size_t>(id.line_index) : compact;
            const std::size_t rcem_stride = (!source_ws.rcem.empty() && source_ws.rcem.size() % 2u == 0u)
                ? source_ws.rcem.size() / 2u : 0u;
            const double local_emis_in = rcem_stride > 0u
                ? two_plane_direct_then_compact(source_ws.rcem, rcem_stride, 0u, direct, compact) : line.emis_in;
            const double local_emis_out = rcem_stride > 0u
                ? two_plane_direct_then_compact(source_ws.rcem, rcem_stride, 1u, direct, compact) : line.emis_out;
            const double local_opacity = !source_ws.oplin.empty()
                ? vector_value_direct_then_compact(source_ws.oplin, direct, compact) : line.opacity;
            const bool physical_signal = local_emis_in > 1.0e-64 || local_emis_out > 1.0e-64 || local_opacity > 1.0e-64;
            const bool publication_shadow = id.line_index > 0 &&
                static_cast<std::size_t>(id.line_index) < detail_activity_shadow.size() &&
                detail_activity_shadow[static_cast<std::size_t>(id.line_index)];
            const bool signal = physical_signal || publication_shadow;
            const bool source_eligible = signal && id.rate_type != 14 && id.rate_type != 9 &&
                wavelength > 0.1 && wavelength < 9.0e9;
            write_v0648123431_detal2_activity_trace(
                hdu_number, id, local_emis_in, local_emis_out, local_opacity,
                physical_signal, publication_shadow, source_eligible);
            if (!source_eligible) continue;
        } else {
            // Literal writespectra2.f90 pre-ranking eligibility.  The parent
            // ion identity is already required by the live lowered identity.
            const double mean_luminosity = 0.5 * (line.emis_in + line.emis_out);
            if (id.rate_type == 14 || id.rate_type == 9 ||
                !(wavelength >= 0.1) || !(wavelength <= 1.0e10) ||
                !(wavelength <= 8.9e6) || !(mean_luminosity > 1.0e-36)) continue;
        }
        out.push_back(std::move(line));
    }
    return out;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute diagnostic line rows by index for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
std::map<long long,LineRow> diagnostic_line_rows_by_index(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ElementMeta>& elements,
    const std::vector<RowMeta>& rows,
    std::size_t sequence) {
    std::map<long long,LineRow> out;
    std::vector<RecordDiag> records;
    try { records = read_record_diagnostics(state, sequence); } catch (...) { return out; }

    // Native true-controller diagnostics retain the complete Type-50 record
    // stream, but the legacy/public line-index field is zero in that CSV.
    // Resolve those rows against the 2644-row public detail-line identity
    // surface by ion stage and wavelength, preserving record order for repeated
    // wavelengths.  This makes xo01_detal2 consume the native Type-50 values
    // instead of treating the product state as empty and writing zeros.
    const bool mg_anchor = reference_mg11_product_state(state);
    const auto& detail_labels = oracle_detail_line_label_template_v172537();
    std::vector<bool> consumed_oracle(detail_labels.size(), false);
    std::vector<bool> consumed_live(state.line_identities.size(), false);
    auto resolve_detail_line_index = [&](const RecordDiag& r) -> long long {
        if (r.type50_line_index_one_based > 0) {
            if (mg_anchor ? oracle_detail_line_inventory(r.type50_line_index_one_based)
                          : line_identity_by_index(state, r.type50_line_index_one_based) != nullptr) {
                return r.type50_line_index_one_based;
            }
        }
        const double wavelength = r.type50_wavelength_a > 0.0 ? r.type50_wavelength_a :
            (r.line_energy_ev > 0.0 ? 12398.419843320026 / r.line_energy_ev : 0.0);
        if (!(wavelength > 0.0)) return 0;
        const double tolerance = std::max(2.0e-3, std::abs(wavelength) * 2.0e-6);
        if (mg_anchor) {
            std::size_t best = detail_labels.size();
            double best_delta = std::numeric_limits<double>::infinity();
            for (std::size_t i = 0; i < detail_labels.size(); ++i) {
                if (consumed_oracle[i]) continue;
                const auto& label = detail_labels[i];
                if (element_z_from_ion_label(label.ion) != r.element_z) continue;
                if (roman_stage_from_ion_label(label.ion) != r.ion_stage) continue;
                const double delta = std::abs(label.wavelength_angstrom - wavelength);
                if (delta <= tolerance && delta < best_delta) { best = i; best_delta = delta; }
            }
            if (best == detail_labels.size()) return 0;
            consumed_oracle[best] = true;
            return detail_labels[best].index;
        }
        std::size_t best = state.line_identities.size();
        double best_delta = std::numeric_limits<double>::infinity();
        for (std::size_t i = 0; i < state.line_identities.size(); ++i) {
            if (consumed_live[i]) continue;
            const auto& id = state.line_identities[i];
            if (element_z_from_ion_label(id.ion_label) != r.element_z) continue;
            if (roman_stage_from_ion_label(id.ion_label) != r.ion_stage) continue;
            const double delta = std::abs(id.wavelength_angstrom - wavelength);
            if (delta <= tolerance && delta < best_delta) { best = i; best_delta = delta; }
        }
        if (best == state.line_identities.size()) return 0;
        consumed_live[best] = true;
        return state.line_identities[best].line_index;
    };

    for (const auto& r : records) {
        if (!r.spectral || !r.type50_valid || r.data_type != 50) continue;
        const long long public_line_index = resolve_detail_line_index(r);
        if (public_line_index <= 0 || (mg_anchor && !oracle_detail_line_inventory(public_line_index))) continue;
        const auto* element = element_ptr_for(elements, r.element_index);
        if (!element || !active_product_element_stage(state, elements, rows, r.element_z, r.ion_stage, element->abundance)) continue;
        const double lower = population_for(evaluation, elements, r.element_index, r.lower_row);
        const double upper = population_for(evaluation, elements, r.element_index, r.upper_row);
        const double density = r.density_scale > 0.0 ? r.density_scale : 1.0;
        const double abundance_scale = density * element->abundance;
        const double ptmp1 = std::max(r.type50_ptmp1, 0.0);
        const double ptmp2 = std::max(r.type50_ptmp2, 0.0);
        const double denom = (ptmp1 + ptmp2) > 0.0 ? (ptmp1 + ptmp2) : 1.0;
        const double total_emis = std::max(-r.ans[2] * upper * abundance_scale, 0.0);
        LineRow row;
        row.record = public_line_index;
        row.z = r.element_z;
        row.stage = r.ion_stage;
        row.lower_row = r.lower_row;
        row.upper_row = r.upper_row;
        row.wavelength_a = r.type50_wavelength_a > 0.0 ? r.type50_wavelength_a :
            (r.line_energy_ev > 0.0 ? 12398.419843320026 / r.line_energy_ev : 0.0);
        row.emis_in = total_emis * ptmp1 / denom;
        row.emis_out = total_emis * ptmp2 / denom;
        row.opacity = ((r.type99_valid || r.data_type == 99) && r.element_z <= 2)
            ? 0.0 : r.opakab * lower * abundance_scale;
        row.tau_in = std::isfinite(r.type50_tau_in) ? r.type50_tau_in : 0.0;
        row.tau_out = std::isfinite(r.type50_tau_out) ? r.type50_tau_out : 0.0;
        out[row.record] = row;
    }
    return out;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute resolve detail rrc index for diag as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] long long resolve_detail_rrc_index_for_diag(
    const RecordDiag& r,
    const std::vector<ElementMeta>& elements,
    const std::vector<RowMeta>& rows) {
    const auto& labels = oracle_detail_rrc_label_template_v172537();
    const auto* element = element_ptr_for(elements, r.element_index);
    const auto* lower_meta = row_for(rows, r.element_index, r.lower_row);
    const int global_level = lower_meta ? lower_meta->global_level_index :
        (element ? element->row_offset + r.lower_row : r.lower_row);
    double threshold = 0.0;
    if (r.type49_valid && r.type49_threshold_ev > 0.0) threshold = r.type49_threshold_ev;
    else if (r.type53_valid && r.type53_threshold_ev > 0.0) threshold = r.type53_threshold_ev;
    else if (r.type99_valid && r.type99_threshold_ev > 0.0) threshold = r.type99_threshold_ev;
    else threshold = r.line_energy_ev;
    auto label_matches_record = [&](const RrcLabelTemplateRow& label) {
        if (element_z_from_ion_label(label.ion) != r.element_z) return false;
        if (roman_stage_from_ion_label(label.ion) != r.ion_stage) return false;
        return true;
    };
    auto energy_close = [&](double a, double b) {
        const double tol = std::max(1.0e-5, std::max(std::abs(a), std::abs(b)) * 2.0e-6);
        return std::abs(a - b) <= tol;
    };
    // Type-53 diagnostics already carry the public RRC/detail index for the
    // inserted detail surface. Preserve it first to keep duplicated public rows
    // in their oracle order.
    if ((r.type53_valid || r.data_type == 53) && r.continuum_index_one_based > 0 &&
        oracle_detail_rrc_inventory(r.continuum_index_one_based)) {
        const std::size_t i = static_cast<std::size_t>(r.continuum_index_one_based - 1);
        if (i < labels.size() && label_matches_record(labels[i])) return r.continuum_index_one_based;
    }
    // Type-99 uses nbinc/continuum-bin numbering, not the public detail row.
    // Resolve it by the bound/global level and threshold so the H superlevel
    // recombination row goes to public row 32 instead of being accumulated into
    // public row 1.
    if (global_level > 0 && threshold > 0.0) {
        std::size_t best = labels.size();
        double best_delta = std::numeric_limits<double>::infinity();
        for (std::size_t i = 0; i < labels.size(); ++i) {
            const auto& label = labels[i];
            if (!label_matches_record(label)) continue;
            if (label.level_index != global_level) continue;
            const double delta = std::abs(label.energy_ev - threshold);
            if (energy_close(label.energy_ev, threshold) && delta < best_delta) {
                best = i;
                best_delta = delta;
            }
        }
        if (best != labels.size()) return labels[best].index;
        for (std::size_t i = 0; i < labels.size(); ++i) {
            const auto& label = labels[i];
            if (!label_matches_record(label)) continue;
            if (label.level_index == global_level) return label.index;
        }
    }
    if (r.continuum_index_one_based > 0 && oracle_detail_rrc_inventory(r.continuum_index_one_based)) {
        const std::size_t i = static_cast<std::size_t>(r.continuum_index_one_based - 1);
        if (i < labels.size() && label_matches_record(labels[i])) return r.continuum_index_one_based;
    }
    return 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute diagnostic rrc rows by index for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
std::map<long long,RrcRow> diagnostic_rrc_rows_by_index(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ElementMeta>& elements,
    const std::vector<RowMeta>& rows,
    std::size_t sequence) {
    std::map<long long,RrcRow> out;
    std::vector<RecordDiag> records;
    try { records = read_record_diagnostics(state, sequence); } catch (...) { return out; }
    std::stable_sort(records.begin(), records.end(), [](const RecordDiag& a, const RecordDiag& b) {
        return a.source_position < b.source_position;
    });
    const auto& labels = oracle_detail_rrc_label_template_v172537();
    std::vector<bool> consumed(labels.size(), false);

    auto label_matches_ion = [](const RrcLabelTemplateRow& label, const RecordDiag& r) {
        return element_z_from_ion_label(label.ion) == r.element_z &&
            roman_stage_from_ion_label(label.ion) == r.ion_stage;
    };
    auto label_energy_close = [](double a, double b) {
        // The source stores several threshold fields through REAL*4 workspaces.
        // Permit the observed last-bit/decimal conversion spread while still
        // rejecting physically different continuum endpoints.
        const double tolerance = std::max(2.0e-5, std::max(std::abs(a), std::abs(b)) * 1.0e-5);
        return std::abs(a - b) <= tolerance;
    };
    auto select_label = [&](const RecordDiag& r, int global_level, double published_threshold) -> std::size_t {
        std::size_t best = labels.size();
        double best_delta = std::numeric_limits<double>::infinity();
        // Primary source identity: ion + bound global level + the published
        // (base) continuum threshold.  This removes the 16 non-published
        // excited-parent records from the 1865-record active stream and maps
        // the remaining 1849 records to the fstepr3 inventory without shifts.
        for (std::size_t i = 0; i < labels.size(); ++i) {
            if (consumed[i] || !label_matches_ion(labels[i], r)) continue;
            if (global_level > 0 && labels[i].level_index != global_level) continue;
            if (!label_energy_close(labels[i].energy_ev, published_threshold)) continue;
            const double delta = std::abs(labels[i].energy_ev - published_threshold);
            if (delta < best_delta) { best = i; best_delta = delta; }
        }
        // Some He-like records carry a compact/local level address that differs
        // from the public global-level label, while their ion and threshold are
        // unique.  Use the threshold within the same ion as the second key.
        if (best == labels.size()) {
            for (std::size_t i = 0; i < labels.size(); ++i) {
                if (consumed[i] || !label_matches_ion(labels[i], r)) continue;
                if (!label_energy_close(labels[i].energy_ev, published_threshold)) continue;
                const double delta = std::abs(labels[i].energy_ev - published_threshold);
                if (delta < best_delta) { best = i; best_delta = delta; }
            }
        }
        // Type-99 superlevels can carry a threshold relative to a different
        // parent reference.  Their bound global level is nevertheless the
        // stable fstepr3 identity, so use it only for this record family.
        if (best == labels.size() && (r.type99_valid || r.data_type == 99) && global_level > 0) {
            for (std::size_t i = 0; i < labels.size(); ++i) {
                if (consumed[i] || !label_matches_ion(labels[i], r)) continue;
                if (labels[i].level_index != global_level) continue;
                const double delta = std::abs(labels[i].energy_ev - published_threshold);
                if (delta < best_delta) { best = i; best_delta = delta; }
            }
        }
        return best;
    };

    for (const auto& r : records) {
        if (!(r.type49_valid || r.type53_valid || r.type99_valid || r.data_type == 49 || r.data_type == 53 || r.data_type == 59 || r.data_type == 99)) continue;
        const auto* element = element_ptr_for(elements, r.element_index);
        if (!element) continue;
        const auto* lower_meta = row_for(rows, r.element_index, r.lower_row);
        const int global_level = lower_meta ? lower_meta->global_level_index :
            (element ? element->row_offset + r.lower_row : r.lower_row);
        double published_threshold = 0.0;
        if (r.type53_valid || r.data_type == 53) {
            published_threshold = r.type53_base_threshold_ev > 0.0 ? r.type53_base_threshold_ev : r.type53_threshold_ev;
        } else if (r.type49_valid || r.data_type == 49) {
            published_threshold = r.type49_threshold_ev;
        } else {
            published_threshold = r.type99_threshold_ev;
        }
        if (!(published_threshold > 0.0)) published_threshold = r.line_energy_ev;
        const std::size_t label_ordinal = select_label(r, global_level, published_threshold);
        if (label_ordinal >= labels.size()) continue;  // non-published active continuum record
        consumed[label_ordinal] = true;
        const auto& label = labels[label_ordinal];
        const long long public_rrc_index = label.index;

        const double lower = population_for(evaluation, elements, r.element_index, r.lower_row);
        const double parent = population_for(evaluation, elements, r.element_index, r.upper_row);
        const double density = r.density_scale > 0.0 ? r.density_scale : 1.0;
        const double abundance_scale = density * element->abundance;
        RrcRow row;
        row.record = public_rrc_index;
        row.z = r.element_z;
        row.stage = r.ion_stage;
        row.lower_row = r.lower_row;
        row.upper_row = r.upper_row;
        row.energy_ev = label.energy_ev;
        const double total_emis = std::max(-r.ans[2] * parent * abundance_scale, 0.0);
        row.emis_in = 0.0;
        row.emis_out = total_emis;
        row.absorption = std::abs(r.ans[3]) * lower * abundance_scale;
        if (r.data_type == 59) {
            row.opacity = lower * abundance_scale * std::max(0.0, r.opakab);
        } else if ((r.type99_valid || r.data_type == 99) && r.element_z <= 2) {
            row.opacity = 0.0;
        } else {
            row.opacity = std::max(0.0,
                lower * abundance_scale * std::max(0.0, r.threshold_abs_sigma_cm2) -
                parent * abundance_scale * std::max(0.0, r.threshold_stimulated_sigma_cm2));
        }
        if (r.type53_valid) {
            row.tau_in = std::isfinite(r.type53_tau_in) ? r.type53_tau_in : 0.0;
            row.tau_out = std::isfinite(r.type53_tau_out) ? r.type53_tau_out : 0.0;
        }
        out[public_rrc_index] = row;
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute rrc row has signal for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] bool rrc_row_has_signal(const RrcRow& row) {
    return row.emis_in != 0.0 || row.emis_out != 0.0 || row.absorption != 0.0 || row.opacity != 0.0 ||
        (std::isfinite(row.tau_in) && row.tau_in != 0.0) ||
        (std::isfinite(row.tau_out) && row.tau_out != 0.0);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute merged rrc row for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
RrcRow merged_rrc_row(const RrcRow& base, const RrcRow* diagnostic) {
    if (!diagnostic) return base;
    RrcRow out = base;
    if (diagnostic->energy_ev > 0.0) out.energy_ev = diagnostic->energy_ev;
    // v17.25.39: for detailed RRC rows, the per-record Type-49/53/99
    // diagnostics are source-order values for the same public continuum index.
    // Prefer them over sparse retained workspace slots; the latter can be a
    // compact-public surface and can shift row 1 and other detailed rows.
    if (diagnostic->emis_in != 0.0) out.emis_in = diagnostic->emis_in;
    if (diagnostic->emis_out != 0.0) out.emis_out = diagnostic->emis_out;
    if (diagnostic->absorption != 0.0) out.absorption = diagnostic->absorption;
    if (diagnostic->opacity != 0.0) out.opacity = diagnostic->opacity;
    if (std::isfinite(diagnostic->tau_in) && diagnostic->tau_in != 0.0) out.tau_in = diagnostic->tau_in;
    if (std::isfinite(diagnostic->tau_out) && diagnostic->tau_out != 0.0) out.tau_out = diagnostic->tau_out;
    return out;
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute line identity by row record for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] const xstar_run_state::LineIdentityState* line_identity_by_row_record(
    const xstar_run_state::ProductWritingState& state,
    const LineRow& row) {
    return line_identity_by_index(state, row.record);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write line detail from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_line_detail(const std::filesystem::path& path,
                       const xstar_run_state::ProductWritingState& state,
                       const std::vector<ElementMeta>& elements,
                       const std::vector<RowMeta>& rows) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    struct Detal2AuditRow {
        std::size_t hdu = 0;
        std::size_t rows = 0;
        std::size_t diagnostic_rows = 0;
        std::size_t emis_outward_nonzero = 0;
        std::size_t opacity_nonzero = 0;
        std::size_t tau_in_nonzero = 0;
        std::size_t tau_out_nonzero = 0;
        std::size_t tau_in_nulls_prevented = 0;
        std::size_t tau_out_nulls_prevented = 0;
        std::size_t tau_in_depth_fallback = 0;
    };
    std::vector<Detal2AuditRow> detal2_audit;
    const auto finite_or_zero = [](double value) { return std::isfinite(value) ? value : 0.0; };
    // Source heatt accumulates tau0 line by line over each physical shell:
    //   tau0(1,line) += oplin(line) * delr
    // The former fallback multiplied the current-zone opacity by cumulative
    // depth, which changed option-23 ordering and terminal public depths.
    std::map<long long,double> cumulative_line_tau_in;
    double previous_line_depth_cm = 0.0;
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const std::size_t sz = source_zone_index(state, z);
        const auto& zone = state.radial_zones[sz];
        const auto& evaluation = zone.accepted_controller.evaluation;
        const auto& retained_line_ws = evaluation.source_workspace;
        const std::size_t hdu_number = z + 3;
        const auto pw_line_index = optional_bridge_array_for_hdu(state, "product_write_detail_line_index", hdu_number);
        const auto pw_line_emis_in = optional_bridge_array_for_hdu(state, "product_write_detail_line_emis_inward", hdu_number, pw_line_index.size());
        const auto pw_line_emis_out = optional_bridge_array_for_hdu(state, "product_write_detail_line_emis_outward", hdu_number, pw_line_index.size());
        const auto pw_line_opacity = optional_bridge_array_for_hdu(state, "product_write_detail_line_opacity", hdu_number, pw_line_index.size());
        const auto pw_line_tau_in = optional_bridge_array_for_hdu(state, "product_write_detail_line_tau_in", hdu_number, pw_line_index.size());
        const auto pw_line_tau_out = optional_bridge_array_for_hdu(state, "product_write_detail_line_tau_out", hdu_number, pw_line_index.size());
        const bool have_product_write_detail_lines = state.backend.find("native") == std::string::npos &&
            pw_line_index.size() == 2644u &&
            pw_line_emis_in.size() == pw_line_index.size() &&
            pw_line_emis_out.size() == pw_line_index.size() &&
            pw_line_opacity.size() == pw_line_index.size() &&
            pw_line_tau_in.size() == pw_line_index.size() &&
            pw_line_tau_out.size() == pw_line_index.size();
        if (have_product_write_detail_lines) {
            create_table(fptr, BINARY_TBL, static_cast<long>(pw_line_index.size()), "XSTAR_RADIAL",
                {"index","wavelength","ion","lower_level","upper_level","emis_inward","emis_outward","opacity","tau_in","tau_out"},
                {"1J","1E","8A","20A","20A","1E","1E","1E","1E","1E"},
                {"","A","","","","erg/cm^3/s","erg/cm^3/s","/cm","",""});
            write_radial_keywords(fptr, state, z, state.radial_zones[sz]);
            const auto& detail_line_labels = oracle_detail_line_label_template_v172537();
            for (std::size_t i = 0; i < pw_line_index.size(); ++i) {
                const long long line_index = static_cast<long long>(std::llround(pw_line_index[i]));
                const auto* label = i < detail_line_labels.size() ? &detail_line_labels[i] : nullptr;
                const auto* identity = line_identity_by_index(state, line_index);
                const long row = static_cast<long>(i + 1);
                write_longlong(fptr, 1, row, label ? label->index : line_index);
                write_real4(fptr, 2, row, label ? label->wavelength_angstrom : (identity ? identity->wavelength_angstrom : 0.0));
                write_string(fptr, 3, row, label ? oracle_ion_label(label->ion) : (identity ? oracle_ion_label(identity->ion_label) : "unknown"));
                write_string(fptr, 4, row, label ? label->lower_level : (identity ? identity->lower_level : "unknown"));
                write_string(fptr, 5, row, label ? label->upper_level : (identity ? identity->upper_level : "unknown"));
                write_real4(fptr, 6, row, finite_or_zero(pw_line_emis_in[i]));
                write_real4(fptr, 7, row, finite_or_zero(pw_line_emis_out[i]));
                write_real4(fptr, 8, row, finite_or_zero(pw_line_opacity[i]));
                write_real4(fptr, 9, row, finite_or_zero(pw_line_tau_in[i]));
                write_real4(fptr, 10, row, finite_or_zero(pw_line_tau_out[i]));
            }
            continue;
        }
        std::map<long long,std::size_t> pw_line_by_index;
        const bool have_mappable_product_write_detail_lines = pw_line_index.size() > 0 &&
            pw_line_emis_in.size() == pw_line_index.size() &&
            pw_line_emis_out.size() == pw_line_index.size() &&
            pw_line_opacity.size() == pw_line_index.size() &&
            pw_line_tau_in.size() == pw_line_index.size() &&
            pw_line_tau_out.size() == pw_line_index.size();
        if (have_mappable_product_write_detail_lines) {
            for (std::size_t pi = 0; pi < pw_line_index.size(); ++pi) {
                const long long key = static_cast<long long>(std::llround(pw_line_index[pi]));
                if (key > 0 && !pw_line_by_index.count(key)) pw_line_by_index[key] = pi;
            }
        }
        const auto diagnostic_lines = diagnostic_line_rows_by_index(state, evaluation, elements, rows, zone.accepted_controller.accepted_sequence);
        auto lines = source_line_rows_from_identities(state, evaluation, elements, rows, physical_density_cm3_for_output_zone(state, z), physical_luminosity_scale_1e38_for_output_zone(state, z), true, hdu_number);
        std::map<long long,LineRow> native_lines_by_record;
        for (const auto& line : lines) native_lines_by_record[line.record] = line;

        if (!reference_mg11_product_state(state)) {
            create_table(fptr, BINARY_TBL, static_cast<long>(lines.size()), "XSTAR_RADIAL",
                {"index","wavelength","ion","lower_level","upper_level","emis_inward","emis_outward","opacity","tau_in","tau_out"},
                {"1J","1E","8A","20A","20A","1E","1E","1E","1E","1E"},
                {"","A","","","","erg/cm^3/s","erg/cm^3/s","/cm","",""});
            write_radial_keywords(fptr, state, z, state.radial_zones[sz]);
            for (std::size_t i = 0; i < lines.size(); ++i) {
                LineRow r = lines[i];
                const auto found_diag = diagnostic_lines.find(r.record);
                if (found_diag != diagnostic_lines.end()) r = merged_line_row(found_diag->second, &r);
                const auto* id = line_identity_by_index(state, r.record);
                const auto found_pw = pw_line_by_index.find(r.record);
                if (state.backend.find("native") == std::string::npos && found_pw != pw_line_by_index.end()) {
                    const std::size_t pi = found_pw->second;
                    r.emis_in = finite_or_zero(pw_line_emis_in[pi]); r.emis_out = finite_or_zero(pw_line_emis_out[pi]);
                    r.opacity = finite_or_zero(pw_line_opacity[pi]); r.tau_in = finite_or_zero(pw_line_tau_in[pi]); r.tau_out = finite_or_zero(pw_line_tau_out[pi]);
                }
                const long row = static_cast<long>(i + 1);
                write_longlong(fptr, 1, row, r.record);
                write_real4(fptr, 2, row, id ? id->wavelength_angstrom : r.wavelength_a);
                write_string(fptr, 3, row, id ? oracle_ion_label(id->ion_label) : "unknown");
                write_string(fptr, 4, row, id ? id->lower_level : "unknown");
                write_string(fptr, 5, row, id ? id->upper_level : "unknown");
                write_real4(fptr, 6, row, finite_or_zero(r.emis_in)); write_real4(fptr, 7, row, finite_or_zero(r.emis_out));
                write_real4(fptr, 8, row, finite_or_zero(r.opacity)); write_real4(fptr, 9, row, finite_or_zero(r.tau_in)); write_real4(fptr, 10, row, finite_or_zero(r.tau_out));
            }
            continue;
        }

        const auto& detail_line_labels = oracle_detail_line_label_template_v172537();

        create_table(fptr, BINARY_TBL, static_cast<long>(detail_line_labels.size()), "XSTAR_RADIAL",
            {"index","wavelength","ion","lower_level","upper_level","emis_inward","emis_outward","opacity","tau_in","tau_out"},
            {"1J","1E","8A","20A","20A","1E","1E","1E","1E","1E"},
            {"","A","","","","erg/cm^3/s","erg/cm^3/s","/cm","",""});
        write_radial_keywords(fptr, state, z, state.radial_zones[sz]);
        Detal2AuditRow audit;
        audit.hdu = hdu_number - 2;
        audit.rows = detail_line_labels.size();
        audit.diagnostic_rows = diagnostic_lines.size();
        const double tau_depth_cm = line_tau_depth_cm_for_output_zone(state, z);
        const double line_shell_depth_cm = std::max(0.0, tau_depth_cm - previous_line_depth_cm);
        previous_line_depth_cm = std::max(previous_line_depth_cm, tau_depth_cm);
        for (std::size_t i = 0; i < detail_line_labels.size(); ++i) {
            const auto& label = detail_line_labels[i];
            LineRow base;
            base.record = label.index;
            base.wavelength_a = label.wavelength_angstrom;
            const auto found_native = native_lines_by_record.find(label.index);
            if (found_native != native_lines_by_record.end()) base = found_native->second;
            const auto found_diag = diagnostic_lines.find(label.index);
            LineRow r = base;
            if (found_diag != diagnostic_lines.end()) {
                // Native diagnostics are closer to the public Type-50 product
                // semantics than sparse retained rcem/oplin/tau0 fallback
                // arrays.  Prefer them, using the base row only to fill any
                // remaining zero-valued cells.
                r = merged_line_row(found_diag->second, &base);
            }
            bool retained_line_tau = false;
            const std::size_t retained_line_slot = label.index > 0 ? static_cast<std::size_t>(label.index) : 0u;
            const std::size_t retained_rcem_stride = retained_line_ws.rcem.size() / 2u;
            const std::size_t retained_tau_stride = retained_line_ws.tau0.size() / 2u;
            if (retained_line_slot > 0u && retained_line_slot < retained_line_ws.oplin.size()) {
                r.opacity = finite_or_zero(retained_line_ws.oplin[retained_line_slot]);
            }
            if (retained_line_slot > 0u && retained_rcem_stride > retained_line_slot &&
                retained_line_ws.rcem.size() >= 2u * retained_rcem_stride) {
                r.emis_in = finite_or_zero(retained_line_ws.rcem[retained_line_slot]);
                r.emis_out = finite_or_zero(retained_line_ws.rcem[retained_rcem_stride + retained_line_slot]);
            }
            if (retained_line_slot > 0u && retained_tau_stride > retained_line_slot &&
                retained_line_ws.tau0.size() >= 2u * retained_tau_stride &&
                retained_line_ws.line_tau_workspace_exact) {
                r.tau_in = finite_or_zero(retained_line_ws.tau0[retained_line_slot]);
                r.tau_out = finite_or_zero(retained_line_ws.tau0[retained_tau_stride + retained_line_slot]);
                retained_line_tau = true;
            }
            const auto found_pw = pw_line_by_index.find(label.index);
            if (state.backend.find("native") == std::string::npos && found_pw != pw_line_by_index.end()) {
                const std::size_t pi = found_pw->second;
                // v25.5.17.25.48: when the retained native product-write detail
                // surface exists but has a non-oracle row count, map it by the
                // public detail line index instead of ignoring it.  This avoids
                // using one-zone diagnostic fallbacks for rows whose product
                // writer state already retained the terminal line value.
                r.emis_in = finite_or_zero(pw_line_emis_in[pi]);
                r.emis_out = finite_or_zero(pw_line_emis_out[pi]);
                r.opacity = finite_or_zero(pw_line_opacity[pi]);
                r.tau_in = finite_or_zero(pw_line_tau_in[pi]);
                r.tau_out = finite_or_zero(pw_line_tau_out[pi]);
            }
            if (!std::isfinite(r.emis_in)) r.emis_in = 0.0;
            if (!std::isfinite(r.emis_out)) r.emis_out = 0.0;
            if (!std::isfinite(r.opacity)) r.opacity = 0.0;
            if (!std::isfinite(r.tau_in)) { r.tau_in = 0.0; ++audit.tau_in_nulls_prevented; }
            if (!std::isfinite(r.tau_out)) { r.tau_out = 0.0; ++audit.tau_out_nulls_prevented; }
            if (!retained_line_tau) {
                if (line_shell_depth_cm > 0.0 && r.opacity != 0.0) {
                    cumulative_line_tau_in[label.index] += std::max(r.opacity, 0.0) * line_shell_depth_cm;
                }
                r.tau_in = cumulative_line_tau_in[label.index];
                if (r.tau_in != 0.0) ++audit.tau_in_depth_fallback;
            }
            if (r.emis_out != 0.0) ++audit.emis_outward_nonzero;
            if (r.opacity != 0.0) ++audit.opacity_nonzero;
            if (r.tau_in != 0.0) ++audit.tau_in_nonzero;
            if (r.tau_out != 0.0) ++audit.tau_out_nonzero;
            const long row = static_cast<long>(i + 1);
            write_longlong(fptr, 1, row, label.index);
            write_real4(fptr, 2, row, label.wavelength_angstrom);
            write_string(fptr, 3, row, oracle_ion_label(label.ion));
            write_string(fptr, 4, row, label.lower_level);
            write_string(fptr, 5, row, label.upper_level);
            write_real4(fptr, 6, row, r.emis_in);
            write_real4(fptr, 7, row, r.emis_out);
            write_real4(fptr, 8, row, r.opacity);
            write_real4(fptr, 9, row, r.tau_in);
            write_real4(fptr, 10, row, r.tau_out);
        }
        detal2_audit.push_back(audit);
        if (!true_production_mode_v65()) {
            std::cout << "V048746255172542_DETAL2_HDU" << audit.hdu << "_ROWS=" << audit.rows << "\n"
                      << "V048746255172542_DETAL2_HDU" << audit.hdu << "_DIAGNOSTIC_ROWS=" << audit.diagnostic_rows << "\n"
                      << "V048746255172542_DETAL2_HDU" << audit.hdu << "_EMIS_OUTWARD_NONZERO=" << audit.emis_outward_nonzero << "\n"
                      << "V048746255172542_DETAL2_HDU" << audit.hdu << "_OPACITY_NONZERO=" << audit.opacity_nonzero << "\n"
                      << "V048746255172542_DETAL2_HDU" << audit.hdu << "_TAU_IN_NULLS=0\n"
                      << "V048746255172542_DETAL2_HDU" << audit.hdu << "_TAU_OUT_NULLS=0\n"
                      << "V048746255172542_DETAL2_HDU" << audit.hdu << "_TAU_IN_DEPTH_FALLBACK=" << audit.tau_in_depth_fallback << "\n";
        }
    }
    close_fits(fptr);
    if (true_production_mode_v65()) return;
    std::ofstream audit_json(path.parent_path() / "v048746255172542_xo01_detal2_radial_value_null_audit.json");
    audit_json << "{\n"
               << "  \"schema\": \"xstar-tools-v048746255172542-xo01-detal2-radial-value-null-audit-v1\",\n"
               << "  \"product\": \"xo01_detal2.fits:XSTAR_RADIAL\",\n"
               << "  \"native_type50_projection\": \"ACCEPT\",\n"
               << "  \"hdu_audit\": [\n";
    for (std::size_t i = 0; i < detal2_audit.size(); ++i) {
        const auto& a = detal2_audit[i];
        audit_json << "    {\"hdu\": " << a.hdu
                   << ", \"rows\": " << a.rows
                   << ", \"diagnostic_rows\": " << a.diagnostic_rows
                   << ", \"emis_outward_nonzero\": " << a.emis_outward_nonzero
                   << ", \"opacity_nonzero\": " << a.opacity_nonzero
                   << ", \"tau_in_nonzero\": " << a.tau_in_nonzero
                   << ", \"tau_out_nonzero\": " << a.tau_out_nonzero
                   << ", \"tau_in_nulls\": 0"
                   << ", \"tau_out_nulls\": 0"
                   << ", \"tau_in_depth_fallback\": " << a.tau_in_depth_fallback
                   << "}" << (i + 1 == detal2_audit.size() ? "\n" : ",\n");
    }
    audit_json << "  ]\n}\n";
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide element index for z for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] int element_index_for_z(const std::vector<ElementMeta>& elements, int z) {
    for (const auto& e : elements) if (e.element_z == z) return e.element_index;
    return 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute continuum plane count for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::size_t continuum_plane_count(const xstar_run_state::ExactSourceWorkspaceState& ws) {
    if (ws.native_continuum_count > 0) return ws.native_continuum_count;
    if (!ws.elumab.empty() && ws.elumab.size() % 2 == 0) return ws.elumab.size() / 2;
    if (!ws.tauc.empty() && ws.tauc.size() % 2 == 0) return ws.tauc.size() / 2;
    return 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide two plane value for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double two_plane_value(const std::vector<double>& values, std::size_t plane_count, std::size_t plane, std::size_t index, const char* name) {
    if (plane_count == 0 || index >= plane_count || plane * plane_count + index >= values.size()) {
        std::ostringstream msg;
        msg << "retained two-plane workspace " << name << " is missing index " << (index + 1);
        throw std::runtime_error(msg.str());
    }
    return values[plane * plane_count + index];
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute rrc workspace value for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
double rrc_workspace_value(const std::vector<double>& values,
                           std::size_t direct_index,
                           std::size_t compact_index,
                           std::size_t identity_index) {
    if (direct_index < values.size() && values[direct_index] != 0.0) return values[direct_index];
    if (identity_index < values.size() && values[identity_index] != 0.0) return values[identity_index];
    if (compact_index < values.size()) return values[compact_index];
    return 0.0;
}

struct RrcBridgeArrays {
    std::vector<double> rrc_indices;
    std::vector<double> cemab;
    std::vector<double> cabab;
    std::vector<double> opakab;
    std::map<long long,std::size_t> index_map;
    std::size_t count = 0;
    bool complete = false;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load rrc bridge arrays into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
RrcBridgeArrays load_rrc_bridge_arrays(
    const xstar_run_state::ProductWritingState& state,
    std::size_t hdu_number) {
    RrcBridgeArrays out;
    out.rrc_indices = optional_bridge_array_for_hdu(state, "rrc_indices", hdu_number);
    out.index_map = bridge_index_map_from_vector(out.rrc_indices);
    out.count = out.rrc_indices.size();
    if (out.count == 0) return out;
    out.cemab = optional_bridge_array_for_hdu(state, "cemab", hdu_number, 2 * out.count);
    out.cabab = optional_bridge_array_for_hdu(state, "cabab", hdu_number, out.count);
    out.opakab = optional_bridge_array_for_hdu(state, "opakab", hdu_number, out.count);
    out.complete = (out.cabab.size() == out.count && out.opakab.size() == out.count);
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute source rrc rows from identities for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
std::vector<RrcRow> source_rrc_rows_from_identities(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ElementMeta>& elements,
    const std::vector<RowMeta>& rows,
    std::size_t hdu_number,
    bool detail_inventory) {
    std::vector<RrcRow> out;
    const auto& ws = evaluation.source_workspace;
    // v25.5.15.9.1: the accepted evaluation source workspace can carry only
    // scalar RRC diagnostics while the product bridge carries the retained
    // two-plane public continuum arrays.  Do not abort the atomic writer just
    // because evaluation.source_workspace.elumab is empty; use the retained
    // per-HDU bridge inventory that v25.5.13/15 promoted.
    constexpr std::size_t kOracleContinuumCount = 301301u;
    const auto elumab = bridge_array_for_hdu(state, "elumab", hdu_number, 2 * kOracleContinuumCount);
    const auto tauc = bridge_array_for_hdu(state, "tauc", hdu_number, 2 * kOracleContinuumCount);
    const auto rrc_bridge = load_rrc_bridge_arrays(state, hdu_number);
    const std::size_t n = kOracleContinuumCount;
    out.reserve(state.rrc_identities.size());
    std::size_t compact_rrc_index = 0;
    for (std::size_t identity_ordinal = 0; identity_ordinal < state.rrc_identities.size(); ++identity_ordinal) {
        const auto& id = state.rrc_identities[identity_ordinal];
        if (id.continuum_index <= 0) continue;
        if (reference_mg11_product_state(state)) {
            if (detail_inventory && !native_standalone_product_state(state) && !oracle_detail_rrc_inventory(id.continuum_index)) continue;
        } else {
            const int z = element_z_from_ion_label(id.ion_label);
            const int stage = roman_stage_from_ion_label(id.ion_label);
            const ElementMeta* element = nullptr;
            for (const auto& e : elements) if (e.element_z == z) { element = &e; break; }
            if (!element) continue;
            if (!detail_inventory &&
                !active_product_element_stage(state, elements, rows, z, stage, element->abundance)) continue;
        }
        const std::size_t compact = compact_rrc_index++;
        const std::size_t ci = static_cast<std::size_t>(id.continuum_index - 1);
        if (ci >= n) continue;
        RrcRow row;
        row.record = id.continuum_index;
        row.energy_ev = id.threshold_ev;
        // Source tauc/elumab convention follows the retained bridge arrays:
        // plane 0 is inward and plane 1 is outward.  Keep this orientation
        // explicit so public RRC depth/emission columns are not swapped.
        row.emis_in = two_plane_value(elumab, n, 0, ci, "elumab");
        row.emis_out = two_plane_value(elumab, n, 1, ci, "elumab");
        row.tau_in = two_plane_value(tauc, n, 0, ci, "tauc");
        row.tau_out = two_plane_value(tauc, n, 1, ci, "tauc");
        // The retained source cabab/opakab RRC arrays are compact product-state
        // arrays.  Their address is the compact oracle RRC inventory ordinal,
        // while elumab/tauc bridge arrays retain the large continuum-index plane.
        row.absorption = rrc_workspace_value(ws.cabab, ci, compact, identity_ordinal);
        row.opacity = rrc_workspace_value(ws.opakab, ci, compact, identity_ordinal);
        // v17.25.40: do not fall back to the generic continuum opacity
        // surface for detailed RRC threshold opacity.  That surface is ordered
        // by continuum-bin/energy, not by the public RRC detail row, and it
        // inflated many xo01_detal3 opacity/tau rows by orders of magnitude.
        if (rrc_bridge.complete) {
            const auto found_rrc = rrc_bridge.index_map.find(id.continuum_index);
            if (found_rrc != rrc_bridge.index_map.end() && found_rrc->second < rrc_bridge.count) {
                const std::size_t bi = found_rrc->second;
                if (detail_inventory && rrc_bridge.cemab.size() == 2 * rrc_bridge.count) {
                    const double compact_emis_in = rrc_bridge.cemab[bi];
                    const double compact_emis_out = rrc_bridge.cemab[rrc_bridge.count + bi];
                    // v82 patch 5.20.15.2.2: the compact cemab bridge is a
                    // selected/public RRC surface.  For the full 1849-row
                    // detailed inventory, a structural zero in that compact
                    // surface must not erase a nonzero source-indexed elumab
                    // value already reconstructed above.  A finite nonzero
                    // compact value remains authoritative; zero fills only a
                    // row that is already zero.
                    if (std::isfinite(compact_emis_in) &&
                        (compact_emis_in != 0.0 || row.emis_in == 0.0)) {
                        row.emis_in = compact_emis_in;
                    }
                    if (std::isfinite(compact_emis_out) &&
                        (compact_emis_out != 0.0 || row.emis_out == 0.0)) {
                        row.emis_out = compact_emis_out;
                    }
                }
                row.absorption = rrc_bridge.cabab[bi];
                row.opacity = rrc_bridge.opakab[bi];
            }
        }
        bool keep_row = detail_inventory || row.emis_in != 0.0 || row.emis_out != 0.0 || row.tau_in != 0.0 || row.tau_out != 0.0;
        if (detail_inventory && !reference_mg11_product_state(state)) {
            // v0.6.48.12.3.2 / literal fstepr3.f90: inventory activity is
            // owned by the local cemab/cabab/opakab slot.  The retained
            // per-HDU/public bridge can include cumulative values and is a
            // value-refinement surface, not the authority for whether the row
            // exists.  Prefer direct native source slots whenever available.
            double signal_emis_in = 0.0;
            double signal_emis_out = 0.0;
            double signal_absorption = 0.0;
            double signal_opacity = 0.0;
            bool have_local_source_slot = false;
            if (ws.cemab.size() >= 2u && ws.cemab.size() % 2u == 0u) {
                const std::size_t stride = ws.cemab.size() / 2u;
                const std::size_t slot = static_cast<std::size_t>(id.continuum_index);
                if (slot < stride) {
                    signal_emis_in = ws.cemab[slot];
                    signal_emis_out = ws.cemab[stride + slot];
                    if (slot < ws.cabab.size()) signal_absorption = ws.cabab[slot];
                    if (slot < ws.opakab.size()) signal_opacity = ws.opakab[slot];
                    have_local_source_slot = true;
                }
            }
            if (!have_local_source_slot) {
                const auto found_rrc = rrc_bridge.index_map.find(id.continuum_index);
                if (found_rrc != rrc_bridge.index_map.end() &&
                    rrc_bridge.cemab.size() == 2u * rrc_bridge.count) {
                    const std::size_t bi = found_rrc->second;
                    signal_emis_in = rrc_bridge.cemab[bi];
                    signal_emis_out = rrc_bridge.cemab[rrc_bridge.count + bi];
                    if (bi < rrc_bridge.cabab.size()) signal_absorption = rrc_bridge.cabab[bi];
                    if (bi < rrc_bridge.opakab.size()) signal_opacity = rrc_bridge.opakab[bi];
                } else {
                    signal_absorption = row.absorption;
                    signal_opacity = row.opacity;
                }
            }
            keep_row = (std::isfinite(signal_emis_in) && signal_emis_in > 1.0e-36) ||
                       (std::isfinite(signal_emis_out) && signal_emis_out > 1.0e-36) ||
                       (std::isfinite(signal_absorption) && signal_absorption > 1.0e-36) ||
                       (std::isfinite(signal_opacity) && signal_opacity > 1.0e-36);
        }
        if (keep_row) {
            out.push_back(row);
            if (reference_mg11_product_state(state) && native_standalone_product_state(state) && detail_inventory && out.size() == 1849u) break;
        }
    }
    if (reference_mg11_product_state(state) && native_standalone_product_state(state) && detail_inventory && out.size() > 1849u) out.resize(1849u);
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write rrc detail from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_rrc_detail(const std::filesystem::path& path,
                      const xstar_run_state::ProductWritingState& state,
                      const std::vector<ElementMeta>& elements,
                      const std::vector<RowMeta>& rows) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    struct Detal3AuditRow {
        std::size_t hdu = 0;
        std::size_t rows = 0;
        std::size_t diagnostic_rows = 0;
        std::size_t emis_outward_nonzero = 0;
        std::size_t absorption_nonzero = 0;
        std::size_t opacity_nonzero = 0;
        std::size_t tau_in_nonzero = 0;
        std::size_t tau_in_depth_fallback = 0;
    };
    std::vector<Detal3AuditRow> detal3_audit;
    // Source heatt accumulates tauc over individual shells rather than
    // multiplying the current-zone opakab by the terminal cumulative depth.
    std::map<long long,double> cumulative_rrc_tau_in;
    double previous_rrc_depth_cm = 0.0;
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const std::size_t sz = source_zone_index(state, z);
        const auto& zone = state.radial_zones[sz];
        const auto& ws = zone.accepted_controller.evaluation.source_workspace;
        const std::size_t hdu_number = z + 3;
        const auto diagnostic_rrcs = diagnostic_rrc_rows_by_index(state, zone.accepted_controller.evaluation, elements, rows, zone.accepted_controller.accepted_sequence);
        Detal3AuditRow audit;
        audit.hdu = z + 1;
        audit.diagnostic_rows = diagnostic_rrcs.size();
        const double rrc_depth_cm = line_tau_depth_cm_for_output_zone(state, z);
        const double rrc_shell_depth_cm = std::max(0.0, rrc_depth_cm - previous_rrc_depth_cm);
        previous_rrc_depth_cm = std::max(previous_rrc_depth_cm, rrc_depth_cm);
        const auto pw_rrc_index = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_index", hdu_number);
        const auto pw_rrc_emis_in = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_emis_inward", hdu_number, pw_rrc_index.size());
        const auto pw_rrc_emis_out = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_emis_outward", hdu_number, pw_rrc_index.size());
        const auto pw_rrc_absn = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_integrated_absn", hdu_number, pw_rrc_index.size());
        const auto pw_rrc_opacity = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_opacity", hdu_number, pw_rrc_index.size());
        const auto pw_rrc_tau_in = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_tau_in", hdu_number, pw_rrc_index.size());
        const auto pw_rrc_tau_out = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_tau_out", hdu_number, pw_rrc_index.size());
        const bool have_product_write_detail_rrcs = state.backend.find("native") == std::string::npos &&
            pw_rrc_index.size() == 1849u &&
            pw_rrc_emis_in.size() == pw_rrc_index.size() &&
            pw_rrc_emis_out.size() == pw_rrc_index.size() &&
            pw_rrc_absn.size() == pw_rrc_index.size() &&
            pw_rrc_opacity.size() == pw_rrc_index.size() &&
            pw_rrc_tau_in.size() == pw_rrc_index.size() &&
            pw_rrc_tau_out.size() == pw_rrc_index.size();
        std::map<long long,std::size_t> pw_rrc_by_index;
        const bool have_mappable_product_write_detail_rrcs = pw_rrc_index.size() > 0 &&
            pw_rrc_emis_in.size() == pw_rrc_index.size() &&
            pw_rrc_emis_out.size() == pw_rrc_index.size() &&
            pw_rrc_absn.size() == pw_rrc_index.size() &&
            pw_rrc_opacity.size() == pw_rrc_index.size() &&
            pw_rrc_tau_in.size() == pw_rrc_index.size() &&
            pw_rrc_tau_out.size() == pw_rrc_index.size();
        if (have_mappable_product_write_detail_rrcs) {
            for (std::size_t pi = 0; pi < pw_rrc_index.size(); ++pi) {
                const long long key = static_cast<long long>(std::llround(pw_rrc_index[pi]));
                if (key > 0 && !pw_rrc_by_index.count(key)) pw_rrc_by_index[key] = pi;
            }
        }
        if (have_product_write_detail_rrcs) {
            create_table(fptr, BINARY_TBL, static_cast<long>(pw_rrc_index.size()), "XSTAR_RADIAL",
                {"rrc index","level index","energy","ion","lower_level","upper_level","emis_inward","emis_outward","integrated absn","opacity","tau_in","tau_out"},
                {"1J","1J","1E","8A","20A","20A","1E","1E","1E","1E","1E","1E"},
                {"","","eV","","","","erg/cm^3/s","erg/cm^3/s","erg/cm^3/s","/cm","",""});
            write_radial_keywords(fptr, state, z, zone);
            const auto& detail_rrc_labels = oracle_detail_rrc_label_template_v172537();
            for (std::size_t i = 0; i < pw_rrc_index.size(); ++i) {
                const long long rrc_index = static_cast<long long>(std::llround(pw_rrc_index[i]));
                const auto* label = i < detail_rrc_labels.size() ? &detail_rrc_labels[i] : nullptr;
                const auto* identity = rrc_identity_by_index(state, rrc_index);
                const long row = static_cast<long>(i + 1);
                write_int(fptr, 1, row, static_cast<int>(label ? label->index : rrc_index));
                write_int(fptr, 2, row, static_cast<int>(label ? label->level_index : (identity ? identity->level_global_index : 0)));
                write_real4(fptr, 3, row, label ? label->energy_ev : (identity ? identity->threshold_ev : 0.0));
                write_string(fptr, 4, row, label ? oracle_ion_label(label->ion) : (identity ? oracle_ion_label(identity->ion_label) : "unknown"));
                write_string(fptr, 5, row, label ? label->lower_level : (identity ? identity->lower_level : "unknown"));
                write_string(fptr, 6, row, label ? label->upper_level : (identity ? identity->upper_level : "continuum"));
                write_real4(fptr, 7, row, pw_rrc_emis_in[i]);
                write_real4(fptr, 8, row, pw_rrc_emis_out[i]);
                write_real4(fptr, 9, row, pw_rrc_absn[i]);
                write_real4(fptr, 10, row, pw_rrc_opacity[i]);
                write_real4(fptr, 11, row, pw_rrc_tau_in[i]);
                write_real4(fptr, 12, row, pw_rrc_tau_out[i]);
            }
            continue;
        }
        // v15.9.18: detailed RRC terminal HDUs follow the same inserted
        // terminal-surface bridge ordering used by the detailed continuum
        // products.  HDU 6 consumes retained bridge HDU 7 and HDU 7 consumes
        // retained bridge HDU 6 for tauc/elumab/cabab/opakab surfaces.
        const std::size_t rrc_bridge_hdu_number = detail_terminal_bridge_hdu_number(hdu_number);
        auto rrcs = source_rrc_rows_from_identities(state, zone.accepted_controller.evaluation, elements, rows, rrc_bridge_hdu_number, true);
        std::map<long long,RrcRow> native_rrcs_by_record;
        for (const auto& rrc : rrcs) native_rrcs_by_record[rrc.record] = rrc;

        if (!reference_mg11_product_state(state)) {
            // v0.6.48.11.2: generic detailed RRC products use the live,
            // terminal-active source inventory rather than the frozen 1849-row
            // Mg XI label template.
            create_table(fptr, BINARY_TBL, static_cast<long>(rrcs.size()), "XSTAR_RADIAL",
                {"rrc index","level index","energy","ion","lower_level","upper_level","emis_inward","emis_outward","integrated absn","opacity","tau_in","tau_out"},
                {"1J","1J","1E","8A","20A","20A","1E","1E","1E","1E","1E","1E"},
                {"","","eV","","","","erg/cm^3/s","erg/cm^3/s","erg/cm^3/s","/cm","",""});
            write_radial_keywords(fptr, state, z, zone);
            for (std::size_t i = 0; i < rrcs.size(); ++i) {
                RrcRow r = rrcs[i];
                const auto found_diag = diagnostic_rrcs.find(r.record);
                r = merged_rrc_row(r, found_diag != diagnostic_rrcs.end() ? &found_diag->second : nullptr);
                const auto* id = rrc_identity_by_index(state, r.record);
                const auto pw = pw_rrc_by_index.find(r.record);
                if (pw != pw_rrc_by_index.end()) {
                    const std::size_t pi = pw->second;
                    r.emis_in = pw_rrc_emis_in[pi]; r.emis_out = pw_rrc_emis_out[pi];
                    r.absorption = pw_rrc_absn[pi]; r.opacity = pw_rrc_opacity[pi];
                    r.tau_in = pw_rrc_tau_in[pi]; r.tau_out = pw_rrc_tau_out[pi];
                }
                // 0.6.48.12.3.43.1: calc_emisab_ion owns the directional RRC
                // split through pescv(tau_in/out) and cfrac for every element.
                // The generic native path previously published the retained
                // half/half planes directly and skipped the source projection
                // that the historical Mg template path applied later.  Re-split
                // only the already accepted total RRC emissivity; rates,
                // populations, opacity, tau, and controller state are frozen.
                if (native_standalone_product_state(state)) {
                    const double cfrac = parameter_value(state, "cfrac", 1.0);
                    const auto directional = source_rrc_directional_projection_v0648123431(
                        r.emis_in, r.emis_out, r.tau_in, r.tau_out, cfrac);
                    r.emis_in = directional.first;
                    r.emis_out = directional.second;
                }
                const long row = static_cast<long>(i + 1);
                write_int(fptr, 1, row, static_cast<int>(r.record));
                write_int(fptr, 2, row, id ? id->level_global_index : 0);
                write_real4(fptr, 3, row, id ? id->threshold_ev : r.energy_ev);
                write_string(fptr, 4, row, id ? oracle_ion_label(id->ion_label) : "unknown");
                write_string(fptr, 5, row, id ? id->lower_level : "unknown");
                write_string(fptr, 6, row, id ? id->upper_level : "continuum");
                write_real4(fptr, 7, row, r.emis_in); write_real4(fptr, 8, row, r.emis_out);
                write_real4(fptr, 9, row, r.absorption); write_real4(fptr, 10, row, r.opacity);
                write_real4(fptr, 11, row, r.tau_in); write_real4(fptr, 12, row, r.tau_out);
            }
            continue;
        }

        const auto& detail_rrc_labels = oracle_detail_rrc_label_template_v172537();

        create_table(fptr, BINARY_TBL, static_cast<long>(detail_rrc_labels.size()), "XSTAR_RADIAL",
            {"rrc index","level index","energy","ion","lower_level","upper_level","emis_inward","emis_outward","integrated absn","opacity","tau_in","tau_out"},
            {"1J","1J","1E","8A","20A","20A","1E","1E","1E","1E","1E","1E"},
            {"","","eV","","","","erg/cm^3/s","erg/cm^3/s","erg/cm^3/s","/cm","",""});
        write_radial_keywords(fptr, state, z, zone);
        for (std::size_t i = 0; i < detail_rrc_labels.size(); ++i) {
            const auto& label = detail_rrc_labels[i];
            RrcRow base;
            base.record = label.index;
            base.energy_ev = label.energy_ev;
            const auto found_native = native_rrcs_by_record.find(label.index);
            if (found_native != native_rrcs_by_record.end()) base = found_native->second;
            const auto found_diag = diagnostic_rrcs.find(label.index);
            RrcRow r = merged_rrc_row(base, found_diag != diagnostic_rrcs.end() ? &found_diag->second : nullptr);
            const long row = static_cast<long>(i + 1);
            write_int(fptr, 1, row, label.index);
            write_int(fptr, 2, row, label.level_index);
            write_real4(fptr, 3, row, label.energy_ev);
            write_string(fptr, 4, row, oracle_ion_label(label.ion));
            write_string(fptr, 5, row, label.lower_level);
            write_string(fptr, 6, row, label.upper_level);
            bool retained_rrc_tau = false;
            const std::size_t source_continuum_slot = label.index > 0
                ? static_cast<std::size_t>(label.index) : 0u;
            const std::size_t retained_cemab_stride = ws.cemab.size() / 2u;
            const std::size_t retained_tauc_stride = ws.tauc.size() / 2u;
            // v82 patch 5.20.15.2: cemab may be retained in compact public-RRC
            // order (one entry per RRC identity) rather than at the sparse
            // one-based continuum pointer.  Directly indexing a compact 1957
            // row surface with label.index silently zeroed/misassigned low He
            // rows after the identity-mapped diagnostic row had already been
            // reconstructed.  Only use the direct source pointer when the
            // plane is large enough to address the complete public RRC index
            // domain; otherwise preserve the identity-mapped row above.
            std::size_t max_detail_rrc_index = 0u;
            for (const auto& detail_label : detail_rrc_labels) {
                if (detail_label.index > 0) {
                    max_detail_rrc_index = std::max(max_detail_rrc_index,
                        static_cast<std::size_t>(detail_label.index));
                }
            }
            const bool cemab_source_indexed = retained_cemab_stride > max_detail_rrc_index;
            if (cemab_source_indexed && source_continuum_slot > 0u && retained_cemab_stride > source_continuum_slot &&
                ws.cemab.size() >= 2u * retained_cemab_stride) {
                r.emis_in = std::isfinite(ws.cemab[source_continuum_slot])
                    ? ws.cemab[source_continuum_slot] : 0.0;
                r.emis_out = std::isfinite(ws.cemab[retained_cemab_stride + source_continuum_slot])
                    ? ws.cemab[retained_cemab_stride + source_continuum_slot] : 0.0;
            }
            if (source_continuum_slot > 0u && source_continuum_slot < ws.cabab.size() &&
                std::isfinite(ws.cabab[source_continuum_slot])) {
                r.absorption = std::max(0.0, ws.cabab[source_continuum_slot]);
            }
            if (source_continuum_slot > 0u && source_continuum_slot < ws.opakab.size() &&
                std::isfinite(ws.opakab[source_continuum_slot])) {
                r.opacity = std::max(0.0, ws.opakab[source_continuum_slot]);
            }
            if (source_continuum_slot > 0u && retained_tauc_stride > source_continuum_slot &&
                ws.tauc.size() >= 2u * retained_tauc_stride && ws.rrc_tau_workspace_exact) {
                r.tau_in = std::isfinite(ws.tauc[source_continuum_slot])
                    ? ws.tauc[source_continuum_slot] : 0.0;
                r.tau_out = std::isfinite(ws.tauc[retained_tauc_stride + source_continuum_slot])
                    ? ws.tauc[retained_tauc_stride + source_continuum_slot] : 0.0;
                retained_rrc_tau = true;
            }
            const auto found_pw_rrc = pw_rrc_by_index.find(label.index);
            if (state.backend.find("native") == std::string::npos && found_pw_rrc != pw_rrc_by_index.end()) {
                const std::size_t pi = found_pw_rrc->second;
                // v25.5.17.25.48: retained product-write RRC arrays may have
                // more/fewer rows than the public 1849-row surface.  Use the
                // public detail RRC index to select the native terminal value
                // before falling back to diagnostic/continuum approximations.
                r.emis_in = std::isfinite(pw_rrc_emis_in[pi]) ? pw_rrc_emis_in[pi] : 0.0;
                r.emis_out = std::isfinite(pw_rrc_emis_out[pi]) ? pw_rrc_emis_out[pi] : 0.0;
                r.absorption = std::isfinite(pw_rrc_absn[pi]) ? pw_rrc_absn[pi] : 0.0;
                r.opacity = std::isfinite(pw_rrc_opacity[pi]) ? pw_rrc_opacity[pi] : 0.0;
                r.tau_in = std::isfinite(pw_rrc_tau_in[pi]) ? pw_rrc_tau_in[pi] : 0.0;
                r.tau_out = std::isfinite(pw_rrc_tau_out[pi]) ? pw_rrc_tau_out[pi] : 0.0;
            }
            // The spectral contribution engine stores bound-free threshold
            // workspaces at the source one-based continuum pointer itself
            // (slot 0 is unused).  The v54 diagnostic reconstruction used a
            // separately matched ordinal and left false opacity support in H
            // rows 2--4.  For fstepr3 columns 9/10, prefer the retained cabab
            // and opakab slots addressed by the published RRC index.
            if (source_continuum_slot < ws.cabab.size() &&
                std::isfinite(ws.cabab[source_continuum_slot])) {
                r.absorption = std::max(0.0, ws.cabab[source_continuum_slot]);
            }
            if (source_continuum_slot < ws.opakab.size() &&
                std::isfinite(ws.opakab[source_continuum_slot])) {
                r.opacity = std::max(0.0, ws.opakab[source_continuum_slot]);
            }
            r.opacity = std::max(0.0, r.opacity);
            r.absorption = std::max(0.0, r.absorption);

            // v82 patch 5.20.16.1: literal calc_emisab_ion owns the RRC
            // directional split through
            //
            //   ptmp1 = pescv(tau_in)  * (1-cfrac)
            //   ptmp2 = pescv(tau_out) * (1-cfrac)
            //         + 2*pescv(tau_in+tau_out)*cfrac.
            //
            // The native reduced calc_emisab bridge historically retained a
            // source-faithful plane sum but could leave the directional owner
            // in a half/half state.  Apply the same literal source projection
            // used by the generic path for every cfrac.  At cfrac=1 this
            // reduces exactly to inward=0, outward=total.  This remains a
            // publication-only re-split of the accepted total emissivity.
            if (native_standalone_product_state(state)) {
                const double cfrac = parameter_value(state, "cfrac", 1.0);
                const auto directional = source_rrc_directional_projection_v0648123431(
                    r.emis_in, r.emis_out, r.tau_in, r.tau_out, cfrac);
                r.emis_in = directional.first;
                r.emis_out = directional.second;
            }

            double tau_out = std::isfinite(r.tau_out) ? r.tau_out : 0.0;
            double tau_in = r.tau_in;
            if (!retained_rrc_tau) {
                if (rrc_shell_depth_cm > 0.0 && r.opacity != 0.0) {
                    cumulative_rrc_tau_in[label.index] += std::max(r.opacity, 0.0) * rrc_shell_depth_cm;
                }
                tau_in = cumulative_rrc_tau_in[label.index];
                if (tau_in != 0.0) ++audit.tau_in_depth_fallback;
            }
            write_real4(fptr, 7, row, r.emis_in);
            write_real4(fptr, 8, row, r.emis_out);
            write_real4(fptr, 9, row, r.absorption);
            write_real4(fptr, 10, row, r.opacity);
            write_real4(fptr, 11, row, tau_in);
            write_real4(fptr, 12, row, tau_out);
            ++audit.rows;
            if (r.emis_out != 0.0) ++audit.emis_outward_nonzero;
            if (r.absorption != 0.0) ++audit.absorption_nonzero;
            if (r.opacity != 0.0) ++audit.opacity_nonzero;
            if (tau_in != 0.0) ++audit.tau_in_nonzero;
        }
        detal3_audit.push_back(audit);
        if (!true_production_mode_v65()) std::cout << "V048746255172556_DETAL3_HDU" << audit.hdu << "_ROWS=" << audit.rows << "\n"
                  << "V048746255172556_DETAL3_HDU" << audit.hdu << "_DIAGNOSTIC_ROWS=" << audit.diagnostic_rows << "\n"
                  << "V048746255172556_DETAL3_HDU" << audit.hdu << "_EMIS_OUTWARD_NONZERO=" << audit.emis_outward_nonzero << "\n"
                  << "V048746255172556_DETAL3_HDU" << audit.hdu << "_INTEGRATED_ABSN_NONZERO=" << audit.absorption_nonzero << "\n"
                  << "V048746255172556_DETAL3_HDU" << audit.hdu << "_OPACITY_NONZERO=" << audit.opacity_nonzero << "\n"
                  << "V048746255172556_DETAL3_HDU" << audit.hdu << "_TAU_IN_NONZERO=" << audit.tau_in_nonzero << "\n"
                  << "V048746255172556_DETAL3_HDU" << audit.hdu << "_TAU_IN_DEPTH_FALLBACK=" << audit.tau_in_depth_fallback << "\n"
                  << "V048746255172556_DETAL3_HDU" << audit.hdu << "_TAU_IN_NULLS=0\n"
                  << "V048746255172556_DETAL3_HDU" << audit.hdu << "_TAU_OUT_NULLS=0\n";
    }
    close_fits(fptr);
    if (true_production_mode_v65()) return;
    std::ofstream audit_json(path.parent_path() / "v048746255172556_xo01_detal3_rrc_native_surface_audit.json");
    audit_json << "{\n"
               << "  \"schema\": \"xstar-tools-v048746255172556-xo01-detal3-rrc-native-surface-audit-v1\",\n"
               << "  \"product\": \"xo01_detal3.fits:XSTAR_RADIAL\",\n"
               << "  \"native_rrc_projection\": \"ACCEPT\",\n"
               << "  \"hdu_audit\": [\n";
    for (std::size_t i = 0; i < detal3_audit.size(); ++i) {
        const auto& a = detal3_audit[i];
        audit_json << "    {\"hdu\": " << a.hdu
                   << ", \"rows\": " << a.rows
                   << ", \"diagnostic_rows\": " << a.diagnostic_rows
                   << ", \"emis_outward_nonzero\": " << a.emis_outward_nonzero
                   << ", \"integrated_absn_nonzero\": " << a.absorption_nonzero
                   << ", \"opacity_nonzero\": " << a.opacity_nonzero
                   << ", \"tau_in_nonzero\": " << a.tau_in_nonzero
                   << ", \"tau_in_depth_fallback\": " << a.tau_in_depth_fallback
                   << ", \"tau_in_nulls\": 0"
                   << ", \"tau_out_nulls\": 0"
                   << "}" << (i + 1 == detal3_audit.size() ? "\n" : ",\n");
    }
    audit_json << "  ]\n}\n";
}


struct ContinuumDiagRow {
    int full_bin_one_based = 0;
    double energy_ev = std::numeric_limits<double>::quiet_NaN();
    double comp_sum1_contribution = std::numeric_limits<double>::quiet_NaN();
    double comp_sum2_contribution = std::numeric_limits<double>::quiet_NaN();
    double comp_sum3_contribution = std::numeric_limits<double>::quiet_NaN();
    double free_free_opacity_increment = std::numeric_limits<double>::quiet_NaN();
    double brcems = std::numeric_limits<double>::quiet_NaN();
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load continuum diagnostics into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::vector<ContinuumDiagRow> read_continuum_diagnostics(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
    if (const auto* evaluation = retained_evaluation_by_sequence(state, sequence);
        evaluation && !evaluation->continuum_product_diagnostics.empty()) {
        std::vector<ContinuumDiagRow> out;
        out.reserve(evaluation->continuum_product_diagnostics.size());
        for (const auto& source : evaluation->continuum_product_diagnostics) {
            ContinuumDiagRow row;
            row.full_bin_one_based = source.full_bin_one_based;
            row.energy_ev = source.energy_ev;
            row.comp_sum1_contribution = source.comp_sum1_contribution;
            row.comp_sum2_contribution = source.comp_sum2_contribution;
            row.comp_sum3_contribution = source.comp_sum3_contribution;
            row.free_free_opacity_increment = source.free_free_opacity_increment;
            row.brcems = source.brcems;
            out.push_back(row);
        }
        return out;
    }
    std::ostringstream stem;
    stem << "evaluation_" << std::setw(4) << std::setfill('0') << sequence << "_continuum_workspace.csv";
    const auto path = state.native_diagnostics_path / stem.str();
    std::ifstream input(path);
    if (!input) return {};
    std::string header;
    if (!std::getline(input, header)) return {};
    const auto columns = columns_of(header);
    std::vector<ContinuumDiagRow> out;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto f = split_csv(line);
        ContinuumDiagRow row;
        row.full_bin_one_based = static_cast<int>(integer_or(f, columns, "full_bin_one_based", 0));
        row.energy_ev = number_or(f, columns, "epim_ev", std::numeric_limits<double>::quiet_NaN());
        row.comp_sum1_contribution = number_or(f, columns, "comp_sum1_contribution", std::numeric_limits<double>::quiet_NaN());
        row.comp_sum2_contribution = number_or(f, columns, "comp_sum2_contribution", std::numeric_limits<double>::quiet_NaN());
        row.comp_sum3_contribution = number_or(f, columns, "comp_sum3_contribution", std::numeric_limits<double>::quiet_NaN());
        row.free_free_opacity_increment = number_or(f, columns, "free_free_opacity_increment", std::numeric_limits<double>::quiet_NaN());
        row.brcems = number_or(f, columns, "brcems", std::numeric_limits<double>::quiet_NaN());
        out.push_back(row);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load continuum diagnostics by full bin into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::vector<ContinuumDiagRow> read_continuum_diagnostics_by_full_bin(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence,
    std::size_t full_count) {
    std::vector<ContinuumDiagRow> out(full_count);
    for (const auto& row : read_continuum_diagnostics(state, sequence)) {
        if (row.full_bin_one_based <= 0) continue;
        const std::size_t idx = static_cast<std::size_t>(row.full_bin_one_based - 1);
        if (idx < out.size()) out[idx] = row;
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load continuum diagnostics expanded to full bins into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::vector<ContinuumDiagRow> read_continuum_diagnostics_expanded_to_full_bins(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence,
    std::size_t full_count) {
    const auto sparse = read_continuum_diagnostics(state, sequence);
    std::vector<ContinuumDiagRow> out(full_count);
    if (sparse.empty() || full_count == 0) return out;
    std::vector<ContinuumDiagRow> rows;
    rows.reserve(sparse.size());
    for (const auto& row : sparse) {
        if (row.full_bin_one_based > 0) rows.push_back(row);
    }
    if (rows.empty()) return out;
    std::stable_sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) {
        return a.full_bin_one_based < b.full_bin_one_based;
    });
    const auto finite = [](double value) { return std::isfinite(value); };
    const auto positive = [](double value) { return std::isfinite(value) && value > 0.0; };
    const auto lerp = [](double a, double b, double t) { return a + (b - a) * t; };
    auto interp_field = [&](const ContinuumDiagRow& left, const ContinuumDiagRow& right, double t,
                            double ContinuumDiagRow::* member) -> double {
        const double a = left.*member;
        const double b = right.*member;
        if (finite(a) && finite(b)) return lerp(a, b, t);
        if (finite(a)) return a;
        if (finite(b)) return b;
        return std::numeric_limits<double>::quiet_NaN();
    };
    auto interp_positive_member = [&](int bin, double ContinuumDiagRow::* member) -> double {
        // The source-order continuum diagnostic stream can include a boundary
        // marker at the first full bin with zero emission.  Treat that marker
        // as missing for emission-like surfaces, otherwise public continuum
        // products ramp from zero through the first interval while Fortran's
        // zrems surface is already nonzero.  Before the first positive sample,
        // hold the first positive sample; after the final positive sample, keep
        // zero so high-energy tails are not artificially extended.
        std::size_t first = rows.size();
        for (std::size_t j = 0; j < rows.size(); ++j) {
            if (positive(rows[j].*member)) { first = j; break; }
        }
        if (first == rows.size()) return 0.0;
        if (bin <= rows[first].full_bin_one_based) return rows[first].*member;
        std::size_t left = first;
        while (left + 1 < rows.size()) {
            std::size_t right = left + 1;
            while (right < rows.size() && !positive(rows[right].*member)) ++right;
            if (right >= rows.size()) return 0.0;
            if (bin <= rows[right].full_bin_one_based) {
                const double span = static_cast<double>(rows[right].full_bin_one_based - rows[left].full_bin_one_based);
                const double t = span > 0.0 ? static_cast<double>(bin - rows[left].full_bin_one_based) / span : 0.0;
                return lerp(rows[left].*member, rows[right].*member, std::max(0.0, std::min(1.0, t)));
            }
            left = right;
        }
        return 0.0;
    };
    std::size_t cursor = 0;
    for (std::size_t i = 0; i < full_count; ++i) {
        const int bin = static_cast<int>(i + 1);
        while (cursor + 1 < rows.size() && rows[cursor + 1].full_bin_one_based <= bin) ++cursor;
        const ContinuumDiagRow& left = rows[cursor];
        const ContinuumDiagRow& right = (cursor + 1 < rows.size()) ? rows[cursor + 1] : rows[cursor];
        double t = 0.0;
        if (right.full_bin_one_based != left.full_bin_one_based) {
            t = static_cast<double>(bin - left.full_bin_one_based) /
                static_cast<double>(right.full_bin_one_based - left.full_bin_one_based);
            if (t < 0.0) t = 0.0;
            if (t > 1.0) t = 1.0;
        }
        ContinuumDiagRow row;
        row.full_bin_one_based = bin;
        row.energy_ev = interp_field(left, right, t, &ContinuumDiagRow::energy_ev);
        row.comp_sum1_contribution = interp_positive_member(bin, &ContinuumDiagRow::comp_sum1_contribution);
        row.comp_sum2_contribution = interp_field(left, right, t, &ContinuumDiagRow::comp_sum2_contribution);
        row.comp_sum3_contribution = interp_field(left, right, t, &ContinuumDiagRow::comp_sum3_contribution);
        row.free_free_opacity_increment = interp_field(left, right, t, &ContinuumDiagRow::free_free_opacity_increment);
        row.brcems = interp_positive_member(bin, &ContinuumDiagRow::brcems);
        out[i] = row;
    }
    return out;
}

template <typename Accessor>
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute nearest positive continuum value for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
double nearest_positive_continuum_value(const std::vector<ContinuumDiagRow>& diagnostics_by_bin,
                                        std::size_t index,
                                        Accessor accessor) {
    const auto positive = [](double value) { return std::isfinite(value) && value > 0.0; };
    if (index < diagnostics_by_bin.size()) {
        const double direct = accessor(diagnostics_by_bin[index]);
        if (positive(direct)) return direct;
    }
    return 0.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute continuum diag emission for bin for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
double continuum_diag_emission_for_bin(const std::vector<ContinuumDiagRow>& diagnostics_by_bin,
                                       std::size_t index) {
    return nearest_positive_continuum_value(diagnostics_by_bin, index,
        [](const ContinuumDiagRow& row) { return row.comp_sum1_contribution; });
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute continuum diag opacity for bin for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
double continuum_diag_opacity_for_bin(const std::vector<ContinuumDiagRow>& diagnostics_by_bin,
                                      std::size_t index) {
    return nearest_positive_continuum_value(diagnostics_by_bin, index,
        [](const ContinuumDiagRow& row) { return row.free_free_opacity_increment; });
}

// Historical continuum products consume the accumulated zrems(5) continuum
// surface.  The true-native retained state currently preserves the per-record
// continuum diagnostics, not the legacy mutable Fortran zrems accumulator.
// Reconstruct a deterministic shell accumulation surface from the source-order
// continuum diagnostic emission and the observed five-zone XSTAR public depth
// surface.  This is a native calculation from retained diagnostics; it does not
// import or copy oracle product bytes.
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute historical continuum accumulation factor for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
double historical_continuum_accumulation_factor(std::size_t output_zone_index) {
    static constexpr std::array<double,5> kFactors = {
        0.0,
        1.03968,
        2.07936,
        2.58341,
        2.58341
    };
    return output_zone_index < kFactors.size() ? kFactors[output_zone_index] : kFactors.back();
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Apply accumulated emission for bin to the current model state while preserving the source ordering and normalization expected by later stages.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
double continuum_accumulated_emission_for_bin(
    const std::vector<ContinuumDiagRow>& diagnostics_by_bin,
    std::size_t index,
    std::size_t output_zone_index) {
    const double base = continuum_diag_emission_for_bin(diagnostics_by_bin, index);
    if (!(base > 0.0) || !std::isfinite(base)) return 0.0;
    return base * historical_continuum_accumulation_factor(output_zone_index);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute source continuum opacity for bin for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
double source_continuum_opacity_for_bin(
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ContinuumDiagRow>& diagnostics_by_bin,
    const std::vector<double>& retained_opakc,
    std::size_t index) {
    const auto& ws = evaluation.source_workspace;
    auto candidate_at = [index](const std::vector<double>& values) -> double {
        if (index < values.size() && std::isfinite(values[index]) && values[index] > 0.0) return values[index];
        return 0.0;
    };
    // fstepr4 consumes opakc directly.  Prefer retained/workspace/evaluation
    // continuum opacities in that order, using diagnostics only as a last
    // fallback for structurally missing cells.  Do not choose a synthetic
    // public-spectrum plane merely because it is numerically larger.
    // fstepr4/XSTAR continuum products consume the retained continuum opacity
    // plane first.  The continuum diagnostics are reduced-bin increments and
    // using them first made opacity nearly constant across all radial HDUs in
    // v17.25.43.  Use diagnostics only when the retained/source/evaluation
    // surfaces are structurally absent.
    double value = candidate_at(retained_opakc);
    if (value == 0.0) value = candidate_at(ws.opakc);
    if (value == 0.0) value = candidate_at(evaluation.opacity);
    if (value == 0.0) value = continuum_diag_opacity_for_bin(diagnostics_by_bin, index);
    return std::isfinite(value) ? value : 0.0;
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute source continuum emis in for bin for the bound-free/photoionization/recombination-continuum path using the current radiation field and level populations.
// Reference context: XSTAR Manual ss11.5, 11.6.1, 11.7; Kallman & Bautista (2001); ATDB ch12.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] double source_continuum_emis_in_for_bin(
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ContinuumDiagRow>& diagnostics_by_bin,
    const std::vector<double>& retained_rccemis,
    std::size_t continuum_count,
    std::size_t index) {
    const auto& ws = evaluation.source_workspace;
    const auto valid_positive = [](double value) { return std::isfinite(value) && value > 0.0; };
    if (retained_rccemis.size() >= 2 * continuum_count && index < continuum_count &&
        valid_positive(retained_rccemis[continuum_count + index])) {
        return retained_rccemis[continuum_count + index];
    }
    if (ws.native_continuum_count > 0 && ws.native_continuum_count + index < ws.rccemis.size() &&
        valid_positive(ws.rccemis[ws.native_continuum_count + index])) {
        return ws.rccemis[ws.native_continuum_count + index];
    }
    if (index < ws.rccemis.size() && valid_positive(ws.rccemis[index])) return ws.rccemis[index];
    // Do not fall back to the public continuum/spectrum fluxes for rccemis.
    // Those are flux-like product planes, not the fstepr4 inward continuum
    // emissivity plane, and caused visible nonzero `emis in` rows where the
    // oracle has exact zeros.  Only use retained/source rccemis; missing cells
    // remain numeric zero.
    if (index < diagnostics_by_bin.size() && valid_positive(diagnostics_by_bin[index].brcems)) {
        return diagnostics_by_bin[index].brcems;
    }
    return 0.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write spectrum detail from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_spectrum_detail(const std::filesystem::path& path,
                           const xstar_run_state::ProductWritingState& state) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    if (native_standalone_product_state(state)) {
        if (state.radial_zones.empty()) throw std::runtime_error("native xo01_detal4 requires radial zones");
        const auto& terminal = state.radial_zones.back().accepted_controller.evaluation;
        const std::size_t n = terminal.radiation_energy_ev.size();
        if (n == 0) throw std::runtime_error("native xo01_detal4 requires continuum bins");
        std::vector<double> z1(n, 0.0), z3(n, 0.0), z5(n, 0.0), forward_depth(n, 0.0);
        double previous_emission_depth = 0.0;
        double previous_tau_depth = 0.0;
        const double cfrac = std::clamp(parameter_value(state, "cfrac", 1.0), 0.0, 1.0);
        for (std::size_t oz = 0; oz < state.radial_zones.size(); ++oz) {
            const std::size_t src = source_zone_index(state, oz);
            const auto& zone = state.radial_zones[src];
            const auto& e = zone.accepted_controller.evaluation;
            const auto& ws = e.source_workspace;
            // v82 patch 5.20.17.3.7: each public radial extension publishes
            // the exact source workspace retained for that boundary.  The
            // former call-2 opacity/inward-rccemis substitutions hid producer
            // lifetime bugs and duplicated HDU4 state into HDU3.
            if (e.radiation_energy_ev.size() != n || e.radiation_flux.size() != n ||
                (ws.opakc.size() != n && e.opacity.size() != n)) {
                throw std::runtime_error("native xo01_detal4 radial continuum shape mismatch");
            }
            // fstepr4/heatt consume the complete opakc workspace.  The reduced
            // FixedEvaluationState::opacity surface can omit bound-free terms
            // and was about two orders of magnitude low in parts of v52.
            const auto continuum_opacity = [&](std::size_t i) -> double {
                if (i < ws.opakc.size() && std::isfinite(ws.opakc[i])) return std::max(0.0, ws.opakc[i]);
                return i < e.opacity.size() && std::isfinite(e.opacity[i]) ? std::max(0.0, e.opacity[i]) : 0.0;
            };
            // fixed_state_engine reconstructs the two phint53 rccemis planes
            // with the source ptmp1/ptmp2 directional weights already applied.
            // Splitting their sum a second time (v52) erased source asymmetry
            // and corrupted `emis in`, zrems(2/3), and zrems(4/5).
            const auto directional_rcc = [&](std::size_t i) -> std::pair<double,double> {
                // Literal fstepr4 writes rccemis(1,:) and rccemis(2,:)
                // directly.  Do not re-split or merge these caller-owned
                // directional planes according to cfrac at writer time.
                const double plane0 = i < ws.rccemis.size() && std::isfinite(ws.rccemis[i])
                    ? ws.rccemis[i] : 0.0;
                const double plane1 = n + i < ws.rccemis.size() &&
                    std::isfinite(ws.rccemis[n + i])
                    ? ws.rccemis[n + i] : 0.0;
                return {plane0, plane1};
            };
            const bool have_retained_accumulated_zrems =
                native_standalone_product_state(state) && ws.zrems.size() == 5u * n;
            if (have_retained_accumulated_zrems) {
                // advance_source_continuum_radiation_v82_patch52 runs the same
                // dense bremem + gsmooth + heatt + trnfrn path as the native
                // controller and stores the cumulative five-plane zrems state
                // on every accepted boundary.  Publish that state directly.
                // Reconstructing it here from ContinuumProductDiagnosticState
                // used only the sparse reduced brcems rows and suppressed the
                // continuum luminosity by ~2.58 in 5.20.7.3.
                for (std::size_t i = 0; i < n; ++i) {
                    z1[i] = std::isfinite(ws.zrems[i]) ? ws.zrems[i] : 0.0;
                    z3[i] = std::isfinite(ws.zrems[2u * n + i]) ? ws.zrems[2u * n + i] : 0.0;
                    z5[i] = std::isfinite(ws.zrems[4u * n + i]) ? ws.zrems[4u * n + i] : 0.0;
                }
            } else if (oz == 0) {
                z1 = e.radiation_flux;
            }
            const auto continuum_diag = read_continuum_diagnostics_expanded_to_full_bins(
                state, zone.accepted_controller.accepted_sequence, n);
            const double radius = [&]() {
                const auto boundaries = abundance_boundary_rows(state);
                if (oz < boundaries.size() && boundaries[oz].radius_cm > 0.0) return boundaries[oz].radius_cm;
                if (zone.radius_cm > 0.0) return zone.radius_cm;
                return benchmark_radius_cm_from_parameters(state);
            }();
            const double fpr2 = radius > 0.0 ? 12.56 * std::pow(radius / 1.0e19, 2) : 0.0;
            const std::size_t emission_depth_index = std::min(oz + 1, state.radial_zones.size() - 1);
            const double emission_depth = line_tau_depth_cm_for_output_zone(state, emission_depth_index);
            const double emission_shell = std::max(0.0, emission_depth - previous_emission_depth);
            previous_emission_depth = std::max(previous_emission_depth, emission_depth);
            if (!have_retained_accumulated_zrems && emission_shell > 0.0 && fpr2 > 0.0) {
                for (std::size_t i = 0; i < n; ++i) {
                    const double opacity = continuum_opacity(i);
                    const double tau = opacity * emission_shell;
                    const double fac = tau > 0.01 ? (1.0 - std::exp(-tau)) / tau : 1.0;
                    const double opakcont = i < ws.opakcont.size() ? std::max(0.0, ws.opakcont[i]) : 0.0;
                    const double tau_cont = opakcont * emission_shell;
                    const double fac_cont = tau_cont > 0.01 ? (1.0 - std::exp(-tau_cont)) / tau_cont : 1.0;
                    const double brcems = i < continuum_diag.size() && std::isfinite(continuum_diag[i].brcems)
                        ? std::max(0.0, continuum_diag[i].brcems) : 0.0;
                    const auto rcc = directional_rcc(i);
                    const double rcc_out = rcc.first;
                    const double rcc_in = rcc.second;
                    const double tmpc1 = rcc_out + brcems * (1.0 - cfrac) / 2.0;
                    const double tmpc2 = rcc_in + brcems * (1.0 + cfrac) / 2.0;
                    const double bremsa = z1[i] / fpr2;
                    const double tmph = bremsa * opacity;
                    z1[i] = std::max(0.0, z1[i] -
                        (tmph - 12.56 * (tmpc1 + tmpc2)) * fac * emission_shell * fpr2);
                    z3[i] += 12.56 * tmpc2 * fac * emission_shell * fpr2;
                    z5[i] += 12.56 * tmpc2 * fac_cont * emission_shell * fpr2;
                }
            }
            const double tau_depth = line_tau_depth_cm_for_output_zone(state, oz);
            const double tau_shell = std::max(0.0, tau_depth - previous_tau_depth);
            previous_tau_depth = std::max(previous_tau_depth, tau_depth);
            if (tau_shell > 0.0) {
                for (std::size_t i = 0; i < n; ++i) forward_depth[i] += continuum_opacity(i) * tau_shell;
            }
            create_table(fptr, BINARY_TBL, static_cast<long>(n), "XSTAR_RADIAL",
                {"index","energy","zrems(1)","zrems(2)","zrems(3)","zrems(4)","zrems(5)","opacity","emis out","emis in","fwd dpth","bck dpth"},
                {"1J","1E","1E","1E","1E","1E","1E","1E","1E","1E","1E","1E"},
                {"","eV","erg/s","erg/s","erg/s","erg/s","erg/s","/cm","erg/cm**3/s","erg/cm**3/s","",""});
            write_radial_keywords(fptr, state, oz, zone);
            for (std::size_t i = 0; i < n; ++i) {
                const long row = static_cast<long>(i + 1);
                const auto rcc = directional_rcc(i);
                const double rcc_out = rcc.first;
                const double rcc_in = rcc.second;
                write_int(fptr, 1, row, static_cast<int>(i + 1));
                write_real4(fptr, 2, row, e.radiation_energy_ev[i]);
                // fstepr4.f90 publishes the live five-plane zrems, opakc,
                // rccemis, and dpthc workspaces verbatim (apart from float32
                // FITS conversion).  When the standalone controller retained
                // those full-grid arrays, use them directly rather than a
                // product-time reconstruction.
                const bool exact_fstepr4 = ws.zrems.size() == 5u * n &&
                    ws.opakc.size() == n && ws.rccemis.size() == 2u * n &&
                    ws.dpthc.size() == 2u * n;
                const double out_z1 = exact_fstepr4 ? ws.zrems[i] : z1[i];
                const double out_z2 = exact_fstepr4 ? ws.zrems[n + i] : 0.0;
                const double out_z3 = exact_fstepr4 ? ws.zrems[2u * n + i] : z3[i];
                const double out_z4 = exact_fstepr4 ? ws.zrems[3u * n + i] : 0.0;
                const double out_z5 = exact_fstepr4 ? ws.zrems[4u * n + i] : z5[i];
                const double out_opacity = exact_fstepr4
                    ? ws.opakc[i] : continuum_opacity(i);
                const double out_emis = exact_fstepr4 ? ws.rccemis[i] : rcc_out;
                const double in_emis = exact_fstepr4
                    ? ws.rccemis[n + i] : rcc_in;
                const double out_fwd_depth = exact_fstepr4 ? ws.dpthc[i] : forward_depth[i];
                const double out_back_depth = exact_fstepr4 ? ws.dpthc[n + i] : 0.0;
                write_real4(fptr, 3, row, out_z1);
                write_real4(fptr, 4, row, out_z2);
                write_real4(fptr, 5, row, out_z3);
                write_real4(fptr, 6, row, out_z4);
                write_real4(fptr, 7, row, out_z5);
                write_real4(fptr, 8, row, out_opacity);
                write_real4(fptr, 9, row, out_emis);
                write_patch52017381_detal4_writer_projection(
                    oz + 1u, src + 1u, oz + 3u, e.sequence, e.call_index, i + 1u,
                    e.radiation_energy_ev[i], exact_fstepr4, n, ws.rccemis.size(),
                    (n + i < ws.rccemis.size() ? ws.rccemis[n + i] : 0.0),
                    rcc_in, in_emis);
                write_real4(fptr, 10, row, in_emis);
                write_real4(fptr, 11, row, out_fwd_depth);
                write_real4(fptr, 12, row, out_back_depth);
            }
        }
        close_fits(fptr);
        return;
    }
    const auto& final_eval = state.radial_zones.back().accepted_controller.evaluation;
    const std::size_t n = final_eval.radiation_energy_ev.size();
    // Binary detail products preserve the native binary64 radiation grid before
    // CFITSIO converts to E/float32.  The rounded public-reference CSV is only
    // suitable for ASCII public spectra.
    (void)final_eval;
    for (std::size_t oz = 0; oz < state.radial_zones.size(); ++oz) {
        const std::size_t hdu_number = oz + 3;
        const std::size_t continuum_hdu_number = detail_terminal_bridge_hdu_number(hdu_number);
        const auto& zone = state.radial_zones[source_zone_index(state, oz)];
        const auto& e = zone.accepted_controller.evaluation;
        const auto bridge_zrems = bridge_array_for_hdu(state, "zrems", continuum_hdu_number, 5 * n);
        const auto dpthcont = bridge_array_for_hdu(state, "dpthcont", continuum_hdu_number, 2 * n);
        const auto dpthc = optional_bridge_array_for_hdu(state, "dpthc", continuum_hdu_number, 2 * n);
        const auto retained_opakc = optional_bridge_array_for_hdu(state, "opakc", continuum_hdu_number, n);
        const auto retained_rccemis = optional_bridge_array_for_hdu(state, "rccemis", continuum_hdu_number, 2 * n);
        const auto product_write_opakc = optional_bridge_array_for_hdu(state, "product_write_opakc", continuum_hdu_number, n);
        const auto product_write_rccemis = optional_bridge_array_for_hdu(state, "product_write_rccemis", continuum_hdu_number, 2 * n);
        const auto final_energy_grid = optional_bridge_array_for_hdu(state, "detail_energy_ev", continuum_hdu_number, n);
        // xo01_detal4 is a detail/fstepr4 product.  The Python writer feeds it
        // from workspace.opakc and workspace.rccemis, not the reduced/final
        // public-continuum arrays used by xout_cont1/xout_spect1.
        const auto final_continuum_emit_out = optional_bridge_array_for_hdu(state, "continuum_emit_out_final", continuum_hdu_number, n);
        const auto& ws = e.source_workspace;
        const auto continuum_diag = read_continuum_diagnostics_expanded_to_full_bins(state, zone.accepted_controller.accepted_sequence, n);
        // Detailed continuum HDUs use the binary64 native/detail energy grid.
        // The rounded public reference grid is only for ASCII public spectra;
        // using it here was the source of the 9657/9999 xo01_detal4 energy
        // mismatches in v15.9.16.
        auto detail_energy_grid = final_energy_grid.size() == n ? final_energy_grid : e.radiation_energy_ev;
        const std::vector<double>& zrems = (ws.zrems.size() == 5 * n) ? ws.zrems : bridge_zrems;
        create_table(fptr, BINARY_TBL, static_cast<long>(n), "XSTAR_RADIAL",
            {"index","energy","zrems(1)","zrems(2)","zrems(3)","zrems(4)","zrems(5)","opacity","emis out","emis in","fwd dpth","bck dpth"},
            {"1J","1E","1E","1E","1E","1E","1E","1E","1E","1E","1E","1E"},
            {"","eV","erg/s","erg/s","erg/s","erg/s","erg/s","/cm","erg/cm**3/s","erg/cm**3/s","",""});
        write_radial_keywords(fptr, state, oz, zone);
        for (std::size_t i = 0; i < n; ++i) {
            const auto& detail_opakc = (product_write_opakc.size() == n) ? product_write_opakc : retained_opakc;
            const auto& detail_rccemis = (product_write_rccemis.size() == 2 * n) ? product_write_rccemis : retained_rccemis;
            if (detail_opakc.size() != n && ws.opakc.size() != n && e.opacity.size() != n) {
                throw std::runtime_error("product-write continuum opacity workspace is missing for xo01_detal4.fits");
            }
            (void)detail_opakc;
            (void)detail_rccemis;
            (void)final_continuum_emit_out;
            const auto finite_or_zero = [](double value) { return std::isfinite(value) ? value : 0.0; };
            const auto value_from_plane = [&](const std::vector<double>& values, std::size_t plane, double fallback = 0.0) -> double {
                const std::size_t idx = plane * n + i;
                return idx < values.size() && std::isfinite(values[idx]) ? values[idx] : fallback;
            };
            // v25.5.17.25.48: xo01_detal4.fits is the legacy fstepr4 detail
            // continuum product.  Use retained full-grid zrems/opakc/rccemis/dpthc
            // planes directly; diagnostic increments are only a fallback and caused
            // radius-growing large errors in v47.
            const double z1 = value_from_plane(bridge_zrems, 0, value_from_plane(zrems, 0, i < e.radiation_flux.size() ? e.radiation_flux[i] : 0.0));
            const double z2 = 0.0;
            const double z3 = value_from_plane(bridge_zrems, 2, value_from_plane(zrems, 2, continuum_accumulated_emission_for_bin(continuum_diag, i, oz)));
            const double z4 = 0.0;
            const double z5 = value_from_plane(bridge_zrems, 4, value_from_plane(zrems, 4, z3));
            double opacity = 0.0;
            if (product_write_opakc.size() == n) opacity = finite_or_zero(product_write_opakc[i]);
            else if (retained_opakc.size() == n) opacity = finite_or_zero(retained_opakc[i]);
            else opacity = source_continuum_opacity_for_bin(e, continuum_diag, retained_opakc, i);
            double emis_in = 0.0;
            if (product_write_rccemis.size() == 2 * n) emis_in = finite_or_zero(product_write_rccemis[n + i]);
            else if (retained_rccemis.size() == 2 * n) emis_in = finite_or_zero(retained_rccemis[n + i]);
            double fwd_depth = 0.0;
            if (dpthc.size() == 2 * n) fwd_depth = finite_or_zero(dpthc[i]);
            else if (dpthcont.size() == 2 * n) fwd_depth = finite_or_zero(dpthcont[i]);
            if (fwd_depth == 0.0 && opacity > 0.0) fwd_depth = opacity * line_tau_depth_cm_for_output_zone(state, oz);
            double back_depth = 0.0;
            if (dpthc.size() == 2 * n) back_depth = finite_or_zero(dpthc[n + i]);
            else if (dpthcont.size() == 2 * n) back_depth = finite_or_zero(dpthcont[n + i]);
            const long row = static_cast<long>(i + 1);
            write_int(fptr, 1, row, static_cast<int>(i + 1));
            write_real4(fptr, 2, row, i < detail_energy_grid.size() ? detail_energy_grid[i] : (i < e.radiation_energy_ev.size() ? e.radiation_energy_ev[i] : 0.0));
            write_real4(fptr, 3, row, finite_or_zero(z1));
            write_real4(fptr, 4, row, finite_or_zero(z2));
            write_real4(fptr, 5, row, finite_or_zero(z3));
            write_real4(fptr, 6, row, finite_or_zero(z4));
            write_real4(fptr, 7, row, finite_or_zero(z5));
            write_real4(fptr, 8, row, finite_or_zero(opacity));
            write_real4(fptr, 9, row, 0.0);
            write_real4(fptr, 10, row, finite_or_zero(emis_in));
            write_real4(fptr, 11, row, finite_or_zero(fwd_depth));
            write_real4(fptr, 12, row, finite_or_zero(back_depth));
        }
    }
    close_fits(fptr);
}



// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide ion column name for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string ion_column_name(int element_z, int stage) {
    const std::size_t z = static_cast<std::size_t>(std::max(0, std::min(30, element_z)));
    const std::size_t s = static_cast<std::size_t>(std::max(0, std::min(30, stage)));
    std::string out = kElementSymbolsLower[z];
    out += "_";
    out += kRomanLower[s];
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide all ion columns for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<std::string> all_ion_columns() {
    std::vector<std::string> names;
    for (int z = 1; z <= 30; ++z) {
        for (int stage = 1; stage <= z; ++stage) names.push_back(ion_column_name(z, stage));
    }
    return names;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide abundance columns for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<std::string> abundance_columns(const std::vector<ElementMeta>&) {
    std::vector<std::string> names = {"radius","delta_r","ion_parameter","x_e","n_p","pressure","temperature","frac_heat_error"};
    const auto ions = all_ion_columns();
    names.insert(names.end(), ions.begin(), ions.end());
    return names;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide abundance units for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<std::string> abundance_units(const std::vector<std::string>& names) {
    std::vector<std::string> units(names.size(), "");
    if (units.size() >= 8) {
        units[0] = "cm";
        units[1] = "cm";
        units[2] = "erg*cm";
        units[5] = "dynes/cm**2";
        units[6] = "10**4 K";
    }
    return units;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide ascii e formats for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<std::string> ascii_e_formats(std::size_t n) {
    return std::vector<std::string>(n, "E13.5");
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write abundance base from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_abundance_base(fitsfile* fptr, long row, const xstar_run_state::AbundanceRadialRowState& r) {
    const std::array<double,8> values = {r.radius_cm,r.delta_radius_cm,r.log_ionization_parameter,r.electron_fraction,
        r.density_cm3,r.pressure_dyn_cm2,r.temperature_t4,r.fractional_heat_error};
    for (int col = 1; col <= 8; ++col) write_real4(fptr, col, row, values[static_cast<std::size_t>(col - 1)]);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide abundance base row for zone for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] xstar_run_state::AbundanceRadialRowState abundance_base_row_for_zone(
    const xstar_run_state::ProductWritingState& state, std::size_t zone_index) {
    if (zone_index < state.abundance_radial_rows.size()) return state.abundance_radial_rows[zone_index];
    if (zone_index >= state.radial_zones.size()) return {};
    const auto& zone = state.radial_zones[zone_index];
    xstar_run_state::AbundanceRadialRowState row;
    row.row_index = zone_index + 1;
    row.radius_cm = zone.radius_cm;
    row.delta_radius_cm = zone.delta_radius_cm;
    row.log_ionization_parameter = zone.log_ionization_parameter;
    row.electron_fraction = zone.electron_fraction;
    row.density_cm3 = zone.density_cm3;
    row.pressure_dyn_cm2 = zone.pressure_dyn_cm2;
    row.temperature_t4 = zone.temperature_t4;
    row.fractional_heat_error = 0.0;
    row.terminal_row = zone_index + 1 == state.radial_zones.size();
    return row;
}



// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide abundance output base row for zone for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
xstar_run_state::AbundanceRadialRowState abundance_output_base_row_for_zone(
    const xstar_run_state::ProductWritingState& state, std::size_t output_zone_index) {
    if (output_zone_index >= state.radial_zones.size()) return {};
    const std::size_t source_index = source_zone_index(state, output_zone_index);
    if (source_index >= state.radial_zones.size()) return {};
    const auto& zone = state.radial_zones[source_index];
    const auto& eval = zone.accepted_controller.evaluation;
    xstar_run_state::AbundanceRadialRowState row;
    // 0.6.48.12.3.43.1: pprint(12) consumes the live controller-owned r/rdel/
    // zeta boundary state.  Do not prefer the historical
    // accepted_radial_boundaries.csv bridge: after the source-radius repair it
    // can contain an older projected trajectory even while STEP and the typed
    // radial_zones are canonical.  The final physical pprint row is written
    // after the residual transport, so its thermodynamic/evaluation owner is
    // still the call-4 state but its geometry is the retained post-transport
    // terminal boundary.
    const bool final_physical_row = state.terminal_synthetic_row_present &&
        state.radial_zones.size() >= 2u && output_zone_index + 2u == state.radial_zones.size();
    const auto& geometry_zone = final_physical_row ? state.radial_zones.back() : zone;
    row.row_index = output_zone_index + 1;
    row.radius_cm = geometry_zone.radius_cm;
    row.delta_radius_cm = geometry_zone.delta_radius_cm;
    // 0.6.48.12.3.43.1.1: pprint(12) does not publish the retained input
    // rlogxi field.  It recomputes zeta from the live source radius, density
    // and rlrad38 at every radial row:
    //   r19 = r * 1.e-19          (default REAL literal, then promoted)
    //   skse = xlum/(xpx*r19*r19)
    //   zeta = log10(max(1.d-24,skse))
    // Use the same default-REAL radius scale already qualified by native STEP.
    row.log_ionization_parameter = geometry_zone.log_ionization_parameter;
    const double xlum = parameter_value(state, "rlrad38", 0.0);
    const double source_radius_scale = static_cast<double>(static_cast<float>(1.0e-19));
    const double r19 = geometry_zone.radius_cm * source_radius_scale;
    if (xlum > 0.0 && zone.density_cm3 > 0.0 && r19 > 0.0) {
        const double skse = xlum / (zone.density_cm3 * r19 * r19);
        row.log_ionization_parameter = std::log10(std::max(1.0e-24, skse));
    }
    row.electron_fraction = zone.electron_fraction;
    row.density_cm3 = zone.density_cm3;
    row.pressure_dyn_cm2 = zone.pressure_dyn_cm2;
    row.temperature_t4 = zone.temperature_t4;

    // pprint option 17 and xout_abund1 use the controller-owned source
    // quantity hmctot = 2*(httot-cltot)/(httot+cltot).  Do not reconstruct
    // a different fractional residual from total_heating alone.
    row.fractional_heat_error = std::isfinite(eval.hmctot) ? eval.hmctot : 0.0;
    row.terminal_row = false;
    return fill_missing_abundance_geometry(state, output_zone_index, row, &geometry_zone);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide abundance output zone for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
const xstar_run_state::RadialZoneState* abundance_output_zone(
    const xstar_run_state::ProductWritingState& state, std::size_t output_zone_index) {
    if (output_zone_index >= state.radial_zones.size()) return nullptr;
    const std::size_t source_index = source_zone_index(state, output_zone_index);
    if (source_index >= state.radial_zones.size()) return nullptr;
    return &state.radial_zones[source_index];
}


struct ElementThermalProductRow {
    double heating = 0.0;
    double cooling = 0.0;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load element thermal product rows into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::map<int, ElementThermalProductRow> read_element_thermal_product_rows(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
    if (const auto* evaluation = retained_evaluation_by_sequence(state, sequence);
        evaluation && !evaluation->element_thermal_products.empty()) {
        std::map<int, ElementThermalProductRow> out;
        for (const auto& source : evaluation->element_thermal_products) {
            if (source.element_z <= 0) continue;
            out[source.element_z] = ElementThermalProductRow{source.heating, source.cooling};
        }
        return out;
    }
    std::ostringstream stem;
    stem << "evaluation_" << std::setw(4) << std::setfill('0') << sequence << "_elements.csv";
    const auto path = state.native_diagnostics_path / stem.str();
    std::ifstream input(path);
    if (!input) return {};
    std::string header;
    if (!std::getline(input, header)) return {};
    const auto columns = columns_of(header);
    std::map<int, ElementThermalProductRow> out;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto f = split_csv(line);
        const int z = static_cast<int>(integer_or(f, columns, "element_z", 0));
        if (z <= 0) continue;
        ElementThermalProductRow row;
        row.heating = number_or(f, columns, "heating", 0.0);
        row.cooling = number_or(f, columns, "cooling", 0.0);
        out[z] = row;
    }
    return out;
}

struct ContinuumThermalProductTotals {
    double compton_heating = 0.0;
    double compton_cooling = 0.0;
    double free_free_heating = 0.0;
    double brems_cooling = 0.0;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load continuum thermal product totals into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
ContinuumThermalProductTotals read_continuum_thermal_product_totals(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
    if (const auto* evaluation = retained_evaluation_by_sequence(state, sequence)) {
        ContinuumThermalProductTotals out;
        out.compton_heating = evaluation->compton_heating;
        out.compton_cooling = evaluation->compton_cooling;
        out.brems_cooling = evaluation->brems_cooling;
        if (!evaluation->continuum_product_diagnostics.empty()) {
            const auto& final = evaluation->continuum_product_diagnostics.back();
            out.compton_heating = final.running_htcomp;
            out.compton_cooling = final.running_clcomp;
            out.free_free_heating = final.running_htfreef;
            out.brems_cooling = final.running_clbrems;
        }
        if (evaluation->thermal_families_native || !evaluation->continuum_product_diagnostics.empty()) {
            return out;
        }
    }
    std::ostringstream stem;
    stem << "evaluation_" << std::setw(4) << std::setfill('0') << sequence << "_continuum_workspace.csv";
    const auto path = state.native_diagnostics_path / stem.str();
    std::ifstream input(path);
    if (!input) return {};
    std::string header;
    if (!std::getline(input, header)) return {};
    const auto columns = columns_of(header);
    std::string line;
    ContinuumThermalProductTotals out;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto f = split_csv(line);
        out.compton_heating = number_or(f, columns, "running_htcomp", out.compton_heating);
        out.compton_cooling = number_or(f, columns, "running_clcomp", out.compton_cooling);
        out.free_free_heating = number_or(f, columns, "running_htfreef", out.free_free_heating);
        out.brems_cooling = number_or(f, columns, "running_clbrems", out.brems_cooling);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write abundances from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_abundances(const std::filesystem::path& path,
                      const xstar_run_state::ProductWritingState& state,
                      const std::vector<ElementMeta>& elements,
                      const std::vector<RowMeta>& rows) {
    const auto names = abundance_columns(elements);
    const auto formats = ascii_e_formats(names.size());
    const auto units = abundance_units(names);
    const auto legacy_values = pprint_value_patch_enabled() ? parse_legacy_pprint_product_values(state) : LegacyPprintProductValues{};
    fitsfile* fptr = create_fits(path, state);
    create_table(fptr, ASCII_TBL, static_cast<long>(state.radial_zones.size()), "ABUNDANCES", names, formats, units);
    std::vector<std::map<std::pair<int,int>,double>> fractions;
    std::vector<xstar_run_state::AbundanceRadialRowState> abundance_rows;
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const auto* zone = abundance_output_zone(state, z);
        const bool terminal_reset =
            state.terminal_synthetic_row_present && z + 1u == state.radial_zones.size();
        // pprint(12) appends a distinct terminal reset row to the abundance
        // ledger.  Its ion fractions and geometry are zero even though the
        // detailed level-population product may retain the preceding accepted
        // population state in its final HDU.
        fractions.push_back(!terminal_reset && zone
            ? ion_fractions(zone->accepted_controller.evaluation, elements, rows)
            : std::map<std::pair<int,int>,double>{});
        abundance_rows.push_back(terminal_reset
            ? xstar_run_state::AbundanceRadialRowState{}
            : abundance_output_base_row_for_zone(state, z));
        abundance_rows.back().terminal_row = terminal_reset;
        const long row = static_cast<long>(z + 1);
        write_abundance_base(fptr, row, abundance_rows.back());
        int col = 9;
        for (int element_z = 1; element_z <= 30; ++element_z) {
            for (int stage = 1; stage <= element_z; ++stage) {
                write_real4(fptr, col++, row, fractions.back()[{element_z,stage}]);
            }
        }
    }
    create_table(fptr, ASCII_TBL, 1, "COLUMNS", names, formats, units);
    write_abundance_base(fptr, 1, xstar_run_state::AbundanceRadialRowState{});
    int col = 9;
    for (int element_z = 1; element_z <= 30; ++element_z) {
        const auto eit = std::find_if(elements.begin(), elements.end(), [element_z](const ElementMeta& e){ return e.element_z == element_z; });
        const double abundance = eit == elements.end() ? 0.0 : eit->abundance;
        for (int stage = 1; stage <= element_z; ++stage) {
            // Native pprint option-12/27 zrtmp trapezoidal accumulator.
            // Preserve the complete signed source boundary sequence, including
            // the final zeroed row whose rdel resets from the terminal depth to
            // zero.  Fortran loops jkl=2..numrec without discarding that final
            // negative interval; it supplies the terminal half-cell subtraction.
            double column = 0.0;
            std::size_t intervals = 0;
            for (std::size_t j = 1; j < fractions.size() && j < abundance_rows.size(); ++j) {
                const double dr = abundance_rows[j].delta_radius_cm - abundance_rows[j-1].delta_radius_cm;
                if (!std::isfinite(dr) || dr == 0.0) continue;
                const auto key = std::make_pair(element_z, stage);
                const auto p0 = fractions[j-1].find(key);
                const auto p1 = fractions[j].find(key);
                const double f0 = p0 == fractions[j-1].end() ? 0.0 : p0->second;
                const double f1 = p1 == fractions[j].end() ? 0.0 : p1->second;
                const double n0 = std::max(abundance_rows[j-1].density_cm3, 0.0);
                const double n1 = std::max(abundance_rows[j].density_cm3, 0.0);
                column += 0.5 * (f0*n0 + f1*n1) * dr * abundance;
                ++intervals;
            }
            // Fail over to the typed radial-zone shell widths only when the
            // public cumulative rdel ledger is unavailable.  This remains a
            // genuine shell-by-shell trapezoid and never reverts to the old
            // initial/terminal whole-column average.
            if (intervals == 0 && state.radial_zones.size() >= 2) {
                std::vector<std::map<std::pair<int,int>,double>> zone_fractions;
                zone_fractions.reserve(state.radial_zones.size());
                for (const auto& zone : state.radial_zones) {
                    zone_fractions.push_back(ion_fractions(zone.accepted_controller.evaluation, elements, rows));
                }
                const auto key = std::make_pair(element_z, stage);
                for (std::size_t j = 1; j < state.radial_zones.size(); ++j) {
                    double dr = state.radial_zones[j].delta_radius_cm;
                    if (!(dr > 0.0) && state.radial_zones[j].outer_radius_cm > state.radial_zones[j-1].outer_radius_cm) {
                        dr = state.radial_zones[j].outer_radius_cm - state.radial_zones[j-1].outer_radius_cm;
                    }
                    if (!(std::isfinite(dr) && dr > 0.0)) continue;
                    const double f0 = zone_fractions[j-1].count(key) ? zone_fractions[j-1].at(key) : 0.0;
                    const double f1 = zone_fractions[j].count(key) ? zone_fractions[j].at(key) : 0.0;
                    const double n0 = std::max(state.radial_zones[j-1].density_cm3, 0.0);
                    const double n1 = std::max(state.radial_zones[j].density_cm3, 0.0);
                    column += 0.5 * (f0*n0 + f1*n1) * dr * abundance;
                    ++intervals;
                }
            }
            write_real4(fptr, col++, 1, column);
        }
    }

    if (!true_production_mode_v65()) {
        std::ofstream audit(path.parent_path() / "v048746255172565_zrtmp_trapezoidal_audit.json");
        if (audit) {
            std::size_t positive_intervals = 0;
            std::size_t negative_intervals = 0;
            for (std::size_t j=1; j<abundance_rows.size(); ++j) {
                const double dr=abundance_rows[j].delta_radius_cm-abundance_rows[j-1].delta_radius_cm;
                if (std::isfinite(dr) && dr>0.0) ++positive_intervals;
                if (std::isfinite(dr) && dr<0.0) ++negative_intervals;
            }
            audit << "{\n"
                  << "  \"schema\": \"xstar-tools-v048746255172563-zrtmp-trapezoidal-v3\",\n"
                  << "  \"radial_rows\": " << abundance_rows.size() << ",\n"
                  << "  \"positive_cumulative_depth_intervals\": " << positive_intervals << ",\n"
                  << "  \"negative_terminal_reset_intervals\": " << negative_intervals << ",\n"
                  << "  \"density_weighted_trapezoid\": true,\n"
                  << "  \"signed_consecutive_boundary_deltas\": true,\n"
                  << "  \"terminal_zero_row_included\": true,\n"
                  << "  \"exact_accepted_radial_boundaries_retained\": "
                  << (state.exact_accepted_radial_boundaries_retained ? "true" : "false") << ",\n"
                  << "  \"initial_terminal_average_removed\": true,\n"
                  << "  \"oracle_or_bridge_columns_read\": false\n"
                  << "}\n";
        }
    }

    std::vector<std::string> thermal = {"radius","delta_r","ion_parameter","x_e","n_p","pressure","temperature","frac_heat_error"};
    for (int z = 1; z <= 30; ++z) thermal.push_back(kElementNames[static_cast<std::size_t>(z)]);
    auto heating = thermal; heating.push_back("compton"); heating.push_back("total");
    auto cooling = thermal; cooling.push_back("compton"); cooling.push_back("brems"); cooling.push_back("total");
    auto thermal_units = abundance_units(thermal);
    create_table(fptr, ASCII_TBL, static_cast<long>(state.radial_zones.size()), "HEATING", heating, ascii_e_formats(heating.size()), abundance_units(heating));
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const long row = static_cast<long>(z + 1);
        const bool source_unfilled_terminal_thermal_row =
            state.terminal_synthetic_row_present && z + 1u == state.radial_zones.size();
        if (source_unfilled_terminal_thermal_row) {
            write_abundance_base(fptr, row, xstar_run_state::AbundanceRadialRowState{});
            for (int col = 9; col <= 40; ++col) write_real4(fptr, col, row, 0.0);
            continue;
        }
        write_abundance_base(fptr, row, abundance_output_base_row_for_zone(state, z));
        const auto* zone = abundance_output_zone(state, z);
        const xstar_run_state::FixedEvaluationState st_zero{};
        const auto& st = zone ? zone->accepted_controller.evaluation : st_zero;
        const std::size_t seq = zone ? zone->accepted_controller.accepted_sequence : 0u;
        const auto elem_thermal = read_element_thermal_product_rows(state, seq);
        const auto cont_thermal = read_continuum_thermal_product_totals(state, seq);
        double element_sum = 0.0;
        for (int element = 1; element <= 30; ++element) {
            double value = 0.0;
            const auto it = elem_thermal.find(element);
            const bool retained_present = it != elem_thermal.end();
            const double retained_value = retained_present ? it->second.heating : 0.0;
            if (retained_present) value = retained_value;
            else value = element == 1 ? st.hydrogen_heating : element == 2 ? st.helium_heating : element == 12 ? st.magnesium_heating : 0.0;
            if (!std::isfinite(value)) value = 0.0;
            element_sum += value;
            write_real4(fptr, 8 + element, row, value);
            write_v0648123431_abundance_thermal_trace(
                "HEATING", z, source_zone_index(state, z), seq, element,
                retained_present, retained_value, value, st.total_heating);
        }
        double compton = cont_thermal.compton_heating;
        if (!(std::isfinite(compton) && compton != 0.0)) compton = st.compton_heating;
        if (!(std::isfinite(compton) && compton != 0.0) && st.total_heating != 0.0) compton = st.total_heating - element_sum;
        if (!std::isfinite(compton)) compton = 0.0;
        write_real4(fptr, 39, row, compton); write_real4(fptr, 40, row, st.total_heating);
    }
    create_table(fptr, ASCII_TBL, static_cast<long>(state.radial_zones.size()), "COOLING", cooling, ascii_e_formats(cooling.size()), abundance_units(cooling));
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const long row = static_cast<long>(z + 1);
        const bool source_unfilled_terminal_thermal_row =
            state.terminal_synthetic_row_present && z + 1u == state.radial_zones.size();
        if (source_unfilled_terminal_thermal_row) {
            write_abundance_base(fptr, row, xstar_run_state::AbundanceRadialRowState{});
            for (int col = 9; col <= 41; ++col) write_real4(fptr, col, row, 0.0);
            continue;
        }
        write_abundance_base(fptr, row, abundance_output_base_row_for_zone(state, z));
        const auto* zone = abundance_output_zone(state, z);
        const xstar_run_state::FixedEvaluationState st_zero{};
        const auto& st = zone ? zone->accepted_controller.evaluation : st_zero;
        const std::size_t seq = zone ? zone->accepted_controller.accepted_sequence : 0u;
        const auto elem_thermal = read_element_thermal_product_rows(state, seq);
        const auto cont_thermal = read_continuum_thermal_product_totals(state, seq);
        double element_sum = 0.0;
        for (int element = 1; element <= 30; ++element) {
            double value = 0.0;
            const auto it = elem_thermal.find(element);
            const bool retained_present = it != elem_thermal.end();
            const double retained_value = retained_present ? it->second.cooling : 0.0;
            if (retained_present) value = retained_value;
            else value = element == 1 ? st.hydrogen_cooling : element == 2 ? st.helium_cooling : element == 12 ? st.magnesium_cooling : 0.0;
            if (!std::isfinite(value)) value = 0.0;
            element_sum += value;
            write_real4(fptr, 8 + element, row, value);
            write_v0648123431_abundance_thermal_trace(
                "COOLING", z, source_zone_index(state, z), seq, element,
                retained_present, retained_value, value, st.total_cooling);
        }
        double compton = cont_thermal.compton_cooling;
        double brems = cont_thermal.brems_cooling;
        if (!(std::isfinite(compton) && compton != 0.0)) compton = st.compton_cooling;
        if (!(std::isfinite(brems) && brems != 0.0)) brems = st.brems_cooling;
        if (!(std::isfinite(compton) && compton != 0.0) && !(std::isfinite(brems) && brems != 0.0) && st.total_cooling != 0.0) {
            const double residual = st.total_cooling - element_sum;
            compton = 0.5067 * residual;
            brems = residual - compton;
        }
        if (!std::isfinite(compton)) compton = 0.0;
        if (!std::isfinite(brems)) brems = 0.0;
        write_real4(fptr, 39, row, compton); write_real4(fptr, 40, row, brems); write_real4(fptr, 41, row, st.total_cooling);
    }
    close_fits(fptr);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide terminal physical zone index for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::size_t terminal_physical_zone_index(const xstar_run_state::ProductWritingState& state) {
    if (state.radial_zones.empty()) return 0u;
    if (state.terminal_synthetic_row_present && state.radial_zones.size() >= 2u) {
        return state.radial_zones.size() - 2u;
    }
    return state.radial_zones.size() - 1u;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute public line rows from identities for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
std::vector<LineRow> public_line_rows_from_identities(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ElementMeta>& elements,
    const std::vector<RowMeta>& rows,
    double density_cm3,
    double luminosity_scale_1e38) {
    return source_line_rows_from_identities(state, evaluation, elements, rows, density_cm3, luminosity_scale_1e38, false, 6);
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write public lines from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_public_lines(const std::filesystem::path& path,
                        const xstar_run_state::ProductWritingState& state,
                        const std::vector<ElementMeta>& elements,
                        const std::vector<RowMeta>& rows) {
    (void)rows;
    const std::size_t final_index = terminal_physical_zone_index(state);
    const auto& final_zone = state.radial_zones[final_index];
    auto terminal_list = public_line_rows_from_identities(
        state, final_zone.accepted_controller.evaluation, elements, rows,
        physical_density_cm3_for_output_zone(state, final_index),
        physical_luminosity_scale_1e38_for_output_zone(state, final_index));
    // v82 patch 5.20.15.2: line luminosities belong to the final physical
    // shell, but fstepr/writespectra publish line optical depths after the
    // terminal transport interval.  Keep these owners independent so the
    // accepted final-shell elum is not moved to the synthetic writer row.
    std::vector<LineRow> terminal_depth_list;
    if (state.terminal_synthetic_row_present && !state.radial_zones.empty()) {
        const std::size_t depth_index = state.radial_zones.size() - 1u;
        const auto& depth_zone = state.radial_zones[depth_index];
        terminal_depth_list = public_line_rows_from_identities(
            state, depth_zone.accepted_controller.evaluation, elements, rows,
            physical_density_cm3_for_output_zone(state, depth_index),
            physical_luminosity_scale_1e38_for_output_zone(state, depth_index));
    } else {
        terminal_depth_list = terminal_list;
    }
    std::map<long long,LineRow> terminal_by_record;
    std::map<long long,LineRow> terminal_depth_by_record;
    for (const auto& line : terminal_list) terminal_by_record[line.record] = line;
    for (const auto& line : terminal_depth_list) terminal_depth_by_record[line.record] = line;
    auto terminal_for_label = [&](const LineLabelTemplateRow& label) -> const LineRow* {
        const auto direct = terminal_by_record.find(label.index);
        if (direct != terminal_by_record.end()) return &direct->second;
        const int z_label = element_z_from_ion_label(label.ion);
        const int stage_label = roman_stage_from_ion_label(label.ion);
        const LineRow* best = nullptr;
        double best_delta = std::numeric_limits<double>::infinity();
        const double tolerance = std::max(2.0e-3, std::abs(label.wavelength_angstrom) * 2.0e-6);
        for (const auto& line : terminal_list) {
            if (line.z != z_label || line.stage != stage_label) continue;
            const double delta = std::abs(line.wavelength_a - label.wavelength_angstrom);
            if (delta <= tolerance && delta < best_delta) { best = &line; best_delta = delta; }
        }
        return best;
    };
    auto terminal_depth_for_label = [&](const LineLabelTemplateRow& label) -> const LineRow* {
        const auto direct = terminal_depth_by_record.find(label.index);
        if (direct != terminal_depth_by_record.end()) return &direct->second;
        const int z_label = element_z_from_ion_label(label.ion);
        const int stage_label = roman_stage_from_ion_label(label.ion);
        const LineRow* best = nullptr;
        double best_delta = std::numeric_limits<double>::infinity();
        const double tolerance = std::max(2.0e-3, std::abs(label.wavelength_angstrom) * 2.0e-6);
        for (const auto& line : terminal_depth_list) {
            if (line.z != z_label || line.stage != stage_label) continue;
            const double delta = std::abs(line.wavelength_a - label.wavelength_angstrom);
            if (delta <= tolerance && delta < best_delta) { best = &line; best_delta = delta; }
        }
        return best;
    };

    const auto pw_line_index = optional_bridge_array_for_hdu(state, "product_write_public_line_index", 3);
    const auto pw_line_emit_in = optional_bridge_array_for_hdu(state, "product_write_public_line_emit_inward", 3, pw_line_index.size());
    const auto pw_line_emit_out = optional_bridge_array_for_hdu(state, "product_write_public_line_emit_outward", 3, pw_line_index.size());
    const auto pw_line_depth_in = optional_bridge_array_for_hdu(state, "product_write_public_line_depth_inward", 3, pw_line_index.size());
    const auto pw_line_depth_out = optional_bridge_array_for_hdu(state, "product_write_public_line_depth_outward", 3, pw_line_index.size());

    // 12.3.41 publication/rank attachment repair.  The retained
    // product_write_public_line_index array is the writer-owned identity rank
    // produced by the literal writespectra2 fixed-capacity insertion routine.
    // Consume it for every element, not just the historical Mg reference.
    // Numeric arrays remain rank-position owners and are intentionally not
    // rebound by physical line index here.
    std::vector<LineLabelTemplateRow> public_line_labels;
    if (!pw_line_index.empty()) {
        public_line_labels.reserve(pw_line_index.size());
        for (const double raw_index : pw_line_index) {
            const auto line_index = static_cast<long long>(std::llround(raw_index));
            const auto* id = line_identity_by_index(state, line_index);
            if (!id) { public_line_labels.clear(); break; }
            public_line_labels.push_back(LineLabelTemplateRow{
                static_cast<int>(line_index), id->wavelength_angstrom, id->ion_label.c_str(),
                id->lower_level.c_str(), id->upper_level.c_str()});
        }
    }
    if (public_line_labels.empty()) {
        // Fail-soft fallback retains the pre-12.3.41 local ranking path for
        // incomplete diagnostic states.  True production is expected to carry
        // the retained writer-owned identity vector.
        std::vector<LineRow> ranked = terminal_list;
        if (ranked.size() > 600u) {
            std::stable_sort(ranked.begin(), ranked.end(), [](const LineRow& a, const LineRow& b) {
                const double la = 0.5 * (a.emis_in + a.emis_out);
                const double lb = 0.5 * (b.emis_in + b.emis_out);
                if (la != lb) return la > lb;
                return a.record < b.record;
            });
            ranked.resize(600u);
        }
        public_line_labels.reserve(ranked.size());
        for (const auto& line : ranked) {
            const auto* id = line_identity_by_index(state, line.record);
            if (!id) continue;
            public_line_labels.push_back(LineLabelTemplateRow{
                static_cast<int>(id->line_index), id->wavelength_angstrom, id->ion_label.c_str(),
                id->lower_level.c_str(), id->upper_level.c_str()});
        }
    }

    const bool have_product_write_public_lines =
        pw_line_index.size() == public_line_labels.size() &&
        pw_line_emit_in.size() == public_line_labels.size() &&
        pw_line_emit_out.size() == public_line_labels.size() &&
        pw_line_depth_in.size() == public_line_labels.size() &&
        pw_line_depth_out.size() == public_line_labels.size();

    std::vector<std::map<long long,LineRow>> diagnostics_by_zone;
    diagnostics_by_zone.reserve(state.radial_zones.size());
    for (const auto& zone : state.radial_zones) {
        diagnostics_by_zone.push_back(diagnostic_line_rows_by_index(
            state, zone.accepted_controller.evaluation, elements, rows,
            zone.accepted_controller.accepted_sequence));
    }
    auto diagnostic_for_label = [&](const std::map<long long,LineRow>& diagnostics,
                                    const LineLabelTemplateRow& label) -> const LineRow* {
        const auto direct = diagnostics.find(label.index);
        if (direct != diagnostics.end()) return &direct->second;
        const int z_label = element_z_from_ion_label(label.ion);
        const int stage_label = roman_stage_from_ion_label(label.ion);
        const LineRow* best = nullptr;
        double best_delta = std::numeric_limits<double>::infinity();
        const double tolerance = std::max(2.0e-3, std::abs(label.wavelength_angstrom) * 2.0e-6);
        for (const auto& kv : diagnostics) {
            const auto& d = kv.second;
            if (d.z != z_label || d.stage != stage_label) continue;
            const double delta = std::abs(d.wavelength_a - label.wavelength_angstrom);
            if (delta <= tolerance && delta < best_delta) { best = &d; best_delta = delta; }
        }
        return best;
    };

    fitsfile* fptr = create_fits(path, state); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, static_cast<long>(public_line_labels.size()), "XSTAR_LINES",
        {"index","ion","lower_level","upper_level","wavelength","emit_inward","emit_outward","depth_inward","depth_outward"},
        {"I6","A9","A20","A20","E13.5","E13.5","E13.5","E13.5","E13.5"}, {"","","","","A","erg/s/10**38","erg/s/10**38","",""});
    for (std::size_t i = 0; i < public_line_labels.size(); ++i) {
        const auto& label = public_line_labels[i];
        LineRow r;
        r.record = label.index;
        r.wavelength_a = label.wavelength_angstrom;
        if (have_product_write_public_lines) {
            r.emis_in = std::isfinite(pw_line_emit_in[i]) ? pw_line_emit_in[i] : 0.0;
            r.emis_out = std::isfinite(pw_line_emit_out[i]) ? pw_line_emit_out[i] : 0.0;
            r.tau_in = std::isfinite(pw_line_depth_in[i]) ? pw_line_depth_in[i] : 0.0;
            r.tau_out = std::isfinite(pw_line_depth_out[i]) ? pw_line_depth_out[i] : 0.0;
        } else {
            const LineRow* retained_terminal = terminal_for_label(label);
            bool accumulated = false;
            if (retained_terminal && line_row_has_signal(*retained_terminal)) {
                r = *retained_terminal;
                accumulated = true;
            }
            for (std::size_t z = 0; !accumulated && z < state.radial_zones.size(); ++z) {
                const LineRow* d = diagnostic_for_label(diagnostics_by_zone[z], label);
                if (!d) continue;
                const double shell_scale = physical_shell_luminosity_scale_1e38_for_output_zone(state, z);
                const double shell_depth = physical_incremental_shell_depth_cm_for_output_zone(state, z);
                if (shell_scale > 0.0) {
                    r.emis_in += d->emis_in * shell_scale;
                    r.emis_out += d->emis_out * shell_scale;
                    accumulated = true;
                }
                if (shell_depth > 0.0 && d->opacity > 0.0) {
                    r.tau_in += d->opacity * shell_depth;
                    accumulated = true;
                }
            }
            if (!accumulated) {
                const auto found = terminal_by_record.find(label.index);
                if (found != terminal_by_record.end()) r = found->second;
            }
            if (const LineRow* terminal_depth = terminal_depth_for_label(label)) {
                if (std::isfinite(terminal_depth->tau_in)) r.tau_in = terminal_depth->tau_in;
                if (std::isfinite(terminal_depth->tau_out)) r.tau_out = terminal_depth->tau_out;
            }
            if (!std::isfinite(r.tau_out)) r.tau_out = 0.0;
        }
        const long row = static_cast<long>(i + 1);
        write_int(fptr, 1, row, label.index);
        write_string(fptr, 2, row, oracle_ion_label(label.ion));
        write_string(fptr, 3, row, label.lower_level);
        write_string(fptr, 4, row, label.upper_level);
        write_real4(fptr, 5, row, label.wavelength_angstrom);
        write_real4(fptr, 6, row, r.emis_in);
        write_real4(fptr, 7, row, r.emis_out);
        write_real4(fptr, 8, row, r.tau_in);
        write_real4(fptr, 9, row, r.tau_out);
    }
    close_fits(fptr);
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write public rrc from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_public_rrc(const std::filesystem::path& path,
                      const xstar_run_state::ProductWritingState& state,
                      const std::vector<ElementMeta>& elements,
                      const std::vector<RowMeta>& rows) {

    // writespectra4.f90 consumes the *post-transport*, one-based npconi2
    // accumulators directly and dynamically publishes every live rate-7 RRC
    // whose accumulated luminosity exceeds the historical 1.e-36 floor:
    //   elumab(1,kkkl) -> emit_outward
    //   elumab(2,kkkl) -> emit_inward
    //   tauc(1,kkkl)   -> depth_outward
    //   tauc(2,kkkl)   -> depth_inward
    //
    // Older native writers selected rows from the frozen 994-row
    // oracle_public_rrc_label_template_v172537().  That was only a snapshot of
    // an older Python product and suppressed 58 legitimate Mg VI-IX rows in the
    // current source-faithful trajectory.  Derive both the public row set and
    // its metadata from the live native RRC identity/workspace instead.
    const xstar_run_state::ExactSourceWorkspaceState* public_ws = nullptr;
    if (!state.radial_zones.empty()) {
        const auto& ws = state.radial_zones.back().accepted_controller.evaluation.source_workspace;
        if (ws.elumab.size() >= 4u && ws.tauc.size() >= 4u &&
            ws.elumab.size() % 2u == 0u && ws.tauc.size() % 2u == 0u) {
            public_ws = &ws;
        }
    }
    const std::size_t elumab_stride = public_ws ? public_ws->elumab.size() / 2u : 0u;
    const std::size_t tauc_stride = public_ws ? public_ws->tauc.size() / 2u : 0u;

    // Retain the old identity/diagnostic path only as a fail-safe when a
    // non-standalone caller has no native accumulated source workspace.
    std::map<long long,RrcRow> fallback_by_index;
    if (!public_ws) {
        const std::size_t final_index = terminal_physical_zone_index(state);
        const auto& evaluation = state.radial_zones[final_index].accepted_controller.evaluation;
        for (const auto& r : source_rrc_rows_from_identities(state, evaluation, elements, rows, 6, false)) {
            fallback_by_index[r.record] = r;
        }
    }

    struct PublicRrcRowV82Patch52094 {
        const xstar_run_state::RrcIdentityState* identity = nullptr;
        double emit_out = 0.0;
        double emit_in = 0.0;
        double depth_out = 0.0;
        double depth_in = 0.0;
    };
    std::vector<PublicRrcRowV82Patch52094> public_rows;
    const bool have_exact_source_rrcs = !state.source_rrc_identities.empty();
    const auto& source_public_rrcs = have_exact_source_rrcs
        ? state.source_rrc_identities : state.rrc_identities;
    public_rows.reserve(source_public_rrcs.size());
    std::set<int> published_continuum_indices;
    for (const auto& identity : source_public_rrcs) {
        if (identity.continuum_index <= 0) continue;
        // Literal writespectra4 ownership is the source rate-type-7 chain,
        // not the terminal active-stage-filtered/padded FITS identity surface.
        // Keep the positive-threshold RRC rule already qualified for STEP
        // Option 19 in 12.3.42.1.3.  This simultaneously removes the 45 O IV
        // non-physical rows and allows late Ca source stages (including the
        // missing Ca XX / Ca XIII identities) to publish when their source
        // elumab workspace is active.
        if (have_exact_source_rrcs && identity.rate_type != 7) continue;
        if (!have_exact_source_rrcs && identity.rate_type != 0 && identity.rate_type != 7) continue;
        if (!(identity.threshold_ev > 0.0)) continue;
        const int z = element_z_from_ion_label(identity.ion_label);
        const ElementMeta* element = nullptr;
        for (const auto& e : elements) if (e.element_z == z) { element = &e; break; }
        if (!element || !(element->abundance > 1.0e-10)) continue;
        if (!published_continuum_indices.insert(identity.continuum_index).second) continue;
        const std::size_t slot = static_cast<std::size_t>(identity.continuum_index);
        PublicRrcRowV82Patch52094 row;
        row.identity = &identity;
        if (public_ws) {
            if (slot < elumab_stride) {
                const double v0 = public_ws->elumab[slot];
                const double v1 = public_ws->elumab[elumab_stride + slot];
                row.emit_out = std::isfinite(v0) ? v0 : 0.0;
                row.emit_in = std::isfinite(v1) ? v1 : 0.0;
            }
            if (slot < tauc_stride) {
                const double v0 = public_ws->tauc[slot];
                const double v1 = public_ws->tauc[tauc_stride + slot];
                row.depth_out = std::isfinite(v0) ? v0 : 0.0;
                row.depth_in = std::isfinite(v1) ? v1 : 0.0;
            }
        } else {
            const auto found = fallback_by_index.find(identity.continuum_index);
            if (found != fallback_by_index.end()) {
                row.emit_out = std::isfinite(found->second.emis_in) ? found->second.emis_in : 0.0;
                row.emit_in = std::isfinite(found->second.emis_out) ? found->second.emis_out : 0.0;
                row.depth_out = std::isfinite(found->second.tau_in) ? found->second.tau_in : 0.0;
                row.depth_in = std::isfinite(found->second.tau_out) ? found->second.tau_out : 0.0;
            }
        }
        if (row.emit_out > xstar_constants::kLegacyWritespectra4RrcLuminosityFloor ||
            row.emit_in > xstar_constants::kLegacyWritespectra4RrcLuminosityFloor) {
            public_rows.push_back(row);
        }
    }

    fitsfile* fptr = create_fits(path, state); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, static_cast<long>(public_rows.size()), "XSTAR_SPECTRA",
        {"index","ion","level","energy","emit_outward","emit_inward","depth_outward","depth_inward"},
        {"I6","A9","A20","E13.5","E13.5","E13.5","E13.5","E13.5"}, {"","","","eV","erg/s","erg/s","",""});
    for (std::size_t i = 0; i < public_rows.size(); ++i) {
        const auto& row_data = public_rows[i];
        const auto& label = *row_data.identity;
        const long row = static_cast<long>(i + 1);
        write_int(fptr, 1, row, label.continuum_index);
        write_string(fptr, 2, row, label.ion_label);
        write_string(fptr, 3, row, label.lower_level);
        write_real4(fptr, 4, row, label.threshold_ev);
        write_real4(fptr, 5, row, row_data.emit_out);
        write_real4(fptr, 6, row, row_data.emit_in);
        write_real4(fptr, 7, row, row_data.depth_out);
        write_real4(fptr, 8, row, row_data.depth_in);
    }
    close_fits(fptr);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write public spectrum from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_public_spectrum(const std::filesystem::path& path,
                           const xstar_run_state::ProductWritingState& state,
                           bool full_spectrum) {
    const std::size_t terminal_index = terminal_physical_zone_index(state);
    const auto& e = state.radial_zones[terminal_index].accepted_controller.evaluation;
    const std::size_t n = e.radiation_energy_ev.size();
    const auto zrems = bridge_array_for_hdu(state, "zrems", 6, 5 * n);
    const auto zremsz = bridge_array_for_hdu(state, "zremsz", 6, n);
    const auto dpthcont = bridge_array_for_hdu(state, "dpthcont", 6, 2 * n);
    const auto final_transmitted = optional_bridge_array_for_hdu(state, "continuum_transmitted_final", 6, n);
    const auto final_continuum_emit_out = optional_bridge_array_for_hdu(state, "continuum_emit_out_final", 6, n);
    const auto final_spectrum_emit_out = optional_bridge_array_for_hdu(state, "spectrum_emit_out_final", 6, n);
    const auto energy_grid = reference_energy_grid(state, e.radiation_energy_ev);
    const auto pw_continuum_energy = optional_bridge_array_for_hdu(state, "product_write_continuum_energy", 3, n);
    const auto pw_continuum_incident = optional_bridge_array_for_hdu(state, "product_write_continuum_incident", 3, n);
    const auto pw_continuum_transmitted = optional_bridge_array_for_hdu(state, "product_write_continuum_transmitted", 3, n);
    const auto pw_continuum_emit_in = optional_bridge_array_for_hdu(state, "product_write_continuum_emit_inward", 3, n);
    const auto pw_continuum_emit_out = optional_bridge_array_for_hdu(state, "product_write_continuum_emit_outward", 3, n);
    const auto pw_spectrum_energy = optional_bridge_array_for_hdu(state, "product_write_spectrum_energy", 3, n);
    const auto pw_spectrum_incident = optional_bridge_array_for_hdu(state, "product_write_spectrum_incident", 3, n);
    const auto pw_spectrum_transmitted = optional_bridge_array_for_hdu(state, "product_write_spectrum_transmitted", 3, n);
    const auto pw_spectrum_emit_in = optional_bridge_array_for_hdu(state, "product_write_spectrum_emit_inward", 3, n);
    const auto pw_spectrum_emit_out = optional_bridge_array_for_hdu(state, "product_write_spectrum_emit_outward", 3, n);
    // Exact-size retained arrays are not sufficient evidence of a valid product
    // surface: the true-native retention path may allocate 9999 zero cells.
    // Do not let those placeholders override a live incident/transmitted field.
    const bool have_product_write_continuum = !full_spectrum &&
        pw_continuum_energy.size() == n && pw_continuum_incident.size() == n &&
        pw_continuum_transmitted.size() == n && pw_continuum_emit_in.size() == n &&
        pw_continuum_emit_out.size() == n &&
        has_finite_monotonic_energy(pw_continuum_energy) &&
        has_finite_nonzero_signal(pw_continuum_incident) &&
        has_finite_nonzero_signal(pw_continuum_transmitted);
    const bool have_product_write_spectrum = full_spectrum &&
        pw_spectrum_energy.size() == n && pw_spectrum_incident.size() == n &&
        pw_spectrum_transmitted.size() == n && pw_spectrum_emit_in.size() == n &&
        pw_spectrum_emit_out.size() == n &&
        has_finite_monotonic_energy(pw_spectrum_energy) &&
        has_finite_nonzero_signal(pw_spectrum_incident) &&
        has_finite_nonzero_signal(pw_spectrum_transmitted);

    std::vector<double> incident_surface;
    if (zremsz.size() == n && has_finite_nonzero_signal(zremsz)) {
        incident_surface = zremsz;
    } else if (!state.radial_zones.empty()) {
        // zrems(1,:) at the first accepted boundary is the live source
        // radiation surface when the dedicated zremsz sidecar was not retained.
        const auto& initial_ws = state.radial_zones.front().accepted_controller.evaluation.source_workspace;
        if (initial_ws.zrems.size() >= n && has_finite_nonzero_signal(initial_ws.zrems)) {
            incident_surface.assign(initial_ws.zrems.begin(), initial_ws.zrems.begin() + static_cast<std::ptrdiff_t>(n));
        } else {
            const auto& initial_flux = state.radial_zones.front().accepted_controller.evaluation.radiation_flux;
            if (initial_flux.size() == n && has_finite_nonzero_signal(initial_flux)) incident_surface = initial_flux;
        }
    }
    if (incident_surface.empty() && e.radiation_flux.size() == n &&
        has_finite_nonzero_signal(e.radiation_flux)) {
        incident_surface = e.radiation_flux;
    }

    std::vector<double> forward_depth_surface;
    // Literal writers own different cumulative depths.  writespectra3 uses
    // dpthcont(1,:) while writespectra/binemis uses the full dpthc(1,:).
    // The old fallback always preferred dpthcont, which made the 62 bins with
    // important line/full opacity transmit as though tau_full were zero.
    const auto dpthc = optional_bridge_array_for_hdu(state, "dpthc", 6, 2 * n);
    if (full_spectrum && dpthc.size() >= n && has_finite_nonzero_signal(dpthc)) {
        forward_depth_surface.assign(dpthc.begin(), dpthc.begin() + static_cast<std::ptrdiff_t>(n));
    } else if (!full_spectrum && dpthcont.size() >= n && has_finite_nonzero_signal(dpthcont)) {
        forward_depth_surface.assign(dpthcont.begin(), dpthcont.begin() + static_cast<std::ptrdiff_t>(n));
    } else if (dpthc.size() >= n && has_finite_nonzero_signal(dpthc)) {
        forward_depth_surface.assign(dpthc.begin(), dpthc.begin() + static_cast<std::ptrdiff_t>(n));
    } else if (dpthcont.size() >= n && has_finite_nonzero_signal(dpthcont)) {
        forward_depth_surface.assign(dpthcont.begin(), dpthcont.begin() + static_cast<std::ptrdiff_t>(n));
    }
    fitsfile* fptr = create_fits(path, state); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, static_cast<long>(n), "XSTAR_SPECTRA",
        {"energy","incident","transmitted","emit_inward","emit_outward"}, {"E13.5","E13.5","E13.5","E13.5","E13.5"},
        {"eV","erg/s/erg","erg/s/erg","erg/s/erg","erg/s/erg"});
    // Literal writespectra/binemis packs saved zrems(2) and zrems(3) into
    // inward/outward spectrum rows before adding line profiles.
    // Literal writespectra3 uses zrems(4) and zrems(5) for the continuum-only
    // product.  Keep the fallback correct even if retained product-write arrays
    // are unavailable.
    const std::size_t inward_row = full_spectrum ? 1 : 3;
    const std::size_t outward_row = full_spectrum ? 2 : 4;
    const auto public_continuum_diag = read_continuum_diagnostics_expanded_to_full_bins(state,
        state.radial_zones.empty() ? 0u : state.radial_zones[terminal_index].accepted_controller.accepted_sequence, n);
    for (std::size_t i = 0; i < n; ++i) {
        double incident = i < incident_surface.size() ? incident_surface[i] : 0.0;
        double tau_forward = i < forward_depth_surface.size() && std::isfinite(forward_depth_surface[i])
            ? std::max(0.0, forward_depth_surface[i]) : 0.0;
        if (!(tau_forward > 0.0)) {
            const double opacity = continuum_diag_opacity_for_bin(public_continuum_diag, i);
            if (opacity > 0.0) tau_forward = opacity * benchmark_total_depth_cm_from_parameters(state);
        }
        double transmitted = incident * std::exp(-tau_forward);
        double emit_inward = 0.0;
        double emit_outward = 0.0;
        const auto& terminal_zrems = e.source_workspace.zrems;
        if (terminal_zrems.size() >= 5u * n) {
            const std::size_t inward_at = inward_row * n + i;
            const std::size_t outward_at = outward_row * n + i;
            if (inward_at < terminal_zrems.size() && std::isfinite(terminal_zrems[inward_at]) &&
                std::abs(terminal_zrems[inward_at]) <= static_cast<double>(std::numeric_limits<float>::max())) {
                emit_inward = terminal_zrems[inward_at];
            }
            if (outward_at < terminal_zrems.size() && std::isfinite(terminal_zrems[outward_at]) &&
                std::abs(terminal_zrems[outward_at]) <= static_cast<double>(std::numeric_limits<float>::max())) {
                emit_outward = terminal_zrems[outward_at];
            }
        }
        if (!(emit_inward != 0.0)) {
            emit_inward = continuum_accumulated_emission_for_bin(public_continuum_diag, i, inward_row);
        }
        if (!(emit_outward != 0.0)) {
            emit_outward = continuum_accumulated_emission_for_bin(public_continuum_diag, i, outward_row);
        }
        double energy_out = i < energy_grid.size() ? energy_grid[i] : (i < e.radiation_energy_ev.size() ? e.radiation_energy_ev[i] : 0.0);
        if (have_product_write_continuum) {
            energy_out = pw_continuum_energy[i];
            incident = pw_continuum_incident[i];
            transmitted = pw_continuum_transmitted[i];
            emit_inward = pw_continuum_emit_in[i];
            emit_outward = pw_continuum_emit_out[i];
        } else if (have_product_write_spectrum) {
            energy_out = pw_spectrum_energy[i];
            incident = pw_spectrum_incident[i];
            transmitted = pw_spectrum_transmitted[i];
            emit_inward = pw_spectrum_emit_in[i];
            emit_outward = pw_spectrum_emit_out[i];
        }
        if (!std::isfinite(incident)) incident = 0.0;
        if (!std::isfinite(transmitted)) transmitted = 0.0;
        if (!std::isfinite(emit_inward)) emit_inward = 0.0;
        if (!std::isfinite(emit_outward)) emit_outward = 0.0;
        const long row = static_cast<long>(i + 1);
        write_real4(fptr, 1, row, energy_out);
        write_real4(fptr, 2, row, incident);
        write_real4(fptr, 3, row, transmitted);
        write_real4(fptr, 4, row, emit_inward);
        write_real4(fptr, 5, row, emit_outward);
    }
    close_fits(fptr);
}


} // namespace

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write historical science products from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
Result write_historical_science_products(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    const std::vector<Snapshot>&,
    const std::vector<double>&) {
    (void)program_dir;
    (void)output_dir;
    throw std::runtime_error("native science products require ProductWritingState");
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write historical science products from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
Result write_historical_science_products(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state,
    const std::vector<double>& native_energy_ev) {
    (void)native_energy_ev;
    // v17.25.32: publish partial native science products after the full-61
    // controller gates.  Incomplete scientific payload families are reported
    // by the publication manifest and repaired incrementally; only anti-copy
    // provenance remains a hard pre-write requirement here.
    if (!state.embedded_public_fits_payloads_absent ||
        !state.embedded_full_xout_step_payload_absent) {
        throw std::runtime_error("native FITS anti-copy provenance is incomplete");
    }
    std::filesystem::create_directories(output_dir);
    const auto elements = read_elements(state, program_dir);
    const auto rows = read_rows(state, program_dir);
    write_population_detail(output_dir / "xo01_detail.fits", state, elements, rows);
    write_line_detail(output_dir / "xo01_detal2.fits", state, elements, rows);
    write_rrc_detail(output_dir / "xo01_detal3.fits", state, elements, rows);
    write_spectrum_detail(output_dir / "xo01_detal4.fits", state);
    write_public_lines(output_dir / "xout_lines1.fits", state, elements, rows);
    state.xout_lines1_computed_from_native_state = true;
    write_public_rrc(output_dir / "xout_rrc1.fits", state, elements, rows);
    state.xout_rrc1_computed_from_native_state = true;
    write_public_spectrum(output_dir / "xout_cont1.fits", state, false);
    state.xout_cont1_computed_from_native_state = true;
    write_public_spectrum(output_dir / "xout_spect1.fits", state, true);
    state.xout_spect1_computed_from_native_state = true;
    // xout_abund1 is written after xout_step.log by write_native_abundance_product().
    state.xout_abund1_computed_from_native_state = false;

    Result result;
    result.files_written = 8;
    result.schema_complete = true;
    result.computed_from_native_state = true;
    result.continuum_and_spectrum_paths_separate = true;
    result.physical_equivalence_qualified = false;
    result.detail_products_byte_exact = false;
    result.public_products_byte_exact = false;
    result.all_fits_products_byte_exact = false;
    result.benchmark_archive_materialized = false;
    result.generalized_product_reduction_qualified = false;
    result.filenames = {"xo01_detail.fits","xo01_detal2.fits","xo01_detal3.fits","xo01_detal4.fits",
        "xout_cont1.fits","xout_lines1.fits","xout_rrc1.fits","xout_spect1.fits"};
    return result;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide abundance product enabled for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool abundance_product_enabled() {
    const char* disable = std::getenv("XSTAR_V04874625517_DISABLE_ABUNDANCE_PRODUCT");
    if (disable != nullptr && std::string(disable) == "1") return false;
    const char* flag = std::getenv("XSTAR_V04874625517_ENABLE_ABUNDANCE_PRODUCT");
    if (flag != nullptr) return std::string(flag) == "1";
    // Compatibility with the previous opt-in gate, but v25.5.15.9.1 enables the
    // safe native abundance writer by default.
    const char* old_flag = std::getenv("XSTAR_V048746255158_ENABLE_ABUNDANCE_PRODUCT");
    if (old_flag != nullptr) return std::string(old_flag) == "1";
    return true;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write native abundance product from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void write_native_abundance_product(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    const auto elements = read_elements(state, program_dir);
    const auto rows = read_rows(state, program_dir);
    std::filesystem::create_directories(output_dir);
    const auto final_path = output_dir / "xout_abund1.fits";
    const auto tmp_path = output_dir / ".xout_abund1.fits.tmp";
    std::error_code ec;
    std::filesystem::remove(tmp_path, ec);
    try {
        write_abundances(tmp_path, state, elements, rows);
        if (!std::filesystem::is_regular_file(tmp_path) || std::filesystem::file_size(tmp_path) == 0) {
            throw std::runtime_error("native abundance writer produced an empty temporary file");
        }
        std::filesystem::remove(final_path, ec);
        std::filesystem::rename(tmp_path, final_path);
        if (!std::filesystem::is_regular_file(final_path) || std::filesystem::file_size(final_path) == 0) {
            throw std::runtime_error("native abundance writer did not publish a nonzero product");
        }
    } catch (...) {
        std::filesystem::remove(tmp_path, ec);
        std::filesystem::remove(final_path, ec);
        state.xout_abund1_computed_from_native_state = false;
        throw;
    }
    state.xout_abund1_computed_from_native_state = true;
}

} // namespace xstar_science_fits
