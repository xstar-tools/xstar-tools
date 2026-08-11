// XSTAR2XSPEC table-writer source concordance
// -------------------------------------------
// This file implements the native XSPEC table-FITS assembly stage of the
// XSTAR2XSPEC workflow described in Chapter 6 of the XSTAR Manual.  It was
// developed by direct comparison with the canonical XSTAR sources
// src/xstar2table/xstar2table.c and xstarlib/src/xstartablelib.c.  Those files
// define the PARAMETERS, ENERGIES, and SPECTRA extensions, interpolated versus
// additive parameter ordering, PARAMVAL/INTPSPEC/ADDSPnnn placement, ADDMODEL
// semantics, LASTSPEC sequencing, and the loopcontrol-to-row/column mapping.
//
// This code intentionally reproduces those table-model semantics while using
// CFITSIO directly and adding one fail-closed improvement: every spectrum after
// the first must have exactly the same selected energy grid.  It does not alter
// XSTAR physics; it serializes already-computed xout_spect1.fits products.  The
// 0.6.81.1 canonical MPI_XSTAR 2x3 fixture requires ENERG_LO/HI, PARAMVAL, and
// AIN/AOUT/MTABLE/ETABLE spectral payloads to be bit-exact to XSTAR 2.59g.

#include "xstar_xspec_table_internal.hpp"
#include "xstar_xspec_table.h"

#include <fitsio.h>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace xstar_xspec {
namespace {

// Trim whitespace from one metadata-file token.
std::string trim(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

// Split a metadata-field list while applying the same whitespace normalization.
std::vector<std::string> split(const std::string &value, char delim) {
    std::vector<std::string> out;
    std::stringstream ss(value);
    std::string item;
    while (std::getline(ss, item, delim)) out.push_back(trim(item));
    return out;
}

// Parse one metadata scalar as float32, matching the historical table columns.
float as_float(const std::string &text, const char *field) {
    char *end = nullptr;
    errno = 0;
    const float value = std::strtof(text.c_str(), &end);
    if (errno != 0 || end == text.c_str() || *end != '\0') {
        throw std::runtime_error(std::string("invalid float for ") + field + ": " + text);
    }
    return value;
}

// Parse a bounded native integer from the characterization metadata format.
int as_int(const std::string &text, const char *field) {
    char *end = nullptr;
    errno = 0;
    const long value = std::strtol(text.c_str(), &end, 10);
    if (errno != 0 || end == text.c_str() || *end != '\0' || value < std::numeric_limits<int>::min() || value > std::numeric_limits<int>::max()) {
        throw std::runtime_error(std::string("invalid integer for ") + field + ": " + text);
    }
    return static_cast<int>(value);
}

// Convert a CFITSIO status to a readable exception message.
std::string fits_error(int status) {
    char text[FLEN_STATUS] = {0};
    fits_get_errstatus(status, text);
    return std::string(text);
}

// Raise on a failed CFITSIO operation while preserving operation context.
void fits_check(int status, const std::string &what) {
    if (status != 0) throw std::runtime_error(what + ": " + fits_error(status));
}

struct OpenFits {
    fitsfile *ptr = nullptr;
    // Close a CFITSIO handle on all normal and exceptional exits.
    ~OpenFits() {
        if (ptr != nullptr) {
            int status = 0;
            fits_close_file(ptr, &status);
        }
    }
};

// Return XSPEC parameters in canonical xstartablelib order: all interpolated
// parameters first, then all additive parameters.
std::vector<Parameter> ordered_parameters(const Config &config) {
    std::vector<Parameter> out;
    for (const auto &p : config.parameters) if (p.kind == ParameterKind::interpolated) out.push_back(p);
    for (const auto &p : config.parameters) if (p.kind == ParameterKind::additive) out.push_back(p);
    return out;
}

// Count interpolated parameters written to NINTPARM and PARAMVAL.
size_t nint(const Config &config) {
    return static_cast<size_t>(std::count_if(config.parameters.begin(), config.parameters.end(), [](const Parameter &p) {
        return p.kind == ParameterKind::interpolated;
    }));
}

// Count additive parameters written to NADDPARM and ADDSPnnn columns.
size_t nadd(const Config &config) {
    return static_cast<size_t>(std::count_if(config.parameters.begin(), config.parameters.end(), [](const Parameter &p) {
        return p.kind == ParameterKind::additive;
    }));
}

// Compute the Cartesian product of interpolated VALUE axes; canonical
// XSTAR2XSPEC requires one base spectrum row for each such combination.
size_t ncombos(const Config &config) {
    size_t count = 1;
    for (const auto &p : config.parameters) {
        if (p.kind == ParameterKind::interpolated) {
            if (p.values.empty()) throw std::runtime_error("interpolated parameter has no VALUE list: " + p.name);
            if (count > std::numeric_limits<size_t>::max() / p.values.size()) throw std::runtime_error("parameter-grid size overflow");
            count *= p.values.size();
        }
    }
    return count;
}

// Create the primary HDU and PARAMETERS extension using the OGIP/XSPEC table
// metadata emitted by canonical Create_FITS_ParmTable/xstartablelib routines.
void write_primary_and_parameters(const std::string &path, const Config &config, bool additive_model) {
    OpenFits file;
    int status = 0;
    std::string create_path = "!" + path;
    fits_create_file(&file.ptr, create_path.c_str(), &status);
    fits_check(status, "create table FITS");
    fits_create_img(file.ptr, SHORT_IMG, 0, nullptr, &status);
    fits_check(status, "create primary HDU");
    fits_write_date(file.ptr, &status);
    fits_check(status, "write DATE");

    std::string modlname = config.model_name.substr(0, 12);
    char *modlname_ptr = const_cast<char *>(modlname.c_str());
    fits_write_key(file.ptr, TSTRING, const_cast<char *>("MODLNAME"), modlname_ptr, const_cast<char *>("first 12 characters of model name"), &status);
    fits_check(status, "write MODLNAME");
    std::string modlunit = config.spectrum_units == 1 ? "photons/cm**2/s" : "ergs/cm**2/s";
    char *modlunit_ptr = const_cast<char *>(modlunit.c_str());
    fits_write_key(file.ptr, TSTRING, const_cast<char *>("MODLUNIT"), modlunit_ptr, const_cast<char *>("model units"), &status);
    fits_check(status, "write MODLUNIT");
    int redshift = config.redshift ? 1 : 0;
    fits_write_key(file.ptr, TLOGICAL, const_cast<char *>("REDSHIFT"), &redshift, const_cast<char *>("Is redshift a parameter?"), &status);
    fits_check(status, "write REDSHIFT");
    int addmodel = additive_model ? 1 : 0;
    fits_write_key(file.ptr, TLOGICAL, const_cast<char *>("ADDMODEL"), &addmodel,
                   const_cast<char *>(additive_model ? "Additive Model" : "Multiplicative/Exponential Model"), &status);
    fits_check(status, "write ADDMODEL");
    const char *ogip = "OGIP";
    const char *doc = "OGIP/92-009";
    const char *klass = "XSPEC TABLE MODEL";
    const char *vers = "1.0.0";
    fits_write_key(file.ptr, TSTRING, const_cast<char *>("HDUCLASS"), const_cast<char *>(ogip), const_cast<char *>("format conforms to OGIP standard"), &status);
    fits_write_key(file.ptr, TSTRING, const_cast<char *>("HDUDOC"), const_cast<char *>(doc), const_cast<char *>("document defining format"), &status);
    fits_write_key(file.ptr, TSTRING, const_cast<char *>("HDUCLAS1"), const_cast<char *>(klass), const_cast<char *>("model spectra for XSPEC"), &status);
    fits_write_key(file.ptr, TSTRING, const_cast<char *>("HDUVERS1"), const_cast<char *>(vers), const_cast<char *>("version of format"), &status);
    fits_check(status, "write primary OGIP keywords");

    const auto params = ordered_parameters(config);
    const size_t max_values = std::max<size_t>(1, [&]() {
        size_t m = 0;
        for (const auto &p : params) m = std::max(m, p.values.size());
        return m;
    }());
    std::string value_form = std::to_string(max_values) + "E";
    char *ttype[] = {
        const_cast<char *>("NAME"), const_cast<char *>("METHOD"), const_cast<char *>("INITIAL"), const_cast<char *>("DELTA"),
        const_cast<char *>("MINIMUM"), const_cast<char *>("BOTTOM"), const_cast<char *>("TOP"), const_cast<char *>("MAXIMUM"),
        const_cast<char *>("NUMBVALS"), const_cast<char *>("VALUE")};
    char *tform[] = {
        const_cast<char *>("12A"), const_cast<char *>("J"), const_cast<char *>("E"), const_cast<char *>("E"),
        const_cast<char *>("E"), const_cast<char *>("E"), const_cast<char *>("E"), const_cast<char *>("E"),
        const_cast<char *>("J"), const_cast<char *>(value_form.c_str())};
    char *tunit[] = {
        const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>(""),
        const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>("")};
    fits_create_tbl(file.ptr, BINARY_TBL, static_cast<LONGLONG>(params.size()), 10, ttype, tform, tunit,
                    const_cast<char *>("PARAMETERS"), &status);
    fits_check(status, "create PARAMETERS");

    for (size_t i = 0; i < params.size(); ++i) {
        const long row = static_cast<long>(i + 1);
        const auto &p = params[i];
        char name_buf[13] = {0};
        std::snprintf(name_buf, sizeof(name_buf), "%s", p.name.c_str());
        char *name_ptr = name_buf;
        long method = p.method;
        long numbvals = p.kind == ParameterKind::interpolated ? static_cast<long>(p.values.size()) : 0L;
        float values[1] = {0.0f};
        fits_write_col(file.ptr, TSTRING, 1, row, 1, 1, &name_ptr, &status);
        fits_write_col(file.ptr, TLONG, 2, row, 1, 1, &method, &status);
        float scalar = p.initial; fits_write_col(file.ptr, TFLOAT, 3, row, 1, 1, &scalar, &status);
        scalar = p.delta; fits_write_col(file.ptr, TFLOAT, 4, row, 1, 1, &scalar, &status);
        scalar = p.hard_min; fits_write_col(file.ptr, TFLOAT, 5, row, 1, 1, &scalar, &status);
        scalar = p.soft_min; fits_write_col(file.ptr, TFLOAT, 6, row, 1, 1, &scalar, &status);
        scalar = p.soft_max; fits_write_col(file.ptr, TFLOAT, 7, row, 1, 1, &scalar, &status);
        scalar = p.hard_max; fits_write_col(file.ptr, TFLOAT, 8, row, 1, 1, &scalar, &status);
        fits_write_col(file.ptr, TLONG, 9, row, 1, 1, &numbvals, &status);
        std::vector<float> padded(max_values, 0.0f);
        for (size_t k = 0; k < p.values.size(); ++k) padded[k] = p.values[k];
        fits_write_col(file.ptr, TFLOAT, 10, row, 1, static_cast<long>(max_values), padded.data(), &status);
        fits_check(status, "write PARAMETERS row");
        (void)values;
    }

    int nint_value = static_cast<int>(nint(config));
    int nadd_value = static_cast<int>(nadd(config));
    fits_write_key(file.ptr, TINT, const_cast<char *>("NINTPARM"), &nint_value, const_cast<char *>("number of interpolated parameters"), &status);
    fits_write_key(file.ptr, TINT, const_cast<char *>("NADDPARM"), &nadd_value, const_cast<char *>("number of additional parameters"), &status);
    float fvalue = config.elow_ev; fits_write_key(file.ptr, TFLOAT, const_cast<char *>("ELOW"), &fvalue, const_cast<char *>("energy band low end (eV)"), &status);
    fvalue = config.ehigh_ev; fits_write_key(file.ptr, TFLOAT, const_cast<char *>("EHIGH"), &fvalue, const_cast<char *>("energy band high end (eV)"), &status);
    for (const auto &[name, value] : config.constants) {
        std::string key = name.substr(0, 8);
        float v = value;
        fits_write_key(file.ptr, TFLOAT, const_cast<char *>(key.c_str()), &v, const_cast<char *>("physical parameter held constant"), &status);
    }
    auto write_string = [&](const char *key, const std::string &value, const char *comment) {
        fits_write_key(file.ptr, TSTRING, const_cast<char *>(key), const_cast<char *>(value.c_str()), const_cast<char *>(comment), &status);
    };
    write_string("SPECTRUM", config.spectrum_name, "spectrum name");
    write_string("SPECFILE", config.spectrum_file, "spectrum file");
    int ivalue = config.spectrum_units; fits_write_key(file.ptr, TINT, const_cast<char *>("SPECUNIT"), &ivalue, const_cast<char *>("spectral units (0=energy, 1=photons)"), &status);
    write_string("ABUNDTBL", config.abundance_table, "abundance table");
    ivalue = config.nsteps; fits_write_key(file.ptr, TINT, const_cast<char *>("NSTEPS"), &ivalue, const_cast<char *>("Number of steps"), &status);
    ivalue = config.niter; fits_write_key(file.ptr, TINT, const_cast<char *>("NITER"), &ivalue, const_cast<char *>("Number of iterations"), &status);
    ivalue = config.write_switch; fits_write_key(file.ptr, TINT, const_cast<char *>("WRITESW"), &ivalue, const_cast<char *>("write switch"), &status);
    ivalue = config.print_switch; fits_write_key(file.ptr, TINT, const_cast<char *>("PRINTSW"), &ivalue, const_cast<char *>("print switch"), &status);
    ivalue = config.step_size; fits_write_key(file.ptr, TINT, const_cast<char *>("STEPSIZE"), &ivalue, const_cast<char *>("step size choice switch"), &status);
    ivalue = config.npass; fits_write_key(file.ptr, TINT, const_cast<char *>("NPASS"), &ivalue, const_cast<char *>("number of passes"), &status);
    ivalue = config.pressure_switch; fits_write_key(file.ptr, TINT, const_cast<char *>("PRESSSW"), &ivalue, const_cast<char *>("constant pressure switch"), &status);
    fvalue = config.emult; fits_write_key(file.ptr, TFLOAT, const_cast<char *>("EMULT"), &fvalue, const_cast<char *>("courant multiplier"), &status);
    fvalue = config.taumax; fits_write_key(file.ptr, TFLOAT, const_cast<char *>("TAUMAX"), &fvalue, const_cast<char *>("tau max for courant step"), &status);
    fvalue = config.xeemin; fits_write_key(file.ptr, TFLOAT, const_cast<char *>("XEEMIN"), &fvalue, const_cast<char *>("minimum electron fraction"), &status);
    fvalue = config.critf; fits_write_key(file.ptr, TFLOAT, const_cast<char *>("CRITF"), &fvalue, const_cast<char *>("critical ion abundance"), &status);
    fvalue = config.radexp; fits_write_key(file.ptr, TFLOAT, const_cast<char *>("RADEXP"), &fvalue, const_cast<char *>("radius exponent"), &status);
    ivalue = config.ncn2; fits_write_key(file.ptr, TINT, const_cast<char *>("NCN2"), &ivalue, const_cast<char *>("number of energy bins"), &status);
    write_string("MODELNAM", config.model_name, "model name");
    fits_write_key(file.ptr, TSTRING, const_cast<char *>("HDUCLASS"), const_cast<char *>(ogip), const_cast<char *>("format conforms to OGIP standard"), &status);
    fits_write_key(file.ptr, TSTRING, const_cast<char *>("HDUDOC"), const_cast<char *>(doc), const_cast<char *>("document defining format"), &status);
    fits_write_key(file.ptr, TSTRING, const_cast<char *>("HDUCLAS1"), const_cast<char *>(klass), const_cast<char *>("model spectra for XSPEC"), &status);
    fits_write_key(file.ptr, TSTRING, const_cast<char *>("HDUVERS1"), const_cast<char *>(vers), const_cast<char *>("version of format"), &status);
    fits_check(status, "write PARAMETERS keywords");
}

// Append the canonical ENERGIES and SPECTRA extensions.  The SPECTRA schema
// contains PARAMVAL, INTPSPEC, and one ADDSPnnn vector per additive parameter.
void write_energies_and_spectra_headers(fitsfile *fptr, const std::vector<float> &elow_kev, const std::vector<float> &ehigh_kev,
                                        size_t combos, size_t nint_value, size_t nadd_value, bool additive_model) {
    int status = 0;
    char *energy_types[] = {const_cast<char *>("ENERG_LO"), const_cast<char *>("ENERG_HI")};
    char *energy_forms[] = {const_cast<char *>("E"), const_cast<char *>("E")};
    char *energy_units[] = {const_cast<char *>("keV"), const_cast<char *>("keV")};
    fits_create_tbl(fptr, BINARY_TBL, static_cast<LONGLONG>(elow_kev.size()), 2, energy_types, energy_forms, energy_units,
                    const_cast<char *>("ENERGIES"), &status);
    fits_check(status, "create ENERGIES");
    fits_write_col(fptr, TFLOAT, 1, 1, 1, static_cast<long>(elow_kev.size()), const_cast<float *>(elow_kev.data()), &status);
    fits_write_col(fptr, TFLOAT, 2, 1, 1, static_cast<long>(ehigh_kev.size()), const_cast<float *>(ehigh_kev.data()), &status);
    const char *klass = "XSPEC TABLE MODEL"; const char *klass2 = "ENERGIES"; const char *vers = "1.0.0";
    fits_write_key(fptr, TSTRING, const_cast<char *>("HDUCLAS1"), const_cast<char *>(klass), const_cast<char *>("model spectra for XSPEC"), &status);
    fits_write_key(fptr, TSTRING, const_cast<char *>("HDUCLAS2"), const_cast<char *>(klass2), const_cast<char *>("extension containing energy bin info"), &status);
    fits_write_key(fptr, TSTRING, const_cast<char *>("HDUVERS1"), const_cast<char *>(vers), const_cast<char *>("version of format"), &status);
    fits_check(status, "write ENERGIES");

    const size_t field_count = nadd_value + 2;
    std::vector<std::string> names(field_count), forms(field_count), units(field_count);
    names[0] = "PARAMVAL"; forms[0] = std::to_string(nint_value) + "E"; units[0] = " ";
    names[1] = "INTPSPEC"; forms[1] = std::to_string(elow_kev.size()) + "E"; units[1] = additive_model ? "photons/cm^2/s" : " ";
    for (size_t j = 2; j < field_count; ++j) {
        char buffer[32]; std::snprintf(buffer, sizeof(buffer), "ADDSP%03zu", j - 1);
        names[j] = buffer; forms[j] = forms[1]; units[j] = units[1];
    }
    std::vector<char *> name_ptrs(field_count), form_ptrs(field_count), unit_ptrs(field_count);
    for (size_t j = 0; j < field_count; ++j) {
        name_ptrs[j] = names[j].data(); form_ptrs[j] = forms[j].data(); unit_ptrs[j] = units[j].data();
    }
    fits_create_tbl(fptr, BINARY_TBL, static_cast<LONGLONG>(combos), static_cast<int>(field_count), name_ptrs.data(), form_ptrs.data(), unit_ptrs.data(),
                    const_cast<char *>("SPECTRA"), &status);
    fits_check(status, "create SPECTRA");
    long zero = 0;
    fits_write_key(fptr, TLONG, const_cast<char *>("LASTSPEC"), &zero, const_cast<char *>("last spectrum written to table"), &status);
    const char *klass_s = "XSPEC TABLE MODEL"; const char *klass_s2 = "MODEL SPECTRA";
    fits_write_key(fptr, TSTRING, const_cast<char *>("HDUCLAS1"), const_cast<char *>(klass_s), const_cast<char *>("model spectra for XSPEC"), &status);
    fits_write_key(fptr, TSTRING, const_cast<char *>("HDUCLAS2"), const_cast<char *>(klass_s2), const_cast<char *>("extension containing model spectra"), &status);
    fits_write_key(fptr, TSTRING, const_cast<char *>("HDUVERS1"), const_cast<char *>(vers), const_cast<char *>("version of format"), &status);
    fits_check(status, "write SPECTRA header");
}

// Open one partially created table and append its energy/spectrum extensions.
void append_headers(const std::string &path, const std::vector<float> &elow_kev, const std::vector<float> &ehigh_kev,
                    size_t combos, size_t nint_value, size_t nadd_value, bool additive_model) {
    OpenFits file;
    int status = 0;
    fits_open_file(&file.ptr, path.c_str(), READWRITE, &status); fits_check(status, "open table for headers");
    write_energies_and_spectra_headers(file.ptr, elow_kev, ehigh_kev, combos, nint_value, nadd_value, additive_model);
}

// Insert one converted spectrum at the canonical loopcontrol-derived row/column.
// 0.6.81/0.6.82 compatibility retains historical LASTSPEC sequential ordering.
void write_spectrum_row(const std::string &path, size_t loopcontrol, size_t row, size_t column,
                        const std::vector<float> &paramvals, const std::vector<float> &spectrum) {
    OpenFits file;
    int status = 0;
    fits_open_file(&file.ptr, path.c_str(), READWRITE, &status); fits_check(status, "open table for spectrum");
    fits_movnam_hdu(file.ptr, BINARY_TBL, const_cast<char *>("SPECTRA"), 0, &status); fits_check(status, "move SPECTRA");
    long lastspec = 0;
    fits_read_key(file.ptr, TLONG, const_cast<char *>("LASTSPEC"), &lastspec, nullptr, &status); fits_check(status, "read LASTSPEC");
    if (lastspec + 1 != static_cast<long>(loopcontrol)) throw std::runtime_error("non-sequential loopcontrol in 0.6.81 compatibility path");
    if (column == 0) {
        if (!paramvals.empty()) fits_write_col(file.ptr, TFLOAT, 1, static_cast<long>(row), 1, static_cast<long>(paramvals.size()), const_cast<float *>(paramvals.data()), &status);
        fits_write_col(file.ptr, TFLOAT, 2, static_cast<long>(row), 1, static_cast<long>(spectrum.size()), const_cast<float *>(spectrum.data()), &status);
    } else {
        fits_write_col(file.ptr, TFLOAT, static_cast<int>(2 + column), static_cast<long>(row), 1, static_cast<long>(spectrum.size()), const_cast<float *>(spectrum.data()), &status);
    }
    fits_check(status, "write SPECTRA row");
    long lc = static_cast<long>(loopcontrol);
    fits_update_key(file.ptr, TLONG, const_cast<char *>("LASTSPEC"), &lc, const_cast<char *>("Last spectrum written"), &status);
    fits_check(status, "update LASTSPEC");
}

// Read one XSTAR run parameter through the shared xout_spect1 PARAMETERS reader.
float read_param(const std::string &path, const std::string &name) {
    float value = 0.0f;
    char message[512] = {0};
    if (xstar_xspec_read_parameter_v1(path.c_str(), name.c_str(), &value, message, sizeof(message)) != 0) {
        throw std::runtime_error("cannot read " + name + " from " + path + ": " + message);
    }
    return value;
}

}  // namespace

// Parse the 0.6.81 characterization metadata representation of the table grid.
// This temporary compatibility format is replaced later by native xstinitable.
Config parse_config(const std::string &path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open metadata config: " + path);
    Config config;
    std::string line;
    size_t line_no = 0;
    while (std::getline(in, line)) {
        ++line_no;
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        const auto pos = line.find('=');
        if (pos == std::string::npos) throw std::runtime_error("metadata line has no '=' at line " + std::to_string(line_no));
        const std::string key = trim(line.substr(0, pos));
        const std::string value = trim(line.substr(pos + 1));
        if (key == "MODEL_NAME") config.model_name = value;
        else if (key == "SPECTRUM_NAME") config.spectrum_name = value;
        else if (key == "SPECTRUM_FILE") config.spectrum_file = value;
        else if (key == "ABUNDANCE_TABLE") config.abundance_table = value;
        else if (key == "SPECTRUM_UNITS") config.spectrum_units = as_int(value, "SPECTRUM_UNITS");
        else if (key == "REDSHIFT") config.redshift = as_int(value, "REDSHIFT");
        else if (key == "ELOW") config.elow_ev = as_float(value, "ELOW");
        else if (key == "EHIGH") config.ehigh_ev = as_float(value, "EHIGH");
        else if (key == "NSTEPS") config.nsteps = as_int(value, "NSTEPS");
        else if (key == "NITER") config.niter = as_int(value, "NITER");
        else if (key == "WRITESW") config.write_switch = as_int(value, "WRITESW");
        else if (key == "PRINTSW") config.print_switch = as_int(value, "PRINTSW");
        else if (key == "STEPSIZE") config.step_size = as_int(value, "STEPSIZE");
        else if (key == "NPASS") config.npass = as_int(value, "NPASS");
        else if (key == "PRESSSW") config.pressure_switch = as_int(value, "PRESSSW");
        else if (key == "EMULT") config.emult = as_float(value, "EMULT");
        else if (key == "TAUMAX") config.taumax = as_float(value, "TAUMAX");
        else if (key == "XEEMIN") config.xeemin = as_float(value, "XEEMIN");
        else if (key == "CRITF") config.critf = as_float(value, "CRITF");
        else if (key == "RADEXP") config.radexp = as_float(value, "RADEXP");
        else if (key == "NCN2") config.ncn2 = as_int(value, "NCN2");
        else if (key == "CONST") {
            const auto fields = split(value, '|');
            if (fields.size() != 2) throw std::runtime_error("CONST requires name|value");
            config.constants.emplace_back(fields[0], as_float(fields[1], "CONST"));
        } else if (key == "PARAM") {
            auto fields = split(value, '|');
            if (fields.size() == 9) fields.push_back("");
            if (fields.size() != 10) throw std::runtime_error("PARAM requires kind|name|method|initial|delta|min|bottom|top|max|values");
            Parameter p;
            if (fields[0] == "interpolated") p.kind = ParameterKind::interpolated;
            else if (fields[0] == "additive") p.kind = ParameterKind::additive;
            else throw std::runtime_error("PARAM kind must be interpolated or additive");
            p.name = fields[1]; p.method = as_int(fields[2], "PARAM method"); p.initial = as_float(fields[3], "PARAM initial");
            p.delta = as_float(fields[4], "PARAM delta"); p.hard_min = as_float(fields[5], "PARAM minimum");
            p.soft_min = as_float(fields[6], "PARAM bottom"); p.soft_max = as_float(fields[7], "PARAM top"); p.hard_max = as_float(fields[8], "PARAM maximum");
            if (!fields[9].empty()) for (const auto &entry : split(fields[9], ',')) if (!entry.empty()) p.values.push_back(as_float(entry, "PARAM VALUE"));
            if (p.kind == ParameterKind::interpolated && p.values.empty()) throw std::runtime_error("interpolated PARAM requires values");
            config.parameters.push_back(std::move(p));
        } else {
            throw std::runtime_error("unknown metadata key: " + key);
        }
    }
    if (config.parameters.empty()) throw std::runtime_error("at least one interpolated/additive parameter is required for XSPEC table characterization");
    if (nint(config) == 0) throw std::runtime_error("0.6.81 characterization requires at least one interpolated parameter");
    if (config.ehigh_ev < config.elow_ev) throw std::runtime_error("EHIGH must be >= ELOW");
    return config;
}

// Reproduce the canonical xstar2table assembly loop for the four XSTAR2XSPEC
// outputs.  Grid rows/columns use (loopcontrol-1)/(NADDPARM+1) and modulo,
// exactly as in xstar2table.c; all spectra are additionally required to share
// the first spectrum's selected energy grid.
void build_tables(const Config &config, const std::vector<std::string> &spectra, const std::string &output_dir) {
    const size_t nint_value = nint(config);
    const size_t nadd_value = nadd(config);
    const size_t combos = ncombos(config);
    const size_t expected = combos * (nadd_value + 1);
    if (spectra.size() != expected) {
        throw std::runtime_error("spectrum count does not match canonical (NADDPARM+1)*product(interpolated values): expected " +
                                 std::to_string(expected) + ", got " + std::to_string(spectra.size()));
    }
    fs::create_directories(output_dir);
    const std::string ain_path = (fs::path(output_dir) / "xout_ain.fits").string();
    const std::string aout_path = (fs::path(output_dir) / "xout_aout.fits").string();
    const std::string mtable_path = (fs::path(output_dir) / "xout_mtable.fits").string();
    const std::string etable_path = (fs::path(output_dir) / "xout_etable.fits").string();
    write_primary_and_parameters(ain_path, config, true);
    write_primary_and_parameters(aout_path, config, true);
    write_primary_and_parameters(mtable_path, config, false);
    write_primary_and_parameters(etable_path, config, false);

    xstar_xspec_slice_v1 canonical_slice{};
    std::vector<float> canonical_edges;
    bool headers_written = false;
    for (size_t job = 0; job < spectra.size(); ++job) {
        const size_t expected_loopcontrol = job + 1;
        const float loopcontrol_f = read_param(spectra[job], "loopcontrol");
        /*
         * XSTAR2XSPEC supplies positive 1-based loopcontrol values.  Ordinary
         * standalone XSTAR commonly records loopcontrol=0; for that explicit
         * compatibility case, the caller-provided file order supplies the
         * canonical job index.
         */
        const size_t loopcontrol = loopcontrol_f > 0.0f ? static_cast<size_t>(std::llround(loopcontrol_f)) : expected_loopcontrol;
        if (loopcontrol != expected_loopcontrol) {
            throw std::runtime_error("0.6.81 compatibility path requires sequential loopcontrol/file order; expected " + std::to_string(expected_loopcontrol) +
                                     ", got " + std::to_string(loopcontrol));
        }
        xstar_xspec_spectrum_handle_v1 *handle = nullptr;
        xstar_xspec_spectrum_v1 view{};
        char message[512] = {0};
        if (xstar_xspec_spectrum_open_v1(spectra[job].c_str(), &handle, &view, message, sizeof(message)) != 0) {
            throw std::runtime_error("read spectrum failed: " + std::string(message));
        }
        struct HandleGuard { xstar_xspec_spectrum_handle_v1 *h; ~HandleGuard(){ xstar_xspec_spectrum_close_v1(h); } } guard{handle};
        xstar_xspec_slice_v1 slice{};
        if (xstar_xspec_slice_energy_v1(&view, config.elow_ev, config.ehigh_ev, &slice, message, sizeof(message)) != 0) {
            throw std::runtime_error("slice failed: " + std::string(message));
        }
        if (!headers_written) {
            canonical_slice = slice;
            canonical_edges.assign(view.energy_ev + slice.first_bin, view.energy_ev + slice.first_bin + slice.bin_count + 1);
            std::vector<float> lows(slice.bin_count), highs(slice.bin_count);
            for (size_t i = 0; i < slice.bin_count; ++i) {
                lows[i] = canonical_edges[i] / 1000.0f;
                highs[i] = canonical_edges[i + 1] / 1000.0f;
            }
            append_headers(ain_path, lows, highs, combos, nint_value, nadd_value, true);
            append_headers(aout_path, lows, highs, combos, nint_value, nadd_value, true);
            append_headers(mtable_path, lows, highs, combos, nint_value, nadd_value, false);
            append_headers(etable_path, lows, highs, combos, nint_value, nadd_value, false);
            headers_written = true;
        } else {
            if (slice.first_bin != canonical_slice.first_bin || slice.bin_count != canonical_slice.bin_count) throw std::runtime_error("energy slice differs between spectra");
            for (size_t i = 0; i < canonical_edges.size(); ++i) {
                if (view.energy_ev[slice.first_bin + i] != canonical_edges[i]) throw std::runtime_error("energy grid differs between spectra");
            }
        }
        const float luminosity = read_param(spectra[job], "rlrad38");
        std::vector<float> ain(slice.bin_count), aout(slice.bin_count), mtable(slice.bin_count), etable(slice.bin_count);
        if (xstar_xspec_transform_v1(&view, slice, luminosity, ain.data(), aout.data(), mtable.data(), etable.data(), message, sizeof(message)) != 0) {
            throw std::runtime_error("transform failed: " + std::string(message));
        }
        const size_t row = 1 + (loopcontrol - 1) / (nadd_value + 1);
        const size_t column = (loopcontrol - 1) % (nadd_value + 1);
        std::vector<float> paramvals;
        if (column == 0) {
            for (const auto &p : config.parameters) if (p.kind == ParameterKind::interpolated) paramvals.push_back(read_param(spectra[job], p.name));
        }
        write_spectrum_row(ain_path, loopcontrol, row, column, paramvals, ain);
        write_spectrum_row(aout_path, loopcontrol, row, column, paramvals, aout);
        write_spectrum_row(mtable_path, loopcontrol, row, column, paramvals, mtable);
        write_spectrum_row(etable_path, loopcontrol, row, column, paramvals, etable);
    }
}

}  // namespace xstar_xspec
