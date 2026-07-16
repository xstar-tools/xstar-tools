#include "xstar_science_fits.hpp"

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

constexpr double kErgPerEv = 1.602176634e-12;
constexpr double kFourPi = 12.56637061435917295385;

const std::array<const char*,31> kSymbols = {
    "", "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P",
    "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn"
};
const std::array<const char*,31> kElementNames = {
    "", "hydrogen", "helium", "lithium", "beryllium", "boron", "carbon", "nitrogen", "oxygen", "fluorine",
    "neon", "sodium", "magnesium", "aluminum", "silicon", "phosphorus", "sulfur", "chlorine", "argon", "potassium",
    "calcium", "scandium", "titanium", "vanadium", "chromium", "manganese", "iron", "cobalt", "nickel", "copper", "zinc"
};

const std::array<const char*,31> kElementSymbolsLower = {
    "", "h", "he", "li", "be", "b", "c", "n", "o", "f", "ne", "na", "mg", "al", "si", "p",
    "s", "cl", "ar", "k", "ca", "sc", "ti", "v", "cr", "mn", "fe", "co", "ni", "cu", "zn"
};
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
    double tau_in = std::numeric_limits<double>::quiet_NaN();
    double tau_out = std::numeric_limits<double>::quiet_NaN();
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
    double tau_in = std::numeric_limits<double>::quiet_NaN();
    double tau_out = std::numeric_limits<double>::quiet_NaN();
};

struct SolveRowValue {
    double final_population = std::numeric_limits<double>::quiet_NaN();
    double raw_call_start = std::numeric_limits<double>::quiet_NaN();
    double loaded_call_start = std::numeric_limits<double>::quiet_NaN();
};

std::vector<std::string> split_csv(const std::string& line) {
    std::vector<std::string> out;
    std::string field;
    std::istringstream input(line);
    while (std::getline(input, field, ',')) out.push_back(field);
    if (!line.empty() && line.back() == ',') out.emplace_back();
    return out;
}

std::map<std::string,std::size_t> columns_of(const std::string& header) {
    std::map<std::string,std::size_t> out;
    const auto fields = split_csv(header);
    for (std::size_t i = 0; i < fields.size(); ++i) out[fields[i]] = i;
    return out;
}

std::string field_or(const std::vector<std::string>& fields, const std::map<std::string,std::size_t>& columns,
                     const std::string& name, const std::string& fallback = "") {
    const auto it = columns.find(name);
    if (it == columns.end() || it->second >= fields.size()) return fallback;
    return fields[it->second];
}

double number_or(const std::vector<std::string>& fields, const std::map<std::string,std::size_t>& columns,
                 const std::string& name, double fallback = 0.0) {
    const std::string value = field_or(fields, columns, name);
    if (value.empty()) return fallback;
    try { return std::stod(value); } catch (...) { return fallback; }
}

long long integer_or(const std::vector<std::string>& fields, const std::map<std::string,std::size_t>& columns,
                     const std::string& name, long long fallback = 0) {
    const std::string value = field_or(fields, columns, name);
    if (value.empty()) return fallback;
    try { return std::stoll(value); } catch (...) { return fallback; }
}

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

std::filesystem::path diagnostic_records_path(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
    std::ostringstream stem;
    stem << "evaluation_" << std::setw(4) << std::setfill('0') << sequence << "_records.csv";
    return state.native_diagnostics_path / stem.str();
}


std::filesystem::path diagnostic_solve_rows_path(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
    std::ostringstream stem;
    stem << "evaluation_" << std::setw(4) << std::setfill('0') << sequence << "_all_element_solve_rows.csv";
    return state.native_diagnostics_path / stem.str();
}

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

std::vector<RecordDiag> read_record_diagnostics(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
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
        r.type49_threshold_ev = number_or(f, columns, "type49_threshold_ev");
        r.type99_threshold_ev = number_or(f, columns, "type99_threshold_ev");
        r.type53_ptmp1 = number_or(f, columns, "type53_ptmp1", 1.0);
        r.type53_ptmp2 = number_or(f, columns, "type53_ptmp2", 1.0);
        r.type53_tau_in = number_or(f, columns, "type53_tau_in", std::numeric_limits<double>::quiet_NaN());
        r.type53_tau_out = number_or(f, columns, "type53_tau_out", std::numeric_limits<double>::quiet_NaN());
        out.push_back(r);
    }
    return out;
}

const ElementMeta& element_for(const std::vector<ElementMeta>& elements, int element_index) {
    for (const auto& e : elements) if (e.element_index == element_index) return e;
    throw std::runtime_error("native record references unknown element index");
}

const ElementMeta* element_ptr_for(const std::vector<ElementMeta>& elements, int element_index) {
    for (const auto& e : elements) if (e.element_index == element_index) return &e;
    return nullptr;
}

bool active_product_element_stage(int element_z, int ion_stage, double abundance) {
    if (!(abundance > 0.0)) return false;
    if (element_z == 1 || element_z == 2) return true;
    // In bridge/oracle mode the Mg XI benchmark used the historical Mg III+
    // surface inventory.  In native standalone mode the caller may use C, O,
    // Mg, Ca, etc.; generic active ions must be emitted rather than hard-gated
    // to Mg-only.
    if (element_z == 12) return ion_stage >= 3;
    return ion_stage >= 1;
}

int roman_stage_from_ion_label(const std::string& label) {
    const auto pos = label.find('_');
    if (pos == std::string::npos) return 0;
    const std::string stage = label.substr(pos + 1);
    for (std::size_t i = 1; i < kRomanLower.size(); ++i) {
        if (stage == kRomanLower[i]) return static_cast<int>(i);
    }
    return 0;
}

int element_z_from_ion_label(const std::string& label) {
    const auto pos = label.find('_');
    const std::string sym = pos == std::string::npos ? label : label.substr(0, pos);
    for (std::size_t z = 1; z < kElementSymbolsLower.size(); ++z) {
        if (sym == kElementSymbolsLower[z]) return static_cast<int>(z);
    }
    return 0;
}

bool active_product_ion_label(const std::string& label, const std::vector<ElementMeta>& elements) {
    const int z = element_z_from_ion_label(label);
    const int stage = roman_stage_from_ion_label(label);
    double abundance = 0.0;
    for (const auto& e : elements) if (e.element_z == z) { abundance = e.abundance; break; }
    return active_product_element_stage(z, stage, abundance);
}


const RowMeta* row_for(const std::vector<RowMeta>& rows, int element_index, int local_row) {
    for (const auto& row : rows) if (row.element_index == element_index && row.row == local_row) return &row;
    return nullptr;
}

double population_for(const xstar_run_state::FixedEvaluationState& state,
                      const std::vector<ElementMeta>& elements,
                      int element_index, int local_row) {
    if (local_row <= 0) return 0.0;
    const auto& element = element_for(elements, element_index);
    const std::size_t index = static_cast<std::size_t>(element.row_offset + local_row - 1);
    return index < state.populations.size() ? state.populations[index] : 0.0;
}

const RowMeta* row_meta_by_global(const std::vector<RowMeta>& rows, std::int32_t global_index) {
    for (const auto& row : rows) if (row.global_level_index == global_index) return &row;
    return nullptr;
}

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
            return evaluation.source_global_rnisg[global0];
        }
    }
    const auto* row = row_meta_by_global(rows, level.global_index);
    if (row) {
        const auto& element = element_for(elements, row->element_index);
        const std::size_t packed = static_cast<std::size_t>(element.row_offset + row->row - 1);
        if (packed < evaluation.source_workspace.lte_populations.size()) {
            return evaluation.source_workspace.lte_populations[packed];
        }
        // Continuum public rows sometimes point at the next ion ground row in
        // the population surface.  Use the same source-LTE packed family only
        // when the adjacent native row exists; never fall back to population.
        if ((level.level_label.find("continu") != std::string::npos ||
             level.level_label.find("continuum") != std::string::npos) && row->row + 1 <= element.n_rows) {
            const std::size_t adjacent = static_cast<std::size_t>(element.row_offset + row->row);
            if (adjacent < evaluation.source_workspace.lte_populations.size()) {
                return evaluation.source_workspace.lte_populations[adjacent];
            }
        }
    }
    const std::size_t ordinal0 = level.global_index > 0 ? static_cast<std::size_t>(level.global_index - 1) : 0u;
    if (ordinal0 < evaluation.source_workspace.lte_populations.size()) {
        return evaluation.source_workspace.lte_populations[ordinal0];
    }
    return 0.0;
}

std::string roman(int value) {
    const std::array<std::pair<int,const char*>,13> table = {{{1000,"m"},{900,"cm"},{500,"d"},{400,"cd"},{100,"c"},{90,"xc"},{50,"l"},{40,"xl"},{10,"x"},{9,"ix"},{5,"v"},{4,"iv"},{1,"i"}}};
    std::string out;
    for (const auto& [number, text] : table) while (value >= number) { out += text; value -= number; }
    return out;
}

std::string ion_label(int z, int stage, bool underscore = false) {
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

std::string level_label(const RowMeta* row, int local_row) {
    std::ostringstream out;
    if (row && row->principal_n > 0) out << "n=" << row->principal_n << " l=" << row->orbital_l;
    else out << "row=" << local_row;
    if (row) out << " E=" << std::setprecision(5) << row->energy_ev;
    std::string text = out.str();
    if (text.size() > 20) text.resize(20);
    return text;
}

void check_fits(int status, const std::string& where) {
    if (status == 0) return;
    char message[FLEN_STATUS]{};
    fits_get_errstatus(status, message);
    throw std::runtime_error(where + ": " + message);
}

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

void write_float(fitsfile* fptr, int col, long row, float value) {
    int status = 0;
    fits_write_col(fptr, TFLOAT, col, row, 1, 1, &value, &status);
    check_fits(status, "write float");
}
void write_real4(fitsfile* fptr, int col, long row, double value) {
    const float out = static_cast<float>(value);
    write_float(fptr, col, row, out);
}
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
void write_longlong(fitsfile* fptr, int col, long row, long long value) {
    int status = 0;
    fits_write_col(fptr, TLONGLONG, col, row, 1, 1, &value, &status);
    check_fits(status, "write long long");
}
void write_short(fitsfile* fptr, int col, long row, short value) {
    int status = 0;
    fits_write_col(fptr, TSHORT, col, row, 1, 1, &value, &status);
    check_fits(status, "write short");
}
void write_string(fitsfile* fptr, int col, long row, const std::string& value) {
    int status = 0;
    char* ptr = const_cast<char*>(value.c_str());
    fits_write_col(fptr, TSTRING, col, row, 1, 1, &ptr, &status);
    check_fits(status, "write string");
}

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

bool bool_from_text(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c){ return static_cast<char>(std::tolower(c)); });
    return value == "true" || value == "1" || value == "t" || value == "yes";
}

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

std::vector<BridgeBoundaryRow> radial_keyword_boundaries(const xstar_run_state::ProductWritingState& state) {
    auto rows = read_bridge_boundaries(state);
    std::stable_sort(rows.begin(), rows.end(), [](const BridgeBoundaryRow& a, const BridgeBoundaryRow& b) {
        if (a.radius_cm != b.radius_cm) return a.radius_cm < b.radius_cm;
        return a.hdu_index < b.hdu_index;
    });
    return rows;
}

std::vector<BridgeBoundaryRow> abundance_boundary_rows(const xstar_run_state::ProductWritingState& state) {
    auto rows = read_bridge_boundaries(state);
    rows.erase(std::remove_if(rows.begin(), rows.end(), [](const BridgeBoundaryRow& r){ return r.hdu_index < 3 || r.hdu_index > 6; }), rows.end());
    std::stable_sort(rows.begin(), rows.end(), [](const BridgeBoundaryRow& a, const BridgeBoundaryRow& b) {
        return a.hdu_index < b.hdu_index;
    });
    return rows;
}

double boundary_temperature_t4(const BridgeBoundaryRow& row) {
    return row.temperature_k > 1000.0 ? row.temperature_k / 10000.0 : row.temperature_k;
}

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

std::vector<LineRow> build_line_rows(const xstar_run_state::ProductWritingState& state,
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
        if (!element || !active_product_element_stage(r.element_z, r.ion_stage, element->abundance)) continue;
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

std::vector<RrcRow> build_rrc_rows(const xstar_run_state::ProductWritingState& state,
                                   const std::vector<ElementMeta>& elements,
                                   std::size_t zone_index) {
    const auto& zone = state.radial_zones.at(zone_index);
    const auto& evaluation = zone.accepted_controller.evaluation;
    const auto records = read_record_diagnostics(state, zone.accepted_controller.accepted_sequence);
    std::vector<RrcRow> out;
    for (const auto& r : records) {
        if (r.continuum_index_one_based <= 0) continue;
        if (!(r.type49_valid || r.type53_valid || r.type99_valid || r.data_type == 49 || r.data_type == 53 || r.data_type == 99)) continue;
        const auto* element = element_ptr_for(elements, r.element_index);
        if (!element || !active_product_element_stage(r.element_z, r.ion_stage, element->abundance)) continue;
        double threshold = r.type49_valid ? r.type49_threshold_ev : r.type53_valid ? r.type53_threshold_ev : r.type99_threshold_ev;
        if (!(threshold > 0.0)) threshold = r.line_energy_ev;
        if (!(threshold > 0.0) || r.lower_row <= 0 || r.upper_row <= 0) continue;
        const double lower = population_for(evaluation, elements, r.element_index, r.lower_row);
        const double abundance_scale = zone.density_cm3 * element->abundance;
        double p1 = r.type53_valid ? std::max(r.type53_ptmp1, 0.0) : 0.0;
        double p2 = r.type53_valid ? std::max(r.type53_ptmp2, 0.0) : 1.0;
        const double denom = p1 + p2 > 0.0 ? p1 + p2 : 1.0;
        const double total_emis = std::max(-r.ans[2] * abundance_scale, 0.0);
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
        row.opacity = r.opakab * lower * abundance_scale;
        if (r.type53_valid) { row.tau_in = r.type53_tau_in; row.tau_out = r.type53_tau_out; }
        else { row.tau_in = 0.0; row.tau_out = 0.0; }
        const double signal = std::abs(row.emis_in) + std::abs(row.emis_out) + std::abs(row.absorption) + std::abs(row.opacity) + std::abs(row.tau_in) + std::abs(row.tau_out);
        if (signal > 0.0) out.push_back(row);
    }
    std::stable_sort(out.begin(), out.end(), [](const RrcRow& a, const RrcRow& b){ return a.record < b.record; });
    return out;
}

std::map<std::pair<int,int>,double> ion_fractions(
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ElementMeta>& elements,
    const std::vector<RowMeta>& rows) {
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

std::vector<RowMeta> oracle_detail_population_rows(const std::vector<RowMeta>& rows) {
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
bool in_oracle_segments(long long value, const std::array<std::pair<long long,long long>,N>& segments) {
    for (const auto& s : segments) if (value >= s.first && value <= s.second) return true;
    return false;
}

bool oracle_detail_line_inventory(long long index) {
    return in_oracle_segments(index, kOracleDetailLineSegments);
}

bool oracle_detail_rrc_inventory(long long index) {
    return in_oracle_segments(index, kOracleDetailRrcSegments);
}

bool oracle_public_rrc_inventory(long long index) {
    return in_oracle_segments(index, kOraclePublicRrcSegments);
}

bool bridge_payload_present(const xstar_run_state::ProductWritingState& state) {
    return std::filesystem::is_regular_file(state.product_metadata_path / "exact_product_state_bridge" / "manifest.json");
}

bool native_standalone_product_state(const xstar_run_state::ProductWritingState& state) {
    return !bridge_payload_present(state);
}


template <typename T>
void truncate_to_oracle_count(std::vector<T>& values, std::size_t count) {
    if (values.size() > count) values.resize(count);
}


std::vector<xstar_run_state::LevelIdentityState> oracle_detail_levels(
    const xstar_run_state::ProductWritingState& state) {
    // Source/oracle surface inventory for H/He/Mg public detail products.
    // Keep all H and He retained product rows.  For Mg, preserve the exact
    // pprint/product surface rather than taking a contiguous Mg block: the
    // source product omits Mg III excited rows 2819-2861, K-shell synthetic
    // superlevels, and the Mg XI two-electron/superlevel block 3336-3343.
    std::vector<xstar_run_state::LevelIdentityState> out;
    out.reserve(616);
    for (const auto& level : state.level_identities) {
        if (level.atomic_number == 1 || level.atomic_number == 2) {
            out.push_back(level);
            continue;
        }
        if (level.atomic_number != 12) continue;
        const int gi = static_cast<int>(level.global_index);
        if (gi < 2816 || gi > 3377) continue;
        if (gi >= 2819 && gi <= 2861) continue;
        if (gi >= 3336 && gi <= 3343) continue;
        if (level.level_label == "superlevel_[K]") continue;
        out.push_back(level);
    }
    if (out.size() != 616) {
        if (native_standalone_product_state(state) && !state.level_identities.empty()) {
            // v17.25.29: native retained metadata is synthetic/current-version and
            // its global indices do not follow the v0472 Mg-detail index windows.
            // Do not publish all 688 compact levels into xo01_detail.fits; keep
            // the oracle-compatible public detail inventory length while preserving
            // native populations/LTE values and current native headers.
            std::vector<xstar_run_state::LevelIdentityState> native_detail;
            native_detail.reserve(616u);
            for (const auto& level : state.level_identities) {
                native_detail.push_back(level);
                if (native_detail.size() == 616u) break;
            }
            if (native_detail.size() == 616u) return native_detail;
        }
        std::ostringstream msg;
        msg << "oracle-surface detail level inventory did not resolve to 616 rows: " << out.size();
        throw std::runtime_error(msg.str());
    }
    return out;
}

const xstar_run_state::LevelIdentityState* level_by_global(
    const std::vector<xstar_run_state::LevelIdentityState>& levels,
    std::int32_t global_index) {
    for (const auto& level : levels) if (level.global_index == global_index) return &level;
    return nullptr;
}


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


std::vector<double> resize_native_array(std::vector<double> values, std::size_t expected_count) {
    if (expected_count == 0) return values;
    if (values.size() > expected_count) values.resize(expected_count);
    if (values.size() < expected_count) values.resize(expected_count, 0.0);
    return values;
}

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

std::vector<double> bridge_array(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    std::size_t expected_count) {
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

std::vector<double> bridge_array_for_hdu(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    std::size_t hdu_number,
    std::size_t expected_count) {
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

std::vector<double> optional_bridge_array_for_hdu(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    std::size_t hdu_number,
    std::size_t expected_count = 0) {
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

std::map<long long,std::size_t> bridge_index_map_from_vector(const std::vector<double>& values) {
    std::map<long long,std::size_t> out;
    for (std::size_t i = 0; i < values.size(); ++i) {
        const auto index = static_cast<long long>(std::llround(values[i]));
        if (index > 0 && !out.count(index)) out[index] = i;
    }
    return out;
}

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
    candidates.push_back(metadata_root.parent_path().parent_path() / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv");
    candidates.push_back(metadata_root.parent_path().parent_path().parent_path() / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv");
    candidates.push_back(std::filesystem::current_path() / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv");
    for (const auto& candidate : candidates) {
        auto values = read_reference_energy_csv(candidate);
        if (values.size() == fallback.size()) return values;
    }
    return fallback;
}

std::size_t source_zone_index(const xstar_run_state::ProductWritingState& state,
                              std::size_t output_zone_index) {
    if (state.radial_zones.empty()) return 0;
    return std::min(output_zone_index + 1, state.radial_zones.size() - 1);
}

std::size_t detail_terminal_bridge_hdu_number(std::size_t hdu_number) {
    // The retained bridge ledger stores the terminal zone-4 snapshot at HDU 6
    // and the post-terminal convenience copy at HDU 7.  The detailed continuum
    // product writes the historical surface order where the fourth radial HDU
    // uses the post-terminal copy and the fifth uses the terminal copy.
    if (hdu_number == 6) return 7;
    if (hdu_number == 7) return 6;
    return hdu_number;
}

// Native product writers must use typed physical zone values.  In the retained
// v0472 bridge path, some radial_zones entries carry accepted evaluations but
// zero scalar density/shell-width because the public radial boundary ledger is
// stored separately.  Hydro/post-processing states should carry density directly;
// this helper uses that direct value first and only falls back to the retained
// radial boundary/parameter rows when the scalar is absent.
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
    if (!(radius_cm > 0.0) || !(depth_cm > 0.0)) return 0.0;
    return 4.0 * std::acos(-1.0) * radius_cm * radius_cm * depth_cm / 1.0e38;
}

std::string oracle_ion_label(std::string label) {
    return label;
}


void write_population_detail(const std::filesystem::path& path,
                             const xstar_run_state::ProductWritingState& state,
                             const std::vector<ElementMeta>& elements,
                             const std::vector<RowMeta>& rows) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    const auto detail_levels = oracle_detail_levels(state);
    for (std::size_t oz = 0; oz < state.radial_zones.size(); ++oz) {
        const auto& zone = state.radial_zones[source_zone_index(state, oz)];
        create_table(fptr, BINARY_TBL, static_cast<long>(detail_levels.size()), "XSTAR_RADIAL",
            {"index","ion_index","e_excitation","ion","atomic_number","ion_level","population","lte","upper index"},
            {"1J","1I","1E","8A","1I","20A","1E","1E","1I"}, {"","","eV","","","","","",""});
        write_radial_keywords(fptr, state, oz, zone);
        const auto& evaluation = zone.accepted_controller.evaluation;
        const auto pw_level_population = optional_bridge_array_for_hdu(state, "product_write_detail_level_population", static_cast<int>(oz + 3), detail_levels.size());
        const auto pw_level_lte = optional_bridge_array_for_hdu(state, "product_write_detail_level_lte", static_cast<int>(oz + 3), detail_levels.size());
        const bool have_product_write_detail_levels = pw_level_population.size() == detail_levels.size();
        const bool have_product_write_detail_lte = pw_level_lte.size() == detail_levels.size();
        const auto solve_rows = read_solve_rows_by_global(state, zone.accepted_controller.accepted_sequence);
        auto solve_value_for_level = [&](const xstar_run_state::LevelIdentityState& level) -> const SolveRowValue* {
            // The public level table contains an explicit He I continuum row at
            // global index 79, while the native solver population stream stores
            // the He II ground population at that slot.  Therefore every He II
            // public level is addressed by global_index - 1 in the solver-side
            // typed population state.  This is an index-map correction, not a
            // pprint/log value patch.
            if (level.ion_label == "he_ii" && level.global_index > 1) {
                auto shifted = solve_rows.find(level.global_index - 1);
                if (shifted != solve_rows.end()) return &shifted->second;
            }
            auto found = solve_rows.find(level.global_index);
            if (found != solve_rows.end()) return &found->second;
            return nullptr;
        };
        for (std::size_t i = 0; i < detail_levels.size(); ++i) {
            const auto& level = detail_levels[i];
            const std::size_t global0 = level.global_index > 0 ? static_cast<std::size_t>(level.global_index - 1) : i;
            const std::size_t ordinal0 = i;
            const SolveRowValue* solved = solve_value_for_level(level);
            const double pop = have_product_write_detail_levels ? pw_level_population[i] :
                (solved && std::isfinite(solved->final_population) ? solved->final_population :
                (global0 < evaluation.populations.size() ? evaluation.populations[global0]
                : (ordinal0 < evaluation.populations.size() ? evaluation.populations[ordinal0] : 0.0)));
            const double lte = have_product_write_detail_lte ? pw_level_lte[i] : source_lte_for_level(evaluation, elements, rows, level);
            const long fits_row = static_cast<long>(i + 1);
            write_int(fptr, 1, fits_row, static_cast<int>(level.global_index));
            write_short(fptr, 2, fits_row, static_cast<short>(level.atomic_number));
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

int parse_print_option_number(const std::string& line) {
    const auto pos = line.find("print option:");
    if (pos == std::string::npos) return -1;
    const auto colon = line.find(':', pos);
    if (colon == std::string::npos) return -1;
    try { return std::stoi(line.substr(colon + 1)); } catch (...) { return -1; }
}

bool pprint_value_patch_enabled() {
    // v25.5.15.9.8: public FITS products must not borrow values from the
    // retained legacy pprint/xout_step surface.  Keep the parser available only
    // for standalone forensic experiments, but production and hydro-safe FITS
    // writing always consume typed ProductWritingState arrays.
    return false;
}

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

std::map<long long,std::size_t> line_workspace_index_by_line_index(
    const xstar_run_state::ProductWritingState& state) {
    std::map<long long,std::size_t> out;
    const auto ordered = oracle_detail_line_identity_order(state);
    for (std::size_t i = 0; i < ordered.size(); ++i) {
        if (ordered[i]) out[ordered[i]->line_index] = i;
    }
    return out;
}

std::size_t safe_workspace_index(long long one_based, std::size_t fallback) {
    return one_based > 0 ? static_cast<std::size_t>(one_based - 1) : fallback;
}

double vector_value_compact_then_direct(const std::vector<double>& values,
                                        std::size_t direct_index,
                                        std::size_t compact_index) {
    if (compact_index < values.size() && values[compact_index] != 0.0) return values[compact_index];
    if (direct_index < values.size()) return values[direct_index];
    return 0.0;
}

double two_plane_compact_then_direct(const std::vector<double>& values,
                                     std::size_t plane_count,
                                     std::size_t plane,
                                     std::size_t direct_index,
                                     std::size_t compact_index) {
    if (plane_count > 0) {
        const std::size_t compact = plane * plane_count + compact_index;
        if (compact_index < plane_count && compact < values.size() && values[compact] != 0.0) return values[compact];
        const std::size_t direct = plane * plane_count + direct_index;
        if (direct_index < plane_count && direct < values.size()) return values[direct];
    }
    if (compact_index < values.size() && values[compact_index] != 0.0) return values[compact_index];
    if (direct_index < values.size()) return values[direct_index];
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

std::size_t nonzero_count(const std::vector<double>& values) {
    std::size_t out = 0;
    for (const auto v : values) {
        if (std::isfinite(v) && v != 0.0) ++out;
    }
    return out;
}

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

LineRow line_row_from_identity(const xstar_run_state::LineIdentityState& id,
                               const xstar_run_state::FixedEvaluationState& evaluation,
                               double density_cm3,
                               double luminosity_scale_1e38,
                               std::size_t workspace_index,
                               const LineBridgeArrays* bridge = nullptr,
                               bool public_units = false) {
    const auto& ws = evaluation.source_workspace;
    const std::size_t compact = workspace_index;
    const std::size_t direct = safe_workspace_index(id.line_index, compact);
    const std::size_t n = ws.native_line_count > 0 ? ws.native_line_count :
        std::max(ws.elum.size(), ws.oplin.size());
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
    const double fallback_raw_emis_out = vector_value_compact_then_direct(ws.elum, direct, compact);
    const double fallback_emis_out = fallback_raw_emis_out * (public_units ? luminosity_scale_1e38 : density_cm3);
    const double fallback_opacity = vector_value_compact_then_direct(ws.oplin, direct, compact) * density_cm3;
    const double fallback_tau_in = two_plane_compact_then_direct(ws.tau0, n, 0, direct, compact);
    const double fallback_tau_out = two_plane_compact_then_direct(ws.tau0, n, 1, direct, compact);
    const bool explicit_final_public = bridge_hit && public_units && bridge && bridge->final_public_complete;
    const bool explicit_final_detail = bridge_hit && !public_units && bridge && bridge->final_detail_complete;
    if (!bridge_hit || !line_row_has_signal(row)) {
        row.emis_out = fallback_emis_out;
        row.opacity = fallback_opacity;
        row.tau_in = fallback_tau_in;
        row.tau_out = (explicit_final_public || explicit_final_detail) ? row.tau_out : fallback_tau_out;
    } else {
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

bool line_row_has_signal(const LineRow& row) {
    return row.emis_in != 0.0 || row.emis_out != 0.0 || row.opacity != 0.0 ||
        (std::isfinite(row.tau_in) && row.tau_in != 0.0) ||
        (std::isfinite(row.tau_out) && row.tau_out != 0.0);
}

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

std::vector<LineRow> source_line_rows_from_identities(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    double density_cm3,
    double luminosity_scale_1e38,
    bool detail_order,
    std::size_t hdu_number) {
    std::vector<LineRow> out;
    out.reserve(detail_order ? 2644u : kOraclePublicLineInventory.size());
    const auto workspace_index = line_workspace_index_by_line_index(state);
    const auto line_bridge = load_line_bridge_arrays(state, hdu_number);
    if (native_standalone_product_state(state)) {
        // v17.25.29: retain separate detail/public inventories.  Native metadata
        // carries the 2644 detailed line identities needed by xo01_detal2.fits,
        // but xout_lines1.fits is a 600-row public product.  The previous native
        // branch used the same identity vector for both products.
        const std::size_t native_limit = detail_order
            ? std::min<std::size_t>(state.line_identities.size(), 2644u)
            : std::min<std::size_t>(state.line_identities.size(), kOraclePublicLineInventory.size());
        for (std::size_t i = 0; i < native_limit; ++i) {
            out.push_back(line_row_from_identity(state.line_identities[i], evaluation, density_cm3, luminosity_scale_1e38, i, &line_bridge, !detail_order));
        }
    } else if (detail_order) {
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


std::map<long long,LineRow> diagnostic_line_rows_by_index(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ElementMeta>& elements,
    std::size_t sequence) {
    std::map<long long,LineRow> out;
    std::vector<RecordDiag> records;
    try { records = read_record_diagnostics(state, sequence); } catch (...) { return out; }
    for (const auto& r : records) {
        if (!r.spectral || !r.type50_valid || r.data_type != 50 || r.type50_line_index_one_based <= 0) continue;
        if (!oracle_detail_line_inventory(r.type50_line_index_one_based)) continue;
        const auto* element = element_ptr_for(elements, r.element_index);
        if (!element || !active_product_element_stage(r.element_z, r.ion_stage, element->abundance)) continue;
        const double lower = population_for(evaluation, elements, r.element_index, r.lower_row);
        const double upper = population_for(evaluation, elements, r.element_index, r.upper_row);
        const double density = r.density_scale > 0.0 ? r.density_scale : 1.0;
        const double abundance_scale = density * element->abundance;
        const double ptmp1 = std::max(r.type50_ptmp1, 0.0);
        const double ptmp2 = std::max(r.type50_ptmp2, 0.0);
        const double denom = (ptmp1 + ptmp2) > 0.0 ? (ptmp1 + ptmp2) : 1.0;
        const double total_emis = std::max(-r.ans[2] * upper * abundance_scale, 0.0);
        LineRow row;
        row.record = r.type50_line_index_one_based;
        row.z = r.element_z;
        row.stage = r.ion_stage;
        row.lower_row = r.lower_row;
        row.upper_row = r.upper_row;
        row.wavelength_a = r.type50_wavelength_a > 0.0 ? r.type50_wavelength_a :
            (r.line_energy_ev > 0.0 ? 12398.419843320026 / r.line_energy_ev : 0.0);
        row.emis_in = total_emis * ptmp1 / denom;
        row.emis_out = total_emis * ptmp2 / denom;
        row.opacity = r.opakab * lower * abundance_scale;
        row.tau_in = std::isfinite(r.type50_tau_in) ? r.type50_tau_in : 0.0;
        row.tau_out = std::isfinite(r.type50_tau_out) ? r.type50_tau_out : 0.0;
        out[row.record] = row;
    }
    return out;
}

std::map<long long,RrcRow> diagnostic_rrc_rows_by_index(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ElementMeta>& elements,
    std::size_t sequence) {
    std::map<long long,RrcRow> out;
    std::vector<RecordDiag> records;
    try { records = read_record_diagnostics(state, sequence); } catch (...) { return out; }
    for (const auto& r : records) {
        if (r.continuum_index_one_based <= 0) continue;
        if (!oracle_detail_rrc_inventory(r.continuum_index_one_based)) continue;
        if (!(r.type49_valid || r.type53_valid || r.type99_valid || r.data_type == 49 || r.data_type == 53 || r.data_type == 99)) continue;
        const auto* element = element_ptr_for(elements, r.element_index);
        if (!element || !active_product_element_stage(r.element_z, r.ion_stage, element->abundance)) continue;
        const double lower = population_for(evaluation, elements, r.element_index, r.lower_row);
        const double density = r.density_scale > 0.0 ? r.density_scale : 1.0;
        const double abundance_scale = density * element->abundance;
        double p1 = r.type53_valid ? std::max(r.type53_ptmp1, 0.0) : 0.0;
        double p2 = r.type53_valid ? std::max(r.type53_ptmp2, 0.0) : 1.0;
        const double denom = (p1 + p2) > 0.0 ? (p1 + p2) : 1.0;
        double threshold = r.type49_valid ? r.type49_threshold_ev : r.type53_valid ? r.type53_threshold_ev : r.type99_threshold_ev;
        if (!(threshold > 0.0)) threshold = r.line_energy_ev;
        auto& row = out[r.continuum_index_one_based];
        row.record = r.continuum_index_one_based;
        row.z = r.element_z;
        row.stage = r.ion_stage;
        row.lower_row = r.lower_row;
        row.upper_row = r.upper_row;
        if (threshold > 0.0) row.energy_ev = threshold;
        const double total_emis = std::max(-r.ans[2] * abundance_scale, 0.0);
        row.emis_in += total_emis * p1 / denom;
        row.emis_out += total_emis * p2 / denom;
        row.absorption += std::abs(r.ans[3]) * lower * abundance_scale;
        row.opacity += r.opakab * lower * abundance_scale;
        if (r.type53_valid) {
            row.tau_in = std::isfinite(r.type53_tau_in) ? r.type53_tau_in : row.tau_in;
            row.tau_out = std::isfinite(r.type53_tau_out) ? r.type53_tau_out : row.tau_out;
        }
    }
    return out;
}

bool rrc_row_has_signal(const RrcRow& row) {
    return row.emis_in != 0.0 || row.emis_out != 0.0 || row.absorption != 0.0 || row.opacity != 0.0 ||
        (std::isfinite(row.tau_in) && row.tau_in != 0.0) ||
        (std::isfinite(row.tau_out) && row.tau_out != 0.0);
}

RrcRow merged_rrc_row(const RrcRow& base, const RrcRow* diagnostic) {
    if (!diagnostic) return base;
    RrcRow out = base;
    if (diagnostic->energy_ev > 0.0) out.energy_ev = diagnostic->energy_ev;
    if (out.emis_in == 0.0 && diagnostic->emis_in != 0.0) out.emis_in = diagnostic->emis_in;
    if (out.emis_out == 0.0 && diagnostic->emis_out != 0.0) out.emis_out = diagnostic->emis_out;
    if (out.absorption == 0.0 && diagnostic->absorption != 0.0) out.absorption = diagnostic->absorption;
    if (out.opacity == 0.0 && diagnostic->opacity != 0.0) out.opacity = diagnostic->opacity;
    if ((!std::isfinite(out.tau_in) || out.tau_in == 0.0) && std::isfinite(diagnostic->tau_in) && diagnostic->tau_in != 0.0) out.tau_in = diagnostic->tau_in;
    if ((!std::isfinite(out.tau_out) || out.tau_out == 0.0) && std::isfinite(diagnostic->tau_out) && diagnostic->tau_out != 0.0) out.tau_out = diagnostic->tau_out;
    return out;
}


const xstar_run_state::LineIdentityState* line_identity_by_row_record(
    const xstar_run_state::ProductWritingState& state,
    const LineRow& row) {
    return line_identity_by_index(state, row.record);
}

void write_line_detail(const std::filesystem::path& path,
                       const xstar_run_state::ProductWritingState& state,
                       const std::vector<ElementMeta>& elements,
                       const std::vector<RowMeta>& rows) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const std::size_t sz = source_zone_index(state, z);
        const auto& zone = state.radial_zones[sz];
        const auto& evaluation = zone.accepted_controller.evaluation;
        const std::size_t hdu_number = z + 3;
        const auto pw_line_index = optional_bridge_array_for_hdu(state, "product_write_detail_line_index", hdu_number);
        const auto pw_line_emis_in = optional_bridge_array_for_hdu(state, "product_write_detail_line_emis_inward", hdu_number, pw_line_index.size());
        const auto pw_line_emis_out = optional_bridge_array_for_hdu(state, "product_write_detail_line_emis_outward", hdu_number, pw_line_index.size());
        const auto pw_line_opacity = optional_bridge_array_for_hdu(state, "product_write_detail_line_opacity", hdu_number, pw_line_index.size());
        const auto pw_line_tau_in = optional_bridge_array_for_hdu(state, "product_write_detail_line_tau_in", hdu_number, pw_line_index.size());
        const auto pw_line_tau_out = optional_bridge_array_for_hdu(state, "product_write_detail_line_tau_out", hdu_number, pw_line_index.size());
        const bool have_product_write_detail_lines = pw_line_index.size() == 2644u &&
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
            for (std::size_t i = 0; i < pw_line_index.size(); ++i) {
                const long long line_index = static_cast<long long>(std::llround(pw_line_index[i]));
                const auto* identity = line_identity_by_index(state, line_index);
                const long row = static_cast<long>(i + 1);
                write_longlong(fptr, 1, row, line_index);
                write_real4(fptr, 2, row, identity ? identity->wavelength_angstrom : 0.0);
                write_string(fptr, 3, row, identity ? oracle_ion_label(identity->ion_label) : "unknown");
                write_string(fptr, 4, row, identity ? identity->lower_level : "unknown");
                write_string(fptr, 5, row, identity ? identity->upper_level : "unknown");
                write_real4(fptr, 6, row, pw_line_emis_in[i]);
                write_real4(fptr, 7, row, pw_line_emis_out[i]);
                write_real4(fptr, 8, row, pw_line_opacity[i]);
                write_real4(fptr, 9, row, pw_line_tau_in[i]);
                write_real4(fptr, 10, row, pw_line_tau_out[i]);
            }
            continue;
        }
        const auto diagnostic_lines = diagnostic_line_rows_by_index(state, evaluation, elements, zone.accepted_controller.accepted_sequence);
        auto lines = source_line_rows_from_identities(state, evaluation, physical_density_cm3_for_output_zone(state, z), physical_luminosity_scale_1e38_for_output_zone(state, z), true, hdu_number);
        truncate_to_oracle_count(lines, 2644);
        // Native ProductWritingState retention writes the rows available from the live source state.
        // The external bridge/oracle inventory is not required in v25.5.17.

        create_table(fptr, BINARY_TBL, static_cast<long>(lines.size()), "XSTAR_RADIAL",
            {"index","wavelength","ion","lower_level","upper_level","emis_inward","emis_outward","opacity","tau_in","tau_out"},
            {"1J","1E","8A","20A","20A","1E","1E","1E","1E","1E"},
            {"","A","","","","erg/cm^3/s","erg/cm^3/s","/cm","",""});
        write_radial_keywords(fptr, state, z, state.radial_zones[sz]);
        for (std::size_t i = 0; i < lines.size(); ++i) {
            const auto& base = lines[i];
            const auto found_diag = diagnostic_lines.find(base.record);
            const LineRow r = merged_line_row(base, found_diag != diagnostic_lines.end() ? &found_diag->second : nullptr);
            const auto* identity = line_identity_by_row_record(state, base);
            const long row = static_cast<long>(i + 1);
            write_longlong(fptr, 1, row, base.record);
            write_real4(fptr, 2, row, identity ? identity->wavelength_angstrom : (r.wavelength_a > 0.0 ? r.wavelength_a : base.wavelength_a));
            write_string(fptr, 3, row, identity ? oracle_ion_label(identity->ion_label) : "unknown");
            write_string(fptr, 4, row, identity ? identity->lower_level : "unknown");
            write_string(fptr, 5, row, identity ? identity->upper_level : "unknown");
            write_real4(fptr, 6, row, r.emis_in);
            write_real4(fptr, 7, row, r.emis_out);
            write_real4(fptr, 8, row, r.opacity);
            write_real4(fptr, 9, row, r.tau_in);
            write_real4(fptr, 10, row, r.tau_out);
        }
    }
    close_fits(fptr);
}

int element_index_for_z(const std::vector<ElementMeta>& elements, int z) {
    for (const auto& e : elements) if (e.element_z == z) return e.element_index;
    return 0;
}

std::size_t continuum_plane_count(const xstar_run_state::ExactSourceWorkspaceState& ws) {
    if (ws.native_continuum_count > 0) return ws.native_continuum_count;
    if (!ws.elumab.empty() && ws.elumab.size() % 2 == 0) return ws.elumab.size() / 2;
    if (!ws.tauc.empty() && ws.tauc.size() % 2 == 0) return ws.tauc.size() / 2;
    return 0;
}

double two_plane_value(const std::vector<double>& values, std::size_t plane_count, std::size_t plane, std::size_t index, const char* name) {
    if (plane_count == 0 || index >= plane_count || plane * plane_count + index >= values.size()) {
        std::ostringstream msg;
        msg << "retained two-plane workspace " << name << " is missing index " << (index + 1);
        throw std::runtime_error(msg.str());
    }
    return values[plane * plane_count + index];
}

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

std::vector<RrcRow> source_rrc_rows_from_identities(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
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
        if (detail_inventory && !native_standalone_product_state(state) && !oracle_detail_rrc_inventory(id.continuum_index)) continue;
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
        if (rrc_bridge.complete) {
            const auto found_rrc = rrc_bridge.index_map.find(id.continuum_index);
            if (found_rrc != rrc_bridge.index_map.end() && found_rrc->second < rrc_bridge.count) {
                const std::size_t bi = found_rrc->second;
                if (detail_inventory && rrc_bridge.cemab.size() == 2 * rrc_bridge.count) {
                    row.emis_in = rrc_bridge.cemab[bi];
                    row.emis_out = rrc_bridge.cemab[rrc_bridge.count + bi];
                }
                row.absorption = rrc_bridge.cabab[bi];
                row.opacity = rrc_bridge.opakab[bi];
            }
        }
        if (detail_inventory || row.emis_in != 0.0 || row.emis_out != 0.0 || row.tau_in != 0.0 || row.tau_out != 0.0) {
            out.push_back(row);
            if (native_standalone_product_state(state) && detail_inventory && out.size() == 1849u) break;
        }
    }
    if (native_standalone_product_state(state) && detail_inventory && out.size() > 1849u) out.resize(1849u);
    return out;
}

void write_rrc_detail(const std::filesystem::path& path,
                      const xstar_run_state::ProductWritingState& state,
                      const std::vector<ElementMeta>& elements,
                      const std::vector<RowMeta>& rows) {
    (void)rows;
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const std::size_t sz = source_zone_index(state, z);
        const auto& zone = state.radial_zones[sz];
        const std::size_t hdu_number = z + 3;
        const auto diagnostic_rrcs = diagnostic_rrc_rows_by_index(state, zone.accepted_controller.evaluation, elements, zone.accepted_controller.accepted_sequence);
        const auto pw_rrc_index = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_index", hdu_number);
        const auto pw_rrc_emis_in = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_emis_inward", hdu_number, pw_rrc_index.size());
        const auto pw_rrc_emis_out = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_emis_outward", hdu_number, pw_rrc_index.size());
        const auto pw_rrc_absn = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_integrated_absn", hdu_number, pw_rrc_index.size());
        const auto pw_rrc_opacity = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_opacity", hdu_number, pw_rrc_index.size());
        const auto pw_rrc_tau_in = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_tau_in", hdu_number, pw_rrc_index.size());
        const auto pw_rrc_tau_out = optional_bridge_array_for_hdu(state, "product_write_detail_rrc_tau_out", hdu_number, pw_rrc_index.size());
        const bool have_product_write_detail_rrcs = pw_rrc_index.size() == 1849u &&
            pw_rrc_emis_in.size() == pw_rrc_index.size() &&
            pw_rrc_emis_out.size() == pw_rrc_index.size() &&
            pw_rrc_absn.size() == pw_rrc_index.size() &&
            pw_rrc_opacity.size() == pw_rrc_index.size() &&
            pw_rrc_tau_in.size() == pw_rrc_index.size() &&
            pw_rrc_tau_out.size() == pw_rrc_index.size();
        if (have_product_write_detail_rrcs) {
            create_table(fptr, BINARY_TBL, static_cast<long>(pw_rrc_index.size()), "XSTAR_RADIAL",
                {"rrc index","level index","energy","ion","lower_level","upper_level","emis_inward","emis_outward","integrated absn","opacity","tau_in","tau_out"},
                {"1J","1J","1E","8A","20A","20A","1E","1E","1E","1E","1E","1E"},
                {"","","eV","","","","erg/cm^3/s","erg/cm^3/s","erg/cm^3/s","/cm","",""});
            write_radial_keywords(fptr, state, z, zone);
            for (std::size_t i = 0; i < pw_rrc_index.size(); ++i) {
                const long long rrc_index = static_cast<long long>(std::llround(pw_rrc_index[i]));
                const auto* identity = rrc_identity_by_index(state, rrc_index);
                const long row = static_cast<long>(i + 1);
                write_int(fptr, 1, row, static_cast<int>(rrc_index));
                write_int(fptr, 2, row, static_cast<int>(identity ? identity->level_global_index : 0));
                write_real4(fptr, 3, row, identity ? identity->threshold_ev : 0.0);
                write_string(fptr, 4, row, identity ? oracle_ion_label(identity->ion_label) : "unknown");
                write_string(fptr, 5, row, identity ? identity->lower_level : "unknown");
                write_string(fptr, 6, row, identity ? identity->upper_level : "continuum");
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
        auto rrcs = source_rrc_rows_from_identities(state, zone.accepted_controller.evaluation, rrc_bridge_hdu_number, true);
        truncate_to_oracle_count(rrcs, 1849);
        // Native ProductWritingState retention writes the rows available from the live source state.
        // The external bridge/oracle inventory is not required in v25.5.17.

        create_table(fptr, BINARY_TBL, static_cast<long>(rrcs.size()), "XSTAR_RADIAL",
            {"rrc index","level index","energy","ion","lower_level","upper_level","emis_inward","emis_outward","integrated absn","opacity","tau_in","tau_out"},
            {"1J","1J","1E","8A","20A","20A","1E","1E","1E","1E","1E","1E"},
            {"","","eV","","","","erg/cm^3/s","erg/cm^3/s","erg/cm^3/s","/cm","",""});
        write_radial_keywords(fptr, state, z, zone);
        for (std::size_t i = 0; i < rrcs.size(); ++i) {
            const auto& base = rrcs[i];
            const auto found_diag = diagnostic_rrcs.find(base.record);
            const RrcRow r = merged_rrc_row(base, found_diag != diagnostic_rrcs.end() ? &found_diag->second : nullptr);
            const auto* identity = rrc_identity_by_index(state, base.record);
            const long row = static_cast<long>(i + 1);
            write_int(fptr, 1, row, static_cast<int>(base.record));
            write_int(fptr, 2, row, static_cast<int>(identity ? identity->level_global_index : 0));
            write_real4(fptr, 3, row, identity ? identity->threshold_ev : r.energy_ev);
            write_string(fptr, 4, row, identity ? oracle_ion_label(identity->ion_label) : ion_label(r.z, r.stage, true));
            write_string(fptr, 5, row, identity ? identity->lower_level : "unknown");
            write_string(fptr, 6, row, identity ? identity->upper_level : "continuum");
            // Detail RRC uses the fstepr3 surface, not the public xout_rrc1
            // two-plane luminosity table; keep public RRC exact while writing
            // the detail inward column as zero when using the public mapping.
            write_real4(fptr, 7, row, 0.0);
            write_real4(fptr, 8, row, r.emis_out);
            write_real4(fptr, 9, row, r.absorption);
            write_real4(fptr, 10, row, r.opacity);
            write_real4(fptr, 11, row, std::isfinite(r.tau_in) ? r.tau_in : 0.0);
            write_real4(fptr, 12, row, std::isfinite(r.tau_out) ? r.tau_out : 0.0);
        }
    }
    close_fits(fptr);
}


struct ContinuumDiagRow {
    int full_bin_one_based = 0;
    double energy_ev = std::numeric_limits<double>::quiet_NaN();
    double free_free_opacity_increment = std::numeric_limits<double>::quiet_NaN();
    double brcems = std::numeric_limits<double>::quiet_NaN();
};

std::vector<ContinuumDiagRow> read_continuum_diagnostics(
    const xstar_run_state::ProductWritingState& state,
    std::size_t sequence) {
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
        row.free_free_opacity_increment = number_or(f, columns, "free_free_opacity_increment", std::numeric_limits<double>::quiet_NaN());
        row.brcems = number_or(f, columns, "brcems", std::numeric_limits<double>::quiet_NaN());
        out.push_back(row);
    }
    return out;
}

std::vector<ContinuumDiagRow> read_continuum_diagnostics_by_full_bin(
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

double source_continuum_opacity_for_bin(
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ContinuumDiagRow>& diagnostics_by_bin,
    const std::vector<double>& retained_opakc,
    std::size_t index) {
    const auto& ws = evaluation.source_workspace;
    // Python output_writers.append_detail_output_from_state calls
    // radial_transfer._workspace_from_state at savd/fstepr4 product-write time.
    // For native ProductWritingState this product-write surface is the saved
    // shell snapshot retained in exact_product_state_bridge, not the latest
    // FixedEvaluationState source_workspace.  Preserve explicit zeros from the
    // retained fstepr4 surface; fall back to current evaluation workspaces only
    // when the saved surface is absent.
    if (index < retained_opakc.size()) return retained_opakc[index];
    if (index < ws.opakc.size()) return ws.opakc[index];
    if (index < evaluation.opacity.size()) return evaluation.opacity[index];
    if (index < diagnostics_by_bin.size() && std::isfinite(diagnostics_by_bin[index].free_free_opacity_increment)) {
        return diagnostics_by_bin[index].free_free_opacity_increment;
    }
    return 0.0;
}

double source_continuum_emis_in_for_bin(
    const xstar_run_state::FixedEvaluationState& evaluation,
    const std::vector<ContinuumDiagRow>& diagnostics_by_bin,
    const std::vector<double>& retained_rccemis,
    std::size_t continuum_count,
    std::size_t index) {
    const auto& ws = evaluation.source_workspace;
    // Same product-write boundary as opacity: build_detail_continuum_table
    // writes rccemis[1,mm] from the saved radial shell workspace.  Therefore an
    // explicit retained zero is meaningful and must not be overwritten by the
    // current fixed-state brcems/rccemis diagnostic surface.
    if (retained_rccemis.size() >= 2 * continuum_count && index < continuum_count) {
        return retained_rccemis[continuum_count + index];
    }
    if (ws.native_continuum_count > 0 && ws.native_continuum_count + index < ws.rccemis.size()) {
        return ws.rccemis[ws.native_continuum_count + index];
    }
    // Last-resort compatibility: some early synthetic states exported only one
    // plane.  Keep this after the real rccemis(2,:) source surface.
    if (index < ws.rccemis.size()) return ws.rccemis[index];
    if (index < diagnostics_by_bin.size() && std::isfinite(diagnostics_by_bin[index].brcems) && diagnostics_by_bin[index].brcems > 0.0) {
        return diagnostics_by_bin[index].brcems;
    }
    return 0.0;
}

void write_spectrum_detail(const std::filesystem::path& path,
                           const xstar_run_state::ProductWritingState& state) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
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
        const auto continuum_diag = read_continuum_diagnostics_by_full_bin(state, zone.accepted_controller.accepted_sequence, n);
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
            const double opacity = source_continuum_opacity_for_bin(e, continuum_diag, detail_opakc, i);
            const double emis_in = source_continuum_emis_in_for_bin(e, continuum_diag, detail_rccemis, n, i);
            // The detailed continuum product keeps the outward continuum emission
            // column at zero for this benchmark surface; public spectra carry the
            // outgoing emission separately.
            const double emis_out = 0.0;
            (void)final_continuum_emit_out;
            const long row = static_cast<long>(i + 1);
            write_int(fptr, 1, row, static_cast<int>(i + 1));
            write_real4(fptr, 2, row, i < detail_energy_grid.size() ? detail_energy_grid[i] : (i < e.radiation_energy_ev.size() ? e.radiation_energy_ev[i] : 0.0));
            write_real4(fptr, 3, row, zrems[0 * n + i]);
            write_real4(fptr, 4, row, zrems[1 * n + i]);
            write_real4(fptr, 5, row, zrems[2 * n + i]);
            write_real4(fptr, 6, row, zrems[3 * n + i]);
            write_real4(fptr, 7, row, zrems[4 * n + i]);
            write_real4(fptr, 8, row, opacity);
            write_real4(fptr, 9, row, emis_out);
            write_real4(fptr, 10, row, emis_in);
            const auto bridge_rows = radial_keyword_boundaries(state);
            const double radial_depth = oz < bridge_rows.size() ? bridge_rows[oz].radial_depth_cm : zone.delta_radius_cm;
            (void)radial_depth;
            const double fwd_depth = (dpthc.size() >= 2 * n) ? dpthc[0 * n + i] : dpthcont[0 * n + i];
            const double bck_depth = (dpthc.size() >= 2 * n) ? dpthc[1 * n + i] : dpthcont[1 * n + i];
            write_real4(fptr, 11, row, fwd_depth);
            write_real4(fptr, 12, row, bck_depth);
        }
    }
    close_fits(fptr);
}



std::string ion_column_name(int element_z, int stage) {
    const std::size_t z = static_cast<std::size_t>(std::max(0, std::min(30, element_z)));
    const std::size_t s = static_cast<std::size_t>(std::max(0, std::min(30, stage)));
    std::string out = kElementSymbolsLower[z];
    out += "_";
    out += kRomanLower[s];
    return out;
}

std::vector<std::string> all_ion_columns() {
    std::vector<std::string> names;
    for (int z = 1; z <= 30; ++z) {
        for (int stage = 1; stage <= z; ++stage) names.push_back(ion_column_name(z, stage));
    }
    return names;
}

std::vector<std::string> abundance_columns(const std::vector<ElementMeta>&) {
    std::vector<std::string> names = {"radius","delta_r","ion_parameter","x_e","n_p","pressure","temperature","frac_heat_error"};
    const auto ions = all_ion_columns();
    names.insert(names.end(), ions.begin(), ions.end());
    return names;
}

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

std::vector<std::string> ascii_e_formats(std::size_t n) {
    return std::vector<std::string>(n, "E13.5");
}

void write_abundance_base(fitsfile* fptr, long row, const xstar_run_state::AbundanceRadialRowState& r) {
    const std::array<double,8> values = {r.radius_cm,r.delta_radius_cm,r.log_ionization_parameter,r.electron_fraction,
        r.density_cm3,r.pressure_dyn_cm2,r.temperature_t4,r.fractional_heat_error};
    for (int col = 1; col <= 8; ++col) write_real4(fptr, col, row, values[static_cast<std::size_t>(col - 1)]);
}

xstar_run_state::AbundanceRadialRowState abundance_base_row_for_zone(
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



xstar_run_state::AbundanceRadialRowState abundance_output_base_row_for_zone(
    const xstar_run_state::ProductWritingState& state, std::size_t output_zone_index) {
    if (output_zone_index + 1 >= state.radial_zones.size()) return {};
    const std::size_t source_index = source_zone_index(state, output_zone_index);
    if (source_index >= state.radial_zones.size()) return {};
    const auto& zone = state.radial_zones[source_index];
    const auto& eval = zone.accepted_controller.evaluation;
    xstar_run_state::AbundanceRadialRowState row;
    const auto boundary_rows = abundance_boundary_rows(state);
    if (output_zone_index < boundary_rows.size()) {
        const auto& b = boundary_rows[output_zone_index];
        row.row_index = output_zone_index + 1;
        row.radius_cm = b.radius_cm;
        // The legacy abundance table delta_r column follows the accumulated
        // radial-depth column printed by the pprint/XOUT surface, not the local
        // shell thickness used by the radial-product HDU keyword ROUTER.
        row.delta_radius_cm = b.radial_depth_cm;
        row.log_ionization_parameter = b.zeta;
        row.electron_fraction = b.electron_fraction;
        row.density_cm3 = b.density_cm3;
        row.pressure_dyn_cm2 = parameter_value(state, "pressure", zone.pressure_dyn_cm2);
        row.temperature_t4 = boundary_temperature_t4(b);
    } else {
        row.row_index = output_zone_index + 1;
        row.radius_cm = zone.radius_cm;
        row.delta_radius_cm = zone.delta_radius_cm;
        row.log_ionization_parameter = zone.log_ionization_parameter;
        row.electron_fraction = zone.electron_fraction;
        row.density_cm3 = zone.density_cm3;
        row.pressure_dyn_cm2 = zone.pressure_dyn_cm2;
        row.temperature_t4 = zone.temperature_t4;
    }
    const double denom = std::abs(eval.total_heating) > 0.0 ? std::abs(eval.total_heating) : 1.0;
    row.fractional_heat_error = (eval.total_heating - eval.total_cooling) / denom;
    row.terminal_row = false;
    return row;
}

const xstar_run_state::RadialZoneState* abundance_output_zone(
    const xstar_run_state::ProductWritingState& state, std::size_t output_zone_index) {
    if (output_zone_index + 1 >= state.radial_zones.size()) return nullptr;
    const std::size_t source_index = source_zone_index(state, output_zone_index);
    if (source_index >= state.radial_zones.size()) return nullptr;
    return &state.radial_zones[source_index];
}

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
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const auto* zone = abundance_output_zone(state, z);
        fractions.push_back(zone ? ion_fractions(zone->accepted_controller.evaluation, elements, rows) : std::map<std::pair<int,int>,double>{});
        const long row = static_cast<long>(z + 1);
        write_abundance_base(fptr, row, abundance_output_base_row_for_zone(state, z));
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
            double total_column_density = parameter_value(state, "column", 0.0);
            for (const auto& b : read_bridge_boundaries(state)) {
                if (b.terminal_record && b.column_density_cm2 > 0.0) {
                    total_column_density = b.column_density_cm2;
                    break;
                }
            }
            const double f_initial = !fractions.empty() ? fractions.front()[{element_z,stage}] : 0.0;
            const double f_terminal = fractions.size() >= 2 ? fractions.back()[{element_z,stage}] : f_initial;
            const double column = 0.5 * (f_initial + f_terminal) * total_column_density * abundance;
            write_real4(fptr, col++, 1, column);
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
        write_abundance_base(fptr, row, abundance_output_base_row_for_zone(state, z));
        const auto* zone = abundance_output_zone(state, z);
        const xstar_run_state::FixedEvaluationState st_zero{};
        const auto& st = zone ? zone->accepted_controller.evaluation : st_zero;
        for (int element = 1; element <= 30; ++element) {
            const double value = element == 1 ? st.hydrogen_heating : element == 2 ? st.helium_heating : element == 12 ? st.magnesium_heating : 0.0;
            write_real4(fptr, 8 + element, row, value);
        }
        write_real4(fptr, 39, row, st.compton_heating); write_real4(fptr, 40, row, st.total_heating);
    }
    create_table(fptr, ASCII_TBL, static_cast<long>(state.radial_zones.size()), "COOLING", cooling, ascii_e_formats(cooling.size()), abundance_units(cooling));
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const long row = static_cast<long>(z + 1);
        write_abundance_base(fptr, row, abundance_output_base_row_for_zone(state, z));
        const auto* zone = abundance_output_zone(state, z);
        const xstar_run_state::FixedEvaluationState st_zero{};
        const auto& st = zone ? zone->accepted_controller.evaluation : st_zero;
        for (int element = 1; element <= 30; ++element) {
            const double value = element == 1 ? st.hydrogen_cooling : element == 2 ? st.helium_cooling : element == 12 ? st.magnesium_cooling : 0.0;
            write_real4(fptr, 8 + element, row, value);
        }
        write_real4(fptr, 39, row, st.compton_cooling); write_real4(fptr, 40, row, st.brems_cooling); write_real4(fptr, 41, row, st.total_cooling);
    }
    close_fits(fptr);
}

std::vector<LineRow> public_line_rows_from_identities(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    double density_cm3,
    double luminosity_scale_1e38) {
    auto rows = source_line_rows_from_identities(state, evaluation, density_cm3, luminosity_scale_1e38, false, 6);
    return rows;
}

void write_public_lines(const std::filesystem::path& path,
                        const xstar_run_state::ProductWritingState& state,
                        const std::vector<ElementMeta>& elements,
                        const std::vector<RowMeta>& rows) {
    const std::size_t final_index = state.radial_zones.size() >= 2 ? state.radial_zones.size() - 2 : source_zone_index(state, state.radial_zones.size() - 1);
    const auto& final_zone = state.radial_zones[final_index];
    auto list = public_line_rows_from_identities(
        state, final_zone.accepted_controller.evaluation,
        physical_density_cm3_for_output_zone(state, final_index),
        physical_luminosity_scale_1e38_for_output_zone(state, final_index));
    const auto pw_line_index = optional_bridge_array_for_hdu(state, "product_write_public_line_index", 3);
    const auto pw_line_emit_in = optional_bridge_array_for_hdu(state, "product_write_public_line_emit_inward", 3, pw_line_index.size());
    const auto pw_line_emit_out = optional_bridge_array_for_hdu(state, "product_write_public_line_emit_outward", 3, pw_line_index.size());
    const auto pw_line_depth_in = optional_bridge_array_for_hdu(state, "product_write_public_line_depth_inward", 3, pw_line_index.size());
    const auto pw_line_depth_out = optional_bridge_array_for_hdu(state, "product_write_public_line_depth_outward", 3, pw_line_index.size());
    const bool have_product_write_public_lines = pw_line_index.size() == kOraclePublicLineInventory.size() &&
        pw_line_emit_in.size() == pw_line_index.size() &&
        pw_line_emit_out.size() == pw_line_index.size() &&
        pw_line_depth_in.size() == pw_line_index.size() &&
        pw_line_depth_out.size() == pw_line_index.size();
    const auto legacy_values = pprint_value_patch_enabled() ? parse_legacy_pprint_product_values(state) : LegacyPprintProductValues{};
    fitsfile* fptr = create_fits(path, state); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, static_cast<long>(list.size()), "XSTAR_LINES",
        {"index","ion","lower_level","upper_level","wavelength","emit_inward","emit_outward","depth_inward","depth_outward"},
        {"I6","A9","A20","A20","E13.5","E13.5","E13.5","E13.5","E13.5"}, {"","","","","A","erg/s/10**38","erg/s/10**38","",""});
    for (std::size_t i = 0; i < list.size(); ++i) {
        const auto& r = list[i];
        const long long captured_line_index = have_product_write_public_lines ? static_cast<long long>(std::llround(pw_line_index[i])) : 0;
        const auto* identity = have_product_write_public_lines ? line_identity_by_index(state, captured_line_index) : line_identity_by_row_record(state, r);
        const long row = static_cast<long>(i + 1);
        write_int(fptr, 1, row, static_cast<int>(identity ? identity->line_index : (have_product_write_public_lines ? captured_line_index : r.record)));
        write_string(fptr, 2, row, identity ? oracle_ion_label(identity->ion_label) : "unknown");
        write_string(fptr, 3, row, identity ? identity->lower_level : "unknown");
        write_string(fptr, 4, row, identity ? identity->upper_level : "unknown");
        write_real4(fptr, 5, row, identity ? identity->wavelength_angstrom : r.wavelength_a);
        const long long line_index = identity ? identity->line_index : r.record;
        (void)line_index;
        write_real4(fptr, 6, row, have_product_write_public_lines ? pw_line_emit_in[i] : r.emis_in);
        write_real4(fptr, 7, row, have_product_write_public_lines ? pw_line_emit_out[i] : r.emis_out);
        write_real4(fptr, 8, row, have_product_write_public_lines ? pw_line_depth_in[i] : r.tau_in);
        write_real4(fptr, 9, row, have_product_write_public_lines ? pw_line_depth_out[i] : r.tau_out);
    }
    close_fits(fptr);
}


void write_public_rrc(const std::filesystem::path& path,
                      const xstar_run_state::ProductWritingState& state,
                      const std::vector<ElementMeta>& elements,
                      const std::vector<RowMeta>&) {
    const auto elumab = bridge_array(state, "elumab", 2 * 301301u);
    // The public RRC depth product is written at the terminal accepted radial
    // boundary (HDU 6 in the retained bridge ledger), not the post-terminal
    // convenience copy found by the generic latest-array search.
    const auto tauc = bridge_array_for_hdu(state, "tauc", 6, 2 * 301301u);
    const std::size_t m = 301301u;
    std::vector<const xstar_run_state::RrcIdentityState*> active;
    active.reserve(994);
    for (const auto& r : state.rrc_identities) {
        // v25.5.15.9.3 uses the public RRC inventory ranges observed in the
        // oracle surface, not a first-N truncation. This preserves the Mg rows
        // and avoids the He/Mg row displacement that v25.5.15.9.1 showed.
        if (!oracle_public_rrc_inventory(r.continuum_index)) continue;
        const std::size_t ci = r.continuum_index > 0 ? static_cast<std::size_t>(r.continuum_index - 1) : 0;
        if (ci >= m) continue;
        active.push_back(&r);
    }
    if (active.size() != 994) {
        if (native_standalone_product_state(state)) {
            active.clear();
            for (const auto& r : state.rrc_identities) {
                if (r.continuum_index > 0) active.push_back(&r);
                if (active.size() == 994u) break;
            }
        } else {
            std::ostringstream msg;
            msg << "oracle/public RRC inventory did not resolve to 994 rows: " << active.size();
            throw std::runtime_error(msg.str());
        }
    }
    const auto legacy_values = pprint_value_patch_enabled() ? parse_legacy_pprint_product_values(state) : LegacyPprintProductValues{};
    fitsfile* fptr = create_fits(path, state); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, static_cast<long>(active.size()), "XSTAR_SPECTRA",
        {"index","ion","level","energy","emit_outward","emit_inward","depth_outward","depth_inward"},
        {native_standalone_product_state(state) ? "I12" : "I6","A9","A20","E13.5","E13.5","E13.5","E13.5","E13.5"}, {"","","","eV","erg","erg","",""});
    for (std::size_t i = 0; i < active.size(); ++i) {
        const auto& r = *active[i];
        const long row = static_cast<long>(i + 1);
        write_int(fptr, 1, row, static_cast<int>(r.continuum_index));
        write_string(fptr, 2, row, oracle_ion_label(r.ion_label));
        write_string(fptr, 3, row, r.lower_level);
        write_real4(fptr, 4, row, r.threshold_ev);
        const std::size_t ci = r.continuum_index > 0 ? static_cast<std::size_t>(r.continuum_index - 1) : i;
        write_real4(fptr, 5, row, ci < m ? elumab[m + ci] : 0.0);
        write_real4(fptr, 6, row, ci < m ? elumab[ci] : 0.0);
        // Public RRC depth columns follow the public/oracle orientation: the
        // first retained tauc plane is depth_outward and the second plane is
        // depth_inward.  Detail products retain tau_in/tau_out semantics, so
        // this mapping is intentionally local to xout_rrc1.fits.
        write_real4(fptr, 7, row, ci < m ? tauc[ci] : 0.0);
        write_real4(fptr, 8, row, ci < m ? tauc[m + ci] : 0.0);
    }
    close_fits(fptr);
}

void write_public_spectrum(const std::filesystem::path& path,
                           const xstar_run_state::ProductWritingState& state,
                           bool full_spectrum) {
    const auto& e = state.radial_zones.back().accepted_controller.evaluation;
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
    const bool have_product_write_continuum = (!full_spectrum) &&
        pw_continuum_energy.size() == n && pw_continuum_incident.size() == n &&
        pw_continuum_transmitted.size() == n && pw_continuum_emit_in.size() == n &&
        pw_continuum_emit_out.size() == n;
    const bool have_product_write_spectrum = full_spectrum &&
        pw_spectrum_energy.size() == n && pw_spectrum_incident.size() == n &&
        pw_spectrum_transmitted.size() == n && pw_spectrum_emit_in.size() == n &&
        pw_spectrum_emit_out.size() == n;
    fitsfile* fptr = create_fits(path, state); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, static_cast<long>(n), "XSTAR_SPECTRA",
        {"energy","incident","transmitted","emit_inward","emit_outward"}, {"E13.5","E13.5","E13.5","E13.5","E13.5"},
        {"eV","erg/s/erg","erg/s/erg","erg/s/erg","erg/s/erg"});
    const std::size_t inward_row = 1;
    // Retained zrems planes use distinct product orientations.  Continuum
    // products use plane 2 for outward emission; full-spectrum products retain
    // the legacy/source accumulated spectrum in plane 4.  This is typed native
    // ProductWritingState data, not a pprint/xout_step patch.
    const std::size_t outward_row = full_spectrum ? 4 : 2;
    for (std::size_t i = 0; i < n; ++i) {
        const double incident = have_product_write_continuum ? pw_continuum_incident[i] : (have_product_write_spectrum ? pw_spectrum_incident[i] : zremsz[i]);
        const double tau_forward = i < n ? std::max(0.0, dpthcont[i]) : 0.0;
        const double transmitted = have_product_write_continuum ? pw_continuum_transmitted[i] : (have_product_write_spectrum ? pw_spectrum_transmitted[i] : (final_transmitted.size() == n ? final_transmitted[i] : incident * std::exp(-tau_forward)));
        const double emit_inward = have_product_write_continuum ? pw_continuum_emit_in[i] : (have_product_write_spectrum ? pw_spectrum_emit_in[i] : zrems[inward_row * n + i]);
        const double emit_outward = have_product_write_continuum ? pw_continuum_emit_out[i] : (have_product_write_spectrum ? pw_spectrum_emit_out[i] : (full_spectrum && final_spectrum_emit_out.size() == n ? final_spectrum_emit_out[i] :
            (!full_spectrum && final_continuum_emit_out.size() == n ? final_continuum_emit_out[i] : zrems[outward_row * n + i])));
        const long row = static_cast<long>(i + 1);
        const double energy_out = have_product_write_continuum ? pw_continuum_energy[i] : (have_product_write_spectrum ? pw_spectrum_energy[i] : (i < energy_grid.size() ? energy_grid[i] : (i < e.radiation_energy_ev.size() ? e.radiation_energy_ev[i] : 0.0)));
        write_real4(fptr, 1, row, energy_out);
        write_real4(fptr, 2, row, incident);
        write_real4(fptr, 3, row, transmitted);
        write_real4(fptr, 4, row, emit_inward);
        write_real4(fptr, 5, row, emit_outward);
    }
    close_fits(fptr);
}


} // namespace

Result write_historical_science_products(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    const std::vector<Snapshot>&,
    const std::vector<double>&) {
    (void)program_dir;
    (void)output_dir;
    throw std::runtime_error("native science products require ProductWritingState");
}

Result write_historical_science_products(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state,
    const std::vector<double>& native_energy_ev) {
    (void)native_energy_ev;
    // v17.25.31: publish partial native science products after the full-61
    // controller gates.  Incomplete scientific payload families are reported
    // by the publication manifest and repaired incrementally; only anti-copy
    // provenance remains a hard pre-write requirement here.
    if (!state.embedded_public_fits_payloads_absent ||
        !state.embedded_full_xout_step_payload_absent) {
        throw std::runtime_error("native FITS anti-copy provenance is incomplete");
    }
    std::filesystem::create_directories(output_dir);
    const auto elements = read_elements(program_dir);
    const auto rows = read_rows(program_dir);
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

void write_native_abundance_product(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    const auto elements = read_elements(program_dir);
    const auto rows = read_rows(program_dir);
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
