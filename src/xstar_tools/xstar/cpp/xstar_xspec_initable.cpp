// Native xstinitable source concordance
// ------------------------------------
// This translation unit is a source-faithful C++17 implementation of the
// canonical XSTAR 2.59g src/xstinitable/xstinitable.c grid-planning stage.
// It reproduces the two artifacts consumed by xstar2xspec / MPI_XSTAR:
// xstinitable.lis and xstinitable.fits.  It does not execute XSTAR jobs and
// does not build final XSPEC tables.
//
// Source behavior deliberately preserved here includes:
//   * the fixed 39-parameter physical ordering from xstinitable.c;
//   * type 0/1/2 = constant/additive/interpolated;
//   * interpolation method 0/1 = linear/logarithmic;
//   * float32 parameter/grid arithmetic;
//   * highest interpolated parameter index varying fastest;
//   * additive expansion: all-zero base, then one active additive parameter;
//   * canonical command formatting and loopcontrol sequencing;
//   * native xstar-cpp command emission by default, with explicit Fortran compatibility;
//   * canonical OGIP PARAMETERS skeleton written with CFITSIO.
//
// Two legacy undefined cases are made fail-closed rather than copied:
// zero interpolated parameters and interpolated nst < 2.  Canonical
// Generate_Combinations indexes numpars-1 and interpolation formulas divide by
// nst-1; accepting those inputs would not provide a stable source contract.

#include "xstar_xspec_initable_internal.hpp"

#include <fitsio.h>

#include <algorithm>
#include <array>
#include <cerrno>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace xstar_xspec_initable {
namespace {

constexpr std::size_t kMaxParmLineLength = 2000;

struct DefaultPhysical {
    const char *name;
    float initial;
    int type;
    int method;
    float soft_minimum;
    int nst;
};

// Defaults transcribed from XSTAR 2.59g xstinitable.par in canonical
// xstinitable.c physical-parameter order.  For constant/additive parameters
// the interpolation defaults are inert, exactly as in Get_Parms().
constexpr std::array<DefaultPhysical, 39> kPhysicalDefaults{{
    {"trad", -1.2f, 0, 1, 0.0f, 1},
    {"cfrac", 1.0f, 0, 1, 0.0f, 1},
    {"temperature", 100.0f, 0, 1, 0.0f, 1},
    {"pressure", 0.03f, 0, 1, 0.0f, 1},
    {"density", 1.0e12f, 0, 1, 0.0f, 1},
    {"rlrad38", 1.0e6f, 0, 1, 0.0f, 1},
    {"column", 1.0e24f, 2, 1, 1.0e21f, 7},
    {"rlogxi", 5.0f, 2, 0, 1.0f, 9},
    {"habund", 1.0f, 0, 1, 0.0f, 1},
    {"heabund", 1.0f, 0, 1, 0.0f, 1},
    {"liabund", 0.0f, 0, 1, 0.0f, 1},
    {"beabund", 0.0f, 0, 1, 0.0f, 1},
    {"babund", 0.0f, 0, 1, 0.0f, 1},
    {"cabund", 1.0f, 0, 1, 0.0f, 1},
    {"nabund", 1.0f, 0, 1, 0.0f, 1},
    {"oabund", 1.0f, 0, 1, 0.0f, 1},
    {"fabund", 1.0f, 0, 1, 0.0f, 1},
    {"neabund", 1.0f, 0, 1, 0.0f, 1},
    {"naabund", 0.0f, 0, 1, 0.0f, 1},
    {"mgabund", 1.0f, 0, 1, 0.0f, 1},
    {"alabund", 0.0f, 0, 1, 0.0f, 1},
    {"siabund", 1.0f, 0, 1, 0.0f, 1},
    {"pabund", 0.0f, 0, 1, 0.0f, 1},
    {"sabund", 1.0f, 0, 1, 0.0f, 1},
    {"clabund", 0.0f, 0, 1, 0.0f, 1},
    {"arabund", 1.0f, 0, 1, 0.0f, 1},
    {"kabund", 0.0f, 0, 1, 0.0f, 1},
    {"caabund", 1.0f, 0, 1, 0.0f, 1},
    {"scabund", 0.0f, 0, 1, 0.0f, 1},
    {"tiabund", 0.0f, 0, 1, 0.0f, 1},
    {"vabund", 0.0f, 0, 1, 0.0f, 1},
    {"crabund", 0.0f, 0, 1, 0.0f, 1},
    {"mnabund", 0.0f, 0, 1, 0.0f, 1},
    {"feabund", 1.0f, 0, 1, 0.0f, 1},
    {"coabund", 0.0f, 0, 1, 0.0f, 1},
    {"niabund", 0.0f, 0, 1, 0.0f, 1},
    {"cuabund", 0.0f, 0, 1, 0.0f, 1},
    {"znabund", 0.0f, 0, 1, 0.0f, 1},
    {"vturbi", 300.0f, 0, 0, 0.0f, 1},
}};

std::string strip_quotes(std::string value) {
    if (value.size() >= 2 && ((value.front() == '\'' && value.back() == '\'') || (value.front() == '"' && value.back() == '"'))) {
        return value.substr(1, value.size() - 2);
    }
    return value;
}

float parse_float(const std::string &text, const std::string &name) {
    char *end = nullptr;
    errno = 0;
    const float value = std::strtof(text.c_str(), &end);
    if (errno != 0 || end == text.c_str() || *end != '\0') {
        throw std::runtime_error("invalid floating value for " + name + ": " + text);
    }
    return value;
}

int parse_int(const std::string &text, const std::string &name) {
    char *end = nullptr;
    errno = 0;
    const long value = std::strtol(text.c_str(), &end, 10);
    if (errno != 0 || end == text.c_str() || *end != '\0' || value < std::numeric_limits<int>::min() || value > std::numeric_limits<int>::max()) {
        throw std::runtime_error("invalid integer value for " + name + ": " + text);
    }
    return static_cast<int>(value);
}

std::string format_g(float value) {
    char buffer[64];
    std::snprintf(buffer, sizeof(buffer), "%g", static_cast<double>(value));
    return buffer;
}

std::string format_f(float value) {
    char buffer[64];
    std::snprintf(buffer, sizeof(buffer), "%f", static_cast<double>(value));
    return buffer;
}

std::string fits_error(int status) {
    char text[FLEN_STATUS] = {0};
    fits_get_errstatus(status, text);
    return std::string(text);
}

void fits_check(int status, const std::string &context) {
    if (status != 0) throw std::runtime_error(context + ": " + fits_error(status));
}

struct FitsHandle {
    fitsfile *ptr = nullptr;
    ~FitsHandle() {
        if (ptr) {
            int status = 0;
            fits_close_file(ptr, &status);
        }
    }
};

std::map<std::string, std::string> parse_arguments(const std::vector<std::string> &arguments) {
    std::map<std::string, std::string> out;
    for (const auto &arg : arguments) {
        const auto pos = arg.find('=');
        if (pos == std::string::npos || pos == 0) throw std::runtime_error("expected XPI-style key=value argument: " + arg);
        std::string key = arg.substr(0, pos);
        std::string value = strip_quotes(arg.substr(pos + 1));
        if (key.empty()) throw std::runtime_error("empty parameter name");
        out[key] = value;
    }
    return out;
}

std::string get_string(const std::map<std::string, std::string> &args, const std::string &name, const std::string &fallback) {
    auto it = args.find(name);
    return it == args.end() ? fallback : it->second;
}

float get_float(const std::map<std::string, std::string> &args, const std::string &name, float fallback) {
    auto it = args.find(name);
    return it == args.end() ? fallback : parse_float(it->second, name);
}

int get_int(const std::map<std::string, std::string> &args, const std::string &name, int fallback) {
    auto it = args.find(name);
    return it == args.end() ? fallback : parse_int(it->second, name);
}

void build_sampling(PhysicalParameter &p) {
    if (p.type == VariationType::constant) {
        p.method = InterpolationMethod::linear;
        p.delta = -1.0f;
        p.soft_minimum = 0.0f;
        p.soft_maximum = 0.0f;
        p.hard_minimum = 0.0f;
        p.hard_maximum = 0.0f;
        p.number_of_values = 0;
        p.values.clear();
        return;
    }
    if (p.type == VariationType::additive) {
        p.method = InterpolationMethod::linear;
        p.delta = -1.0f;
        p.soft_minimum = 0.0f;
        p.soft_maximum = p.initial;
        p.hard_minimum = p.soft_minimum;
        p.hard_maximum = p.soft_maximum;
        p.number_of_values = 0;
        p.values.clear();
        return;
    }
    if (p.number_of_values < 2) {
        throw std::runtime_error("interpolated parameter " + p.name + " requires nst >= 2 for a defined canonical grid");
    }
    const float maximum = p.soft_maximum;
    const float minimum = p.soft_minimum;
    p.hard_minimum = minimum;
    p.hard_maximum = maximum;
    p.values.assign(static_cast<std::size_t>(p.number_of_values), 0.0f);
    if (p.method == InterpolationMethod::linear) {
        const float step = (maximum - minimum) / static_cast<float>(p.number_of_values - 1);
        for (int i = 0; i < p.number_of_values; ++i) p.values[static_cast<std::size_t>(i)] = minimum + static_cast<float>(i) * step;
        p.delta = step;
        p.initial = (maximum + minimum) / 2.0f;
    } else {
        if (minimum <= 0.0f || maximum <= 0.0f) {
            throw std::runtime_error("minimum and maximum must be > 0 for logarithmic sampling of " + p.name);
        }
        const float step = (std::log10(maximum) - std::log10(minimum)) / static_cast<float>(p.number_of_values - 1);
        for (int i = 0; i < p.number_of_values; ++i) {
            p.values[static_cast<std::size_t>(i)] = minimum * std::pow(10.0f, static_cast<float>(i) * step);
        }
        p.delta = p.values[1] - p.values[0];
        p.initial = static_cast<float>(std::sqrt(static_cast<double>(maximum) * static_cast<double>(minimum)));
    }
}

std::vector<std::size_t> indices_of(const PlannerConfig &config, VariationType type) {
    std::vector<std::size_t> out;
    for (std::size_t i = 0; i < config.physical.size(); ++i) if (config.physical[i].type == type) out.push_back(i);
    return out;
}

std::size_t checked_job_count(const PlannerConfig &config) {
    const auto interp = indices_of(config, VariationType::interpolated);
    const auto additive = indices_of(config, VariationType::additive);
    if (interp.empty()) throw std::runtime_error("native xstinitable requires at least one interpolated parameter");
    std::size_t count = additive.size() + 1;
    for (const auto idx : interp) {
        const auto n = static_cast<std::size_t>(config.physical[idx].number_of_values);
        if (n == 0 || count > std::numeric_limits<std::size_t>::max() / n) throw std::runtime_error("xstinitable grid size overflow");
        count *= n;
    }
    if (count > 30000) throw std::runtime_error("xstinitable grid exceeds canonical loopcontrol maximum 30000");
    return count;
}

std::string generate_control(const PlannerConfig &c) {
    std::string out;
    out += "spectrum='" + c.spectrum_name + "' ";
    out += "spectrum_file='" + c.spectrum_file + "' ";
    out += "spectun=" + std::to_string(c.spectrum_units) + " ";
    out += "nsteps=" + std::to_string(c.nsteps) + " ";
    out += "niter=" + std::to_string(c.niter) + " ";
    out += "lwrite=" + std::to_string(c.lwrite) + " ";
    out += "lprint=" + std::to_string(c.lprint) + " ";
    out += "lstep=" + std::to_string(c.lstep) + " ";
    out += "npass=" + std::to_string(c.npass) + " ";
    out += "lcpres=" + std::to_string(c.lcpres) + " ";
    out += "emult=" + format_g(c.emult) + " ";
    out += "taumax=" + format_f(c.taumax) + " ";
    out += "xeemin=" + format_f(c.xeemin) + " ";
    out += "critf=" + format_g(c.critf) + " ";
    out += "radexp=" + format_f(c.radexp) + " ";
    out += "ncn2=" + std::to_string(c.ncn2) + " ";
    out += "modelname='" + c.model_name + "' ";
    out += "abundtbl='" + c.abundance_table + "' ";
    return out;
}

std::string generate_constants(const PlannerConfig &c) {
    std::string out;
    for (const auto &p : c.physical) {
        if (p.type == VariationType::constant) out += " " + p.name + "=" + format_g(p.initial);
    }
    return out;
}

std::string generate_interpolated(const PlannerConfig &c, const std::vector<std::size_t> &indices, const std::vector<int> &sample) {
    std::string out;
    for (std::size_t j = 0; j < indices.size(); ++j) {
        const auto &p = c.physical[indices[j]];
        out += " " + p.name + "=" + format_g(p.values.at(static_cast<std::size_t>(sample[j])));
    }
    return out;
}

std::string shell_quote(const std::string &text) {
    if (text.empty()) return "''";
    bool safe = true;
    for (const unsigned char c : text) {
        if (!(std::isalnum(c) || c == '_' || c == '-' || c == '.' || c == '/' || c == ':')) {
            safe = false;
            break;
        }
    }
    if (safe) return text;
    std::string out = "'";
    for (const char c : text) {
        if (c == '\'') out += "'\"'\"'";
        else out.push_back(c);
    }
    out += "'";
    return out;
}

std::string command_prefix(const PlannerConfig &c) {
    if (c.xstar_target == XStarCommandTarget::fortran) return "xstar ";
    std::string out = "xstar-cpp ";
    if (!c.data_dir.empty()) out += "--data-dir " + shell_quote(c.data_dir.string()) + " ";
    return out;
}

std::string generate_additive(const PlannerConfig &c, const std::vector<std::size_t> &indices, int current) {
    std::string out;
    for (std::size_t j = 0; j < indices.size(); ++j) {
        const auto &p = c.physical[indices[j]];
        out += " " + p.name + "=" + (current == static_cast<int>(j) ? format_g(p.initial) : std::string("0.0"));
    }
    return out;
}

bool advance_combination(std::vector<int> &current, const std::vector<int> &maximum) {
    int j = static_cast<int>(current.size()) - 1;
    while (j >= 0) {
        ++current[static_cast<std::size_t>(j)];
        if (current[static_cast<std::size_t>(j)] == maximum[static_cast<std::size_t>(j)]) {
            if (j == 0) return false;
            current[static_cast<std::size_t>(j)] = 0;
            --j;
        } else {
            return true;
        }
    }
    return false;
}

void write_lis(const PlannerConfig &c, const fs::path &path) {
    const auto interp = indices_of(c, VariationType::interpolated);
    const auto additive = indices_of(c, VariationType::additive);
    std::vector<int> maximum;
    maximum.reserve(interp.size());
    for (auto idx : interp) maximum.push_back(c.physical[idx].number_of_values);
    std::vector<int> current(interp.size(), 0);
    current.back() = -1;

    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create " + path.string());
    std::size_t loopcontrol = 0;
    while (advance_combination(current, maximum)) {
        const std::string base = command_prefix(c) + generate_control(c) + generate_constants(c) + generate_interpolated(c, interp, current);
        if (!additive.empty()) {
            for (int active = -1; active < static_cast<int>(additive.size()); ++active) {
                std::string line = base + generate_additive(c, additive, active) + " loopcontrol=" + std::to_string(++loopcontrol);
                if (line.size() >= kMaxParmLineLength) throw std::runtime_error("generated XSTAR parameter list exceeds canonical 2000-character buffer");
                out << line << '\n';
            }
        } else {
            std::string line = base + " loopcontrol=" + std::to_string(++loopcontrol);
            if (line.size() >= kMaxParmLineLength) throw std::runtime_error("generated XSTAR parameter list exceeds canonical 2000-character buffer");
            out << line << '\n';
        }
    }
}

void write_fits(const PlannerConfig &c, const fs::path &path) {
    const auto interp = indices_of(c, VariationType::interpolated);
    const auto additive = indices_of(c, VariationType::additive);
    int max_values = 0;
    for (const auto &p : c.physical) max_values = std::max(max_values, p.number_of_values);
    if (max_values <= 0) throw std::runtime_error("xstinitable FITS PARAMETERS requires at least one interpolation value axis");

    FitsHandle f;
    int status = 0;
    const std::string create_path = "!" + path.string();
    fits_create_file(&f.ptr, create_path.c_str(), &status);
    fits_check(status, "create xstinitable.fits");

    int simple = 1;
    int bitpix = 16;
    int naxis = 0;
    long naxes[2] = {0, 0};
    long pcount = 0;
    long gcount = 1;
    int extend = 1;
    fits_write_grphdr(f.ptr, simple, bitpix, naxis, naxes, pcount, gcount, extend, &status);
    fits_check(status, "write primary FITS header");
    fits_write_date(f.ptr, &status);
    fits_check(status, "write DATE");

    char modlname[13] = {0};
    std::strncpy(modlname, c.model_name.c_str(), 12);
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("MODLNAME"), modlname, const_cast<char *>("first 12 characters of model name"), &status);
    std::string modlunit = c.spectrum_units == 1 ? "photons/cm**2/s" : "ergs/cm**2/s";
    char *unit_ptr = const_cast<char *>(modlunit.c_str());
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("MODLUNIT"), unit_ptr, const_cast<char *>("model units"), &status);
    int redshift = c.redshift;
    fits_write_key(f.ptr, TLOGICAL, const_cast<char *>("REDSHIFT"), &redshift, const_cast<char *>("Is redshift a parameter?"), &status);
    const char *ogip = "OGIP";
    const char *doc = "OGIP/92-009";
    const char *klass = "XSPEC TABLE MODEL";
    const char *vers = "1.0.0";
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("HDUCLASS"), const_cast<char *>(ogip), const_cast<char *>("format conforms to OGIP standard"), &status);
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("HDUDOC"), const_cast<char *>(doc), const_cast<char *>("document defining format"), &status);
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("HDUCLAS1"), const_cast<char *>(klass), const_cast<char *>("model spectra for XSPEC"), &status);
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("HDUVERS1"), const_cast<char *>(vers), const_cast<char *>("version of format"), &status);
    fits_check(status, "write primary metadata");

    std::string value_form = std::to_string(max_values) + "E";
    char *ttype[] = {const_cast<char *>("NAME"), const_cast<char *>("METHOD"), const_cast<char *>("INITIAL"), const_cast<char *>("DELTA"),
                     const_cast<char *>("MINIMUM"), const_cast<char *>("BOTTOM"), const_cast<char *>("TOP"), const_cast<char *>("MAXIMUM"),
                     const_cast<char *>("NUMBVALS"), const_cast<char *>("VALUE")};
    char *tform[] = {const_cast<char *>("12A"), const_cast<char *>("J"), const_cast<char *>("E"), const_cast<char *>("E"),
                     const_cast<char *>("E"), const_cast<char *>("E"), const_cast<char *>("E"), const_cast<char *>("E"),
                     const_cast<char *>("J"), const_cast<char *>(value_form.c_str())};
    char *tunit[] = {const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>(""),
                     const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>(""), const_cast<char *>("")};
    const long rows = static_cast<long>(interp.size() + additive.size());
    fits_create_tbl(f.ptr, BINARY_TBL, rows, 10, ttype, tform, tunit, const_cast<char *>("PARAMETERS"), &status);
    fits_check(status, "create PARAMETERS extension");

    std::vector<const PhysicalParameter *> ordered;
    for (auto idx : interp) ordered.push_back(&c.physical[idx]);
    for (auto idx : additive) ordered.push_back(&c.physical[idx]);
    for (long r = 1; r <= rows; ++r) {
        const auto &p = *ordered[static_cast<std::size_t>(r - 1)];
        char name_buffer[13] = {0};
        std::snprintf(name_buffer, sizeof(name_buffer), "%s", p.name.c_str());
        char *name_ptr = name_buffer;
        long method = static_cast<long>(p.method);
        long numbvals = p.number_of_values;
        float initial = p.initial, delta = p.delta, minimum = p.hard_minimum, bottom = p.soft_minimum;
        float top = p.soft_maximum, maximum = p.hard_maximum;
        fits_write_col(f.ptr, TSTRING, 1, r, 1, 1, &name_ptr, &status);
        fits_write_col(f.ptr, TLONG, 2, r, 1, 1, &method, &status);
        fits_write_col(f.ptr, TFLOAT, 3, r, 1, 1, &initial, &status);
        fits_write_col(f.ptr, TFLOAT, 4, r, 1, 1, &delta, &status);
        fits_write_col(f.ptr, TFLOAT, 5, r, 1, 1, &minimum, &status);
        fits_write_col(f.ptr, TFLOAT, 6, r, 1, 1, &bottom, &status);
        fits_write_col(f.ptr, TFLOAT, 7, r, 1, 1, &top, &status);
        fits_write_col(f.ptr, TFLOAT, 8, r, 1, 1, &maximum, &status);
        fits_write_col(f.ptr, TLONG, 9, r, 1, 1, &numbvals, &status);
        std::vector<float> values(static_cast<std::size_t>(max_values), 0.0f);
        for (std::size_t i = 0; i < p.values.size() && i < values.size(); ++i) values[i] = p.values[i];
        fits_write_col(f.ptr, TFLOAT, 10, r, 1, max_values, values.data(), &status);
        fits_check(status, "write PARAMETERS row");
    }

    for (const auto &p : c.physical) {
        if (p.type != VariationType::constant) continue;
        char key[9] = {0};
        std::strncpy(key, p.name.c_str(), 8);
        float value = p.initial;
        fits_write_key(f.ptr, TFLOAT, key, &value, const_cast<char *>("physical parameter held constant"), &status);
        fits_check(status, "write constant physical keyword");
    }

    fits_write_comment(f.ptr, const_cast<char *>("Required by XSPEC"), &status);
    int nint = static_cast<int>(interp.size());
    int nadd = static_cast<int>(additive.size());
    fits_write_key(f.ptr, TINT, const_cast<char *>("NINTPARM"), &nint, const_cast<char *>("number of interpolated parameters"), &status);
    fits_write_key(f.ptr, TINT, const_cast<char *>("NADDPARM"), &nadd, const_cast<char *>("number of additional parameters"), &status);
    float elow = c.energy_low, ehigh = c.energy_high;
    fits_write_key(f.ptr, TFLOAT, const_cast<char *>("ELOW"), &elow, const_cast<char *>("energy band low end (eV)"), &status);
    fits_write_key(f.ptr, TFLOAT, const_cast<char *>("EHIGH"), &ehigh, const_cast<char *>("energy band high end (eV)"), &status);
    fits_write_comment(f.ptr, const_cast<char *>("Non-Physical Control Parameters"), &status);
    char *spectrum = const_cast<char *>(c.spectrum_name.c_str());
    char *specfile = const_cast<char *>(c.spectrum_file.c_str());
    char *abundtbl = const_cast<char *>(c.abundance_table.c_str());
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("SPECTRUM"), spectrum, const_cast<char *>("spectrum name"), &status);
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("SPECFILE"), specfile, const_cast<char *>("spectrum file"), &status);
    int specunit = c.spectrum_units;
    fits_write_key(f.ptr, TINT, const_cast<char *>("SPECUNIT"), &specunit, const_cast<char *>("spectral units (0=energy, 1=photons)"), &status);
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("ABUNDTBL"), abundtbl, const_cast<char *>("abundance table"), &status);
    int nsteps = c.nsteps, niter = c.niter, lwrite = c.lwrite, lprint = c.lprint, lstep = c.lstep, npass = c.npass, lcpres = c.lcpres;
    fits_write_key(f.ptr, TINT, const_cast<char *>("NSTEPS"), &nsteps, const_cast<char *>("Number of steps"), &status);
    fits_write_key(f.ptr, TINT, const_cast<char *>("NITER"), &niter, const_cast<char *>("Number of iterations"), &status);
    fits_write_key(f.ptr, TINT, const_cast<char *>("WRITESW"), &lwrite, const_cast<char *>("write switch"), &status);
    fits_write_key(f.ptr, TINT, const_cast<char *>("PRINTSW"), &lprint, const_cast<char *>("print switch"), &status);
    fits_write_key(f.ptr, TINT, const_cast<char *>("STEPSIZE"), &lstep, const_cast<char *>("step size choice switch"), &status);
    fits_write_key(f.ptr, TINT, const_cast<char *>("NPASS"), &npass, const_cast<char *>("number of passes"), &status);
    fits_write_key(f.ptr, TINT, const_cast<char *>("PRESSSW"), &lcpres, const_cast<char *>("constant pressure switch"), &status);
    float emult = c.emult, taumax = c.taumax, xeemin = c.xeemin, critf = c.critf, radexp = c.radexp;
    fits_write_key(f.ptr, TFLOAT, const_cast<char *>("EMULT"), &emult, const_cast<char *>("courant multiplier"), &status);
    fits_write_key(f.ptr, TFLOAT, const_cast<char *>("TAUMAX"), &taumax, const_cast<char *>("tau max for courant step"), &status);
    fits_write_key(f.ptr, TFLOAT, const_cast<char *>("XEEMIN"), &xeemin, const_cast<char *>("minimum elctron fraction"), &status);
    fits_write_key(f.ptr, TFLOAT, const_cast<char *>("CRITF"), &critf, const_cast<char *>("critical ion abundance"), &status);
    fits_write_key(f.ptr, TFLOAT, const_cast<char *>("RADEXP"), &radexp, const_cast<char *>("radius exponent"), &status);
    int ncn2 = c.ncn2;
    fits_write_key(f.ptr, TINT, const_cast<char *>("NCN2"), &ncn2, const_cast<char *>("number of energy bins"), &status);
    char *modelnam = const_cast<char *>(c.model_name.c_str());
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("MODELNAM"), modelnam, const_cast<char *>("model name"), &status);
    fits_write_comment(f.ptr, const_cast<char *>("OGIP Required Keywords"), &status);
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("HDUCLASS"), const_cast<char *>(ogip), const_cast<char *>("format conforms to OGIP standard"), &status);
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("HDUDOC"), const_cast<char *>(doc), const_cast<char *>("document defining format"), &status);
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("HDUCLAS1"), const_cast<char *>(klass), const_cast<char *>("model spectra for XSPEC"), &status);
    fits_write_key(f.ptr, TSTRING, const_cast<char *>("HDUVERS1"), const_cast<char *>(vers), const_cast<char *>("version of format"), &status);
    fits_check(status, "write xstinitable metadata");

    fits_close_file(f.ptr, &status);
    f.ptr = nullptr;
    fits_check(status, "close xstinitable.fits");
}

}  // namespace

PlannerConfig parse_key_value_arguments(const std::vector<std::string> &arguments) {
    const auto args = parse_arguments(arguments);
    PlannerConfig c;
    c.spectrum_name = get_string(args, "spectrum", "pow");
    if (c.spectrum_name == "file") {
        c.spectrum_file = get_string(args, "spectrum_file", "bknpw5");
        c.spectrum_units = get_int(args, "spectun", 0);
    } else {
        // Exact Get_Parms behavior: non-file spectra never query these XPI
        // values and retain the local defaults below.
        c.spectrum_file = "spect.dat";
        c.spectrum_units = 0;
    }
    c.redshift = get_int(args, "redshift", 1);
    c.nsteps = get_int(args, "nsteps", 3);
    c.niter = get_int(args, "niter", 99);
    c.lwrite = get_int(args, "lwrite", 0);
    c.lprint = get_int(args, "lprint", 0);
    c.lstep = get_int(args, "lstep", 0);
    c.npass = get_int(args, "npass", 1);
    c.lcpres = get_int(args, "lcpres", 0);
    c.model_name = get_string(args, "modelname", "template");
    c.abundance_table = get_string(args, "abundtbl", "xdef");
    c.emult = get_float(args, "emult", 0.5f);
    c.taumax = get_float(args, "taumax", 5.0f);
    c.xeemin = get_float(args, "xeemin", 0.1f);
    c.critf = get_float(args, "critf", 1.0e-4f);
    c.radexp = get_float(args, "radexp", 0.0f);
    c.ncn2 = get_int(args, "ncn2", 9999);
    c.energy_low = get_float(args, "elow", 100.0f);
    c.energy_high = get_float(args, "ehigh", 20000.0f);
    if (c.energy_high < c.energy_low) throw std::runtime_error("EHIGH must be >= ELOW");

    c.physical.reserve(kPhysicalDefaults.size());
    for (std::size_t i = 0; i < kPhysicalDefaults.size(); ++i) {
        const auto &d = kPhysicalDefaults[i];
        PhysicalParameter p;
        p.name = d.name;
        p.xstar_sequence_number = static_cast<int>(i + 1);
        if (p.name == "trad" && c.spectrum_name == "file") {
            p.initial = 0.0f;
            p.type = VariationType::constant;
            p.method = InterpolationMethod::linear;
            build_sampling(p);
            c.physical.push_back(std::move(p));
            continue;
        }
        p.initial = get_float(args, p.name, d.initial);
        const int type = get_int(args, p.name + "typ", d.type);
        if (type < 0 || type > 2) throw std::runtime_error("invalid variation type for " + p.name);
        p.type = static_cast<VariationType>(type);
        if (p.type == VariationType::interpolated) {
            const int method = get_int(args, p.name + "int", d.method);
            if (method < 0 || method > 1) throw std::runtime_error("invalid interpolation method for " + p.name);
            p.method = static_cast<InterpolationMethod>(method);
            p.soft_maximum = p.initial;
            p.soft_minimum = get_float(args, p.name + "sof", d.soft_minimum);
            p.number_of_values = get_int(args, p.name + "nst", d.nst);
        }
        build_sampling(p);
        c.physical.push_back(std::move(p));
    }

    checked_job_count(c);
    return c;
}

PlannerResult write_native_xstinitable(const PlannerConfig &config, const fs::path &output_dir) {
    const std::size_t jobs = checked_job_count(config);
    fs::create_directories(output_dir);
    PlannerResult result;
    result.lis_path = output_dir / "xstinitable.lis";
    result.fits_path = output_dir / "xstinitable.fits";
    result.n_interpolated = static_cast<int>(indices_of(config, VariationType::interpolated).size());
    result.n_additive = static_cast<int>(indices_of(config, VariationType::additive).size());
    result.job_count = jobs;
    write_fits(config, result.fits_path);
    write_lis(config, result.lis_path);
    return result;
}

}  // namespace xstar_xspec_initable
