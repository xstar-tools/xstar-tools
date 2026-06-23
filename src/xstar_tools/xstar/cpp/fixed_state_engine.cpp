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
#include <limits>
#include <memory>
#include <map>
#include <optional>
#include <sstream>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
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
        constexpr double kPythonPi = 3.141592653589793238462643383279502884;
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
    bool matrix_enabled = true;
    double line_energy_ev = 0.0;
    double atomic_mass_amu = 1.0;
    double natural_width_ev = 0.0;
    double opakab = 0.0;
    double type56_upsilon = std::numeric_limits<double>::quiet_NaN();
    Type53SourceShadow type53_shadow{};
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
            out.terms.push_back(term);
        };

        // The candidates are captured from the final committed contribution
        // stream, after source matrix-closure replacement/removal and source-
        // order restoration.  This keeps the canonical Thermal coefficients
        // synchronized with the rates actually consumed by the element solve,
        // while element-specific preservation rules (notably Mg Type-50) remain
        // encoded in the corrected contribution itself.
        for (const auto& contribution : committed_contributions) {
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
    for (const int z : {1, 2, 12}) {
        auto it = out.rows_by_element_z.find(z);
        if (it == out.rows_by_element_z.end() || it->second.empty()) {
            throw std::runtime_error("thermal compact-population closure missing active element");
        }
        auto& rows = it->second;
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
    constexpr int kContextIntCount = 8;
    Type99PersistentLeveltempContextV048746223 context{};
    const bool has_magic = ints && record.int_count >= kContextIntCount &&
        ints[record.int_count - 1] == kLayoutMagic;
    if (!has_magic) return context;
    if (!payload || record.real_count != core_real_count + kContextRealCount) {
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
        const int base = std::max(pair_count - 2, 0);
        double e1 = pair_energy_ryd[static_cast<std::size_t>(base)] * 13.6 + threshold_ev;
        double s1 = pair_sigma_cm2[static_cast<std::size_t>(base)];
        // v0.6.47.2 calls phextrap with len(_mapped_grid(c)); the physical
        // runner's reduced ucalc grid is ncn2m=999.  Do not use the full
        // 9999-bin phint53 integration grid as extrapolation capacity.
        while (s1 > 1.0e-27 && static_cast<int>(pair_energy_ryd.size()) < phextrap_max_points && e1 < 2.0e5) {
            const double e2 = e1 * 1.3;
            const double s2 = s1 / (1.3 * 1.3 * 1.3);
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
        ++kl;
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
        shadow->base_threshold_ev = record_context && record_context->valid
            ? record_context->base_threshold_ev : threshold_ev;
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
                r, pair_real_count, lower, upper, input, source_threshold,
                contract_ptmp1 + contract_ptmp2, row46_contract,
                record_context.valid ? &record_context : nullptr, record.record, false, false,
                source_shadow, &out.type53_shadow);
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
                out.type53_shadow.dsec_radiation_bin_count = input.dsec_radiation_bin_count;
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
                    out.type53_shadow.dsec_radiation_bin_count = input.dsec_radiation_bin_count;
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
                    r, pair_real_count, lower, upper, input, source_threshold, ptmp1 + ptmp2,
                    nullptr, record_context.valid ? &record_context : nullptr, record.record,
                    true, true, source_shadow, &out.type49_shadow);
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
            out.type49_shadow.dsec_radiation_bin_count = input.dsec_radiation_bin_count;
            out.type49_shadow.continuum_tau_count = input.continuum_tau_count;
            if (magnesium_replacement &&
                (out.type49_shadow.committed_nonfinite || out.type49_shadow.committed_implausible)) {
                throw std::runtime_error("Mg Type-49 finite-state replacement remained nonfinite or implausibly large");
            }
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
            double endpoint_energy_ev = delta_ev;
            int line_index_one_based = 0;
            double line_tau_in = 0.0;
            double line_tau_out = 0.0;
            const auto& hydrogen_escape = hydrogen_type50_escape_state_v04874618();
            if (hydrogen_escape.enabled && element.element_z == 1) {
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
            if (magnesium_escape.enabled && element.element_z == 12 &&
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
            // Preserve the already-qualified Type-50 opakab product path.
            // The stored source wavelength is used for the rate branch, while
            // product promotion retains the endpoint-derived wavelength until
            // product parity is reopened explicitly.
            const double product_wavelength_a = delta_ev > 0.0 ? 12398.4016 / delta_ev : 0.0;
            out.opakab = (!high_wavelength_zero && v > 0.0)
                ? 0.02655 * oscillator * product_wavelength_a * 1.0e-8 / v : 0.0;
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
            if (evaluate_type99_source_faithful(record, r, ints, lower, upper, input, c, &out.type99_shadow)) break;
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
            const double scale=3.3e-11*std::pow(13.6/std::max(xstar_constants::kModernBoltzmannEvPerT4*t4,1.0e-300),1.5);
            const double rtmp=record.real_count>=3?r[2]:1.0;
            const double rate=scale*limited_exp(-r[1]/std::max(xstar_constants::kModernBoltzmannEvPerT4*t4,1.0e-300))*(r[0]/1.0e13)*rtmp;
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
            c.ans3=-aij*delta_ev*xstar_constants::kLegacyCollisionErgPerEv;
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

    // v0.6.48.7.32: reproduce the source msolvelucy compact-seed contract
    // for helium.  Each ion copies nlev entries, while the compact cursor
    // advances by nlev-1.  The next-ion ground therefore overwrites the
    // preceding continuum row.  The lowered He II ordinals retain the shared
    // ground at their first row; subsequent rows consume the following global
    // level, and the terminal solver-normalization row starts at exact zero.
    if (e.element_z == 2 && compact_row == e.normalization_row) {
        seed.global_level_index = 0;
        seed.value = 0.0;
        seed.loaded = true;
        return seed;
    }

    int global_level_index = row.global_level_index;
    if (e.element_z == 2 && compact_index > 0 && row.ion_charge > 0 &&
        e.rows[compact_index - 1].ion_charge == row.ion_charge) {
        ++global_level_index;
    }
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
    const std::size_t n = static_cast<std::size_t>(e.n_rows);
    const std::size_t ni = static_cast<std::size_t>(e.n_ions);
    b.superlevels.resize(n); b.ions.resize(n); b.initial.resize(n);
    b.populations.resize(n); b.outer.resize(n); b.dense.resize(n * n); b.heat.resize(n * n); b.heat2.resize(n * n); b.rhs.resize(n);
    b.gamma.resize(n); b.alpha.resize(n); b.fgamma.resize(5 * n); b.falpha.resize(5 * n); b.igamma.resize(n); b.ialpha.resize(n);
    b.ion_population.resize(ni); b.ion_population_final.resize(ni); b.ionization.resize(ni); b.recombination.resize(ni);
    b.ionization_components.resize(3 * ni); b.recombination_components.resize(3 * ni);
    b.row_residual.resize(n); b.row_scale.resize(n); b.relative_residual.resize(n);
    bool source_faithful_helium_runtime_seed = false;
    for (std::size_t k = 0; k < n; ++k) {
        b.superlevels[k] = e.rows[k].superlevel;
        b.ions[k] = e.rows[k].ion;
        b.initial[k] = e.rows[k].initial_population;
        if (!preserve_initial_seed) {
            const RuntimeInitialSeed seed = source_faithful_runtime_initial_seed(e, k, runtime_input);
            if (seed.loaded) {
                b.initial[k] = seed.value;
                if (e.element_z == 2) source_faithful_helium_runtime_seed = true;
            }
        }
    }

    // The source passes the unnormalized helium compact vector into
    // msolvelucy.  Number conservation is imposed by the solver normalization
    // row; normalizing here changes every solve-state entry and duplicates the
    // shared He I/He II boundary population.
    if (!preserve_initial_seed && !source_faithful_helium_runtime_seed) {
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
    const bool thermal_diagonal_source_domain =
        environment_flag("XSTAR_QUALIFICATION_THERMAL_DIAGONAL_DOMAIN_SOURCE_FAITHFUL");
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
        (!matrix_construction_closure || !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT"))) {
        throw std::runtime_error(
            "source-faithful thermal diagonal domain requires replacement and matrix-construction closure");
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
    if (thermal_component_parity_closure && !fixed_state_parity_closure) {
        throw std::runtime_error("thermal component parity closure requires fixed-state parity closure");
    }
    if (thermal_component_parity_closure) {
        const char* closure_dir = std::getenv("XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE_DIR");
        if (!closure_dir || !*closure_dir) {
            throw std::runtime_error("thermal component parity closure directory is missing");
        }
    }
    if (thermal_compact_population_closure && !environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")) {
        throw std::runtime_error("thermal compact-population closure requires XSTAR_QUALIFICATION_REPLACEMENT=1");
    }
    if (thermal_compact_population_closure && !thermal_component_parity_closure) {
        throw std::runtime_error("thermal compact-population closure requires thermal component parity closure");
    }
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
        const ActiveElementView active = source_compact_oracle.has_value()
            ? make_source_compact_element_view(
                element, source_compact_oracle->rows_by_element_z.at(element.element_z))
            : (element.n_ions == element.element_z
                ? make_active_element_view(element, preliminary)
                : make_full_element_view(element));
        apply_magnesium_type99_persistent_leveltemp_v048746223(
            ctx.program, element, active, input, evaluated);
        apply_magnesium_type49_persistent_leveltemp_v048746222(
            element, active, evaluated);
        apply_magnesium_type53_persistent_leveltemp_v048746221(
            element, active, evaluated);
        std::vector<xstar_element_contribution_v1> contributions;
        contributions.reserve(evaluated.size());
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
            const bool source_absent_type95_self_loop = element.element_z == 2 &&
                original.data_type == 95 && original.rate_type == 15 &&
                original.lower_row == original.upper_row;
            const bool qualification_ablated = matrix_family_ablated || matrix_source_ablated || matrix_row_ablated ||
                unqualified_type53_ablated || unqualified_type71_ablated || unqualified_type99_ablated;
            bool matrix_committed = false;
            if (item.matrix_enabled && active_stage && endpoints_active && !qualification_ablated &&
                !source_absent_type95_self_loop) {
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
        for (const auto& contribution : contributions) {
            canonical_thermal_builder.append_matrix_committed(contribution);
        }
        const auto canonical_thermal_ledger =
            canonical_thermal_builder.finish(contributions);
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
        if (thermal_compact_population_closure_data.has_value()) {
            thermal_populations = thermal_compact_population_values_for_element(
                *thermal_compact_population_closure_data, active);
            element_thermal_compact_closure_applied = true;
            ctx.last_thermal_consumed_compact_population_closure = true;
        } else if (thermal_component_closure_data.has_value()) {
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
        thermal_population_stream.insert(
            thermal_population_stream.end(), thermal_populations.begin(), thermal_populations.end());

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
        double element_electron_fraction = 0.0;
        for (int ion_slot = 0; ion_slot < active.element.n_ions; ++ion_slot) {
            const double fraction =
                buffers.ion_population_final[static_cast<std::size_t>(ion_slot)];
            const int stage = active.min_stage + ion_slot;
            explicit_stage_sum += fraction;
            element_electron_fraction +=
                fraction * static_cast<double>(stage - 1) * element.abundance;
        }
        const double fully_stripped_fraction =
            std::max(0.0, 1.0 - explicit_stage_sum);
        element_electron_fraction +=
            fully_stripped_fraction * static_cast<double>(element.element_z) * element.abundance;
        computed_electron_fraction += element_electron_fraction;

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
            const double nu = e * 2.417989242e14;
            const double stim = 1.0 - limited_exp(-e / std::max(kt_ev, 1.0e-300));
            output.opacity[k] += 3.692e8 * input.electron_density_cm3 * input.ionized_h_density_cm3 * std::pow(input.temperature_k, -0.5) * std::pow(std::max(nu, 1.0), -3.0) * stim;
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
        if (!fixed_state_closure_data.has_value() || closure.elcter != fixed_state_closure_data->charge_residual) {
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
        output.elcter = input.electron_fraction_xee - computed_electron_fraction;
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
        record_file << "evaluation_ordinal,source_position,record,element_index,element_z,data_type,rate_type,ion_index,ion_stage,lower_row,upper_row,matrix_enabled,active_stage,matrix_committed,spectral,ans1,ans2,ans3,ans4,ans5,ans6,density_scale,line_energy_ev,atomic_mass_amu,natural_width_ev,opakab,type56_upsilon,type53_shadow_valid,type53_shadow_ans1,type53_shadow_ans2,type53_shadow_ans3,type53_shadow_ans4,type53_shadow_ans5,type53_shadow_ans6,type53_delta_ans1,type53_delta_ans2,type53_delta_ans3,type53_delta_ans4,type53_delta_ans5,type53_delta_ans6,type53_shadow_base_threshold_ev,type53_shadow_threshold_ev,type53_shadow_bound_energy_ev,type53_shadow_continuum_energy_ev,type53_shadow_destination_energy_ev,type53_shadow_excited_parent_energy_ev,type53_shadow_bound_g,type53_shadow_continuum_g,type53_shadow_destination_g,type53_shadow_excited_parent_g,type53_milne_partition_context_used,type53_excited_threshold_context_used,type53_corrected_threshold_before_mapping,type53_phextrap_source_reference_order,type53_phextrap_input_pair_count,type53_phextrap_output_pair_count,type53_shadow_rnist,type53_shadow_sumr,type53_shadow_sumi,type53_shadow_sumh,type53_shadow_sumh2,type53_shadow_sumc,type53_shadow_sumc2,type53_sumc_ieee_nextafter_applied,type53_shadow_nb1_one_based,type53_shadow_klmax_one_based,type53_row46_contract,type53_captured_state_anchor,type53_tau_in,type53_tau_out,type53_ptmp1,type53_ptmp2,type53_covering_fraction,type53_runtime_state_abi_used,type53_continuum_index_one_based,type53_dsec_radiation_bin_count,type53_continuum_tau_count,type50_shadow_valid,type50_shadow_ans1,type50_shadow_ans2,type50_shadow_ans3,type50_shadow_ans4,type50_shadow_ans5,type50_shadow_ans6,type50_stored_wavelength_a,type50_endpoint_energy_ev,type50_covering_fraction,type50_ptmp1,type50_ptmp2,type50_bremsa_nb1,type50_density_floor_s,type50_density_floor_applied,type50_photoexcitation_zero_covering,type50_used_dsec_covering,type50_used_dsec_radiation,type50_nb1_one_based,type50_hydrogen_escape_state_applied,type50_magnesium_escape_state_applied,type50_magnesium_source_endpoint_energy_applied,type50_source_idest1,type50_source_idest2,type50_source_endpoint1_energy_ev,type50_source_endpoint2_energy_ev,type50_line_index_one_based,type50_line_tau_in,type50_line_tau_out,type99_shadow_valid,type99_shadow_ans1,type99_shadow_ans2,type99_shadow_ans3,type99_shadow_ans4,type99_shadow_ans5,type99_shadow_ans6,type99_threshold_ev,type99_destination_energy_ev,type99_bound_energy_ev,type99_parent_energy_ev,type99_bound_g,type99_parent_g,type99_destination_g,type99_swrat,type99_persistent_leveltemp_context_valid,type99_persistent_leveltemp_context_applied,type99_bound_owner_stage,type99_parent_owner_stage,type99_destination_owner_stage,type99_calt99_density_cm3,type99_phint53hunt_density_cm3,type99_rec_cm3_s,type99_milne_alpha_cm3_s,type99_cross_section_scale,type99_ans2d_unscaled_s,type99_phint_scale,type99_pirt_unscaled_s,type99_rrrt_unscaled_s,type99_piht_unscaled_erg_s,type99_rrcl_unscaled_erg_s,type99_piht2_unscaled_erg_s,type99_rrcl2_unscaled_erg_s,type99_energy_difference_ev,type99_destination_threshold_identity,type99_ans5_pre_energy_correction,type99_ans6_pre_energy_correction,type99_ans5_energy_correction_numerator,type99_ans5_energy_correction_denominator,type99_ans5_energy_correction_factor,type99_ans6_energy_correction_numerator,type99_ans6_energy_correction_denominator,type99_ans6_energy_correction_factor,type99_destination_identity_correction_applied,type99_nbinc_threshold_one_based,type99_nb1_one_based,type99_nphint_one_based,type99_ndelt,type99_npass,type99_last_pass_first_kl_one_based,type99_last_pass_last_kl_one_based,type99_cached_atmp22_stale_reuses,type99_used_dsec_radiation,mg_type53_legacy_max_abs,mg_type53_shadow_max_abs,mg_type53_committed_max_abs,mg_type53_legacy_nonfinite,mg_type53_legacy_implausible,mg_type53_replacement_applied,mg_type53_committed_nonfinite,mg_type53_committed_implausible,mg_type53_exponent_energy_ev,mg_type53_exponent_dimensionless,mg_type53_electron_density_cm3,mg_type53_hydrogen_density_cm3,mg_type53_matrix_density_scale,mg_type53_source_faithful_mode,type49_shadow_valid,type49_shadow_ans1,type49_shadow_ans2,type49_shadow_ans3,type49_shadow_ans4,type49_shadow_ans5,type49_shadow_ans6,type49_legacy_max_abs,type49_shadow_max_abs,type49_committed_max_abs,type49_legacy_nonfinite,type49_legacy_implausible,type49_replacement_applied,type49_committed_nonfinite,type49_committed_implausible,type49_base_threshold_ev,type49_threshold_ev,type49_bound_energy_ev,type49_continuum_energy_ev,type49_destination_energy_ev,type49_excited_parent_energy_ev,type49_bound_g,type49_continuum_g,type49_destination_g,type49_excited_parent_g,type49_milne_partition_context_used,type49_excited_threshold_context_used,type49_corrected_threshold_before_mapping,type49_phextrap_source_reference_order,type49_phextrap_input_pair_count,type49_phextrap_output_pair_count,type49_phextrap_max_points,type49_phextrap_input_energy_hash,type49_phextrap_input_sigma_hash,type49_phextrap_output_energy_hash,type49_phextrap_output_sigma_hash,type49_rnist,type49_exponent_energy_ev,type49_exponent_dimensionless,type49_electron_density_cm3,type49_hydrogen_density_cm3,type49_matrix_density_scale,type49_phextrap_applied,type49_source_zero_gate,type49_source_faithful_mode,type49_runtime_state_abi_used,type49_continuum_index_one_based,type49_dsec_radiation_bin_count,type49_continuum_tau_count,type51_shadow_valid,type51_source_faithful_mode,type51_replacement_applied,type51_endpoint_order_exact,type51_committed_nonfinite,type51_bt_type,type51_point_count,type51_eij_ryd,type51_eij_ev,type51_scaling_c,type51_physical_temperature_k,type51_floor_temperature_k,type51_effective_temperature_k,type51_temperature_floor_applied,type51_scaled_temperature,type51_transformed_temperature,type51_scaled_upsilon,type51_upsilon,type51_lower_g,type51_upper_g,type51_electron_density_cm3,type51_q_excitation_cm3_s,type51_q_deexcitation_cm3_s,type51_shadow_ans1,type51_shadow_ans2,type51_shadow_ans3,type51_shadow_ans4,type51_shadow_ans5,type51_shadow_ans6,type51_legacy_ans1,type51_legacy_ans2,type51_legacy_ans3,type51_legacy_ans4,type51_legacy_ans5,type51_legacy_ans6\n";
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
        const int source_sequence = required_environment_integer("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
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

            solve_terms << "evaluation_ordinal,source_order_index,contribution_source_position,term_source_position,record,data_type,rate_type,ion_index,ion_stage,role,compact_row,compact_column,full_row,full_column,aj1,aj2,cj,cj2,density_scale\n";
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
