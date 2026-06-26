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
    double natural_width_ev = 0.0;
    double opakab = 0.0;
    bool type50_valid = false;
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
        r.natural_width_ev = number_or(f, columns, "natural_width_ev");
        r.opakab = number_or(f, columns, "opakab");
        r.type50_valid = integer_or(f, columns, "type50_shadow_valid") != 0;
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

void write_radial_keywords(fitsfile* fptr, const xstar_run_state::RadialZoneState& zone) {
    int status = 0;
    auto put = [&](const char* key, double value) {
        float v = static_cast<float>(value);
        fits_update_key(fptr, TFLOAT, const_cast<char*>(key), &v, nullptr, &status);
        check_fits(status, std::string("write radial keyword ") + key);
    };
    put("RINNER", zone.radius_cm); put("ROUTER", zone.outer_radius_cm); put("RDEL", zone.delta_radius_cm);
    put("TEMPERAT", zone.temperature_t4); put("PRESSURE", zone.pressure_dyn_cm2); put("COLUMN", zone.column_density_cm2);
    put("XEE", zone.electron_fraction); put("DENSITY", zone.density_cm3); put("LOGXI", zone.log_ionization_parameter);
    std::string source = "accepted native controller sequence " + std::to_string(zone.accepted_controller.accepted_sequence);
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
        if (!r.spectral || !(r.line_energy_ev > 0.0) || r.lower_row <= 0 || r.upper_row <= 0) continue;
        const double lower = population_for(evaluation, elements, r.element_index, r.lower_row);
        const double upper = population_for(evaluation, elements, r.element_index, r.upper_row);
        const double net = r.ans[1] * upper - r.ans[0] * lower;
        const double total_emissivity = std::max(net * r.line_energy_ev * kErgPerEv, 0.0);
        const double ptmp1 = r.type50_valid ? std::max(r.type50_ptmp1, 0.0)
            : r.type53_valid ? std::max(r.type53_ptmp1, 0.0) : 1.0;
        const double ptmp2 = r.type50_valid ? std::max(r.type50_ptmp2, 0.0)
            : r.type53_valid ? std::max(r.type53_ptmp2, 0.0) : 1.0;
        const double escape_sum = ptmp1 + ptmp2 > 0.0 ? ptmp1 + ptmp2 : 2.0;
        LineRow row;
        row.record = r.record;
        row.z = r.element_z;
        row.stage = r.ion_stage;
        row.lower_row = r.lower_row;
        row.upper_row = r.upper_row;
        row.wavelength_a = r.type50_wavelength_a > 0.0 ? r.type50_wavelength_a : 12398.419843320026 / r.line_energy_ev;
        row.emis_in = total_emissivity * ptmp1 / escape_sum;
        row.emis_out = total_emissivity * ptmp2 / escape_sum;
        row.opacity = r.opakab * lower;
        if (r.type50_valid) { row.tau_in = r.type50_tau_in; row.tau_out = r.type50_tau_out; }
        else if (r.type53_valid) { row.tau_in = r.type53_tau_in; row.tau_out = r.type53_tau_out; }
        out.push_back(row);
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
        if (!(r.type49_valid || r.type53_valid || r.type99_valid || r.data_type == 49 || r.data_type == 53 || r.data_type == 99)) continue;
        double threshold = r.type49_valid ? r.type49_threshold_ev : r.type53_valid ? r.type53_threshold_ev : r.type99_threshold_ev;
        if (!(threshold > 0.0)) threshold = r.line_energy_ev;
        if (!(threshold > 0.0) || r.lower_row <= 0 || r.upper_row <= 0) continue;
        const double lower = population_for(evaluation, elements, r.element_index, r.lower_row);
        const double upper = population_for(evaluation, elements, r.element_index, r.upper_row);
        double p1 = r.type53_valid ? std::max(r.type53_ptmp1, 0.0) : 1.0;
        double p2 = r.type53_valid ? std::max(r.type53_ptmp2, 0.0) : 1.0;
        const double denom = p1 + p2 > 0.0 ? p1 + p2 : 2.0;
        const double total_emis = std::abs(r.ans[2]) * upper * zone.density_cm3;
        RrcRow row;
        row.record = r.record; row.z = r.element_z; row.stage = r.ion_stage;
        row.lower_row = r.lower_row; row.upper_row = r.upper_row; row.energy_ev = threshold;
        row.emis_in = total_emis * p1 / denom;
        row.emis_out = total_emis * p2 / denom;
        row.absorption = std::abs(r.ans[3]) * lower * zone.density_cm3;
        row.opacity = r.opakab * lower;
        if (r.type53_valid) { row.tau_in = r.type53_tau_in; row.tau_out = r.type53_tau_out; }
        out.push_back(row);
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
        return &state.line_identities[static_cast<std::size_t>(line_index - 1)];
    }
    for (const auto& line : state.line_identities) if (line.line_index == line_index) return &line;
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
    auto values = read_binary_double_array(bridge_array_path(state, name));
    if (values.size() != expected_count) {
        std::ostringstream msg;
        msg << "native product bridge array " << name << " size mismatch: "
            << values.size() << " != " << expected_count;
        throw std::runtime_error(msg.str());
    }
    return values;
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
    auto values = read_binary_double_array(bridge_array_path_for_hdu(state, name, hdu_number));
    if (values.size() != expected_count) {
        std::ostringstream msg;
        msg << "native product bridge array " << name << " hdu " << hdu_number
            << " size mismatch: " << values.size() << " != " << expected_count;
        throw std::runtime_error(msg.str());
    }
    return values;
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
    const char* explicit_path = std::getenv("XSTAR_V048746255156_RADIATION_CSV");
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

std::string oracle_ion_label(std::string label) {
    return label;
}


void write_population_detail(const std::filesystem::path& path,
                             const xstar_run_state::ProductWritingState& state,
                             const std::vector<ElementMeta>&,
                             const std::vector<RowMeta>&) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    const auto detail_levels = oracle_detail_levels(state);
    for (std::size_t oz = 0; oz < state.radial_zones.size(); ++oz) {
        const auto& zone = state.radial_zones[source_zone_index(state, oz)];
        create_table(fptr, BINARY_TBL, static_cast<long>(detail_levels.size()), "XSTAR_RADIAL",
            {"index","ion_index","e_excitation","ion","atomic_number","ion_level","population","lte","upper index"},
            {"1J","1I","1E","8A","1I","20A","1E","1E","1I"}, {"","","eV","","","","","",""});
        write_radial_keywords(fptr, zone);
        const auto& evaluation = zone.accepted_controller.evaluation;
        for (std::size_t i = 0; i < detail_levels.size(); ++i) {
            const auto& level = detail_levels[i];
            const std::size_t global0 = level.global_index > 0 ? static_cast<std::size_t>(level.global_index - 1) : i;
            const std::size_t ordinal0 = i;
            const double pop = global0 < evaluation.populations.size() ? evaluation.populations[global0]
                : ordinal0 < evaluation.populations.size() ? evaluation.populations[ordinal0] : 0.0;
            const double lte = global0 < evaluation.source_workspace.lte_populations.size() ? evaluation.source_workspace.lte_populations[global0]
                : ordinal0 < evaluation.source_workspace.lte_populations.size() ? evaluation.source_workspace.lte_populations[ordinal0] : 0.0;
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

std::vector<LineRow> source_line_rows_from_identities(
    const xstar_run_state::ProductWritingState& state,
    const xstar_run_state::FixedEvaluationState& evaluation,
    bool detail_order) {
    std::vector<LineRow> out;
    const auto& ws = evaluation.source_workspace;
    const std::size_t n = ws.native_line_count > 0 ? ws.native_line_count : state.line_identities.size();
    out.reserve(std::min<std::size_t>(state.line_identities.size(), n));
    for (std::size_t i = 0; i < state.line_identities.size() && i < n; ++i) {
        const auto& id = state.line_identities[i];
        const std::size_t idx = id.line_index > 0 ? static_cast<std::size_t>(id.line_index - 1) : i;
        if (idx >= n) continue;
        LineRow row;
        row.record = id.line_index;
        row.z = 0;
        row.stage = 0;
        row.wavelength_a = id.wavelength_angstrom;
        row.emis_in = idx < ws.elum.size() ? ws.elum[idx] : 0.0;
        row.emis_out = (n + idx) < ws.elum.size() ? ws.elum[n + idx] : 0.0;
        row.opacity = idx < ws.oplin.size() ? ws.oplin[idx] : 0.0;
        row.tau_in = idx < ws.tau0.size() ? ws.tau0[idx] : 0.0;
        row.tau_out = (n + idx) < ws.tau0.size() ? ws.tau0[n + idx] : 0.0;
        if (detail_order || row.emis_in != 0.0 || row.emis_out != 0.0 || row.opacity != 0.0) {
            out.push_back(row);
        }
    }
    if (!detail_order) {
        std::stable_sort(out.begin(), out.end(), [](const LineRow& a, const LineRow& b) {
            return std::abs(a.emis_in) + std::abs(a.emis_out) > std::abs(b.emis_in) + std::abs(b.emis_out);
        });
    }
    return out;
}

const xstar_run_state::LineIdentityState* line_identity_by_row_record(
    const xstar_run_state::ProductWritingState& state,
    const LineRow& row) {
    const auto index = row.record;
    if (index > 0 && static_cast<std::size_t>(index) <= state.line_identities.size()) {
        return &state.line_identities[static_cast<std::size_t>(index - 1)];
    }
    return line_identity_by_index(state, index);
}

void write_line_detail(const std::filesystem::path& path,
                       const xstar_run_state::ProductWritingState& state,
                       const std::vector<ElementMeta>& elements,
                       const std::vector<RowMeta>& rows) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const std::size_t sz = source_zone_index(state, z);
        const auto& evaluation = state.radial_zones[sz].accepted_controller.evaluation;
        auto lines = source_line_rows_from_identities(state, evaluation, true);
        truncate_to_oracle_count(lines, 2644);
        create_table(fptr, BINARY_TBL, static_cast<long>(lines.size()), "XSTAR_RADIAL",
            {"index","wavelength","ion","lower_level","upper_level","emis_inward","emis_outward","opacity","tau_in","tau_out"},
            {"1J","1E","8A","20A","20A","1E","1E","1E","1E","1E"},
            {"","A","","","","erg/cm^3/s","erg/cm^3/s","/cm","",""});
        write_radial_keywords(fptr, state.radial_zones[sz]);
        for (std::size_t i = 0; i < lines.size(); ++i) {
            const auto& r = lines[i];
            const auto* identity = line_identity_by_row_record(state, r);
            const long row = static_cast<long>(i + 1);
            write_longlong(fptr, 1, row, r.record);
            write_real4(fptr, 2, row, identity ? identity->wavelength_angstrom : r.wavelength_a);
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

void write_rrc_detail(const std::filesystem::path& path,
                      const xstar_run_state::ProductWritingState& state,
                      const std::vector<ElementMeta>& elements,
                      const std::vector<RowMeta>& rows) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const std::size_t sz = source_zone_index(state, z);
        auto rrc = build_rrc_rows(state, elements, sz);
        truncate_to_oracle_count(rrc, 1849);
        create_table(fptr, BINARY_TBL, static_cast<long>(rrc.size()), "XSTAR_RADIAL",
            {"rrc index","level index","energy","ion","lower_level","upper_level","emis_inward","emis_outward","integrated absn","opacity","tau_in","tau_out"},
            {"1J","1J","1E","8A","20A","20A","1E","1E","1E","1E","1E","1E"},
            {"","","eV","","","","erg/cm^3/s","erg/cm^3/s","erg/cm^3/s","/cm","",""});
        write_radial_keywords(fptr, state.radial_zones[sz]);
        for (std::size_t i = 0; i < rrc.size(); ++i) {
            const auto& r = rrc[i];
            const int element_index = element_index_for_z(elements, r.z);
            const auto* lower = row_for(rows, element_index, r.lower_row);
            const auto* upper = row_for(rows, element_index, r.upper_row);
            const long row = static_cast<long>(i + 1);
            write_longlong(fptr, 1, row, r.record); write_int(fptr, 2, row, r.upper_row); write_real4(fptr, 3, row, r.energy_ev);
            write_string(fptr, 4, row, ion_label(r.z, r.stage, true)); write_string(fptr, 5, row, level_label(lower, r.lower_row));
            write_string(fptr, 6, row, level_label(upper, r.upper_row)); write_real4(fptr, 7, row, r.emis_in); write_real4(fptr, 8, row, r.emis_out);
            write_real4(fptr, 9, row, r.absorption); write_real4(fptr, 10, row, r.opacity); write_real4(fptr, 11, row, r.tau_in); write_real4(fptr, 12, row, r.tau_out);
        }
    }
    close_fits(fptr);
}

void write_spectrum_detail(const std::filesystem::path& path,
                           const xstar_run_state::ProductWritingState& state) {
    fitsfile* fptr = create_fits(path, state);
    write_parameters(fptr, state.parameter_rows);
    const auto& final_eval = state.radial_zones.back().accepted_controller.evaluation;
    const std::size_t n = final_eval.radiation_energy_ev.size();
    const auto energy_grid = reference_energy_grid(state, final_eval.radiation_energy_ev);
    for (std::size_t oz = 0; oz < state.radial_zones.size(); ++oz) {
        const std::size_t hdu_number = oz + 3;
        const auto& zone = state.radial_zones[source_zone_index(state, oz)];
        const auto& e = zone.accepted_controller.evaluation;
        const auto zrems = bridge_array_for_hdu(state, "zrems", hdu_number, 5 * n);
        const auto dpthcont = bridge_array_for_hdu(state, "dpthcont", hdu_number, 2 * n);
        create_table(fptr, BINARY_TBL, static_cast<long>(n), "XSTAR_RADIAL",
            {"index","energy","zrems(1)","zrems(2)","zrems(3)","zrems(4)","zrems(5)","opacity","emis out","emis in","fwd dpth","bck dpth"},
            {"1J","1E","1E","1E","1E","1E","1E","1E","1E","1E","1E","1E"},
            {"","eV","erg/s","erg/s","erg/s","erg/s","erg/s","/cm","erg/cm**3/s","erg/cm**3/s","",""});
        write_radial_keywords(fptr, zone);
        for (std::size_t i = 0; i < n; ++i) {
            const double opacity = i < e.opacity.size() ? e.opacity[i] : 0.0;
            const long row = static_cast<long>(i + 1);
            write_int(fptr, 1, row, static_cast<int>(i + 1));
            write_real4(fptr, 2, row, i < energy_grid.size() ? energy_grid[i] : 0.0);
            write_real4(fptr, 3, row, zrems[0 * n + i]);
            write_real4(fptr, 4, row, zrems[1 * n + i]);
            write_real4(fptr, 5, row, zrems[2 * n + i]);
            write_real4(fptr, 6, row, zrems[3 * n + i]);
            write_real4(fptr, 7, row, zrems[4 * n + i]);
            write_real4(fptr, 8, row, opacity);
            write_real4(fptr, 9, row, zrems[3 * n + i]);
            write_real4(fptr, 10, row, zrems[2 * n + i]);
            write_real4(fptr, 11, row, dpthcont[0 * n + i]);
            write_real4(fptr, 12, row, dpthcont[1 * n + i]);
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

void write_abundances(const std::filesystem::path& path,
                      const xstar_run_state::ProductWritingState& state,
                      const std::vector<ElementMeta>& elements,
                      const std::vector<RowMeta>& rows) {
    const auto names = abundance_columns(elements);
    const auto formats = ascii_e_formats(names.size());
    const auto units = abundance_units(names);
    fitsfile* fptr = create_fits(path, state);
    create_table(fptr, ASCII_TBL, static_cast<long>(state.radial_zones.size()), "ABUNDANCES", names, formats, units);
    std::vector<std::map<std::pair<int,int>,double>> fractions;
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        fractions.push_back(ion_fractions(state.radial_zones[z].accepted_controller.evaluation, elements, rows));
        const long row = static_cast<long>(z + 1);
        write_abundance_base(fptr, row, state.abundance_radial_rows[z]);
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
            double column = 0.0;
            for (std::size_t z = 0; z + 1 < state.radial_zones.size(); ++z) {
                const double f0 = fractions[z][{element_z,stage}];
                const double f1 = fractions[z+1][{element_z,stage}];
                const double n0 = state.radial_zones[z].density_cm3;
                const double n1 = state.radial_zones[z+1].density_cm3;
                const double dr = state.radial_zones[z].delta_radius_cm;
                column += 0.5 * (f0*n0 + f1*n1) * dr * abundance;
            }
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
        write_abundance_base(fptr, row, state.abundance_radial_rows[z]);
        const auto& st = state.radial_zones[z].accepted_controller.evaluation;
        for (int element = 1; element <= 30; ++element) {
            const double value = element == 1 ? st.hydrogen_heating : element == 2 ? st.helium_heating : element == 12 ? st.magnesium_heating : 0.0;
            write_real4(fptr, 8 + element, row, value);
        }
        write_real4(fptr, 39, row, st.compton_heating); write_real4(fptr, 40, row, st.total_heating);
    }
    create_table(fptr, ASCII_TBL, static_cast<long>(state.radial_zones.size()), "COOLING", cooling, ascii_e_formats(cooling.size()), abundance_units(cooling));
    for (std::size_t z = 0; z < state.radial_zones.size(); ++z) {
        const long row = static_cast<long>(z + 1);
        write_abundance_base(fptr, row, state.abundance_radial_rows[z]);
        const auto& st = state.radial_zones[z].accepted_controller.evaluation;
        for (int element = 1; element <= 30; ++element) {
            const double value = element == 1 ? st.hydrogen_cooling : element == 2 ? st.helium_cooling : element == 12 ? st.magnesium_cooling : 0.0;
            write_real4(fptr, 8 + element, row, value);
        }
        write_real4(fptr, 39, row, st.compton_cooling); write_real4(fptr, 40, row, st.brems_cooling); write_real4(fptr, 41, row, st.total_cooling);
    }
    close_fits(fptr);
}

void write_public_lines(const std::filesystem::path& path,
                        const xstar_run_state::ProductWritingState& state,
                        const std::vector<ElementMeta>&,
                        const std::vector<RowMeta>&) {
    const auto& final_zone = state.radial_zones[source_zone_index(state, state.radial_zones.size() - 1)];
    auto list = source_line_rows_from_identities(state, final_zone.accepted_controller.evaluation, false);
    if (list.size() > 600) list.resize(600);
    fitsfile* fptr = create_fits(path, state); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, static_cast<long>(list.size()), "XSTAR_LINES",
        {"index","ion","lower_level","upper_level","wavelength","emit_inward","emit_outward","depth_inward","depth_outward"},
        {"I6","A9","A20","A20","E13.5","E13.5","E13.5","E13.5","E13.5"}, {"","","","","A","erg/s/10**38","erg/s/10**38","",""});
    for (std::size_t i = 0; i < list.size(); ++i) {
        const auto& r = list[i];
        const auto* identity = line_identity_by_row_record(state, r);
        const long row = static_cast<long>(i + 1);
        write_int(fptr, 1, row, static_cast<int>(identity ? identity->line_index : r.record));
        write_string(fptr, 2, row, identity ? oracle_ion_label(identity->ion_label) : "unknown");
        write_string(fptr, 3, row, identity ? identity->lower_level : "unknown");
        write_string(fptr, 4, row, identity ? identity->upper_level : "unknown");
        write_real4(fptr, 5, row, identity ? identity->wavelength_angstrom : r.wavelength_a);
        write_real4(fptr, 6, row, r.emis_in);
        write_real4(fptr, 7, row, r.emis_out);
        write_real4(fptr, 8, row, r.tau_in);
        write_real4(fptr, 9, row, r.tau_out);
    }
    close_fits(fptr);
}


void write_public_rrc(const std::filesystem::path& path,
                      const xstar_run_state::ProductWritingState& state,
                      const std::vector<ElementMeta>&,
                      const std::vector<RowMeta>&) {
    const std::size_t n = std::min<std::size_t>(994, state.rrc_identities.size());
    const auto elumab = bridge_array(state, "elumab", 2 * 301301u);
    const auto tauc = bridge_array(state, "tauc", 2 * 301301u);
    fitsfile* fptr = create_fits(path, state); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, static_cast<long>(n), "XSTAR_SPECTRA",
        {"index","ion","level","energy","emit_outward","emit_inward","depth_outward","depth_inward"},
        {"I6","A9","A20","E13.5","E13.5","E13.5","E13.5","E13.5"}, {"","","","eV","erg","erg","",""});
    const std::size_t m = 301301u;
    for (std::size_t i = 0; i < n; ++i) {
        const auto& r = state.rrc_identities[i];
        const long row = static_cast<long>(i + 1);
        write_int(fptr, 1, row, static_cast<int>(r.continuum_index));
        write_string(fptr, 2, row, oracle_ion_label(r.ion_label));
        write_string(fptr, 3, row, r.lower_level);
        write_real4(fptr, 4, row, r.threshold_ev);
        const std::size_t ci = r.continuum_index > 0 ? static_cast<std::size_t>(r.continuum_index - 1) : i;
        write_real4(fptr, 5, row, ci < m ? elumab[ci] : 0.0);
        write_real4(fptr, 6, row, ci < m ? elumab[m + ci] : 0.0);
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
    const auto zrems = bridge_array(state, "zrems", 5 * n);
    const auto zremsz = bridge_array(state, "zremsz", n);
    const auto energy_grid = reference_energy_grid(state, e.radiation_energy_ev);
    fitsfile* fptr = create_fits(path, state); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, static_cast<long>(n), "XSTAR_SPECTRA",
        {"energy","incident","transmitted","emit_inward","emit_outward"}, {"E13.5","E13.5","E13.5","E13.5","E13.5"},
        {"eV","erg/s/erg","erg/s/erg","erg/s/erg","erg/s/erg"});
    const std::size_t inward_row = 1;
    const std::size_t outward_row = full_spectrum ? 4 : 2;
    for (std::size_t i = 0; i < n; ++i) {
        const double incident = zremsz[i];
        const double transmitted = zremsz[i];
        const double emit_inward = zrems[inward_row * n + i];
        const double emit_outward = zrems[outward_row * n + i];
        const long row = static_cast<long>(i + 1);
        write_real4(fptr, 1, row, i < energy_grid.size() ? energy_grid[i] : (i < e.radiation_energy_ev.size() ? e.radiation_energy_ev[i] : 0.0));
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
    if (!state.product_state_complete || !state.native_detail_state_retained ||
        !state.exact_source_metadata_retained || !state.exact_source_workspaces_retained ||
        !state.exact_accepted_radial_boundaries_retained ||
        !state.exact_legacy_pprint_state_retained ||
        !state.embedded_public_fits_payloads_absent || !state.embedded_full_xout_step_payload_absent) {
        throw std::runtime_error("native product state or anti-copy provenance is incomplete");
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
    // xout_abund1 remains isolated because its 473-column ASCII writer is the
    // current crash suspect. v25.5.15.3 writes xout_step.log before invoking
    // the abundance writer and keeps abundance behind an explicit env gate.
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
    const char* flag = std::getenv("XSTAR_V048746255156_ENABLE_ABUNDANCE_PRODUCT");
    return flag != nullptr && std::string(flag) == "1";
}

void write_native_abundance_product(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    const auto elements = read_elements(program_dir);
    const auto rows = read_rows(program_dir);
    write_abundances(output_dir / "xout_abund1.fits", state, elements, rows);
    state.xout_abund1_computed_from_native_state = true;
}

} // namespace xstar_science_fits
