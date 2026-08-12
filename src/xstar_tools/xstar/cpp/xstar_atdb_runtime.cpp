// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: xstarsetup.f90; readtbl.f90; setptrs.f90; rread1.f90
// Role: Resolve/read production atomic data and parameters, construct source-equivalent
//   record/level/line/RRC pointer topology, and retain source reader semantics.
// Relation: Source-exact identities/pointers with C++ storage; parameter/default-REAL details are preserved
//   where qualified.
// Concordance: DB-001; INPUT-001
// Qualification: all-element pointer qualification; radius/default-REAL 12.3.36; C++ 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#include "xstar_atdb_runtime.hpp"

#include <fitsio.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>

namespace xstar_atdb_runtime {
namespace {

constexpr int kProgramAbi = 60486;
constexpr int kType49PhextrapMaxPoints = 999;
constexpr int kType53LayoutMagic = 221; // legacy Mg-only 12-stage payload
constexpr int kType49LayoutMagic = 222; // legacy Mg-only 12-stage payload
constexpr int kType99LayoutMagic = 223; // legacy 12-stage payload
constexpr int kType99LayoutMagicZ1Z30V068213 = 226;
constexpr int kType53LayoutMagicZ1Z30V06481231 = 224;
constexpr int kType49LayoutMagicZ1Z30V06481231 = 225;
constexpr int kType70SourceIonIdentityMagicV068213 = 227;
constexpr double kEvAngstrom = 12398.419843320026;

// Atomic-database record semantics (XSTAR Manual, Chapter 12; Mendoza et al.
// 2021, Appendix A): a record's data type selects the formula/layout used to
// interpret its constants, while its rate type tells XSTAR how the resulting
// rate participates in the physics.  The source ASCII record header carries
// six integers: data type, rate type, continuation flag, number of reals,
// number of integers, and number of characters.  ucalc.f90 is the canonical
// dispatcher that converts those heterogeneous payloads to the standard XSTAR
// rate outputs.  Keep data-type parsing separate from rate-type ownership.

const std::set<int> kLegacyActiveTypes = {
    1,2,7,9,10,30,38,39,49,50,51,53,54,56,57,59,60,62,63,66,68,69,71,72,73,74,76,77,86,88,95,99
};

/* All physical labels executed by SourceFaithfulUCalc.  The 24 omitted labels
 * are literal source metadata/no-op branches and must not become native rate
 * records.  This set is intentionally element-independent. */
const std::set<int> kActiveTypes = {
    1,2,3,4,5,6,7,8,9,10,11,12,15,16,17,18,19,20,21,22,23,25,26,27,28,30,31,32,33,34,35,36,37,38,39,
    49,50,51,52,53,54,55,56,57,59,60,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,79,81,82,85,86,
    88,89,91,92,95,96,97,98,99,101,102
};

const std::array<double,31> kAtomicMass = {{
    0.0, 1.00794, 4.002602, 6.941, 9.012182, 10.811, 12.0107, 14.0067,
    15.9994, 18.9984032, 20.1797, 22.98976928, 24.3050, 26.9815386,
    28.0855, 30.973762, 32.065, 35.453, 39.948, 39.0983, 40.078,
    44.955912, 47.867, 50.9415, 51.9961, 54.938045, 55.845, 58.933195,
    58.6934, 63.546, 65.38
}};


// XSTAR 2.59g xstarsetup.f90 abundance bases.  These are not new atomic
// physics: xstarsetup selects one 30-element cosmic table and multiplies it by
// the public habund..znabund factors before any rate calculation is entered.
// The manual spells the Lodders et al. (2009) tables lpgp/lpgs, while the
// supplied source uses lgpp/lgps.  Accept both spellings as compatibility
// aliases for the same two source arrays.
using AbundanceBase = std::array<double,30>;
const AbundanceBase kAbundXdef = {{
    1.00e0,1.00e-1,1.00e-10,1.00e-10,1.00e-10,3.70e-4,1.10e-4,6.80e-4,3.98e-8,2.80e-5,
    1.78e-6,3.50e-5,2.45e-6,3.50e-5,3.31e-7,1.60e-5,3.98e-7,4.50e-6,8.91e-8,2.10e-6,
    1.66e-9,1.35e-7,2.51e-8,7.08e-7,2.51e-7,2.50e-5,1.26e-7,2.00e-6,3.16e-8,1.58e-8}};
const AbundanceBase kAbundAngr = {{
    1.00e0,9.77e-2,1.45e-11,1.41e-11,3.98e-10,3.63e-4,1.12e-4,8.51e-4,3.63e-8,1.23e-4,
    2.14e-6,3.80e-5,2.95e-6,3.55e-5,2.82e-7,1.62e-5,3.16e-7,3.63e-6,1.32e-7,2.29e-6,
    1.26e-9,9.77e-8,1.00e-8,4.68e-7,2.45e-7,4.68e-5,8.32e-8,1.78e-6,1.62e-8,3.98e-8}};
const AbundanceBase kAbundAspl = {{
    1.00e0,8.51e-2,1.12e-11,2.40e-11,5.01e-10,2.69e-4,6.76e-5,4.90e-4,3.63e-8,8.51e-5,
    1.74e-6,3.98e-5,2.82e-6,3.24e-5,2.57e-7,1.32e-5,3.16e-7,2.51e-6,1.07e-7,2.19e-6,
    1.41e-9,8.91e-8,8.51e-9,4.37e-7,2.69e-7,3.16e-5,9.77e-8,1.66e-6,1.55e-8,3.63e-8}};
const AbundanceBase kAbundFeld = {{
    1.00e0,9.77e-2,1.26e-11,2.51e-11,3.55e-10,3.98e-4,1.00e-4,8.51e-4,3.63e-8,1.29e-4,
    2.14e-6,3.80e-5,2.95e-6,3.55e-5,2.82e-7,1.62e-5,3.16e-7,4.47e-6,1.32e-7,2.29e-6,
    1.48e-9,1.05e-7,1.00e-8,4.68e-7,2.45e-7,3.24e-5,8.32e-8,1.78e-6,1.62e-8,3.98e-8}};
const AbundanceBase kAbundAneb = {{
    1.00e0,8.01e-2,2.19e-9,2.87e-11,8.82e-10,4.45e-4,9.12e-5,7.39e-4,3.10e-8,1.38e-4,
    2.10e-6,3.95e-5,3.12e-6,3.68e-5,3.82e-7,1.89e-5,1.93e-7,3.82e-6,1.39e-7,2.25e-6,
    1.24e-9,8.82e-8,1.08e-8,4.93e-7,3.50e-7,3.31e-5,8.27e-8,1.81e-6,1.89e-8,4.63e-8}};
const AbundanceBase kAbundGrsa = {{
    1.00e0,8.51e-2,1.26e-11,2.51e-11,3.55e-10,3.31e-4,8.32e-5,6.76e-4,3.63e-8,1.20e-4,
    2.14e-6,3.80e-5,2.95e-6,3.55e-5,2.82e-7,2.14e-5,3.16e-7,2.51e-6,1.32e-7,2.29e-6,
    1.48e-9,1.05e-7,1.00e-8,4.68e-7,2.45e-7,3.16e-5,8.32e-8,1.78e-6,1.62e-8,3.98e-8}};
const AbundanceBase kAbundWilm = {{
    1.00e0,9.77e-2,0.0,0.0,0.0,2.40e-4,7.59e-5,4.90e-4,0.0,8.71e-5,
    1.45e-6,2.51e-5,2.14e-6,1.86e-5,2.63e-7,1.23e-5,1.32e-7,2.57e-6,0.0,1.58e-6,
    0.0,6.46e-8,0.0,3.24e-7,2.19e-7,2.69e-5,8.32e-8,1.12e-6,0.0,0.0}};
const AbundanceBase kAbundLodd = {{
    1.00e0,7.92e-2,1.90e-9,2.57e-11,6.03e-10,2.45e-4,6.76e-5,4.90e-4,2.88e-8,7.41e-5,
    1.99e-6,3.55e-5,2.88e-6,3.47e-5,2.88e-7,1.55e-5,1.82e-7,3.55e-6,1.29e-7,2.19e-6,
    1.17e-9,8.32e-8,1.00e-8,4.47e-7,3.16e-7,2.95e-5,8.13e-8,1.66e-6,1.82e-8,4.27e-8}};
const AbundanceBase kAbundLpgp = {{
    1.00e0,8.41e-2,1.26e-11,2.40e-11,5.01e-10,2.45e-4,7.24e-5,5.37e-4,3.63e-8,1.12e-4,
    2.00e-6,3.47e-5,2.95e-6,3.31e-5,2.88e-7,1.38e-5,3.16e-7,3.16e-6,1.32e-7,2.14e-6,
    1.26e-9,7.94e-8,1.00e-8,4.37e-7,2.34e-7,2.82e-5,8.32e-8,1.70e-6,1.62e-8,4.17e-8}};
const AbundanceBase kAbundLpgs = {{
    1.00e0,9.69e-2,2.15e-9,2.36e-11,7.26e-10,2.78e-4,8.19e-5,6.06e-4,3.10e-8,1.27e-4,
    2.23e-6,3.98e-5,3.27e-6,3.86e-5,3.20e-7,1.63e-5,2.00e-7,3.58e-6,1.45e-7,2.33e-6,
    1.33e-9,9.54e-8,1.11e-8,5.06e-7,3.56e-7,3.27e-5,9.07e-8,1.89e-6,2.09e-8,5.02e-8}};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Resolve the public abundtbl selector to the xstarsetup.f90 cosmic abundance base used before applying element multipliers.
// Reference context: XSTAR Manual Ch. 4 abundance-table input; xstarsetup.f90 select case(abndtbl).
// XSTAR-FUNCTION-COMMENT-END
const AbundanceBase& source_abundance_base(std::string name) {
    std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c){ return static_cast<char>(std::tolower(c)); });
    if (name.size() > 4u) name.resize(4u);
    if (name == "angr") return kAbundAngr;
    if (name == "aspl") return kAbundAspl;
    if (name == "feld") return kAbundFeld;
    if (name == "aneb") return kAbundAneb;
    if (name == "grsa") return kAbundGrsa;
    if (name == "wilm") return kAbundWilm;
    if (name == "lodd") return kAbundLodd;
    if (name == "lpgp" || name == "lgpp") return kAbundLpgp;
    if (name == "lpgs" || name == "lgps") return kAbundLpgs;
    if (!name.empty() && name != "xdef") {
        std::cerr << "Invalid abundance table - using default (xdef): " << name << "\n";
    }
    return kAbundXdef;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load file into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::string read_file(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open parameters file: " + path.string());
    return std::string(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide json string as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::string json_string(const std::string& text, const std::string& key, const std::string& fallback = {}) {
    const std::regex pattern("\\\"" + key + "\\\"\\s*:\\s*\\\"([^\\\"]*)\\\"");
    std::smatch match;
    return std::regex_search(text, match, pattern) ? match[1].str() : fallback;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide json number as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
double json_number(const std::string& text, const std::string& key, double fallback) {
    const std::regex pattern("\\\"" + key + "\\\"\\s*:\\s*(?:\\\")?([-+0-9.eE]+)(?:\\\")?");
    std::smatch match;
    if (!std::regex_search(text, match, pattern)) return fallback;
    try { return std::stod(match[1].str()); } catch (...) { return fallback; }
}

// XSTAR uclgsr8.f90 reads a user-facing REAL parameter through a REAL(4)
// temporary (uclgsr) and only then promotes it to REAL(8).  Keep this helper
// distinct from true DOUBLE PRECISION source constants.
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide source uclgsr8 as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
double source_uclgsr8(const std::string& text, const std::string& key, double fallback) {
    return static_cast<double>(static_cast<float>(json_number(text, key, fallback)));
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide source default real literal as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
double source_default_real_literal(double value) {
    return static_cast<double>(static_cast<float>(value));
}

// Literal rread1.f90 initial-radius construction, independent of the Python
// normalized initial_radius_cm payload.  This prevents a Python/C++ agreement
// from masking a shared departure from the canonical FORTRAN source.
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide source rread1 initial radius cm as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
double source_rread1_initial_radius_cm(const std::string& text) {
    const int lcpres = static_cast<int>(json_number(text, "lcpres", 0.0));
    const int lcdd = lcpres <= 1 ? 1 - lcpres : lcpres;
    const double t4 = source_uclgsr8(text, "temperature", 400.0);
    const double pressure = source_uclgsr8(text, "pressure", 0.03);
    double density = source_uclgsr8(text, "density", 1.0e4);
    const double xlum = source_uclgsr8(text, "rlrad38", 1.0e-6);
    const double zeta = source_uclgsr8(text, "rlogxi", 5.0);
    const double xi = std::pow(source_default_real_literal(10.0), zeta);
    double r19 = 0.0;
    if (lcdd == 0) {
        density = pressure / 1.38e-12 / std::max(t4, 1.0e-49);
        const double four_pi = source_default_real_literal(12.56);
        const double ccc = 2.99792458e10; // constants.f90 REAL(8) parameter
        r19 = std::sqrt(xlum / four_pi / ccc / std::max(1.0e-49, pressure * xi));
    } else if (lcdd == 2) {
        const double xee = source_default_real_literal(1.2);
        density = pressure / (xee + source_default_real_literal(1.0e-34));
        r19 = std::sqrt(xlum / std::max(1.0e-49, pressure * xi));
    } else if (lcdd == 1) {
        r19 = std::sqrt(xlum / std::max(1.0e-49, density * xi));
    } else {
        throw std::runtime_error("unsupported rread1 lcdd branch");
    }
    const double radius_scale = source_default_real_literal(1.0e19);
    return r19 * radius_scale;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide json number array as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::vector<double> json_number_array(const std::string& text, const std::string& key) {
    const std::regex pattern("\\\"" + key + "\\\"\\s*:\\s*\\[([^\\]]*)\\]");
    std::smatch match;
    if (!std::regex_search(text, match, pattern)) return {};
    std::vector<double> out;
    std::istringstream in(match[1].str());
    std::string token;
    while (std::getline(in, token, ',')) {
        try { out.push_back(std::stod(token)); } catch (...) { out.push_back(0.0); }
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide trim as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::string trim(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n\0", 0);
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n\0");
    return value.substr(first, last - first + 1);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Append candidate from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
void append_candidate(std::vector<std::filesystem::path>& out, std::filesystem::path candidate) {
    if (candidate.empty()) return;
    std::error_code ec;
    if (candidate.is_relative()) candidate = std::filesystem::absolute(candidate, ec);
    if (!ec) candidate = candidate.lexically_normal();
    if (std::find(out.begin(), out.end(), candidate) == out.end()) out.push_back(std::move(candidate));
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide first file as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::filesystem::path first_file(const std::vector<std::filesystem::path>& candidates) {
    for (const auto& p : candidates) {
        std::error_code ec;
        if (std::filesystem::is_regular_file(p, ec) && !ec) {
            auto q = std::filesystem::weakly_canonical(p, ec);
            return ec ? p : q;
        }
    }
    return {};
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide fits error as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::string fits_error(int status) {
    char text[FLEN_STATUS]{};
    fits_get_errstatus(status, text);
    return text;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide fits check as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
void fits_check(int status, const std::string& context) {
    if (status) throw std::runtime_error(context + ": " + fits_error(status));
}

struct Header {
    std::int64_t raw_pointer = 0;
    int data_type = 0;
    int rate_type = 0;
    int continuation = 0;
    int nreal = 0;
    int nint = 0;
    int nchar = 0;
    std::int64_t real_ptr = 0;
    std::int64_t int_ptr = 0;
    std::int64_t char_ptr = 0;
};

class AtdbReader {
public:
    explicit AtdbReader(const std::filesystem::path& path) : path_(path) {
        int status = 0;
        fits_open_file(&file_, path.string().c_str(), READONLY, &status);
        fits_check(status, "open atdb.fits");
        try {
            pointers_hdu_ = find_hdu("POINTERS", 2);
            reals_hdu_ = find_hdu("REALS", 3);
            integers_hdu_ = find_hdu("INTEGERS", 4);
            chars_hdu_ = find_hdu("CHARS", 5);
            read_headers();
            load_payload_columns();
        } catch (...) {
            close();
            throw;
        }
    }
    ~AtdbReader() { close(); }
    AtdbReader(const AtdbReader&) = delete;
    AtdbReader& operator=(const AtdbReader&) = delete;

    std::size_t record_count() const { return headers_.size() - 1; }
    const Header& header(int rec) const {
        if (rec <= 0 || static_cast<std::size_t>(rec) >= headers_.size()) throw std::runtime_error("ATDB record outside range");
        return headers_[static_cast<std::size_t>(rec)];
    }
    std::vector<double> reals(int rec) const {
        const auto& h = header(rec);
        return cached_span(reals_cache_, h.real_ptr, h.nreal,
            "read ATDB REALS record " + std::to_string(rec));
    }
    std::vector<std::int64_t> ints(int rec) const {
        const auto& h = header(rec);
        return cached_span(ints_cache_, h.int_ptr, h.nint,
            "read ATDB INTEGERS record " + std::to_string(rec));
    }
    std::string chars(int rec) const {
        const auto& h = header(rec);
        const auto bytes = cached_span(chars_cache_, h.char_ptr, h.nchar,
            "read ATDB CHARS record " + std::to_string(rec));
        return trim(std::string(bytes.begin(), bytes.end()));
    }
    int first_int(int rec, int fallback = 0) const {
        auto v = ints(rec); return v.empty() ? fallback : static_cast<int>(v.front());
    }
    int local_level(int rec) const {
        auto v = ints(rec);
        if (v.size() < 2) throw std::runtime_error("ATDB level record lacks local level");
        return static_cast<int>(v[v.size()-2]);
    }
private:
    int find_hdu(const char* name, int fallback) {
        int status = 0;
        fits_movnam_hdu(file_, BINARY_TBL, const_cast<char*>(name), 0, &status);
        if (status) {
            status = 0;
            int type = 0;
            fits_movabs_hdu(file_, fallback, &type, &status);
            fits_check(status, std::string("locate ATDB ") + name + " HDU");
        }
        int number = 0;
        fits_get_hdu_num(file_, &number);
        return number;
    }
    void move(int hdu) {
        int status = 0, type = 0;
        fits_movabs_hdu(file_, hdu, &type, &status);
        fits_check(status, "move ATDB HDU");
    }
    long long length_keyword(int hdu) {
        move(hdu);
        int status = 0;
        long long value = 0;
        fits_read_key(file_, TLONGLONG, const_cast<char*>("LENGTH"), &value, nullptr, &status);
        if (status == KEY_NO_EXIST) { status = 0; return 0; }
        fits_check(status, "read ATDB LENGTH");
        return value;
    }
    struct ColumnLayout {
        int typecode = 0;
        long long repeat = 0;
        long long width = 0;
        long long rows = 0;
        bool variable = false;
    };
    ColumnLayout column_layout(int hdu) {
        move(hdu);
        ColumnLayout out;
        int status = 0;
        fits_get_coltypell(file_, 1, &out.typecode, &out.repeat, &out.width, &status);
        fits_check(status, "read ATDB column type");
        fits_get_num_rowsll(file_, &out.rows, &status);
        fits_check(status, "read ATDB row count");
        out.variable = out.typecode < 0;
        if (out.rows <= 0) throw std::runtime_error("ATDB packed column has no rows");
        if (!out.variable && out.repeat <= 0) throw std::runtime_error("ATDB packed column repeat is not positive");
        return out;
    }
    long long row_element_count(int hdu, const ColumnLayout& layout, long long row) {
        if (!layout.variable) return layout.repeat;
        move(hdu);
        int status = 0;
        long long length = 0, heapaddr = 0;
        fits_read_descriptll(file_, 1, row, &length, &heapaddr, &status);
        fits_check(status, "read ATDB variable-length descriptor");
        if (length < 0) throw std::runtime_error("ATDB variable-length descriptor is negative");
        return length;
    }
    long long column_element_count(int hdu, const ColumnLayout& layout) {
        long long total = 0;
        for (long long row = 1; row <= layout.rows; ++row) {
            const long long count = row_element_count(hdu, layout, row);
            if (count > std::numeric_limits<long long>::max() - total)
                throw std::runtime_error("ATDB packed column length overflow");
            total += count;
        }
        return total;
    }
    template <typename T>
    void read_column_slice(
        int hdu,
        int datatype,
        long long first_element,
        long long count,
        T* destination,
        const std::string& context
    ) {
        if (count < 0 || first_element <= 0) throw std::runtime_error(context + ": invalid packed-vector span");
        if (count == 0) return;
        const ColumnLayout layout = column_layout(hdu);
        const long long available = column_element_count(hdu, layout);
        if (first_element - 1 > available || count > available - (first_element - 1)) {
            throw std::runtime_error(
                context + ": packed-vector span " + std::to_string(first_element) + "+" +
                std::to_string(count) + " exceeds available length " + std::to_string(available)
            );
        }
        long long logical_start = 1;
        long long remaining = count;
        long long written = 0;
        for (long long row = 1; row <= layout.rows && remaining > 0; ++row) {
            const long long row_count = row_element_count(hdu, layout, row);
            const long long logical_stop = logical_start + row_count;
            if (first_element >= logical_stop) {
                logical_start = logical_stop;
                continue;
            }
            const long long offset = std::max<long long>(0, first_element - logical_start);
            const long long take = std::min(remaining, row_count - offset);
            move(hdu);
            int status = 0, anynul = 0;
            fits_read_col(
                file_, datatype, 1, row, offset + 1, take, nullptr,
                destination + written, &anynul, &status
            );
            fits_check(status, context);
            written += take;
            remaining -= take;
            first_element += take;
            logical_start = logical_stop;
        }
        if (remaining != 0) throw std::runtime_error(context + ": short packed-vector read");
    }

    template <typename T>
    std::vector<T> cached_span(
        const std::vector<T>& cache,
        long long first_element,
        long long count,
        const std::string& context) const {
        if (count <= 0) return {};
        if (first_element <= 0) throw std::runtime_error(context + ": invalid packed-vector pointer");
        const auto start = static_cast<unsigned long long>(first_element - 1);
        const auto width = static_cast<unsigned long long>(count);
        if (start > cache.size() || width > cache.size() - start) {
            throw std::runtime_error(context + ": cached packed-vector span exceeds payload");
        }
        return std::vector<T>(cache.begin() + static_cast<std::ptrdiff_t>(start),
                              cache.begin() + static_cast<std::ptrdiff_t>(start + width));
    }

    template <typename T>
    std::vector<T> read_full_column(int hdu, int datatype, const std::string& context) {
        const ColumnLayout layout = column_layout(hdu);
        const long long total = column_element_count(hdu, layout);
        if (total < 0 || static_cast<unsigned long long>(total) >
                static_cast<unsigned long long>(std::numeric_limits<std::size_t>::max())) {
            throw std::runtime_error(context + ": packed column is too large");
        }
        std::vector<T> values(static_cast<std::size_t>(total));
        long long written = 0;
        for (long long row = 1; row <= layout.rows; ++row) {
            const long long count = row_element_count(hdu, layout, row);
            if (count == 0) continue;
            move(hdu);
            int status = 0, anynul = 0;
            fits_read_col(file_, datatype, 1, row, 1, count, nullptr,
                          values.data() + written, &anynul, &status);
            fits_check(status, context);
            written += count;
        }
        if (written != total) throw std::runtime_error(context + ": short full-column read");
        return values;
    }

    void load_payload_columns() {
        reals_cache_ = read_full_column<double>(reals_hdu_, TDOUBLE, "cache ATDB REALS");
        const auto ints = read_full_column<long long>(integers_hdu_, TLONGLONG, "cache ATDB INTEGERS");
        ints_cache_.assign(ints.begin(), ints.end());
        chars_cache_ = read_full_column<unsigned char>(chars_hdu_, TBYTE, "cache ATDB CHARS");
    }

    void read_headers() {
        long long nrecords = length_keyword(pointers_hdu_);
        const ColumnLayout layout = column_layout(pointers_hdu_);
        const long long available = column_element_count(pointers_hdu_, layout);
        if (nrecords <= 0) {
            if (available <= 0 || available % 10 != 0)
                throw std::runtime_error("ATDB POINTERS length is not divisible by 10");
            nrecords = available / 10;
        }
        const long long required = 10 * nrecords;
        if (required <= 0 || available < required) {
            throw std::runtime_error(
                "ATDB POINTERS payload shorter than 10*LENGTH: available=" +
                std::to_string(available) + " required=" + std::to_string(required)
            );
        }
        std::vector<long long> packed(static_cast<std::size_t>(required));
        read_column_slice(
            pointers_hdu_, TLONGLONG, 1, required, packed.data(), "read ATDB POINTERS"
        );
        headers_.resize(static_cast<std::size_t>(nrecords)+1);
        for (long long r=1; r<=nrecords; ++r) {
            const auto i = static_cast<std::size_t>(10*(r-1));
            Header h;
            h.raw_pointer=packed[i+0]; h.data_type=static_cast<int>(packed[i+1]);
            h.rate_type=static_cast<int>(packed[i+2]); h.continuation=static_cast<int>(packed[i+3]);
            h.nreal=static_cast<int>(packed[i+4]); h.nint=static_cast<int>(packed[i+5]);
            h.nchar=static_cast<int>(packed[i+6]); h.real_ptr=packed[i+7];
            h.int_ptr=packed[i+8]; h.char_ptr=packed[i+9];
            if (h.nreal < 0 || h.nint < 0 || h.nchar < 0) throw std::runtime_error("ATDB negative record span");
            if ((h.nreal > 0 && h.real_ptr <= 0) || (h.nint > 0 && h.int_ptr <= 0) ||
                (h.nchar > 0 && h.char_ptr <= 0))
                throw std::runtime_error("ATDB positive record span has non-positive packed pointer");
            headers_[static_cast<std::size_t>(r)] = h;
        }
    }
    void close() {
        if (file_) { int status=0; fits_close_file(file_, &status); file_=nullptr; }
    }
    std::filesystem::path path_;
    fitsfile* file_ = nullptr;
    int pointers_hdu_=0, reals_hdu_=0, integers_hdu_=0, chars_hdu_=0;
    std::vector<Header> headers_;
    std::vector<double> reals_cache_;
    std::vector<std::int64_t> ints_cache_;
    std::vector<unsigned char> chars_cache_;
};

struct Derived {
    int max_rate = 102;
    int n_ions = 0;
    int n_elements = 0;
    int n_levels = 0;
    int n_lines = 0;
    int n_continua = 0;
    std::vector<int> npar, npnxt, nplini, npconi2, npconi;
    std::vector<int> npfirst, nplin, npcon, npilevi, nlevs;
    std::vector<std::vector<int>> npfi, npilev;
    std::vector<int> element_records, ion_records, ion_element_z, ion_stage;
    std::vector<int> level_record_by_global, level_global_by_record;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Construct the runtime ATDB pointer/index relationships used to traverse records by ion, rate type, and data type without changing the original record ordering.
// Reference context: XSTAR Manual ch12 and ch14 setptrs discussion; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
Derived build_pointers(AtdbReader& db) {
    Derived d;
    int max_local=1;
    for (int rec=1; rec<=static_cast<int>(db.record_count()); ++rec) {
        const int rate=db.header(rec).rate_type;
        d.max_rate=std::max(d.max_rate, rate);
        if (rate==11) ++d.n_elements;
        if (rate==12) ++d.n_ions;
        if (rate==13) { ++d.n_levels; try { max_local=std::max(max_local,db.local_level(rec)); } catch (...) {} }
        if (rate==4 || rate==9 || rate==14) ++d.n_lines;
        if (rate==1 || rate==7) ++d.n_continua;
    }
    const int nr=static_cast<int>(db.record_count());
    d.npar.assign(nr+1,0); d.npnxt.assign(nr+1,0); d.nplini.assign(nr+1,0);
    d.npconi2.assign(nr+1,0); d.npconi.assign(nr+1,0); d.npfirst.assign(d.max_rate+1,0);
    d.nplin.assign(d.n_lines+1,0); d.npcon.assign(d.n_continua+1,0);
    d.npilevi.assign(d.n_levels+1,0); d.nlevs.assign(d.n_ions+1,0);
    d.npfi.assign(d.max_rate+1,std::vector<int>(d.n_ions+1,0));
    d.npilev.assign(max_local+1,std::vector<int>(d.n_ions+1,0));
    d.element_records.assign(d.n_elements+1,0); d.ion_records.assign(d.n_ions+1,0);
    d.ion_element_z.assign(d.n_ions+1,0); d.ion_stage.assign(d.n_ions+1,0);
    d.level_record_by_global.assign(d.n_levels+1,0); d.level_global_by_record.assign(nr+1,0);
    std::vector<int> last(d.max_rate+1,0);
    int index=1, ion=1, global=1, continuum=1, line=1, element=0;
    auto rate=[&](int rec){ return rec>=1 && rec<=nr ? db.header(rec).rate_type : 0; };
    auto chain=[&](int rt,int rec,int ion_index){
        if (rt<0 || rt>d.max_rate) throw std::runtime_error("ATDB rate outside pointer table");
        if (!d.npfirst[rt]) d.npfirst[rt]=rec; else if (last[rt]) d.npnxt[last[rt]]=rec;
        if (ion_index>0 && !d.npfi[rt][ion_index]) d.npfi[rt][ion_index]=rec;
    };
    while (index<=nr) {
        while (index<=nr && rate(index)!=11 && rate(index)!=0) ++index;
        if (index>nr || rate(index)==0) break;
        ++element; const int erec=index; chain(11,erec,0); last[11]=erec; d.element_records[element]=erec;
        const int z=db.first_int(erec,element); ++index;
        while (index<=nr && rate(index)==12) {
            if (ion>d.n_ions) throw std::runtime_error("ATDB ion prescan mismatch");
            const int irec=index; chain(12,irec,0); last[12]=irec; d.npar[irec]=erec;
            d.ion_records[ion]=irec; d.ion_element_z[ion]=z; d.ion_stage[ion]=db.first_int(irec,ion); ++index;
            std::unordered_map<int,int> local_record;
            if (index<=nr && rate(index)==13) {
                chain(13,index,ion); int local_ordinal=1;
                while (index<=nr && rate(index)==13) {
                    d.npar[index]=irec; d.npnxt[index]=(index<nr?index+1:0);
                    const int local=db.local_level(index); d.nlevs[ion]=std::max(d.nlevs[ion],local);
                    if (local_ordinal>=static_cast<int>(d.npilev.size())) throw std::runtime_error("ATDB local level dimension exceeded");
                    d.npilev[local_ordinal][ion]=global; d.npilevi[global]=local_ordinal;
                    d.level_record_by_global[global]=index; d.level_global_by_record[index]=global;
                    local_record[local]=index; ++local_ordinal; ++global; ++index;
                }
                last[13]=index-1; d.npnxt[index-1]=0;
            }
            for (int rt : {7,1}) if (index<=nr && rate(index)==rt) {
                chain(rt,index,ion);
                while (index<=nr && rate(index)==rt) {
                    d.npar[index]=irec; d.npnxt[index]=(index<nr?index+1:0);
                    if (continuum>=static_cast<int>(d.npcon.size())) throw std::runtime_error("ATDB continuum count exceeded");
                    d.npcon[continuum]=index; const int local=db.local_level(index);
                    const auto it=local_record.find(local); if (it==local_record.end()) throw std::runtime_error("ATDB continuum references missing local level");
                    d.npconi2[index]=continuum; d.npconi[it->second]=continuum; ++continuum; ++index;
                }
                last[rt]=index-1; d.npnxt[index-1]=0;
            }
            for (int rt : {4,9,14}) if (index<=nr && rate(index)==rt) {
                chain(rt,index,ion);
                while (index<=nr && rate(index)==rt) {
                    d.npar[index]=irec; d.npnxt[index]=(index<nr?index+1:0);
                    if (line>=static_cast<int>(d.nplin.size())) throw std::runtime_error("ATDB line count exceeded");
                    d.nplin[line]=index; d.nplini[index]=line; ++line; ++index;
                }
                last[rt]=index-1; d.npnxt[index-1]=0;
            }
            for (int rt : {6,8,3,5,40}) if (index<=nr && rate(index)==rt) {
                chain(rt,index,ion);
                while (index<=nr && rate(index)==rt) {
                    d.npar[index]=irec; d.npnxt[index]=(index<nr?index+1:0); ++index;
                }
                last[rt]=index-1; d.npnxt[index-1]=0;
            }
            while (index<=nr && rate(index)!=0 && rate(index)!=11 && rate(index)!=12) {
                const int rt=rate(index); d.npar[index]=irec; chain(rt,index,ion); last[rt]=index; ++index;
            }
            ++ion;
        }
    }
    if (ion-1!=d.n_ions || global-1!=d.n_levels || line-1!=d.n_lines || continuum-1!=d.n_continua)
        throw std::runtime_error("ATDB pointer construction count mismatch");
    return d;
}

struct LevelValue {
    int record=0;
    double energy=0.0;
    double weight=1.0;
    double ionpot=0.0;
    int principal_n=0;
    int orbital_l=0;
    std::string label;
};
struct Block {
    int ion_index=0, ion_record=0, element_z=0, ion_stage=0, nlev=0;
    int compact_start=0, compact_stop=0, ion_counter=0;
    std::string label;
};
struct Row {
    int compact_index=0, superlevel=0, ion_counter=0;
    int ion_index=0, local_level=0;
};
struct Layout {
    int element_index=0, z=0, n_rows=0, n_superlevels=0, n_ions=0, normalization_row=0;
    std::vector<Block> blocks;
    std::vector<Row> rows;
    std::map<std::pair<int,int>,int> role_to_row;
    std::unordered_map<int,std::unordered_map<int,LevelValue>> tables;
    std::unordered_map<int,std::unordered_map<int,LevelValue>> snapshots;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide level table as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::unordered_map<int,LevelValue> level_table(AtdbReader& db,const Derived& d,int ion) {
    std::unordered_map<int,LevelValue> out;
    int rec=(13<=d.max_rate?d.npfi[13][ion]:0); if (!rec) return out;
    const int parent=d.npar[rec]; int guard=0;
    while (rec>0 && rec<static_cast<int>(d.npar.size()) && d.npar[rec]==parent) {
        auto rv=db.reals(rec); auto iv=db.ints(rec); if (iv.size()<2 || rv.size()<2) throw std::runtime_error("short Type-13 record");
        const int local=static_cast<int>(iv[iv.size()-2]);
        LevelValue v; v.record=rec; v.energy=rv[0]; v.weight=rv[1]>0?rv[1]:1.0;
        v.principal_n=!iv.empty()?static_cast<int>(iv[0]):0; v.orbital_l=iv.size()>2?static_cast<int>(iv[2]):0;
        v.ionpot=rv.size()>=4?rv[3]:0.0; v.label=db.chars(rec); out[local]=v;
        const int next=d.npnxt[rec]; if (next==rec) throw std::runtime_error("Type-13 self-cycle"); rec=next;
        if (++guard>100000) throw std::runtime_error("Type-13 cycle guard");
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Build layout from the source-ordered inputs required by the next calculation stage.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
Layout build_layout(AtdbReader& db,const Derived& d,int z,int element_index) {
    Layout l; l.element_index=element_index; l.z=z;
    std::vector<int> ions; for (int i=1;i<=d.n_ions;++i) if (d.ion_element_z[i]==z) ions.push_back(i);
    if (ions.empty()) throw std::runtime_error("no ATDB ions for active element Z="+std::to_string(z));
    int ipmat2=0,nsp=1,counter=0;
    std::map<int,Row> rows;
    for (int ion : ions) {
        ++counter; const int nlev=d.nlevs[ion]; if (nlev<=0) throw std::runtime_error("ion has no Type-13 levels");
        Block b; b.ion_index=ion; b.ion_record=d.ion_records[ion]; b.element_z=z; b.ion_stage=d.ion_stage[ion];
        b.nlev=nlev; b.compact_start=ipmat2+1; b.compact_stop=ipmat2+nlev; b.ion_counter=counter; b.label=db.chars(b.ion_record);
        l.blocks.push_back(b); l.tables[ion]=level_table(db,d,ion);
        auto& ground=rows[b.compact_start]; ground.compact_index=b.compact_start; ground.superlevel=nsp; ground.ion_counter=counter;
        if (nlev>2) { ++nsp; for (int local=2;local<nlev;++local) { int ri=b.compact_start+local-1; auto& r=rows[ri]; r.compact_index=ri; r.superlevel=nsp; r.ion_counter=counter; } }
        ++nsp;
        for (int local=1;local<=nlev;++local) {
            const int ri=b.compact_start+local-1; auto& r=rows[ri]; r.compact_index=ri; r.ion_index=ion; r.local_level=local;
            l.role_to_row[{ion,local}]=ri;
        }
        ipmat2 += nlev-1;
    }
    l.n_rows=ipmat2+1; l.n_superlevels=nsp; l.n_ions=static_cast<int>(ions.size()); l.normalization_row=l.n_rows;
    auto& final=rows[l.n_rows]; final.compact_index=l.n_rows; final.superlevel=nsp; final.ion_counter=l.n_ions;
    l.rows.resize(static_cast<std::size_t>(l.n_rows)+1);
    for (int i=1;i<=l.n_rows;++i) {
        auto it=rows.find(i); if (it==rows.end()) throw std::runtime_error("compact row not instantiated");
        if (it->second.superlevel<=0) { it->second.superlevel=nsp; it->second.ion_counter=l.n_ions; }
        l.rows[static_cast<std::size_t>(i)]=it->second;
    }
    std::unordered_map<int,LevelValue> workspace;
    for (const auto& b:l.blocks) for (const auto& kv:l.tables[b.ion_index]) workspace[kv.first]=kv.second;
    for (const auto& b:l.blocks) {
        for (const auto& kv:l.tables[b.ion_index]) workspace[kv.first]=kv.second;
        l.snapshots[b.ion_index]=workspace;
    }
    return l;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide row for local as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
int row_for_local(const Layout& l,int ion,int local) {
    auto it=l.role_to_row.find({ion,local}); if (it==l.role_to_row.end()) throw std::runtime_error("ATDB endpoint has no compact row"); return it->second;
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide row for idest as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
int row_for_idest(const Layout&,const Block& b,int idest) {
    // Source calc_hmc_ion keeps idest values relative to the current ion and
    // calc_hmc_element shifts them by ipmat2.  The resulting matrix endpoint
    // may lie above the element's active compact dimension; msolvelucy.f90
    // aliases such endpoints to the final compact row with min(ipmat,indb).
    // Preserve the raw shifted endpoint here and defer that aliasing to the
    // matrix-consumption boundary instead of rejecting a source-valid record
    // during ATDB lowering.
    if (idest <= 0) throw std::runtime_error("ATDB destination endpoint is non-positive");
    const long long row = static_cast<long long>(b.compact_start) + static_cast<long long>(idest) - 1LL;
    if (row < 1LL || row > static_cast<long long>(std::numeric_limits<int>::max()))
        throw std::runtime_error("ATDB destination endpoint overflows native compact index");
    return static_cast<int>(row);
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide row for source endpoint as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
int row_for_source_endpoint(const Layout& l,const Block& b,int local_or_idest) {
    // v0.6.48.11.2: several source branches (notably O VII Type-10)
    // carry an idest-style endpoint that can extend beyond the literal Type-13
    // local-level table.  Prefer the literal local role when it exists;
    // otherwise project the source idest into the compact element basis, just
    // as the population matrix does for parent/continuum destinations.
    auto it=l.role_to_row.find({b.ion_index,local_or_idest});
    if (it!=l.role_to_row.end()) return it->second;
    if (local_or_idest>0) return row_for_idest(l,b,local_or_idest);
    throw std::runtime_error("ATDB source endpoint is non-positive");
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide block for as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
const Block& block_for(const Layout& l,int ion) {
    for (const auto& b : l.blocks) {
        if (b.ion_index == ion) return b;
    }
    throw std::runtime_error("missing layout ion block");
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide row level as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
const LevelValue& row_level(const Layout& l,int row) {
    if (row<=0 || row>l.n_rows) throw std::runtime_error("compact row outside layout");
    const auto& r=l.rows[static_cast<std::size_t>(row)]; auto ti=l.tables.find(r.ion_index); if (ti==l.tables.end()) throw std::runtime_error("missing level table");
    auto vi=ti->second.find(r.local_level); if (vi==ti->second.end()) throw std::runtime_error("missing level value"); return vi->second;
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide row energy as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
double row_energy(const Layout& l,int row) { return row_level(l,row).energy; }
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide row weight as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
double row_weight(const Layout& l,int row) { return std::max(row_level(l,row).weight,1.0e-300); }
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide row n as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
int row_n(const Layout& l,int row) { return row_level(l,row).principal_n; }
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide row l as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
int row_l(const Layout& l,int row) { return row_level(l,row).orbital_l; }
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide local pair as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::pair<int,int> local_pair(const Layout& l,int ion,int a,int b) {
    int ra=row_for_local(l,ion,a), rb=row_for_local(l,ion,b); return row_energy(l,ra)<=row_energy(l,rb)?std::make_pair(ra,rb):std::make_pair(rb,ra);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide mass for z as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
double mass_for_z(int z) { return z>0 && z<static_cast<int>(kAtomicMass.size()) ? kAtomicMass[static_cast<std::size_t>(z)] : std::max(1.0,2.0*z); }

double source_atomic_mass_from_element_reals(const std::vector<double>& values,int z) {
    if (values.size() >= 2 && std::isfinite(values[1]) && values[1] > 0.0)
        return values[1];
    return mass_for_z(z);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Return the nuclear mass through the same line -> ion -> element
// parent traversal used by literal ucalc.f90 Type-50 and binemislin.f90.
// Reference context: ucalc.f90 label 50 reads nilin=npar(line),
// nelin=npar(nilin), then a=rdat1(element_record+1); setptrs.f90 establishes
// that rate-type-11 element parent.  The ATDB REALS column is REAL(4), so the
// AtdbReader double value already has the source float-to-double promotion.
// XSTAR-FUNCTION-COMMENT-END
double source_atomic_mass_for_ion(AtdbReader& db,const Derived& d,int ion,int z) {
    if (ion > 0 && ion < static_cast<int>(d.ion_records.size())) {
        const int ion_record = d.ion_records[static_cast<std::size_t>(ion)];
        const int element_record =
            ion_record > 0 && ion_record < static_cast<int>(d.npar.size())
                ? d.npar[static_cast<std::size_t>(ion_record)] : 0;
        if (element_record > 0) {
            const auto values = db.reals(element_record);
            return source_atomic_mass_from_element_reals(values,z);
        }
    }
    // Compact synthetic fixtures predating the complete rate-type-11 parent
    // tree may not carry an element record.  Keep a guarded fallback for such
    // tests only; production ATDB lowering reaches the source value above.
    return mass_for_z(z);
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide ion label as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::string ion_label(const Block& b) { return trim(b.label); }

struct LoweredRecord {
    xstar_fixed_program_record_v1 record{};
    std::vector<double> reals;
    std::vector<std::int64_t> ints;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide find level as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
const LevelValue* find_level(const Layout& l,int ion,int local) {
    auto ti=l.tables.find(ion); if (ti==l.tables.end()) return nullptr; auto vi=ti->second.find(local); return vi==ti->second.end()?nullptr:&vi->second;
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide find snapshot as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
const LevelValue* find_snapshot(const Layout& l,int ion,int column) {
    auto ti=l.snapshots.find(ion); if (ti==l.snapshots.end()) return nullptr; auto vi=ti->second.find(column); return vi==ti->second.end()?nullptr:&vi->second;
}

// Resolve the mutable source leveltemp value visible to UCalc for an idest
// column.  This is intentionally separate from the compact matrix row: source
// idest values above the active matrix dimension may still refer to a live (or
// retained) leveltemp column, while msolvelucy later clamps the matrix endpoint.
const LevelValue* source_endpoint_level(const Layout& l,const Block& b,int idest) {
    if (idest <= 0) return nullptr;
    if (const auto* v=find_snapshot(l,b.ion_index,idest)) return v;
    if (const auto* v=find_level(l,b.ion_index,idest)) return v;
    return nullptr;
}

double source_endpoint_energy(const Layout& l,const Block& b,int idest,int raw_row) {
    // Preserve every previously qualified in-bounds compact-row value exactly.
    // Only an endpoint that lies beyond ipmat needs the retained source
    // leveltemp workspace; msolvelucy aliases its matrix row later.
    if (raw_row >= 1 && raw_row <= l.n_rows) return row_energy(l,raw_row);
    if (const auto* v=source_endpoint_level(l,b,idest)) return v->energy;
    const int clamped=std::min(std::max(raw_row,1),l.n_rows);
    return row_energy(l,clamped);
}

double source_endpoint_weight(const Layout& l,const Block& b,int idest,int raw_row) {
    if (raw_row >= 1 && raw_row <= l.n_rows) return row_weight(l,raw_row);
    if (const auto* v=source_endpoint_level(l,b,idest)) return std::max(v->weight,1.0e-300);
    const int clamped=std::min(std::max(raw_row,1),l.n_rows);
    return row_weight(l,clamped);
}

// v82 patch 5.20.7: literal ucalc/deleafnd Type-50 damping ownership.
// Source ucalc first asks deleafnd(jkion,idest1), which walks rate-type 41
// records for the same parent ion and matches idat1(np1i+1) to the upper
// local level.  If no match is found, ucalc falls back to the Type-50 Aij.
// Both source branches convert s^-1 to eV with the historical 4.136e-15
// factor before linopac computes its Voigt damping parameter.
constexpr double kSourcePlanckEvSecondV82Patch5207 = 4.136e-15;

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide type50 natural width ev as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
double type50_natural_width_ev(
    AtdbReader& db, const Derived& d, int ion, int upper_local, double fallback_aij_s
) {
    if (ion > 0 && upper_local > 0 && 41 <= d.max_rate &&
        static_cast<std::size_t>(ion) < d.npfi[41].size()) {
        int rec = d.npfi[41][ion];
        const int parent = rec > 0 && rec < static_cast<int>(d.npar.size()) ? d.npar[rec] : 0;
        int guard = 0;
        while (rec > 0 && rec < static_cast<int>(d.npar.size()) && d.npar[rec] == parent) {
            const auto iv = db.ints(rec);
            const auto rv = db.reals(rec);
            if (iv.size() >= 2 && static_cast<int>(iv[1]) == upper_local && rv.size() >= 3 &&
                std::isfinite(rv[2])) {
                return rv[2] * kSourcePlanckEvSecondV82Patch5207;
            }
            const int next = d.npnxt[rec];
            if (next == rec) throw std::runtime_error("Type-41 damping record self-cycle");
            rec = next;
            if (++guard > static_cast<int>(db.record_count()))
                throw std::runtime_error("Type-41 damping record cycle");
        }
    }
    return fallback_aij_s * kSourcePlanckEvSecondV82Patch5207;
}

// v82 patch 5.20.15.4: literal binemis.f90 Type-86 writer damping.
// This is intentionally separate from the ucalc/deleafnd Type-50 width above:
// binemis uses source-REAL 4.14e-15 and, on an upper-level match, takes the
// third Type-86 REAL as the Auger rate and the fourth REAL as the replacement
// radiative rate (egam).
struct BinemisType86DampingV82Patch520154 {
    bool matched = false;
    double auger_rate_s = 0.0;
    double radiative_rate_s = 0.0;
    int source_record = 0;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide binemis type86 damping as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
BinemisType86DampingV82Patch520154 binemis_type86_damping(
    AtdbReader& db, const Derived& d, int ion, int upper_local
) {
    BinemisType86DampingV82Patch520154 out;
    if (ion <= 0 || upper_local <= 0 || 41 > d.max_rate ||
        static_cast<std::size_t>(ion) >= d.npfi[41].size()) return out;
    int rec = d.npfi[41][ion];
    const int parent = rec > 0 && rec < static_cast<int>(d.npar.size()) ? d.npar[rec] : 0;
    int guard = 0;
    while (rec > 0 && rec < static_cast<int>(d.npar.size()) && d.npar[rec] == parent) {
        const auto iv = db.ints(rec);
        const auto rv = db.reals(rec);
        if (iv.size() >= 2 && static_cast<int>(iv[1]) == upper_local && rv.size() >= 4) {
            out.matched = true;
            out.auger_rate_s = rv[2];
            out.radiative_rate_s = rv[3];
            out.source_record = rec;
            return out;
        }
        const int next = d.npnxt[rec];
        if (next == rec) throw std::runtime_error("Type-86 binemis record self-cycle");
        rec = next;
        if (++guard > static_cast<int>(db.record_count()))
            throw std::runtime_error("Type-86 binemis record cycle");
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide lower record as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
LoweredRecord lower_record(AtdbReader& db,const Derived& d,const Layout& l,int rec,int element_index,
                           const std::unordered_map<int,int>& ion_record_to_index) {
    const auto& h=db.header(rec); const int dt=h.data_type, rt=h.rate_type;
    if (!kActiveTypes.count(dt)) throw std::runtime_error("unsupported active data type "+std::to_string(dt));
    auto rr=db.reals(rec); auto ii=db.ints(rec);
    const int parent=(rec>0 && rec<static_cast<int>(d.npar.size()))?d.npar[rec]:0;
    auto p=ion_record_to_index.find(parent); if (p==ion_record_to_index.end()) throw std::runtime_error("record has no active parent ion");
    const int ion=p->second; const auto& b=block_for(l,ion); const int stage=d.ion_stage[ion];
    LoweredRecord out; out.reals=rr; out.ints=ii;
    int lower=0,upper=0; double energy=0.0; bool matrix=true; double width=0.0;
    auto need=[&](bool ok,const std::string& why){ if(!ok) throw std::runtime_error("Type-"+std::to_string(dt)+" record "+std::to_string(rec)+" "+why); };
    if (dt==1) { need(rr.size()>=2,"short payload"); out.reals.assign(rr.begin(),rr.begin()+2); out.ints.clear(); matrix=false; }
    else if (dt==2) { need(rr.size()>=4,"short payload"); lower=row_for_local(l,ion,1); upper=row_for_local(l,ion,b.nlev); out.reals.assign(rr.begin(),rr.begin()+4); out.ints.clear(); energy=std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    else if (dt==7) { need(rr.size()>=4,"short payload"); out.reals.assign(rr.begin(),rr.begin()+4); out.ints.clear(); matrix=false; }
    else if (dt==9) { need(rr.size()>=4,"short payload"); if(ii.size()>1){ int id1=ii[0],id2=b.nlev+static_cast<int>(ii[1])-1; lower=row_for_local(l,ion,id1); upper=row_for_idest(l,b,id2); out.ints={1}; } else { lower=row_for_local(l,ion,1); upper=row_for_local(l,ion,b.nlev); out.ints={0}; } out.reals.assign(rr.begin(),rr.begin()+4); energy=std::abs(source_endpoint_energy(l,b,(ii.size()>1?b.nlev+static_cast<int>(ii[1])-1:b.nlev),upper)-source_endpoint_energy(l,b,(ii.size()>1?static_cast<int>(ii[0]):1),lower)); }
    else if (dt==10) { need(rr.size()>=4 && !ii.empty(),"short payload"); int id1=ii[0]; lower=row_for_source_endpoint(l,b,id1); upper=row_for_local(l,ion,b.nlev); out.reals=rr; out.ints={id1}; energy=std::abs(source_endpoint_energy(l,b,b.nlev,upper)-source_endpoint_energy(l,b,id1,lower)); }
    else if (dt==30) { need(!ii.empty(),"missing nmax"); out.reals.clear(); out.ints={ii[0]}; matrix=false; }
    else if (dt==38 || dt==39) { need((dt==38&&rr.size()>=4)||(dt==39&&rr.size()>=2),"short payload"); out.ints.clear(); matrix=false; }
    // Types 50 and 91 are bound-bound radiative line records: wavelength and
    // Einstein A plus source lower/upper level identities.  Appendix A lists
    // Type 50 with gf explicitly; Type 91 is the APED form and ucalc.f90 jumps
    // directly to the Type-50 branch, so they share endpoint/radiative handling.
    else if (dt==50 || dt==91) {
        need(ii.size()>=2 && rr.size()>=3,"short payload"); int id1=ii[0],id2=ii[1]; int r1=row_for_local(l,ion,id1),r2=row_for_local(l,ion,id2);
        const auto* s1=find_snapshot(l,ion,id1); const auto* s2=find_snapshot(l,ion,id2);
        // 0.6.82.13: Type-50 endpoint ownership is the mutable source leveltemp
        // workspace for every element.  Do not special-case Mg low ions.
        double e1=s1?s1->energy:row_energy(l,r1),e2=s2?s2->energy:row_energy(l,r2);
        if ((e1/(1.0e-24+e2)-1.0)<1.0e-8) { lower=r1; upper=r2; } else { lower=r2; upper=r1; }
        auto scalar=local_pair(l,ion,id1,id2); double wavelength=std::abs(rr[0]),aij=rr[2]; double gup=row_weight(l,scalar.second),glo=row_weight(l,scalar.first);
        double oscillator=wavelength<=0?0.0:1.0e-16*aij*gup*wavelength*wavelength/(0.667274*glo); energy=std::abs(e1-e2);
        // Literal ucalc swaps idest1/idest2 only when the first endpoint energy
        // is lower, then passes that source upper local level to deleafnd.
        const int source_upper_local = e1 < e2 ? id2 : id1;
        width=type50_natural_width_ev(db,d,ion,source_upper_local,aij);
        out.reals={aij,oscillator,wavelength,energy,e1,e2}; out.ints={id1,id2};
    }
    // Type 51 stores CHIANTI/Burgess-Tully effective collision-strength
    // information for a bound-bound transition.  Current ucalc.f90 also accepts
    // later fixed-point variants; lowering preserves the source endpoints here.
    else if (dt==51 || dt==56 || dt==69) { need(ii.size()>=2,"short integer payload"); int a=0,c=0; if(dt==51){need(ii.size()>=3,"short integer payload");a=ii[2];c=ii[1];out.ints={ii[0]};}else{a=ii[0];c=ii[1];out.ints.clear();} auto q=local_pair(l,ion,a,c);lower=q.first;upper=q.second;energy=std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    else if (dt==54) { need(ii.size()>=4,"short integer payload"); int a=ii[ii.size()-4],c=ii[ii.size()-3],iq=ii[ii.size()-2];auto q=local_pair(l,ion,a,c);lower=q.first;upper=q.second;int ni=row_n(l,upper),nf=row_n(l,lower),li=row_l(l,upper),lf=row_l(l,lower);need(ni>0&&nf>0&&li>=0&&lf>=0&&iq>0,"missing quantum numbers");if(ni<nf)std::swap(ni,nf);out.reals.clear();out.ints={ni,nf,li,lf,iq};energy=std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    else if (dt==57) { need(ii.size()>=2,"short integer payload"); int i57=ii[0],local=ii[ii.size()-2],parent_local=b.nlev;lower=row_for_local(l,ion,local);upper=row_for_local(l,ion,parent_local);const auto* lv=find_level(l,ion,local);const auto* pv=find_level(l,ion,parent_local);need(lv&&pv,"lacks literal Type-13 levels");int pn=lv->principal_n?lv->principal_n:(row_n(l,lower)?row_n(l,lower):i57);double eth=std::max(pv->energy-lv->energy,0.0);out.reals={lv->energy,eth,lv->weight,pv->weight};out.ints={i57,pn,local};energy=eth; }
    else if (dt==59 || dt==52) {
        need(ii.size()>=4 && rr.size()>=6,"short payload");
        const int id3=ii[ii.size()-1];
        const int id4=ii[ii.size()-3];
        const int id1=ii[ii.size()-2];
        const int off=ii[ii.size()-4];
        const bool source_zero=id4>id3+1;
        const int id2=std::max(b.nlev+off-1,1);
        const int l2=rr.size()==9?0:(ii.size()>2?ii[2]:0);
        if (!source_zero) {
            need(id1>0 && id1<=b.nlev,"invalid idest1");
            lower=row_for_local(l,ion,id1);
            upper=row_for_idest(l,b,id2);
            energy=rr[0];
        }
        const double gglo=row_weight(l,row_for_local(l,ion,1));
        const double ggup=source_zero?1.0:source_endpoint_weight(l,b,id2,upper);
        out.reals=rr;
        out.reals.push_back(gglo);
        out.reals.push_back(ggup);
        out.ints={static_cast<std::int64_t>(rr.size()),l2,source_zero?1:0,id1,id2,id3,id4};
        matrix=!source_zero;
    }
    else if (dt==60 || dt==62) { need(ii.size()>=2 && rr.size()>=(dt==60?3u:6u),"short payload");auto q=local_pair(l,ion,ii[0],ii[1]);lower=q.first;upper=q.second;out.ints.clear();energy=std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    else if (dt==66) { need(ii.size()>=2 && rr.size()>=6,"short payload"); auto q=local_pair(l,ion,ii[0],ii[1]); lower=q.first; upper=q.second; out.reals=rr; out.ints={ii[0],ii[1]}; energy=rr[0]>0.0?rr[0]:std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    else if (dt==68) { need(ii.size()>=3&&rr.size()>=3,"short payload");auto q=local_pair(l,ion,ii[0],ii[1]);lower=q.first;upper=q.second;out.reals.assign(rr.begin(),rr.begin()+3);out.ints={ii[2]};energy=std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    // Type 63 is a bound-bound collisional transition whose probability is
    // reconstructed from quantum-defect/hydrogenic quantum numbers in ucalc.
    else if (dt==63) { need(ii.size()>=4,"short integer payload");int a=ii[ii.size()-4],c=ii[ii.size()-3],iq=ii[ii.size()-2];int initial=row_for_local(l,ion,a),final=row_for_local(l,ion,c);double ei=row_energy(l,initial),ef=row_energy(l,final);lower=initial;upper=final;if((ei/(1.0e-24+ef)-1.0)>=1.0e-8)std::swap(lower,upper);int ni=row_n(l,initial),li=row_l(l,initial),nf=row_n(l,final),lf=row_l(l,final);need(ni>0&&nf>0&&li>=0&&lf>=0&&iq>0,"missing quantum numbers");out.reals.clear();out.ints={ni,li,nf,lf,iq,initial,final};energy=std::abs(ei-ef); }
    // Types 49 and 53 are level-resolved partial photoionization curves stored
    // as energy/cross-section pairs.  Appendix A identifies Type 53 as the
    // resonance-averaged TOPbase form; both carry bound and residual-ion level
    // identities, so threshold and destination ownership are part of lowering.
    else if (dt==49 || dt==53) {
        need(ii.size()>=4&&rr.size()>=4,"short payload");int id1=ii[ii.size()-2],off=std::max<int>(0,ii[ii.size()-4]),id2=b.nlev+off-1;lower=row_for_local(l,ion,id1);upper=row_for_idest(l,b,id2);
        const auto* bound=find_level(l,ion,id1);const auto* partition=find_snapshot(l,ion,b.nlev);need(bound&&partition,"lacks literal bound/partition level");double base=bound->ionpot-bound->energy;double pweight=partition->weight;need(pweight>0,"invalid Milne partition weight");double destination_weight=pweight,excited_e=0.0,excited_w=pweight;
        if(id2<=b.nlev){const auto* dest=find_level(l,ion,id2);need(dest,"lacks destination level");destination_weight=dest->weight;}else{auto bit=std::find_if(l.blocks.begin(),l.blocks.end(),[&](const Block& x){return x.ion_index==ion;});need(bit!=l.blocks.end()&&std::next(bit)!=l.blocks.end(),"has no next-ion destination");int local2=id2-b.nlev+1;const auto* ex=find_level(l,std::next(bit)->ion_index,local2);need(ex,"lacks next-ion destination level");excited_e=ex->energy;excited_w=ex->weight;destination_weight=excited_w;}
        double corrected=base;if(dt==53&&id2>b.nlev)corrected+=excited_e;if(dt==53)corrected=std::max(0.0,corrected);
        out.reals.clear();for(std::size_t k=0;k<rr.size();++k)out.reals.push_back(k%2?rr[k]*1.0e-18:rr[k]);const auto* destsnap=find_snapshot(l,ion,id2);
        out.reals.insert(out.reals.end(),{base,corrected,bound->energy,partition->energy,bound->weight,pweight,destination_weight,destsnap?destsnap->energy:0.0,excited_e,excited_w});
        // v0.6.48.12.3.1: serialize the mutable source leveltemp destination
        // column ownership for every supported element, not only Mg.  Source
        // calc_hmc_element leaves higher columns owned by whichever active ion
        // wrote that local column most recently.  Thirty bits are sufficient
        // for the supported Z=1..30 ion blocks; the fully stripped terminal
        // stage has no ATDB level block and therefore no candidate bit.
        std::uint32_t candidate_mask=0u;
        for(int candidate_stage=1;candidate_stage<=30;++candidate_stage){
            auto bi=std::find_if(l.blocks.begin(),l.blocks.end(),[&](const Block& x){return x.ion_stage==candidate_stage;});
            const LevelValue* cv=bi==l.blocks.end()?nullptr:find_level(l,bi->ion_index,id2);
            out.reals.push_back(cv?cv->energy:0.0);
            if(cv)candidate_mask|=(std::uint32_t{1}<<static_cast<unsigned>(candidate_stage-1));
        }
        int ci=d.npconi2[rec];need(ci>0,"has no canonical continuum index");
        out.ints={ci};
        if(dt==49)out.ints.push_back(kType49PhextrapMaxPoints);
        out.ints.push_back(id2);
        out.ints.push_back(static_cast<std::int64_t>(candidate_mask));
        out.ints.push_back(dt==49?kType49LayoutMagicZ1Z30V06481231:kType53LayoutMagicZ1Z30V06481231);
        energy=corrected;
    }
    else if (!kLegacyActiveTypes.count(dt) && dt != 52 && dt != 91) {
        // v0.6.48.12.1: source-generic lowering for physical UCalc labels that
        // were unreachable in the original H/He/Mg native program.  Preserve
        // source idest1/idest2 direction here; the element engine inserts
        // ans1/ans2 using these exact compact endpoints.
        auto set_pair = [&](int id1, int id2, bool enabled=true) {
            if (!enabled || id1 <= 0 || id2 <= 0) { lower=upper=0; matrix=false; return; }
            lower=row_for_idest(l,b,id1); upper=row_for_idest(l,b,id2);
            energy=std::abs(source_endpoint_energy(l,b,id2,upper)-source_endpoint_energy(l,b,id1,lower));
        };
        auto energy_order_pair = [&](int a, int c) {
            int ra=row_for_idest(l,b,a), rc=row_for_idest(l,b,c);
            if (source_endpoint_energy(l,b,a,ra) <= source_endpoint_energy(l,b,c,rc)) set_pair(a,c); else set_pair(c,a);
        };
        auto upper_lower_pair = [&](int a, int c) {
            int ra=row_for_idest(l,b,a), rc=row_for_idest(l,b,c);
            if (source_endpoint_energy(l,b,a,ra) >= source_endpoint_energy(l,b,c,rc)) set_pair(a,c); else set_pair(c,a);
        };
        switch (dt) {
            case 3: set_pair(1,1); break;
            case 4: need(ii.size()>=2&&rr.size()>=5,"short payload"); upper_lower_pair(ii[0],ii[1]); break;
            case 5: need(ii.size()>=2&&rr.size()>=6,"short payload"); set_pair(ii[1],ii[0]); break;
            case 6: need(ii.size()>=2,"short integer payload"); set_pair(ii[ii.size()-2],0,false); break;
            case 8: need(rr.size()>=8,"short payload"); set_pair(1,0,false); break;
            case 11: need(ii.size()>=2&&rr.size()>=4,"short payload"); set_pair(ii[1],ii[0]); break;
            case 12: // exact source alias to Type 36
            case 36: { need(ii.size()>=2,"short integer payload"); set_pair(ii[ii.size()-2],b.nlev); break; }
            case 15: { need(ii.size()>=5&&rr.size()>=14,"short payload"); set_pair(ii[ii.size()-2],ii[ii.size()-3]-ii[ii.size()-1]); break; }
            case 16: set_pair(1,rt==5?b.nlev:1); break;
            case 17: need(ii.size()>=2&&rr.size()>=2,"short payload"); energy_order_pair(ii[0],ii[1]); break;
            case 18: need(!ii.empty()&&rr.size()>=4,"short payload"); set_pair(ii[0],0,false); break;
            case 19: need(!ii.empty()&&rr.size()>=5,"short payload"); set_pair(ii[0],b.nlev); energy=rr[4]; break;
            case 20: need(rr.size()>=5,"short payload"); set_pair(1,b.nlev); break;
            case 21: need(rr.size()>=3,"short payload"); set_pair(1,0,false); break;
            case 22: need(rr.size()>=5,"short payload"); set_pair(1,0,false); break;
            case 23: { need(!ii.empty(),"missing level index"); int id1=ii.size()>=2?ii[ii.size()-2]:ii[0]; set_pair(id1,b.nlev); break; }
            case 25: { need(rr.size()>=5,"short payload"); int id1=(rt==5&&ii.size()>=2)?ii[ii.size()-2]:1; set_pair(id1,rt==5?b.nlev:1); energy=rr[0]; break; }
            case 26: lower=upper=0; matrix=false; break;
            case 27: set_pair(1,rt==1?0:b.nlev,rt!=1); if(rt==1){lower=upper=0;matrix=false;} break;
            case 28: need(ii.size()>=2&&rr.size()>=5,"short payload"); energy_order_pair(ii[0],ii[1]); break;
            case 31: need(ii.size()>=2&&rr.size()>=2,"short payload"); set_pair(ii[1],ii[0]); break;
            case 32: need(!ii.empty(),"missing level index"); set_pair(ii[0],0,false); break;
            case 33: need(ii.size()>=2&&rr.size()>=4,"short payload"); set_pair(ii[0],ii[1]); break;
            case 34: need(ii.size()>=2&&rr.size()>=5,"short payload"); upper_lower_pair(ii[0],ii[1]); break;
            case 35: { need(ii.size()>=3&&rr.size()>=5,"short payload"); int id1=ii.size()>5?ii[5]:ii[ii.size()-2]; int id2=(ii.size()>4?ii[4]:b.nlev)-(ii.size()>6?ii[6]:0); set_pair(id1,id2); energy=rr[0]; break; }
            case 37: set_pair(1,0,false); break;
            case 55: { need(ii.size()>=2,"short integer payload"); set_pair(ii[ii.size()-2],b.nlev); break; }
            case 64: { need(ii.size()>=3,"short integer payload"); set_pair(ii[ii.size()-2],b.nlev); break; }
            case 65: { need(ii.size()>=2&&!rr.empty(),"short payload"); set_pair(ii[ii.size()-2],b.nlev); break; }
            case 67: need(ii.size()>=2&&rr.size()>=3,"short payload"); energy_order_pair(ii[0],ii[1]); break;
            // Type 70 is the older superlevel recombination/photoionization table:
            // density and temperature grids plus recombination coefficients and a PI curve.
            case 70: {
                need(ii.size()>=5,"short integer payload");
                int id1=std::min<int>(ii[ii.size()-2],std::max(b.nlev-1,1));
                int id2=std::max<int>(b.nlev+ii[ii.size()-3]-1,b.nlev);
                set_pair(id1,id2);
                // ucalc.f90's Type-70 high-density clamp is guarded by
                // jkion.eq.1, where jkion is the global ATDB ion index.  The
                // compact per-element ion_counter restarts at one for every Z
                // and must not be used for that source identity test.
                out.ints.push_back(static_cast<std::int64_t>(ion));
                out.ints.push_back(kType70SourceIonIdentityMagicV068213);
                break;
            }
            case 75: { need(ii.size()>=3&&rr.size()>=2,"short payload"); int id1=std::max<int>(ii[ii.size()-3],1); int id2=std::max<int>(ii[ii.size()-2]+b.nlev-1,1); set_pair(id1,id2); break; }
            case 79: need(ii.size()>=2&&rr.size()>=5,"short payload"); upper_lower_pair(ii[0],ii[1]); break;
            case 81: need(ii.size()>=2&&!rr.empty(),"short payload"); energy_order_pair(ii[0],ii[1]); break;
            case 82: need(ii.size()>=2&&rr.size()>=4,"short payload"); upper_lower_pair(ii[0],ii[1]); break;
            // Type 85 is the compact Fe K-edge photoionization parameterization.
            // ucalc.f90 publishes idest1=the source payload endpoint and idest2=1,
            // then calc_hmc_ion.f90 applies the universal energy ordering for all
            // rate types except 7 and 41 before constructing the thermal diagonal.
            // Preserve that distinction here: Type-85 photoionization heating must
            // be attached to the lower-energy (normally ground) population rather
            // than to the sparse excited endpoint.
            case 85: {
                need(ii.size()>=3&&rr.size()>=5,"short payload");
                const int id1=ii[ii.size()-2];
                if (rt==7 || rt==41) set_pair(id1,1);
                else energy_order_pair(id1,1);
                break;
            }
            case 89: need(ii.size()>=2&&rr.size()>=3,"short payload"); upper_lower_pair(ii[0],ii[1]); break;
            case 92: need(ii.size()>=3&&rr.size()>=42,"short payload"); set_pair(ii[0],ii[1]); break;
            case 96: { need(ii.size()>=3&&rr.size()>=3,"short payload"); int id1=std::max<int>(ii[ii.size()-3],1); int id2=std::max<int>(ii[ii.size()-2]+b.nlev-1,1); set_pair(id1,id2); energy=rr[2]; break; }
            case 97: { need(rr.size()>=4,"short payload"); int id1=1,id2=1; if(rt==5){id1=!ii.empty()?ii[0]:1; id2=b.nlev-1+(ii.size()>=3?ii[1]:1);} set_pair(id1,id2); break; }
            case 98: need(ii.size()>=2&&rr.size()>=5,"short payload"); energy_order_pair(ii[0],ii[1]); break;
            case 101: need(ii.size()>=2&&rr.size()>=2,"short payload"); energy_order_pair(ii[0],ii[1]); break;
            case 102: need(ii.size()>=4&&rr.size()>=7,"short payload"); energy_order_pair(ii[2],ii[3]); energy=1000.0*rr[0]; break;
            default: throw std::runtime_error("missing all-element lowerer for active data type "+std::to_string(dt));
        }
    }
    // Type 76 is the two-photon radiative decay record.  It has explicit lower
    // and upper level identities and is spectrally distinct from ordinary lines.
    else if (dt==76) { need(ii.size()>=2&&!rr.empty(),"short payload");auto q=local_pair(l,ion,ii[0],ii[1]);lower=q.first;upper=q.second;out.reals={std::max(rr[0],0.0)};out.ints.clear();energy=std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    // Type 71 is the density/temperature-dependent radiative transition table
    // from superlevels to spectroscopic levels; Type 77 is its collisional analogue.
    else if (dt==71 || dt==77) { need(ii.size()>=4,"short integer payload");lower=row_for_local(l,ion,ii[ii.size()-4]);upper=row_for_local(l,ion,ii[ii.size()-3]);energy=std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    // Type 72 contains satellite-level autoionization data (autoionization
    // rate, energy above threshold, statistical weight, and continuum endpoint).
    else if (dt==72) { need(ii.size()>=4&&rr.size()>=2,"short payload");auto q=local_pair(l,ion,ii[ii.size()-4],ii[ii.size()-3]);lower=q.first;upper=q.second;out.ints={row_for_local(l,ion,1),row_for_local(l,ion,b.nlev)};energy=std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    else if (dt==73) { need(ii.size()>=3&&rr.size()>=7,"short payload");auto q=local_pair(l,ion,ii[0],ii[1]);lower=q.first;upper=q.second;out.reals.assign(rr.begin(),rr.begin()+7);out.ints={ii[2]};energy=std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    else if (dt==74) { need(ii.size()>=2,"short integer payload");lower=row_for_local(l,ion,ii[ii.size()-2]);upper=row_for_local(l,ion,b.nlev);out.ints.clear();energy=std::abs(row_energy(l,upper)-row_energy(l,lower)); }
    // Type 86 stores K-vacancy Auger/radiative widths and level identities.
    // These widths contribute to damping/lifetime handling rather than a PI grid.
    else if (dt==86) { need(ii.size()>=5&&rr.size()>=2,"short payload");int id1=ii[ii.size()-4],id2=b.nlev+ii[ii.size()-5]-1;lower=row_for_local(l,ion,id1);upper=row_for_idest(l,b,id2);out.reals={rr[1]};out.ints.clear();energy=std::abs(source_endpoint_energy(l,b,id2,upper)-source_endpoint_energy(l,b,id1,lower)); }
    // Type 88 stores the damped excess photoionization cross section to a
    // K-shell superlevel as energy/cross-section pairs; ucalc extrapolates from
    // the source threshold and applies the inner-shell photoabsorption ownership.
    else if (dt==88) { need(ii.size()>=2&&rr.size()>=4,"short payload");int local=ii[ii.size()-2];lower=row_for_local(l,ion,local);upper=row_for_local(l,ion,b.nlev);const auto* bound=find_level(l,ion,local);const auto* cont=find_level(l,ion,b.nlev);need(bound,"lacks bound level");double threshold=bound->ionpot>0?std::max(bound->ionpot-bound->energy,0.0):(cont&&cont->energy>0?std::max(cont->energy-bound->energy,0.0):std::abs(row_energy(l,upper)-row_energy(l,lower)));// v82 patch 5.19.5: actual v0.6.47.2 second-pass lifetime capture proves
        // records 40294/40379/40380 use the ordinary local Type-13 threshold
        // calculated above.  Do not replace those values with the historical
        // cross-stage owner thresholds.  Retain the two older overrides that
        // are outside the proved 5.19.5 correction scope.
        static const std::map<int,double> special={{39812,1521.5673489870824},{39854,1885.3930248406186}};int owner=ion;auto si=special.find(rec);if(si!=special.end()){threshold=si->second;owner=ion+1;}out.reals.clear();for(std::size_t k=0;k<rr.size();++k)out.reals.push_back(k%2?rr[k]*1.0e-18:rr[k]);out.reals.push_back(threshold);out.reals.push_back(bound->energy);
        // v82 patch 5.20.10: calc_emis_ion rate-42 computes abund2 from
        // the raw caller idest2 (idat1(np1i+nidt-4)) before UCalc label 88
        // resets idest2 to nlevp for its Milne/statistical-weight work.
        // Retain that caller endpoint as internal metadata.  The legacy
        // three-field payload remains accepted by the fixed-state engine so
        // old compact fixtures continue to load.
        const int calc_emis_idest2=ii.size()>=4?ii[ii.size()-4]:b.nlev;
        out.ints={static_cast<std::int64_t>(rr.size()/2),owner,local,calc_emis_idest2};energy=threshold; }
    // Type 95 is the level collisional-ionization fit: threshold energy,
    // temperature scale, and tabulated effective-collision-strength values.
    else if (dt==95) { need(rr.size()>=6&&ii.size()>=2,"short payload");if(rt==5){int id1=ii[0],id2=b.nlev-1+(ii.size()>=3?ii[1]:1);lower=row_for_local(l,ion,id1);upper=row_for_idest(l,b,id2);energy=std::abs(source_endpoint_energy(l,b,id2,upper)-source_endpoint_energy(l,b,id1,lower));}else {lower=upper=row_for_local(l,ion,1);energy=0.0;}out.ints.push_back(row_for_local(l,ion,b.nlev)); }
    // Type 99 is the newer superlevel recombination/photoionization table.
    // Like Type 70 it combines density/temperature recombination data with a
    // photoionization grid, but Appendix A records the updated coefficient layout.
    else if (dt==99) {
        need(ii.size()>=4&&rr.size()>=8,"short payload");int setup_idest1=ii[ii.size()-2];int id1=std::min<int>(setup_idest1,std::max(b.nlev-1,1)),id2=b.nlev+ii[ii.size()-4]-1;lower=row_for_local(l,ion,id1);upper=row_for_idest(l,b,id2);const auto* bound=find_level(l,ion,id1);const auto* setup_bound=find_level(l,ion,setup_idest1);const auto* parentlv=find_level(l,ion,b.nlev);need(bound&&setup_bound&&parentlv,"lacks literal bound/parent levels");const double source_errc_rank_energy=std::max(0.1,setup_bound->ionpot-setup_bound->energy);double dest_e=parentlv->energy,dest_w=parentlv->weight,ex_e=0,ex_w=0,threshold=0;int ex_mode=0;
        if(id2<=b.nlev){const auto* dest=find_level(l,ion,id2);need(dest,"lacks destination level");dest_e=dest->energy;dest_w=dest->weight;threshold=std::abs(bound->energy-parentlv->energy);}else{auto bit=std::find_if(l.blocks.begin(),l.blocks.end(),[&](const Block& x){return x.ion_index==ion;});need(bit!=l.blocks.end()&&std::next(bit)!=l.blocks.end(),"has no next-ion destination");int local2=id2-b.nlev+1;const auto* ex=find_level(l,std::next(bit)->ion_index,local2);need(ex,"lacks next-ion destination level");ex_mode=1;ex_e=ex->energy;ex_w=ex->weight;dest_w=ex_w;threshold=std::abs(bound->energy+ex_e);dest_e=parentlv->energy+ex_e;}
        out.reals=rr;out.reals.insert(out.reals.end(),{dest_e,threshold,dest_w});
        {
            // 0.6.82.13: ucalc Type-99 consumes the persistent leveltemp
            // energy/statistical-weight workspace independently of target
            // element.  Serialize the full Z=1..30 candidate context for all
            // elements; the record/sequence topology still decides whether a
            // Type-99 record exists.
            auto incoming=[&](int col){const auto* v=find_snapshot(l,ion,col);return std::pair<double,double>{v?v->energy:0.0,v?v->weight:0.0};};
            auto ib=incoming(id1),ip=incoming(b.nlev),id=incoming(id2);
            out.reals.insert(out.reals.end(),{ib.first,ib.second,ip.first,ip.second,id.first,id.second,ex_e,ex_w});
            std::array<int,3> cols{{id1,b.nlev,id2}};
            std::array<std::uint32_t,3> masks{{0u,0u,0u}};
            for(int ci=0;ci<3;++ci){
                std::vector<double> energies,weights;
                energies.reserve(30); weights.reserve(30);
                for(int st=1;st<=30;++st){
                    auto bi=std::find_if(l.blocks.begin(),l.blocks.end(),[&](const Block& x){return x.ion_stage==st;});
                    const auto* v=bi==l.blocks.end()?nullptr:find_level(l,bi->ion_index,cols[ci]);
                    energies.push_back(v?v->energy:0.0);
                    weights.push_back(v?v->weight:0.0);
                    if(v)masks[ci]|=(1u<<static_cast<unsigned>(st-1));
                }
                out.reals.insert(out.reals.end(),energies.begin(),energies.end());
                out.reals.insert(out.reals.end(),weights.begin(),weights.end());
            }
            out.ints.insert(out.ints.end(),{id1,b.nlev,id2,static_cast<std::int64_t>(masks[0]),static_cast<std::int64_t>(masks[1]),static_cast<std::int64_t>(masks[2]),ex_mode,kType99LayoutMagicZ1Z30V068213});
        }
        // v82 patch 5.20.5: xstarsetup builds errc before calc_emis using
        // leveltemp rlev(4,idest1)-rlev(1,idest1), independent of calt99's
        // later threshold/destination semantics.  Append it as internal payload.
        out.reals.push_back(source_errc_rank_energy);
        energy=threshold;
    }
    out.record.source_position=0; out.record.record=rec; out.record.next_index=-1; out.record.element_index=element_index;
    out.record.opcode=(dt==91?XSTAR_FIXED_OPCODE_TYPE50_RADIATIVE_LINE:(dt==52?XSTAR_FIXED_OPCODE_TYPE59_VERNER_BOUND_FREE:(kLegacyActiveTypes.count(dt)?dt:XSTAR_FIXED_OPCODE_SOURCE_UCALC_GENERIC))); out.record.data_type=dt; out.record.rate_type=rt; out.record.ion_index=b.ion_counter; out.record.ion_stage=stage;
    out.record.lower_row=lower; out.record.upper_row=upper; out.record.density_scale=1.0; out.record.line_energy_ev=energy;
    out.record.atomic_mass_amu=source_atomic_mass_for_ion(db,d,ion,b.element_z); out.record.natural_width_ev=width;
    out.record.line_index_one_based=d.nplini[rec]; out.record.continuum_index_one_based=d.npconi2[rec]; out.record.matrix_enabled=matrix?1u:0u;
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide symbol for z as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::string symbol_for_z(int z) {
    static const char* names[] = {"","h","he","li","be","b","c","n","o","f","ne","na","mg","al","si","p","s","cl","ar","k","ca","sc","ti","v","cr","mn","fe","co","ni","cu","zn"};
    return z>=1&&z<=30?names[z]:("z"+std::to_string(z));
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide normalized ion label as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::string normalized_ion_label(const Block& b) {
    auto value=trim(b.label); if(!value.empty())return value; return symbol_for_z(b.element_z)+"_"+std::to_string(b.ion_stage);
}

} // namespace

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide bundle as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
xstar_fixed_program_bundle_v1 ProgramStorage::bundle() const {
    xstar_fixed_program_bundle_v1 b{}; xstar_fixed_program_bundle_init_v1(&b);
    b.program_id=program_id.c_str(); b.active_atdb_lowered=1; b.topology_record_count=topology_record_count;
    b.unsupported_record_count=unsupported_record_count; b.native_line_count=native_line_count; b.native_continuum_count=native_continuum_count;
    b.elements=elements.data(); b.element_count=elements.size(); b.rows=rows.data(); b.row_count=rows.size();
    b.records=records.data(); b.record_count=records.size(); b.reals=reals.data(); b.real_count=reals.size(); b.ints=ints.data(); b.int_count=ints.size();
    b.lte_ions=lte_ion_topology.data(); b.lte_ion_count=lte_ion_topology.size();
    b.lte_levels=lte_levels.data(); b.lte_level_count=lte_levels.size();
    return b;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load production parameters into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
int source_lcdd_from_lcpres(int lcpres) {
    return lcpres <= 1 ? 1 - lcpres : lcpres;
}

double source_runtime_density_cm3(
    const ProductionParameters& parameters,
    double temperature_t4,
    double electron_fraction_xee) {
    const int lcdd = source_lcdd_from_lcpres(parameters.pressure_mode);
    if (lcdd == 0) {
        // calc_hmc_all.f90 / calc_emis*_all.f90 use the unsuffixed
        // default-REAL 1.38e-12 literal, promoted to REAL(8), and a REAL(8)
        // 1.d-24 temperature floor.
        const double coefficient = source_default_real_literal(1.38e-12);
        return parameters.pressure_dyn_cm2 / coefficient /
            std::max(temperature_t4, 1.0e-24);
    }
    if (lcdd == 2) {
        return parameters.pressure_dyn_cm2 /
            (electron_fraction_xee + source_default_real_literal(1.0e-34));
    }
    return parameters.input_density_cm3;
}

ProductionParameters read_production_parameters(const std::filesystem::path& path) {
    ProductionParameters p; p.source_path=path; p.raw_json=read_file(path);
    auto has_key = [&](const char* key) {
        const std::regex pattern("\\\"" + std::string(key) + "\\\"\\s*:");
        return std::regex_search(p.raw_json, pattern);
    };
    auto public_number = [&](const char* key, double fallback) {
        const std::regex pattern("\\\"" + std::string(key) + "\\\"\\s*:\\s*(?:\\\")?([-+0-9.eE]+)(?:\\\")?");
        std::smatch match;
        double value=fallback;
        if (std::regex_search(p.raw_json,match,pattern)) {
            try { value=std::stod(match[1].str()); }
            catch (...) { throw std::runtime_error(std::string(key)+" is not numeric"); }
        } else if (has_key(key)) {
            throw std::runtime_error(std::string(key)+" is not a valid numeric XSTAR parameter");
        }
        if (const auto* rule=xstar_parameter_contract::find(key)) xstar_parameter_contract::validate_numeric(*rule,value);
        return value;
    };
    auto public_string = [&](const char* key, const char* fallback) {
        const std::regex pattern("\\\"" + std::string(key) + "\\\"\\s*:\\s*\\\"([^\\\"]*)\\\"");
        std::smatch match;
        if (std::regex_search(p.raw_json,match,pattern)) return match[1].str();
        if (has_key(key)) throw std::runtime_error(std::string(key)+" is not a valid string XSTAR parameter");
        return std::string(fallback);
    };

    p.density_cm3=public_number("density",p.density_cm3);
    p.input_density_cm3=p.density_cm3;
    p.pressure_dyn_cm2=public_number("pressure",p.pressure_dyn_cm2);
    const double input_t4=public_number("temperature",400.0);
    p.temperature_k=json_number(p.raw_json,"temperature_k",input_t4*1.0e4);
    // Source uclgsr8 reads REAL input through REAL(4), then promotes it.
    p.column_cm2=static_cast<double>(static_cast<float>(public_number("column",p.column_cm2)));
    p.log_xi=public_number("rlogxi",p.log_xi);
    p.covering_fraction=public_number("cfrac",p.covering_fraction);
    p.emission_multiplier=public_number("emult",p.emission_multiplier);
    p.maximum_optical_depth=public_number("taumax",p.maximum_optical_depth);
    p.turbulent_velocity_km_s=public_number("vturbi",p.turbulent_velocity_km_s);
    p.minimum_electron_fraction=public_number("xeemin",p.minimum_electron_fraction);
    p.initial_electron_fraction=json_number(
        p.raw_json,"initial_electron_fraction",
        json_number(p.raw_json,"xee",p.initial_electron_fraction));
    p.luminosity_1e38=public_number("rlrad38",p.luminosity_1e38);
    p.spectral_index=public_number("trad",p.spectral_index);
    p.radial_density_exponent=public_number("radexp",p.radial_density_exponent);
    p.pressure_mode=static_cast<int>(public_number("lcpres",p.pressure_mode));
    if (source_lcdd_from_lcpres(p.pressure_mode) == 0) {
        // rread1 reads pressure/temperature through uclgsr8 (REAL(4) ->
        // REAL(8)), then uses the double-precision 1.38d-12 coefficient for
        // its initial trial density.  The per-evaluation coefficient differs
        // slightly and is handled by source_runtime_density_cm3().
        p.pressure_dyn_cm2=source_uclgsr8(p.raw_json,"pressure",p.pressure_dyn_cm2);
        const double source_t4=source_uclgsr8(p.raw_json,"temperature",input_t4);
        // Under lcdd=0 this same uclgsr8-promoted T4 is the live controller
        // input.  Keep the promotion local to constant pressure so frozen
        // constant-density trajectories are byte-for-byte unaffected.
        p.temperature_k=source_t4*1.0e4;
        p.density_cm3=p.pressure_dyn_cm2/1.38e-12/std::max(source_t4,1.0e-49);
    }
    p.spectrum_units=static_cast<int>(public_number("spectun",p.spectrum_units));
    p.spectrum_file=public_string("spectrum_file","spct.dat");
    p.input_dir=json_string(p.raw_json,"input_dir",".");
    p.critical_fraction=public_number("critf",p.critical_fraction);
    p.controller_charge_tolerance=json_number(p.raw_json,"standalone_charge_tolerance",0.0);
    p.controller_thermal_tolerance=json_number(p.raw_json,"standalone_thermal_tolerance",0.0);
    p.ncn2=static_cast<int>(public_number("ncn2",p.ncn2));
    p.nsteps=static_cast<int>(public_number("nsteps",p.nsteps));
    p.npass=static_cast<int>(public_number("npass",p.npass));
    p.requested_niter=static_cast<int>(public_number("niter",p.niter));
    // 0.6.82.24: preserve the literal FORTRAN nlimd contract.
    //   niter == 0 : xstarcalc skips dsec entirely; fixed input T and source xee.
    //   niter <  0 : dsec solves charge neutrality only (nlimt=0, nlimx=abs(nlim)).
    //   niter >  0 : dsec solves charge neutrality and thermal equilibrium.
    p.niter=p.requested_niter;
    p.lwrite=static_cast<int>(public_number("lwrite",0.0));
    p.lprint=static_cast<int>(public_number("lprint",0.0));
    p.lstep=static_cast<int>(public_number("lstep",0.0));
    p.loopcontrol=static_cast<int>(public_number("loopcontrol",0.0));
    p.model_name=public_string("modelname","XSTAR Default");
    p.abundance_table=public_string("abundtbl","xdef");
    p.mode=public_string("mode","ql");
    p.spectrum=public_string("spectrum","pow");
    p.initial_radius_cm=source_rread1_initial_radius_cm(p.raw_json);

    auto physical=json_number_array(p.raw_json,"physical_abundances");
    for(std::size_t i=0;i<physical.size()&&i<30;++i) if(physical[i]>0) p.abundances_by_z[static_cast<int>(i)+1]=physical[i];
    if(p.abundances_by_z.empty()) {
        static const std::array<const char*,30> keys={{"habund","heabund","liabund","beabund","babund","cabund","nabund","oabund","fabund","neabund","naabund","mgabund","alabund","siabund","pabund","sabund","clabund","arabund","kabund","caabund","scabund","tiabund","vabund","crabund","mnabund","feabund","coabund","niabund","cuabund","znabund"}};
        const auto& base = source_abundance_base(p.abundance_table);
        for(int z=1;z<=30;++z){
            const double source_default_multiplier = (z==3 || z==4 || z==5) ? 0.0 : 1.0;
            const double multiplier=public_number(keys[static_cast<std::size_t>(z-1)],source_default_multiplier);
            const double a=multiplier*base[static_cast<std::size_t>(z-1)];
            if(a>0)p.abundances_by_z[z]=a;
        }
    }
    if(p.abundances_by_z.empty()) throw std::runtime_error("parameters contain no positive physical abundances");
    return p;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute resolve atomic data as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
ResolvedAtomicData resolve_atomic_data(const std::filesystem::path& parameters_path,const std::string& json,const std::filesystem::path& executable_path) {
    ResolvedAtomicData r; const auto base=parameters_path.parent_path();
    auto add_json=[&](std::vector<std::filesystem::path>& out,const char* key){auto v=json_string(json,key,"");if(!v.empty()){std::filesystem::path p(v);append_candidate(out,p.is_relative()?base/p:p);}};
    add_json(r.atdb_candidates,"atomic_database"); add_json(r.atdb_candidates,"atomic_db"); add_json(r.atdb_candidates,"atdb"); append_candidate(r.atdb_candidates,base/"atdb.fits");
    if (const char* v = std::getenv("XSTAR_ATOMIC_DB")) append_candidate(r.atdb_candidates, v);
    if (const char* v = std::getenv("XSTAR_ATDB_FITS")) append_candidate(r.atdb_candidates, v);
    if (const char* v = std::getenv("XSTAR_DATA")) append_candidate(r.atdb_candidates, std::filesystem::path(v) / "atdb.fits");
    if (const char* v = std::getenv("XSTAR_HOME")) append_candidate(r.atdb_candidates, std::filesystem::path(v) / "data" / "atdb.fits");
    if(!executable_path.empty()){auto d=executable_path.parent_path();append_candidate(r.atdb_candidates,d/"../data/atdb.fits");append_candidate(r.atdb_candidates,d/"../../data/atdb.fits");}
    append_candidate(r.atdb_candidates,"src/xstar_tools/xstar/data/atdb.fits"); append_candidate(r.atdb_candidates,"atdb.fits"); r.atdb=first_file(r.atdb_candidates);
    add_json(r.coheat_candidates,"coheat_file"); add_json(r.coheat_candidates,"coheat"); append_candidate(r.coheat_candidates,base/"coheat.dat");
    if (const char* v = std::getenv("XSTAR_COHEAT")) append_candidate(r.coheat_candidates, v);
    if (const char* v = std::getenv("XSTAR_DATA")) append_candidate(r.coheat_candidates, std::filesystem::path(v) / "coheat.dat");
    if (const char* v = std::getenv("XSTAR_HOME")) append_candidate(r.coheat_candidates, std::filesystem::path(v) / "data" / "coheat.dat");
    if(!executable_path.empty()){auto d=executable_path.parent_path();append_candidate(r.coheat_candidates,d/"../data/coheat.dat");append_candidate(r.coheat_candidates,d/"../../data/coheat.dat");}
    append_candidate(r.coheat_candidates,"src/xstar_tools/xstar/data/coheat.dat"); append_candidate(r.coheat_candidates,"coheat.dat"); r.coheat=first_file(r.coheat_candidates); return r;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide lower atdb in memory as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
ProgramStorage lower_atdb_in_memory(const std::filesystem::path& atdb,const ProductionParameters& parameters) {
    AtdbReader db(atdb); Derived d=build_pointers(db); ProgramStorage out;
    out.program_id="v067_runtime_atdb_"+std::to_string(db.record_count()); out.topology_record_count=static_cast<std::uint64_t>(d.n_elements+d.n_ions+d.n_levels); out.native_line_count=d.n_lines; out.native_continuum_count=d.n_continua;
    std::unordered_map<int,int> ion_record_to_index;for(int i=1;i<=d.n_ions;++i)ion_record_to_index[d.ion_records[i]]=i;
    std::vector<int> active;for(const auto& kv:parameters.abundances_by_z)if(kv.second>0)active.push_back(kv.first);std::sort(active.begin(),active.end());
    std::unordered_set<int> active_set(active.begin(),active.end());
    std::map<int,std::vector<int>> records_by_z; std::set<int> unsupported;
    for(int ion=1;ion<=d.n_ions;++ion){int z=d.ion_element_z[ion];if(!active_set.count(z))continue;int parent=d.ion_records[ion];for(int rt=1;rt<=d.max_rate;++rt){int rec=d.npfi[rt][ion],guard=0;while(rec>0&&rec<static_cast<int>(d.npar.size())&&d.npar[rec]==parent){int dt=db.header(rec).data_type;if(kActiveTypes.count(dt))records_by_z[z].push_back(rec);else if(rt!=11&&rt!=12&&rt!=13)unsupported.insert(dt);int next=d.npnxt[rec];if(next==rec)throw std::runtime_error("ATDB record self-cycle");rec=next;if(++guard>static_cast<int>(db.record_count()))throw std::runtime_error("ATDB record cycle");}}}
    for(auto& kv:records_by_z){auto& v=kv.second;std::sort(v.begin(),v.end());v.erase(std::unique(v.begin(),v.end()),v.end());}
    out.unsupported_data_types.assign(unsupported.begin(),unsupported.end()); out.unsupported_record_count=unsupported.size();
    if(!unsupported.empty()){std::ostringstream s;s<<"unsupported active ATDB data types:";for(int dt:unsupported)s<<' '<<dt;throw std::runtime_error(s.str());}
    std::size_t global_record=0;int row_offset=0;
    for(std::size_t ei=0;ei<active.size();++ei){int z=active[ei];Layout l=build_layout(db,d,z,static_cast<int>(ei));auto rit=records_by_z.find(z);if(rit==records_by_z.end()||rit->second.empty())throw std::runtime_error("no executable records for active Z="+std::to_string(z));
        xstar_fixed_program_element_v1 e{};e.element_index=ei;e.element_z=z;e.abundance=parameters.abundances_by_z.at(z);e.n_rows=l.n_rows;e.n_superlevels=l.n_superlevels;e.n_ions=l.n_ions;e.normalization_row=l.normalization_row;e.record_head=global_record;e.record_count=rit->second.size();out.elements.push_back(e);
        xstar_run_state::ElementMetadataState em;em.element_index=ei;em.atomic_number=z;em.abundance=e.abundance;em.row_offset=row_offset;em.row_count=l.n_rows;em.ion_count=l.n_ions;out.element_metadata.push_back(em);
        for (const auto& block : l.blocks) {
            const auto* terminal = find_level(l, block.ion_index, block.nlev);
            if (!terminal || !(terminal->weight > 0.0)) {
                throw std::runtime_error("source LTE terminal Type-13 metadata missing");
            }
            xstar_fixed_lte_ion_topology_v1 topo{};
            topo.element_index = static_cast<int32_t>(ei);
            topo.ion_stage = block.ion_stage;
            topo.start_row = block.compact_start;
            topo.nlev = block.nlev;
            topo.terminal_energy_ev = terminal->energy;
            topo.terminal_statistical_weight = terminal->weight;
            out.lte_ion_topology.push_back(topo);

            // v82 patch 5.6: calc_rates_level_lte rebuilds leveltemp from every
            // Type-13 record in source order.  Preserve every local level here,
            // not only the terminal continuum metadata retained by patch 5.4.
            for (int local = 1; local <= block.nlev; ++local) {
                const auto* lv = find_level(l, block.ion_index, local);
                if (!lv || !(lv->weight > 0.0) || !std::isfinite(lv->energy)) {
                    throw std::runtime_error("complete source LTE Type-13 leveltemp metadata missing");
                }
                xstar_fixed_lte_level_v1 level{};
                level.element_index = static_cast<int32_t>(ei);
                level.ion_stage = block.ion_stage;
                level.local_level = local;
                level.source_record = lv->record;
                level.energy_ev = lv->energy;
                level.statistical_weight = lv->weight;
                out.lte_levels.push_back(level);
            }
        }
        for(int row=1;row<=l.n_rows;++row){const auto& r=l.rows[row];const auto& lv=row_level(l,row);const auto& b=block_for(l,r.ion_index);xstar_fixed_program_row_v1 pr{};pr.element_index=ei;pr.row=row;pr.superlevel=r.superlevel;pr.ion=r.ion_counter;pr.ion_charge=std::max(0,b.ion_stage-1);pr.initial_population=row==1?1.0:0.0;pr.energy_ev=lv.energy;pr.statistical_weight=lv.weight;pr.principal_n=lv.principal_n;pr.orbital_l=lv.orbital_l;int global=d.level_global_by_record[lv.record];
            // v0.6.48.12.3.20: XSTAR npilev is indexed by the Type-13
            // source encounter ordinal within an ion, not by the packed local
            // level identifier stored in the record.  This was historically
            // corrected only for Mg, but Ca XVIII demonstrates the same
            // source topology at its superlevel/K-shell boundary.  Apply the
            // literal setptrs npilev ordinal generically for every element;
            // this is native addressing, never an empirical row shift.
            if (r.local_level > 0 &&
                static_cast<std::size_t>(r.local_level) < d.npilev.size() &&
                r.ion_index > 0 &&
                static_cast<std::size_t>(r.ion_index) < d.npilev[static_cast<std::size_t>(r.local_level)].size()) {
                const int source_ordinal_global =
                    d.npilev[static_cast<std::size_t>(r.local_level)][static_cast<std::size_t>(r.ion_index)];
                if (source_ordinal_global > 0) global = source_ordinal_global;
            }
            pr.global_level_index=global;out.rows.push_back(pr);
            std::vector<std::int32_t> global_aliases;
            std::vector<std::uint8_t> terminal_aliases;
            for (const auto& role : l.role_to_row) {
                if (role.second != row) continue;
                const int role_ion = role.first.first;
                const int role_local = role.first.second;
                const auto* role_level = find_level(l, role_ion, role_local);
                if (!role_level) continue;
                int role_global = d.level_global_by_record[role_level->record];
                if (role_local > 0 &&
                    static_cast<std::size_t>(role_local) < d.npilev.size() &&
                    role_ion > 0 && static_cast<std::size_t>(role_ion) < d.npilev[static_cast<std::size_t>(role_local)].size()) {
                    const int source_ordinal_global =
                        d.npilev[static_cast<std::size_t>(role_local)][static_cast<std::size_t>(role_ion)];
                    if (source_ordinal_global > 0) role_global = source_ordinal_global;
                }
                if (role_global <= 0) continue;
                const auto& role_block = block_for(l, role_ion);
                const std::uint8_t terminal = role_local == role_block.nlev ? 1u : 0u;
                auto found = std::find(global_aliases.begin(), global_aliases.end(), role_global);
                if (found == global_aliases.end()) {
                    global_aliases.push_back(role_global);
                    terminal_aliases.push_back(terminal);
                } else if (terminal) {
                    terminal_aliases[static_cast<std::size_t>(found - global_aliases.begin())] = 1u;
                }
            }
            if (global > 0 && std::find(global_aliases.begin(), global_aliases.end(), global) == global_aliases.end()) {
                global_aliases.push_back(global);
                terminal_aliases.push_back(r.local_level == b.nlev ? 1u : 0u);
            }
            out.row_global_level_aliases.push_back(std::move(global_aliases));
            out.row_global_level_terminal_roles.push_back(std::move(terminal_aliases));
            xstar_run_state::CompactRowMetadataState rm;rm.element_index=ei;rm.row=row;rm.superlevel=r.superlevel;rm.ion=r.ion_counter;rm.ion_charge=pr.ion_charge;rm.energy_ev=lv.energy;rm.statistical_weight=lv.weight;rm.principal_n=lv.principal_n;rm.orbital_l=lv.orbital_l;rm.global_level_index=global;rm.ion_label=normalized_ion_label(b);rm.level_label=lv.label;out.row_metadata.push_back(rm);
            // fstepr public identity columns use the element atomic number in
            // ion_index and the source-local level ordinal in upper index.
            // These are publication metadata only; do not reuse the ion stage
            // or ion nlev as compatibility surrogates.
            xstar_run_state::LevelIdentityState id;id.global_index=global;id.ion_index=z;id.excitation_ev=lv.energy;id.ion_label=rm.ion_label;id.atomic_number=z;id.level_label=lv.label;id.upper_index=r.local_level; if(global>0)out.level_identities.push_back(id);
        }

        // v0.6.48.12.3.19: fstepr does not iterate the compact row basis.
        // It walks every source ion and every local npilev role.  Adjacent
        // ions share one compact continuum/next-ground row, so the compact
        // metadata above necessarily loses one of those two publication
        // identities.  Retain a dedicated source-role identity inventory for
        // xo01_detail.fits, using setptrs npilev addresses for every element.
        for (const auto& detail_block : l.blocks) {
            for (int local = 1; local <= detail_block.nlev; ++local) {
                const auto* detail_level = find_level(l, detail_block.ion_index, local);
                if (!detail_level) continue;
                int detail_global = d.level_global_by_record[detail_level->record];
                if (local > 0 && static_cast<std::size_t>(local) < d.npilev.size() &&
                    detail_block.ion_index > 0 &&
                    static_cast<std::size_t>(detail_block.ion_index) < d.npilev[static_cast<std::size_t>(local)].size()) {
                    const int source_global =
                        d.npilev[static_cast<std::size_t>(local)][static_cast<std::size_t>(detail_block.ion_index)];
                    if (source_global > 0) detail_global = source_global;
                }
                if (detail_global <= 0) continue;
                xstar_run_state::LevelIdentityState detail_id;
                detail_id.global_index = detail_global;
                detail_id.ion_index = z;
                detail_id.excitation_ev = detail_level->energy;
                detail_id.ion_label = normalized_ion_label(detail_block);
                detail_id.atomic_number = z;
                detail_id.level_label = detail_level->label;
                detail_id.upper_index = static_cast<std::int16_t>(local);
                out.detail_level_identities.push_back(std::move(detail_id));
            }
        }
        // 0.6.48.12.3.43.1.1.1: source RRC publication ownership follows
        // setptrs.f90's one-based continuum pointer table directly:
        //     npcon(jkkl) = ml
        // writespectra4 then publishes the rate-type-7 members of that table.
        // Do not reconstruct this surface through d.npfi: 43.1.1 showed that
        // the per-ion reconstruction can omit a source continuum identity
        // (Ca XIII continuum 23595) even though the canonical npcon ordinal
        // exists.  This scan is publication metadata only; it never inserts a
        // record into records_by_z and therefore cannot change rate/matrix
        // execution.
        for (std::size_t continuum_index = 1; continuum_index < d.npcon.size(); ++continuum_index) {
            const int rec = d.npcon[continuum_index];
            if (rec <= 0 || rec >= static_cast<int>(d.npar.size())) continue;
            const auto& h = db.header(rec);
            if (h.rate_type != 7) continue;
            const int parent = d.npar[static_cast<std::size_t>(rec)];
            const auto ion_it = ion_record_to_index.find(parent);
            if (ion_it == ion_record_to_index.end()) continue;
            const int source_ion = ion_it->second;
            if (source_ion <= 0 || source_ion > d.n_ions || d.ion_element_z[source_ion] != z) continue;
            const auto iv = db.ints(rec);
            const int local = iv.size() >= 2 ? static_cast<int>(iv[iv.size()-2]) : 1;
            const int upper_seed = iv.size() >= 4 ? static_cast<int>(iv[iv.size()-4]) : 0;
            const auto* lv = find_level(l, source_ion, local);
            const auto& source_block = block_for(l, source_ion);
            int source_global = 0;
            if (local > 0 && static_cast<std::size_t>(local) < d.npilev.size() &&
                static_cast<std::size_t>(source_ion) < d.npilev[static_cast<std::size_t>(local)].size()) {
                source_global = d.npilev[static_cast<std::size_t>(local)][static_cast<std::size_t>(source_ion)];
            }
            xstar_run_state::RrcIdentityState id;
            id.continuum_index = static_cast<int>(continuum_index);
            id.level_global_index = source_global > 0 ? source_global :
                (lv ? d.level_global_by_record[lv->record] : 0);
            const double source_threshold = lv ? (lv->ionpot - lv->energy) : 0.0;
            id.threshold_ev = std::isfinite(source_threshold) ? source_threshold : 0.0;
            id.ion_label = normalized_ion_label(source_block);
            id.lower_level = lv ? lv->label : "";
            id.upper_level = "continuum";
            id.lower_local_index = local;
            id.upper_local_index = upper_seed > 0 ? source_block.nlev + upper_seed - 1 : 0;
            id.rate_type = h.rate_type;
            id.source_record = rec;
            out.source_rrc_identities.push_back(std::move(id));
        }
        row_offset+=l.n_rows;
        for(std::size_t li=0;li<rit->second.size();++li){int rec=rit->second[li];auto lr=lower_record(db,d,l,rec,ei,ion_record_to_index);lr.record.source_position=4*static_cast<std::int64_t>(global_record+1);lr.record.next_index=(li+1<rit->second.size())?static_cast<int>(global_record+1):-1;lr.record.real_offset=out.reals.size();lr.record.real_count=lr.reals.size();lr.record.int_offset=out.ints.size();lr.record.int_count=lr.ints.size();out.reals.insert(out.reals.end(),lr.reals.begin(),lr.reals.end());out.ints.insert(out.ints.end(),lr.ints.begin(),lr.ints.end());out.records.push_back(lr.record);++global_record;
            const auto& h=db.header(rec);const int parent=d.npar[rec];const int ion=ion_record_to_index[parent];const auto& b=block_for(l,ion);auto iv=db.ints(rec);auto rv=db.reals(rec);
            if(d.nplini[rec]>0){xstar_run_state::LineIdentityState id;id.line_index=d.nplini[rec];id.wavelength_angstrom=!rv.empty()?std::abs(rv[0]):(lr.record.line_energy_ev>0?kEvAngstrom/lr.record.line_energy_ev:0.0);id.ion_label=normalized_ion_label(b);int a=iv.size()>=2?iv[0]:1,c=iv.size()>=2?iv[1]:b.nlev;const auto* la=find_level(l,ion,a);const auto* lc=find_level(l,ion,c);id.lower_level=la?la->label:"";id.upper_level=lc?lc->label:"";id.rate_type=h.rate_type;id.data_type=h.data_type;id.atomic_mass=source_atomic_mass_for_ion(db,d,ion,z);id.natural_rate_s=rv.size()>=3?rv[2]:0.0;const auto type86=binemis_type86_damping(db,d,ion,c);if(type86.matched){id.auger_rate_s=type86.auger_rate_s;id.natural_rate_s=type86.radiative_rate_s;}id.source_record=rec;id.lower_local_index=a;id.upper_local_index=c;out.line_identities.push_back(id);}
            if(d.npconi2[rec]>0){
                // Literal pprint.f90/writespectra4.f90 identity metadata is
                // distinct from the UCalc physical threshold used by the
                // bound-free kernel.  The public edge energy is
                //   rlev(4,idest1)-rlev(1,idest1),
                // while idest2 is nlevp + the fourth-to-last packed INTEGER
                // seed - 1.  Do not publish lr.record.line_energy_ev here:
                // Type-53 may include the excited-parent correction in that
                // kernel coordinate, and Type-49 carries its setup/rank
                // coordinate separately.
                xstar_run_state::RrcIdentityState id;
                id.continuum_index=d.npconi2[rec];
                const int local=iv.size()>=2?static_cast<int>(iv[iv.size()-2]):1;
                const int upper_seed=iv.size()>=4?static_cast<int>(iv[iv.size()-4]):0;
                const auto* lv=find_level(l,ion,local);
                // v82 patch 5.20.12: literal pprint/writespectra4 publishes
                // mmlv=npilev(idest1,jkk).  Packed Type-13 local identifiers
                // are not guaranteed to map to the same global source ordinal.
                int source_global = 0;
                if (local > 0 && static_cast<std::size_t>(local) < d.npilev.size() &&
                    ion > 0 && static_cast<std::size_t>(ion) < d.npilev[static_cast<std::size_t>(local)].size()) {
                    source_global = d.npilev[static_cast<std::size_t>(local)][static_cast<std::size_t>(ion)];
                }
                id.level_global_index=source_global>0?source_global:(lv?d.level_global_by_record[lv->record]:0);
                const double source_threshold=lv?(lv->ionpot-lv->energy):lr.record.line_energy_ev;
                id.threshold_ev=std::isfinite(source_threshold)?source_threshold:lr.record.line_energy_ev;
                id.ion_label=normalized_ion_label(b);
                id.lower_level=lv?lv->label:"";
                id.upper_level="continuum";
                id.lower_local_index=local;
                id.upper_local_index=upper_seed>0?b.nlev+upper_seed-1:0;
                id.rate_type=h.rate_type;
                id.source_record=rec;
                out.rrc_identities.push_back(id);
            }
        }
    }
    std::sort(out.level_identities.begin(),out.level_identities.end(),[](const auto&a,const auto&b){return a.global_index<b.global_index;});out.level_identities.erase(std::unique(out.level_identities.begin(),out.level_identities.end(),[](const auto&a,const auto&b){return a.global_index==b.global_index;}),out.level_identities.end());
    std::sort(out.detail_level_identities.begin(), out.detail_level_identities.end(), [](const auto& a, const auto& b) {
        if (a.global_index != b.global_index) return a.global_index < b.global_index;
        if (a.atomic_number != b.atomic_number) return a.atomic_number < b.atomic_number;
        if (a.ion_label != b.ion_label) return a.ion_label < b.ion_label;
        return a.upper_index < b.upper_index;
    });
    out.detail_level_identities.erase(
        std::unique(out.detail_level_identities.begin(), out.detail_level_identities.end(), [](const auto& a, const auto& b) {
            return a.global_index == b.global_index && a.atomic_number == b.atomic_number &&
                a.ion_label == b.ion_label && a.upper_index == b.upper_index;
        }),
        out.detail_level_identities.end());
    std::sort(out.line_identities.begin(),out.line_identities.end(),[](const auto&a,const auto&b){return a.line_index<b.line_index;});
    std::sort(out.rrc_identities.begin(),out.rrc_identities.end(),[](const auto&a,const auto&b){return a.continuum_index<b.continuum_index;});
    std::sort(out.source_rrc_identities.begin(),out.source_rrc_identities.end(),[](const auto&a,const auto&b){return a.continuum_index<b.continuum_index;});
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide format search candidates as part of the runtime atomic-database representation or source-compatible pointer/metadata lookup.
// Reference context: XSTAR Manual ch12; Bautista & Kallman (2001); Mendoza et al. (2021).
// XSTAR-FUNCTION-COMMENT-END
std::string format_search_candidates(const std::vector<std::filesystem::path>& candidates) { std::ostringstream out;for(std::size_t i=0;i<candidates.size();++i)out<<(i?";":"")<<candidates[i].string();return out.str(); }

} // namespace xstar_atdb_runtime
