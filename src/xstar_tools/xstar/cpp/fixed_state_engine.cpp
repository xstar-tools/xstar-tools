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
#include <map>
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

struct EvaluatedRecord {
    xstar_element_contribution_v1 contribution{};
    bool spectral = false;
    bool matrix_enabled = true;
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
    std::map<int, std::uint64_t> visited_data_types;
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
        if (c.size() != 8 && c.size() != 9) throw std::runtime_error("elements.csv requires 8 legacy columns or 9 columns with abundance");
        ElementProgram e;
        e.element_index = parse_number<int>(c[0], "element_index");
        e.element_z = parse_number<int>(c[1], "element_z");
        const std::size_t offset = c.size() == 9 ? 1u : 0u;
        if (c.size() == 9) e.abundance = parse_number<double>(c[2], "abundance");
        e.n_rows = parse_number<int>(c[2 + offset], "n_rows");
        e.n_superlevels = parse_number<int>(c[3 + offset], "n_superlevels");
        e.n_ions = parse_number<int>(c[4 + offset], "n_ions");
        e.normalization_row = parse_number<int>(c[5 + offset], "normalization_row");
        e.record_head = parse_number<int>(c[6 + offset], "record_head");
        e.record_count = parse_number<int>(c[7 + offset], "record_count");
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
    if (abi_it == manifest.end() || parse_number<unsigned>(abi_it->second, "program_abi") != XSTAR_FIXED_STATE_ENGINE_ABI_VERSION) {
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
        case XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE:
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

        std::vector<xstar_element_contribution_v1> contributions;
        contributions.reserve(evaluated.size());
        for (const auto& e : evaluated) if (e.matrix_enabled) contributions.push_back(e.contribution);
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
        for (double population : buffers.populations) all_populations.push_back(population);

        // Source calc_hmc_all electron accounting is abundance weighted and
        // treats the compact normalization row as the fully stripped stage.
        // The element engine's final ion totals deliberately exclude that last
        // row, so the missing fraction is the bare-ion population.
        double represented_fraction = 0.0;
        double charge_per_element = 0.0;
        for (int ion_slot = 0; ion_slot < element.n_ions; ++ion_slot) {
            const double fraction = buffers.ion_population_final[static_cast<std::size_t>(ion_slot)];
            represented_fraction += fraction;
            int ion_charge = 0;
            bool found_charge = false;
            for (const auto& row : element.rows) {
                if (row.ion == ion_slot + 1) {
                    ion_charge = row.ion_charge;
                    found_charge = true;
                    break;
                }
            }
            if (!found_charge) throw std::runtime_error("missing ion charge for compact ion counter");
            charge_per_element += fraction * static_cast<double>(ion_charge);
        }
        const double fully_ionized_fraction = std::max(0.0, 1.0 - represented_fraction);
        charge_per_element += fully_ionized_fraction * static_cast<double>(element.element_z);
        output.elcter += element.abundance * charge_per_element;
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
        XSTAR_FIXED_STATE_STATUS_ACTIVE_ATDB_LOWERED;
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
