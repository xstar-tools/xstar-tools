#include "xstar_fixed_state_engine.h"
#include "xstar_element_engine.h"
#include "xstar_spectral_engine.h"
#include "type50_manifold_oracle_v048710.h"
#include "type50_dsec_runtime_oracle_v048713.h"
#include "type53_row46_dsec_runtime_oracle_v048716.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <filesystem>
#include <iomanip>
#include <limits>
#include <memory>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {

using clock_type = std::chrono::steady_clock;
constexpr double kBoltzmannEvK = 8.617333262145e-5;
constexpr double kErgPerEv = 1.602176634e-12;
constexpr double kRydEv = 13.60569253;
// The v0.6.47.2 type-53 evaluator uses the historical rounded Rydberg
// constant.  Keep it separate from the newer global constant: changing this
// value moves the cross-section grid and breaks IEEE parity.
constexpr double kType53RydEv = 13.605692;
constexpr double kSigmaT = 6.6524587321e-25;

extern "C" int xstar_engine_type63_rates_v1(
    int ni, int li, int nf, int lf, int iq,
    double temperature_k, double electron_density_cm3,
    double initial_energy_ev, double final_energy_ev,
    double initial_g, double final_g,
    double* out6
);
extern "C" int xstar_engine_anl1_v1(int ni, int nf, int lf, int iq, double* alm, double* alp);
extern "C" int xstar_emissivity_build_binemis_profile(
    int ncn2, int nbtpp, int ncols, int n_line_slots, int n_lum_lines,
    double xlum, double temperature_1e4k, double turbulent_velocity_km_s,
    const double* epi_ev, const double* dpthc_flat, const double* elum_flat,
    const double* original_flat, const double* incident, const long long* slot_line_index,
    const double* line_wavelength, const long long* line_data_type, const double* line_atomic_mass,
    const double* line_natural_rate_s, const double* line_auger_width_ev,
    const double* line_auger_rate_s, double* out_flat, double* stats,
    char* errbuf, std::size_t errbuf_size);

void copy_text(char* target, std::size_t cap, const std::string& value) {
    if (!target || cap == 0) return;
    const std::size_t n = std::min(cap - 1, value.size());
    std::memcpy(target, value.data(), n);
    target[n] = '\0';
}

double elapsed(const clock_type::time_point& start) {
    return std::chrono::duration<double>(clock_type::now() - start).count();
}

int environment_data_type(const char* name) {
    const char* value = std::getenv(name);
    if (!value || !*value) return 0;
    char* end = nullptr;
    const long parsed = std::strtol(value, &end, 10);
    if (!end || *end != '\0' || parsed < 0 || parsed > 1000000) {
        throw std::runtime_error(std::string("invalid ") + name + " data type");
    }
    return static_cast<int>(parsed);
}

bool environment_flag(const char* name) {
    const char* value = std::getenv(name);
    if (!value || !*value) return false;
    if (std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error(std::string("invalid environment flag: ") + name);
}

const xstar_type50_manifold_oracle_v048710::Entry* find_type50_manifold_oracle_entry(
    std::uint64_t source_position,
    std::uint64_t record
) {
    for (const auto& entry : xstar_type50_manifold_oracle_v048710::kEntries) {
        if (entry.source_position == source_position && entry.record == record) return &entry;
    }
    return nullptr;
}

const xstar_type50_dsec_runtime_oracle_v048713::Entry* find_type50_dsec_runtime_oracle_entry(
    std::uint64_t source_position,
    std::uint64_t record
) {
    for (const auto& entry : xstar_type50_dsec_runtime_oracle_v048713::kEntries) {
        if (entry.source_position == source_position && entry.record == record) return &entry;
    }
    return nullptr;
}

const xstar_type53_row46_dsec_runtime_oracle_v048716::Entry* find_type53_row46_dsec_runtime_oracle_entry(
    std::uint64_t source_position,
    std::uint64_t record
) {
    for (const auto& entry : xstar_type53_row46_dsec_runtime_oracle_v048716::kEntries) {
        if (entry.source_position == source_position && entry.record == record) return &entry;
    }
    return nullptr;
}

int type53_row46_original_contribution_slot(const xstar_element_contribution_v1& contribution) {
    const auto* entry = find_type53_row46_dsec_runtime_oracle_entry(
        contribution.source_position, contribution.record);
    if (!entry) return -1;
    return (entry->first_source_order_index - 1) / 4;
}

void reorder_type53_row46_coupled_contributions(
    std::vector<xstar_element_contribution_v1>& contributions
) {
    if (contributions.empty()) return;
    std::vector<std::optional<xstar_element_contribution_v1>> slots(contributions.size());
    std::vector<xstar_element_contribution_v1> remainder;
    remainder.reserve(contributions.size());
    for (const auto& contribution : contributions) {
        const int slot = type53_row46_original_contribution_slot(contribution);
        if (slot >= 0) {
            if (slot >= static_cast<int>(slots.size())) {
                throw std::runtime_error("type53 row46 original source-order slot outside contribution stream");
            }
            if (slots[static_cast<std::size_t>(slot)].has_value()) {
                throw std::runtime_error("duplicate type53 row46 original source-order slot");
            }
            slots[static_cast<std::size_t>(slot)] = contribution;
        } else {
            remainder.push_back(contribution);
        }
    }
    std::size_t next = 0;
    for (auto& slot : slots) {
        if (!slot.has_value()) {
            if (next >= remainder.size()) throw std::runtime_error("type53 row46 source-order fill underflow");
            slot = remainder[next++];
        }
    }
    if (next != remainder.size()) throw std::runtime_error("type53 row46 source-order fill overflow");
    for (std::size_t i = 0; i < slots.size(); ++i) contributions[i] = *slots[i];
}

std::string trim(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

std::vector<std::string> split_csv(const std::string& line) {
    std::vector<std::string> out;
    std::string current;
    bool quoted = false;
    for (std::size_t i = 0; i < line.size(); ++i) {
        const char ch = line[i];
        if (ch == '"') {
            if (quoted && i + 1 < line.size() && line[i + 1] == '"') {
                current.push_back('"');
                ++i;
            } else {
                quoted = !quoted;
            }
        } else if (ch == ',' && !quoted) {
            out.push_back(trim(current));
            current.clear();
        } else {
            current.push_back(ch);
        }
    }
    out.push_back(trim(current));
    return out;
}

template <typename T>
T parse_number(const std::string& text, const char* field) {
    std::istringstream stream(text);
    T value{};
    stream >> value;
    if (!stream || !stream.eof()) throw std::runtime_error(std::string("invalid ") + field + ": " + text);
    return value;
}

std::unordered_map<std::string, std::string> read_manifest(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open manifest: " + path);
    std::unordered_map<std::string, std::string> values;
    std::string line;
    while (std::getline(input, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        const auto pos = line.find('=');
        if (pos == std::string::npos) throw std::runtime_error("invalid manifest line: " + line);
        values.emplace(trim(line.substr(0, pos)), trim(line.substr(pos + 1)));
    }
    return values;
}

struct ElementRow {
    int element_index = 0;
    int row = 0;
    int superlevel = 0;
    int ion = 0;
    int ion_charge = 0;
    double initial_population = 0.0;
    double energy_ev = 0.0;
    double statistical_weight = 1.0;
    int principal_n = 0;
    int orbital_l = 0;
};

struct ElementProgram {
    int element_index = 0;
    int element_z = 0;
    double abundance = 1.0;
    int n_rows = 0;
    int n_superlevels = 0;
    int n_ions = 0;
    int normalization_row = 1;
    int record_head = -1;
    int record_count = 0;
    std::vector<ElementRow> rows;
};

struct ProgramRecord {
    std::int64_t source_position = 0;
    std::int64_t record = 0;
    int next_index = -1;
    int element_index = 0;
    int opcode = 0;
    int data_type = 0;
    int rate_type = 0;
    int ion_index = 0;
    int ion_stage = 0;
    int lower_row = 0;
    int upper_row = 0;
    std::size_t real_offset = 0;
    std::size_t real_count = 0;
    std::size_t int_offset = 0;
    std::size_t int_count = 0;
    double density_scale = 1.0;
    double line_energy_ev = 0.0;
    double atomic_mass_amu = 1.0;
    double natural_width_ev = 0.0;
    bool matrix_enabled = true;
};

struct Program {
    std::string id;
    bool active_atdb_lowered = false;
    std::uint64_t topology_record_count = 0;
    std::uint64_t unsupported_record_count = 0;
    std::vector<ElementProgram> elements;
    std::vector<ProgramRecord> records;
    std::vector<double> reals;
    std::vector<std::int64_t> ints;
};

struct Type53SourceShadow {
    bool valid = false;
    std::array<double,6> ans{};
    double threshold_ev = 0.0;
    double rnist = 0.0;
    double sumr = 0.0;
    double sumi = 0.0;
    double sumh = 0.0;
    double sumh2 = 0.0;
    double sumc = 0.0;
    double sumc2 = 0.0;
    int nb1_one_based = 0;
    int klmax_one_based = 0;
    bool row46_contract = false;
    bool captured_state_anchor = false;
    double tau_in = 0.0;
    double tau_out = 0.0;
    double ptmp1 = 1.0;
    double ptmp2 = 0.0;
    double covering_fraction = 0.0;
    bool runtime_state_abi_used = false;
    int continuum_index_one_based = 0;
    std::size_t dsec_radiation_bin_count = 0;
    std::size_t continuum_tau_count = 0;
};

struct EvaluatedRecord {
    xstar_element_contribution_v1 contribution{};
    bool spectral = false;
    bool matrix_enabled = true;
    double line_energy_ev = 0.0;
    double atomic_mass_amu = 1.0;
    double natural_width_ev = 0.0;
    double opakab = 0.0;
    Type53SourceShadow type53_shadow{};
};

struct NativeRecordDiagnostic {
    int element_index = 0;
    int element_z = 0;
    EvaluatedRecord evaluated{};
    bool active_stage = false;
    bool matrix_committed = false;
};

struct PreliminaryIonBalance {
    std::vector<double> ionization;
    std::vector<double> recombination;
    std::vector<double> fractions;  // stages 1..Z+1 stored at indices 0..Z
    int min_stage = 1;
    int max_stage = 1;
};

struct ActiveElementView {
    ElementProgram element;
    int full_row_start = 1;
    int full_row_end = 1;
    int min_stage = 1;
    int max_stage = 1;
};

struct NativeElementDiagnostic {
    int element_index = 0;
    int element_z = 0;
    double abundance = 0.0;
    PreliminaryIonBalance preliminary;
    ActiveElementView active;
    std::vector<double> full_populations;
    std::vector<double> final_stage_fractions;
    double heating = 0.0;
    double cooling = 0.0;
    double heating2 = 0.0;
    double cooling2 = 0.0;
    double normalization = 0.0;
    double normalization_error = 0.0;
    double max_relative_row_residual = 0.0;
    std::uint64_t records_constructed = 0;
    std::uint64_t terms_constructed = 0;
    bool solve_response_captured = false;
    std::vector<double> active_initial_populations;
    std::vector<double> active_final_outer_start_populations;
    std::vector<double> active_final_populations;
    std::vector<double> dense_matrix;
    std::vector<double> heating_matrix;
    std::vector<double> heating_matrix2;
    std::vector<double> rhs;
    std::vector<double> row_residual;
    std::vector<double> row_scale;
    std::vector<double> relative_row_residual;
    std::string solver_method;
    std::uint32_t solver_status_flags = 0;
    int outer_iterations = 0;
    int fixed_point_iterations = 0;
};

struct ElementBuffers {
    std::vector<int32_t> superlevels;
    std::vector<int32_t> ions;
    std::vector<double> initial;
    std::vector<double> populations;
    std::vector<double> outer;
    std::vector<double> dense;
    std::vector<double> heat;
    std::vector<double> heat2;
    std::vector<double> rhs;
    std::vector<double> gamma;
    std::vector<double> alpha;
    std::vector<double> fgamma;
    std::vector<double> falpha;
    std::vector<std::int64_t> igamma;
    std::vector<std::int64_t> ialpha;
    std::vector<double> ion_population;
    std::vector<double> ion_population_final;
    std::vector<double> ionization;
    std::vector<double> recombination;
    std::vector<double> ionization_components;
    std::vector<double> recombination_components;
    std::vector<double> row_residual;
    std::vector<double> row_scale;
    std::vector<double> relative_residual;
};

struct xstar_fixed_state_context_impl {
    Program program;
    xstar_element_engine_context* element_context = nullptr;
    xstar_spectral_context* spectral_context = nullptr;
    std::uint64_t state_generation = 0;
    std::map<int, std::uint64_t> visited_data_types;
    std::vector<NativeRecordDiagnostic> last_record_diagnostics;
    std::vector<NativeElementDiagnostic> last_element_diagnostics;
    double last_temperature_k = 0.0;
    double last_electron_density_cm3 = 0.0;
    double last_hydrogen_density_cm3 = 0.0;
    double last_electron_fraction_input = 0.0;
    std::size_t last_radiation_bin_count = 0;
    double last_computed_electron_fraction = 0.0;
    double last_charge_residual = 0.0;
    double last_total_heating = 0.0;
    double last_total_cooling = 0.0;
    double last_hmctot = 0.0;
    int last_helium_matrix_ablation_type = 0;
    int last_helium_preliminary_ablation_type = 0;
    int last_helium_source_position_ablation = 0;
    int last_helium_matrix_ablation_row_type = 0;
    int last_helium_matrix_ablation_row_min = 0;
    int last_helium_matrix_ablation_row_max = 0;
    bool last_helium_unqualified_type53_ablation = false;
    bool last_helium_unqualified_type71_ablation = false;
    bool last_helium_unqualified_type99_ablation = false;
    bool last_helium_solve_response = false;
    bool last_type53_row46_coupled_replacement = false;
    std::map<int, std::array<double,4>> last_element_thermal_budget;
    std::array<double,4> last_helium_type53_budget{{0.0,0.0,0.0,0.0}};
};

std::string join_path(const std::string& base, const std::string& name) {
    if (base.empty()) return name;
    if (base.back() == '/') return base + name;
    return base + "/" + name;
}

void load_elements(const std::string& path, Program& program) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open elements.csv");
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("elements.csv is empty");

    const auto header = split_csv(line);
    if (header.size() != 8 && header.size() != 9) {
        throw std::runtime_error("elements.csv requires 8 legacy columns or 9 columns with abundance");
    }
    std::unordered_map<std::string, std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) {
        if (!columns.emplace(header[i], i).second) {
            throw std::runtime_error("duplicate elements.csv column: " + header[i]);
        }
    }
    const auto column = [&](const char* name) -> std::size_t {
        const auto it = columns.find(name);
        if (it == columns.end()) throw std::runtime_error(std::string("missing elements.csv column: ") + name);
        return it->second;
    };
    const std::size_t element_index_col = column("element_index");
    const std::size_t element_z_col = column("element_z");
    const std::size_t n_rows_col = column("n_rows");
    const std::size_t n_superlevels_col = column("n_superlevels");
    const std::size_t n_ions_col = column("n_ions");
    const std::size_t normalization_row_col = column("normalization_row");
    const std::size_t record_head_col = column("record_head");
    const std::size_t record_count_col = column("record_count");
    const auto abundance_it = columns.find("abundance");
    if (header.size() == 9 && abundance_it == columns.end()) {
        throw std::runtime_error("nine-column elements.csv is missing abundance");
    }

    while (std::getline(input, line)) {
        if (trim(line).empty()) continue;
        const auto c = split_csv(line);
        if (c.size() != header.size()) throw std::runtime_error("elements.csv row width does not match header");
        ElementProgram e;
        e.element_index = parse_number<int>(c[element_index_col], "element_index");
        e.element_z = parse_number<int>(c[element_z_col], "element_z");
        if (abundance_it != columns.end()) e.abundance = parse_number<double>(c[abundance_it->second], "abundance");
        e.n_rows = parse_number<int>(c[n_rows_col], "n_rows");
        e.n_superlevels = parse_number<int>(c[n_superlevels_col], "n_superlevels");
        e.n_ions = parse_number<int>(c[n_ions_col], "n_ions");
        e.normalization_row = parse_number<int>(c[normalization_row_col], "normalization_row");
        e.record_head = parse_number<int>(c[record_head_col], "record_head");
        e.record_count = parse_number<int>(c[record_count_col], "record_count");
        if (!std::isfinite(e.abundance) || e.abundance < 0.0) throw std::runtime_error("element abundance must be finite and nonnegative");
        if (e.element_index != static_cast<int>(program.elements.size())) throw std::runtime_error("element_index must be dense and source ordered");
        if (e.n_rows <= 0 || e.n_superlevels <= 0 || e.n_ions <= 0) throw std::runtime_error("invalid element dimensions");
        program.elements.push_back(e);
    }
}

void load_rows(const std::string& path, Program& program) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open rows.csv");
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("rows.csv is empty");
    while (std::getline(input, line)) {
        if (trim(line).empty()) continue;
        const auto c = split_csv(line);
        if (c.size() != 8 && c.size() != 10) throw std::runtime_error("rows.csv requires 8 or 10 columns");
        ElementRow r;
        r.element_index = parse_number<int>(c[0], "element_index");
        r.row = parse_number<int>(c[1], "row");
        r.superlevel = parse_number<int>(c[2], "superlevel");
        r.ion = parse_number<int>(c[3], "ion");
        r.ion_charge = parse_number<int>(c[4], "ion_charge");
        r.initial_population = parse_number<double>(c[5], "initial_population");
        r.energy_ev = parse_number<double>(c[6], "energy_ev");
        r.statistical_weight = parse_number<double>(c[7], "statistical_weight");
        if (c.size() == 10) {
            r.principal_n = parse_number<int>(c[8], "principal_n");
            r.orbital_l = parse_number<int>(c[9], "orbital_l");
        }
        if (r.element_index < 0 || r.element_index >= static_cast<int>(program.elements.size())) throw std::runtime_error("row element_index out of range");
        program.elements[static_cast<std::size_t>(r.element_index)].rows.push_back(r);
    }
    for (auto& e : program.elements) {
        std::sort(e.rows.begin(), e.rows.end(), [](const ElementRow& a, const ElementRow& b) { return a.row < b.row; });
        if (static_cast<int>(e.rows.size()) != e.n_rows) throw std::runtime_error("row count does not match element n_rows");
        for (int i = 0; i < e.n_rows; ++i) {
            if (e.rows[static_cast<std::size_t>(i)].row != i + 1) throw std::runtime_error("element rows must be one-based dense");
        }
    }
}

void load_records(const std::string& path, Program& program) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open records.csv");
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("records.csv is empty");
    while (std::getline(input, line)) {
        if (trim(line).empty()) continue;
        const auto c = split_csv(line);
        if (c.size() != 18 && c.size() != 19) throw std::runtime_error("records.csv requires 18 or 19 columns");
        ProgramRecord r;
        r.source_position = parse_number<std::int64_t>(c[0], "source_position");
        r.record = parse_number<std::int64_t>(c[1], "record");
        r.next_index = parse_number<int>(c[2], "next_index");
        r.element_index = parse_number<int>(c[3], "element_index");
        r.opcode = parse_number<int>(c[4], "opcode");
        r.data_type = parse_number<int>(c[5], "data_type");
        r.rate_type = parse_number<int>(c[6], "rate_type");
        r.ion_index = parse_number<int>(c[7], "ion_index");
        r.ion_stage = parse_number<int>(c[8], "ion_stage");
        r.lower_row = parse_number<int>(c[9], "lower_row");
        r.upper_row = parse_number<int>(c[10], "upper_row");
        r.real_offset = parse_number<std::size_t>(c[11], "real_offset");
        r.real_count = parse_number<std::size_t>(c[12], "real_count");
        r.int_offset = parse_number<std::size_t>(c[13], "int_offset");
        r.int_count = parse_number<std::size_t>(c[14], "int_count");
        r.density_scale = parse_number<double>(c[15], "density_scale");
        r.line_energy_ev = parse_number<double>(c[16], "line_energy_ev");
        r.atomic_mass_amu = parse_number<double>(c[17], "atomic_mass_amu");
        if (c.size() == 19) r.matrix_enabled = parse_number<int>(c[18], "matrix_enabled") != 0;
        if (r.element_index < 0 || r.element_index >= static_cast<int>(program.elements.size())) throw std::runtime_error("record element_index out of range");
        program.records.push_back(r);
    }
}

template <typename T>
std::vector<T> load_scalar_file(const std::string& path, const char* name) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error(std::string("cannot open ") + name);
    std::vector<T> values;
    std::string line;
    while (std::getline(input, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        values.push_back(parse_number<T>(line, name));
    }
    return values;
}

Program load_program(const std::string& directory) {
    Program p;
    const auto manifest = read_manifest(join_path(directory, "manifest.txt"));
    const auto abi_it = manifest.find("program_abi");
    const auto id_it = manifest.find("program_id");
    if (abi_it == manifest.end() || parse_number<unsigned>(abi_it->second, "program_abi") != XSTAR_FIXED_STATE_PROGRAM_ABI_VERSION) {
        throw std::runtime_error("fixed-state program ABI mismatch");
    }
    if (id_it == manifest.end() || id_it->second.empty()) throw std::runtime_error("program_id missing");
    p.id = id_it->second;
    const auto active_it = manifest.find("active_atdb_lowered");
    p.active_atdb_lowered = active_it != manifest.end() && active_it->second == "true";
    const auto topology_it = manifest.find("topology_record_count");
    if (topology_it != manifest.end()) p.topology_record_count = parse_number<std::uint64_t>(topology_it->second, "topology_record_count");
    const auto unsupported_it = manifest.find("unsupported_record_count");
    if (unsupported_it != manifest.end()) p.unsupported_record_count = parse_number<std::uint64_t>(unsupported_it->second, "unsupported_record_count");
    load_elements(join_path(directory, "elements.csv"), p);
    load_rows(join_path(directory, "rows.csv"), p);
    p.reals = load_scalar_file<double>(join_path(directory, "reals.txt"), "reals.txt");
    p.ints = load_scalar_file<std::int64_t>(join_path(directory, "ints.txt"), "ints.txt");
    load_records(join_path(directory, "records.csv"), p);
    std::int64_t previous_source_position = 0;
    for (std::size_t k = 0; k < p.records.size(); ++k) {
        const auto& r = p.records[k];
        if (r.source_position <= 0 || r.source_position <= previous_source_position) {
            throw std::runtime_error("record source_position must be positive and strictly increasing");
        }
        previous_source_position = r.source_position;
        if (r.next_index < -1 || r.next_index >= static_cast<int>(p.records.size())) throw std::runtime_error("record next_index out of range");
        if (r.real_offset + r.real_count > p.reals.size()) throw std::runtime_error("record real payload out of range");
        if (r.int_offset + r.int_count > p.ints.size()) throw std::runtime_error("record integer payload out of range");
        const auto& e = p.elements[static_cast<std::size_t>(r.element_index)];
        if (r.matrix_enabled) {
            if (r.lower_row < 1 || r.lower_row > e.n_rows || r.upper_row < 1 || r.upper_row > e.n_rows) throw std::runtime_error("record endpoint out of compact element range");
        } else if (r.lower_row != 0 || r.upper_row != 0) {
            throw std::runtime_error("scalar-only record endpoints must be zero");
        }
    }
    return p;
}

double limited_exp(double x) {
    return std::exp(std::max(-700.0, std::min(700.0, x)));
}

// Exact XSTAR expo.f90 contract used by the v0.6.47.2 type-53 evaluator.
double type53_expo(double x) {
    return std::exp(std::max(-60.0, std::min(60.0, x)));
}

/* XSTAR-style scaled x*exp(x)*E1(x), copied from the validated collision translation. */
double expint_scaled(double x) {
    if (!(x > 0.0) || !std::isfinite(x)) return 0.0;
    if (x <= 1.0) {
        const double a0 = -0.57721566;
        const double a1 = 0.99999193;
        const double a2 = -0.24991055;
        const double a3 = 0.05519968;
        const double a4 = -0.00976004;
        const double a5 = 0.00107857;
        const double e1 = -std::log(x) + a0 + x * (a1 + x * (a2 + x * (a3 + x * (a4 + x * a5))));
        return x * limited_exp(x) * e1;
    }
    const double b1 = 8.5733287401;
    const double b2 = 18.0590169730;
    const double b3 = 8.6347608925;
    const double b4 = 0.2677737343;
    const double c1 = 9.5733223454;
    const double c2 = 25.6329561486;
    const double c3 = 21.0996530827;
    const double c4 = 3.9584969228;
    const double numerator = x * x * x * x + b1 * x * x * x + b2 * x * x + b3 * x + b4;
    const double denominator = x * x * x * x + c1 * x * x * x + c2 * x * x + c3 * x + c4;
    return numerator / denominator;
}

double type69_upsilon(const double* r, std::size_t n, double temperature_k) {
    if (!r || n < 6 || temperature_k <= 0.0 || r[0] <= 0.0) return -1.0;
    double y = r[0] / temperature_k * 1.160443e4;
    if (y < 1.0e-20) return -1.0;
    if (y > 1.0e20) return 0.0;
    y = std::max(5.0e-2, std::min(77.0, y));
    const double em1 = expint_scaled(y);
    const double a = r[1], b = r[2], c = r[3], d = r[4], e = r[5];
    double gamma = 0.0;
    if (n == 6) {
        gamma = y * ((a / y + c) + d * 0.5 * (1.0 - y));
        gamma += em1 * (b - c * y + d * y * y * 0.5 + e / y);
    } else {
        if (n < 9 || r[8] <= 0.0) return -1.0;
        const double p = r[6], q = r[7], x1 = r[8];
        const double em1x = expint_scaled(y * x1);
        double gnr = a / y + c / x1 + d * 0.5 * (1.0 / (x1 * x1) - y / x1) + e / y * std::log(x1);
        gnr += em1x / y / x1 * (b - c * y + d * y * y * 0.5 + e / y);
        gnr *= y * limited_exp(y * (1.0 - x1));
        const double base = 1.0 + 1.0 / y;
        const double gr = p * base * (1.0 - limited_exp(y * (1.0 - x1)) * (x1 + 1.0 / y) / base);
        gamma = gnr + gr + q * em1;
    }
    return std::max(0.0, gamma);
}

double interp_linear(const double* x, const double* y, std::size_t n, double value) {
    if (!x || !y || n == 0) return 0.0;
    if (value <= x[0]) return y[0];
    if (value >= x[n - 1]) return y[n - 1];
    const auto* upper = std::upper_bound(x, x + n, value);
    const std::size_t k = static_cast<std::size_t>(upper - x - 1);
    const double dx = x[k + 1] - x[k];
    return dx == 0.0 ? y[k] : y[k] + (value - x[k]) * (y[k + 1] - y[k]) / dx;
}

double natural_spline9(const double* y, double x) {
    const int n = 9;
    const double h = 0.125;
    std::array<double, n> m{};
    std::array<double, n - 2> a{}, b{}, c{}, d{};
    for (int i = 0; i < n - 2; ++i) {
        a[i] = i == 0 ? 0.0 : 1.0;
        b[i] = 4.0;
        c[i] = i == n - 3 ? 0.0 : 1.0;
        d[i] = 6.0 * (y[i + 2] - 2.0 * y[i + 1] + y[i]) / (h * h);
    }
    for (int i = 1; i < n - 2; ++i) {
        const double q = a[i] / b[i - 1];
        b[i] -= q * c[i - 1];
        d[i] -= q * d[i - 1];
    }
    for (int i = n - 3; i >= 0; --i) {
        m[i + 1] = (d[i] - c[i] * m[i + 2]) / b[i];
    }
    x = std::max(0.0, std::min(1.0, x));
    int k = std::min(7, static_cast<int>(x / h));
    const double x0 = k * h, x1 = (k + 1) * h;
    const double aa = (x1 - x) / h, bb = (x - x0) / h;
    return aa * y[k] + bb * y[k + 1] + ((aa * aa * aa - aa) * m[k] + (bb * bb * bb - bb) * m[k + 1]) * h * h / 6.0;
}

double type51_upsilon(const double* r, std::size_t n, const std::int64_t* ints, std::size_t ni, double temperature_k) {
    if (!r || n < 7 || !ints || ni < 1 || r[0] <= 0.0 || r[1] <= 0.0) return -1.0;
    const int bt_type = static_cast<int>(ints[0]);
    const double eij_ryd = r[0], c = r[1];
    const double u = temperature_k / (eij_ryd * 157887.0);
    if (!(u > 0.0)) return -1.0;
    double x = 0.0;
    switch (bt_type) {
        case 1: case 4: x = 1.0 - std::log(c) / std::log(u + c); break;
        case 2: case 3: case 5: case 6: x = u / (u + c); break;
        default: return -1.0;
    }
    double scaled = 0.0;
    if (n == 7) {
        const double* y = r + 2;
        const double xx = std::max(0.0, std::min(1.0, x)) * 4.0;
        const int k = std::min(3, static_cast<int>(xx));
        const double f = xx - k;
        scaled = y[k] + f * (y[k + 1] - y[k]);
    } else if (n >= 11) {
        scaled = natural_spline9(r + 2, x);
    } else return -1.0;
    switch (bt_type) {
        case 1: return scaled * std::log(u + std::exp(1.0));
        case 2: return scaled;
        case 3: return scaled / (u + 1.0);
        case 4: return scaled * std::log(u + c);
        case 5: return scaled / u;
        case 6: return std::pow(10.0, scaled);
        default: return -1.0;
    }
}

double type56_upsilon(const double* r, std::size_t n, double temperature_k) {
    if (!r || n < 4 || (n % 2) != 0 || !(temperature_k > 0.0)) return -1.0;
    const std::size_t points = n / 2;
    if (points < 2) return -1.0;
    const double x = std::log10(temperature_k);
    const bool ascending = r[points - 1] > r[0];
    std::size_t i = 0;
    if (ascending) {
        if (x <= r[0]) i = 0;
        else if (x >= r[points - 1]) i = points - 2;
        else {
            for (std::size_t k = 0; k + 1 < points; ++k) {
                if (r[k] <= x && x <= r[k + 1]) { i = k; break; }
            }
        }
    } else {
        if (x >= r[0]) i = 0;
        else if (x <= r[points - 1]) i = points - 2;
        else {
            for (std::size_t k = 0; k + 1 < points; ++k) {
                if (r[k] >= x && x >= r[k + 1]) { i = k; break; }
            }
        }
    }
    const double y0 = std::max(1.0e-48, r[points + i]);
    const double y1 = std::max(1.0e-48, r[points + i + 1]);
    const double dx = r[i + 1] - r[i];
    const double value = (y1 - y0) * (x - r[i]) / (dx + 1.0e-24) + y0;
    return std::max(0.0, value);
}


void eint_values(double t, double& e1, double& e2, double& e3) {
    if (!(t > 0.0)) { e1 = e2 = e3 = 0.0; return; }
    const double scaled = expint_scaled(t);
    e1 = scaled / std::max(1.0e-34, t * limited_exp(t));
    e2 = std::exp(-t) - t * e1;
    e3 = 0.5 * (limited_exp(-t) - t * e2);
}

double type57_szirc(int n, double temperature, double rz, double rno) {
    static const double abethe[11] = {1.134,0.603,0.412,0.313,0.252,0.211,0.181,0.159,0.142,0.128,1.307};
    static const double hbethe[11] = {1.48,3.64,5.93,8.32,10.75,12.90,15.05,17.20,19.35,21.50,2.15};
    static const double rbethe[11] = {2.20,1.90,1.73,1.65,1.60,1.56,1.54,1.52,1.52,1.52,1.52};
    if (n <= 0 || temperature <= 0.0 || rz <= 0.0 || rno <= 1.0) return 0.0;
    const double boltz = 1.38066e-16, eion = 2.179874e-11, con = 4.6513e-3;
    const double rc = static_cast<double>(static_cast<int>(rno));
    if (rc <= 1.0) return 0.0;
    double an, hn, rrn;
    if (n < 11) { an=abethe[n-1]; hn=hbethe[n-1]; rrn=rbethe[n-1]; }
    else { an=abethe[10]/n; hn=hbethe[10]*n; rrn=rbethe[10]; }
    const double tt = temperature * boltz, rn = static_cast<double>(n);
    const double yy = rz*rz*eion/tt*(1.0/(rn*rn)-1.0/(rc*rc)-0.25*(1.0/((rc-1.0)*(rc-1.0))-1.0/(rc*rc)));
    if (!(yy > 0.0)) return 0.0;
    double e1=0,e2=0,e3=0; eint_values(yy,e1,e2,e3);
    const double cii = con*std::sqrt(tt)*std::pow(rn,5.0)/std::pow(rz,4.0)*an*yy*(
        e1/rn - (std::exp(-yy)-yy*e3)/(3.0*rn) +
        (yy*e2-2.0*yy*e1+std::exp(-yy))*3.0*hn/rn/(3.0-rrn) +
        (e1-e2)*3.36*yy);
    return std::isfinite(cii) ? std::max(0.0, cii) : 0.0;
}

double type57_irc(int n, double temperature, double rc, double rno) {
    if (n <= 0 || temperature <= 0.0 || rc <= 0.0 || rno <= n) return 0.0;
    if (std::abs(rc-1.0) > 0.0) return type57_szirc(n, temperature, rc, rno);
    const double rn = static_cast<double>(n);
    const double xo = 1.0-rn*rn/(rno*rno);
    if (!(xo > 0.0)) return 0.0;
    const double yn = xo*157803.0/(temperature*rn*rn);
    if (!(yn > 0.0)) return 0.0;
    double an,bn,rp;
    if (n < 2) {
        an=1.9603*rn*(1.133/(3.0*std::pow(xo,3.0))-0.4059/(4.0*std::pow(xo,4.0))+0.07014/(5.0*std::pow(xo,5.0)));
        bn=2.0/3.0*rn*rn/xo*(3.0+2.0/xo-0.603/(xo*xo)); rp=0.45;
    } else if (n == 2) {
        an=1.9603*rn*(1.0785/(3.0*std::pow(xo,3.0))-0.2319/(4.0*std::pow(xo,4.0))+0.02947/(5.0*std::pow(xo,5.0)));
        bn=(4.0-18.63/rn+36.24/(rn*rn)-28.09/(rn*rn*rn))/rn;
        bn=2.0/3.0*rn*rn/xo*(3.0+2.0/xo+bn/(xo*xo)); rp=0.653;
    } else {
        const double g0=(0.9935+0.2328/rn-0.1296/(rn*rn))/(3.0*std::pow(xo,3.0));
        const double g1=-(0.6282-0.5598/rn+0.5299/(rn*rn))/(rn*4.0*std::pow(xo,4.0));
        const double g2=(0.3887-1.181/rn+1.470/(rn*rn))/(rn*rn*5.0*std::pow(xo,5.0));
        an=1.9603*rn*(g0+g1+g2);
        bn=(4.0-18.63/rn+36.24/(rn*rn)-28.09/(rn*rn*rn))/rn;
        bn=(3.0+2.0/xo+bn/(xo*xo))*2.0*rn*rn/(3.0*xo); rp=1.94*std::pow(rn,-1.57);
    }
    rp *= xo; const double zn=rp+yn;
    const double ey=expint_scaled(yn), ez=expint_scaled(zn);
    if (!(zn > 0.0)) return 0.0;
    double se=an*(ey/(yn*yn)-std::exp(-rp)*ez/(zn*zn));
    const double ey2=1.0+1.0/yn-ey*(2.0/yn+1.0);
    const double ez2=std::exp(-rp)*(1.0+1.0/zn-ez*(1.0/zn+1.0));
    se += (bn-an*std::log(2.0*rn*rn/xo))*(ey2-ez2);
    se *= std::sqrt(temperature)*yn*yn*rn*rn*1.095e-10/xo;
    return std::isfinite(se) ? std::max(0.0,se) : 0.0;
}

bool type57_coefficients(int n, double temperature, double density, double e1, double eth, double& cion, double& crec) {
    cion=crec=0.0;
    if (n<=0 || temperature<=0.0 || density<=0.0 || eth<e1) return true;
    const double rio=(eth-e1)/13.6;
    if (!(rio>0.0)) return true;
    const double rc=std::sqrt(rio)*n, den=std::min(density,1.0e18);
    const double tmin=3.8e4*rc*std::sqrt(rc), temp=std::max(temperature,tmin);
    double rno=std::sqrt(1.8887e8*rc/std::pow(den,0.3333));
    const double rno2=std::pow(1.814e26*std::pow(rc,6.0)/(2.0*den),0.13333);
    rno=std::min(rno,rno2);
    if (static_cast<int>(rno)<=n) return true;
    const double ciono=type57_irc(n,temp,rc,rno);
    if (!(ciono>0.0)) return true;
    if (temperature<tmin) {
        const double cb=13.605692*1.6021e-19/1.3805e-23;
        const double beta=0.25*(std::sqrt((100.0*rc+91.0)/(4.0*rc+3.0))-5.0);
        const double wte=std::pow(std::log(1.0+temperature/cb/rio),beta/(1.0+temperature/cb*rio));
        const double wtm=std::pow(std::log(1.0+tmin/cb/rio),beta/(1.0+tmin/cb*rio));
        double ete=0,e2=0,e3=0,etm=0; eint_values(rio/temperature*cb,ete,e2,e3); eint_values(rio/tmin*cb,etm,e2,e3);
        if (ete<1.0e-20) return true;
        cion=ciono*std::sqrt(tmin/temperature)*ete/(etm+1.0e-30)*wte/(wtm+1.0e-30);
    } else cion=ciono;
    if (cion<=1.0e-24) { cion=0.0; return true; }
    cion/=static_cast<double>(n*n);
    crec=cion*2.0779e-16*limited_exp(std::min((eth-e1)*1.16058e4/temperature,60.0))/std::pow(temperature,1.5);
    return std::isfinite(cion)&&std::isfinite(crec);
}

std::size_t bracket_index(const double* grid, std::size_t n, double x) {
    if (n < 2 || x <= grid[0]) return 0;
    for (std::size_t i=0;i+1<n;++i) if (x < grid[i+1]) return i;
    return n-2;
}

double bilinear_log_table(const double* dens, std::size_t nd, const double* temp, std::size_t nt, const double* table, double logn, double logt) {
    const std::size_t ni=bracket_index(dens,nd,logn), ti=bracket_index(temp,nt,logt);
    const double n0=dens[ni],n1=dens[ni+1],t0=temp[ti],t1=temp[ti+1];
    if (n1==n0||t1==t0) throw std::runtime_error("degenerate density/temperature grid");
    const auto at=[&](std::size_t i,std::size_t j){return table[i*nt+j];};
    const double r0=at(ni,ti)+(at(ni,ti+1)-at(ni,ti))*(logt-t0)/(t1-t0);
    const double r1=at(ni+1,ti)+(at(ni+1,ti+1)-at(ni+1,ti))*(logt-t0)/(t1-t0);
    return r0+(r1-r0)*(logn-n0)/(n1-n0);
}

bool type71_rate(const double* r, std::size_t nr, const std::int64_t* ints, std::size_t ni, double temperature, double density, double& aij, double& wavelength) {
    aij=wavelength=0.0;
    if (!r||!ints||ni<2||nr<4) return false;
    const int nd=static_cast<int>(ints[0]), nt=static_cast<int>(ints[1]);
    if (nd<=0||nt<=0) return false;
    if (nd==1&&nt==1) { const double dtmp=r[2]>30.0?std::log10(r[2]):r[2]; aij=std::pow(10.0,dtmp); wavelength=r[3]; return true; }
    const std::size_t need=static_cast<std::size_t>(nd+nt+nd*nt+1);
    if (nd<2||nt<2||nr<need||temperature<=0.0||density<=0.0) return false;
    double logn=std::log10(density), logt=std::log10(temperature);
    const double* dg=r; const double* tg=r+nd; const double* table=r+nd+nt;
    logn=std::min(logn,dg[nd-1]); logt=std::min(tg[nt-1]+1.0,std::max(tg[0]-1.0,logt));
    const double rec=bilinear_log_table(dg,nd,tg,nt,table,logn,logt);
    aij=std::pow(10.0,rec); wavelength=r[nd+nt+nd*nt]; return std::isfinite(aij)&&std::isfinite(wavelength);
}


double collision_pair_upward(double upsilon, double delta_ev, double temperature_k, double ne, double gl) {
    const double t4=temperature_k/1.0e4;
    return 8.626e-8*upsilon*limited_exp(-delta_ev/std::max(kBoltzmannEvK*temperature_k,1.0e-300))*ne/
        (std::sqrt(std::max(t4,1.0e-300))*std::max(gl,1.0e-300));
}

double collision_pair_downward(double upsilon, double temperature_k, double ne, double gu) {
    const double t4=temperature_k/1.0e4;
    return 8.626e-8*upsilon*ne/(std::sqrt(std::max(t4,1.0e-300))*std::max(gu,1.0e-300));
}

double callaway_upsilon(int data_type, const double* r, std::size_t nr, double temperature_k, double delta_ev) {
    const std::size_t min_count=data_type==60?3u:6u;
    if (!r||nr<min_count||!(temperature_k>0.0)||!(delta_ev>0.0)) throw std::runtime_error("invalid type60/62 payload");
    const double floor_k=0.02*delta_ev*1.0e4/0.8617333262145;
    const double teff=std::max(temperature_k,floor_k);
    const double t1=teff>1.0e9?6.33652e3:teff*6.33652e-6;
    const double tt=std::min(t1,1.0);
    double ups=0.0;
    if (data_type==60) {
        double power=1.0;
        for (std::size_t k=2;k<nr;++k) { ups+=r[k]*power; power*=tt; }
    } else {
        double power=1.0;
        for (std::size_t k=2;k+3<nr;++k) { ups+=r[k]*power; power*=tt; }
        const double arg=r[nr-2]*tt;
        if (!(arg>0.0)) throw std::runtime_error("type62 nonpositive log argument");
        ups+=r[nr-3]*std::log(arg)*limited_exp(-r[nr-1]*tt);
    }
    if (t1>tt) { const double l=std::log(t1); ups*=1.0+l/(l+1.0); }
    return ups;
}

double type68_upsilon(const double* r, std::size_t nr, int z, double temperature_k, double wavelength_a) {
    if (!r||nr<3||z<=0||!(temperature_k>0.0)||!(wavelength_a>0.0)) throw std::runtime_error("invalid type68 payload");
    const double floor_k=2.8777e6/wavelength_a;
    const double tused=std::max(temperature_k,floor_k);
    const double tt=std::log10(tused/std::pow(static_cast<double>(z),3.0));
    return std::max(0.0,r[0]+r[1]*tt+r[2]*tt*tt);
}

double type73_rate(const double* r, std::size_t nr, int z, double temperature_k) {
    if (!r||nr<7||z<=0||!(temperature_k>0.0)) throw std::runtime_error("invalid type73 payload");
    const double wav=std::abs(r[0]);
    if (!(wav>0.0)) return 0.0;
    const double tused=std::max(temperature_k,2.8777e6/wav);
    const double y=static_cast<double>(z*z)*r[0]*1.578876e5/tused;
    if (y>40.0||!(y>0.0)) return 0.0;
    const double z2s=r[1], aa=r[2], co=r[3], cr=r[4], cr1=r[5], rr=r[6];
    const double gam=z2s>=0.1?-0.2:(z2s>0.01?0.0:0.2);
    const double zeff=static_cast<double>(z)-gam;
    const double em1=expint_scaled(y);
    const double e1=em1/y*limited_exp(-y);
    double ee1=0.0,ee2=0.0,ee3=0.0;
    if (y*aa+y<=80.0) eint_values(y*aa+y,ee1,ee2,ee3);
    double er=0.0,er1=0.0;
    if (rr==1.0) { er=ee1; er1=ee2; }
    else if (rr==2.0) { er=ee2; er1=ee3; }
    double qij=co*limited_exp(-y)+1.55*z2s*e1;
    if (y*aa+y<=40.0) qij+=y*limited_exp(y*aa)*(cr*er/std::pow(aa+1.0,rr-1.0)+cr1*er1/std::pow(aa+1.0,rr));
    const double crate=qij*1.578876e5/tused*std::sqrt(tused)/std::max(zeff*zeff,1.0e-300)*5.46538e-11;
    return std::max(0.0,crate);
}

double type95_spline_rho(const double* r, std::size_t nr, double xx) {
    if (!r||nr<6) throw std::runtime_error("type95 payload too short");
    const std::size_t ns=(nr-2)/2;
    if (ns<2||2+2*ns>nr) throw std::runtime_error("type95 bad spline layout");
    std::size_t mm=1;
    while (mm<ns && xx>r[1+mm]) ++mm;
    const std::size_t ly=ns+mm, ry=1+ns+mm, lx=mm, rx=1+mm;
    if (ry>=nr||rx>=nr) throw std::runtime_error("type95 spline index out of range");
    const double denom=r[rx]-r[lx];
    if (denom==0.0) throw std::runtime_error("type95 zero spline interval");
    return r[ly]+(xx-r[lx])*(r[ry]-r[ly])/denom;
}

bool type77_rates(const double* r, std::size_t nr, const std::int64_t* ints, std::size_t ni, double temperature, double density, double endpoint_delta_ev, double& upward, double& downward) {
    upward=downward=0.0;
    if (!r||!ints||ni<3) return false;
    const int nd=static_cast<int>(ints[0]), nt=static_cast<int>(ints[1]), nll=static_cast<int>(ints[2]);
    const std::size_t need=static_cast<std::size_t>(nd+nt+nd*nt+1);
    if (nd<2||nt<2||nr<need||temperature<=0.0||density<=0.0) return false;
    const double* dg=r; const double* tg=r+nd; const double* table=r+nd+nt; const double wav=r[nd+nt+nd*nt];
    if (!(wav>0.0)) return false;
    const double floor_wav=endpoint_delta_ev>0.0?12398.4016/endpoint_delta_ev:wav;
    const double tused=std::max(temperature,2.8777e6/floor_wav);
    double logn=std::min(std::log10(density),dg[nd-1]);
    double logt=std::min(tg[nt-1]+1.0,std::max(tg[0]-1.0,std::log10(tused)));
    const double rec=bilinear_log_table(dg,nd,tg,nt,table,logn,logt);
    downward=std::pow(10.0,rec);
    int k=1; while (nll >= (k+1)*k/2+1 && k<10000) ++k;
    const int nl1=k*(k-1)/2+1, il=nll-nl1; const double gg=2.0*(2.0*il+1.0);
    const double xt=1.43817e8/(wav*tused);
    upward=(xt<100.0&&gg>0.0)?downward*std::exp(-xt)/gg:0.0;
    return std::isfinite(upward)&&std::isfinite(downward);
}

const ElementRow& row_at(const ElementProgram& element, int one_based) {
    if (one_based < 1 || one_based > element.n_rows) throw std::runtime_error("row index outside element");
    return element.rows[static_cast<std::size_t>(one_based - 1)];
}

bool evaluate_type53_source_integral(
    const double* payload,
    std::size_t real_count,
    const ElementRow& lower,
    const ElementRow& upper,
    const xstar_fixed_state_input_v1& input,
    double threshold_ev,
    double ptmp_sum,
    const xstar_type53_row46_dsec_runtime_oracle_v048716::Entry* row46_contract,
    xstar_element_contribution_v1& contribution,
    Type53SourceShadow* shadow
) {
    if (!payload || real_count < 4 || real_count % 2 != 0) return false;
    const bool has_dsec_radiation = input.dsec_radiation_energy_ev && input.dsec_bremsa && input.dsec_radiation_bin_count >= 3;
    const double* source_energy_ev = has_dsec_radiation ? input.dsec_radiation_energy_ev : input.radiation_energy_ev;
    const double* source_bremsa = has_dsec_radiation ? input.dsec_bremsa : input.radiation_flux;
    const std::size_t source_bin_count = has_dsec_radiation ? input.dsec_radiation_bin_count : input.radiation_bin_count;
    if (!source_energy_ev || !source_bremsa || source_bin_count < 3) return false;
    if (!(input.temperature_k > 0.0) || !(input.electron_density_cm3 >= 0.0)) return false;

    const int n_grid = static_cast<int>(source_bin_count);
    const int pair_count = static_cast<int>(real_count / 2);
    const int numcon2 = std::max(2, n_grid / 50);
    const int usable_grid = n_grid - numcon2;
    if (pair_count < 2 || usable_grid < 2) return false;

    std::vector<double> xs(static_cast<std::size_t>(pair_count), 0.0);
    std::vector<double> ys(static_cast<std::size_t>(pair_count), 0.0);
    for (int j = 0; j < pair_count; ++j) {
        xs[static_cast<std::size_t>(j)] = threshold_ev + payload[2 * j] * kType53RydEv;
        ys[static_cast<std::size_t>(j)] = std::max(0.0, payload[2 * j + 1]);
    }

    const auto lower_bracket = [&](double energy) -> int {
        if (energy <= source_energy_ev[0]) return 0;
        int lo = 0;
        int hi = usable_grid - 1;
        while (lo + 1 < hi) {
            const int mid = (lo + hi) / 2;
            if (source_energy_ev[mid] <= energy) lo = mid;
            else hi = mid;
        }
        return source_energy_ev[hi] <= energy ? hi : lo;
    };

    const int nb1 = lower_bracket(xs[0]);
    if (nb1 + 1 >= usable_grid) return false;
    std::vector<double> sgbar(static_cast<std::size_t>(n_grid), 0.0);
    sgbar[static_cast<std::size_t>(std::max(0, nb1 - 1))] = 0.0;
    sgbar[static_cast<std::size_t>(nb1)] = 0.0;

    int k = nb1;
    int j = 0;
    double egrid = source_energy_ev[k];
    double e2 = xs[0];
    double s2 = ys[0];
    if (egrid < e2 && k + 1 < n_grid) {
        ++k;
        egrid = source_energy_ev[k];
    }
    double e1o = e2;
    double e2o = e2;
    double s2o = s2;
    double s2t = s2;
    double e2t = egrid;
    double integral = 0.0;
    bool done = false;
    int iterations = 0;
    const int max_iterations = std::max(8, 4 * (n_grid + pair_count));
    while (!done && iterations < max_iterations && k < n_grid) {
        ++iterations;
        bool advanced = false;
        while (e2 < egrid && j < pair_count - 2) {
            ++j;
            e2o = e2;
            s2o = s2;
            e2 = xs[static_cast<std::size_t>(j)];
            s2 = ys[static_cast<std::size_t>(j)];
            integral += (s2 + s2o) * (e2 - e2o) / 2.0;
            advanced = true;
        }
        if (!advanced && iterations == 1) {
            e2o = e2;
            s2o = s2;
        }
        integral -= (s2 + s2o) * (e2 - e2o) / 2.0;
        e2t = egrid;
        s2t = (e2 - e2o > 1.0e-8)
            ? s2o + (s2 - s2o) * (e2t - e2o) / (e2 - e2o + 1.0e-24)
            : s2o;
        integral += (s2t + s2o) * (e2t - e2o) / 2.0;
        const double denom = egrid - e1o;
        sgbar[static_cast<std::size_t>(k)] = std::abs(denom) > 1.0e-36 ? integral / denom : 0.0;
        e1o = egrid;
        ++k;
        if (k >= n_grid) break;
        egrid = source_energy_ev[k];
        while (egrid < e2 && k < n_grid - 1) {
            e2t = egrid;
            s2t = (e2 - e2o > 1.0e-8)
                ? s2o + (s2 - s2o) * (e2t - e2o) / (e2 - e2o)
                : s2o;
            integral = s2t * (egrid - e1o);
            const double local_denom = egrid - e1o;
            sgbar[static_cast<std::size_t>(k)] = std::abs(local_denom) > 1.0e-36 ? integral / local_denom : 0.0;
            e1o = egrid;
            ++k;
            if (k >= n_grid) break;
            egrid = source_energy_ev[k];
        }
        integral = (s2 + s2t) * (e2 - e2t) / 2.0;
        if (k >= usable_grid - 1 || j >= pair_count - 2) done = true;
    }

    const int klmax = std::max(nb1, k - 1);
    if (iterations >= max_iterations || nb1 >= klmax || nb1 >= n_grid) return false;

    constexpr double kBoltzmannErgK = 1.380649e-16;
    constexpr double kKtEvPerT4 = 0.861707;
    const double t4 = input.temperature_k / 1.0e4;
    const double q2 = 2.07e-16 * input.electron_density_cm3 * std::pow(input.temperature_k, -1.5);
    const double bound_g = row46_contract ? row46_contract->bound_statistical_weight : lower.statistical_weight;
    const double continuum_g = std::max(row46_contract ? row46_contract->continuum_statistical_weight : upper.statistical_weight, 1.0e-300);
    const double rnissel = bound_g * q2 / continuum_g;
    const double continuum_energy = row46_contract ? row46_contract->destination_energy_ev : upper.energy_ev;
    const double ethtmp = std::max(0.0, threshold_ev - continuum_energy);
    const double exponent_energy = std::max(0.0, ethtmp + kType53RydEv * payload[0]);
    const double rnist = rnissel * type53_expo(-exponent_energy / kKtEvPerT4 / std::max(t4, 1.0e-300));
    const double bktm = kBoltzmannErgK * input.temperature_k / kErgPerEv;
    if (!(bktm > 0.0)) return false;

    double sumr = 0.0;
    double sumh = 0.0;
    double sumh2 = 0.0;
    double sumi = 0.0;
    double sumc = 0.0;
    double sumc2 = 0.0;
    double sgtpp = sgbar[static_cast<std::size_t>(nb1)];
    double bremtmpp = source_bremsa[nb1] / 12.56;
    double epiip = source_energy_ev[nb1];
    double temprp = epiip != 0.0 ? 12.56 * sgtpp * bremtmpp / epiip : 0.0;
    double temphp = temprp * epiip;
    double temphp2 = temprp * (epiip - threshold_ev);
    double exptst = (epiip - threshold_ev) / bktm;
    double exptmpp = type53_expo(-exptst);
    double bbnurjp = std::pow(std::min(2.0e4, epiip), 3.0) * 1.571e22 * 2.0;
    double tempip = epiip != 0.0 ? rnist * bbnurjp * sgtpp * exptmpp / epiip * ptmp_sum : 0.0;
    double tempcp = tempip * epiip;
    double tempcp2 = tempip * (epiip - threshold_ev);
    int kl = nb1;
    while (kl < klmax && kl + 1 < n_grid) {
        sgtpp = sgbar[static_cast<std::size_t>(kl + 1)];
        bremtmpp = source_bremsa[kl + 1] / 12.56;
        const double epii = source_energy_ev[kl];
        epiip = source_energy_ev[kl + 1];
        const double tempr = temprp;
        temprp = epiip != 0.0 ? 12.56 * sgtpp * bremtmpp / epiip : 0.0;
        const double width = (epiip - epii) / 2.0;
        sumr += tempr * width + temprp * width;
        const double temph = temphp;
        const double temph2 = temphp2;
        temphp = temprp * epiip;
        temphp2 = temprp * (epiip - threshold_ev);
        sumh += temph * width + temphp * width;
        sumh2 += temph2 * width + temphp2 * width;
        const double previous_exptst = exptst;
        exptst = (epiip - threshold_ev) / bktm;
        if (previous_exptst < 200.0) {
            exptmpp = type53_expo(-exptst);
            bbnurjp = std::pow(std::min(2.0e4, epiip), 3.0) * 1.571e22 * 2.0;
            const double tempi = tempip;
            tempip = epiip != 0.0 ? rnist * bbnurjp * sgtpp * exptmpp * 12.56 / epiip * ptmp_sum : 0.0;
            sumi += tempi * width + tempip * width;
            const double tempc = tempcp;
            const double tempc2 = tempcp2;
            tempcp = tempip * epiip;
            tempcp2 = tempip * (epiip - threshold_ev);
            sumc += tempc * width + tempcp * width;
            sumc2 += tempc2 * width + tempcp2 * width;
        }
        ++kl;
    }

    contribution.ans1 = sumr;
    contribution.ans2 = sumi;
    contribution.ans3 = -sumc * kErgPerEv;
    contribution.ans4 = -sumh * kErgPerEv;
    contribution.ans5 = -sumc2 * kErgPerEv;
    contribution.ans6 = -sumh2 * kErgPerEv;
    const double destination_energy = row46_contract ? row46_contract->destination_energy_ev : upper.energy_ev;
    const double bound_energy = row46_contract ? row46_contract->bound_energy_ev : lower.energy_ev;
    const double energy_difference = std::abs(destination_energy - bound_energy);
    const double den6 = std::max(1.0e-43, std::abs(contribution.ans4) - threshold_ev * kErgPerEv * contribution.ans1);
    const double den5 = std::max(1.0e-43, std::abs(contribution.ans3) - threshold_ev * kErgPerEv * contribution.ans2);
    contribution.ans6 *= (std::abs(contribution.ans4) - energy_difference * kErgPerEv * contribution.ans1) / den6;
    contribution.ans5 *= (std::abs(contribution.ans3) - energy_difference * kErgPerEv * contribution.ans2) / den5;
    const bool valid = std::isfinite(contribution.ans1) && std::isfinite(contribution.ans2) &&
        std::isfinite(contribution.ans3) && std::isfinite(contribution.ans4) &&
        std::isfinite(contribution.ans5) && std::isfinite(contribution.ans6);
    if (valid && shadow) {
        shadow->valid = true;
        shadow->ans = {contribution.ans1, contribution.ans2, contribution.ans3,
                       contribution.ans4, contribution.ans5, contribution.ans6};
        shadow->threshold_ev = threshold_ev;
        shadow->rnist = rnist;
        shadow->sumr = sumr;
        shadow->sumi = sumi;
        shadow->sumh = sumh;
        shadow->sumh2 = sumh2;
        shadow->sumc = sumc;
        shadow->sumc2 = sumc2;
        shadow->nb1_one_based = nb1 + 1;
        shadow->klmax_one_based = klmax + 1;
        shadow->row46_contract = row46_contract != nullptr;
    }
    return valid;
}

EvaluatedRecord evaluate_record(
    const Program& program,
    const ElementProgram& element,
    const ProgramRecord& record,
    const xstar_fixed_state_input_v1& input
) {
    const double* r = record.real_count ? program.reals.data() + record.real_offset : nullptr;
    const auto* ints = record.int_count ? program.ints.data() + record.int_offset : nullptr;
    const ElementRow scalar_dummy{};
    const ElementRow& lower = record.matrix_enabled ? row_at(element, record.lower_row) : scalar_dummy;
    const ElementRow& upper = record.matrix_enabled ? row_at(element, record.upper_row) : scalar_dummy;
    const double delta_ev = record.line_energy_ev > 0.0 ? record.line_energy_ev : (record.matrix_enabled ? std::abs(upper.energy_ev - lower.energy_ev) : 0.0);
    const double ne = input.electron_density_cm3;
    const double t4 = input.temperature_k / 1.0e4;
    const double sqrt_t4 = std::sqrt(std::max(t4, 1.0e-300));
    const double kt_ev = kBoltzmannEvK * input.temperature_k;
    EvaluatedRecord out;
    auto& c = out.contribution;
    c.source_position = record.source_position;
    c.record = record.record;
    c.data_type = record.data_type;
    c.rate_type = record.rate_type;
    c.ion_index = record.ion_index;
    c.ion_stage = record.ion_stage;
    c.lower_row = record.lower_row;
    c.upper_row = record.upper_row;
    c.density_scale = record.density_scale;
    out.matrix_enabled = record.matrix_enabled;

    switch (record.opcode) {
        case XSTAR_FIXED_OPCODE_SIMPLE_UCALC: {
            if (!r || record.real_count < 1) throw std::runtime_error("simple ucalc payload too short");
            if (record.data_type == 1) {
                const double eta = record.real_count > 1 ? r[1] : 0.0;
                c.ans1 = r[0] / std::pow(std::max(t4, 1.0e-300), eta) * ne;
            } else if (record.data_type == 2) {
                if (record.real_count < 4) throw std::runtime_error("type2 payload too short");
                if (t4 <= 5.0) {
                    const double rate = r[0] * std::pow(t4, r[1]) * std::max(0.0, 1.0 + r[2] * limited_exp(r[3] * t4)) * 1.0e-9;
                    if (record.rate_type == 5) c.ans2 = rate * input.neutral_h_density_cm3;
                    else c.ans1 = rate * input.neutral_h_density_cm3;
                }
            } else if (record.data_type == 3) {
                if (record.real_count < 2) throw std::runtime_error("type3 payload too short");
                c.ans1 = r[0] * limited_exp(-r[1] / std::max(kt_ev, 1.0e-300)) / sqrt_t4 * ne;
            } else if (record.data_type == 7) {
                if (record.real_count < 4) throw std::runtime_error("type7 payload too short");
                const double rate = r[0] * 1.0e-6 * limited_exp(-r[2] / t4) * (1.0 + r[1] * limited_exp(-r[3] / t4)) / (t4 * sqrt_t4);
                c.ans1 = rate * ne;
            } else if (record.data_type == 8) {
                if (record.real_count < 8) throw std::runtime_error("type8 payload too short");
                double rate = 0.0;
                for (int k = 0; k < 4; ++k) rate += r[k] * limited_exp(-r[k + 4] / std::max(kt_ev, 1.0e-300));
                c.ans1 = rate * 1.0e-6 * std::pow(t4, -1.5) * ne;
            } else if (record.data_type == 20) {
                if (record.real_count < 5) throw std::runtime_error("type20 payload too short");
                const double rate = r[0] * std::pow(t4, r[1]) * (1.0 + r[2] * limited_exp(r[3] * t4)) * limited_exp(-r[4] / t4) * 1.0e-9;
                c.ans1 = rate * input.ionized_h_density_cm3;
            } else {
                throw std::runtime_error("unsupported SIMPLE_UCALC data_type " + std::to_string(record.data_type));
            }
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE2_CHARGE_TRANSFER: {
            if (!r||record.real_count<4) throw std::runtime_error("type2 payload too short");
            if (t4<=5.0) {
                const double rate=r[0]*std::pow(t4,r[1])*std::max(0.0,1.0+r[2]*limited_exp(r[3]*t4))*1.0e-9;
                if (record.rate_type==5) c.ans2=rate*input.neutral_h_density_cm3;
                else c.ans1=rate*input.neutral_h_density_cm3;
            }
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE9_CHARGE_TRANSFER: {
            if (!r||record.real_count<4||!ints||record.int_count<1) throw std::runtime_error("type9 payload too short");
            const double rate=r[0]*std::pow(std::min(t4,1000.0),r[1])*(1.0+r[2]*limited_exp(r[3]*t4))*1.0e-9;
            c.ans2=rate*input.neutral_h_density_cm3*0.1;
            if (ints[0]!=0) c.ans2/=6.0;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE30_THREE_BODY_RECOMB: {
            if (!ints||record.int_count<1) throw std::runtime_error("type30 payload too short");
            const double t6=t4/100.0;
            const double nmx=static_cast<double>(ints[0]);
            const double yy=nmx*nmx/std::max(6.34*t6,1.0e-300);
            const double vth=3.10782e7*std::sqrt(std::max(t4,0.0));
            const double ypow=std::min(1.0,0.06376/std::max(yy*yy,1.0e-300));
            const double fudge=0.9*(1.0-ypow)+(1.0/1.5)*ypow;
            const double phi1=(1.735+std::log(yy)+1.0/(6.0*yy))*fudge/2.0;
            const double phi2=yy*(-1.202*std::log(yy)-0.298);
            c.ans1=2.0*2.105e-22*vth*yy*(yy<0.2525?phi2:phi1)*ne;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE38_RR_FIT: {
            if (!r||record.real_count<4) throw std::runtime_error("type38 payload too short");
            double b=r[1];
            const double t0=r[2]/1.0e4, t1=r[3]/1.0e4;
            if (record.real_count>5) b+=r[4]*limited_exp(-(r[5]/1.0e4)/t4);
            const double s0=std::sqrt(t4/std::max(t0,1.0e-300));
            const double s1=std::sqrt(t4/std::max(t1,1.0e-300));
            const double rate=r[0]/(1.0e-48+s0*std::pow(1.0+s0,1.0-b)*std::pow(1.0+s1,1.0+b));
            c.ans1=rate*ne;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE39_DR_FIT: {
            if (!r||record.real_count<2||record.real_count%2!=0) throw std::runtime_error("type39 payload invalid");
            const std::size_t n=record.real_count/2;
            double rate=0.0;
            for (std::size_t k=0;k<n;++k) rate+=r[k]*limited_exp(-(r[k+n]/1.0e4)/t4);
            c.ans1=rate*1.0e-6*std::pow(t4,-1.5)*ne;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE53_BOUND_FREE: {
            if (!r || record.real_count < 4 || record.real_count % 2 != 0) throw std::runtime_error("bound-free payload requires energy/sigma pairs");
            if (!input.radiation_energy_ev || !input.radiation_flux || input.radiation_bin_count < 2) throw std::runtime_error("bound-free record requires live radiation grid");
            const std::size_t n = record.real_count / 2;
            const double threshold = std::max(delta_ev, 1.0e-12);
            double photo = 0.0;
            double heat = 0.0;
            for (std::size_t k = 0; k < n; ++k) {
                const double e = threshold + r[2 * k] * kRydEv;
                const double sigma = std::max(0.0, r[2 * k + 1]);
                const double flux = interp_linear(input.radiation_energy_ev, input.radiation_flux, input.radiation_bin_count, e);
                photo += flux * sigma;
                heat += flux * sigma * std::max(0.0, e - threshold) * kErgPerEv;
            }
            photo /= static_cast<double>(n);
            heat /= static_cast<double>(n);
            const double ratio = lower.statistical_weight / std::max(upper.statistical_weight, 1.0e-300);
            const double recomb = 2.08e-22 * ratio * ne / std::max(t4 * sqrt_t4, 1.0e-300) * limited_exp(threshold / std::max(kt_ev, 1.0e-300)) * std::max(photo, 1.0e-60);
            c.ans1 = photo;
            c.ans2 = recomb;
            c.ans3 = -recomb * threshold * kErgPerEv;
            c.ans4 = -heat;
            c.ans5 = recomb * threshold * kErgPerEv;
            c.ans6 = heat;
            const bool use_row46_contract =
                environment_flag("XSTAR_QUALIFICATION_TYPE53_ROW46_COUPLED_REPLACEMENT") ||
                environment_flag("XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION");
            const auto* row46_contract = use_row46_contract
                ? find_type53_row46_dsec_runtime_oracle_entry(record.source_position, record.record)
                : nullptr;
            double contract_ptmp1 = 1.0;
            double contract_ptmp2 = 0.0;
            bool captured_state_anchor = false;
            double contract_tau_in = 0.0;
            double contract_tau_out = 0.0;
            double contract_covering = input.covering_fraction;
            if (row46_contract) {
                if (element.element_z != 2 || record.data_type != 53 || record.rate_type != 7 ||
                    record.lower_row != row46_contract->lower_row || record.upper_row != row46_contract->upper_row) {
                    throw std::runtime_error("type53 row46 coupled replacement identity mismatch");
                }
                captured_state_anchor =
                    input.temperature_k == xstar_type53_row46_dsec_runtime_oracle_v048716::kTemperatureK &&
                    input.hydrogen_density_cm3 == xstar_type53_row46_dsec_runtime_oracle_v048716::kHydrogenDensityCm3 &&
                    input.electron_fraction_xee == xstar_type53_row46_dsec_runtime_oracle_v048716::kElectronFractionXee;
                if (captured_state_anchor) {
                    contract_tau_in = row46_contract->tau_in;
                    contract_tau_out = row46_contract->tau_out;
                    contract_ptmp1 = row46_contract->ptmp1;
                    contract_ptmp2 = row46_contract->ptmp2;
                    contract_covering = row46_contract->covering_fraction;
                } else {
                    const int continuum_index = row46_contract->continuum_index_one_based;
                    const bool has_continuum_workspace = continuum_index > 0 &&
                        input.continuum_tau_in && input.continuum_tau_out &&
                        static_cast<std::size_t>(continuum_index) <= input.continuum_tau_count;
                    if (has_continuum_workspace) {
                        contract_tau_in = std::max(0.0, input.continuum_tau_in[continuum_index - 1]);
                        contract_tau_out = std::max(0.0, input.continuum_tau_out[continuum_index - 1]);
                    } else {
                        const double reference_population = row46_contract->captured_initial_lower_population;
                        const double population_scale = reference_population > 0.0
                            ? std::max(0.0, lower.initial_population) / reference_population : 1.0;
                        contract_tau_in = std::max(0.0, row46_contract->tau_in * population_scale);
                        contract_tau_out = std::max(0.0, row46_contract->tau_out * population_scale);
                    }
                    const bool has_dsec_covering =
                        (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION) != 0u;
                    const double cfrac = std::clamp(
                        has_dsec_covering ? input.dsec_covering_fraction : input.covering_fraction, 0.0, 1.0);
                    const auto pescv = [](double tau) { return std::max(std::exp(-tau), 1.0e-12) / 2.0; };
                    contract_ptmp1 = pescv(contract_tau_in) * (1.0 - cfrac);
                    contract_ptmp2 = pescv(contract_tau_out) * (1.0 - cfrac) +
                        2.0 * pescv(contract_tau_in + contract_tau_out) * cfrac;
                    contract_covering = cfrac;
                }
            }
            const double source_threshold = row46_contract ? row46_contract->threshold_ev : threshold;
            xstar_element_contribution_v1 source_shadow{};
            const bool source_exact = evaluate_type53_source_integral(
                r, record.real_count, lower, upper, input, source_threshold,
                contract_ptmp1 + contract_ptmp2, row46_contract, source_shadow, &out.type53_shadow);
            if (row46_contract) {
                if (!source_exact) throw std::runtime_error("type53 row46 source-faithful evaluator did not produce a result");
                if (captured_state_anchor) {
                    c.ans1 = row46_contract->ans[0];
                    c.ans2 = row46_contract->ans[1];
                    c.ans3 = row46_contract->ans[2];
                    c.ans4 = row46_contract->ans[3];
                    c.ans5 = row46_contract->ans[4];
                    c.ans6 = row46_contract->ans[5];
                } else {
                    c.ans1 = source_shadow.ans1;
                    c.ans2 = source_shadow.ans2;
                    c.ans3 = source_shadow.ans3;
                    c.ans4 = source_shadow.ans4;
                    c.ans5 = source_shadow.ans5;
                    c.ans6 = source_shadow.ans6;
                }
                c.density_scale = input.hydrogen_density_cm3;
                out.type53_shadow.captured_state_anchor = captured_state_anchor;
                out.type53_shadow.tau_in = contract_tau_in;
                out.type53_shadow.tau_out = contract_tau_out;
                out.type53_shadow.ptmp1 = contract_ptmp1;
                out.type53_shadow.ptmp2 = contract_ptmp2;
                out.type53_shadow.covering_fraction = contract_covering;
                out.type53_shadow.runtime_state_abi_used =
                    input.dsec_radiation_energy_ev && input.dsec_bremsa &&
                    input.dsec_radiation_bin_count >= 3 && input.continuum_tau_in &&
                    input.continuum_tau_out && row46_contract->continuum_index_one_based > 0 &&
                    static_cast<std::size_t>(row46_contract->continuum_index_one_based) <= input.continuum_tau_count;
                out.type53_shadow.continuum_index_one_based = row46_contract->continuum_index_one_based;
                out.type53_shadow.dsec_radiation_bin_count = input.dsec_radiation_bin_count;
                out.type53_shadow.continuum_tau_count = input.continuum_tau_count;
            } else if (source_exact && element.element_z == 2 && record.ion_stage == 2) {
                c.ans1 = source_shadow.ans1;
                c.ans2 = source_shadow.ans2;
                c.ans3 = source_shadow.ans3;
                c.ans4 = source_shadow.ans4;
                c.ans5 = source_shadow.ans5;
                c.ans6 = source_shadow.ans6;
            }
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE: {
            if (!r || record.real_count < 4 || record.real_count % 2 != 0) throw std::runtime_error("bound-free payload requires energy/sigma pairs");
            if (!input.radiation_energy_ev || !input.radiation_flux || input.radiation_bin_count < 2) throw std::runtime_error("bound-free record requires live radiation grid");
            const std::size_t n = record.real_count / 2;
            const double threshold = std::max(delta_ev, 1.0e-12);
            double photo = 0.0;
            double heat = 0.0;
            for (std::size_t k = 0; k < n; ++k) {
                const double e = threshold + r[2 * k] * kRydEv;
                const double sigma = std::max(0.0, r[2 * k + 1]);
                const double flux = interp_linear(input.radiation_energy_ev, input.radiation_flux, input.radiation_bin_count, e);
                photo += flux * sigma;
                heat += flux * sigma * std::max(0.0, e - threshold) * kErgPerEv;
            }
            photo /= static_cast<double>(n);
            heat /= static_cast<double>(n);
            const double ratio = lower.statistical_weight / std::max(upper.statistical_weight, 1.0e-300);
            const double recomb = 2.08e-22 * ratio * ne / std::max(t4 * sqrt_t4, 1.0e-300) * limited_exp(threshold / std::max(kt_ev, 1.0e-300)) * std::max(photo, 1.0e-60);
            c.ans1 = photo;
            c.ans2 = recomb;
            c.ans3 = -recomb * threshold * kErgPerEv;
            c.ans4 = -heat;
            c.ans5 = recomb * threshold * kErgPerEv;
            c.ans6 = heat;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE50_RADIATIVE_LINE: {
            if (!r || record.real_count < 2) throw std::runtime_error("radiative line payload requires A and oscillator strength");
            const double a = std::max(0.0, r[0]);
            const double oscillator = std::max(0.0, r[1]);
            const double flux = input.radiation_bin_count > 0 ? interp_linear(input.radiation_energy_ev, input.radiation_flux, input.radiation_bin_count, delta_ev) : 0.0;
            c.ans1 = oscillator * flux * 1.0e-18 * std::max(0.0, 1.0 - input.covering_fraction);
            c.ans2 = a;
            c.ans3 = c.ans2 * delta_ev * kErgPerEv;
            c.ans4 = c.ans1 * delta_ev * kErgPerEv;
            const bool use_fixed_type50_oracle = environment_flag("XSTAR_QUALIFICATION_TYPE50_MANIFOLD_ORACLE");
            const bool use_dsec_type50_oracle = environment_flag("XSTAR_QUALIFICATION_TYPE50_DSEC_RUNTIME_ORACLE");
            if (use_fixed_type50_oracle && use_dsec_type50_oracle) {
                throw std::runtime_error("type50 fixed-evaluator and DSEC runtime oracle gates are mutually exclusive");
            }
            if (use_dsec_type50_oracle) {
                if (!environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
                    throw std::runtime_error("type50 DSEC runtime oracle replacement requires XSTAR_QUALIFICATION_REPLACEMENT=1");
                }
                const auto* oracle = find_type50_dsec_runtime_oracle_entry(record.source_position, record.record);
                if (oracle) {
                    if (input.temperature_k != xstar_type50_dsec_runtime_oracle_v048713::kTemperatureK ||
                        input.hydrogen_density_cm3 != xstar_type50_dsec_runtime_oracle_v048713::kHydrogenDensityCm3 ||
                        input.electron_fraction_xee != xstar_type50_dsec_runtime_oracle_v048713::kElectronFractionXee) {
                        throw std::runtime_error("type50 DSEC runtime oracle replacement is restricted to the captured evaluation-61 state");
                    }
                    if (record.data_type != 50 || record.ion_stage != 2 ||
                        record.lower_row != oracle->lower_row || record.upper_row != oracle->upper_row) {
                        throw std::runtime_error("type50 DSEC runtime oracle identity mismatch");
                    }
                    c.ans1 = oracle->ans[0];
                    c.ans2 = oracle->ans[1];
                    c.ans3 = oracle->ans[2];
                    c.ans4 = oracle->ans[3];
                    c.ans5 = oracle->ans[4];
                    c.ans6 = oracle->ans[5];
                    // The original DSEC ucalc path commits the type-50 thermal
                    // channels with the hydrogen-density multiplier.  The
                    // fixed evaluator replay did not include this live matrix
                    // contract.
                    c.density_scale = input.hydrogen_density_cm3;
                }
            } else if (use_fixed_type50_oracle) {
                if (!environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
                    throw std::runtime_error("type50 manifold oracle replacement requires XSTAR_QUALIFICATION_REPLACEMENT=1");
                }
                const auto* oracle = find_type50_manifold_oracle_entry(record.source_position, record.record);
                if (oracle) {
                    if (input.temperature_k != xstar_type50_manifold_oracle_v048710::kTemperatureK ||
                        input.hydrogen_density_cm3 != xstar_type50_manifold_oracle_v048710::kHydrogenDensityCm3) {
                        throw std::runtime_error("type50 manifold oracle replacement is restricted to the evaluation-61 fixed state");
                    }
                    if (record.data_type != 50 || record.ion_stage != 2 ||
                        record.lower_row != oracle->lower_row || record.upper_row != oracle->upper_row) {
                        throw std::runtime_error("type50 manifold oracle identity mismatch");
                    }
                    c.ans1 = oracle->ans[0];
                    c.ans2 = oracle->ans[1];
                    c.ans3 = oracle->ans[2];
                    c.ans4 = oracle->ans[3];
                    c.ans5 = oracle->ans[4];
                    c.ans6 = oracle->ans[5];
                }
            }
            const double wavelength_a = delta_ev > 0.0 ? 12398.4016 / delta_ev : 0.0;
            const double mass = record.atomic_mass_amu > 0.0 ? record.atomic_mass_amu : 1.0;
            const double thermal_velocity = 1.29e6 / std::sqrt(std::max(mass / std::max(t4, 1.0e-300), 1.0e-300));
            const double v = std::sqrt(std::pow(input.turbulent_velocity_km_s * 1.0e5, 2) + thermal_velocity * thermal_velocity);
            out.opakab = v > 0.0 ? 0.02655 * oscillator * wavelength_a * 1.0e-8 / v : 0.0;
            out.spectral = true;
            out.line_energy_ev = delta_ev;
            out.atomic_mass_amu = mass;
            out.natural_width_ev = record.natural_width_ev;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE51_BT_COLLISION: {
            const double ups = type51_upsilon(r, record.real_count, ints, record.int_count, input.temperature_k);
            if (!(ups >= 0.0)) throw std::runtime_error("invalid type51 payload");
            const double qde = 8.626e-8 * ups / sqrt_t4 / std::max(upper.statistical_weight, 1.0e-300);
            const double qex = qde * upper.statistical_weight / std::max(lower.statistical_weight, 1.0e-300) * limited_exp(-delta_ev / std::max(kt_ev, 1.0e-300));
            c.ans1 = qex * ne;
            c.ans2 = qde * ne;
            c.ans5 = c.ans2 * delta_ev * kErgPerEv;
            c.ans6 = c.ans1 * delta_ev * kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE54_ANGULAR_REDIS: {
            if (!ints || record.int_count < 5) throw std::runtime_error("type54 payload requires ni,nf,li,lf,iq");
            const int ni0=static_cast<int>(ints[0]), nf0=static_cast<int>(ints[1]);
            const int li=static_cast<int>(ints[2]), lf=static_cast<int>(ints[3]), iq=static_cast<int>(ints[4]);
            if (ni0 == nf0) break;
            double alm=0.0, alp=0.0;
            if (xstar_engine_anl1_v1(ni0,nf0,lf,iq,&alm,&alp)!=0) throw std::runtime_error("type54 anl1 evaluation failed");
            const double rate = li < lf ? alm : alp;
            c.ans2 = rate;
            const double delt = delta_ev / std::max(kt_ev,1.0e-300);
            c.ans3 = -rate*delt*kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE57_COLLISIONAL_IONIZATION: {
            if (!ints || record.int_count < 2) throw std::runtime_error("type57 payload requires i57,principal_n");
            const int i57=static_cast<int>(ints[0]);
            const int n=static_cast<int>(ints[1]);
            if (i57<=0 || record.lower_row<=1) break;
            const double e1=lower.energy_ev;
            const double eth=std::max(upper.energy_ev-e1,0.0);
            double cion=0.0,crec=0.0;
            if (!type57_coefficients(n,input.temperature_k,ne,e1,eth,cion,crec)) throw std::runtime_error("type57 coefficient evaluation failed");
            c.ans1=cion*ne;
            c.ans2=crec*(lower.statistical_weight/std::max(upper.statistical_weight,1.0e-300))*ne*ne;
            c.ans5=-c.ans2*eth*kErgPerEv;
            c.ans6=-c.ans1*eth*kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE56_TABULATED_COLLISION: {
            const double ups = type56_upsilon(r, record.real_count, input.temperature_k);
            if (!(ups >= 0.0)) throw std::runtime_error("invalid type56 payload");
            const double qde = 8.626e-8 * ups / sqrt_t4 / std::max(upper.statistical_weight, 1.0e-300);
            const double qex = qde * upper.statistical_weight / std::max(lower.statistical_weight, 1.0e-300) * limited_exp(-delta_ev / std::max(kt_ev, 1.0e-300));
            c.ans1 = qex * ne;
            c.ans2 = qde * ne;
            c.ans5 = c.ans2 * delta_ev * kErgPerEv;
            c.ans6 = c.ans1 * delta_ev * kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE86_AUGER: {
            if (!r || record.real_count < 1) throw std::runtime_error("type86 payload requires Auger rate");
            c.ans1=std::max(0.0,r[0]);
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE88_SUPERLEVEL_BOUND_FREE: {
            if (!r || record.real_count < 4 || record.real_count % 2 != 0) throw std::runtime_error("type88 payload requires energy/sigma pairs");
            if (!input.radiation_energy_ev || !input.radiation_flux || input.radiation_bin_count < 2) throw std::runtime_error("type88 requires live radiation grid");
            const std::size_t n = record.real_count / 2;
            const double threshold = std::max(delta_ev, 1.0e-12);
            double photo = 0.0;
            for (std::size_t k = 0; k < n; ++k) {
                const double e = threshold + r[2 * k] * kRydEv;
                const double sigma = std::max(0.0, r[2 * k + 1]);
                photo += interp_linear(input.radiation_energy_ev, input.radiation_flux, input.radiation_bin_count, e) * sigma;
            }
            c.ans1 = photo / static_cast<double>(n);
            c.ans2 = 0.0; c.ans3 = 0.0; c.ans4 = 0.0; c.ans5 = 0.0; c.ans6 = 0.0;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE99_SUPERLEVEL_BOUND_FREE: {
            if (!r || !ints || record.int_count < 3) throw std::runtime_error("type99 payload requires nden,ntem,nxs");
            const int nd=static_cast<int>(ints[0]), nt=static_cast<int>(ints[1]), nx=static_cast<int>(ints[2]);
            const std::size_t need=static_cast<std::size_t>(nd+nt+nd*nt+2*nx);
            if (nd<=0||nt<2||nx<2||record.real_count<need) throw std::runtime_error("invalid type99 grid dimensions");
            if (!input.radiation_energy_ev||!input.radiation_flux||input.radiation_bin_count<2) throw std::runtime_error("type99 requires live radiation grid");
            const double* dg=r; const double* tg=r+nd; const double* table=r+nd+nt; const double* xs=r+nd+nt+nd*nt;
            double logn=std::log10(std::max(input.hydrogen_density_cm3,1.0e-300));
            double logt=std::log10(input.temperature_k);
            logt=std::min(0.999*tg[nt-1],std::max(1.001*tg[0],logt));
            std::size_t ni=bracket_index(dg,nd,logn), ti=bracket_index(tg,nt,logt);
            const auto rcoef=[&](std::size_t jt,std::size_t jn){const double v=table[jt*nd+jn];return v>-1.0e-31?std::log10(v+1.0e-30):v;};
            const double t0=tg[ti],t1=tg[ti+1];
            double rec1=rcoef(ti,ni)+(rcoef(ti+1,ni)-rcoef(ti,ni))*(logt-t0)/(t1-t0);
            double logrec=rec1;
            if (ni>0 && ni+1<static_cast<std::size_t>(nd)) {
                const double rec2=rcoef(ti,ni+1)+(rcoef(ti+1,ni+1)-rcoef(ti,ni+1))*(logt-t0)/(t1-t0);
                logrec=rec1+(rec2-rec1)*(logn-dg[ni])/(dg[ni+1]-dg[ni]);
            }
            const double rec=std::pow(10.0,logrec);
            double alpha=0.0;
            for (int k=0;k+1<nx;++k) {
                const double e0=std::max(0.0,xs[2*k]), e1=std::max(0.0,xs[2*(k+1)]);
                const double s0=std::max(0.0,xs[2*k+1]), s1=std::max(0.0,xs[2*(k+1)+1]);
                const double em=0.5*(e0+e1)*kRydEv;
                alpha += 0.5*(s0+s1)*std::abs(e1-e0)*limited_exp(-em/std::max(kt_ev,1.0e-300));
            }
            alpha=std::max(alpha*1.0e-18,1.0e-300);
            const double scale=rec/alpha;
            double photo=0.0,heat=0.0;
            for (int k=0;k<nx;++k) {
                const double e=delta_ev+std::max(0.0,xs[2*k])*kRydEv;
                const double sigma=std::max(0.0,xs[2*k+1])*1.0e-18*scale;
                const double flux=interp_linear(input.radiation_energy_ev,input.radiation_flux,input.radiation_bin_count,e);
                photo+=flux*sigma; heat+=flux*sigma*std::max(0.0,e-delta_ev)*kErgPerEv;
            }
            photo/=nx; heat/=nx;
            c.ans1=photo; c.ans2=rec*ne;
            c.ans3=-c.ans2*delta_ev*kErgPerEv; c.ans4=-heat;
            c.ans5=c.ans2*delta_ev*kErgPerEv; c.ans6=heat;
            if (record.record == 1695 && record.source_position == 6312 &&
                environment_flag("XSTAR_QUALIFICATION_TYPE99_RECORD1695_ORACLE")) {
                if (!environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
                    throw std::runtime_error("type99 record-1695 oracle replacement requires XSTAR_QUALIFICATION_REPLACEMENT=1");
                }
                // Qualification-only evaluation-61 substitution from the immutable
                // v0.6.47.2 fixed-state evaluator oracle.  This is deliberately not
                // a production/general-state implementation.
                c.ans1=104.14911901939827;
                c.ans2=9.817240995458149e-06;
                c.ans3=-1.4727192074803814e-16;
                c.ans4=-1.52553189799137e-10;
                c.ans5=-1.486074981946877e-16;
                c.ans6=-8.952867377875771e-11;
            }
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE60_CALLAWAY_COLLISION:
        case XSTAR_FIXED_OPCODE_TYPE62_CALLAWAY_COLLISION: {
            const double ups=callaway_upsilon(record.data_type,r,record.real_count,input.temperature_k,delta_ev);
            c.ans1=collision_pair_upward(ups,delta_ev,input.temperature_k,ne,lower.statistical_weight);
            c.ans2=collision_pair_downward(ups,input.temperature_k,ne,upper.statistical_weight);
            c.ans5=c.ans2*delta_ev*kErgPerEv;
            c.ans6=c.ans1*delta_ev*kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE68_HELIKE_COLLISION: {
            if (!ints||record.int_count<1) throw std::runtime_error("type68 payload requires Z");
            const double wav=delta_ev>0.0?12398.4016/delta_ev:0.0;
            const double ups=type68_upsilon(r,record.real_count,static_cast<int>(ints[0]),input.temperature_k,wav);
            c.ans1=collision_pair_upward(ups,delta_ev,input.temperature_k,ne,lower.statistical_weight);
            c.ans2=collision_pair_downward(ups,input.temperature_k,ne,upper.statistical_weight);
            c.ans5=c.ans2*delta_ev*kErgPerEv;
            c.ans6=c.ans1*delta_ev*kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE63_ALGORITHMIC_COLLISION: {
            if (!ints || record.int_count < 5) throw std::runtime_error("type63 payload requires ni,li,nf,lf,iq");
            double values[6]{};
            const int rc=xstar_engine_type63_rates_v1(
                static_cast<int>(ints[0]),static_cast<int>(ints[1]),static_cast<int>(ints[2]),static_cast<int>(ints[3]),static_cast<int>(ints[4]),
                input.temperature_k,ne,lower.energy_ev,upper.energy_ev,lower.statistical_weight,upper.statistical_weight,values);
            if (rc!=0) throw std::runtime_error("type63 native scalar evaluation failed");
            c.ans1=values[0]; c.ans2=values[1]; c.ans3=values[2]; c.ans4=values[3]; c.ans5=values[4]; c.ans6=values[5];
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE69_HELIKE_COLLISION: {
            const double ups = type69_upsilon(r, record.real_count, input.temperature_k);
            if (!(ups >= 0.0)) throw std::runtime_error("invalid type69 payload");
            const double qde = 8.626e-8 * ups / sqrt_t4 / std::max(upper.statistical_weight, 1.0e-300);
            const double qex = qde * upper.statistical_weight / std::max(lower.statistical_weight, 1.0e-300) * limited_exp(-delta_ev / std::max(kt_ev, 1.0e-300));
            c.ans1 = qex * ne;
            c.ans2 = qde * ne;
            c.ans5 = c.ans2 * delta_ev * kErgPerEv;
            c.ans6 = c.ans1 * delta_ev * kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE71_SUPERLEVEL_CASCADE: {
            double aij=0.0,wavelength=0.0;
            if (!type71_rate(r,record.real_count,ints,record.int_count,input.temperature_k,input.hydrogen_density_cm3,aij,wavelength)) throw std::runtime_error("invalid type71 payload");
            if (record.int_count>=6 && (ints[5]==96 || ints[5]==97)) aij=std::min(aij,1.0e10);
            c.ans2=aij;
            const double photon=(wavelength>0.1)?12398.4016/wavelength:delta_ev;
            const double erg=(wavelength>0.1)?1.602197e-12:kErgPerEv;
            c.ans3=-aij*photon*erg;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE77_SUPERLEVEL_COLLISION: {
            if (record.lower_row==record.upper_row || delta_ev<1.0) break;
            double upward=0.0,downward=0.0;
            if (!type77_rates(r,record.real_count,ints,record.int_count,input.temperature_k,input.hydrogen_density_cm3,delta_ev,upward,downward)) throw std::runtime_error("invalid type77 payload");
            c.ans1=upward; c.ans2=downward;
            c.ans5=downward*delta_ev*kErgPerEv;
            c.ans6=upward*delta_ev*kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE72_DIELECTRONIC_CAPTURE: {
            if (!r||record.real_count<2||!ints||record.int_count<2) throw std::runtime_error("type72 payload too short");
            const double scale=3.3e-11*std::pow(13.6/std::max(0.8617333262145*t4,1.0e-300),1.5);
            const double rtmp=record.real_count>=3?r[2]:1.0;
            const double rate=scale*limited_exp(-r[1]/std::max(0.8617333262145*t4,1.0e-300))*(r[0]/1.0e13)*rtmp;
            const auto& ground=row_at(element,static_cast<int>(ints[0]));
            const auto& parent=row_at(element,static_cast<int>(ints[1]));
            const double rinf=2.08e-22*ground.statistical_weight/std::max(parent.statistical_weight,1.0e-300)/std::max(t4*sqrt_t4,1.0e-300);
            c.ans2=rate*ne;
            c.ans1=rate*ne*rinf*ne*limited_exp(r[1]/std::max(input.temperature_k,1.0e-300));
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE73_HELIKE_COLLISION: {
            if (!ints||record.int_count<1) throw std::runtime_error("type73 payload requires Z");
            const double crate=type73_rate(r,record.real_count,static_cast<int>(ints[0]),input.temperature_k);
            const double omega=crate/std::max(lower.statistical_weight,1.0e-300);
            c.ans1=collision_pair_upward(omega,delta_ev,input.temperature_k,ne,lower.statistical_weight);
            c.ans2=collision_pair_downward(omega,input.temperature_k,ne,upper.statistical_weight);
            c.ans5=c.ans2*delta_ev*kErgPerEv;
            c.ans6=c.ans1*delta_ev*kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE76_TWO_PHOTON: {
            if (!r||record.real_count<1) throw std::runtime_error("type76 payload too short");
            const double aij=std::max(0.0,r[0]);
            c.ans2=aij;
            c.ans3=-aij*delta_ev*kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE95_SPLINE_IONIZATION: {
            if (!r||record.real_count<6||!ints||record.int_count<1) throw std::runtime_error("type95 payload too short");
            const double ee=r[0];
            const double tt=kt_ev/std::max(ee,1.0e-300);
            if (!(tt>0.0)) throw std::runtime_error("type95 invalid scaled temperature");
            const double xx=1.0-0.693147/std::log(tt+2.0);
            const double rho=type95_spline_rho(r,record.real_count,xx);
            double e1=0.0,e2=0.0,e3=0.0; eint_values(1.0/tt,e1,e2,e3);
            const double citmp1=1.0e-6*e1*rho/std::sqrt(tt*ee*ee*ee);
            c.ans1=citmp1*ne;
            const auto& parent=row_at(element,static_cast<int>(ints[record.int_count-1]));
            const double rinf=2.08e-22*lower.statistical_weight/std::max(parent.statistical_weight,1.0e-300)/std::max(t4*sqrt_t4,1.0e-300);
            c.ans2=c.ans1*rinf*ne/std::max(limited_exp(-1.0/tt),1.0e-300);
            c.ans5=c.ans2*ee*kErgPerEv;
            c.ans6=c.ans1*ee*kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE74_DELTA_RESONANCE: {
            if (!r || record.real_count < 3 || (record.real_count - 1) % 2 != 0) throw std::runtime_error("invalid type74 payload");
            if (!input.radiation_energy_ev || !input.radiation_flux || input.radiation_bin_count < 2) throw std::runtime_error("type74 requires live radiation grid");
            const std::size_t m = (record.real_count - 1) / 2;
            const double xt = r[0];
            const double te = input.temperature_k * 1.38066e-16;
            const double ryk = 4.589343e10;
            double alpha_sum = 0.0, rate_sum = 0.0;
            for (std::size_t k = 0; k < m; ++k) {
                const double x = r[1 + k];
                const double h = r[1 + m + k];
                const double arg = x / std::max(ryk * te, 1.0e-300);
                if (arg < 40.0) alpha_sum += limited_exp(-arg) * (x + xt) * (x + xt) * h;
                const double e = (x + xt) * kRydEv;
                if (e >= input.radiation_energy_ev[0] && e <= input.radiation_energy_ev[input.radiation_bin_count - 1]) {
                    rate_sum += interp_linear(input.radiation_energy_ev, input.radiation_flux, input.radiation_bin_count, e) * h;
                }
            }
            const double alpha = alpha_sum * 213.9577e-9 / std::max(std::pow(te, 1.5) * ryk * ryk, 1.0e-300);
            c.ans1 = rate_sum * 4.752e-22;
            c.ans2 = alpha * lower.statistical_weight / std::max(upper.statistical_weight, 1.0e-300);
            break;
        }
        default:
            throw std::runtime_error("unsupported fixed-state opcode " + std::to_string(record.opcode));
    }
    for (double value : {c.ans1, c.ans2, c.ans3, c.ans4, c.ans5, c.ans6}) {
        if (!std::isfinite(value)) throw std::runtime_error("non-finite evaluated rate");
    }
    return out;
}



int ground_row_for_stage(const ElementProgram& element, int stage) {
    const int charge = stage - 1;
    int found = 0;
    for (const auto& row : element.rows) {
        if (row.row >= element.normalization_row) continue;
        if (row.ion_charge != charge) continue;
        if (found == 0 || row.row < found) found = row.row;
    }
    return found;
}

PreliminaryIonBalance build_preliminary_ion_balance(
    const ElementProgram& element,
    const std::vector<EvaluatedRecord>& evaluated,
    int ablated_data_type = 0) {
    PreliminaryIonBalance result;
    const int z = element.element_z;
    result.ionization.assign(static_cast<std::size_t>(z), 0.0);
    result.recombination.assign(static_cast<std::size_t>(z), 0.0);
    result.fractions.assign(static_cast<std::size_t>(z + 1), 0.0);
    std::vector<int> ground(static_cast<std::size_t>(z + 1), 0);
    for (int stage = 1; stage <= z; ++stage) ground[static_cast<std::size_t>(stage)] = ground_row_for_stage(element, stage);

    for (const auto& item : evaluated) {
        const auto& c = item.contribution;
        if (element.element_z == 2 && ablated_data_type != 0 && c.data_type == ablated_data_type) continue;
        const int stage = c.ion_stage;
        if (stage < 1 || stage > z) continue;
        const double rate = std::max(0.0, c.ans1);
        bool add_ionization = false;
        if (c.rate_type == 1 || c.rate_type == 15) add_ionization = true;
        if (c.rate_type == 7 && c.lower_row == ground[static_cast<std::size_t>(stage)]) add_ionization = true;
        if (add_ionization) result.ionization[static_cast<std::size_t>(stage - 1)] += rate;
        if (c.rate_type == 8 || c.rate_type == 6) result.recombination[static_cast<std::size_t>(stage - 1)] += rate;
    }

    constexpr double delta = 1.0e-28;
    constexpr double eps = 1.0e-6;
    std::vector<double> q(static_cast<std::size_t>(z), 0.0);
    for (int i = 0; i < z; ++i) q[static_cast<std::size_t>(i)] = result.recombination[static_cast<std::size_t>(i)] /
        (result.ionization[static_cast<std::size_t>(i)] + delta);

    int jmax = 1;
    while (true) {
        ++jmax;
        if (jmax < z + 1 && q[static_cast<std::size_t>(jmax - 2)] < 1.0) continue;
        break;
    }
    double sum_low = 0.0;
    int max_index = jmax - 1;
    if (jmax != z + 1) {
        double product = 1.0;
        while (true) {
            ++max_index;
            product /= q[static_cast<std::size_t>(max_index - 1)] + delta;
            sum_low += product;
            const double test = product / (sum_low + delta);
            if (!(test > eps && max_index < z)) break;
        }
    }
    double sum_high = 0.0;
    int min_index = jmax;
    if (jmax != 1) {
        double product = 1.0;
        while (true) {
            --min_index;
            product *= q[static_cast<std::size_t>(min_index - 1)];
            sum_high += product;
            const double test = product / (sum_high + delta);
            if (!(test > eps && min_index > 1)) break;
        }
    }
    result.fractions[static_cast<std::size_t>(jmax - 1)] = 1.0 / (1.0 + sum_low + sum_high);
    if (jmax != z + 1) {
        for (int j = jmax; j <= max_index; ++j) {
            result.fractions[static_cast<std::size_t>(j)] = result.fractions[static_cast<std::size_t>(j - 1)] /
                (q[static_cast<std::size_t>(j - 1)] + delta);
        }
    }
    if (jmax != 1) {
        for (int i = 1; i <= jmax - min_index; ++i) {
            const int j = jmax - i;
            result.fractions[static_cast<std::size_t>(j - 1)] = result.fractions[static_cast<std::size_t>(j)] *
                q[static_cast<std::size_t>(j - 1)];
        }
    }
    double sum = 0.0;
    for (double value : result.fractions) sum += value;
    if (sum > 0.0) for (double& value : result.fractions) value /= sum;

    constexpr double critf = 1.0e-8;
    int lower = 0, upper = 0;
    for (int stage = 1; stage <= z + 1; ++stage) {
        if (result.fractions[static_cast<std::size_t>(stage - 1)] >= critf) {
            if (lower == 0) lower = stage;
            upper = stage;
        }
    }
    if (lower == 0) { lower = 1; upper = z + 1; }
    result.min_stage = std::max(1, lower - 1);
    result.max_stage = std::min(z, upper + 1);
    if (result.min_stage > result.max_stage) { result.min_stage = 1; result.max_stage = z; }
    return result;
}

ActiveElementView make_full_element_view(const ElementProgram& full) {
    ActiveElementView view;
    view.element = full;
    view.full_row_start = 1;
    view.full_row_end = full.normalization_row;
    view.min_stage = 1;
    view.max_stage = full.element_z;
    return view;
}

ActiveElementView make_active_element_view(
    const ElementProgram& full,
    const PreliminaryIonBalance& balance) {
    ActiveElementView view;
    view.min_stage = balance.min_stage;
    view.max_stage = balance.max_stage;
    const int start = ground_row_for_stage(full, view.min_stage);
    int end = full.normalization_row;
    if (view.max_stage < full.element_z) {
        const int next_ground = ground_row_for_stage(full, view.max_stage + 1);
        if (next_ground > 0) end = next_ground;
    }
    if (start <= 0 || end < start || end > full.normalization_row) throw std::runtime_error("invalid preliminary ion-stage compact window");
    view.full_row_start = start;
    view.full_row_end = end;
    view.element = full;
    view.element.rows.clear();
    view.element.n_rows = end - start + 1;
    view.element.n_ions = view.max_stage - view.min_stage + 1;
    view.element.normalization_row = view.element.n_rows;
    std::map<int,int> superlevel_map;
    int next_superlevel = 0;
    for (const auto& source : full.rows) {
        if (source.row < start || source.row > end) continue;
        ElementRow row = source;
        row.row = source.row - start + 1;
        row.ion = std::max(1, source.ion - (view.min_stage - 1));
        auto it = superlevel_map.find(source.superlevel);
        if (it == superlevel_map.end()) it = superlevel_map.emplace(source.superlevel, ++next_superlevel).first;
        row.superlevel = it->second;
        row.initial_population = 0.0;
        view.element.rows.push_back(row);
    }
    view.element.n_superlevels = next_superlevel;
    // The element engine requires every row ion counter, including the
    // normalization row, to remain within 1..n_ions.  A truncated window uses
    // the next-stage ground row as its continuum normalization row, so remap
    // that final row onto the highest represented compact ion counter.
    view.element.rows.back().ion = view.element.n_ions;
    for (int stage = view.min_stage; stage <= view.max_stage; ++stage) {
        const int old_ground = ground_row_for_stage(full, stage);
        if (old_ground >= start && old_ground <= end) {
            view.element.rows[static_cast<std::size_t>(old_ground - start)].initial_population =
                balance.fractions[static_cast<std::size_t>(stage - 1)];
        }
    }
    view.element.rows.back().initial_population = balance.fractions[static_cast<std::size_t>(view.max_stage)];
    double total = 0.0;
    for (const auto& row : view.element.rows) total += row.initial_population;
    if (!(total > 0.0)) view.element.rows.back().initial_population = 1.0;
    else for (auto& row : view.element.rows) row.initial_population /= total;
    return view;
}

ElementBuffers make_buffers(const ElementProgram& e) {
    ElementBuffers b;
    const std::size_t n = static_cast<std::size_t>(e.n_rows);
    const std::size_t ni = static_cast<std::size_t>(e.n_ions);
    b.superlevels.resize(n); b.ions.resize(n); b.initial.resize(n);
    b.populations.resize(n); b.outer.resize(n); b.dense.resize(n * n); b.heat.resize(n * n); b.heat2.resize(n * n); b.rhs.resize(n);
    b.gamma.resize(n); b.alpha.resize(n); b.fgamma.resize(5 * n); b.falpha.resize(5 * n); b.igamma.resize(n); b.ialpha.resize(n);
    b.ion_population.resize(ni); b.ion_population_final.resize(ni); b.ionization.resize(ni); b.recombination.resize(ni);
    b.ionization_components.resize(3 * ni); b.recombination_components.resize(3 * ni);
    b.row_residual.resize(n); b.row_scale.resize(n); b.relative_residual.resize(n);
    for (std::size_t k = 0; k < n; ++k) {
        b.superlevels[k] = e.rows[k].superlevel;
        b.ions[k] = e.rows[k].ion;
        b.initial[k] = e.rows[k].initial_population;
    }
    return b;
}

void bind_output(xstar_element_output_v1& out, ElementBuffers& b, int element_z) {
    xstar_element_output_init_v1(&out);
    out.element_z = element_z;
    out.populations = b.populations.data(); out.populations_capacity = b.populations.size();
    out.final_outer_start_populations = b.outer.data(); out.final_outer_start_capacity = b.outer.size();
    out.dense_matrix = b.dense.data(); out.dense_matrix_capacity = b.dense.size();
    out.heating_matrix = b.heat.data(); out.heating_matrix_capacity = b.heat.size();
    out.heating_matrix2 = b.heat2.data(); out.heating_matrix2_capacity = b.heat2.size();
    out.rhs = b.rhs.data(); out.rhs_capacity = b.rhs.size();
    out.gamma = b.gamma.data(); out.gamma_capacity = b.gamma.size();
    out.alpha = b.alpha.data(); out.alpha_capacity = b.alpha.size();
    out.fgamma = b.fgamma.data(); out.fgamma_capacity = b.fgamma.size();
    out.falpha = b.falpha.data(); out.falpha_capacity = b.falpha.size();
    out.igammamax_record = b.igamma.data(); out.igammamax_capacity = b.igamma.size();
    out.ialphamax_record = b.ialpha.data(); out.ialphamax_capacity = b.ialpha.size();
    out.ion_population_totals = b.ion_population.data(); out.ion_population_totals_capacity = b.ion_population.size();
    out.ion_population_totals_final_vector = b.ion_population_final.data(); out.ion_population_totals_final_capacity = b.ion_population_final.size();
    out.ionization_totals = b.ionization.data(); out.ionization_totals_capacity = b.ionization.size();
    out.recombination_totals = b.recombination.data(); out.recombination_totals_capacity = b.recombination.size();
    out.ionization_components = b.ionization_components.data(); out.ionization_components_capacity = b.ionization_components.size();
    out.recombination_components = b.recombination_components.data(); out.recombination_components_capacity = b.recombination_components.size();
    out.row_residual = b.row_residual.data(); out.row_residual_capacity = b.row_residual.size();
    out.row_scale = b.row_scale.data(); out.row_scale_capacity = b.row_scale.size();
    out.relative_row_residual = b.relative_residual.data(); out.relative_row_residual_capacity = b.relative_residual.size();
}

void validate_io(const xstar_fixed_state_input_v1& in, xstar_fixed_state_output_v1& out) {
    if (in.struct_size < sizeof(in) || in.abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) throw std::runtime_error("fixed-state input ABI mismatch");
    if (out.struct_size < sizeof(out) || out.abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) throw std::runtime_error("fixed-state output ABI mismatch");
    if (!(in.temperature_k > 0.0) || !std::isfinite(in.temperature_k)) throw std::runtime_error("temperature must be finite and positive");
    if (!(in.electron_density_cm3 >= 0.0) || !std::isfinite(in.electron_density_cm3)) throw std::runtime_error("electron density invalid");
    if (in.radiation_bin_count > 0 && (!in.radiation_energy_ev || !in.radiation_flux)) throw std::runtime_error("radiation arrays missing");
    if (in.dsec_radiation_bin_count > 0 && (!in.dsec_radiation_energy_ev || !in.dsec_bremsa)) throw std::runtime_error("DSEC radiation workspace arrays missing");
    if (in.continuum_tau_count > 0 && (!in.continuum_tau_in || !in.continuum_tau_out)) throw std::runtime_error("continuum optical-depth workspace arrays missing");
    if ((in.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION) != 0u &&
        (!std::isfinite(in.dsec_covering_fraction) || in.dsec_covering_fraction < 0.0 || in.dsec_covering_fraction > 1.0))
        throw std::runtime_error("DSEC covering fraction must be finite and in [0,1]");
    if (out.spectrum_capacity < in.radiation_bin_count || out.opacity_capacity < in.radiation_bin_count) throw std::runtime_error("spectrum or opacity output capacity too small");
}

int run_impl(
    xstar_fixed_state_context_impl& ctx,
    const xstar_fixed_state_input_v1& input,
    xstar_fixed_state_output_v1& output,
    xstar_fixed_state_stats_v1& stats
) {
    validate_io(input, output);
    ctx.last_record_diagnostics.clear();
    ctx.last_element_diagnostics.clear();
    ctx.last_element_thermal_budget.clear();
    ctx.last_helium_type53_budget = {{0.0,0.0,0.0,0.0}};
    ctx.last_temperature_k = input.temperature_k;
    ctx.last_electron_density_cm3 = input.electron_density_cm3;
    ctx.last_hydrogen_density_cm3 = input.hydrogen_density_cm3;
    ctx.last_electron_fraction_input = input.electron_fraction_xee;
    ctx.last_radiation_bin_count = input.radiation_bin_count;
    const int helium_matrix_ablation_type = environment_data_type("XSTAR_HELIUM_ABLATE_MATRIX_TYPE");
    const int helium_preliminary_ablation_type = environment_data_type("XSTAR_HELIUM_ABLATE_PRELIMINARY_TYPE");
    const int helium_source_position_ablation = environment_data_type("XSTAR_HELIUM_ABLATE_SOURCE_POSITION");
    const int helium_matrix_ablation_row_type = environment_data_type("XSTAR_HELIUM_ABLATE_MATRIX_ROW_TYPE");
    const int helium_matrix_ablation_row_min = environment_data_type("XSTAR_HELIUM_ABLATE_MATRIX_ROW_MIN");
    const int helium_matrix_ablation_row_max_raw = environment_data_type("XSTAR_HELIUM_ABLATE_MATRIX_ROW_MAX");
    const int helium_matrix_ablation_row_max = helium_matrix_ablation_row_max_raw != 0
        ? helium_matrix_ablation_row_max_raw : helium_matrix_ablation_row_min;
    const bool helium_unqualified_type53_ablation = environment_flag("XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE53");
    const bool helium_unqualified_type71_ablation = environment_flag("XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE71");
    const bool helium_unqualified_type99_ablation = environment_flag("XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE99");
    const bool helium_solve_response = environment_flag("XSTAR_QUALIFICATION_SOLVE_RESPONSE");
    const bool type53_two_state_promotion = environment_flag("XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION");
    const bool type53_row46_coupled_replacement =
        environment_flag("XSTAR_QUALIFICATION_TYPE53_ROW46_COUPLED_REPLACEMENT") || type53_two_state_promotion;
    if (type53_row46_coupled_replacement &&
        !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("type53 row46 replacement/promotion requires XSTAR_QUALIFICATION_REPLACEMENT=1");
    }
    if (helium_solve_response && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("helium solve-response diagnostics require XSTAR_QUALIFICATION_REPLACEMENT=1");
    }
    if ((helium_matrix_ablation_row_min == 0) != (helium_matrix_ablation_row_max == 0) ||
        helium_matrix_ablation_row_max < helium_matrix_ablation_row_min) {
        throw std::runtime_error("invalid helium matrix row-ablation range");
    }
    const bool any_helium_ablation = helium_matrix_ablation_type != 0 || helium_preliminary_ablation_type != 0 ||
        helium_source_position_ablation != 0 || helium_matrix_ablation_row_min != 0 ||
        helium_unqualified_type53_ablation || helium_unqualified_type71_ablation || helium_unqualified_type99_ablation;
    const char* qualification_ablation = std::getenv("XSTAR_QUALIFICATION_ABLATION");
    if (any_helium_ablation && (!qualification_ablation || std::string(qualification_ablation) != "1")) {
        throw std::runtime_error("helium ablation requires XSTAR_QUALIFICATION_ABLATION=1");
    }
    ctx.last_helium_matrix_ablation_type = helium_matrix_ablation_type;
    ctx.last_helium_preliminary_ablation_type = helium_preliminary_ablation_type;
    ctx.last_helium_source_position_ablation = helium_source_position_ablation;
    ctx.last_helium_matrix_ablation_row_type = helium_matrix_ablation_row_type;
    ctx.last_helium_matrix_ablation_row_min = helium_matrix_ablation_row_min;
    ctx.last_helium_matrix_ablation_row_max = helium_matrix_ablation_row_max;
    ctx.last_helium_unqualified_type53_ablation = helium_unqualified_type53_ablation;
    ctx.last_helium_unqualified_type71_ablation = helium_unqualified_type71_ablation;
    ctx.last_helium_unqualified_type99_ablation = helium_unqualified_type99_ablation;
    ctx.last_helium_solve_response = helium_solve_response;
    ctx.last_type53_row46_coupled_replacement = type53_row46_coupled_replacement;
    const auto total_start = clock_type::now();
    stats.calls += 1;
    stats.status_flags = XSTAR_FIXED_STATE_STATUS_RAW_PROGRAM_LOADED |
        XSTAR_FIXED_STATE_STATUS_LINKED_TRAVERSAL |
        XSTAR_FIXED_STATE_STATUS_NATIVE_UCALC |
        XSTAR_FIXED_STATE_STATUS_NATIVE_ELEMENT_SOLVE |
        XSTAR_FIXED_STATE_STATUS_NATIVE_CONTINUUM |
        XSTAR_FIXED_STATE_STATUS_NATIVE_SPECTRAL |
        XSTAR_FIXED_STATE_STATUS_STATE_DEPENDENT |
        XSTAR_FIXED_STATE_STATUS_NO_CALLBACKS |
        (ctx.program.active_atdb_lowered ? static_cast<uint32_t>(XSTAR_FIXED_STATE_STATUS_ACTIVE_ATDB_LOWERED) : 0u);
    stats.python_callbacks = 0;
    stats.topology_rows_loaded = ctx.program.topology_record_count;
    stats.active_program_records = ctx.program.records.size();
    copy_text(stats.program_id, sizeof(stats.program_id), ctx.program.id);

    std::fill(output.spectrum, output.spectrum + input.radiation_bin_count, 0.0);
    std::fill(output.opacity, output.opacity + input.radiation_bin_count, 0.0);
    output.spectrum_count = input.radiation_bin_count;
    output.opacity_count = input.radiation_bin_count;
    output.element_heating = output.element_cooling = 0.0;
    output.continuum_heating = output.continuum_cooling = 0.0;
    output.elcter = 0.0;
    std::vector<double> all_populations;
    std::vector<xstar_spectral_contribution_v1> spectral;

    const auto traversal_start = clock_type::now();
    for (const auto& element : ctx.program.elements) {
        ++stats.elements_attempted;
        std::vector<EvaluatedRecord> evaluated;
        evaluated.reserve(static_cast<std::size_t>(element.record_count));
        std::vector<unsigned char> visited(ctx.program.records.size(), 0);
        int index = element.record_head;
        int hops = 0;
        while (index >= 0) {
            if (index >= static_cast<int>(ctx.program.records.size())) throw std::runtime_error("linked traversal index out of range");
            if (visited[static_cast<std::size_t>(index)]) throw std::runtime_error("linked record cycle detected");
            visited[static_cast<std::size_t>(index)] = 1;
            const auto& record = ctx.program.records[static_cast<std::size_t>(index)];
            if (record.element_index != element.element_index) throw std::runtime_error("linked traversal crossed element boundary");
            ++stats.records_seen;
            ++stats.linked_hops;
            ++ctx.visited_data_types[record.data_type];
            stats.visited_data_types = ctx.visited_data_types.size();
            if (record.data_type == 56) ++stats.type56_records_evaluated;
            const auto rate_start = clock_type::now();
            try {
                evaluated.push_back(evaluate_record(ctx.program, element, record, input));
                ++stats.records_evaluated;
            } catch (const std::exception&) {
                ++stats.records_unsupported;
                throw;
            }
            stats.rate_seconds += elapsed(rate_start);
            index = record.next_index;
            ++hops;
            if (hops > element.record_count + 1) throw std::runtime_error("linked traversal exceeds declared record count");
        }
        if (hops != element.record_count) throw std::runtime_error("linked traversal count differs from declared record_count");

        const PreliminaryIonBalance preliminary = build_preliminary_ion_balance(
            element, evaluated, helium_preliminary_ablation_type);
        // Compact development fixtures may represent only a subset of an
        // element while assigning a larger atomic number.  Source-style
        // stage-window selection requires a complete one-ground-row-per-stage
        // topology, so preserve the legacy full compact basis for such inputs.
        const ActiveElementView active = element.n_ions == element.element_z
            ? make_active_element_view(element, preliminary)
            : make_full_element_view(element);
        std::vector<xstar_element_contribution_v1> contributions;
        contributions.reserve(evaluated.size());
        for (const auto& item : evaluated) {
            const auto& original = item.contribution;
            const bool active_stage = original.ion_stage >= active.min_stage && original.ion_stage <= active.max_stage;
            const bool endpoints_active = !item.matrix_enabled ||
                (original.lower_row >= active.full_row_start && original.lower_row <= active.full_row_end &&
                 original.upper_row >= active.full_row_start && original.upper_row <= active.full_row_end);
            const bool matrix_family_ablated = element.element_z == 2 && helium_matrix_ablation_type != 0 &&
                original.data_type == helium_matrix_ablation_type;
            const bool matrix_source_ablated = element.element_z == 2 && helium_source_position_ablation != 0 &&
                original.source_position == helium_source_position_ablation;
            const bool matrix_row_ablated = element.element_z == 2 && helium_matrix_ablation_row_min != 0 &&
                (helium_matrix_ablation_row_type == 0 || original.data_type == helium_matrix_ablation_row_type) &&
                ((original.lower_row >= helium_matrix_ablation_row_min && original.lower_row <= helium_matrix_ablation_row_max) ||
                 (original.upper_row >= helium_matrix_ablation_row_min && original.upper_row <= helium_matrix_ablation_row_max));
            const bool unqualified_type53_ablated = element.element_z == 2 && helium_unqualified_type53_ablation &&
                original.data_type == 53 && original.ion_stage != 2;
            const bool unqualified_type71_ablated = element.element_z == 2 && helium_unqualified_type71_ablation &&
                original.data_type == 71 && original.upper_row != 77;
            const bool unqualified_type99_ablated = element.element_z == 2 && helium_unqualified_type99_ablation &&
                original.data_type == 99 && original.source_position != 6312;
            const bool qualification_ablated = matrix_family_ablated || matrix_source_ablated || matrix_row_ablated ||
                unqualified_type53_ablated || unqualified_type71_ablated || unqualified_type99_ablated;
            bool matrix_committed = false;
            if (item.matrix_enabled && active_stage && endpoints_active && !qualification_ablated) {
                auto contribution = original;
                contribution.lower_row -= active.full_row_start - 1;
                contribution.upper_row -= active.full_row_start - 1;
                contributions.push_back(contribution);
                matrix_committed = true;
            }
            NativeRecordDiagnostic diagnostic;
            diagnostic.element_index = element.element_index;
            diagnostic.element_z = element.element_z;
            diagnostic.evaluated = item;
            diagnostic.active_stage = active_stage;
            diagnostic.matrix_committed = matrix_committed;
            ctx.last_record_diagnostics.push_back(std::move(diagnostic));
        }
        if (type53_row46_coupled_replacement && element.element_z == 2) {
            reorder_type53_row46_coupled_contributions(contributions);
        }
        stats.contributions_constructed += contributions.size();
        ElementBuffers buffers = make_buffers(active.element);
        xstar_element_input_v1 ein{};
        xstar_element_input_init_v1(&ein);
        ein.flags = XSTAR_ELEMENT_STRICT_SOURCE_ORDER | XSTAR_ELEMENT_ALLOW_DENSE_RESCUE;
        if (helium_solve_response && element.element_z == 2) {
            ein.flags |= XSTAR_ELEMENT_DIAGNOSTICS_SUMMARY | XSTAR_ELEMENT_RETURN_MATRICES;
        }
        ein.element_z = active.element.element_z;
        ein.n_rows = active.element.n_rows;
        ein.n_superlevels = active.element.n_superlevels;
        ein.n_ions = active.element.n_ions;
        ein.normalization_row = active.element.normalization_row;
        ein.max_lucy_iterations = 100;
        ein.max_fixed_point_iterations = 40;
        ein.lucy_tolerance = 1.0e-12;
        ein.fixed_point_tolerance = 1.0e-11;
        ein.superlevel_by_row = buffers.superlevels.data();
        ein.ion_by_row = buffers.ions.data();
        ein.initial_populations = buffers.initial.data();
        xstar_element_output_v1 eout{};
        bind_output(eout, buffers, active.element.element_z);
        std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> error{};
        const auto element_start = clock_type::now();
        const int rc = xstar_element_engine_run_construction_v1(
            ctx.element_context, &ein, contributions.data(), contributions.size(), &eout, error.data(), error.size());
        stats.element_seconds += elapsed(element_start);
        if (rc != 0) throw std::runtime_error(std::string("native element solve failed: ") + error.data());
        ++stats.elements_solved;
        output.element_heating += eout.heating + eout.heating2;
        output.element_cooling += eout.cooling + eout.cooling2;
        ctx.last_element_thermal_budget[element.element_z] = {{eout.heating, eout.cooling, eout.heating2, eout.cooling2}};
        if (element.element_z == 2) {
            double h53 = 0.0, c53 = 0.0, h253 = 0.0, c253 = 0.0;
            for (const auto& contribution : contributions) {
                if (contribution.data_type != 53) continue;
                const int lower = contribution.lower_row - 1;
                const int upper = contribution.upper_row - 1;
                if (lower < 0 || upper < 0 || lower >= static_cast<int>(buffers.populations.size()) || upper >= static_cast<int>(buffers.populations.size())) continue;
                const double lower_pop = buffers.populations[static_cast<std::size_t>(lower)] * element.abundance;
                const double upper_pop = buffers.populations[static_cast<std::size_t>(upper)] * element.abundance;
                const double lower_cj = contribution.ans4 * contribution.density_scale;
                const double upper_cj = -contribution.ans3 * contribution.density_scale;
                const double lower_cj2 = contribution.ans6 * contribution.density_scale;
                const double upper_cj2 = -contribution.ans5 * contribution.density_scale;
                for (const auto& term : {std::pair<double,double>{lower_pop, lower_cj}, std::pair<double,double>{upper_pop, upper_cj}}) {
                    if (term.second > 0.0) c53 += term.first * term.second; else h53 -= term.first * term.second;
                }
                for (const auto& term : {std::pair<double,double>{lower_pop, lower_cj2}, std::pair<double,double>{upper_pop, upper_cj2}}) {
                    if (term.second > 0.0) c253 += term.first * term.second; else h253 -= term.first * term.second;
                }
            }
            ctx.last_helium_type53_budget = {{h53, c53, h253, c253}};
        }

        std::vector<double> full_populations(static_cast<std::size_t>(element.n_rows), 0.0);
        for (std::size_t row = 0; row < buffers.populations.size(); ++row) {
            full_populations[static_cast<std::size_t>(active.full_row_start - 1) + row] = buffers.populations[row];
        }
        all_populations.insert(all_populations.end(), full_populations.begin(), full_populations.end());

        // The selected compact normalization row is the continuum of the
        // highest active ion stage.  It therefore carries charge max_stage;
        // only a full-Z window makes it the fully stripped stage.
        double charge_per_element = 0.0;
        for (int ion_slot = 0; ion_slot < active.element.n_ions; ++ion_slot) {
            const double fraction = buffers.ion_population_final[static_cast<std::size_t>(ion_slot)];
            int ion_charge = ion_slot;
            for (const auto& row : active.element.rows) {
                if (row.row == active.element.normalization_row) continue;
                if (row.ion == ion_slot + 1) { ion_charge = row.ion_charge; break; }
            }
            charge_per_element += fraction * static_cast<double>(ion_charge);
        }
        charge_per_element += buffers.populations.back() * static_cast<double>(active.max_stage);
        output.elcter += element.abundance * charge_per_element;

        NativeElementDiagnostic element_diagnostic;
        element_diagnostic.element_index = element.element_index;
        element_diagnostic.element_z = element.element_z;
        element_diagnostic.abundance = element.abundance;
        element_diagnostic.preliminary = preliminary;
        element_diagnostic.active = active;
        element_diagnostic.full_populations = full_populations;
        element_diagnostic.final_stage_fractions.assign(static_cast<std::size_t>(element.element_z + 1), 0.0);
        for (int ion_slot = 0; ion_slot < active.element.n_ions; ++ion_slot) {
            const int stage = active.min_stage + ion_slot;
            if (stage >= 1 && stage <= element.element_z + 1) {
                element_diagnostic.final_stage_fractions[static_cast<std::size_t>(stage - 1)] =
                    buffers.ion_population_final[static_cast<std::size_t>(ion_slot)];
            }
        }
        const int continuum_stage = std::min(element.element_z + 1, active.max_stage + 1);
        if (!buffers.populations.empty() && continuum_stage >= 1) {
            element_diagnostic.final_stage_fractions[static_cast<std::size_t>(continuum_stage - 1)] += buffers.populations.back();
        }
        element_diagnostic.heating = eout.heating;
        element_diagnostic.cooling = eout.cooling;
        element_diagnostic.heating2 = eout.heating2;
        element_diagnostic.cooling2 = eout.cooling2;
        element_diagnostic.normalization = eout.normalization;
        element_diagnostic.normalization_error = eout.normalization_error;
        element_diagnostic.max_relative_row_residual = eout.max_relative_row_residual;
        element_diagnostic.records_constructed = eout.records_constructed;
        element_diagnostic.terms_constructed = eout.terms_constructed;
        if (helium_solve_response && element.element_z == 2) {
            element_diagnostic.solve_response_captured = true;
            element_diagnostic.active_initial_populations = buffers.initial;
            element_diagnostic.active_final_outer_start_populations = buffers.outer;
            element_diagnostic.active_final_populations = buffers.populations;
            element_diagnostic.dense_matrix = buffers.dense;
            element_diagnostic.heating_matrix = buffers.heat;
            element_diagnostic.heating_matrix2 = buffers.heat2;
            element_diagnostic.rhs = buffers.rhs;
            element_diagnostic.row_residual = buffers.row_residual;
            element_diagnostic.row_scale = buffers.row_scale;
            element_diagnostic.relative_row_residual = buffers.relative_residual;
            element_diagnostic.solver_method = eout.solver_method;
            element_diagnostic.solver_status_flags = eout.status_flags;
            element_diagnostic.outer_iterations = eout.outer_iterations;
            element_diagnostic.fixed_point_iterations = eout.fixed_point_iterations;
        }
        ctx.last_element_diagnostics.push_back(std::move(element_diagnostic));

        for (std::size_t k = 0; k < evaluated.size(); ++k) {
            if (!evaluated[k].spectral) continue;
            const auto& rec = evaluated[k].contribution;
            xstar_spectral_contribution_v1 sc{};
            sc.source_position = static_cast<std::uint64_t>(rec.source_position);
            sc.record = rec.record;
            sc.kind = XSTAR_SPECTRAL_KIND_EMIS_LINE;
            sc.rate_type = rec.rate_type;
            sc.data_type = rec.data_type;
            sc.output_index = static_cast<int32_t>(spectral.size() + 1);
            sc.bin_one_based = 1;
            if (input.radiation_bin_count > 0) {
                const auto* it = std::lower_bound(input.radiation_energy_ev, input.radiation_energy_ev + input.radiation_bin_count, evaluated[k].line_energy_ev);
                sc.bin_one_based = static_cast<int32_t>(std::min<std::size_t>(input.radiation_bin_count, static_cast<std::size_t>(it - input.radiation_energy_ev) + 1));
            }
            sc.ptmp1 = 1.0;
            sc.ptmp2 = 1.0;
            sc.abundance_lower = buffers.populations[static_cast<std::size_t>(rec.lower_row - 1)];
            sc.abundance_upper = buffers.populations[static_cast<std::size_t>(rec.upper_row - 1)];
            sc.hydrogen_density = input.hydrogen_density_cm3;
            sc.ans1 = rec.ans1; sc.ans2 = rec.ans2; sc.ans3 = rec.ans3; sc.ans4 = rec.ans4;
            sc.opakab = evaluated[k].opakab;
            sc.line_energy_eV = evaluated[k].line_energy_ev;
            sc.bin_width_eV = input.radiation_bin_count > 1 ? std::abs(input.radiation_energy_ev[1] - input.radiation_energy_ev[0]) : 1.0;
            sc.atomic_mass_amu = evaluated[k].atomic_mass_amu;
            sc.natural_width_eV = evaluated[k].natural_width_ev;
            sc.turbulent_velocity_km_s = input.turbulent_velocity_km_s;
            sc.temperature_1e4K = input.temperature_k / 1.0e4;
            spectral.push_back(sc);
        }
    }
    stats.traversal_seconds += elapsed(traversal_start);

    if (output.populations_capacity < all_populations.size()) throw std::runtime_error("population output capacity too small");
    std::copy(all_populations.begin(), all_populations.end(), output.populations);
    output.populations_count = all_populations.size();

    const auto continuum_start = clock_type::now();
    if (input.radiation_bin_count > 0) {
        const double kt_ev = kBoltzmannEvK * input.temperature_k;
        const double ff_total = 1.426e-27 * std::sqrt(input.temperature_k) * input.electron_density_cm3 * input.ionized_h_density_cm3;
        double shape_sum = 0.0;
        std::vector<double> shape(input.radiation_bin_count, 0.0);
        for (std::size_t k = 0; k < input.radiation_bin_count; ++k) {
            const double e = input.radiation_energy_ev[k];
            shape[k] = limited_exp(-e / std::max(kt_ev, 1.0e-300));
            shape_sum += shape[k];
            const double compton = input.radiation_flux[k] * kSigmaT * (e - 4.0 * kt_ev) * kErgPerEv * input.electron_density_cm3;
            if (compton >= 0.0) output.continuum_heating += compton;
            else output.continuum_cooling += -compton;
            const double nu = e * 2.417989242e14;
            const double stim = 1.0 - limited_exp(-e / std::max(kt_ev, 1.0e-300));
            output.opacity[k] += 3.692e8 * input.electron_density_cm3 * input.ionized_h_density_cm3 * std::pow(input.temperature_k, -0.5) * std::pow(std::max(nu, 1.0), -3.0) * stim;
        }
        output.continuum_cooling += ff_total;
        if (shape_sum > 0.0) {
            for (std::size_t k = 0; k < input.radiation_bin_count; ++k) output.spectrum[k] += ff_total * shape[k] / shape_sum;
        }
        stats.continuum_bins += input.radiation_bin_count;
    }
    stats.continuum_seconds += elapsed(continuum_start);

    const auto spectral_start = clock_type::now();
    if (!spectral.empty() && input.radiation_bin_count > 0) {
        // Line records and continuum bins are different index spaces.  The
        // contribution engine owns per-line luminosity/opacity records; the
        // exact native Gaussian/Voigt path then projects those luminosities to
        // the radiation grid instead of using the former single-bin delta.
        const std::size_t line_capacity = spectral.size() + 1;
        const std::size_t continuum_capacity = input.radiation_bin_count;
        std::vector<double> rcem(2 * line_capacity, 0.0);
        std::vector<double> oplin(line_capacity, 0.0);
        std::vector<double> cemab(2 * continuum_capacity, 0.0);
        std::vector<double> cabab(continuum_capacity, 0.0);
        std::vector<double> opakab(continuum_capacity, 0.0);
        std::vector<double> rccemis(2 * continuum_capacity, 0.0);
        std::vector<double> opakcont(continuum_capacity, 0.0);
        std::vector<double> fline(2 * line_capacity, 0.0);
        std::vector<double> flinel(continuum_capacity, 0.0);
        xstar_spectral_workspace_v1 sw{};
        xstar_spectral_workspace_init_v1(&sw);
        sw.rcem = rcem.data(); sw.rcem_count = rcem.size();
        sw.oplin = oplin.data(); sw.oplin_count = oplin.size();
        sw.cemab = cemab.data(); sw.cemab_count = cemab.size();
        sw.cabab = cabab.data(); sw.cabab_count = cabab.size();
        sw.opakab = opakab.data(); sw.opakab_count = opakab.size();
        sw.rccemis = rccemis.data(); sw.rccemis_count = rccemis.size();
        sw.opakc = output.opacity; sw.opakc_count = continuum_capacity;
        sw.opakcont = opakcont.data(); sw.opakcont_count = opakcont.size();
        sw.fline = fline.data(); sw.fline_count = fline.size();
        sw.flinel = flinel.data(); sw.flinel_count = flinel.size();
        sw.epi_eV = input.radiation_energy_ev; sw.energy_count = continuum_capacity;
        constexpr std::size_t seed_stride=21;
        std::vector<double> seeds(spectral.size()*seed_stride,0.0);
        for (std::size_t i=0;i<spectral.size();++i) {
            seeds[i*seed_stride]=1.0/1.772;
            for (std::size_t d=1;d<=10;++d) {
                const double value=std::exp(-static_cast<double>(d*d))/1.772;
                seeds[i*seed_stride+2*d-1]=value;
                seeds[i*seed_stride+2*d]=value;
            }
        }
        xstar_spectral_stats_v1 ss{};
        xstar_spectral_stats_init_v1(&ss);
        std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> error{};
        const int rc = xstar_spectral_apply_contributions_v1(ctx.spectral_context, spectral.data(), spectral.size(), seeds.data(), seed_stride, &sw, &ss, error.data(), error.size());
        if (rc != 0) throw std::runtime_error(std::string("native spectral commit failed: ") + error.data());

        const std::size_t nlines=spectral.size();
        std::vector<double> dpthc(continuum_capacity,0.0), original(5*continuum_capacity,0.0), profiled(5*continuum_capacity,0.0);
        std::vector<double> elum(2*nlines,0.0), wavelength(nlines,0.0), mass(nlines,1.0), natural_rate(nlines,0.0), auger_width(nlines,0.0), auger_rate(nlines,0.0);
        std::vector<long long> slot(nlines,0), dtype(nlines,50);
        for (std::size_t j=0;j<nlines;++j) {
            const auto& c=spectral[j];
            const auto li=static_cast<std::size_t>(c.output_index);
            if (li>=line_capacity) throw std::runtime_error("line profile output index out of range");
            slot[j]=static_cast<long long>(j+1);
            dtype[j]=c.data_type;
            wavelength[j]=c.line_energy_eV>0.0?12398.4016/c.line_energy_eV:1.0e30;
            mass[j]=std::max(c.atomic_mass_amu,1.0e-30);
            auger_width[j]=std::max(c.natural_width_eV,0.0);
            elum[j]=fline[li];
            elum[nlines+j]=fline[line_capacity+li];
        }
        std::array<double,16> profile_stats{};
        std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> profile_error{};
        const int prc=xstar_emissivity_build_binemis_profile(
            static_cast<int>(continuum_capacity),20000,static_cast<int>(continuum_capacity),
            static_cast<int>(nlines),static_cast<int>(nlines),1.0,input.temperature_k/1.0e4,
            input.turbulent_velocity_km_s,input.radiation_energy_ev,dpthc.data(),elum.data(),
            original.data(),input.radiation_flux,slot.data(),wavelength.data(),dtype.data(),mass.data(),
            natural_rate.data(),auger_width.data(),auger_rate.data(),profiled.data(),profile_stats.data(),
            profile_error.data(),profile_error.size());
        if (prc!=0) throw std::runtime_error(std::string("native line emissivity profile failed: ")+profile_error.data());
        for (std::size_t k = 0; k < continuum_capacity; ++k) {
            output.spectrum[k] += cemab[k] + cemab[continuum_capacity + k]
                + rccemis[k] + rccemis[continuum_capacity + k]
                + profiled[2*continuum_capacity+k] + profiled[3*continuum_capacity+k];
            output.opacity[k] += opakcont[k];
        }
        stats.spectral_contributions += ss.contributions_committed;
    }
    stats.spectral_seconds += elapsed(spectral_start);

    output.total_heating = output.element_heating + output.continuum_heating;
    output.total_cooling = output.element_cooling + output.continuum_cooling;
    const double denom = std::max(std::abs(output.total_heating) + std::abs(output.total_cooling), 1.0e-300);
    output.hmctot = (output.total_heating - output.total_cooling) / denom;
    output.electron_fraction_xee = output.elcter;
    ctx.last_computed_electron_fraction = output.electron_fraction_xee;
    ctx.last_charge_residual = input.electron_fraction_xee - output.electron_fraction_xee;
    ctx.last_total_heating = output.total_heating;
    ctx.last_total_cooling = output.total_cooling;
    ctx.last_hmctot = output.hmctot;
    output.status_flags = stats.status_flags;
    if (input.dsec_radiation_bin_count > 0 || input.continuum_tau_count > 0)
        output.status_flags |= XSTAR_FIXED_STATE_STATUS_DSEC_RUNTIME_STATE_ABI;
    copy_text(output.message, sizeof(output.message), "native fixed-state raw program evaluated");
    ++ctx.state_generation;
    stats.state_generation = ctx.state_generation;
    stats.total_seconds += elapsed(total_start);
    copy_text(stats.message, sizeof(stats.message), "native fixed-state raw program evaluated");
    return 0;
}

} // namespace

struct xstar_fixed_state_context : xstar_fixed_state_context_impl {};

extern "C" {

uint32_t xstar_fixed_state_engine_abi_version(void) { return XSTAR_FIXED_STATE_ENGINE_ABI_VERSION; }
const char* xstar_fixed_state_engine_backend_name(void) { return "xstar_native_fixed_state_active_family_phase2_trajectory_v06485"; }
uint32_t xstar_fixed_state_engine_feature_flags(void) {
    return XSTAR_FIXED_STATE_STATUS_RAW_PROGRAM_LOADED |
        XSTAR_FIXED_STATE_STATUS_LINKED_TRAVERSAL |
        XSTAR_FIXED_STATE_STATUS_NATIVE_UCALC |
        XSTAR_FIXED_STATE_STATUS_NATIVE_ELEMENT_SOLVE |
        XSTAR_FIXED_STATE_STATUS_NATIVE_CONTINUUM |
        XSTAR_FIXED_STATE_STATUS_NATIVE_SPECTRAL |
        XSTAR_FIXED_STATE_STATUS_STATE_DEPENDENT |
        XSTAR_FIXED_STATE_STATUS_NO_CALLBACKS |
        XSTAR_FIXED_STATE_STATUS_ACTIVE_ATDB_LOWERED |
        XSTAR_FIXED_STATE_STATUS_DSEC_RUNTIME_STATE_ABI;
}

int xstar_fixed_state_input_init_v1(xstar_fixed_state_input_v1* input) {
    if (!input) return 1;
    std::memset(input, 0, sizeof(*input));
    input->struct_size = sizeof(*input);
    input->abi_version = XSTAR_FIXED_STATE_ENGINE_ABI_VERSION;
    input->temperature_k = 1.0e4;
    input->electron_density_cm3 = 1.0;
    input->hydrogen_density_cm3 = 1.0;
    input->electron_fraction_xee = 1.0;
    input->covering_fraction = 1.0;
    return 0;
}

int xstar_fixed_state_output_init_v1(xstar_fixed_state_output_v1* output) {
    if (!output) return 1;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->abi_version = XSTAR_FIXED_STATE_ENGINE_ABI_VERSION;
    return 0;
}

int xstar_fixed_state_stats_init_v1(xstar_fixed_state_stats_v1* stats) {
    if (!stats) return 1;
    std::memset(stats, 0, sizeof(*stats));
    stats->struct_size = sizeof(*stats);
    stats->abi_version = XSTAR_FIXED_STATE_ENGINE_ABI_VERSION;
    return 0;
}

int xstar_fixed_state_program_info_init_v1(xstar_fixed_state_program_info_v1* info) {
    if (!info) return 1;
    std::memset(info, 0, sizeof(*info));
    info->struct_size = sizeof(*info);
    info->abi_version = XSTAR_FIXED_STATE_ENGINE_ABI_VERSION;
    return 0;
}

int xstar_fixed_state_context_create_v1(const char* program_directory, xstar_fixed_state_context** context, char* message, size_t message_size) {
    if (!program_directory || !context) {
        copy_text(message, message_size, "program_directory and context are required");
        return 1;
    }
    *context = nullptr;
    try {
        auto ptr = std::make_unique<xstar_fixed_state_context>();
        ptr->program = load_program(program_directory);
        std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> error{};
        int rc = xstar_element_engine_context_create_v1(&ptr->element_context, error.data(), error.size());
        if (rc != 0) throw std::runtime_error(std::string("cannot create element context: ") + error.data());
        rc = xstar_spectral_context_create_v1(&ptr->spectral_context, error.data(), error.size());
        if (rc != 0) throw std::runtime_error(std::string("cannot create spectral context: ") + error.data());
        *context = ptr.release();
        copy_text(message, message_size, "native fixed-state raw program loaded");
        return 0;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return 4;
    }
}

void xstar_fixed_state_context_destroy(xstar_fixed_state_context* context) {
    if (!context) return;
    if (context->element_context) xstar_element_engine_context_destroy(context->element_context);
    if (context->spectral_context) xstar_spectral_context_destroy(context->spectral_context);
    delete context;
}

int xstar_fixed_state_context_get_program_info_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_state_program_info_v1* info,
    char* message,
    size_t message_size
) {
    if (!context || !info) {
        copy_text(message, message_size, "context and info are required");
        return 1;
    }
    if (info->struct_size < sizeof(*info) || info->abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) {
        copy_text(message, message_size, "fixed-state program-info ABI mismatch");
        return 2;
    }
    info->status_flags = XSTAR_FIXED_STATE_STATUS_RAW_PROGRAM_LOADED |
        (context->program.active_atdb_lowered ? static_cast<uint32_t>(XSTAR_FIXED_STATE_STATUS_ACTIVE_ATDB_LOWERED) : 0u);
    info->element_count = context->program.elements.size();
    info->population_rows = 0;
    for (const auto& element : context->program.elements) info->population_rows += static_cast<uint64_t>(element.n_rows);
    info->record_count = context->program.records.size();
    info->topology_record_count = context->program.topology_record_count;
    info->unsupported_record_count = context->program.unsupported_record_count;
    copy_text(info->program_id, sizeof(info->program_id), context->program.id);
    copy_text(info->message, sizeof(info->message), "native fixed-state program info available");
    copy_text(message, message_size, info->message);
    return 0;
}

int xstar_fixed_state_context_reset_v1(xstar_fixed_state_context* context, char* message, size_t message_size) {
    if (!context) return 1;
    std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> error{};
    if (xstar_element_engine_context_reset_v1(context->element_context, error.data(), error.size()) != 0) {
        copy_text(message, message_size, error.data());
        return 5;
    }
    if (xstar_spectral_context_reset_v1(context->spectral_context, error.data(), error.size()) != 0) {
        copy_text(message, message_size, error.data());
        return 5;
    }
    context->state_generation = 0;
    context->visited_data_types.clear();
    context->last_record_diagnostics.clear();
    context->last_element_diagnostics.clear();
    copy_text(message, message_size, "native fixed-state context reset");
    return 0;
}

int xstar_fixed_state_run_v1(xstar_fixed_state_context* context, const xstar_fixed_state_input_v1* input, xstar_fixed_state_output_v1* output, xstar_fixed_state_stats_v1* stats, char* message, size_t message_size) {
    if (!context || !input || !output || !stats) return 1;
    try {
        if (stats->struct_size < sizeof(*stats) || stats->abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) throw std::runtime_error("fixed-state stats ABI mismatch");
        const int rc = run_impl(*context, *input, *output, *stats);
        copy_text(message, message_size, output->message);
        return rc;
    } catch (const std::exception& exc) {
        copy_text(output->message, sizeof(output->message), exc.what());
        copy_text(stats->message, sizeof(stats->message), exc.what());
        copy_text(message, message_size, exc.what());
        return 7;
    }
}

int xstar_fixed_state_write_last_thermal_budget_v1(
    const xstar_fixed_state_context* context,
    const char* output_csv,
    uint64_t sequence,
    uint64_t call_index,
    uint64_t evaluation_index,
    const char* kind,
    char* message,
    size_t message_size
) {
    if (!context || !output_csv || !*output_csv || sequence == 0 || call_index == 0 || evaluation_index == 0) {
        copy_text(message, message_size, "context, output_csv, and positive indices are required");
        return 1;
    }
    try {
        const std::filesystem::path path(output_csv);
        if (path.has_parent_path()) std::filesystem::create_directories(path.parent_path());
        const bool write_header = !std::filesystem::exists(path) || std::filesystem::file_size(path) == 0;
        std::ofstream out(path, std::ios::app);
        if (!out) throw std::runtime_error("cannot create native thermal-budget ledger");
        if (write_header) {
            out << "sequence,kind,call_index,evaluation_index,temperature_k,electron_density_cm3,hydrogen_density_cm3,electron_fraction_input," 
                   "h_heating,h_cooling,h_heating2,h_cooling2,he_heating,he_cooling,he_heating2,he_cooling2," 
                   "he_type53_heating,he_type53_cooling,he_type53_heating2,he_type53_cooling2," 
                   "he_non_type53_heating,he_non_type53_cooling,he_non_type53_heating2,he_non_type53_cooling2," 
                   "mg_heating,mg_cooling,mg_heating2,mg_cooling2,element_heating,element_cooling,continuum_heating,continuum_cooling,total_heating,total_cooling,hmctot\n";
        }
        const auto budget = [&](int z) {
            const auto it = context->last_element_thermal_budget.find(z);
            return it == context->last_element_thermal_budget.end() ? std::array<double,4>{{0.0,0.0,0.0,0.0}} : it->second;
        };
        const auto h = budget(1);
        const auto he = budget(2);
        const auto mg = budget(12);
        const auto he53 = context->last_helium_type53_budget;
        std::array<double,4> he_other{{
            he[0]-he53[0], he[1]-he53[1], he[2]-he53[2], he[3]-he53[3]
        }};
        double element_heating = 0.0;
        double element_cooling = 0.0;
        for (const auto& item : context->last_element_thermal_budget) {
            element_heating += item.second[0] + item.second[2];
            element_cooling += item.second[1] + item.second[3];
        }
        const double continuum_heating = context->last_total_heating - element_heating;
        const double continuum_cooling = context->last_total_cooling - element_cooling;
        out << std::setprecision(17)
            << sequence << ',' << (kind && *kind ? kind : "dsec") << ',' << call_index << ',' << evaluation_index << ','
            << context->last_temperature_k << ',' << context->last_electron_density_cm3 << ',' << context->last_hydrogen_density_cm3 << ',' << context->last_electron_fraction_input << ','
            << h[0] << ',' << h[1] << ',' << h[2] << ',' << h[3] << ','
            << he[0] << ',' << he[1] << ',' << he[2] << ',' << he[3] << ','
            << he53[0] << ',' << he53[1] << ',' << he53[2] << ',' << he53[3] << ','
            << he_other[0] << ',' << he_other[1] << ',' << he_other[2] << ',' << he_other[3] << ','
            << mg[0] << ',' << mg[1] << ',' << mg[2] << ',' << mg[3] << ','
            << element_heating << ',' << element_cooling << ',' << continuum_heating << ',' << continuum_cooling << ','
            << context->last_total_heating << ',' << context->last_total_cooling << ',' << context->last_hmctot << '\n';
        copy_text(message, message_size, "native thermal-budget ledger written");
        return 0;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return 8;
    }
}

int xstar_fixed_state_write_visited_report_v1(const xstar_fixed_state_context* context, const char* output_path, char* message, size_t message_size) {
    if (!context || !output_path || !*output_path) {
        copy_text(message, message_size, "context and output_path are required");
        return 1;
    }
    try {
        std::ofstream out(output_path);
        if (!out) throw std::runtime_error("cannot create visited-record report");
        out << "data_type,visits\n";
        for (const auto& item : context->visited_data_types) out << item.first << ',' << item.second << '\n';
        copy_text(message, message_size, "visited-record report written");
        return 0;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return 8;
    }
}

int xstar_fixed_state_write_last_diagnostics_v1(
    const xstar_fixed_state_context* context,
    const char* output_directory,
    uint64_t evaluation_ordinal,
    char* message,
    size_t message_size
) {
    if (!context || !output_directory || !*output_directory || evaluation_ordinal == 0) {
        copy_text(message, message_size, "context, output_directory, and positive evaluation_ordinal are required");
        return 1;
    }
    try {
        if (context->last_record_diagnostics.empty() || context->last_element_diagnostics.empty()) {
            throw std::runtime_error("no completed fixed-state evaluation is available for diagnostics");
        }
        const std::filesystem::path root(output_directory);
        std::filesystem::create_directories(root);
        std::ostringstream stem_builder;
        stem_builder << "evaluation_" << std::setw(4) << std::setfill('0') << evaluation_ordinal;
        const std::string stem = stem_builder.str();

        std::vector<NativeRecordDiagnostic> records = context->last_record_diagnostics;
        std::stable_sort(records.begin(), records.end(), [](const NativeRecordDiagnostic& a, const NativeRecordDiagnostic& b) {
            return a.evaluated.contribution.source_position < b.evaluated.contribution.source_position;
        });
        std::ofstream record_file(root / (stem + "_records.csv"));
        if (!record_file) throw std::runtime_error("cannot create record diagnostics CSV");
        record_file << "evaluation_ordinal,source_position,record,element_index,element_z,data_type,rate_type,ion_index,ion_stage,lower_row,upper_row,matrix_enabled,active_stage,matrix_committed,spectral,ans1,ans2,ans3,ans4,ans5,ans6,density_scale,line_energy_ev,atomic_mass_amu,natural_width_ev,opakab,type53_shadow_valid,type53_shadow_ans1,type53_shadow_ans2,type53_shadow_ans3,type53_shadow_ans4,type53_shadow_ans5,type53_shadow_ans6,type53_delta_ans1,type53_delta_ans2,type53_delta_ans3,type53_delta_ans4,type53_delta_ans5,type53_delta_ans6,type53_shadow_threshold_ev,type53_shadow_rnist,type53_shadow_sumr,type53_shadow_sumi,type53_shadow_sumh,type53_shadow_sumh2,type53_shadow_sumc,type53_shadow_sumc2,type53_shadow_nb1_one_based,type53_shadow_klmax_one_based,type53_row46_contract,type53_captured_state_anchor,type53_tau_in,type53_tau_out,type53_ptmp1,type53_ptmp2,type53_covering_fraction,type53_runtime_state_abi_used,type53_continuum_index_one_based,type53_dsec_radiation_bin_count,type53_continuum_tau_count\n";
        record_file << std::setprecision(17);

        struct FamilySummary {
            std::uint64_t records = 0;
            std::uint64_t matrix_enabled = 0;
            std::uint64_t active_stage = 0;
            std::uint64_t matrix_committed = 0;
            std::uint64_t spectral = 0;
            std::int64_t first_source_position = 0;
            std::int64_t last_source_position = 0;
            std::array<double,6> sums{};
            std::array<double,6> l1{};
        };
        std::map<int, FamilySummary> summaries;
        for (const auto& diagnostic : records) {
            const auto& item = diagnostic.evaluated;
            const auto& c = item.contribution;
            record_file << evaluation_ordinal << ',' << c.source_position << ',' << c.record << ','
                        << diagnostic.element_index << ',' << diagnostic.element_z << ',' << c.data_type << ',' << c.rate_type << ','
                        << c.ion_index << ',' << c.ion_stage << ',' << c.lower_row << ',' << c.upper_row << ','
                        << (item.matrix_enabled ? 1 : 0) << ',' << (diagnostic.active_stage ? 1 : 0) << ','
                        << (diagnostic.matrix_committed ? 1 : 0) << ',' << (item.spectral ? 1 : 0) << ','
                        << c.ans1 << ',' << c.ans2 << ',' << c.ans3 << ',' << c.ans4 << ',' << c.ans5 << ',' << c.ans6 << ','
                        << c.density_scale << ',' << item.line_energy_ev << ',' << item.atomic_mass_amu << ','
                        << item.natural_width_ev << ',' << item.opakab << ','
                        << (item.type53_shadow.valid ? 1 : 0);
            for (std::size_t k = 0; k < item.type53_shadow.ans.size(); ++k) {
                record_file << ',' << item.type53_shadow.ans[k];
            }
            const std::array<double,6> applied_values{c.ans1,c.ans2,c.ans3,c.ans4,c.ans5,c.ans6};
            for (std::size_t k = 0; k < item.type53_shadow.ans.size(); ++k) {
                record_file << ',' << (item.type53_shadow.ans[k] - applied_values[k]);
            }
            record_file << ',' << item.type53_shadow.threshold_ev << ',' << item.type53_shadow.rnist
                        << ',' << item.type53_shadow.sumr << ',' << item.type53_shadow.sumi
                        << ',' << item.type53_shadow.sumh << ',' << item.type53_shadow.sumh2
                        << ',' << item.type53_shadow.sumc << ',' << item.type53_shadow.sumc2
                        << ',' << item.type53_shadow.nb1_one_based << ',' << item.type53_shadow.klmax_one_based
                        << ',' << (item.type53_shadow.row46_contract ? 1 : 0)
                        << ',' << (item.type53_shadow.captured_state_anchor ? 1 : 0)
                        << ',' << item.type53_shadow.tau_in << ',' << item.type53_shadow.tau_out
                        << ',' << item.type53_shadow.ptmp1 << ',' << item.type53_shadow.ptmp2
                        << ',' << item.type53_shadow.covering_fraction
                        << ',' << (item.type53_shadow.runtime_state_abi_used ? 1 : 0)
                        << ',' << item.type53_shadow.continuum_index_one_based
                        << ',' << item.type53_shadow.dsec_radiation_bin_count
                        << ',' << item.type53_shadow.continuum_tau_count << '\n';
            auto& summary = summaries[c.data_type];
            if (summary.records == 0) summary.first_source_position = c.source_position;
            summary.last_source_position = c.source_position;
            ++summary.records;
            summary.matrix_enabled += item.matrix_enabled ? 1u : 0u;
            summary.active_stage += diagnostic.active_stage ? 1u : 0u;
            summary.matrix_committed += diagnostic.matrix_committed ? 1u : 0u;
            summary.spectral += item.spectral ? 1u : 0u;
            const std::array<double,6> values{c.ans1,c.ans2,c.ans3,c.ans4,c.ans5,c.ans6};
            for (std::size_t k=0;k<values.size();++k) {
                summary.sums[k] += values[k];
                summary.l1[k] += std::abs(values[k]);
            }
        }

        std::ofstream family_file(root / (stem + "_family_summary.csv"));
        if (!family_file) throw std::runtime_error("cannot create family summary CSV");
        family_file << "evaluation_ordinal,data_type,records,matrix_enabled,active_stage,matrix_committed,spectral,first_source_position,last_source_position,sum_ans1,sum_ans2,sum_ans3,sum_ans4,sum_ans5,sum_ans6,l1_ans1,l1_ans2,l1_ans3,l1_ans4,l1_ans5,l1_ans6\n";
        family_file << std::setprecision(17);
        for (const auto& entry : summaries) {
            const auto& value = entry.second;
            family_file << evaluation_ordinal << ',' << entry.first << ',' << value.records << ',' << value.matrix_enabled << ','
                        << value.active_stage << ',' << value.matrix_committed << ',' << value.spectral << ','
                        << value.first_source_position << ',' << value.last_source_position;
            for (double x : value.sums) family_file << ',' << x;
            for (double x : value.l1) family_file << ',' << x;
            family_file << '\n';
        }

        std::ofstream element_file(root / (stem + "_elements.csv"));
        std::ofstream ion_file(root / (stem + "_ion_balance.csv"));
        std::ofstream population_file(root / (stem + "_populations.csv"));
        if (!element_file || !ion_file || !population_file) throw std::runtime_error("cannot create element diagnostics CSV files");
        element_file << "evaluation_ordinal,element_index,element_z,abundance,active_min_stage,active_max_stage,active_full_row_start,active_full_row_end,heating,cooling,heating2,cooling2,normalization,normalization_error,max_relative_row_residual,records_constructed,terms_constructed\n";
        ion_file << "evaluation_ordinal,element_index,element_z,stage,ion_charge,preliminary_ionization,preliminary_recombination,preliminary_fraction,final_fraction,active_stage\n";
        population_file << "evaluation_ordinal,global_population_row,element_index,element_z,element_row,superlevel,ion,ion_charge,energy_ev,statistical_weight,initial_population,final_population,active_row\n";
        element_file << std::setprecision(17);
        ion_file << std::setprecision(17);
        population_file << std::setprecision(17);
        std::size_t global_offset = 0;
        for (const auto& diagnostic : context->last_element_diagnostics) {
            const auto& source = context->program.elements.at(static_cast<std::size_t>(diagnostic.element_index));
            element_file << evaluation_ordinal << ',' << diagnostic.element_index << ',' << diagnostic.element_z << ',' << diagnostic.abundance << ','
                         << diagnostic.active.min_stage << ',' << diagnostic.active.max_stage << ',' << diagnostic.active.full_row_start << ','
                         << diagnostic.active.full_row_end << ',' << diagnostic.heating << ',' << diagnostic.cooling << ',' << diagnostic.heating2 << ','
                         << diagnostic.cooling2 << ',' << diagnostic.normalization << ',' << diagnostic.normalization_error << ','
                         << diagnostic.max_relative_row_residual << ',' << diagnostic.records_constructed << ',' << diagnostic.terms_constructed << '\n';
            for (int stage=1; stage<=diagnostic.element_z+1; ++stage) {
                const std::size_t index=static_cast<std::size_t>(stage-1);
                const double ionization = index < diagnostic.preliminary.ionization.size() ? diagnostic.preliminary.ionization[index] : 0.0;
                const double recombination = index < diagnostic.preliminary.recombination.size() ? diagnostic.preliminary.recombination[index] : 0.0;
                const double preliminary_fraction = index < diagnostic.preliminary.fractions.size() ? diagnostic.preliminary.fractions[index] : 0.0;
                const double final_fraction = index < diagnostic.final_stage_fractions.size() ? diagnostic.final_stage_fractions[index] : 0.0;
                const bool active_stage = stage >= diagnostic.active.min_stage && stage <= diagnostic.active.max_stage + 1;
                ion_file << evaluation_ordinal << ',' << diagnostic.element_index << ',' << diagnostic.element_z << ',' << stage << ',' << stage-1 << ','
                         << ionization << ',' << recombination << ',' << preliminary_fraction << ',' << final_fraction << ',' << (active_stage ? 1 : 0) << '\n';
            }
            for (std::size_t row_index=0; row_index<source.rows.size(); ++row_index) {
                const auto& row = source.rows[row_index];
                const double final_population = row_index < diagnostic.full_populations.size() ? diagnostic.full_populations[row_index] : 0.0;
                const bool active_row = row.row >= diagnostic.active.full_row_start && row.row <= diagnostic.active.full_row_end;
                population_file << evaluation_ordinal << ',' << global_offset + row_index + 1 << ',' << diagnostic.element_index << ',' << diagnostic.element_z << ','
                                << row.row << ',' << row.superlevel << ',' << row.ion << ',' << row.ion_charge << ',' << row.energy_ev << ','
                                << row.statistical_weight << ',' << row.initial_population << ',' << final_population << ',' << (active_row ? 1 : 0) << '\n';
            }
            global_offset += source.rows.size();
        }

        if (context->last_helium_solve_response) {
            const NativeElementDiagnostic* helium = nullptr;
            for (const auto& diagnostic : context->last_element_diagnostics) {
                if (diagnostic.element_z == 2 && diagnostic.solve_response_captured) {
                    helium = &diagnostic;
                    break;
                }
            }
            if (!helium) throw std::runtime_error("helium solve-response diagnostics were requested but not captured");
            const auto& source = context->program.elements.at(static_cast<std::size_t>(helium->element_index));
            const int n = helium->active.element.n_rows;
            if (helium->dense_matrix.size() != static_cast<std::size_t>(n * n) ||
                helium->rhs.size() != static_cast<std::size_t>(n) ||
                helium->active_final_populations.size() != static_cast<std::size_t>(n)) {
                throw std::runtime_error("helium solve-response buffer dimensions are inconsistent");
            }

            std::ofstream solve_rows(root / (stem + "_helium_solve_rows.csv"));
            std::ofstream solve_matrix(root / (stem + "_helium_solve_matrix.csv"));
            std::ofstream solve_terms(root / (stem + "_helium_source_order_terms.csv"));
            if (!solve_rows || !solve_matrix || !solve_terms) {
                throw std::runtime_error("cannot create helium solve-response CSV files");
            }
            solve_rows << "evaluation_ordinal,compact_row,full_row,superlevel,ion,ion_charge,energy_ev,statistical_weight,is_normalization_row,initial_population,final_outer_start_population,final_population,rhs,native_row_residual,native_row_scale,native_relative_row_residual\n";
            solve_rows << std::setprecision(17);
            for (int compact_row = 1; compact_row <= n; ++compact_row) {
                const int full_row = helium->active.full_row_start + compact_row - 1;
                const auto& row = source.rows.at(static_cast<std::size_t>(full_row - 1));
                const std::size_t index = static_cast<std::size_t>(compact_row - 1);
                solve_rows << evaluation_ordinal << ',' << compact_row << ',' << full_row << ','
                           << row.superlevel << ',' << row.ion << ',' << row.ion_charge << ','
                           << row.energy_ev << ',' << row.statistical_weight << ','
                           << (compact_row == helium->active.element.normalization_row ? 1 : 0) << ','
                           << helium->active_initial_populations.at(index) << ','
                           << helium->active_final_outer_start_populations.at(index) << ','
                           << helium->active_final_populations.at(index) << ','
                           << helium->rhs.at(index) << ','
                           << helium->row_residual.at(index) << ','
                           << helium->row_scale.at(index) << ','
                           << helium->relative_row_residual.at(index) << '\n';
            }

            solve_matrix << "evaluation_ordinal,compact_row,compact_column,full_row,full_column,dense_value,heating_value,heating2_value\n";
            solve_matrix << std::setprecision(17);
            for (int compact_row = 1; compact_row <= n; ++compact_row) {
                for (int compact_column = 1; compact_column <= n; ++compact_column) {
                    const std::size_t index = static_cast<std::size_t>((compact_row - 1) * n + compact_column - 1);
                    solve_matrix << evaluation_ordinal << ',' << compact_row << ',' << compact_column << ','
                                 << helium->active.full_row_start + compact_row - 1 << ','
                                 << helium->active.full_row_start + compact_column - 1 << ','
                                 << helium->dense_matrix.at(index) << ','
                                 << helium->heating_matrix.at(index) << ','
                                 << helium->heating_matrix2.at(index) << '\n';
                }
            }

            solve_terms << "evaluation_ordinal,source_order_index,contribution_source_position,term_source_position,record,data_type,rate_type,ion_index,ion_stage,role,compact_row,compact_column,full_row,full_column,aj1,aj2,cj,cj2,density_scale\n";
            solve_terms << std::setprecision(17);
            std::uint64_t source_order_index = 0;
            std::vector<const NativeRecordDiagnostic*> ordered_helium_records;
            for (const auto& diagnostic : records) {
                if (diagnostic.element_z == 2 && diagnostic.matrix_committed) ordered_helium_records.push_back(&diagnostic);
            }
            if (context->last_type53_row46_coupled_replacement) {
                std::vector<std::optional<const NativeRecordDiagnostic*>> slots(ordered_helium_records.size());
                std::vector<const NativeRecordDiagnostic*> remainder;
                for (const auto* diagnostic : ordered_helium_records) {
                    const int slot = type53_row46_original_contribution_slot(diagnostic->evaluated.contribution);
                    if (slot >= 0) {
                        if (slot >= static_cast<int>(slots.size()) || slots[static_cast<std::size_t>(slot)].has_value()) {
                            throw std::runtime_error("type53 row46 diagnostic source-order slot invalid");
                        }
                        slots[static_cast<std::size_t>(slot)] = diagnostic;
                    } else remainder.push_back(diagnostic);
                }
                std::size_t next = 0;
                ordered_helium_records.clear();
                for (auto& slot : slots) {
                    if (!slot.has_value()) slot = remainder.at(next++);
                    ordered_helium_records.push_back(*slot);
                }
            }
            for (const auto* diagnostic_ptr : ordered_helium_records) {
                const auto& diagnostic = *diagnostic_ptr;
                const auto& c = diagnostic.evaluated.contribution;
                const int lower = c.lower_row - helium->active.full_row_start + 1;
                const int upper = c.upper_row - helium->active.full_row_start + 1;
                if (lower < 1 || lower > n || upper < 1 || upper > n) continue;
                const int rows4[4] = {upper, lower, lower, upper};
                const int cols4[4] = {lower, upper, lower, upper};
                const char* roles[4] = {"forward_gain", "reverse_gain", "forward_diag_loss", "reverse_diag_loss"};
                const double aj1[4] = {c.ans1, c.ans2, -c.ans1, -c.ans2};
                const double aj2[4] = {c.ans2, c.ans1, -c.ans1, -c.ans2};
                const double cj[4] = {0.0, 0.0, c.ans4 * c.density_scale, -c.ans3 * c.density_scale};
                const double cj2[4] = {0.0, 0.0, c.ans6 * c.density_scale, -c.ans5 * c.density_scale};
                for (int offset = 0; offset < 4; ++offset) {
                    ++source_order_index;
                    solve_terms << evaluation_ordinal << ',' << source_order_index << ',' << c.source_position << ','
                                << c.source_position + offset << ',' << c.record << ',' << c.data_type << ','
                                << c.rate_type << ',' << c.ion_index << ',' << c.ion_stage << ',' << roles[offset] << ','
                                << rows4[offset] << ',' << cols4[offset] << ','
                                << helium->active.full_row_start + rows4[offset] - 1 << ','
                                << helium->active.full_row_start + cols4[offset] - 1 << ','
                                << aj1[offset] << ',' << aj2[offset] << ',' << cj[offset] << ',' << cj2[offset] << ','
                                << c.density_scale << '\n';
                }
            }

            std::ofstream solve_state(root / (stem + "_helium_solve_state.json"));
            if (!solve_state) throw std::runtime_error("cannot create helium solve-response state JSON");
            solve_state << std::setprecision(17)
                        << "{\n  \"schema\": \"xstar-tools-v0648711-helium-solve-response-state-v1\",\n"
                        << "  \"release\": \"0.6.48.7.21.1\",\n"
                        << "  \"evaluation_ordinal\": " << evaluation_ordinal << ",\n"
                        << "  \"active_full_row_start\": " << helium->active.full_row_start << ",\n"
                        << "  \"active_full_row_end\": " << helium->active.full_row_end << ",\n"
                        << "  \"compact_row_count\": " << n << ",\n"
                        << "  \"normalization_compact_row\": " << helium->active.element.normalization_row << ",\n"
                        << "  \"normalization_full_row\": " << helium->active.full_row_start + helium->active.element.normalization_row - 1 << ",\n"
                        << "  \"solver_method\": \"" << helium->solver_method << "\",\n"
                        << "  \"solver_status_flags\": " << helium->solver_status_flags << ",\n"
                        << "  \"outer_iterations\": " << helium->outer_iterations << ",\n"
                        << "  \"fixed_point_iterations\": " << helium->fixed_point_iterations << ",\n"
                        << "  \"source_order_term_count\": " << source_order_index << ",\n"
                        << "  \"type53_row46_coupled_replacement\": " << (context->last_type53_row46_coupled_replacement ? "true" : "false") << ",\n"
                        << "  \"qualification_only\": true,\n"
                        << "  \"production_promotion_ready\": false\n}\n";
        }

        std::ofstream state_file(root / (stem + "_state.json"));
        if (!state_file) throw std::runtime_error("cannot create state diagnostics JSON");
        state_file << std::setprecision(17)
                   << "{\n  \"schema_version\": \"0.6.48.7.21.1\",\n  \"qualification_only\": true,\n"
                   << "  \"evaluation_ordinal\": " << evaluation_ordinal << ",\n"
                   << "  \"program_id\": \"" << context->program.id << "\",\n"
                   << "  \"temperature_k\": " << context->last_temperature_k << ",\n"
                   << "  \"electron_density_cm3\": " << context->last_electron_density_cm3 << ",\n"
                   << "  \"hydrogen_density_cm3\": " << context->last_hydrogen_density_cm3 << ",\n"
                   << "  \"electron_fraction_input\": " << context->last_electron_fraction_input << ",\n"
                   << "  \"computed_electron_fraction\": " << context->last_computed_electron_fraction << ",\n"
                   << "  \"charge_residual\": " << context->last_charge_residual << ",\n"
                   << "  \"total_heating\": " << context->last_total_heating << ",\n"
                   << "  \"total_cooling\": " << context->last_total_cooling << ",\n"
                   << "  \"hmctot\": " << context->last_hmctot << ",\n"
                   << "  \"radiation_bin_count\": " << context->last_radiation_bin_count << ",\n"
                   << "  \"helium_matrix_ablation_type\": " << context->last_helium_matrix_ablation_type << ",\n"
                   << "  \"helium_preliminary_ablation_type\": " << context->last_helium_preliminary_ablation_type << ",\n"
                   << "  \"helium_source_position_ablation\": " << context->last_helium_source_position_ablation << ",\n"
                   << "  \"helium_matrix_ablation_row_type\": " << context->last_helium_matrix_ablation_row_type << ",\n"
                   << "  \"helium_matrix_ablation_row_min\": " << context->last_helium_matrix_ablation_row_min << ",\n"
                   << "  \"helium_matrix_ablation_row_max\": " << context->last_helium_matrix_ablation_row_max << ",\n"
                   << "  \"helium_unqualified_type53_ablation\": " << (context->last_helium_unqualified_type53_ablation ? "true" : "false") << ",\n"
                   << "  \"helium_unqualified_type71_ablation\": " << (context->last_helium_unqualified_type71_ablation ? "true" : "false") << ",\n"
                   << "  \"helium_unqualified_type99_ablation\": " << (context->last_helium_unqualified_type99_ablation ? "true" : "false") << ",\n"
                   << "  \"helium_solve_response\": " << (context->last_helium_solve_response ? "true" : "false") << ",\n"
                   << "  \"type53_row46_coupled_replacement\": " << (context->last_type53_row46_coupled_replacement ? "true" : "false") << ",\n"
                   << "  \"record_diagnostic_count\": " << records.size() << ",\n"
                   << "  \"element_diagnostic_count\": " << context->last_element_diagnostics.size() << ",\n"
                   << "  \"production_promotion_ready\": false\n}\n";
        copy_text(message, message_size, "source-ordered fixed-state diagnostics written");
        return 0;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return 8;
    }
}

int xstar_fixed_state_run_batch_v1(xstar_fixed_state_context* context, const xstar_fixed_state_input_v1* inputs, size_t input_count, xstar_fixed_state_output_v1* outputs, xstar_fixed_state_stats_v1* stats, char* message, size_t message_size) {
    if (!context || (!inputs && input_count) || (!outputs && input_count) || !stats) return 1;
    for (std::size_t k = 0; k < input_count; ++k) {
        const int rc = xstar_fixed_state_run_v1(context, &inputs[k], &outputs[k], stats, message, message_size);
        if (rc != 0) return rc;
    }
    copy_text(message, message_size, "native fixed-state batch evaluated");
    return 0;
}

} // extern "C"
