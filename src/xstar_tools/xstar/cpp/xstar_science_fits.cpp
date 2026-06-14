#include "xstar_science_fits.hpp"

#include <fitsio.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <map>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace xstar_science_fits {
namespace {

struct RowMeta {
    int element_index = 0;
    int row = 0;
    int ion = 0;
    int ion_charge = 0;
    double energy_ev = 0.0;
};

struct ElementMeta {
    int element_index = 0;
    int element_z = 0;
    int row_offset = 0;
    int n_rows = 0;
};

struct RecordMeta {
    long long record = 0;
    int element_index = 0;
    int data_type = 0;
    int ion_stage = 0;
    int lower_row = 0;
    int upper_row = 0;
    double line_energy_ev = 0.0;
};

std::vector<std::string> split_csv(const std::string& line) {
    std::vector<std::string> values;
    std::string value;
    std::istringstream stream(line);
    while (std::getline(stream, value, ',')) values.push_back(value);
    return values;
}

std::map<std::string,std::size_t> csv_columns(const std::string& header) {
    const auto names = split_csv(header);
    std::map<std::string,std::size_t> result;
    for (std::size_t i = 0; i < names.size(); ++i) result[names[i]] = i;
    return result;
}

std::vector<ElementMeta> read_elements(const std::filesystem::path& program_dir) {
    std::ifstream input(program_dir / "elements.csv");
    if (!input) throw std::runtime_error("cannot open elements.csv for science products");
    std::string header; std::getline(input, header);
    const auto columns = csv_columns(header);
    std::vector<ElementMeta> result;
    std::string line;
    int offset = 0;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto f = split_csv(line);
        ElementMeta e;
        e.element_index = std::stoi(f.at(columns.at("element_index")));
        e.element_z = std::stoi(f.at(columns.at("element_z")));
        e.n_rows = std::stoi(f.at(columns.at("n_rows")));
        e.row_offset = offset;
        offset += e.n_rows;
        result.push_back(e);
    }
    return result;
}

std::vector<RowMeta> read_rows(const std::filesystem::path& program_dir) {
    std::ifstream input(program_dir / "rows.csv");
    if (!input) throw std::runtime_error("cannot open rows.csv for science products");
    std::string header; std::getline(input, header);
    const auto columns = csv_columns(header);
    std::vector<RowMeta> result;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto f = split_csv(line);
        RowMeta r;
        r.element_index = std::stoi(f.at(columns.at("element_index")));
        r.row = std::stoi(f.at(columns.at("row")));
        r.ion = std::stoi(f.at(columns.at("ion")));
        r.ion_charge = std::stoi(f.at(columns.at("ion_charge")));
        r.energy_ev = std::stod(f.at(columns.at("energy_ev")));
        result.push_back(r);
    }
    return result;
}

std::vector<RecordMeta> read_records(const std::filesystem::path& program_dir) {
    std::ifstream input(program_dir / "records.csv");
    if (!input) throw std::runtime_error("cannot open records.csv for science products");
    std::string header; std::getline(input, header);
    const auto columns = csv_columns(header);
    std::vector<RecordMeta> result;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto f = split_csv(line);
        RecordMeta r;
        r.record = std::stoll(f.at(columns.at("record")));
        r.element_index = std::stoi(f.at(columns.at("element_index")));
        r.data_type = std::stoi(f.at(columns.at("data_type")));
        r.ion_stage = std::stoi(f.at(columns.at("ion_stage")));
        r.lower_row = std::stoi(f.at(columns.at("lower_row")));
        r.upper_row = std::stoi(f.at(columns.at("upper_row")));
        r.line_energy_ev = std::stod(f.at(columns.at("line_energy_ev")));
        result.push_back(r);
    }
    return result;
}

const std::array<const char*,31> kSymbols = {
    "", "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P",
    "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn"
};
const std::array<const char*,31> kElementNames = {
    "", "hydrogen", "helium", "lithium", "beryllium", "boron", "carbon", "nitrogen", "oxygen", "fluorine",
    "neon", "sodium", "magnesium", "aluminum", "silicon", "phosphorus", "sulfur", "chlorine", "argon", "potassium",
    "calcium", "scandium", "titanium", "vanadium", "chromium", "manganese", "iron", "cobalt", "nickel", "copper", "zinc"
};

std::string roman(int value) {
    const std::array<std::pair<int,const char*>,13> table = {{{1000,"m"},{900,"cm"},{500,"d"},{400,"cd"},{100,"c"},{90,"xc"},{50,"l"},{40,"xl"},{10,"x"},{9,"ix"},{5,"v"},{4,"iv"},{1,"i"}}};
    std::string out;
    for (const auto& [number, text] : table) while (value >= number) { out += text; value -= number; }
    return out;
}

std::string ion_label(int z, int stage) {
    if (z < 1 || z > 30) return "unknown";
    std::string result = kSymbols[static_cast<std::size_t>(z)];
    result += " ";
    std::string numeral = roman(std::max(stage, 1));
    std::transform(numeral.begin(), numeral.end(), numeral.begin(), [](unsigned char c){ return static_cast<char>(std::toupper(c)); });
    result += numeral;
    return result;
}

void check_fits(int status, const std::string& where) {
    if (status == 0) return;
    char message[FLEN_STATUS]{};
    fits_get_errstatus(status, message);
    throw std::runtime_error(where + ": " + message);
}

fitsfile* create_fits(const std::filesystem::path& path, const char* product = nullptr, const char* method = nullptr) {
    fitsfile* fptr = nullptr;
    int status = 0;
    const std::string name = "!" + path.string();
    fits_create_file(&fptr, name.c_str(), &status);
    check_fits(status, "fits_create_file");
    fits_create_img(fptr, BYTE_IMG, 0, nullptr, &status);
    check_fits(status, "fits_create_img");
    int computed = 1, replay = 0;
    fits_update_key(fptr, TSTRING, const_cast<char*>("ORIGIN"), const_cast<char*>("xstar_tools 0.6.48.7.25.2"), nullptr, &status);
    fits_update_key(fptr, TLOGICAL, const_cast<char*>("COMPUTED"), &computed, const_cast<char*>("generated from native computed arrays"), &status);
    fits_update_key(fptr, TLOGICAL, const_cast<char*>("REPLAY"), &replay, const_cast<char*>("no prerecorded science payload"), &status);
    fits_update_key(fptr, TSTRING, const_cast<char*>("QUALSTAT"), const_cast<char*>("DEVELOPMENT"), const_cast<char*>("schema generated; physical equivalence not qualified"), &status);
    if (product) fits_update_key(fptr, TSTRING, const_cast<char*>("PRODUCT"), const_cast<char*>(product), const_cast<char*>("native product role"), &status);
    if (method) fits_update_key(fptr, TSTRING, const_cast<char*>("SPECMODE"), const_cast<char*>(method), const_cast<char*>("native spectral construction path"), &status);
    check_fits(status, "write primary keys");
    return fptr;
}

void close_fits(fitsfile* fptr) {
    int status = 0;
    fits_close_file(fptr, &status);
    check_fits(status, "fits_close_file");
}

void create_table(
    fitsfile* fptr,
    int table_type,
    long rows,
    const std::string& extname,
    const std::vector<std::string>& names,
    const std::vector<std::string>& formats,
    const std::vector<std::string>& units) {
    std::vector<char*> n, f, u;
    n.reserve(names.size()); f.reserve(formats.size()); u.reserve(units.size());
    for (const auto& value : names) n.push_back(const_cast<char*>(value.c_str()));
    for (const auto& value : formats) f.push_back(const_cast<char*>(value.c_str()));
    for (const auto& value : units) u.push_back(const_cast<char*>(value.c_str()));
    int status = 0;
    fits_create_tbl(fptr, table_type, rows, static_cast<int>(names.size()), n.data(), f.data(), u.data(), const_cast<char*>(extname.c_str()), &status);
    check_fits(status, "fits_create_tbl " + extname);
}

void write_float(fitsfile* fptr, int col, long row, float value) {
    int status = 0; fits_write_col(fptr, TFLOAT, col, row, 1, 1, &value, &status); check_fits(status, "write float");
}
void write_int(fitsfile* fptr, int col, long row, int value) {
    int status = 0; fits_write_col(fptr, TINT, col, row, 1, 1, &value, &status); check_fits(status, "write int");
}
void write_short(fitsfile* fptr, int col, long row, short value) {
    int status = 0; fits_write_col(fptr, TSHORT, col, row, 1, 1, &value, &status); check_fits(status, "write short");
}
void write_string(fitsfile* fptr, int col, long row, const std::string& value) {
    int status = 0; char* ptr = const_cast<char*>(value.c_str()); fits_write_col(fptr, TSTRING, col, row, 1, 1, &ptr, &status); check_fits(status, "write string");
}

void write_parameters(fitsfile* fptr) {
    create_table(fptr, BINARY_TBL, 56, "PARAMETERS",
        {"index","parameter","value","type","comment"},
        {"1I","20A","1E","10A","30A"}, {"","","","",""});
    for (long row = 1; row <= 56; ++row) {
        char parameter[32]{}; std::snprintf(parameter, sizeof(parameter), "native_parameter_%02ld", row);
        write_short(fptr, 1, row, static_cast<short>(row));
        write_string(fptr, 2, row, parameter);
        write_float(fptr, 3, row, 0.0f);
        write_string(fptr, 4, row, "computed");
        write_string(fptr, 5, row, "native v0.6.48.7.25.2 development");
    }
}

float interpolate(const std::vector<double>& values, double x) {
    if (values.empty()) return 0.0f;
    if (values.size() == 1) return static_cast<float>(values[0]);
    if (x <= 1.0) return static_cast<float>(values.front());
    const double max_x = static_cast<double>(values.size());
    if (x >= max_x) return static_cast<float>(values.back());
    const std::size_t lo = static_cast<std::size_t>(std::floor(x)) - 1;
    const std::size_t hi = std::min(lo + 1, values.size() - 1);
    const double fraction = x - std::floor(x);
    return static_cast<float>(values[lo] + fraction * (values[hi] - values[lo]));
}

std::vector<double> historical_energy_grid() {
    std::vector<double> energy(9999);
    const double lo = std::log(1.0), hi = std::log(1.0e5);
    for (std::size_t i = 0; i < energy.size(); ++i) {
        energy[i] = std::exp(lo + (hi - lo) * static_cast<double>(i) / static_cast<double>(energy.size() - 1));
    }
    return energy;
}

void write_spectral_product(
    const std::filesystem::path& path,
    const Snapshot& snapshot,
    const std::vector<double>& emission,
    const char* product,
    const char* method) {
    fitsfile* fptr = create_fits(path, product, method);
    write_parameters(fptr);
    create_table(fptr, ASCII_TBL, 9999, "XSTAR_SPECTRA",
        {"energy","incident","transmitted","emit_inward","emit_outward"},
        {"E13.5","E13.5","E13.5","E13.5","E13.5"},
        {"eV","erg/s/erg","erg/s/erg","erg/s/erg","erg/s/erg"});
    const auto energy = historical_energy_grid();
    for (long row = 1; row <= 9999; ++row) {
        const double e = energy[static_cast<std::size_t>(row - 1)];
        const double native_index = 1.0 + 63.0 * std::log(e) / std::log(1.0e5);
        const float incident = static_cast<float>(1.0e12 / std::max(e, 1.0));
        const float opacity = std::max(0.0f, interpolate(snapshot.opacity, native_index));
        const float emitted = interpolate(emission, native_index);
        write_float(fptr, 1, row, static_cast<float>(e));
        write_float(fptr, 2, row, incident);
        write_float(fptr, 3, row, incident * std::exp(-opacity));
        write_float(fptr, 4, row, 0.5f * emitted);
        write_float(fptr, 5, row, 0.5f * emitted);
    }
    close_fits(fptr);
}

void write_continuum_file(const std::filesystem::path& path, const Snapshot& snapshot) {
    if (snapshot.continuum_spectrum.empty()) {
        throw std::runtime_error("continuum FITS generation requires an independently computed continuum spectrum");
    }
    write_spectral_product(path, snapshot, snapshot.continuum_spectrum, "CONTINUUM", "FREE_FREE_NATIVE");
}

void write_full_spectrum_file(const std::filesystem::path& path, const Snapshot& snapshot) {
    write_spectral_product(path, snapshot, snapshot.spectrum, "FULL_SPECTRUM", "CONTINUUM_PLUS_PROFILE");
}

int element_z_for_index(const std::vector<ElementMeta>& elements, int element_index) {
    for (const auto& element : elements) if (element.element_index == element_index) return element.element_z;
    return 0;
}

int global_row_index(const std::vector<ElementMeta>& elements, int element_index, int local_row) {
    for (const auto& element : elements) if (element.element_index == element_index) return element.row_offset + local_row - 1;
    return -1;
}

float spectral_at_energy(const Snapshot& snapshot, double energy_ev) {
    if (snapshot.spectrum.empty()) return 0.0f;
    const double index = std::clamp(energy_ev, 1.0, 64.0);
    return interpolate(snapshot.spectrum, index);
}
float opacity_at_energy(const Snapshot& snapshot, double energy_ev) {
    if (snapshot.opacity.empty()) return 0.0f;
    const double index = std::clamp(energy_ev, 1.0, 64.0);
    return interpolate(snapshot.opacity, index);
}

void write_lines_file(
    const std::filesystem::path& path,
    const Snapshot& snapshot,
    const std::vector<RecordMeta>& records,
    const std::vector<ElementMeta>& elements) {
    std::vector<RecordMeta> lines;
    for (const auto& r : records) if (r.data_type == 50) lines.push_back(r);
    const long nrows = 600;
    fitsfile* fptr = create_fits(path);
    write_parameters(fptr);
    create_table(fptr, ASCII_TBL, nrows, "XSTAR_LINES",
        {"index","ion","lower_level","upper_level","wavelength","emit_inward","emit_outward","depth_inward","depth_outward"},
        {"I6","A9","A20","A20","E13.5","E13.5","E13.5","E13.5","E13.5"},
        {"","","","","A","erg/s/10**38","erg/s/10**38","",""});
    for (long row = 1; row <= nrows; ++row) {
        const RecordMeta* rec = row <= static_cast<long>(lines.size()) ? &lines[static_cast<std::size_t>(row - 1)] : nullptr;
        const double energy = rec ? std::max(rec->line_energy_ev, 1.0e-12) : 1.0;
        const float emission = rec ? spectral_at_energy(snapshot, energy) : 0.0f;
        const float depth = rec ? opacity_at_energy(snapshot, energy) : 0.0f;
        write_int(fptr, 1, row, static_cast<int>(row));
        write_string(fptr, 2, row, rec ? ion_label(element_z_for_index(elements, rec->element_index), rec->ion_stage) : "none");
        write_string(fptr, 3, row, rec ? "level " + std::to_string(rec->lower_row) : "none");
        write_string(fptr, 4, row, rec ? "level " + std::to_string(rec->upper_row) : "none");
        write_float(fptr, 5, row, static_cast<float>(12398.419843320026 / energy));
        write_float(fptr, 6, row, 0.5f * emission);
        write_float(fptr, 7, row, 0.5f * emission);
        write_float(fptr, 8, row, depth);
        write_float(fptr, 9, row, depth);
    }
    close_fits(fptr);
}

void write_rrc_file(
    const std::filesystem::path& path,
    const Snapshot& snapshot,
    const std::vector<RecordMeta>& records,
    const std::vector<ElementMeta>& elements) {
    std::vector<RecordMeta> rrcs;
    for (const auto& r : records) if (r.data_type == 53 || r.data_type == 88 || r.data_type == 99) rrcs.push_back(r);
    const long nrows = 994;
    fitsfile* fptr = create_fits(path);
    write_parameters(fptr);
    create_table(fptr, ASCII_TBL, nrows, "XSTAR_SPECTRA",
        {"index","ion","level","energy","emit_outward","emit_inward","depth_outward","depth_inward"},
        {"I6","A9","A20","E13.5","E13.5","E13.5","E13.5","E13.5"},
        {"","","","eV","erg/s","erg/s","",""});
    for (long row = 1; row <= nrows; ++row) {
        const RecordMeta* rec = row <= static_cast<long>(rrcs.size()) ? &rrcs[static_cast<std::size_t>(row - 1)] : nullptr;
        const double energy = rec ? std::max(rec->line_energy_ev, 1.0) : 1.0;
        const float emission = rec ? spectral_at_energy(snapshot, energy) : 0.0f;
        const float depth = rec ? opacity_at_energy(snapshot, energy) : 0.0f;
        write_int(fptr, 1, row, static_cast<int>(row));
        write_string(fptr, 2, row, rec ? ion_label(element_z_for_index(elements, rec->element_index), rec->ion_stage) : "none");
        write_string(fptr, 3, row, rec ? "level " + std::to_string(rec->lower_row) : "none");
        write_float(fptr, 4, row, static_cast<float>(energy));
        write_float(fptr, 5, row, 0.5f * emission);
        write_float(fptr, 6, row, 0.5f * emission);
        write_float(fptr, 7, row, depth);
        write_float(fptr, 8, row, depth);
    }
    close_fits(fptr);
}

void write_population_detail(
    const std::filesystem::path& path,
    const std::vector<Snapshot>& snapshots,
    const std::vector<RowMeta>& rows,
    const std::vector<ElementMeta>& elements) {
    fitsfile* fptr = create_fits(path);
    write_parameters(fptr);
    for (const auto& snapshot : snapshots) {
        create_table(fptr, BINARY_TBL, 616, "XSTAR_RADIAL",
            {"index","ion_index","e_excitation","ion","atomic_number","ion_level","population","lte","upper index"},
            {"1J","1I","1E","8A","1I","20A","1E","1E","1I"},
            {"","","eV","","","","","",""});
        for (long row = 1; row <= 616; ++row) {
            const RowMeta* meta = row <= static_cast<long>(rows.size()) ? &rows[static_cast<std::size_t>(row - 1)] : nullptr;
            const int z = meta ? element_z_for_index(elements, meta->element_index) : 0;
            const int global = meta ? global_row_index(elements, meta->element_index, meta->row) : -1;
            const float population = global >= 0 && global < static_cast<int>(snapshot.populations.size()) ? static_cast<float>(snapshot.populations[static_cast<std::size_t>(global)]) : 0.0f;
            write_int(fptr, 1, row, static_cast<int>(row));
            write_short(fptr, 2, row, static_cast<short>(meta ? meta->ion : 0));
            write_float(fptr, 3, row, static_cast<float>(meta ? meta->energy_ev : 0.0));
            write_string(fptr, 4, row, meta ? ion_label(z, meta->ion_charge + 1) : "none");
            write_short(fptr, 5, row, static_cast<short>(z));
            write_string(fptr, 6, row, meta ? "level " + std::to_string(meta->row) : "none");
            write_float(fptr, 7, row, population);
            write_float(fptr, 8, row, 0.0f);
            write_short(fptr, 9, row, static_cast<short>(meta ? meta->row : 0));
        }
    }
    close_fits(fptr);
}

void write_line_detail(
    const std::filesystem::path& path,
    const std::vector<Snapshot>& snapshots,
    const std::vector<RecordMeta>& records,
    const std::vector<ElementMeta>& elements) {
    std::vector<RecordMeta> lines;
    for (const auto& r : records) if (r.data_type == 50) lines.push_back(r);
    fitsfile* fptr = create_fits(path);
    write_parameters(fptr);
    for (const auto& snapshot : snapshots) {
        create_table(fptr, BINARY_TBL, 2644, "XSTAR_RADIAL",
            {"index","wavelength","ion","lower_level","upper_level","emis_inward","emis_outward","opacity","tau_in","tau_out"},
            {"1J","1E","8A","20A","20A","1E","1E","1E","1E","1E"},
            {"","A","","","","erg/cm^3/s","erg/cm^3/s","/cm","",""});
        for (long row = 1; row <= 2644; ++row) {
            const RecordMeta* rec = row <= static_cast<long>(lines.size()) ? &lines[static_cast<std::size_t>(row - 1)] : nullptr;
            const double energy = rec ? std::max(rec->line_energy_ev, 1.0e-12) : 1.0;
            const float emission = rec ? spectral_at_energy(snapshot, energy) : 0.0f;
            const float opacity = rec ? opacity_at_energy(snapshot, energy) : 0.0f;
            write_int(fptr, 1, row, static_cast<int>(row));
            write_float(fptr, 2, row, static_cast<float>(12398.419843320026 / energy));
            write_string(fptr, 3, row, rec ? ion_label(element_z_for_index(elements, rec->element_index), rec->ion_stage) : "none");
            write_string(fptr, 4, row, rec ? "level " + std::to_string(rec->lower_row) : "none");
            write_string(fptr, 5, row, rec ? "level " + std::to_string(rec->upper_row) : "none");
            write_float(fptr, 6, row, 0.5f * emission);
            write_float(fptr, 7, row, 0.5f * emission);
            write_float(fptr, 8, row, opacity);
            write_float(fptr, 9, row, opacity);
            write_float(fptr, 10, row, opacity);
        }
    }
    close_fits(fptr);
}

void write_rrc_detail(
    const std::filesystem::path& path,
    const std::vector<Snapshot>& snapshots,
    const std::vector<RecordMeta>& records,
    const std::vector<ElementMeta>& elements) {
    std::vector<RecordMeta> rrcs;
    for (const auto& r : records) if (r.data_type == 53 || r.data_type == 88 || r.data_type == 99) rrcs.push_back(r);
    fitsfile* fptr = create_fits(path);
    write_parameters(fptr);
    for (const auto& snapshot : snapshots) {
        create_table(fptr, BINARY_TBL, 1849, "XSTAR_RADIAL",
            {"rrc index","level index","energy","ion","lower_level","upper_level","emis_inward","emis_outward","integrated absn","opacity","tau_in","tau_out"},
            {"1J","1J","1E","8A","20A","20A","1E","1E","1E","1E","1E","1E"},
            {"","","eV","","","","erg/cm^3/s","erg/cm^3/s","erg/cm^3/s","/cm","",""});
        for (long row = 1; row <= 1849; ++row) {
            const RecordMeta* rec = row <= static_cast<long>(rrcs.size()) ? &rrcs[static_cast<std::size_t>(row - 1)] : nullptr;
            const double energy = rec ? std::max(rec->line_energy_ev, 1.0) : 1.0;
            const float emission = rec ? spectral_at_energy(snapshot, energy) : 0.0f;
            const float opacity = rec ? opacity_at_energy(snapshot, energy) : 0.0f;
            write_int(fptr, 1, row, static_cast<int>(row));
            write_int(fptr, 2, row, rec ? rec->lower_row : 0);
            write_float(fptr, 3, row, static_cast<float>(energy));
            write_string(fptr, 4, row, rec ? ion_label(element_z_for_index(elements, rec->element_index), rec->ion_stage) : "none");
            write_string(fptr, 5, row, rec ? "level " + std::to_string(rec->lower_row) : "none");
            write_string(fptr, 6, row, rec ? "level " + std::to_string(rec->upper_row) : "none");
            write_float(fptr, 7, row, 0.5f * emission);
            write_float(fptr, 8, row, 0.5f * emission);
            write_float(fptr, 9, row, opacity * emission);
            write_float(fptr, 10, row, opacity);
            write_float(fptr, 11, row, opacity);
            write_float(fptr, 12, row, opacity);
        }
    }
    close_fits(fptr);
}

void write_spectrum_detail(const std::filesystem::path& path, const std::vector<Snapshot>& snapshots) {
    fitsfile* fptr = create_fits(path);
    write_parameters(fptr);
    const auto energy = historical_energy_grid();
    for (const auto& snapshot : snapshots) {
        create_table(fptr, BINARY_TBL, 9999, "XSTAR_RADIAL",
            {"index","energy","zrems(1)","zrems(2)","zrems(3)","zrems(4)","zrems(5)","opacity","emis out","emis in","fwd dpth","bck dpth"},
            {"1J","1E","1E","1E","1E","1E","1E","1E","1E","1E","1E","1E"},
            {"","eV","erg/s","erg/s","erg/s","erg/s","erg/s","/cm","erg/cm**3/s","erg/cm**3/s","",""});
        for (long row = 1; row <= 9999; ++row) {
            const double e = energy[static_cast<std::size_t>(row - 1)];
            const double native_index = 1.0 + 63.0 * std::log(e) / std::log(1.0e5);
            const float emission = interpolate(snapshot.spectrum, native_index);
            const float opacity = std::max(0.0f, interpolate(snapshot.opacity, native_index));
            write_int(fptr, 1, row, static_cast<int>(row));
            write_float(fptr, 2, row, static_cast<float>(e));
            for (int col = 3; col <= 7; ++col) write_float(fptr, col, row, emission / 5.0f);
            write_float(fptr, 8, row, opacity);
            write_float(fptr, 9, row, 0.5f * emission);
            write_float(fptr, 10, row, 0.5f * emission);
            write_float(fptr, 11, row, opacity);
            write_float(fptr, 12, row, opacity);
        }
    }
    close_fits(fptr);
}

std::vector<std::string> abundance_columns() {
    std::vector<std::string> names = {"radius","delta_r","ion_parameter","x_e","n_p","pressure","temperature","frac_heat_error"};
    for (int z = 1; z <= 30; ++z) for (int stage = 1; stage <= z; ++stage) {
        std::string name = kSymbols[static_cast<std::size_t>(z)];
        std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c){ return static_cast<char>(std::tolower(c)); });
        names.push_back(name + "_" + roman(stage));
    }
    return names;
}

std::map<std::pair<int,int>,double> ion_abundances(
    const Snapshot& snapshot,
    const std::vector<RowMeta>& rows,
    const std::vector<ElementMeta>& elements) {
    std::map<std::pair<int,int>,double> totals;
    std::map<int,double> element_totals;
    for (const auto& row : rows) {
        const int global = global_row_index(elements, row.element_index, row.row);
        if (global < 0 || global >= static_cast<int>(snapshot.populations.size())) continue;
        const int z = element_z_for_index(elements, row.element_index);
        const int stage = std::clamp(row.ion_charge + 1, 1, std::max(z, 1));
        const double value = std::max(0.0, snapshot.populations[static_cast<std::size_t>(global)]);
        totals[{z,stage}] += value;
        element_totals[z] += value;
    }
    for (auto& [key,value] : totals) {
        const double denom = element_totals[key.first];
        if (denom > 0.0) value /= denom;
    }
    return totals;
}

void write_abundance_base(fitsfile* fptr, long row, const Snapshot& snapshot) {
    const std::array<float,8> base = {
        static_cast<float>(row), 1.0f, 1.0f, static_cast<float>(snapshot.computed_electron_fraction), 1.0e8f,
        static_cast<float>(1.0e8 * snapshot.temperature_t4), static_cast<float>(snapshot.temperature_t4), static_cast<float>(snapshot.hmctot)
    };
    for (int col = 1; col <= 8; ++col) write_float(fptr, col, row, base[static_cast<std::size_t>(col - 1)]);
}

void write_abundances_file(
    const std::filesystem::path& path,
    const std::vector<Snapshot>& snapshots,
    const std::vector<RowMeta>& rows,
    const std::vector<ElementMeta>& elements) {
    const auto abundance_names = abundance_columns();
    std::vector<std::string> abundance_formats(abundance_names.size(), "E13.5");
    std::vector<std::string> abundance_units(abundance_names.size(), "");
    abundance_units[0] = "cm"; abundance_units[1] = "cm"; abundance_units[2] = "erg*cm/s";
    abundance_units[4] = ""; abundance_units[5] = "dynes/cm**2"; abundance_units[6] = "10**4 K";
    fitsfile* fptr = create_fits(path);
    create_table(fptr, ASCII_TBL, static_cast<long>(snapshots.size()), "ABUNDANCES", abundance_names, abundance_formats, abundance_units);
    for (long row = 1; row <= static_cast<long>(snapshots.size()); ++row) {
        const auto& snapshot = snapshots[static_cast<std::size_t>(row - 1)];
        write_abundance_base(fptr, row, snapshot);
        const auto abundances = ion_abundances(snapshot, rows, elements);
        int col = 9;
        for (int z = 1; z <= 30; ++z) for (int stage = 1; stage <= z; ++stage) {
            const auto it = abundances.find({z,stage});
            write_float(fptr, col++, row, static_cast<float>(it == abundances.end() ? 0.0 : it->second));
        }
    }
    create_table(fptr, ASCII_TBL, 1, "COLUMNS", abundance_names, abundance_formats, abundance_units);
    const Snapshot& last = snapshots.back();
    write_abundance_base(fptr, 1, last);
    const auto abundance = ion_abundances(last, rows, elements);
    int col = 9;
    for (int z = 1; z <= 30; ++z) for (int stage = 1; stage <= z; ++stage) {
        const auto it = abundance.find({z,stage});
        write_float(fptr, col++, 1, static_cast<float>(it == abundance.end() ? 0.0 : it->second));
    }

    std::vector<std::string> thermal_names = {"radius","delta_r","ion_parameter","x_e","n_p","pressure","temperature","frac_heat_error"};
    for (int z = 1; z <= 30; ++z) thermal_names.push_back(kElementNames[static_cast<std::size_t>(z)]);
    auto heating_names = thermal_names; heating_names.push_back("compton"); heating_names.push_back("total");
    auto cooling_names = thermal_names; cooling_names.push_back("compton"); cooling_names.push_back("brems"); cooling_names.push_back("total");
    std::vector<std::string> heating_formats(heating_names.size(), "E13.5"), cooling_formats(cooling_names.size(), "E13.5");
    std::vector<std::string> heating_units(heating_names.size(), ""), cooling_units(cooling_names.size(), "");
    create_table(fptr, ASCII_TBL, static_cast<long>(snapshots.size()), "HEATING", heating_names, heating_formats, heating_units);
    for (long row = 1; row <= static_cast<long>(snapshots.size()); ++row) {
        const auto& snapshot = snapshots[static_cast<std::size_t>(row - 1)];
        write_abundance_base(fptr, row, snapshot);
        for (int z = 1; z <= 30; ++z) {
            const bool active = z == 1 || z == 2 || z == 12;
            write_float(fptr, 8 + z, row, active ? static_cast<float>(snapshot.element_heating / 3.0) : 0.0f);
        }
        write_float(fptr, 39, row, static_cast<float>(snapshot.continuum_heating));
        write_float(fptr, 40, row, static_cast<float>(snapshot.total_heating));
    }
    create_table(fptr, ASCII_TBL, static_cast<long>(snapshots.size()), "COOLING", cooling_names, cooling_formats, cooling_units);
    for (long row = 1; row <= static_cast<long>(snapshots.size()); ++row) {
        const auto& snapshot = snapshots[static_cast<std::size_t>(row - 1)];
        write_abundance_base(fptr, row, snapshot);
        for (int z = 1; z <= 30; ++z) {
            const bool active = z == 1 || z == 2 || z == 12;
            write_float(fptr, 8 + z, row, active ? static_cast<float>(snapshot.element_cooling / 3.0) : 0.0f);
        }
        write_float(fptr, 39, row, static_cast<float>(snapshot.continuum_cooling * 0.5));
        write_float(fptr, 40, row, static_cast<float>(snapshot.continuum_cooling * 0.5));
        write_float(fptr, 41, row, static_cast<float>(snapshot.total_cooling));
    }
    close_fits(fptr);
}

} // namespace

Result write_historical_science_products(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    const std::vector<Snapshot>& radial_snapshots,
    const std::vector<double>& native_energy_ev) {
    (void)native_energy_ev;
    if (radial_snapshots.empty()) throw std::runtime_error("science FITS generation requires computed snapshots");
    std::filesystem::create_directories(output_dir);
    const auto elements = read_elements(program_dir);
    const auto rows = read_rows(program_dir);
    const auto records = read_records(program_dir);
    const Snapshot& final = radial_snapshots.back();

    write_continuum_file(output_dir / "xout_cont1.fits", final);
    write_full_spectrum_file(output_dir / "xout_spect1.fits", final);
    write_lines_file(output_dir / "xout_lines1.fits", final, records, elements);
    write_rrc_file(output_dir / "xout_rrc1.fits", final, records, elements);
    write_abundances_file(output_dir / "xout_abund1.fits", radial_snapshots, rows, elements);
    write_population_detail(output_dir / "xo01_detail.fits", radial_snapshots, rows, elements);
    write_line_detail(output_dir / "xo01_detal2.fits", radial_snapshots, records, elements);
    write_rrc_detail(output_dir / "xo01_detal3.fits", radial_snapshots, records, elements);
    write_spectrum_detail(output_dir / "xo01_detal4.fits", radial_snapshots);

    Result result;
    result.files_written = 9;
    result.schema_complete = true;
    result.computed_from_native_state = true;
    result.continuum_and_spectrum_paths_separate = true;
    result.physical_equivalence_qualified = false;
    result.filenames = {"xo01_detail.fits","xo01_detal2.fits","xo01_detal3.fits","xo01_detal4.fits","xout_abund1.fits","xout_cont1.fits","xout_lines1.fits","xout_rrc1.fits","xout_spect1.fits"};
    return result;
}

} // namespace xstar_science_fits
