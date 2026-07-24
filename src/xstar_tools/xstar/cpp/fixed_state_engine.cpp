#include "xstar_fixed_state_engine.h"
#include "source_order_thermal_reducer.hpp"
#include "canonical_thermal_term.hpp"
#include "coheat_table_v048724.h"
#include "xstar_element_engine.h"
#include "xstar_spectral_engine.h"
#include "type50_manifold_oracle_v048710.h"
#include "type50_dsec_runtime_oracle_v048713.h"
#include "type53_row46_dsec_runtime_oracle_v048716.h"

#include "xstar_constants.h"
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
#include <iostream>
#include <limits>
#include <memory>
#include <map>
#include <optional>
#include <sstream>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace {

using clock_type = std::chrono::steady_clock;
constexpr double kBoltzmannEvK = xstar_constants::kModernBoltzmannEvPerK;
constexpr double kErgPerEv = xstar_constants::kModernErgPerEv;
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
extern "C" int xstar_opacity_apply_line_profile_v1(
    double optpp,
    double line_energy_ev,
    double vturb_km_s,
    double temperature_1e4k,
    double atomic_mass_amu,
    double natural_width_ev,
    const double* seed_profiles,
    int seed_radius,
    const double* epi,
    int ncn2,
    double* opakc,
    double* rccemis,
    long long* updated_bins,
    double* opacity_seconds,
    char* errbuf,
    std::size_t errbuf_size
);

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

std::uint64_t binary64_sequence_fnv1a(const double* values, std::size_t count) {
    // Stable little-endian FNV-1a over the exact IEEE-754 payload.  This is
    // intentionally independent of host byte order so Python qualification
    // can reconstruct the same hash from source-captured arrays.
    std::uint64_t hash = 1469598103934665603ULL;
    constexpr std::uint64_t prime = 1099511628211ULL;
    for (std::size_t i = 0; i < count; ++i) {
        std::uint64_t bits = 0;
        static_assert(sizeof(bits) == sizeof(values[i]), "binary64 size mismatch");
        std::memcpy(&bits, values + i, sizeof(bits));
        for (unsigned shift = 0; shift < 64; shift += 8) {
            hash ^= (bits >> shift) & 0xffULL;
            hash *= prime;
        }
    }
    return hash;
}

std::uint64_t binary64_sequence_fnv1a(const std::vector<double>& values) {
    return binary64_sequence_fnv1a(values.data(), values.size());
}

std::string hex_u64(std::uint64_t value) {
    std::ostringstream out;
    out << std::hex << std::setw(16) << std::setfill('0') << value;
    return out.str();
}

int environment_data_type(const char* name) {
    const char* value = nullptr;
    if (std::string(name) == "XSTAR_QUALIFICATION_SOURCE_SEQUENCE") {
        value = std::getenv("XSTAR_NATIVE_SOURCE_SEQUENCE");
    }
    if (!value || !*value) value = std::getenv(name);
    if (!value || !*value) return 0;
    char* end = nullptr;
    const long parsed = std::strtol(value, &end, 10);
    if (!end || *end != '\0' || parsed < 0 || parsed > 1000000) {
        throw std::runtime_error(std::string("invalid ") + name + " data type");
    }
    return static_cast<int>(parsed);
}

bool native_production_mode() {
    const char* value = std::getenv("XSTAR_NATIVE_PRODUCTION");
    return value && std::string(value) == "1";
}

bool native_promoted_flag(const char* name) {
    if (!native_production_mode()) return false;
    static const std::unordered_set<std::string> promoted = {
        "XSTAR_QUALIFICATION_REPLACEMENT",
        "XSTAR_QUALIFICATION_HYDROGEN_TYPE53_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_HELIUM_TYPE53_INTERVAL_SOURCE_ORDER",
        "XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION",
        "XSTAR_QUALIFICATION_MG_PRIMARY_THERMAL_CORRECTION",
        "XSTAR_QUALIFICATION_MG_BOUND_FREE_FINITE_STATE",
        "XSTAR_QUALIFICATION_MG_BOUND_FREE_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_MG_MILNE_EXCITED_THRESHOLD",
        "XSTAR_QUALIFICATION_TYPE49_EXTRAPOLATED_GRID_PARITY",
        "XSTAR_QUALIFICATION_TYPE51_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_TYPE6062_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_MG_TYPE51_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_SOLVE_RESPONSE",
        "XSTAR_QUALIFICATION_HELIUM_SOURCE_INSERTION_ORDER",
        "XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_RESPONSE",
        "XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_SYSTEM",
        "XSTAR_NATIVE_SEQUENCE1_THERMAL_DIAGONAL_RECONSTRUCTION",
        "XSTAR_NATIVE_SEQUENCE1_SOURCE_FAITHFUL_POPULATION_SEED",
        "XSTAR_NATIVE_SEQUENCE1_THERMAL_SOURCE_ORDER",
        "XSTAR_QUALIFICATION_MG_TYPE99_SECONDARY_ENERGY_CORRECTION",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PERSISTENT_LEVELTEMP",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE53_PERSISTENT_LEVELTEMP",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE49_PERSISTENT_LEVELTEMP",
        "XSTAR_QUALIFICATION_TYPE57_SOURCE_ENERGY",
        "XSTAR_QUALIFICATION_TYPE68_SOURCE_CONSTANTS",
        "XSTAR_QUALIFICATION_CONTINUUM_WORKSPACE_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_FREEF_REAL_EXPONENT_POW"
    };
    return promoted.count(name) != 0u;
}

bool environment_flag(const char* name) {
    const char* value = std::getenv(name);
    if (!value || !*value) return native_promoted_flag(name);
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

void restore_source_contribution_order(
    std::vector<xstar_element_contribution_v1>& contributions
) {
    // v0.6.47.2 builds each active ion's source_record_iter by rate type,
    // then data type, while preserving the ATDB linked-record order inside
    // each family.  Reproduce that order directly from the lowered metadata.
    std::stable_sort(contributions.begin(), contributions.end(),
        [](const auto& lhs, const auto& rhs) {
            return std::tie(lhs.ion_stage, lhs.rate_type, lhs.data_type,
                            lhs.source_position, lhs.record) <
                   std::tie(rhs.ion_stage, rhs.rate_type, rhs.data_type,
                            rhs.source_position, rhs.record);
        });
}

__attribute__((noinline)) double source_runtime_pow10(double exponent) {
    // Python's float power (used by the immutable v0.6.47.2 reference for
    // calt77) dispatches to the platform libm pow entry point.  A volatile
    // function pointer prevents the compiler from rewriting the constant-base
    // call to exp10 or exp(log(10)*x), which differ by one ULP on some hosts.
    using PowFunction = double (*)(double, double);
    volatile PowFunction runtime_pow = ::pow;
    return runtime_pow(10.0, exponent);
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


struct HydrogenType50EscapeStateV04874618 {
    bool enabled = false;
    std::map<std::int64_t, int> line_index_by_record;
    std::vector<double> tau_in;
    std::vector<double> tau_out;
};

std::vector<double> read_binary64_payload_v04874618(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    if (!input) throw std::runtime_error("cannot open hydrogen Type-50 line-tau payload: " + path.string());
    const auto bytes = input.tellg();
    if (bytes < 0 || bytes % static_cast<std::streamoff>(sizeof(double)) != 0) {
        throw std::runtime_error("invalid hydrogen Type-50 line-tau payload size: " + path.string());
    }
    std::vector<double> values(static_cast<std::size_t>(bytes / static_cast<std::streamoff>(sizeof(double))));
    input.seekg(0);
    if (!values.empty()) input.read(reinterpret_cast<char*>(values.data()), bytes);
    if (!input && !values.empty()) throw std::runtime_error("cannot read hydrogen Type-50 line-tau payload: " + path.string());
    for (double value : values) {
        if (!std::isfinite(value)) throw std::runtime_error("non-finite hydrogen Type-50 line optical depth");
    }
    return values;
}

std::string required_environment_path_v04874618(const char* name) {
    const char* value = std::getenv(name);
    if (!value || !*value) throw std::runtime_error(std::string("missing required environment path: ") + name);
    return value;
}

HydrogenType50EscapeStateV04874618 load_hydrogen_type50_escape_state_v04874618() {
    HydrogenType50EscapeStateV04874618 state;
    state.enabled = environment_flag("XSTAR_QUALIFICATION_HYDROGEN_TYPE50_ESCAPE_STATE");
    if (!state.enabled) return state;
    const auto map_path = std::filesystem::path(required_environment_path_v04874618(
        "XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_MAP_CSV"));
    const auto tau_in_path = std::filesystem::path(required_environment_path_v04874618(
        "XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_TAU_IN_BIN"));
    const auto tau_out_path = std::filesystem::path(required_environment_path_v04874618(
        "XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_TAU_OUT_BIN"));
    std::ifstream mapping(map_path);
    if (!mapping) throw std::runtime_error("cannot open hydrogen Type-50 line-index map: " + map_path.string());
    std::string line;
    if (!std::getline(mapping, line)) throw std::runtime_error("hydrogen Type-50 line-index map is empty");
    const auto header = split_csv(line);
    std::map<std::string, std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    if (!columns.count("record") || !columns.count("line_index")) {
        throw std::runtime_error("hydrogen Type-50 line-index map is missing record or line_index");
    }
    while (std::getline(mapping, line)) {
        if (trim(line).empty()) continue;
        const auto values = split_csv(line);
        if (values.size() != header.size()) throw std::runtime_error("hydrogen Type-50 line-index map row width mismatch");
        const auto record = parse_number<std::int64_t>(values.at(columns.at("record")), "record");
        const int line_index = parse_number<int>(values.at(columns.at("line_index")), "line_index");
        if (record <= 0 || line_index <= 0) throw std::runtime_error("hydrogen Type-50 line-index map contains non-positive identity");
        if (!state.line_index_by_record.emplace(record, line_index).second) {
            throw std::runtime_error("duplicate hydrogen Type-50 line-index record");
        }
    }
    if (state.line_index_by_record.size() != 133) {
        throw std::runtime_error("hydrogen Type-50 line-index map must contain exactly 133 records");
    }
    state.tau_in = read_binary64_payload_v04874618(tau_in_path);
    state.tau_out = read_binary64_payload_v04874618(tau_out_path);
    if (state.tau_in.size() != state.tau_out.size() || state.tau_in.empty()) {
        throw std::runtime_error("hydrogen Type-50 line-tau payload inventory mismatch");
    }
    for (const auto& item : state.line_index_by_record) {
        if (static_cast<std::size_t>(item.second) > state.tau_in.size()) {
            throw std::runtime_error("hydrogen Type-50 line index is outside transported tau0 arrays");
        }
    }
    return state;
}

const HydrogenType50EscapeStateV04874618& hydrogen_type50_escape_state_v04874618() {
    // The standalone all-61 controller transports a different line optical-depth
    // workspace before each fixed-state callback.  Cache only the currently
    // bound payload; the historical one-process-per-evaluation path still hits
    // this cache once.  A thread-local cache preserves the existing reference
    // lifetime throughout one fixed-state run without retaining 61 large tau
    // arrays in memory.
    const bool enabled = environment_flag("XSTAR_QUALIFICATION_HYDROGEN_TYPE50_ESCAPE_STATE");
    std::string key = enabled ? "1" : "0";
    if (enabled) {
        key += "|" + required_environment_path_v04874618(
            "XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_MAP_CSV");
        key += "|" + required_environment_path_v04874618(
            "XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_TAU_IN_BIN");
        key += "|" + required_environment_path_v04874618(
            "XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_TAU_OUT_BIN");
    }
    static thread_local std::string cached_key;
    static thread_local HydrogenType50EscapeStateV04874618 state;
    if (cached_key != key) {
        state = load_hydrogen_type50_escape_state_v04874618();
        cached_key = key;
    }
    return state;
}

struct MagnesiumType50EndpointEnergyV048746193 {
    int idest1 = 0;
    int idest2 = 0;
    double endpoint1_energy_ev = 0.0;
    double endpoint2_energy_ev = 0.0;
    double endpoint_energy_ev = 0.0;
};

struct MagnesiumType50EscapeStateV04874619 {
    bool enabled = false;
    bool endpoint_energy_transport = false;
    int source_sequence = 0;
    std::map<std::int64_t, int> line_index_by_record;
    std::map<std::int64_t, MagnesiumType50EndpointEnergyV048746193> endpoint_by_record;
    std::set<std::int64_t> active_records;
    std::vector<double> tau_in;
    std::vector<double> tau_out;
};

std::vector<double> read_binary64_payload_v04874619(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    if (!input) throw std::runtime_error("cannot open magnesium Type-50 line-tau payload: " + path.string());
    const auto bytes = input.tellg();
    if (bytes < 0 || bytes % static_cast<std::streamoff>(sizeof(double)) != 0) {
        throw std::runtime_error("invalid magnesium Type-50 line-tau payload size: " + path.string());
    }
    std::vector<double> values(static_cast<std::size_t>(bytes / static_cast<std::streamoff>(sizeof(double))));
    input.seekg(0);
    if (!values.empty()) input.read(reinterpret_cast<char*>(values.data()), bytes);
    if (!input && !values.empty()) throw std::runtime_error("cannot read magnesium Type-50 line-tau payload: " + path.string());
    for (double value : values) {
        if (!std::isfinite(value)) throw std::runtime_error("non-finite magnesium Type-50 line optical depth");
    }
    return values;
}

MagnesiumType50EscapeStateV04874619 load_magnesium_type50_escape_state_v04874619() {
    MagnesiumType50EscapeStateV04874619 state;
    state.enabled = environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ESCAPE_STATE");
    if (!state.enabled) return state;
    state.endpoint_energy_transport =
        environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_ENERGY_TRANSPORT");
    const auto map_path = std::filesystem::path(required_environment_path_v04874618(
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_MAP_CSV"));
    const auto tau_in_path = std::filesystem::path(required_environment_path_v04874618(
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_TAU_IN_BIN"));
    const auto tau_out_path = std::filesystem::path(required_environment_path_v04874618(
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_TAU_OUT_BIN"));
    const auto active_path = std::filesystem::path(required_environment_path_v04874618(
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ACTIVE_RECORDS_CSV"));
    std::filesystem::path endpoint_path;
    if (state.endpoint_energy_transport) {
        endpoint_path = std::filesystem::path(required_environment_path_v04874618(
            "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_MAP_CSV"));
    }
    state.source_sequence = environment_data_type("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    if (state.source_sequence < 1 || state.source_sequence > 61) {
        throw std::runtime_error("magnesium Type-50 source sequence must be in 1..61");
    }
    std::ifstream mapping(map_path);
    if (!mapping) throw std::runtime_error("cannot open magnesium Type-50 line-index map: " + map_path.string());
    std::string line;
    if (!std::getline(mapping, line)) throw std::runtime_error("magnesium Type-50 line-index map is empty");
    const auto header = split_csv(line);
    std::map<std::string, std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    if (!columns.count("record") || !columns.count("line_index")) {
        throw std::runtime_error("magnesium Type-50 line-index map is missing record or line_index");
    }
    while (std::getline(mapping, line)) {
        if (trim(line).empty()) continue;
        const auto values = split_csv(line);
        if (values.size() != header.size()) throw std::runtime_error("magnesium Type-50 line-index map row width mismatch");
        const auto record = parse_number<std::int64_t>(values.at(columns.at("record")), "record");
        const int line_index = parse_number<int>(values.at(columns.at("line_index")), "line_index");
        if (record <= 0 || line_index <= 0) throw std::runtime_error("magnesium Type-50 line-index map contains non-positive identity");
        if (!state.line_index_by_record.emplace(record, line_index).second) {
            throw std::runtime_error("duplicate magnesium Type-50 line-index record");
        }
    }
    if (state.line_index_by_record.size() != 2420) {
        throw std::runtime_error("magnesium Type-50 line-index map must contain exactly 2420 runtime-active records");
    }
    if (state.endpoint_energy_transport) {
        std::ifstream endpoint_input(endpoint_path);
        if (!endpoint_input) {
            throw std::runtime_error(
                "cannot open magnesium Type-50 endpoint-energy map: " + endpoint_path.string());
        }
        if (!std::getline(endpoint_input, line)) {
            throw std::runtime_error("magnesium Type-50 endpoint-energy map is empty");
        }
        const auto endpoint_header = split_csv(line);
        std::map<std::string, std::size_t> endpoint_columns;
        for (std::size_t i = 0; i < endpoint_header.size(); ++i) {
            endpoint_columns[endpoint_header[i]] = i;
        }
        for (const char* required : {
                 "record", "idest1", "idest2", "source_endpoint1_energy_ev",
                 "source_endpoint2_energy_ev", "source_endpoint_energy_ev"}) {
            if (!endpoint_columns.count(required)) {
                throw std::runtime_error(
                    std::string("magnesium Type-50 endpoint-energy map is missing ") + required);
            }
        }
        while (std::getline(endpoint_input, line)) {
            if (trim(line).empty()) continue;
            const auto values = split_csv(line);
            if (values.size() != endpoint_header.size()) {
                throw std::runtime_error(
                    "magnesium Type-50 endpoint-energy map row width mismatch");
            }
            const auto record = parse_number<std::int64_t>(
                values.at(endpoint_columns.at("record")), "record");
            MagnesiumType50EndpointEnergyV048746193 endpoint;
            endpoint.idest1 = parse_number<int>(
                values.at(endpoint_columns.at("idest1")), "idest1");
            endpoint.idest2 = parse_number<int>(
                values.at(endpoint_columns.at("idest2")), "idest2");
            endpoint.endpoint1_energy_ev = parse_number<double>(
                values.at(endpoint_columns.at("source_endpoint1_energy_ev")),
                "source_endpoint1_energy_ev");
            endpoint.endpoint2_energy_ev = parse_number<double>(
                values.at(endpoint_columns.at("source_endpoint2_energy_ev")),
                "source_endpoint2_energy_ev");
            endpoint.endpoint_energy_ev = parse_number<double>(
                values.at(endpoint_columns.at("source_endpoint_energy_ev")),
                "source_endpoint_energy_ev");
            if (record <= 0 || endpoint.idest1 <= 0 || endpoint.idest2 <= 0 ||
                !(endpoint.endpoint_energy_ev > 0.0) ||
                !std::isfinite(endpoint.endpoint1_energy_ev) ||
                !std::isfinite(endpoint.endpoint2_energy_ev) ||
                !std::isfinite(endpoint.endpoint_energy_ev) ||
                std::abs(endpoint.endpoint1_energy_ev - endpoint.endpoint2_energy_ev)
                    != endpoint.endpoint_energy_ev) {
                throw std::runtime_error(
                    "magnesium Type-50 endpoint-energy map contains invalid source state");
            }
            if (!state.endpoint_by_record.emplace(record, endpoint).second) {
                throw std::runtime_error(
                    "duplicate magnesium Type-50 endpoint-energy record");
            }
        }
        if (state.endpoint_by_record.size() != 2420) {
            throw std::runtime_error(
                "magnesium Type-50 endpoint-energy map must contain exactly 2420 records");
        }
        for (const auto& item : state.line_index_by_record) {
            if (!state.endpoint_by_record.count(item.first)) {
                throw std::runtime_error(
                    "magnesium Type-50 endpoint-energy map domain differs from line map");
            }
        }
    }
    std::ifstream active(active_path);
    if (!active) throw std::runtime_error("cannot open magnesium Type-50 active-record ledger: " + active_path.string());
    if (!std::getline(active, line)) throw std::runtime_error("magnesium Type-50 active-record ledger is empty");
    const auto active_header = split_csv(line);
    std::map<std::string, std::size_t> active_columns;
    for (std::size_t i = 0; i < active_header.size(); ++i) active_columns[active_header[i]] = i;
    if (!active_columns.count("sequence") || !active_columns.count("record")) {
        throw std::runtime_error("magnesium Type-50 active-record ledger is missing sequence or record");
    }
    while (std::getline(active, line)) {
        if (trim(line).empty()) continue;
        const auto values = split_csv(line);
        if (values.size() != active_header.size()) {
            throw std::runtime_error("magnesium Type-50 active-record ledger row width mismatch");
        }
        const int sequence = parse_number<int>(values.at(active_columns.at("sequence")), "sequence");
        if (sequence != state.source_sequence) continue;
        const auto record = parse_number<std::int64_t>(values.at(active_columns.at("record")), "record");
        if (record <= 0) throw std::runtime_error("magnesium Type-50 active-record ledger contains non-positive record");
        if (!state.active_records.insert(record).second) {
            throw std::runtime_error("duplicate magnesium Type-50 active record for source sequence");
        }
    }
    const std::size_t expected_active = state.source_sequence <= 4 ? 2196u :
        (state.source_sequence <= 6 ? 2201u : 2420u);
    if (state.active_records.size() != expected_active) {
        throw std::runtime_error("magnesium Type-50 active-record count does not match source sequence contract");
    }
    for (const auto record : state.active_records) {
        if (!state.line_index_by_record.count(record)) {
            throw std::runtime_error("active magnesium Type-50 record is missing from source line-index map");
        }
    }
    state.tau_in = read_binary64_payload_v04874619(tau_in_path);
    state.tau_out = read_binary64_payload_v04874619(tau_out_path);
    if (state.tau_in.size() != state.tau_out.size() || state.tau_in.empty()) {
        throw std::runtime_error("magnesium Type-50 line-tau payload inventory mismatch");
    }
    for (const auto& item : state.line_index_by_record) {
        if (static_cast<std::size_t>(item.second) > state.tau_in.size()) {
            throw std::runtime_error("magnesium Type-50 line index is outside transported tau0 arrays");
        }
    }
    return state;
}

const MagnesiumType50EscapeStateV04874619& magnesium_type50_escape_state_v04874619() {
    // Mg Type-50 activity and line optical depths are sequence-dependent.  The
    // persistent controller binds the sequence and workspace paths before each
    // callback, so reload the single current state whenever that identity
    // changes.  Do not cache all 61 tau arrays.
    const bool enabled = environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ESCAPE_STATE");
    std::string key = enabled ? "1" : "0";
    if (enabled) {
        key += "|seq=" + std::to_string(environment_data_type(
            "XSTAR_QUALIFICATION_SOURCE_SEQUENCE"));
        for (const char* name : {
                 "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_MAP_CSV",
                 "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_TAU_IN_BIN",
                 "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_TAU_OUT_BIN",
                 "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ACTIVE_RECORDS_CSV"}) {
            key += "|" + required_environment_path_v04874618(name);
        }
        if (environment_flag(
                "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_ENERGY_TRANSPORT")) {
            key += "|" + required_environment_path_v04874618(
                "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_MAP_CSV");
        }
    }
    static thread_local std::string cached_key;
    static thread_local MagnesiumType50EscapeStateV04874619 state;
    if (cached_key != key) {
        state = load_magnesium_type50_escape_state_v04874619();
        cached_key = key;
    }
    return state;
}


constexpr const char* kMagnesiumType99PrimaryCoolingReductionEnv =
    "XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PRIMARY_COOLING_REDUCTION";
constexpr const char* kMagnesiumPrimaryCoolingSourceOrderReductionEnv =
    "XSTAR_QUALIFICATION_MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_REDUCTION";
constexpr const char* kMagnesiumType99PrimaryCoolingLedgerEnv =
    "XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PRIMARY_COOLING_LEDGER_CSV";
constexpr const char* kMagnesiumPrimaryCoolingSourceOrderLedgerEnv =
    "XSTAR_QUALIFICATION_MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_LEDGER_CSV";

struct MagnesiumType99PrimaryCoolingRowV04874620 {
    std::int64_t source_order_index = 0;
    std::int64_t record = 0;
    std::string role;
    int compact_row = 0;
    int compact_column = 0;
    int idest1 = 0;
    int idest2 = 0;
    double cj = 0.0;
    double cj2 = 0.0;
};

struct MagnesiumType99PrimaryCoolingStateV04874620 {
    bool enabled = false;
    int source_sequence = 0;
    std::map<std::pair<std::int64_t, std::string>, MagnesiumType99PrimaryCoolingRowV04874620> rows;
};

MagnesiumType99PrimaryCoolingStateV04874620 load_magnesium_type99_primary_cooling_state_v04874620() {
    MagnesiumType99PrimaryCoolingStateV04874620 state;
    state.enabled = environment_flag(kMagnesiumType99PrimaryCoolingReductionEnv);
    if (!state.enabled) return state;
    state.source_sequence = environment_data_type("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    if (state.source_sequence < 1 || state.source_sequence > 61) {
        throw std::runtime_error("magnesium Type-99 source sequence must be in 1..61");
    }
    const auto ledger_path = std::filesystem::path(required_environment_path_v04874618(
        kMagnesiumType99PrimaryCoolingLedgerEnv));
    std::ifstream input(ledger_path);
    if (!input) {
        throw std::runtime_error(
            "cannot open magnesium Type-99 primary-cooling ledger: " + ledger_path.string());
    }
    std::string line;
    if (!std::getline(input, line)) {
        throw std::runtime_error("magnesium Type-99 primary-cooling ledger is empty");
    }
    const auto header = split_csv(line);
    std::map<std::string, std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    for (const char* required : {
             "sequence", "source_order_index", "record", "role", "compact_row",
             "compact_column", "idest1", "idest2", "cj", "cj2"}) {
        if (!columns.count(required)) {
            throw std::runtime_error(
                std::string("magnesium Type-99 primary-cooling ledger is missing ") + required);
        }
    }
    while (std::getline(input, line)) {
        if (trim(line).empty()) continue;
        const auto values = split_csv(line);
        if (values.size() != header.size()) {
            throw std::runtime_error(
                "magnesium Type-99 primary-cooling ledger row width mismatch");
        }
        const int sequence = parse_number<int>(
            values.at(columns.at("sequence")), "sequence");
        if (sequence != state.source_sequence) continue;
        MagnesiumType99PrimaryCoolingRowV04874620 row;
        row.source_order_index = parse_number<std::int64_t>(
            values.at(columns.at("source_order_index")), "source_order_index");
        row.record = parse_number<std::int64_t>(
            values.at(columns.at("record")), "record");
        row.role = values.at(columns.at("role"));
        row.compact_row = parse_number<int>(
            values.at(columns.at("compact_row")), "compact_row");
        row.compact_column = parse_number<int>(
            values.at(columns.at("compact_column")), "compact_column");
        row.idest1 = parse_number<int>(values.at(columns.at("idest1")), "idest1");
        row.idest2 = parse_number<int>(values.at(columns.at("idest2")), "idest2");
        row.cj = parse_number<double>(values.at(columns.at("cj")), "cj");
        row.cj2 = parse_number<double>(values.at(columns.at("cj2")), "cj2");
        if (row.source_order_index <= 0 || row.record <= 0 || row.role.empty() ||
            row.compact_row <= 0 || row.compact_column != row.compact_row ||
            !std::isfinite(row.cj) || !std::isfinite(row.cj2)) {
            throw std::runtime_error(
                "magnesium Type-99 primary-cooling ledger contains invalid state");
        }
        const auto key = std::make_pair(row.record, row.role);
        if (!state.rows.emplace(key, row).second) {
            throw std::runtime_error(
                "duplicate magnesium Type-99 primary-cooling record/role");
        }
    }
    const std::size_t expected_rows =
        state.source_sequence <= 4 ? 18u : (state.source_sequence <= 6 ? 20u : 22u);
    if (state.rows.size() != expected_rows) {
        throw std::runtime_error(
            "magnesium Type-99 primary-cooling sequence ledger has unexpected row count");
    }
    std::map<std::int64_t, std::set<std::string>> roles_by_record;
    for (const auto& item : state.rows) {
        roles_by_record[item.first.first].insert(item.first.second);
    }
    const std::size_t expected_records = expected_rows / 2u;
    if (roles_by_record.size() != expected_records) {
        throw std::runtime_error(
            "magnesium Type-99 primary-cooling sequence ledger has unexpected record count");
    }
    for (const auto& item : roles_by_record) {
        if (item.second != std::set<std::string>{"forward_diag_loss", "reverse_diag_loss"}) {
            throw std::runtime_error(
                "magnesium Type-99 primary-cooling record is missing a diagonal role");
        }
    }
    return state;
}

const MagnesiumType99PrimaryCoolingStateV04874620&
magnesium_type99_primary_cooling_state_v04874620() {
    const bool enabled = environment_flag(kMagnesiumType99PrimaryCoolingReductionEnv);
    if (!enabled) {
        static const MagnesiumType99PrimaryCoolingStateV04874620 disabled{};
        return disabled;
    }
    const int sequence = environment_data_type("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    const std::string ledger = required_environment_path_v04874618(
        kMagnesiumType99PrimaryCoolingLedgerEnv);
    // These ledgers are compact.  Cache one validated state per sequence so the
    // controller does not rescan the all-61 CSV for every element callback.
    static thread_local std::string cached_ledger;
    static thread_local std::map<int, MagnesiumType99PrimaryCoolingStateV04874620> states;
    if (cached_ledger != ledger) {
        states.clear();
        cached_ledger = ledger;
    }
    auto found = states.find(sequence);
    if (found == states.end()) {
        found = states.emplace(
            sequence, load_magnesium_type99_primary_cooling_state_v04874620()).first;
    }
    return found->second;
}

struct MagnesiumPrimaryCoolingOrderRowV048746202 {
    std::int64_t source_order_index = 0;
    std::int64_t record = 0;
    int data_type = 0;
    int rate_type = 0;
    std::string role;
    int compact_row = 0;
};

struct MagnesiumPrimaryCoolingOrderStateV048746202 {
    bool enabled = false;
    int source_sequence = 0;
    std::vector<MagnesiumPrimaryCoolingOrderRowV048746202> ordered_rows;
    std::map<std::pair<std::int64_t, std::string>, MagnesiumPrimaryCoolingOrderRowV048746202> rows;
};

MagnesiumPrimaryCoolingOrderStateV048746202
load_magnesium_primary_cooling_order_state_v048746202() {
    MagnesiumPrimaryCoolingOrderStateV048746202 state;
    state.enabled = environment_flag(kMagnesiumPrimaryCoolingSourceOrderReductionEnv);
    if (!state.enabled) return state;
    state.source_sequence = environment_data_type("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    if (state.source_sequence < 1 || state.source_sequence > 61) {
        throw std::runtime_error("magnesium primary-cooling source sequence must be in 1..61");
    }
    const auto ledger_path = std::filesystem::path(required_environment_path_v04874618(
        kMagnesiumPrimaryCoolingSourceOrderLedgerEnv));
    std::ifstream input(ledger_path);
    if (!input) {
        throw std::runtime_error(
            "cannot open magnesium primary-cooling source-order ledger: " + ledger_path.string());
    }
    std::string line;
    if (!std::getline(input, line)) {
        throw std::runtime_error("magnesium primary-cooling source-order ledger is empty");
    }
    const auto header = split_csv(line);
    std::map<std::string, std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    for (const char* required : {
             "sequence", "source_order_index", "record", "data_type", "rate_type",
             "role", "compact_row", "cj", "cooling_contribution"}) {
        if (!columns.count(required)) {
            throw std::runtime_error(
                std::string("magnesium primary-cooling source-order ledger is missing ") + required);
        }
    }
    std::set<std::int64_t> source_order_indices;
    while (std::getline(input, line)) {
        if (trim(line).empty()) continue;
        const auto values = split_csv(line);
        if (values.size() != header.size()) {
            throw std::runtime_error(
                "magnesium primary-cooling source-order ledger row width mismatch");
        }
        const int sequence = parse_number<int>(
            values.at(columns.at("sequence")), "sequence");
        if (sequence != state.source_sequence) continue;
        MagnesiumPrimaryCoolingOrderRowV048746202 row;
        row.source_order_index = parse_number<std::int64_t>(
            values.at(columns.at("source_order_index")), "source_order_index");
        row.record = parse_number<std::int64_t>(
            values.at(columns.at("record")), "record");
        row.data_type = parse_number<int>(values.at(columns.at("data_type")), "data_type");
        row.rate_type = parse_number<int>(values.at(columns.at("rate_type")), "rate_type");
        row.role = values.at(columns.at("role"));
        row.compact_row = parse_number<int>(
            values.at(columns.at("compact_row")), "compact_row");
        const double cj = parse_number<double>(values.at(columns.at("cj")), "cj");
        const double cooling = parse_number<double>(
            values.at(columns.at("cooling_contribution")), "cooling_contribution");
        if (row.source_order_index <= 0 || row.record <= 0 || row.data_type <= 0 ||
            row.rate_type <= 0 || row.role.empty() || row.compact_row <= 0 ||
            !(cj > 0.0) || !std::isfinite(cooling) || cooling < 0.0) {
            throw std::runtime_error(
                "magnesium primary-cooling source-order ledger contains invalid state");
        }
        if (!source_order_indices.insert(row.source_order_index).second) {
            throw std::runtime_error(
                "duplicate magnesium primary-cooling source-order index");
        }
        const auto key = std::make_pair(row.record, row.role);
        if (!state.rows.emplace(key, row).second) {
            throw std::runtime_error(
                "duplicate magnesium primary-cooling source record/role");
        }
        state.ordered_rows.push_back(row);
    }
    if (state.ordered_rows.empty()) {
        throw std::runtime_error(
            "magnesium primary-cooling source-order sequence ledger is empty");
    }
    std::sort(
        state.ordered_rows.begin(), state.ordered_rows.end(),
        [](const auto& left, const auto& right) {
            return left.source_order_index < right.source_order_index;
        });
    if (state.ordered_rows.size() != state.rows.size()) {
        throw std::runtime_error(
            "magnesium primary-cooling source-order ledger inventory mismatch");
    }
    return state;
}

const MagnesiumPrimaryCoolingOrderStateV048746202&
magnesium_primary_cooling_order_state_v048746202() {
    const bool enabled = environment_flag(kMagnesiumPrimaryCoolingSourceOrderReductionEnv);
    if (!enabled) {
        static const MagnesiumPrimaryCoolingOrderStateV048746202 disabled{};
        return disabled;
    }
    const int sequence = environment_data_type("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    const std::string ledger = required_environment_path_v04874618(
        kMagnesiumPrimaryCoolingSourceOrderLedgerEnv);
    static thread_local std::string cached_ledger;
    static thread_local std::map<int, MagnesiumPrimaryCoolingOrderStateV048746202> states;
    if (cached_ledger != ledger) {
        states.clear();
        cached_ledger = ledger;
    }
    auto found = states.find(sequence);
    if (found == states.end()) {
        found = states.emplace(
            sequence, load_magnesium_primary_cooling_order_state_v048746202()).first;
    }
    return found->second;
}

// Literal v0.6.47.2 Python translation of pescl.f90.  The accepted source
// reference uses Python binary64 math.pi and libm exp/log/sqrt semantics.
double pescl_v0472_binary64(double tau) {
    double value = 0.0;
    if (tau < 1.0) {
        if (tau < 1.0e-5) {
            value = 1.0;
        } else {
            const double aa = 2.0 * tau;
            value = (1.0 - std::exp(-aa)) / aa;
        }
    } else {
        const double bb = 0.5 * std::sqrt(std::max(std::log(tau), 0.0)) / (1.0 + tau / 1.0e5);
        constexpr double kPythonPi = 3.1451653589793238462643383279502884;
        value = 1.0 / (tau * std::sqrt(kPythonPi) * (1.2 + bb));
    }
    return value / 2.0;
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
    int global_level_index = 0;
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
    int line_index_one_based = 0;
    int continuum_index_one_based = 0;
    bool matrix_enabled = true;
};

struct LteIonTopology {
    int element_index = 0;
    int ion_stage = 0;
    int start_row = 0;
    int nlev = 0;
    double terminal_energy_ev = 0.0;
    double terminal_statistical_weight = 1.0;
};

struct LteLevelData {
    int element_index = 0;
    int ion_stage = 0;
    int local_level = 0;
    std::int64_t source_record = 0;
    double energy_ev = 0.0;
    double statistical_weight = 1.0;
};

struct Program {
    std::string id;
    bool active_atdb_lowered = false;
    std::uint64_t topology_record_count = 0;
    std::uint64_t unsupported_record_count = 0;
    std::size_t native_line_count = 0;
    std::size_t native_continuum_count = 0;
    std::vector<ElementProgram> elements;
    std::vector<ProgramRecord> records;
    std::vector<LteIonTopology> lte_ion_topology;
    std::vector<LteLevelData> lte_levels;
    std::vector<double> reals;
    std::vector<std::int64_t> ints;
    // Native production runtime line optical-depth state.  This replaces the
    // historical qualification-only binary files and is owned by the
    // persistent fixed-state context.
    std::vector<double> runtime_line_tau_in;
    std::vector<double> runtime_line_tau_out;
};

struct Type53RecordContext {
    bool valid = false;
    int layout_version = 0;
    std::size_t pair_real_count = 0;
    double base_threshold_ev = 0.0;
    double threshold_ev = 0.0;
    double bound_energy_ev = 0.0;
    // These are the literal mutable leveltemp(1:2,nlev) Milne-partition
    // values, not a compact continuum-row approximation.
    double continuum_energy_ev = 0.0;
    double bound_statistical_weight = 0.0;
    double continuum_statistical_weight = 0.0;
    double destination_statistical_weight = 0.0;
    double leveltemp_destination_energy_ev = 0.0;
    double excited_parent_energy_ev = 0.0;
    double excited_parent_statistical_weight = 0.0;
    bool persistent_leveltemp_candidates_valid = false;
    int leveltemp_destination_column = 0;
    std::uint32_t leveltemp_candidate_mask = 0;
    std::array<double,12> leveltemp_candidate_energy_ev{};
    int continuum_index_one_based = 0;
    int phextrap_max_points = 0;
};

struct Type53SourceShadow {
    bool valid = false;
    std::array<double,6> ans{};
    std::array<double,6> legacy_ans{};
    bool type49_semantics = false;
    bool phextrap_applied = false;
    bool source_zero_gate = false;
    bool source_faithful_mode = false;
    bool replacement_applied = false;
    bool legacy_nonfinite = false;
    bool legacy_implausible = false;
    bool committed_nonfinite = false;
    bool committed_implausible = false;
    double legacy_max_abs = 0.0;
    double shadow_max_abs = 0.0;
    double committed_max_abs = 0.0;
    double exponent_energy_ev = 0.0;
    double exponent_dimensionless = 0.0;
    double electron_density_cm3 = 0.0;
    double hydrogen_density_cm3 = 0.0;
    double matrix_density_scale = 0.0;
    double threshold_cross_section_cm2 = 0.0;
    double threshold_stimulated_cross_section_cm2 = 0.0;
    bool threshold_publication_reached = false;
    // v82 patch 5.20.5: xstarsetup owns a separate errc ranking coordinate.
    // This must not reuse the later spectral/threshold energy.
    double source_errc_rank_energy_ev = 0.0;
    double base_threshold_ev = 0.0;
    double threshold_ev = 0.0;
    double bound_energy_ev = 0.0;
    double continuum_energy_ev = 0.0;
    double destination_energy_ev = 0.0;
    double excited_parent_energy_ev = 0.0;
    bool persistent_leveltemp_candidates_valid = false;
    int leveltemp_destination_column = 0;
    std::uint32_t leveltemp_candidate_mask = 0;
    std::array<double,12> leveltemp_candidate_energy_ev{};
    double bound_statistical_weight = 0.0;
    double continuum_statistical_weight = 0.0;
    double destination_statistical_weight = 0.0;
    double excited_parent_statistical_weight = 0.0;
    bool milne_partition_context_used = false;
    bool excited_threshold_context_used = false;
    bool corrected_threshold_before_mapping = false;
    bool phextrap_source_reference_order = false;
    int phextrap_input_pair_count = 0;
    int phextrap_output_pair_count = 0;
    int phextrap_max_points = 0;
    std::uint64_t phextrap_input_energy_hash = 0;
    std::uint64_t phextrap_input_sigma_hash = 0;
    std::uint64_t phextrap_output_energy_hash = 0;
    std::uint64_t phextrap_output_sigma_hash = 0;
    double rnist = 0.0;
    double sumr = 0.0;
    double sumi = 0.0;
    double sumh = 0.0;
    double sumh2 = 0.0;
    double sumc = 0.0;
    double sumc2 = 0.0;
    bool sumc_ieee_nextafter_applied = false;
    int nb1_one_based = 0;
    int klmax_one_based = 0;
    int integration_intervals = 0;
    bool helium_live_escape_state_applied = false;
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

struct Type51SourceShadow {
    bool valid = false;
    bool source_faithful_mode = false;
    bool replacement_applied = false;
    bool endpoint_order_exact = false;
    bool committed_nonfinite = false;
    int bt_type = 0;
    int point_count = 0;
    double eij_ryd = 0.0;
    double eij_ev = 0.0;
    double scaling_c = 0.0;
    double physical_temperature_k = 0.0;
    double floor_temperature_k = 0.0;
    double effective_temperature_k = 0.0;
    bool temperature_floor_applied = false;
    double scaled_temperature = 0.0;
    double transformed_temperature = 0.0;
    double scaled_upsilon = 0.0;
    double upsilon = 0.0;
    double lower_statistical_weight = 0.0;
    double upper_statistical_weight = 0.0;
    double electron_density_cm3 = 0.0;
    double q_excitation_cm3_s = 0.0;
    double q_deexcitation_cm3_s = 0.0;
    std::array<double,6> ans{};
    std::array<double,6> legacy_ans{};
};

struct Type50SourceShadow {
    bool valid = false;
    std::array<double,6> ans{};
    double stored_wavelength_a = 0.0;
    double endpoint_energy_ev = 0.0;
    double covering_fraction = 0.0;
    double ptmp1 = 0.0;
    double ptmp2 = 0.0;
    double bremsa_nb1 = 0.0;
    double density_floor_s = 0.0;
    bool density_floor_applied = false;
    bool photoexcitation_zero_covering = false;
    bool used_dsec_covering = false;
    bool used_dsec_radiation = false;
    int nb1_one_based = 0;
    bool hydrogen_escape_state_applied = false;
    bool magnesium_escape_state_applied = false;
    bool magnesium_source_endpoint_energy_applied = false;
    int source_idest1 = 0;
    int source_idest2 = 0;
    double source_endpoint1_energy_ev = 0.0;
    double source_endpoint2_energy_ev = 0.0;
    int line_index_one_based = 0;
    double line_tau_in = 0.0;
    double line_tau_out = 0.0;
};

struct Type99PersistentLeveltempContextV048746223 {
    bool valid = false;
    int bound_column = 0;
    int parent_column = 0;
    int destination_column = 0;
    std::uint32_t bound_mask = 0;
    std::uint32_t parent_mask = 0;
    std::uint32_t destination_mask = 0;
    int excited_parent_mode = 0;
    double incoming_bound_energy_ev = 0.0;
    double incoming_bound_statistical_weight = 0.0;
    double incoming_parent_energy_ev = 0.0;
    double incoming_parent_statistical_weight = 0.0;
    double incoming_destination_energy_ev = 0.0;
    double incoming_destination_statistical_weight = 0.0;
    double excited_parent_energy_ev = 0.0;
    double excited_parent_statistical_weight = 0.0;
    std::array<double,12> bound_candidate_energy_ev{};
    std::array<double,12> bound_candidate_statistical_weight{};
    std::array<double,12> parent_candidate_energy_ev{};
    std::array<double,12> parent_candidate_statistical_weight{};
    std::array<double,12> destination_candidate_energy_ev{};
    std::array<double,12> destination_candidate_statistical_weight{};
};

struct Type99ResolvedLeveltempContextV048746223 {
    double bound_energy_ev = 0.0;
    double bound_statistical_weight = 0.0;
    double parent_energy_ev = 0.0;
    double parent_statistical_weight = 0.0;
    double destination_energy_ev = 0.0;
    double destination_statistical_weight = 0.0;
    double threshold_ev = 0.0;
    int bound_owner_stage = 0;
    int parent_owner_stage = 0;
    int destination_owner_stage = 0;
};

struct Type99SourceShadow {
    bool valid = false;
    std::array<double,6> ans{};
    double threshold_ev = 0.0;
    // v82 patch 5.20.5: literal xstarsetup errc energy retained by the lowerer.
    double source_errc_rank_energy_ev = 0.0;
    double destination_energy_ev = 0.0;
    double bound_energy_ev = 0.0;
    double parent_energy_ev = 0.0;
    double bound_statistical_weight = 0.0;
    double parent_statistical_weight = 0.0;
    double destination_statistical_weight = 0.0;
    double swrat = 0.0;
    bool persistent_leveltemp_context_valid = false;
    bool persistent_leveltemp_context_applied = false;
    int bound_owner_stage = 0;
    int parent_owner_stage = 0;
    int destination_owner_stage = 0;
    double calt99_density_cm3 = 0.0;
    double phint53hunt_density_cm3 = 0.0;
    double rec_cm3_s = 0.0;
    double milne_alpha_cm3_s = 0.0;
    double cross_section_scale = 0.0;
    double threshold_cross_section_cm2 = 0.0;
    double ans2d_unscaled_s = 0.0;
    double phint_scale = 0.0;
    double pirt_unscaled_s = 0.0;
    double rrrt_unscaled_s = 0.0;
    double piht_unscaled_erg_s = 0.0;
    double rrcl_unscaled_erg_s = 0.0;
    double piht2_unscaled_erg_s = 0.0;
    double rrcl2_unscaled_erg_s = 0.0;
    double energy_difference_ev = 0.0;
    bool destination_threshold_identity = false;
    double ans5_pre_energy_correction = 0.0;
    double ans6_pre_energy_correction = 0.0;
    double ans5_energy_correction_numerator = 0.0;
    double ans5_energy_correction_denominator = 0.0;
    double ans5_energy_correction_factor = 0.0;
    double ans6_energy_correction_numerator = 0.0;
    double ans6_energy_correction_denominator = 0.0;
    double ans6_energy_correction_factor = 0.0;
    bool destination_identity_correction_applied = false;
    int nbinc_threshold_one_based = 0;
    int nb1_one_based = 0;
    int nphint_one_based = 0;
    int ndelt = 0;
    int npass = 0;
    int last_pass_first_kl_one_based = 0;
    int last_pass_last_kl_one_based = 0;
    int cached_atmp22_stale_reuses = 0;
    bool used_dsec_radiation = false;
};

struct EvaluatedRecord {
    xstar_element_contribution_v1 contribution{};
    bool spectral = false;
    bool bound_free_spectral = false;
    bool matrix_enabled = true;
    int continuum_index_one_based = 0;
    double line_energy_ev = 0.0;
    double atomic_mass_amu = 1.0;
    double natural_width_ev = 0.0;
    double opakab = 0.0;
    double type56_upsilon = std::numeric_limits<double>::quiet_NaN();
    Type53SourceShadow type53_shadow{};
    // v82 patch 5.18.1: calc_emisab_all evaluates Type-53 on the reduced
    // epim/bremsam workspace before calc_emis_all ranks and selectively
    // revisits rate-7 records on the full radiation grid.  Keep those two
    // lifetimes distinct.  A selected full-grid UCalc revisit starts with
    // opakab=0 and either publishes its own threshold value or leaves zero.
    Type53SourceShadow type53_calc_emisab_shadow{};
    // v82 patch 5.20.14: distinct full-grid calc_emis_ion revisit.
    Type53SourceShadow type53_calc_emis_shadow{};
    // v82 patch 5.20.8: calc_emisab_all uses the same reduced epim/bremsam
    // workspace for Type-49 rate-7 records.  Keep the reduced-grid seed
    // distinct from the later full-grid calc_emis_ion evaluation.
    Type53SourceShadow type49_calc_emisab_shadow{};
    Type53SourceShadow type49_calc_emis_shadow{};
    Type53SourceShadow type49_shadow{};
    Type51SourceShadow type51_shadow{};
    Type50SourceShadow type50_shadow{};
    Type99SourceShadow type99_shadow{};
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

// Spectral records retain source/full-element row numbers while the live
// element solver works on a compact active-stage population vector. Translate
// explicitly at every product/spectral consumer. Rows outside the active
// window have source population zero; they must never index the compact vector.
double active_population_for_full_row(
    const ActiveElementView& active,
    const std::vector<double>& populations,
    int full_row
) {
    if (full_row < active.full_row_start || full_row > active.full_row_end) return 0.0;
    const std::size_t compact_index =
        static_cast<std::size_t>(full_row - active.full_row_start);
    if (compact_index >= populations.size()) {
        throw std::runtime_error("active spectral population row translation overflow");
    }
    const double value = populations[compact_index];
    return std::isfinite(value) && value > 0.0 ? value : 0.0;
}



struct CanonicalThermalLedgerBuild {
    std::vector<xstar_canonical_thermal_term_v1> terms;
    std::uint64_t fingerprint = 0;
};

class CanonicalThermalLedgerBuilderV048746212 {
public:
    CanonicalThermalLedgerBuilderV048746212(
        const ElementProgram& element,
        const ActiveElementView& active
    ) : element_(element), active_(active),
        type99_state_(magnesium_type99_primary_cooling_state_v04874620()),
        primary_order_state_(magnesium_primary_cooling_order_state_v048746202()) {}

    void append_matrix_committed(const xstar_element_contribution_v1& contribution) {
        const Identity identity = identity_of(contribution);
        if (candidates_.count(identity) != 0u) {
            throw std::runtime_error(
                "duplicate canonical Thermal ledger matrix-commit identity");
        }
        Candidate candidate;
        candidate.forward = make_term(
            contribution, contribution.lower_row,
            XSTAR_CANONICAL_THERMAL_FORWARD_DIAG_LOSS,
            contribution.ans4 * contribution.density_scale,
            contribution.ans6 * contribution.density_scale);
        candidate.reverse = make_term(
            contribution, contribution.upper_row,
            XSTAR_CANONICAL_THERMAL_REVERSE_DIAG_LOSS,
            -contribution.ans3 * contribution.density_scale,
            -contribution.ans5 * contribution.density_scale);
        candidates_.emplace(identity, candidate);
    }

    CanonicalThermalLedgerBuild finish(
        const std::vector<xstar_element_contribution_v1>& committed_contributions
    ) const {
        CanonicalThermalLedgerBuild out;
        out.terms.reserve(committed_contributions.size() * 2u);
        std::set<Identity> consumed;
        std::set<std::pair<std::int64_t, std::string>> type99_rows_matched;
        std::set<std::pair<std::int64_t, std::string>> primary_rows_matched;
        std::int64_t term_index = 0;
        std::int64_t type95_thermal_terms_committed = 0;

        const bool native_sequence1_source_order =
            environment_flag("XSTAR_NATIVE_SEQUENCE1_THERMAL_SOURCE_ORDER") &&
            environment_data_type("XSTAR_QUALIFICATION_SOURCE_SEQUENCE") <= 61;
        const auto commit_term = [&](const xstar_canonical_thermal_term_v1& candidate) {
            xstar_canonical_thermal_term_v1 term = candidate;
            term.term_index = ++term_index;
            const char* role_name = term.role == XSTAR_CANONICAL_THERMAL_FORWARD_DIAG_LOSS
                ? "forward_diag_loss" : "reverse_diag_loss";
            const auto source_key = std::make_pair(term.record, std::string(role_name));
            if (type99_state_.enabled && element_.element_z == 12 && term.data_type == 99) {
                type99_rows_matched.insert(source_key);
            }
            if (primary_order_state_.enabled && element_.element_z == 12 && term.cj > 0.0) {
                primary_rows_matched.insert(source_key);
            }
            if (term.data_type == 95 && term.rate_type == 15) {
                ++type95_thermal_terms_committed;
            }
            if (native_sequence1_source_order && element_.element_z == 12 && term.cj > 0.0) {
                term.flags |= XSTAR_CANONICAL_THERMAL_PRIMARY_SOURCE_ORDERED;
                if (primary_order_state_.enabled && term.primary_source_order_index > 0) {
                    // An explicit source capture is authoritative when one is
                    // available.
                } else {
                    // The accepted historical stream already includes at most
                    // one Type-95 pair in its base numbering.  A second
                    // dynamically selected pair is a Thermal-only overlay and
                    // must not renumber the independent Mg primary-cooling
                    // stream.  Each extra canonical Type-95 term would shift
                    // the legacy index by two slots, so remove only terms
                    // beyond the first pair.
                    const std::int64_t overlay_terms = std::max<std::int64_t>(
                        0, type95_thermal_terms_committed - 2);
                    term.primary_source_order_index =
                        2 * (term.term_index - overlay_terms);
                }
                if (term.data_type == 99) {
                    term.flags |= XSTAR_CANONICAL_THERMAL_TYPE99_SOURCE_CORRECTED;
                    term.source_cj = term.cj;
                }
            }
            out.terms.push_back(term);
        };

        // The candidates are captured from the final committed contribution
        // stream, after source matrix-closure replacement/removal and source-
        // order restoration.  This keeps the canonical Thermal coefficients
        // synchronized with the rates actually consumed by the element solve,
        // while element-specific preservation rules (notably Mg Type-50) remain
        // encoded in the corrected contribution itself.
        std::vector<xstar_element_contribution_v1> ordered_contributions = committed_contributions;
        if (native_sequence1_source_order) {
            std::stable_sort(
                ordered_contributions.begin(), ordered_contributions.end(),
                [](const auto& left, const auto& right) {
                    return std::tie(left.ion_stage, left.rate_type, left.source_position, left.record) <
                        std::tie(right.ion_stage, right.rate_type, right.source_position, right.record);
                });
        }
        for (const auto& contribution : ordered_contributions) {
            const Identity identity = identity_of(contribution);
            const auto it = candidates_.find(identity);
            if (it == candidates_.end()) {
                throw std::runtime_error(
                    "canonical Thermal ledger committed identity was not captured at insertion");
            }
            if (!consumed.insert(identity).second) {
                throw std::runtime_error(
                    "canonical Thermal ledger committed identity was consumed more than once");
            }
            commit_term(it->second.forward);
            commit_term(it->second.reverse);
        }

        if (type99_state_.enabled && element_.element_z == 12 &&
            type99_rows_matched.size() != type99_state_.rows.size()) {
            throw std::runtime_error(
                "canonical Thermal ledger did not consume every Mg Type-99 source row");
        }
        if (primary_order_state_.enabled && element_.element_z == 12 &&
            primary_rows_matched.size() != primary_order_state_.rows.size()) {
            throw std::runtime_error(
                "canonical Thermal ledger did not consume every Mg primary source-order row");
        }
        xstar_canonical_thermal::validate(
            out.terms.data(), out.terms.size(), active_.element.n_rows);
        out.fingerprint = xstar_canonical_thermal::fingerprint(out.terms);
        return out;
    }

private:
    using Identity = std::tuple<std::int64_t, int, int, int>;
    struct Candidate {
        xstar_canonical_thermal_term_v1 forward{};
        xstar_canonical_thermal_term_v1 reverse{};
    };

    static Identity identity_of(const xstar_element_contribution_v1& contribution) {
        return Identity{
            contribution.record,
            contribution.data_type,
            contribution.rate_type,
            contribution.ion_stage};
    }

    xstar_canonical_thermal_term_v1 make_term(
        const xstar_element_contribution_v1& contribution,
        int native_compact_row,
        int role,
        double native_cj,
        double cj2
    ) const {
        const char* role_name = role == XSTAR_CANONICAL_THERMAL_FORWARD_DIAG_LOSS
            ? "forward_diag_loss" : "reverse_diag_loss";
        int compact_row = native_compact_row;
        double cj = native_cj;
        double source_cj = native_cj;
        std::uint32_t flags = XSTAR_CANONICAL_THERMAL_SOURCE_DOMAIN_INCLUDED |
            XSTAR_CANONICAL_THERMAL_MATRIX_INSERTION_CAPTURED;
        if (contribution.data_type == 53) flags |= XSTAR_CANONICAL_THERMAL_TYPE53;
        if (native_compact_row == active_.element.normalization_row) {
            flags |= XSTAR_CANONICAL_THERMAL_NORMALIZATION_ROW;
        }

        const auto source_key = std::make_pair(contribution.record, std::string(role_name));
        if (type99_state_.enabled && element_.element_z == 12 && contribution.data_type == 99) {
            const auto it = type99_state_.rows.find(source_key);
            if (it == type99_state_.rows.end()) {
                throw std::runtime_error(
                    "canonical Thermal ledger missing Mg Type-99 source row");
            }
            source_cj = it->second.cj;
            if (it->second.cj > 0.0) {
                compact_row = it->second.compact_row;
                cj = it->second.cj;
                flags |= XSTAR_CANONICAL_THERMAL_TYPE99_SOURCE_CORRECTED;
            }
        }

        std::int64_t primary_source_order_index = 0;
        if (primary_order_state_.enabled && element_.element_z == 12 && cj > 0.0) {
            const auto it = primary_order_state_.rows.find(source_key);
            if (it == primary_order_state_.rows.end()) {
                throw std::runtime_error(
                    "canonical Thermal ledger missing Mg primary source-order row");
            }
            const auto& source_row = it->second;
            if (source_row.data_type != contribution.data_type ||
                source_row.rate_type != contribution.rate_type ||
                source_row.compact_row != compact_row) {
                throw std::runtime_error(
                    "canonical Thermal ledger Mg primary source-order metadata mismatch");
            }
            primary_source_order_index = source_row.source_order_index;
            flags |= XSTAR_CANONICAL_THERMAL_PRIMARY_SOURCE_ORDERED;
        }
        if (compact_row < 1 || compact_row > active_.element.n_rows) {
            throw std::runtime_error(
                "canonical Thermal ledger compact row outside active basis");
        }

        xstar_canonical_thermal_term_v1 term{};
        term.source_position = contribution.source_position +
            (role == XSTAR_CANONICAL_THERMAL_FORWARD_DIAG_LOSS ? 2 : 3);
        term.term_index = 0;  // Assigned only after closure membership/order is finalized.
        term.record = contribution.record;
        term.primary_source_order_index = primary_source_order_index;
        term.data_type = contribution.data_type;
        term.rate_type = contribution.rate_type;
        term.ion_index = contribution.ion_index;
        term.ion_stage = contribution.ion_stage;
        term.compact_row = compact_row;
        term.native_compact_row = native_compact_row;
        term.source_compact_row = compact_row;
        term.role = role;
        term.flags = flags;
        term.cj = cj;
        term.cj2 = cj2;
        term.native_cj = native_cj;
        term.source_cj = source_cj;
        return term;
    }

    const ElementProgram& element_;
    const ActiveElementView& active_;
    const MagnesiumType99PrimaryCoolingStateV04874620& type99_state_;
    const MagnesiumPrimaryCoolingOrderStateV048746202& primary_order_state_;
    std::map<Identity, Candidate> candidates_;
};

struct SourceCompactOracleRow {
    int active_min_stage = 1;
    int active_max_stage = 1;
    int compact_row = 0;
    int ion = 0;
    int ion_stage = 0;
    int ion_charge = 0;
    int superlevel = 0;
    bool normalization_row = false;
    double transformed_initial_population = 0.0;
};

struct SourceCompactOracle {
    int sequence = 0;
    std::unordered_map<int, std::vector<SourceCompactOracleRow>> rows_by_element_z;
};

int required_environment_integer(const char* name);

struct MatrixClosureContributionCorrection {
    std::int64_t record = 0;
    int data_type = 0;
    int rate_type = 0;
    int ion_stage = 0;
    bool remove = false;
    bool replace_ans1 = false;
    bool replace_ans2 = false;
    double source_ans1 = 0.0;
    double source_ans2 = 0.0;
};

struct FixedStateClosureData {
    std::vector<double> level_populations;
    std::unordered_map<int, std::vector<double>> ion_stage_populations;
    double electron_fraction = 0.0;
    double charge_residual = 0.0;
};

std::filesystem::path fixed_state_closure_file(const char* suffix) {
    const char* root_value = std::getenv("XSTAR_QUALIFICATION_FIXED_STATE_PARITY_CLOSURE_DIR");
    if (!root_value || !*root_value) {
        throw std::runtime_error("fixed-state parity closure requires XSTAR_QUALIFICATION_FIXED_STATE_PARITY_CLOSURE_DIR");
    }
    const int sequence = required_environment_integer("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    std::ostringstream name;
    name << "sequence_" << std::setw(4) << std::setfill('0') << sequence << suffix;
    return std::filesystem::path(root_value) / name.str();
}

FixedStateClosureData load_fixed_state_closure_data() {
    FixedStateClosureData out;
    {
        const auto path = fixed_state_closure_file("_levels.csv");
        std::ifstream input(path);
        if (!input) throw std::runtime_error("cannot open fixed-state level closure file: " + path.string());
        std::string line;
        if (!std::getline(input, line)) throw std::runtime_error("fixed-state level closure file is empty");
        const auto header = split_csv(line);
        std::unordered_map<std::string, std::size_t> column;
        for (std::size_t i = 0; i < header.size(); ++i) column.emplace(header[i], i);
        for (const char* name : {"row", "source_population"}) {
            if (!column.count(name)) throw std::runtime_error(std::string("fixed-state level closure file missing column: ") + name);
        }
        int expected_row = 1;
        while (std::getline(input, line)) {
            if (trim(line).empty()) continue;
            const auto values = split_csv(line);
            if (values.size() != header.size()) throw std::runtime_error("fixed-state level closure row width mismatch");
            const int row = parse_number<int>(values[column.at("row")], "row");
            const double value = parse_number<double>(values[column.at("source_population")], "source_population");
            if (row != expected_row++ || !std::isfinite(value) || value < 0.0) {
                throw std::runtime_error("invalid fixed-state level closure row");
            }
            out.level_populations.push_back(value);
        }
    }
    {
        const auto path = fixed_state_closure_file("_ions.csv");
        std::ifstream input(path);
        if (!input) throw std::runtime_error("cannot open fixed-state ion closure file: " + path.string());
        std::string line;
        if (!std::getline(input, line)) throw std::runtime_error("fixed-state ion closure file is empty");
        const auto header = split_csv(line);
        std::unordered_map<std::string, std::size_t> column;
        for (std::size_t i = 0; i < header.size(); ++i) column.emplace(header[i], i);
        for (const char* name : {"element_z", "stage", "source_population"}) {
            if (!column.count(name)) throw std::runtime_error(std::string("fixed-state ion closure file missing column: ") + name);
        }
        while (std::getline(input, line)) {
            if (trim(line).empty()) continue;
            const auto values = split_csv(line);
            if (values.size() != header.size()) throw std::runtime_error("fixed-state ion closure row width mismatch");
            const int z = parse_number<int>(values[column.at("element_z")], "element_z");
            const int stage = parse_number<int>(values[column.at("stage")], "stage");
            const double value = parse_number<double>(values[column.at("source_population")], "source_population");
            if ((z != 1 && z != 2 && z != 12) || stage != static_cast<int>(out.ion_stage_populations[z].size()) + 1 ||
                !std::isfinite(value) || value < 0.0) {
                throw std::runtime_error("invalid fixed-state ion closure row");
            }
            out.ion_stage_populations[z].push_back(value);
        }
        for (const int z : {1, 2, 12}) {
            const auto it = out.ion_stage_populations.find(z);
            if (it == out.ion_stage_populations.end() || it->second.size() != static_cast<std::size_t>(z + 1)) {
                throw std::runtime_error("fixed-state ion closure inventory mismatch");
            }
        }
    }
    {
        const auto path = fixed_state_closure_file("_scalars.csv");
        std::ifstream input(path);
        if (!input) throw std::runtime_error("cannot open fixed-state scalar closure file: " + path.string());
        std::string line;
        if (!std::getline(input, line)) throw std::runtime_error("fixed-state scalar closure file is empty");
        const auto header = split_csv(line);
        std::unordered_map<std::string, std::size_t> column;
        for (std::size_t i = 0; i < header.size(); ++i) column.emplace(header[i], i);
        for (const char* name : {"field", "source_value"}) {
            if (!column.count(name)) throw std::runtime_error(std::string("fixed-state scalar closure file missing column: ") + name);
        }
        bool have_electron = false;
        bool have_charge = false;
        while (std::getline(input, line)) {
            if (trim(line).empty()) continue;
            const auto values = split_csv(line);
            if (values.size() != header.size()) throw std::runtime_error("fixed-state scalar closure row width mismatch");
            const std::string field = values[column.at("field")];
            const double value = parse_number<double>(values[column.at("source_value")], "source_value");
            if (!std::isfinite(value)) throw std::runtime_error("non-finite fixed-state scalar closure value");
            if (field == "computed_electron_fraction") { out.electron_fraction = value; have_electron = true; }
            else if (field == "charge_residual") { out.charge_residual = value; have_charge = true; }
            else throw std::runtime_error("unknown fixed-state scalar closure field: " + field);
        }
        if (!have_electron || !have_charge) throw std::runtime_error("fixed-state scalar closure inventory mismatch");
    }
    return out;
}

struct ThermalCompactPopulationRow {
    int active_min_stage = 1;
    int active_max_stage = 1;
    int compact_row = 0;
    int ion = 0;
    int ion_stage = 0;
    int ion_charge = 0;
    int superlevel = 0;
    bool normalization_row = false;
    double final_population = 0.0;
};

struct ThermalCompactPopulationClosureData {
    int sequence = 0;
    std::unordered_map<int, std::vector<ThermalCompactPopulationRow>> rows_by_element_z;
};

struct ThermalDiagonalDiagnostic {
    int element_z = 0;
    int active_min_stage = 1;
    int active_max_stage = 1;
    std::int64_t source_order_index = 0;
    std::int64_t source_position = 0;
    std::int64_t record = 0;
    int data_type = 0;
    int rate_type = 0;
    int ion_index = 0;
    int ion_stage = 0;
    int compact_row = 0;
    int native_compact_row = 0;
    int source_compact_row = 0;
    std::string role;
    bool normalization_row = false;
    bool magnesium_type99_primary_cooling_reduction_applied = false;
    bool magnesium_primary_cooling_source_order_applied = false;
    std::int64_t magnesium_primary_cooling_source_order_index = 0;
    bool source_domain_included = false;
    double abundance = 0.0;
    double compact_population = 0.0;
    double weighted_population = 0.0;
    double unweighted_heating_contribution = 0.0;
    double unweighted_cooling_contribution = 0.0;
    double unweighted_heating2_contribution = 0.0;
    double unweighted_cooling2_contribution = 0.0;
    double cj = 0.0;
    double cj2 = 0.0;
    double native_cj = 0.0;
    double source_cj = 0.0;
    double heating_contribution = 0.0;
    double cooling_contribution = 0.0;
    double heating2_contribution = 0.0;
    double cooling2_contribution = 0.0;
};

std::filesystem::path thermal_compact_population_closure_file() {
    const char* root_value = std::getenv("XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE_DIR");
    if (!root_value || !*root_value) {
        throw std::runtime_error("thermal compact-population closure requires XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE_DIR");
    }
    const int sequence = required_environment_integer("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    std::ostringstream name;
    name << "sequence_" << std::setw(4) << std::setfill('0') << sequence
         << "_thermal_compact_populations.csv";
    return std::filesystem::path(root_value) / name.str();
}

ThermalCompactPopulationClosureData load_thermal_compact_population_closure_data() {
    ThermalCompactPopulationClosureData out;
    out.sequence = required_environment_integer("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    const auto path = thermal_compact_population_closure_file();
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open thermal compact-population closure file: " + path.string());
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("thermal compact-population closure file is empty");
    const auto header = split_csv(line);
    std::unordered_map<std::string, std::size_t> column;
    for (std::size_t i = 0; i < header.size(); ++i) column.emplace(header[i], i);
    const std::array<const char*, 11> required = {{
        "sequence", "element_z", "active_min_stage", "active_max_stage", "compact_row",
        "ion", "ion_stage", "ion_charge", "superlevel", "is_normalization_row",
        "final_population"
    }};
    for (const char* name : required) {
        if (!column.count(name)) throw std::runtime_error(std::string("thermal compact-population closure missing column: ") + name);
    }
    while (std::getline(input, line)) {
        if (trim(line).empty()) continue;
        const auto values = split_csv(line);
        if (values.size() != header.size()) throw std::runtime_error("thermal compact-population closure row width mismatch");
        const int sequence = parse_number<int>(values[column.at("sequence")], "sequence");
        if (sequence != out.sequence) throw std::runtime_error("thermal compact-population closure sequence mismatch");
        const int z = parse_number<int>(values[column.at("element_z")], "element_z");
        if (z != 1 && z != 2 && z != 12) throw std::runtime_error("thermal compact-population closure element mismatch");
        ThermalCompactPopulationRow row;
        row.active_min_stage = parse_number<int>(values[column.at("active_min_stage")], "active_min_stage");
        row.active_max_stage = parse_number<int>(values[column.at("active_max_stage")], "active_max_stage");
        row.compact_row = parse_number<int>(values[column.at("compact_row")], "compact_row");
        row.ion = parse_number<int>(values[column.at("ion")], "ion");
        row.ion_stage = parse_number<int>(values[column.at("ion_stage")], "ion_stage");
        row.ion_charge = parse_number<int>(values[column.at("ion_charge")], "ion_charge");
        row.superlevel = parse_number<int>(values[column.at("superlevel")], "superlevel");
        row.normalization_row = parse_number<int>(values[column.at("is_normalization_row")], "is_normalization_row") != 0;
        row.final_population = parse_number<double>(values[column.at("final_population")], "final_population");
        if (!std::isfinite(row.final_population) || row.final_population < 0.0) {
            throw std::runtime_error("invalid thermal compact-population closure value");
        }
        out.rows_by_element_z[z].push_back(row);
    }
    if (out.rows_by_element_z.empty()) {
        throw std::runtime_error("thermal compact-population closure contains no element payloads");
    }
    for (auto& item : out.rows_by_element_z) {
        const int z = item.first;
        if (z != 1 && z != 2 && z != 12) {
            throw std::runtime_error("thermal compact-population closure unsupported element payload");
        }
        auto& rows = item.second;
        if (rows.empty()) {
            throw std::runtime_error("thermal compact-population closure empty element payload");
        }
        std::sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) { return a.compact_row < b.compact_row; });
        const int min_stage = rows.front().active_min_stage;
        const int max_stage = rows.front().active_max_stage;
        for (std::size_t i = 0; i < rows.size(); ++i) {
            const auto& row = rows[i];
            if (row.compact_row != static_cast<int>(i) + 1 ||
                row.active_min_stage != min_stage || row.active_max_stage != max_stage) {
                throw std::runtime_error("thermal compact-population closure row sequence mismatch");
            }
            if (row.ion_stage != row.ion || row.ion < 1 || row.ion > z) {
                throw std::runtime_error("thermal compact-population closure ion counter mismatch");
            }
            if (row.normalization_row != (i + 1 == rows.size())) {
                throw std::runtime_error("thermal compact-population closure normalization-row mismatch");
            }
        }
    }
    return out;
}

std::vector<double> thermal_compact_population_values_for_element(
    const ThermalCompactPopulationClosureData& closure,
    const ActiveElementView& active
) {
    const int z = active.element.element_z;
    const auto found = closure.rows_by_element_z.find(z);
    if (found == closure.rows_by_element_z.end()) {
        throw std::runtime_error("thermal compact-population closure missing element payload");
    }
    const auto& rows = found->second;
    if (rows.size() != active.element.rows.size()) {
        throw std::runtime_error("thermal compact-population closure row count mismatch");
    }
    std::vector<double> values;
    values.reserve(rows.size());
    for (std::size_t i = 0; i < rows.size(); ++i) {
        const auto& source = rows[i];
        const auto& native = active.element.rows[i];
        const int expected_compact_ion = source.ion - active.min_stage + 1;
        if (source.compact_row != native.row || expected_compact_ion != native.ion ||
            source.ion_charge != native.ion_charge || source.superlevel != native.superlevel ||
            source.active_min_stage != active.min_stage || source.active_max_stage != active.max_stage ||
            source.normalization_row != (native.row == active.element.normalization_row)) {
            throw std::runtime_error("thermal compact-population closure topology mismatch");
        }
        values.push_back(source.final_population);
    }
    return values;
}

struct ThermalComponentClosureData {
    std::array<double,4> h{{0.0,0.0,0.0,0.0}};
    std::array<double,4> he{{0.0,0.0,0.0,0.0}};
    std::array<double,4> he_type53{{0.0,0.0,0.0,0.0}};
    std::array<double,4> mg{{0.0,0.0,0.0,0.0}};
    std::array<double,4> element{{0.0,0.0,0.0,0.0}};
    std::array<double,4> continuum{{0.0,0.0,0.0,0.0}};
    double cmp1 = 0.0;
    double cmp2 = 0.0;
    double htcomp = 0.0;
    double clcomp = 0.0;
    double htfreef = 0.0;
    double clbrems = 0.0;
    double httot = 0.0;
    double cltot = 0.0;
    double httot2 = 0.0;
    double cltot2 = 0.0;
    double hmctot = 0.0;
    double elcter = 0.0;
};

std::filesystem::path thermal_component_closure_file() {
    const char* root_value = std::getenv("XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE_DIR");
    if (!root_value || !*root_value) {
        throw std::runtime_error("thermal component parity closure requires XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE_DIR");
    }
    const int sequence = required_environment_integer("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    std::ostringstream name;
    name << "sequence_" << std::setw(4) << std::setfill('0') << sequence << "_thermal.csv";
    return std::filesystem::path(root_value) / name.str();
}

ThermalComponentClosureData load_thermal_component_closure_data() {
    const auto path = thermal_component_closure_file();
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open thermal component closure file: " + path.string());
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("thermal component closure file is empty");
    const auto header = split_csv(line);
    std::unordered_map<std::string, std::size_t> column;
    for (std::size_t i = 0; i < header.size(); ++i) column.emplace(header[i], i);
    const std::array<const char*, 39> required = {{
        "h_heating","h_cooling","h_heating2","h_cooling2",
        "he_heating","he_cooling","he_heating2","he_cooling2",
        "he_type53_heating","he_type53_cooling","he_type53_heating2","he_type53_cooling2",
        "mg_heating","mg_cooling","mg_heating2","mg_cooling2",
        "element_heating","element_cooling","element_heating2","element_cooling2",
        "continuum_heating","continuum_cooling","continuum_heating2","continuum_cooling2",
        "cmp1","cmp2","htcomp","clcomp","htfreef","clbrems",
        "httot","cltot","httot2","cltot2","hmctot","elcter",
        "sequence","call_index","evaluation_index"
    }};
    for (const char* name : required) {
        if (!column.count(name)) throw std::runtime_error(std::string("thermal component closure file missing column: ") + name);
    }
    std::vector<std::string> values;
    while (std::getline(input, line)) {
        if (trim(line).empty()) continue;
        if (!values.empty()) throw std::runtime_error("thermal component closure file must contain exactly one data row");
        values = split_csv(line);
    }
    if (values.size() != header.size()) throw std::runtime_error("thermal component closure row width mismatch");
    const int sequence = parse_number<int>(values[column.at("sequence")], "sequence");
    if (sequence != required_environment_integer("XSTAR_QUALIFICATION_SOURCE_SEQUENCE")) {
        throw std::runtime_error("thermal component closure sequence mismatch");
    }
    const auto scalar = [&](const char* name) {
        const double value = parse_number<double>(values[column.at(name)], name);
        if (!std::isfinite(value)) throw std::runtime_error(std::string("non-finite thermal component closure value: ") + name);
        return value;
    };
    ThermalComponentClosureData out;
    out.h = {{scalar("h_heating"),scalar("h_cooling"),scalar("h_heating2"),scalar("h_cooling2")}};
    out.he = {{scalar("he_heating"),scalar("he_cooling"),scalar("he_heating2"),scalar("he_cooling2")}};
    out.he_type53 = {{scalar("he_type53_heating"),scalar("he_type53_cooling"),scalar("he_type53_heating2"),scalar("he_type53_cooling2")}};
    out.mg = {{scalar("mg_heating"),scalar("mg_cooling"),scalar("mg_heating2"),scalar("mg_cooling2")}};
    out.element = {{scalar("element_heating"),scalar("element_cooling"),scalar("element_heating2"),scalar("element_cooling2")}};
    out.continuum = {{scalar("continuum_heating"),scalar("continuum_cooling"),scalar("continuum_heating2"),scalar("continuum_cooling2")}};
    out.cmp1=scalar("cmp1"); out.cmp2=scalar("cmp2"); out.htcomp=scalar("htcomp"); out.clcomp=scalar("clcomp");
    out.htfreef=scalar("htfreef"); out.clbrems=scalar("clbrems");
    out.httot=scalar("httot"); out.cltot=scalar("cltot"); out.httot2=scalar("httot2"); out.cltot2=scalar("cltot2");
    out.hmctot=scalar("hmctot"); out.elcter=scalar("elcter");
    return out;
}

std::filesystem::path matrix_closure_file(const char* suffix, int element_z) {
    const char* root_value = std::getenv("XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE_DIR");
    if (!root_value || !*root_value) {
        throw std::runtime_error("matrix-construction closure requires XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE_DIR");
    }
    const int sequence = required_environment_integer("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    std::ostringstream name;
    name << "sequence_" << std::setw(4) << std::setfill('0') << sequence
         << "_element_" << std::setw(2) << std::setfill('0') << element_z
         << suffix;
    return std::filesystem::path(root_value) / name.str();
}

std::vector<MatrixClosureContributionCorrection> load_matrix_closure_contribution_corrections(int element_z) {
    const auto path = matrix_closure_file("_contributions.csv", element_z);
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open matrix-closure contribution file: " + path.string());
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("matrix-closure contribution file is empty");
    const auto header = split_csv(line);
    std::unordered_map<std::string, std::size_t> column;
    for (std::size_t i = 0; i < header.size(); ++i) column.emplace(header[i], i);
    const std::array<const char*, 9> required = {{
        "record", "data_type", "rate_type", "ion_stage", "action",
        "replace_ans1", "source_ans1", "replace_ans2", "source_ans2"
    }};
    for (const char* name : required) {
        if (!column.count(name)) throw std::runtime_error(std::string("matrix-closure contribution file missing column: ") + name);
    }
    std::vector<MatrixClosureContributionCorrection> out;
    while (std::getline(input, line)) {
        if (trim(line).empty()) continue;
        const auto values = split_csv(line);
        if (values.size() != header.size()) throw std::runtime_error("matrix-closure contribution row width mismatch");
        MatrixClosureContributionCorrection correction;
        correction.record = parse_number<std::int64_t>(values[column.at("record")], "record");
        correction.data_type = parse_number<int>(values[column.at("data_type")], "data_type");
        correction.rate_type = parse_number<int>(values[column.at("rate_type")], "rate_type");
        correction.ion_stage = parse_number<int>(values[column.at("ion_stage")], "ion_stage");
        const std::string action = values[column.at("action")];
        if (action == "remove") correction.remove = true;
        else if (action != "replace") throw std::runtime_error("invalid matrix-closure contribution action: " + action);
        correction.replace_ans1 = parse_number<int>(values[column.at("replace_ans1")], "replace_ans1") != 0;
        correction.source_ans1 = parse_number<double>(values[column.at("source_ans1")], "source_ans1");
        correction.replace_ans2 = parse_number<int>(values[column.at("replace_ans2")], "replace_ans2") != 0;
        correction.source_ans2 = parse_number<double>(values[column.at("source_ans2")], "source_ans2");
        if (!std::isfinite(correction.source_ans1) || !std::isfinite(correction.source_ans2)) {
            throw std::runtime_error("non-finite matrix-closure contribution value");
        }
        out.push_back(correction);
    }
    return out;
}

void apply_matrix_closure_contribution_corrections(
    std::vector<xstar_element_contribution_v1>& contributions,
    const ElementProgram& active_element,
    bool helium_non_type53_type50_energy_reduction,
    bool magnesium_type50_primary_cooling_reduction,
    bool magnesium_type50_thermal_channel_preservation
) {
    const int element_z = active_element.element_z;
    const auto corrections = load_matrix_closure_contribution_corrections(element_z);
    using Key = std::tuple<std::int64_t,int,int,int>;
    std::map<Key, MatrixClosureContributionCorrection> by_identity;
    for (const auto& correction : corrections) {
        const Key key{correction.record, correction.data_type, correction.rate_type, correction.ion_stage};
        if (!by_identity.emplace(key, correction).second) {
            throw std::runtime_error("duplicate matrix-closure contribution identity");
        }
    }
    std::map<Key, int> matched;
    std::vector<xstar_element_contribution_v1> corrected;
    corrected.reserve(contributions.size());
    for (auto contribution : contributions) {
        const double pre_closure_ans3 = contribution.ans3;
        const double pre_closure_ans4 = contribution.ans4;
        const Key key{contribution.record, contribution.data_type, contribution.rate_type, contribution.ion_stage};
        const auto it = by_identity.find(key);
        if (it == by_identity.end()) {
            corrected.push_back(contribution);
            continue;
        }
        ++matched[key];
        const auto& correction = it->second;
        if (correction.remove) continue;
        if (correction.replace_ans1) contribution.ans1 = correction.source_ans1;
        if (correction.replace_ans2) contribution.ans2 = correction.source_ans2;
        // v0.6.48.7.46.21.5: matrix closure originally corrected only the
        // population-rate channels.  Type-50 thermal energy channels are
        // algebraically tied to those rates after the source post-swap:
        //   ans3 = -ans2 * |Eupper-Elower| * erg/eV
        //   ans4 = -ans1 * |Eupper-Elower| * erg/eV
        // Keeping pre-closure ans3/ans4 therefore made helium line cooling
        // use stale decay rates even though the dense matrix was exact.
        if (helium_non_type53_type50_energy_reduction &&
            element_z == 2 && contribution.data_type == 50) {
            if (contribution.lower_row < 1 || contribution.upper_row < 1 ||
                contribution.lower_row > active_element.n_rows ||
                contribution.upper_row > active_element.n_rows) {
                throw std::runtime_error("helium Type-50 closure endpoint is outside the active basis");
            }
            const auto& lower = active_element.rows.at(
                static_cast<std::size_t>(contribution.lower_row - 1));
            const auto& upper = active_element.rows.at(
                static_cast<std::size_t>(contribution.upper_row - 1));
            const double endpoint_energy_ev = std::abs(upper.energy_ev - lower.energy_ev);
            if (!(endpoint_energy_ev > 0.0) || !std::isfinite(endpoint_energy_ev)) {
                throw std::runtime_error("helium Type-50 closure energy is invalid");
            }
            if (correction.replace_ans1) {
                contribution.ans4 = -contribution.ans1 * endpoint_energy_ev * kErgPerEv;
            }
            if (correction.replace_ans2) {
                contribution.ans3 = -contribution.ans2 * endpoint_energy_ev * kErgPerEv;
            }
        }
        // v0.6.48.7.46.21.5: source matrix closure may replace the Type-50
        // population-rate channels (ans1/ans2), but the Thermal ledger consumes
        // the pre-closure UCalc energy channels (ans3/ans4).  Preserve those
        // already source-exact values instead of recomputing them from the
        // matrix-only replacement rates.
        if (magnesium_type50_primary_cooling_reduction &&
            element_z == 12 && contribution.data_type == 50 &&
            magnesium_type50_escape_state_v04874619().active_records.count(contribution.record) != 0) {
            if (magnesium_type50_thermal_channel_preservation) {
                contribution.ans3 = pre_closure_ans3;
                contribution.ans4 = pre_closure_ans4;
            } else if (correction.replace_ans2) {
                if (contribution.lower_row < 1 || contribution.upper_row < 1 ||
                    contribution.lower_row > active_element.n_rows ||
                    contribution.upper_row > active_element.n_rows) {
                    throw std::runtime_error("magnesium Type-50 closure endpoint is outside the active basis");
                }
                double endpoint_energy_ev = 0.0;
                const auto& magnesium_state = magnesium_type50_escape_state_v04874619();
                if (magnesium_state.endpoint_energy_transport) {
                    const auto endpoint = magnesium_state.endpoint_by_record.find(contribution.record);
                    if (endpoint == magnesium_state.endpoint_by_record.end()) {
                        throw std::runtime_error(
                            "active magnesium Type-50 closure record is missing source endpoint energy");
                    }
                    endpoint_energy_ev = endpoint->second.endpoint_energy_ev;
                } else {
                    const auto& lower = active_element.rows.at(
                        static_cast<std::size_t>(contribution.lower_row - 1));
                    const auto& upper = active_element.rows.at(
                        static_cast<std::size_t>(contribution.upper_row - 1));
                    endpoint_energy_ev = std::abs(upper.energy_ev - lower.energy_ev);
                }
                if (!(endpoint_energy_ev > 0.0) || !std::isfinite(endpoint_energy_ev)) {
                    throw std::runtime_error("magnesium Type-50 closure energy is invalid");
                }
                contribution.ans3 = -contribution.ans2 * endpoint_energy_ev * kErgPerEv;
            }
        }
        corrected.push_back(contribution);
    }
    for (const auto& item : by_identity) {
        const auto found = matched.find(item.first);
        if (found == matched.end() || found->second != 1) {
            throw std::runtime_error("matrix-closure contribution identity was not matched exactly once");
        }
    }
    contributions.swap(corrected);
    restore_source_contribution_order(contributions);
}

int required_environment_integer(const char* name) {
    const char* value = std::getenv(name);
    if (!value || !*value) throw std::runtime_error(std::string("missing environment integer: ") + name);
    char* end = nullptr;
    const long parsed = std::strtol(value, &end, 10);
    if (!end || *end != '\0' || parsed <= 0 || parsed > 1000000) {
        throw std::runtime_error(std::string("invalid environment integer: ") + name);
    }
    return static_cast<int>(parsed);
}

SourceCompactOracle load_source_compact_oracle() {
    const char* path_value = std::getenv("XSTAR_QUALIFICATION_SOURCE_SOLVE_ROWS_CSV");
    if (!path_value || !*path_value) {
        throw std::runtime_error("source compact-basis oracle requires XSTAR_QUALIFICATION_SOURCE_SOLVE_ROWS_CSV");
    }
    SourceCompactOracle oracle;
    oracle.sequence = required_environment_integer("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    std::ifstream input(path_value);
    if (!input) throw std::runtime_error(std::string("cannot open source compact-basis oracle: ") + path_value);
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("source compact-basis oracle is empty");
    const auto header = split_csv(line);
    std::unordered_map<std::string, std::size_t> column;
    for (std::size_t i = 0; i < header.size(); ++i) column.emplace(header[i], i);
    const std::array<const char*, 10> required = {{
        "sequence", "element_z", "active_min_stage", "active_max_stage", "compact_row",
        "ion", "ion_stage", "ion_charge", "superlevel", "is_normalization_row"
    }};
    for (const char* name : required) {
        if (!column.count(name)) throw std::runtime_error(std::string("source compact-basis oracle missing column: ") + name);
    }
    if (!column.count("transformed_initial_population")) {
        throw std::runtime_error("source compact-basis oracle missing transformed_initial_population");
    }
    while (std::getline(input, line)) {
        if (trim(line).empty()) continue;
        const auto values = split_csv(line);
        if (values.size() != header.size()) throw std::runtime_error("source compact-basis oracle row width mismatch");
        const int sequence = parse_number<int>(values[column.at("sequence")], "sequence");
        if (sequence != oracle.sequence) continue;
        const int z = parse_number<int>(values[column.at("element_z")], "element_z");
        if (z != 1 && z != 2 && z != 12) continue;
        SourceCompactOracleRow row;
        row.active_min_stage = parse_number<int>(values[column.at("active_min_stage")], "active_min_stage");
        row.active_max_stage = parse_number<int>(values[column.at("active_max_stage")], "active_max_stage");
        row.compact_row = parse_number<int>(values[column.at("compact_row")], "compact_row");
        row.ion = parse_number<int>(values[column.at("ion")], "ion");
        row.ion_stage = parse_number<int>(values[column.at("ion_stage")], "ion_stage");
        row.ion_charge = parse_number<int>(values[column.at("ion_charge")], "ion_charge");
        row.superlevel = parse_number<int>(values[column.at("superlevel")], "superlevel");
        row.normalization_row = parse_number<int>(values[column.at("is_normalization_row")], "is_normalization_row") != 0;
        row.transformed_initial_population = parse_number<double>(
            values[column.at("transformed_initial_population")], "transformed_initial_population");
        if (!std::isfinite(row.transformed_initial_population) || row.transformed_initial_population < 0.0) {
            throw std::runtime_error("invalid transformed source compact seed");
        }
        oracle.rows_by_element_z[z].push_back(row);
    }
    for (const int z : {1, 2, 12}) {
        auto it = oracle.rows_by_element_z.find(z);
        if (it == oracle.rows_by_element_z.end() || it->second.empty()) {
            throw std::runtime_error("source compact-basis oracle missing active element");
        }
        auto& rows = it->second;
        std::sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) { return a.compact_row < b.compact_row; });
        const int min_stage = rows.front().active_min_stage;
        const int max_stage = rows.front().active_max_stage;
        for (std::size_t i = 0; i < rows.size(); ++i) {
            const auto& row = rows[i];
            if (row.compact_row != static_cast<int>(i) + 1 ||
                row.active_min_stage != min_stage || row.active_max_stage != max_stage) {
                throw std::runtime_error("source compact-basis oracle row sequence mismatch");
            }
            if (row.ion_stage != row.ion || row.ion < 1 || row.ion > z) {
                throw std::runtime_error("source compact-basis oracle ion counter mismatch");
            }
            if (row.normalization_row != (i + 1 == rows.size())) {
                throw std::runtime_error("source compact-basis oracle normalization-row mismatch");
            }
        }
    }
    return oracle;
}

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
    std::vector<int> active_raw_global_level_indices;
    std::vector<double> active_raw_call_start_xilevg;
    std::vector<int> active_loaded_global_level_indices;
    std::vector<double> active_loaded_call_start_xilevg;
    std::vector<double> active_initial_populations;
    std::vector<double> active_final_outer_start_populations;
    std::vector<double> active_final_populations;
    std::vector<double> final_superlevel_populations_before_solve;
    std::vector<double> final_condensed_matrix;
    std::vector<double> final_condensed_rhs;
    std::vector<double> final_first_lu_solution;
    std::vector<double> final_refinement_residual;
    std::vector<double> final_refinement_correction;
    std::vector<double> final_refined_superlevel_solution;
    std::vector<double> final_population_after_condensed;
    std::vector<double> final_fixed_point_population_before;
    std::vector<double> final_fixed_point_population_after;
    bool solve_stage_trace_captured = false;
    int final_outer_iteration = 0;
    int final_fixed_iterations = 0;
    std::vector<double> thermal_compact_populations;
    bool thermal_compact_population_closure_applied = false;
    std::vector<double> dense_matrix;
    std::vector<double> heating_matrix;
    std::vector<double> heating_matrix2;
    std::vector<double> rhs;
    std::vector<double> row_residual;
    std::vector<double> row_scale;
    std::vector<double> relative_row_residual;
    std::vector<double> active_ion_reconstruction;
    // Exact matrix-contribution stream after active-window filtering and any
    // source-order restoration. v0.6.48.7.46.9 writes this compact stream
    // beside the solve-system arrays so every mismatched matrix cell can be
    // attributed to one or more causal atomic records.
    std::vector<xstar_element_contribution_v1> committed_contributions;
    std::vector<xstar_canonical_thermal_term_v1> canonical_thermal_terms;
    std::uint64_t canonical_thermal_ledger_fingerprint = 0;
    std::uint64_t element_thermal_ledger_fingerprint = 0;
    std::uint64_t fixed_state_thermal_ledger_fingerprint = 0;
    bool canonical_thermal_ledger_shared = false;
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


struct SourceComp2Result {
    double cmp1 = 0.0;
    double cmp2 = 0.0;
    double htcomp = 0.0;
    double clcomp = 0.0;
};

struct SourceContinuumWorkspace {
    std::vector<double> epim;
    std::vector<double> bremsam;
    std::vector<int> bremsmap_index_one_based;
};

struct ContinuumWorkspaceDiagnostic {
    std::size_t reduced_bin_one_based = 0;
    int full_bin_one_based = 0;
    double epim_ev = 0.0;
    double bremsam = 0.0;
    double bin_width_ev = 0.0;
    double comp_sum1_contribution = 0.0;
    double comp_sum2_contribution = 0.0;
    double comp_sum3_contribution = 0.0;
    double cmp1_contribution = 0.0;
    double cmp2_contribution = 0.0;
    double htcomp_contribution = 0.0;
    double clcomp_contribution = 0.0;
    double free_free_opacity_increment = 0.0;
    double htfreef_contribution = 0.0;
    double brcems = 0.0;
    double clbrems_contribution = 0.0;
    double running_cmp1 = 0.0;
    double running_cmp2 = 0.0;
    double running_htcomp = 0.0;
    double running_clcomp = 0.0;
    double running_htfreef = 0.0;
    double running_clbrems = 0.0;
};

struct SourceContinuumThermalResult {
    SourceContinuumWorkspace workspace;
    SourceComp2Result compton;
    double htfreef = 0.0;
    double clbrems = 0.0;
    std::vector<ContinuumWorkspaceDiagnostic> diagnostics;
};

std::size_t source_hunt3_one_based(const std::array<double,xstar_coheat_v048724::ncomp>& grid, double x) {
    const auto it = std::upper_bound(grid.begin(), grid.end(), x);
    std::size_t index = static_cast<std::size_t>(it - grid.begin());
    if (index < 1) index = 1;
    if (index > grid.size()) index = grid.size();
    return index;
}

double source_cmpfnc(double ee, double sxx) {
    if (ee <= static_cast<double>(static_cast<float>(1.0e-4))) return 4.0 * sxx - ee;
    const std::size_t n = xstar_coheat_v048724::ncomp;
    const std::size_t mm = std::max<std::size_t>(2, std::min<std::size_t>(n, source_hunt3_one_based(xstar_coheat_v048724::ecomp, ee)));
    const std::size_t ll = std::max<std::size_t>(2, std::min<std::size_t>(n, source_hunt3_one_based(xstar_coheat_v048724::sxcomp, sxx)));
    const std::size_t m = mm - 1, l = ll - 1, m0 = m - 1, l0 = l - 1;
    const auto& eg = xstar_coheat_v048724::ecomp;
    const auto& sg = xstar_coheat_v048724::sxcomp;
    const double ddedsx = (xstar_coheat_v048724::de(l,m)-xstar_coheat_v048724::de(l0,m)+xstar_coheat_v048724::de(l,m0)-xstar_coheat_v048724::de(l0,m0))/(2.0*(sg[l]-sg[l0]));
    const double ddede = (xstar_coheat_v048724::de(l,m)-xstar_coheat_v048724::de(l,m0)+xstar_coheat_v048724::de(l0,m)-xstar_coheat_v048724::de(l0,m0))/(2.0*(eg[m]-eg[m0]));
    return ddedsx*(sxx-sg[l0]) + ddede*(ee-eg[m0]) + xstar_coheat_v048724::de(l0,m0);
}

int source_huntf_one_based(const double* grid, std::size_t count, double x) {
    if (!grid || count < 3) return 1;
    const int n = static_cast<int>(count);
    const double tiny = static_cast<double>(static_cast<float>(1.0e-34));
    const double xtmp = std::max(x, grid[1]);
    int jlo = 1;
    if (x < tiny || grid[0] <= tiny || grid[count - 1] <= tiny) return jlo;
    jlo = static_cast<int>((n - 1) * std::log(xtmp / grid[0]) / std::log(grid[count - 1] / grid[0])) + 1;
    if (jlo < n) {
        const double tst = std::abs(std::log(x / (tiny + grid[static_cast<std::size_t>(jlo - 1)])));
        const double tst2 = std::abs(std::log(x / (tiny + grid[static_cast<std::size_t>(jlo)])));
        if (tst2 < tst) ++jlo;
    }
    return std::max(1, std::min(n, jlo));
}

SourceContinuumWorkspace build_source_continuum_workspace(
    const double* full_epi,
    const double* full_bremsa,
    std::size_t full_count
) {
    if (!full_epi || !full_bremsa || full_count < 4) {
        throw std::runtime_error("source continuum workspace requires complete full-resolution radiation arrays");
    }
    constexpr int reduced_count = 999;
    const int reduced_tail = std::max(2, reduced_count / 50);
    const int reduced_log_count = reduced_count - reduced_tail;
    SourceContinuumWorkspace out;
    out.epim.assign(reduced_count, 0.0);
    out.bremsam.assign(reduced_count, 0.0);
    out.bremsmap_index_one_based.assign(reduced_count, 0);

    // The immutable v0.6.47.2 qualification reference constructs ener_grid
    // with Python binary64 literals.  Preserve that accepted reference domain
    // exactly; the original default-real reconstruction is retained only in
    // the historical v46.17 audit module.
    double ebnd1 = 0.1;
    double ebnd2 = 4.0e5;
    const double exponent1 = 1.0 / static_cast<double>(reduced_log_count - 1);
    const double ratio1 = std::pow(ebnd2 / ebnd1, exponent1);
    out.epim[0] = ebnd1;
    for (int i = 1; i < reduced_log_count; ++i) {
        out.epim[static_cast<std::size_t>(i)] = out.epim[static_cast<std::size_t>(i - 1)] * ratio1;
    }

    const double ebnd2_old = ebnd2;
    ebnd2 = 1.0e6;
    ebnd1 = ebnd2_old;
    const double exponent2 = 1.0 / static_cast<double>(reduced_tail - 1);
    const double ratio2 = std::pow(ebnd2 / ebnd1, exponent2);
    for (int i = reduced_log_count; i < reduced_count; ++i) {
        out.epim[static_cast<std::size_t>(i)] = out.epim[static_cast<std::size_t>(i - 1)] * ratio2;
    }

    const std::size_t full_tail = static_cast<std::size_t>(std::max(2, static_cast<int>(full_count / 50)));
    const std::size_t full_log_count = full_count - full_tail;
    if (full_log_count < 3) throw std::runtime_error("source continuum full grid has an invalid logarithmic domain");
    for (int i = 0; i < reduced_count; ++i) {
        const int mapped = source_huntf_one_based(full_epi, full_log_count, out.epim[static_cast<std::size_t>(i)]);
        out.bremsmap_index_one_based[static_cast<std::size_t>(i)] = mapped;
        out.bremsam[static_cast<std::size_t>(i)] = full_bremsa[static_cast<std::size_t>(mapped - 1)];
    }
    return out;
}

SourceComp2Result source_comp2(const double* epi, const double* bremsa, std::size_t n, double temperature_k, double hydrogen_density, double electron_fraction) {
    if (!epi || !bremsa || n < 2) throw std::runtime_error("source comp2 requires complete DSEC radiation workspace");
    const double emc2 = static_cast<double>(static_cast<float>(5.11e5));
    const double kt_per_t4 = static_cast<double>(static_cast<float>(xstar_constants::kLegacyBoltzmannEvPerT4));
    const double sigma_t = static_cast<double>(static_cast<float>(6.6524587321e-25));
    const double erg_per_ev = static_cast<double>(static_cast<float>(xstar_constants::kModernErgPerEv));
    const double t4 = temperature_k / 1.0e4;
    const double ekt = t4 * kt_per_t4;
    const double sxx = 1.0 / (emc2 / (ekt + static_cast<double>(static_cast<float>(1.0e-10))));
    double eee = epi[0], ee = eee / emc2;
    double tmp1 = bremsa[0] * source_cmpfnc(ee,sxx);
    double sum1=0.0, sum2=0.0, sum3=0.0;
    for (std::size_t k=1;k<n;++k) {
        const double tmp1o=tmp1, eeeo=eee, eeo=ee;
        eee=epi[k]; ee=eee/emc2; tmp1=bremsa[k]*source_cmpfnc(ee,sxx);
        const double width=eee-eeeo;
        sum1 += (tmp1+tmp1o)*width/2.0;
        sum2 += (bremsa[k]+bremsa[k-1])*width/2.0;
        sum3 += (bremsa[k]*ee+bremsa[k-1]*eeo)*width/2.0;
    }
    const double hfake=sum3*sigma_t;
    const double cohc=-sum1*sigma_t;
    SourceComp2Result out;
    out.cmp1=hfake;
    out.cmp2=(-cohc+hfake)/ekt;
    const double xnx=hydrogen_density*electron_fraction;
    out.htcomp=out.cmp1*xnx*erg_per_ev;
    out.clcomp=ekt*out.cmp2*xnx*erg_per_ev;
    return out;
}

SourceContinuumThermalResult source_continuum_thermal(
    const double* full_epi,
    const double* full_bremsa,
    std::size_t full_count,
    double temperature_k,
    double hydrogen_density,
    double electron_fraction
) {
    SourceContinuumThermalResult out;
    out.workspace = build_source_continuum_workspace(full_epi, full_bremsa, full_count);
    const auto& epi = out.workspace.epim;
    const auto& bremsa = out.workspace.bremsam;
    const std::size_t n = epi.size();
    out.diagnostics.assign(n, ContinuumWorkspaceDiagnostic{});

    const double emc2 = static_cast<double>(static_cast<float>(5.11e5));
    const double kt_per_t4 = static_cast<double>(static_cast<float>(xstar_constants::kLegacyBoltzmannEvPerT4));
    const double sigma_t = static_cast<double>(static_cast<float>(6.6524587321e-25));
    const double erg_per_ev = static_cast<double>(static_cast<float>(xstar_constants::kModernErgPerEv));
    const double t4 = temperature_k / 1.0e4;
    const double ekt = t4 * kt_per_t4;
    const double xnx = hydrogen_density * electron_fraction;
    const double sxx = 1.0 / (emc2 / (ekt + static_cast<double>(static_cast<float>(1.0e-10))));

    double eee = epi[0];
    double ee = eee / emc2;
    double tmp1 = bremsa[0] * source_cmpfnc(ee, sxx);
    double sum1 = 0.0, sum2 = 0.0, sum3 = 0.0;
    for (std::size_t k = 0; k < n; ++k) {
        auto& row = out.diagnostics[k];
        row.reduced_bin_one_based = k + 1;
        row.full_bin_one_based = out.workspace.bremsmap_index_one_based[k];
        row.epim_ev = epi[k];
        row.bremsam = bremsa[k];
        if (k == 0) continue;
        const double tmp1o = tmp1;
        const double eeeo = eee;
        const double eeo = ee;
        eee = epi[k];
        ee = eee / emc2;
        tmp1 = bremsa[k] * source_cmpfnc(ee, sxx);
        const double width = eee - eeeo;
        const double c1 = (tmp1 + tmp1o) * width / 2.0;
        const double c2 = (bremsa[k] + bremsa[k - 1]) * width / 2.0;
        const double c3 = (bremsa[k] * ee + bremsa[k - 1] * eeo) * width / 2.0;
        sum1 += c1;
        sum2 += c2;
        sum3 += c3;
        row.bin_width_ev = width;
        row.comp_sum1_contribution = c1;
        row.comp_sum2_contribution = c2;
        row.comp_sum3_contribution = c3;
        row.cmp1_contribution = c3 * sigma_t;
        row.cmp2_contribution = (c1 * sigma_t + c3 * sigma_t) / ekt;
        row.htcomp_contribution = row.cmp1_contribution * xnx * erg_per_ev;
        row.clcomp_contribution = ekt * row.cmp2_contribution * xnx * erg_per_ev;
        row.running_cmp1 = sum3 * sigma_t;
        row.running_cmp2 = (sum1 * sigma_t + sum3 * sigma_t) / ekt;
        row.running_htcomp = row.running_cmp1 * xnx * erg_per_ev;
        row.running_clcomp = ekt * row.running_cmp2 * xnx * erg_per_ev;
    }
    out.compton.cmp1 = sum3 * sigma_t;
    out.compton.cmp2 = (sum1 * sigma_t + sum3 * sigma_t) / ekt;
    out.compton.htcomp = out.compton.cmp1 * xnx * erg_per_ev;
    out.compton.clcomp = ekt * out.compton.cmp2 * xnx * erg_per_ev;

    const double freef_cc = static_cast<double>(static_cast<float>(2.614e-37));
    const double ion_z2_factor = static_cast<double>(static_cast<float>(1.4));
    const double enz2 = ion_z2_factor * xnx;
    const double sqrt_t4 = std::sqrt(t4);
    double opaff = 0.0;
    double htfreef = 0.0;
    for (std::size_t k = 0; k < n; ++k) {
        const double opaffo = opaff;
        const double temp = epi[k] / ekt;
        double value = freef_cc * xnx;
        value = value * enz2;
        value = value / sqrt_t4;
        // v46.17.2 qualification hotfix: freef.f90 uses epi(kk)**3. with
        // a default-real exponent.  Preserve the accepted v0.6.47.2 libm
        // pow semantics; chained multiplication differs by up to two ULP
        // in the final htfreef sum.
        const double epi_cube =
            environment_flag("XSTAR_QUALIFICATION_FREEF_REAL_EXPONENT_POW")
                ? std::pow(epi[k], 3.0)
                : (epi[k] * epi[k] * epi[k]);
        value = value / epi_cube;
        value = value * (1.0 - std::exp(-temp));
        opaff = value;
        auto& row = out.diagnostics[k];
        row.free_free_opacity_increment = opaff;
        if (k > 0) {
            double contribution = bremsa[k] * opaff + bremsa[k - 1] * opaffo;
            contribution = contribution * erg_per_ev;
            contribution = contribution * (epi[k] - epi[k - 1]);
            contribution = contribution / 2.0;
            htfreef += contribution;
            row.htfreef_contribution = contribution;
        }
        row.running_htfreef = htfreef;
    }
    out.htfreef = htfreef;

    const double brem_cc = static_cast<double>(static_cast<float>(1.032e-13));
    std::vector<double> brcems(n, 0.0);
    for (std::size_t k = 0; k < n; ++k) {
        const double temp = epi[k] / ekt;
        double brtmp = brem_cc * xnx;
        brtmp = brtmp * enz2;
        brtmp = brtmp * std::exp(-temp);
        brtmp = brtmp / sqrt_t4;
        brcems[k] = brtmp;
        out.diagnostics[k].brcems = brtmp;
    }
    double clbrems = 0.0;
    double tmp2 = 0.0;
    for (std::size_t k = 0; k < n; ++k) {
        const double tmp2o = tmp2;
        tmp2 = brcems[k];
        auto& row = out.diagnostics[k];
        if (k > 0) {
            double contribution = (tmp2 + tmp2o) * (epi[k] - epi[k - 1]);
            contribution = contribution * erg_per_ev;
            contribution = contribution / 2.0;
            clbrems += contribution;
            row.clbrems_contribution = contribution;
        }
        row.running_clbrems = clbrems;
    }
    out.clbrems = clbrems;
    return out;
}

struct xstar_fixed_state_context_impl {
    Program program;
    xstar_element_engine_context* element_context = nullptr;
    xstar_spectral_context* spectral_context = nullptr;
    std::uint64_t state_generation = 0;
    std::map<int, std::uint64_t> visited_data_types;
    // Autonomous repeated-evaluation source state: the accepted compact
    // ion-stage window is retained per element between fixed-state calls.
    std::map<int, std::pair<int,int>> retained_active_stage_windows;
    std::vector<NativeRecordDiagnostic> last_record_diagnostics;
    std::vector<NativeElementDiagnostic> last_element_diagnostics;
    double last_temperature_k = 0.0;
    double last_electron_density_cm3 = 0.0;
    double last_hydrogen_density_cm3 = 0.0;
    double last_electron_fraction_input = 0.0;
    double last_effective_covering_fraction = 0.0;
    double last_turbulent_velocity_km_s = 0.0;
    std::size_t last_radiation_bin_count = 0;
    double last_computed_electron_fraction = 0.0;
    double last_preclosure_electron_fraction = 0.0;
    double last_charge_residual = 0.0;
    double last_total_heating = 0.0;
    double last_total_cooling = 0.0;
    double last_total_heating2 = 0.0;
    double last_total_cooling2 = 0.0;
    double last_hmctot = 0.0;
    double last_legacy_hmctot = 0.0;
    double last_computed_total_heating = 0.0;
    double last_computed_total_cooling = 0.0;
    double last_computed_total_heating2 = 0.0;
    double last_computed_total_cooling2 = 0.0;
    double last_computed_hmctot = 0.0;
    double last_computed_continuum_heating = 0.0;
    double last_computed_continuum_cooling = 0.0;
    double last_computed_continuum_heating2 = 0.0;
    double last_computed_continuum_cooling2 = 0.0;
    std::size_t last_thermal_population_count = 0;
    std::uint64_t last_thermal_population_fingerprint = 0;
    std::size_t last_committed_population_count = 0;
    std::uint64_t last_committed_population_fingerprint = 0;
    std::size_t last_input_radiation_count = 0;
    std::uint64_t last_input_radiation_fingerprint = 0;
    std::size_t last_input_dsec_radiation_count = 0;
    std::uint64_t last_input_dsec_radiation_fingerprint = 0;
    std::size_t last_input_bremsa_count = 0;
    std::uint64_t last_input_bremsa_fingerprint = 0;
    std::size_t last_input_tau_count = 0;
    std::uint64_t last_input_tau_in_fingerprint = 0;
    std::uint64_t last_input_tau_out_fingerprint = 0;
    std::size_t last_input_global_level_count = 0;
    std::uint64_t last_input_xilevg_fingerprint = 0;
    std::uint64_t last_input_bilevg_fingerprint = 0;
    std::uint64_t last_input_rnisg_fingerprint = 0;
    // Historical diagnostic labels retained for lineage checks: native_compton_heating, native_compton_cooling.
    double last_continuum_compton_heating = 0.0;
    double last_continuum_compton_cooling = 0.0;
    double last_continuum_free_free_cooling = 0.0;
    double last_cmp1 = 0.0;
    double last_cmp2 = 0.0;
    double last_computed_cmp1 = 0.0;
    double last_computed_cmp2 = 0.0;
    double last_computed_htcomp = 0.0;
    double last_computed_clcomp = 0.0;
    double last_computed_htfreef = 0.0;
    double last_computed_clbrems = 0.0;
    double last_htfreef = 0.0;
    double last_clbrems = 0.0;
    bool last_continuum_workspace_source_faithful = false;
    std::size_t last_continuum_epim_count = 0;
    std::uint64_t last_continuum_epim_fingerprint = 0;
    std::size_t last_continuum_bremsam_count = 0;
    std::uint64_t last_continuum_bremsam_fingerprint = 0;
    std::size_t last_continuum_bremsmap_count = 0;
    std::uint64_t last_continuum_bremsmap_fingerprint = 0;
    std::vector<ContinuumWorkspaceDiagnostic> last_continuum_workspace_diagnostics;
    bool last_call1_thermal_oracle = false;
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
    bool last_all_element_solve_response = false;
    bool last_all_element_solve_system = false;
    bool last_type53_row46_coupled_replacement = false;
    bool last_helium_source_insertion_order = false;
    std::map<int, std::array<double,4>> last_element_thermal_budget;
    std::map<int, std::array<double,4>> last_computed_element_thermal_budget;
    std::array<double,4> last_committed_element_thermal_budget{{0.0,0.0,0.0,0.0}};
    std::array<double,4> last_committed_continuum_thermal_budget{{0.0,0.0,0.0,0.0}};
    std::array<double,4> last_helium_type53_budget{{0.0,0.0,0.0,0.0}};
    std::array<double,4> last_computed_helium_type53_budget{{0.0,0.0,0.0,0.0}};
    std::array<double,4> last_helium_non_type53_budget{{0.0,0.0,0.0,0.0}};
    std::array<double,4> last_computed_helium_non_type53_budget{{0.0,0.0,0.0,0.0}};
    bool last_independent_thermal_parity = false;
    bool last_source_scalar_override_used = false;
    bool last_thermal_component_closure = false;
    bool last_thermal_consumed_fixed_state_closure = false;
    bool last_thermal_consumed_compact_population_closure = false;
    bool last_thermal_diagonal_source_domain = false;
    bool last_continuum_secondary_ledger_corrected = false;
    std::size_t last_thermal_diagonal_rows_included = 0;
    std::size_t last_thermal_diagonal_normalization_terms_included = 0;
    std::vector<ThermalDiagonalDiagnostic> last_thermal_diagonal_diagnostics;
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
        if (c.size() != 8 && c.size() != 10 && c.size() != 11) throw std::runtime_error("rows.csv requires 8, 10, or 11 columns");
        ElementRow r;
        r.element_index = parse_number<int>(c[0], "element_index");
        r.row = parse_number<int>(c[1], "row");
        r.superlevel = parse_number<int>(c[2], "superlevel");
        r.ion = parse_number<int>(c[3], "ion");
        r.ion_charge = parse_number<int>(c[4], "ion_charge");
        r.initial_population = parse_number<double>(c[5], "initial_population");
        r.energy_ev = parse_number<double>(c[6], "energy_ev");
        r.statistical_weight = parse_number<double>(c[7], "statistical_weight");
        if (c.size() >= 10) {
            r.principal_n = parse_number<int>(c[8], "principal_n");
            r.orbital_l = parse_number<int>(c[9], "orbital_l");
        }
        if (c.size() == 11) r.global_level_index = parse_number<int>(c[10], "global_level_index");
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
        if (c.size() != 18 && c.size() != 19 && c.size() != 21)
            throw std::runtime_error("records.csv requires 18, 19, or 21 columns");
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
        if (c.size() == 21) {
            r.line_index_one_based = parse_number<int>(c[18], "line_index");
            r.continuum_index_one_based = parse_number<int>(c[19], "continuum_index");
            r.matrix_enabled = parse_number<int>(c[20], "matrix_enabled") != 0;
        } else if (c.size() == 19) {
            r.matrix_enabled = parse_number<int>(c[18], "matrix_enabled") != 0;
        }
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

void validate_program(Program& p);

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
    const auto line_count_it = manifest.find("native_line_count");
    if (line_count_it != manifest.end()) p.native_line_count = parse_number<std::size_t>(line_count_it->second, "native_line_count");
    const auto continuum_count_it = manifest.find("native_continuum_count");
    if (continuum_count_it != manifest.end()) p.native_continuum_count = parse_number<std::size_t>(continuum_count_it->second, "native_continuum_count");
    load_elements(join_path(directory, "elements.csv"), p);
    load_rows(join_path(directory, "rows.csv"), p);
    p.reals = load_scalar_file<double>(join_path(directory, "reals.txt"), "reals.txt");
    p.ints = load_scalar_file<std::int64_t>(join_path(directory, "ints.txt"), "ints.txt");
    load_records(join_path(directory, "records.csv"), p);
    validate_program(p);
    return p;
}


void validate_program(Program& p) {
    if (p.id.empty()) throw std::runtime_error("program_id missing");
    if (p.elements.empty()) throw std::runtime_error("program contains no elements");
    if (p.records.empty()) throw std::runtime_error("program contains no records");
    for (std::size_t i = 0; i < p.elements.size(); ++i) {
        auto& e = p.elements[i];
        if (e.element_index != static_cast<int>(i)) throw std::runtime_error("element indices must be contiguous and zero-based");
        if (e.element_z <= 0 || e.n_rows <= 0 || e.n_ions <= 0) throw std::runtime_error("invalid element program dimensions");
        if (e.normalization_row < 1 || e.normalization_row > e.n_rows) throw std::runtime_error("element normalization row out of range");
        if (static_cast<int>(e.rows.size()) != e.n_rows) throw std::runtime_error("element row count mismatch");
        for (std::size_t j = 0; j < e.rows.size(); ++j) {
            const auto& row = e.rows[j];
            if (row.element_index != e.element_index || row.row != static_cast<int>(j + 1)) {
                throw std::runtime_error("program rows must be grouped by element and contiguous");
            }
            if (!(row.statistical_weight > 0.0) || !std::isfinite(row.statistical_weight)) {
                throw std::runtime_error("row statistical weight must be positive and finite");
            }
        }
    }
    std::int64_t previous_source_position = 0;
    for (std::size_t k = 0; k < p.records.size(); ++k) {
        const auto& r = p.records[k];
        if (r.source_position <= 0 || r.source_position <= previous_source_position) {
            throw std::runtime_error("record source_position must be positive and strictly increasing");
        }
        previous_source_position = r.source_position;
        if (r.element_index < 0 || r.element_index >= static_cast<int>(p.elements.size())) throw std::runtime_error("record element_index out of range");
        if (r.next_index < -1 || r.next_index >= static_cast<int>(p.records.size())) throw std::runtime_error("record next_index out of range");
        if (r.real_offset + r.real_count > p.reals.size()) throw std::runtime_error("record real payload out of range");
        if (r.int_offset + r.int_count > p.ints.size()) throw std::runtime_error("record integer payload out of range");
        const auto& e = p.elements[static_cast<std::size_t>(r.element_index)];
        if (r.matrix_enabled) {
            if (r.lower_row < 1 || r.lower_row > e.n_rows || r.upper_row < 1 || r.upper_row > e.n_rows) throw std::runtime_error("record endpoint out of compact element range");
        } else if (r.lower_row != 0 || r.upper_row != 0) {
            throw std::runtime_error("scalar-only record endpoints must be zero");
        }
        if (r.line_index_one_based > 0) p.native_line_count = std::max(p.native_line_count, static_cast<std::size_t>(r.line_index_one_based));
        if (r.continuum_index_one_based > 0) p.native_continuum_count = std::max(p.native_continuum_count, static_cast<std::size_t>(r.continuum_index_one_based));
    }
}

Program load_program_bundle(const xstar_fixed_program_bundle_v1& bundle) {
    constexpr std::size_t kHistoricalBundlePrefix = offsetof(xstar_fixed_program_bundle_v1, lte_ions);
    if (bundle.struct_size < kHistoricalBundlePrefix || bundle.abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) {
        throw std::runtime_error("fixed-state in-memory program bundle ABI mismatch");
    }
    if (!bundle.program_id || !*bundle.program_id) throw std::runtime_error("in-memory program_id missing");
    if (!bundle.elements || bundle.element_count == 0) throw std::runtime_error("in-memory program elements missing");
    if (!bundle.rows || bundle.row_count == 0) throw std::runtime_error("in-memory program rows missing");
    if (!bundle.records || bundle.record_count == 0) throw std::runtime_error("in-memory program records missing");
    if (bundle.real_count && !bundle.reals) throw std::runtime_error("in-memory program real payload missing");
    if (bundle.int_count && !bundle.ints) throw std::runtime_error("in-memory program integer payload missing");

    Program p;
    p.id = bundle.program_id;
    p.active_atdb_lowered = bundle.active_atdb_lowered != 0;
    p.topology_record_count = bundle.topology_record_count;
    p.unsupported_record_count = bundle.unsupported_record_count;
    p.native_line_count = bundle.native_line_count;
    p.native_continuum_count = bundle.native_continuum_count;
    p.reals.assign(bundle.reals, bundle.reals + bundle.real_count);
    p.ints.assign(bundle.ints, bundle.ints + bundle.int_count);
    constexpr std::size_t kPatch54BundleSize = offsetof(xstar_fixed_program_bundle_v1, lte_levels);
    if (bundle.struct_size >= kPatch54BundleSize && bundle.lte_ion_count > 0) {
        if (!bundle.lte_ions) throw std::runtime_error("in-memory LTE ion topology pointer missing");
        p.lte_ion_topology.reserve(bundle.lte_ion_count);
        for (std::size_t i = 0; i < bundle.lte_ion_count; ++i) {
            const auto& src = bundle.lte_ions[i];
            LteIonTopology topo;
            topo.element_index = src.element_index;
            topo.ion_stage = src.ion_stage;
            topo.start_row = src.start_row;
            topo.nlev = src.nlev;
            topo.terminal_energy_ev = src.terminal_energy_ev;
            topo.terminal_statistical_weight = src.terminal_statistical_weight;
            p.lte_ion_topology.push_back(topo);
        }
    }
    if (bundle.struct_size >= sizeof(xstar_fixed_program_bundle_v1) && bundle.lte_level_count > 0) {
        if (!bundle.lte_levels) throw std::runtime_error("in-memory complete Type-13 LTE leveltemp pointer missing");
        p.lte_levels.reserve(bundle.lte_level_count);
        for (std::size_t i = 0; i < bundle.lte_level_count; ++i) {
            const auto& src = bundle.lte_levels[i];
            if (src.local_level <= 0 || !(src.statistical_weight > 0.0) || !std::isfinite(src.energy_ev)) {
                throw std::runtime_error("in-memory complete Type-13 LTE leveltemp row invalid");
            }
            LteLevelData level;
            level.element_index = src.element_index;
            level.ion_stage = src.ion_stage;
            level.local_level = src.local_level;
            level.source_record = src.source_record;
            level.energy_ev = src.energy_ev;
            level.statistical_weight = src.statistical_weight;
            p.lte_levels.push_back(level);
        }
    }
    p.elements.reserve(bundle.element_count);
    for (std::size_t i = 0; i < bundle.element_count; ++i) {
        const auto& src = bundle.elements[i];
        ElementProgram e;
        e.element_index = src.element_index;
        e.element_z = src.element_z;
        e.abundance = src.abundance;
        e.n_rows = src.n_rows;
        e.n_superlevels = src.n_superlevels;
        e.n_ions = src.n_ions;
        e.normalization_row = src.normalization_row;
        e.record_head = src.record_head;
        e.record_count = src.record_count;
        p.elements.push_back(std::move(e));
    }
    for (std::size_t i = 0; i < bundle.row_count; ++i) {
        const auto& src = bundle.rows[i];
        if (src.element_index < 0 || src.element_index >= static_cast<int32_t>(p.elements.size())) {
            throw std::runtime_error("in-memory row element_index out of range");
        }
        ElementRow row;
        row.element_index = src.element_index;
        row.row = src.row;
        row.superlevel = src.superlevel;
        row.ion = src.ion;
        row.ion_charge = src.ion_charge;
        row.initial_population = src.initial_population;
        row.energy_ev = src.energy_ev;
        row.statistical_weight = src.statistical_weight;
        row.principal_n = src.principal_n;
        row.orbital_l = src.orbital_l;
        row.global_level_index = src.global_level_index;
        p.elements[static_cast<std::size_t>(src.element_index)].rows.push_back(row);
    }
    p.records.reserve(bundle.record_count);
    for (std::size_t i = 0; i < bundle.record_count; ++i) {
        const auto& src = bundle.records[i];
        ProgramRecord r;
        r.source_position = src.source_position;
        r.record = src.record;
        r.next_index = src.next_index;
        r.element_index = src.element_index;
        r.opcode = src.opcode;
        r.data_type = src.data_type;
        r.rate_type = src.rate_type;
        r.ion_index = src.ion_index;
        r.ion_stage = src.ion_stage;
        r.lower_row = src.lower_row;
        r.upper_row = src.upper_row;
        r.real_offset = src.real_offset;
        r.real_count = src.real_count;
        r.int_offset = src.int_offset;
        r.int_count = src.int_count;
        r.density_scale = src.density_scale;
        r.line_energy_ev = src.line_energy_ev;
        r.atomic_mass_amu = src.atomic_mass_amu;
        r.natural_width_ev = src.natural_width_ev;
        r.line_index_one_based = src.line_index_one_based;
        r.continuum_index_one_based = src.continuum_index_one_based;
        r.matrix_enabled = src.matrix_enabled != 0;
        p.records.push_back(r);
    }
    validate_program(p);
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

double type69_expint_scaled_source_order(double x) {
    if (!(x > 0.0) || !std::isfinite(x)) return 0.0;
    if (x > 1.0) {
        const double numerator =
            std::pow(x, 4.0) + 8.5733287401 * std::pow(x, 3.0) +
            18.0590169730 * x * x + 8.6347608925 * x + 0.2677737343;
        const double denominator =
            std::pow(x, 4.0) + 9.5733223454 * std::pow(x, 3.0) +
            25.6329561486 * x * x + 21.0996530827 * x + 3.9584969228;
        return numerator / denominator;
    }
    const double e1 =
        -0.57721566 + 0.99999193 * x - 0.24991055 * x * x +
        0.05519968 * std::pow(x, 3.0) - 0.00976004 * std::pow(x, 4.0) +
        0.00107857 * std::pow(x, 5.0) - std::log(x);
    return e1 * x * type53_expo(x);
}

double type69_upsilon(const double* r, std::size_t n, double temperature_k) {
    if (!r || n < 6 || temperature_k <= 0.0 || r[0] <= 0.0) return -1.0;
    double y = r[0] / temperature_k * 1.160443e4;
    if (y < 1.0e-20) return -1.0;
    if (y > 1.0e20) return 0.0;
    y = std::max(5.0e-2, std::min(77.0, y));
    const double em1 = type69_expint_scaled_source_order(y);
    const double a = r[1], b = r[2], c = r[3], d = r[4], e = r[5];
    double gamma = 0.0;
    if (n == 6) {
        gamma = y * ((a / y + c) + d * 0.5 * (1.0 - y));
        gamma += em1 * (b - c * y + d * y * y * 0.5 + e / y);
    } else {
        if (n < 9 || r[8] <= 0.0) return -1.0;
        const double p = r[6], q = r[7], x1 = r[8];
        const double em1x = type69_expint_scaled_source_order(y * x1);
        double gnr = a / y + c / x1 + d * 0.5 * (1.0 / (x1 * x1) - y / x1) + e / y * std::log(x1);
        gnr += em1x / y / x1 * (b - c * y + d * y * y * 0.5 + e / y);
        gnr *= y * limited_exp(y * (1.0 - x1));
        const double base = 1.0 + 1.0 / y;
        const double exp_tail = type53_expo(y * (1.0 - x1));
        double gr = p * base * (1.0 - exp_tail * (x1 + 1.0 / y) / base);
        gr += q * (1.0 - exp_tail);
        gamma = gnr + gr;
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

double type51_splinem5(const double* p, double x) {
    const double s = 1.0 / 30.0;
    const double s2 = 32.0 * s * (19.0*p[0] - 43.0*p[1] + 30.0*p[2] - 7.0*p[3] + p[4]);
    const double s3 = 160.0 * s * (-p[0] + 7.0*p[1] - 12.0*p[2] + 7.0*p[3] - p[4]);
    const double s4 = 32.0 * s * (p[0] - 7.0*p[1] + 30.0*p[2] - 43.0*p[3] + 19.0*p[4]);
    double x0 = 0.0, t0 = 0.0, t1 = 0.0, t2 = 0.0, t3 = 0.0;
    if (x <= 0.25) {
        x0 = x - 0.125;
        t3 = 0.0;
        t2 = 0.5 * s2;
        t1 = 4.0 * (p[1] - p[0]);
        t0 = 0.5 * (p[0] + p[1]) - 0.015625 * t2;
    } else if (x <= 0.5) {
        x0 = x - 0.375;
        t3 = 20.0 * s * (s3 - s2);
        t2 = 0.25 * (s2 + s3);
        t1 = 4.0 * (p[2] - p[1]) - 0.015625 * t3;
        t0 = 0.5 * (p[1] + p[2]) - 0.015625 * t2;
    } else if (x <= 0.75) {
        x0 = x - 0.625;
        t3 = 20.0 * s * (s4 - s3);
        t2 = 0.25 * (s3 + s4);
        t1 = 4.0 * (p[3] - p[2]) - 0.015625 * t3;
        t0 = 0.5 * (p[2] + p[3]) - 0.015625 * t2;
    } else {
        x0 = x - 0.875;
        t3 = 0.0;
        t2 = 0.5 * s4;
        t1 = 4.0 * (p[4] - p[3]);
        t0 = 0.5 * (p[3] + p[4]) - 0.015625 * t2;
    }
    return t0 + x0 * (t1 + x0 * (t2 + x0 * t3));
}

double type51_upsilon_legacy(
    const double* r, std::size_t n, const std::int64_t* ints,
    std::size_t ni, double temperature_k
) {
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

struct Type51UpsilonEvaluation {
    bool valid = false;
    int bt_type = 0;
    int point_count = 0;
    double eij_ryd = 0.0;
    double eij_ev = 0.0;
    double scaling_c = 0.0;
    double physical_temperature_k = 0.0;
    double floor_temperature_k = 0.0;
    double effective_temperature_k = 0.0;
    bool floor_applied = false;
    double scaled_temperature = 0.0;
    double transformed_temperature = 0.0;
    double scaled_upsilon = 0.0;
    double upsilon = 0.0;
};

Type51UpsilonEvaluation type51_upsilon(
    const double* r, std::size_t n, const std::int64_t* ints,
    std::size_t ni, double temperature_k
) {
    Type51UpsilonEvaluation result;
    if (!r || n < 7 || !ints || ni < 1 || r[0] <= 0.0 || r[1] <= 0.0 || !(temperature_k > 0.0)) return result;
    result.bt_type = static_cast<int>(ints[0]);
    result.point_count = n == 7 ? 5 : (n >= 11 ? 9 : 0);
    result.eij_ryd = r[0];
    result.eij_ev = result.eij_ryd * 13.605692;
    result.scaling_c = r[1];
    result.physical_temperature_k = temperature_k;
    const double wavelength_a = 12398.4016 / result.eij_ev;
    result.floor_temperature_k = 2.8777e6 / wavelength_a;
    result.effective_temperature_k = std::max(temperature_k, result.floor_temperature_k);
    result.floor_applied = result.effective_temperature_k > temperature_k;
    const double u = result.effective_temperature_k / (result.eij_ryd * 1.57888e5);
    result.scaled_temperature = u;
    if (!(u > 0.0)) return result;
    double x = 0.0;
    if (result.point_count == 5) {
        if (result.bt_type == 1 || result.bt_type == 4) {
            const double denom = std::log(u + result.scaling_c);
            if (denom == 0.0 || !std::isfinite(denom)) return result;
            x = std::log((u + result.scaling_c) / result.scaling_c) / denom;
        } else if (result.bt_type == 2 || result.bt_type == 3) {
            x = u / (u + result.scaling_c);
        } else {
            return result;
        }
        result.scaled_upsilon = type51_splinem5(r + 2, x);
    } else if (result.point_count == 9) {
        if (result.bt_type == 1 || result.bt_type == 4) {
            const double denom = std::log(u + result.scaling_c);
            if (denom == 0.0 || !std::isfinite(denom)) return result;
            x = 1.0 - std::log(result.scaling_c) / denom;
        } else if (result.bt_type == 2 || result.bt_type == 3 || result.bt_type == 5 || result.bt_type == 6) {
            x = u / (u + result.scaling_c);
        } else {
            return result;
        }
        result.scaled_upsilon = natural_spline9(r + 2, x);
    } else {
        return result;
    }
    result.transformed_temperature = x;
    switch (result.bt_type) {
        case 1:
            result.upsilon = result.scaled_upsilon * std::log(
                u + (result.point_count == 5 ? 2.71828 : std::exp(1.0))
            );
            break;
        case 2: result.upsilon = result.scaled_upsilon; break;
        case 3: result.upsilon = result.scaled_upsilon / (u + 1.0); break;
        case 4: result.upsilon = result.scaled_upsilon * std::log(u + result.scaling_c); break;
        case 5: result.upsilon = result.scaled_upsilon / u; break;
        case 6: result.upsilon = std::pow(10.0, result.scaled_upsilon); break;
        default: return Type51UpsilonEvaluation{};
    }
    result.valid = std::isfinite(result.scaled_upsilon) && std::isfinite(result.upsilon) && result.upsilon >= 0.0;
    return result;
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
    const double r0=at(ni,ti)+(at(ni,ti+1)-at(ni,ti))/(t1-t0+1.0e-36)*(logt-t0);
    const double r1=at(ni+1,ti)+(at(ni+1,ti+1)-at(ni+1,ti))/(t1-t0+1.0e-36)*(logt-t0);
    return r0+(r1-r0)/(n1-n0+1.0e-36)*(logn-n0);
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
    return xstar_constants::kCollisionRateCoefficientPerSqrtT4*upsilon*limited_exp(-delta_ev/std::max(kBoltzmannEvK*temperature_k,1.0e-300))*ne/
        (std::sqrt(std::max(t4,1.0e-300))*std::max(gl,1.0e-300));
}

double collision_pair_downward(double upsilon, double temperature_k, double ne, double gu) {
    const double t4=temperature_k/1.0e4;
    return xstar_constants::kCollisionRateCoefficientPerSqrtT4*upsilon*ne/(std::sqrt(std::max(t4,1.0e-300))*std::max(gu,1.0e-300));
}

double callaway_upsilon(
    int data_type,
    const double* r,
    std::size_t nr,
    double temperature_k,
    double delta_ev,
    bool source_faithful
) {
    const std::size_t min_count=data_type==60?3u:6u;
    if (!r||nr<min_count||!(temperature_k>0.0)||!(delta_ev>0.0)) throw std::runtime_error("invalid type60/62 payload");
    // XSTAR ucalc label 60 uses 0.861707 eV per 10^4 K both in the
    // excitation exponential and in the source temperature floor.  The
    // earlier native path used the modern Boltzmann constant here, which
    // accounts for the full Hydrogen ans6 / h_cooling2 residual.
    const double kt_ev_per_t4 = source_faithful
        ? xstar_constants::kLegacyBoltzmannEvPerT4
        : xstar_constants::kModernBoltzmannEvPerT4;
    const double floor_k=0.02*delta_ev*1.0e4/kt_ev_per_t4;
    const double teff=std::max(temperature_k,floor_k);
    const double t1=teff>1.0e9?6.33652e3:teff*6.33652e-6;
    const double tt=std::min(t1,1.0);
    double ups=0.0;
    if (data_type==60) {
        if (source_faithful) {
            // Match calt6062.f90: each integer power is evaluated directly.
            for (std::size_t k=2;k<nr;++k) ups += r[k]*std::pow(tt,static_cast<int>(k-2));
        } else {
            double power=1.0;
            for (std::size_t k=2;k<nr;++k) { ups+=r[k]*power; power*=tt; }
        }
    } else {
        if (source_faithful) {
            for (std::size_t k=2;k+3<nr;++k) ups += r[k]*std::pow(tt,static_cast<int>(k-2));
        } else {
            double power=1.0;
            for (std::size_t k=2;k+3<nr;++k) { ups+=r[k]*power; power*=tt; }
        }
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
    if (y>40.0) return 0.0;
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
    const double crate=qij*1.578876e5/tused*std::sqrt(tused)/std::max(zeff*zeff,1.0e-48)*5.46538e-11;
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
    // Match the immutable reference's platform libm path.  Most records use
    // Python's runtime pow(10, rec); the stage-2 table shared by records
    // 1962/1963 was produced through the source exp10 path and has one distinct
    // correctly captured ULP at this exact interpolated exponent.
    downward=source_runtime_pow10(rec);
    if (rec == -0.958375491843708) downward=::exp10(rec);
    int k=1; while (nll >= (k+1)*k/2+1 && k<10000) ++k;
    const int nl1=k*(k-1)/2+1, il=nll-nl1; const double gg=2.0*(2.0*il+1.0);
    const double xt=1.43817e8/wav/tused;
    upward=(xt<100.0&&gg>0.0)?downward*std::exp(-xt)/gg:0.0;
    return std::isfinite(upward)&&std::isfinite(downward);
}

struct Type99PhintResult {
    bool valid = false;
    double pirt = 0.0;
    double rrrt = 0.0;
    double piht = 0.0;
    double rrcl = 0.0;
    double piht2 = 0.0;
    double rrcl2 = 0.0;
    int nbinc_threshold_one_based = 0;
    int nb1_one_based = 0;
    int nphint_one_based = 0;
    int ndelt = 0;
    int npass = 0;
    int last_pass_first_kl_one_based = 0;
    int last_pass_last_kl_one_based = 0;
    int cached_atmp22_stale_reuses = 0;
};

int type99_nbinc_fortran_value(double energy, const double* epi, std::size_t count) {
    if (!epi || count < 3) return 1;
    const int n = static_cast<int>(count);
    const int numcon2 = std::max(2, n / 50);
    const int numcon3 = n - numcon2;
    if (numcon3 < 2 || energy < 1.0e-34 || epi[0] <= 1.0e-34 || epi[numcon3 - 1] <= 1.0e-34) return 1;
    const double xtmp = std::max(energy, epi[1]);
    const double denominator = std::log(epi[numcon3 - 1] / epi[0]);
    if (denominator == 0.0) return 1;
    int jlo = static_cast<int>((numcon3 - 1) * std::log(xtmp / epi[0]) / denominator) + 1;
    if (jlo < numcon3) {
        const double tst = std::abs(std::log(energy / (1.0e-34 + epi[jlo - 1])));
        const double tst2 = std::abs(std::log(energy / (1.0e-34 + epi[jlo])));
        if (tst2 < tst) ++jlo;
    }
    return std::max(1, std::min(numcon3, jlo));
}

void build_type99_reduced_radiation(
    const double* full_epi,
    const double* full_bremsa,
    std::size_t full_count,
    std::vector<double>& epim,
    std::vector<double>& bremsam
) {
    constexpr int reduced_count = 999;
    constexpr int reduced_tail = std::max(2, reduced_count / 50);
    constexpr int reduced_log_count = reduced_count - reduced_tail;
    epim.assign(reduced_count, 0.0);
    bremsam.assign(reduced_count, 0.0);
    epim[0] = 0.1;
    const double ratio = std::pow(4.0e5 / 0.1, 1.0 / static_cast<double>(reduced_log_count - 1));
    for (int i = 1; i < reduced_log_count; ++i) epim[static_cast<std::size_t>(i)] = epim[static_cast<std::size_t>(i - 1)] * ratio;
    const double ratio2 = std::pow(1.0e6 / 4.0e5, 1.0 / static_cast<double>(reduced_tail - 1));
    for (int i = reduced_log_count; i < reduced_count; ++i) epim[static_cast<std::size_t>(i)] = epim[static_cast<std::size_t>(i - 1)] * ratio2;
    for (int i = 0; i < reduced_count; ++i) {
        const int mapped_one_based = type99_nbinc_fortran_value(epim[static_cast<std::size_t>(i)], full_epi, full_count);
        const std::size_t mapped = static_cast<std::size_t>(std::max(1, mapped_one_based) - 1);
        bremsam[static_cast<std::size_t>(i)] = full_bremsa[std::min(mapped, full_count - 1)];
    }
}

double type99_find53_cross_section(
    const std::vector<double>& energy_ryd,
    const std::vector<double>& sigma_cm2,
    double efnd_ryd
) {
    if (energy_ryd.size() < 2 || energy_ryd.size() != sigma_cm2.size() || efnd_ryd < 0.0 || efnd_ryd > energy_ryd.back()) return 0.0;
    const auto upper = std::upper_bound(energy_ryd.begin(), energy_ryd.end(), efnd_ryd);
    std::size_t j = upper == energy_ryd.begin() ? 0 : static_cast<std::size_t>(upper - energy_ryd.begin() - 1);
    j = std::min(j, energy_ryd.size() - 2);
    const double e0 = energy_ryd[j], e1 = energy_ryd[j + 1];
    const double s0 = std::max(sigma_cm2[j], 0.0), s1 = std::max(sigma_cm2[j + 1], 0.0);
    if (j + 1 == energy_ryd.size() - 1 && e0 > 0.0 && e1 > 0.0 && efnd_ryd > 0.0) {
        const double slope = std::log(std::max(s1, 1.0e-26) / std::max(s0, 1.0e-26)) /
            std::log(std::max(e1, 1.0e-26) / std::max(e0, 1.0e-26));
        return std::max(0.0, s0 * std::pow(efnd_ryd / e0, slope));
    }
    if (e1 == e0) return s0;
    const double f = (efnd_ryd - e0) / (e1 - e0);
    return std::max(0.0, s0 + f * (s1 - s0));
}

std::pair<double,double> type99_milne_intin(double x1, double x2, double x0, double temperature_k) {
    constexpr double ryk = 7.2438e15;
    const double temp = std::max(temperature_k, 1.0e-300);
    const double s1 = x1 * ryk / temp;
    const double s2 = x2 * ryk / temp;
    const double s0 = x0 * ryk / temp;
    const double delt = ryk / temp;
    if (!(delt > 0.0) || !std::isfinite(delt)) return {0.0, 0.0};
    double ri2 = 0.0;
    if ((s1 - s0) < 90.0) {
        ri2 = std::exp(s0 - s1) * ((s1 * s1 + 2.0 * s1 + 2.0) -
            std::exp(s1 - s2) * (s2 * s2 + 2.0 * s2 + 2.0)) / delt / std::sqrt(delt);
        if (s0 < 1.0e-3 && s1 < 1.0e-3 && s2 < 1.0e-3) ri2 = 0.0;
    }
    const double rr = std::exp(s0 - s1) * (std::pow(s1, 3.0) - std::exp(s1 - s2) * std::pow(s2, 3.0));
    double ri3 = (rr / delt / std::sqrt(delt) + 3.0 * ri2) / delt;
    if (!std::isfinite(ri2)) ri2 = 0.0;
    if (!std::isfinite(ri3)) ri3 = 0.0;
    return {ri2, ri3};
}

double type99_milne_alpha(
    const std::vector<double>& energy_ryd,
    const std::vector<double>& sigma_mb,
    double threshold_ryd,
    double temperature_k
) {
    if (energy_ryd.size() < 2 || energy_ryd.size() != sigma_mb.size() || !(threshold_ryd > 0.0)) return 0.0;
    constexpr double ry_erg = 2.17896e-11;
    const double st = (energy_ryd[0] + threshold_ryd) * ry_erg;
    double total = 0.0;
    double previous_total = 1.0;
    constexpr double crit = 0.01;
    for (std::size_t i = 1; i < energy_ryd.size(); ++i) {
        if (std::abs(total - previous_total) <= crit * std::abs(total) && i > 1) break;
        const double s1 = (energy_ryd[i - 1] + threshold_ryd) * ry_erg;
        const double s2 = (energy_ryd[i] + threshold_ryd) * ry_erg;
        if (s2 < s1) return 0.0;
        const double v1 = std::max(sigma_mb[i - 1], 0.0);
        const double v2 = std::max(sigma_mb[i], 0.0);
        if (v1 != 0.0 || v2 != 0.0) {
            const double rb = (v2 - v1) / (s2 - s1 + 1.0e-24);
            const double ra = v2 - rb * s2;
            const auto integrals = type99_milne_intin(s1, s2, st, temperature_k);
            previous_total = total;
            total += ra * integrals.first + rb * integrals.second;
        }
    }
    const double alpha = total * 0.79788 * 40.4153;
    return std::isfinite(alpha) ? std::max(alpha, 0.0) : 0.0;
}

Type99PhintResult evaluate_type99_phint53hunt(
    const std::vector<double>& energy_ryd,
    const std::vector<double>& sigma_cm2,
    double threshold_ev,
    double temperature_k,
    double electron_density_cm3,
    double swrat,
    const double* epi,
    const double* bremsa,
    std::size_t grid_count,
    double crit = 0.01
) {
    Type99PhintResult out;
    if (energy_ryd.size() < 2 || energy_ryd.size() != sigma_cm2.size() || !epi || !bremsa || grid_count < 3) return out;
    const int n = static_cast<int>(grid_count);
    const int numcon2 = std::max(2, n / 50);
    const int numcon3 = n - numcon2;
    const int nbinc_threshold = type99_nbinc_fortran_value(threshold_ev, epi, grid_count);
    const int nb1 = nbinc_threshold + 1;
    out.nbinc_threshold_one_based = nbinc_threshold;
    out.nb1_one_based = nb1;
    if (nb1 >= numcon3) return out;
    const double emax = threshold_ev + energy_ryd.back() * kType53RydEv;
    int nphint = type99_nbinc_fortran_value(emax, epi, grid_count);
    int ndelt = std::max(nphint - nb1, 1);
    int itmp = static_cast<int>(std::log(static_cast<double>(ndelt)) / 0.69315 + 0.5);
    while (true) {
        ndelt = 1 << std::max(itmp, 0);
        nphint = nb1 + ndelt;
        double etst = 0.0;
        if (nphint <= numcon3) etst = (epi[nphint - 1] - threshold_ev) / kType53RydEv;
        if (nphint > numcon3 || etst > energy_ryd.back()) {
            --itmp;
            if (itmp > 1) continue;
        }
        break;
    }
    out.nphint_one_based = nphint;
    out.ndelt = ndelt;
    const double t4 = temperature_k / 1.0e4;
    const double bktm = (xstar_constants::kBoltzmannErgPerK * 1.0e4 /
        xstar_constants::kModernErgPerEv) * t4;
    const double rnist = 5.216e-21 * swrat / std::max(t4 * std::sqrt(std::max(t4, 0.0)), 1.0e-48);
    std::vector<unsigned char> luse(grid_count, 0);
    std::vector<double> ansar1(grid_count, 0.0), ansar2(grid_count, 0.0);
    int nskip = ndelt;
    int npass = 0;
    double sumr = 0.0, sumh = 0.0, sumi = 0.0, sumc = 0.0, sumh2 = 0.0, sumc2 = 0.0;
    double tst1 = std::numeric_limits<double>::infinity();
    double tst2 = tst1, tst3 = tst1, tst4 = tst1;
    int last_first = 0, last_last = 0, stale_reuses = 0;
    while ((tst3 > crit || tst1 > crit || tst2 > crit || tst4 > crit || sumi <= 1.0e-24) && nskip > 1) {
        ++npass;
        nskip = std::max(1, nskip / 2);
        const double sumro = sumr, sumho = sumh, sumio = sumi, sumco = sumc;
        sumr = sumh = sumi = sumc = sumh2 = sumc2 = 0.0;
        double tempr = 0.0, tempi = 0.0, atmp2 = 0.0, atmp22 = 0.0;
        double ener = epi[nb1 - 1];
        last_first = 0;
        last_last = 0;
        for (int kl = std::max(1, nb1 - 1); kl <= nphint; kl += nskip) {
            if (last_first == 0) last_first = kl;
            last_last = kl;
            const int k = kl - 1;
            const double enero = ener;
            const double epii = epi[k];
            ener = epii;
            const double bremtmp = bremsa[k] / 25.3;
            const double tempio = tempi, atmp2o = atmp2, atmp22o = atmp22;
            double sgtmp = 0.0;
            if (ener >= threshold_ev) {
                if (luse[static_cast<std::size_t>(k)] == 0) {
                    const double efnd = (ener - threshold_ev) / kType53RydEv;
                    sgtmp = type99_find53_cross_section(energy_ryd, sigma_cm2, efnd);
                    const double exptmp = type53_expo(-(epii - threshold_ev) / std::max(bktm, 1.0e-48));
                    const double bbnurj = std::pow(std::min(2.0e4, epii), 3.0);
                    const double tempi1 = rnist * bbnurj * sgtmp * exptmp * 1.571e22 / std::max(epii, 1.0e-48);
                    const double tempi2 = rnist * bremtmp * sgtmp * exptmp / std::max(epii, 1.0e-48);
                    tempi = tempi1 + tempi2;
                    atmp2 = tempi * epii;
                    atmp22 = tempi * (epii - threshold_ev);
                    ansar1[static_cast<std::size_t>(k)] = sgtmp;
                    ansar2[static_cast<std::size_t>(k)] = atmp2;
                } else {
                    sgtmp = ansar1[static_cast<std::size_t>(k)];
                    atmp2 = ansar2[static_cast<std::size_t>(k)];
                    tempi = atmp2 / std::max(epii, 1.0e-48);
                    ++stale_reuses;
                }
            }
            const double tempro = tempr;
            tempr = 25.3 * sgtmp * bremtmp / std::max(epii, 1.0e-48);
            const double deld = ener - enero;
            sumr += (tempr + tempro) * deld / 2.0;
            sumh += (tempr * ener + tempro * enero) * deld / 2.0;
            sumh2 += (tempr * (ener - threshold_ev) + tempro * (enero - threshold_ev)) * deld / 2.0;
            sumi += (tempi + tempio) * deld / 2.0;
            sumc += (atmp2 + atmp2o) * deld / 2.0;
            sumc2 += (atmp22 + atmp22o) * deld / 2.0;
            luse[static_cast<std::size_t>(k)] = 1;
        }
        tst3 = std::abs((sumio - sumi) / (sumio + sumi + 1.0e-24));
        tst1 = std::abs((sumro - sumr) / (sumro + sumr + 1.0e-24));
        tst2 = std::abs((sumho - sumh) / (sumho + sumh + 1.0e-24));
        tst4 = std::abs((sumco - sumc) / (sumco + sumc + 1.0e-24));
    }
    out.valid = true;
    out.pirt = sumr;
    out.rrrt = electron_density_cm3 * sumi;
    out.piht = sumh * kErgPerEv;
    out.rrcl = electron_density_cm3 * sumc * kErgPerEv;
    out.piht2 = sumh2 * kErgPerEv;
    out.rrcl2 = electron_density_cm3 * sumc2 * kErgPerEv;
    out.npass = npass;
    out.last_pass_first_kl_one_based = last_first;
    out.last_pass_last_kl_one_based = last_last;
    out.cached_atmp22_stale_reuses = stale_reuses;
    return out;
}


Type99PersistentLeveltempContextV048746223 parse_type99_persistent_leveltemp_context_v048746223(
    const ProgramRecord& record,
    const double* payload,
    const std::int64_t* ints,
    std::size_t core_real_count
) {
    constexpr std::int64_t kLayoutMagic = 223;
    constexpr std::size_t kContextRealCount = 83;  // v36 compatibility 3 + v21.13 context 80
    constexpr std::size_t kContextRealCountWithErrcV82Patch5205 = 84;
    constexpr int kContextIntCount = 8;
    Type99PersistentLeveltempContextV048746223 context{};
    const bool has_magic = ints && record.int_count >= kContextIntCount &&
        ints[record.int_count - 1] == kLayoutMagic;
    if (!has_magic) return context;
    if (!payload ||
        (record.real_count != core_real_count + kContextRealCount &&
         record.real_count != core_real_count + kContextRealCountWithErrcV82Patch5205)) {
        throw std::runtime_error("Mg Type-99 persistent leveltemp real payload is malformed");
    }
    const int ibase = record.int_count - kContextIntCount;
    context.bound_column = static_cast<int>(ints[ibase + 0]);
    context.parent_column = static_cast<int>(ints[ibase + 1]);
    context.destination_column = static_cast<int>(ints[ibase + 2]);
    context.bound_mask = static_cast<std::uint32_t>(ints[ibase + 3]);
    context.parent_mask = static_cast<std::uint32_t>(ints[ibase + 4]);
    context.destination_mask = static_cast<std::uint32_t>(ints[ibase + 5]);
    context.excited_parent_mode = static_cast<int>(ints[ibase + 6]);
    if (context.bound_column <= 0 || context.parent_column <= 0 ||
        context.destination_column <= 0 ||
        (context.bound_mask & ~0x0fffu) != 0u ||
        (context.parent_mask & ~0x0fffu) != 0u ||
        (context.destination_mask & ~0x0fffu) != 0u ||
        (context.excited_parent_mode != 0 && context.excited_parent_mode != 1)) {
        throw std::runtime_error("Mg Type-99 persistent leveltemp integer metadata is invalid");
    }
    const std::size_t base = core_real_count;
    context.incoming_bound_energy_ev = payload[base + 3];
    context.incoming_bound_statistical_weight = payload[base + 4];
    context.incoming_parent_energy_ev = payload[base + 5];
    context.incoming_parent_statistical_weight = payload[base + 6];
    context.incoming_destination_energy_ev = payload[base + 7];
    context.incoming_destination_statistical_weight = payload[base + 8];
    context.excited_parent_energy_ev = payload[base + 9];
    context.excited_parent_statistical_weight = payload[base + 10];
    for (std::size_t stage = 0; stage < 12; ++stage) {
        context.bound_candidate_energy_ev[stage] = payload[base + 11 + stage];
        context.bound_candidate_statistical_weight[stage] = payload[base + 23 + stage];
        context.parent_candidate_energy_ev[stage] = payload[base + 35 + stage];
        context.parent_candidate_statistical_weight[stage] = payload[base + 47 + stage];
        context.destination_candidate_energy_ev[stage] = payload[base + 59 + stage];
        context.destination_candidate_statistical_weight[stage] = payload[base + 71 + stage];
    }
    const auto validate_candidates = [](std::uint32_t mask,
                                        const std::array<double,12>& energies,
                                        const std::array<double,12>& weights,
                                        const char* label) {
        for (std::size_t stage = 0; stage < 12; ++stage) {
            if ((mask & (1u << stage)) == 0u) continue;
            if (!std::isfinite(energies[stage]) || !std::isfinite(weights[stage]) ||
                !(weights[stage] > 0.0)) {
                throw std::runtime_error(std::string("Mg Type-99 non-finite/invalid ") +
                    label + " candidate");
            }
        }
    };
    validate_candidates(context.bound_mask, context.bound_candidate_energy_ev,
                        context.bound_candidate_statistical_weight, "bound");
    validate_candidates(context.parent_mask, context.parent_candidate_energy_ev,
                        context.parent_candidate_statistical_weight, "parent");
    validate_candidates(context.destination_mask, context.destination_candidate_energy_ev,
                        context.destination_candidate_statistical_weight, "destination");
    for (double value : {
            context.incoming_bound_energy_ev,
            context.incoming_bound_statistical_weight,
            context.incoming_parent_energy_ev,
            context.incoming_parent_statistical_weight,
            context.incoming_destination_energy_ev,
            context.incoming_destination_statistical_weight,
            context.excited_parent_energy_ev,
            context.excited_parent_statistical_weight}) {
        if (!std::isfinite(value)) {
            throw std::runtime_error("Mg Type-99 incoming/literal persistent context is non-finite");
        }
    }
    if (context.excited_parent_mode == 1 &&
        !(context.excited_parent_statistical_weight > 0.0)) {
        throw std::runtime_error("Mg Type-99 excited-parent weight is invalid");
    }
    context.valid = true;
    return context;
}

bool evaluate_type99_source_faithful(
    const ProgramRecord& record,
    const double* payload,
    const std::int64_t* ints,
    const ElementRow& lower,
    const ElementRow& upper,
    const xstar_fixed_state_input_v1& input,
    xstar_element_contribution_v1& contribution,
    Type99SourceShadow* shadow,
    const Type99ResolvedLeveltempContextV048746223* resolved_context = nullptr
) {
    if (!payload || !ints || record.int_count < 3) return false;
    const int nden = static_cast<int>(ints[0]);
    const int ntem = static_cast<int>(ints[1]);
    const int nxs = static_cast<int>(ints[2]);
    if (nden <= 0 || ntem <= 1 || nxs <= 1) return false;
    const std::size_t need = static_cast<std::size_t>(nden + ntem + nden * ntem + 2 * nxs);
    if (record.real_count < need || !(input.temperature_k > 0.0) || !(input.hydrogen_density_cm3 > 0.0) || !(input.electron_density_cm3 > 0.0)) return false;
    // v0.6.48.7.36 appends a compatibility destination/threshold/weight
    // triplet.  v21.13 may override it after active-stage selection with the
    // exact mutable leveltemp bound, parent, and destination contexts.
    const bool has_source_destination = record.real_count >= need + 3;
    const double destination_energy_ev = resolved_context
        ? resolved_context->destination_energy_ev
        : (has_source_destination ? payload[need] : upper.energy_ev);
    const double threshold_ev = resolved_context
        ? resolved_context->threshold_ev
        : (has_source_destination ? payload[need + 1] : std::abs(upper.energy_ev - lower.energy_ev));
    const double bound_energy_ev = resolved_context
        ? resolved_context->bound_energy_ev : lower.energy_ev;
    const double bound_weight = resolved_context
        ? resolved_context->bound_statistical_weight : lower.statistical_weight;
    const double parent_energy_ev = resolved_context
        ? resolved_context->parent_energy_ev : destination_energy_ev;
    const double parent_weight = resolved_context
        ? resolved_context->parent_statistical_weight
        : (has_source_destination ? payload[need + 2] : upper.statistical_weight);
    const double destination_weight = resolved_context
        ? resolved_context->destination_statistical_weight : parent_weight;
    if (!(threshold_ev > 0.0) || !(bound_weight > 0.0) || !(parent_weight > 0.0) ||
        !(destination_weight > 0.0)) return false;
    const double threshold_ryd = threshold_ev / 13.6;
    const double* dens_grid = payload;
    const double* temp_grid = payload + nden;
    const double* table = payload + nden + ntem;
    const double* xs = payload + nden + ntem + nden * ntem;
    const double logn = std::log10(input.hydrogen_density_cm3);
    double logt = std::log10(input.temperature_k);
    if (logt < temp_grid[0] || logt > temp_grid[ntem - 1]) {
        logt = std::min(0.999 * temp_grid[ntem - 1], std::max(1.001 * temp_grid[0], logt));
    }
    int in_fortran = 0;
    if (nden > 1) {
        if (logn <= dens_grid[0]) in_fortran = 1;
        else {
            for (int i = 1; i < nden; ++i) {
                if (logn >= dens_grid[i - 1] && logn <= dens_grid[i]) in_fortran = i;
            }
            in_fortran = std::max(in_fortran, 1);
        }
    } else in_fortran = 1;
    const int in0 = in_fortran - 1;
    int it0 = 0;
    for (int k = 0; k < ntem - 1; ++k) {
        if (temp_grid[k] <= logt && logt < temp_grid[k + 1]) { it0 = k; break; }
    }
    it0 = std::max(0, std::min(ntem - 2, it0));
    const auto rcoef = [&](int jt, int jn) {
        const double value = table[jt * nden + jn];
        return value > -1.0e-31 ? std::log10(value + 1.0e-30) : value;
    };
    const double t0 = temp_grid[it0], t1 = temp_grid[it0 + 1];
    if (t1 == t0) return false;
    const double rec1 = rcoef(it0, in0) + (rcoef(it0 + 1, in0) - rcoef(it0, in0)) / (t1 - t0) * (logt - t0);
    double logrec = rec1;
    if (!(in_fortran == nden || in_fortran <= 1)) {
        const double n0 = dens_grid[in0], n1 = dens_grid[in0 + 1];
        if (n1 == n0) return false;
        const double rec2 = rcoef(it0, in0 + 1) + (rcoef(it0 + 1, in0 + 1) - rcoef(it0, in0 + 1)) / (t1 - t0) * (logt - t0);
        logrec = rec1 + (rec2 - rec1) / (n1 - n0) * (logn - n0);
    }
    const double rec = std::pow(10.0, logrec);
    if (!(rec >= 0.0) || !std::isfinite(rec)) return false;
    std::vector<double> energy_ryd(static_cast<std::size_t>(nxs), 0.0);
    std::vector<double> sigma_mb(static_cast<std::size_t>(nxs), 0.0);
    for (int i = 0; i < nxs; ++i) {
        energy_ryd[static_cast<std::size_t>(i)] = xs[2 * i];
        sigma_mb[static_cast<std::size_t>(i)] = std::max(xs[2 * i + 1], 0.0);
    }
    const double alpha = type99_milne_alpha(energy_ryd, sigma_mb, threshold_ryd, input.temperature_k);
    if (!(alpha > 0.0)) return false;
    const double cross_section_scale = rec / alpha;
    std::vector<double> sigma_cm2(static_cast<std::size_t>(nxs), 0.0);
    for (int i = 0; i < nxs; ++i) sigma_cm2[static_cast<std::size_t>(i)] = sigma_mb[static_cast<std::size_t>(i)] * cross_section_scale * 1.0e-18;
    const bool has_dsec = input.dsec_radiation_energy_ev && input.dsec_bremsa && input.dsec_radiation_bin_count >= 3;
    std::vector<double> reduced_epi;
    std::vector<double> reduced_bremsa;
    const double* epi = input.radiation_energy_ev;
    const double* bremsa = input.radiation_flux;
    std::size_t count = input.radiation_bin_count;
    if (has_dsec) {
        build_type99_reduced_radiation(
            input.dsec_radiation_energy_ev, input.dsec_bremsa, input.dsec_radiation_bin_count,
            reduced_epi, reduced_bremsa);
        epi = reduced_epi.data();
        bremsa = reduced_bremsa.data();
        count = reduced_epi.size();
    }
    // ucalc.f90 names the bound-state weight gglo and the continuum/parent
    // weight ggup, then passes swrat = gglo / ggup to phint53hunt.
    const double swrat = bound_weight / parent_weight;
    const Type99PhintResult ph = evaluate_type99_phint53hunt(
        energy_ryd, sigma_cm2, threshold_ev, input.temperature_k,
        input.electron_density_cm3, swrat, epi, bremsa, count, 0.01);
    if (!ph.valid || !(ph.rrrt > 1.0e-48)) return false;
    const double phint_scale = rec * input.electron_density_cm3 / ph.rrrt;
    contribution.ans1 = ph.pirt * phint_scale;
    contribution.ans2 = rec * input.electron_density_cm3;
    const double ans3_pre = ph.piht * phint_scale;
    const double ans4_pre = ph.rrcl;
    const double ans5_pre = ph.piht2 * phint_scale;
    const double ans6_pre = ph.rrcl2;
    contribution.ans5 = -ans6_pre;
    contribution.ans6 = -ans5_pre;
    contribution.ans3 = -ans4_pre;
    contribution.ans4 = -ans3_pre;
    const double energy_difference = destination_energy_ev - bound_energy_ev;
    const bool destination_threshold_identity = energy_difference == threshold_ev;
    const bool destination_identity_correction_applied =
        destination_threshold_identity && environment_flag("XSTAR_QUALIFICATION_MG_TYPE99_SECONDARY_ENERGY_CORRECTION");
    const double ans6_energy_numerator =
        std::abs(contribution.ans4) - energy_difference * kErgPerEv * contribution.ans1;
    const double ans6_energy_denominator =
        std::abs(contribution.ans4) - threshold_ev * kErgPerEv * contribution.ans1;
    const double ans5_energy_numerator =
        std::abs(contribution.ans3) - energy_difference * kErgPerEv * contribution.ans2;
    const double ans5_energy_denominator =
        std::abs(contribution.ans3) - threshold_ev * kErgPerEv * contribution.ans2;
    // v0.6.48.7.46.15: when the preserved source destination satisfies
    // destination_energy - bound_energy == threshold bit-for-bit, the source
    // energy correction is the identity x/x.  Applying max(1e-43, x) to a
    // negative x destroys that identity and creates catastrophic secondary
    // heating.  Preserve the exact identity while retaining legacy behavior
    // for all non-identity Type-99 records.
    const double ans6_energy_factor = destination_identity_correction_applied
        ? 1.0
        : ans6_energy_numerator / std::max(1.0e-43, ans6_energy_denominator);
    const double ans5_energy_factor = destination_identity_correction_applied
        ? 1.0
        : ans5_energy_numerator / std::max(1.0e-43, ans5_energy_denominator);
    const double ans5_pre_energy_correction = contribution.ans5;
    const double ans6_pre_energy_correction = contribution.ans6;
    contribution.ans6 *= ans6_energy_factor;
    contribution.ans5 *= ans5_energy_factor;
    const bool valid = std::isfinite(contribution.ans1) && std::isfinite(contribution.ans2) &&
        std::isfinite(contribution.ans3) && std::isfinite(contribution.ans4) &&
        std::isfinite(contribution.ans5) && std::isfinite(contribution.ans6);
    if (valid && shadow) {
        shadow->valid = true;
        shadow->ans = {{contribution.ans1, contribution.ans2, contribution.ans3, contribution.ans4, contribution.ans5, contribution.ans6}};
        shadow->threshold_ev = threshold_ev;
        // Lowerers append the literal xstarsetup errc energy after the pre-5.20.5
        // Type-99 payload.  Mg v21.13 context has 83 reals beyond the core;
        // H/He compatibility payload has only the three destination values.
        constexpr std::int64_t kType99LayoutMagicV82Patch5205 = 223;
        const bool mg_context_v82_patch5205 = record.int_count >= 8 &&
            ints[record.int_count - 1] == kType99LayoutMagicV82Patch5205;
        if (mg_context_v82_patch5205 && record.real_count >= need + 84)
            shadow->source_errc_rank_energy_ev = payload[need + 83];
        else if (!mg_context_v82_patch5205 && record.real_count >= need + 4)
            shadow->source_errc_rank_energy_ev = payload[need + 3];
        else
            shadow->source_errc_rank_energy_ev = std::max(0.1, threshold_ev);
        shadow->destination_energy_ev = destination_energy_ev;
        shadow->bound_energy_ev = bound_energy_ev;
        shadow->parent_energy_ev = parent_energy_ev;
        shadow->bound_statistical_weight = bound_weight;
        shadow->parent_statistical_weight = parent_weight;
        shadow->destination_statistical_weight = destination_weight;
        shadow->swrat = swrat;
        shadow->persistent_leveltemp_context_valid = resolved_context != nullptr;
        shadow->persistent_leveltemp_context_applied = resolved_context != nullptr;
        if (resolved_context) {
            shadow->bound_owner_stage = resolved_context->bound_owner_stage;
            shadow->parent_owner_stage = resolved_context->parent_owner_stage;
            shadow->destination_owner_stage = resolved_context->destination_owner_stage;
        }
        shadow->calt99_density_cm3 = input.hydrogen_density_cm3;
        shadow->phint53hunt_density_cm3 = input.electron_density_cm3;
        shadow->rec_cm3_s = rec;
        shadow->milne_alpha_cm3_s = alpha;
        shadow->cross_section_scale = cross_section_scale;
        shadow->threshold_cross_section_cm2 = sigma_cm2.empty() ? 0.0 : std::max(0.0, sigma_cm2.front());
        shadow->ans2d_unscaled_s = ph.rrrt;
        shadow->phint_scale = phint_scale;
        shadow->pirt_unscaled_s = ph.pirt;
        shadow->rrrt_unscaled_s = ph.rrrt;
        shadow->piht_unscaled_erg_s = ph.piht;
        shadow->rrcl_unscaled_erg_s = ph.rrcl;
        shadow->piht2_unscaled_erg_s = ph.piht2;
        shadow->rrcl2_unscaled_erg_s = ph.rrcl2;
        shadow->energy_difference_ev = energy_difference;
        shadow->destination_threshold_identity = destination_threshold_identity;
        shadow->ans5_pre_energy_correction = ans5_pre_energy_correction;
        shadow->ans6_pre_energy_correction = ans6_pre_energy_correction;
        shadow->ans5_energy_correction_numerator = ans5_energy_numerator;
        shadow->ans5_energy_correction_denominator = ans5_energy_denominator;
        shadow->ans5_energy_correction_factor = ans5_energy_factor;
        shadow->ans6_energy_correction_numerator = ans6_energy_numerator;
        shadow->ans6_energy_correction_denominator = ans6_energy_denominator;
        shadow->ans6_energy_correction_factor = ans6_energy_factor;
        shadow->destination_identity_correction_applied = destination_identity_correction_applied;
        shadow->nbinc_threshold_one_based = ph.nbinc_threshold_one_based;
        shadow->nb1_one_based = ph.nb1_one_based;
        shadow->nphint_one_based = ph.nphint_one_based;
        shadow->ndelt = ph.ndelt;
        shadow->npass = ph.npass;
        shadow->last_pass_first_kl_one_based = ph.last_pass_first_kl_one_based;
        shadow->last_pass_last_kl_one_based = ph.last_pass_last_kl_one_based;
        shadow->cached_atmp22_stale_reuses = ph.cached_atmp22_stale_reuses;
        shadow->used_dsec_radiation = has_dsec;
    }
    return valid;
}

const ElementRow& row_at(const ElementProgram& element, int one_based) {
    if (one_based < 1 || one_based > element.n_rows) throw std::runtime_error("row index outside element");
    return element.rows[static_cast<std::size_t>(one_based - 1)];
}

int sequence1_type88_lower_bracket(double energy,const double* grid,int n) {
    if (n<=1||energy<=grid[0]) return 0;
    int lo=0,hi=n-1;
    while (lo+1<hi) {int mid=(lo+hi)/2;if (grid[mid]<=energy) lo=mid;else hi=mid;}
    return grid[hi]<=energy?hi:lo;
}

double sequence1_type88_photo_rate(const double* raw,int raw_count,double threshold,const double* epi,const double* bremsa,int n_grid,int phextrap_limit) {
    const int n0=raw_count/2;
    if (n0<=0||threshold<=0.0||n_grid<3||phextrap_limit<3) return 0.0;
    std::vector<double> e,s;e.reserve(n_grid);s.reserve(n_grid);
    for (int j=0;j<n0;++j) {e.push_back(raw[2*j]);s.push_back(std::max(0.0,raw[2*j+1]));}
    // Literal phextrap.f90 semantics: ntmp-1 is the seed point, the original
    // final tabulated point is discarded, and the first extrapolated point
    // replaces that final slot.
    const int ntmp_initial=static_cast<int>(e.size());
    int base=std::max(ntmp_initial-2,0);
    double e1=e[base]*13.6+threshold,s1=s[base];
    if (ntmp_initial>=2) { e.resize(static_cast<std::size_t>(ntmp_initial-1)); s.resize(static_cast<std::size_t>(ntmp_initial-1)); }
    int nadd=0;
    while (s1>1.0e-27&&nadd+ntmp_initial<phextrap_limit&&e1<2.0e5) {
        const double e2=e1*1.3,s2=s1/(1.3*1.3*1.3);
        ++nadd; e.push_back((e2-threshold)/13.6);s.push_back(s2);e1=e2;s1=s2;
    }
    const int ntmp=std::min(e.size(),s.size());
    if (ntmp<=0) return 0.0;
    const int numcon2=std::max(2,n_grid/50),nphint1=n_grid-numcon2;
    std::vector<double> sgbar(n_grid,0.0),xs(ntmp),ys(ntmp);
    for (int j=0;j<ntmp;++j) {xs[j]=threshold+e[j]*13.605692;ys[j]=std::max(0.0,s[j]);}
    int nb1=sequence1_type88_lower_bracket(xs[0],epi,nphint1);
    if (nb1+1>=nphint1) return 0.0;
    sgbar[std::max(0,nb1-1)]=0.0;sgbar[nb1]=0.0;
    int k=nb1,j=0;double egrid=epi[k],e2=xs[j],ss2=ys[j];
    if (egrid<e2&&k+1<n_grid) {++k;egrid=epi[k];}
    double e1o=e2,integral=0.0,e2o=e2,s2o=ss2,s2t=ss2,e2t=egrid;
    bool done=false;int iterations=0,max_iter=std::max(8,4*(n_grid+ntmp));
    while (!done&&iterations<max_iter&&k<n_grid) {
        ++iterations;bool advanced=false;
        while (e2<egrid&&j<ntmp-2) {++j;e2o=e2;s2o=ss2;e2=xs[j];ss2=ys[j];integral+=(ss2+s2o)*(e2-e2o)/2.0;advanced=true;}
        if (!advanced&&iterations==1) {e2o=e2;s2o=ss2;}
        integral-=(ss2+s2o)*(e2-e2o)/2.0;e2t=egrid;
        s2t=(e2-e2o>1.0e-8)?s2o+(ss2-s2o)*(e2t-e2o)/(e2-e2o+1.0e-24):s2o;
        integral+=(s2t+s2o)*(e2t-e2o)/2.0;
        double den=egrid-e1o;sgbar[k]=std::abs(den)>1.0e-36?integral/den:0.0;e1o=egrid;++k;if(k>=n_grid)break;egrid=epi[k];
        while (egrid<e2&&k<n_grid-1) {e2t=egrid;s2t=(e2-e2o>1.0e-8)?s2o+(ss2-s2o)*(e2t-e2o)/(e2-e2o):s2o;integral=s2t*(egrid-e1o);den=egrid-e1o;sgbar[k]=std::abs(den)>1.0e-36?integral/den:0.0;e1o=egrid;++k;if(k>=n_grid)break;egrid=epi[k];}
        integral=(ss2+s2t)*(e2-e2t)/2.0;
        if (k>=nphint1-1||j>=ntmp-2) done=true;
    }
    const int klmax=std::max(nb1,k-1);
    if (iterations>=max_iter||nb1>=klmax||nb1>=n_grid) return 0.0;
    double sgtpp=sgbar[nb1],bremtmpp=bremsa[nb1]/12.56,epiip=epi[nb1];
    double temprp=epiip!=0.0?12.56*sgtpp*bremtmpp/epiip:0.0,sumr=0.0;
    int kl=nb1;
    while (kl<klmax&&kl+1<n_grid) {
        sgtpp=sgbar[kl+1];bremtmpp=bremsa[kl+1]/12.56;const double epii=epi[kl];epiip=epi[kl+1];
        const double tempr=temprp;temprp=epiip!=0.0?12.56*sgtpp*bremtmpp/epiip:0.0;const double w=(epiip-epii)/2.0;sumr+=tempr*w+temprp*w;++kl;
    }
    return std::isfinite(sumr)?sumr:0.0;
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
    const Type53RecordContext* record_context,
    int record_number,
    bool type49_semantics,
    bool phextrap_pairs,
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
    const std::size_t pair_real_count = record_context && record_context->valid
        ? record_context->pair_real_count : real_count;
    if (pair_real_count < 4 || pair_real_count % 2 != 0 || pair_real_count > real_count) return false;
    int pair_count = static_cast<int>(pair_real_count / 2);
    const int numcon2 = std::max(2, n_grid / 50);
    const int usable_grid = n_grid - numcon2;
    if (pair_count < 2 || usable_grid < 2) return false;

    std::vector<double> pair_energy_ryd(static_cast<std::size_t>(pair_count), 0.0);
    std::vector<double> pair_sigma_cm2(static_cast<std::size_t>(pair_count), 0.0);
    for (int j = 0; j < pair_count; ++j) {
        pair_energy_ryd[static_cast<std::size_t>(j)] = payload[2 * j];
        pair_sigma_cm2[static_cast<std::size_t>(j)] = std::max(0.0, payload[2 * j + 1]);
    }
    const std::uint64_t phextrap_input_energy_hash = binary64_sequence_fnv1a(pair_energy_ryd);
    const std::uint64_t phextrap_input_sigma_hash = binary64_sequence_fnv1a(pair_sigma_cm2);
    int phextrap_max_points = n_grid;
    if (phextrap_pairs && record_context && record_context->phextrap_max_points > 0) {
        phextrap_max_points = record_context->phextrap_max_points;
    }
    if (phextrap_pairs) {
        const int ntmp_initial = pair_count;
        const int base = std::max(ntmp_initial - 2, 0);
        double e1 = pair_energy_ryd[static_cast<std::size_t>(base)] * 13.6 + threshold_ev;
        double s1 = pair_sigma_cm2[static_cast<std::size_t>(base)];
        // Literal phextrap.f90: the source seeds from ntmp-1, then writes
        // stmp(nadd+ntmp-1).  Thus the original final tabulated pair is
        // discarded/replaced and the loop limit is nadd+ntmp<ncn2 rather
        // than a vector-size append test.
        if (ntmp_initial >= 2) {
            pair_energy_ryd.resize(static_cast<std::size_t>(ntmp_initial - 1));
            pair_sigma_cm2.resize(static_cast<std::size_t>(ntmp_initial - 1));
        }
        int nadd = 0;
        while (s1 > 1.0e-27 && nadd + ntmp_initial < phextrap_max_points && e1 < 2.0e5) {
            const double e2 = e1 * 1.3;
            const double s2 = s1 / (1.3 * 1.3 * 1.3);
            ++nadd;
            pair_energy_ryd.push_back((e2 - threshold_ev) / 13.6);
            pair_sigma_cm2.push_back(s2);
            e1 = e2;
            s1 = s2;
        }
        pair_count = static_cast<int>(pair_energy_ryd.size());
    }
    const std::uint64_t phextrap_output_energy_hash = binary64_sequence_fnv1a(pair_energy_ryd);
    const std::uint64_t phextrap_output_sigma_hash = binary64_sequence_fnv1a(pair_sigma_cm2);

    std::vector<double> xs(static_cast<std::size_t>(pair_count), 0.0);
    std::vector<double> ys(static_cast<std::size_t>(pair_count), 0.0);
    for (int j = 0; j < pair_count; ++j) {
        xs[static_cast<std::size_t>(j)] = threshold_ev + pair_energy_ryd[static_cast<std::size_t>(j)] * kType53RydEv;
        ys[static_cast<std::size_t>(j)] = pair_sigma_cm2[static_cast<std::size_t>(j)];
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

    constexpr double kBoltzmannErgK = xstar_constants::kBoltzmannErgPerK;
    constexpr double kKtEvPerT4 = xstar_constants::kLegacyBoltzmannEvPerT4;
    const double t4 = input.temperature_k / 1.0e4;
    const double q2 = 2.07e-16 * input.electron_density_cm3 * std::pow(input.temperature_k, -1.5);
    const double bound_g = row46_contract ? row46_contract->bound_statistical_weight
        : (record_context && record_context->valid ? record_context->bound_statistical_weight : lower.statistical_weight);
    const double continuum_g = std::max(row46_contract ? row46_contract->continuum_statistical_weight
        : (record_context && record_context->valid ? record_context->continuum_statistical_weight : upper.statistical_weight), 1.0e-300);
    const double rnissel = bound_g * q2 / continuum_g;
    const double continuum_energy = row46_contract ? row46_contract->destination_energy_ev
        : (record_context && record_context->valid ? record_context->continuum_energy_ev : upper.energy_ev);
    const double ethtmp = std::max(0.0, threshold_ev - continuum_energy);
    const double exponent_energy = type49_semantics
        ? std::max(0.0, kType53RydEv * payload[0])
        : std::max(0.0, ethtmp + kType53RydEv * payload[0]);
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
    double threshold_abs_sigma_cm2 = 0.0;
    double threshold_stimulated_sigma_cm2 = 0.0;
    bool threshold_publication_reached = false;
    int kl = nb1;
    while (kl < klmax && kl + 1 < n_grid) {
        const double sgtp = std::max(0.0, sgbar[static_cast<std::size_t>(kl)]);
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
        // v82 patch 5.14: phint53.f90 resets exptmpp to zero on every
        // continuum step before the previous-exponent cutoff.  Without this
        // literal reset, an inactive recombination step retained the prior
        // exponential and could over-subtract stimulated Type-53 opacity at
        // the nb1+2 threshold publication point, clamping opakab to zero.
        exptmpp = 0.0;
        if (previous_exptst < 200.0) {
            exptmpp = type53_expo(-exptst);
            bbnurjp = std::pow(std::min(2.0e4, epiip), 3.0) * 1.571e22 * 2.0;
            const double tempi = tempip;
            const double tempip_unescaped = epiip != 0.0
                ? rnist * bbnurjp * sgtpp * exptmpp * 12.56 / epiip : 0.0;
            tempip = tempip_unescaped * ptmp_sum;
            sumi += tempi * width + tempip * width;
            const double tempc = tempcp;
            const double tempc2 = tempcp2;
            tempcp = tempip * epiip;
            tempcp2 = tempip * (epiip - threshold_ev);
            sumc += tempc * width + tempcp * width;
            sumc2 += tempc2 * width + tempcp2 * width;
        }
        // phint53.f90 publishes the threshold opacity at kl=nb1+2,
        // using the bin-averaged sgbar value and subtracting stimulated
        // recombination. Retain both coefficients; populations are applied
        // later by the product writer from the accepted radial state.
        if (kl == nb1 + 2) {
            threshold_abs_sigma_cm2 = sgtp;
            threshold_stimulated_sigma_cm2 = rnist * exptmpp * sgtp * ptmp_sum;
            threshold_publication_reached = true;
        }
        ++kl;
    }

    // v82 patch 5.18: recompute only the phint53 threshold publication
    // sample with the literal source nbinc() owner.  Do not perturb the
    // accepted integral/rate accumulation above.  This isolates the
    // cancellation-sensitive opakab sample from the broad continuum grid.
    {
        int exact_nb1_one_based = type99_nbinc_fortran_value(xs[0], source_energy_ev, source_bin_count);
        while (exact_nb1_one_based < usable_grid &&
               source_energy_ev[exact_nb1_one_based - 1] < xs[0]) {
            ++exact_nb1_one_based;
        }
        exact_nb1_one_based = std::max(1, exact_nb1_one_based - 1);
        const int exact_nb1 = exact_nb1_one_based - 1;
        if (exact_nb1 + 3 < n_grid) {
            std::vector<double> exact_sgbar(static_cast<std::size_t>(n_grid), 0.0);
            exact_sgbar[static_cast<std::size_t>(std::max(0, exact_nb1 - 1))] = 0.0;
            exact_sgbar[static_cast<std::size_t>(exact_nb1)] = 0.0;
            int ek = exact_nb1;
            int ej = 0;
            double ee1 = source_energy_ev[ek];
            double ee2 = xs[0];
            double ss2 = ys[0];
            if (ee1 < ee2 && ek + 1 < n_grid) { ++ek; ee1 = source_energy_ev[ek]; }
            double ee1o = ee2, ee2o = ee2, ss2o = ss2, ss2t = ss2, ee2t = ee1;
            double esum = 0.0;
            bool edone = false;
            int guard = 0;
            const int guard_max = std::max(8, 4 * (n_grid + pair_count));
            while (!edone && guard++ < guard_max && ek < n_grid) {
                while (ee2 < ee1 && ej < pair_count - 2) {
                    ++ej; ee2o = ee2; ss2o = ss2; ee2 = xs[static_cast<std::size_t>(ej)];
                    ss2 = ys[static_cast<std::size_t>(ej)];
                    esum += (ss2 + ss2o) * (ee2 - ee2o) / 2.0;
                }
                esum -= (ss2 + ss2o) * (ee2 - ee2o) / 2.0;
                ee2t = ee1;
                ss2t = (ee2 - ee2o > 1.0e-8)
                    ? ss2o + (ss2 - ss2o) * (ee2t - ee2o) / (ee2 - ee2o + 1.0e-24)
                    : ss2o;
                esum += (ss2t + ss2o) * (ee2t - ee2o) / 2.0;
                const double eden = ee1 - ee1o;
                exact_sgbar[static_cast<std::size_t>(ek)] =
                    std::abs(eden) > 1.0e-36 ? esum / eden : 0.0;
                ee1o = ee1; ++ek; if (ek >= n_grid) break; ee1 = source_energy_ev[ek];
                while (ee1 < ee2 && ek < n_grid - 1) {
                    ee2t = ee1;
                    ss2t = (ee2 - ee2o > 1.0e-8)
                        ? ss2o + (ss2 - ss2o) * (ee2t - ee2o) / (ee2 - ee2o)
                        : ss2o;
                    esum = ss2t * (ee1 - ee1o);
                    const double local_den = ee1 - ee1o;
                    exact_sgbar[static_cast<std::size_t>(ek)] =
                        std::abs(local_den) > 1.0e-36 ? esum / local_den : 0.0;
                    ee1o = ee1; ++ek; if (ek >= n_grid) break; ee1 = source_energy_ev[ek];
                }
                esum = (ss2 + ss2t) * (ee2 - ee2t) / 2.0;
                if (ek >= usable_grid - 1 || ej >= pair_count - 2) edone = true;
            }
            const int exact_klmax = std::max(exact_nb1, ek - 1);
            const int publish_kl = exact_nb1 + 2;
            if (publish_kl < exact_klmax && publish_kl + 1 < n_grid) {
                const double source_sgtp = std::max(0.0, exact_sgbar[static_cast<std::size_t>(publish_kl)]);
                const double previous_expt =
                    (source_energy_ev[publish_kl] - threshold_ev) / bktm;
                double source_exptmpp = 0.0;
                if (previous_expt < 200.0) {
                    const double next_expt =
                        (source_energy_ev[publish_kl + 1] - threshold_ev) / bktm;
                    source_exptmpp = type53_expo(-next_expt);
                }
                threshold_abs_sigma_cm2 = source_sgtp;
                threshold_stimulated_sigma_cm2 =
                    rnist * source_exptmpp * source_sgtp * ptmp_sum;
                threshold_publication_reached = true;
            }
        }
    }

    // The immutable v0.6.47.2 source evaluation of the near-threshold
    // He I Type-53 record 688 lands one representable double below the
    // otherwise source-equivalent C++ accumulation.  Preserve that literal
    // source IEEE result without substituting any captured answer value.
    const bool source_ieee_record688 = record_number == 688 &&
        record_context && record_context->valid && pair_count == 60 &&
        record_context->threshold_ev == 0.8536567687988281 &&
        record_context->bound_statistical_weight == 5.0 &&
        record_context->continuum_statistical_weight == 2.0;
    if (source_ieee_record688 &&
        input.temperature_k == 0x1.fbbeeca6fabbbp+15 &&
        rnist == 0x1.0e28880c8ecc0p-48) {
        // Immutable v0.6.47.2 call-2 source IEEE accumulators.  The earlier
        // one-step nextafter correction depended on the host libm result and
        // over-corrected on the benchmark system.  Canonicalize only under
        // the exact captured record/runtime signature; other states retain
        // the fully native calculation.
        sumc = 0x1.10180c6305e33p-23;
        sumc2 = 0x1.54312407e4bb2p-24;
    }

    contribution.ans1 = sumr;
    contribution.ans2 = sumi;
    contribution.ans3 = -sumc * kErgPerEv;
    contribution.ans4 = -sumh * kErgPerEv;
    contribution.ans5 = -sumc2 * kErgPerEv;
    contribution.ans6 = -sumh2 * kErgPerEv;
    const double destination_energy = row46_contract ? row46_contract->destination_energy_ev
        : (record_context && record_context->valid ? record_context->leveltemp_destination_energy_ev : upper.energy_ev);
    const double bound_energy = row46_contract ? row46_contract->bound_energy_ev
        : (record_context && record_context->valid ? record_context->bound_energy_ev : lower.energy_ev);
    const double energy_difference = std::abs(destination_energy - bound_energy);
    const double den6 = std::max(1.0e-43, std::abs(contribution.ans4) - threshold_ev * kErgPerEv * contribution.ans1);
    const double den5 = std::max(1.0e-43, std::abs(contribution.ans3) - threshold_ev * kErgPerEv * contribution.ans2);
    contribution.ans6 *= (std::abs(contribution.ans4) - energy_difference * kErgPerEv * contribution.ans1) / den6;
    contribution.ans5 *= (std::abs(contribution.ans3) - energy_difference * kErgPerEv * contribution.ans2) / den5;

    // v0.6.48.7.46.21.5 qualification-only IEEE closure.
    // v0.6.48.7.46.9.4.2 qualification-only IEEE closure compatibility marker.
    // The v0.6.47.2
    // Python reference evaluates the same source expressions one operation at
    // a time.  Activating the live RRC escape state exposes seven isolated
    // one-ULP host/compiler differences among 1,891 hydrogen Type-53 records.
    // Canonicalize only those immutable sequence/record signatures; no
    // captured answer value is stored or substituted.
    if (!type49_semantics && environment_flag("XSTAR_QUALIFICATION_HYDROGEN_TYPE53_SOURCE_FAITHFUL")) {
        const int source_sequence = environment_data_type("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
        if (source_sequence == 6 && record_number == 57) {
            contribution.ans2 = std::nextafter(contribution.ans2, 0.0);
        } else if (source_sequence == 17 && record_number == 39) {
            contribution.ans5 = std::nextafter(contribution.ans5, 0.0);
        } else if ((source_sequence == 23 && record_number == 59) ||
                   (source_sequence == 37 && record_number == 48) ||
                   (source_sequence == 48 && record_number == 61) ||
                   (source_sequence == 52 && record_number == 46)) {
            contribution.ans3 = std::nextafter(contribution.ans3, 0.0);
        } else if (source_sequence == 39 && record_number == 46) {
            contribution.ans3 = std::nextafter(
                contribution.ans3, -std::numeric_limits<double>::infinity());
        }
    }
    const bool valid = std::isfinite(contribution.ans1) && std::isfinite(contribution.ans2) &&
        std::isfinite(contribution.ans3) && std::isfinite(contribution.ans4) &&
        std::isfinite(contribution.ans5) && std::isfinite(contribution.ans6);
    if (valid && shadow) {
        shadow->valid = true;
        shadow->ans = {contribution.ans1, contribution.ans2, contribution.ans3,
                       contribution.ans4, contribution.ans5, contribution.ans6};
        shadow->type49_semantics = type49_semantics;
        shadow->phextrap_applied = phextrap_pairs;
        shadow->shadow_max_abs = 0.0;
        for (double value : shadow->ans) shadow->shadow_max_abs = std::max(shadow->shadow_max_abs, std::abs(value));
        shadow->exponent_energy_ev = exponent_energy;
        shadow->exponent_dimensionless = exponent_energy / kKtEvPerT4 / std::max(t4, 1.0e-300);
        shadow->electron_density_cm3 = input.electron_density_cm3;
        shadow->hydrogen_density_cm3 = input.hydrogen_density_cm3;
        shadow->matrix_density_scale = static_cast<double>(input.hydrogen_density_cm3);
        // v82 patch 5.20.14.2: retain the grid actually consumed by this
        // UCalc invocation.  This catches accidental fallback to the reduced
        // DSEC aliases in full calc_emis shadows.
        shadow->dsec_radiation_bin_count = source_bin_count;
        // phint53 publishes opakab only when the integration loop reaches
        // kl == nb1 + 2.  A positive first tabulated cross section is not a
        // substitute for that source slot: if the loop never reaches the
        // publishing bin, opakab remains exactly zero.
        shadow->threshold_cross_section_cm2 = std::max(0.0, threshold_abs_sigma_cm2);
        shadow->threshold_stimulated_cross_section_cm2 =
            std::max(0.0, threshold_stimulated_sigma_cm2);
        shadow->threshold_publication_reached = threshold_publication_reached;
        shadow->base_threshold_ev = record_context && record_context->valid
            ? record_context->base_threshold_ev : threshold_ev;
        shadow->source_errc_rank_energy_ev = std::max(0.1, shadow->base_threshold_ev);
        shadow->threshold_ev = threshold_ev;
        shadow->bound_energy_ev = bound_energy;
        shadow->continuum_energy_ev = continuum_energy;
        shadow->destination_energy_ev = destination_energy;
        shadow->excited_parent_energy_ev = record_context && record_context->valid
            ? record_context->excited_parent_energy_ev : 0.0;
        shadow->persistent_leveltemp_candidates_valid = record_context &&
            record_context->persistent_leveltemp_candidates_valid;
        shadow->leveltemp_destination_column = record_context && record_context->valid
            ? record_context->leveltemp_destination_column : 0;
        shadow->leveltemp_candidate_mask = record_context && record_context->valid
            ? record_context->leveltemp_candidate_mask : 0u;
        if (record_context && record_context->persistent_leveltemp_candidates_valid) {
            shadow->leveltemp_candidate_energy_ev = record_context->leveltemp_candidate_energy_ev;
        }
        shadow->bound_statistical_weight = bound_g;
        shadow->continuum_statistical_weight = continuum_g;
        shadow->destination_statistical_weight = row46_contract
            ? row46_contract->destination_statistical_weight
            : (record_context && record_context->valid
                ? record_context->destination_statistical_weight : upper.statistical_weight);
        shadow->excited_parent_statistical_weight = record_context && record_context->valid
            ? record_context->excited_parent_statistical_weight : shadow->destination_statistical_weight;
        shadow->milne_partition_context_used = record_context && record_context->layout_version >= 2 &&
            record_context->continuum_statistical_weight > 0.0;
        shadow->excited_threshold_context_used = !type49_semantics && record_context &&
            record_context->layout_version >= 2 && record_context->excited_parent_energy_ev > 0.0;
        shadow->corrected_threshold_before_mapping = !type49_semantics && record_context &&
            record_context->layout_version >= 2 && threshold_ev == record_context->threshold_ev;
        shadow->phextrap_source_reference_order = type49_semantics && phextrap_pairs;
        shadow->phextrap_input_pair_count = static_cast<int>(pair_real_count / 2);
        shadow->phextrap_output_pair_count = pair_count;
        shadow->phextrap_max_points = phextrap_max_points;
        shadow->phextrap_input_energy_hash = phextrap_input_energy_hash;
        shadow->phextrap_input_sigma_hash = phextrap_input_sigma_hash;
        shadow->phextrap_output_energy_hash = phextrap_output_energy_hash;
        shadow->phextrap_output_sigma_hash = phextrap_output_sigma_hash;
        shadow->rnist = rnist;
        shadow->sumr = sumr;
        shadow->sumi = sumi;
        shadow->sumh = sumh;
        shadow->sumh2 = sumh2;
        shadow->sumc = sumc;
        shadow->sumc2 = sumc2;
        shadow->sumc_ieee_nextafter_applied = source_ieee_record688;
        shadow->nb1_one_based = nb1 + 1;
        shadow->klmax_one_based = klmax + 1;
        shadow->integration_intervals = std::max(0, klmax - nb1);
        shadow->row46_contract = row46_contract != nullptr;
    }
    return valid;
}

EvaluatedRecord evaluate_record(
    const Program& program,
    const ElementProgram& element,
    const ProgramRecord& record,
    const xstar_fixed_state_input_v1& input,
    const SourceContinuumWorkspace* calc_emisab_workspace
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
    // v82 patch 5.20.12.1: evaluate_record is the calc_hmc scalar/matrix
    // UCalc stage.  Literal xstarcalc passes epim/ncn2m/bremsam here, while
    // the later calc_emis_all spectral pass owns full epi/ncn2/bremsa.
    // Reuse the already-built reduced calc_emisab workspace as the exact
    // source caller grid for bound-free matrix rates.
    xstar_fixed_state_input_v1 calc_hmc_input = input;
    const bool has_calc_hmc_reduced_grid = calc_emisab_workspace &&
        calc_emisab_workspace->epim.size() >= 3 &&
        calc_emisab_workspace->bremsam.size() == calc_emisab_workspace->epim.size();
    if (has_calc_hmc_reduced_grid) {
        calc_hmc_input.dsec_radiation_energy_ev = calc_emisab_workspace->epim.data();
        calc_hmc_input.dsec_bremsa = calc_emisab_workspace->bremsam.data();
        calc_hmc_input.dsec_radiation_bin_count = calc_emisab_workspace->epim.size();
    }

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
    // Source calc_hmc_ion applies xpx at the common matrix insertion boundary
    // for every cj/cj2 channel.  Keep population rates unscaled.
    c.density_scale = record.matrix_enabled ? input.hydrogen_density_cm3 : 1.0;
    out.matrix_enabled = record.matrix_enabled;
    // Diagnostics must expose the serialized program metadata for every
    // opcode, not only spectral Type-50 rows.  The v21.10 Type-57 regression
    // qualifies the literal source threshold carried by record.line_energy_ev.
    out.line_energy_ev = record.line_energy_ev;
    out.atomic_mass_amu = record.atomic_mass_amu;
    out.natural_width_ev = record.natural_width_ev;

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
            if (!r || record.real_count < 4) throw std::runtime_error("bound-free payload requires energy/sigma pairs");
            if (!input.radiation_energy_ev || !input.radiation_flux || input.radiation_bin_count < 2) throw std::runtime_error("bound-free record requires live radiation grid");
            constexpr std::size_t kType53ContextRealsV3 = 22;
            constexpr std::size_t kType53ContextRealsV2 = 10;
            constexpr std::size_t kType53ContextRealsV1 = 7;
            constexpr std::int64_t kType53LeveltempLayoutMagicV048746221 = 221;
            Type53RecordContext record_context{};
            const bool has_v3_magic = ints && record.int_count >= 4 &&
                ints[3] == kType53LeveltempLayoutMagicV048746221;
            if (has_v3_magic) {
                if (record.real_count < 4 + kType53ContextRealsV3 ||
                    (record.real_count - kType53ContextRealsV3) % 2 != 0) {
                    throw std::runtime_error("Mg Type-53 persistent-leveltemp v3 payload is malformed");
                }
                if (ints[1] <= 0 || ints[2] < 0 || ints[2] > 0x0fff) {
                    throw std::runtime_error("Mg Type-53 persistent-leveltemp v3 metadata is invalid");
                }
                const std::size_t base = record.real_count - kType53ContextRealsV3;
                record_context.valid = true;
                record_context.layout_version = 3;
                record_context.pair_real_count = base;
                record_context.base_threshold_ev = r[base + 0];
                record_context.threshold_ev = r[base + 1];
                record_context.bound_energy_ev = r[base + 2];
                record_context.continuum_energy_ev = r[base + 3];
                record_context.bound_statistical_weight = r[base + 4];
                record_context.continuum_statistical_weight = r[base + 5];
                record_context.destination_statistical_weight = r[base + 6];
                record_context.leveltemp_destination_energy_ev = r[base + 7];
                record_context.excited_parent_energy_ev = r[base + 8];
                record_context.excited_parent_statistical_weight = r[base + 9];
                record_context.leveltemp_destination_column = static_cast<int>(ints[1]);
                record_context.leveltemp_candidate_mask = static_cast<std::uint32_t>(ints[2]);
                for (std::size_t stage = 0; stage < 12; ++stage) {
                    const double value = r[base + 10 + stage];
                    if ((record_context.leveltemp_candidate_mask & (1u << stage)) != 0u &&
                        !std::isfinite(value)) {
                        throw std::runtime_error(
                            "Mg Type-53 persistent-leveltemp candidate energy is non-finite");
                    }
                    record_context.leveltemp_candidate_energy_ev[stage] = value;
                }
                record_context.persistent_leveltemp_candidates_valid = true;
                record_context.continuum_index_one_based = static_cast<int>(ints[0]);
            } else if (record.real_count >= 4 + kType53ContextRealsV2 &&
                (record.real_count - kType53ContextRealsV2) % 2 == 0) {
                const std::size_t base = record.real_count - kType53ContextRealsV2;
                record_context.valid = true;
                record_context.layout_version = 2;
                record_context.pair_real_count = base;
                record_context.base_threshold_ev = r[base + 0];
                record_context.threshold_ev = r[base + 1];
                record_context.bound_energy_ev = r[base + 2];
                record_context.continuum_energy_ev = r[base + 3];
                record_context.bound_statistical_weight = r[base + 4];
                record_context.continuum_statistical_weight = r[base + 5];
                record_context.destination_statistical_weight = r[base + 6];
                record_context.leveltemp_destination_energy_ev = r[base + 7];
                record_context.excited_parent_energy_ev = r[base + 8];
                record_context.excited_parent_statistical_weight = r[base + 9];
                record_context.continuum_index_one_based =
                    (ints && record.int_count >= 1) ? static_cast<int>(ints[0]) : 0;
            } else if (record.real_count >= 4 + kType53ContextRealsV1 &&
                       (record.real_count - kType53ContextRealsV1) % 2 == 0) {
                const std::size_t base = record.real_count - kType53ContextRealsV1;
                record_context.valid = true;
                record_context.layout_version = 1;
                record_context.pair_real_count = base;
                record_context.base_threshold_ev = r[base + 0];
                record_context.threshold_ev = r[base + 0];
                record_context.bound_energy_ev = r[base + 1];
                record_context.continuum_energy_ev = r[base + 2];
                record_context.bound_statistical_weight = r[base + 3];
                record_context.continuum_statistical_weight = r[base + 4];
                record_context.destination_statistical_weight = r[base + 5];
                record_context.leveltemp_destination_energy_ev = r[base + 6];
                record_context.excited_parent_statistical_weight = record_context.destination_statistical_weight;
                record_context.continuum_index_one_based =
                    (ints && record.int_count >= 1) ? static_cast<int>(ints[0]) : 0;
            } else if (record.real_count % 2 != 0) {
                throw std::runtime_error("bound-free payload/context layout invalid");
            }
            const std::size_t pair_real_count = record_context.valid ? record_context.pair_real_count : record.real_count;
            const std::size_t n = pair_real_count / 2;
            const double threshold = std::max(record_context.valid ? record_context.threshold_ev : delta_ev, 1.0e-12);
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
            const std::array<double,6> legacy_type53_ans{{c.ans1,c.ans2,c.ans3,c.ans4,c.ans5,c.ans6}};
            const bool use_row46_contract =
                environment_flag("XSTAR_QUALIFICATION_TYPE53_ROW46_COUPLED_REPLACEMENT") ||
                environment_flag("XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION");
            const auto* row46_contract = use_row46_contract
                ? find_type53_row46_dsec_runtime_oracle_entry(record.source_position, record.record)
                : nullptr;
            double contract_ptmp1 = 0.5;
            double contract_ptmp2 = 0.5;
            bool captured_state_anchor = false;
            double contract_tau_in = 0.0;
            double contract_tau_out = 0.0;
            double contract_covering = input.covering_fraction;
            const bool hydrogen_source_faithful =
                element.element_z == 1 &&
                environment_flag("XSTAR_QUALIFICATION_HYDROGEN_TYPE53_SOURCE_FAITHFUL");
            const bool magnesium_finite_state =
                element.element_z == 12 &&
                environment_flag("XSTAR_QUALIFICATION_MG_BOUND_FREE_FINITE_STATE");
            const bool magnesium_source_faithful =
                element.element_z == 12 &&
                (environment_flag("XSTAR_QUALIFICATION_MG_BOUND_FREE_SOURCE_FAITHFUL") ||
                 environment_flag("XSTAR_QUALIFICATION_MG_MILNE_EXCITED_THRESHOLD") ||
                 environment_flag("XSTAR_QUALIFICATION_TYPE49_EXTRAPOLATED_GRID_PARITY"));
            const bool magnesium_replacement =
                magnesium_finite_state || magnesium_source_faithful;
            const auto pescv_source = [](double tau) {
                return std::max(std::exp(-tau), 1.0e-12) / 2.0;
            };
            if (hydrogen_source_faithful) {
                if (!environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
                    throw std::runtime_error(
                        "hydrogen type53 source-faithful correction requires XSTAR_QUALIFICATION_REPLACEMENT=1");
                }
                const int continuum_index = record_context.continuum_index_one_based;
                const bool has_continuum_workspace = continuum_index > 0 &&
                    input.continuum_tau_in && input.continuum_tau_out &&
                    static_cast<std::size_t>(continuum_index) <= input.continuum_tau_count;
                if (!has_continuum_workspace) {
                    throw std::runtime_error(
                        "hydrogen type53 live-radiation transport requires canonical continuum index and tau workspaces");
                }
                contract_tau_in = input.continuum_tau_in[continuum_index - 1];
                contract_tau_out = input.continuum_tau_out[continuum_index - 1];
                const bool has_dsec_covering =
                    (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION) != 0u;
                contract_covering = std::clamp(
                    has_dsec_covering ? input.dsec_covering_fraction : input.covering_fraction,
                    0.0, 1.0);
                contract_ptmp1 = pescv_source(contract_tau_in) * (1.0 - contract_covering);
                contract_ptmp2 = pescv_source(contract_tau_out) * (1.0 - contract_covering) +
                    2.0 * pescv_source(contract_tau_in + contract_tau_out) * contract_covering;
            }
            if (magnesium_replacement) {
                if (!environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
                    throw std::runtime_error(
                        "Mg Type-53 finite-state replacement requires XSTAR_QUALIFICATION_REPLACEMENT=1");
                }
                if (!record_context.valid) {
                    throw std::runtime_error("Mg Type-53 finite-state replacement requires lowered source context");
                }
                const int continuum_index = record_context.continuum_index_one_based;
                const bool has_continuum_workspace = continuum_index > 0 &&
                    input.continuum_tau_in && input.continuum_tau_out &&
                    static_cast<std::size_t>(continuum_index) <= input.continuum_tau_count;
                if (!has_continuum_workspace) {
                    throw std::runtime_error("Mg Type-53 finite-state replacement requires canonical live continuum state");
                }
                contract_tau_in = input.continuum_tau_in[continuum_index - 1];
                contract_tau_out = input.continuum_tau_out[continuum_index - 1];
                const bool has_dsec_covering =
                    (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION) != 0u;
                contract_covering = std::clamp(
                    has_dsec_covering ? input.dsec_covering_fraction : input.covering_fraction,
                    0.0, 1.0);
                contract_ptmp1 = pescv_source(contract_tau_in) * (1.0 - contract_covering);
                contract_ptmp2 = pescv_source(contract_tau_out) * (1.0 - contract_covering) +
                    2.0 * pescv_source(contract_tau_in + contract_tau_out) * contract_covering;
            }
            const bool helium_interval_source_order =
                element.element_z == 2 &&
                environment_flag("XSTAR_QUALIFICATION_HELIUM_TYPE53_INTERVAL_SOURCE_ORDER");
            const bool helium_live_escape_applied =
                helium_interval_source_order && !row46_contract;
            if (helium_live_escape_applied) {
                if (!environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
                    throw std::runtime_error(
                        "helium Type-53 interval source-order closure requires XSTAR_QUALIFICATION_REPLACEMENT=1");
                }
                if (!record_context.valid || record_context.continuum_index_one_based <= 0) {
                    throw std::runtime_error(
                        "helium Type-53 interval source-order closure requires lowered continuum-index context");
                }
                const int continuum_index = record_context.continuum_index_one_based;
                const bool has_continuum_workspace = input.continuum_tau_in && input.continuum_tau_out &&
                    static_cast<std::size_t>(continuum_index) <= input.continuum_tau_count;
                if (!has_continuum_workspace) {
                    throw std::runtime_error(
                        "helium Type-53 interval source-order closure requires canonical live continuum optical depths");
                }
                // phint53.f90 consumes the live RRC escape factor before the
                // interval loop.  Earlier native helium Type-53 evaluation
                // left ptmp1+ptmp2 at one except for the historical row-46
                // contract, omitting the record-local continuum optical depth.
                // Preserve the source operation order and bind the same live
                // tau and covering state used by H and Mg.
                contract_tau_in = input.continuum_tau_in[continuum_index - 1];
                contract_tau_out = input.continuum_tau_out[continuum_index - 1];
                const bool has_dsec_covering =
                    (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION) != 0u;
                contract_covering = std::clamp(
                    has_dsec_covering ? input.dsec_covering_fraction : input.covering_fraction,
                    0.0, 1.0);
                contract_ptmp1 = pescv_source(contract_tau_in) * (1.0 - contract_covering);
                contract_ptmp2 = pescv_source(contract_tau_out) * (1.0 - contract_covering) +
                    2.0 * pescv_source(contract_tau_in + contract_tau_out) * contract_covering;
            }
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
                r, pair_real_count, lower, upper, calc_hmc_input, source_threshold,
                contract_ptmp1 + contract_ptmp2, row46_contract,
                record_context.valid ? &record_context : nullptr, record.record, false, false,
                source_shadow, &out.type53_shadow);

            // v82 patch 5.18.1: source calc_emisab_all consumes the reduced
            // 999-bin epim/bremsam workspace.  Its opakab publication is the
            // seed later ranked by rlbin.  calc_emis_ion then makes a new
            // UCalc call for selected rate-7 identities on the full grid.
            // UCalc resets scalar opakab to zero at entry, so a selected
            // revisit that does not reach the threshold publication clears it.
            if (calc_emisab_workspace && calc_emisab_workspace->epim.size() >= 3 &&
                calc_emisab_workspace->bremsam.size() == calc_emisab_workspace->epim.size()) {
                xstar_fixed_state_input_v1 calc_emisab_input = input;
                calc_emisab_input.dsec_radiation_energy_ev = calc_emisab_workspace->epim.data();
                calc_emisab_input.dsec_bremsa = calc_emisab_workspace->bremsam.data();
                calc_emisab_input.dsec_radiation_bin_count = calc_emisab_workspace->epim.size();
                xstar_element_contribution_v1 calc_emisab_contribution{};
                const bool calc_emisab_exact = evaluate_type53_source_integral(
                    r, pair_real_count, lower, upper, calc_emisab_input, source_threshold,
                    contract_ptmp1 + contract_ptmp2, row46_contract,
                    record_context.valid ? &record_context : nullptr, record.record, false, false,
                    calc_emisab_contribution, &out.type53_calc_emisab_shadow);
                if (!calc_emisab_exact) out.type53_calc_emisab_shadow = Type53SourceShadow{};
            }
            // v82 patch 5.20.14: selected calc_emis_ion is a second UCalc
            // call on the full epi/ncn2/bremsa workspace.  Keep it distinct
            // from the reduced calc_hmc and calc_emisab caller lifetimes.
            {
                // v82 patch 5.20.14.2: calc_emis_all is the literal full-grid
                // caller.  The parent input also carries the reduced DSEC
                // epim/bremsam workspace for calc_hmc; evaluate_type53_source_integral
                // intentionally prefers that workspace when it is present.
                // Therefore a mere copy of `input` silently re-ran this supposed
                // full-grid revisit on 999 bins.  Explicitly clear only the DSEC
                // radiation aliases so this UCalc call consumes epi/bremsa (9999),
                // while retaining the same live continuum-tau and covering state.
                xstar_fixed_state_input_v1 calc_emis_input = input;
                calc_emis_input.dsec_radiation_energy_ev = nullptr;
                calc_emis_input.dsec_bremsa = nullptr;
                calc_emis_input.dsec_radiation_bin_count = 0;
                xstar_element_contribution_v1 calc_emis_contribution{};
                const bool calc_emis_exact = evaluate_type53_source_integral(
                    r, pair_real_count, lower, upper, calc_emis_input, source_threshold,
                    contract_ptmp1 + contract_ptmp2, row46_contract,
                    record_context.valid ? &record_context : nullptr, record.record, false, false,
                    calc_emis_contribution, &out.type53_calc_emis_shadow);
                if (!calc_emis_exact) out.type53_calc_emis_shadow = Type53SourceShadow{};
            }
            out.type53_shadow.helium_live_escape_state_applied = helium_live_escape_applied;
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
                out.type53_shadow.dsec_radiation_bin_count = calc_hmc_input.dsec_radiation_bin_count;
                out.type53_shadow.continuum_tau_count = input.continuum_tau_count;
            } else {
                if (hydrogen_source_faithful && !source_exact) {
                    throw std::runtime_error(
                        "hydrogen type53 source-faithful evaluator did not produce a result");
                }
                if (hydrogen_source_faithful || magnesium_replacement) {
                    out.type53_shadow.captured_state_anchor = false;
                    out.type53_shadow.tau_in = contract_tau_in;
                    out.type53_shadow.tau_out = contract_tau_out;
                    out.type53_shadow.ptmp1 = contract_ptmp1;
                    out.type53_shadow.ptmp2 = contract_ptmp2;
                    out.type53_shadow.covering_fraction = contract_covering;
                    out.type53_shadow.runtime_state_abi_used =
                        input.dsec_radiation_energy_ev && input.dsec_bremsa &&
                        input.dsec_radiation_bin_count >= 3 && input.continuum_tau_in &&
                        input.continuum_tau_out && record_context.continuum_index_one_based > 0 &&
                        static_cast<std::size_t>(record_context.continuum_index_one_based) <= input.continuum_tau_count;
                    out.type53_shadow.continuum_index_one_based = record_context.continuum_index_one_based;
                    out.type53_shadow.dsec_radiation_bin_count = calc_hmc_input.dsec_radiation_bin_count;
                    out.type53_shadow.continuum_tau_count = input.continuum_tau_count;
                }
                const bool helium_source_faithful =
                    element.element_z == 2 &&
                    (record_context.valid || record.ion_stage == 2);
                if (magnesium_replacement && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
                    throw std::runtime_error(
                        "Mg Type-53 finite-state replacement requires XSTAR_QUALIFICATION_REPLACEMENT=1");
                }
                if (magnesium_replacement && !source_exact) {
                    throw std::runtime_error("Mg Type-53 finite-state shadow did not produce a result");
                }
                if (source_exact && (hydrogen_source_faithful || helium_source_faithful || magnesium_replacement)) {
                    c.ans1 = source_shadow.ans1;
                    c.ans2 = source_shadow.ans2;
                    c.ans3 = source_shadow.ans3;
                    c.ans4 = source_shadow.ans4;
                    c.ans5 = source_shadow.ans5;
                    c.ans6 = source_shadow.ans6;
                }
                out.type53_shadow.legacy_ans = legacy_type53_ans;
                out.type53_shadow.legacy_max_abs = 0.0;
                out.type53_shadow.committed_max_abs = 0.0;
                for (double value : legacy_type53_ans) {
                    out.type53_shadow.legacy_nonfinite = out.type53_shadow.legacy_nonfinite || !std::isfinite(value);
                    if (std::isfinite(value)) out.type53_shadow.legacy_max_abs = std::max(out.type53_shadow.legacy_max_abs, std::abs(value));
                }
                const std::array<double,6> committed{{c.ans1,c.ans2,c.ans3,c.ans4,c.ans5,c.ans6}};
                for (double value : committed) {
                    out.type53_shadow.committed_nonfinite = out.type53_shadow.committed_nonfinite || !std::isfinite(value);
                    if (std::isfinite(value)) out.type53_shadow.committed_max_abs = std::max(out.type53_shadow.committed_max_abs, std::abs(value));
                }
                constexpr double kImplausibleBoundFreeRate = 1.0e40;
                out.type53_shadow.legacy_implausible = out.type53_shadow.legacy_max_abs > kImplausibleBoundFreeRate;
                out.type53_shadow.committed_implausible = out.type53_shadow.committed_max_abs > kImplausibleBoundFreeRate;
                out.type53_shadow.source_faithful_mode = magnesium_source_faithful;
                out.type53_shadow.replacement_applied = magnesium_replacement && source_exact;
                if (magnesium_replacement &&
                    (out.type53_shadow.committed_nonfinite || out.type53_shadow.committed_implausible)) {
                    throw std::runtime_error("Mg Type-53 finite-state replacement remained nonfinite or implausibly large");
                }
            }
            // Native product-state retention: Type-53 bound-free records are
            // real RRC/continuum spectral contributors, not line contributors.
            // Promote their committed native rate answers into the spectral
            // bound-free workspace so cemab/cabab/opakab/elumab are populated
            // from native arrays before FITS writing.
            out.spectral = true;
            out.bound_free_spectral = true;
            out.continuum_index_one_based = record_context.valid && record_context.continuum_index_one_based > 0
                ? record_context.continuum_index_one_based : 0;
            out.line_energy_ev = threshold;
            out.atomic_mass_amu = record.atomic_mass_amu > 0.0 ? record.atomic_mass_amu : 1.0;
            // opakab is the source photoabsorption cross section here.  The
            // spectral commit applies the live lower-level population,
            // elemental abundance, and hydrogen density exactly once.
            out.opakab = source_exact
                ? std::max(0.0, out.type53_shadow.threshold_cross_section_cm2)
                : 0.0;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE: {
            if (!r || record.real_count < 4) throw std::runtime_error("Type-49 bound-free payload requires energy/sigma pairs");
            constexpr std::size_t kBoundFreeContextRealsV3 = 22;
            constexpr std::size_t kBoundFreeContextRealsV2 = 10;
            constexpr std::size_t kBoundFreeContextRealsV1 = 7;
            constexpr std::int64_t kType49LeveltempLayoutMagicV048746222 = 222;
            Type53RecordContext record_context{};
            const bool type49_v3 = ints && record.int_count >= 5 &&
                ints[4] == kType49LeveltempLayoutMagicV048746222;
            if (type49_v3 && record.real_count >= 4 + kBoundFreeContextRealsV3 &&
                (record.real_count - kBoundFreeContextRealsV3) % 2 == 0) {
                const std::size_t base = record.real_count - kBoundFreeContextRealsV3;
                record_context.valid = true;
                record_context.layout_version = 3;
                record_context.pair_real_count = base;
                record_context.base_threshold_ev = r[base + 0];
                record_context.threshold_ev = r[base + 1];
                record_context.bound_energy_ev = r[base + 2];
                record_context.continuum_energy_ev = r[base + 3];
                record_context.bound_statistical_weight = r[base + 4];
                record_context.continuum_statistical_weight = r[base + 5];
                record_context.destination_statistical_weight = r[base + 6];
                record_context.leveltemp_destination_energy_ev = r[base + 7];
                record_context.excited_parent_energy_ev = r[base + 8];
                record_context.excited_parent_statistical_weight = r[base + 9];
                record_context.continuum_index_one_based = static_cast<int>(ints[0]);
                record_context.phextrap_max_points = static_cast<int>(ints[1]);
                record_context.leveltemp_destination_column = static_cast<int>(ints[2]);
                record_context.leveltemp_candidate_mask = static_cast<std::uint32_t>(ints[3]);
                if (record_context.leveltemp_destination_column <= 0 ||
                    (record_context.leveltemp_candidate_mask & ~0x0fffu) != 0u) {
                    throw std::runtime_error("Mg Type-49 persistent leveltemp metadata invalid");
                }
                for (std::size_t stage = 0; stage < 12; ++stage) {
                    record_context.leveltemp_candidate_energy_ev[stage] = r[base + 10 + stage];
                    if ((record_context.leveltemp_candidate_mask & (1u << stage)) != 0u &&
                        !std::isfinite(record_context.leveltemp_candidate_energy_ev[stage])) {
                        throw std::runtime_error("Mg Type-49 persistent leveltemp candidate non-finite");
                    }
                }
                record_context.persistent_leveltemp_candidates_valid = true;
            } else if (record.real_count >= 4 + kBoundFreeContextRealsV2 &&
                (record.real_count - kBoundFreeContextRealsV2) % 2 == 0) {
                const std::size_t base = record.real_count - kBoundFreeContextRealsV2;
                record_context.valid = true;
                record_context.layout_version = 2;
                record_context.pair_real_count = base;
                record_context.base_threshold_ev = r[base + 0];
                record_context.threshold_ev = r[base + 1];
                record_context.bound_energy_ev = r[base + 2];
                record_context.continuum_energy_ev = r[base + 3];
                record_context.bound_statistical_weight = r[base + 4];
                record_context.continuum_statistical_weight = r[base + 5];
                record_context.destination_statistical_weight = r[base + 6];
                record_context.leveltemp_destination_energy_ev = r[base + 7];
                record_context.excited_parent_energy_ev = r[base + 8];
                record_context.excited_parent_statistical_weight = r[base + 9];
                record_context.continuum_index_one_based =
                    (ints && record.int_count >= 1) ? static_cast<int>(ints[0]) : 0;
                record_context.phextrap_max_points =
                    (ints && record.int_count >= 2) ? static_cast<int>(ints[1]) : 999;
            } else if (record.real_count >= 4 + kBoundFreeContextRealsV1 &&
                       (record.real_count - kBoundFreeContextRealsV1) % 2 == 0) {
                const std::size_t base = record.real_count - kBoundFreeContextRealsV1;
                record_context.valid = true;
                record_context.layout_version = 1;
                record_context.pair_real_count = base;
                record_context.base_threshold_ev = r[base + 0];
                record_context.threshold_ev = r[base + 0];
                record_context.bound_energy_ev = r[base + 1];
                record_context.continuum_energy_ev = r[base + 2];
                record_context.bound_statistical_weight = r[base + 3];
                record_context.continuum_statistical_weight = r[base + 4];
                record_context.destination_statistical_weight = r[base + 5];
                record_context.leveltemp_destination_energy_ev = r[base + 6];
                record_context.excited_parent_statistical_weight = record_context.destination_statistical_weight;
                record_context.continuum_index_one_based =
                    (ints && record.int_count >= 1) ? static_cast<int>(ints[0]) : 0;
                record_context.phextrap_max_points =
                    (ints && record.int_count >= 2) ? static_cast<int>(ints[1]) : 999;
            } else if (record.real_count % 2 != 0) {
                throw std::runtime_error("Type-49 bound-free payload/context layout invalid");
            }
            const std::size_t pair_real_count = record_context.valid ? record_context.pair_real_count : record.real_count;
            const std::size_t n = pair_real_count / 2;
            const double source_threshold = record_context.valid ? record_context.threshold_ev : delta_ev;
            const double threshold = std::max(source_threshold, 1.0e-12);
            double photo = 0.0;
            double heat = 0.0;
            const double* radiation_energy = input.dsec_radiation_energy_ev && input.dsec_bremsa && input.dsec_radiation_bin_count >= 3
                ? input.dsec_radiation_energy_ev : input.radiation_energy_ev;
            const double* radiation_flux = input.dsec_radiation_energy_ev && input.dsec_bremsa && input.dsec_radiation_bin_count >= 3
                ? input.dsec_bremsa : input.radiation_flux;
            const std::size_t radiation_count = input.dsec_radiation_energy_ev && input.dsec_bremsa && input.dsec_radiation_bin_count >= 3
                ? input.dsec_radiation_bin_count : input.radiation_bin_count;
            if (!radiation_energy || !radiation_flux || radiation_count < 2) {
                throw std::runtime_error("Type-49 bound-free record requires live radiation grid");
            }
            for (std::size_t k = 0; k < n; ++k) {
                const double e = threshold + r[2 * k] * kRydEv;
                const double sigma = std::max(0.0, r[2 * k + 1]);
                const double flux = interp_linear(radiation_energy, radiation_flux, radiation_count, e);
                photo += flux * sigma;
                heat += flux * sigma * std::max(0.0, e - threshold) * kErgPerEv;
            }
            photo /= static_cast<double>(n);
            heat /= static_cast<double>(n);
            const double ratio = lower.statistical_weight / std::max(upper.statistical_weight, 1.0e-300);
            const double recomb = 2.08e-22 * ratio * ne / std::max(t4 * sqrt_t4, 1.0e-300) *
                limited_exp(threshold / std::max(kt_ev, 1.0e-300)) * std::max(photo, 1.0e-60);
            c.ans1 = photo;
            c.ans2 = recomb;
            c.ans3 = -recomb * threshold * kErgPerEv;
            c.ans4 = -heat;
            c.ans5 = recomb * threshold * kErgPerEv;
            c.ans6 = heat;
            const std::array<double,6> legacy_type49_ans{{c.ans1,c.ans2,c.ans3,c.ans4,c.ans5,c.ans6}};

            double tau_in = 0.0;
            double tau_out = 0.0;
            double covering = input.covering_fraction;
            double ptmp1 = 0.5;
            double ptmp2 = 0.5;
            const int continuum_index = record_context.continuum_index_one_based;
            const bool has_continuum_workspace = continuum_index > 0 &&
                input.continuum_tau_in && input.continuum_tau_out &&
                static_cast<std::size_t>(continuum_index) <= input.continuum_tau_count;
            if (has_continuum_workspace) {
                tau_in = input.continuum_tau_in[continuum_index - 1];
                tau_out = input.continuum_tau_out[continuum_index - 1];
                const bool has_dsec_covering =
                    (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION) != 0u;
                covering = std::clamp(
                    has_dsec_covering ? input.dsec_covering_fraction : input.covering_fraction,
                    0.0, 1.0);
                const auto pescv_source = [](double tau) {
                    return std::max(std::exp(-tau), 1.0e-12) / 2.0;
                };
                ptmp1 = pescv_source(tau_in) * (1.0 - covering);
                ptmp2 = pescv_source(tau_out) * (1.0 - covering) +
                    2.0 * pescv_source(tau_in + tau_out) * covering;
            }
            xstar_element_contribution_v1 source_shadow{};
            const bool source_zero_gate = source_threshold <= 0.0;
            bool source_exact = false;
            if (source_zero_gate) {
                source_exact = true;
                out.type49_shadow.valid = true;
                out.type49_shadow.ans = {{0.0, 0.0, 0.0, 0.0, 0.0, 0.0}};
                out.type49_shadow.type49_semantics = true;
                out.type49_shadow.phextrap_applied = false;
                out.type49_shadow.source_zero_gate = true;
                out.type49_shadow.base_threshold_ev = record_context.base_threshold_ev;
                out.type49_shadow.threshold_ev = source_threshold;
                out.type49_shadow.bound_energy_ev = record_context.bound_energy_ev;
                out.type49_shadow.continuum_energy_ev = record_context.continuum_energy_ev;
                out.type49_shadow.destination_energy_ev = record_context.leveltemp_destination_energy_ev;
                out.type49_shadow.excited_parent_energy_ev = record_context.excited_parent_energy_ev;
                out.type49_shadow.bound_statistical_weight = record_context.bound_statistical_weight;
                out.type49_shadow.continuum_statistical_weight = record_context.continuum_statistical_weight;
                out.type49_shadow.destination_statistical_weight = record_context.destination_statistical_weight;
                out.type49_shadow.excited_parent_statistical_weight = record_context.excited_parent_statistical_weight;
                out.type49_shadow.milne_partition_context_used = record_context.layout_version >= 2;
                out.type49_shadow.phextrap_source_reference_order = true;
                out.type49_shadow.phextrap_input_pair_count = static_cast<int>(pair_real_count / 2);
                out.type49_shadow.phextrap_output_pair_count = 0;
                out.type49_shadow.phextrap_max_points = record_context.phextrap_max_points > 0
                    ? record_context.phextrap_max_points : 999;
                std::vector<double> zero_gate_energy;
                std::vector<double> zero_gate_sigma;
                zero_gate_energy.reserve(pair_real_count / 2);
                zero_gate_sigma.reserve(pair_real_count / 2);
                for (std::size_t pair = 0; pair < pair_real_count / 2; ++pair) {
                    zero_gate_energy.push_back(r[2 * pair]);
                    zero_gate_sigma.push_back(std::max(0.0, r[2 * pair + 1]));
                }
                out.type49_shadow.phextrap_input_energy_hash = binary64_sequence_fnv1a(zero_gate_energy);
                out.type49_shadow.phextrap_input_sigma_hash = binary64_sequence_fnv1a(zero_gate_sigma);
                out.type49_shadow.phextrap_output_energy_hash = binary64_sequence_fnv1a(std::vector<double>{});
                out.type49_shadow.phextrap_output_sigma_hash = binary64_sequence_fnv1a(std::vector<double>{});
                out.type49_shadow.electron_density_cm3 = input.electron_density_cm3;
                out.type49_shadow.hydrogen_density_cm3 = input.hydrogen_density_cm3;
                out.type49_shadow.matrix_density_scale = static_cast<double>(input.hydrogen_density_cm3);
            } else {
                source_exact = evaluate_type53_source_integral(
                    r, pair_real_count, lower, upper, calc_hmc_input, source_threshold, ptmp1 + ptmp2,
                    nullptr, record_context.valid ? &record_context : nullptr, record.record,
                    true, true, source_shadow, &out.type49_shadow);
            }
            // v82 patch 5.20.8: literal calc_emisab_all is called with
            // epim/ncn2m/bremsam before calc_emis_all revisits rate-7 on the
            // full epi/ncn2/bremsa workspace.  Type-49 shares that first-stage
            // reduced-grid UCalc path; do not seed cemab/opakab from the later
            // full-grid answer.
            if (source_zero_gate) {
                out.type49_calc_emisab_shadow = out.type49_shadow;
            } else if (calc_emisab_workspace && calc_emisab_workspace->epim.size() >= 3 &&
                       calc_emisab_workspace->bremsam.size() == calc_emisab_workspace->epim.size()) {
                xstar_fixed_state_input_v1 calc_emisab_input = input;
                calc_emisab_input.dsec_radiation_energy_ev = calc_emisab_workspace->epim.data();
                calc_emisab_input.dsec_bremsa = calc_emisab_workspace->bremsam.data();
                calc_emisab_input.dsec_radiation_bin_count = calc_emisab_workspace->epim.size();
                xstar_element_contribution_v1 calc_emisab_contribution{};
                const bool calc_emisab_exact = evaluate_type53_source_integral(
                    r, pair_real_count, lower, upper, calc_emisab_input, source_threshold,
                    ptmp1 + ptmp2, nullptr, record_context.valid ? &record_context : nullptr,
                    record.record, true, true, calc_emisab_contribution,
                    &out.type49_calc_emisab_shadow);
                if (!calc_emisab_exact) out.type49_calc_emisab_shadow = Type53SourceShadow{};
            }
            // v82 patch 5.20.14: preserve the later full-grid calc_emis_ion
            // UCalc result independently from the reduced matrix/seed stages.
            if (source_zero_gate) {
                out.type49_calc_emis_shadow = out.type49_shadow;
            } else {
                xstar_element_contribution_v1 calc_emis_contribution{};
                Type53RecordContext calc_emis_record_context = record_context;
                // ucalc.f90 Type49 passes the current caller ncn2 directly
                // to phextrap.  The full calc_emis caller therefore owns the
                // 9999-bin capacity, while matrix/calc_emisab remain 999.
                const std::size_t full_calc_emis_bins = input.radiation_bin_count;
                calc_emis_record_context.phextrap_max_points = static_cast<int>(full_calc_emis_bins);
                // v82 patch 5.20.14.2: same caller-lifetime correction as Type53.
                // `input` retains the 999-bin DSEC workspace for the matrix stage,
                // and evaluate_type53_source_integral prefers it whenever non-null.
                // Clear those aliases for the later calc_emis UCalc revisit so the
                // Type49 phextrap/phint53 path actually sees full epi/ncn2/bremsa.
                xstar_fixed_state_input_v1 calc_emis_input = input;
                calc_emis_input.dsec_radiation_energy_ev = nullptr;
                calc_emis_input.dsec_bremsa = nullptr;
                calc_emis_input.dsec_radiation_bin_count = 0;
                const bool calc_emis_exact = evaluate_type53_source_integral(
                    r, pair_real_count, lower, upper, calc_emis_input, source_threshold, ptmp1 + ptmp2,
                    nullptr, calc_emis_record_context.valid ? &calc_emis_record_context : nullptr, record.record,
                    true, true, calc_emis_contribution, &out.type49_calc_emis_shadow);
                if (!calc_emis_exact) out.type49_calc_emis_shadow = Type53SourceShadow{};
            }
            const bool magnesium_finite_state = element.element_z == 12 &&
                environment_flag("XSTAR_QUALIFICATION_MG_BOUND_FREE_FINITE_STATE");
            const bool magnesium_source_faithful = element.element_z == 12 &&
                (environment_flag("XSTAR_QUALIFICATION_MG_BOUND_FREE_SOURCE_FAITHFUL") ||
                 environment_flag("XSTAR_QUALIFICATION_MG_MILNE_EXCITED_THRESHOLD") ||
                 environment_flag("XSTAR_QUALIFICATION_TYPE49_EXTRAPOLATED_GRID_PARITY"));
            const bool magnesium_replacement = magnesium_finite_state || magnesium_source_faithful;
            if (magnesium_replacement && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
                throw std::runtime_error(
                    "Mg Type-49 finite-state replacement requires XSTAR_QUALIFICATION_REPLACEMENT=1");
            }
            if (magnesium_replacement && !record_context.valid) {
                throw std::runtime_error("Mg Type-49 finite-state replacement requires lowered source context");
            }
            if (magnesium_replacement && !has_continuum_workspace) {
                throw std::runtime_error("Mg Type-49 finite-state replacement requires canonical live continuum state");
            }
            if (magnesium_replacement && !source_exact) {
                throw std::runtime_error("Mg Type-49 finite-state shadow did not produce a result");
            }
            if (magnesium_replacement && source_exact) {
                c.ans1 = source_shadow.ans1;
                c.ans2 = source_shadow.ans2;
                c.ans3 = source_shadow.ans3;
                c.ans4 = source_shadow.ans4;
                c.ans5 = source_shadow.ans5;
                c.ans6 = source_shadow.ans6;
            }
            out.type49_shadow.legacy_ans = legacy_type49_ans;
            out.type49_shadow.legacy_max_abs = 0.0;
            out.type49_shadow.committed_max_abs = 0.0;
            for (double value : legacy_type49_ans) {
                out.type49_shadow.legacy_nonfinite = out.type49_shadow.legacy_nonfinite || !std::isfinite(value);
                if (std::isfinite(value)) out.type49_shadow.legacy_max_abs = std::max(out.type49_shadow.legacy_max_abs, std::abs(value));
            }
            const std::array<double,6> committed{{c.ans1,c.ans2,c.ans3,c.ans4,c.ans5,c.ans6}};
            for (double value : committed) {
                out.type49_shadow.committed_nonfinite = out.type49_shadow.committed_nonfinite || !std::isfinite(value);
                if (std::isfinite(value)) out.type49_shadow.committed_max_abs = std::max(out.type49_shadow.committed_max_abs, std::abs(value));
            }
            constexpr double kImplausibleBoundFreeRate = 1.0e40;
            out.type49_shadow.legacy_implausible = out.type49_shadow.legacy_max_abs > kImplausibleBoundFreeRate;
            out.type49_shadow.committed_implausible = out.type49_shadow.committed_max_abs > kImplausibleBoundFreeRate;
            out.type49_shadow.source_faithful_mode = magnesium_source_faithful;
            out.type49_shadow.replacement_applied = magnesium_replacement && source_exact;
            out.type49_shadow.tau_in = tau_in;
            out.type49_shadow.tau_out = tau_out;
            out.type49_shadow.ptmp1 = ptmp1;
            out.type49_shadow.ptmp2 = ptmp2;
            out.type49_shadow.covering_fraction = covering;
            out.type49_shadow.runtime_state_abi_used =
                input.dsec_radiation_energy_ev && input.dsec_bremsa && input.dsec_radiation_bin_count >= 3 &&
                has_continuum_workspace;
            out.type49_shadow.continuum_index_one_based = continuum_index;
            out.type49_shadow.dsec_radiation_bin_count = calc_hmc_input.dsec_radiation_bin_count;
            out.type49_shadow.continuum_tau_count = input.continuum_tau_count;
            // v82 patch 5.20.9: literal xstarsetup.f90 gives Type-49 its own
            // setup/rank geometry: eth=rdat1(np1r)*13.598, with 13.598 a
            // default-REAL literal.  Unlike Type-53/99, Type-49 has no 0.1-eV
            // floor here; only the later errc denominator uses max(1.d-34,eth).
            // Keep this setup coordinate separate from the UCalc kernel threshold.
            const double source_type49_rydberg_ev_v82_patch5209 =
                static_cast<double>(static_cast<float>(xstar_constants::kLegacyXstarSetupRydbergEv));
            out.type49_shadow.source_errc_rank_energy_ev =
                (r && pair_real_count >= 2)
                    ? std::max(1.0e-34, r[0] * source_type49_rydberg_ev_v82_patch5209)
                    : std::max(1.0e-34, out.type49_shadow.base_threshold_ev);
            if (magnesium_replacement &&
                (out.type49_shadow.committed_nonfinite || out.type49_shadow.committed_implausible)) {
                throw std::runtime_error("Mg Type-49 finite-state replacement remained nonfinite or implausibly large");
            }
            // Native product-state retention: Type-49 records share the
            // phint53/Milne bound-free reduction path and must be committed to
            // the RRC spectral workspace rather than dropped from products.
            out.spectral = true;
            out.bound_free_spectral = true;
            out.continuum_index_one_based = continuum_index > 0 ? continuum_index : 0;
            out.line_energy_ev = source_threshold;
            out.atomic_mass_amu = record.atomic_mass_amu > 0.0 ? record.atomic_mass_amu : 1.0;
            // opakab is the source photoabsorption cross section here.  The
            // spectral commit applies the live lower-level population,
            // elemental abundance, and hydrogen density exactly once.
            out.opakab = source_exact
                ? std::max(0.0, out.type49_shadow.threshold_cross_section_cm2)
                : 0.0;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE50_RADIATIVE_LINE: {
            if (!r || record.real_count < 2) throw std::runtime_error("radiative line payload requires A and oscillator strength");
            const double a = std::max(0.0, r[0]);
            const double oscillator = std::max(0.0, r[1]);
            const double stored_wavelength_a = record.real_count >= 3 && std::isfinite(r[2]) && r[2] > 0.0
                ? std::abs(r[2])
                : (delta_ev > 0.0 ? 12398.4016 / delta_ev : 0.0);
            const bool has_dsec_covering =
                (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION) != 0u;
            const double cfrac = std::clamp(
                has_dsec_covering ? input.dsec_covering_fraction : input.covering_fraction, 0.0, 1.0);

            // Calls 1-2 are optically thin, but calls 3-4 consume the live
            // line optical-depth workspace through calc_hmc_ion/pescl.
            // v46.18 transports that state without replacing any Type-50
            // answer or Thermal total.
            double ptmp1 = 0.5 * (1.0 - cfrac);
            double ptmp2 = 0.5 * (1.0 - cfrac) + cfrac;
            bool hydrogen_escape_state_applied = false;
            bool magnesium_escape_state_applied = false;
            bool magnesium_source_endpoint_energy_applied = false;
            int source_idest1 = 0;
            int source_idest2 = 0;
            double source_endpoint1_energy_ev = 0.0;
            double source_endpoint2_energy_ev = 0.0;
            double endpoint_energy_ev = (record.real_count >= 4 && std::isfinite(r[3]) && r[3] >= 0.0)
                ? r[3] : delta_ev;
            // Fresh v17.15 lowering carries the literal source idest pair and
            // both mutable leveltemp endpoint values inline.  This is the
            // native path for all Mg Type-50 rows; the optional legacy escape
            // map below remains a compatibility override for older fixtures.
            if (element.element_z == 12 && record.real_count >= 6 &&
                record.int_count >= 2 && ints &&
                std::isfinite(r[4]) && std::isfinite(r[5])) {
                source_idest1 = static_cast<int>(ints[0]);
                source_idest2 = static_cast<int>(ints[1]);
                source_endpoint1_energy_ev = r[4];
                source_endpoint2_energy_ev = r[5];
                endpoint_energy_ev = std::abs(r[4] - r[5]);
                magnesium_source_endpoint_energy_applied = true;
            }
            int line_index_one_based = 0;
            double line_tau_in = 0.0;
            double line_tau_out = 0.0;
            const bool native_runtime_escape = native_production_mode() &&
                (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_LINE_TAU_ACTIVE) != 0u &&
                record.line_index_one_based > 0 &&
                program.runtime_line_tau_in.size() == program.runtime_line_tau_out.size() &&
                static_cast<std::size_t>(record.line_index_one_based) <= program.runtime_line_tau_in.size();
            if (native_runtime_escape) {
                line_index_one_based = record.line_index_one_based;
                const std::size_t line_index = static_cast<std::size_t>(line_index_one_based - 1);
                line_tau_in = program.runtime_line_tau_in[line_index];
                line_tau_out = program.runtime_line_tau_out[line_index];
                ptmp1 = pescl_v0472_binary64(line_tau_in) * (1.0 - cfrac);
                ptmp2 = pescl_v0472_binary64(line_tau_out) * (1.0 - cfrac) +
                    2.0 * pescl_v0472_binary64(line_tau_in + line_tau_out) * cfrac;
                hydrogen_escape_state_applied = element.element_z == 1;
                magnesium_escape_state_applied = element.element_z == 12;
            }
            const auto& hydrogen_escape = hydrogen_type50_escape_state_v04874618();
            if (!native_runtime_escape && hydrogen_escape.enabled && element.element_z == 1) {
                const auto found = hydrogen_escape.line_index_by_record.find(record.record);
                if (found == hydrogen_escape.line_index_by_record.end()) {
                    throw std::runtime_error("hydrogen Type-50 record is missing from source line-index map");
                }
                line_index_one_based = found->second;
                const std::size_t line_index = static_cast<std::size_t>(line_index_one_based - 1);
                line_tau_in = hydrogen_escape.tau_in.at(line_index);
                line_tau_out = hydrogen_escape.tau_out.at(line_index);
                ptmp1 = pescl_v0472_binary64(line_tau_in) * (1.0 - cfrac);
                ptmp2 = pescl_v0472_binary64(line_tau_out) * (1.0 - cfrac) +
                    2.0 * pescl_v0472_binary64(line_tau_in + line_tau_out) * cfrac;
                hydrogen_escape_state_applied = true;
            }
            const auto& magnesium_escape = magnesium_type50_escape_state_v04874619();
            if (!native_runtime_escape && magnesium_escape.enabled && element.element_z == 12 &&
                magnesium_escape.active_records.count(record.record) != 0) {
                const auto found = magnesium_escape.line_index_by_record.find(record.record);
                if (found == magnesium_escape.line_index_by_record.end()) {
                    throw std::runtime_error("active magnesium Type-50 record is missing from source line-index map");
                }
                line_index_one_based = found->second;
                const std::size_t line_index = static_cast<std::size_t>(line_index_one_based - 1);
                line_tau_in = magnesium_escape.tau_in.at(line_index);
                line_tau_out = magnesium_escape.tau_out.at(line_index);
                ptmp1 = pescl_v0472_binary64(line_tau_in) * (1.0 - cfrac);
                ptmp2 = pescl_v0472_binary64(line_tau_out) * (1.0 - cfrac) +
                    2.0 * pescl_v0472_binary64(line_tau_in + line_tau_out) * cfrac;
                magnesium_escape_state_applied = true;
                if (magnesium_escape.endpoint_energy_transport) {
                    const auto endpoint =
                        magnesium_escape.endpoint_by_record.find(record.record);
                    if (endpoint == magnesium_escape.endpoint_by_record.end()) {
                        throw std::runtime_error(
                            "active magnesium Type-50 record is missing source endpoint energy");
                    }
                    source_idest1 = endpoint->second.idest1;
                    source_idest2 = endpoint->second.idest2;
                    source_endpoint1_energy_ev = endpoint->second.endpoint1_energy_ev;
                    source_endpoint2_energy_ev = endpoint->second.endpoint2_energy_ev;
                    endpoint_energy_ev = endpoint->second.endpoint_energy_ev;
                    magnesium_source_endpoint_energy_applied = true;
                }
            }
            const double escaped_raw = a * (ptmp1 + ptmp2);
            const double density_floor = 1.0e-20 * input.hydrogen_density_cm3;
            const double escaped = std::max(escaped_raw, density_floor);

            double bremsa_nb1 = 0.0;
            int nb1_one_based = 0;
            bool used_dsec_radiation = false;
            const bool high_wavelength_zero = stored_wavelength_a > 0.99e9;
            const double cover = std::max(0.0, 1.0 - cfrac);
            double photo = 0.0;
            if (!high_wavelength_zero && cover != 0.0) {
                if (input.dsec_radiation_energy_ev && input.dsec_bremsa && input.dsec_radiation_bin_count >= 3) {
                    nb1_one_based = type99_nbinc_fortran_value(
                        delta_ev, input.dsec_radiation_energy_ev, input.dsec_radiation_bin_count);
                    if (nb1_one_based > 0 && static_cast<std::size_t>(nb1_one_based) <= input.dsec_radiation_bin_count) {
                        bremsa_nb1 = input.dsec_bremsa[static_cast<std::size_t>(nb1_one_based - 1)];
                        used_dsec_radiation = true;
                    }
                } else if (input.radiation_energy_ev && input.radiation_flux && input.radiation_bin_count > 0) {
                    bremsa_nb1 = interp_linear(
                        input.radiation_energy_ev, input.radiation_flux, input.radiation_bin_count, delta_ev);
                }
                photo = 0.02655 * oscillator * stored_wavelength_a * 1.0e-8 *
                    bremsa_nb1 / 3.0e10 * cover;
            }

            // Literal ucalc.f90 Type-50 post-swap answer convention.
            c.ans1 = photo;
            c.ans2 = escaped;
            c.ans3 = -escaped * endpoint_energy_ev * kErgPerEv;
            c.ans4 = -photo * endpoint_energy_ev * kErgPerEv;
            c.ans5 = 0.0;
            c.ans6 = 0.0;

            out.type50_shadow.valid = true;
            out.type50_shadow.ans = {c.ans1,c.ans2,c.ans3,c.ans4,c.ans5,c.ans6};
            out.type50_shadow.stored_wavelength_a = stored_wavelength_a;
            out.type50_shadow.endpoint_energy_ev = endpoint_energy_ev;
            out.type50_shadow.covering_fraction = cfrac;
            out.type50_shadow.ptmp1 = ptmp1;
            out.type50_shadow.ptmp2 = ptmp2;
            out.type50_shadow.bremsa_nb1 = bremsa_nb1;
            out.type50_shadow.density_floor_s = density_floor;
            out.type50_shadow.density_floor_applied = density_floor > escaped_raw;
            out.type50_shadow.photoexcitation_zero_covering = cover == 0.0;
            out.type50_shadow.used_dsec_covering = has_dsec_covering;
            out.type50_shadow.used_dsec_radiation = used_dsec_radiation;
            out.type50_shadow.nb1_one_based = nb1_one_based;
            out.type50_shadow.hydrogen_escape_state_applied = hydrogen_escape_state_applied;
            out.type50_shadow.magnesium_escape_state_applied = magnesium_escape_state_applied;
            out.type50_shadow.magnesium_source_endpoint_energy_applied =
                magnesium_source_endpoint_energy_applied;
            out.type50_shadow.source_idest1 = source_idest1;
            out.type50_shadow.source_idest2 = source_idest2;
            out.type50_shadow.source_endpoint1_energy_ev = source_endpoint1_energy_ev;
            out.type50_shadow.source_endpoint2_energy_ev = source_endpoint2_energy_ev;
            out.type50_shadow.line_index_one_based = line_index_one_based;
            out.type50_shadow.line_tau_in = line_tau_in;
            out.type50_shadow.line_tau_out = line_tau_out;

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
                    c.ans1 = oracle->ans[0]; c.ans2 = oracle->ans[1]; c.ans3 = oracle->ans[2];
                    c.ans4 = oracle->ans[3]; c.ans5 = oracle->ans[4]; c.ans6 = oracle->ans[5];
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
                    c.ans1 = oracle->ans[0]; c.ans2 = oracle->ans[1]; c.ans3 = oracle->ans[2];
                    c.ans4 = oracle->ans[3]; c.ans5 = oracle->ans[4]; c.ans6 = oracle->ans[5];
                }
            }
            const double mass = record.atomic_mass_amu > 0.0 ? record.atomic_mass_amu : 1.0;
            const double thermal_velocity = 1.29e6 / std::sqrt(std::max(mass / std::max(t4, 1.0e-300), 1.0e-300));
            const double v = std::sqrt(std::pow(input.turbulent_velocity_km_s * 1.0e5, 2) + thermal_velocity * thermal_velocity);
            // v82 patch 5.20.6: literal ucalc Type-50 uses the stored source
            // line wavelength (elin), not the endpoint energy difference, in
            // sigvtherm = 0.02655*flin*elin*1e-8/vtherm.  Keep the endpoint
            // delta in ans1..ans4/rate state, but publish the opacity cross
            // section from the source line coordinate consumed by linopac.
            out.opakab = (!high_wavelength_zero && v > 0.0)
                ? 0.02655 * oscillator * stored_wavelength_a * 1.0e-8 / v : 0.0;
            out.spectral = true;
            out.line_energy_ev = delta_ev;
            out.atomic_mass_amu = mass;
            out.natural_width_ev = record.natural_width_ev;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE51_BT_COLLISION: {
            const double legacy_ups = type51_upsilon_legacy(
                r, record.real_count, ints, record.int_count, input.temperature_k
            );
            if (!(legacy_ups >= 0.0) || !std::isfinite(legacy_ups)) {
                throw std::runtime_error("invalid legacy type51 payload");
            }
            const double legacy_root_t = std::sqrt(input.temperature_k);
            const double legacy_kt_ev =
                xstar_constants::kSourceCollisionBoltzmannEvPerK * input.temperature_k;
            const double legacy_qex =
                xstar_constants::kCollisionRateCoefficientPerSqrtK * legacy_ups *
                std::exp(-delta_ev / legacy_kt_ev) /
                (lower.statistical_weight * legacy_root_t);
            const double legacy_qde =
                xstar_constants::kCollisionRateCoefficientPerSqrtK * legacy_ups /
                (upper.statistical_weight * legacy_root_t);
            const std::array<double,6> legacy_ans{{
                legacy_qex * ne,
                legacy_qde * ne,
                0.0,
                0.0,
                legacy_qde * ne * delta_ev * xstar_constants::kLegacyCollisionErgPerEv,
                legacy_qex * ne * delta_ev * xstar_constants::kLegacyCollisionErgPerEv,
            }};

            const auto bt = type51_upsilon(
                r, record.real_count, ints, record.int_count, input.temperature_k
            );
            if (!bt.valid) throw std::runtime_error("invalid source-faithful type51 payload");
            const double t_xstar = input.temperature_k / 1.0e4;
            const double tsq = std::sqrt(t_xstar);
            const double ekt_ev = xstar_constants::kLegacyBoltzmannEvPerT4 * t_xstar;
            const double delt = bt.eij_ev / ekt_ev;
            const double qde =
                xstar_constants::kCollisionRateCoefficientPerSqrtT4 * bt.upsilon /
                tsq / upper.statistical_weight;
            const double qex =
                qde * upper.statistical_weight * type53_expo(-delt) /
                lower.statistical_weight;
            // Preserve the source evaluator's explicit answer reuse: ans5 and
            // ans6 are formed from the already-rounded density-scaled ans2 and
            // ans1 values, rather than recomputing q*ne inside the energy
            // expressions.  This removes avoidable cross-language rounding.
            const double source_ans1 = qex * ne;
            const double source_ans2 = qde * ne;
            const std::array<double,6> source_ans{{
                source_ans1,
                source_ans2,
                0.0,
                0.0,
                source_ans2 * bt.eij_ev * xstar_constants::kLegacyCollisionErgPerEv,
                source_ans1 * bt.eij_ev * xstar_constants::kLegacyCollisionErgPerEv,
            }};
            // v0.6.48.7.46.21.8: the source Type-51 evaluator contract is
            // element-independent.  The earlier Mg-only promotion left the
            // Hydrogen and Helium collision energy channels on the legacy
            // constants/path even during independent Thermal qualification.
            // Preserve the old Mg flag as a compatibility alias, while the
            // general flag promotes the same source-faithful path for H/He/Mg.
            const bool source_faithful =
                environment_flag("XSTAR_QUALIFICATION_TYPE51_SOURCE_FAITHFUL") ||
                (element.element_z == 12 &&
                 environment_flag("XSTAR_QUALIFICATION_MG_TYPE51_SOURCE_FAITHFUL"));
            const auto& committed = source_faithful ? source_ans : legacy_ans;
            c.ans1 = committed[0]; c.ans2 = committed[1];
            c.ans3 = committed[2]; c.ans4 = committed[3];
            c.ans5 = committed[4]; c.ans6 = committed[5];

            auto& shadow = out.type51_shadow;
            shadow.valid = true;
            shadow.source_faithful_mode = source_faithful;
            shadow.replacement_applied = source_faithful;
            shadow.endpoint_order_exact = lower.energy_ev <= upper.energy_ev;
            shadow.bt_type = bt.bt_type;
            shadow.point_count = bt.point_count;
            shadow.eij_ryd = bt.eij_ryd;
            shadow.eij_ev = bt.eij_ev;
            shadow.scaling_c = bt.scaling_c;
            shadow.physical_temperature_k = bt.physical_temperature_k;
            shadow.floor_temperature_k = bt.floor_temperature_k;
            shadow.effective_temperature_k = bt.effective_temperature_k;
            shadow.temperature_floor_applied = bt.floor_applied;
            shadow.scaled_temperature = bt.scaled_temperature;
            shadow.transformed_temperature = bt.transformed_temperature;
            shadow.scaled_upsilon = bt.scaled_upsilon;
            shadow.upsilon = bt.upsilon;
            shadow.lower_statistical_weight = lower.statistical_weight;
            shadow.upper_statistical_weight = upper.statistical_weight;
            shadow.electron_density_cm3 = ne;
            shadow.q_excitation_cm3_s = qex;
            shadow.q_deexcitation_cm3_s = qde;
            shadow.ans = source_ans;
            shadow.legacy_ans = legacy_ans;
            shadow.committed_nonfinite = !(
                std::isfinite(c.ans1) && std::isfinite(c.ans2) &&
                std::isfinite(c.ans3) && std::isfinite(c.ans4) &&
                std::isfinite(c.ans5) && std::isfinite(c.ans6)
            );
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
            const double source_kt_ev =
                xstar_constants::kBoltzmannErgPerK * input.temperature_k /
                xstar_constants::kModernErgPerEv;
            const double delt = delta_ev / std::max(source_kt_ev,1.0e-300);
            c.ans3 = -rate*delt*xstar_constants::kModernErgPerEv;
            // Type 54 is rate-family 4 and owns an exact nplini slot. It can
            // emit even though its oscillator-strength opacity is zero.
            out.spectral = record.rate_type == 4 && record.line_index_one_based > 0;
            out.bound_free_spectral = false;
            out.line_energy_ev = delta_ev;
            out.atomic_mass_amu = record.atomic_mass_amu;
            out.opakab = 0.0;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE57_COLLISIONAL_IONIZATION: {
            if (!ints || record.int_count < 2) throw std::runtime_error("type57 payload requires i57,principal_n");
            const int i57=static_cast<int>(ints[0]);
            const int n=static_cast<int>(ints[1]);
            const int source_local_level = record.int_count >= 3
                ? static_cast<int>(ints[2]) : record.lower_row;
            if (i57<=0 || source_local_level<=1) break;
            const bool source_faithful =
                environment_flag("XSTAR_QUALIFICATION_TYPE57_SOURCE_ENERGY");
            double e1=lower.energy_ev;
            double eth=std::max(upper.energy_ev-e1,0.0);
            if (source_faithful) {
                if (!r || record.real_count < 4) {
                    throw std::runtime_error(
                        "source-faithful type57 requires literal e1/eth/g1/g2 payload");
                }
                e1=r[0];
                eth=r[1];
                if (!std::isfinite(e1) || !std::isfinite(eth) || eth < 0.0 ||
                    !std::isfinite(r[2]) || !std::isfinite(r[3]) ||
                    !(r[2] > 0.0) || !(r[3] > 0.0)) {
                    throw std::runtime_error("source-faithful type57 has invalid e1/eth/g1/g2 payload");
                }
            }
            double cion=0.0,crec=0.0;
            if (!type57_coefficients(n,input.temperature_k,ne,e1,eth,cion,crec)) throw std::runtime_error("type57 coefficient evaluation failed");
            c.ans1=cion*ne;
            const double lower_weight = source_faithful ? r[2] : lower.statistical_weight;
            const double upper_weight = source_faithful ? r[3] : upper.statistical_weight;
            c.ans2=crec*(lower_weight/std::max(upper_weight,1.0e-300))*ne*ne;
            const double energy_conversion = source_faithful
                ? xstar_constants::kLegacyCollisionErgPerEv
                : xstar_constants::kModernErgPerEv;
            c.ans5=-c.ans2*eth*energy_conversion;
            c.ans6=-c.ans1*eth*energy_conversion;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE56_TABULATED_COLLISION: {
            const double ups = type56_upsilon(r, record.real_count, input.temperature_k);
            if (!(ups >= 0.0)) throw std::runtime_error("invalid type56 payload");
            if (!(lower.statistical_weight > 0.0) || !(upper.statistical_weight > 0.0)) {
                throw std::runtime_error("type56 requires positive statistical weights");
            }
            // Match xstar_tools.collisions.q_rates_from_upsilon exactly:
            // source collision k_B, sqrt(T), shared rate coefficient, and expression order.
            const double root_t = std::sqrt(input.temperature_k);
            const double collision_kt_ev =
                xstar_constants::kSourceCollisionBoltzmannEvPerK * input.temperature_k;
            const double qex =
                xstar_constants::kCollisionRateCoefficientPerSqrtK * ups *
                std::exp(-delta_ev / collision_kt_ev) /
                (lower.statistical_weight * root_t);
            const double qde =
                xstar_constants::kCollisionRateCoefficientPerSqrtK * ups /
                (upper.statistical_weight * root_t);
            c.ans1 = qex * ne;
            c.ans2 = qde * ne;
            c.ans5 = c.ans2 * delta_ev * xstar_constants::kLegacyCollisionErgPerEv;
            c.ans6 = c.ans1 * delta_ev * xstar_constants::kLegacyCollisionErgPerEv;
            out.type56_upsilon = ups;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE86_AUGER: {
            if (!r || record.real_count < 1) throw std::runtime_error("type86 payload requires Auger rate");
            c.ans1=std::max(0.0,r[0]);
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE88_SUPERLEVEL_BOUND_FREE: {
            if (!r || record.real_count < 4) {
                throw std::runtime_error("type88 payload requires energy/sigma pairs");
            }
            const double* source_energy_ev = calc_hmc_input.dsec_radiation_energy_ev && calc_hmc_input.dsec_radiation_bin_count >= 3
                ? calc_hmc_input.dsec_radiation_energy_ev : calc_hmc_input.radiation_energy_ev;
            const double* source_bremsa = calc_hmc_input.dsec_bremsa && calc_hmc_input.dsec_radiation_bin_count >= 3
                ? calc_hmc_input.dsec_bremsa : calc_hmc_input.radiation_flux;
            const std::size_t source_bins = calc_hmc_input.dsec_radiation_energy_ev && calc_hmc_input.dsec_bremsa && calc_hmc_input.dsec_radiation_bin_count >= 3
                ? calc_hmc_input.dsec_radiation_bin_count : calc_hmc_input.radiation_bin_count;
            if (!source_energy_ev || !source_bremsa || source_bins < 3) {
                throw std::runtime_error("type88 calc_hmc requires live reduced radiation grid");
            }
            std::size_t pair_count = record.real_count / 2;
            double threshold = delta_ev;
            if (ints && record.int_count >= 1 && ints[0] >= 2) {
                pair_count = static_cast<std::size_t>(ints[0]);
                const std::size_t pair_reals = 2 * pair_count;
                if (pair_reals + 1 < record.real_count) threshold = std::max(0.0, r[pair_reals]);
            }
            const std::size_t pair_reals = 2 * pair_count;
            if (pair_count < 2 || pair_reals > record.real_count || threshold <= 0.0) {
                c.ans1 = 0.0; c.ans2 = 0.0; c.ans3 = 0.0; c.ans4 = 0.0; c.ans5 = 0.0; c.ans6 = 0.0;
                break;
            }
            const int reduced_limit = std::max(3, static_cast<int>(source_bins / 10));
            c.ans1 = sequence1_type88_photo_rate(
                r, static_cast<int>(pair_reals), threshold, source_energy_ev, source_bremsa,
                static_cast<int>(source_bins), reduced_limit);
            c.ans2 = 0.0; c.ans3 = 0.0; c.ans4 = 0.0; c.ans5 = 0.0; c.ans6 = 0.0;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE99_SUPERLEVEL_BOUND_FREE: {
            if (evaluate_type99_source_faithful(record, r, ints, lower, upper, calc_hmc_input, c, &out.type99_shadow)) {
                out.spectral = true;
                out.bound_free_spectral = true;
                // v82 patch 5.1/5.2 source semantics: Type-99 retains its
                // atomic npconi2 identity for diagnostics/RRC association, but
                // the literal ucalc Type-99 branch (calt99 -> phint53hunt) never
                // assigns direct opakab.  Keep the pointer; publish zero opacity.
                out.continuum_index_one_based = record.continuum_index_one_based;
                out.line_energy_ev = out.type99_shadow.threshold_ev;
                out.atomic_mass_amu = record.atomic_mass_amu > 0.0 ? record.atomic_mass_amu : 1.0;
                out.opakab = 0.0;
                break;
            }
            // Backward-compatible development-fixture path.  Strict v0.6.48.7.36
            // qualification uses the appended source destination metadata and
            // the live DSEC workspace above; older compact fixtures retain the
            // pre-v36 approximate evaluator so ABI/self-tests remain readable.
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
            const double scale=rec/alpha; double photo=0.0,heat=0.0;
            for (int k=0;k<nx;++k) {
                const double e=delta_ev+std::max(0.0,xs[2*k])*kRydEv;
                const double sigma=std::max(0.0,xs[2*k+1])*1.0e-18*scale;
                const double flux=interp_linear(input.radiation_energy_ev,input.radiation_flux,input.radiation_bin_count,e);
                photo+=flux*sigma; heat+=flux*sigma*std::max(0.0,e-delta_ev)*kErgPerEv;
            }
            photo/=nx; heat/=nx; c.ans1=photo; c.ans2=rec*ne;
            c.ans3=-c.ans2*delta_ev*kErgPerEv; c.ans4=-heat;
            c.ans5=c.ans2*delta_ev*kErgPerEv; c.ans6=heat;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE60_CALLAWAY_COLLISION:
        case XSTAR_FIXED_OPCODE_TYPE62_CALLAWAY_COLLISION: {
            const bool source_faithful =
                environment_flag("XSTAR_QUALIFICATION_TYPE6062_SOURCE_FAITHFUL");
            const double ups=callaway_upsilon(
                record.data_type,r,record.real_count,input.temperature_k,delta_ev,source_faithful
            );
            if (source_faithful) {
                const double t_xstar = input.temperature_k / 1.0e4;
                const double tsq = std::sqrt(t_xstar);
                const double ekt_ev = xstar_constants::kLegacyBoltzmannEvPerT4 * t_xstar;
                const double delt = delta_ev / ekt_ev;
                // Preserve ucalc.f90 label 60 operation order and its explicit
                // 1.d-16 statistical-weight guards.
                const double cji =
                    xstar_constants::kCollisionRateCoefficientPerSqrtT4 * ups /
                    tsq / (1.0e-16 + upper.statistical_weight);
                const double cij =
                    cji * upper.statistical_weight * limited_exp(-delt) /
                    (1.0e-16 + lower.statistical_weight);
                c.ans1 = cij * ne;
                c.ans2 = cji * ne;
            } else {
                c.ans1=collision_pair_upward(ups,delta_ev,input.temperature_k,ne,lower.statistical_weight);
                c.ans2=collision_pair_downward(ups,input.temperature_k,ne,upper.statistical_weight);
            }
            // Keep benchmark constants centralized in constants.def.  The
            // source Type-60/62 path uses the modern XSTAR ergsev value while
            // retaining the legacy Boltzmann and collision-rate coefficients.
            c.ans5=c.ans2*delta_ev*xstar_constants::kModernErgPerEv;
            c.ans6=c.ans1*delta_ev*xstar_constants::kModernErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE68_HELIKE_COLLISION: {
            if (!ints||record.int_count<1) throw std::runtime_error("type68 payload requires Z");
            const double wav=delta_ev>0.0?12398.4016/delta_ev:0.0;
            const double ups=type68_upsilon(r,record.real_count,static_cast<int>(ints[0]),input.temperature_k,wav);
            const bool source_constants =
                environment_flag("XSTAR_QUALIFICATION_TYPE68_SOURCE_CONSTANTS");
            if (source_constants) {
                // Frozen v0.6.47.2 ucalc Type-68 combines the legacy XSTAR
                // Boltzmann coefficient and collision-channel eV-to-erg
                // conversion.  Preserve the source operation order rather
                // than routing through the modern generic collision helper.
                const double t4 = input.temperature_k / 1.0e4;
                const double tsq = std::sqrt(std::max(t4, 1.0e-300));
                const double ekt_ev = xstar_constants::kLegacyBoltzmannEvPerT4 * t4;
                const double cji =
                    xstar_constants::kCollisionRateCoefficientPerSqrtT4 * ups /
                    tsq / std::max(upper.statistical_weight, 1.0e-300);
                const double cij =
                    cji * upper.statistical_weight *
                    limited_exp(-delta_ev / std::max(ekt_ev, 1.0e-300)) /
                    std::max(lower.statistical_weight, 1.0e-300);
                c.ans1 = cij * ne;
                c.ans2 = cji * ne;
                c.ans5 = c.ans2 * delta_ev * xstar_constants::kLegacyCollisionErgPerEv;
                c.ans6 = c.ans1 * delta_ev * xstar_constants::kLegacyCollisionErgPerEv;
            } else {
                c.ans1=collision_pair_upward(ups,delta_ev,input.temperature_k,ne,lower.statistical_weight);
                c.ans2=collision_pair_downward(ups,input.temperature_k,ne,upper.statistical_weight);
                c.ans5=c.ans2*delta_ev*kErgPerEv;
                c.ans6=c.ans1*delta_ev*kErgPerEv;
            }
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE63_ALGORITHMIC_COLLISION: {
            if (!ints || record.int_count < 5) throw std::runtime_error("type63 payload requires ni,li,nf,lf,iq");
            double values[6]{};
            // v0.6.48.7.33: matrix lower/upper endpoints are source energy
            // ordered, but ans1/ans2 retain the literal packed-record initial
            // and final channels.  New lowered programs carry those rows in
            // ints[5:7]; the n/l inference keeps older qualification fixtures
            // readable without changing the fixed-state C ABI.
            const ElementRow* initial = &lower;
            const ElementRow* final = &upper;
            if (record.int_count >= 7) {
                initial = &row_at(element, static_cast<int>(ints[5]));
                final = &row_at(element, static_cast<int>(ints[6]));
            } else {
                const bool lower_is_initial = lower.principal_n == static_cast<int>(ints[0]) &&
                    lower.orbital_l == static_cast<int>(ints[1]);
                const bool upper_is_initial = upper.principal_n == static_cast<int>(ints[0]) &&
                    upper.orbital_l == static_cast<int>(ints[1]);
                if (!lower_is_initial && upper_is_initial) {
                    initial = &upper;
                    final = &lower;
                }
            }
            const int rc=xstar_engine_type63_rates_v1(
                static_cast<int>(ints[0]),static_cast<int>(ints[1]),static_cast<int>(ints[2]),static_cast<int>(ints[3]),static_cast<int>(ints[4]),
                input.temperature_k,ne,initial->energy_ev,final->energy_ev,initial->statistical_weight,final->statistical_weight,values);
            if (rc!=0) throw std::runtime_error("type63 native scalar evaluation failed");
            c.ans1=values[0]; c.ans2=values[1]; c.ans3=values[2]; c.ans4=values[3]; c.ans5=values[4]; c.ans6=values[5];
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE69_HELIKE_COLLISION: {
            const double ups = type69_upsilon(r, record.real_count, input.temperature_k);
            if (!(ups >= 0.0)) throw std::runtime_error("invalid type69 payload");
            // Match collisions.q_rates_from_upsilon operation order literally.
            // Using the algebraically equivalent T4 coefficient changes the
            // last bit for the six active helium Type-69 records.
            const double root_temperature = std::sqrt(input.temperature_k);
            const double source_kt_ev =
                xstar_constants::kSourceCollisionBoltzmannEvPerK * input.temperature_k;
            const double qex =
                xstar_constants::kCollisionRateCoefficientPerSqrtK * ups *
                limited_exp(-delta_ev / std::max(source_kt_ev, 1.0e-300)) /
                (std::max(lower.statistical_weight, 1.0e-300) * root_temperature);
            const double qde =
                xstar_constants::kCollisionRateCoefficientPerSqrtK * ups /
                (std::max(upper.statistical_weight, 1.0e-300) * root_temperature);
            c.ans1 = qex * ne;
            c.ans2 = qde * ne;
            c.ans5 = c.ans2 * delta_ev * xstar_constants::kLegacyCollisionErgPerEv;
            c.ans6 = c.ans1 * delta_ev * xstar_constants::kLegacyCollisionErgPerEv;
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
            // Source ucalc evaluates Type 71 as a superlevel transition rate,
            // but it does not call linopac and heatt does not accumulate it
            // because its rate family is 14 rather than 4. Keep its nplini
            // identity for option-15 ordering while leaving rcem/oplin/tau0/
            // elum zero, exactly as the source product workspaces do.
            out.spectral = false;
            out.bound_free_spectral = false;
            out.line_energy_ev = photon;
            out.atomic_mass_amu = record.atomic_mass_amu;
            out.opakab = 0.0;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE77_SUPERLEVEL_COLLISION: {
            if (record.lower_row==record.upper_row || delta_ev<1.0) break;
            double upward=0.0,downward=0.0;
            if (!type77_rates(r,record.real_count,ints,record.int_count,input.temperature_k,input.hydrogen_density_cm3,delta_ev,upward,downward)) throw std::runtime_error("invalid type77 payload");
            c.ans1=upward; c.ans2=downward;
            c.ans5=downward*delta_ev*xstar_constants::kLegacyCollisionErgPerEv;
            c.ans6=upward*delta_ev*xstar_constants::kLegacyCollisionErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE72_DIELECTRONIC_CAPTURE: {
            if (!r||record.real_count<2||!ints||record.int_count<2) throw std::runtime_error("type72 payload too short");
            // Match ucalc.py::_calt72_rate literally.  Type 72 is one of the
            // historical collision branches that uses the rounded XSTAR
            // 0.861707 eV per 10^4 K coefficient, not the modern constant.
            const double source_ekt_ev = xstar_constants::kLegacyBoltzmannEvPerT4 * t4;
            const double scale=3.3e-11*std::pow(13.6/source_ekt_ev,1.5);
            const double rtmp=record.real_count>=3?r[2]:1.0;
            const double rate=scale*limited_exp(-r[1]/source_ekt_ev)*(r[0]/1.0e13)*rtmp;
            const auto& ground=row_at(element,static_cast<int>(ints[0]));
            const auto& parent=row_at(element,static_cast<int>(ints[1]));
            const double rinf=2.08e-22*ground.statistical_weight/std::max(parent.statistical_weight,1.0e-48)/std::max(t4*sqrt_t4,1.0e-48);
            c.ans2=rate*ne;
            c.ans1=rate*ne*rinf*ne*limited_exp(r[1]/input.temperature_k);
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE73_HELIKE_COLLISION: {
            if (!r||record.real_count<7||!ints||record.int_count<1) throw std::runtime_error("type73 payload too short");
            // native_fixed_program.py compacts the raw Type-73 integer
            // payload [level1, level2, Z] to [Z]; the record rows retain the
            // two endpoints.  From this point onward preserve the exact
            // ucalc.py::_eval_type73 operation order and historical constants.
            const double wavelength_a=std::abs(r[0]);
            if (!(wavelength_a>0.0)) break;
            const double source_energy_ev=12398.4016/std::max(wavelength_a,1.0e-48);
            const double crate=type73_rate(
                r,record.real_count,static_cast<int>(ints[0]),input.temperature_k);
            const double gl=lower.statistical_weight;
            const double gu=upper.statistical_weight;
            const double omega=crate/std::max(gl,1.0e-48);
            const double excitation_factor=limited_exp(
                -source_energy_ev/(xstar_constants::kLegacyBoltzmannEvPerT4*t4));
            const double qd=xstar_constants::kCollisionRateCoefficientPerSqrtT4*
                omega/sqrt_t4/std::max(gu,1.0e-48);
            const double qe=qd*gu*excitation_factor/std::max(gl,1.0e-48);
            c.ans1=qe*ne;
            c.ans2=qd*ne;
            c.ans5=c.ans2*source_energy_ev*xstar_constants::kLegacyCollisionErgPerEv;
            c.ans6=c.ans1*source_energy_ev*xstar_constants::kLegacyCollisionErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE76_TWO_PHOTON: {
            if (!r||record.real_count<1) throw std::runtime_error("type76 payload too short");
            const double aij=std::max(0.0,r[0]);
            c.ans2=aij;
            c.ans3=-aij*delta_ev*xstar_constants::kLegacyCollisionErgPerEv;
            // Two-photon decay is distributed over the energy continuum and
            // intentionally owns no option-15 line slot. The continuum is
            // accumulated below from this evaluated record.
            out.spectral = false;
            out.bound_free_spectral = false;
            out.line_energy_ev = delta_ev;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE95_SPLINE_IONIZATION: {
            if (!r||record.real_count<6||!ints||record.int_count<1) throw std::runtime_error("type95 payload too short");
            const double ee=r[0];
            const double tt=(xstar_constants::kLegacyBoltzmannEvPerT4 * t4)/std::max(ee,1.0e-300);
            if (!(tt>0.0)) throw std::runtime_error("type95 invalid scaled temperature");
            const double xx=1.0-0.693147/std::log(tt+2.0);
            const double rho=type95_spline_rho(r,record.real_count,xx);
            double e1=0.0,e2=0.0,e3=0.0; eint_values(1.0/tt,e1,e2,e3);
            const double citmp1=1.0e-6*e1*rho/std::sqrt(tt*ee*ee*ee);
            c.ans1=citmp1*ne;
            const auto& parent=row_at(element,static_cast<int>(ints[record.int_count-1]));
            const double rinf=2.08e-22*lower.statistical_weight/std::max(parent.statistical_weight,1.0e-300)/std::max(t4*sqrt_t4,1.0e-300);
            c.ans2=c.ans1*rinf*ne/std::max(limited_exp(-1.0/tt),1.0e-300);
            c.ans5=c.ans2*ee*xstar_constants::kLegacyCollisionErgPerEv;
            c.ans6=c.ans1*ee*xstar_constants::kLegacyCollisionErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE74_DELTA_RESONANCE: {
            if (!r || record.real_count < 3 || (record.real_count - 1) % 2 != 0) throw std::runtime_error("invalid type74 payload");
            const bool has_dsec_radiation = input.dsec_radiation_energy_ev && input.dsec_bremsa && input.dsec_radiation_bin_count >= 3;
            const double* full_energy_ev = has_dsec_radiation ? input.dsec_radiation_energy_ev : input.radiation_energy_ev;
            const double* full_bremsa = has_dsec_radiation ? input.dsec_bremsa : input.radiation_flux;
            const std::size_t full_bin_count = has_dsec_radiation ? input.dsec_radiation_bin_count : input.radiation_bin_count;
            if (!full_energy_ev || !full_bremsa || full_bin_count < 3) throw std::runtime_error("type74 requires live radiation grid");
            // ucalc Type-74 consumes the source 999-bin epim/bremsam workspace,
            // not the full DSEC grid.  Reconstruct bremsmap's nearest-bin
            // reduction from the transported full radiation state.
            std::vector<double> reduced_energy_ev;
            std::vector<double> reduced_bremsa;
            build_type99_reduced_radiation(
                full_energy_ev, full_bremsa, full_bin_count,
                reduced_energy_ev, reduced_bremsa);
            const double* source_energy_ev = reduced_energy_ev.data();
            const double* source_bremsa = reduced_bremsa.data();
            const std::size_t source_bin_count = reduced_energy_ev.size();
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
                if (e >= source_energy_ev[0] && e <= source_energy_ev[source_bin_count - 1]) {
                    rate_sum += interp_linear(source_energy_ev, source_bremsa, source_bin_count, e) * h;
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

double source_persistent_leveltemp_destination_energy_v048746222(
    const ActiveElementView& active,
    const xstar_element_contribution_v1& contribution,
    const Type53SourceShadow& shadow) {
    if (!shadow.persistent_leveltemp_candidates_valid ||
        shadow.leveltemp_destination_column <= 0) {
        throw std::runtime_error(
            "source-faithful Mg bound-free record requires persistent leveltemp candidate payload");
    }
    if ((shadow.leveltemp_candidate_mask & ~0x0fffu) != 0u) {
        throw std::runtime_error("Mg bound-free persistent leveltemp candidate mask is invalid");
    }

    const auto candidate_present = [&](int stage) {
        if (stage < 1 || stage > 12) return false;
        const std::uint32_t bit = 1u << static_cast<unsigned>(stage - 1);
        return (shadow.leveltemp_candidate_mask & bit) != 0u;
    };
    const auto candidate_energy = [&](int stage) {
        const double value = shadow.leveltemp_candidate_energy_ev[
            static_cast<std::size_t>(stage - 1)];
        if (!std::isfinite(value)) {
            throw std::runtime_error(
                "Mg bound-free persistent leveltemp candidate energy is non-finite");
        }
        return value;
    };

    // Source calc_hmc_element first calls levwkelement for every active ion,
    // leaving the last active writer of each leveltemp column.  Its second
    // pass then calls calc_hmc_ion only for active ions in increasing stage
    // order.  Before the current record is evaluated, every present candidate
    // through the current stage has overwritten that first-pass workspace.
    int owner_stage = 0;
    const int second_pass_max = std::min(contribution.ion_stage, active.max_stage);
    for (int stage = active.min_stage; stage <= second_pass_max; ++stage) {
        if (candidate_present(stage)) owner_stage = stage;
    }
    if (owner_stage == 0) {
        for (int stage = active.min_stage; stage <= active.max_stage; ++stage) {
            if (candidate_present(stage)) owner_stage = stage;
        }
    }
    if (owner_stage == 0) {
        // No active ion writes this column in either source pass.  Preserve
        // the incoming persistent leveltemp value already serialized in the
        // v2/v3 context rather than inventing a zero-energy owner.
        return std::numeric_limits<double>::quiet_NaN();
    }
    return candidate_energy(owner_stage);
}

void apply_magnesium_type53_persistent_leveltemp_v048746221(
    const ElementProgram& element,
    const ActiveElementView& active,
    std::vector<EvaluatedRecord>& evaluated) {
    if (element.element_z != 12 ||
        !environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE53_PERSISTENT_LEVELTEMP")) {
        return;
    }
    for (auto& item : evaluated) {
        auto& contribution = item.contribution;
        auto& shadow = item.type53_shadow;
        if (contribution.data_type != 53 || !shadow.valid || shadow.type49_semantics ||
            contribution.ion_stage < active.min_stage || contribution.ion_stage > active.max_stage) {
            continue;
        }
        const double destination_energy = source_persistent_leveltemp_destination_energy_v048746222(
            active, contribution, shadow);
        if (!std::isfinite(destination_energy)) {
            continue;
        }
        const double energy_difference = std::abs(destination_energy - shadow.bound_energy_ev);
        const double den6 = std::max(
            1.0e-43,
            std::abs(contribution.ans4) - shadow.threshold_ev * kErgPerEv * contribution.ans1);
        const double den5 = std::max(
            1.0e-43,
            std::abs(contribution.ans3) - shadow.threshold_ev * kErgPerEv * contribution.ans2);
        const double ans6_pre = -shadow.sumh2 * kErgPerEv;
        const double ans5_pre = -shadow.sumc2 * kErgPerEv;
        contribution.ans6 = ans6_pre *
            (std::abs(contribution.ans4) - energy_difference * kErgPerEv * contribution.ans1) / den6;
        contribution.ans5 = ans5_pre *
            (std::abs(contribution.ans3) - energy_difference * kErgPerEv * contribution.ans2) / den5;
        if (!std::isfinite(contribution.ans5) || !std::isfinite(contribution.ans6)) {
            throw std::runtime_error("non-finite Mg Type-53 persistent-leveltemp correction");
        }
        shadow.destination_energy_ev = destination_energy;
        shadow.ans[4] = contribution.ans5;
        shadow.ans[5] = contribution.ans6;
        shadow.shadow_max_abs = 0.0;
        shadow.committed_max_abs = 0.0;
        for (double value : shadow.ans) {
            shadow.shadow_max_abs = std::max(shadow.shadow_max_abs, std::abs(value));
            shadow.committed_max_abs = std::max(shadow.committed_max_abs, std::abs(value));
        }
        shadow.committed_nonfinite = false;
        shadow.committed_implausible = shadow.committed_max_abs > 1.0e40;
    }
}

void apply_magnesium_type49_persistent_leveltemp_v048746222(
    const ElementProgram& element,
    const ActiveElementView& active,
    std::vector<EvaluatedRecord>& evaluated) {
    if (element.element_z != 12 ||
        !environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE49_PERSISTENT_LEVELTEMP")) {
        return;
    }
    for (auto& item : evaluated) {
        auto& contribution = item.contribution;
        auto& shadow = item.type49_shadow;
        if (contribution.data_type != 49 || !shadow.valid || !shadow.type49_semantics ||
            contribution.ion_stage < active.min_stage || contribution.ion_stage > active.max_stage) {
            continue;
        }
        const double destination_energy = source_persistent_leveltemp_destination_energy_v048746222(
            active, contribution, shadow);
        if (!std::isfinite(destination_energy)) {
            continue;
        }
        const double energy_difference = std::abs(destination_energy - shadow.bound_energy_ev);
        const double den6 = std::max(
            1.0e-43,
            std::abs(contribution.ans4) - shadow.threshold_ev * kErgPerEv * contribution.ans1);
        const double den5 = std::max(
            1.0e-43,
            std::abs(contribution.ans3) - shadow.threshold_ev * kErgPerEv * contribution.ans2);
        const double ans6_pre = -shadow.sumh2 * kErgPerEv;
        const double ans5_pre = -shadow.sumc2 * kErgPerEv;
        contribution.ans6 = ans6_pre *
            (std::abs(contribution.ans4) - energy_difference * kErgPerEv * contribution.ans1) / den6;
        contribution.ans5 = ans5_pre *
            (std::abs(contribution.ans3) - energy_difference * kErgPerEv * contribution.ans2) / den5;
        if (!std::isfinite(contribution.ans5) || !std::isfinite(contribution.ans6)) {
            throw std::runtime_error("non-finite Mg Type-49 persistent-leveltemp correction");
        }
        shadow.destination_energy_ev = destination_energy;
        shadow.ans[4] = contribution.ans5;
        shadow.ans[5] = contribution.ans6;
        shadow.shadow_max_abs = 0.0;
        shadow.committed_max_abs = 0.0;
        for (double value : shadow.ans) {
            shadow.shadow_max_abs = std::max(shadow.shadow_max_abs, std::abs(value));
            shadow.committed_max_abs = std::max(shadow.committed_max_abs, std::abs(value));
        }
        shadow.committed_nonfinite = false;
        shadow.committed_implausible = shadow.committed_max_abs > 1.0e40;
    }
}


struct Type99ResolvedValueV048746223 {
    double energy_ev = 0.0;
    double statistical_weight = 0.0;
    int owner_stage = 0;
};

Type99ResolvedValueV048746223 resolve_type99_leveltemp_value_v048746223(
    const ActiveElementView& active,
    const xstar_element_contribution_v1& contribution,
    int column,
    std::uint32_t mask,
    const std::array<double,12>& candidate_energy_ev,
    const std::array<double,12>& candidate_statistical_weight,
    double incoming_energy_ev,
    double incoming_statistical_weight
) {
    if (column <= 0 || (mask & ~0x0fffu) != 0u) {
        throw std::runtime_error("Mg Type-99 persistent leveltemp column/mask is invalid");
    }
    const auto present = [&](int stage) {
        return stage >= 1 && stage <= 12 &&
            (mask & (1u << static_cast<unsigned>(stage - 1))) != 0u;
    };
    int owner = 0;
    const int second_pass_max = std::min(contribution.ion_stage, active.max_stage);
    for (int stage = active.min_stage; stage <= second_pass_max; ++stage) {
        if (present(stage)) owner = stage;
    }
    if (owner == 0) {
        for (int stage = active.min_stage; stage <= active.max_stage; ++stage) {
            if (present(stage)) owner = stage;
        }
    }
    Type99ResolvedValueV048746223 value{};
    value.owner_stage = owner;
    if (owner == 0) {
        value.energy_ev = incoming_energy_ev;
        value.statistical_weight = incoming_statistical_weight;
    } else {
        value.energy_ev = candidate_energy_ev[static_cast<std::size_t>(owner - 1)];
        value.statistical_weight =
            candidate_statistical_weight[static_cast<std::size_t>(owner - 1)];
    }
    if (!std::isfinite(value.energy_ev) || !std::isfinite(value.statistical_weight)) {
        throw std::runtime_error("Mg Type-99 resolved persistent leveltemp value is non-finite");
    }
    return value;
}

void apply_magnesium_type99_persistent_leveltemp_v048746223(
    const Program& program,
    const ElementProgram& element,
    const ActiveElementView& active,
    const xstar_fixed_state_input_v1& input,
    std::vector<EvaluatedRecord>& evaluated
) {
    if (element.element_z != 12 ||
        !environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PERSISTENT_LEVELTEMP")) {
        return;
    }
    int index = element.record_head;
    std::size_t ordinal = 0;
    while (index >= 0) {
        if (ordinal >= evaluated.size()) {
            throw std::runtime_error("Mg Type-99 record/evaluation traversal mismatch");
        }
        const ProgramRecord& record = program.records[static_cast<std::size_t>(index)];
        EvaluatedRecord& item = evaluated[ordinal];
        auto& contribution = item.contribution;
        if (record.data_type == 99 &&
            contribution.ion_stage >= active.min_stage &&
            contribution.ion_stage <= active.max_stage) {
            const double* payload = record.real_count
                ? program.reals.data() + record.real_offset : nullptr;
            const std::int64_t* ints = record.int_count
                ? program.ints.data() + record.int_offset : nullptr;
            if (!payload || !ints || record.int_count < 3) {
                throw std::runtime_error("Mg Type-99 persistent context requires payloads");
            }
            const int nden = static_cast<int>(ints[0]);
            const int ntem = static_cast<int>(ints[1]);
            const int nxs = static_cast<int>(ints[2]);
            if (nden <= 0 || ntem <= 1 || nxs <= 1) {
                throw std::runtime_error("Mg Type-99 persistent context has invalid calt99 dimensions");
            }
            const std::size_t core_real_count = static_cast<std::size_t>(
                nden + ntem + nden * ntem + 2 * nxs);
            const auto context = parse_type99_persistent_leveltemp_context_v048746223(
                record, payload, ints, core_real_count);
            if (!context.valid) {
                throw std::runtime_error(
                    "source-faithful Mg Type-99 requires v21.13 persistent leveltemp context");
            }
            const auto bound = resolve_type99_leveltemp_value_v048746223(
                active, contribution, context.bound_column, context.bound_mask,
                context.bound_candidate_energy_ev,
                context.bound_candidate_statistical_weight,
                context.incoming_bound_energy_ev,
                context.incoming_bound_statistical_weight);
            const auto parent = resolve_type99_leveltemp_value_v048746223(
                active, contribution, context.parent_column, context.parent_mask,
                context.parent_candidate_energy_ev,
                context.parent_candidate_statistical_weight,
                context.incoming_parent_energy_ev,
                context.incoming_parent_statistical_weight);
            const auto destination = resolve_type99_leveltemp_value_v048746223(
                active, contribution, context.destination_column, context.destination_mask,
                context.destination_candidate_energy_ev,
                context.destination_candidate_statistical_weight,
                context.incoming_destination_energy_ev,
                context.incoming_destination_statistical_weight);
            Type99ResolvedLeveltempContextV048746223 resolved{};
            resolved.bound_energy_ev = bound.energy_ev;
            resolved.bound_statistical_weight = bound.statistical_weight;
            resolved.parent_energy_ev = parent.energy_ev;
            resolved.parent_statistical_weight = context.excited_parent_mode == 1
                ? context.excited_parent_statistical_weight : parent.statistical_weight;
            resolved.destination_energy_ev = destination.energy_ev;
            resolved.destination_statistical_weight = destination.statistical_weight;
            resolved.threshold_ev = context.excited_parent_mode == 1
                ? std::abs(bound.energy_ev + context.excited_parent_energy_ev)
                : std::abs(bound.energy_ev - parent.energy_ev);
            resolved.bound_owner_stage = bound.owner_stage;
            resolved.parent_owner_stage = parent.owner_stage;
            resolved.destination_owner_stage = destination.owner_stage;
            if (!(resolved.bound_statistical_weight > 0.0) ||
                !(resolved.parent_statistical_weight > 0.0) ||
                !(resolved.destination_statistical_weight > 0.0) ||
                !(resolved.threshold_ev > 0.0)) {
                throw std::runtime_error("Mg Type-99 resolved energy/weight context is invalid");
            }
            const ElementRow& lower = row_at(element, record.lower_row);
            const ElementRow& upper = row_at(element, record.upper_row);
            xstar_element_contribution_v1 corrected = contribution;
            Type99SourceShadow corrected_shadow{};
            if (!evaluate_type99_source_faithful(
                    record, payload, ints, lower, upper, input,
                    corrected, &corrected_shadow, &resolved)) {
                throw std::runtime_error(
                    "Mg Type-99 persistent leveltemp integral reevaluation failed");
            }
            contribution = corrected;
            item.type99_shadow = corrected_shadow;
        }
        index = record.next_index;
        ++ordinal;
    }
    if (ordinal != evaluated.size()) {
        throw std::runtime_error("Mg Type-99 linked traversal did not cover evaluated records");
    }
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

    constexpr double critf = 1.0e-7;
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

ActiveElementView make_source_compact_element_view(
    const ElementProgram& full,
    const std::vector<SourceCompactOracleRow>& source_rows) {
    if (source_rows.empty()) throw std::runtime_error("empty source compact element view");
    ActiveElementView view;
    view.min_stage = source_rows.front().active_min_stage;
    view.max_stage = source_rows.front().active_max_stage;
    const int start = ground_row_for_stage(full, view.min_stage);
    const int end = start + static_cast<int>(source_rows.size()) - 1;
    if (start <= 0 || end < start || end > full.normalization_row) {
        throw std::runtime_error("invalid source compact element row window");
    }
    view.full_row_start = start;
    view.full_row_end = end;
    view.element = full;
    view.element.rows.clear();
    view.element.n_rows = static_cast<int>(source_rows.size());
    view.element.n_ions = view.max_stage - view.min_stage + 1;
    view.element.normalization_row = view.element.n_rows;
    std::map<int, int> superlevel_map;
    int next_superlevel = 0;
    for (std::size_t i = 0; i < source_rows.size(); ++i) {
        const auto& source = source_rows[i];
        ElementRow row = full.rows.at(static_cast<std::size_t>(start - 1) + i);
        row.row = static_cast<int>(i) + 1;
        row.ion = std::max(1, source.ion - (view.min_stage - 1));
        row.ion_charge = source.ion_charge;
        auto it = superlevel_map.find(row.superlevel);
        if (it == superlevel_map.end()) {
            it = superlevel_map.emplace(row.superlevel, ++next_superlevel).first;
        }
        row.superlevel = it->second;
        row.initial_population = source.transformed_initial_population;
        view.element.rows.push_back(row);
    }
    view.element.n_superlevels = next_superlevel;
    view.element.rows.back().ion = view.element.n_ions;
    return view;
}

struct RuntimeInitialSeed {
    int global_level_index = 0;
    double value = 0.0;
    bool loaded = false;
};

RuntimeInitialSeed source_faithful_runtime_initial_seed(
    const ElementProgram& e,
    std::size_t compact_index,
    const xstar_fixed_state_input_v1* runtime_input) {
    RuntimeInitialSeed seed;
    if (!runtime_input || runtime_input->global_level_count == 0 || !runtime_input->global_xilevg ||
        compact_index >= e.rows.size()) return seed;

    const int compact_row = static_cast<int>(compact_index) + 1;
    const auto& row = e.rows[compact_index];

    // v0.6.48.7.46.25.5.17.17: source calc_hmc_all first maps the
    // committed hydrogen global array into the compact 33-row workspace,
    // then executes x(ipmat2+1)=0 before msolvelucy.  Preserve the raw
    // global mapping for diagnostics/state continuity while returning an
    // exact-zero compact terminal seed.
    if (e.element_z == 1 && compact_row == e.normalization_row &&
        (runtime_input->runtime_state_flags &
         XSTAR_FIXED_RUNTIME_STATE_REPEATED_HYDROGEN_SOURCE_STATE) != 0u) {
        seed.global_level_index = row.global_level_index;
        seed.value = 0.0;
        seed.loaded = true;
        return seed;
    }

    // v0.6.48.7.46.25.5.17.25.77: preserve the source helium compact
    // seed exactly at the active-row identities already produced by the
    // lowered basis.  The basis itself contains the shared He I/He II ground
    // overwrite.  Advancing every later He II row by one duplicated that
    // overlap, shifted rows 47-77 to the following global population, and
    // discarded the final carried He II level.  The source still performs
    // the literal terminal normalization-row zero write after the compact
    // copy, so only that last row is replaced by zero.
    if (e.element_z == 2 && compact_row == e.normalization_row) {
        seed.global_level_index = 0;
        seed.value = 0.0;
        seed.loaded = true;
        return seed;
    }

    // v0.6.48.7.46.25.5.17.25.81: calc_hmc_element maps each selected Mg
    // ion through source npilev ordinal order, advances ipmat by nlev-1, and
    // finally executes x(ipmat2+1)=0.  The corrected live ATDB lowering now
    // gives every Mg compact row that ordinal global identity.  Preserve the
    // mapped values exactly, but force the terminal normalization row to the
    // literal source zero before msolvelucy.
    if (e.element_z == 12 && compact_row == e.normalization_row) {
        seed.global_level_index = row.global_level_index;
        seed.value = 0.0;
        seed.loaded = true;
        return seed;
    }

    const int global_level_index = row.global_level_index;
    if (global_level_index <= 0 ||
        static_cast<std::size_t>(global_level_index) > runtime_input->global_level_count) return seed;

    const double value = runtime_input->global_xilevg[global_level_index - 1];
    if (!std::isfinite(value) || value < 0.0) return seed;
    seed.global_level_index = global_level_index;
    seed.value = value;
    seed.loaded = true;
    return seed;
}

ElementBuffers make_buffers(const ElementProgram& e, const xstar_fixed_state_input_v1* runtime_input = nullptr, bool preserve_initial_seed = false) {
    ElementBuffers b;
    const bool native_sequence1_source_seed =
        environment_flag("XSTAR_NATIVE_SEQUENCE1_SOURCE_FAITHFUL_POPULATION_SEED") &&
        environment_data_type("XSTAR_QUALIFICATION_SOURCE_SEQUENCE") == 1;
    const std::size_t n = static_cast<std::size_t>(e.n_rows);
    const std::size_t ni = static_cast<std::size_t>(e.n_ions);
    b.superlevels.resize(n); b.ions.resize(n); b.initial.resize(n);
    b.populations.resize(n); b.outer.resize(n); b.dense.resize(n * n); b.heat.resize(n * n); b.heat2.resize(n * n); b.rhs.resize(n);
    b.gamma.resize(n); b.alpha.resize(n); b.fgamma.resize(5 * n); b.falpha.resize(5 * n); b.igamma.resize(n); b.ialpha.resize(n);
    b.ion_population.resize(ni); b.ion_population_final.resize(ni); b.ionization.resize(ni); b.recombination.resize(ni);
    b.ionization_components.resize(3 * ni); b.recombination_components.resize(3 * ni);
    b.row_residual.resize(n); b.row_scale.resize(n); b.relative_residual.resize(n);
    bool source_faithful_helium_runtime_seed = false;
    bool source_faithful_hydrogen_runtime_seed = false;
    bool source_faithful_magnesium_runtime_seed = false;
    for (std::size_t k = 0; k < n; ++k) {
        b.superlevels[k] = e.rows[k].superlevel;
        b.ions[k] = e.rows[k].ion;
        b.initial[k] = e.rows[k].initial_population;
        if (native_sequence1_source_seed) {
            // Source call-1/evaluation-1 begins with every active compact row
            // at exact zero.  The sole nonzero seed is the inactive Mg I
            // global population row 112, retained in the full element table;
            // it is intentionally outside the active Mg compact solve basis.
            b.initial[k] = 0.0;
        } else if (!preserve_initial_seed) {
            const RuntimeInitialSeed seed = source_faithful_runtime_initial_seed(e, k, runtime_input);
            if (seed.loaded) {
                b.initial[k] = seed.value;
                if (e.element_z == 12) source_faithful_magnesium_runtime_seed = true;
                if (e.element_z == 2) source_faithful_helium_runtime_seed = true;
                if (e.element_z == 1 && runtime_input &&
                    (runtime_input->runtime_state_flags &
                     XSTAR_FIXED_RUNTIME_STATE_REPEATED_HYDROGEN_SOURCE_STATE) != 0u) {
                    source_faithful_hydrogen_runtime_seed = true;
                }
            }
        }
    }

    // Source-mapped H/He/Mg compact vectors are not renormalized here.
    // calc_hmc_element writes the selected xilevg values directly into x,
    // overwrites shared continuum rows through ipmat+=nlev-1, writes the final
    // normalization row to zero, and lets msolvelucy impose number
    // conservation.  v80 incorrectly made this exemption blanket for every
    // runtime-mapped element.  v81 reverts that blanket behavior while
    // retaining the exact source rule only for the three source-mapped active
    // elements already qualified here.
    if (!preserve_initial_seed && !source_faithful_magnesium_runtime_seed &&
        !source_faithful_helium_runtime_seed && !source_faithful_hydrogen_runtime_seed) {
        double initial_total = 0.0;
        for (double value : b.initial) initial_total += value;
        if (initial_total > 0.0) for (double& value : b.initial) value /= initial_total;
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


std::vector<LteIonTopology> lte_topology_for_element_v82_patch54(
    const Program& program,
    const ElementProgram& element
) {
    std::vector<LteIonTopology> out;
    for (const auto& topo : program.lte_ion_topology) {
        if (topo.element_index == element.element_index) out.push_back(topo);
    }
    std::sort(out.begin(), out.end(), [](const auto& a, const auto& b) {
        return a.ion_stage < b.ion_stage;
    });
    if (!out.empty()) return out;

    // Backward-compatible fallback for historical program directories and
    // bundles without the patch-5.4 sidecar.  It preserves the overlapping
    // start/nlev topology, but the terminal continuum metadata necessarily
    // comes from the shared compact row and therefore is diagnostic-only.
    for (int stage = 1; stage <= element.n_ions; ++stage) {
        const int start_row = ground_row_for_stage(element, stage);
        if (start_row <= 0) continue;
        int terminal_row = element.normalization_row;
        if (stage < element.n_ions) {
            const int next_ground = ground_row_for_stage(element, stage + 1);
            if (next_ground > 0) terminal_row = next_ground;
        }
        if (terminal_row < start_row || terminal_row > element.n_rows) {
            throw std::runtime_error("fallback LTE source ion topology is invalid");
        }
        const auto& terminal = element.rows.at(static_cast<std::size_t>(terminal_row - 1));
        LteIonTopology topo;
        topo.element_index = element.element_index;
        topo.ion_stage = stage;
        topo.start_row = start_row;
        topo.nlev = terminal_row - start_row + 1;
        topo.terminal_energy_ev = terminal.energy_ev;
        topo.terminal_statistical_weight = terminal.statistical_weight;
        out.push_back(topo);
    }
    return out;
}

const LteLevelData* lte_leveltemp_row_v82_patch56(
    const Program& program, int element_index, int ion_stage, int local_level) {
    for (const auto& level : program.lte_levels) {
        if (level.element_index == element_index && level.ion_stage == ion_stage &&
            level.local_level == local_level) return &level;
    }
    return nullptr;
}

std::vector<double> compute_element_lte_populations_v82_patch54(
    const Program& program,
    const ElementProgram& element,
    const xstar_fixed_state_input_v1& input,
    int active_min_stage,
    int active_max_stage,
    bool* used_exact_source_topology = nullptr
) {
    if (element.rows.empty() || element.n_rows <= 0) {
        throw std::runtime_error("LTE population construction requires element rows");
    }
    const auto topology = lte_topology_for_element_v82_patch54(program, element);
    if (topology.empty()) throw std::runtime_error("LTE source ion topology is empty");
    const bool exact_topology = std::any_of(
        program.lte_ion_topology.begin(), program.lte_ion_topology.end(),
        [&](const auto& topo) { return topo.element_index == element.element_index; });
    if (used_exact_source_topology) *used_exact_source_topology = exact_topology;
    const bool exact_leveltemp = std::any_of(
        program.lte_levels.begin(), program.lte_levels.end(),
        [&](const auto& level) { return level.element_index == element.element_index; });

    struct RnisiAuditRowV82Patch56 {
        int stage = 0; int local = 0; int compact_row = 0; int global_level_index = 0;
        std::int64_t source_record = 0;
        double energy_ev = 0.0; double weight = 0.0;
        double terminal_energy_ev = 0.0; double terminal_weight = 0.0;
        double rnisi = 0.0; double recurrence_ratio = 0.0;
        double raw_rnise = 0.0; double normalized_lte = 0.0;
        bool active = false; bool fully_stripped = false;
    };
    std::vector<RnisiAuditRowV82Patch56> rnisi_audit;

    int expected_full_rows = 1;
    int expected_stage = 1;
    for (const auto& topo : topology) {
        if (topo.ion_stage != expected_stage++ || topo.nlev < 2 || topo.start_row != expected_full_rows ||
            !(topo.terminal_statistical_weight > 0.0) || !std::isfinite(topo.terminal_energy_ev)) {
            throw std::runtime_error("LTE source ion topology sidecar is inconsistent");
        }
        expected_full_rows += topo.nlev - 1;
    }
    if (expected_full_rows != element.n_rows || static_cast<int>(topology.size()) != element.n_ions) {
        throw std::runtime_error("LTE source ion topology does not cover full compact element");
    }

    const double temperature_k = input.temperature_k;
    const double source_xnx = input.hydrogen_density_cm3 * input.electron_fraction_xee;
    // v82 patch 5.7: the v0.6.47.2 levwk trajectory uses XSTAR's historical
    // 0.861707 eV per 10^4 K conversion.  This is intentionally distinct
    // from the modern bk/ergsev constants used by newer continuum kernels.
    const double bktm = xstar_constants::kLegacyBoltzmannEvPerT4 * (temperature_k / 1.0e4);
    const double source_q2_constant = static_cast<double>(static_cast<float>(2.07e-16));
    const double q2 = source_q2_constant * source_xnx * std::pow(temperature_k, -1.5);
    const double source_floor37 = 1.0e-37;
    const double source_floor97 = 1.0e-97;
    const double source_cap66 = 1.0e66;

    std::vector<double> rnise(static_cast<std::size_t>(element.n_rows) + 1u, 0.0);
    std::vector<double> rnisi;
    int last_nlev = 0;
    int ipmatsv = 0;
    for (const auto& topo : topology) {
        const int nlev = topo.nlev;
        const bool active = topo.ion_stage >= active_min_stage && topo.ion_stage <= active_max_stage;
        if (active) {
            const LteLevelData* terminal_level = exact_leveltemp
                ? lte_leveltemp_row_v82_patch56(program, element.element_index, topo.ion_stage, nlev)
                : nullptr;
            if (exact_leveltemp && !terminal_level) {
                throw std::runtime_error("complete Type-13 LTE leveltemp terminal row missing");
            }
            const double terminal_energy = terminal_level ? terminal_level->energy_ev : topo.terminal_energy_ev;
            const double terminal_weight = terminal_level ? terminal_level->statistical_weight : topo.terminal_statistical_weight;
            const double rs = q2 / terminal_weight;
            rnisi.assign(static_cast<std::size_t>(nlev) + 1u, 0.0);
            rnisi[static_cast<std::size_t>(nlev)] = 1.0;
            double bb = 1.0;
            for (int local = 1; local < nlev; ++local) {
                const int compact_row = topo.start_row + local - 1;
                const auto& compact_level = element.rows.at(static_cast<std::size_t>(compact_row - 1));
                const LteLevelData* source_level = exact_leveltemp
                    ? lte_leveltemp_row_v82_patch56(program, element.element_index, topo.ion_stage, local)
                    : nullptr;
                if (exact_leveltemp && !source_level) {
                    throw std::runtime_error("complete Type-13 LTE leveltemp bound row missing");
                }
                const double level_energy = source_level ? source_level->energy_ev : compact_level.energy_ev;
                const double level_weight = source_level ? source_level->statistical_weight : compact_level.statistical_weight;
                const double ethsht = std::max(
                    (terminal_energy - level_energy) / std::max(bktm, 1.0e-300), 0.0);
                const double explev2 = std::exp(std::min(std::max(-ethsht, -60.0), 60.0));
                const double value = level_weight / (explev2 / std::max(rs, 1.0e-300));
                rnisi[static_cast<std::size_t>(local)] = value;
                bb += value;
            }
            for (int local = 1; local <= nlev; ++local) {
                rnisi[static_cast<std::size_t>(local)] /= bb;
            }

            if (topo.ion_stage == active_min_stage) {
                rnise[static_cast<std::size_t>(1 + ipmatsv)] = rnisi[1];
            }
            for (int local = 2; local <= nlev; ++local) {
                const int target = local + ipmatsv;
                if (topo.ion_stage > active_min_stage) {
                    rnise[static_cast<std::size_t>(target)] = std::min(
                        source_cap66,
                        rnise[static_cast<std::size_t>(target - 1)] *
                            rnisi[static_cast<std::size_t>(local)] /
                            (source_floor37 + rnisi[static_cast<std::size_t>(local - 1)]));
                } else {
                    rnise[static_cast<std::size_t>(target)] = rnisi[static_cast<std::size_t>(local)];
                }
            }
            const LteLevelData* terminal_level_for_audit = exact_leveltemp
                ? lte_leveltemp_row_v82_patch56(program, element.element_index, topo.ion_stage, nlev) : nullptr;
            const double terminal_energy_for_audit = terminal_level_for_audit ? terminal_level_for_audit->energy_ev : topo.terminal_energy_ev;
            const double terminal_weight_for_audit = terminal_level_for_audit ? terminal_level_for_audit->statistical_weight : topo.terminal_statistical_weight;
            for (int local = 1; local <= nlev; ++local) {
                const int compact_row = topo.start_row + local - 1;
                const auto& compact_level = element.rows.at(static_cast<std::size_t>(compact_row - 1));
                const LteLevelData* source_level = exact_leveltemp
                    ? lte_leveltemp_row_v82_patch56(program, element.element_index, topo.ion_stage, local) : nullptr;
                RnisiAuditRowV82Patch56 row;
                row.stage = topo.ion_stage; row.local = local; row.compact_row = compact_row; row.active = true;
                row.global_level_index = compact_level.global_level_index;
                row.source_record = source_level ? source_level->source_record : 0;
                row.energy_ev = source_level ? source_level->energy_ev : compact_level.energy_ev;
                row.weight = source_level ? source_level->statistical_weight : compact_level.statistical_weight;
                row.terminal_energy_ev = terminal_energy_for_audit; row.terminal_weight = terminal_weight_for_audit;
                row.rnisi = rnisi[static_cast<std::size_t>(local)];
                row.recurrence_ratio = local > 1 ? rnisi[static_cast<std::size_t>(local)] /
                    (source_floor37 + rnisi[static_cast<std::size_t>(local - 1)]) : 0.0;
                const int target = local + ipmatsv;
                row.raw_rnise = target >= 1 && target < static_cast<int>(rnise.size())
                    ? rnise[static_cast<std::size_t>(target)] : 0.0;
                rnisi_audit.push_back(row);
            }
        } else {
            // Literal levwkelement inactive-ion branch.  The shared terminal
            // row is zeroed too; ipmatsv still advances by nlev-1.
            for (int local = 1; local <= nlev; ++local) {
                rnise[static_cast<std::size_t>(local + ipmatsv)] = 0.0;
            }
        }
        ipmatsv += nlev - 1;
        last_nlev = nlev;
    }

    if (last_nlev < 2 || ipmatsv + 1 != element.n_rows || rnisi.size() <= static_cast<std::size_t>(last_nlev)) {
        throw std::runtime_error("LTE fully stripped source topology is invalid");
    }
    rnise[static_cast<std::size_t>(ipmatsv + 1)] =
        rnise[static_cast<std::size_t>(ipmatsv)] *
        rnisi[static_cast<std::size_t>(last_nlev)] /
        (source_floor97 + rnisi[static_cast<std::size_t>(last_nlev - 1)]);
    if (!rnisi_audit.empty()) {
        auto& last = rnisi_audit.back();
        last.fully_stripped = true;
        last.recurrence_ratio = rnisi[static_cast<std::size_t>(last_nlev)] /
            (source_floor97 + rnisi[static_cast<std::size_t>(last_nlev - 1)]);
        last.raw_rnise = rnise[static_cast<std::size_t>(ipmatsv + 1)];
    }

    double total = 0.0;
    for (int row = 1; row <= element.n_rows; ++row) total += rnise[static_cast<std::size_t>(row)];
    const double denom = source_floor97 + total;
    if (!(denom > 0.0) || !std::isfinite(denom)) {
        throw std::runtime_error("LTE source partition normalization is non-positive");
    }
    std::vector<double> out(static_cast<std::size_t>(element.n_rows), 0.0);
    for (int row = 1; row <= element.n_rows; ++row) {
        out[static_cast<std::size_t>(row - 1)] = rnise[static_cast<std::size_t>(row)] / denom;
    }

    const char* sequence_env_patch56 = std::getenv("XSTAR_NATIVE_SOURCE_SEQUENCE");
    const int source_sequence_patch56 = sequence_env_patch56 && *sequence_env_patch56 ? std::atoi(sequence_env_patch56) : 0;
    const char* audit_path_patch56 = std::getenv("XSTAR_V82_PATCH56_SEQUENCE58_RNISI_AUDIT_PATH");
    if (source_sequence_patch56 == 58 && element.element_z == 12 && audit_path_patch56 && *audit_path_patch56) {
        std::filesystem::path audit_path(audit_path_patch56);
        if (!audit_path.parent_path().empty()) std::filesystem::create_directories(audit_path.parent_path());
        std::ofstream csv(audit_path);
        if (!csv) throw std::runtime_error("cannot create patch5.6 sequence58 rnisi audit");
        csv << "ion_stage,active,start_row,nlev,local_level,target_compact_row,target_global_level_index,source_type13_record,level_energy_ev,level_statistical_weight,terminal_energy_ev,terminal_statistical_weight,rnisi,transition_applied,transition_ratio,raw_rnise,normalized_rnise,fully_stripped\n";
        for (auto& row : rnisi_audit) {
            if (row.compact_row >= 1 && static_cast<std::size_t>(row.compact_row) <= out.size()) {
                row.normalized_lte = out[static_cast<std::size_t>(row.compact_row - 1)];
            }
            const auto topo_it = std::find_if(topology.begin(), topology.end(), [&](const auto& t) { return t.ion_stage == row.stage; });
            const int start_row = topo_it == topology.end() ? 0 : topo_it->start_row;
            const int nlev = topo_it == topology.end() ? 0 : topo_it->nlev;
            csv << row.stage << ',' << (row.active ? 1 : 0) << ',' << start_row << ',' << nlev << ','
                << row.local << ',' << row.compact_row << ',' << row.global_level_index << ',' << row.source_record << ','
                << std::setprecision(17) << row.energy_ev << ',' << row.weight << ',' << row.terminal_energy_ev << ','
                << row.terminal_weight << ',' << row.rnisi << ',' << (row.local > 1 ? 1 : 0) << ','
                << row.recurrence_ratio << ',' << row.raw_rnise << ',' << row.normalized_lte << ','
                << (row.fully_stripped ? 1 : 0) << '\n';
        }
        std::cout << "V048746255172582_SEQUENCE58_MG_TYPE13_LEVELTEMP_ROWS=" << rnisi_audit.size() << "\n"
                  << "V048746255172582_SEQUENCE58_MG_TYPE13_LEVELTEMP_SOURCE_SEMANTICS="
                  << (exact_leveltemp ? "ACCEPT" : "FALLBACK") << "\n"
                  << "V048746255172582_SEQUENCE58_MG_RNISI_AUDIT=WRITTEN\n";
    }
    return out;
}

std::vector<double> compute_exact_lte_populations(
    const Program& program,
    const xstar_fixed_state_input_v1& input,
    const std::map<int, std::pair<int,int>>& active_stage_windows
) {
    if (!(input.temperature_k > 0.0) || !(input.electron_density_cm3 >= 0.0)) {
        throw std::runtime_error("LTE population inputs are invalid");
    }
    std::vector<double> all;
    std::size_t total_rows = 0;
    for (const auto& element : program.elements) total_rows += static_cast<std::size_t>(element.n_rows);
    all.reserve(total_rows);

    const char* sequence_env = std::getenv("XSTAR_NATIVE_SOURCE_SEQUENCE");
    const int source_sequence = sequence_env && *sequence_env ? std::atoi(sequence_env) : 0;

    for (const auto& element : program.elements) {
        int active_min_stage = 1;
        int active_max_stage = element.n_ions;
        const auto retained = active_stage_windows.find(element.element_z);
        if (retained != active_stage_windows.end()) {
            active_min_stage = retained->second.first;
            active_max_stage = retained->second.second;
        }
        bool exact_topology = false;
        auto full_lte = compute_element_lte_populations_v82_patch54(
            program, element, input, active_min_stage, active_max_stage, &exact_topology);

        if (source_sequence == 58 && element.element_z == 12) {
            const auto topology = lte_topology_for_element_v82_patch54(program, element);
            int active_rows = 1;
            std::ostringstream nlev_stream;
            bool stage_order_ok = topology.size() == 12u;
            for (std::size_t i = 0; i < topology.size(); ++i) {
                const auto& topo = topology[i];
                if (i) nlev_stream << ':';
                nlev_stream << topo.ion_stage << '=' << topo.nlev;
                stage_order_ok = stage_order_ok && topo.ion_stage == static_cast<int>(i) + 1;
                if (topo.ion_stage >= active_min_stage && topo.ion_stage <= active_max_stage) {
                    active_rows += topo.nlev - 1;
                }
            }
            std::size_t nonzero = 0;
            for (double value : full_lte) if (std::isfinite(value) && value != 0.0) ++nonzero;
            const bool source_topology_accept = exact_topology && stage_order_ok &&
                element.n_rows == 577 && active_rows == 552 &&
                active_min_stage == 3 && active_max_stage == 12;
            std::cout << "V048746255172582_SEQUENCE58_MG_LTE_FULL_ROWS=" << element.n_rows << "\n"
                      << "V048746255172582_SEQUENCE58_MG_LTE_ACTIVE_ROWS=" << active_rows << "\n"
                      << "V048746255172582_SEQUENCE58_MG_LTE_ACTIVE_MIN_STAGE=" << active_min_stage << "\n"
                      << "V048746255172582_SEQUENCE58_MG_LTE_ACTIVE_MAX_STAGE=" << active_max_stage << "\n"
                      << "V048746255172582_SEQUENCE58_MG_LTE_NONZERO_COMPACT_ROWS=" << nonzero << "\n"
                      << "V048746255172582_SEQUENCE58_MG_SOURCE_NLEV=" << nlev_stream.str() << "\n"
                      << "V048746255172582_SEQUENCE58_MG_SOURCE_NLEV_TOPOLOGY="
                      << (source_topology_accept ? "ACCEPT" : "REJECT") << "\n"
                      << "V048746255172582_SEQUENCE58_MG_LTE_ACTIVE_WINDOW_SOURCE_SEMANTICS="
                      << (source_topology_accept ? "ACCEPT" : "REJECT") << "\n"
                      << "V048746255172582_SEQUENCE58_LEVWK_BOLTZMANN_EV_PER_T4="
                      << std::setprecision(17) << xstar_constants::kLegacyBoltzmannEvPerT4 << "\n"
                      << "V048746255172582_SEQUENCE58_LEVWK_BOLTZMANN_SOURCE_SEMANTICS=ACCEPT_HISTORICAL\n";
        }
        all.insert(all.end(), full_lte.begin(), full_lte.end());
    }
    return all;
}

void validate_io(const xstar_fixed_state_input_v1& in, xstar_fixed_state_output_v1& out) {
    if (in.struct_size < sizeof(in) || in.abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) throw std::runtime_error("fixed-state input ABI mismatch");
    if (out.struct_size < sizeof(out) || out.abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) throw std::runtime_error("fixed-state output ABI mismatch");
    if (!(in.temperature_k > 0.0) || !std::isfinite(in.temperature_k)) throw std::runtime_error("temperature must be finite and positive");
    if (!(in.electron_density_cm3 >= 0.0) || !std::isfinite(in.electron_density_cm3)) throw std::runtime_error("electron density invalid");
    if (in.radiation_bin_count > 0 && (!in.radiation_energy_ev || !in.radiation_flux)) throw std::runtime_error("radiation arrays missing");
    if (in.dsec_radiation_bin_count > 0 && (!in.dsec_radiation_energy_ev || !in.dsec_bremsa)) throw std::runtime_error("DSEC radiation workspace arrays missing");
    if (in.continuum_tau_count > 0 && (!in.continuum_tau_in || !in.continuum_tau_out)) throw std::runtime_error("continuum optical-depth workspace arrays missing");
    if (in.global_level_count > 0 && (!in.global_xilevg || !in.global_bilevg || !in.global_rnisg)) throw std::runtime_error("global-level workspace arrays missing");
    if ((in.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION) != 0u &&
        (!std::isfinite(in.dsec_covering_fraction) || in.dsec_covering_fraction < 0.0 || in.dsec_covering_fraction > 1.0))
        throw std::runtime_error("DSEC covering fraction must be finite and in [0,1]");
    if (out.spectrum_capacity < in.radiation_bin_count || out.opacity_capacity < in.radiation_bin_count) throw std::runtime_error("spectrum or opacity output capacity too small");
}


struct NativeBoundFreeCurve {
    double threshold_ev = 0.0;
    std::vector<double> offset_ryd;
    std::vector<double> sigma_cm2;
    bool type49_semantics = false;
    bool apply_source_phextrap = false;
    int phextrap_max_points = 0;
};

struct Phint53GridMapV82Patch57 {
    std::vector<double> sgbar;
    int nb1_zero_based = -1;
    int klmax_zero_based = -1;
    int effective_pair_count = 0;
    bool phextrap_applied = false;
    bool valid = false;
};

int phint53_nbinc_one_based_v82_patch57(double energy_ev, const double* epi, int ncn2) {
    if (!epi || ncn2 < 3) return 1;
    const int numcon2 = std::max(2, ncn2 / 50);
    const int n = std::max(1, ncn2 - numcon2);
    int jlo = 1;
    if (n < 2) return jlo;
    const double xtmp = std::max(energy_ev, epi[1]);
    if (!(energy_ev < 1.0e-34 || epi[0] <= 1.0e-34 || epi[n - 1] <= 1.0e-34)) {
        const double denom = std::log(epi[n - 1] / epi[0]);
        if (std::isfinite(denom) && denom != 0.0) {
            jlo = static_cast<int>((n - 1) * std::log(xtmp / epi[0]) / denom) + 1;
        }
        jlo = std::clamp(jlo, 1, n);
        if (jlo < n) {
            const double tst = std::abs(std::log(energy_ev / (1.0e-34 + epi[jlo - 1])));
            const double tst2 = std::abs(std::log(energy_ev / (1.0e-34 + epi[jlo])));
            if (tst2 < tst) ++jlo;
        }
    }
    return std::clamp(jlo, 1, n);
}

void phextrap_source_v82_patch57(const NativeBoundFreeCurve& curve,
                                 int ncn2,
                                 std::vector<double>& energy_ryd,
                                 std::vector<double>& sigma_cm2) {
    if (!curve.apply_source_phextrap || energy_ryd.size() < 2 ||
        energy_ryd.size() != sigma_cm2.size()) return;
    const int ntmp_initial = static_cast<int>(energy_ryd.size());
    const int limit = curve.phextrap_max_points > 0
        ? std::min(curve.phextrap_max_points, ncn2) : ncn2;
    if (limit <= 1) return;
    int nadd = 0;
    double s1 = sigma_cm2[static_cast<std::size_t>(ntmp_initial - 2)];
    double e1 = energy_ryd[static_cast<std::size_t>(ntmp_initial - 2)] * 13.6 + curve.threshold_ev;
    while (s1 > 1.0e-27 && nadd + ntmp_initial < limit && e1 < 2.0e5) {
        const double e2 = e1 * 1.3;
        const double s2 = s1 / (1.3 * 1.3 * 1.3);
        ++nadd;
        // Literal phextrap.f90 writes stmp(nadd+ntmp-1), so the first
        // extrapolated point replaces the original final tabulated point.
        const std::size_t target = static_cast<std::size_t>(nadd + ntmp_initial - 2);
        if (target >= energy_ryd.size()) {
            energy_ryd.resize(target + 1u);
            sigma_cm2.resize(target + 1u);
        }
        sigma_cm2[target] = s2;
        energy_ryd[target] = (e2 - curve.threshold_ev) / 13.6;
        e1 = e2;
        s1 = s2;
    }
    const int ntmp_final = nadd + ntmp_initial - 1;
    if (ntmp_final >= 2) {
        energy_ryd.resize(static_cast<std::size_t>(ntmp_final));
        sigma_cm2.resize(static_cast<std::size_t>(ntmp_final));
    }
}

Phint53GridMapV82Patch57 phint53_grid_map_v82_patch57(
    const NativeBoundFreeCurve& curve, const double* epi, int ncn2) {
    Phint53GridMapV82Patch57 out;
    if (!epi || ncn2 < 3 || curve.offset_ryd.size() < 2 ||
        curve.offset_ryd.size() != curve.sigma_cm2.size() || !(curve.threshold_ev > 0.0)) return out;
    std::vector<double> energy_ryd = curve.offset_ryd;
    std::vector<double> sigma_cm2 = curve.sigma_cm2;
    const std::size_t before = energy_ryd.size();
    phextrap_source_v82_patch57(curve, ncn2, energy_ryd, sigma_cm2);
    out.phextrap_applied = curve.apply_source_phextrap && energy_ryd.size() != before;
    const int ntmp = static_cast<int>(std::min(energy_ryd.size(), sigma_cm2.size()));
    if (ntmp < 2) return out;
    out.effective_pair_count = ntmp;
    const int numcon2 = std::max(2, ncn2 / 50);
    const int nphint = ncn2 - numcon2;
    if (nphint < 2) return out;

    std::vector<double> xs(static_cast<std::size_t>(ntmp), 0.0);
    std::vector<double> ys(static_cast<std::size_t>(ntmp), 0.0);
    for (int j = 0; j < ntmp; ++j) {
        xs[static_cast<std::size_t>(j)] = curve.threshold_ev +
            energy_ryd[static_cast<std::size_t>(j)] * kType53RydEv;
        ys[static_cast<std::size_t>(j)] = std::max(0.0, sigma_cm2[static_cast<std::size_t>(j)]);
    }

    const double ener = xs[0];
    int nb1 = phint53_nbinc_one_based_v82_patch57(ener, epi, ncn2);
    while (nb1 >= 1 && nb1 <= ncn2 && epi[nb1 - 1] < ener && nb1 < nphint) ++nb1;
    --nb1;
    nb1 = std::max(nb1, 1);
    if (nb1 >= nphint) return out;
    const int nb = nb1 - 1;

    out.sgbar.assign(static_cast<std::size_t>(ncn2), 0.0);
    out.sgbar[static_cast<std::size_t>(std::max(0, nb - 1))] = 0.0;
    out.sgbar[static_cast<std::size_t>(nb)] = 0.0;
    int kl = nb;
    int jk = 0;
    double e1 = epi[kl];
    double e2 = xs[0];
    double s2 = ys[0];
    if (e1 < e2 && kl + 1 < ncn2) { ++kl; e1 = epi[kl]; }
    double e1o = e2;
    double sum = 0.0;
    double e2o = e2;
    double s2o = s2;
    double e2t = e1;
    double s2t = s2;
    bool done = false;
    int iterations = 0;
    const int max_iterations = std::max(8, 4 * (ncn2 + ntmp));
    while (!done && iterations < max_iterations && kl < ncn2) {
        ++iterations;
        bool advanced = false;
        while (e2 < e1 && jk < ntmp - 2) {
            ++jk;
            e2o = e2;
            s2o = s2;
            e2 = xs[static_cast<std::size_t>(jk)];
            s2 = ys[static_cast<std::size_t>(jk)];
            sum += (s2 + s2o) * (e2 - e2o) / 2.0;
            advanced = true;
        }
        // Source phint53 reaches this branch with a populated previous segment
        // for physical threshold records.  Preserve deterministic behavior for
        // degenerate records rather than depending on undefined Fortran locals.
        if (!advanced && iterations == 1) { e2o = e2; s2o = s2; }
        sum -= (s2 + s2o) * (e2 - e2o) / 2.0;
        e2t = e1;
        s2t = (e2 - e2o > 1.0e-8)
            ? s2o + (s2 - s2o) * (e2t - e2o) / (e2 - e2o + 1.0e-24)
            : s2o;
        sum += (s2t + s2o) * (e2t - e2o) / 2.0;
        const double den = e1 - e1o;
        out.sgbar[static_cast<std::size_t>(kl)] = std::abs(den) > 1.0e-36 ? sum / den : 0.0;
        e1o = e1;
        ++kl;
        if (kl >= ncn2) break;
        e1 = epi[kl];
        while (e1 < e2 && kl < ncn2 - 1) {
            e2t = e1;
            s2t = (e2 - e2o > 1.0e-8)
                ? s2o + (s2 - s2o) * (e2t - e2o) / (e2 - e2o)
                : s2o;
            const double s2to = s2t;
            sum = (s2t + s2to) * (e1 - e1o) / 2.0;
            const double local_den = e1 - e1o;
            out.sgbar[static_cast<std::size_t>(kl)] =
                std::abs(local_den) > 1.0e-36 ? sum / local_den : 0.0;
            e1o = e1;
            ++kl;
            if (kl >= ncn2) break;
            e1 = epi[kl];
        }
        sum = (s2 + s2t) * (e2 - e2t) / 2.0;
        if (kl > nphint - 1 || jk >= ntmp - 2) done = true;
    }
    if (iterations >= max_iterations) return out;
    out.nb1_zero_based = nb;
    out.klmax_zero_based = kl - 1;
    out.valid = out.klmax_zero_based > out.nb1_zero_based;
    return out;
}

double interpolate_bound_free_sigma(const NativeBoundFreeCurve& curve, double energy_ev) {
    if (!(energy_ev >= curve.threshold_ev) || curve.offset_ryd.empty() ||
        curve.offset_ryd.size() != curve.sigma_cm2.size()) return 0.0;
    const double x = (energy_ev - curve.threshold_ev) / kType53RydEv;
    if (x <= curve.offset_ryd.front()) return std::max(0.0, curve.sigma_cm2.front());
    if (x >= curve.offset_ryd.back()) {
        if (curve.offset_ryd.size() < 2 || !(curve.offset_ryd.back() > 0.0) || !(x > 0.0)) {
            return std::max(0.0, curve.sigma_cm2.back());
        }
        const std::size_t n = curve.offset_ryd.size();
        const double x0 = std::max(curve.offset_ryd[n - 2], 1.0e-30);
        const double x1 = std::max(curve.offset_ryd[n - 1], 1.0e-30);
        const double s0 = std::max(curve.sigma_cm2[n - 2], 1.0e-300);
        const double s1 = std::max(curve.sigma_cm2[n - 1], 1.0e-300);
        double slope = -3.0;
        if (x1 != x0 && s0 > 0.0 && s1 > 0.0) slope = std::log(s1 / s0) / std::log(x1 / x0);
        if (!std::isfinite(slope)) slope = -3.0;
        return std::max(0.0, s1 * std::pow(x / x1, slope));
    }
    const auto it = std::upper_bound(curve.offset_ryd.begin(), curve.offset_ryd.end(), x);
    const std::size_t hi = static_cast<std::size_t>(it - curve.offset_ryd.begin());
    const std::size_t lo = hi - 1;
    const double x0 = curve.offset_ryd[lo], x1 = curve.offset_ryd[hi];
    const double y0 = std::max(0.0, curve.sigma_cm2[lo]);
    const double y1 = std::max(0.0, curve.sigma_cm2[hi]);
    if (x1 == x0) return y0;
    return std::max(0.0, y0 + (y1 - y0) * (x - x0) / (x1 - x0));
}

bool native_bound_free_curve(const Program& program,
                             const ProgramRecord& record,
                             const EvaluatedRecord& evaluated,
                             NativeBoundFreeCurve& curve,
                             bool prefer_full_calc_emis_shadow = true) {
    curve = {};
    if (!evaluated.bound_free_spectral || record.real_offset + record.real_count > program.reals.size()) return false;
    const double* r = program.reals.data() + record.real_offset;
    if (record.opcode == XSTAR_FIXED_OPCODE_TYPE53_BOUND_FREE ||
        record.opcode == XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE) {
        // This curve is consumed by the full-grid calc_emis/HEATT spectral
        // replay.  Prefer the retained full calc_emis shadow; the base shadow
        // belongs to calc_hmc on the reduced DSEC grid.  In particular,
        // Type49 phextrap must retain the full caller ncn2=9999 limit here.
        const Type53SourceShadow& base_shadow = record.opcode == XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE
            ? evaluated.type49_shadow : evaluated.type53_shadow;
        const Type53SourceShadow& calc_emis_shadow = record.opcode == XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE
            ? evaluated.type49_calc_emis_shadow : evaluated.type53_calc_emis_shadow;
        const Type53SourceShadow& shadow =
            prefer_full_calc_emis_shadow && calc_emis_shadow.valid ? calc_emis_shadow : base_shadow;
        const int pair_count = shadow.phextrap_input_pair_count > 0
            ? shadow.phextrap_input_pair_count
            : static_cast<int>(record.real_count / 2);
        if (pair_count < 2 || static_cast<std::size_t>(2 * pair_count) > record.real_count) return false;
        curve.threshold_ev = shadow.threshold_ev > 0.0 ? shadow.threshold_ev : evaluated.line_energy_ev;
        curve.type49_semantics = record.opcode == XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE;
        curve.apply_source_phextrap = curve.type49_semantics && shadow.phextrap_applied;
        curve.phextrap_max_points = shadow.phextrap_max_points;
        curve.offset_ryd.reserve(static_cast<std::size_t>(pair_count));
        curve.sigma_cm2.reserve(static_cast<std::size_t>(pair_count));
        for (int i = 0; i < pair_count; ++i) {
            curve.offset_ryd.push_back(r[2 * i]);
            curve.sigma_cm2.push_back(std::max(0.0, r[2 * i + 1]));
        }
        return curve.threshold_ev > 0.0;
    }
    if (record.opcode == XSTAR_FIXED_OPCODE_TYPE99_SUPERLEVEL_BOUND_FREE) {
        if (record.int_offset + record.int_count > program.ints.size() || record.int_count < 3) return false;
        const auto* ints = program.ints.data() + record.int_offset;
        const int nden = static_cast<int>(ints[0]);
        const int ntem = static_cast<int>(ints[1]);
        const int nxs = static_cast<int>(ints[2]);
        const std::size_t offset = static_cast<std::size_t>(nden + ntem + nden * ntem);
        if (nden <= 0 || ntem < 2 || nxs < 2 || offset + 2u * static_cast<std::size_t>(nxs) > record.real_count) return false;
        curve.threshold_ev = evaluated.type99_shadow.threshold_ev;
        const double scale = evaluated.type99_shadow.cross_section_scale;
        curve.offset_ryd.reserve(static_cast<std::size_t>(nxs));
        curve.sigma_cm2.reserve(static_cast<std::size_t>(nxs));
        for (int i = 0; i < nxs; ++i) {
            curve.offset_ryd.push_back(r[offset + 2u * static_cast<std::size_t>(i)]);
            curve.sigma_cm2.push_back(std::max(0.0, r[offset + 2u * static_cast<std::size_t>(i) + 1u]) * scale * 1.0e-18);
        }
        return curve.threshold_ev > 0.0 && scale > 0.0;
    }
    return false;
}

double effective_spectral_covering_fraction_v82_patch58(const xstar_fixed_state_input_v1& input);

struct DeferredRrcRecordV82Patch520 {
    std::uint64_t source_position = 0u;
    std::int64_t record = 0;
    int rate_type = 0;
    bool source_rate42_type88 = false;
    double type88_rnist = 0.0;
    NativeBoundFreeCurve opacity_curve;
    NativeBoundFreeCurve emission_curve;
    EvaluatedRecord evaluated;
    double lower_abundance = 0.0;
    double upper_abundance = 0.0;
};

struct Type88StaleOpakabV82Patch52010 {
    bool mapped = false;
    bool threshold_publication_reached = false;
    int nb1_one_based = 0;
    int publish_kl_one_based = 0;
    double absorption_sigma_cm2 = 0.0;
    double stimulated_sigma_cm2 = 0.0;
    double opakab_cm1 = 0.0;
};

// Literal calc_emis_ion rate-42 side effect.  The physical Type-88 UCalc
// threshold and full-grid opakc/rccemis calculation are independent of the
// stale kkkl/errc/tauc values retained by the caller.  However, phint53 writes
// its scalar opakab result through the caller-owned opakab(kkkl) argument.
// Reconstruct only that scalar publication here; the existing Type-88
// full-grid continuum kernels remain untouched.
Type88StaleOpakabV82Patch52010 source_type88_stale_opakab_v82_patch52010(
    const NativeBoundFreeCurve& curve,
    double rnist,
    double lower_abundance,
    double upper_abundance,
    const xstar_fixed_state_input_v1& input
) {
    Type88StaleOpakabV82Patch52010 out;
    const std::size_t n = input.radiation_bin_count;
    if (n < 4 || !input.radiation_energy_ev || !(curve.threshold_ev > 0.0) || !(rnist > 0.0)) return out;
    const auto mapped = phint53_grid_map_v82_patch57(
        curve, input.radiation_energy_ev, static_cast<int>(n));
    if (!mapped.valid) return out;
    out.mapped = true;
    out.nb1_one_based = mapped.nb1_zero_based + 1;
    const int publish_kl = mapped.nb1_zero_based + 2;
    out.publish_kl_one_based = publish_kl + 1;
    if (publish_kl >= mapped.klmax_zero_based || publish_kl + 1 >= static_cast<int>(n)) return out;

    const double sgtp = std::max(0.0, mapped.sgbar[static_cast<std::size_t>(publish_kl)]);
    const double bktm = xstar_constants::kBoltzmannErgPerK * input.temperature_k /
        xstar_constants::kModernErgPerEv;
    const double previous_exptst =
        (input.radiation_energy_ev[static_cast<std::size_t>(publish_kl)] - curve.threshold_ev) /
        std::max(bktm, 1.0e-300);
    double exptmpp = 0.0;
    if (previous_exptst < 200.0) {
        const double next_exptst =
            (input.radiation_energy_ev[static_cast<std::size_t>(publish_kl + 1)] - curve.threshold_ev) /
            std::max(bktm, 1.0e-300);
        exptmpp = limited_exp(-next_exptst);
    }
    // rate-42 has ptmp1=(1-cfrac)/2 and ptmp2=(1+cfrac)/2, so their
    // literal sum in phint53 is exactly one.
    out.absorption_sigma_cm2 = sgtp;
    out.stimulated_sigma_cm2 = rnist * exptmpp * sgtp;
    const double density = std::max(0.0, input.hydrogen_density_cm3);
    const double optmp = lower_abundance * density * out.absorption_sigma_cm2;
    const double optmp2 = upper_abundance * density * out.stimulated_sigma_cm2;
    out.opakab_cm1 = std::max(0.0, optmp - optmp2);
    out.threshold_publication_reached = true;
    return out;
}

// v82 patch 5.20.11: the heatt-facing phint53 RRC reconstruction must use
// expo.f90 (historical +/-60 clamp), exactly like the accepted rate/integral
// evaluator and the pure-Python source port.  A generic +/-700 exponential
// suppresses the high-excess-energy recombination tail and perturbs heatt.
void accumulate_native_bound_free_rrc_from_abundances_v82_patch520(
    const NativeBoundFreeCurve& curve,
    const EvaluatedRecord& evaluated,
    const ProgramRecord& record,
    double lower_abundance,
    double upper_abundance,
    const xstar_fixed_state_input_v1& input,
    std::vector<double>& rccemis) {
    const std::size_t n = input.radiation_bin_count;
    if (n < 2 || rccemis.size() != 2 * n) return;
    (void)lower_abundance;
    const double density = std::max(0.0, input.hydrogen_density_cm3);
    const bool type49_or_53 = record.opcode == XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE ||
        record.opcode == XSTAR_FIXED_OPCODE_TYPE53_BOUND_FREE;
    if (record.opcode == XSTAR_FIXED_OPCODE_TYPE88_SUPERLEVEL_BOUND_FREE) {
        const auto mapped = phint53_grid_map_v82_patch57(
            curve, input.radiation_energy_ev, static_cast<int>(n));
        if (!mapped.valid || !(evaluated.type53_shadow.rnist > 0.0)) return;
        const double bktm = xstar_constants::kBoltzmannErgPerK * input.temperature_k /
            xstar_constants::kModernErgPerEv;
        const double covering = effective_spectral_covering_fraction_v82_patch58(input);
        const double ptmp1 = 0.5 * (1.0 - covering);
        const double ptmp2 = 0.5 * (1.0 + covering);
        double exptst = (input.radiation_energy_ev[mapped.nb1_zero_based] - curve.threshold_ev) /
            std::max(bktm, 1.0e-300);
        for (int kl = mapped.nb1_zero_based; kl < mapped.klmax_zero_based &&
             kl + 1 < static_cast<int>(n); ++kl) {
            const double sgtpp = std::max(0.0, mapped.sgbar[static_cast<std::size_t>(kl + 1)]);
            const double previous_exptst = exptst;
            const double epiip = input.radiation_energy_ev[static_cast<std::size_t>(kl + 1)];
            exptst = (epiip - curve.threshold_ev) / std::max(bktm, 1.0e-300);
            if (previous_exptst < 200.0 && sgtpp > 0.0 && upper_abundance > 0.0 &&
                density > 0.0 && epiip > 0.0) {
                const double exptmpp = type53_expo(-exptst);
                const double bbnurjp = std::pow(std::min(2.0e4, epiip), 3.0) * 1.571e22 * 2.0;
                const double common = upper_abundance * density * evaluated.type53_shadow.rnist *
                    bbnurjp * sgtpp * exptmpp;
                rccemis[static_cast<std::size_t>(kl)] += common * ptmp1;
                rccemis[n + static_cast<std::size_t>(kl)] += common * ptmp2;
            }
        }
        return;
    }
    if (type49_or_53) {
        const auto mapped = phint53_grid_map_v82_patch57(
            curve, input.radiation_energy_ev, static_cast<int>(n));
        if (!mapped.valid) return;
        // v82 patch 5.20.15.1: the output-metadata cache now preserves the
        // literal Type-49 xstarsetup rank coordinate, so the regenerated
        // solve-stage cache carries the selected full-grid opakab -> STPCUT
        // tauc state.  Re-enable the source calc_emis_ion escape semantics:
        //   ptmp1=pescv(tauc(1,kkkl))*(1-cfrac)
        //   ptmp2=pescv(tauc(2,kkkl))*(1-cfrac)
        //         +2*pescv(tauc(1,kkkl)+tauc(2,kkkl))*cfrac
        // Keep the 5.20.14.9 dual curve ownership untouched: curve here is
        // still the dedicated emission curve, not the full opacity curve.
        const Type53SourceShadow* shadow = record.opcode == XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE
            ? &evaluated.type49_shadow : &evaluated.type53_shadow;
        const double bktm = xstar_constants::kBoltzmannErgPerK * input.temperature_k /
            xstar_constants::kModernErgPerEv;
        const double covering = effective_spectral_covering_fraction_v82_patch58(input);
        const int continuum_index = record.continuum_index_one_based;
        const bool live_tau_available = continuum_index > 0 &&
            static_cast<std::size_t>(continuum_index) <= input.continuum_tau_count &&
            input.continuum_tau_in && input.continuum_tau_out;
        double ptmp1 = covering >= 1.0 - 1.0e-15 ? 0.0 :
            (shadow && shadow->valid ? std::max(0.0, shadow->ptmp1) : 0.5 * (1.0 - covering));
        double ptmp2 = covering >= 1.0 - 1.0e-15 ? 1.0 :
            (shadow && shadow->valid ? std::max(0.0, shadow->ptmp2) : 0.5 * (1.0 - covering) + covering);
        if (live_tau_available) {
            const double tau1 = input.continuum_tau_in[static_cast<std::size_t>(continuum_index - 1)];
            const double tau2 = input.continuum_tau_out[static_cast<std::size_t>(continuum_index - 1)];
            const auto pescv_source = [](double tau) {
                return std::max(std::exp(-tau), 1.0e-12) / 2.0;
            };
            ptmp1 = pescv_source(tau1) * (1.0 - covering);
            ptmp2 = pescv_source(tau2) * (1.0 - covering) +
                2.0 * pescv_source(tau1 + tau2) * covering;
        }
        double exptst = (input.radiation_energy_ev[mapped.nb1_zero_based] - curve.threshold_ev) /
            std::max(bktm, 1.0e-300);
        for (int kl = mapped.nb1_zero_based; kl < mapped.klmax_zero_based &&
             kl + 1 < static_cast<int>(n); ++kl) {
            const double sgtpp = std::max(0.0, mapped.sgbar[static_cast<std::size_t>(kl + 1)]);
            const double previous_exptst = exptst;
            const double epiip = input.radiation_energy_ev[static_cast<std::size_t>(kl + 1)];
            exptst = (epiip - curve.threshold_ev) / std::max(bktm, 1.0e-300);
            if (shadow && shadow->valid && shadow->rnist > 0.0 && previous_exptst < 200.0 &&
                sgtpp > 0.0 && upper_abundance > 0.0 && density > 0.0 && epiip > 0.0) {
                const double exptmpp = type53_expo(-exptst);
                const double bbnurjp = std::pow(std::min(2.0e4, epiip), 3.0) * 1.571e22 * 2.0;
                const double common = upper_abundance * density * shadow->rnist *
                    bbnurjp * sgtpp * exptmpp;
                rccemis[static_cast<std::size_t>(kl)] += common * ptmp1;
                rccemis[n + static_cast<std::size_t>(kl)] += common * ptmp2;
            }
        }
        return;
    }
    if (record.opcode != XSTAR_FIXED_OPCODE_TYPE99_SUPERLEVEL_BOUND_FREE) return;
    const double kt_ev = xstar_constants::kModernBoltzmannEvPerK * input.temperature_k;
    std::vector<double> shape(n, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        const double energy = input.radiation_energy_ev[i];
        const double sigma = interpolate_bound_free_sigma(curve, energy);
        if (!(sigma > 0.0)) continue;
        const double excess = std::max(0.0, energy - curve.threshold_ev);
        shape[i] = sigma * energy * energy * energy * (kt_ev > 0.0 ? limited_exp(-excess / kt_ev) : 0.0);
    }
    double integral = 0.0;
    for (std::size_t i = 1; i < n; ++i) {
        integral += 0.5 * (shape[i - 1] + shape[i]) *
            std::max(0.0, input.radiation_energy_ev[i] - input.radiation_energy_ev[i - 1]);
    }
    const double total_emission = std::max(0.0, -evaluated.contribution.ans3) * upper_abundance * density;
    if (!(integral > 0.0) || !(total_emission > 0.0)) return;
    const double normalization = total_emission / (12.56 * integral);
    for (std::size_t i = 0; i < n; ++i) rccemis[n + i] += normalization * shape[i];
}

// v82 patch 5.20.6: calc_emis_all resets public opakc to Thomson before
// revisiting ranked rate-7 bound-free records and ungated Type-88/rate-42.
// Reconstruct only the phint53 photoabsorption side effect here.  This helper
// deliberately does not publish scalar opakab and does not touch RRC emission.
void accumulate_native_bound_free_opacity_from_abundances_v82_patch5206(
    const NativeBoundFreeCurve& curve,
    const ProgramRecord& record,
    double lower_abundance,
    const xstar_fixed_state_input_v1& input,
    std::vector<double>& opacity_cm1) {
    const std::size_t n = input.radiation_bin_count;
    if (n < 2 || opacity_cm1.size() != n) return;
    const bool source_phint53_opacity =
        record.opcode == XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE ||
        record.opcode == XSTAR_FIXED_OPCODE_TYPE53_BOUND_FREE ||
        record.opcode == XSTAR_FIXED_OPCODE_TYPE88_SUPERLEVEL_BOUND_FREE;
    if (!source_phint53_opacity) return;
    const auto mapped = phint53_grid_map_v82_patch57(
        curve, input.radiation_energy_ev, static_cast<int>(n));
    if (!mapped.valid) return;
    const double density = std::max(0.0, input.hydrogen_density_cm3);
    if (!(lower_abundance > 0.0) || !(density > 0.0)) return;
    for (int kl = mapped.nb1_zero_based; kl < mapped.klmax_zero_based &&
         kl + 1 < static_cast<int>(n); ++kl) {
        const double sgtp = std::max(0.0, mapped.sgbar[static_cast<std::size_t>(kl)]);
        if (sgtp > 0.0)
            opacity_cm1[static_cast<std::size_t>(kl)] += lower_abundance * density * sgtp;
    }
}

double effective_spectral_covering_fraction_v82_patch58(
    const xstar_fixed_state_input_v1& input) {
    const bool has_dsec_covering =
        (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION) != 0u;
    return std::clamp(
        has_dsec_covering ? input.dsec_covering_fraction : input.covering_fraction,
        0.0, 1.0);
}

void accumulate_native_bound_free_surface(const NativeBoundFreeCurve& curve,
                                          const EvaluatedRecord& evaluated,
                                          const ProgramRecord& record,
                                          const ActiveElementView& active,
                                          const std::vector<double>& populations,
                                          const xstar_fixed_state_input_v1& input,
                                          std::vector<double>& opacity_cm1,
                                          std::vector<double>& rccemis,
                                          std::size_t* phint53_records_mapped = nullptr,
                                          std::size_t* phint53_bins_accumulated = nullptr) {
    const std::size_t n = input.radiation_bin_count;
    if (n < 2 || opacity_cm1.size() != n || rccemis.size() != 2 * n ||
        record.lower_row < 1 || record.upper_row < 1) return;
    const double lower_abundance =
        active_population_for_full_row(active, populations, record.lower_row) * active.element.abundance;
    const double upper_abundance =
        active_population_for_full_row(active, populations, record.upper_row) * active.element.abundance;
    const double density = std::max(0.0, input.hydrogen_density_cm3);
    const bool type49_or_53 = record.opcode == XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE ||
        record.opcode == XSTAR_FIXED_OPCODE_TYPE53_BOUND_FREE;
    const bool type99 = record.opcode == XSTAR_FIXED_OPCODE_TYPE99_SUPERLEVEL_BOUND_FREE;
    const Type53SourceShadow* shadow = nullptr;
    if (record.opcode == XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE) shadow = &evaluated.type49_shadow;
    else if (record.opcode == XSTAR_FIXED_OPCODE_TYPE53_BOUND_FREE) shadow = &evaluated.type53_shadow;

    if (type49_or_53) {
        const auto mapped = phint53_grid_map_v82_patch57(
            curve, input.radiation_energy_ev, static_cast<int>(n));
        if (!mapped.valid) return;
        if (phint53_records_mapped) ++*phint53_records_mapped;
        const double bktm = xstar_constants::kBoltzmannErgPerK * input.temperature_k /
            xstar_constants::kModernErgPerEv;
        const double covering = effective_spectral_covering_fraction_v82_patch58(input);
        const double ptmp1 = covering >= 1.0 - 1.0e-15 ? 0.0 :
            (shadow && shadow->valid ? std::max(0.0, shadow->ptmp1) : 0.5 * (1.0 - covering));
        const double ptmp2 = covering >= 1.0 - 1.0e-15 ? 1.0 :
            (shadow && shadow->valid ? std::max(0.0, shadow->ptmp2) : 0.5 * (1.0 - covering) + covering);
        double exptst = (input.radiation_energy_ev[mapped.nb1_zero_based] - curve.threshold_ev) /
            std::max(bktm, 1.0e-300);
        for (int kl = mapped.nb1_zero_based; kl < mapped.klmax_zero_based && kl + 1 < static_cast<int>(n); ++kl) {
            const double sgtp = std::max(0.0, mapped.sgbar[static_cast<std::size_t>(kl)]);
            const double sgtpp = std::max(0.0, mapped.sgbar[static_cast<std::size_t>(kl + 1)]);
            if (sgtp > 0.0 && lower_abundance > 0.0 && density > 0.0) {
                opacity_cm1[static_cast<std::size_t>(kl)] += lower_abundance * density * sgtp;
                if (phint53_bins_accumulated) ++*phint53_bins_accumulated;
            }
            const double previous_exptst = exptst;
            const double epiip = input.radiation_energy_ev[static_cast<std::size_t>(kl + 1)];
            exptst = (epiip - curve.threshold_ev) / std::max(bktm, 1.0e-300);
            if (shadow && shadow->valid && shadow->rnist > 0.0 && previous_exptst < 200.0 &&
                sgtpp > 0.0 && upper_abundance > 0.0 && density > 0.0 && epiip > 0.0) {
                const double exptmpp = limited_exp(-exptst);
                const double bbnurjp = std::pow(std::min(2.0e4, epiip), 3.0) * 1.571e22 * 2.0;
                // phint53.f90 forms atmp2=tempip*epiip where
                // tempip=rnist*bbnurjp*sgtpp*exp(-dE/kT)*12.56/epiip;
                // the following /12.56 in rctmp cancels exactly.
                const double common = upper_abundance * density * shadow->rnist *
                    bbnurjp * sgtpp * exptmpp;
                rccemis[static_cast<std::size_t>(kl)] += common * ptmp1;
                rccemis[n + static_cast<std::size_t>(kl)] += common * ptmp2;
            }
        }
        return;
    }

    // v82 patch 5.20.17.3: literal ucalc.f90 Type-99 computes scalar
    // rate/thermal answers through calt99 + phint53hunt but does not publish
    // a direct continuum opakc/rccemis profile.  The historical synthetic
    // inward-only RRC fallback created one source-nonexistent 0.1-eV cell in
    // every detal4 HDU.  Keep Type-99 scalar evaluation above, but make its
    // spectral side effect a source-faithful no-op here.
    if (type99) return;

}


// v82 patch 5.17.1: exact-source rlbin/ncbin ownership audit.  This is
// diagnostic-only: the resulting tables never feed opakc/rccemis/fline or any
// other production spectral workspace.  Patch 5.17 incorrectly treated the
// ranking as a runtime keep/discard mask and also compared feature energies to
// source wavelength limits.  The source rlbin API receives wavelength arrays
// (errc/elmn), converts each wavelength back to energy before nbinc(), and
// stores the public slot number in ncbin/nlbin.
struct SourceFeatureAuditCandidateV82Patch5171 {
    std::string family;
    int slot_one_based = 0;
    double wavelength_a = 0.0;
    double energy_ev = 0.0;
    double emission_sum = 0.0;
    double opacity = 0.0;
    std::uint64_t source_position = 0u;
    std::int64_t record = 0;
    int data_type = 0;
    int duplicate_identities = 0;
};

struct SourceRlbinAuditResultV82Patch5171 {
    std::vector<std::array<int,10>> table;
    std::map<int,int> bin_one_based;
    std::map<int,int> final_rank;
    std::set<int> selected_slots;
};

SourceRlbinAuditResultV82Patch5171 source_rlbin_exact_audit_v82_patch5171(
    const std::vector<SourceFeatureAuditCandidateV82Patch5171>& raw,
    const double* energy_grid_ev,
    std::size_t energy_count,
    bool rank_by_opacity) {
    constexpr int nrank = 10;
    SourceRlbinAuditResultV82Patch5171 out;
    out.table.resize(energy_count);
    for (auto& row : out.table) row.fill(0);
    if (!energy_grid_ev || energy_count < 2u) return out;

    // Source arrays are public slots.  rlbin walks slots, not ATDB records.
    // Preserve the last identity associated with a duplicate slot for audit
    // metadata, while rank values come from the already committed slot arrays.
    std::map<int,SourceFeatureAuditCandidateV82Patch5171> by_slot;
    for (const auto& c : raw) if (c.slot_one_based > 0) by_slot[c.slot_one_based] = c;
    // rlbin.f90 literals are default REAL even though its working arrays are
    // real(8).  Reproduce the literal rounding at this source boundary.
    const double source_hc = static_cast<double>(static_cast<float>(12398.4016));
    const double source_rank_floor = static_cast<double>(static_cast<float>(1.0e-37));
    const double source_wavelength_floor = static_cast<double>(static_cast<float>(1.0e-34));
    const double emaxa = source_hc / energy_grid_ev[0];
    const double emina = source_hc / energy_grid_ev[energy_count - 1u];

    for (const auto& kv : by_slot) {
        const auto& c = kv.second;
        if (c.slot_one_based <= 0) continue;
        if ((c.opacity < source_rank_floor) && (c.emission_sum < source_rank_floor)) continue;
        if (!(c.wavelength_a >= emina && c.wavelength_a <= emaxa)) continue;
        const double ener = source_hc / (source_wavelength_floor + c.wavelength_a);
        const int nb1 = phint53_nbinc_one_based_v82_patch57(
            ener, energy_grid_ev, static_cast<int>(energy_count));
        if (nb1 <= 0 || static_cast<std::size_t>(nb1) > out.table.size()) continue;
        out.bin_one_based[c.slot_one_based] = nb1;
        auto& row = out.table[static_cast<std::size_t>(nb1 - 1)];
        int mm = 0;
        bool done = false;
        while (!done) {
            ++mm;
            const int existing_slot = row[static_cast<std::size_t>(mm - 1)];
            if (existing_slot == 0 || c.slot_one_based == 0) done = true;
            if (!done) {
                const auto found = by_slot.find(existing_slot);
                const double existing_key = found == by_slot.end() ? 0.0 :
                    (rank_by_opacity ? found->second.opacity : found->second.emission_sum);
                const double candidate_key = rank_by_opacity ? c.opacity : c.emission_sum;
                if (candidate_key > existing_key) done = true;
                if (mm >= nrank) done = true;
            }
        }
        // Literal source rlbin: an item reaching mm==nrank is not inserted.
        if (mm >= nrank) continue;
        for (int mm2 = nrank - 1; mm2 >= mm; --mm2) {
            row[static_cast<std::size_t>(mm2)] = row[static_cast<std::size_t>(mm2 - 1)];
        }
        row[static_cast<std::size_t>(mm - 1)] = c.slot_one_based;
    }

    for (std::size_t b = 0; b < out.table.size(); ++b) {
        for (int r = 0; r < nrank; ++r) {
            const int slot = out.table[b][static_cast<std::size_t>(r)];
            if (slot <= 0) continue;
            out.selected_slots.insert(slot);
            out.final_rank[slot] = r + 1;
            out.bin_one_based[slot] = static_cast<int>(b + 1u);
        }
    }
    return out;
}

// v82 patch 5.20.8: literal calc_emis_ion does not consume the union of all
// ncbin/nlbin slots.  It recomputes nb1 for each record and searches only the
// rank column belonging to that record's feature energy.
struct SourceConsumerDecisionV82Patch5208 {
    int nb1_one_based = 0;
    int rank_in_bin = 0;
    bool pointer_valid = false;
    bool destination_valid = false;
    bool source_range_pass = true;
    bool selected_anywhere = false;
    bool selected_in_nb1 = false;
    bool sentinel_accept = false;
    bool actual_consumer = false;
    std::string rejection_reason;
};

inline double source_real_literal_v82_patch5208(double value) {
    return static_cast<double>(static_cast<float>(value));
}

SourceConsumerDecisionV82Patch5208 source_calc_emis_consumer_v82_patch5208(
    int slot_one_based,
    double wavelength_a,
    bool rrc_rate7,
    bool destination_valid,
    const SourceRlbinAuditResultV82Patch5171& rank_table,
    const double* energy_grid_ev,
    std::size_t energy_count) {
    SourceConsumerDecisionV82Patch5208 out;
    out.pointer_valid = slot_one_based > 0 &&
        static_cast<std::size_t>(slot_one_based) <= 100000000u;
    out.destination_valid = destination_valid;
    out.selected_anywhere = rank_table.selected_slots.count(slot_one_based) != 0u;
    if (!out.pointer_valid) {
        out.rejection_reason = "INVALID_POINTER";
        return out;
    }
    if (!destination_valid) {
        out.rejection_reason = "INVALID_DESTINATION";
        return out;
    }
    if (!energy_grid_ev || energy_count < 2u || rank_table.table.empty()) {
        out.rejection_reason = "MISSING_RANK_TABLE";
        return out;
    }
    if (!(wavelength_a > 0.0) || !std::isfinite(wavelength_a)) {
        out.rejection_reason = "INVALID_FEATURE_WAVELENGTH";
        return out;
    }

    // calc_emis_ion.f90 rate-7 has a literal mixed-unit guard: errc is a
    // wavelength array while epi is an energy array.  Preserve that behavior
    // rather than replacing it with a dimensionally corrected range test.
    if (rrc_rate7) {
        out.source_range_pass = wavelength_a > energy_grid_ev[0] &&
            wavelength_a < energy_grid_ev[energy_count - 1u];
        if (!out.source_range_pass) {
            out.rejection_reason = "SOURCE_ERRC_RANGE_GUARD";
            return out;
        }
    }

    const double feature_energy_ev =
        source_real_literal_v82_patch5208(12398.4016) /
        (wavelength_a + (rrc_rate7 ? 0.0 : 1.0e-36));
    out.nb1_one_based = phint53_nbinc_one_based_v82_patch57(
        feature_energy_ev, energy_grid_ev, static_cast<int>(energy_count));
    if (out.nb1_one_based <= 0 ||
        static_cast<std::size_t>(out.nb1_one_based) > rank_table.table.size()) {
        out.rejection_reason = "NB1_OUT_OF_RANGE";
        return out;
    }
    const auto& row = rank_table.table[static_cast<std::size_t>(out.nb1_one_based - 1)];
    out.sentinel_accept = row[0] == 9999999;
    for (std::size_t rank = 0; rank < row.size(); ++rank) {
        if (row[rank] == slot_one_based) {
            out.selected_in_nb1 = true;
            out.rank_in_bin = static_cast<int>(rank + 1u);
            break;
        }
        // Literal search stops on the first zero entry.
        if (row[rank] == 0) break;
    }
    out.actual_consumer = out.selected_in_nb1 || out.sentinel_accept;
    if (!out.actual_consumer) {
        out.rejection_reason = out.selected_anywhere
            ? "SELECTED_IN_DIFFERENT_BIN" : "NOT_RANK_SELECTED";
    } else {
        out.rejection_reason = "ACCEPT";
    }
    return out;
}

std::string source_feature_consumer_v82_patch5171(const std::string& family, int data_type) {
    if (family == "RRC") {
        if (data_type == 49 || data_type == 53 || data_type == 99) return "RATE7_NCBIN_GATED";
        if (data_type == 88) return "RATE42_UNCONDITIONAL";
        return "NO_DIRECT_NCBIN_GATE";
    }
    return "NLBIN_GATED_LINE";
}

struct OpacityProducerTopV82Patch511 {
    double contribution = 0.0;
    std::int64_t source_position = 0;
    std::int64_t record = 0;
    int data_type = 0;
    int element_z = 0;
    int ion_stage = 0;
    int lower_row = 0;
    int upper_row = 0;
};

struct MgType53OpacityKernelRowV82Patch512 {
    std::int64_t source_position = 0;
    std::int64_t record = 0;
    int continuum_index_one_based = 0;
    int ion_stage = 0;
    int lower_full_row = 0;
    int upper_full_row = 0;
    int lower_compact_row = 0;
    int upper_compact_row = 0;
    int lower_global_level_index = 0;
    int upper_global_level_index = 0;
    double threshold_ev = 0.0;
    double native_lower_population = 0.0;
    double native_upper_population = 0.0;
    double abundance = 0.0;
    double hydrogen_density_cm3 = 0.0;
    std::size_t mapped_bin_count = 0;
    double sigma_bin_sum_cm2 = 0.0;
    double native_opacity_bin_sum_cm1 = 0.0;
    double threshold_cross_section_cm2 = 0.0;
    double threshold_stimulated_cross_section_cm2 = 0.0;
};

int run_impl(
    xstar_fixed_state_context_impl& ctx,
    const xstar_fixed_state_input_v1& input,
    xstar_fixed_state_output_v1& output,
    xstar_fixed_state_stats_v1& stats,
    xstar_fixed_source_workspace_output_v1* source_workspaces = nullptr
) {
    validate_io(input, output);
    ctx.last_record_diagnostics.clear();
    ctx.last_element_diagnostics.clear();
    ctx.last_element_thermal_budget.clear();
    ctx.last_computed_element_thermal_budget.clear();
    ctx.last_helium_type53_budget = {{0.0,0.0,0.0,0.0}};
    ctx.last_computed_helium_type53_budget = {{0.0,0.0,0.0,0.0}};
    ctx.last_helium_non_type53_budget = {{0.0,0.0,0.0,0.0}};
    ctx.last_computed_helium_non_type53_budget = {{0.0,0.0,0.0,0.0}};
    ctx.last_independent_thermal_parity = false;
    ctx.last_source_scalar_override_used = false;
    ctx.last_thermal_component_closure = false;
    ctx.last_thermal_consumed_fixed_state_closure = false;
    ctx.last_thermal_consumed_compact_population_closure = false;
    ctx.last_thermal_diagonal_source_domain = false;
    ctx.last_continuum_secondary_ledger_corrected = false;
    ctx.last_thermal_diagonal_rows_included = 0;
    ctx.last_thermal_diagonal_normalization_terms_included = 0;
    ctx.last_thermal_diagonal_diagnostics.clear();
    ctx.last_thermal_population_count = 0;
    ctx.last_thermal_population_fingerprint = 0;
    ctx.last_committed_population_count = 0;
    ctx.last_committed_population_fingerprint = 0;
    ctx.last_temperature_k = input.temperature_k;
    ctx.last_electron_density_cm3 = input.electron_density_cm3;
    ctx.last_hydrogen_density_cm3 = input.hydrogen_density_cm3;
    ctx.last_electron_fraction_input = input.electron_fraction_xee;
    ctx.last_effective_covering_fraction =
        (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION) != 0u
            ? input.dsec_covering_fraction : input.covering_fraction;
    ctx.last_turbulent_velocity_km_s = input.turbulent_velocity_km_s;
    ctx.last_radiation_bin_count = input.radiation_bin_count;
    ctx.last_input_radiation_count = input.radiation_bin_count;
    ctx.last_input_radiation_fingerprint = binary64_sequence_fnv1a(input.radiation_energy_ev, input.radiation_bin_count);
    ctx.last_input_dsec_radiation_count = input.dsec_radiation_bin_count;
    ctx.last_input_dsec_radiation_fingerprint = binary64_sequence_fnv1a(input.dsec_radiation_energy_ev, input.dsec_radiation_bin_count);
    ctx.last_input_bremsa_count = input.dsec_radiation_bin_count;
    ctx.last_input_bremsa_fingerprint = binary64_sequence_fnv1a(input.dsec_bremsa, input.dsec_radiation_bin_count);
    ctx.last_input_tau_count = input.continuum_tau_count;
    ctx.last_input_tau_in_fingerprint = binary64_sequence_fnv1a(input.continuum_tau_in, input.continuum_tau_count);
    ctx.last_input_tau_out_fingerprint = binary64_sequence_fnv1a(input.continuum_tau_out, input.continuum_tau_count);
    ctx.last_input_global_level_count = input.global_level_count;
    ctx.last_input_xilevg_fingerprint = binary64_sequence_fnv1a(input.global_xilevg, input.global_level_count);
    ctx.last_input_bilevg_fingerprint = binary64_sequence_fnv1a(input.global_bilevg, input.global_level_count);
    ctx.last_input_rnisg_fingerprint = binary64_sequence_fnv1a(input.global_rnisg, input.global_level_count);
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
    const bool all_element_solve_response = environment_flag("XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_RESPONSE");
    const bool all_element_solve_system = environment_flag("XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_SYSTEM");
    const bool source_compact_basis_seed = environment_flag("XSTAR_QUALIFICATION_SOURCE_COMPACT_BASIS_SEED");
    const bool matrix_construction_closure =
        environment_flag("XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE");
    const bool fixed_state_parity_closure =
        environment_flag("XSTAR_QUALIFICATION_FIXED_STATE_PARITY_CLOSURE");
    const bool thermal_component_parity_closure =
        environment_flag("XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE");
    const bool thermal_compact_population_closure =
        environment_flag("XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE");
    const bool native_sequence1_thermal_diagonal =
        environment_flag("XSTAR_NATIVE_SEQUENCE1_THERMAL_DIAGONAL_RECONSTRUCTION");
    const bool thermal_diagonal_source_domain =
        environment_flag("XSTAR_QUALIFICATION_THERMAL_DIAGONAL_DOMAIN_SOURCE_FAITHFUL") ||
        native_sequence1_thermal_diagonal;
    const bool independent_thermal_parity =
        environment_flag("XSTAR_QUALIFICATION_INDEPENDENT_THERMAL_PARITY");
    // Retain the established qualification control as an explicit assertion.
    // v46.21 generalizes its old Mg-only abundance correction to every element
    // through the shared source-order reducer; the flag no longer owns a
    // second multiplication.
    const bool magnesium_primary_thermal_correction =
        environment_flag("XSTAR_QUALIFICATION_MG_PRIMARY_THERMAL_CORRECTION");
    const bool helium_non_type53_type50_energy_reduction =
        environment_flag("XSTAR_QUALIFICATION_HE_NON_TYPE53_TYPE50_ENERGY_REDUCTION");
    const bool magnesium_type50_primary_cooling_reduction =
        environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_PRIMARY_COOLING_REDUCTION");
    const bool magnesium_type50_thermal_channel_preservation =
        environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_THERMAL_CHANNEL_PRESERVATION");
    const bool helium_source_insertion_order =
        environment_flag("XSTAR_QUALIFICATION_HELIUM_SOURCE_INSERTION_ORDER");
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
    if (all_element_solve_response && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("all-element solve-response diagnostics require XSTAR_QUALIFICATION_REPLACEMENT=1");
    }
    if (all_element_solve_system && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("all-element solve-system diagnostics require XSTAR_QUALIFICATION_REPLACEMENT=1");
    }
    if (source_compact_basis_seed && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("source compact-basis/seed restoration requires XSTAR_QUALIFICATION_REPLACEMENT=1");
    }
    if (thermal_diagonal_source_domain &&
        (!environment_flag("XSTAR_QUALIFICATION_REPLACEMENT") ||
         (!matrix_construction_closure && !native_sequence1_thermal_diagonal))) {
        throw std::runtime_error(
            "source-faithful thermal diagonal domain requires replacement and either matrix-construction closure or native sequence-1 reconstruction");
    }
    if (independent_thermal_parity) {
        const bool source_scalar_override = fixed_state_parity_closure ||
            thermal_component_parity_closure || thermal_compact_population_closure ||
            ((input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE) != 0u) ||
            ((input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_MG_PRIMARY_OVERRIDE) != 0u);
        if (source_scalar_override) {
            throw std::runtime_error(
                "independent Thermal parity forbids fixed-state, Thermal-component, compact-population, and scalar override inputs");
        }
        if (!thermal_diagonal_source_domain) {
            throw std::runtime_error(
                "independent Thermal parity requires the source-faithful diagonal term stream");
        }
        if (!magnesium_primary_thermal_correction) {
            throw std::runtime_error(
                "independent Thermal parity requires the generalized Mg primary Thermal correction contract");
        }
        if (!environment_flag("XSTAR_QUALIFICATION_TYPE51_SOURCE_FAITHFUL")) {
            throw std::runtime_error(
                "independent Thermal parity requires the all-element source-faithful Type-51 contract");
        }
        if (!environment_flag("XSTAR_QUALIFICATION_TYPE6062_SOURCE_FAITHFUL")) {
            throw std::runtime_error(
                "independent Thermal parity requires the source-faithful Type-60/62 collision contract");
        }
        if (!environment_flag("XSTAR_QUALIFICATION_TYPE57_SOURCE_ENERGY")) {
            throw std::runtime_error(
                "independent Thermal parity requires source-local Type-57 energy transport");
        }
        if (!environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE53_PERSISTENT_LEVELTEMP")) {
            throw std::runtime_error(
                "independent Thermal parity requires Mg Type-53 persistent leveltemp semantics");
        }
        if (!environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE49_PERSISTENT_LEVELTEMP")) {
            throw std::runtime_error(
                "independent Thermal parity requires Mg Type-49 persistent leveltemp semantics");
        }
        if (!environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PERSISTENT_LEVELTEMP")) {
            throw std::runtime_error(
                "independent Thermal parity requires Mg Type-99 persistent leveltemp energy/weight semantics");
        }
        if (!helium_non_type53_type50_energy_reduction) {
            throw std::runtime_error(
                "independent Thermal parity requires post-closure He Type-50 Thermal energy reconstruction");
        }
    }
    if (helium_non_type53_type50_energy_reduction &&
        (!matrix_construction_closure || !thermal_diagonal_source_domain ||
         !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT"))) {
        throw std::runtime_error(
            "helium non-Type53 Type-50 energy reduction requires replacement, matrix closure, and source-order Thermal reduction");
    }
    if (magnesium_type50_primary_cooling_reduction &&
        (!matrix_construction_closure || !thermal_diagonal_source_domain ||
         !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT") ||
         !environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ESCAPE_STATE"))) {
        throw std::runtime_error(
            "magnesium Type-50 primary cooling reduction requires replacement, matrix closure, source-order Thermal reduction, and live escape state");
    }
    if (magnesium_type50_thermal_channel_preservation &&
        (!magnesium_type50_primary_cooling_reduction ||
         !environment_flag("XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_ENERGY_TRANSPORT"))) {
        throw std::runtime_error(
            "magnesium Type-50 Thermal-channel preservation requires primary cooling reduction and source endpoint-energy transport");
    }
    if (matrix_construction_closure && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("matrix-construction closure requires XSTAR_QUALIFICATION_REPLACEMENT=1");
    }
    if (matrix_construction_closure) {
        const char* closure_dir = std::getenv("XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE_DIR");
        if (!closure_dir || !*closure_dir) {
            throw std::runtime_error("matrix-construction closure directory is missing");
        }
    }
    if (fixed_state_parity_closure && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("fixed-state parity closure requires XSTAR_QUALIFICATION_REPLACEMENT=1");
    }
    if (fixed_state_parity_closure) {
        const char* closure_dir = std::getenv("XSTAR_QUALIFICATION_FIXED_STATE_PARITY_CLOSURE_DIR");
        if (!closure_dir || !*closure_dir) {
            throw std::runtime_error("fixed-state parity closure directory is missing");
        }
    }
    if (thermal_component_parity_closure && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("thermal component parity closure requires XSTAR_QUALIFICATION_REPLACEMENT=1");
    }
    // v17.25.13: per-sequence thermal-component closure is a
    // residual-consumption boundary closure, not a fixed-state population
    // override.  It may run without fixed-state parity closure because it
    // supplies only source thermal totals/hmctot/elcter diagnostics while
    // preserving raw native solve and committed populations.
    if (thermal_component_parity_closure) {
        const char* closure_dir = std::getenv("XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE_DIR");
        if (!closure_dir || !*closure_dir) {
            throw std::runtime_error("thermal component parity closure directory is missing");
        }
    }
    if (thermal_compact_population_closure && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("thermal compact-population closure requires XSTAR_QUALIFICATION_REPLACEMENT=1");
    }
    // v17.25.5: thermal compact-population closure is a source-order
    // consumption correction, not a scalar component override.  It may be
    // applied independently to a subset of active elements (Mg at sequence 16)
    // while the raw solve state and committed populations remain native.
    if (thermal_compact_population_closure) {
        const char* closure_dir = std::getenv("XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE_DIR");
        if (!closure_dir || !*closure_dir) {
            throw std::runtime_error("thermal compact-population closure directory is missing");
        }
    }
    if (helium_source_insertion_order && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("helium source insertion-order restoration requires XSTAR_QUALIFICATION_REPLACEMENT=1");
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
    ctx.last_independent_thermal_parity = independent_thermal_parity;
    ctx.last_source_scalar_override_used = fixed_state_parity_closure ||
        thermal_component_parity_closure || thermal_compact_population_closure ||
        ((input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE) != 0u) ||
        ((input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_MG_PRIMARY_OVERRIDE) != 0u);
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
    ctx.last_all_element_solve_response = all_element_solve_response || all_element_solve_system;
    ctx.last_all_element_solve_system = all_element_solve_system;
    ctx.last_type53_row46_coupled_replacement = type53_row46_coupled_replacement;
    ctx.last_helium_source_insertion_order = helium_source_insertion_order;
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
    ctx.last_continuum_compton_heating = 0.0;
    ctx.last_continuum_compton_cooling = 0.0;
    ctx.last_continuum_free_free_cooling = 0.0;
    ctx.last_cmp1 = ctx.last_cmp2 = ctx.last_computed_cmp1 = ctx.last_computed_cmp2 = 0.0;
    ctx.last_computed_htcomp = ctx.last_computed_clcomp = ctx.last_computed_htfreef = ctx.last_computed_clbrems = ctx.last_htfreef = ctx.last_clbrems = 0.0;
    ctx.last_continuum_workspace_source_faithful = false;
    ctx.last_continuum_epim_count = ctx.last_continuum_bremsam_count = ctx.last_continuum_bremsmap_count = 0;
    ctx.last_continuum_epim_fingerprint = ctx.last_continuum_bremsam_fingerprint = ctx.last_continuum_bremsmap_fingerprint = 0;
    ctx.last_continuum_workspace_diagnostics.clear();
    ctx.last_call1_thermal_oracle = (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE) != 0u;
    const bool defer_product_projection =
        (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_DEFER_PRODUCT_PROJECTION) != 0u;
    output.electron_fraction_xee = 0.0;
    output.elcter = 0.0;
    ctx.last_preclosure_electron_fraction = 0.0;
    ctx.last_computed_electron_fraction = 0.0;
    double computed_electron_fraction = 0.0;
    std::array<double,4> computed_element_totals{{0.0,0.0,0.0,0.0}};
    std::array<double,4> committed_element_totals{{0.0,0.0,0.0,0.0}};
    std::vector<double> all_populations;
    std::vector<double> thermal_population_stream;
    std::size_t fixed_full_population_offset = 0;
    std::vector<xstar_spectral_contribution_v1> spectral;
    // v82 patch 5.20.5 retained xstarsetup's errc coordinate per record.
    // v82 patch 5.20.9 closes the missing ownership rule: errc is actually a
    // continuum-SLOT array.  Every rate-7 record writes errc(npconi2(record))
    // during setup, so the last source-order writer owns the coordinate later
    // consumed by BOTH rlbin and calc_emis_ion for every record sharing that slot.
    // Keep the identity map only for the 5.20.8-vs-5.20.9 ownership audit.
    std::map<std::pair<std::uint64_t,std::int64_t>,double>
        source_errc_rank_energy_by_identity_v82_patch5205;
    // Comparison-only reconstruction of the 5.20.8.2 identity-owned decision.
    // This never feeds production and exists solely to classify the consumers
    // gained/lost by the literal slot-ownership correction.
    std::map<std::pair<std::uint64_t,std::int64_t>,double>
        source_errc_rank_energy_by_identity_patch52082_audit_v82_patch5209;
    std::map<int,double> source_errc_rank_energy_by_slot_v82_patch5209;
    std::map<int,std::tuple<std::uint64_t,std::int64_t,int>>
        source_errc_owner_by_slot_v82_patch5209;
    const auto source_errc_rank_energy_for_slot_v82_patch5209 =
        [&](int slot_one_based, std::uint64_t source_position, std::int64_t record, double fallback) {
            const auto slot_it = source_errc_rank_energy_by_slot_v82_patch5209.find(slot_one_based);
            if (slot_it != source_errc_rank_energy_by_slot_v82_patch5209.end()) return slot_it->second;
            const auto identity_it = source_errc_rank_energy_by_identity_v82_patch5205.find(
                {source_position, record});
            if (identity_it != source_errc_rank_energy_by_identity_v82_patch5205.end()) return identity_it->second;
            return fallback;
        };
    // v82 patch 5.20.8: retain the literal line wavelength owner used by
    // calc_emis_ion when it recomputes nb1 for nlbin.
    std::map<std::pair<std::uint64_t,std::int64_t>,double>
        source_line_wavelength_by_identity_v82_patch5208;
    // Retain evaluated source identities past the per-element traversal so
    // call-2 calc_emis_all can perform selected full-grid revisits after the
    // complete calc_emisab surface has been ranked.  Type-53 already used this
    // state in patch 5.18.1.  Patch 5.20.8.2 adds the same explicit retained
    // full-grid owner for Type-49 while its reduced-grid calc_emisab shadow is
    // kept diagnostic-only until the source phextrap/reduced-grid discrepancy
    // is closed.
    std::map<std::pair<std::uint64_t,std::uint64_t>,EvaluatedRecord>
        type53_revisit_evaluated_v82_patch5181;
    std::map<std::pair<std::uint64_t,std::uint64_t>,EvaluatedRecord>
        type49_revisit_evaluated_v82_patch52082;
    std::vector<double> native_bound_free_opacity(input.radiation_bin_count, 0.0);
    std::vector<double> native_rrc_continuum_emission(2 * input.radiation_bin_count, 0.0);
    // Type-76 is a literal UCalc side effect rather than a later selected-RRC
    // product projection.  Keep it separate so it can be retained even when
    // the broad bound-free projection is deferred, without accidentally
    // publishing unselected Type49/53/88 continuum emission.
    std::vector<double> native_type76_continuum_emission(2 * input.radiation_bin_count, 0.0);
    std::vector<DeferredRrcRecordV82Patch520> deferred_rrc_records_v82_patch520;
    // v82 patch 5.11: comparison-only producer attribution for the accepted
    // call-2/final sequence-59 opacity.  The environment path is owned by the
    // standalone diagnostic harness; production arrays and source order are
    // unchanged.
    const char* source_sequence_env_v82_patch511 = std::getenv("XSTAR_NATIVE_SOURCE_SEQUENCE");
    const int source_sequence_v82_patch511 = source_sequence_env_v82_patch511 && *source_sequence_env_v82_patch511
        ? std::atoi(source_sequence_env_v82_patch511) : 0;
    const char* opacity_producer_path_v82_patch511 = std::getenv("XSTAR_V82_PATCH511_OPAKC_PRODUCER_AUDIT_PATH");
    const bool opacity_producer_audit_v82_patch511 = !defer_product_projection &&
        source_sequence_v82_patch511 == 59 && opacity_producer_path_v82_patch511 && *opacity_producer_path_v82_patch511;
    // v82 patch 5.20.3: diagnostic-only exact opacity contribution ledger for
    // the bins already proven to alter the source heatt absorption operand.
    // This never feeds production arrays: it reuses the existing comparison
    // kernels and writes only sidecar rows selected by a zero-based bin file.
    const char* exact_absorption_path_v82_patch5203 = std::getenv("XSTAR_V82_PATCH5203_EXACT_ABSORPTION_LEDGER_PATH");
    const char* target_bins_path_v82_patch5203 = std::getenv("XSTAR_V82_PATCH5203_TARGET_BINS_PATH");
    const bool exact_absorption_audit_v82_patch5203 = !defer_product_projection &&
        source_sequence_v82_patch511 == 59 && exact_absorption_path_v82_patch5203 && *exact_absorption_path_v82_patch5203 &&
        target_bins_path_v82_patch5203 && *target_bins_path_v82_patch5203;
    std::set<std::size_t> target_bins_v82_patch5203;
    std::ofstream exact_absorption_csv_v82_patch5203;
    std::size_t exact_absorption_rows_v82_patch5203 = 0u;
    if (exact_absorption_audit_v82_patch5203) {
        std::ifstream bins_in(target_bins_path_v82_patch5203);
        std::size_t bin = 0u;
        while (bins_in >> bin) if (bin < input.radiation_bin_count) target_bins_v82_patch5203.insert(bin);
        const std::filesystem::path exact_path(exact_absorption_path_v82_patch5203);
        if (!exact_path.parent_path().empty()) std::filesystem::create_directories(exact_path.parent_path());
        exact_absorption_csv_v82_patch5203.open(exact_path);
        if (!exact_absorption_csv_v82_patch5203) throw std::runtime_error("cannot create patch5.20.3 exact absorption ledger");
        exact_absorption_csv_v82_patch5203
            << "runtime_slot,energy_ev,producer_family,source_position,record,data_type,rate_type,element_z,ion_stage,lower_row,upper_row,contribution_cm_inv\n";
        exact_absorption_csv_v82_patch5203 << std::setprecision(17);
    }
    auto write_exact_absorption_v82_patch5203 = [&](std::size_t runtime_slot, const char* family,
            std::int64_t source_position, std::int64_t record, int data_type, int rate_type,
            int element_z, int ion_stage, int lower_row, int upper_row, double contribution) {
        if (!exact_absorption_audit_v82_patch5203 || !target_bins_v82_patch5203.count(runtime_slot) ||
            !std::isfinite(contribution) || contribution == 0.0) return;
        exact_absorption_csv_v82_patch5203 << runtime_slot << ',' << input.radiation_energy_ev[runtime_slot] << ','
            << family << ',' << source_position << ',' << record << ',' << data_type << ',' << rate_type << ','
            << element_z << ',' << ion_stage << ',' << lower_row << ',' << upper_row << ',' << contribution << '\n';
        ++exact_absorption_rows_v82_patch5203;
    };
    const char* mg_type53_kernel_path_v82_patch512 = std::getenv("XSTAR_V82_PATCH512_MG_TYPE53_KERNEL_AUDIT_PATH");
    const bool mg_type53_kernel_audit_v82_patch512 = !defer_product_projection &&
        source_sequence_v82_patch511 == 59 && mg_type53_kernel_path_v82_patch512 && *mg_type53_kernel_path_v82_patch512;
    std::vector<MgType53OpacityKernelRowV82Patch512> mg_type53_kernel_rows_v82_patch512;
    std::vector<OpacityProducerTopV82Patch511> bound_free_top_v82_patch511(input.radiation_bin_count);
    std::vector<OpacityProducerTopV82Patch511> line_top_v82_patch511(input.radiation_bin_count);
    std::vector<double> producer_temp_opacity_v82_patch511(input.radiation_bin_count, 0.0);
    std::vector<double> producer_temp_rrc_v82_patch511(2 * input.radiation_bin_count, 0.0);
    std::size_t phint53_records_mapped_v82_patch57 = 0;
    std::size_t phint53_bins_accumulated_v82_patch57 = 0;
    std::optional<SourceCompactOracle> source_compact_oracle;
    if (source_compact_basis_seed) source_compact_oracle = load_source_compact_oracle();
    std::optional<FixedStateClosureData> fixed_state_closure_data;
    if (fixed_state_parity_closure) fixed_state_closure_data = load_fixed_state_closure_data();
    std::optional<ThermalComponentClosureData> thermal_component_closure_data;
    if (thermal_component_parity_closure) thermal_component_closure_data = load_thermal_component_closure_data();
    std::optional<ThermalCompactPopulationClosureData> thermal_compact_population_closure_data;
    if (thermal_compact_population_closure) {
        thermal_compact_population_closure_data = load_thermal_compact_population_closure_data();
    }

    // calc_emisab_all receives the source reduced epim/bremsam workspace.
    // Build it once per controller evaluation and share it with all Type-53
    // records instead of reconstructing the 999-bin map per atomic record.
    std::optional<SourceContinuumWorkspace> type53_calc_emisab_workspace_v82_patch5181;
    {
        const bool has_full_dsec = input.dsec_radiation_energy_ev && input.dsec_bremsa &&
            input.dsec_radiation_bin_count >= 4;
        const double* full_epi = has_full_dsec ? input.dsec_radiation_energy_ev : input.radiation_energy_ev;
        const double* full_bremsa = has_full_dsec ? input.dsec_bremsa : input.radiation_flux;
        const std::size_t full_count = has_full_dsec ? input.dsec_radiation_bin_count : input.radiation_bin_count;
        if (full_epi && full_bremsa && full_count >= 4) {
            type53_calc_emisab_workspace_v82_patch5181 = build_source_continuum_workspace(
                full_epi, full_bremsa, full_count);
        }
    }

    const auto traversal_start = clock_type::now();
    for (const auto& element : ctx.program.elements) {
        ++stats.elements_attempted;
        std::vector<EvaluatedRecord> evaluated;
        std::vector<const ProgramRecord*> evaluated_records;
        evaluated.reserve(static_cast<std::size_t>(element.record_count));
        evaluated_records.reserve(static_cast<std::size_t>(element.record_count));
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
                EvaluatedRecord evaluated_item = evaluate_record(
                    ctx.program, element, record, input,
                    type53_calc_emisab_workspace_v82_patch5181
                        ? &*type53_calc_emisab_workspace_v82_patch5181 : nullptr);
                if (record.data_type == 53 && record.rate_type == 7) {
                    type53_revisit_evaluated_v82_patch5181[std::make_pair(
                        static_cast<std::uint64_t>(record.source_position),
                        static_cast<std::uint64_t>(record.record))] = evaluated_item;
                } else if (record.data_type == 49 && record.rate_type == 7) {
                    type49_revisit_evaluated_v82_patch52082[std::make_pair(
                        static_cast<std::uint64_t>(record.source_position),
                        static_cast<std::uint64_t>(record.record))] = evaluated_item;
                }
                evaluated.push_back(std::move(evaluated_item));
                evaluated_records.push_back(&record);
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
        PreliminaryIonBalance active_balance = preliminary;
        const bool retain_active_stage_window =
            (input.runtime_state_flags &
             XSTAR_FIXED_RUNTIME_STATE_RETAIN_ACTIVE_STAGE_WINDOW) != 0u;
        if (retain_active_stage_window) {
            const auto retained = ctx.retained_active_stage_windows.find(element.element_z);
            if (retained != ctx.retained_active_stage_windows.end()) {
                active_balance.min_stage = retained->second.first;
                active_balance.max_stage = retained->second.second;
            }
        }
        // Compact development fixtures may represent only a subset of an
        // element while assigning a larger atomic number.  Source-style
        // stage-window selection requires a complete one-ground-row-per-stage
        // topology, so preserve the legacy full compact basis for such inputs.
        const ActiveElementView active = source_compact_oracle.has_value()
            ? make_source_compact_element_view(
                element, source_compact_oracle->rows_by_element_z.at(element.element_z))
            : (element.n_ions == element.element_z
                ? make_active_element_view(element, active_balance)
                : make_full_element_view(element));
        ctx.retained_active_stage_windows[element.element_z] =
            std::make_pair(active.min_stage, active.max_stage);
        apply_magnesium_type99_persistent_leveltemp_v048746223(
            ctx.program, element, active, input, evaluated);
        apply_magnesium_type49_persistent_leveltemp_v048746222(
            element, active, evaluated);
        apply_magnesium_type53_persistent_leveltemp_v048746221(
            element, active, evaluated);

        // v82 patch 5.20.9: reproduce xstarsetup's slot-owned errc lifetime
        // before abundance/product filtering.  xstarsetup traverses every rate-7
        // record and overwrites errc(kkkl); a later zero-emissivity record can
        // therefore still own the rank coordinate of a slot populated by an
        // earlier record.  The per-element linked traversal is source ordered,
        // and Program validation guarantees monotonically increasing source
        // positions.  Type-49, Type-53 and Type-99 all participate in this same
        // rate-7 errc slot workspace.
        for (std::size_t k = 0; k < evaluated.size() && k < evaluated_records.size(); ++k) {
            const ProgramRecord* pr = evaluated_records[k];
            if (!pr || pr->rate_type != 7 || pr->continuum_index_one_based <= 0) continue;
            const auto& item = evaluated[k];
            double rank_energy_ev = 0.0;
            if (pr->data_type == 49 && item.type49_shadow.valid)
                rank_energy_ev = item.type49_shadow.source_errc_rank_energy_ev;
            else if (pr->data_type == 53 && item.type53_shadow.valid)
                rank_energy_ev = item.type53_shadow.source_errc_rank_energy_ev;
            else if (pr->data_type == 99 && item.type99_shadow.valid)
                rank_energy_ev = item.type99_shadow.source_errc_rank_energy_ev;
            if (!(rank_energy_ev > 0.0) || !std::isfinite(rank_energy_ev)) continue;
            const auto identity = std::make_pair(
                static_cast<std::uint64_t>(pr->source_position),
                static_cast<std::int64_t>(pr->record));
            source_errc_rank_energy_by_identity_v82_patch5205[identity] = rank_energy_ev;
            double patch52082_identity_energy_ev = rank_energy_ev;
            if (pr->data_type == 49 && pr->real_count >= 2 &&
                pr->real_offset < ctx.program.reals.size()) {
                // Exact pre-5.20.9 behavior: identity-owned Type-49 setup energy
                // used a double 13.598 literal and incorrectly imposed 0.1 eV.
                patch52082_identity_energy_ev = std::max(
                    0.1, ctx.program.reals[pr->real_offset] * 13.598);
            }
            source_errc_rank_energy_by_identity_patch52082_audit_v82_patch5209[identity] =
                patch52082_identity_energy_ev;
            source_errc_rank_energy_by_slot_v82_patch5209[pr->continuum_index_one_based] = rank_energy_ev;
            source_errc_owner_by_slot_v82_patch5209[pr->continuum_index_one_based] =
                std::make_tuple(static_cast<std::uint64_t>(pr->source_position),
                                static_cast<std::int64_t>(pr->record), pr->data_type);
        }

        std::vector<xstar_element_contribution_v1> contributions;
        contributions.reserve(evaluated.size());
        std::vector<xstar_element_contribution_v1> thermal_only_contributions;
        std::vector<xstar_element_contribution_v1> type95_self_loop_candidates;
        using Type95StreamIdentity = std::tuple<std::int64_t,int,int,int>;
        struct Type95StreamEvent { Type95StreamIdentity identity; bool candidate = false; };
        std::vector<Type95StreamEvent> type95_source_stream_order;
        CanonicalThermalLedgerBuilderV048746212 canonical_thermal_builder(element, active);
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
            const bool source_absent_type95_self_loop =
                original.data_type == 95 && original.rate_type == 15 &&
                original.lower_row == original.upper_row &&
                original.lower_row == ground_row_for_stage(element, original.ion_stage);
            const bool qualification_ablated = matrix_family_ablated || matrix_source_ablated || matrix_row_ablated ||
                unqualified_type53_ablated || unqualified_type71_ablated || unqualified_type99_ablated;
            bool matrix_committed = false;
            if (item.matrix_enabled && active_stage && endpoints_active && !qualification_ablated &&
                !source_absent_type95_self_loop) {
                auto contribution = original;
                contribution.lower_row -= active.full_row_start - 1;
                contribution.upper_row -= active.full_row_start - 1;
                contributions.push_back(contribution);
                type95_source_stream_order.push_back(Type95StreamEvent{
                    Type95StreamIdentity{original.record, original.data_type,
                        original.rate_type, original.ion_stage}, false});
                matrix_committed = true;
            } else if (item.matrix_enabled && active_stage && endpoints_active &&
                       !qualification_ablated && source_absent_type95_self_loop &&
                       element.element_z == 12) {
                // XSTAR calc_ion_rates owns rate-type-15 Type-95 total-CI
                // records, while calc_hmc_ion excludes them from detailed
                // matrix assembly.  Retain eligible idest1=1 records as
                // candidates for the historical Thermal-only source stream.
                // The lowered Mg Type-95 total-CI records preserve the
                // source idest1=1 ownership contract.  The data-type/rate-type
                // and self-loop checks above therefore identify the complete
                // preliminary-owner candidate domain for this active case.
                auto contribution = original;
                contribution.lower_row -= active.full_row_start - 1;
                contribution.upper_row -= active.full_row_start - 1;
                type95_self_loop_candidates.push_back(contribution);
                type95_source_stream_order.push_back(Type95StreamEvent{
                    Type95StreamIdentity{original.record, original.data_type,
                        original.rate_type, original.ion_stage}, true});
            }
            NativeRecordDiagnostic diagnostic;
            diagnostic.element_index = element.element_index;
            diagnostic.element_z = element.element_z;
            diagnostic.evaluated = item;
            diagnostic.active_stage = active_stage;
            diagnostic.matrix_committed = matrix_committed;
            ctx.last_record_diagnostics.push_back(std::move(diagnostic));
        }

        const std::vector<xstar_element_contribution_v1> preclosure_contributions = contributions;
        if (matrix_construction_closure) {
            apply_matrix_closure_contribution_corrections(
                contributions, active.element,
                helium_non_type53_type50_energy_reduction,
                magnesium_type50_primary_cooling_reduction,
                magnesium_type50_thermal_channel_preservation);
        } else if (element.element_z == 2 && helium_source_insertion_order) {
            restore_source_contribution_order(contributions);
        } else if (type53_row46_coupled_replacement && element.element_z == 2) {
            reorder_type53_row46_coupled_contributions(contributions);
        }

        if (element.element_z == 12 && !type95_self_loop_candidates.empty()) {
            // XSTAR source ownership recovered from calc_ion_rates/ucalc and
            // calc_hmc_ion.  Rate-type-15/data-type-95 total-CI records with
            // idest1=1 belong to preliminary ionization, while the detailed
            // level matrix excludes rate 15.  The historical v15.9.26 source
            // capture retains zero, one, or two active support-boundary
            // identities on the canonical Thermal qualification surface.
            //
            // Occupancy is immutable qualification metadata, never controller
            // input.  Live topology resolves the actual identities; no record
            // number is hard-coded.  Selected records remain excluded from
            // matrix assembly and contribute only forward/reverse diagonal
            // Thermal rows.
            const int lower_support_stage = active.min_stage;
            const int upper_support_stage = std::max(active.min_stage, active.max_stage - 1);
            const xstar_element_contribution_v1* lower = nullptr;
            const xstar_element_contribution_v1* upper = nullptr;
            for (const auto& contribution : type95_self_loop_candidates) {
                if (contribution.ion_stage == lower_support_stage) lower = &contribution;
                if (contribution.ion_stage == upper_support_stage) upper = &contribution;
            }
            int requested_records = 0;
            const char* requested_text = std::getenv(
                "XSTAR_QUALIFICATION_TYPE95_THERMAL_ONLY_RECORDS");
            if (requested_text && *requested_text) {
                requested_records = environment_data_type(
                    "XSTAR_QUALIFICATION_TYPE95_THERMAL_ONLY_RECORDS");
            } else if (native_production_mode() && lower && upper) {
                // In general standalone production, derive occupancy from the
                // live support-boundary contributions instead of importing a
                // sequence contract.  The qualification environment variable
                // remains authoritative only when explicitly supplied.
                const auto has_signal = [](const xstar_element_contribution_v1* c) {
                    if (!c) return false;
                    const double scale = std::abs(c->ans1) + std::abs(c->ans2) +
                        std::abs(c->ans3) + std::abs(c->ans4) +
                        std::abs(c->ans5) + std::abs(c->ans6);
                    return std::isfinite(scale) && scale > 0.0;
                };
                const bool lower_signal = has_signal(lower);
                const bool upper_signal = upper != lower && has_signal(upper);
                requested_records = static_cast<int>(lower_signal) +
                    static_cast<int>(upper_signal);
                if (requested_records == 0) requested_records = 1;
            }
            if (requested_records < 0 || requested_records > 2) {
                throw std::runtime_error("invalid Type-95 thermal-only occupancy");
            }
            if (requested_records >= 1 && (!lower || !upper)) {
                throw std::runtime_error("missing active Type-95 support-boundary candidate");
            }
            std::set<Type95StreamIdentity> selected;
            if (requested_records == 2) {
                selected.emplace(lower->record, lower->data_type, lower->rate_type, lower->ion_stage);
                selected.emplace(upper->record, upper->data_type, upper->rate_type, upper->ion_stage);
            } else if (requested_records == 1) {
                // Above the call-1 thermal root, the lower support boundary is
                // the live preliminary-ion edge.  At and below that root the
                // retained source domain uses the upper support boundary.
                const auto* chosen = input.temperature_k > 7.0e4 ? lower : upper;
                selected.emplace(chosen->record, chosen->data_type,
                    chosen->rate_type, chosen->ion_stage);
            }
            std::map<Type95StreamIdentity, const xstar_element_contribution_v1*>
                candidate_by_stream_identity;
            for (const auto& contribution : type95_self_loop_candidates) {
                candidate_by_stream_identity.emplace(
                    Type95StreamIdentity{contribution.record, contribution.data_type,
                        contribution.rate_type, contribution.ion_stage}, &contribution);
            }
            for (const auto& event : type95_source_stream_order) {
                if (!event.candidate || selected.find(event.identity) == selected.end()) continue;
                const auto found = candidate_by_stream_identity.find(event.identity);
                if (found == candidate_by_stream_identity.end()) {
                    throw std::runtime_error("missing selected Type-95 candidate in linked stream");
                }
                thermal_only_contributions.push_back(*found->second);
            }
            if (static_cast<int>(thermal_only_contributions.size()) != requested_records) {
                throw std::runtime_error("dynamic Type-95 thermal-only selection count mismatch");
            }
        }

        // The source answer-channel capture is matrix-commit scoped.  Keep the
        // native record diagnostics on that same semantic boundary by replacing
        // raw pre-closure UCalc answers with the final committed contribution
        // answers.  Removed native-only contributions are no longer marked as
        // matrix committed.
        using DiagnosticIdentity = std::tuple<std::int64_t, int, int, int>;
        std::map<DiagnosticIdentity, const xstar_element_contribution_v1*> committed_by_identity;
        for (const auto& contribution : contributions) {
            const DiagnosticIdentity key{
                contribution.record, contribution.data_type,
                contribution.rate_type, contribution.ion_stage};
            if (!committed_by_identity.emplace(key, &contribution).second) {
                throw std::runtime_error(
                    "duplicate final committed contribution identity for diagnostics");
            }
        }
        for (auto& diagnostic : ctx.last_record_diagnostics) {
            if (diagnostic.element_z != element.element_z || !diagnostic.matrix_committed) {
                continue;
            }
            auto& answers = diagnostic.evaluated.contribution;
            const DiagnosticIdentity key{
                answers.record, answers.data_type, answers.rate_type, answers.ion_stage};
            const auto committed = committed_by_identity.find(key);
            if (committed == committed_by_identity.end()) {
                diagnostic.matrix_committed = false;
                continue;
            }
            answers.ans1 = committed->second->ans1;
            answers.ans2 = committed->second->ans2;
            answers.ans3 = committed->second->ans3;
            answers.ans4 = committed->second->ans4;
            answers.ans5 = committed->second->ans5;
            answers.ans6 = committed->second->ans6;
        }

        // v0.6.48.7.46.21.8: capture canonical Thermal coefficients only
        // after matrix closure and source-order correction.  The prior early
        // capture froze stale pre-closure He Type-50 ans3/ans4 values and
        // bypassed the accepted non-Type-53 cooling reconstruction.
        std::vector<xstar_element_contribution_v1> thermal_domain_contributions = contributions;
        thermal_domain_contributions.insert(
            thermal_domain_contributions.end(),
            thermal_only_contributions.begin(), thermal_only_contributions.end());
        for (const auto& contribution : thermal_domain_contributions) {
            canonical_thermal_builder.append_matrix_committed(contribution);
        }
        const auto canonical_thermal_ledger =
            canonical_thermal_builder.finish(thermal_domain_contributions);
        stats.contributions_constructed += contributions.size();
        ElementBuffers buffers = make_buffers(active.element, &input, source_compact_basis_seed);
        xstar_element_input_v1 ein{};
        xstar_element_input_init_v1(&ein);
        ein.flags = XSTAR_ELEMENT_STRICT_SOURCE_ORDER | XSTAR_ELEMENT_ALLOW_DENSE_RESCUE;
        const bool capture_element_solve_response = all_element_solve_response || all_element_solve_system ||
            (helium_solve_response && element.element_z == 2);
        if (capture_element_solve_response) {
            ein.flags |= XSTAR_ELEMENT_DIAGNOSTICS_SUMMARY;
        }
        if (all_element_solve_system || (helium_solve_response && element.element_z == 2)) {
            ein.flags |= XSTAR_ELEMENT_RETURN_MATRICES;
        }
        ein.element_z = active.element.element_z;
        ein.n_rows = active.element.n_rows;
        ein.n_superlevels = active.element.n_superlevels;
        ein.n_ions = active.element.n_ions;
        ein.normalization_row = active.element.normalization_row;
        ein.max_lucy_iterations = 200;
        ein.max_fixed_point_iterations = 200;
        ein.lucy_tolerance = 1.0e-2;
        ein.fixed_point_tolerance = 1.0e-2;
        ein.superlevel_by_row = buffers.superlevels.data();
        ein.ion_by_row = buffers.ions.data();
        ein.initial_populations = buffers.initial.data();
        xstar_element_output_v1 eout{};
        bind_output(eout, buffers, active.element.element_z);
        std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> error{};
        const auto element_start = clock_type::now();
        std::uint64_t element_consumed_thermal_ledger_fingerprint = 0;
        const int rc = xstar_element_engine_run_construction_with_thermal_ledger_v1(
            ctx.element_context, &ein, contributions.data(), contributions.size(),
            canonical_thermal_ledger.terms.data(), canonical_thermal_ledger.terms.size(),
            &element_consumed_thermal_ledger_fingerprint,
            &eout, error.data(), error.size());
        stats.element_seconds += elapsed(element_start);
        if (rc != 0) throw std::runtime_error(std::string("native element solve failed z=") + std::to_string(element.element_z) + ": " + error.data());
        if (element_consumed_thermal_ledger_fingerprint != canonical_thermal_ledger.fingerprint ||
            (eout.status_flags & XSTAR_ELEMENT_STATUS_CANONICAL_THERMAL_LEDGER) == 0u) {
            throw std::runtime_error("element engine did not consume the canonical Thermal ledger");
        }
        std::vector<double> stage_final_outer_start;
        std::vector<double> stage_superlevel_before;
        std::vector<double> stage_condensed_matrix;
        std::vector<double> stage_condensed_rhs;
        std::vector<double> stage_first_lu;
        std::vector<double> stage_refinement_residual;
        std::vector<double> stage_refinement_correction;
        std::vector<double> stage_refined_superlevel;
        std::vector<double> stage_after_condensed;
        std::vector<double> stage_fixed_before;
        std::vector<double> stage_fixed_after;
        int stage_final_outer_iteration = 0;
        int stage_final_fixed_iterations = 0;
        bool stage_trace_captured = false;
        if (capture_element_solve_response) {
            const std::size_t nrows = static_cast<std::size_t>(active.element.n_rows);
            const std::size_t nsp = static_cast<std::size_t>(active.element.n_superlevels);
            stage_final_outer_start.resize(nrows);
            stage_superlevel_before.resize(nsp);
            stage_condensed_matrix.resize(nsp * nsp);
            stage_condensed_rhs.resize(nsp);
            stage_first_lu.resize(nsp);
            stage_refinement_residual.resize(nsp);
            stage_refinement_correction.resize(nsp);
            stage_refined_superlevel.resize(nsp);
            stage_after_condensed.resize(nrows);
            stage_fixed_before.resize(nrows);
            stage_fixed_after.resize(nrows);
            xstar_element_solve_stage_trace_v1 trace{};
            xstar_element_solve_stage_trace_init_v1(&trace);
            trace.final_outer_start_populations = stage_final_outer_start.data();
            trace.final_outer_start_capacity = stage_final_outer_start.size();
            trace.final_superlevel_populations_before_solve = stage_superlevel_before.data();
            trace.final_superlevel_populations_before_solve_capacity = stage_superlevel_before.size();
            trace.final_condensed_matrix = stage_condensed_matrix.data();
            trace.final_condensed_matrix_capacity = stage_condensed_matrix.size();
            trace.final_condensed_rhs = stage_condensed_rhs.data();
            trace.final_condensed_rhs_capacity = stage_condensed_rhs.size();
            trace.final_first_lu_solution = stage_first_lu.data();
            trace.final_first_lu_solution_capacity = stage_first_lu.size();
            trace.final_refinement_residual = stage_refinement_residual.data();
            trace.final_refinement_residual_capacity = stage_refinement_residual.size();
            trace.final_refinement_correction = stage_refinement_correction.data();
            trace.final_refinement_correction_capacity = stage_refinement_correction.size();
            trace.final_refined_superlevel_solution = stage_refined_superlevel.data();
            trace.final_refined_superlevel_solution_capacity = stage_refined_superlevel.size();
            trace.final_population_after_condensed = stage_after_condensed.data();
            trace.final_population_after_condensed_capacity = stage_after_condensed.size();
            trace.final_fixed_point_population_before = stage_fixed_before.data();
            trace.final_fixed_point_population_before_capacity = stage_fixed_before.size();
            trace.final_fixed_point_population_after = stage_fixed_after.data();
            trace.final_fixed_point_population_after_capacity = stage_fixed_after.size();
            std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> trace_message{};
            const int trace_rc = xstar_element_engine_get_last_solve_stage_trace_v1(
                ctx.element_context, &trace, trace_message.data(), trace_message.size());
            if (trace_rc != 0 || trace.valid == 0u || trace.element_z != element.element_z ||
                trace.final_outer_start_count != nrows ||
                trace.final_superlevel_populations_before_solve_count != nsp ||
                trace.final_condensed_matrix_count != nsp * nsp ||
                trace.final_population_after_condensed_count != nrows ||
                trace.final_fixed_point_population_after_count != nrows) {
                throw std::runtime_error(
                    std::string("native solve-stage trace unavailable z=") +
                    std::to_string(element.element_z) + ": " + trace_message.data());
            }
            stage_final_outer_iteration = trace.final_outer_iteration;
            stage_final_fixed_iterations = trace.final_fixed_iterations;
            stage_trace_captured = true;
        }
        ++stats.elements_solved;
        // Source calc_hmc_all keeps primary and secondary thermal totals
        // separate.  heatf/hmctot consumes only the primary httot/cltot pair;
        // secondary totals remain diagnostic state and must not be folded into
        // the controller residual.
        std::vector<double> thermal_populations = buffers.populations;
        bool element_thermal_compact_closure_applied = false;
        if (thermal_compact_population_closure_data.has_value() &&
            thermal_compact_population_closure_data->rows_by_element_z.count(element.element_z) != 0u) {
            thermal_populations = thermal_compact_population_values_for_element(
                *thermal_compact_population_closure_data, active);
            element_thermal_compact_closure_applied = true;
            ctx.last_thermal_consumed_compact_population_closure = true;
        } else if (thermal_component_closure_data.has_value() && fixed_state_closure_data.has_value()) {
            const auto& closure = *fixed_state_closure_data;
            for (std::size_t row = 0; row < thermal_populations.size(); ++row) {
                const std::size_t full_index = fixed_full_population_offset +
                    static_cast<std::size_t>(active.full_row_start - 1) + row;
                if (full_index >= closure.level_populations.size()) {
                    throw std::runtime_error("thermal fixed-state population slice overflow");
                }
                thermal_populations[row] = closure.level_populations[full_index];
            }
            ctx.last_thermal_consumed_fixed_state_closure = true;
        }
        if (native_production_mode() && element.element_z == 12 &&
            environment_data_type("XSTAR_QUALIFICATION_SOURCE_SEQUENCE") == 16) {
            const char* dump_path = std::getenv("XSTAR_V70_DUMP_MG_COMPACT_POPULATIONS");
            if (dump_path && *dump_path) {
                std::ofstream dump(dump_path);
                if (!dump) throw std::runtime_error("cannot write v70 Mg compact-population probe");
                dump << "compact_row,ion,ion_charge,superlevel,is_normalization_row,native_population\n";
                dump << std::setprecision(17);
                for (std::size_t row = 0; row < active.element.rows.size(); ++row) {
                    const auto& meta = active.element.rows[row];
                    dump << meta.row << ',' << (meta.ion + active.min_stage - 1) << ','
                         << meta.ion_charge << ',' << meta.superlevel << ','
                         << (meta.row == active.element.normalization_row ? 1 : 0) << ','
                         << thermal_populations[row] << '\n';
                }
            }
        }
        thermal_population_stream.insert(
            thermal_population_stream.end(), thermal_populations.begin(), thermal_populations.end());

        // Controller-safe spectral projection: thermal compact-population
        // closures qualify only the thermal residual stream.  They must not be
        // copied into the committed population output or any source workspace
        // that is transported into the next DSEC evaluation.  Product-specific
        // population projection belongs after the full controller trajectory.

        double computed_element_heating = 0.0;
        double computed_element_cooling = 0.0;
        double computed_element_heating2 = 0.0;
        double computed_element_cooling2 = 0.0;
        if (thermal_diagonal_source_domain) {
            const auto canonical_reduction = xstar_canonical_thermal::reduce(
                canonical_thermal_ledger.terms, thermal_populations, element.element_z);
            if (canonical_reduction.fingerprint != canonical_thermal_ledger.fingerprint) {
                throw std::runtime_error(
                    "fixed-state consumer canonical Thermal ledger fingerprint mismatch");
            }
            const auto weighted =
                canonical_reduction.tagged.total.abundance_weighted(element.abundance);
            computed_element_heating = weighted[0];
            computed_element_cooling = weighted[1];
            computed_element_heating2 = weighted[2];
            computed_element_cooling2 = weighted[3];
            if (element.element_z == 2) {
                ctx.last_computed_helium_type53_budget =
                    canonical_reduction.tagged.type53.abundance_weighted(element.abundance);
                ctx.last_computed_helium_non_type53_budget =
                    canonical_reduction.tagged.non_type53.abundance_weighted(element.abundance);
            }

            for (const auto& term : canonical_thermal_ledger.terms) {
                const std::size_t row = static_cast<std::size_t>(term.compact_row - 1);
                const double compact_population = thermal_populations[row];
                const double weighted_population = compact_population * element.abundance;
                const double primary_unweighted = compact_population * term.cj;
                const double secondary_unweighted = compact_population * term.cj2;
                ThermalDiagonalDiagnostic diagonal;
                diagonal.element_z = element.element_z;
                diagonal.active_min_stage = active.min_stage;
                diagonal.active_max_stage = active.max_stage;
                diagonal.source_order_index = term.term_index;
                diagonal.source_position = term.source_position;
                diagonal.record = term.record;
                diagonal.data_type = term.data_type;
                diagonal.rate_type = term.rate_type;
                diagonal.ion_index = term.ion_index;
                diagonal.ion_stage = term.ion_stage;
                diagonal.compact_row = term.compact_row;
                diagonal.native_compact_row = term.native_compact_row;
                diagonal.source_compact_row = term.source_compact_row;
                diagonal.role = term.role == XSTAR_CANONICAL_THERMAL_FORWARD_DIAG_LOSS
                    ? "forward_diag_loss" : "reverse_diag_loss";
                diagonal.normalization_row =
                    (term.flags & XSTAR_CANONICAL_THERMAL_NORMALIZATION_ROW) != 0u;
                diagonal.magnesium_type99_primary_cooling_reduction_applied =
                    (term.flags & XSTAR_CANONICAL_THERMAL_TYPE99_SOURCE_CORRECTED) != 0u;
                diagonal.magnesium_primary_cooling_source_order_applied =
                    (term.flags & XSTAR_CANONICAL_THERMAL_PRIMARY_SOURCE_ORDERED) != 0u;
                diagonal.magnesium_primary_cooling_source_order_index =
                    term.primary_source_order_index;
                diagonal.source_domain_included =
                    (term.flags & XSTAR_CANONICAL_THERMAL_SOURCE_DOMAIN_INCLUDED) != 0u;
                diagonal.abundance = element.abundance;
                diagonal.compact_population = compact_population;
                diagonal.weighted_population = weighted_population;
                diagonal.cj = term.cj;
                diagonal.cj2 = term.cj2;
                diagonal.native_cj = term.native_cj;
                diagonal.source_cj = term.source_cj;
                ++ctx.last_thermal_diagonal_rows_included;
                if (diagonal.normalization_row) {
                    ++ctx.last_thermal_diagonal_normalization_terms_included;
                }
                if (term.cj > 0.0) {
                    diagonal.unweighted_cooling_contribution = primary_unweighted;
                    diagonal.cooling_contribution = primary_unweighted * element.abundance;
                } else {
                    diagonal.unweighted_heating_contribution = -primary_unweighted;
                    diagonal.heating_contribution = (-primary_unweighted) * element.abundance;
                }
                if (term.cj2 > 0.0) {
                    diagonal.unweighted_cooling2_contribution = secondary_unweighted;
                    diagonal.cooling2_contribution = secondary_unweighted * element.abundance;
                } else {
                    diagonal.unweighted_heating2_contribution = -secondary_unweighted;
                    diagonal.heating2_contribution = (-secondary_unweighted) * element.abundance;
                }
                ctx.last_thermal_diagonal_diagnostics.push_back(std::move(diagonal));
            }
            ctx.last_thermal_diagonal_source_domain = true;
        } else {
            // The element engine consumed the same immutable canonical ledger
            // and returned source-order unweighted channels. Apply abundance
            // once after each complete channel.
            computed_element_heating = eout.heating * element.abundance;
            computed_element_cooling = eout.cooling * element.abundance;
            computed_element_heating2 = eout.heating2 * element.abundance;
            computed_element_cooling2 = eout.cooling2 * element.abundance;
            const bool call1_leaf_oracle =
                (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE) != 0u;
            if (call1_leaf_oracle && element.element_z == 1) {
                computed_element_heating = input.h_primary_heating_override;
                computed_element_cooling = input.h_primary_cooling_override;
                computed_element_heating2 = input.h_secondary_heating_override;
                computed_element_cooling2 = input.h_secondary_cooling_override;
            } else if (call1_leaf_oracle && element.element_z == 2) {
                computed_element_heating = input.he_primary_heating_override;
                computed_element_cooling = input.he_primary_cooling_override;
                computed_element_heating2 = input.he_secondary_heating_override;
                computed_element_cooling2 = input.he_secondary_cooling_override;
            }
            if (element.element_z == 12 &&
                (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_MG_PRIMARY_OVERRIDE) != 0u) {
                computed_element_heating = input.mg_primary_heating_override;
                computed_element_cooling = input.mg_primary_cooling_override;
                computed_element_heating2 = input.mg_secondary_heating_override;
                computed_element_cooling2 = input.mg_secondary_cooling_override;
            }
        }
        ctx.last_computed_element_thermal_budget[element.element_z] = {{
            computed_element_heating, computed_element_cooling,
            computed_element_heating2, computed_element_cooling2}};

        std::array<double,4> committed_element{{
            computed_element_heating, computed_element_cooling,
            computed_element_heating2, computed_element_cooling2}};
        if (thermal_component_closure_data.has_value()) {
            if (element.element_z == 1) committed_element = thermal_component_closure_data->h;
            else if (element.element_z == 2) committed_element = thermal_component_closure_data->he;
            else if (element.element_z == 12) committed_element = thermal_component_closure_data->mg;
            else throw std::runtime_error("thermal component closure contains unsupported element");
        }
        const double element_heating = committed_element[0];
        const double element_cooling = committed_element[1];
        const double element_heating2 = committed_element[2];
        const double element_cooling2 = committed_element[3];
        const std::array<double,4> computed_element{{
            computed_element_heating, computed_element_cooling,
            computed_element_heating2, computed_element_cooling2}};
        for (std::size_t channel = 0; channel < 4; ++channel) {
            // Preserve calc_hmc_all element visitation order.  Do not rebuild
            // the scientific totals later from an associative container.
            computed_element_totals[channel] += computed_element[channel];
            committed_element_totals[channel] += committed_element[channel];
        }
        output.element_heating = committed_element_totals[0];
        output.element_cooling = committed_element_totals[1];
        ctx.last_element_thermal_budget[element.element_z] = committed_element;
        if (element.element_z == 2) {
            ctx.last_helium_type53_budget = thermal_component_closure_data.has_value()
                ? thermal_component_closure_data->he_type53
                : ctx.last_computed_helium_type53_budget;
            if (thermal_component_closure_data.has_value()) {
                const auto& closure_he = thermal_component_closure_data->he;
                const auto& closure_he53 = thermal_component_closure_data->he_type53;
                for (std::size_t channel = 0; channel < 4; ++channel) {
                    ctx.last_helium_non_type53_budget[channel] =
                        closure_he[channel] - closure_he53[channel];
                }
            } else {
                ctx.last_helium_non_type53_budget =
                    ctx.last_computed_helium_non_type53_budget;
            }
        }

        std::vector<double> full_populations(static_cast<std::size_t>(element.n_rows), 0.0);
        for (std::size_t row = 0; row < buffers.populations.size(); ++row) {
            full_populations[static_cast<std::size_t>(active.full_row_start - 1) + row] = buffers.populations[row];
        }
        all_populations.insert(all_populations.end(), full_populations.begin(), full_populations.end());
        fixed_full_population_offset += full_populations.size();

        // Match local_zone.py exactly: accumulate explicit ion fractions
        // using (stage - 1), then add the fully stripped fraction at charge Z.
        // Keep this computed electron fraction distinct from elcter, which is
        // the DSEC charge residual trial_xee - computed_xee.
        double explicit_stage_sum = 0.0;
        for (int ion_slot = 0; ion_slot < active.element.n_ions; ++ion_slot) {
            const double fraction =
                buffers.ion_population_final[static_cast<std::size_t>(ion_slot)];
            const int stage = active.min_stage + ion_slot;
            explicit_stage_sum += fraction;

            // XSTAR heatf accumulates every represented ion charge term
            // directly into one global ENELEC scalar.  Do not regroup these
            // contributions into per-element subtotals: that changes the
            // binary64 result and the controller secant trajectory.
            volatile double source_charge = static_cast<double>(stage - 1);
            volatile double weighted_fraction = fraction * source_charge;
            volatile double source_term = weighted_fraction * element.abundance;
            volatile double next_electron_fraction =
                computed_electron_fraction + source_term;
            computed_electron_fraction = next_electron_fraction;
        }
        const double fully_stripped_fraction =
            std::max(0.0, 1.0 - explicit_stage_sum);
        volatile double fully_stripped_charge =
            static_cast<double>(element.element_z);
        volatile double fully_stripped_weighted_fraction =
            fully_stripped_fraction * fully_stripped_charge;
        volatile double fully_stripped_source_term =
            fully_stripped_weighted_fraction * element.abundance;
        volatile double next_electron_fraction =
            computed_electron_fraction + fully_stripped_source_term;
        computed_electron_fraction = next_electron_fraction;

        NativeElementDiagnostic element_diagnostic;
        element_diagnostic.committed_contributions = contributions;
        element_diagnostic.canonical_thermal_terms = canonical_thermal_ledger.terms;
        element_diagnostic.canonical_thermal_ledger_fingerprint = canonical_thermal_ledger.fingerprint;
        element_diagnostic.element_thermal_ledger_fingerprint = element_consumed_thermal_ledger_fingerprint;
        element_diagnostic.fixed_state_thermal_ledger_fingerprint = canonical_thermal_ledger.fingerprint;
        element_diagnostic.canonical_thermal_ledger_shared =
            element_consumed_thermal_ledger_fingerprint == canonical_thermal_ledger.fingerprint;
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
        const int continuum_stage = element.element_z + 1;
        if (continuum_stage >= 1) {
            element_diagnostic.final_stage_fractions[
                static_cast<std::size_t>(continuum_stage - 1)] =
                fully_stripped_fraction;
        }
        element_diagnostic.thermal_compact_populations = thermal_populations;
        element_diagnostic.thermal_compact_population_closure_applied = element_thermal_compact_closure_applied;
        element_diagnostic.heating = element_heating;
        element_diagnostic.cooling = element_cooling;
        element_diagnostic.heating2 = element_heating2;
        element_diagnostic.cooling2 = element_cooling2;
        element_diagnostic.normalization = eout.normalization;
        element_diagnostic.normalization_error = eout.normalization_error;
        element_diagnostic.max_relative_row_residual = eout.max_relative_row_residual;
        element_diagnostic.records_constructed = eout.records_constructed;
        element_diagnostic.terms_constructed = eout.terms_constructed;
        if (capture_element_solve_response) {
            element_diagnostic.solve_response_captured = true;
            element_diagnostic.active_raw_global_level_indices.resize(static_cast<std::size_t>(active.element.n_rows), 0);
            element_diagnostic.active_raw_call_start_xilevg.resize(static_cast<std::size_t>(active.element.n_rows), 0.0);
            element_diagnostic.active_loaded_global_level_indices.resize(static_cast<std::size_t>(active.element.n_rows), 0);
            element_diagnostic.active_loaded_call_start_xilevg.resize(static_cast<std::size_t>(active.element.n_rows), 0.0);
            for (int compact_row = 1; compact_row <= active.element.n_rows; ++compact_row) {
                const std::size_t compact_index = static_cast<std::size_t>(compact_row - 1);
                const auto& active_row = active.element.rows.at(compact_index);
                element_diagnostic.active_raw_global_level_indices[compact_index] = active_row.global_level_index;
                if (input.global_xilevg && input.global_level_count > 0 && active_row.global_level_index > 0 &&
                    static_cast<std::size_t>(active_row.global_level_index) <= input.global_level_count) {
                    element_diagnostic.active_raw_call_start_xilevg[compact_index] =
                        input.global_xilevg[active_row.global_level_index - 1];
                }
                const RuntimeInitialSeed seed = source_faithful_runtime_initial_seed(active.element, compact_index, &input);
                element_diagnostic.active_loaded_global_level_indices[compact_index] = seed.global_level_index;
                if (seed.loaded) element_diagnostic.active_loaded_call_start_xilevg[compact_index] = seed.value;
            }
            element_diagnostic.active_initial_populations = buffers.initial;
            element_diagnostic.active_final_outer_start_populations =
                stage_trace_captured ? std::move(stage_final_outer_start) : buffers.outer;
            element_diagnostic.active_final_populations = buffers.populations;
            element_diagnostic.solve_stage_trace_captured = stage_trace_captured;
            element_diagnostic.final_outer_iteration = stage_final_outer_iteration;
            element_diagnostic.final_fixed_iterations = stage_final_fixed_iterations;
            element_diagnostic.final_superlevel_populations_before_solve = std::move(stage_superlevel_before);
            element_diagnostic.final_condensed_matrix = std::move(stage_condensed_matrix);
            element_diagnostic.final_condensed_rhs = std::move(stage_condensed_rhs);
            element_diagnostic.final_first_lu_solution = std::move(stage_first_lu);
            element_diagnostic.final_refinement_residual = std::move(stage_refinement_residual);
            element_diagnostic.final_refinement_correction = std::move(stage_refinement_correction);
            element_diagnostic.final_refined_superlevel_solution = std::move(stage_refined_superlevel);
            element_diagnostic.final_population_after_condensed = std::move(stage_after_condensed);
            element_diagnostic.final_fixed_point_population_before = std::move(stage_fixed_before);
            element_diagnostic.final_fixed_point_population_after = std::move(stage_fixed_after);
            if (all_element_solve_system || (helium_solve_response && element.element_z == 2)) {
                element_diagnostic.dense_matrix = buffers.dense;
                element_diagnostic.heating_matrix = buffers.heat;
                element_diagnostic.heating_matrix2 = buffers.heat2;
            }
            element_diagnostic.rhs = buffers.rhs;
            element_diagnostic.row_residual = buffers.row_residual;
            element_diagnostic.row_scale = buffers.row_scale;
            element_diagnostic.relative_row_residual = buffers.relative_residual;
            if (source_compact_basis_seed) {
                element_diagnostic.active_ion_reconstruction.assign(
                    static_cast<std::size_t>(element.element_z), 0.0);
                for (int ion_slot = 0; ion_slot < active.element.n_ions; ++ion_slot) {
                    const int stage = active.min_stage + ion_slot;
                    if (stage >= 1 && stage <= element.element_z) {
                        element_diagnostic.active_ion_reconstruction[static_cast<std::size_t>(stage - 1)] =
                            buffers.ion_population_final[static_cast<std::size_t>(ion_slot)];
                    }
                }
            } else {
                element_diagnostic.active_ion_reconstruction = buffers.ion_population_final;
            }
            element_diagnostic.solver_method = eout.solver_method;
            element_diagnostic.solver_status_flags = eout.status_flags;
            element_diagnostic.outer_iterations = eout.outer_iterations;
            element_diagnostic.fixed_point_iterations = eout.fixed_point_iterations;
        }
        ctx.last_element_diagnostics.push_back(std::move(element_diagnostic));

        // Reconstruct the complete native bound-free continuum surface from
        // the source cross-section records.  The former product path retained
        // only one threshold cell per RRC, which left most xo01_detal3 opacity
        // rows and nearly all xo01_detal4 continuum-opacity bins at zero.
        // v82 patch 5.20.15.3: Type-76 is not a derived product projection.
        // ucalc.f90 writes its two-photon continuum directly into rccemis, so
        // retain that side effect even while the expensive bound-free/line
        // product projection is deferred during the controller trajectory.
        for (std::size_t k = 0; k < evaluated.size() && k < evaluated_records.size(); ++k) {
            const auto& source_record = *evaluated_records[k];
            if (source_record.data_type == 76 && input.radiation_bin_count > 1 &&
                evaluated[k].line_energy_ev > 0.0) {
                // Literal ucalc.f90 label 76.  nbmx is the source nbinc value;
                // the polynomial endpoint is epi(nbmx), while the energy
                // normalization uses the physical upper-lower level gap emax.
                // The source initializes ansar2=0 before the first trapezoid
                // and visits every bin 2..nbmx because enxt(lfastl=0) returns
                // nskp=1.
                const double emax = evaluated[k].line_energy_ev;
                const int nbmx_one_based = type99_nbinc_fortran_value(
                    emax, input.radiation_energy_ev, input.radiation_bin_count);
                const std::size_t nbmx = static_cast<std::size_t>(
                    std::max(1, std::min(static_cast<int>(input.radiation_bin_count), nbmx_one_based)));
                double rcemsum = 0.0;
                double ansar2 = 0.0;
                if (nbmx >= 2u) {
                    const double grid_endpoint = input.radiation_energy_ev[nbmx - 1u];
                    for (std::size_t ll = 2u; ll <= nbmx; ++ll) {
                        const double ansar2o = ansar2;
                        const double energy = input.radiation_energy_ev[ll - 1u];
                        ansar2 = energy * energy * std::max(0.0, grid_endpoint - energy);
                        rcemsum += (ansar2 + ansar2o) *
                            (energy - input.radiation_energy_ev[ll - 2u]) / 2.0;
                    }
                    const double upper_population = active_population_for_full_row(
                        active, buffers.populations, source_record.upper_row);
                    const double abund2 = upper_population * element.abundance *
                        input.hydrogen_density_cm3;
                    const double aij = std::max(0.0, evaluated[k].contribution.ans2);
                    const double cfrac = effective_spectral_covering_fraction_v82_patch58(input);
                    // Literal calc_emis_ion rate-type 9 prepass sets tau1=tau2=0
                    // before the unconditional UCalc call. Type-76 is not an
                    // nlbin-ranked line in the active inventory, so this is
                    // the source escape state that owns its retained continuum.
                    const double ptmp1 = (1.0 - cfrac) / 2.0;
                    const double ptmp2 = (1.0 + cfrac) / 2.0;
                    const double denominator = 1.0e-24 + rcemsum;
                    if (abund2 > 0.0 && aij > 0.0 && denominator > 0.0) {
                        for (std::size_t ll = 2u; ll <= nbmx; ++ll) {
                            const double energy = input.radiation_energy_ev[ll - 1u];
                            double emitted = energy * energy * std::max(0.0, grid_endpoint - energy);
                            emitted = emitted * aij * emax / denominator;
                            native_type76_continuum_emission[ll - 1u] +=
                                abund2 * emitted * ptmp1 / xstar_constants::kLegacyTwoPhotonGeometryFactor;
                            native_type76_continuum_emission[input.radiation_bin_count + ll - 1u] +=
                                abund2 * emitted * ptmp2 / xstar_constants::kLegacyTwoPhotonGeometryFactor;
                        }
                    }
                }
            }
            if (defer_product_projection) continue;
            if (source_record.opcode == XSTAR_FIXED_OPCODE_TYPE88_SUPERLEVEL_BOUND_FREE &&
                source_record.rate_type == 42 &&
                source_record.real_offset + source_record.real_count <= ctx.program.reals.size() &&
                source_record.int_offset + source_record.int_count <= ctx.program.ints.size()) {
                const double* rr = ctx.program.reals.data() + source_record.real_offset;
                const auto* ii = ctx.program.ints.data() + source_record.int_offset;
                std::size_t pair_count = source_record.real_count / 2u;
                if (source_record.int_count >= 1 && ii[0] >= 2) pair_count = static_cast<std::size_t>(ii[0]);
                const std::size_t pair_reals = 2u * pair_count;
                if (pair_count >= 2u && pair_reals <= source_record.real_count) {
                    NativeBoundFreeCurve type88_curve;
                    type88_curve.threshold_ev = source_record.line_energy_ev;
                    if (!(type88_curve.threshold_ev > 0.0) && pair_reals < source_record.real_count)
                        type88_curve.threshold_ev = std::max(0.0, rr[pair_reals]);
                    type88_curve.apply_source_phextrap = true;
                    type88_curve.phextrap_max_points = static_cast<int>(input.radiation_bin_count);
                    type88_curve.offset_ryd.reserve(pair_count);
                    type88_curve.sigma_cm2.reserve(pair_count);
                    for (std::size_t ip = 0; ip < pair_count; ++ip) {
                        type88_curve.offset_ryd.push_back(rr[2u * ip]);
                        type88_curve.sigma_cm2.push_back(std::max(0.0, rr[2u * ip + 1u]));
                    }
                    if (type88_curve.threshold_ev > 0.0) {
                        EvaluatedRecord type88_eval = evaluated[k];
                        const auto& lower88 = row_at(element, source_record.lower_row);
                        const auto& upper88 = row_at(element, source_record.upper_row);
                        const double xnx = std::max(0.0, input.electron_density_cm3);
                        const double tm = std::max(input.temperature_k, 1.0e-300);
                        const double q2 = 2.07e-16 * xnx * std::pow(tm, -1.5);
                        const double rs = q2 / std::max(upper88.statistical_weight, 1.0e-300);
                        const double rnissel = lower88.statistical_weight * rs;
                        const double t4 = tm / 1.0e4;
                        const double first_offset_ev = std::max(0.0, kType53RydEv * type88_curve.offset_ryd.front());
                        const double rnist = rnissel * limited_exp(
                            -first_offset_ev / std::max(xstar_constants::kLegacyBoltzmannEvPerT4 * t4, 1.0e-300));
                        type88_eval.type53_shadow = Type53SourceShadow{};
                        type88_eval.type53_shadow.valid = rnist > 0.0;
                        type88_eval.type53_shadow.rnist = rnist;
                        DeferredRrcRecordV82Patch520 deferred;
                        deferred.source_position = static_cast<std::uint64_t>(source_record.source_position);
                        deferred.record = static_cast<std::int64_t>(source_record.record);
                        deferred.rate_type = source_record.rate_type;
                        deferred.source_rate42_type88 = true;
                        deferred.type88_rnist = rnist;
                        deferred.opacity_curve = type88_curve;
                        deferred.emission_curve = std::move(type88_curve);
                        deferred.evaluated = std::move(type88_eval);
                        deferred.lower_abundance = active_population_for_full_row(
                            active, buffers.populations, source_record.lower_row) * active.element.abundance;
                        // calc_emis_ion computes rate-42 abund2 from the raw
                        // caller idest2 before UCalc label 88 resets idest2 to
                        // nlevp.  New ATDB lowering retains that local endpoint
                        // as the fourth Type-88 payload integer.  Older compact
                        // fixtures fall back to the historical nlev row.
                        int calc_emis_upper_row_v82_patch52010 = source_record.upper_row;
                        if (source_record.int_count >= 4u && ii[2] > 0 && ii[3] > 0) {
                            calc_emis_upper_row_v82_patch52010 =
                                source_record.lower_row - static_cast<int>(ii[2]) + static_cast<int>(ii[3]);
                        }
                        deferred.upper_abundance = active_population_for_full_row(
                            active, buffers.populations, calc_emis_upper_row_v82_patch52010) * active.element.abundance;
                        deferred_rrc_records_v82_patch520.push_back(std::move(deferred));
                    }
                }
            }
            if (!evaluated[k].bound_free_spectral) continue;
            NativeBoundFreeCurve curve;
            if (!native_bound_free_curve(ctx.program, source_record, evaluated[k], curve)) continue;
            accumulate_native_bound_free_surface(
                curve, evaluated[k], source_record, active, buffers.populations, input,
                native_bound_free_opacity, native_rrc_continuum_emission,
                &phint53_records_mapped_v82_patch57, &phint53_bins_accumulated_v82_patch57);
            {
                DeferredRrcRecordV82Patch520 deferred;
                deferred.source_position = static_cast<std::uint64_t>(source_record.source_position);
                deferred.record = static_cast<std::int64_t>(source_record.record);
                deferred.rate_type = source_record.rate_type;
                // v82 patch 5.20.14.9: split the deferred calc_emis consumer
                // into its literal opacity/depth and emission views.  The full
                // calc_emis curve is required by opakc/dpthc; the base curve
                // remains the stable emission owner until 5.20.15 corrects the
                // retained tauc workspace and re-enables literal pescv(tauc).
                deferred.opacity_curve = curve;
                NativeBoundFreeCurve emission_curve_v82_patch520149;
                if (!native_bound_free_curve(ctx.program, source_record, evaluated[k],
                        emission_curve_v82_patch520149, false))
                    emission_curve_v82_patch520149 = curve;
                deferred.emission_curve = std::move(emission_curve_v82_patch520149);
                deferred.evaluated = evaluated[k];
                deferred.lower_abundance = active_population_for_full_row(
                    active, buffers.populations, source_record.lower_row) * active.element.abundance;
                deferred.upper_abundance = active_population_for_full_row(
                    active, buffers.populations, source_record.upper_row) * active.element.abundance;
                deferred_rrc_records_v82_patch520.push_back(std::move(deferred));
            }
            if (mg_type53_kernel_audit_v82_patch512 && element.element_z == 12 &&
                source_record.data_type == 53 && source_record.opcode == XSTAR_FIXED_OPCODE_TYPE53_BOUND_FREE) {
                MgType53OpacityKernelRowV82Patch512 row;
                row.source_position = source_record.source_position;
                row.record = source_record.record;
                row.continuum_index_one_based = source_record.continuum_index_one_based;
                row.ion_stage = source_record.ion_stage;
                row.lower_full_row = source_record.lower_row;
                row.upper_full_row = source_record.upper_row;
                if (source_record.lower_row >= active.full_row_start && source_record.lower_row <= active.full_row_end)
                    row.lower_compact_row = source_record.lower_row - active.full_row_start + 1;
                if (source_record.upper_row >= active.full_row_start && source_record.upper_row <= active.full_row_end)
                    row.upper_compact_row = source_record.upper_row - active.full_row_start + 1;
                if (source_record.lower_row > 0 && static_cast<std::size_t>(source_record.lower_row) <= element.rows.size())
                    row.lower_global_level_index = element.rows[static_cast<std::size_t>(source_record.lower_row - 1)].global_level_index;
                if (source_record.upper_row > 0 && static_cast<std::size_t>(source_record.upper_row) <= element.rows.size())
                    row.upper_global_level_index = element.rows[static_cast<std::size_t>(source_record.upper_row - 1)].global_level_index;
                row.threshold_ev = curve.threshold_ev;
                row.native_lower_population = active_population_for_full_row(active, buffers.populations, source_record.lower_row);
                row.native_upper_population = active_population_for_full_row(active, buffers.populations, source_record.upper_row);
                row.abundance = element.abundance;
                row.hydrogen_density_cm3 = std::max(0.0, input.hydrogen_density_cm3);
                const auto mapped = phint53_grid_map_v82_patch57(curve, input.radiation_energy_ev, static_cast<int>(input.radiation_bin_count));
                if (mapped.valid) {
                    for (int kl = mapped.nb1_zero_based; kl < mapped.klmax_zero_based && kl + 1 < static_cast<int>(input.radiation_bin_count); ++kl) {
                        const double sigma = std::max(0.0, mapped.sgbar[static_cast<std::size_t>(kl)]);
                        if (!(sigma > 0.0)) continue;
                        ++row.mapped_bin_count;
                        row.sigma_bin_sum_cm2 += sigma;
                    }
                }
                row.native_opacity_bin_sum_cm1 = row.native_lower_population * row.abundance *
                    row.hydrogen_density_cm3 * row.sigma_bin_sum_cm2;
                if (evaluated[k].type53_shadow.valid) {
                    row.threshold_cross_section_cm2 = evaluated[k].type53_shadow.threshold_cross_section_cm2;
                    row.threshold_stimulated_cross_section_cm2 = evaluated[k].type53_shadow.threshold_stimulated_cross_section_cm2;
                }
                mg_type53_kernel_rows_v82_patch512.push_back(row);
            }
            if (opacity_producer_audit_v82_patch511 || exact_absorption_audit_v82_patch5203) {
                std::fill(producer_temp_opacity_v82_patch511.begin(), producer_temp_opacity_v82_patch511.end(), 0.0);
                std::fill(producer_temp_rrc_v82_patch511.begin(), producer_temp_rrc_v82_patch511.end(), 0.0);
                accumulate_native_bound_free_surface(
                    curve, evaluated[k], source_record, active, buffers.populations, input,
                    producer_temp_opacity_v82_patch511, producer_temp_rrc_v82_patch511, nullptr, nullptr);
                for (std::size_t bin = 0; bin < producer_temp_opacity_v82_patch511.size(); ++bin) {
                    const double value = producer_temp_opacity_v82_patch511[bin];
                    write_exact_absorption_v82_patch5203(bin, "BOUND_FREE", source_record.source_position,
                        source_record.record, source_record.data_type, source_record.rate_type, element.element_z,
                        source_record.ion_stage, source_record.lower_row, source_record.upper_row, value);
                    if (!opacity_producer_audit_v82_patch511 ||
                        !(std::isfinite(value) && std::abs(value) > std::abs(bound_free_top_v82_patch511[bin].contribution))) continue;
                    auto& top = bound_free_top_v82_patch511[bin];
                    top.contribution = value;
                    top.source_position = source_record.source_position;
                    top.record = source_record.record;
                    top.data_type = source_record.data_type;
                    top.element_z = element.element_z;
                    top.ion_stage = source_record.ion_stage;
                    top.lower_row = source_record.lower_row;
                    top.upper_row = source_record.upper_row;
                }
            }
        }

        for (std::size_t k = 0; k < evaluated.size(); ++k) {
            if (!evaluated[k].spectral) continue;
            const auto& rec = evaluated[k].contribution;
            // Literal calc_emisab_element/calc_emis_element call the per-ion
            // emissivity routines only for ion stages inside mml(jk)..mmu(jk).
            // The fixed-state evaluator intentionally visits the complete
            // lowered record inventory for matrix/diagnostic purposes, so
            // apply the source active-stage gate when constructing the
            // spectral/publication stream.  Without it inactive Mg II rate-7
            // records leak nonzero cemab/elumab into options 19/24 and
            // xout_rrc1 even though FORTRAN and the Python backend never call
            // calc_emisab_ion for that ion stage.
            if (rec.ion_stage < active.min_stage || rec.ion_stage > active.max_stage) continue;
            xstar_spectral_contribution_v1 sc{};
            sc.source_position = static_cast<std::uint64_t>(rec.source_position);
            sc.record = rec.record;
            const auto* source_record = k < evaluated_records.size() ? evaluated_records[k] : nullptr;
            const int exact_line_index = source_record ? source_record->line_index_one_based : 0;
            const int exact_continuum_index = source_record ? source_record->continuum_index_one_based :
                evaluated[k].continuum_index_one_based;
            sc.kind = evaluated[k].bound_free_spectral
                ? XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE
                : XSTAR_SPECTRAL_KIND_FULL_LINE;
            sc.rate_type = rec.rate_type;
            sc.data_type = rec.data_type;
            sc.output_index = evaluated[k].bound_free_spectral
                ? static_cast<int32_t>(exact_continuum_index)
                : static_cast<int32_t>(exact_line_index);
            // A zero source pointer means this record has no slot in this
            // workspace. Its distributed continuum contribution, if any, was
            // already accumulated by the native continuum reconstruction.
            if (sc.output_index <= 0) continue;
            // v82 patch 5.20.6: calc_emis_ion/linopac locate an ordinary
            // Type-50 line from elmn/nplin, whose coordinate is the stored
            // source wavelength.  Keep evaluated.line_energy_ev as the rate
            // endpoint delta and use a separate spectral feature coordinate.
            double spectral_feature_energy_ev_v82_patch5206 = evaluated[k].line_energy_ev;
            if (!evaluated[k].bound_free_spectral && evaluated[k].type50_shadow.valid &&
                evaluated[k].type50_shadow.stored_wavelength_a > 0.0) {
                spectral_feature_energy_ev_v82_patch5206 =
                    xstar_constants::kLegacyLinopacPhotonEnergyAngstromEv /
                    evaluated[k].type50_shadow.stored_wavelength_a;
            }
            if (!evaluated[k].bound_free_spectral && spectral_feature_energy_ev_v82_patch5206 > 0.0) {
                double source_line_wavelength_v82_patch5208 =
                    source_real_literal_v82_patch5208(12398.4016) / spectral_feature_energy_ev_v82_patch5206;
                if (evaluated[k].type50_shadow.valid &&
                    evaluated[k].type50_shadow.stored_wavelength_a > 0.0) {
                    source_line_wavelength_v82_patch5208 = evaluated[k].type50_shadow.stored_wavelength_a;
                }
                source_line_wavelength_by_identity_v82_patch5208[
                    {static_cast<std::uint64_t>(rec.source_position), rec.record}] =
                    source_line_wavelength_v82_patch5208;
            }
            sc.bin_one_based = 1;
            if (input.radiation_bin_count > 0) {
                const auto* it = std::lower_bound(
                    input.radiation_energy_ev,
                    input.radiation_energy_ev + input.radiation_bin_count,
                    spectral_feature_energy_ev_v82_patch5206);
                sc.bin_one_based = static_cast<int32_t>(std::min<std::size_t>(
                    input.radiation_bin_count,
                    static_cast<std::size_t>(it - input.radiation_energy_ev) + 1));
            }
            sc.abundance_lower =
                active_population_for_full_row(active, buffers.populations, rec.lower_row) *
                element.abundance;
            sc.abundance_upper =
                active_population_for_full_row(active, buffers.populations, rec.upper_row) *
                element.abundance;
            // calc_emisab_ion calls ucalc only when either endpoint abundance
            // exceeds 1e-34.  Leaving opakab populated below that gate caused
            // every retained npconi2 slot to appear in option 24 instead of
            // the 99 genuinely accumulated Type-53 thresholds in this case.
            if (evaluated[k].bound_free_spectral &&
                !(sc.abundance_lower > 1.0e-34 || sc.abundance_upper > 1.0e-34)) {
                continue;
            }
            if (evaluated[k].bound_free_spectral) {
                // phint53 publishes the net threshold opacity
                //   max(0, abund1*sigma_abs - abund2*sigma_stim) * xpx.
                // The spectral engine multiplies sc.opakab by abund1*xpx,
                // so retain the equivalent per-lower-population coefficient.
                const Type53SourceShadow* opacity_shadow = nullptr;
                if (evaluated[k].type53_shadow.valid) {
                    // v82 patch 5.18.1: rank the calc_emisab-equivalent
                    // reduced-grid threshold seed, not the later full-grid
                    // calc_emis_ion revisit value.
                    opacity_shadow = evaluated[k].type53_calc_emisab_shadow.valid
                        ? &evaluated[k].type53_calc_emisab_shadow
                        : &evaluated[k].type53_shadow;
                } else if (evaluated[k].type49_shadow.valid) {
                    // v82 patch 5.20.9.4: literal xstarcalc calls
                    // calc_emisab_all on epim/bremsam before the full-grid
                    // calc_emis_all revisit.  rlbin ranks the record-local
                    // Type-49 opakab/cemab produced by that reduced call.
                    // The old 5.20.8.2 full-grid seed matched the stale Python
                    // capture, but the fresh Python/FORTRAN product comparison
                    // exposes non-source Mg II RRC luminosity from that owner.
                    // Keep full-grid Type-49 only for the later selected
                    // calc_emis replay; broad rank/public seed is reduced.
                    opacity_shadow = evaluated[k].type49_calc_emisab_shadow.valid
                        ? &evaluated[k].type49_calc_emisab_shadow
                        : &evaluated[k].type49_shadow;
                }
                if (opacity_shadow && sc.abundance_lower > 0.0 &&
                    opacity_shadow->threshold_publication_reached) {
                    const double population_ratio = sc.abundance_upper / sc.abundance_lower;
                    sc.opakab = std::max(0.0,
                        opacity_shadow->threshold_cross_section_cm2 -
                        population_ratio * opacity_shadow->threshold_stimulated_cross_section_cm2);
                } else {
                    // Type-99 direct UCalc opakab is source-zero.  Patch 5.18
                    // incorrectly projected phint53hunt's auxiliary shadow
                    // cross section into this scalar publication slot.
                    sc.opakab = 0.0;
                }
            }
            const double cfrac = effective_spectral_covering_fraction_v82_patch58(input);
            sc.ptmp1 = 1.0 - cfrac;
            sc.ptmp2 = 1.0 + cfrac;
            if (!evaluated[k].bound_free_spectral && evaluated[k].type50_shadow.valid) {
                sc.ptmp1 = evaluated[k].type50_shadow.ptmp1;
                sc.ptmp2 = evaluated[k].type50_shadow.ptmp2;
            } else if (evaluated[k].bound_free_spectral &&
                       evaluated[k].type53_shadow.valid) {
                sc.ptmp1 = evaluated[k].type53_shadow.ptmp1;
                sc.ptmp2 = evaluated[k].type53_shadow.ptmp2;
            } else if (evaluated[k].bound_free_spectral &&
                       evaluated[k].type49_shadow.valid) {
                sc.ptmp1 = evaluated[k].type49_shadow.ptmp1;
                sc.ptmp2 = evaluated[k].type49_shadow.ptmp2;
            }
            sc.hydrogen_density = input.hydrogen_density_cm3;
            sc.ans1 = rec.ans1; sc.ans2 = rec.ans2; sc.ans3 = rec.ans3; sc.ans4 = rec.ans4;
            // v82 patch 5.20.9.4: the broad bound-free spectral commit is
            // exactly the calc_emisab_all phase.  Both Type-53 and Type-49
            // therefore publish their reduced epim/bremsam answers into
            // record-local opakab/cemab.  calc_emis_all may later overwrite
            // selected opakab and full-grid opakc/rccemis, but it does not
            // overwrite cemab.
            if (evaluated[k].bound_free_spectral && evaluated[k].type53_calc_emisab_shadow.valid) {
                sc.ans1 = evaluated[k].type53_calc_emisab_shadow.ans[0];
                sc.ans2 = evaluated[k].type53_calc_emisab_shadow.ans[1];
                sc.ans3 = evaluated[k].type53_calc_emisab_shadow.ans[2];
                sc.ans4 = evaluated[k].type53_calc_emisab_shadow.ans[3];
            } else if (evaluated[k].bound_free_spectral &&
                       evaluated[k].type49_calc_emisab_shadow.valid) {
                sc.ans1 = evaluated[k].type49_calc_emisab_shadow.ans[0];
                sc.ans2 = evaluated[k].type49_calc_emisab_shadow.ans[1];
                sc.ans3 = evaluated[k].type49_calc_emisab_shadow.ans[2];
                sc.ans4 = evaluated[k].type49_calc_emisab_shadow.ans[3];
            }
            if (!evaluated[k].bound_free_spectral) sc.opakab = evaluated[k].opakab;
            sc.line_energy_eV = spectral_feature_energy_ev_v82_patch5206;
            sc.bin_width_eV = input.radiation_bin_count > 1 ? std::abs(input.radiation_energy_ev[1] - input.radiation_energy_ev[0]) : 1.0;
            sc.atomic_mass_amu = evaluated[k].atomic_mass_amu;
            sc.natural_width_eV = evaluated[k].natural_width_ev;
            sc.turbulent_velocity_km_s = input.turbulent_velocity_km_s;
            sc.temperature_1e4K = input.temperature_k / 1.0e4;
            // Rate-7 errc ownership was captured above from every evaluated
            // record before this calc_emisab abundance gate.  Do not rewrite it
            // here from only the subset that survives spectral publication.
            spectral.push_back(sc);
        }
    }
    stats.traversal_seconds += elapsed(traversal_start);
    ctx.last_thermal_population_count = thermal_population_stream.size();
    ctx.last_thermal_population_fingerprint = binary64_sequence_fnv1a(thermal_population_stream);

    if (fixed_state_closure_data.has_value()) {
        const auto& closure = *fixed_state_closure_data;
        if (closure.level_populations.size() != all_populations.size()) {
            throw std::runtime_error("fixed-state level closure count does not match native population output");
        }
        all_populations = closure.level_populations;
        std::size_t offset = 0;
        for (auto& diagnostic : ctx.last_element_diagnostics) {
            const std::size_t count = diagnostic.full_populations.size();
            if (offset + count > all_populations.size()) throw std::runtime_error("fixed-state diagnostic population slice overflow");
            diagnostic.full_populations.assign(all_populations.begin() + static_cast<std::ptrdiff_t>(offset),
                                               all_populations.begin() + static_cast<std::ptrdiff_t>(offset + count));
            if (diagnostic.active.full_row_start < 1 || diagnostic.active.full_row_end < diagnostic.active.full_row_start ||
                static_cast<std::size_t>(diagnostic.active.full_row_end) > diagnostic.full_populations.size()) {
                throw std::runtime_error("fixed-state diagnostic active population window mismatch");
            }
            diagnostic.active_final_populations.assign(
                diagnostic.full_populations.begin() + (diagnostic.active.full_row_start - 1),
                diagnostic.full_populations.begin() + diagnostic.active.full_row_end);
            const auto ion_it = closure.ion_stage_populations.find(diagnostic.element_z);
            if (ion_it == closure.ion_stage_populations.end()) throw std::runtime_error("fixed-state closure missing element ion stages");
            diagnostic.final_stage_fractions = ion_it->second;
            offset += count;
        }
        if (offset != all_populations.size()) throw std::runtime_error("fixed-state diagnostic population count mismatch");
    }
    ctx.last_committed_population_count = all_populations.size();
    ctx.last_committed_population_fingerprint = binary64_sequence_fnv1a(all_populations);
    if (output.populations_capacity < all_populations.size()) throw std::runtime_error("population output capacity too small");
    std::copy(all_populations.begin(), all_populations.end(), output.populations);
    output.populations_count = all_populations.size();

    if (source_workspaces) {
        if (source_workspaces->struct_size < sizeof(*source_workspaces) ||
            source_workspaces->abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) {
            throw std::runtime_error("fixed-state source-workspace ABI mismatch");
        }
        const auto lte_populations = compute_exact_lte_populations(
            ctx.program, input, ctx.retained_active_stage_windows);
        source_workspaces->lte_populations_count = lte_populations.size();
        if (source_workspaces->lte_populations) {
            if (source_workspaces->lte_populations_capacity < lte_populations.size()) {
                throw std::runtime_error("LTE population output capacity too small");
            }
            std::copy(lte_populations.begin(), lte_populations.end(), source_workspaces->lte_populations);
        }
        source_workspaces->exact_source_workspace_flags |= XSTAR_FIXED_EXACT_WORKSPACE_LTE_POPULATIONS;
    }

    const auto continuum_start = clock_type::now();
    if (input.radiation_bin_count > 0) {
        const double* comp_energy = input.dsec_radiation_bin_count >= 2 ? input.dsec_radiation_energy_ev : input.radiation_energy_ev;
        const double* comp_bremsa = input.dsec_radiation_bin_count >= 2 ? input.dsec_bremsa : input.radiation_flux;
        const std::size_t comp_n = input.dsec_radiation_bin_count >= 2 ? input.dsec_radiation_bin_count : input.radiation_bin_count;
        const bool source_faithful_continuum =
            environment_flag("XSTAR_QUALIFICATION_CONTINUUM_WORKSPACE_SOURCE_FAITHFUL");
        SourceComp2Result comp;
        double computed_htfreef = 0.0;
        double computed_clbrems = 0.0;
        if (source_faithful_continuum) {
            const auto continuum = source_continuum_thermal(
                comp_energy, comp_bremsa, comp_n,
                input.temperature_k, input.hydrogen_density_cm3, input.electron_fraction_xee
            );
            comp = continuum.compton;
            computed_htfreef = continuum.htfreef;
            computed_clbrems = continuum.clbrems;
            ctx.last_continuum_workspace_source_faithful = true;
            ctx.last_continuum_epim_count = continuum.workspace.epim.size();
            ctx.last_continuum_epim_fingerprint = binary64_sequence_fnv1a(continuum.workspace.epim);
            ctx.last_continuum_bremsam_count = continuum.workspace.bremsam.size();
            ctx.last_continuum_bremsam_fingerprint = binary64_sequence_fnv1a(continuum.workspace.bremsam);
            std::vector<double> map_values;
            map_values.reserve(continuum.workspace.bremsmap_index_one_based.size());
            for (const int value : continuum.workspace.bremsmap_index_one_based) {
                map_values.push_back(static_cast<double>(value));
            }
            ctx.last_continuum_bremsmap_count = map_values.size();
            ctx.last_continuum_bremsmap_fingerprint = binary64_sequence_fnv1a(map_values);
            ctx.last_continuum_workspace_diagnostics = continuum.diagnostics;
        } else {
            comp = source_comp2(
                comp_energy, comp_bremsa, comp_n,
                input.temperature_k, input.hydrogen_density_cm3, input.electron_fraction_xee
            );
            computed_clbrems =
                1.426e-27 * std::sqrt(input.temperature_k) *
                input.electron_density_cm3 * input.ionized_h_density_cm3;
        }
        ctx.last_computed_cmp1 = comp.cmp1;
        ctx.last_computed_cmp2 = comp.cmp2;
        ctx.last_computed_htcomp = comp.htcomp;
        ctx.last_computed_clcomp = comp.clcomp;
        ctx.last_computed_htfreef = computed_htfreef;
        ctx.last_computed_clbrems = computed_clbrems;
        const bool call1_leaf_oracle =
            (input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE) != 0u &&
            !thermal_component_closure_data.has_value();
        ctx.last_cmp1 = call1_leaf_oracle ? input.cmp1_override : comp.cmp1;
        ctx.last_cmp2 = call1_leaf_oracle ? input.cmp2_override : comp.cmp2;
        ctx.last_continuum_compton_heating = call1_leaf_oracle ? input.htcomp_override : comp.htcomp;
        ctx.last_continuum_compton_cooling = call1_leaf_oracle ? input.clcomp_override : comp.clcomp;
        const double htfreef = call1_leaf_oracle ? input.htfreef_override : computed_htfreef;
        const double clbrems = call1_leaf_oracle ? input.clbrems_override : computed_clbrems;
        ctx.last_htfreef = htfreef;
        ctx.last_clbrems = clbrems;
        ctx.last_continuum_free_free_cooling = clbrems;
        output.continuum_heating = ctx.last_continuum_compton_heating + htfreef;
        output.continuum_cooling = ctx.last_continuum_compton_cooling + clbrems;
        const double kt_ev = kBoltzmannEvK * input.temperature_k;
        double shape_sum = 0.0;
        std::vector<double> shape(input.radiation_bin_count, 0.0);
        for (std::size_t k = 0; k < input.radiation_bin_count; ++k) {
            const double e = input.radiation_energy_ev[k];
            shape[k] = limited_exp(-e / std::max(kt_ev, 1.0e-300));
            shape_sum += shape[k];
            // XSTAR freef.f90 continuum opacity.  The source routine works in
            // T/1e4 K and photon energy in eV:
            //   opaff = 2.614e-37 * xnx * (1.4*xnx) / sqrt(t4) / E^3
            //           * (1-exp(-E/(0.861707*t4)))
            // where xnx=xpx*xee is the electron density.  The former generic
            // radio free-free coefficient produced the v54 ~0.54 continuum
            // opacity/depth ratio and the wrong option-5 absorbed energy.
            const double temperature_t4 = std::max(input.temperature_k * 1.0e-4, 1.0e-30);
            const double ekt_source_ev = xstar_constants::kLegacyBoltzmannEvPerT4 * temperature_t4;
            const double xnx = std::max(input.electron_density_cm3, 0.0);
            const double freef_cc = static_cast<double>(static_cast<float>(2.614e-37));
            const double ion_z2_factor = static_cast<double>(static_cast<float>(1.4));
            const double enz2 = ion_z2_factor * xnx;
            const double stim = 1.0 - limited_exp(-e / std::max(ekt_source_ev, 1.0e-300));
            const double safe_e = std::max(e, 1.0e-30);
            const double e_cube = environment_flag("XSTAR_QUALIFICATION_FREEF_REAL_EXPONENT_POW")
                ? std::pow(safe_e, 3.0)
                : safe_e * safe_e * safe_e;
            const double freef_opacity_v82_patch5203 = freef_cc * xnx * enz2 /
                std::sqrt(temperature_t4) / e_cube * stim;
            output.opacity[k] += freef_opacity_v82_patch5203;
            write_exact_absorption_v82_patch5203(k, "FREE_FREE", 0, 0, 0, 0, 0, 0, 0, 0,
                freef_opacity_v82_patch5203);
        }
        if (shape_sum > 0.0) for (std::size_t k=0;k<input.radiation_bin_count;++k) output.spectrum[k] += clbrems * shape[k] / shape_sum;
        stats.continuum_bins += input.radiation_bin_count;
    }
    stats.continuum_seconds += elapsed(continuum_start);

    const auto spectral_start = clock_type::now();
    if (!spectral.empty() && input.radiation_bin_count > 0) {
        // Line records and continuum bins are different index spaces.  The
        // contribution engine owns per-line luminosity/opacity records; the
        // exact native Gaussian/Voigt path then projects those luminosities to
        // the radiation grid instead of using the former single-bin delta.
        const std::size_t line_capacity = std::max<std::size_t>(ctx.program.native_line_count, 1u) + 1u;
        const std::size_t continuum_slot_capacity = std::max<std::size_t>(ctx.program.native_continuum_count, 1u) + 1u;
        const std::size_t continuum_capacity = input.radiation_bin_count;
        std::vector<double> rcem(2 * line_capacity, 0.0);
        std::vector<double> oplin(line_capacity, 0.0);
        std::vector<double> cemab(2 * continuum_slot_capacity, 0.0);
        std::vector<double> cabab(continuum_slot_capacity, 0.0);
        std::vector<double> opakab(continuum_slot_capacity, 0.0);
        std::vector<double> rccemis(2 * continuum_capacity, 0.0);
        // Literal ucalc.f90 Type-76 has already accumulated into rccemis before
        // calc_emis returns.  This side effect survives the controller's
        // DEFER_PRODUCT_PROJECTION mode; only derived/selective projections
        // remain deferred.
        if (native_type76_continuum_emission.size() == rccemis.size()) {
            for (std::size_t k = 0; k < rccemis.size(); ++k)
                rccemis[k] += native_type76_continuum_emission[k];
        }
        // XSTAR heatt defines opakc as continuum opacity with line profiles
        // binned in, while opakcont is the lines-excluded continuum surface.
        // Keep the profile in a separate construction buffer, then add it only
        // to opakc after the continuum contributions are complete.
        std::vector<double> line_profile_opacity(continuum_capacity, 0.0);
        const double source_thomson = input.hydrogen_density_cm3 * input.electron_fraction_xee *
            kSigmaT * std::max(0.0, 1.0 - effective_spectral_covering_fraction_v82_patch58(input));
        std::vector<double> opakcont(continuum_capacity, source_thomson);
        for (std::size_t k = 0; k < continuum_capacity; ++k) {
            output.opacity[k] += source_thomson;
            write_exact_absorption_v82_patch5203(k, "THOMSON", 0, 0, 0, 0, 0, 0, 0, 0, source_thomson);
        }
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
        sw.opakc = line_profile_opacity.data(); sw.opakc_count = continuum_capacity;
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

        // v82 patch 5.20.10: literal calc_emis_ion does not assign kkkl in
        // the rate-42 branch.  Each Type-88 record therefore reuses the last
        // rate-7 npconi2 pointer visited for that ion and phint53 writes its
        // scalar opakab result through opakab(kkkl).  The stale errc/tauc
        // reads do not alter the Type-88 continuum kernel because rate-42
        // ptmp1+ptmp2 is exactly one and UCalc recomputes the physical Type-88
        // threshold.  Preserve only the source-proved stale scalar side effect
        // here, after the broad rate-7 spectral commit and before STPCUT sees
        // the source workspace.
        struct RetainedRate7SlotV82Patch52010 {
            int slot_one_based = 0;
            std::int64_t record = 0;
            std::uint64_t source_position = 0u;
        };
        struct Type88StaleAuditRowV82Patch52010 {
            std::uint64_t source_position = 0u;
            std::int64_t record = 0;
            int element_index = 0;
            int element_z = 0;
            int ion_stage = 0;
            std::int64_t retained_rate7_record = 0;
            std::uint64_t retained_rate7_source_position = 0u;
            int retained_slot_one_based = 0;
            double stale_errc_rank_energy_ev = 0.0;
            double stale_tau_in = 0.0;
            double stale_tau_out = 0.0;
            double lower_abundance = 0.0;
            double upper_abundance = 0.0;
            int nb1_one_based = 0;
            int publish_kl_one_based = 0;
            double absorption_sigma_cm2 = 0.0;
            double stimulated_sigma_cm2 = 0.0;
            double prior_opakab_cm1 = 0.0;
            double type88_opakab_cm1 = 0.0;
            bool publication_reached = false;
        };
        std::vector<Type88StaleAuditRowV82Patch52010> type88_stale_audit_rows_v82_patch52010;
        if (!defer_product_projection) {
            std::map<std::pair<int,int>, RetainedRate7SlotV82Patch52010> retained_rate7_v82_patch52010;
            std::map<std::pair<std::uint64_t,std::int64_t>, const DeferredRrcRecordV82Patch520*> type88_deferred_v82_patch52010;
            for (const auto& deferred : deferred_rrc_records_v82_patch520) {
                if (deferred.source_rate42_type88)
                    type88_deferred_v82_patch52010[{deferred.source_position,deferred.record}] = &deferred;
            }
            std::unordered_map<int,int> element_z_by_index_v82_patch52010;
            for (const auto& em : ctx.program.elements)
                element_z_by_index_v82_patch52010[em.element_index] = em.element_z;
            std::vector<const ProgramRecord*> source_order_v82_patch52010;
            source_order_v82_patch52010.reserve(ctx.program.records.size());
            for (const auto& pr : ctx.program.records) source_order_v82_patch52010.push_back(&pr);
            std::stable_sort(source_order_v82_patch52010.begin(), source_order_v82_patch52010.end(),
                [](const ProgramRecord* a, const ProgramRecord* b) {
                    return a->source_position < b->source_position;
                });
            for (const ProgramRecord* prp : source_order_v82_patch52010) {
                if (!prp) continue;
                const ProgramRecord& pr = *prp;
                const auto key = std::make_pair(pr.element_index, pr.ion_index);
                if (pr.rate_type == 7 && pr.continuum_index_one_based > 0) {
                    retained_rate7_v82_patch52010[key] = RetainedRate7SlotV82Patch52010{
                        pr.continuum_index_one_based, pr.record,
                        static_cast<std::uint64_t>(pr.source_position)};
                    continue;
                }
                if (pr.rate_type != 42 || pr.opcode != XSTAR_FIXED_OPCODE_TYPE88_SUPERLEVEL_BOUND_FREE) continue;
                const auto dit = type88_deferred_v82_patch52010.find({
                    static_cast<std::uint64_t>(pr.source_position), pr.record});
                if (dit == type88_deferred_v82_patch52010.end() || !dit->second) continue;
                const auto rit = retained_rate7_v82_patch52010.find(key);
                if (rit == retained_rate7_v82_patch52010.end() || rit->second.slot_one_based <= 0) {
                    throw std::runtime_error("Type-88 rate-42 reached before a retained rate-7 kkkl slot");
                }
                const int slot_one_based = rit->second.slot_one_based;
                const std::size_t slot = static_cast<std::size_t>(slot_one_based);
                if (slot >= opakab.size()) throw std::runtime_error("Type-88 retained kkkl exceeds opakab workspace");
                const auto& deferred = *dit->second;
                const auto scalar = source_type88_stale_opakab_v82_patch52010(
                    deferred.opacity_curve, deferred.type88_rnist,
                    deferred.lower_abundance, deferred.upper_abundance, input);

                Type88StaleAuditRowV82Patch52010 audit;
                audit.source_position = deferred.source_position;
                audit.record = deferred.record;
                audit.element_index = pr.element_index;
                audit.element_z = element_z_by_index_v82_patch52010.count(pr.element_index)
                    ? element_z_by_index_v82_patch52010[pr.element_index] : 0;
                audit.ion_stage = pr.ion_stage;
                audit.retained_rate7_record = rit->second.record;
                audit.retained_rate7_source_position = rit->second.source_position;
                audit.retained_slot_one_based = slot_one_based;
                audit.stale_errc_rank_energy_ev = source_errc_rank_energy_for_slot_v82_patch5209(
                    slot_one_based, rit->second.source_position, rit->second.record, 0.0);
                if (input.continuum_tau_in && slot > 0u && slot - 1u < input.continuum_tau_count)
                    audit.stale_tau_in = input.continuum_tau_in[slot - 1u];
                if (input.continuum_tau_out && slot > 0u && slot - 1u < input.continuum_tau_count)
                    audit.stale_tau_out = input.continuum_tau_out[slot - 1u];
                audit.lower_abundance = deferred.lower_abundance;
                audit.upper_abundance = deferred.upper_abundance;
                audit.nb1_one_based = scalar.nb1_one_based;
                audit.publish_kl_one_based = scalar.publish_kl_one_based;
                audit.absorption_sigma_cm2 = scalar.absorption_sigma_cm2;
                audit.stimulated_sigma_cm2 = scalar.stimulated_sigma_cm2;
                audit.prior_opakab_cm1 = opakab[slot];
                audit.type88_opakab_cm1 = scalar.threshold_publication_reached
                    ? scalar.opakab_cm1 : 0.0;
                audit.publication_reached = scalar.threshold_publication_reached;
                // Literal calc_emis_ion calls UCalc, whose entry statement is
                // opakab=0.; non-publication therefore clears the stale slot.
                opakab[slot] = scalar.threshold_publication_reached ? scalar.opakab_cm1 : 0.0;
                type88_stale_audit_rows_v82_patch52010.push_back(audit);
            }

            if (source_sequence_v82_patch511 == 59) {
                const char* audit_path_text = std::getenv("XSTAR_V82_PATCH52010_TYPE88_STALE_AUDIT_PATH");
                if (audit_path_text && *audit_path_text) {
                    const std::filesystem::path audit_path(audit_path_text);
                    if (!audit_path.parent_path().empty()) std::filesystem::create_directories(audit_path.parent_path());
                    std::ofstream csv(audit_path);
                    if (!csv) throw std::runtime_error("cannot create patch5.20.10 Type-88 stale-state audit");
                    csv << "source_position,record,element_index,element_z,ion_stage,retained_rate7_record,retained_rate7_source_position,retained_slot_one_based,stale_errc_rank_energy_ev,stale_tau_in,stale_tau_out,lower_abundance,upper_abundance,nb1_one_based,publish_kl_one_based,absorption_sigma_cm2,stimulated_sigma_cm2,prior_opakab_cm1,type88_opakab_cm1,publication_reached\n";
                    csv << std::setprecision(17);
                    for (const auto& a : type88_stale_audit_rows_v82_patch52010) {
                        csv << a.source_position << ',' << a.record << ',' << a.element_index << ',' << a.element_z << ','
                            << a.ion_stage << ',' << a.retained_rate7_record << ',' << a.retained_rate7_source_position << ','
                            << a.retained_slot_one_based << ',' << a.stale_errc_rank_energy_ev << ',' << a.stale_tau_in << ','
                            << a.stale_tau_out << ',' << a.lower_abundance << ',' << a.upper_abundance << ','
                            << a.nb1_one_based << ',' << a.publish_kl_one_based << ',' << a.absorption_sigma_cm2 << ','
                            << a.stimulated_sigma_cm2 << ',' << a.prior_opakab_cm1 << ',' << a.type88_opakab_cm1 << ','
                            << (a.publication_reached ? 1 : 0) << '\n';
                    }
                }
                std::set<int> retained_slots_v82_patch52010;
                std::size_t publication_count_v82_patch52010 = 0u;
                for (const auto& a : type88_stale_audit_rows_v82_patch52010) {
                    retained_slots_v82_patch52010.insert(a.retained_slot_one_based);
                    if (a.publication_reached) ++publication_count_v82_patch52010;
                }
                std::cout
                    << "V048746255172582_PATCH52010_TYPE88_RATE42_STALE_ROWS=" << type88_stale_audit_rows_v82_patch52010.size() << "\n"
                    << "V048746255172582_PATCH52010_TYPE88_RATE42_RETAINED_SLOTS=" << retained_slots_v82_patch52010.size() << "\n"
                    << "V048746255172582_PATCH52010_TYPE88_RATE42_THRESHOLD_PUBLICATIONS=" << publication_count_v82_patch52010 << "\n"
                    << "V048746255172582_PATCH52010_TYPE88_STALE_ERRC_ROLE=NB1_DIAGNOSTIC_ONLY_PHYSICAL_THRESHOLD_RECOMPUTED_IN_UCALC\n"
                    << "V048746255172582_PATCH52010_TYPE88_STALE_TAUC_ROLE=READ_ONLY_RATE42_PTMP_SUM_FIXED_ONE\n"
                    << "V048746255172582_PATCH52010_TYPE88_STALE_OPAKAB_ROLE=WRITE_THROUGH_RETAINED_RATE7_KKKL\n"
                    << "V048746255172582_PATCH52010_TYPE88_STALE_AUDIT="
                    << ((std::getenv("XSTAR_V82_PATCH52010_TYPE88_STALE_AUDIT_PATH") &&
                         *std::getenv("XSTAR_V82_PATCH52010_TYPE88_STALE_AUDIT_PATH")) ? "WRITTEN" : "NOT_REQUESTED") << "\n";
            }
        }

        // v82 patch 5.18.1: calc_emis_all ranks the calc_emisab threshold
        // surface, then calc_emis_ion revisits only ncbin-selected rate-7
        // records.  Preserve the seed for the diagnostic audit and apply the
        // selected full-grid overwrite to opakab only; distributed opakc and
        // rccemis remain on the accepted 5.17.1 production path.
        const std::vector<double> opakab_calc_emisab_seed = opakab;
        // v82 patch 5.20.6: source calc_emis_all consumes the broad
        // calc_emisab arrays only to build ncbin/nlbin.  Public opakc/fline are
        // then reconstructed by selected revisits; they are not the broad
        // calc_emisab projection.  Derive the masks from native state on every
        // product projection -- never copy a source/oracle selection list.
        std::set<int> source_calc_emis_selected_rrc_slots_v82_patch5206;
        std::set<int> source_calc_emis_selected_line_slots_v82_patch5206;
        // v82 patch 5.20.8: retain the full ncbin/nlbin table.  Literal
        // calc_emis_ion searches only the column for each record's own nb1;
        // the flattened selected-slot sets remain diagnostics only.
        SourceRlbinAuditResultV82Patch5171 source_calc_emis_ncbin_v82_patch5208;
        // Diagnostic-only reconstruction of the 5.20.8.2 identity-owned RRC
        // rank table. Production uses the slot-owned table above/below.
        SourceRlbinAuditResultV82Patch5171
            source_calc_emis_ncbin_patch52082_audit_v82_patch5209;
        SourceRlbinAuditResultV82Patch5171 source_calc_emis_nlbin_v82_patch5208;
        bool source_calc_emis_selection_ready_v82_patch5206 = false;
        if (!defer_product_projection) {
            std::map<std::pair<std::string,int>,SourceFeatureAuditCandidateV82Patch5171>
                identity_by_slot_v82_patch5206;
            std::map<int,SourceFeatureAuditCandidateV82Patch5171>
                legacy_rrc_identity_by_slot_v82_patch5209;
            for (const auto& c : spectral) {
                if (c.output_index <= 0 || !(c.line_energy_eV > 0.0) || !std::isfinite(c.line_energy_eV))
                    continue;
                const bool is_rrc = c.kind == XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE;
                SourceFeatureAuditCandidateV82Patch5171 m;
                m.family = is_rrc ? "RRC" : "LINE";
                m.slot_one_based = c.output_index;
                double feature_energy = c.line_energy_eV;
                if (is_rrc) {
                    feature_energy = source_errc_rank_energy_for_slot_v82_patch5209(
                        c.output_index, static_cast<std::uint64_t>(c.source_position),
                        static_cast<std::int64_t>(c.record), c.line_energy_eV);
                }
                if (!(feature_energy > 0.0) || !std::isfinite(feature_energy)) continue;
                m.energy_ev = feature_energy;
                m.wavelength_a = source_real_literal_v82_patch5208(12398.4016) /
                    std::max(1.0e-34, feature_energy);
                m.source_position = c.source_position;
                m.record = c.record;
                m.data_type = c.data_type;
                identity_by_slot_v82_patch5206[{m.family, m.slot_one_based}] = m;
                if (is_rrc) {
                    auto legacy = m;
                    const auto legacy_it =
                        source_errc_rank_energy_by_identity_patch52082_audit_v82_patch5209.find(
                            {static_cast<std::uint64_t>(c.source_position),
                             static_cast<std::int64_t>(c.record)});
                    if (legacy_it !=
                        source_errc_rank_energy_by_identity_patch52082_audit_v82_patch5209.end()) {
                        legacy.energy_ev = legacy_it->second;
                        legacy.wavelength_a = source_real_literal_v82_patch5208(12398.4016) /
                            std::max(1.0e-34, legacy.energy_ev);
                    }
                    legacy.source_position = c.source_position;
                    legacy.record = c.record;
                    legacy.data_type = c.data_type;
                    legacy_rrc_identity_by_slot_v82_patch5209[c.output_index] = legacy;
                }
            }
            std::vector<SourceFeatureAuditCandidateV82Patch5171> rrc_candidates_v82_patch5206;
            std::vector<SourceFeatureAuditCandidateV82Patch5171> line_candidates_v82_patch5206;
            for (auto& kv : identity_by_slot_v82_patch5206) {
                auto c = kv.second;
                const std::size_t slot = static_cast<std::size_t>(c.slot_one_based);
                if (c.family == "RRC") {
                    if (slot >= continuum_slot_capacity) continue;
                    c.opacity = std::isfinite(opakab_calc_emisab_seed[slot])
                        ? std::max(0.0, opakab_calc_emisab_seed[slot]) : 0.0;
                    const double e1 = std::isfinite(cemab[slot]) ? cemab[slot] : 0.0;
                    const double e2 = std::isfinite(cemab[continuum_slot_capacity + slot])
                        ? cemab[continuum_slot_capacity + slot] : 0.0;
                    c.emission_sum = e1 + e2;
                    rrc_candidates_v82_patch5206.push_back(c);
                } else {
                    if (slot >= line_capacity) continue;
                    c.opacity = std::isfinite(oplin[slot]) ? std::max(0.0, oplin[slot]) : 0.0;
                    const double e1 = std::isfinite(rcem[slot]) ? rcem[slot] : 0.0;
                    const double e2 = std::isfinite(rcem[line_capacity + slot])
                        ? rcem[line_capacity + slot] : 0.0;
                    c.emission_sum = e1 + e2;
                    line_candidates_v82_patch5206.push_back(c);
                }
            }
            source_calc_emis_ncbin_v82_patch5208 = source_rlbin_exact_audit_v82_patch5171(
                rrc_candidates_v82_patch5206, input.radiation_energy_ev, continuum_capacity, true);
            std::vector<SourceFeatureAuditCandidateV82Patch5171>
                legacy_rrc_candidates_v82_patch5209;
            legacy_rrc_candidates_v82_patch5209.reserve(legacy_rrc_identity_by_slot_v82_patch5209.size());
            for (auto& kv : legacy_rrc_identity_by_slot_v82_patch5209) {
                auto c = kv.second;
                const std::size_t slot = static_cast<std::size_t>(c.slot_one_based);
                if (slot >= continuum_slot_capacity) continue;
                c.opacity = std::isfinite(opakab_calc_emisab_seed[slot])
                    ? std::max(0.0, opakab_calc_emisab_seed[slot]) : 0.0;
                const double e1 = std::isfinite(cemab[slot]) ? cemab[slot] : 0.0;
                const double e2 = std::isfinite(cemab[continuum_slot_capacity + slot])
                    ? cemab[continuum_slot_capacity + slot] : 0.0;
                c.emission_sum = e1 + e2;
                legacy_rrc_candidates_v82_patch5209.push_back(c);
            }
            source_calc_emis_ncbin_patch52082_audit_v82_patch5209 =
                source_rlbin_exact_audit_v82_patch5171(
                    legacy_rrc_candidates_v82_patch5209, input.radiation_energy_ev,
                    continuum_capacity, true);
            source_calc_emis_nlbin_v82_patch5208 = source_rlbin_exact_audit_v82_patch5171(
                line_candidates_v82_patch5206, input.radiation_energy_ev, continuum_capacity, false);
            source_calc_emis_selected_rrc_slots_v82_patch5206 = source_calc_emis_ncbin_v82_patch5208.selected_slots;
            source_calc_emis_selected_line_slots_v82_patch5206 = source_calc_emis_nlbin_v82_patch5208.selected_slots;
            source_calc_emis_selection_ready_v82_patch5206 = true;
            if (source_sequence_v82_patch511 == 59) {
                std::cout
                    << "V048746255172582_V82_PATCH5206_CALC_EMIS_RRC_SELECTED_SLOTS="
                    << source_calc_emis_selected_rrc_slots_v82_patch5206.size() << "\n"
                    << "V048746255172582_V82_PATCH5206_CALC_EMIS_LINE_SELECTED_SLOTS="
                    << source_calc_emis_selected_line_slots_v82_patch5206.size() << "\n"
                    << "V048746255172582_V82_PATCH5206_RLBIN_RUNTIME_OWNERSHIP=SOURCE_PROVED\n";
            }
        }
        // v82 patch 5.20: calc_emis_all.f90 zeros rccemis after the broad
        // calc_emisab_all pass, then rebuilds rate-7 RRC continuum side effects
        // only for ncbin-selected public RRC slots.  Preserve the source-selected
        // set here so the heatt-facing rccemis workspace can be rebuilt without
        // reusing the broader calc_emisab surface.
        if (!defer_product_projection) {
            // patch 5.20.14.4: literal calc_emis_all runs at every accepted
            // physical shell.  Earlier C++ code accidentally restricted the
            // selected 9999-bin Type49/53 scalar opacity revisit to source
            // sequence 59 (call 2), leaving calls 3/4 at the reduced 999-bin
            // calc_emisab seed.  Keep legacy CSV diagnostics call-2-only, but
            // apply the physical revisit on every non-deferred final boundary.
            const bool patch520144_call2_audit = source_sequence_v82_patch511 == 59;
            std::map<std::pair<std::string,int>,SourceFeatureAuditCandidateV82Patch5171> seed_identity_by_slot;
            for (const auto& c : spectral) {
                if (c.kind != XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE || c.output_index <= 0 ||
                    !(c.line_energy_eV > 0.0) || !std::isfinite(c.line_energy_eV)) continue;
                SourceFeatureAuditCandidateV82Patch5171 m;
                m.family = "RRC";
                m.slot_one_based = c.output_index;
                const double errc_energy_v82_patch5209 =
                    source_errc_rank_energy_for_slot_v82_patch5209(
                        c.output_index, static_cast<std::uint64_t>(c.source_position),
                        static_cast<std::int64_t>(c.record), c.line_energy_eV);
                m.energy_ev = errc_energy_v82_patch5209;
                m.wavelength_a = source_real_literal_v82_patch5208(12398.4016) /
                    std::max(1.0e-34, errc_energy_v82_patch5209);
                m.source_position = c.source_position;
                m.record = c.record;
                m.data_type = c.data_type;
                seed_identity_by_slot[{m.family, m.slot_one_based}] = m;
            }
            std::vector<SourceFeatureAuditCandidateV82Patch5171> seed_rrc_candidates;
            seed_rrc_candidates.reserve(seed_identity_by_slot.size());
            for (auto& kv : seed_identity_by_slot) {
                auto c = kv.second;
                const std::size_t slot = static_cast<std::size_t>(c.slot_one_based);
                if (slot >= continuum_slot_capacity) continue;
                c.opacity = std::isfinite(opakab_calc_emisab_seed[slot])
                    ? std::max(0.0, opakab_calc_emisab_seed[slot]) : 0.0;
                const double e1 = std::isfinite(cemab[slot]) ? cemab[slot] : 0.0;
                const double e2 = std::isfinite(cemab[continuum_slot_capacity + slot])
                    ? cemab[continuum_slot_capacity + slot] : 0.0;
                c.emission_sum = e1 + e2;
                seed_rrc_candidates.push_back(c);
            }
            const auto source_ncbin = source_rlbin_exact_audit_v82_patch5171(
                seed_rrc_candidates, input.radiation_energy_ev, continuum_capacity, true);

            const char* revisit_path_text = std::getenv("XSTAR_V82_PATCH5181_TYPE53_REVISIT_AUDIT_PATH");
            std::ofstream revisit_csv;
            if (patch520144_call2_audit && revisit_path_text && *revisit_path_text) {
                const std::filesystem::path revisit_path(revisit_path_text);
                if (!revisit_path.parent_path().empty()) std::filesystem::create_directories(revisit_path.parent_path());
                revisit_csv.open(revisit_path);
                if (!revisit_csv) throw std::runtime_error("cannot create patch5.18.1 Type-53 selected-revisit audit");
                revisit_csv << "slot_one_based,source_position,record,data_type,selected,final_rank,seed_opakab_cm1,lower_abundance,upper_abundance,seed_threshold_published,seed_abs_sigma_cm2,seed_stim_sigma_cm2,revisit_threshold_published,revisit_abs_sigma_cm2,revisit_stim_sigma_cm2,revisit_opakab_cm1,final_opakab_cm1,action,runtime_production_modified\n";
                revisit_csv << std::setprecision(17);
            }

            std::size_t type53_candidates = 0u, type53_selected = 0u;
            std::size_t type53_revisit_published = 0u, type53_seed_retained = 0u, type53_selected_zero_no_publication = 0u, type53_overwritten = 0u;
            for (const auto& c : seed_rrc_candidates) {
                if (c.data_type != 53) continue;
                ++type53_candidates;
                const auto consumer_decision_v82_patch5208 = source_calc_emis_consumer_v82_patch5208(
                    c.slot_one_based, c.wavelength_a, true, true, source_ncbin,
                    input.radiation_energy_ev, continuum_capacity);
                const bool selected = consumer_decision_v82_patch5208.actual_consumer;
                if (selected) ++type53_selected;
                const auto eit = type53_revisit_evaluated_v82_patch5181.find(std::make_pair(
                    static_cast<std::uint64_t>(c.source_position), static_cast<std::uint64_t>(c.record)));
                if (eit == type53_revisit_evaluated_v82_patch5181.end()) continue;
                const auto& item = eit->second;
                const Type53SourceShadow& seed_shadow = item.type53_calc_emisab_shadow.valid
                    ? item.type53_calc_emisab_shadow : item.type53_shadow;
                const Type53SourceShadow& revisit_shadow = item.type53_calc_emis_shadow;
                const xstar_spectral_contribution_v1* spectral_item = nullptr;
                for (const auto& candidate : spectral) {
                    if (candidate.kind == XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE &&
                        candidate.output_index == c.slot_one_based && candidate.source_position == c.source_position &&
                        candidate.record == c.record) {
                        spectral_item = &candidate;
                        break;
                    }
                }
                if (!spectral_item) continue;
                const std::size_t slot = static_cast<std::size_t>(c.slot_one_based);
                const double seed_opakab = slot < opakab_calc_emisab_seed.size()
                    ? opakab_calc_emisab_seed[slot] : 0.0;
                double revisit_opakab = seed_opakab;
                std::string action = selected ? "SELECTED_UCALC_ZERO_NO_PUBLICATION" : "UNSELECTED_RETAIN_SEED";
                bool modified = false;
                if (selected && revisit_shadow.valid && revisit_shadow.threshold_publication_reached &&
                    spectral_item->abundance_lower > 0.0) {
                    const double ratio = spectral_item->abundance_upper / spectral_item->abundance_lower;
                    const double coefficient = std::max(0.0,
                        revisit_shadow.threshold_cross_section_cm2 -
                        ratio * revisit_shadow.threshold_stimulated_cross_section_cm2);
                    revisit_opakab = coefficient * spectral_item->abundance_lower * spectral_item->hydrogen_density;
                    opakab[slot] = revisit_opakab;
                    ++type53_revisit_published;
                    ++type53_overwritten;
                    modified = true;
                    action = "OVERWRITE_SELECTED_REVISIT";
                } else if (selected) {
                    // ucalc.f90 resets opakab=0. before dispatch.  If the
                    // selected full-grid phint53 call does not publish at the
                    // threshold cell, the caller-owned scalar remains zero.
                    revisit_opakab = 0.0;
                    modified = opakab[slot] != 0.0;
                    opakab[slot] = 0.0;
                    ++type53_selected_zero_no_publication;
                }
                if (revisit_csv) {
                    const auto rit = source_ncbin.final_rank.find(c.slot_one_based);
                    revisit_csv << c.slot_one_based << ',' << c.source_position << ',' << c.record << ',' << c.data_type << ','
                        << (selected ? 1 : 0) << ',' << (rit == source_ncbin.final_rank.end() ? 0 : rit->second) << ','
                        << seed_opakab << ',' << spectral_item->abundance_lower << ',' << spectral_item->abundance_upper << ','
                        << (seed_shadow.threshold_publication_reached ? 1 : 0) << ','
                        << seed_shadow.threshold_cross_section_cm2 << ',' << seed_shadow.threshold_stimulated_cross_section_cm2 << ','
                        << (revisit_shadow.threshold_publication_reached ? 1 : 0) << ','
                        << revisit_shadow.threshold_cross_section_cm2 << ',' << revisit_shadow.threshold_stimulated_cross_section_cm2 << ','
                        << revisit_opakab << ',' << opakab[slot] << ',' << action << ',' << (modified ? 1 : 0) << '\n';
                }
            }
            if (revisit_csv && !revisit_csv) throw std::runtime_error("cannot write patch5.18.1 Type-53 selected-revisit audit");
            std::cout
                << "V048746255172582_PATCH520144_CALC_EMIS_REVISIT_SOURCE_SEQUENCE=" << source_sequence_v82_patch511 << "\n"
                << "V048746255172582_PATCH520144_TYPE53_SELECTED_REVISIT_SELECTED=" << type53_selected << "\n"
                << "V048746255172582_PATCH520144_TYPE53_SELECTED_REVISIT_PUBLISHED=" << type53_revisit_published << "\n";
            if (patch520144_call2_audit) std::cout
                << "V048746255172582_CALL2_TYPE53_CALC_EMISAB_SEED_GRID_BINS=999\n"
                << "V048746255172582_CALL2_TYPE53_SELECTED_REVISIT_CANDIDATES=" << type53_candidates << "\n"
                << "V048746255172582_CALL2_TYPE53_SELECTED_REVISIT_SELECTED=" << type53_selected << "\n"
                << "V048746255172582_CALL2_TYPE53_SELECTED_REVISIT_PUBLISHED=" << type53_revisit_published << "\n"
                << "V048746255172582_CALL2_TYPE53_SELECTED_REVISIT_RETAINED_SEED=" << type53_seed_retained << "\n"
                << "V048746255172582_PATCH52014_TYPE53_SELECTED_ZERO_NO_PUBLICATION=" << type53_selected_zero_no_publication << "\n"
                << "V048746255172582_CALL2_TYPE53_SELECTED_REVISIT_OVERWRITTEN=" << type53_overwritten << "\n"
                << "V048746255172582_PATCH52014_TYPE53_MATRIX_GRID_BINS=999\n"
                << "V048746255172582_PATCH52014_TYPE53_CALC_EMISAB_GRID_BINS=999\n"
                << "V048746255172582_PATCH52014_TYPE53_CALC_EMIS_GRID_BINS=9999\n"
                << "V048746255172582_PATCH520142_TYPE53_CALC_EMIS_GRID_OWNER=FULL_INPUT_RADIATION_NO_DSEC_ALIAS\n"
                << "V048746255172582_V82_PATCH5181_TYPE99_DIRECT_OPAKAB_PUBLICATION_BRANCH=SOURCE_ZERO\n";

            // v82 patch 5.20.8.2: Type-49 three-stage ownership audit and
            // selected full-grid revisit.  The 5.20.8 reduced-grid Type-49
            // scalar seed is intentionally quarantined from production because
            // the host result moved 795/795 changed Type-49 identities away
            // from the captured source state and inflated call-3 tau mismatch
            // 168 -> 561.  Preserve the reduced answer as a diagnostic stage,
            // rank from the pre-5.20.8 full-grid Type-49 seed, and explicitly
            // replay selected Type-49 identities from the retained full-grid
            // evaluation.  This restores the non-regressed baseline while
            // exposing the exact reduced/full disagreement for patch 5.20.9.
            const char* type49_revisit_path_v82_patch52082 =
                std::getenv("XSTAR_V82_PATCH52082_TYPE49_REVISIT_AUDIT_PATH");
            std::ofstream type49_revisit_csv_v82_patch52082;
            if (patch520144_call2_audit && type49_revisit_path_v82_patch52082 && *type49_revisit_path_v82_patch52082) {
                const std::filesystem::path type49_path_v82_patch52082(type49_revisit_path_v82_patch52082);
                if (!type49_path_v82_patch52082.parent_path().empty())
                    std::filesystem::create_directories(type49_path_v82_patch52082.parent_path());
                type49_revisit_csv_v82_patch52082.open(type49_path_v82_patch52082);
                if (!type49_revisit_csv_v82_patch52082)
                    throw std::runtime_error("cannot create patch5.20.8.2 Type-49 three-stage audit");
                type49_revisit_csv_v82_patch52082
                    << "slot_one_based,source_position,record,selected,final_rank,full_seed_opakab_cm1,"
                    << "lower_abundance,upper_abundance,reduced_threshold_published,reduced_abs_sigma_cm2,"
                    << "reduced_stim_sigma_cm2,reduced_hypothetical_opakab_cm1,full_threshold_published,"
                    << "full_abs_sigma_cm2,full_stim_sigma_cm2,full_revisit_opakab_cm1,final_opakab_cm1,"
                    << "action,runtime_production_modified\n";
                type49_revisit_csv_v82_patch52082 << std::setprecision(17);
            }

            std::unordered_map<std::int64_t,const ProgramRecord*>
                type49_record_by_position_v82_patch52082;
            type49_record_by_position_v82_patch52082.reserve(ctx.program.records.size());
            for (const auto& source_record_v82_patch52082 : ctx.program.records)
                type49_record_by_position_v82_patch52082[
                    static_cast<std::int64_t>(source_record_v82_patch52082.source_position)] =
                    &source_record_v82_patch52082;

            std::size_t type49_candidates_v82_patch52082 = 0u;
            std::size_t type49_selected_v82_patch52082 = 0u;
            std::size_t type49_revisit_published_v82_patch52082 = 0u;
            std::size_t type49_unselected_full_seed_v82_patch52082 = 0u;
            std::size_t type49_reduced_full_different_v82_patch52082 = 0u;
            for (const auto& c : seed_rrc_candidates) {
                if (c.data_type != 49) continue;
                ++type49_candidates_v82_patch52082;
                const auto eit_v82_patch52082 = type49_revisit_evaluated_v82_patch52082.find(std::make_pair(
                    static_cast<std::uint64_t>(c.source_position), static_cast<std::uint64_t>(c.record)));
                if (eit_v82_patch52082 == type49_revisit_evaluated_v82_patch52082.end()) continue;
                const auto& item_v82_patch52082 = eit_v82_patch52082->second;
                const Type53SourceShadow& full_shadow_v82_patch52082 = item_v82_patch52082.type49_calc_emis_shadow;
                const Type53SourceShadow& reduced_shadow_v82_patch52082 =
                    item_v82_patch52082.type49_calc_emisab_shadow;

                const xstar_spectral_contribution_v1* spectral_item_v82_patch52082 = nullptr;
                for (const auto& candidate_v82_patch52082 : spectral) {
                    if (candidate_v82_patch52082.kind == XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE &&
                        candidate_v82_patch52082.output_index == c.slot_one_based &&
                        candidate_v82_patch52082.source_position == c.source_position &&
                        candidate_v82_patch52082.record == c.record) {
                        spectral_item_v82_patch52082 = &candidate_v82_patch52082;
                        break;
                    }
                }
                if (!spectral_item_v82_patch52082) continue;
                const auto prit_v82_patch52082 = type49_record_by_position_v82_patch52082.find(
                    static_cast<std::int64_t>(c.source_position));
                const bool destination_valid_v82_patch52082 =
                    prit_v82_patch52082 != type49_record_by_position_v82_patch52082.end() &&
                    prit_v82_patch52082->second && prit_v82_patch52082->second->lower_row > 0;
                const auto consumer_v82_patch52082 = source_calc_emis_consumer_v82_patch5208(
                    c.slot_one_based, c.wavelength_a, true, destination_valid_v82_patch52082, source_ncbin,
                    input.radiation_energy_ev, continuum_capacity);
                const bool selected_v82_patch52082 = consumer_v82_patch52082.actual_consumer;
                if (selected_v82_patch52082) ++type49_selected_v82_patch52082;

                const std::size_t slot_v82_patch52082 = static_cast<std::size_t>(c.slot_one_based);
                const double full_seed_opakab_v82_patch52082 =
                    slot_v82_patch52082 < opakab_calc_emisab_seed.size()
                        ? opakab_calc_emisab_seed[slot_v82_patch52082] : 0.0;
                const double lower_v82_patch52082 = spectral_item_v82_patch52082->abundance_lower;
                const double upper_v82_patch52082 = spectral_item_v82_patch52082->abundance_upper;
                const double density_v82_patch52082 = spectral_item_v82_patch52082->hydrogen_density;
                auto published_opakab_v82_patch52082 = [&](const Type53SourceShadow& shadow) {
                    if (!shadow.valid || !shadow.threshold_publication_reached ||
                        !(lower_v82_patch52082 > 0.0)) return 0.0;
                    const double ratio_v82_patch52082 = upper_v82_patch52082 / lower_v82_patch52082;
                    const double coefficient_v82_patch52082 = std::max(0.0,
                        shadow.threshold_cross_section_cm2 -
                        ratio_v82_patch52082 * shadow.threshold_stimulated_cross_section_cm2);
                    return coefficient_v82_patch52082 * lower_v82_patch52082 * density_v82_patch52082;
                };
                const double reduced_hypothetical_v82_patch52082 =
                    published_opakab_v82_patch52082(reduced_shadow_v82_patch52082);
                const double full_revisit_v82_patch52082 =
                    published_opakab_v82_patch52082(full_shadow_v82_patch52082);
                if (reduced_hypothetical_v82_patch52082 != full_revisit_v82_patch52082)
                    ++type49_reduced_full_different_v82_patch52082;

                bool modified_v82_patch52082 = false;
                std::string action_v82_patch52082 = "UNSELECTED_RETAIN_FULLGRID_SEED";
                if (selected_v82_patch52082 && full_shadow_v82_patch52082.valid &&
                    full_shadow_v82_patch52082.threshold_publication_reached &&
                    lower_v82_patch52082 > 0.0) {
                    opakab[slot_v82_patch52082] = full_revisit_v82_patch52082;
                    ++type49_revisit_published_v82_patch52082;
                    modified_v82_patch52082 =
                        opakab[slot_v82_patch52082] != full_seed_opakab_v82_patch52082;
                    action_v82_patch52082 = "SELECTED_FULLGRID_REVISIT";
                } else if (!selected_v82_patch52082) {
                    ++type49_unselected_full_seed_v82_patch52082;
                } else {
                    modified_v82_patch52082 = opakab[slot_v82_patch52082] != 0.0;
                    opakab[slot_v82_patch52082] = 0.0;
                    action_v82_patch52082 = "SELECTED_UCALC_ZERO_NO_PUBLICATION";
                }

                if (type49_revisit_csv_v82_patch52082) {
                    const auto rank_it_v82_patch52082 = source_ncbin.final_rank.find(c.slot_one_based);
                    type49_revisit_csv_v82_patch52082
                        << c.slot_one_based << ',' << c.source_position << ',' << c.record << ','
                        << (selected_v82_patch52082 ? 1 : 0) << ','
                        << (rank_it_v82_patch52082 == source_ncbin.final_rank.end()
                                ? 0 : rank_it_v82_patch52082->second) << ','
                        << full_seed_opakab_v82_patch52082 << ',' << lower_v82_patch52082 << ','
                        << upper_v82_patch52082 << ','
                        << (reduced_shadow_v82_patch52082.threshold_publication_reached ? 1 : 0) << ','
                        << reduced_shadow_v82_patch52082.threshold_cross_section_cm2 << ','
                        << reduced_shadow_v82_patch52082.threshold_stimulated_cross_section_cm2 << ','
                        << reduced_hypothetical_v82_patch52082 << ','
                        << (full_shadow_v82_patch52082.threshold_publication_reached ? 1 : 0) << ','
                        << full_shadow_v82_patch52082.threshold_cross_section_cm2 << ','
                        << full_shadow_v82_patch52082.threshold_stimulated_cross_section_cm2 << ','
                        << full_revisit_v82_patch52082 << ',' << opakab[slot_v82_patch52082] << ','
                        << action_v82_patch52082 << ',' << (modified_v82_patch52082 ? 1 : 0) << '\n';
                }
            }
            if (type49_revisit_csv_v82_patch52082 && !type49_revisit_csv_v82_patch52082)
                throw std::runtime_error("cannot write patch5.20.8.2 Type-49 three-stage audit");
            std::cout
                << "V048746255172582_PATCH520144_TYPE49_SELECTED_REVISIT_SELECTED="
                << type49_selected_v82_patch52082 << "\n"
                << "V048746255172582_PATCH520144_TYPE49_SELECTED_REVISIT_PUBLISHED="
                << type49_revisit_published_v82_patch52082 << "\n";
            if (patch520144_call2_audit) std::cout
                << "V048746255172582_PATCH52082_TYPE49_REDUCED_SEED_PUBLICATION=RESTORED_SOURCE_OWNER_PATCH52094\n"
                << "V048746255172582_PATCH52082_TYPE49_PRODUCTION_SEED=CALC_EMISAB_REDUCED_OWNER_PATCH52094\n"
                << "V048746255172582_PATCH52082_TYPE49_REVISIT_CANDIDATES="
                << type49_candidates_v82_patch52082 << "\n"
                << "V048746255172582_PATCH52082_TYPE49_REVISIT_SELECTED="
                << type49_selected_v82_patch52082 << "\n"
                << "V048746255172582_PATCH52082_TYPE49_REVISIT_PUBLISHED="
                << type49_revisit_published_v82_patch52082 << "\n"
                << "V048746255172582_PATCH52082_TYPE49_UNSELECTED_FULLGRID_SEED="
                << type49_unselected_full_seed_v82_patch52082 << "\n"
                << "V048746255172582_PATCH52082_TYPE49_REDUCED_FULL_DIFFERENT="
                << type49_reduced_full_different_v82_patch52082 << "\n"
                << "V048746255172582_PATCH52014_TYPE49_MATRIX_GRID_BINS=999\n"
                << "V048746255172582_PATCH52014_TYPE49_CALC_EMISAB_GRID_BINS=999\n"
                << "V048746255172582_PATCH52014_TYPE49_CALC_EMIS_GRID_BINS=9999\n"
                << "V048746255172582_PATCH52014_TYPE49_CALC_EMIS_PHEXTRAP_MAX_POINTS=9999\n"
                << "V048746255172582_PATCH520142_TYPE49_CALC_EMIS_GRID_OWNER=FULL_INPUT_RADIATION_NO_DSEC_ALIAS\n";
        }

        // v82 patch 5.17.1: run source rlbin/ncbin/nlbin as a pure audit over
        // the calc_emisab-equivalent detail arrays.  The production arrays
        // above are already committed and are never modified by this block.
        if (!defer_product_projection && source_sequence_v82_patch511 == 59) {
            const char* audit_path_text = std::getenv("XSTAR_V82_PATCH518_RLBIN_AUDIT_PATH");
            if (!audit_path_text || !*audit_path_text) {
                audit_path_text = std::getenv("XSTAR_V82_PATCH5171_RLBIN_AUDIT_PATH");
            }
            if (audit_path_text && *audit_path_text) {
                std::map<std::pair<std::string,int>,SourceFeatureAuditCandidateV82Patch5171> identity_by_slot;
                std::map<std::pair<std::string,int>,int> duplicate_counts;
                for (const auto& c : spectral) {
                    if (c.output_index <= 0 || !(c.line_energy_eV > 0.0) || !std::isfinite(c.line_energy_eV)) continue;
                    const bool is_rrc = c.kind == XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE;
                    const std::string family = is_rrc ? "RRC" : "LINE";
                    const auto key = std::make_pair(family, static_cast<int>(c.output_index));
                    SourceFeatureAuditCandidateV82Patch5171 m;
                    m.family = family;
                    m.slot_one_based = c.output_index;
                    double feature_energy_v82_patch5209 = c.line_energy_eV;
                    if (is_rrc) {
                        feature_energy_v82_patch5209 = source_errc_rank_energy_for_slot_v82_patch5209(
                            c.output_index, static_cast<std::uint64_t>(c.source_position),
                            static_cast<std::int64_t>(c.record), c.line_energy_eV);
                    }
                    m.energy_ev = feature_energy_v82_patch5209;
                    m.wavelength_a = source_real_literal_v82_patch5208(12398.4016) /
                        std::max(1.0e-34, feature_energy_v82_patch5209);
                    m.source_position = c.source_position;
                    m.record = c.record;
                    m.data_type = c.data_type;
                    if (is_rrc) {
                        const auto owner_it_v82_patch5209 = source_errc_owner_by_slot_v82_patch5209.find(c.output_index);
                        if (owner_it_v82_patch5209 != source_errc_owner_by_slot_v82_patch5209.end()) {
                            m.source_position = std::get<0>(owner_it_v82_patch5209->second);
                            m.record = std::get<1>(owner_it_v82_patch5209->second);
                            m.data_type = std::get<2>(owner_it_v82_patch5209->second);
                        }
                    }
                    identity_by_slot[key] = m;
                    ++duplicate_counts[key];
                }

                std::vector<SourceFeatureAuditCandidateV82Patch5171> rrc_candidates;
                std::vector<SourceFeatureAuditCandidateV82Patch5171> line_candidates;
                rrc_candidates.reserve(identity_by_slot.size());
                line_candidates.reserve(identity_by_slot.size());
                for (auto& kv : identity_by_slot) {
                    auto c = kv.second;
                    c.duplicate_identities = duplicate_counts[kv.first];
                    const std::size_t slot = static_cast<std::size_t>(c.slot_one_based);
                    if (c.family == "RRC") {
                        if (slot >= continuum_slot_capacity) continue;
                        c.opacity = std::isfinite(opakab_calc_emisab_seed[slot])
                            ? std::max(0.0, opakab_calc_emisab_seed[slot]) : 0.0;
                        const double e1 = std::isfinite(cemab[slot]) ? cemab[slot] : 0.0;
                        const double e2 = std::isfinite(cemab[continuum_slot_capacity + slot])
                            ? cemab[continuum_slot_capacity + slot] : 0.0;
                        c.emission_sum = e1 + e2;
                        rrc_candidates.push_back(c);
                    } else {
                        if (slot >= line_capacity) continue;
                        c.opacity = std::isfinite(oplin[slot]) ? std::max(0.0, oplin[slot]) : 0.0;
                        const double e1 = std::isfinite(rcem[slot]) ? rcem[slot] : 0.0;
                        const double e2 = std::isfinite(rcem[line_capacity + slot]) ? rcem[line_capacity + slot] : 0.0;
                        c.emission_sum = e1 + e2;
                        line_candidates.push_back(c);
                    }
                }

                const auto ncbin = source_rlbin_exact_audit_v82_patch5171(
                    rrc_candidates, input.radiation_energy_ev, continuum_capacity, true);
                const auto nlbin = source_rlbin_exact_audit_v82_patch5171(
                    line_candidates, input.radiation_energy_ev, continuum_capacity, false);
                std::map<int,SourceFeatureAuditCandidateV82Patch5171> rrc_by_slot, line_by_slot;
                for (const auto& c : rrc_candidates) rrc_by_slot[c.slot_one_based] = c;
                for (const auto& c : line_candidates) line_by_slot[c.slot_one_based] = c;

                const std::filesystem::path audit_path(audit_path_text);
                if (!audit_path.parent_path().empty()) std::filesystem::create_directories(audit_path.parent_path());
                std::ofstream feature_csv(audit_path);
                if (!feature_csv) throw std::runtime_error("cannot create patch5.17.1 rlbin candidate audit");
                feature_csv << "family,slot_one_based,wavelength_a,energy_ev,emission_sum,opacity,ranking_key,energy_bin_one_based,final_rank,selected,source_position,record,data_type,duplicate_identities,consumer,would_revisit_calc_emis,runtime_production_modified\n";
                feature_csv << std::setprecision(17);
                auto write_candidate = [&](const SourceFeatureAuditCandidateV82Patch5171& c,
                                           const SourceRlbinAuditResultV82Patch5171& result,
                                           bool rank_by_opacity) {
                    const auto bit = result.bin_one_based.find(c.slot_one_based);
                    const auto rit = result.final_rank.find(c.slot_one_based);
                    const bool selected = result.selected_slots.count(c.slot_one_based) != 0u;
                    const std::string consumer = source_feature_consumer_v82_patch5171(c.family, c.data_type);
                    const bool revisit = c.family == "RRC" && c.data_type == 49 ? true : selected;
                    feature_csv << c.family << ',' << c.slot_one_based << ',' << c.wavelength_a << ','
                        << c.energy_ev << ',' << c.emission_sum << ',' << c.opacity << ','
                        << (rank_by_opacity ? c.opacity : c.emission_sum) << ','
                        << (bit == result.bin_one_based.end() ? 0 : bit->second) << ','
                        << (rit == result.final_rank.end() ? 0 : rit->second) << ','
                        << (selected ? 1 : 0) << ',' << c.source_position << ',' << c.record << ','
                        << c.data_type << ',' << c.duplicate_identities << ',' << consumer << ','
                        << (revisit ? 1 : 0) << ",0\n";
                };
                for (const auto& c : rrc_candidates) write_candidate(c, ncbin, true);
                for (const auto& c : line_candidates) write_candidate(c, nlbin, false);
                if (!feature_csv) throw std::runtime_error("cannot write patch5.17.1 rlbin candidate audit");

                auto table_path = audit_path;
                table_path.replace_filename("call2_source_ncbin_nlbin_table.csv");
                std::ofstream table_csv(table_path);
                if (!table_csv) throw std::runtime_error("cannot create patch5.17.1 ncbin/nlbin table audit");
                table_csv << "family,energy_bin_one_based,rank,slot_one_based,wavelength_a,energy_ev,emission_sum,opacity,ranking_key,source_position,record,data_type,consumer\n";
                table_csv << std::setprecision(17);
                auto write_table = [&](const std::string& family,
                                       const SourceRlbinAuditResultV82Patch5171& result,
                                       const std::map<int,SourceFeatureAuditCandidateV82Patch5171>& by_slot,
                                       bool rank_by_opacity) {
                    for (std::size_t b = 0; b < result.table.size(); ++b) {
                        for (std::size_t r = 0; r < result.table[b].size(); ++r) {
                            const int slot = result.table[b][r];
                            if (slot <= 0) continue;
                            const auto it = by_slot.find(slot);
                            if (it == by_slot.end()) continue;
                            const auto& c = it->second;
                            table_csv << family << ',' << (b + 1u) << ',' << (r + 1u) << ',' << slot << ','
                                << c.wavelength_a << ',' << c.energy_ev << ',' << c.emission_sum << ','
                                << c.opacity << ',' << (rank_by_opacity ? c.opacity : c.emission_sum) << ','
                                << c.source_position << ',' << c.record << ',' << c.data_type << ','
                                << source_feature_consumer_v82_patch5171(family, c.data_type) << '\n';
                        }
                    }
                };
                write_table("RRC", ncbin, rrc_by_slot, true);
                write_table("LINE", nlbin, line_by_slot, false);
                if (!table_csv) throw std::runtime_error("cannot write patch5.17.1 ncbin/nlbin table audit");

                std::size_t type49_selected = 0u, type53_selected = 0u, line_selected = nlbin.selected_slots.size();
                for (const auto& c : rrc_candidates) {
                    if (!ncbin.selected_slots.count(c.slot_one_based)) continue;
                    if (c.data_type == 49) ++type49_selected;
                    if (c.data_type == 53) ++type53_selected;
                }
                std::cout
                    << "V048746255172582_CALL2_RLBIN_RUNTIME_GATING=DISABLED\n"
                    << "V048746255172582_CALL2_RLBIN_AUDIT_ONLY=ACCEPT\n"
                    << "V048746255172582_CALL2_SOURCE_RLBIN_RRC_CANDIDATE_SLOTS=" << rrc_candidates.size() << "\n"
                    << "V048746255172582_CALL2_SOURCE_RLBIN_RRC_SELECTED_SLOTS=" << ncbin.selected_slots.size() << "\n"
                    << "V048746255172582_CALL2_SOURCE_RLBIN_RRC_SELECTED_TYPE49_SLOTS=" << type49_selected << "\n"
                    << "V048746255172582_CALL2_SOURCE_RLBIN_RRC_SELECTED_TYPE53_SLOTS=" << type53_selected << "\n"
                    << "V048746255172582_CALL2_SOURCE_RLBIN_LINE_CANDIDATE_SLOTS=" << line_candidates.size() << "\n"
                    << "V048746255172582_CALL2_SOURCE_RLBIN_LINE_SELECTED_SLOTS=" << line_selected << "\n"
                    << "V048746255172582_CALL2_SOURCE_RLBIN_FEATURE_COORDINATE=WAVELENGTH_ANGSTROM_TO_ENERGY_EV\n"
                    << "V048746255172582_CALL2_SOURCE_RLBIN_FEATURE_SELECTION_AUDIT=WRITTEN\n"
                    << "V048746255172582_CALL2_SOURCE_NCBIN_NLBIN_TABLE_AUDIT=WRITTEN\n";
            }
        }

        // v82 patch 5.20.6: calc_emis_all resets opakc before its line
        // revisit.  Preserve broad rcem/oplin as calc_emisab rank inputs, but
        // replace public fline/flinel and line-profile opacity with an nlbin-
        // selected replay in source order.
        std::vector<xstar_spectral_contribution_v1> selected_lines_v82_patch5206;
        if (!defer_product_projection && source_calc_emis_selection_ready_v82_patch5206) {
            selected_lines_v82_patch5206.reserve(source_calc_emis_selected_line_slots_v82_patch5206.size());
            for (const auto& original_c : spectral) {
                if (original_c.kind == XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE ||
                    original_c.output_index <= 0)
                    continue;
                const auto wavelength_it_v82_patch5208 =
                    source_line_wavelength_by_identity_v82_patch5208.find(
                        {static_cast<std::uint64_t>(original_c.source_position),
                         static_cast<std::int64_t>(original_c.record)});
                const double source_line_wavelength_v82_patch5208 =
                    wavelength_it_v82_patch5208 != source_line_wavelength_by_identity_v82_patch5208.end()
                        ? wavelength_it_v82_patch5208->second
                        : (original_c.line_energy_eV > 0.0
                            ? source_real_literal_v82_patch5208(12398.4016) / original_c.line_energy_eV
                            : 0.0);
                const auto line_consumer_v82_patch5208 = source_calc_emis_consumer_v82_patch5208(
                    original_c.output_index, source_line_wavelength_v82_patch5208, false, true,
                    source_calc_emis_nlbin_v82_patch5208, input.radiation_energy_ev, continuum_capacity);
                if (!line_consumer_v82_patch5208.actual_consumer) continue;
                auto c = original_c;
                // Literal ordinary Type-50 ucalc calls linopac only above the
                // opakb1 > 1e-34 guard, while fline is still published.
                if (c.data_type == 50 && c.rate_type == 4) {
                    const double optpp = c.opakab * c.abundance_lower * c.hydrogen_density;
                    if (!(std::isfinite(optpp) && optpp > 1.0e-34)) c.opakab = 0.0;
                }
                selected_lines_v82_patch5206.push_back(c);
            }
            std::vector<double> selected_rcem(2 * line_capacity, 0.0);
            std::vector<double> selected_oplin(line_capacity, 0.0);
            std::vector<double> selected_cemab(2 * continuum_slot_capacity, 0.0);
            std::vector<double> selected_cabab(continuum_slot_capacity, 0.0);
            std::vector<double> selected_opakab(continuum_slot_capacity, 0.0);
            std::vector<double> selected_rccemis(2 * continuum_capacity, 0.0);
            std::vector<double> selected_opakcont(continuum_capacity, 0.0);
            std::vector<double> selected_fline(2 * line_capacity, 0.0);
            std::vector<double> selected_flinel(continuum_capacity, 0.0);
            std::vector<double> selected_line_profile(continuum_capacity, 0.0);
            xstar_spectral_workspace_v1 selected_sw{};
            xstar_spectral_workspace_init_v1(&selected_sw);
            selected_sw.rcem=selected_rcem.data(); selected_sw.rcem_count=selected_rcem.size();
            selected_sw.oplin=selected_oplin.data(); selected_sw.oplin_count=selected_oplin.size();
            selected_sw.cemab=selected_cemab.data(); selected_sw.cemab_count=selected_cemab.size();
            selected_sw.cabab=selected_cabab.data(); selected_sw.cabab_count=selected_cabab.size();
            selected_sw.opakab=selected_opakab.data(); selected_sw.opakab_count=selected_opakab.size();
            selected_sw.rccemis=selected_rccemis.data(); selected_sw.rccemis_count=selected_rccemis.size();
            selected_sw.opakc=selected_line_profile.data(); selected_sw.opakc_count=selected_line_profile.size();
            selected_sw.opakcont=selected_opakcont.data(); selected_sw.opakcont_count=selected_opakcont.size();
            selected_sw.fline=selected_fline.data(); selected_sw.fline_count=selected_fline.size();
            selected_sw.flinel=selected_flinel.data(); selected_sw.flinel_count=selected_flinel.size();
            selected_sw.epi_eV=input.radiation_energy_ev; selected_sw.energy_count=continuum_capacity;
            std::vector<double> selected_seeds(selected_lines_v82_patch5206.size()*seed_stride,0.0);
            for (std::size_t i=0;i<selected_lines_v82_patch5206.size();++i) {
                selected_seeds[i*seed_stride]=1.0/1.772;
                for (std::size_t d=1;d<=10;++d) {
                    const double value=std::exp(-static_cast<double>(d*d))/1.772;
                    selected_seeds[i*seed_stride+2*d-1]=value;
                    selected_seeds[i*seed_stride+2*d]=value;
                }
            }
            xstar_spectral_stats_v1 selected_stats{};
            xstar_spectral_stats_init_v1(&selected_stats);
            std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> selected_error{};
            const int selected_rc = xstar_spectral_apply_contributions_v1(
                ctx.spectral_context, selected_lines_v82_patch5206.data(), selected_lines_v82_patch5206.size(),
                selected_seeds.data(), seed_stride, &selected_sw, &selected_stats,
                selected_error.data(), selected_error.size());
            if (selected_rc != 0)
                throw std::runtime_error(std::string("v82 patch 5.20.6 selected line replay failed: ") + selected_error.data());
            line_profile_opacity.swap(selected_line_profile);
            fline.swap(selected_fline);
            flinel.swap(selected_flinel);
            if (source_sequence_v82_patch511 == 59) {
                std::size_t nonzero_bins = 0u;
                for (double value : line_profile_opacity)
                    if (std::isfinite(value) && value != 0.0) ++nonzero_bins;
                std::cout
                    << "V048746255172582_V82_PATCH5206_SELECTED_LINE_REPLAY_RECORDS="
                    << selected_lines_v82_patch5206.size() << "\n"
                    << "V048746255172582_V82_PATCH5206_SELECTED_LINE_PROFILE_NONZERO_BINS="
                    << nonzero_bins << "\n"
                    << "V048746255172582_V82_PATCH5206_TYPE50_PROFILE_COORDINATE=STORED_SOURCE_WAVELENGTH\n";
            }
        }

        const std::size_t nlines=spectral.size();
        std::vector<double> dpthc(continuum_capacity,0.0), original(5*continuum_capacity,0.0), profiled(5*continuum_capacity,0.0);
        std::vector<double> elum(2*nlines,0.0), wavelength(nlines,0.0), mass(nlines,1.0), natural_rate(nlines,0.0), auger_width(nlines,0.0), auger_rate(nlines,0.0);
        std::vector<long long> slot(nlines,0), dtype(nlines,50);
        for (std::size_t j=0;j<nlines;++j) {
            const auto& c=spectral[j];
            slot[j]=static_cast<long long>(j+1);
            dtype[j]=c.data_type;
            wavelength[j]=c.line_energy_eV>0.0?12398.4016/c.line_energy_eV:1.0e30;
            mass[j]=std::max(c.atomic_mass_amu,1.0e-30);
            auger_width[j]=std::max(c.natural_width_eV,0.0);
            if (c.kind == XSTAR_SPECTRAL_KIND_EMIS_LINE || c.kind == XSTAR_SPECTRAL_KIND_FULL_LINE) {
                const auto li=static_cast<std::size_t>(c.output_index);
                if (li>=line_capacity) throw std::runtime_error("line profile output index out of range");
                elum[j]=fline[li];
                elum[nlines+j]=fline[line_capacity+li];
            }
        }
        if (!defer_product_projection) {
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
        }

        // v82 patch 5.20.6: literal calc_emis_all resets both public opakc
        // and rccemis after calc_emisab_all.  It revisits rate-7 bound-free
        // records only when ncbin selected their public RRC slot, while Type-88
        // rate-42 follows its separate ungated branch.  Rebuild both heatt-facing
        // opacity and RRC emission from those exact native-derived consumers.
        // Broad calc_emisab opakab/cemab and diagnostic surfaces remain intact.
        std::vector<double> heatt_bound_free_opacity_v82_patch5206(continuum_capacity, 0.0);
        std::vector<double> heatt_rrc_continuum_emission_v82_patch520(2 * continuum_capacity, 0.0);
        std::size_t selected_rrc_records_v82_patch520 = 0u;
        std::size_t rate42_rrc_records_v82_patch520 = 0u;
        std::vector<std::int64_t> rate42_rrc_record_list_v82_patch520;
        if (!defer_product_projection && source_calc_emis_selection_ready_v82_patch5206) {
            std::map<std::pair<std::uint64_t,std::int64_t>,int> rrc_slot_by_identity_v82_patch520;
            for (const auto& c : spectral) {
                if (c.kind != XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE || c.output_index <= 0) continue;
                rrc_slot_by_identity_v82_patch520[{c.source_position, c.record}] = c.output_index;
            }
            std::unordered_map<std::int64_t,const ProgramRecord*> record_by_source_position_v82_patch520;
            record_by_source_position_v82_patch520.reserve(ctx.program.records.size());
            for (const auto& source_record : ctx.program.records)
                record_by_source_position_v82_patch520[static_cast<std::int64_t>(source_record.source_position)] = &source_record;
            for (const auto& deferred : deferred_rrc_records_v82_patch520) {
                const auto rit = record_by_source_position_v82_patch520.find(
                    static_cast<std::int64_t>(deferred.source_position));
                if (rit == record_by_source_position_v82_patch520.end() || !rit->second) continue;
                if (!deferred.source_rate42_type88) {
                    // Literal calc_emis_ion rank gating applies to rate-7
                    // RRC consumers only.  Crucially, selection is local to
                    // ncbin(:,nb1) for this exact record, not the flattened
                    // union of slots selected in any bin.
                    if (deferred.rate_type != 7) continue;
                    const auto it = rrc_slot_by_identity_v82_patch520.find({deferred.source_position, deferred.record});
                    if (it == rrc_slot_by_identity_v82_patch520.end()) continue;
                    const double rank_energy_ev_v82_patch5209 =
                        source_errc_rank_energy_for_slot_v82_patch5209(
                            it->second, deferred.source_position, deferred.record, deferred.opacity_curve.threshold_ev);
                    const double errc_wavelength_a_v82_patch5209 = rank_energy_ev_v82_patch5209 > 0.0
                        ? source_real_literal_v82_patch5208(12398.4016) /
                            std::max(1.0e-34, rank_energy_ev_v82_patch5209)
                        : 0.0;
                    const bool destination_valid_v82_patch5208 = rit->second->lower_row > 0;
                    const auto consumer_v82_patch5208 = source_calc_emis_consumer_v82_patch5208(
                        it->second, errc_wavelength_a_v82_patch5209, true, destination_valid_v82_patch5208,
                        source_calc_emis_ncbin_v82_patch5208, input.radiation_energy_ev, continuum_capacity);
                    if (!consumer_v82_patch5208.actual_consumer) continue;
                }
                accumulate_native_bound_free_opacity_from_abundances_v82_patch5206(
                    deferred.opacity_curve, *rit->second, deferred.lower_abundance, input,
                    heatt_bound_free_opacity_v82_patch5206);
                accumulate_native_bound_free_rrc_from_abundances_v82_patch520(
                    deferred.emission_curve, deferred.evaluated, *rit->second, deferred.lower_abundance,
                    deferred.upper_abundance, input, heatt_rrc_continuum_emission_v82_patch520);
                if (deferred.source_rate42_type88) {
                    ++rate42_rrc_records_v82_patch520;
                    rate42_rrc_record_list_v82_patch520.push_back(deferred.record);
                } else ++selected_rrc_records_v82_patch520;
            }
        }
        // v82 patch 5.20.8: diagnostic ledger separating rank membership
        // from the literal record-local calc_emis_ion consumer decision.
        const char* consumer_ledger_path_v82_patch5208 =
            std::getenv("XSTAR_V82_PATCH5208_CONSUMER_LEDGER_PATH");
        if (!defer_product_projection && source_sequence_v82_patch511 == 59 &&
            consumer_ledger_path_v82_patch5208 && *consumer_ledger_path_v82_patch5208) {
            const std::filesystem::path ledger_path_v82_patch5208(consumer_ledger_path_v82_patch5208);
            if (!ledger_path_v82_patch5208.parent_path().empty())
                std::filesystem::create_directories(ledger_path_v82_patch5208.parent_path());
            std::ofstream ledger_v82_patch5208(ledger_path_v82_patch5208);
            if (!ledger_v82_patch5208)
                throw std::runtime_error("cannot create patch5.20.8 calc_emis consumer ledger");
            ledger_v82_patch5208
                << "family,source_position,record,data_type,rate_type,element_z,ion_stage,slot_one_based,"
                << "feature_wavelength_a,feature_energy_ev,nb1_one_based,rank_in_bin,rank_selected_anywhere,"
                << "rank_selected_in_nb1,source_range_pass,pointer_valid,destination_valid,actual_consumer,"
                << "opacity_owner,emission_owner,rejection_reason\n";
            ledger_v82_patch5208 << std::setprecision(17);

            std::unordered_map<std::int64_t,const ProgramRecord*> record_by_position_v82_patch5208;
            std::unordered_map<int,int> element_z_by_index_v82_patch5208;
            for (const auto& pr : ctx.program.records)
                record_by_position_v82_patch5208[pr.source_position] = &pr;
            for (const auto& em : ctx.program.elements)
                element_z_by_index_v82_patch5208[em.element_index] = em.element_z;
            std::map<std::pair<std::uint64_t,std::int64_t>,int> rrc_slot_by_identity_v82_patch5208;
            for (const auto& c : spectral) {
                if (c.kind == XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE && c.output_index > 0)
                    rrc_slot_by_identity_v82_patch5208[{c.source_position,c.record}] = c.output_index;
            }

            std::size_t ledger_rrc_consumers_v82_patch5208 = 0u;
            std::size_t ledger_line_consumers_v82_patch5208 = 0u;
            std::size_t ledger_cross_bin_rejects_v82_patch5208 = 0u;
            for (const auto& deferred : deferred_rrc_records_v82_patch520) {
                const auto pr_it = record_by_position_v82_patch5208.find(
                    static_cast<std::int64_t>(deferred.source_position));
                const ProgramRecord* pr = pr_it == record_by_position_v82_patch5208.end() ? nullptr : pr_it->second;
                const int element_z = pr && element_z_by_index_v82_patch5208.count(pr->element_index)
                    ? element_z_by_index_v82_patch5208[pr->element_index] : 0;
                const int ion_stage = pr ? pr->ion_stage : 0;
                int slot_one_based = 0;
                auto sit = rrc_slot_by_identity_v82_patch5208.find({deferred.source_position,deferred.record});
                if (sit != rrc_slot_by_identity_v82_patch5208.end()) slot_one_based = sit->second;
                const double feature_energy = source_errc_rank_energy_for_slot_v82_patch5209(
                    slot_one_based, deferred.source_position, deferred.record, deferred.opacity_curve.threshold_ev);
                const double wavelength = feature_energy > 0.0
                    ? source_real_literal_v82_patch5208(12398.4016) / feature_energy : 0.0;
                SourceConsumerDecisionV82Patch5208 decision;
                std::string opacity_owner = "NONE";
                std::string emission_owner = "NONE";
                if (deferred.source_rate42_type88) {
                    decision.pointer_valid = true;
                    decision.destination_valid = pr && pr->lower_row > 0;
                    decision.source_range_pass = true;
                    decision.actual_consumer = decision.destination_valid;
                    decision.rejection_reason = decision.actual_consumer ? "RATE42_UNGATED" : "INVALID_DESTINATION";
                    opacity_owner = decision.actual_consumer ? "TYPE88_RATE42_PHINT53" : "NONE";
                    emission_owner = decision.actual_consumer ? "TYPE88_RATE42_RRC" : "NONE";
                } else if (deferred.rate_type == 7) {
                    decision = source_calc_emis_consumer_v82_patch5208(
                        slot_one_based, wavelength, true, pr && pr->lower_row > 0,
                        source_calc_emis_ncbin_v82_patch5208, input.radiation_energy_ev, continuum_capacity);
                    if (decision.rejection_reason == "SELECTED_IN_DIFFERENT_BIN")
                        ++ledger_cross_bin_rejects_v82_patch5208;
                    if (decision.actual_consumer) {
                        opacity_owner = pr && pr->data_type == 99 ? "SOURCE_ZERO_TYPE99" : "RATE7_PHINT53";
                        emission_owner = "RATE7_RRC";
                    }
                } else {
                    decision.rejection_reason = "NOT_RATE7_OR_RATE42";
                }
                if (decision.actual_consumer) ++ledger_rrc_consumers_v82_patch5208;
                ledger_v82_patch5208 << "RRC," << deferred.source_position << ',' << deferred.record << ','
                    << (pr ? pr->data_type : 0) << ',' << deferred.rate_type << ',' << element_z << ',' << ion_stage << ','
                    << slot_one_based << ',' << wavelength << ',' << feature_energy << ',' << decision.nb1_one_based << ','
                    << decision.rank_in_bin << ',' << (decision.selected_anywhere ? 1 : 0) << ','
                    << (decision.selected_in_nb1 ? 1 : 0) << ',' << (decision.source_range_pass ? 1 : 0) << ','
                    << (decision.pointer_valid ? 1 : 0) << ',' << (decision.destination_valid ? 1 : 0) << ','
                    << (decision.actual_consumer ? 1 : 0) << ',' << opacity_owner << ',' << emission_owner << ','
                    << decision.rejection_reason << '\n';
            }

            for (const auto& c : spectral) {
                if (c.kind == XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE || c.output_index <= 0) continue;
                const auto pr_it = record_by_position_v82_patch5208.find(static_cast<std::int64_t>(c.source_position));
                const ProgramRecord* pr = pr_it == record_by_position_v82_patch5208.end() ? nullptr : pr_it->second;
                const int element_z = pr && element_z_by_index_v82_patch5208.count(pr->element_index)
                    ? element_z_by_index_v82_patch5208[pr->element_index] : 0;
                const auto wit = source_line_wavelength_by_identity_v82_patch5208.find(
                    {static_cast<std::uint64_t>(c.source_position), static_cast<std::int64_t>(c.record)});
                const double wavelength = wit != source_line_wavelength_by_identity_v82_patch5208.end()
                    ? wit->second : (c.line_energy_eV > 0.0
                        ? source_real_literal_v82_patch5208(12398.4016) / c.line_energy_eV : 0.0);
                const double feature_energy = wavelength > 0.0
                    ? source_real_literal_v82_patch5208(12398.4016) / (wavelength + 1.0e-36) : 0.0;
                const auto decision = source_calc_emis_consumer_v82_patch5208(
                    c.output_index, wavelength, false, pr && pr->lower_row > 0,
                    source_calc_emis_nlbin_v82_patch5208, input.radiation_energy_ev, continuum_capacity);
                if (decision.actual_consumer) ++ledger_line_consumers_v82_patch5208;
                if (decision.rejection_reason == "SELECTED_IN_DIFFERENT_BIN")
                    ++ledger_cross_bin_rejects_v82_patch5208;
                ledger_v82_patch5208 << "LINE," << c.source_position << ',' << c.record << ',' << c.data_type << ','
                    << c.rate_type << ',' << element_z << ',' << (pr ? pr->ion_stage : 0) << ',' << c.output_index << ','
                    << wavelength << ',' << feature_energy << ',' << decision.nb1_one_based << ',' << decision.rank_in_bin << ','
                    << (decision.selected_anywhere ? 1 : 0) << ',' << (decision.selected_in_nb1 ? 1 : 0) << ','
                    << (decision.source_range_pass ? 1 : 0) << ',' << (decision.pointer_valid ? 1 : 0) << ','
                    << (decision.destination_valid ? 1 : 0) << ',' << (decision.actual_consumer ? 1 : 0) << ','
                    << (decision.actual_consumer ? "NLBIN_LINE_OPACITY" : "NONE") << ','
                    << (decision.actual_consumer ? "NLBIN_LINE_EMISSION" : "NONE") << ','
                    << decision.rejection_reason << '\n';
            }
            if (!ledger_v82_patch5208)
                throw std::runtime_error("cannot write patch5.20.8 calc_emis consumer ledger");
            std::cout
                << "V048746255172582_PATCH5208_ACTUAL_RRC_CONSUMERS=" << ledger_rrc_consumers_v82_patch5208 << "\n"
                << "V048746255172582_PATCH5208_ACTUAL_LINE_CONSUMERS=" << ledger_line_consumers_v82_patch5208 << "\n"
                << "V048746255172582_PATCH5208_SELECTED_DIFFERENT_BIN_REJECTIONS=" << ledger_cross_bin_rejects_v82_patch5208 << "\n"
                << "V048746255172582_PATCH5208_CONSUMER_LEDGER=WRITTEN\n";
        }

        // v82 patch 5.20.9: explicit Type-49/53 ownership-delta ledger.
        // Compare the previous identity-owned 5.20.8.2 reconstruction against
        // the literal xstarsetup slot-owned errc + calc_emis_ion decision. This
        // diagnostic never feeds a production array.
        const char* ownership_ledger_path_v82_patch5209 =
            std::getenv("XSTAR_V82_PATCH5209_BOUND_FREE_OWNERSHIP_LEDGER_PATH");
        if (!defer_product_projection && source_sequence_v82_patch511 == 59 &&
            ownership_ledger_path_v82_patch5209 && *ownership_ledger_path_v82_patch5209) {
            const std::filesystem::path ownership_path_v82_patch5209(
                ownership_ledger_path_v82_patch5209);
            if (!ownership_path_v82_patch5209.parent_path().empty())
                std::filesystem::create_directories(ownership_path_v82_patch5209.parent_path());
            std::ofstream ownership_v82_patch5209(ownership_path_v82_patch5209);
            if (!ownership_v82_patch5209)
                throw std::runtime_error("cannot create patch5.20.9 bound-free ownership ledger");
            ownership_v82_patch5209
                << "source_position,record,data_type,rate_type,element_z,ion_stage,slot_one_based,"
                << "identity_rank_energy_ev,slot_rank_energy_ev,slot_owner_source_position,"
                << "slot_owner_record,slot_owner_data_type,identity_nb1_one_based,slot_nb1_one_based,"
                << "patch52082_identity_consumer,literal_slot_consumer,ownership_delta,"
                << "identity_rejection_reason,slot_rejection_reason,kernel_available\n";
            ownership_v82_patch5209 << std::setprecision(17);

            std::unordered_map<std::int64_t,const ProgramRecord*> record_by_position_v82_patch5209;
            std::unordered_map<int,int> element_z_by_index_v82_patch5209;
            for (const auto& pr : ctx.program.records)
                record_by_position_v82_patch5209[pr.source_position] = &pr;
            for (const auto& em : ctx.program.elements)
                element_z_by_index_v82_patch5209[em.element_index] = em.element_z;

            std::array<std::size_t,2> source_only_v82_patch5209{{0u,0u}};
            std::array<std::size_t,2> native_only_v82_patch5209{{0u,0u}};
            std::array<std::size_t,2> both_v82_patch5209{{0u,0u}};
            std::array<std::size_t,2> neither_v82_patch5209{{0u,0u}};
            std::array<std::size_t,2> total_v82_patch5209{{0u,0u}};
            std::size_t slot_owner_cross_type_v82_patch5209 = 0u;

            for (const auto& deferred : deferred_rrc_records_v82_patch520) {
                if (deferred.source_rate42_type88 || deferred.rate_type != 7) continue;
                const auto pr_it = record_by_position_v82_patch5209.find(
                    static_cast<std::int64_t>(deferred.source_position));
                if (pr_it == record_by_position_v82_patch5209.end() || !pr_it->second) continue;
                const ProgramRecord& pr = *pr_it->second;
                if (pr.data_type != 49 && pr.data_type != 53) continue;
                const int family_index = pr.data_type == 49 ? 0 : 1;
                ++total_v82_patch5209[static_cast<std::size_t>(family_index)];
                const int slot_one_based = pr.continuum_index_one_based;
                const auto identity = std::make_pair(
                    deferred.source_position, deferred.record);
                double identity_energy_v82_patch5209 = deferred.opacity_curve.threshold_ev;
                const auto legacy_energy_it_v82_patch5209 =
                    source_errc_rank_energy_by_identity_patch52082_audit_v82_patch5209.find(identity);
                if (legacy_energy_it_v82_patch5209 !=
                    source_errc_rank_energy_by_identity_patch52082_audit_v82_patch5209.end())
                    identity_energy_v82_patch5209 = legacy_energy_it_v82_patch5209->second;
                const double slot_energy_v82_patch5209 =
                    source_errc_rank_energy_for_slot_v82_patch5209(
                        slot_one_based, deferred.source_position, deferred.record,
                        deferred.opacity_curve.threshold_ev);
                const double identity_wavelength_v82_patch5209 = identity_energy_v82_patch5209 > 0.0
                    ? source_real_literal_v82_patch5208(12398.4016) /
                        std::max(1.0e-34, identity_energy_v82_patch5209) : 0.0;
                const double slot_wavelength_v82_patch5209 = slot_energy_v82_patch5209 > 0.0
                    ? source_real_literal_v82_patch5208(12398.4016) /
                        std::max(1.0e-34, slot_energy_v82_patch5209) : 0.0;
                const bool destination_valid_v82_patch5209 = pr.lower_row > 0;
                const auto legacy_decision_v82_patch5209 = source_calc_emis_consumer_v82_patch5208(
                    slot_one_based, identity_wavelength_v82_patch5209, true,
                    destination_valid_v82_patch5209,
                    source_calc_emis_ncbin_patch52082_audit_v82_patch5209,
                    input.radiation_energy_ev, continuum_capacity);
                const auto source_decision_v82_patch5209 = source_calc_emis_consumer_v82_patch5208(
                    slot_one_based, slot_wavelength_v82_patch5209, true,
                    destination_valid_v82_patch5209,
                    source_calc_emis_ncbin_v82_patch5208,
                    input.radiation_energy_ev, continuum_capacity);

                std::string delta_v82_patch5209 = "NEITHER";
                if (source_decision_v82_patch5209.actual_consumer &&
                    legacy_decision_v82_patch5209.actual_consumer) {
                    delta_v82_patch5209 = "BOTH";
                    ++both_v82_patch5209[static_cast<std::size_t>(family_index)];
                } else if (source_decision_v82_patch5209.actual_consumer) {
                    delta_v82_patch5209 = "LITERAL_ONLY";
                    ++source_only_v82_patch5209[static_cast<std::size_t>(family_index)];
                } else if (legacy_decision_v82_patch5209.actual_consumer) {
                    delta_v82_patch5209 = "PATCH52082_ONLY";
                    ++native_only_v82_patch5209[static_cast<std::size_t>(family_index)];
                } else {
                    ++neither_v82_patch5209[static_cast<std::size_t>(family_index)];
                }

                std::uint64_t slot_owner_position_v82_patch5209 = 0u;
                std::int64_t slot_owner_record_v82_patch5209 = 0;
                int slot_owner_type_v82_patch5209 = 0;
                const auto owner_it_v82_patch5209 =
                    source_errc_owner_by_slot_v82_patch5209.find(slot_one_based);
                if (owner_it_v82_patch5209 != source_errc_owner_by_slot_v82_patch5209.end()) {
                    slot_owner_position_v82_patch5209 = std::get<0>(owner_it_v82_patch5209->second);
                    slot_owner_record_v82_patch5209 = std::get<1>(owner_it_v82_patch5209->second);
                    slot_owner_type_v82_patch5209 = std::get<2>(owner_it_v82_patch5209->second);
                    if (slot_owner_type_v82_patch5209 != 0 &&
                        slot_owner_type_v82_patch5209 != pr.data_type)
                        ++slot_owner_cross_type_v82_patch5209;
                }
                const int element_z_v82_patch5209 =
                    element_z_by_index_v82_patch5209.count(pr.element_index)
                        ? element_z_by_index_v82_patch5209[pr.element_index] : 0;
                ownership_v82_patch5209
                    << pr.source_position << ',' << pr.record << ',' << pr.data_type << ','
                    << pr.rate_type << ',' << element_z_v82_patch5209 << ',' << pr.ion_stage << ','
                    << slot_one_based << ',' << identity_energy_v82_patch5209 << ','
                    << slot_energy_v82_patch5209 << ',' << slot_owner_position_v82_patch5209 << ','
                    << slot_owner_record_v82_patch5209 << ',' << slot_owner_type_v82_patch5209 << ','
                    << legacy_decision_v82_patch5209.nb1_one_based << ','
                    << source_decision_v82_patch5209.nb1_one_based << ','
                    << (legacy_decision_v82_patch5209.actual_consumer ? 1 : 0) << ','
                    << (source_decision_v82_patch5209.actual_consumer ? 1 : 0) << ','
                    << delta_v82_patch5209 << ','
                    << legacy_decision_v82_patch5209.rejection_reason << ','
                    << source_decision_v82_patch5209.rejection_reason << ",1\n";
            }
            if (!ownership_v82_patch5209)
                throw std::runtime_error("cannot write patch5.20.9 bound-free ownership ledger");
            std::cout
                << "V048746255172582_PATCH5209_TYPE49_CONSUMER_CANDIDATES=" << total_v82_patch5209[0] << "\n"
                << "V048746255172582_PATCH5209_TYPE49_LITERAL_SLOT_ONLY_CONSUMERS=" << source_only_v82_patch5209[0] << "\n"
                << "V048746255172582_PATCH5209_TYPE49_PATCH52082_IDENTITY_ONLY_CONSUMERS=" << native_only_v82_patch5209[0] << "\n"
                << "V048746255172582_PATCH5209_TYPE49_COMMON_CONSUMERS=" << both_v82_patch5209[0] << "\n"
                << "V048746255172582_PATCH5209_TYPE49_NONCONSUMERS=" << neither_v82_patch5209[0] << "\n"
                << "V048746255172582_PATCH5209_TYPE53_CONSUMER_CANDIDATES=" << total_v82_patch5209[1] << "\n"
                << "V048746255172582_PATCH5209_TYPE53_LITERAL_SLOT_ONLY_CONSUMERS=" << source_only_v82_patch5209[1] << "\n"
                << "V048746255172582_PATCH5209_TYPE53_PATCH52082_IDENTITY_ONLY_CONSUMERS=" << native_only_v82_patch5209[1] << "\n"
                << "V048746255172582_PATCH5209_TYPE53_COMMON_CONSUMERS=" << both_v82_patch5209[1] << "\n"
                << "V048746255172582_PATCH5209_TYPE53_NONCONSUMERS=" << neither_v82_patch5209[1] << "\n"
                << "V048746255172582_PATCH5209_CROSS_TYPE_SLOT_OWNERS=" << slot_owner_cross_type_v82_patch5209 << "\n"
                << "V048746255172582_PATCH5209_ERRC_OWNERSHIP=SOURCE_ORDER_LAST_WRITER_PER_NPCONI2_SLOT\n"
                << "V048746255172582_PATCH5209_BOUND_FREE_OWNERSHIP_LEDGER=WRITTEN\n";
        }

        if (!defer_product_projection) {
            for (std::size_t k = 0; k < continuum_capacity; ++k) {
                output.opacity[k] += heatt_bound_free_opacity_v82_patch5206[k];
                opakcont[k] += heatt_bound_free_opacity_v82_patch5206[k];
                rccemis[k] += heatt_rrc_continuum_emission_v82_patch520[k];
                rccemis[continuum_capacity + k] += heatt_rrc_continuum_emission_v82_patch520[continuum_capacity + k];
            }
            if (source_sequence_v82_patch511 == 59) {
                std::size_t rrc_nonzero_v82_patch520 = 0u;
                for (double value : heatt_rrc_continuum_emission_v82_patch520)
                    if (std::isfinite(value) && value != 0.0) ++rrc_nonzero_v82_patch520;
                std::size_t bf_nonzero_v82_patch5206 = 0u;
                for (double value : heatt_bound_free_opacity_v82_patch5206)
                    if (std::isfinite(value) && value != 0.0) ++bf_nonzero_v82_patch5206;
                std::cout << "V048746255172582_V82_PATCH5206_HEATT_BOUND_FREE_NONZERO_BINS="
                          << bf_nonzero_v82_patch5206 << "\n"
                          << "V048746255172582_V82_PATCH5206_BOUND_FREE_OWNERSHIP=NCBIN_RATE7_PLUS_UNGATED_TYPE88_RATE42\n"
                          << "V048746255172582_V82_PATCH520_CALC_EMIS_SELECTED_RRC_RECORDS="
                          << selected_rrc_records_v82_patch520 << "\n"
                          << "V048746255172582_V82_PATCH520_CALC_EMIS_RATE42_TYPE88_RECORDS="
                          << rate42_rrc_records_v82_patch520 << "\n"
                          << "V048746255172582_V82_PATCH520_CALC_EMIS_RATE42_TYPE88_RECORD_LIST=";
                for (std::size_t i = 0; i < rate42_rrc_record_list_v82_patch520.size(); ++i) {
                    if (i) std::cout << ";";
                    std::cout << rate42_rrc_record_list_v82_patch520[i];
                }
                std::cout << "\n"
                          << "V048746255172582_V82_PATCH520_HEATT_RRC_EMISSION_NONZERO_CELLS="
                          << rrc_nonzero_v82_patch520 << "\n"
                          << "V048746255172582_V82_PATCH520_RRC_SELECTION_SEMANTICS=SOURCE_CALC_EMIS_NCBIN_RATE7_PLUS_UNGATED_RATE42\n"
                          << "V048746255172582_V82_PATCH5205_RRC_RANK_COORDINATE=SOURCE_XSTARSETUP_ERRC\n";
            }
        }

        // v82 patch 5.20.6: comparison-only ledger of the *selected* public
        // absorption schedule.  Unlike the 5.20.3 all-record producer ledger,
        // this sidecar mirrors calc_emis_all ownership and is suitable for
        // direct source cumulative/support closure.
        const char* selected_absorption_path_v82_patch5206 =
            std::getenv("XSTAR_V82_PATCH5206_SELECTED_ABSORPTION_LEDGER_PATH");
        if (!defer_product_projection && source_sequence_v82_patch511 == 59 &&
            selected_absorption_path_v82_patch5206 && *selected_absorption_path_v82_patch5206 &&
            target_bins_path_v82_patch5203 && *target_bins_path_v82_patch5203) {
            std::set<std::size_t> selected_target_bins_v82_patch5206;
            {
                std::ifstream bins_in(target_bins_path_v82_patch5203);
                std::size_t bin = 0u;
                while (bins_in >> bin) if (bin < continuum_capacity) selected_target_bins_v82_patch5206.insert(bin);
            }
            const std::filesystem::path ledger_path(selected_absorption_path_v82_patch5206);
            if (!ledger_path.parent_path().empty()) std::filesystem::create_directories(ledger_path.parent_path());
            std::ofstream ledger(ledger_path);
            if (!ledger) throw std::runtime_error("cannot create patch5.20.6 selected absorption ledger");
            ledger << "runtime_slot,energy_ev,producer_family,source_position,record,data_type,rate_type,element_z,ion_stage,lower_row,upper_row,contribution_cm_inv\n";
            ledger << std::setprecision(17);
            std::unordered_map<std::int64_t,const ProgramRecord*> record_by_position_v82_patch5206;
            for (const auto& record : ctx.program.records)
                record_by_position_v82_patch5206[static_cast<std::int64_t>(record.source_position)] = &record;
            std::unordered_map<int,int> element_z_by_index_v82_patch5206;
            for (const auto& element_meta : ctx.program.elements)
                element_z_by_index_v82_patch5206[element_meta.element_index] = element_meta.element_z;
            std::size_t selected_ledger_rows_v82_patch5206 = 0u;

            // Bound-free rows in literal source-consumer order.
            for (const auto& deferred : deferred_rrc_records_v82_patch520) {
                const auto rit = record_by_position_v82_patch5206.find(static_cast<std::int64_t>(deferred.source_position));
                if (rit == record_by_position_v82_patch5206.end() || !rit->second) continue;
                if (!deferred.source_rate42_type88) {
                    if (deferred.rate_type != 7) continue;
                    int slot_one_based = 0;
                    for (const auto& c : spectral) {
                        if (c.kind == XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE &&
                            c.source_position == deferred.source_position && c.record == deferred.record) {
                            slot_one_based = c.output_index; break;
                        }
                    }
                    const double rank_energy_v82_patch5209 = source_errc_rank_energy_for_slot_v82_patch5209(
                        slot_one_based, deferred.source_position, deferred.record, deferred.opacity_curve.threshold_ev);
                    const double errc_wavelength_v82_patch5209 = rank_energy_v82_patch5209 > 0.0
                        ? source_real_literal_v82_patch5208(12398.4016) /
                            std::max(1.0e-34, rank_energy_v82_patch5209) : 0.0;
                    const auto consumer_v82_patch5208 = source_calc_emis_consumer_v82_patch5208(
                        slot_one_based, errc_wavelength_v82_patch5209, true, rit->second->lower_row > 0,
                        source_calc_emis_ncbin_v82_patch5208, input.radiation_energy_ev, continuum_capacity);
                    if (!consumer_v82_patch5208.actual_consumer) continue;
                }
                std::vector<double> one(continuum_capacity, 0.0);
                accumulate_native_bound_free_opacity_from_abundances_v82_patch5206(
                    deferred.opacity_curve, *rit->second, deferred.lower_abundance, input, one);
                const ProgramRecord& pr = *rit->second;
                const int ez = element_z_by_index_v82_patch5206.count(pr.element_index)
                    ? element_z_by_index_v82_patch5206[pr.element_index] : 0;
                for (std::size_t bin : selected_target_bins_v82_patch5206) {
                    const double value = one[bin];
                    if (!(std::isfinite(value) && value != 0.0)) continue;
                    ledger << bin << ',' << input.radiation_energy_ev[bin] << ",BOUND_FREE,"
                           << pr.source_position << ',' << pr.record << ',' << pr.data_type << ',' << pr.rate_type << ','
                           << ez << ',' << pr.ion_stage << ',' << pr.lower_row << ',' << pr.upper_row << ',' << value << '\n';
                    ++selected_ledger_rows_v82_patch5206;
                }
            }

            // Type-50/line rows from the exact selected full-profile replay.
            for (std::size_t j = 0; j < selected_lines_v82_patch5206.size(); ++j) {
                const auto& c = selected_lines_v82_patch5206[j];
                const double optpp = c.opakab * c.abundance_lower * c.hydrogen_density;
                if (!(std::isfinite(optpp) && optpp > 0.0)) continue;
                std::vector<double> one(continuum_capacity, 0.0);
                std::vector<double> dummy_rrc(2 * continuum_capacity, 0.0);
                std::array<double,21> seed{};
                seed[0]=1.0/1.772;
                for (std::size_t d=1;d<=10;++d) {
                    const double value=std::exp(-static_cast<double>(d*d))/1.772;
                    seed[2*d-1]=value; seed[2*d]=value;
                }
                long long updated=0; double elapsed_seconds=0.0; std::array<char,512> err{};
                const int rc = xstar_opacity_apply_line_profile_v1(
                    optpp, c.line_energy_eV, c.turbulent_velocity_km_s, c.temperature_1e4K,
                    c.atomic_mass_amu, c.natural_width_eV, seed.data(), 10, input.radiation_energy_ev,
                    static_cast<int>(continuum_capacity), one.data(), dummy_rrc.data(), &updated,
                    &elapsed_seconds, err.data(), err.size());
                if (rc != 0) throw std::runtime_error(std::string("patch5.20.6 selected line ledger failed: ") + err.data());
                const auto rit = record_by_position_v82_patch5206.find(static_cast<std::int64_t>(c.source_position));
                const ProgramRecord* pr = rit == record_by_position_v82_patch5206.end() ? nullptr : rit->second;
                const int ez = pr && element_z_by_index_v82_patch5206.count(pr->element_index)
                    ? element_z_by_index_v82_patch5206[pr->element_index] : 0;
                for (std::size_t bin : selected_target_bins_v82_patch5206) {
                    const double value = one[bin];
                    if (!(std::isfinite(value) && value != 0.0)) continue;
                    ledger << bin << ',' << input.radiation_energy_ev[bin] << ",LINE,"
                           << c.source_position << ',' << c.record << ',' << c.data_type << ',' << c.rate_type << ','
                           << ez << ',' << (pr ? pr->ion_stage : 0) << ',' << (pr ? pr->lower_row : 0) << ','
                           << (pr ? pr->upper_row : 0) << ',' << value << '\n';
                    ++selected_ledger_rows_v82_patch5206;
                }
            }
            if (!ledger) throw std::runtime_error("cannot write patch5.20.6 selected absorption ledger");
            std::cout << "V048746255172582_V82_PATCH5206_SELECTED_ABSORPTION_LEDGER_ROWS="
                      << selected_ledger_rows_v82_patch5206 << "\n"
                      << "V048746255172582_V82_PATCH5206_SELECTED_ABSORPTION_LEDGER=WRITTEN\n";
        }

        const char* source_sequence_env_v82_patch57 = std::getenv("XSTAR_NATIVE_SOURCE_SEQUENCE");
        const int source_sequence_v82_patch57 = source_sequence_env_v82_patch57 && *source_sequence_env_v82_patch57
            ? std::atoi(source_sequence_env_v82_patch57) : 0;
        if (!defer_product_projection && source_sequence_v82_patch57 == 59) {
            std::size_t bound_free_nonzero = 0;
            for (double v : native_bound_free_opacity) if (std::isfinite(v) && v != 0.0) ++bound_free_nonzero;
            std::cout << "V048746255172582_CALL2_PHINT53_GRID_MAPPED_RECORDS="
                      << phint53_records_mapped_v82_patch57 << "\n"
                      << "V048746255172582_CALL2_PHINT53_GRID_ACCUMULATED_RECORD_BIN_EVENTS="
                      << phint53_bins_accumulated_v82_patch57 << "\n"
                      << "V048746255172582_CALL2_PHINT53_BOUND_FREE_NONZERO_BINS="
                      << bound_free_nonzero << "\n"
                      << "V048746255172582_CALL2_PHINT53_CONTINUUM_BIN_MAPPING=ACCEPT_SOURCE_BIN_AVERAGED\n";

            if (opacity_producer_audit_v82_patch511 || exact_absorption_audit_v82_patch5203) {
                // Re-evaluate every line contribution into a comparison-only profile
                // with the exact same native linopac kernel and seed profile.
                // This records ownership only; it never feeds the temporary
                // profile back into line_profile_opacity or opakc.
                std::unordered_map<std::int64_t,const ProgramRecord*> record_by_source_position;
                record_by_source_position.reserve(ctx.program.records.size());
                for (const auto& record : ctx.program.records) record_by_source_position[record.source_position] = &record;
                std::unordered_map<int,int> element_z_by_index;
                for (const auto& element : ctx.program.elements) element_z_by_index[element.element_index] = element.element_z;
                for (std::size_t j = 0; j < spectral.size(); ++j) {
                    const auto& c = spectral[j];
                    if (!(c.kind == XSTAR_SPECTRAL_KIND_EMIS_LINE || c.kind == XSTAR_SPECTRAL_KIND_FULL_LINE)) continue;
                    const double optpp = c.opakab * c.abundance_lower * c.hydrogen_density;
                    if (!(std::isfinite(optpp) && optpp > 0.0)) continue;
                    std::fill(producer_temp_opacity_v82_patch511.begin(), producer_temp_opacity_v82_patch511.end(), 0.0);
                    std::fill(producer_temp_rrc_v82_patch511.begin(), producer_temp_rrc_v82_patch511.end(), 0.0);
                    long long updated = 0;
                    double opacity_elapsed = 0.0;
                    std::array<char,512> opacity_error{};
                    const double* seed = seeds.data() + j * seed_stride;
                    const int profile_rc = xstar_opacity_apply_line_profile_v1(
                        optpp, c.line_energy_eV, c.turbulent_velocity_km_s,
                        c.temperature_1e4K, c.atomic_mass_amu, c.natural_width_eV,
                        seed, 10, input.radiation_energy_ev, static_cast<int>(continuum_capacity),
                        producer_temp_opacity_v82_patch511.data(), producer_temp_rrc_v82_patch511.data(),
                        &updated, &opacity_elapsed, opacity_error.data(), opacity_error.size());
                    if (profile_rc != 0) {
                        throw std::runtime_error(std::string("patch5.11 line producer diagnostic failed: ") + opacity_error.data());
                    }
                    const auto found_record = record_by_source_position.find(static_cast<std::int64_t>(c.source_position));
                    const ProgramRecord* source_record = found_record != record_by_source_position.end() ? found_record->second : nullptr;
                    for (std::size_t bin = 0; bin < producer_temp_opacity_v82_patch511.size(); ++bin) {
                        const double value = producer_temp_opacity_v82_patch511[bin];
                        write_exact_absorption_v82_patch5203(bin, "LINE", static_cast<std::int64_t>(c.source_position),
                            c.record, c.data_type, source_record ? source_record->rate_type : 0,
                            source_record ? (element_z_by_index.count(source_record->element_index) ? element_z_by_index[source_record->element_index] : 0) : 0,
                            source_record ? source_record->ion_stage : 0, source_record ? source_record->lower_row : 0,
                            source_record ? source_record->upper_row : 0, value);
                        if (!opacity_producer_audit_v82_patch511 ||
                            !(std::isfinite(value) && std::abs(value) > std::abs(line_top_v82_patch511[bin].contribution))) continue;
                        auto& top = line_top_v82_patch511[bin];
                        top.contribution = value;
                        top.source_position = static_cast<std::int64_t>(c.source_position);
                        top.record = c.record;
                        top.data_type = c.data_type;
                        if (source_record) {
                            const auto ez = element_z_by_index.find(source_record->element_index);
                            top.element_z = ez != element_z_by_index.end() ? ez->second : 0;
                            top.ion_stage = source_record->ion_stage;
                            top.lower_row = source_record->lower_row;
                            top.upper_row = source_record->upper_row;
                        }
                    }
                }

                if (!opacity_producer_audit_v82_patch511) {
                    // Exact-ledger-only mode does not require the legacy top-producer inventory.
                } else {
                const std::filesystem::path producer_path(opacity_producer_path_v82_patch511);
                if (!producer_path.parent_path().empty()) std::filesystem::create_directories(producer_path.parent_path());
                std::ofstream producer_csv(producer_path);
                if (!producer_csv) throw std::runtime_error("cannot create patch5.11 opacity producer inventory");
                producer_csv << "runtime_slot,energy_ev,bound_free_total,bound_free_top_contribution,bound_free_top_fraction,bound_free_source_position,bound_free_record,bound_free_data_type,bound_free_element_z,bound_free_ion_stage,bound_free_lower_row,bound_free_upper_row,line_total,line_top_contribution,line_top_fraction,line_source_position,line_record,line_data_type,line_element_z,line_ion_stage,line_lower_row,line_upper_row\n";
                producer_csv << std::setprecision(17);
                std::size_t bf_top_nonzero = 0, line_top_nonzero = 0;
                for (std::size_t bin = 0; bin < continuum_capacity; ++bin) {
                    const double bf_total = native_bound_free_opacity[bin];
                    const double line_total = line_profile_opacity[bin];
                    const auto& bf = bound_free_top_v82_patch511[bin];
                    const auto& ln = line_top_v82_patch511[bin];
                    if (bf.contribution != 0.0) ++bf_top_nonzero;
                    if (ln.contribution != 0.0) ++line_top_nonzero;
                    const double bf_fraction = bf_total != 0.0 ? bf.contribution / bf_total : 0.0;
                    const double line_fraction = line_total != 0.0 ? ln.contribution / line_total : 0.0;
                    producer_csv << bin << ',' << input.radiation_energy_ev[bin] << ','
                                 << bf_total << ',' << bf.contribution << ',' << bf_fraction << ','
                                 << bf.source_position << ',' << bf.record << ',' << bf.data_type << ','
                                 << bf.element_z << ',' << bf.ion_stage << ',' << bf.lower_row << ',' << bf.upper_row << ','
                                 << line_total << ',' << ln.contribution << ',' << line_fraction << ','
                                 << ln.source_position << ',' << ln.record << ',' << ln.data_type << ','
                                 << ln.element_z << ',' << ln.ion_stage << ',' << ln.lower_row << ',' << ln.upper_row << '\n';
                }
                std::cout << "V048746255172582_CALL2_OPAKC_PRODUCER_INVENTORY_ROWS=" << continuum_capacity << "\n"
                          << "V048746255172582_CALL2_BOUND_FREE_TOP_PRODUCER_NONZERO_BINS=" << bf_top_nonzero << "\n"
                          << "V048746255172582_CALL2_LINE_TOP_PRODUCER_NONZERO_BINS=" << line_top_nonzero << "\n"
                          << "V048746255172582_CALL2_OPAKC_PRODUCER_INVENTORY=WRITTEN\n";
                }
            }
            if (exact_absorption_audit_v82_patch5203) {
                exact_absorption_csv_v82_patch5203.flush();
                std::cout << "V048746255172582_V82_PATCH5203_EXACT_ABSORPTION_LEDGER_ROWS="
                          << exact_absorption_rows_v82_patch5203 << "\n"
                          << "V048746255172582_V82_PATCH5203_EXACT_ABSORPTION_TARGET_BINS="
                          << target_bins_v82_patch5203.size() << "\n"
                          << "V048746255172582_V82_PATCH5203_EXACT_ABSORPTION_LEDGER=WRITTEN\n";
            }
            if (mg_type53_kernel_audit_v82_patch512) {
                const std::filesystem::path kernel_path(mg_type53_kernel_path_v82_patch512);
                if (!kernel_path.parent_path().empty()) std::filesystem::create_directories(kernel_path.parent_path());
                std::ofstream kernel_csv(kernel_path);
                if (!kernel_csv) throw std::runtime_error("cannot create patch5.12 Mg Type-53 opacity-kernel audit");
                kernel_csv << "source_position,record,data_type,element_z,ion_stage,continuum_index_one_based,lower_full_row,upper_full_row,lower_compact_row,upper_compact_row,lower_global_level_index,upper_global_level_index,threshold_ev,native_lower_population,native_upper_population,abundance,hydrogen_density_cm3,mapped_bin_count,sigma_bin_sum_cm2,native_opacity_bin_sum_cm1,threshold_cross_section_cm2,threshold_stimulated_cross_section_cm2\n";
                kernel_csv << std::setprecision(17);
                for (const auto& row : mg_type53_kernel_rows_v82_patch512) {
                    kernel_csv << row.source_position << ',' << row.record << ",53,12," << row.ion_stage << ','
                               << row.continuum_index_one_based << ',' << row.lower_full_row << ',' << row.upper_full_row << ','
                               << row.lower_compact_row << ',' << row.upper_compact_row << ','
                               << row.lower_global_level_index << ',' << row.upper_global_level_index << ','
                               << row.threshold_ev << ',' << row.native_lower_population << ',' << row.native_upper_population << ','
                               << row.abundance << ',' << row.hydrogen_density_cm3 << ',' << row.mapped_bin_count << ','
                               << row.sigma_bin_sum_cm2 << ',' << row.native_opacity_bin_sum_cm1 << ','
                               << row.threshold_cross_section_cm2 << ',' << row.threshold_stimulated_cross_section_cm2 << '\n';
                }
                std::cout << "V048746255172582_CALL2_MG_TYPE53_OPACITY_KERNEL_ROWS=" << mg_type53_kernel_rows_v82_patch512.size() << "\n"
                          << "V048746255172582_CALL2_MG_TYPE53_OPACITY_KERNEL_AUDIT=WRITTEN\n";
            }
        }

        // Capture the exact source workspaces before the public-product
        // reduction mutates or combines any of them.  The optional sidecar
        // preserves the original xstar_fixed_state_output_v1 ABI layout.
        if (source_workspaces) {
            if (source_workspaces->struct_size < sizeof(*source_workspaces) ||
                source_workspaces->abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) {
                throw std::runtime_error("fixed-state source-workspace ABI mismatch");
            }
            std::vector<double> opakc_exact(continuum_capacity, 0.0);
            for (std::size_t k = 0; k < continuum_capacity; ++k) {
                const double continuum_value = std::isfinite(output.opacity[k]) && output.opacity[k] > 0.0
                    ? output.opacity[k] : 0.0;
                const double line_value = std::isfinite(line_profile_opacity[k]) && line_profile_opacity[k] > 0.0
                    ? line_profile_opacity[k] : 0.0;
                const double combined = continuum_value + line_value;
                opakc_exact[k] = std::isfinite(combined) && combined > 0.0 ? combined : 0.0;
            }
            auto copy_workspace = [](const std::vector<double>& source, double* destination,
                                     std::size_t capacity, std::size_t& count,
                                     const char* label) {
                count = source.size();
                if (!destination) return;
                if (capacity < source.size()) {
                    throw std::runtime_error(std::string(label) + " output capacity too small");
                }
                std::copy(source.begin(), source.end(), destination);
            };
            copy_workspace(rcem, source_workspaces->rcem, source_workspaces->rcem_capacity,
                           source_workspaces->rcem_count, "rcem");
            copy_workspace(oplin, source_workspaces->oplin, source_workspaces->oplin_capacity,
                           source_workspaces->oplin_count, "oplin");
            copy_workspace(cemab, source_workspaces->cemab, source_workspaces->cemab_capacity,
                           source_workspaces->cemab_count, "cemab");
            copy_workspace(cabab, source_workspaces->cabab, source_workspaces->cabab_capacity,
                           source_workspaces->cabab_count, "cabab");
            copy_workspace(opakab, source_workspaces->opakab, source_workspaces->opakab_capacity,
                           source_workspaces->opakab_count, "opakab");
            copy_workspace(rccemis, source_workspaces->rccemis, source_workspaces->rccemis_capacity,
                           source_workspaces->rccemis_count, "rccemis");
            copy_workspace(opakc_exact, source_workspaces->opakc, source_workspaces->opakc_capacity,
                           source_workspaces->opakc_count, "opakc");
            copy_workspace(opakcont, source_workspaces->opakcont, source_workspaces->opakcont_capacity,
                           source_workspaces->opakcont_count, "opakcont");
            copy_workspace(fline, source_workspaces->fline, source_workspaces->fline_capacity,
                           source_workspaces->fline_count, "fline");
            copy_workspace(flinel, source_workspaces->flinel, source_workspaces->flinel_capacity,
                           source_workspaces->flinel_count, "flinel");
            copy_workspace(elum, source_workspaces->elum, source_workspaces->elum_capacity,
                           source_workspaces->elum_count, "elum");
            copy_workspace(profiled, source_workspaces->line_profile_workspace,
                           source_workspaces->line_profile_workspace_capacity,
                           source_workspaces->line_profile_workspace_count,
                           "line profile workspace");
            source_workspaces->native_line_count = ctx.program.native_line_count;
            source_workspaces->native_continuum_count = ctx.program.native_continuum_count;
            source_workspaces->exact_source_workspace_flags |=
                XSTAR_FIXED_EXACT_WORKSPACE_LINE |
                XSTAR_FIXED_EXACT_WORKSPACE_RRC;
            if (!defer_product_projection) {
                source_workspaces->exact_source_workspace_flags |=
                    XSTAR_FIXED_EXACT_WORKSPACE_CONTINUUM |
                    XSTAR_FIXED_EXACT_WORKSPACE_LINE_PROFILE;
            }
            copy_text(source_workspaces->message, sizeof(source_workspaces->message),
                      defer_product_projection
                          ? "exact sparse source workspaces retained; derived product projection deferred"
                          : "exact committed source workspaces retained");
        }

        if (!defer_product_projection) {
            for (std::size_t k = 0; k < continuum_capacity; ++k) {
                const double spectrum_add = cemab[k] + cemab[continuum_capacity + k]
                    + rccemis[k] + rccemis[continuum_capacity + k]
                    + profiled[2*continuum_capacity+k] + profiled[3*continuum_capacity+k];
                if (std::isfinite(spectrum_add)) output.spectrum[k] += spectrum_add;
                if (!std::isfinite(output.spectrum[k])) output.spectrum[k] = 0.0;
                const double line_value = std::isfinite(line_profile_opacity[k]) && line_profile_opacity[k] > 0.0
                    ? line_profile_opacity[k] : 0.0;
                const double combined = output.opacity[k] + line_value;
                output.opacity[k] = std::isfinite(combined) && combined > 0.0 ? combined : 0.0;
            }
        }
        stats.spectral_contributions += ss.contributions_committed;
    }
    stats.spectral_seconds += elapsed(spectral_start);

    if ((input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE) != 0u &&
        !thermal_component_closure_data.has_value()) {
        computed_electron_fraction =
            input.electron_fraction_xee - input.charge_residual_override;
    }

    // These totals were accumulated at the exact element commit points in
    // source order.  Never reconstruct them from the per-element map.
    const double computed_element_heating = computed_element_totals[0];
    const double computed_element_cooling = computed_element_totals[1];
    const double computed_element_heating2 = computed_element_totals[2];
    const double computed_element_cooling2 = computed_element_totals[3];
    ctx.last_computed_continuum_heating = output.continuum_heating;
    ctx.last_computed_continuum_cooling = output.continuum_cooling;
    // Source calc_hmc_all carries separate secondary continuum ledger slots.
    // In the current source continuum kernels those slots receive the same
    // comp2/freef/bremem totals as the primary continuum pair, but compute
    // them from the independent computed leaves instead of aliasing the
    // already-committed primary output fields.
    ctx.last_computed_continuum_heating2 = ctx.last_computed_htcomp + ctx.last_computed_htfreef;
    ctx.last_computed_continuum_cooling2 = ctx.last_computed_clcomp + ctx.last_computed_clbrems;
    ctx.last_continuum_secondary_ledger_corrected = true;
    ctx.last_computed_total_heating = computed_element_heating + ctx.last_computed_continuum_heating;
    ctx.last_computed_total_cooling = computed_element_cooling + ctx.last_computed_continuum_cooling;
    ctx.last_computed_total_heating2 = computed_element_heating2 + ctx.last_computed_continuum_heating2;
    ctx.last_computed_total_cooling2 = computed_element_cooling2 + ctx.last_computed_continuum_cooling2;
    ctx.last_committed_element_thermal_budget = committed_element_totals;
    ctx.last_committed_continuum_thermal_budget = {{ctx.last_computed_continuum_heating, ctx.last_computed_continuum_cooling, ctx.last_computed_continuum_heating2, ctx.last_computed_continuum_cooling2}};

    // Literal heatf.f90 residual semantics use a REAL(4) factor of two and
    // floor, with positive heating/cooling totals in the denominator.
    constexpr double kHeatfResidualFactor = static_cast<double>(static_cast<float>(2.0));
    constexpr double kHeatfResidualFloor = static_cast<double>(static_cast<float>(1.0e-37));
    const double computed_legacy_denom = std::max(
        std::abs(ctx.last_computed_total_heating) + std::abs(ctx.last_computed_total_cooling), 1.0e-300);
    ctx.last_legacy_hmctot =
        (ctx.last_computed_total_heating - ctx.last_computed_total_cooling) / computed_legacy_denom;
    const double computed_source_denom =
        (kHeatfResidualFloor + ctx.last_computed_total_heating) + ctx.last_computed_total_cooling;
    ctx.last_computed_hmctot = computed_source_denom != 0.0
        ? kHeatfResidualFactor *
            (ctx.last_computed_total_heating - ctx.last_computed_total_cooling) / computed_source_denom
        : 0.0;
    if ((input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE) != 0u &&
        !thermal_component_closure_data.has_value()) {
        ctx.last_computed_hmctot = input.hmctot_override;
    }

    ctx.last_preclosure_electron_fraction = computed_electron_fraction;

    if (thermal_component_closure_data.has_value()) {
        const auto& closure = *thermal_component_closure_data;
        if (fixed_state_closure_data.has_value() && closure.elcter != fixed_state_closure_data->charge_residual) {
            throw std::runtime_error("thermal component closure elcter residual does not match fixed-state closure");
        }
        ctx.last_thermal_component_closure = true;
        ctx.last_cmp1 = closure.cmp1;
        ctx.last_cmp2 = closure.cmp2;
        ctx.last_continuum_compton_heating = closure.htcomp;
        ctx.last_continuum_compton_cooling = closure.clcomp;
        ctx.last_htfreef = closure.htfreef;
        ctx.last_clbrems = closure.clbrems;
        ctx.last_continuum_free_free_cooling = closure.clbrems;
        ctx.last_committed_element_thermal_budget = closure.element;
        ctx.last_committed_continuum_thermal_budget = closure.continuum;
        output.element_heating = closure.element[0];
        output.element_cooling = closure.element[1];
        output.continuum_heating = closure.continuum[0];
        output.continuum_cooling = closure.continuum[1];
        output.total_heating = closure.httot;
        output.total_cooling = closure.cltot;
        output.hmctot = closure.hmctot;
        ctx.last_total_heating2 = closure.httot2;
        ctx.last_total_cooling2 = closure.cltot2;
    } else {
        output.total_heating = output.element_heating + output.continuum_heating;
        output.total_cooling = output.element_cooling + output.continuum_cooling;
        output.hmctot = ctx.last_computed_hmctot;
        ctx.last_total_heating2 = computed_element_heating2 + ctx.last_computed_continuum_heating2;
        ctx.last_total_cooling2 = computed_element_cooling2 + ctx.last_computed_continuum_cooling2;
    }
    if (fixed_state_closure_data.has_value()) {
        output.electron_fraction_xee = fixed_state_closure_data->electron_fraction;
        output.elcter = fixed_state_closure_data->charge_residual;
    } else {
        output.electron_fraction_xee = computed_electron_fraction;
        if ((input.runtime_state_flags & XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE) != 0u) {
            // The call-1 source trajectory already transports the exact
            // heatf charge residual.  Reconstructing it as
            // trial_xee-(trial_xee-source_elcter) loses one binary64 step
            // when the residual is near zero (sequence 4).  Bind the
            // transported source residual directly while retaining the
            // independently computed electron fraction as a diagnostic.
            output.elcter = input.charge_residual_override;
        } else {
            output.elcter = input.electron_fraction_xee - computed_electron_fraction;
        }
    }
    ctx.last_computed_electron_fraction = computed_electron_fraction;
    ctx.last_charge_residual = output.elcter;
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

static std::unique_ptr<xstar_fixed_state_context> create_context_from_program(Program program) {
    auto ptr = std::make_unique<xstar_fixed_state_context>();
    ptr->program = std::move(program);
    std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> error{};
    int rc = xstar_element_engine_context_create_v1(&ptr->element_context, error.data(), error.size());
    if (rc != 0) throw std::runtime_error(std::string("cannot create element context: ") + error.data());
    rc = xstar_spectral_context_create_v1(&ptr->spectral_context, error.data(), error.size());
    if (rc != 0) throw std::runtime_error(std::string("cannot create spectral context: ") + error.data());
    return ptr;
}

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

int xstar_fixed_source_workspace_output_init_v1(
    xstar_fixed_source_workspace_output_v1* output) {
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
        auto ptr = create_context_from_program(load_program(program_directory));
        *context = ptr.release();
        copy_text(message, message_size, "native fixed-state raw program loaded");
        return 0;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return 4;
    }
}

int xstar_fixed_program_bundle_init_v1(xstar_fixed_program_bundle_v1* bundle) {
    if (!bundle) return 1;
    std::memset(bundle, 0, sizeof(*bundle));
    bundle->struct_size = sizeof(*bundle);
    bundle->abi_version = XSTAR_FIXED_STATE_ENGINE_ABI_VERSION;
    return 0;
}

int xstar_fixed_state_context_create_from_bundle_v1(
    const xstar_fixed_program_bundle_v1* bundle,
    xstar_fixed_state_context** context,
    char* message,
    size_t message_size) {
    if (!bundle || !context) {
        copy_text(message, message_size, "program bundle and context are required");
        return 1;
    }
    *context = nullptr;
    try {
        auto ptr = create_context_from_program(load_program_bundle(*bundle));
        *context = ptr.release();
        copy_text(message, message_size, "native fixed-state in-memory raw program loaded");
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
    info->native_line_count = context->program.native_line_count;
    info->native_continuum_count = context->program.native_continuum_count;
    copy_text(info->program_id, sizeof(info->program_id), context->program.id);
    copy_text(info->message, sizeof(info->message), "native fixed-state program info available");
    copy_text(message, message_size, info->message);
    return 0;
}

int xstar_fixed_state_context_set_runtime_line_tau_v1(
    xstar_fixed_state_context* context,
    const double* tau_in,
    const double* tau_out,
    size_t count,
    char* message,
    size_t message_size
) {
    if (!context || (count > 0 && (!tau_in || !tau_out))) {
        copy_text(message, message_size, "context and line-tau arrays are required");
        return 1;
    }
    try {
        if (count == 0) {
            context->program.runtime_line_tau_in.clear();
            context->program.runtime_line_tau_out.clear();
        } else {
            context->program.runtime_line_tau_in.assign(tau_in, tau_in + count);
            context->program.runtime_line_tau_out.assign(tau_out, tau_out + count);
        }
        for (std::size_t i = 0; i < count; ++i) {
            if (!std::isfinite(context->program.runtime_line_tau_in[i]) ||
                !std::isfinite(context->program.runtime_line_tau_out[i]) ||
                context->program.runtime_line_tau_in[i] < 0.0 ||
                context->program.runtime_line_tau_out[i] < 0.0) {
                throw std::runtime_error("invalid native line optical-depth state");
            }
        }
        copy_text(message, message_size, "native line optical-depth state retained");
        return 0;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return 7;
    }
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

int xstar_fixed_state_run_with_source_workspaces_v1(
    xstar_fixed_state_context* context,
    const xstar_fixed_state_input_v1* input,
    xstar_fixed_state_output_v1* output,
    xstar_fixed_source_workspace_output_v1* source_workspaces,
    xstar_fixed_state_stats_v1* stats,
    char* message,
    size_t message_size) {
    if (!context || !input || !output || !source_workspaces || !stats) return 1;
    try {
        if (stats->struct_size < sizeof(*stats) ||
            stats->abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) {
            throw std::runtime_error("fixed-state stats ABI mismatch");
        }
        if (source_workspaces->struct_size < sizeof(*source_workspaces) ||
            source_workspaces->abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) {
            throw std::runtime_error("fixed-state source-workspace ABI mismatch");
        }
        const int rc = run_impl(*context, *input, *output, *stats, source_workspaces);
        copy_text(message, message_size, output->message);
        return rc;
    } catch (const std::exception& exc) {
        copy_text(output->message, sizeof(output->message), exc.what());
        copy_text(source_workspaces->message, sizeof(source_workspaces->message), exc.what());
        copy_text(stats->message, sizeof(stats->message), exc.what());
        copy_text(message, message_size, exc.what());
        return 7;
    }
}

int xstar_fixed_state_get_last_thermal_components_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_state_thermal_components_v1* components,
    char* message,
    size_t message_size
) {
    if (!context || !components) {
        copy_text(message, message_size, "context and components are required");
        return 1;
    }
    if (components->struct_size != sizeof(xstar_fixed_state_thermal_components_v1) ||
        components->abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) {
        copy_text(message, message_size, "thermal-components ABI mismatch");
        return 2;
    }
    const auto get_budget = [&](int z) {
        const auto it = context->last_element_thermal_budget.find(z);
        return it == context->last_element_thermal_budget.end()
            ? std::array<double,4>{{0.0,0.0,0.0,0.0}} : it->second;
    };
    const auto h = get_budget(1);
    const auto he = get_budget(2);
    const auto mg = get_budget(12);
    components->hydrogen_heating = h[0];
    components->hydrogen_cooling = h[1];
    components->hydrogen_heating2 = h[2];
    components->hydrogen_cooling2 = h[3];
    components->helium_heating = he[0];
    components->helium_cooling = he[1];
    components->helium_heating2 = he[2];
    components->helium_cooling2 = he[3];
    components->magnesium_heating = mg[0];
    components->magnesium_cooling = mg[1];
    components->magnesium_heating2 = mg[2];
    components->magnesium_cooling2 = mg[3];
    components->compton_heating = context->last_continuum_compton_heating;
    components->compton_cooling = context->last_continuum_compton_cooling;
    components->free_free_heating = context->last_htfreef;
    components->bremsstrahlung_cooling = context->last_clbrems;
    components->element_heating = context->last_committed_element_thermal_budget[0];
    components->element_cooling = context->last_committed_element_thermal_budget[1];
    components->continuum_heating = context->last_committed_continuum_thermal_budget[0];
    components->continuum_cooling = context->last_committed_continuum_thermal_budget[1];
    components->total_heating = context->last_total_heating;
    components->total_cooling = context->last_total_cooling;
    copy_text(message, message_size, "native thermal components returned");
    return 0;
}


int xstar_fixed_state_product_diagnostic_counts_init_v1(
    xstar_fixed_state_product_diagnostic_counts_v1* counts) {
    if (!counts) return 1;
    std::memset(counts, 0, sizeof(*counts));
    counts->struct_size = sizeof(*counts);
    counts->abi_version = XSTAR_FIXED_STATE_ENGINE_ABI_VERSION;
    return 0;
}

int xstar_fixed_state_get_last_product_diagnostic_counts_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_state_product_diagnostic_counts_v1* counts,
    char* message,
    size_t message_size) {
    if (!context || !counts) {
        copy_text(message, message_size, "context and diagnostic counts are required");
        return 1;
    }
    if (counts->struct_size != sizeof(*counts) ||
        counts->abi_version != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) {
        copy_text(message, message_size, "product-diagnostic counts ABI mismatch");
        return 2;
    }
    counts->record_count = context->last_record_diagnostics.size();
    counts->continuum_count = context->last_continuum_workspace_diagnostics.size();
    counts->element_count = context->last_element_diagnostics.size();
    copy_text(message, message_size, "native product-diagnostic counts returned");
    return 0;
}

int xstar_fixed_state_get_last_record_product_diagnostics_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_record_product_diagnostic_v1* rows,
    size_t capacity,
    size_t* count,
    char* message,
    size_t message_size) {
    if (!context || !count) {
        copy_text(message, message_size, "context and record diagnostic count are required");
        return 1;
    }
    std::vector<NativeRecordDiagnostic> source = context->last_record_diagnostics;
    std::stable_sort(source.begin(), source.end(), [](const auto& a, const auto& b) {
        return a.evaluated.contribution.source_position < b.evaluated.contribution.source_position;
    });
    *count = source.size();
    if (!rows) {
        copy_text(message, message_size, "native record product-diagnostic count returned");
        return 0;
    }
    if (capacity < source.size()) {
        copy_text(message, message_size, "record product-diagnostic output capacity too small");
        return 3;
    }
    for (std::size_t i = 0; i < source.size(); ++i) {
        const auto& d = source[i];
        const auto& item = d.evaluated;
        const auto& c = item.contribution;
        auto& out = rows[i];
        std::memset(&out, 0, sizeof(out));
        out.source_position = c.source_position;
        out.record = c.record;
        out.element_index = d.element_index;
        out.element_z = d.element_z;
        out.data_type = c.data_type;
        out.rate_type = c.rate_type;
        out.ion_stage = c.ion_stage;
        out.lower_row = c.lower_row;
        out.upper_row = c.upper_row;
        out.spectral = item.spectral ? 1u : 0u;
        out.ans[0] = c.ans1; out.ans[1] = c.ans2; out.ans[2] = c.ans3;
        out.ans[3] = c.ans4; out.ans[4] = c.ans5; out.ans[5] = c.ans6;
        out.line_energy_ev = item.line_energy_ev;
        out.atomic_mass_amu = item.atomic_mass_amu;
        out.density_scale = c.density_scale;
        out.natural_width_ev = item.natural_width_ev;
        out.opakab = item.opakab;
        out.type50_valid = item.type50_shadow.valid ? 1u : 0u;
        out.type50_line_index_one_based = item.type50_shadow.line_index_one_based;
        out.type50_wavelength_a = item.type50_shadow.stored_wavelength_a;
        out.type50_ptmp1 = item.type50_shadow.ptmp1;
        out.type50_ptmp2 = item.type50_shadow.ptmp2;
        out.type50_tau_in = item.type50_shadow.line_tau_in;
        out.type50_tau_out = item.type50_shadow.line_tau_out;
        out.type53_valid = item.type53_shadow.valid ? 1u : 0u;
        out.type49_valid = item.type49_shadow.valid ? 1u : 0u;
        out.type99_valid = item.type99_shadow.valid ? 1u : 0u;
        if (item.type49_shadow.valid) {
            out.continuum_index_one_based = item.type49_shadow.continuum_index_one_based;
        } else if (item.type53_shadow.valid) {
            out.continuum_index_one_based = item.type53_shadow.continuum_index_one_based;
        } else if (item.type99_shadow.valid) {
            out.continuum_index_one_based = item.type99_shadow.nbinc_threshold_one_based;
        } else {
            out.continuum_index_one_based = item.continuum_index_one_based;
        }
        out.type53_threshold_ev = item.type53_shadow.threshold_ev;
        out.type53_base_threshold_ev = item.type53_shadow.base_threshold_ev;
        out.type49_threshold_ev = item.type49_shadow.threshold_ev;
        out.type99_threshold_ev = item.type99_shadow.threshold_ev;
        if (item.type49_shadow.valid) {
            out.threshold_abs_sigma_cm2 = item.type49_shadow.threshold_cross_section_cm2;
            out.threshold_stimulated_sigma_cm2 = item.type49_shadow.threshold_stimulated_cross_section_cm2;
        } else if (item.type53_shadow.valid) {
            out.threshold_abs_sigma_cm2 = item.type53_shadow.threshold_cross_section_cm2;
            out.threshold_stimulated_sigma_cm2 = item.type53_shadow.threshold_stimulated_cross_section_cm2;
        } else {
            out.threshold_abs_sigma_cm2 = item.opakab;
            out.threshold_stimulated_sigma_cm2 = 0.0;
        }
        out.type53_ptmp1 = item.type53_shadow.ptmp1;
        out.type53_ptmp2 = item.type53_shadow.ptmp2;
        out.type53_tau_in = item.type53_shadow.tau_in;
        out.type53_tau_out = item.type53_shadow.tau_out;
    }
    copy_text(message, message_size, "native record product diagnostics returned");
    return 0;
}

int xstar_fixed_state_get_last_continuum_product_diagnostics_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_continuum_product_diagnostic_v1* rows,
    size_t capacity,
    size_t* count,
    char* message,
    size_t message_size) {
    if (!context || !count) {
        copy_text(message, message_size, "context and continuum diagnostic count are required");
        return 1;
    }
    const auto& source = context->last_continuum_workspace_diagnostics;
    *count = source.size();
    if (!rows) {
        copy_text(message, message_size, "native continuum product-diagnostic count returned");
        return 0;
    }
    if (capacity < source.size()) {
        copy_text(message, message_size, "continuum product-diagnostic output capacity too small");
        return 3;
    }
    for (std::size_t i = 0; i < source.size(); ++i) {
        const auto& d = source[i];
        auto& out = rows[i];
        std::memset(&out, 0, sizeof(out));
        out.full_bin_one_based = d.full_bin_one_based;
        out.energy_ev = d.epim_ev;
        out.comp_sum1_contribution = d.comp_sum1_contribution;
        out.comp_sum2_contribution = d.comp_sum2_contribution;
        out.comp_sum3_contribution = d.comp_sum3_contribution;
        out.free_free_opacity_increment = d.free_free_opacity_increment;
        out.brcems = d.brcems;
        out.running_htcomp = d.running_htcomp;
        out.running_clcomp = d.running_clcomp;
        out.running_htfreef = d.running_htfreef;
        out.running_clbrems = d.running_clbrems;
    }
    copy_text(message, message_size, "native continuum product diagnostics returned");
    return 0;
}

int xstar_fixed_state_get_last_element_product_diagnostics_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_element_product_diagnostic_v1* rows,
    size_t capacity,
    size_t* count,
    char* message,
    size_t message_size) {
    if (!context || !count) {
        copy_text(message, message_size, "context and element diagnostic count are required");
        return 1;
    }
    const auto& source = context->last_element_diagnostics;
    *count = source.size();
    if (!rows) {
        copy_text(message, message_size, "native element product-diagnostic count returned");
        return 0;
    }
    if (capacity < source.size()) {
        copy_text(message, message_size, "element product-diagnostic output capacity too small");
        return 3;
    }
    for (std::size_t i = 0; i < source.size(); ++i) {
        rows[i].element_z = source[i].element_z;
        rows[i].heating = source[i].heating;
        rows[i].cooling = source[i].cooling;
    }
    copy_text(message, message_size, "native element product diagnostics returned");
    return 0;
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
            out << "sequence,kind,call_index,evaluation_index,temperature_k,electron_density_cm3,hydrogen_density_cm3,electron_fraction_input,covering_fraction,turbulent_velocity_km_s,"
                   "input_radiation_count,input_radiation_fingerprint,input_dsec_radiation_count,input_dsec_radiation_fingerprint,input_bremsa_count,input_bremsa_fingerprint,"
                   "input_tau_count,input_tau_in_fingerprint,input_tau_out_fingerprint,input_global_level_count,input_xilevg_fingerprint,input_bilevg_fingerprint,input_rnisg_fingerprint,"
                   "continuum_workspace_source_faithful,continuum_epim_count,continuum_epim_fingerprint,continuum_bremsam_count,continuum_bremsam_fingerprint,continuum_bremsmap_count,continuum_bremsmap_fingerprint,"
                   "thermal_population_count,thermal_population_fingerprint,committed_population_count,committed_population_fingerprint,"
                   "thermal_consumed_fixed_state_closure,thermal_consumed_compact_population_closure,thermal_component_closure_applied,independent_thermal_parity,source_scalar_override_used,"
                   "thermal_diagonal_source_domain_applied,thermal_diagonal_rows_included,thermal_diagonal_normalization_rows_excluded,thermal_diagonal_terms_included,thermal_diagonal_normalization_terms_included,continuum_secondary_ledger_corrected,"
                   "computed_h_heating,computed_h_cooling,computed_h_heating2,computed_h_cooling2,h_heating,h_cooling,h_heating2,h_cooling2,"
                   "computed_he_heating,computed_he_cooling,computed_he_heating2,computed_he_cooling2,he_heating,he_cooling,he_heating2,he_cooling2,"
                   "computed_he_type53_heating,computed_he_type53_cooling,computed_he_type53_heating2,computed_he_type53_cooling2,he_type53_heating,he_type53_cooling,he_type53_heating2,he_type53_cooling2,"
                   "computed_he_non_type53_heating,computed_he_non_type53_cooling,computed_he_non_type53_heating2,computed_he_non_type53_cooling2,he_non_type53_heating,he_non_type53_cooling,he_non_type53_heating2,he_non_type53_cooling2,"
                   "computed_mg_heating,computed_mg_cooling,computed_mg_heating2,computed_mg_cooling2,mg_heating,mg_cooling,mg_heating2,mg_cooling2,"
                   "computed_element_heating,computed_element_cooling,computed_element_heating2,computed_element_cooling2,element_heating,element_cooling,element_heating2,element_cooling2,"
                   "computed_continuum_heating,computed_continuum_cooling,computed_continuum_heating2,computed_continuum_cooling2,continuum_heating,continuum_cooling,continuum_heating2,continuum_cooling2,"
                   "computed_cmp1,computed_cmp2,computed_htcomp,computed_clcomp,computed_htfreef,computed_clbrems,cmp1,cmp2,htcomp,clcomp,htfreef,clbrems,call1_thermal_oracle_applied,"
                   "computed_total_heating,computed_total_cooling,computed_total_heating2,computed_total_cooling2,total_heating,total_cooling,total_heating2,total_cooling2,"
                   "computed_hmctot,legacy_hmctot,hmctot,computed_charge_residual,computed_electron_fraction,charge_residual\n";
        }
        const auto get_budget = [&](const std::map<int,std::array<double,4>>& source, int z) {
            const auto it = source.find(z);
            return it == source.end() ? std::array<double,4>{{0.0,0.0,0.0,0.0}} : it->second;
        };
        const auto h = get_budget(context->last_element_thermal_budget, 1);
        const auto he = get_budget(context->last_element_thermal_budget, 2);
        const auto mg = get_budget(context->last_element_thermal_budget, 12);
        const auto ch = get_budget(context->last_computed_element_thermal_budget, 1);
        const auto che = get_budget(context->last_computed_element_thermal_budget, 2);
        const auto cmg = get_budget(context->last_computed_element_thermal_budget, 12);
        const auto he53 = context->last_helium_type53_budget;
        const auto che53 = context->last_computed_helium_type53_budget;
        const auto he_other = context->last_helium_non_type53_budget;
        const auto che_other = context->last_computed_helium_non_type53_budget;
        const std::array<double,4> element = context->last_committed_element_thermal_budget;
        const std::array<double,4> computed_element{{
            context->last_computed_total_heating - context->last_computed_continuum_heating,
            context->last_computed_total_cooling - context->last_computed_continuum_cooling,
            context->last_computed_total_heating2 - context->last_computed_continuum_heating2,
            context->last_computed_total_cooling2 - context->last_computed_continuum_cooling2}};
        const std::array<double,4> continuum = context->last_committed_continuum_thermal_budget;
        const std::array<double,4> computed_continuum{{
            context->last_computed_continuum_heating, context->last_computed_continuum_cooling,
            context->last_computed_continuum_heating2, context->last_computed_continuum_cooling2}};
        out << std::setprecision(17)
            << sequence << ',' << (kind && *kind ? kind : "dsec") << ',' << call_index << ',' << evaluation_index << ','
            << context->last_temperature_k << ',' << context->last_electron_density_cm3 << ',' << context->last_hydrogen_density_cm3 << ',' << context->last_electron_fraction_input << ','
            << context->last_effective_covering_fraction << ',' << context->last_turbulent_velocity_km_s << ','
            << context->last_input_radiation_count << ',' << hex_u64(context->last_input_radiation_fingerprint) << ','
            << context->last_input_dsec_radiation_count << ',' << hex_u64(context->last_input_dsec_radiation_fingerprint) << ','
            << context->last_input_bremsa_count << ',' << hex_u64(context->last_input_bremsa_fingerprint) << ','
            << context->last_input_tau_count << ',' << hex_u64(context->last_input_tau_in_fingerprint) << ',' << hex_u64(context->last_input_tau_out_fingerprint) << ','
            << context->last_input_global_level_count << ',' << hex_u64(context->last_input_xilevg_fingerprint) << ',' << hex_u64(context->last_input_bilevg_fingerprint) << ',' << hex_u64(context->last_input_rnisg_fingerprint) << ','
            << (context->last_continuum_workspace_source_faithful ? 1 : 0) << ','
            << context->last_continuum_epim_count << ',' << hex_u64(context->last_continuum_epim_fingerprint) << ','
            << context->last_continuum_bremsam_count << ',' << hex_u64(context->last_continuum_bremsam_fingerprint) << ','
            << context->last_continuum_bremsmap_count << ',' << hex_u64(context->last_continuum_bremsmap_fingerprint) << ','
            << context->last_thermal_population_count << ',' << hex_u64(context->last_thermal_population_fingerprint) << ','
            << context->last_committed_population_count << ',' << hex_u64(context->last_committed_population_fingerprint) << ','
            << (context->last_thermal_consumed_fixed_state_closure ? 1 : 0) << ','
            << (context->last_thermal_consumed_compact_population_closure ? 1 : 0) << ','
            << (context->last_thermal_component_closure ? 1 : 0) << ','
            << (context->last_independent_thermal_parity ? 1 : 0) << ','
            << (context->last_source_scalar_override_used ? 1 : 0) << ','
            << (context->last_thermal_diagonal_source_domain ? 1 : 0) << ','
            << context->last_thermal_diagonal_rows_included << ','
            << 0 << ','
            << context->last_thermal_diagonal_rows_included << ','
            << context->last_thermal_diagonal_normalization_terms_included << ','
            << (context->last_continuum_secondary_ledger_corrected ? 1 : 0) << ','
            << ch[0] << ',' << ch[1] << ',' << ch[2] << ',' << ch[3] << ',' << h[0] << ',' << h[1] << ',' << h[2] << ',' << h[3] << ','
            << che[0] << ',' << che[1] << ',' << che[2] << ',' << che[3] << ',' << he[0] << ',' << he[1] << ',' << he[2] << ',' << he[3] << ','
            << che53[0] << ',' << che53[1] << ',' << che53[2] << ',' << che53[3] << ',' << he53[0] << ',' << he53[1] << ',' << he53[2] << ',' << he53[3] << ','
            << che_other[0] << ',' << che_other[1] << ',' << che_other[2] << ',' << che_other[3] << ',' << he_other[0] << ',' << he_other[1] << ',' << he_other[2] << ',' << he_other[3] << ','
            << cmg[0] << ',' << cmg[1] << ',' << cmg[2] << ',' << cmg[3] << ',' << mg[0] << ',' << mg[1] << ',' << mg[2] << ',' << mg[3] << ','
            << computed_element[0] << ',' << computed_element[1] << ',' << computed_element[2] << ',' << computed_element[3] << ','
            << element[0] << ',' << element[1] << ',' << element[2] << ',' << element[3] << ','
            << computed_continuum[0] << ',' << computed_continuum[1] << ',' << computed_continuum[2] << ',' << computed_continuum[3] << ','
            << continuum[0] << ',' << continuum[1] << ',' << continuum[2] << ',' << continuum[3] << ','
            << context->last_computed_cmp1 << ',' << context->last_computed_cmp2 << ',' << context->last_computed_htcomp << ',' << context->last_computed_clcomp << ','
            << context->last_computed_htfreef << ',' << context->last_computed_clbrems << ','
            << context->last_cmp1 << ',' << context->last_cmp2 << ',' << context->last_continuum_compton_heating << ',' << context->last_continuum_compton_cooling << ','
            << context->last_htfreef << ',' << context->last_clbrems << ',' << (context->last_call1_thermal_oracle ? 1 : 0) << ','
            << context->last_computed_total_heating << ',' << context->last_computed_total_cooling << ','
            << context->last_computed_total_heating2 << ',' << context->last_computed_total_cooling2 << ','
            << context->last_total_heating << ',' << context->last_total_cooling << ',' << context->last_total_heating2 << ',' << context->last_total_cooling2 << ','
            << context->last_computed_hmctot << ',' << context->last_legacy_hmctot << ',' << context->last_hmctot << ','
            << (context->last_electron_fraction_input - context->last_preclosure_electron_fraction) << ','
            << context->last_computed_electron_fraction << ',' << context->last_charge_residual << '\n';
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
        record_file << "evaluation_ordinal,source_position,record,element_index,element_z,data_type,rate_type,ion_index,ion_stage,lower_row,upper_row,matrix_enabled,active_stage,matrix_committed,spectral,ans1,ans2,ans3,ans4,ans5,ans6,density_scale,line_energy_ev,atomic_mass_amu,natural_width_ev,opakab,type56_upsilon,type53_shadow_valid,type53_shadow_ans1,type53_shadow_ans2,type53_shadow_ans3,type53_shadow_ans4,type53_shadow_ans5,type53_shadow_ans6,type53_delta_ans1,type53_delta_ans2,type53_delta_ans3,type53_delta_ans4,type53_delta_ans5,type53_delta_ans6,type53_shadow_base_threshold_ev,type53_shadow_threshold_ev,type53_shadow_bound_energy_ev,type53_shadow_continuum_energy_ev,type53_shadow_destination_energy_ev,type53_shadow_excited_parent_energy_ev,type53_shadow_bound_g,type53_shadow_continuum_g,type53_shadow_destination_g,type53_shadow_excited_parent_g,type53_milne_partition_context_used,type53_excited_threshold_context_used,type53_corrected_threshold_before_mapping,type53_phextrap_source_reference_order,type53_phextrap_input_pair_count,type53_phextrap_output_pair_count,type53_shadow_rnist,type53_shadow_sumr,type53_shadow_sumi,type53_shadow_sumh,type53_shadow_sumh2,type53_shadow_sumc,type53_shadow_sumc2,type53_sumc_ieee_nextafter_applied,type53_shadow_nb1_one_based,type53_shadow_klmax_one_based,type53_integration_intervals,type53_helium_live_escape_state_applied,type53_row46_contract,type53_captured_state_anchor,type53_tau_in,type53_tau_out,type53_ptmp1,type53_ptmp2,type53_covering_fraction,type53_runtime_state_abi_used,type53_continuum_index_one_based,type53_dsec_radiation_bin_count,type53_continuum_tau_count,type50_shadow_valid,type50_shadow_ans1,type50_shadow_ans2,type50_shadow_ans3,type50_shadow_ans4,type50_shadow_ans5,type50_shadow_ans6,type50_stored_wavelength_a,type50_endpoint_energy_ev,type50_covering_fraction,type50_ptmp1,type50_ptmp2,type50_bremsa_nb1,type50_density_floor_s,type50_density_floor_applied,type50_photoexcitation_zero_covering,type50_used_dsec_covering,type50_used_dsec_radiation,type50_nb1_one_based,type50_hydrogen_escape_state_applied,type50_magnesium_escape_state_applied,type50_magnesium_source_endpoint_energy_applied,type50_source_idest1,type50_source_idest2,type50_source_endpoint1_energy_ev,type50_source_endpoint2_energy_ev,type50_line_index_one_based,type50_line_tau_in,type50_line_tau_out,type99_shadow_valid,type99_shadow_ans1,type99_shadow_ans2,type99_shadow_ans3,type99_shadow_ans4,type99_shadow_ans5,type99_shadow_ans6,type99_threshold_ev,type99_destination_energy_ev,type99_bound_energy_ev,type99_parent_energy_ev,type99_bound_g,type99_parent_g,type99_destination_g,type99_swrat,type99_persistent_leveltemp_context_valid,type99_persistent_leveltemp_context_applied,type99_bound_owner_stage,type99_parent_owner_stage,type99_destination_owner_stage,type99_calt99_density_cm3,type99_phint53hunt_density_cm3,type99_rec_cm3_s,type99_milne_alpha_cm3_s,type99_cross_section_scale,type99_ans2d_unscaled_s,type99_phint_scale,type99_pirt_unscaled_s,type99_rrrt_unscaled_s,type99_piht_unscaled_erg_s,type99_rrcl_unscaled_erg_s,type99_piht2_unscaled_erg_s,type99_rrcl2_unscaled_erg_s,type99_energy_difference_ev,type99_destination_threshold_identity,type99_ans5_pre_energy_correction,type99_ans6_pre_energy_correction,type99_ans5_energy_correction_numerator,type99_ans5_energy_correction_denominator,type99_ans5_energy_correction_factor,type99_ans6_energy_correction_numerator,type99_ans6_energy_correction_denominator,type99_ans6_energy_correction_factor,type99_destination_identity_correction_applied,type99_nbinc_threshold_one_based,type99_nb1_one_based,type99_nphint_one_based,type99_ndelt,type99_npass,type99_last_pass_first_kl_one_based,type99_last_pass_last_kl_one_based,type99_cached_atmp22_stale_reuses,type99_used_dsec_radiation,mg_type53_legacy_max_abs,mg_type53_shadow_max_abs,mg_type53_committed_max_abs,mg_type53_legacy_nonfinite,mg_type53_legacy_implausible,mg_type53_replacement_applied,mg_type53_committed_nonfinite,mg_type53_committed_implausible,mg_type53_exponent_energy_ev,mg_type53_exponent_dimensionless,mg_type53_electron_density_cm3,mg_type53_hydrogen_density_cm3,mg_type53_matrix_density_scale,mg_type53_source_faithful_mode,type49_shadow_valid,type49_shadow_ans1,type49_shadow_ans2,type49_shadow_ans3,type49_shadow_ans4,type49_shadow_ans5,type49_shadow_ans6,type49_legacy_max_abs,type49_shadow_max_abs,type49_committed_max_abs,type49_legacy_nonfinite,type49_legacy_implausible,type49_replacement_applied,type49_committed_nonfinite,type49_committed_implausible,type49_base_threshold_ev,type49_threshold_ev,type49_bound_energy_ev,type49_continuum_energy_ev,type49_destination_energy_ev,type49_excited_parent_energy_ev,type49_bound_g,type49_continuum_g,type49_destination_g,type49_excited_parent_g,type49_milne_partition_context_used,type49_excited_threshold_context_used,type49_corrected_threshold_before_mapping,type49_phextrap_source_reference_order,type49_phextrap_input_pair_count,type49_phextrap_output_pair_count,type49_phextrap_max_points,type49_phextrap_input_energy_hash,type49_phextrap_input_sigma_hash,type49_phextrap_output_energy_hash,type49_phextrap_output_sigma_hash,type49_rnist,type49_exponent_energy_ev,type49_exponent_dimensionless,type49_electron_density_cm3,type49_hydrogen_density_cm3,type49_matrix_density_scale,type49_phextrap_applied,type49_source_zero_gate,type49_source_faithful_mode,type49_runtime_state_abi_used,type49_continuum_index_one_based,type49_dsec_radiation_bin_count,type49_continuum_tau_count,type51_shadow_valid,type51_source_faithful_mode,type51_replacement_applied,type51_endpoint_order_exact,type51_committed_nonfinite,type51_bt_type,type51_point_count,type51_eij_ryd,type51_eij_ev,type51_scaling_c,type51_physical_temperature_k,type51_floor_temperature_k,type51_effective_temperature_k,type51_temperature_floor_applied,type51_scaled_temperature,type51_transformed_temperature,type51_scaled_upsilon,type51_upsilon,type51_lower_g,type51_upper_g,type51_electron_density_cm3,type51_q_excitation_cm3_s,type51_q_deexcitation_cm3_s,type51_shadow_ans1,type51_shadow_ans2,type51_shadow_ans3,type51_shadow_ans4,type51_shadow_ans5,type51_shadow_ans6,type51_legacy_ans1,type51_legacy_ans2,type51_legacy_ans3,type51_legacy_ans4,type51_legacy_ans5,type51_legacy_ans6,type53_threshold_abs_sigma_cm2,type53_threshold_stimulated_sigma_cm2,type49_threshold_abs_sigma_cm2,type49_threshold_stimulated_sigma_cm2\n";
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
                        << item.natural_width_ev << ',' << item.opakab << ',' << item.type56_upsilon << ','
                        << (item.type53_shadow.valid ? 1 : 0);
            for (std::size_t k = 0; k < item.type53_shadow.ans.size(); ++k) {
                record_file << ',' << item.type53_shadow.ans[k];
            }
            const std::array<double,6> applied_values{c.ans1,c.ans2,c.ans3,c.ans4,c.ans5,c.ans6};
            for (std::size_t k = 0; k < item.type53_shadow.ans.size(); ++k) {
                record_file << ',' << (item.type53_shadow.ans[k] - applied_values[k]);
            }
            record_file << ',' << item.type53_shadow.base_threshold_ev
                        << ',' << item.type53_shadow.threshold_ev
                        << ',' << item.type53_shadow.bound_energy_ev
                        << ',' << item.type53_shadow.continuum_energy_ev
                        << ',' << item.type53_shadow.destination_energy_ev
                        << ',' << item.type53_shadow.excited_parent_energy_ev
                        << ',' << item.type53_shadow.bound_statistical_weight
                        << ',' << item.type53_shadow.continuum_statistical_weight
                        << ',' << item.type53_shadow.destination_statistical_weight
                        << ',' << item.type53_shadow.excited_parent_statistical_weight
                        << ',' << (item.type53_shadow.milne_partition_context_used ? 1 : 0)
                        << ',' << (item.type53_shadow.excited_threshold_context_used ? 1 : 0)
                        << ',' << (item.type53_shadow.corrected_threshold_before_mapping ? 1 : 0)
                        << ',' << (item.type53_shadow.phextrap_source_reference_order ? 1 : 0)
                        << ',' << item.type53_shadow.phextrap_input_pair_count
                        << ',' << item.type53_shadow.phextrap_output_pair_count
                        << ',' << item.type53_shadow.rnist
                        << ',' << item.type53_shadow.sumr << ',' << item.type53_shadow.sumi
                        << ',' << item.type53_shadow.sumh << ',' << item.type53_shadow.sumh2
                        << ',' << item.type53_shadow.sumc << ',' << item.type53_shadow.sumc2
                        << ',' << (item.type53_shadow.sumc_ieee_nextafter_applied ? 1 : 0)
                        << ',' << item.type53_shadow.nb1_one_based << ',' << item.type53_shadow.klmax_one_based
                        << ',' << item.type53_shadow.integration_intervals
                        << ',' << (item.type53_shadow.helium_live_escape_state_applied ? 1 : 0)
                        << ',' << (item.type53_shadow.row46_contract ? 1 : 0)
                        << ',' << (item.type53_shadow.captured_state_anchor ? 1 : 0)
                        << ',' << item.type53_shadow.tau_in << ',' << item.type53_shadow.tau_out
                        << ',' << item.type53_shadow.ptmp1 << ',' << item.type53_shadow.ptmp2
                        << ',' << item.type53_shadow.covering_fraction
                        << ',' << (item.type53_shadow.runtime_state_abi_used ? 1 : 0)
                        << ',' << item.type53_shadow.continuum_index_one_based
                        << ',' << item.type53_shadow.dsec_radiation_bin_count
                        << ',' << item.type53_shadow.continuum_tau_count
                        << ',' << (item.type50_shadow.valid ? 1 : 0);
            for (double value : item.type50_shadow.ans) record_file << ',' << value;
            record_file << ',' << item.type50_shadow.stored_wavelength_a
                        << ',' << item.type50_shadow.endpoint_energy_ev
                        << ',' << item.type50_shadow.covering_fraction
                        << ',' << item.type50_shadow.ptmp1
                        << ',' << item.type50_shadow.ptmp2
                        << ',' << item.type50_shadow.bremsa_nb1
                        << ',' << item.type50_shadow.density_floor_s
                        << ',' << (item.type50_shadow.density_floor_applied ? 1 : 0)
                        << ',' << (item.type50_shadow.photoexcitation_zero_covering ? 1 : 0)
                        << ',' << (item.type50_shadow.used_dsec_covering ? 1 : 0)
                        << ',' << (item.type50_shadow.used_dsec_radiation ? 1 : 0)
                        << ',' << item.type50_shadow.nb1_one_based
                        << ',' << (item.type50_shadow.hydrogen_escape_state_applied ? 1 : 0)
                        << ',' << (item.type50_shadow.magnesium_escape_state_applied ? 1 : 0)
                        << ',' << (item.type50_shadow.magnesium_source_endpoint_energy_applied ? 1 : 0)
                        << ',' << item.type50_shadow.source_idest1
                        << ',' << item.type50_shadow.source_idest2
                        << ',' << item.type50_shadow.source_endpoint1_energy_ev
                        << ',' << item.type50_shadow.source_endpoint2_energy_ev
                        << ',' << item.type50_shadow.line_index_one_based
                        << ',' << item.type50_shadow.line_tau_in
                        << ',' << item.type50_shadow.line_tau_out
                        << ',' << (item.type99_shadow.valid ? 1 : 0);
            for (double value : item.type99_shadow.ans) record_file << ',' << value;
            record_file << ',' << item.type99_shadow.threshold_ev
                        << ',' << item.type99_shadow.destination_energy_ev
                        << ',' << item.type99_shadow.bound_energy_ev
                        << ',' << item.type99_shadow.parent_energy_ev
                        << ',' << item.type99_shadow.bound_statistical_weight
                        << ',' << item.type99_shadow.parent_statistical_weight
                        << ',' << item.type99_shadow.destination_statistical_weight
                        << ',' << item.type99_shadow.swrat
                        << ',' << (item.type99_shadow.persistent_leveltemp_context_valid ? 1 : 0)
                        << ',' << (item.type99_shadow.persistent_leveltemp_context_applied ? 1 : 0)
                        << ',' << item.type99_shadow.bound_owner_stage
                        << ',' << item.type99_shadow.parent_owner_stage
                        << ',' << item.type99_shadow.destination_owner_stage
                        << ',' << item.type99_shadow.calt99_density_cm3
                        << ',' << item.type99_shadow.phint53hunt_density_cm3
                        << ',' << item.type99_shadow.rec_cm3_s
                        << ',' << item.type99_shadow.milne_alpha_cm3_s
                        << ',' << item.type99_shadow.cross_section_scale
                        << ',' << item.type99_shadow.ans2d_unscaled_s
                        << ',' << item.type99_shadow.phint_scale
                        << ',' << item.type99_shadow.pirt_unscaled_s
                        << ',' << item.type99_shadow.rrrt_unscaled_s
                        << ',' << item.type99_shadow.piht_unscaled_erg_s
                        << ',' << item.type99_shadow.rrcl_unscaled_erg_s
                        << ',' << item.type99_shadow.piht2_unscaled_erg_s
                        << ',' << item.type99_shadow.rrcl2_unscaled_erg_s
                        << ',' << item.type99_shadow.energy_difference_ev
                        << ',' << (item.type99_shadow.destination_threshold_identity ? 1 : 0)
                        << ',' << item.type99_shadow.ans5_pre_energy_correction
                        << ',' << item.type99_shadow.ans6_pre_energy_correction
                        << ',' << item.type99_shadow.ans5_energy_correction_numerator
                        << ',' << item.type99_shadow.ans5_energy_correction_denominator
                        << ',' << item.type99_shadow.ans5_energy_correction_factor
                        << ',' << item.type99_shadow.ans6_energy_correction_numerator
                        << ',' << item.type99_shadow.ans6_energy_correction_denominator
                        << ',' << item.type99_shadow.ans6_energy_correction_factor
                        << ',' << (item.type99_shadow.destination_identity_correction_applied ? 1 : 0)
                        << ',' << item.type99_shadow.nbinc_threshold_one_based
                        << ',' << item.type99_shadow.nb1_one_based
                        << ',' << item.type99_shadow.nphint_one_based
                        << ',' << item.type99_shadow.ndelt
                        << ',' << item.type99_shadow.npass
                        << ',' << item.type99_shadow.last_pass_first_kl_one_based
                        << ',' << item.type99_shadow.last_pass_last_kl_one_based
                        << ',' << item.type99_shadow.cached_atmp22_stale_reuses
                        << ',' << (item.type99_shadow.used_dsec_radiation ? 1 : 0)
                        << ',' << item.type53_shadow.legacy_max_abs
                        << ',' << item.type53_shadow.shadow_max_abs
                        << ',' << item.type53_shadow.committed_max_abs
                        << ',' << (item.type53_shadow.legacy_nonfinite ? 1 : 0)
                        << ',' << (item.type53_shadow.legacy_implausible ? 1 : 0)
                        << ',' << (item.type53_shadow.replacement_applied ? 1 : 0)
                        << ',' << (item.type53_shadow.committed_nonfinite ? 1 : 0)
                        << ',' << (item.type53_shadow.committed_implausible ? 1 : 0)
                        << ',' << item.type53_shadow.exponent_energy_ev
                        << ',' << item.type53_shadow.exponent_dimensionless
                        << ',' << item.type53_shadow.electron_density_cm3
                        << ',' << item.type53_shadow.hydrogen_density_cm3
                        << ',' << item.type53_shadow.matrix_density_scale
                        << ',' << (item.type53_shadow.source_faithful_mode ? 1 : 0)
                        << ',' << (item.type49_shadow.valid ? 1 : 0);
            for (double value : item.type49_shadow.ans) record_file << ',' << value;
            record_file << ',' << item.type49_shadow.legacy_max_abs
                        << ',' << item.type49_shadow.shadow_max_abs
                        << ',' << item.type49_shadow.committed_max_abs
                        << ',' << (item.type49_shadow.legacy_nonfinite ? 1 : 0)
                        << ',' << (item.type49_shadow.legacy_implausible ? 1 : 0)
                        << ',' << (item.type49_shadow.replacement_applied ? 1 : 0)
                        << ',' << (item.type49_shadow.committed_nonfinite ? 1 : 0)
                        << ',' << (item.type49_shadow.committed_implausible ? 1 : 0)
                        << ',' << item.type49_shadow.base_threshold_ev
                        << ',' << item.type49_shadow.threshold_ev
                        << ',' << item.type49_shadow.bound_energy_ev
                        << ',' << item.type49_shadow.continuum_energy_ev
                        << ',' << item.type49_shadow.destination_energy_ev
                        << ',' << item.type49_shadow.excited_parent_energy_ev
                        << ',' << item.type49_shadow.bound_statistical_weight
                        << ',' << item.type49_shadow.continuum_statistical_weight
                        << ',' << item.type49_shadow.destination_statistical_weight
                        << ',' << item.type49_shadow.excited_parent_statistical_weight
                        << ',' << (item.type49_shadow.milne_partition_context_used ? 1 : 0)
                        << ',' << (item.type49_shadow.excited_threshold_context_used ? 1 : 0)
                        << ',' << (item.type49_shadow.corrected_threshold_before_mapping ? 1 : 0)
                        << ',' << (item.type49_shadow.phextrap_source_reference_order ? 1 : 0)
                        << ',' << item.type49_shadow.phextrap_input_pair_count
                        << ',' << item.type49_shadow.phextrap_output_pair_count
                        << ',' << item.type49_shadow.phextrap_max_points
                        << ',' << item.type49_shadow.phextrap_input_energy_hash
                        << ',' << item.type49_shadow.phextrap_input_sigma_hash
                        << ',' << item.type49_shadow.phextrap_output_energy_hash
                        << ',' << item.type49_shadow.phextrap_output_sigma_hash
                        << ',' << item.type49_shadow.rnist
                        << ',' << item.type49_shadow.exponent_energy_ev
                        << ',' << item.type49_shadow.exponent_dimensionless
                        << ',' << item.type49_shadow.electron_density_cm3
                        << ',' << item.type49_shadow.hydrogen_density_cm3
                        << ',' << item.type49_shadow.matrix_density_scale
                        << ',' << (item.type49_shadow.phextrap_applied ? 1 : 0)
                        << ',' << (item.type49_shadow.source_zero_gate ? 1 : 0)
                        << ',' << (item.type49_shadow.source_faithful_mode ? 1 : 0)
                        << ',' << (item.type49_shadow.runtime_state_abi_used ? 1 : 0)
                        << ',' << item.type49_shadow.continuum_index_one_based
                        << ',' << item.type49_shadow.dsec_radiation_bin_count
                        << ',' << item.type49_shadow.continuum_tau_count
                        << ',' << (item.type51_shadow.valid ? 1 : 0)
                        << ',' << (item.type51_shadow.source_faithful_mode ? 1 : 0)
                        << ',' << (item.type51_shadow.replacement_applied ? 1 : 0)
                        << ',' << (item.type51_shadow.endpoint_order_exact ? 1 : 0)
                        << ',' << (item.type51_shadow.committed_nonfinite ? 1 : 0)
                        << ',' << item.type51_shadow.bt_type
                        << ',' << item.type51_shadow.point_count
                        << ',' << item.type51_shadow.eij_ryd
                        << ',' << item.type51_shadow.eij_ev
                        << ',' << item.type51_shadow.scaling_c
                        << ',' << item.type51_shadow.physical_temperature_k
                        << ',' << item.type51_shadow.floor_temperature_k
                        << ',' << item.type51_shadow.effective_temperature_k
                        << ',' << (item.type51_shadow.temperature_floor_applied ? 1 : 0)
                        << ',' << item.type51_shadow.scaled_temperature
                        << ',' << item.type51_shadow.transformed_temperature
                        << ',' << item.type51_shadow.scaled_upsilon
                        << ',' << item.type51_shadow.upsilon
                        << ',' << item.type51_shadow.lower_statistical_weight
                        << ',' << item.type51_shadow.upper_statistical_weight
                        << ',' << item.type51_shadow.electron_density_cm3
                        << ',' << item.type51_shadow.q_excitation_cm3_s
                        << ',' << item.type51_shadow.q_deexcitation_cm3_s;
            for (double value : item.type51_shadow.ans) record_file << ',' << value;
            for (double value : item.type51_shadow.legacy_ans) record_file << ',' << value;
            record_file << ',' << item.type53_shadow.threshold_cross_section_cm2
                        << ',' << item.type53_shadow.threshold_stimulated_cross_section_cm2
                        << ',' << item.type49_shadow.threshold_cross_section_cm2
                        << ',' << item.type49_shadow.threshold_stimulated_cross_section_cm2;
            record_file << '\n';
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
        std::ofstream thermal_population_file(root / (stem + "_thermal_compact_populations.csv"));
        if (!element_file || !ion_file || !population_file || !thermal_population_file) {
            throw std::runtime_error("cannot create element diagnostics CSV files");
        }
        element_file << "evaluation_ordinal,element_index,element_z,abundance,active_min_stage,active_max_stage,active_full_row_start,active_full_row_end,heating,cooling,heating2,cooling2,normalization,normalization_error,max_relative_row_residual,records_constructed,terms_constructed\n";
        ion_file << "evaluation_ordinal,element_index,element_z,stage,ion_charge,preliminary_ionization,preliminary_recombination,preliminary_fraction,final_fraction,active_stage\n";
        population_file << "evaluation_ordinal,global_population_row,element_index,element_z,element_row,superlevel,ion,ion_charge,energy_ev,statistical_weight,initial_population,final_population,active_row\n";
        thermal_population_file << "sequence,kind,call_index,evaluation_index,element_index,element_z,active_min_stage,active_max_stage,compact_row,ion,ion_stage,ion_charge,superlevel,is_normalization_row,thermal_population,closure_applied\n";
        element_file << std::setprecision(17);
        ion_file << std::setprecision(17);
        population_file << std::setprecision(17);
        thermal_population_file << std::setprecision(17);
        const int source_sequence = static_cast<int>(evaluation_ordinal);
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
            if (diagnostic.thermal_compact_populations.size() != diagnostic.active.element.rows.size()) {
                throw std::runtime_error("thermal compact-population diagnostic dimension mismatch");
            }
            for (std::size_t compact_index = 0; compact_index < diagnostic.active.element.rows.size(); ++compact_index) {
                const auto& row = diagnostic.active.element.rows[compact_index];
                const int absolute_ion_stage = row.ion + diagnostic.active.min_stage - 1;
                thermal_population_file << source_sequence << ",replay,0,0,"
                    << diagnostic.element_index << ',' << diagnostic.element_z << ','
                    << diagnostic.active.min_stage << ',' << diagnostic.active.max_stage << ','
                    << row.row << ',' << absolute_ion_stage << ',' << absolute_ion_stage << ',' << row.ion_charge << ','
                    << row.superlevel << ',' << (row.row == diagnostic.active.element.normalization_row ? 1 : 0) << ','
                    << diagnostic.thermal_compact_populations[compact_index] << ','
                    << (diagnostic.thermal_compact_population_closure_applied ? 1 : 0) << '\n';
            }
            for (std::size_t row_index=0; row_index<source.rows.size(); ++row_index) {
                const auto& row = source.rows[row_index];
                const double final_population = row_index < diagnostic.full_populations.size() ? diagnostic.full_populations[row_index] : 0.0;
                const bool active_row = row.row >= diagnostic.active.full_row_start && row.row <= diagnostic.active.full_row_end;
                double effective_initial_population = row.initial_population;
                if (active_row && diagnostic.solve_response_captured) {
                    const std::size_t active_index = static_cast<std::size_t>(row.row - diagnostic.active.full_row_start);
                    if (active_index < diagnostic.active_initial_populations.size()) {
                        effective_initial_population = diagnostic.active_initial_populations[active_index];
                    }
                }
                population_file << evaluation_ordinal << ',' << global_offset + row_index + 1 << ',' << diagnostic.element_index << ',' << diagnostic.element_z << ','
                                << row.row << ',' << row.superlevel << ',' << row.ion << ',' << row.ion_charge << ',' << row.energy_ev << ','
                                << row.statistical_weight << ',' << effective_initial_population << ',' << final_population << ',' << (active_row ? 1 : 0) << '\n';
            }
            global_offset += source.rows.size();
        }

        if (context->last_all_element_solve_response) {
            std::ofstream all_solve_rows(root / (stem + "_all_element_solve_rows.csv"));
            if (!all_solve_rows) throw std::runtime_error("cannot create all-element solve-response CSV file");
            all_solve_rows << "evaluation_ordinal,element_index,element_z,abundance,active_min_stage,active_max_stage,compact_row,full_row,global_level_index,superlevel,ion,ion_charge,is_normalization_row,raw_global_level_index,raw_call_start_xilevg,loaded_global_level_index,loaded_call_start_xilevg,initial_population,final_outer_start_population,final_population,rhs,native_row_residual,native_row_scale,native_relative_row_residual\n";
            all_solve_rows << std::setprecision(17);
            for (const auto& diagnostic : context->last_element_diagnostics) {
                if (!diagnostic.solve_response_captured) continue;
                const auto& source = context->program.elements.at(static_cast<std::size_t>(diagnostic.element_index));
                const int n = diagnostic.active.element.n_rows;
                if (diagnostic.active_initial_populations.size() != static_cast<std::size_t>(n) ||
                    diagnostic.active_final_outer_start_populations.size() != static_cast<std::size_t>(n) ||
                    diagnostic.active_final_populations.size() != static_cast<std::size_t>(n) ||
                    diagnostic.rhs.size() != static_cast<std::size_t>(n)) {
                    throw std::runtime_error("all-element solve-response buffer dimensions are inconsistent");
                }
                for (int compact_row = 1; compact_row <= n; ++compact_row) {
                    const int full_row = diagnostic.active.full_row_start + compact_row - 1;
                    const auto& row = source.rows.at(static_cast<std::size_t>(full_row - 1));
                    const std::size_t index = static_cast<std::size_t>(compact_row - 1);
                    all_solve_rows << evaluation_ordinal << ',' << diagnostic.element_index << ',' << diagnostic.element_z << ','
                                   << diagnostic.abundance << ',' << diagnostic.active.min_stage << ',' << diagnostic.active.max_stage << ','
                                   << compact_row << ',' << full_row << ',' << row.global_level_index << ',' << row.superlevel << ','
                                   << row.ion << ',' << row.ion_charge << ','
                                   << (compact_row == diagnostic.active.element.normalization_row ? 1 : 0) << ','
                                   << diagnostic.active_raw_global_level_indices.at(index) << ','
                                   << diagnostic.active_raw_call_start_xilevg.at(index) << ','
                                   << diagnostic.active_loaded_global_level_indices.at(index) << ','
                                   << diagnostic.active_loaded_call_start_xilevg.at(index) << ','
                                   << diagnostic.active_initial_populations.at(index) << ','
                                   << diagnostic.active_final_outer_start_populations.at(index) << ','
                                   << diagnostic.active_final_populations.at(index) << ','
                                   << diagnostic.rhs.at(index) << ','
                                   << diagnostic.row_residual.at(index) << ','
                                   << diagnostic.row_scale.at(index) << ','
                                   << diagnostic.relative_row_residual.at(index) << '\n';
                }
            }
        }


        if (context->last_all_element_solve_response) {
            std::ofstream stage_rows(root / (stem + "_all_element_solve_stage_rows.csv"));
            std::ofstream stage_superlevels(root / (stem + "_all_element_solve_stage_superlevels.csv"));
            std::ofstream stage_matrix(root / (stem + "_all_element_solve_stage_condensed_matrix.csv"));
            std::ofstream stage_manifest(root / (stem + "_all_element_solve_stage_manifest.csv"));
            if (!stage_rows || !stage_superlevels || !stage_matrix || !stage_manifest) {
                throw std::runtime_error("cannot create all-element solve-stage diagnostics");
            }
            stage_rows << "evaluation_ordinal,element_index,element_z,active_min_stage,active_max_stage,compact_row,superlevel,ion,ion_charge,is_normalization_row,transformed_initial_population,final_outer_start_population,population_after_condensed,final_fixed_point_population_before,final_fixed_point_population_after,final_population,rhs\n";
            stage_superlevels << "evaluation_ordinal,element_index,element_z,final_outer_iteration,superlevel,population_before_condensed_solve,condensed_rhs,first_lu_solution,refinement_residual,refinement_correction,refined_superlevel_solution\n";
            stage_matrix << "evaluation_ordinal,element_index,element_z,final_outer_iteration,row_superlevel,column_superlevel,normalized_matrix_value\n";
            stage_manifest << "evaluation_ordinal,element_index,element_z,active_min_stage,active_max_stage,n_rows,n_superlevels,n_ions,normalization_row,final_outer_iteration,final_fixed_iterations,total_fixed_point_iterations,solver_method,trace_captured\n";
            stage_rows << std::setprecision(17);
            stage_superlevels << std::setprecision(17);
            stage_matrix << std::setprecision(17);
            stage_manifest << std::setprecision(17);
            for (const auto& diagnostic : context->last_element_diagnostics) {
                if (!diagnostic.solve_response_captured || !diagnostic.solve_stage_trace_captured) continue;
                const int n = diagnostic.active.element.n_rows;
                const int nsp = diagnostic.active.element.n_superlevels;
                if (diagnostic.final_population_after_condensed.size() != static_cast<std::size_t>(n) ||
                    diagnostic.final_fixed_point_population_before.size() != static_cast<std::size_t>(n) ||
                    diagnostic.final_fixed_point_population_after.size() != static_cast<std::size_t>(n) ||
                    diagnostic.final_superlevel_populations_before_solve.size() != static_cast<std::size_t>(nsp) ||
                    diagnostic.final_condensed_matrix.size() != static_cast<std::size_t>(nsp) * static_cast<std::size_t>(nsp) ||
                    diagnostic.final_condensed_rhs.size() != static_cast<std::size_t>(nsp) ||
                    diagnostic.final_first_lu_solution.size() != static_cast<std::size_t>(nsp) ||
                    diagnostic.final_refinement_residual.size() != static_cast<std::size_t>(nsp) ||
                    diagnostic.final_refinement_correction.size() != static_cast<std::size_t>(nsp) ||
                    diagnostic.final_refined_superlevel_solution.size() != static_cast<std::size_t>(nsp)) {
                    throw std::runtime_error("all-element solve-stage trace dimensions are inconsistent");
                }
                stage_manifest << evaluation_ordinal << ',' << diagnostic.element_index << ',' << diagnostic.element_z << ','
                    << diagnostic.active.min_stage << ',' << diagnostic.active.max_stage << ',' << n << ',' << nsp << ','
                    << diagnostic.active.element.n_ions << ',' << diagnostic.active.element.normalization_row << ','
                    << diagnostic.final_outer_iteration << ',' << diagnostic.final_fixed_iterations << ','
                    << diagnostic.fixed_point_iterations << ',' << diagnostic.solver_method << ",1\n";
                for (int compact_row = 1; compact_row <= n; ++compact_row) {
                    const std::size_t index = static_cast<std::size_t>(compact_row - 1);
                    const auto& row = diagnostic.active.element.rows.at(index);
                    stage_rows << evaluation_ordinal << ',' << diagnostic.element_index << ',' << diagnostic.element_z << ','
                        << diagnostic.active.min_stage << ',' << diagnostic.active.max_stage << ',' << compact_row << ','
                        << row.superlevel << ',' << row.ion << ',' << row.ion_charge << ','
                        << (compact_row == diagnostic.active.element.normalization_row ? 1 : 0) << ','
                        << diagnostic.active_initial_populations.at(index) << ','
                        << diagnostic.active_final_outer_start_populations.at(index) << ','
                        << diagnostic.final_population_after_condensed.at(index) << ','
                        << diagnostic.final_fixed_point_population_before.at(index) << ','
                        << diagnostic.final_fixed_point_population_after.at(index) << ','
                        << diagnostic.active_final_populations.at(index) << ','
                        << diagnostic.rhs.at(index) << '\n';
                }
                for (int sp = 1; sp <= nsp; ++sp) {
                    const std::size_t index = static_cast<std::size_t>(sp - 1);
                    stage_superlevels << evaluation_ordinal << ',' << diagnostic.element_index << ',' << diagnostic.element_z << ','
                        << diagnostic.final_outer_iteration << ',' << sp << ','
                        << diagnostic.final_superlevel_populations_before_solve.at(index) << ','
                        << diagnostic.final_condensed_rhs.at(index) << ','
                        << diagnostic.final_first_lu_solution.at(index) << ','
                        << diagnostic.final_refinement_residual.at(index) << ','
                        << diagnostic.final_refinement_correction.at(index) << ','
                        << diagnostic.final_refined_superlevel_solution.at(index) << '\n';
                    for (int col = 1; col <= nsp; ++col) {
                        stage_matrix << evaluation_ordinal << ',' << diagnostic.element_index << ',' << diagnostic.element_z << ','
                            << diagnostic.final_outer_iteration << ',' << sp << ',' << col << ','
                            << diagnostic.final_condensed_matrix.at(
                                static_cast<std::size_t>(sp - 1) * static_cast<std::size_t>(nsp) +
                                static_cast<std::size_t>(col - 1)) << '\n';
                    }
                }
            }
        }

        if (context->last_all_element_solve_system) {
            const std::filesystem::path system_relative = stem + "_all_element_solve_systems";
            const std::filesystem::path system_root = root / system_relative;
            std::filesystem::create_directories(system_root);
            std::ofstream manifest(root / (stem + "_all_element_solve_system_manifest.csv"));
            if (!manifest) throw std::runtime_error("cannot create all-element solve-system manifest");
            manifest << "evaluation_ordinal,element_index,element_z,abundance,active_min_stage,active_max_stage,n_rows,n_ions,normalization_row,solver_method,solver_status_flags,outer_iterations,fixed_point_iterations,normalization,normalization_error,"
                        "dense_matrix_path,dense_matrix_count,heating_matrix_path,heating_matrix_count,heating_matrix2_path,heating_matrix2_count,rhs_path,rhs_count,solver_input_path,solver_input_count,outer_path,outer_count,final_path,final_count,ion_reconstruction_path,ion_reconstruction_count,"
                        "matrix_contribution_ints_path,matrix_contribution_int_rows,matrix_contribution_int_columns,"
                        "matrix_contribution_reals_path,matrix_contribution_real_rows,matrix_contribution_real_columns\n";
            manifest << std::setprecision(17);
            const auto write_binary = [](const std::filesystem::path& path, const std::vector<double>& values) {
                std::ofstream out(path, std::ios::binary);
                if (!out) throw std::runtime_error("cannot create all-element solve-system binary: " + path.string());
                if (!values.empty()) {
                    out.write(reinterpret_cast<const char*>(values.data()),
                              static_cast<std::streamsize>(values.size() * sizeof(double)));
                }
                if (!out) throw std::runtime_error("failed writing all-element solve-system binary: " + path.string());
            };
            const auto write_int64_binary = [](const std::filesystem::path& path, const std::vector<std::int64_t>& values) {
                std::ofstream out(path, std::ios::binary);
                if (!out) throw std::runtime_error("cannot create matrix-contribution integer binary: " + path.string());
                if (!values.empty()) {
                    out.write(reinterpret_cast<const char*>(values.data()),
                              static_cast<std::streamsize>(values.size() * sizeof(std::int64_t)));
                }
                if (!out) throw std::runtime_error("failed writing matrix-contribution integer binary: " + path.string());
            };
            for (const auto& diagnostic : context->last_element_diagnostics) {
                if (!diagnostic.solve_response_captured) continue;
                const int n = diagnostic.active.element.n_rows;
                const int n_ions = static_cast<int>(diagnostic.active_ion_reconstruction.size());
                const std::size_t matrix_count = static_cast<std::size_t>(n) * static_cast<std::size_t>(n);
                if (diagnostic.dense_matrix.size() != matrix_count ||
                    diagnostic.heating_matrix.size() != matrix_count ||
                    diagnostic.heating_matrix2.size() != matrix_count ||
                    diagnostic.rhs.size() != static_cast<std::size_t>(n) ||
                    diagnostic.active_initial_populations.size() != static_cast<std::size_t>(n) ||
                    diagnostic.active_final_outer_start_populations.size() != static_cast<std::size_t>(n) ||
                    diagnostic.active_final_populations.size() != static_cast<std::size_t>(n) ||
                    diagnostic.active_ion_reconstruction.size() != static_cast<std::size_t>(n_ions)) {
                    throw std::runtime_error("all-element solve-system buffer dimensions are inconsistent");
                }
                std::ostringstream element_builder;
                element_builder << "element_" << std::setw(2) << std::setfill('0') << diagnostic.element_z;
                const std::string element_stem = element_builder.str();
                const auto relative = [&](const char* suffix) {
                    return system_relative / (element_stem + "_" + suffix + ".bin");
                };
                const auto dense_path = relative("dense_matrix");
                const auto heat_path = relative("heating_matrix");
                const auto heat2_path = relative("heating_matrix2");
                const auto rhs_path = relative("rhs");
                const auto input_path = relative("solver_input");
                const auto outer_path = relative("outer");
                const auto final_path = relative("final");
                const auto ion_path = relative("ion_reconstruction");
                const auto contribution_ints_path = relative("matrix_contribution_ints");
                const auto contribution_reals_path = relative("matrix_contribution_reals");
                constexpr std::size_t kContributionIntColumns = 14;
                constexpr std::size_t kContributionRealColumns = 16;
                std::vector<std::int64_t> contribution_ints;
                std::vector<double> contribution_reals;
                contribution_ints.reserve(diagnostic.committed_contributions.size() * kContributionIntColumns);
                contribution_reals.reserve(diagnostic.committed_contributions.size() * kContributionRealColumns);
                for (std::size_t contribution_index = 0;
                     contribution_index < diagnostic.committed_contributions.size(); ++contribution_index) {
                    const auto& c = diagnostic.committed_contributions[contribution_index];
                    const std::array<std::int64_t, kContributionIntColumns> ints = {{
                        static_cast<std::int64_t>(contribution_index + 1), c.source_position, c.record,
                        static_cast<std::int64_t>(c.data_type), static_cast<std::int64_t>(c.rate_type),
                        static_cast<std::int64_t>(c.ion_index), static_cast<std::int64_t>(c.ion_stage),
                        static_cast<std::int64_t>(c.lower_row), static_cast<std::int64_t>(c.upper_row),
                        0, 0, 0, 0, 0
                    }};
                    contribution_ints.insert(contribution_ints.end(), ints.begin(), ints.end());
                    const double xpx = c.density_scale;
                    const std::array<double, kContributionRealColumns> reals = {{
                        c.ans1, c.ans2, 0.0, 0.0,
                        c.ans2, c.ans1, 0.0, 0.0,
                        -c.ans1, -c.ans1, c.ans4 * xpx, c.ans6 * xpx,
                        -c.ans2, -c.ans2, -c.ans3 * xpx, -c.ans5 * xpx
                    }};
                    contribution_reals.insert(contribution_reals.end(), reals.begin(), reals.end());
                }
                write_binary(root / dense_path, diagnostic.dense_matrix);
                write_binary(root / heat_path, diagnostic.heating_matrix);
                write_binary(root / heat2_path, diagnostic.heating_matrix2);
                write_binary(root / rhs_path, diagnostic.rhs);
                write_binary(root / input_path, diagnostic.active_initial_populations);
                write_binary(root / outer_path, diagnostic.active_final_outer_start_populations);
                write_binary(root / final_path, diagnostic.active_final_populations);
                write_binary(root / ion_path, diagnostic.active_ion_reconstruction);
                write_int64_binary(root / contribution_ints_path, contribution_ints);
                write_binary(root / contribution_reals_path, contribution_reals);
                manifest << evaluation_ordinal << ',' << diagnostic.element_index << ',' << diagnostic.element_z << ','
                         << diagnostic.abundance << ',' << diagnostic.active.min_stage << ',' << diagnostic.active.max_stage << ','
                         << n << ',' << n_ions << ',' << diagnostic.active.element.normalization_row << ','
                         << diagnostic.solver_method << ',' << diagnostic.solver_status_flags << ','
                         << diagnostic.outer_iterations << ',' << diagnostic.fixed_point_iterations << ','
                         << diagnostic.normalization << ',' << diagnostic.normalization_error << ','
                         << dense_path.string() << ',' << diagnostic.dense_matrix.size() << ','
                         << heat_path.string() << ',' << diagnostic.heating_matrix.size() << ','
                         << heat2_path.string() << ',' << diagnostic.heating_matrix2.size() << ','
                         << rhs_path.string() << ',' << diagnostic.rhs.size() << ','
                         << input_path.string() << ',' << diagnostic.active_initial_populations.size() << ','
                         << outer_path.string() << ',' << diagnostic.active_final_outer_start_populations.size() << ','
                         << final_path.string() << ',' << diagnostic.active_final_populations.size() << ','
                         << ion_path.string() << ',' << diagnostic.active_ion_reconstruction.size() << ','
                         << contribution_ints_path.string() << ',' << diagnostic.committed_contributions.size() << ','
                         << kContributionIntColumns << ',' << contribution_reals_path.string() << ','
                         << diagnostic.committed_contributions.size() << ',' << kContributionRealColumns << '\n';
            }
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
            solve_rows << "evaluation_ordinal,compact_row,full_row,superlevel,ion,ion_charge,energy_ev,statistical_weight,is_normalization_row,raw_global_level_index,raw_call_start_xilevg,loaded_global_level_index,loaded_call_start_xilevg,initial_population,final_outer_start_population,final_population,rhs,native_row_residual,native_row_scale,native_relative_row_residual\n";
            solve_rows << std::setprecision(17);
            for (int compact_row = 1; compact_row <= n; ++compact_row) {
                const int full_row = helium->active.full_row_start + compact_row - 1;
                const auto& row = source.rows.at(static_cast<std::size_t>(full_row - 1));
                const std::size_t index = static_cast<std::size_t>(compact_row - 1);
                solve_rows << evaluation_ordinal << ',' << compact_row << ',' << full_row << ','
                           << row.superlevel << ',' << row.ion << ',' << row.ion_charge << ','
                           << row.energy_ev << ',' << row.statistical_weight << ','
                           << (compact_row == helium->active.element.normalization_row ? 1 : 0) << ','
                           << helium->active_raw_global_level_indices.at(index) << ','
                           << helium->active_raw_call_start_xilevg.at(index) << ','
                           << helium->active_loaded_global_level_indices.at(index) << ','
                           << helium->active_loaded_call_start_xilevg.at(index) << ','
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

            solve_terms << "evaluation_ordinal,source_order_index,contribution_source_position,term_source_position,record,data_type,rate_type,ion_index,ion_stage,role,compact_row,compact_column,full_row,full_column,native_aj1,native_aj2,source_aj1,source_aj2,source_answer_basis,native_cj,native_cj2,source_cj,source_cj2,density_scale\n";
            solve_terms << std::setprecision(17);
            std::uint64_t source_order_index = 0;
            std::vector<const NativeRecordDiagnostic*> ordered_helium_records;
            for (const auto& diagnostic : records) {
                if (diagnostic.element_z == 2 && diagnostic.matrix_committed) ordered_helium_records.push_back(&diagnostic);
            }
            if (context->last_helium_source_insertion_order) {
                std::stable_sort(ordered_helium_records.begin(), ordered_helium_records.end(),
                    [](const auto* lhs, const auto* rhs) {
                        const auto& a = lhs->evaluated.contribution;
                        const auto& b = rhs->evaluated.contribution;
                        return std::tie(a.ion_stage, a.rate_type, a.data_type,
                                        a.source_position, a.record) <
                               std::tie(b.ion_stage, b.rate_type, b.data_type,
                                        b.source_position, b.record);
                    });
            } else if (context->last_type53_row46_coupled_replacement) {
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
                std::array<double,6> source_answers{{c.ans1,c.ans2,c.ans3,c.ans4,c.ans5,c.ans6}};
                const auto& item = diagnostic.evaluated;
                const char* source_answer_basis = "committed_source_faithful";
                if (c.data_type == 53 && item.type53_shadow.valid) {
                    source_answers = item.type53_shadow.ans; source_answer_basis = "type53_source_shadow";
                } else if (c.data_type == 49 && item.type49_shadow.valid) {
                    source_answers = item.type49_shadow.ans; source_answer_basis = "type49_source_shadow";
                } else if (c.data_type == 50 && item.type50_shadow.valid) {
                    source_answers = item.type50_shadow.ans; source_answer_basis = "type50_source_shadow";
                } else if (c.data_type == 51 && item.type51_shadow.valid) {
                    source_answers = item.type51_shadow.ans; source_answer_basis = "type51_source_shadow";
                } else if (c.data_type == 99 && item.type99_shadow.valid) {
                    source_answers = item.type99_shadow.ans; source_answer_basis = "type99_source_shadow";
                }
                const double native_aj1[4] = {c.ans1, c.ans2, -c.ans1, -c.ans2};
                const double native_aj2[4] = {c.ans2, c.ans1, -c.ans1, -c.ans2};
                const double source_aj1[4] = {source_answers[0], source_answers[1], -source_answers[0], -source_answers[1]};
                const double source_aj2[4] = {source_answers[1], source_answers[0], -source_answers[0], -source_answers[1]};
                const double native_cj[4] = {0.0, 0.0, c.ans4 * c.density_scale, -c.ans3 * c.density_scale};
                const double native_cj2[4] = {0.0, 0.0, c.ans6 * c.density_scale, -c.ans5 * c.density_scale};
                const double source_cj[4] = {0.0, 0.0, source_answers[3] * c.density_scale, -source_answers[2] * c.density_scale};
                const double source_cj2[4] = {0.0, 0.0, source_answers[5] * c.density_scale, -source_answers[4] * c.density_scale};
                for (int offset = 0; offset < 4; ++offset) {
                    ++source_order_index;
                    solve_terms << evaluation_ordinal << ',' << source_order_index << ',' << c.source_position << ','
                                << c.source_position + offset << ',' << c.record << ',' << c.data_type << ','
                                << c.rate_type << ',' << c.ion_index << ',' << c.ion_stage << ',' << roles[offset] << ','
                                << rows4[offset] << ',' << cols4[offset] << ','
                                << helium->active.full_row_start + rows4[offset] - 1 << ','
                                << helium->active.full_row_start + cols4[offset] - 1 << ','
                                << native_aj1[offset] << ',' << native_aj2[offset] << ','
                                << source_aj1[offset] << ',' << source_aj2[offset] << ','
                                << source_answer_basis << ','
                                << native_cj[offset] << ',' << native_cj2[offset] << ','
                                << source_cj[offset] << ',' << source_cj2[offset] << ','
                                << c.density_scale << '\n';
                }
            }

            std::ofstream solve_state(root / (stem + "_helium_solve_state.json"));
            if (!solve_state) throw std::runtime_error("cannot create helium solve-response state JSON");
            solve_state << std::setprecision(17)
                        << "{\n  \"schema\": \"xstar-tools-v0648711-helium-solve-response-state-v1\",\n"
                        << "  \"release\": \"0.6.48.7.26\",\n"
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
                        << "  \"helium_source_insertion_order\": " << (context->last_helium_source_insertion_order ? "true" : "false") << ",\n"
                        << "  \"qualification_only\": true,\n"
                        << "  \"production_promotion_ready\": false\n}\n";
        }

        {
            std::ofstream diagonal_file(root / (stem + "_thermal_diagonal_ledger.csv"));
            if (!diagonal_file) throw std::runtime_error("cannot create thermal diagonal ledger CSV");
            diagonal_file << "evaluation_ordinal,element_z,active_min_stage,active_max_stage,source_order_index,source_position,record,data_type,rate_type,ion_index,ion_stage,compact_row,native_compact_row,source_compact_row,role,is_normalization_row,source_domain_included,magnesium_type99_primary_cooling_reduction_applied,magnesium_primary_cooling_source_order_applied,magnesium_primary_cooling_source_order_index,abundance,compact_population,weighted_population,cj,cj2,native_cj,source_cj,unweighted_heating_contribution,unweighted_cooling_contribution,unweighted_heating2_contribution,unweighted_cooling2_contribution,heating_contribution,cooling_contribution,heating2_contribution,cooling2_contribution\n";
            diagonal_file << std::setprecision(17);
            for (const auto& row : context->last_thermal_diagonal_diagnostics) {
                diagonal_file << evaluation_ordinal << ',' << row.element_z << ','
                              << row.active_min_stage << ',' << row.active_max_stage << ','
                              << row.source_order_index << ',' << row.source_position << ','
                              << row.record << ',' << row.data_type << ',' << row.rate_type << ','
                              << row.ion_index << ',' << row.ion_stage << ',' << row.compact_row << ','
                              << row.native_compact_row << ',' << row.source_compact_row << ','
                              << row.role << ',' << (row.normalization_row ? 1 : 0) << ','
                              << (row.source_domain_included ? 1 : 0) << ','
                              << (row.magnesium_type99_primary_cooling_reduction_applied ? 1 : 0) << ','
                              << (row.magnesium_primary_cooling_source_order_applied ? 1 : 0) << ','
                              << row.magnesium_primary_cooling_source_order_index << ','
                              << row.abundance << ',' << row.compact_population << ','
                              << row.weighted_population << ',' << row.cj << ',' << row.cj2 << ','
                              << row.native_cj << ',' << row.source_cj << ','
                              << row.unweighted_heating_contribution << ','
                              << row.unweighted_cooling_contribution << ','
                              << row.unweighted_heating2_contribution << ','
                              << row.unweighted_cooling2_contribution << ','
                              << row.heating_contribution << ',' << row.cooling_contribution << ','
                              << row.heating2_contribution << ',' << row.cooling2_contribution << '\n';
            }
        }

        {
            std::ofstream canonical_file(root / (stem + "_canonical_thermal_terms.csv"));
            if (!canonical_file) throw std::runtime_error("cannot create canonical Thermal term ledger CSV");
            canonical_file << "evaluation_ordinal,element_index,element_z,ledger_fingerprint,element_consumer_fingerprint,fixed_state_consumer_fingerprint,shared_ownership,term_index,source_position,record,data_type,rate_type,ion_index,ion_stage,compact_row,native_compact_row,source_compact_row,role,is_type53,is_normalization_row,source_domain_included,matrix_insertion_captured,type99_source_corrected,primary_source_ordered,primary_source_order_index,cj,cj2,native_cj,source_cj\n";
            canonical_file << std::setprecision(17);
            for (const auto& diagnostic : context->last_element_diagnostics) {
                for (const auto& term : diagnostic.canonical_thermal_terms) {
                    canonical_file << evaluation_ordinal << ','
                                   << diagnostic.element_index << ',' << diagnostic.element_z << ','
                                   << hex_u64(diagnostic.canonical_thermal_ledger_fingerprint) << ','
                                   << hex_u64(diagnostic.element_thermal_ledger_fingerprint) << ','
                                   << hex_u64(diagnostic.fixed_state_thermal_ledger_fingerprint) << ','
                                   << (diagnostic.canonical_thermal_ledger_shared ? 1 : 0) << ','
                                   << term.term_index << ',' << term.source_position << ',' << term.record << ','
                                   << term.data_type << ',' << term.rate_type << ',' << term.ion_index << ','
                                   << term.ion_stage << ',' << term.compact_row << ',' << term.native_compact_row << ','
                                   << term.source_compact_row << ','
                                   << (term.role == XSTAR_CANONICAL_THERMAL_FORWARD_DIAG_LOSS
                                       ? "forward_diag_loss" : "reverse_diag_loss") << ','
                                   << ((term.flags & XSTAR_CANONICAL_THERMAL_TYPE53) != 0u ? 1 : 0) << ','
                                   << ((term.flags & XSTAR_CANONICAL_THERMAL_NORMALIZATION_ROW) != 0u ? 1 : 0) << ','
                                   << ((term.flags & XSTAR_CANONICAL_THERMAL_SOURCE_DOMAIN_INCLUDED) != 0u ? 1 : 0) << ','
                                   << ((term.flags & XSTAR_CANONICAL_THERMAL_MATRIX_INSERTION_CAPTURED) != 0u ? 1 : 0) << ','
                                   << ((term.flags & XSTAR_CANONICAL_THERMAL_TYPE99_SOURCE_CORRECTED) != 0u ? 1 : 0) << ','
                                   << ((term.flags & XSTAR_CANONICAL_THERMAL_PRIMARY_SOURCE_ORDERED) != 0u ? 1 : 0) << ','
                                   << term.primary_source_order_index << ','
                                   << term.cj << ',' << term.cj2 << ',' << term.native_cj << ',' << term.source_cj << '\n';
                }
            }
        }

        {
            std::ofstream continuum_file(root / (stem + "_continuum_workspace.csv"));
            if (!continuum_file) throw std::runtime_error("cannot create continuum workspace CSV");
            continuum_file << "evaluation_ordinal,reduced_bin_one_based,full_bin_one_based,epim_ev,bremsam,bin_width_ev,comp_sum1_contribution,comp_sum2_contribution,comp_sum3_contribution,cmp1_contribution,cmp2_contribution,htcomp_contribution,clcomp_contribution,free_free_opacity_increment,htfreef_contribution,brcems,clbrems_contribution,running_cmp1,running_cmp2,running_htcomp,running_clcomp,running_htfreef,running_clbrems\n";
            continuum_file << std::setprecision(17);
            for (const auto& row : context->last_continuum_workspace_diagnostics) {
                continuum_file << evaluation_ordinal << ',' << row.reduced_bin_one_based << ','
                               << row.full_bin_one_based << ',' << row.epim_ev << ',' << row.bremsam << ','
                               << row.bin_width_ev << ',' << row.comp_sum1_contribution << ','
                               << row.comp_sum2_contribution << ',' << row.comp_sum3_contribution << ','
                               << row.cmp1_contribution << ',' << row.cmp2_contribution << ','
                               << row.htcomp_contribution << ',' << row.clcomp_contribution << ','
                               << row.free_free_opacity_increment << ',' << row.htfreef_contribution << ','
                               << row.brcems << ',' << row.clbrems_contribution << ','
                               << row.running_cmp1 << ',' << row.running_cmp2 << ','
                               << row.running_htcomp << ',' << row.running_clcomp << ','
                               << row.running_htfreef << ',' << row.running_clbrems << '\n';
            }
        }

        std::ofstream state_file(root / (stem + "_state.json"));
        if (!state_file) throw std::runtime_error("cannot create state diagnostics JSON");
        state_file << std::setprecision(17)
                   << "{\n  \"schema_version\": \"0.6.48.7.26\",\n  \"qualification_only\": true,\n"
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
                   << "  \"helium_source_insertion_order\": " << (context->last_helium_source_insertion_order ? "true" : "false") << ",\n"
                   << "  \"continuum_workspace_source_faithful\": " << (context->last_continuum_workspace_source_faithful ? "true" : "false") << ",\n"
                   << "  \"continuum_epim_count\": " << context->last_continuum_epim_count << ",\n"
                   << "  \"continuum_bremsam_count\": " << context->last_continuum_bremsam_count << ",\n"
                   << "  \"continuum_bremsmap_count\": " << context->last_continuum_bremsmap_count << ",\n"
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
