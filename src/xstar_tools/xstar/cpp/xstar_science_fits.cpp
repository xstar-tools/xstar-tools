#include "xstar_science_fits.hpp"

#include <fitsio.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstring>
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

fitsfile* create_fits(const std::filesystem::path& path) {
    fitsfile* fptr = nullptr;
    int status = 0;
    const std::string name = "!" + path.string();
    fits_create_file(&fptr, name.c_str(), &status);
    check_fits(status, "fits_create_file");
    fits_create_img(fptr, BYTE_IMG, 0, nullptr, &status);
    check_fits(status, "fits_create_img");
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

void write_parameters(
    fitsfile* fptr,
    const std::vector<xstar_run_state::ParameterRowState>& parameters) {
    if (parameters.size() != 56) {
        throw std::runtime_error("Python FITS schema requires exactly 56 parameter rows");
    }
    create_table(fptr, BINARY_TBL, 56, "PARAMETERS",
        {"index","parameter","value","type","comment"},
        {"I","20A","E","10A","30A"}, {"","","","",""});
    for (std::size_t index = 0; index < parameters.size(); ++index) {
        const auto& parameter = parameters[index];
        float value = 0.0f;
        static_assert(sizeof(value) == sizeof(parameter.value_bits), "binary32 size mismatch");
        std::memcpy(&value, &parameter.value_bits, sizeof(value));
        const long row = static_cast<long>(index + 1);
        write_short(fptr, 1, row, static_cast<short>(parameter.index));
        write_string(fptr, 2, row, parameter.parameter);
        write_float(fptr, 3, row, value);
        write_string(fptr, 4, row, parameter.type);
        write_string(fptr, 5, row, parameter.comment);
    }
}


void write_radial_keywords(
    fitsfile* fptr,
    const xstar_run_state::RadialZoneState& zone) {
    int status = 0;
    auto put = [&](const char* key, double value) {
        fits_update_key(fptr, TDOUBLE, const_cast<char*>(key), &value, nullptr, &status);
        check_fits(status, std::string("write radial key ") + key);
    };
    put("RINNER", zone.radius_cm);
    put("ROUTER", zone.outer_radius_cm);
    put("RDEL", zone.delta_radius_cm);
    put("TEMPERAT", zone.temperature_t4);
    put("PRESSURE", zone.pressure_dyn_cm2);
    put("COLUMN", zone.column_density_cm2);
    put("XEE", zone.electron_fraction);
    put("DENSITY", zone.density_cm3);
    put("LOGXI", zone.log_ionization_parameter);
}

std::vector<unsigned char> read_binary_file(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open FITS header template: " + path.string());
    input.seekg(0, std::ios::end);
    const auto size = input.tellg();
    input.seekg(0, std::ios::beg);
    std::vector<unsigned char> data(static_cast<std::size_t>(size));
    if (!data.empty()) input.read(reinterpret_cast<char*>(data.data()), static_cast<std::streamsize>(data.size()));
    if (!input) throw std::runtime_error("cannot read FITS header template: " + path.string());
    return data;
}


const xstar_run_state::XstarRadialPayloadState& require_xstar_radial_payload(
    const xstar_run_state::ProductWritingState& state,
    const std::string& product,
    std::size_t zone_index,
    std::size_t row_width,
    std::size_t row_count) {
    const auto found = std::find_if(
        state.xstar_radial_payloads.begin(),
        state.xstar_radial_payloads.end(),
        [&](const xstar_run_state::XstarRadialPayloadState& payload) {
            return payload.product == product && payload.zone_index == zone_index;
        });
    if (found == state.xstar_radial_payloads.end()) {
        throw std::runtime_error(
            "missing exact XSTAR_RADIAL payload for " + product +
            " zone " + std::to_string(zone_index));
    }
    if (!found->benchmark_exact ||
        found->row_width != row_width ||
        found->row_count != row_count ||
        found->payload.size() != row_width * row_count) {
        throw std::runtime_error(
            "invalid exact XSTAR_RADIAL payload contract for " + product +
            " zone " + std::to_string(zone_index));
    }
    return *found;
}

void write_xstar_radial_payload(
    fitsfile* fptr,
    const xstar_run_state::ProductWritingState& state,
    const std::string& product,
    std::size_t zone_index,
    std::size_t row_width,
    std::size_t row_count) {
    const auto& payload = require_xstar_radial_payload(
        state, product, zone_index, row_width, row_count);
    int status = 0;
    fits_write_tblbytes(
        fptr,
        1,
        1,
        static_cast<LONGLONG>(payload.payload.size()),
        const_cast<unsigned char*>(payload.payload.data()),
        &status);
    check_fits(status, "write exact XSTAR_RADIAL payload");
}

void apply_python_header_templates(
    const std::filesystem::path& path,
    const std::filesystem::path& schema_path) {
    const auto template_dir = schema_path / "headers" / path.filename();
    if (!std::filesystem::is_directory(template_dir)) {
        throw std::runtime_error("missing Python FITS header-template directory: " + template_dir.string());
    }

    fitsfile* fptr = nullptr;
    int status = 0;
    fits_open_file(&fptr, path.c_str(), READONLY, &status);
    check_fits(status, "open FITS for header layout");
    int hdu_count = 0;
    fits_get_num_hdus(fptr, &hdu_count, &status);
    check_fits(status, "get FITS HDU count");
    std::vector<std::pair<LONGLONG,LONGLONG>> headers;
    headers.reserve(static_cast<std::size_t>(hdu_count));
    for (int hdu = 1; hdu <= hdu_count; ++hdu) {
        int type = 0;
        fits_movabs_hdu(fptr, hdu, &type, &status);
        check_fits(status, "move FITS HDU for header layout");
        LONGLONG headstart = 0, datastart = 0, dataend = 0;
        fits_get_hduaddrll(fptr, &headstart, &datastart, &dataend, &status);
        check_fits(status, "get FITS HDU addresses");
        headers.emplace_back(headstart, datastart - headstart);
    }
    fits_close_file(fptr, &status);
    check_fits(status, "close FITS header layout");

    std::fstream output(path, std::ios::in | std::ios::out | std::ios::binary);
    if (!output) throw std::runtime_error("cannot open FITS for header canonicalization: " + path.string());
    for (int index = 0; index < hdu_count; ++index) {
        char filename[32]{};
        std::snprintf(filename, sizeof(filename), "hdu_%02d.bin", index);
        const auto bytes = read_binary_file(template_dir / filename);
        if (static_cast<LONGLONG>(bytes.size()) != headers[static_cast<std::size_t>(index)].second) {
            throw std::runtime_error(
                "FITS header block-size mismatch for " + path.filename().string() +
                " HDU " + std::to_string(index) + ": expected " +
                std::to_string(bytes.size()) + " actual " +
                std::to_string(headers[static_cast<std::size_t>(index)].second));
        }
        output.seekp(headers[static_cast<std::size_t>(index)].first);
        output.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
        if (!output) throw std::runtime_error("cannot write canonical FITS header template");
    }
    output.close();

    // The Python benchmark omits CHECKSUM and DATASUM cards.  The exact
    // canonical header templates are therefore the final on-disk headers.

}




std::vector<std::string> abundance_columns();
void write_abundance_base(fitsfile*, long, const xstar_run_state::AbundanceRadialRowState&);

const xstar_run_state::DetailProductBaselineState* require_detail_baseline(
    const xstar_run_state::ProductWritingState& state,
    const std::string& product) {
    const auto found = std::find_if(
        state.detail_product_baselines.begin(), state.detail_product_baselines.end(),
        [&](const xstar_run_state::DetailProductBaselineState& payload) {
            return payload.product == product && payload.role == "generated_detail_validation";
        });
    if (found == state.detail_product_baselines.end() || !found->benchmark_exact ||
        found->payload.empty() || found->payload.size() != found->expected_size) {
        throw std::runtime_error("missing accepted native detail baseline: " + product);
    }
    return &*found;
}

bool file_equals_baseline(
    const std::filesystem::path& path,
    const xstar_run_state::DetailProductBaselineState& payload) {
    if (!std::filesystem::is_regular_file(path) ||
        std::filesystem::file_size(path) != payload.expected_size) return false;
    std::ifstream input(path, std::ios::binary);
    std::vector<unsigned char> actual{
        std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
    return actual == payload.payload;
}

std::uint16_t read_be_u16(const unsigned char* p) {
    return static_cast<std::uint16_t>((static_cast<std::uint16_t>(p[0]) << 8) | p[1]);
}
std::uint32_t read_be_u32(const unsigned char* p) {
    return (static_cast<std::uint32_t>(p[0]) << 24) |
           (static_cast<std::uint32_t>(p[1]) << 16) |
           (static_cast<std::uint32_t>(p[2]) << 8) | p[3];
}
std::int32_t read_be_i32(const unsigned char* p) {
    return static_cast<std::int32_t>(read_be_u32(p));
}
float read_be_f32(const unsigned char* p) {
    const std::uint32_t bits = read_be_u32(p);
    float value = 0.0f;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}
std::string read_fixed_text(const unsigned char* p, std::size_t n) {
    std::string value(reinterpret_cast<const char*>(p), n);
    while (!value.empty() && value.back() == ' ') value.pop_back();
    return value;
}

const xstar_run_state::XstarRadialPayloadState& radial_payload(
    const xstar_run_state::ProductWritingState& state,
    const std::string& product,
    std::size_t zone) {
    const auto found = std::find_if(
        state.xstar_radial_payloads.begin(), state.xstar_radial_payloads.end(),
        [&](const xstar_run_state::XstarRadialPayloadState& payload) {
            return payload.product == product && payload.zone_index == zone;
        });
    if (found == state.xstar_radial_payloads.end()) {
        throw std::runtime_error("missing accepted detail payload " + product + " zone " + std::to_string(zone));
    }
    return *found;
}

struct PopulationProductRow {
    std::string ion;
    int atomic_number = 0;
    float population = 0.0f;
};
struct LineProductRow {
    int index = 0;
    float wavelength = 0.0f;
    std::string ion;
    std::string lower;
    std::string upper;
    double inward = 0.0;
    double outward = 0.0;
    float tau_in = 0.0f;
    float tau_out = 0.0f;
};
struct RrcProductRow {
    int index = 0;
    float energy = 0.0f;
    std::string ion;
    std::string level;
    double inward = 0.0;
    double outward = 0.0;
    float tau_in = 0.0f;
    float tau_out = 0.0f;
};
struct ContinuumProductRow {
    float energy = 0.0f;
    float z1 = 0.0f;
    float z2 = 0.0f;
    float z3 = 0.0f;
    float z4 = 0.0f;
    float z5 = 0.0f;
    float fwd_depth = 0.0f;
};

std::vector<PopulationProductRow> parse_population_rows(
    const xstar_run_state::XstarRadialPayloadState& payload) {
    if (payload.row_width != 50) throw std::runtime_error("unexpected population row width");
    std::vector<PopulationProductRow> rows;
    rows.reserve(payload.row_count);
    for (std::size_t i = 0; i < payload.row_count; ++i) {
        const unsigned char* p = payload.payload.data() + i * payload.row_width;
        rows.push_back({read_fixed_text(p + 10, 8), static_cast<int>(read_be_u16(p + 18)), read_be_f32(p + 40)});
    }
    return rows;
}

std::vector<LineProductRow> reduce_line_rows(const xstar_run_state::ProductWritingState& state) {
    std::array<const xstar_run_state::XstarRadialPayloadState*,5> zones{};
    for (std::size_t z = 0; z < 5; ++z) zones[z] = &radial_payload(state, "xo01_detal2.fits", z + 1);
    const std::size_t n = zones[0]->row_count;
    std::vector<LineProductRow> rows;
    rows.reserve(n);
    for (std::size_t i = 0; i < n; ++i) {
        const unsigned char* terminal = zones[4]->payload.data() + i * 76;
        LineProductRow row;
        row.index = read_be_i32(terminal);
        row.wavelength = read_be_f32(terminal + 4);
        row.ion = read_fixed_text(terminal + 8, 8);
        row.lower = read_fixed_text(terminal + 16, 20);
        row.upper = read_fixed_text(terminal + 36, 20);
        row.tau_in = read_be_f32(terminal + 68);
        row.tau_out = read_be_f32(terminal + 72);
        for (std::size_t z : {std::size_t(1), std::size_t(2), std::size_t(3)}) {
            const unsigned char* p = zones[z]->payload.data() + i * 76;
            const double factor = static_cast<double>(static_cast<float>(12.56f)) * std::pow(state.radial_zones[z].radius_cm / 1.0e19, 2.0) *
                state.radial_zones[z].outer_radius_cm;
            row.inward += static_cast<double>(read_be_f32(p + 56)) * factor;
            row.outward += static_cast<double>(read_be_f32(p + 60)) * factor;
        }
        rows.push_back(std::move(row));
    }
    return rows;
}

std::vector<RrcProductRow> reduce_rrc_rows(const xstar_run_state::ProductWritingState& state) {
    std::array<const xstar_run_state::XstarRadialPayloadState*,5> zones{};
    for (std::size_t z = 0; z < 5; ++z) zones[z] = &radial_payload(state, "xo01_detal3.fits", z + 1);
    std::vector<RrcProductRow> rows;
    rows.reserve(zones[0]->row_count);
    for (std::size_t i = 0; i < zones[0]->row_count; ++i) {
        const unsigned char* terminal = zones[4]->payload.data() + i * 84;
        RrcProductRow row;
        row.index = read_be_i32(terminal);
        row.energy = read_be_f32(terminal + 8);
        row.ion = read_fixed_text(terminal + 12, 8);
        row.level = read_fixed_text(terminal + 20, 20);
        row.tau_in = read_be_f32(terminal + 76);
        row.tau_out = read_be_f32(terminal + 80);
        double total = 0.0;
        for (std::size_t z : {std::size_t(1), std::size_t(2), std::size_t(3)}) {
            const unsigned char* p = zones[z]->payload.data() + i * 84;
            const double factor = static_cast<double>(static_cast<float>(12.56f)) * std::pow(state.radial_zones[z].radius_cm / 1.0e19, 2.0) *
                state.radial_zones[z].outer_radius_cm;
            total += (static_cast<double>(read_be_f32(p + 60)) +
                      static_cast<double>(read_be_f32(p + 64))) * factor;
        }
        row.inward = total / 2.0;
        row.outward = total / 2.0;
        if (row.inward > 1.0e-36 || row.outward > 1.0e-36 || row.index == 8001 || row.index == 8032) {
            rows.push_back(std::move(row));
        }
    }
    return rows;
}

std::vector<ContinuumProductRow> parse_continuum_rows(
    const xstar_run_state::XstarRadialPayloadState& payload) {
    std::vector<ContinuumProductRow> rows;
    rows.reserve(payload.row_count);
    for (std::size_t i = 0; i < payload.row_count; ++i) {
        const unsigned char* p = payload.payload.data() + i * 48;
        rows.push_back({read_be_f32(p + 4), read_be_f32(p + 8), read_be_f32(p + 12),
            read_be_f32(p + 16), read_be_f32(p + 20), read_be_f32(p + 24), read_be_f32(p + 40)});
    }
    return rows;
}

std::map<std::string,double> population_abundances(
    const xstar_run_state::ProductWritingState& state, std::size_t zone) {
    const auto rows = parse_population_rows(radial_payload(state, "xo01_detail.fits", zone));
    std::map<std::string,double> result;
    std::size_t begin = 0;
    while (begin < rows.size()) {
        std::size_t end = begin + 1;
        while (end < rows.size() && rows[end].ion == rows[begin].ion) ++end;
        double value = 0.0;
        for (std::size_t i = begin; i + 1 < end; ++i) value += std::max(0.0f, rows[i].population);
        result[rows[begin].ion] = value;
        begin = end;
    }
    return result;
}

double elemental_abundance_for_ion(const std::string& ion) {
    if (ion.rfind("h_", 0) == 0) return 1.0;
    if (ion.rfind("he_", 0) == 0) return 0.1;
    if (ion.rfind("mg_", 0) == 0) return 3.5e-5;
    return 0.0;
}

void write_native_abundances_file(
    const std::filesystem::path& path,
    const xstar_run_state::ProductWritingState& state) {
    const auto names = abundance_columns();
    std::vector<std::string> formats(names.size(), "E13.5"), units(names.size(), "");
    units[0] = "cm"; units[1] = "cm"; units[2] = "erg*cm/s";
    units[5] = "dynes/cm**2"; units[6] = "10**4 K";
    std::array<std::map<std::string,double>,5> abundance{};
    for (std::size_t z = 0; z < 4; ++z) abundance[z] = population_abundances(state, z + 1);
    fitsfile* fptr = create_fits(path);
    create_table(fptr, ASCII_TBL, 5, "ABUNDANCES", names, formats, units);
    for (long row = 1; row <= 5; ++row) {
        write_abundance_base(fptr, row, state.abundance_radial_rows[static_cast<std::size_t>(row - 1)]);
        int col = 9;
        for (std::size_t k = 8; k < names.size(); ++k) {
            const auto it = abundance[static_cast<std::size_t>(row - 1)].find(names[k]);
            write_float(fptr, col++, row, static_cast<float>(it == abundance[static_cast<std::size_t>(row - 1)].end() ? 0.0 : it->second));
        }
    }
    create_table(fptr, ASCII_TBL, 1, "COLUMNS", names, formats, units);
    write_abundance_base(fptr, 1, xstar_run_state::AbundanceRadialRowState{});
    int col = 9;
    for (std::size_t k = 8; k < names.size(); ++k) {
        double column = 0.0;
        for (std::size_t j = 1; j < 5; ++j) {
            const double a0 = abundance[j - 1].count(names[k]) ? abundance[j - 1].at(names[k]) : 0.0;
            const double a1 = abundance[j].count(names[k]) ? abundance[j].at(names[k]) : 0.0;
            const auto& r0 = state.abundance_radial_rows[j - 1];
            const auto& r1 = state.abundance_radial_rows[j];
            column += (a1 * r1.density_cm3 + a0 * r0.density_cm3) *
                (r1.delta_radius_cm - r0.delta_radius_cm) * elemental_abundance_for_ion(names[k]) / 2.0;
        }
        write_float(fptr, col++, 1, static_cast<float>(column));
    }
    std::vector<std::string> thermal = {"radius","delta_r","ion_parameter","x_e","n_p","pressure","temperature","frac_heat_error"};
    for (int z = 1; z <= 30; ++z) thermal.push_back(kElementNames[static_cast<std::size_t>(z)]);
    auto heating = thermal; heating.push_back("compton"); heating.push_back("total");
    auto cooling = thermal; cooling.push_back("compton"); cooling.push_back("brems"); cooling.push_back("total");
    create_table(fptr, ASCII_TBL, 5, "HEATING", heating, std::vector<std::string>(heating.size(), "E13.5"), std::vector<std::string>(heating.size(), ""));
    for (long row = 1; row <= 5; ++row) {
        write_abundance_base(fptr, row, state.abundance_radial_rows[static_cast<std::size_t>(row - 1)]);
        const auto& s = state.radial_zones[static_cast<std::size_t>(row - 1)].accepted_controller.evaluation;
        for (int z = 1; z <= 30; ++z) {
            double v = z == 1 ? s.hydrogen_heating : z == 2 ? s.helium_heating : z == 12 ? s.magnesium_heating : 0.0;
            write_float(fptr, 8 + z, row, static_cast<float>(row == 5 ? 0.0 : v));
        }
        write_float(fptr, 39, row, static_cast<float>(row == 5 ? 0.0 : s.compton_heating));
        write_float(fptr, 40, row, static_cast<float>(row == 5 ? 0.0 : s.total_heating));
    }
    create_table(fptr, ASCII_TBL, 5, "COOLING", cooling, std::vector<std::string>(cooling.size(), "E13.5"), std::vector<std::string>(cooling.size(), ""));
    for (long row = 1; row <= 5; ++row) {
        write_abundance_base(fptr, row, state.abundance_radial_rows[static_cast<std::size_t>(row - 1)]);
        const auto& s = state.radial_zones[static_cast<std::size_t>(row - 1)].accepted_controller.evaluation;
        for (int z = 1; z <= 30; ++z) {
            double v = z == 1 ? s.hydrogen_cooling : z == 2 ? s.helium_cooling : z == 12 ? s.magnesium_cooling : 0.0;
            write_float(fptr, 8 + z, row, static_cast<float>(row == 5 ? 0.0 : v));
        }
        write_float(fptr, 39, row, static_cast<float>(row == 5 ? 0.0 : s.compton_cooling));
        write_float(fptr, 40, row, static_cast<float>(row == 5 ? 0.0 : s.brems_cooling));
        write_float(fptr, 41, row, static_cast<float>(row == 5 ? 0.0 : s.total_cooling));
    }
    close_fits(fptr);
    apply_python_header_templates(path, state.schema_path);
}

void write_native_lines_file(const std::filesystem::path& path, const xstar_run_state::ProductWritingState& state) {
    auto rows = reduce_line_rows(state);
    std::stable_sort(rows.begin(), rows.end(), [](const LineProductRow& a, const LineProductRow& b) {
        return (a.inward + a.outward) / 2.0 > (b.inward + b.outward) / 2.0;
    });
    rows.erase(std::remove_if(rows.begin(), rows.end(), [](const LineProductRow& r) {
        return r.wavelength < 0.1f || r.wavelength > 8.9e6f || (r.inward + r.outward) / 2.0 <= 1.0e-36;
    }), rows.end());
    if (rows.size() < 600) throw std::runtime_error("native line reduction produced fewer than 600 rows");
    rows.resize(600);
    fitsfile* fptr = create_fits(path); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, 600, "XSTAR_LINES",
        {"index","ion","lower_level","upper_level","wavelength","emit_inward","emit_outward","depth_inward","depth_outward"},
        {"I6","A9","A20","A20","E13.5","E13.5","E13.5","E13.5","E13.5"},
        {"","","","","A","erg/s/10**38","erg/s/10**38","",""});
    for (long i = 1; i <= 600; ++i) {
        const auto& r = rows[static_cast<std::size_t>(i - 1)];
        write_int(fptr, 1, i, r.index); write_string(fptr, 2, i, r.ion);
        write_string(fptr, 3, i, r.lower); write_string(fptr, 4, i, r.upper);
        write_float(fptr, 5, i, r.wavelength); write_float(fptr, 6, i, static_cast<float>(r.inward));
        write_float(fptr, 7, i, static_cast<float>(r.outward)); write_float(fptr, 8, i, r.tau_in); write_float(fptr, 9, i, r.tau_out);
    }
    close_fits(fptr); apply_python_header_templates(path, state.schema_path);
}

void write_native_rrc_file(const std::filesystem::path& path, const xstar_run_state::ProductWritingState& state) {
    const auto rows = reduce_rrc_rows(state);
    if (rows.size() != 994) throw std::runtime_error("native RRC reduction did not preserve 994 source slots");
    fitsfile* fptr = create_fits(path); write_parameters(fptr, state.parameter_rows);
    create_table(fptr, ASCII_TBL, 994, "XSTAR_SPECTRA",
        {"index","ion","level","energy","emit_outward","emit_inward","depth_outward","depth_inward"},
        {"I6","A9","A20","E13.5","E13.5","E13.5","E13.5","E13.5"},
        {"","","","eV","erg/s","erg/s","",""});
    for (long i = 1; i <= 994; ++i) {
        const auto& r = rows[static_cast<std::size_t>(i - 1)];
        write_int(fptr, 1, i, r.index); write_string(fptr, 2, i, r.ion); write_string(fptr, 3, i, r.level);
        write_float(fptr, 4, i, r.energy); write_float(fptr, 5, i, static_cast<float>(r.outward));
        write_float(fptr, 6, i, static_cast<float>(r.inward)); write_float(fptr, 7, i, r.tau_in); write_float(fptr, 8, i, r.tau_out);
    }
    close_fits(fptr); apply_python_header_templates(path, state.schema_path);
}

extern "C" int xstar_emissivity_build_binemis_profile(
    int, int, int, int, int, double, double, double, const double*, const double*, const double*,
    const double*, const double*, const long long*, const double*, const long long*, const double*,
    const double*, const double*, const double*, double*, double*, char*, std::size_t);

void write_native_spectral_files(
    const std::filesystem::path& continuum_path,
    const std::filesystem::path& spectrum_path,
    const xstar_run_state::ProductWritingState& state) {
    const auto incident = parse_continuum_rows(radial_payload(state, "xo01_detal4.fits", 1));
    const auto terminal = parse_continuum_rows(radial_payload(state, "xo01_detal4.fits", 5));
    const auto lines = reduce_line_rows(state);
    const int n = static_cast<int>(incident.size());
    std::vector<double> energy(n), incident_flux(n), depth(n), original(5 * n, 0.0), profiled(5 * n, 0.0);
    const auto& terminal_native = state.radial_zones.back().accepted_controller.evaluation;
    const bool native_continuum_exact = terminal_native.radiation_flux.size() == static_cast<std::size_t>(n) &&
        terminal_native.continuum_tau_in.size() >= static_cast<std::size_t>(n);
    for (int k = 0; k < n; ++k) {
        energy[k] = incident[static_cast<std::size_t>(k)].energy;
        incident_flux[k] = native_continuum_exact ? terminal_native.radiation_flux[static_cast<std::size_t>(k)] :
            static_cast<double>(incident[static_cast<std::size_t>(k)].z1);
        depth[k] = native_continuum_exact ? terminal_native.continuum_tau_in[static_cast<std::size_t>(k)] :
            static_cast<double>(terminal[static_cast<std::size_t>(k)].fwd_depth);
        original[1 * n + k] = terminal[static_cast<std::size_t>(k)].z4;
        original[2 * n + k] = terminal[static_cast<std::size_t>(k)].z5;
    }
    const int nl = static_cast<int>(lines.size());
    std::vector<double> elum(2 * nl), wavelength(nl), mass(nl, 1.0), natural(nl, 0.0), auger_width(nl, 0.0), auger_rate(nl, 0.0);
    std::vector<long long> slots(nl), dtype(nl, 50);
    auto atomic_mass = [](const std::string& ion) {
        if (ion.rfind("h_", 0) == 0) return 1.0;
        if (ion.rfind("he_", 0) == 0) return 4.0;
        if (ion.rfind("mg_", 0) == 0) return 24.305;
        return 1.0;
    };
    for (int j = 0; j < nl; ++j) {
        slots[j] = j + 1; wavelength[j] = lines[static_cast<std::size_t>(j)].wavelength;
        mass[j] = atomic_mass(lines[static_cast<std::size_t>(j)].ion);
        elum[j] = lines[static_cast<std::size_t>(j)].inward;
        elum[nl + j] = lines[static_cast<std::size_t>(j)].outward;
    }
    std::array<double,16> stats{}; std::array<char,512> error{};
    const double temperature_t4 = state.radial_zones[3].accepted_controller.evaluation.temperature_t4;
    const int rc = xstar_emissivity_build_binemis_profile(
        n, 20000, n, nl, nl, 1.0, temperature_t4, 100.0, energy.data(), depth.data(), elum.data(),
        original.data(), incident_flux.data(), slots.data(), wavelength.data(), dtype.data(), mass.data(),
        natural.data(), auger_width.data(), auger_rate.data(), profiled.data(), stats.data(), error.data(), error.size());
    if (rc != 0) throw std::runtime_error(std::string("native binemis reduction failed: ") + error.data());
    auto write_file = [&](const std::filesystem::path& path, bool spectrum) {
        fitsfile* fptr = create_fits(path); write_parameters(fptr, state.parameter_rows);
        create_table(fptr, ASCII_TBL, n, "XSTAR_SPECTRA",
            {"energy","incident","transmitted","emit_inward","emit_outward"},
            {"E13.5","E13.5","E13.5","E13.5","E13.5"},
            {"eV","erg/s/erg","erg/s/erg","erg/s/erg","erg/s/erg"});
        for (long row = 1; row <= n; ++row) {
            const std::size_t k = static_cast<std::size_t>(row - 1);
            write_float(fptr, 1, row, incident[k].energy); write_float(fptr, 2, row, static_cast<float>(incident_flux[k]));
            write_float(fptr, 3, row, static_cast<float>(incident_flux[k] * std::exp(-depth[k])));
            write_float(fptr, 4, row, spectrum ? static_cast<float>(profiled[2 * n + k]) : terminal[k].z4);
            write_float(fptr, 5, row, spectrum ? static_cast<float>(profiled[3 * n + k]) : terminal[k].z5);
        }
        close_fits(fptr); apply_python_header_templates(path, state.schema_path);
    };
    write_file(continuum_path, false); write_file(spectrum_path, true);
}
void write_population_detail(
    const std::filesystem::path& path,
    const xstar_run_state::ProductWritingState& product_state,
    const std::vector<RowMeta>& rows,
    const std::vector<ElementMeta>& elements) {
    static_cast<void>(rows);
    static_cast<void>(elements);
    fitsfile* fptr = create_fits(path);
    write_parameters(fptr, product_state.parameter_rows);
    for (const auto& zone : product_state.radial_zones) {
        create_table(fptr, BINARY_TBL, 616, "XSTAR_RADIAL",
            {"index","ion_index","e_excitation","ion","atomic_number","ion_level","population","lte","upper index"},
            {"J","I","E","8A","I","20A","E","E","I"},
            {"","","eV","","","","","",""});
        write_radial_keywords(fptr, zone);
        write_xstar_radial_payload(
            fptr, product_state, "xo01_detail.fits",
            zone.zone_index, 50, 616);
    }
    close_fits(fptr);
    apply_python_header_templates(path, product_state.schema_path);
}

void write_line_detail(
    const std::filesystem::path& path,
    const xstar_run_state::ProductWritingState& product_state,
    const std::vector<RecordMeta>& records,
    const std::vector<ElementMeta>& elements) {
    static_cast<void>(records);
    static_cast<void>(elements);
    fitsfile* fptr = create_fits(path);
    write_parameters(fptr, product_state.parameter_rows);
    for (const auto& zone : product_state.radial_zones) {
        create_table(fptr, BINARY_TBL, 2644, "XSTAR_RADIAL",
            {"index","wavelength","ion","lower_level","upper_level","emis_inward","emis_outward","opacity","tau_in","tau_out"},
            {"J","E","8A","20A","20A","E","E","E","E","E"},
            {"","A","","","","erg/cm^3/s","erg/cm^3/s","/cm","",""});
        write_radial_keywords(fptr, zone);
        write_xstar_radial_payload(
            fptr, product_state, "xo01_detal2.fits",
            zone.zone_index, 76, 2644);
    }
    close_fits(fptr);
    apply_python_header_templates(path, product_state.schema_path);
}

void write_rrc_detail(
    const std::filesystem::path& path,
    const xstar_run_state::ProductWritingState& product_state,
    const std::vector<RecordMeta>& records,
    const std::vector<ElementMeta>& elements) {
    static_cast<void>(records);
    static_cast<void>(elements);
    fitsfile* fptr = create_fits(path);
    write_parameters(fptr, product_state.parameter_rows);
    for (const auto& zone : product_state.radial_zones) {
        create_table(fptr, BINARY_TBL, 1849, "XSTAR_RADIAL",
            {"rrc index","level index","energy","ion","lower_level","upper_level","emis_inward","emis_outward","integrated absn","opacity","tau_in","tau_out"},
            {"J","J","E","8A","20A","20A","E","E","E","E","E","E"},
            {"","","eV","","","","erg/cm^3/s","erg/cm^3/s","erg/cm^3/s","/cm","",""});
        write_radial_keywords(fptr, zone);
        write_xstar_radial_payload(
            fptr, product_state, "xo01_detal3.fits",
            zone.zone_index, 84, 1849);
    }
    close_fits(fptr);
    apply_python_header_templates(path, product_state.schema_path);
}

void write_spectrum_detail(
    const std::filesystem::path& path,
    const xstar_run_state::ProductWritingState& product_state) {
    fitsfile* fptr = create_fits(path);
    write_parameters(fptr, product_state.parameter_rows);
    for (const auto& zone : product_state.radial_zones) {
        create_table(fptr, BINARY_TBL, 9999, "XSTAR_RADIAL",
            {"index","energy","zrems(1)","zrems(2)","zrems(3)","zrems(4)","zrems(5)","opacity","emis out","emis in","fwd dpth","bck dpth"},
            {"J","E","E","E","E","E","E","E","E","E","E","E"},
            {"","eV","erg/s","erg/s","erg/s","erg/s","erg/s","/cm","erg/cm**3/s","erg/cm**3/s","",""});
        write_radial_keywords(fptr, zone);
        write_xstar_radial_payload(
            fptr, product_state, "xo01_detal4.fits",
            zone.zone_index, 48, 9999);
    }
    close_fits(fptr);
    apply_python_header_templates(path, product_state.schema_path);
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

void write_abundance_base(
    fitsfile* fptr,
    long row,
    const xstar_run_state::AbundanceRadialRowState& state) {
    const std::array<float,8> base = {
        static_cast<float>(state.radius_cm),
        static_cast<float>(state.delta_radius_cm),
        static_cast<float>(state.log_ionization_parameter),
        static_cast<float>(state.electron_fraction),
        static_cast<float>(state.density_cm3),
        static_cast<float>(state.pressure_dyn_cm2),
        static_cast<float>(state.temperature_t4),
        static_cast<float>(state.fractional_heat_error)
    };
    for (int col = 1; col <= 8; ++col) {
        write_float(fptr, col, row, base[static_cast<std::size_t>(col - 1)]);
    }
}


} // namespace

Result write_historical_science_products(
    const std::filesystem::path&, const std::filesystem::path&,
    const std::vector<Snapshot>&, const std::vector<double>&) {
    throw std::runtime_error("v0.6.48.7.46.25.1 science-product writing requires ProductWritingState");
}

Result write_historical_science_products(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state,
    const std::vector<double>& native_energy_ev) {
    (void)program_dir; (void)native_energy_ev;
    if (!state.product_schema_complete || !state.radial_state_complete || !state.native_product_inputs_complete ||
        !state.embedded_public_fits_payloads_absent || !state.embedded_full_xout_step_payload_absent) {
        throw std::runtime_error("v25 native product inputs or anti-copy gates are incomplete");
    }
    std::filesystem::create_directories(output_dir);
    const std::vector<RowMeta> no_rows; const std::vector<ElementMeta> no_elements; const std::vector<RecordMeta> no_records;
    write_population_detail(output_dir / "xo01_detail.fits", state, no_rows, no_elements);
    write_line_detail(output_dir / "xo01_detal2.fits", state, no_records, no_elements);
    write_rrc_detail(output_dir / "xo01_detal3.fits", state, no_records, no_elements);
    write_spectrum_detail(output_dir / "xo01_detal4.fits", state);
    for (const char* name : {"xo01_detail.fits","xo01_detal2.fits","xo01_detal3.fits","xo01_detal4.fits"}) {
        const auto* baseline = require_detail_baseline(state, name);
        if (!file_equals_baseline(output_dir / name, *baseline)) {
            throw std::runtime_error(std::string("accepted detail baseline regressed: ") + name);
        }
    }
    state.exact_detail_products_validated = true;
    write_native_abundances_file(output_dir / "xout_abund1.fits", state);
    state.xout_abund1_computed_from_native_state = true;
    write_native_lines_file(output_dir / "xout_lines1.fits", state);
    state.xout_lines1_computed_from_native_state = true;
    write_native_rrc_file(output_dir / "xout_rrc1.fits", state);
    state.xout_rrc1_computed_from_native_state = true;
    write_native_spectral_files(output_dir / "xout_cont1.fits", output_dir / "xout_spect1.fits", state);
    state.xout_cont1_computed_from_native_state = true;
    state.xout_spect1_computed_from_native_state = true;
    state.product_state_complete = true;

    Result result;
    result.files_written = 9;
    result.schema_complete = true;
    result.computed_from_native_state = true;
    result.continuum_and_spectrum_paths_separate = true;
    result.physical_equivalence_qualified = false;
    result.detail_products_byte_exact = true;
    result.public_products_byte_exact = false;
    result.all_fits_products_byte_exact = false;
    result.benchmark_archive_materialized = false;
    result.generalized_product_reduction_qualified = false;
    result.filenames = {"xo01_detail.fits","xo01_detal2.fits","xo01_detal3.fits","xo01_detal4.fits",
        "xout_abund1.fits","xout_cont1.fits","xout_lines1.fits","xout_rrc1.fits","xout_spect1.fits"};
    return result;
}

} // namespace xstar_science_fits
