#include "xstar_fixed_state_engine.h"
#include "xstar_element_engine.h"
#include "xstar_spectral_engine.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <limits>
#include <memory>
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
constexpr double kSigmaT = 6.6524587321e-25;

void copy_text(char* target, std::size_t cap, const std::string& value) {
    if (!target || cap == 0) return;
    const std::size_t n = std::min(cap - 1, value.size());
    std::memcpy(target, value.data(), n);
    target[n] = '\0';
}

double elapsed(const clock_type::time_point& start) {
    return std::chrono::duration<double>(clock_type::now() - start).count();
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
};

struct ElementProgram {
    int element_index = 0;
    int element_z = 0;
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
};

struct Program {
    std::string id;
    std::vector<ElementProgram> elements;
    std::vector<ProgramRecord> records;
    std::vector<double> reals;
    std::vector<std::int64_t> ints;
};

struct EvaluatedRecord {
    xstar_element_contribution_v1 contribution{};
    bool spectral = false;
    double line_energy_ev = 0.0;
    double atomic_mass_amu = 1.0;
    double natural_width_ev = 0.0;
    double opakab = 0.0;
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
    while (std::getline(input, line)) {
        if (trim(line).empty()) continue;
        const auto c = split_csv(line);
        if (c.size() != 8) throw std::runtime_error("elements.csv requires 8 columns");
        ElementProgram e;
        e.element_index = parse_number<int>(c[0], "element_index");
        e.element_z = parse_number<int>(c[1], "element_z");
        e.n_rows = parse_number<int>(c[2], "n_rows");
        e.n_superlevels = parse_number<int>(c[3], "n_superlevels");
        e.n_ions = parse_number<int>(c[4], "n_ions");
        e.normalization_row = parse_number<int>(c[5], "normalization_row");
        e.record_head = parse_number<int>(c[6], "record_head");
        e.record_count = parse_number<int>(c[7], "record_count");
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
        if (c.size() != 8) throw std::runtime_error("rows.csv requires 8 columns");
        ElementRow r;
        r.element_index = parse_number<int>(c[0], "element_index");
        r.row = parse_number<int>(c[1], "row");
        r.superlevel = parse_number<int>(c[2], "superlevel");
        r.ion = parse_number<int>(c[3], "ion");
        r.ion_charge = parse_number<int>(c[4], "ion_charge");
        r.initial_population = parse_number<double>(c[5], "initial_population");
        r.energy_ev = parse_number<double>(c[6], "energy_ev");
        r.statistical_weight = parse_number<double>(c[7], "statistical_weight");
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
        if (c.size() != 18) throw std::runtime_error("records.csv requires 18 columns");
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
    if (abi_it == manifest.end() || parse_number<unsigned>(abi_it->second, "program_abi") != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) {
        throw std::runtime_error("fixed-state program ABI mismatch");
    }
    if (id_it == manifest.end() || id_it->second.empty()) throw std::runtime_error("program_id missing");
    p.id = id_it->second;
    load_elements(join_path(directory, "elements.csv"), p);
    load_rows(join_path(directory, "rows.csv"), p);
    p.reals = load_scalar_file<double>(join_path(directory, "reals.txt"), "reals.txt");
    p.ints = load_scalar_file<std::int64_t>(join_path(directory, "ints.txt"), "ints.txt");
    load_records(join_path(directory, "records.csv"), p);
    for (std::size_t k = 0; k < p.records.size(); ++k) {
        const auto& r = p.records[k];
        if (r.next_index < -1 || r.next_index >= static_cast<int>(p.records.size())) throw std::runtime_error("record next_index out of range");
        if (r.real_offset + r.real_count > p.reals.size()) throw std::runtime_error("record real payload out of range");
        if (r.int_offset + r.int_count > p.ints.size()) throw std::runtime_error("record integer payload out of range");
        const auto& e = p.elements[static_cast<std::size_t>(r.element_index)];
        if (r.lower_row < 1 || r.lower_row > e.n_rows || r.upper_row < 1 || r.upper_row > e.n_rows) throw std::runtime_error("record endpoint out of compact element range");
    }
    return p;
}

double limited_exp(double x) {
    return std::exp(std::max(-700.0, std::min(700.0, x)));
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

const ElementRow& row_at(const ElementProgram& element, int one_based) {
    if (one_based < 1 || one_based > element.n_rows) throw std::runtime_error("row index outside element");
    return element.rows[static_cast<std::size_t>(one_based - 1)];
}

EvaluatedRecord evaluate_record(
    const Program& program,
    const ElementProgram& element,
    const ProgramRecord& record,
    const xstar_fixed_state_input_v1& input
) {
    const double* r = record.real_count ? program.reals.data() + record.real_offset : nullptr;
    const auto* ints = record.int_count ? program.ints.data() + record.int_offset : nullptr;
    const ElementRow& lower = row_at(element, record.lower_row);
    const ElementRow& upper = row_at(element, record.upper_row);
    const double delta_ev = record.line_energy_ev > 0.0 ? record.line_energy_ev : std::abs(upper.energy_ev - lower.energy_ev);
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
        case XSTAR_FIXED_OPCODE_TYPE49_AUTOIONIZATION: {
            if (!r || record.real_count < 2) throw std::runtime_error("type49 payload requires autoionization rate and resonance energy");
            const double auto_rate = std::max(0.0, r[0]);
            const double resonance_ev = std::max(0.0, r[1]);
            c.ans1 = auto_rate;
            const double ratio = lower.statistical_weight / std::max(upper.statistical_weight, 1.0e-300);
            c.ans2 = auto_rate * 2.08e-22 * ratio * ne / std::max(t4 * sqrt_t4, 1.0e-300) * limited_exp(resonance_ev / std::max(kt_ev, 1.0e-300));
            c.ans5 = c.ans2 * resonance_ev * kErgPerEv;
            c.ans6 = c.ans1 * resonance_ev * kErgPerEv;
            break;
        }
        case XSTAR_FIXED_OPCODE_TYPE50_RADIATIVE_LINE:
        case XSTAR_FIXED_OPCODE_TYPE88_RADIATIVE_LINE: {
            if (!r || record.real_count < 2) throw std::runtime_error("radiative line payload requires A and oscillator strength");
            const double a = std::max(0.0, r[0]);
            const double oscillator = std::max(0.0, r[1]);
            const double flux = input.radiation_bin_count > 0 ? interp_linear(input.radiation_energy_ev, input.radiation_flux, input.radiation_bin_count, delta_ev) : 0.0;
            c.ans1 = oscillator * flux * 1.0e-18 * std::max(0.0, 1.0 - input.covering_fraction);
            c.ans2 = a;
            c.ans3 = c.ans2 * delta_ev * kErgPerEv;
            c.ans4 = c.ans1 * delta_ev * kErgPerEv;
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
        case XSTAR_FIXED_OPCODE_TYPE53_BOUND_FREE:
        case XSTAR_FIXED_OPCODE_TYPE99_SUPERLEVEL_BOUND_FREE: {
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
        case XSTAR_FIXED_OPCODE_TYPE63_ALGORITHMIC_COLLISION: {
            if (!r || record.real_count < 3) throw std::runtime_error("type63 lowered payload requires coefficient,power,activation_eV");
            const double qforward = std::max(0.0, r[0] * std::pow(std::max(t4, 1.0e-300), r[1]) * limited_exp(-r[2] / std::max(kt_ev, 1.0e-300)));
            const double qreverse = qforward * lower.statistical_weight / std::max(upper.statistical_weight, 1.0e-300) * limited_exp(delta_ev / std::max(kt_ev, 1.0e-300));
            c.ans1 = qforward * ne;
            c.ans2 = qreverse * ne;
            c.ans5 = c.ans2 * delta_ev * kErgPerEv;
            c.ans6 = c.ans1 * delta_ev * kErgPerEv;
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
    if (out.spectrum_capacity < in.radiation_bin_count || out.opacity_capacity < in.radiation_bin_count) throw std::runtime_error("spectrum or opacity output capacity too small");
}

int run_impl(
    xstar_fixed_state_context_impl& ctx,
    const xstar_fixed_state_input_v1& input,
    xstar_fixed_state_output_v1& output,
    xstar_fixed_state_stats_v1& stats
) {
    validate_io(input, output);
    const auto total_start = clock_type::now();
    stats.calls += 1;
    stats.status_flags = XSTAR_FIXED_STATE_STATUS_RAW_PROGRAM_LOADED |
        XSTAR_FIXED_STATE_STATUS_LINKED_TRAVERSAL |
        XSTAR_FIXED_STATE_STATUS_NATIVE_UCALC |
        XSTAR_FIXED_STATE_STATUS_NATIVE_ELEMENT_SOLVE |
        XSTAR_FIXED_STATE_STATUS_NATIVE_CONTINUUM |
        XSTAR_FIXED_STATE_STATUS_NATIVE_SPECTRAL |
        XSTAR_FIXED_STATE_STATUS_STATE_DEPENDENT |
        XSTAR_FIXED_STATE_STATUS_NO_CALLBACKS;
    stats.python_callbacks = 0;
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

        std::vector<xstar_element_contribution_v1> contributions;
        contributions.reserve(evaluated.size());
        for (const auto& e : evaluated) contributions.push_back(e.contribution);
        stats.contributions_constructed += contributions.size();
        ElementBuffers buffers = make_buffers(element);
        xstar_element_input_v1 ein{};
        xstar_element_input_init_v1(&ein);
        ein.flags = XSTAR_ELEMENT_STRICT_SOURCE_ORDER | XSTAR_ELEMENT_ALLOW_DENSE_RESCUE;
        ein.element_z = element.element_z;
        ein.n_rows = element.n_rows;
        ein.n_superlevels = element.n_superlevels;
        ein.n_ions = element.n_ions;
        ein.normalization_row = element.normalization_row;
        ein.max_lucy_iterations = 100;
        ein.max_fixed_point_iterations = 40;
        ein.lucy_tolerance = 1.0e-12;
        ein.fixed_point_tolerance = 1.0e-11;
        ein.superlevel_by_row = buffers.superlevels.data();
        ein.ion_by_row = buffers.ions.data();
        ein.initial_populations = buffers.initial.data();
        xstar_element_output_v1 eout{};
        bind_output(eout, buffers, element.element_z);
        std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> error{};
        const auto element_start = clock_type::now();
        const int rc = xstar_element_engine_run_construction_v1(
            ctx.element_context, &ein, contributions.data(), contributions.size(), &eout, error.data(), error.size());
        stats.element_seconds += elapsed(element_start);
        if (rc != 0) throw std::runtime_error(std::string("native element solve failed: ") + error.data());
        ++stats.elements_solved;
        output.element_heating += eout.heating + eout.heating2;
        output.element_cooling += eout.cooling + eout.cooling2;
        for (std::size_t k = 0; k < buffers.populations.size(); ++k) {
            all_populations.push_back(buffers.populations[k]);
            output.elcter += buffers.populations[k] * static_cast<double>(element.rows[k].ion_charge);
        }
        for (std::size_t k = 0; k < evaluated.size(); ++k) {
            if (!evaluated[k].spectral) continue;
            const auto& rec = evaluated[k].contribution;
            xstar_spectral_contribution_v1 sc{};
            sc.source_position = static_cast<std::uint64_t>(rec.source_position);
            sc.record = rec.record;
            sc.kind = XSTAR_SPECTRAL_KIND_EMISAB_LINE;
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
        std::vector<double> rcem(2 * input.radiation_bin_count, 0.0), oplin(input.radiation_bin_count, 0.0), cemab(2 * input.radiation_bin_count, 0.0), cabab(input.radiation_bin_count, 0.0), opakab(input.radiation_bin_count, 0.0), rccemis(2 * input.radiation_bin_count, 0.0), opakcont(input.radiation_bin_count, 0.0), fline(2 * (spectral.size() + 1), 0.0), flinel(input.radiation_bin_count, 0.0);
        xstar_spectral_workspace_v1 sw{};
        xstar_spectral_workspace_init_v1(&sw);
        sw.rcem = rcem.data(); sw.rcem_count = rcem.size();
        sw.oplin = oplin.data(); sw.oplin_count = oplin.size();
        sw.cemab = cemab.data(); sw.cemab_count = cemab.size();
        sw.cabab = cabab.data(); sw.cabab_count = cabab.size();
        sw.opakab = opakab.data(); sw.opakab_count = opakab.size();
        sw.rccemis = rccemis.data(); sw.rccemis_count = rccemis.size();
        sw.opakc = output.opacity; sw.opakc_count = input.radiation_bin_count;
        sw.opakcont = opakcont.data(); sw.opakcont_count = opakcont.size();
        sw.fline = fline.data(); sw.fline_count = fline.size();
        sw.flinel = flinel.data(); sw.flinel_count = flinel.size();
        sw.epi_eV = input.radiation_energy_ev; sw.energy_count = input.radiation_bin_count;
        xstar_spectral_stats_v1 ss{};
        xstar_spectral_stats_init_v1(&ss);
        std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> error{};
        const int rc = xstar_spectral_apply_contributions_v1(ctx.spectral_context, spectral.data(), spectral.size(), nullptr, 0, &sw, &ss, error.data(), error.size());
        if (rc != 0) throw std::runtime_error(std::string("native spectral commit failed: ") + error.data());
        for (std::size_t k = 0; k < input.radiation_bin_count; ++k) output.spectrum[k] += rcem[k] + cemab[k] + rccemis[k];
        stats.spectral_contributions += ss.contributions_committed;
    }
    stats.spectral_seconds += elapsed(spectral_start);

    output.total_heating = output.element_heating + output.continuum_heating;
    output.total_cooling = output.element_cooling + output.continuum_cooling;
    const double denom = std::max(std::abs(output.total_heating) + std::abs(output.total_cooling), 1.0e-300);
    output.hmctot = (output.total_heating - output.total_cooling) / denom;
    output.electron_fraction_xee = output.elcter;
    output.status_flags = stats.status_flags;
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
const char* xstar_fixed_state_engine_backend_name(void) { return "xstar_native_fixed_state_raw_program_development_v06482"; }
uint32_t xstar_fixed_state_engine_feature_flags(void) {
    return XSTAR_FIXED_STATE_STATUS_RAW_PROGRAM_LOADED |
        XSTAR_FIXED_STATE_STATUS_LINKED_TRAVERSAL |
        XSTAR_FIXED_STATE_STATUS_NATIVE_UCALC |
        XSTAR_FIXED_STATE_STATUS_NATIVE_ELEMENT_SOLVE |
        XSTAR_FIXED_STATE_STATUS_NATIVE_CONTINUUM |
        XSTAR_FIXED_STATE_STATUS_NATIVE_SPECTRAL |
        XSTAR_FIXED_STATE_STATUS_STATE_DEPENDENT |
        XSTAR_FIXED_STATE_STATUS_NO_CALLBACKS;
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
