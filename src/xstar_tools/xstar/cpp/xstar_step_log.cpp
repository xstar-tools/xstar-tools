// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: pprint.f90; nbinc.f90; huntf.f90
// Role: Native STEP/log publication including source-ranked lines, RRC/edge inventories, ion columns, and
//   controller summaries.
// Relation: Source-exact/source-equivalent print-option semantics where qualified; numerical science is
//   separated from identity/order/inventory diagnostics.
// Concordance: STEP-001; TERMINAL-001
// Qualification: comparator 12.3.34/36.1/41/42; Python rank parity 45.1/45.3.3.2
// XSTAR-SOURCE-CORRESPONDENCE-END

#include "xstar_step_log.hpp"
#include "xstar_constants.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <map>
#include <numeric>
#include <set>
#include <tuple>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <fitsio.h>

namespace xstar_step_log {
namespace {

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide true production mode for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool true_production_mode() {
    const char* value = std::getenv("XSTAR_TRUE_PRODUCTION");
    return value && std::string(value) == "1";
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute count lines for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
std::size_t count_lines(const std::filesystem::path& path) {
    std::ifstream input(path);
    std::size_t count = 0;
    std::string line;
    while (std::getline(input, line)) ++count;
    return count;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide human time for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string human_time(double seconds) {
    if (seconds < 0.0 || !std::isfinite(seconds)) seconds = 0.0;
    const long long whole = static_cast<long long>(seconds);
    const long long minutes = whole / 60;
    const double remainder = seconds - static_cast<double>(minutes * 60);
    std::ostringstream out;
    out << minutes << " min " << std::fixed << std::setprecision(3) << remainder << " sec";
    return out.str();
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Validate the invariants required by require legacy pprint payload; reject malformed dimensions, pointers, or state before scientific kernels are entered.
// Reference context: Implementation/safety helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
void require_legacy_pprint_payload(const xstar_run_state::ProductWritingState& state) {
    // v17.25.32: allow a native compact step log while scientific product
    // families are still being repaired.  Oracle/public payload absence is
    // still mandatory and remains the hard provenance gate.
    if (!state.embedded_public_fits_payloads_absent ||
        !state.embedded_full_xout_step_payload_absent) {
        throw std::runtime_error("native xout_step.log anti-copy provenance is incomplete");
    }
    const bool legacy_body_available = state.legacy_pprint.complete() && !state.legacy_pprint.buffered_lines.empty();
    const bool true_native_equivalent_available =
        state.legacy_pprint.initialized_from_native_controller &&
        state.legacy_pprint.finalized_from_native_controller &&
        state.legacy_pprint.buffered_lines.empty();
    if (!(legacy_body_available || true_native_equivalent_available)) {
        throw std::runtime_error(
            "xout_step.log requires retained legacy/full xout_step body or a validated true native equivalent; "
            "scratch ProductWritingState log body is disabled");
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load atomic data version into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::string read_atomic_data_version(const std::filesystem::path& atdb) {
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
    if (read_status != 0) return "unknown";
    return std::string(value);
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide parameter numeric value for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double parameter_numeric_value(const xstar_run_state::ParameterRowState& row) {
    float value = 0.0f;
    static_assert(sizeof(value) == sizeof(row.value_bits), "parameter bits size mismatch");
    std::uint32_t bits = row.value_bits;
    std::memcpy(&value, &bits, sizeof(value));
    return static_cast<double>(value);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide parameter row for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
const xstar_run_state::ParameterRowState* parameter_row(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name) {
    for (const auto& row : state.parameter_rows) if (row.parameter == name) return &row;
    return nullptr;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide parameter number for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double parameter_number(const xstar_run_state::ProductWritingState& state,
                        const std::string& name,
                        double fallback = 0.0) {
    const auto* row = parameter_row(state, name);
    return row ? parameter_numeric_value(*row) : fallback;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide parameter text for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string parameter_text(const xstar_run_state::ProductWritingState& state,
                           const std::string& name,
                           const std::string& fallback = "") {
    const auto* row = parameter_row(state, name);
    return row && !row->comment.empty() ? row->comment : fallback;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide e3 for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string e3(double value) {
    std::ostringstream out;
    out << std::uppercase << std::scientific << std::setprecision(3)
        << (std::isfinite(value) ? value : 0.0);
    return out.str();
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Append native input parameters from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void append_native_input_parameters(std::ofstream& out,
                                    const xstar_run_state::ProductWritingState& state) {
    out << " print option: 3\n \n print option: 2\n input parameters:\n";
    out << "covering fraction=      " << e3(parameter_number(state, "cfrac", 1.0)) << "\n";
    out << "temperature (/10**4K)=  " << e3(parameter_number(state, "temperature", 0.0)) << "\n";
    out << " constant pressure switch (1=yes, 0=no)= "
        << static_cast<long long>(std::llround(parameter_number(state, "lcpres", 0.0))) << "\n";
    out << "pressure (dyne/cm**2)=  " << e3(parameter_number(state, "pressure", 0.0)) << "\n";
    out << "density (cm**-3)=       " << e3(parameter_number(state, "density", 0.0)) << "\n";
    out << " spectrum type=" << parameter_text(state, "spectrum", "unavailable") << "\n";
    out << " spectrum file=" << parameter_text(state, "spectrum_file", "unavailable") << "\n";
    out << " spectrum units? (0=energy, 1=photons) "
        << static_cast<long long>(std::llround(parameter_number(state, "spectun", 0.0))) << "\n";
    out << "radiation temperature or alpha= " << e3(parameter_number(state, "trad", 0.0)) << "\n";
    out << "luminosity (/10**38 erg/s)=  " << e3(parameter_number(state, "rlrad38", 0.0)) << "\n";
    out << "column density (cm**-2)=  " << e3(parameter_number(state, "column", 0.0)) << "\n";
    out << "log(ionization parameter)=  " << e3(parameter_number(state, "rlogxi", 0.0)) << "\n";
    const double density = parameter_number(state, "density", 0.0);
    const double logxi = parameter_number(state, "rlogxi", 0.0);
    out << "flux=                   " << e3(density > 0.0 ? density * std::pow(10.0, logxi) / 12.56 : 0.0) << "\n";
    out << " abundance table: " << parameter_text(state, "abundtbl", "unavailable") << "\n";
    out << " abundances:\n";
    out << " element,   rel.to cosmic,     rel. to H,     H=12\n";
    struct AbundancePrintRow { const char* symbol; const char* parameter; int atomic_number; };
    // v0.6.48.12.3.2: never hard-code xdef (or any other abundance-table)
    // values in the step-log writer.  The input parameter is the source
    // abundance multiplier relative to the selected cosmic table, while the
    // already-lowered element metadata carries the resulting abundance
    // relative to H after applying abundtbl + <element>abund.  This makes
    // print option 2 follow the actual run input for every supported table.
    const AbundancePrintRow abundance_rows[] = {
        {"H","habund",1},{"He","heabund",2},{"Li","liabund",3},{"Be","beabund",4},{"B","babund",5},
        {"C","cabund",6},{"N","nabund",7},{"O","oabund",8},{"F","fabund",9},{"Ne","neabund",10},
        {"Na","naabund",11},{"Mg","mgabund",12},{"Al","alabund",13},{"Si","siabund",14},{"P","pabund",15},
        {"S","sabund",16},{"Cl","clabund",17},{"Ar","arabund",18},{"K","kabund",19},{"Ca","caabund",20},
        {"Sc","scabund",21},{"Ti","tiabund",22},{"V","vabund",23},{"Cr","crabund",24},{"Mn","mnabund",25},
        {"Fe","feabund",26},{"Co","coabund",27},{"Ni","niabund",28},{"Cu","cuabund",29},{"Zn","znabund",30}
    };
    const auto abundance_to_h = [&](int atomic_number) {
        for (const auto& element : state.element_metadata) {
            if (element.atomic_number == atomic_number) {
                return std::isfinite(element.abundance) ? element.abundance : 0.0;
            }
        }
        return 0.0;
    };
    for (const auto& item : abundance_rows) {
        const double relative_cosmic = parameter_number(state, item.parameter, 0.0);
        const double relative_h = abundance_to_h(item.atomic_number);
        const double h12 = relative_h > 0.0 ? 12.0 + std::log10(relative_h) : 0.0;
        out << " " << std::left << std::setw(8) << item.symbol << std::right
            << e3(relative_cosmic) << "  " << e3(relative_h) << "  " << e3(h12) << "\n";
    }
    out << " model name=" << parameter_text(state, "modelname", "unavailable") << "\n";
    out << " number of steps= " << static_cast<long long>(std::llround(parameter_number(state, "nsteps", 0.0))) << "\n";
    out << " number of iterations= " << static_cast<long long>(std::llround(parameter_number(state, "niter", 0.0))) << "\n";
    out << " write switch (1=yes, 0=no)= " << static_cast<long long>(std::llround(parameter_number(state, "lwrite", 0.0))) << "\n";
    out << " print switch (1=yes, 0=no)= " << static_cast<long long>(std::llround(parameter_number(state, "lprint", 0.0))) << "\n";
    out << " step size choice switch= " << static_cast<long long>(std::llround(parameter_number(state, "lstep", 0.0))) << "\n";
    out << " loop control (0=standalone)= " << static_cast<long long>(std::llround(parameter_number(state, "loopcontrol", 0.0))) << "\n";
    out << " number of passes= " << static_cast<long long>(std::llround(parameter_number(state, "npass", 0.0))) << "\n";
    out << " emult=  " << e3(parameter_number(state, "emult", 0.0)) << "\n";
    out << " taumax=  " << e3(parameter_number(state, "taumax", 0.0)) << "\n";
    out << " xeemin=  " << e3(parameter_number(state, "xeemin", 0.0)) << "\n";
    out << " critf=  " << e3(parameter_number(state, "critf", 0.0)) << "\n";
    out << " vturbi=  " << e3(parameter_number(state, "vturbi", 0.0)) << "\n";
    out << " ncn2= " << static_cast<long long>(std::llround(parameter_number(state, "ncn2", 9999.0))) << "\n";
    out << " radexp=  " << e3(0.0) << "\n\n";
}

bool read_spectrum_column(const std::filesystem::path& path,
                          const char* extname,
                          const char* energy_name,
                          const std::vector<const char*>& value_names,
                          std::vector<double>& energy,
                          std::vector<std::vector<double>>& values);

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide finite nonzero vector for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool finite_nonzero_vector(const std::vector<double>& values) {
    return std::any_of(values.begin(), values.end(), [](double value) {
        return std::isfinite(value) && std::abs(value) > 1.0e-300;
    });
}


// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide source pprint nry zero based for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::size_t source_pprint_nry_zero_based(
    double x,
    const std::vector<double>& energy) {
    // Literal nbinc.f90 -> huntf.f90 semantics used throughout pprint.
    // When pprint forms nry=nbinc(E,epi,ncn2)+1, converting that Fortran
    // one-based nry to a C++ zero-based index yields the numeric nbinc value.
    const std::size_t n = energy.size();
    if (n == 0u) return 0u;
    const std::size_t numcon2 = std::max<std::size_t>(2u, n / 50u);
    const std::size_t nn = n > numcon2 ? n - numcon2 : 1u;
    if (nn < 2u) return 0u;
    constexpr double floor = 1.0e-36;
    const double xx1 = energy[0];
    const double xx2 = energy[1];
    const double xxn = energy[nn - 1u];
    std::size_t jlo_one_based = 1u;
    if (x >= floor && xx1 > floor && xxn > floor) {
        const double xtmp = std::max(x, xx2);
        const double denom = std::log(xxn / xx1);
        if (std::isfinite(denom) && denom != 0.0) {
            const double raw = static_cast<double>(nn - 1u) *
                std::log(xtmp / xx1) / denom;
            if (std::isfinite(raw)) {
                const long long base = static_cast<long long>(raw);
                jlo_one_based = static_cast<std::size_t>(std::max<long long>(1ll, base + 1ll));
            }
        }
        if (jlo_one_based < nn) {
            const std::size_t a = jlo_one_based - 1u;
            const std::size_t b = jlo_one_based;
            const double tst = std::abs(std::log(x / (floor + energy[a])));
            const double tst2 = std::abs(std::log(x / (floor + energy[b])));
            if (tst2 < tst) ++jlo_one_based;
        }
    }
    jlo_one_based = std::max<std::size_t>(1u, std::min(nn, jlo_one_based));
    return std::min(n - 1u, jlo_one_based);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide source option17 reference bin zero based for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::size_t source_option17_reference_bin_zero_based(
    const std::vector<double>& energy) {
    // pprint option 9/17: nry=nbinc(13.6,epi,ncn2)+1.
    return source_pprint_nry_zero_based(13.6, energy);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide source option17 radiation balance percent for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool source_option17_radiation_balance_percent(
    const xstar_run_state::FixedEvaluationState& evaluation,
    double& percent) {
    const auto& energy = evaluation.radiation_energy_ev;
    const auto& ws = evaluation.source_workspace;
    const std::size_t n = energy.size();
    if (n < 2u || ws.zrems.size() < n) return false;
    const auto& incident = ws.zremsz.size() >= n ? ws.zremsz : evaluation.radiation_flux;
    if (incident.size() < n) return false;
    double sum_in = 0.0;
    double sum_out = 0.0;
    double in_previous = std::isfinite(incident[0]) ? incident[0] : 0.0;
    double out_previous = std::isfinite(ws.zrems[0]) ? ws.zrems[0] : 0.0;
    for (std::size_t i = 1u; i < n; ++i) {
        const double in_current = std::isfinite(incident[i]) ? incident[i] : 0.0;
        const double out_current = std::isfinite(ws.zrems[i]) ? ws.zrems[i] : 0.0;
        const double de = energy[i] - energy[i - 1u];
        if (std::isfinite(de)) {
            // ergsev cancels from the source terr ratio, so retaining it would
            // only multiply numerator and denominator by the same constant.
            sum_in += 0.5 * (in_current + in_previous) * de;
            sum_out += 0.5 * (out_current + out_previous) * de;
        }
        in_previous = in_current;
        out_previous = out_current;
    }
    const double denom = sum_in + 1.0e-24;
    if (!std::isfinite(sum_in) || !std::isfinite(sum_out) || denom == 0.0) return false;
    percent = 100.0 * (sum_in - sum_out) / denom;
    return std::isfinite(percent);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Append native radial summary from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void append_native_radial_summary(std::ofstream& out,
                                  const std::filesystem::path& output_dir,
                                  const xstar_run_state::ProductWritingState& state) {
    struct Row { double radius=0, dr=0, column=0, logxi=0, xee=0, density=0, temperature=0, heat_error=0; };
    std::vector<Row> rows;
    fitsfile* af = nullptr;
    int status = 0;
    const auto abundance_path = output_dir / "xout_abund1.fits";
    fits_open_file(&af, abundance_path.c_str(), READONLY, &status);
    if (status == 0) {
        status = 0;
        fits_movnam_hdu(af, ANY_HDU, const_cast<char*>("ABUNDANCES"), 0, &status);
        if (status == 0) {
            auto col = [&](const char* name) { int c=0, st=0; fits_get_colnum(af, CASEINSEN, const_cast<char*>(name), &c, &st); return st==0?c:0; };
            const int cr=col("radius"), cd=col("delta_r"), cx=col("ion_parameter"), ce=col("x_e"), cn=col("n_p"), ct=col("temperature"), ch=col("frac_heat_error");
            long long nr=0; fits_get_num_rowsll(af,&nr,&status);
            for (long long i=1; status==0 && i<=nr; ++i) {
                Row r; int any=0, st=0;
                auto rd=[&](int c){ double v=0; if(c>0) fits_read_col(af,TDOUBLE,c,i,1,1,nullptr,&v,&any,&st); return st==0?v:0.0; };
                r.radius=rd(cr); r.dr=rd(cd); r.logxi=rd(cx); r.xee=rd(ce); r.density=rd(cn); r.temperature=rd(ct); r.heat_error=rd(ch);
                r.column=r.density*r.dr;
                if (r.radius>0.0 || r.density>0.0) rows.push_back(r);
            }
        }
        int cs=0; fits_close_file(af,&cs);
    }
    if (rows.empty()) {
        for (const auto& r : state.abundance_radial_rows) {
            if (r.radius_cm<=0.0 && r.density_cm3<=0.0) continue;
            rows.push_back({r.radius_cm,r.delta_radius_cm,r.density_cm3 * r.delta_radius_cm,r.log_ionization_parameter,r.electron_fraction,r.density_cm3,r.temperature_t4,r.fractional_heat_error});
        }
    }
    // v0.6.48.12.3.12: native pprint must consume the controller-owned radial
    // state, not the projected xout_abund1 table.  The historical 5-row/4-row
    // reconstruction below was useful for old bridge products, but on generic
    // standalone runs it couples a pre-transport radius to a terminal rdel and
    // preserves the input rlogxi in the FITS row.  FORTRAN/Python pprint(9)
    // recompute zeta from live r, xpx and xlum for every row.  Recreate that
    // literal source surface directly from RadialZoneState here.
    const bool native_general_rows =
        state.backend == "cpp-general-standalone" && !state.radial_zones.empty();
    if (native_general_rows) {
        rows.clear();
        const std::size_t physical_rows = state.physical_radial_boundaries_retained > 0u
            ? std::min(state.physical_radial_boundaries_retained, state.radial_zones.size())
            : (state.terminal_synthetic_row_present && !state.radial_zones.empty()
                ? state.radial_zones.size() - 1u : state.radial_zones.size());
        rows.reserve(physical_rows);
        const double xlum = parameter_number(state, "rlrad38", 0.0);
        const double source_radius_scale = static_cast<double>(static_cast<float>(1.0e-19));
        for (std::size_t zi = 0; zi < physical_rows; ++zi) {
            const auto& zone = state.radial_zones[zi];
            double logxi = zone.log_ionization_parameter;
            const double r19 = zone.radius_cm * source_radius_scale;
            // pprint.f90 option 9 recomputes zeta from the live radius and
            // density on every invocation, including the post-loop terminal
            // row.  Do not preserve the pre-geometry scalar here.
            if (xlum > 0.0 && zone.density_cm3 > 0.0 && r19 > 0.0) {
                const double skse = xlum / (zone.density_cm3 * r19 * r19);
                logxi = std::log10(std::max(1.0e-24, skse));
            }
            rows.push_back({zone.radius_cm, zone.delta_radius_cm,
                zone.column_density_cm2, logxi, zone.electron_fraction,
                zone.density_cm3, zone.temperature_t4,
                zone.accepted_controller.evaluation.hmctot});
        }
    } else if (!state.diagnostic_preview_partial && state.radial_zones.size() == 5u &&
        rows.size() == 4u && rows[2].dr > 0.0 && rows[3].dr > rows[2].dr) {
        const Row entry0 = rows[0];
        const Row entry1 = rows[1];
        Row shell1 = rows[2];
        Row shell2 = rows[3]; shell2.dr = 2.0 * rows[2].dr;
        Row shell3 = rows[3];
        rows = {entry0, entry1, shell1, shell2, shell3};
    } else if (!state.radial_zones.empty() && rows.size() != state.radial_zones.size()) {
        rows.clear();
        rows.reserve(state.radial_zones.size());
        for (const auto& zone : state.radial_zones) {
            rows.push_back({zone.radius_cm, zone.delta_radius_cm,
                zone.column_density_cm2, zone.log_ionization_parameter, zone.electron_fraction,
                zone.density_cm3, zone.temperature_t4,
                zone.accepted_controller.evaluation.hmctot});
        }
    }
    // pprint option 17 prints the controller-owned hmctot directly.  Keep the
    // FITS abundance table only as the geometry source; thermal balance comes
    // from the retained accepted boundary state.
    if (!state.radial_zones.empty()) {
        const std::size_t terminal_physical =
            state.terminal_synthetic_row_present && state.radial_zones.size() >= 2u
                ? state.radial_zones.size() - 2u
                : state.radial_zones.size() - 1u;
        for (std::size_t i = 0; i < rows.size(); ++i) {
            const std::size_t source_index = std::min(i, terminal_physical);
            const double hmctot = state.radial_zones[source_index].accepted_controller.evaluation.hmctot;
            if (std::isfinite(hmctot)) rows[i].heat_error = hmctot;
        }
    }
    std::vector<std::pair<double,double>> depth_logs;
    std::vector<std::pair<double,double>> reference_depths;
    std::vector<double> heat_balance_percent;
    std::vector<double> current_radiation_integrals;
    std::vector<double> source_energy;
    std::vector<double> source_flux;
    std::vector<std::vector<double>> public_spectrum_values;
    if (read_spectrum_column(output_dir / "xout_spect1.fits", "XSTAR_SPECTRA", "energy",
                             {"incident"}, source_energy, public_spectrum_values) &&
        !public_spectrum_values.empty() && finite_nonzero_vector(public_spectrum_values.front())) {
        source_flux = public_spectrum_values.front();
    } else {
        source_energy.clear();
        source_flux.clear();
    }
    fitsfile* df=nullptr; status=0;
    const auto detail_path=output_dir/"xo01_detal4.fits";
    fits_open_file(&df,detail_path.c_str(),READONLY,&status);
    if(status==0){
        int nh=0; fits_get_num_hdus(df,&nh,&status);
        double fallback_source_integral=0.0;
        for(int h=2;status==0&&h<=nh;++h){
            int type=0; fits_movabs_hdu(df,h,&type,&status); if(status!=0) break;
            char ext[FLEN_VALUE]{}; int st=0; fits_read_key(df,TSTRING,const_cast<char*>("EXTNAME"),ext,nullptr,&st);
            if(st!=0 || std::string(ext)!="XSTAR_RADIAL") continue;
            int cf=0,cb=0,ce=0,cz=0;
            st=0; fits_get_colnum(df,CASEINSEN,const_cast<char*>("fwd dpth"),&cf,&st); if(st!=0) cf=0;
            st=0; fits_get_colnum(df,CASEINSEN,const_cast<char*>("bck dpth"),&cb,&st); if(st!=0) cb=0;
            st=0; fits_get_colnum(df,CASEINSEN,const_cast<char*>("energy"),&ce,&st); if(st!=0) ce=0;
            st=0; fits_get_colnum(df,CASEINSEN,const_cast<char*>("zrems(1)"),&cz,&st); if(st!=0) cz=0;
            long long nr=0; st=0; fits_get_num_rowsll(df,&nr,&st);
            double integral=0.0,prev_e=0.0,prev_z=0.0;
            std::vector<double> local_e,local_z,local_fwd,local_bck;
            local_e.reserve(static_cast<std::size_t>(nr)); local_z.reserve(static_cast<std::size_t>(nr));
            local_fwd.reserve(static_cast<std::size_t>(nr)); local_bck.reserve(static_cast<std::size_t>(nr));
            for(long long rr=1;st==0&&rr<=nr;++rr){
                int any=0;
                double fwd=0.0,bck=0.0;
                if(cf){fits_read_col(df,TDOUBLE,cf,rr,1,1,nullptr,&fwd,&any,&st);if(!std::isfinite(fwd))fwd=0.0;}
                if(cb){fits_read_col(df,TDOUBLE,cb,rr,1,1,nullptr,&bck,&any,&st);if(!std::isfinite(bck))bck=0.0;}
                double ev=0,zv=0;
                if(ce) fits_read_col(df,TDOUBLE,ce,rr,1,1,nullptr,&ev,&any,&st);
                if(cz) fits_read_col(df,TDOUBLE,cz,rr,1,1,nullptr,&zv,&any,&st);
                local_e.push_back(ev); local_z.push_back(zv);
                local_fwd.push_back(std::max(0.0,fwd)); local_bck.push_back(std::max(0.0,bck));
                if(rr>1) integral += 0.5*(prev_z+zv)*(ev-prev_e);
                prev_e=ev; prev_z=zv;
            }
            if (source_energy.empty()) {
                source_energy = local_e;
                source_flux = local_z;
                fallback_source_integral = integral;
            }
            current_radiation_integrals.push_back(integral);
            // pprint uses nry=nbinc(13.6,epi,ncn2)+1, not the maximum
            // optical depth over the grid.  For the retained grid this is the
            // second bin above 13.6 eV (13.628082 eV).
            std::size_t reference_bin=0;
            if(!local_e.empty()) {
                const auto it=std::upper_bound(local_e.begin(),local_e.end(),13.6);
                reference_bin=static_cast<std::size_t>(it-local_e.begin());
                if(reference_bin+1<local_e.size()) ++reference_bin;
                if(reference_bin>=local_e.size()) reference_bin=local_e.size()-1;
            }
            const double reference_fwd=reference_bin<local_fwd.size()?local_fwd[reference_bin]:0.0;
            const double reference_bck=reference_bin<local_bck.size()?local_bck[reference_bin]:0.0;
            depth_logs.push_back({std::log10(std::max(reference_fwd, 1.0e-10)),
                                  std::log10(std::max(reference_bck, 1.0e-10))});
            reference_depths.push_back({reference_fwd,reference_bck});
        }
        int cs=0;fits_close_file(df,&cs);
        double source_integral = 0.0;
        if (source_energy.size() == source_flux.size() && source_energy.size() > 1 &&
            finite_nonzero_vector(source_flux)) {
            for (std::size_t i = 1; i < source_energy.size(); ++i) {
                source_integral += 0.5 * (source_flux[i - 1] + source_flux[i]) *
                    (source_energy[i] - source_energy[i - 1]);
            }
        }
        if (!(source_integral > 0.0)) source_integral = fallback_source_integral;
        heat_balance_percent.reserve(current_radiation_integrals.size());
        for (double current_integral : current_radiation_integrals) {
            heat_balance_percent.push_back(source_integral > 0.0
                ? 100.0 * (source_integral - current_integral) / source_integral : 0.0);
        }
    }
    // patch 5.20.14.5: option 17 is a pprint surface and therefore reads
    // dpthc directly from each retained HEATT-before-STPCUT boundary.  Do not
    // route it through xo01_detal4, whose FITS projection has its own product
    // lifetime and can hide a one-zone offset.  The fifth row is the genuine
    // terminal post-STPCUT boundary.
    std::vector<std::pair<double,double>> retained_depth_logs;
    std::vector<std::pair<double,double>> retained_reference_depths;
    retained_depth_logs.reserve(state.radial_zones.size());
    retained_reference_depths.reserve(state.radial_zones.size());
    bool retained_depth_complete = !state.radial_zones.empty();
    for (const auto& zone : state.radial_zones) {
        const auto& eval = zone.accepted_controller.evaluation;
        const auto& energy = eval.radiation_energy_ev;
        const auto& dpthc = eval.source_workspace.dpthc;
        const std::size_t n = energy.size();
        if (n < 2u || dpthc.size() < 2u * n) {
            retained_depth_complete = false;
            break;
        }
        const std::size_t reference_bin = source_option17_reference_bin_zero_based(energy);
        const double fwd = std::max(0.0, dpthc[reference_bin]);
        const double rev = std::max(0.0, dpthc[n + reference_bin]);
        retained_depth_logs.push_back({std::log10(std::max(fwd, 1.0e-10)),
                                       std::log10(std::max(rev, 1.0e-10))});
        retained_reference_depths.push_back({fwd, rev});
    }
    if (retained_depth_complete && retained_depth_logs.size() >= rows.size()) {
        depth_logs = retained_depth_logs;
        reference_depths = retained_reference_depths;
    }

    // Prefer the literal pprint option-17 source surfaces retained at each
    // accepted boundary: terr = integral(zremsz-zrems(1))/integral(zremsz).
    // This avoids feeding xout_step through already-projected FITS planes.
    std::vector<double> retained_heat_balance_percent;
    retained_heat_balance_percent.reserve(rows.size());
    bool retained_heat_balance_complete = !state.radial_zones.empty();
    if (retained_heat_balance_complete) {
        const std::size_t terminal_physical =
            state.terminal_synthetic_row_present && state.radial_zones.size() >= 2u
                ? state.radial_zones.size() - 2u
                : state.radial_zones.size() - 1u;
        for (std::size_t i = 0; i < rows.size(); ++i) {
            const std::size_t source_index = std::min(i, terminal_physical);
            double percent = 0.0;
            if (!source_option17_radiation_balance_percent(
                    state.radial_zones[source_index].accepted_controller.evaluation, percent)) {
                retained_heat_balance_complete = false;
                break;
            }
            retained_heat_balance_percent.push_back(percent);
        }
    }
    if (retained_heat_balance_complete && !retained_heat_balance_percent.empty()) {
        heat_balance_percent.swap(retained_heat_balance_percent);
    }
    // 0.6.82.5: Option-17 ntotit comes from the thermal engine and is
    // retained on RadialZoneState. Do not infer it from evaluation_index.

    // xstar.f90 calls ispcg2 immediately after "running ...".  Reconstruct
    // its source-grid photon-band and bolometric diagnostics from the retained
    // incident spectrum.  Endpoint gating intentionally follows ispcg2.f90.
    double ispcg2_enlum = 0.0;
    double ispcg2_u_1_1p8 = 0.0;
    double ispcg2_u_1p8_4 = 0.0;
    double ispcg2_lbol_sum = 0.0;
    if (source_energy.size() == source_flux.size() && source_energy.size() > 1u) {
        for (std::size_t i = 1u; i < source_energy.size(); ++i) {
            const double e0 = source_energy[i - 1u];
            const double e1 = source_energy[i];
            const double z0 = source_flux[i - 1u];
            const double z1 = source_flux[i];
            const double de = e1 - e0;
            ispcg2_lbol_sum += 0.5 * (z1 + z0) * de;
            if (e1 >= 13.6 && e0 > 0.0 && e1 > 0.0) {
                const double term = 0.5 * (z1 / e1 + z0 / e0) * de;
                ispcg2_enlum += term;
                if (e1 <= 24.48) ispcg2_u_1_1p8 += term;
            }
            if (e1 >= 24.48 && e1 <= 54.4 && e0 > 0.0 && e1 > 0.0) {
                ispcg2_u_1p8_4 += 0.5 * (z1 / e1 + z0 / e0) * de;
            }
        }
    }
    const double ispcg2_lbol = ispcg2_lbol_sum * static_cast<double>(static_cast<float>(1.602197e-12));

    out << "\n running ...\n";
    const auto print_ispcg2_v0682273 = [&](std::size_t pass_index) {
        double u1_v0682273 = ispcg2_u_1_1p8;
        double u2_v0682273 = ispcg2_u_1p8_4;
        double lbol_v0682273 = ispcg2_lbol;
        for (const auto& saved_v0682273 : state.legacy_pprint.ispcg2_passes) {
            if (saved_v0682273.pass_index != pass_index) continue;
            u1_v0682273 = saved_v0682273.u_1_1p8;
            u2_v0682273 = saved_v0682273.u_1p8_4;
            lbol_v0682273 = saved_v0682273.lbol;
            break;
        }
        const auto flags_v0682273 = out.flags();
        const auto precision_v0682273 = out.precision();
        out << std::defaultfloat << std::setprecision(17)
            << " U(1-1.8),U(1.8-4):   " << u1_v0682273
            << "        " << u2_v0682273 << "\n";
        // Match the source's 1P-style scientific presentation consistently
        // on every pass instead of inheriting stream state from prior output.
        out << " Lbol=   " << std::scientific << std::setprecision(16)
            << lbol_v0682273 << "\n";
        out.flags(flags_v0682273);
        out.precision(precision_v0682273);
    };
    if (state.diagnostic_preview_partial) {
        out << " diagnostic partial radial trajectory: physical boundaries retained="
            << state.physical_radial_boundaries_retained
            << " expected=" << state.physical_radial_boundaries_expected
            << " transport intervals completed=" << state.physical_transport_intervals_completed
            << " terminal synthetic row="
            << (state.terminal_synthetic_row_present ? "reached" : "not reached") << "\n";
    }
    auto safe_log=[](double v,double floor){return v>0.0?std::log10(v):floor;};
    const auto print_option17_heading = [&]() {
        out << " print option:17\n";
        out << "   log(r) delr/r log(N) log(xi) x_e   log(n) log(t) h-c(%) h-c(%) log(tau)\n";
        out << "                                                                  fwd    rev\n";
    };
    const std::size_t requested_passes = static_cast<std::size_t>(std::max<long long>(
        1ll, static_cast<long long>(std::llround(parameter_number(state,"npass",1.0)))));
    const bool exact_multipass_pprint_v068227 = requested_passes > 1u &&
        state.legacy_pprint.radial_pass_trajectory_exact &&
        !state.legacy_pprint.radial_rows.empty();
    if (exact_multipass_pprint_v068227) {
        // 0.6.82.27: xstar.f90 calls pprint(17) once per pass and pprint(9)
        // for every shell plus the post-loop endpoint.  Old passes are kept as
        // compact source surfaces in LegacyPprintState rather than as full
        // FixedEvaluationState copies.
        for (std::size_t pass = 1u; pass <= requested_passes; ++pass) {
            const int direction = (pass % 2u == 1u) ? -1 : 1;
            // xstar.f90 calls ispec*/ispcg2 at the start of every pass, before
            // pprint(17).  Preserve the repeated U/Lbol block in xout_step.log.
            print_ispcg2_v0682273(pass);
            out << "\n pass number= " << pass << ' ' << direction << "\n";
            print_option17_heading();
            for (const auto& r : state.legacy_pprint.radial_rows) {
                if (r.pass_index != pass) continue;
                const double radial_ratio = (r.radius_cm > 0.0)
                    ? std::max(1.0e-36,std::min(99.0,r.radial_depth_cm / r.radius_cm))
                    : 1.0e-36;
                out << std::fixed << std::setprecision(2)
                    << std::setw(8) << safe_log(r.radius_cm,-10.0)
                    << std::setw(7) << std::log10(radial_ratio)
                    << std::setw(7) << safe_log(std::max(r.column_density_cm2,1.0e-10),-10.0)
                    << std::setw(7) << r.log_ionization_parameter
                    << std::setw(7) << r.electron_fraction
                    << std::setw(7) << safe_log(r.density_cm3,-10.0)
                    << std::setw(7) << (r.temperature_t4 > 0.0
                        ? 4.0 + std::log10(r.temperature_t4) : -10.0)
                    << std::setw(7) << std::clamp(100.0 * r.hmctot,-99.99,99.99)
                    << std::setw(7) << std::clamp(r.radiation_balance_percent,-99.99,99.99)
                    << std::setw(7) << std::log10(std::max(r.forward_reference_tau,1.0e-10))
                    << std::setw(7) << std::log10(std::max(r.reverse_reference_tau,1.0e-10))
                    << std::setw(3) << r.dsec_ntotit << "\n";
            }
        }
    } else {
        // Preserve the already-qualified npass=1 serializer unchanged.
        print_ispcg2_v0682273(1u);
        out << "\n pass number= 1 -1\n";
        print_option17_heading();
        // Option 17 owns the complete physical pprint(9) trajectory: ordinary
        // radial boundaries plus the canonical post-loop/post-transport endpoint.
        // The later zero-thickness xstarcalc/pprint(22) evaluation is not stored in
        // radial_zones and must never expand xout_step.
        const std::size_t output_rows = rows.size();
        for(std::size_t i=0;i<output_rows && !rows.empty();++i){
            const Row& r=rows[i];
            const auto depths=i<depth_logs.size()?depth_logs[i]:std::pair<double,double>{-10.0,-10.0};
            const std::size_t ntotit = i < state.radial_zones.size() ? state.radial_zones[i].dsec_ntotit : 0u;
            out<<std::fixed<<std::setprecision(2)
               <<std::setw(8)<<safe_log(r.radius,-10.0)
               <<std::setw(7)<<(r.radius>0&&r.dr>0?std::log10(r.dr/r.radius):-36.0)
               <<std::setw(7)<<safe_log(r.column,-10.0)
               <<std::setw(7)<<r.logxi<<std::setw(7)<<r.xee
               <<std::setw(7)<<safe_log(r.density,-10.0)
               <<std::setw(7)<<(r.temperature>0?4.0+std::log10(r.temperature):-10.0)
               <<std::setw(7)<<std::clamp(100.0*r.heat_error,-99.99,99.99)
               <<std::setw(7)<<std::clamp((i<heat_balance_percent.size()?heat_balance_percent[i]:0.0),-99.99,99.99)
               <<std::setw(7)<<depths.first<<std::setw(7)<<depths.second
               <<std::setw(3)<<ntotit<<"\n";
        }
    }
    out.unsetf(std::ios::floatfield); out<<std::setprecision(17);
    if (state.legacy_pprint.final_zero_thickness_evaluation_present) {
        const long long lpri = static_cast<long long>(std::llround(
            parameter_number(state, "lprint", 0.0)));
        out << "\n  final print:" << std::setw(12) << lpri << "\n"
            << std::uppercase << std::scientific << std::setprecision(8)
            << std::setw(16) << state.legacy_pprint.final_temperature_t4
            << std::setw(16) << state.legacy_pprint.final_total_heating
            << std::setw(16) << state.legacy_pprint.final_total_cooling
            << std::setw(16) << state.legacy_pprint.final_hmctot << "\n\n";
        out.unsetf(std::ios::floatfield); out << std::setprecision(17);
    }
    if (!rows.empty() && (!state.radial_zones.empty() || !state.fixed_evaluations.empty())) {
        const auto& r=rows.back();
        const auto& boundary_eval=state.radial_zones.empty()?state.fixed_evaluations.back():state.radial_zones.back().accepted_controller.evaluation;
        const auto& eval=state.final_writer_evaluation ? *state.final_writer_evaluation : boundary_eval;
        const bool have_final = state.legacy_pprint.final_zero_thickness_evaluation_present;
        const double final_t4 = have_final ? state.legacy_pprint.final_temperature_t4 : r.temperature;
        const double final_heating = have_final ? state.legacy_pprint.final_total_heating : eval.total_heating;
        const double final_cooling = have_final ? state.legacy_pprint.final_total_cooling : eval.total_cooling;
        // 0.6.82.24.2: pprint(22) publishes the accepted/source xee.  The
        // fixed-state computed electron fraction is diagnostic only and may
        // differ intentionally when niter=0 or when a finite DSEC iteration
        // limit returns before charge neutrality is solved.
        const double final_xee = std::isfinite(eval.electron_fraction_input) && eval.electron_fraction_input > 0.0
            ? eval.electron_fraction_input : r.xee;
        // 0.6.82.27.7: pprint(22) is called after the post-loop
        // xstarcalc -> HEATT -> STPCUT(delr=1.e-15) sequence.  Consume the
        // final-writer dpthc retained for that exact lifetime, not the last
        // radial Option-17 boundary.
        double tf=0.0, tb=0.0;
        {
            const auto& final_energy_v0682277 = eval.radiation_energy_ev;
            const auto& final_dpthc_v0682277 = eval.source_workspace.dpthc;
            const std::size_t n_v0682277 = final_energy_v0682277.size();
            if (n_v0682277 > 0u && final_dpthc_v0682277.size() >= 2u*n_v0682277) {
                const std::size_t rb_v0682277 = std::min(
                    source_option17_reference_bin_zero_based(final_energy_v0682277), n_v0682277-1u);
                tf = std::max(0.0, final_dpthc_v0682277[rb_v0682277]);
                tb = std::max(0.0, final_dpthc_v0682277[n_v0682277 + rb_v0682277]);
            }
        }
        const double source_radius_scale=static_cast<double>(static_cast<float>(1.0e-19));
        const double r19=r.radius*source_radius_scale;
        const double xlum=parameter_number(state,"rlrad38",0.0);
        const double skse=(r.density>0.0&&r19>0.0)?xlum/(r.density*r19*r19):0.0;
        const double zeta=std::log10(std::max(1.0e-24,skse));
        out<<" print option:22\n";
        out<<" r=  "<<e3(r.radius)<<" t=  "<<e3(final_t4)<<" log(xi)=  "<<e3(zeta)
           <<" n_e=  "<<e3(final_xee*r.density)<<" n_p=  "<<e3(r.density)<<"\n";
        out<<"httot=  "<<e3(final_heating)<<" cltot=  "<<e3(final_cooling)
           <<" taulc=  "<<e3(tf)<<" taulcb=  "<<e3(tb)<<"\n";

        // pprint(22) uses enlum from the startup ispcg2 call for U1, but the
        // live final zremsz for UX and gamma.  Keep those two source lifetimes
        // separate exactly as FORTRAN/Python do.
        const double geometry=static_cast<double>(static_cast<float>(12.56));
        const double source_c_u=static_cast<double>(static_cast<float>(3.0e10));
        const double source_c_gamma=static_cast<double>(static_cast<float>(2.998e10));
        const double denom_u=geometry*r.density*r19*r19*source_c_u;
        const double u1=denom_u>0.0?ispcg2_enlum/denom_u:0.0;

        const auto& final_energy = !eval.radiation_energy_ev.empty() ? eval.radiation_energy_ev : source_energy;
        const auto& final_zremsz = eval.source_workspace.zremsz.size() >= final_energy.size()
            ? eval.source_workspace.zremsz : source_flux;
        double enlumx=0.0;
        if(final_energy.size()>=2u && final_zremsz.size()>=final_energy.size()){
            const std::size_t nb1=source_pprint_nry_zero_based(100.0,final_energy);
            const std::size_t nb10=source_pprint_nry_zero_based(10000.0,final_energy);
            const std::size_t lo=std::max<std::size_t>(2u,std::min(final_energy.size(),nb1));
            const std::size_t hi=std::max(lo,std::min(final_energy.size(),nb10));
            for(std::size_t kl=lo;kl<=hi;++kl){
                const std::size_t i=kl-1u;
                if(i==0u||i>=final_energy.size()) continue;
                const double e0=final_energy[i-1u],e1=final_energy[i];
                if(e0<=0.0||e1<=0.0) continue;
                enlumx+=(final_zremsz[i]/e1+final_zremsz[i-1u]/e0)*(e1-e0)/2.0;
            }
        }
        const double ux=denom_u>0.0?enlumx/denom_u:0.0;
        const double ekt=final_t4*xstar_constants::kLegacyBoltzmannEvPerT4*xstar_constants::kModernErgPerEv;
        const double xi_pressure=(ekt>0.0&&skse>0.0)?skse/geometry/((1.0+final_xee)*ekt*source_c_gamma):0.0;
        double gamma=0.0;
        if(final_energy.size()>=2u&&final_zremsz.size()>=final_energy.size()&&r.density>0.0&&r19>0.0){
            const std::size_t gi=source_pprint_nry_zero_based(13.7,final_energy);
            gamma=final_zremsz[gi]/(2.0*geometry*r.density*source_c_gamma*r19*r19+1.0e-24);
        }
        out<<" log(Xi)=  "<<e3(xi_pressure>0.0?std::log10(xi_pressure):0.0)
           <<" log(u1)= "<<e3(u1>0.0?std::log10(u1):0.0)
           <<" log(ux)= "<<e3(ux>0.0?std::log10(ux):0.0)
           <<" gamma=  "<<e3(gamma)<<" rdel=  "<<e3(r.dr)<<"\n\n";
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide move to last named hdu for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool move_to_last_named_hdu(fitsfile* fptr, const std::string& extname) {
    int status = 0;
    int nhdus = 0;
    fits_get_num_hdus(fptr, &nhdus, &status);
    if (status != 0) return false;
    for (int hdu = nhdus; hdu >= 2; --hdu) {
        int hdutype = 0;
        status = 0;
        fits_movabs_hdu(fptr, hdu, &hdutype, &status);
        if (status != 0) continue;
        char value[FLEN_VALUE]{};
        status = 0;
        fits_read_key(fptr, TSTRING, const_cast<char*>("EXTNAME"), value, nullptr, &status);
        if (status == 0 && extname == value) return true;
    }
    return false;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide column number for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
int column_number(fitsfile* fptr, const char* name) {
    int status = 0;
    int col = 0;
    fits_get_colnum(fptr, CASEINSEN, const_cast<char*>(name), &col, &status);
    return status == 0 ? col : 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide table rows for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
long long table_rows(fitsfile* fptr) {
    int status = 0;
    LONGLONG rows = 0;
    fits_get_num_rowsll(fptr, &rows, &status);
    return status == 0 ? static_cast<long long>(rows) : 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load integer cell into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
long long read_integer_cell(fitsfile* fptr, int col, long long row) {
    if (col <= 0) return 0;
    int status = 0;
    int anynul = 0;
    LONGLONG value = 0;
    LONGLONG nulval = 0;
    fits_read_col(fptr, TLONGLONG, col, row, 1, 1, &nulval, &value, &anynul, &status);
    return status == 0 ? static_cast<long long>(value) : 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load double cell into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
double read_double_cell(fitsfile* fptr, int col, long long row) {
    if (col <= 0) return 0.0;
    int status = 0;
    int anynul = 0;
    double value = 0.0;
    double nulval = 0.0;
    fits_read_col(fptr, TDOUBLE, col, row, 1, 1, &nulval, &value, &anynul, &status);
    return status == 0 && std::isfinite(value) ? value : 0.0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load string cell into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
std::string read_string_cell(fitsfile* fptr, int col, long long row) {
    if (col <= 0) return "unavailable";
    int status = 0;
    int anynul = 0;
    char buffer[256]{};
    char* ptr = buffer;
    char nulval[] = "";
    fits_read_col(fptr, TSTRING, col, row, 1, 1, nulval, &ptr, &anynul, &status);
    if (status != 0) return "unavailable";
    std::string out(buffer);
    while (!out.empty() && std::isspace(static_cast<unsigned char>(out.back()))) out.pop_back();
    return out.empty() ? "unavailable" : out;
}

struct PublicLineLogRow {
    long long index=0; std::string ion; double wavelength=0, emit_in=0, emit_out=0, depth_in=0, depth_out=0;
};

struct SourceRankIdentityV064812341 {
    const xstar_run_state::LineIdentityState* identity = nullptr;
    double key = 0.0;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute source pprint line identity rank for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
std::vector<SourceRankIdentityV064812341> source_pprint_line_identity_rank(
    const xstar_run_state::ProductWritingState& state,
    bool depth_mode,
    std::size_t maximum_rows) {
    std::vector<SourceRankIdentityV064812341> result;
    if (state.radial_zones.empty() || state.line_identities.empty() || maximum_rows == 0u) return result;
    const auto& ws = state.radial_zones.back().accepted_controller.evaluation.source_workspace;
    const std::size_t elum_stride = ws.elum.size() >= 2u && ws.elum.size() % 2u == 0u ? ws.elum.size() / 2u : 0u;
    const std::size_t tau_stride = ws.tau0.size() >= 2u && ws.tau0.size() % 2u == 0u ? ws.tau0.size() / 2u : 0u;
    if ((!depth_mode && elum_stride == 0u) || (depth_mode && tau_stride == 0u)) return result;

    std::vector<const xstar_run_state::LineIdentityState*> ordered;
    ordered.reserve(state.line_identities.size());
    for (const auto& id : state.line_identities) if (id.line_index > 0) ordered.push_back(&id);
    std::sort(ordered.begin(), ordered.end(), [](const auto* a, const auto* b) {
        return a->line_index < b->line_index;
    });

    std::vector<std::size_t> kltmp(maximum_rows, 0u); // ordered index + 1, zero sentinel
    std::vector<double> keys(ordered.size(), 0.0);
    std::vector<unsigned char> valid(ordered.size(), 0u);
    std::size_t kltmpo = 0u;
    std::size_t nlpl = 1u;
    for (std::size_t si = 0; si < ordered.size(); ++si) {
        const auto& id = *ordered[si];
        if (id.rate_type == 9 || id.rate_type == 14) continue;
        const double wavelength = std::abs(id.wavelength_angstrom);
        if (!(wavelength >= 0.1 && wavelength <= 1.0e10 && wavelength <= 8.9e6)) continue;
        const std::size_t slot = static_cast<std::size_t>(id.line_index);
        double key = 0.0;
        if (depth_mode) {
            if (slot >= tau_stride || tau_stride + slot >= ws.tau0.size()) continue;
            key = std::isfinite(ws.tau0[slot]) ? ws.tau0[slot] : 0.0;
        } else {
            if (slot >= elum_stride || elum_stride + slot >= ws.elum.size()) continue;
            const double inward = std::isfinite(ws.elum[slot]) ? ws.elum[slot] : 0.0;
            const double outward = std::isfinite(ws.elum[elum_stride + slot]) ? ws.elum[elum_stride + slot] : 0.0;
            key = 0.5 * (inward + outward);
        }
        // pprint(1/23) uses a double-precision 1.d-49 activity gate.
        if (!(std::isfinite(key) && key > 1.0e-49)) continue;
        keys[si] = key;
        valid[si] = 1u;

        std::size_t lmm = 0u;
        double elcomp = 1.0e10;
        while (lmm < nlpl && key < elcomp) {
            ++lmm;
            const std::size_t kl2 = kltmp[lmm - 1u];
            elcomp = 0.0;
            if (kl2 > 0u) elcomp = keys[kl2 - 1u];
        }
        kltmpo = si + 1u;
        const std::size_t last = std::min(maximum_rows, nlpl);
        if (lmm > 0u) {
            for (std::size_t k = lmm; k <= last; ++k) {
                const std::size_t at = k - 1u;
                const std::size_t kltmpn = kltmp[at];
                kltmp[at] = kltmpo;
                kltmpo = kltmpn;
            }
        }
        nlpl = std::min(maximum_rows, nlpl + 1u);
    }
    if (nlpl > 0u) kltmp[nlpl - 1u] = kltmpo;
    result.reserve(maximum_rows);
    for (std::size_t kk = 0; kk < nlpl && kk < kltmp.size(); ++kk) {
        if (kltmp[kk] == 0u) continue;
        const std::size_t si = kltmp[kk] - 1u;
        if (si < ordered.size() && valid[si]) result.push_back({ordered[si], keys[si]});
    }
    return result;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Append native public line sections from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void append_native_public_line_sections(std::ofstream& out,
                                        const std::filesystem::path& output_dir,
                                        const xstar_run_state::ProductWritingState& state) {
    fitsfile* fptr=nullptr; int status=0;
    const auto path=output_dir/"xout_lines1.fits";
    fits_open_file(&fptr,path.c_str(),READONLY,&status);
    if(status!=0 || !move_to_last_named_hdu(fptr,"XSTAR_LINES")){
        if(fptr){int cs=0;fits_close_file(fptr,&cs);} out<<"\n public line sections unavailable: xout_lines1.fits not readable.\n\n"; return;
    }
    const int ci=column_number(fptr,"index"),cion=column_number(fptr,"ion"),cw=column_number(fptr,"wavelength"),
        cei=column_number(fptr,"emit_inward"),ceo=column_number(fptr,"emit_outward"),cdi=column_number(fptr,"depth_inward"),cdo=column_number(fptr,"depth_outward");
    std::vector<PublicLineLogRow> rows; const long long nr=table_rows(fptr); rows.reserve(nr);
    for(long long r=1;r<=nr;++r) rows.push_back({read_integer_cell(fptr,ci,r),read_string_cell(fptr,cion,r),read_double_cell(fptr,cw,r),read_double_cell(fptr,cei,r),read_double_cell(fptr,ceo,r),read_double_cell(fptr,cdi,r),read_double_cell(fptr,cdo,r)});
    int cs=0;fits_close_file(fptr,&cs);
    out<<"\n print option: 1\n";
    if (state.diagnostic_preview_partial) {
        out<<" diagnostic partial values: accumulated only through retained physical transport intervals\n";
    }
    out<<" emission line luminosities (erg/sec/10**38))\n";
    out<<" index, ion, wavelength, reflected, transmitted\n";
    auto luminosity_rows=rows;
    std::stable_sort(luminosity_rows.begin(),luminosity_rows.end(),[](const auto&a,const auto&b){return (a.emit_in+a.emit_out)>(b.emit_in+b.emit_out);});
    const std::size_t luminosity_count=std::min<std::size_t>(500,luminosity_rows.size());
    const auto luminosity_identities = source_pprint_line_identity_rank(state, false, 500u);
    for(std::size_t k=0;k<luminosity_count;++k){
        const auto& numeric=luminosity_rows[k];
        const auto* id = k < luminosity_identities.size() ? luminosity_identities[k].identity : nullptr;
        const long long index = id ? id->line_index : numeric.index;
        const std::string ion = id ? id->ion_label : numeric.ion;
        const double wavelength = id ? id->wavelength_angstrom : numeric.wavelength;
        out<<std::setw(8)<<(k+1)<<std::setw(8)<<index<<" "<<std::left<<std::setw(10)<<ion<<std::right
           <<std::setw(14)<<std::uppercase<<std::scientific<<std::setprecision(5)<<wavelength
           <<std::setw(14)<<numeric.emit_in<<std::setw(14)<<numeric.emit_out<<"\n";
    }
    out<<"\n print option:23\n";
    if (state.diagnostic_preview_partial) {
        out<<" diagnostic partial values: terminal radial depth has not been reached\n";
    }
    out<<" line depths\n index, ion, wavelength, reflected, transmitted\n";
    // Source pprint option 23 ranks the complete detailed line inventory by
    // terminal backward depth.  xout_lines1 is a 600-row luminosity-selected
    // public subset and cannot reproduce the depth interval near rank 500.
    std::vector<PublicLineLogRow> depth_rows;
    fitsfile* detail=nullptr; status=0;
    const int final_pass_v0682279 = std::max(1, static_cast<int>(std::llround(parameter_number(state, "npass", 1.0))));
    std::ostringstream final_line_detail_name_v0682279;
    final_line_detail_name_v0682279 << "xo" << std::setw(2) << std::setfill('0')
                                    << final_pass_v0682279 << "_detal2.fits";
    const auto final_line_detail_path_v0682279 = output_dir / final_line_detail_name_v0682279.str();
    fits_open_file(&detail,final_line_detail_path_v0682279.c_str(),READONLY,&status);
    if(status==0 && move_to_last_named_hdu(detail,"XSTAR_RADIAL")){
        const int di=column_number(detail,"index"),dion=column_number(detail,"ion"),dw=column_number(detail,"wavelength"),
            dti=column_number(detail,"tau_in"),dto=column_number(detail,"tau_out");
        const long long dn=table_rows(detail); depth_rows.reserve(static_cast<std::size_t>(dn));
        for(long long rr=1;rr<=dn;++rr){
            depth_rows.push_back({read_integer_cell(detail,di,rr),read_string_cell(detail,dion,rr),
                read_double_cell(detail,dw,rr),0.0,0.0,read_double_cell(detail,dti,rr),read_double_cell(detail,dto,rr)});
        }
    }
    if(detail){int dcs=0;fits_close_file(detail,&dcs);}
    if(depth_rows.empty()) depth_rows=rows;
    std::stable_sort(depth_rows.begin(),depth_rows.end(),[](const auto&a,const auto&b){return a.depth_in>b.depth_in;});
    const std::size_t depth_count=std::min<std::size_t>(500,depth_rows.size());
    const auto depth_identities = source_pprint_line_identity_rank(state, true, 500u);
    for(std::size_t k=0;k<depth_count;++k){
        const auto& numeric=depth_rows[k];
        const auto* id = k < depth_identities.size() ? depth_identities[k].identity : nullptr;
        const long long index = id ? id->line_index : numeric.index;
        const std::string ion = id ? id->ion_label : numeric.ion;
        const double wavelength = id ? id->wavelength_angstrom : numeric.wavelength;
        out<<std::setw(8)<<(k+1)<<std::setw(8)<<index<<" "<<std::left<<std::setw(10)<<ion<<std::right
           <<std::setw(14)<<std::uppercase<<std::scientific<<std::setprecision(5)<<wavelength
           <<std::setw(14)<<numeric.depth_in<<std::setw(14)<<numeric.depth_out<<"\n";
    }
    out<<"\n";out.unsetf(std::ios::floatfield);out<<std::setprecision(17);
}

struct DetailRrcLogRow { long long index=0,level_index=0; std::string ion,lower,upper; double energy=0; };

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide split simple csv for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<std::string> split_simple_csv(const std::string& line) {
    std::vector<std::string> out;
    std::string current;
    bool quoted = false;
    for (char ch : line) {
        if (ch == '"') { quoted = !quoted; continue; }
        if (ch == ',' && !quoted) { out.push_back(current); current.clear(); }
        else current.push_back(ch);
    }
    out.push_back(current);
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide csv integer for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
long long csv_integer(const std::vector<std::string>& fields, std::size_t index) {
    if (index >= fields.size() || fields[index].empty()) return 0;
    try { return std::stoll(fields[index]); } catch (...) { return 0; }
}

struct RrcSourceRecord {
    long long source_index = 0;
    long long data_type = 0;
    long long element_index = 0;
    long long element_z = 0;
    long long ion_index = 0;
    long long lower_row = 0;
    long long upper_row = 0;
    long long continuum_index = 0;
    long long lower_local = 0;
    long long upper_local = 0;
    double threshold_ev = 0.0;
    std::string ion_label;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide csv double for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] double csv_double(const std::vector<std::string>& fields, std::size_t index) {
    if (index >= fields.size() || fields[index].empty()) return 0.0;
    try { return std::stod(fields[index]); } catch (...) { return 0.0; }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide roman lower for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::string roman_lower(long long value) {
    struct Roman { int value; const char* text; };
    static const Roman tokens[] = {
        {1000,"m"},{900,"cm"},{500,"d"},{400,"cd"},{100,"c"},{90,"xc"},
        {50,"l"},{40,"xl"},{10,"x"},{9,"ix"},{5,"v"},{4,"iv"},{1,"i"}
    };
    if (value <= 0) return "";
    std::string out;
    for (const auto& token : tokens) {
        while (value >= token.value) { out += token.text; value -= token.value; }
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide source ion label for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::string source_ion_label(long long element_z, long long ion_index) {
    std::string symbol;
    if (element_z == 1) symbol = "h";
    else if (element_z == 2) symbol = "he";
    else if (element_z == 12) symbol = "mg";
    else symbol = "z" + std::to_string(element_z);
    return symbol + "_" + roman_lower(ion_index);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide hydrogen or helium ion label for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
bool hydrogen_or_helium_ion_label(const std::string& label) {
    return label.rfind("h_", 0) == 0 || label.rfind("he_", 0) == 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load native ion row minima into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
[[maybe_unused]] std::map<std::pair<long long,long long>,long long> load_native_ion_row_minima(
    const std::filesystem::path& output_dir,
    const xstar_run_state::ProductWritingState& state) {
    std::map<std::pair<long long,long long>,long long> minima;
    if (!state.row_metadata.empty()) {
        for (const auto& source : state.row_metadata) {
            if (source.row <= 0) continue;
            const auto key = std::make_pair(
                static_cast<long long>(source.element_index),
                static_cast<long long>(source.ion));
            const auto found = minima.find(key);
            if (found == minima.end() || source.row < found->second) {
                minima[key] = source.row;
            }
        }
        return minima;
    }
    std::ifstream input(output_dir / "_native_atdb_case" / "rows.csv");
    if (!input) return minima;
    std::string line;
    if (!std::getline(input, line)) return minima;
    const auto header = split_simple_csv(line);
    std::map<std::string,std::size_t> column;
    for (std::size_t i=0; i<header.size(); ++i) column[header[i]] = i;
    const auto at = [&](const char* key) -> std::size_t {
        const auto found = column.find(key);
        return found == column.end() ? header.size() : found->second;
    };
    const std::size_t celement=at("element_index"), cion=at("ion"), crow=at("row");
    while (std::getline(input, line)) {
        const auto fields = split_simple_csv(line);
        const long long element = csv_integer(fields, celement);
        const long long ion = csv_integer(fields, cion);
        const long long row = csv_integer(fields, crow);
        if (row <= 0) continue;
        const auto key = std::make_pair(element, ion);
        const auto found = minima.find(key);
        if (found == minima.end() || row < found->second) minima[key] = row;
    }
    return minima;
}

struct ShellGeometry { double radius_cm = 0.0; double delta_cm = 0.0; };
std::vector<int> named_hdu_numbers(fitsfile* fptr, const std::string& extname);

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Publish Option-24 recombination-edge rows from clean per-ion Type-7 identities and current continuum optical depths; do not reproduce the known Fortran pprint(24) stale-local H I/He II alias.
// Reference context: XSTAR Manual ss11.5, 11.7 and ch12 rate type 7; frozen Option-24 qualification semantics from the accepted parity campaign.
// XSTAR-FUNCTION-COMMENT-END
void append_native_public_rrc_sections(std::ofstream& out,
                                       const std::filesystem::path&,
                                       const xstar_run_state::ProductWritingState& state,
                                       bool write_depth,bool write_luminosity) {
    if (state.radial_zones.empty()) {
        out << "\n retained native RRC workspace unavailable.\n\n";
        return;
    }
    const auto& ws = state.radial_zones.back().accepted_controller.evaluation.source_workspace;
    const std::size_t tauc_stride = ws.tauc.size() >= 2u ? ws.tauc.size() / 2u : 0u;
    const std::size_t elum_stride = ws.elumab.size() >= 2u ? ws.elumab.size() / 2u : 0u;
    if (write_depth) {
        out << " print option:24\n absorption edge depths\n"
               " index, ion, level, energy (eV), depth \n";
    }
    if (write_luminosity) {
        out << " print option:19\n recombination continuum luminosities(erg/sec/10**38))\n"
               " index, ion, level, energy (eV), RRC luminosity \n";
    }
    // Source pprint traverses the exact per-ion npfi(7,jkk) chains and
    // addresses retained arrays through npconi2.  Do not walk the legacy
    // 1849-slot FITS compatibility identity vector here: that vector may be
    // synthesized after lowering and can attach a source rate owner to a
    // different synthetic level identity.  12.3.42.1.2 retains the original
    // ATDB-derived RRC identities separately for STEP publication.
    const auto& source_rrcs = !state.source_rrc_identities.empty()
        ? state.source_rrc_identities : state.rrc_identities;
    for (const auto& id : source_rrcs) {
        if (id.continuum_index <= 0) continue;
        // pprint(19/24) traverses npfi(7,jkk) only. Production ATDB lowering
        // retains that source rate family explicitly; do not admit legacy
        // rate_type==0 placeholders on this canonical publication path.
        if (id.rate_type != 7) continue;
        const std::size_t slot = static_cast<std::size_t>(id.continuum_index);
        const double tau_in = slot < tauc_stride ? ws.tauc[slot] : 0.0;
        const double tau_out = slot < tauc_stride ? ws.tauc[tauc_stride + slot] : 0.0;
        const double lum_in = slot < elum_stride ? ws.elumab[slot] : 0.0;
        const double lum_out = slot < elum_stride ? ws.elumab[elum_stride + slot] : 0.0;
        if (write_depth && hydrogen_or_helium_ion_label(id.ion_label) &&
            (std::abs(tau_in) > 1.0e-49 || std::abs(tau_out) > 1.0e-49)) {
            // pprint.f90 label 9293 is shared by options 24 and 19:
            // kkkl(npconi2), mmlv(npilev), ion, idest1, idest2, labels.
            out << std::setw(7) << id.continuum_index
                << std::setw(6) << id.level_global_index << " "
                << std::left << std::setw(8) << id.ion_label << std::right
                << std::setw(6) << id.lower_local_index
                << std::setw(6) << id.upper_local_index << " "
                << std::left << std::setw(20) << id.lower_level << " "
                << std::setw(20) << id.upper_level << std::right
                << std::setw(13) << std::uppercase << std::scientific
                << std::setprecision(3) << id.threshold_ev
                << std::setw(13) << tau_in << std::setw(13) << tau_out << "\n";
        }
        // 0.6.48.12.3.42.1.3: canonical pprint(19) never publishes the
        // non-physical negative-threshold O IV subset observed in the O VII
        // qualification.  In FORTRAN those slots remain below the luminosity
        // print floor; the native retained workspace can carry non-zero values
        // there.  Treat a strictly positive physical RRC threshold as an
        // Option-19 publication eligibility condition.  This is publication
        // only: it does not modify the retained elumab/tauc science arrays or
        // the FITS RRC writer.
        if (write_luminosity && id.threshold_ev > 0.0 &&
            (std::abs(lum_in) > 1.0e-49 || std::abs(lum_out) > 1.0e-49)) {
            out << std::setw(7) << id.continuum_index
                << std::setw(6) << id.level_global_index << " "
                << std::left << std::setw(10) << id.ion_label << std::right
                << std::setw(6) << id.lower_local_index
                << std::setw(6) << id.upper_local_index << " "
                << std::left << std::setw(24) << id.lower_level
                << std::setw(24) << id.upper_level << std::right
                << std::setw(13) << std::uppercase << std::scientific
                << std::setprecision(3) << id.threshold_ev
                << std::setw(13) << lum_in << std::setw(13) << lum_out << "\n";
        }
    }
    out << "\n";
    out.unsetf(std::ios::floatfield);
    out << std::setprecision(17);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Append native ion columns from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void append_native_ion_columns(std::ofstream& out,const std::filesystem::path& output_dir){
    fitsfile*f=nullptr;int status=0;fits_open_file(&f,(output_dir/"xout_abund1.fits").c_str(),READONLY,&status);
    out<<" print option:27\n ion column densities\n index, ion, column density\n";
    // Source pprint(27) uses `if (xcoltmp(lk).gt.1.e-15)` and format
    // `(1x,i4,1x,9a1,1pe16.8)`.  Preserve the default-REAL threshold and
    // guarantee separation between an eight-character ion name and the value.
    const double source_column_floor_v064812316 = static_cast<double>(1.0e-15f);
    if(status==0){status=0;fits_movnam_hdu(f,ANY_HDU,const_cast<char*>("COLUMNS"),0,&status);int nc=0;if(status==0)fits_get_num_cols(f,&nc,&status);for(int c=9;status==0&&c<=nc;++c){char key[FLEN_KEYWORD]{},name[FLEN_VALUE]{};fits_make_keyn("TTYPE",c,key,&status);int st=0;fits_read_key(f,TSTRING,key,name,nullptr,&st);if(st!=0)continue;double v=0;int any=0;st=0;fits_read_col(f,TDOUBLE,c,1,1,1,nullptr,&v,&any,&st);if(st==0&&v>source_column_floor_v064812316)out<<std::setw(5)<<(c-8)<<" "<<std::left<<std::setw(9)<<name<<std::right<<std::setw(16)<<std::uppercase<<std::scientific<<std::setprecision(8)<<v<<"\n";}int cs=0;fits_close_file(f,&cs);}else out<<" native COLUMNS product unavailable.\n";
    out<<"\n";out.unsetf(std::ios::floatfield);out<<std::setprecision(17);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide named hdu numbers for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
std::vector<int> named_hdu_numbers(fitsfile* fptr, const std::string& extname) {
    std::vector<int> out;
    int status = 0, nhdus = 0;
    fits_get_num_hdus(fptr, &nhdus, &status);
    for (int hdu = 2; status == 0 && hdu <= nhdus; ++hdu) {
        int type = 0;
        fits_movabs_hdu(fptr, hdu, &type, &status);
        if (status != 0) break;
        char value[FLEN_VALUE]{};
        int st = 0;
        fits_read_key(fptr, TSTRING, const_cast<char*>("EXTNAME"), value, nullptr, &st);
        if (st == 0 && extname == value) out.push_back(hdu);
    }
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Append native detail line section from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void append_native_detail_line_section(
    std::ofstream& out,
    const std::filesystem::path& output_dir,
    const xstar_run_state::ProductWritingState& state) {
    if (state.radial_zones.empty()) {
        out << " print option:15\n retained native line workspace unavailable.\n\n";
        return;
    }
    const auto& ws = state.radial_zones.back().accepted_controller.evaluation.source_workspace;
    const std::size_t rcem_stride = ws.rcem.size() / 2u;
    const std::size_t tau_stride = ws.tau0.size() / 2u;
    const std::size_t elum_stride = ws.elum.size() / 2u;

    std::vector<const xstar_run_state::LineIdentityState*> ordered;
    ordered.reserve(state.line_identities.size());
    for (const auto& id : state.line_identities) {
        const double source_wavelength = std::abs(id.wavelength_angstrom);
        // Literal pprint(15) walks the complete nplin inventory.  Although
        // the source IF mentions lrtyp, pprint calls drd for the ion and then
        // the element before that IF; those calls overwrite lrtyp.  Therefore
        // the test is not a line-rate-type exclusion.  The observable public
        // line gate is wavelength (+ element abundance, already enforced by
        // active-element lowering).  Filtering id.rate_type here incorrectly
        // removed canonical H I and terminal element blocks.
        if (id.line_index > 0 &&
            source_wavelength > 0.1 && source_wavelength < 9.0e9) {
            ordered.push_back(&id);
        }
    }
    std::stable_sort(ordered.begin(), ordered.end(), [](const auto* a, const auto* b) {
        return a->line_index < b->line_index;
    });

    auto plane_value = [](const std::vector<double>& values, std::size_t stride,
                          std::size_t plane, std::size_t slot) {
        const std::size_t at = plane * stride + slot;
        return at < values.size() && std::isfinite(values[at]) ? values[at] : 0.0;
    };
    std::map<int,std::size_t> rows_by_type;
    std::map<int,std::size_t> nonzero_by_type;
    std::size_t mapped_rows = 0;
    std::size_t max_slot = 0;

    out << " print option:15\n line luminosities (erg/sec/10**38) and depths\n";
    out << "  line, wavelength, ion, ref. lum.,trn. lum.,backward depth, forward depth\n";
    for (const auto* id : ordered) {
        const std::size_t slot = static_cast<std::size_t>(id->line_index);
        max_slot = std::max(max_slot, slot);
        ++rows_by_type[id->data_type];
        const bool mapped = slot < ws.oplin.size() && slot < rcem_stride &&
            slot < tau_stride && slot < elum_stride;
        if (mapped) ++mapped_rows;
        const double ref = mapped ? plane_value(ws.elum, elum_stride, 0u, slot) : 0.0;
        const double trn = mapped ? plane_value(ws.elum, elum_stride, 1u, slot) : 0.0;
        const double backward = mapped ? plane_value(ws.tau0, tau_stride, 0u, slot) : 0.0;
        const double forward = mapped ? plane_value(ws.tau0, tau_stride, 1u, slot) : 0.0;
        if (ref != 0.0 || trn != 0.0 || backward != 0.0 || forward != 0.0) {
            ++nonzero_by_type[id->data_type];
        }
        std::string ion = id->ion_label;
        if (ion.size() > 8u) ion.resize(8u);
        std::string description = id->lower_level + "-" + id->upper_level;
        description.erase(std::remove(description.begin(), description.end(), ' '), description.end());
        if (description.size() > 18u) description.resize(18u);
        out << std::setw(10) << id->line_index
            << std::setw(13) << std::uppercase << std::scientific << std::setprecision(5)
            << id->wavelength_angstrom << " "
            << std::left << std::setw(8) << ion << std::right
            << std::setw(13) << ref << std::setw(13) << trn
            << std::setw(13) << backward << std::setw(13) << forward
            << " " << description << "\n";
    }
    out << "\n";
    out.unsetf(std::ios::floatfield);
    out << std::setprecision(17);

    const bool coverage_ok = !ordered.empty() && mapped_rows == ordered.size() &&
        ws.line_workspace_exact && ws.line_tau_workspace_exact &&
        elum_stride > max_slot;
    std::ofstream audit;
    if (!true_production_mode()) audit.open(output_dir / "v048746255172565_full_line_channels_audit.json");
    if (audit) {
        audit << "{\n"
              << "  \"schema\": \"xstar-tools-v048746255172563-full-line-channels-v3\",\n"
              << "  \"source_line_rows\": " << ordered.size() << ",\n"
              << "  \"mapped_exact_nplini_rows\": " << mapped_rows << ",\n"
              << "  \"maximum_nplini_slot\": " << max_slot << ",\n"
              << "  \"native_line_workspace_slots\": " << (ws.oplin.empty() ? 0u : ws.oplin.size() - 1u) << ",\n"
              << "  \"type50_rows\": " << rows_by_type[50] << ",\n"
              << "  \"type54_rows\": " << rows_by_type[54] << ",\n"
              << "  \"type71_rows\": " << rows_by_type[71] << ",\n"
              << "  \"type76_rows\": " << rows_by_type[76] << ",\n"
              << "  \"nonzero_type50\": " << nonzero_by_type[50] << ",\n"
              << "  \"nonzero_type54\": " << nonzero_by_type[54] << ",\n"
              << "  \"nonzero_type71\": " << nonzero_by_type[71] << ",\n"
              << "  \"nonzero_type76\": " << nonzero_by_type[76] << ",\n"
              << "  \"controller_owned_rcem_oplin_tau0_elum\": true,\n"
              << "  \"zero_placeholder_merge_removed\": true,\n"
              << "  \"coverage_gate\": \"" << (coverage_ok ? "ACCEPT" : "REJECT") << "\",\n"
              << "  \"oracle_or_bridge_values_read\": false\n"
              << "}\n";
    }
    if (!coverage_ok) {
        throw std::runtime_error("full option-15 nplini workspace coverage gate failed");
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load spectrum column into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
bool read_spectrum_column(const std::filesystem::path& path,
                          const char* extname,
                          const char* energy_name,
                          const std::vector<const char*>& value_names,
                          std::vector<double>& energy,
                          std::vector<std::vector<double>>& values) {
    fitsfile* f=nullptr; int status=0;
    fits_open_file(&f,path.c_str(),READONLY,&status);
    if(status!=0 || !move_to_last_named_hdu(f,extname)) {
        if(f){int cs=0;fits_close_file(f,&cs);} return false;
    }
    const int ce=column_number(f,energy_name);
    std::vector<int> columns; for(const char* name:value_names) columns.push_back(column_number(f,name));
    if(ce<=0 || std::any_of(columns.begin(),columns.end(),[](int c){return c<=0;})) {
        int cs=0;fits_close_file(f,&cs);return false;
    }
    const long long nr=table_rows(f); energy.resize(static_cast<std::size_t>(nr));
    values.assign(columns.size(),std::vector<double>(static_cast<std::size_t>(nr),0.0));
    for(long long row=1;row<=nr;++row){const std::size_t i=static_cast<std::size_t>(row-1);energy[i]=read_double_cell(f,ce,row);for(std::size_t j=0;j<columns.size();++j)values[j][i]=read_double_cell(f,columns[j],row);}
    int cs=0;fits_close_file(f,&cs);return true;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Provide trapezoid values for final science-product publication from already-committed run state.
// Reference context: XSTAR Manual ch5 plus ss11.5-11.6 for the published physical quantities.
// XSTAR-FUNCTION-COMMENT-END
double trapezoid_values(const std::vector<double>& energy,const std::vector<double>& value){
    if (energy.size() != value.size() || energy.size() < 2) return 0.0;
    double sum = 0.0;
    for (std::size_t i=1; i<energy.size(); ++i) {
        sum += 0.5 * (value[i-1] + value[i]) * (energy[i] - energy[i-1]) * 1.602176634e-12;
    }
    return sum;
}

// 0.6.82.27.7: pprint(5) consumes the live/final-pass continuum state.
// Multipass publication writes that state to xoNN_detal4.fits, where NN is
// the final requested/source pass.  The old native formatter always reopened
// xo01_detal4.fits and therefore mixed pass-1 continuum sums with final-pass
// line luminosities.
std::filesystem::path final_pass_detal4_path_v0682277(
    const std::filesystem::path& output_dir,
    const xstar_run_state::ProductWritingState& state) {
    long long npass = static_cast<long long>(std::llround(parameter_number(state, "npass", 1.0)));
    if (npass < 1) npass = 1;
    std::ostringstream name;
    name << "xo" << std::setfill('0') << std::setw(2) << npass << "_detal4.fits";
    auto path = output_dir / name.str();
    if (!std::filesystem::is_regular_file(path) && npass != 1) {
        // Source conditions can collapse detail publication to the common
        // single-pass file.  Keep that legacy fallback without ever selecting
        // pass 1 when the final-pass file exists.
        path = output_dir / "xo01_detal4.fits";
    }
    return path;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Append native energy sums from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void append_native_energy_sums(std::ofstream& out,const std::filesystem::path& output_dir,const xstar_run_state::ProductWritingState& state){
    std::vector<double> ce,de;std::vector<std::vector<double>> cv,dv;
    const auto detail_path_v0682277 = final_pass_detal4_path_v0682277(output_dir, state);
    bool have_incident=read_spectrum_column(output_dir/"xout_spect1.fits","XSTAR_SPECTRA","energy",{"incident"},ce,cv) &&
        !cv.empty() && finite_nonzero_vector(cv.front());
    if(!have_incident){
        fitsfile* cf=nullptr;int cstatus=0;
        fits_open_file(&cf,detail_path_v0682277.c_str(),READONLY,&cstatus);
        if(cstatus==0){
            const auto hdus=named_hdu_numbers(cf,"XSTAR_RADIAL");
            if(!hdus.empty()){
                int type=0;cstatus=0;fits_movabs_hdu(cf,hdus.front(),&type,&cstatus);
                const int ee=column_number(cf,"energy"),zz=column_number(cf,"zrems(1)");
                const long long nr=table_rows(cf);
                if(cstatus==0&&ee>0&&zz>0&&nr>1){ce.resize(static_cast<std::size_t>(nr));cv.assign(1,std::vector<double>(static_cast<std::size_t>(nr),0.0));for(long long row=1;row<=nr;++row){ce[static_cast<std::size_t>(row-1)]=read_double_cell(cf,ee,row);cv[0][static_cast<std::size_t>(row-1)]=read_double_cell(cf,zz,row);}have_incident=finite_nonzero_vector(cv.front());}
            }
            int cs=0;fits_close_file(cf,&cs);
        }
    }
    const bool have_detail=read_spectrum_column(detail_path_v0682277,"XSTAR_RADIAL","energy",{"zrems(2)","zrems(3)","fwd dpth"},de,dv);
    // pprint(5) sums the full nlsvn cumulative elum surface, not the
    // luminosity-ranked 500/600-row public xout_lines1 subset.
    double line_sum=0.0;
    bool have_lines=false;
    if (!state.radial_zones.empty()) {
        const std::size_t final_zone = state.terminal_synthetic_row_present && state.radial_zones.size() >= 2u
            ? state.radial_zones.size() - 2u : state.radial_zones.size() - 1u;
        const auto& ws = state.radial_zones[final_zone].accepted_controller.evaluation.source_workspace;
        if (ws.elum.size() >= 2u && ws.elum.size() % 2u == 0u) {
            const std::size_t stride = ws.elum.size() / 2u;
            std::set<long long> seen;
            for (const auto& id : state.line_identities) {
                const long long li = id.line_index;
                if (li <= 0 || !seen.insert(li).second) continue;
                if (!(id.wavelength_angstrom > 1.0 && id.wavelength_angstrom < 1.0e8)) continue;
                const std::size_t slot = static_cast<std::size_t>(li);
                if (slot >= stride || stride + slot >= ws.elum.size()) continue;
                const double inward = std::isfinite(ws.elum[slot]) ? ws.elum[slot] : 0.0;
                const double outward = std::isfinite(ws.elum[stride + slot]) ? ws.elum[stride + slot] : 0.0;
                line_sum += inward + outward;
                have_lines = true;
            }
        }
    }
    out<<" print option: 5\n";
    if(!have_incident||!have_detail||!have_lines||ce.size()!=de.size()){
        out<<" source energy sums unavailable: required native continuum/detail/line products are incomplete.\n\n";return;
    }
    std::vector<double> absorbed(ce.size(),0.0),continuum(ce.size(),0.0);
    for(std::size_t i=0;i<ce.size();++i){absorbed[i]=cv[0][i]*(1.0-std::exp(-std::max(0.0,dv[2][i])));continuum[i]=dv[0][i]+dv[1][i];}
    const double abs_sum=trapezoid_values(ce,absorbed);const double cont_sum=trapezoid_values(de,continuum);const double err=(abs_sum-cont_sum-line_sum)/(abs_sum+1.0e-24);
    out<<" energy sums: abs, cont, line, err:"<<std::uppercase<<std::scientific<<std::setprecision(5)<<std::setw(13)<<abs_sum<<std::setw(13)<<cont_sum<<std::setw(13)<<line_sum<<std::setw(13)<<err<<"\n\n";
    out.unsetf(std::ios::floatfield);out<<std::setprecision(17);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Append native product sections from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
void append_native_product_sections(std::ofstream& out,const std::filesystem::path& output_dir,const xstar_run_state::ProductWritingState& state){
    append_native_public_line_sections(out,output_dir,state);
    append_native_public_rrc_sections(out,output_dir,state,true,false);
    out<<" print option:16\n source CPU accumulators and per-rate call counts: unavailable (not retained by the native controller).\n\n";
    append_native_ion_columns(out,output_dir);
    append_native_detail_line_section(out,output_dir,state);
    append_native_public_rrc_sections(out,output_dir,state,false,true);
    append_native_energy_sums(out,output_dir,state);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Append source like timing footer from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Append the additional source-owned verbose pprint surfaces selected by lprint>=2.
// Reference context: xstar.f90 nlprnt/nlnprnt final dispatch and pprint.f90 options 14,21,7,10,26,0,4,6,18,29,30.
// XSTAR-FUNCTION-COMMENT-END
void append_native_lprint_extra_sections(
    std::ofstream& out,
    const xstar_run_state::ProductWritingState& state,
    int lprint) {
    if (lprint < 2) return;

    const xstar_run_state::FixedEvaluationState* eval = nullptr;
    // The final nlprnt loop runs after xstar.f90's post-radial zero-thickness
    // xstarcalc.  Use the retained final-writer evaluation when available;
    // only fall back to the last physical radial boundary for older states.
    if (state.final_writer_evaluation) {
        eval = &*state.final_writer_evaluation;
    } else if (!state.radial_zones.empty()) {
        std::size_t zi = state.radial_zones.size() - 1u;
        if (state.terminal_synthetic_row_present && state.radial_zones.size() >= 2u) zi -= 1u;
        eval = &state.radial_zones[zi].accepted_controller.evaluation;
    } else if (!state.fixed_evaluations.empty()) {
        eval = &state.fixed_evaluations.back();
    }
    if (!eval) {
        throw std::runtime_error("verbose pprint publication requires a retained final fixed evaluation");
    }
    const auto& ws = eval->source_workspace;

    std::map<int,double> abundance_by_z;
    std::map<int,int> element_index_to_z;
    for (const auto& element : state.element_metadata) {
        abundance_by_z[element.atomic_number] = element.abundance;
        element_index_to_z[element.element_index] = element.atomic_number;
    }
    auto active_z = [&](int z, double floor) {
        const auto it = abundance_by_z.find(z);
        return it != abundance_by_z.end() && it->second > floor;
    };

    std::map<std::pair<int,int>, std::string> ion_labels;
    std::map<std::string,int> ion_label_to_z;
    std::map<std::string,int> ion_label_to_stage;
    for (const auto& row : state.row_metadata) {
        const auto ez = element_index_to_z.find(row.element_index);
        if (ez == element_index_to_z.end() || row.ion <= 0 || row.ion_label.empty()) continue;
        const auto key = std::make_pair(ez->second, row.ion);
        if (!ion_labels.count(key)) ion_labels[key] = row.ion_label;
        ion_label_to_z[row.ion_label] = ez->second;
        ion_label_to_stage[row.ion_label] = row.ion;
    }

    // pprint(10) numbers ions in the complete global Type-12 source encounter
    // order, including zero-abundance elements that are skipped by the final
    // printing predicate.  For atomic number Z the source owns Z Type-12 ion
    // records before the fully stripped state, so the one-based global index
    // is triangular(Z-1)+stage.  Do not derive this offset from the retained
    // active element inventory: doing so incorrectly numbered C I..C VI as
    // 4..9 instead of the canonical 16..21 when Li/Be/B were absent.
    auto global_type12_ion_index = [](int z, int stage) {
        return z > 0 && stage > 0 ? (z * (z - 1)) / 2 + stage : stage;
    };

    auto element_label_for_z = [](int z) -> std::string {
        static const std::array<const char*,30> names = {{
            "hydrogen","helium","lithium","beryllium","boron","carbon",
            "nitrogen","oxygen","fluorine","neon","sodium","magnesium",
            "aluminum","silicon","phosphorus","sulfur","chlorine","argon",
            "potassium","calcium","scandium","titanium","vanadium","chromium",
            "manganese","iron","cobalt","nickel","copper","zinc"
        }};
        return z >= 1 && z <= static_cast<int>(names.size()) ? names[static_cast<std::size_t>(z-1)] : ("z" + std::to_string(z));
    };

    // pprint(14) and pprint(18) walk nplin in source order.  The apparent
    // lrtyp exclusion in pprint.f90 occurs after drd() has visited the parent
    // ion and element and therefore does not act as a line-rate-type filter.
    // The observable source inventory is the same active-element/wavelength
    // inventory already qualified for pprint(15).
    std::vector<const xstar_run_state::LineIdentityState*> source_lines;
    source_lines.reserve(state.line_identities.size());
    for (const auto& id : state.line_identities) {
        const double wave = std::abs(id.wavelength_angstrom);
        const auto owner = ion_label_to_z.find(id.ion_label);
        if (id.line_index > 0 && wave > 0.1 && wave < 9.0e9 &&
            owner != ion_label_to_z.end() && active_z(owner->second, 1.0e-36)) {
            source_lines.push_back(&id);
        }
    }
    std::stable_sort(source_lines.begin(), source_lines.end(), [](const auto* a, const auto* b) {
        return a->line_index < b->line_index;
    });

    auto flat_plane = [](const std::vector<double>& values, std::size_t planes,
                         std::size_t plane, std::size_t slot) {
        if (planes == 0u || values.empty() || values.size() % planes != 0u) return 0.0;
        const std::size_t stride = values.size() / planes;
        const std::size_t at = plane * stride + slot;
        return at < values.size() && std::isfinite(values[at]) ? values[at] : 0.0;
    };
    auto vector_value = [](const std::vector<double>& values, std::size_t slot) {
        return slot < values.size() && std::isfinite(values[slot]) ? values[slot] : 0.0;
    };

    if (lprint >= 2) {
        out << "\n print option:14\nline opacities and emissivities (erg/cm**3/sec/10**38)\n";
        out << " index,wavelength,energy,ion,opacity,rec. em.,coll. em.,fl. em.,di. em.,cx. em.\n";
        // nlsvn is the complete source database line capacity; the native
        // lowered state intentionally retains only active line identities.
        // Preserve the source row surface without inventing the unavailable
        // inactive capacity scalar.
        out << " retained active source line inventory " << source_lines.size() << "\n";
        const std::size_t rcem_stride = ws.rcem.size() >= 2u ? ws.rcem.size() / 2u : 0u;
        for (const auto* id : source_lines) {
            const std::size_t slot = static_cast<std::size_t>(id->line_index);
            const double op = vector_value(ws.oplin, slot);
            const double r0 = rcem_stride ? flat_plane(ws.rcem, 2u, 0u, slot) : 0.0;
            const double r1 = rcem_stride ? flat_plane(ws.rcem, 2u, 1u, slot) : 0.0;
            const double energy = 12398.4016 / std::max(std::abs(id->wavelength_angstrom), 1.0e-24);
            out << std::setw(10) << id->line_index << std::setw(13) << std::uppercase
                << std::scientific << std::setprecision(5) << id->wavelength_angstrom
                << std::setw(13) << energy << " " << std::left << std::setw(9)
                << id->ion_label.substr(0,9) << std::right << std::setw(13) << op
                << std::setw(13) << r0 << std::setw(13) << r1 << "\n";
        }
        out << "\n print option:21\n level opacities and emissivities\n";
        out << "index,energy,ion,level,index,emiss in,emiss out,threshold opacity,absorbed energy,depth in, depth out\n";
        // pprint(21) walks each ion's rate-type-7 npfi chain and publishes
        // kkkl=npconi2(ml).  That identity surface is state.rrc_identities.
        // source_rrc_identities instead follows the global npcon ordinal used
        // by writespectra4/FITS publication; substituting it here changes both
        // the ion label and the reusable npconi2 slot inventory.
        const auto& source_rrcs = state.rrc_identities.empty()
            ? state.source_rrc_identities : state.rrc_identities;
        std::vector<const xstar_run_state::RrcIdentityState*> rrcs;
        rrcs.reserve(source_rrcs.size());
        for (const auto& id : source_rrcs) {
            const auto owner = ion_label_to_z.find(id.ion_label);
            const bool source_rate7 = id.rate_type == 0 || id.rate_type == 7;
            if (source_rate7 && id.continuum_index > 0 && owner != ion_label_to_z.end() && active_z(owner->second, 1.0e-10)) {
                rrcs.push_back(&id);
            }
        }
        std::stable_sort(rrcs.begin(), rrcs.end(), [&](const auto* a, const auto* b) {
            const int za = ion_label_to_z.count(a->ion_label) ? ion_label_to_z.at(a->ion_label) : 0;
            const int zb = ion_label_to_z.count(b->ion_label) ? ion_label_to_z.at(b->ion_label) : 0;
            if (za != zb) return za < zb;
            const int sa = ion_label_to_stage.count(a->ion_label) ? ion_label_to_stage.at(a->ion_label) : 0;
            const int sb = ion_label_to_stage.count(b->ion_label) ? ion_label_to_stage.at(b->ion_label) : 0;
            if (sa != sb) return sa < sb;
            if (a->continuum_index != b->continuum_index) return a->continuum_index < b->continuum_index;
            return a->source_record < b->source_record;
        });
        for (const auto* id : rrcs) {
            const std::size_t slot = static_cast<std::size_t>(id->continuum_index);
            const double cin = flat_plane(ws.cemab, 2u, 0u, slot);
            const double cout = flat_plane(ws.cemab, 2u, 1u, slot);
            const double opa = vector_value(ws.opakab, slot);
            const double absorbed = vector_value(ws.cabab, slot);
            if (!(opa > 1.0e-49 || absorbed > 1.0e-49 || cin > 1.0e-49 || cout > 1.0e-49)) continue;
            const double tin = flat_plane(ws.tauc, 2u, 0u, slot);
            const double tout = flat_plane(ws.tauc, 2u, 1u, slot);
            out << std::setw(7) << id->continuum_index << std::setw(6) << id->level_global_index
                << " " << std::left << std::setw(9) << id->ion_label.substr(0,9) << std::right
                << std::setw(6) << id->lower_local_index << std::setw(6) << id->upper_local_index
                << " " << std::left << std::setw(20) << id->lower_level.substr(0,20)
                << " " << std::setw(20) << id->upper_level.substr(0,20) << std::right
                << std::setw(13) << std::uppercase << std::scientific << std::setprecision(5)
                << id->threshold_ev << std::setw(13) << cin << std::setw(13) << cout
                << std::setw(13) << opa << std::setw(13) << absorbed
                << std::setw(13) << tin << std::setw(13) << tout << "\n";
        }

        out << "\n print option: 7\n  level populations \n";
        out << " ion                      level               e_exc population\n";
        // pprint(7), like fstepr, walks every source ion/local-level npilev
        // role.  Adjacent ions can share a compact continuum/next-ground row,
        // so the compact level_identities surface loses legitimate continuum
        // publication roles.  detail_level_identities retains exactly those
        // source roles and was introduced for this same npilev ownership.
        const auto& source_levels = !state.detail_level_identities.empty()
            ? state.detail_level_identities : state.level_identities;
        std::vector<const xstar_run_state::LevelIdentityState*> levels;
        for (const auto& level : source_levels) {
            if (level.global_index <= 0 || !active_z(level.atomic_number, 1.0e-10)) continue;
            const std::size_t slot = static_cast<std::size_t>(level.global_index - 1);
            const double pop = vector_value(eval->source_global_xilevg, slot);
            if (!(pop > 1.0e-64)) continue;
            levels.push_back(&level);
        }
        std::stable_sort(levels.begin(), levels.end(), [&](const auto* a, const auto* b) {
            if (a->atomic_number != b->atomic_number) return a->atomic_number < b->atomic_number;
            const int sa = ion_label_to_stage.count(a->ion_label) ? ion_label_to_stage.at(a->ion_label) : 0;
            const int sb = ion_label_to_stage.count(b->ion_label) ? ion_label_to_stage.at(b->ion_label) : 0;
            if (sa != sb) return sa < sb;
            if (a->upper_index != b->upper_index) return a->upper_index < b->upper_index;
            return a->global_index < b->global_index;
        });
        for (const auto* level : levels) {
            const std::size_t slot = static_cast<std::size_t>(level->global_index - 1);
            const double pop = vector_value(eval->source_global_xilevg, slot);
            const double rn = vector_value(eval->source_global_rnisg, slot);
            out << std::setw(7) << level->global_index << " " << std::left << std::setw(9)
                << level->ion_label.substr(0,9) << " " << std::setw(20)
                << level->level_label.substr(0,20) << std::right << std::setw(13)
                << std::uppercase << std::scientific << std::setprecision(5)
                << level->excitation_ev << std::setw(13) << pop << std::setw(13) << rn << "\n";
        }
        out << " done with 7\n";

        out << "\n print option:10\n ion abundances and  rates (/sec)\n";
        out << " index, ion, abundance, recombination, ionization,\n";
        for (const auto& [z, fractions] : eval->source_ion_stage_fractions) {
            if (!active_z(z, 1.0e-15)) continue;
            const int nstage = std::min<int>(z, static_cast<int>(fractions.size()));
            for (int stage = 1; stage <= nstage; ++stage) {
                const auto key = std::make_pair(z, stage);
                const auto found = ion_labels.find(key);
                const int global_ion = global_type12_ion_index(z, stage);
                const std::string label = found != ion_labels.end() ? found->second : ("z" + std::to_string(z) + "_" + std::to_string(stage));
                out << std::setw(5) << global_ion << " " << std::left << std::setw(9) << label.substr(0,9)
                    << std::right << std::setw(16) << std::uppercase << std::scientific << std::setprecision(8)
                    << fractions[static_cast<std::size_t>(stage-1)]
                    << std::setw(16) << 0.0 << std::setw(16) << 0.0 << " retained-rate-components-unavailable\n";
            }
        }
        out << " heating and cooling rates (erg/sec)\n";
        out << " index element   heating         cooling        heating-cooling\n";
        for (const auto& item : eval->element_thermal_products) {
            if (!active_z(item.element_z, 1.0e-36)) continue;
            out << std::setw(5) << item.element_z << " " << std::left << std::setw(10) << element_label_for_z(item.element_z) << std::right
                << std::setw(16) << std::uppercase << std::scientific << std::setprecision(8) << item.heating
                << std::setw(16) << item.cooling << std::setw(16) << (item.heating-item.cooling) << "\n";
        }
        out << "      compton " << std::uppercase << std::scientific << std::setprecision(8)
            << eval->compton_heating << " " << eval->compton_cooling << "\n";
        out << "      free-free retained continuum components\n";
        out << "      total " << eval->total_heating << " " << eval->total_cooling << "\n";
        // pprint.f90 option 26 branches directly to the common return after
        // printing the option marker, so no body follows in the current source.
        out << "\n print option:26\n";
    }

    if (lprint >= 3) {
        out << "\n print option: 0\n";
        const std::size_t n = std::min<std::size_t>(
            static_cast<std::size_t>(std::max<long long>(0LL, std::llround(parameter_number(state, "ncn2", static_cast<double>(eval->radiation_energy_ev.size()))))),
            eval->radiation_energy_ev.size());
        out << "\n print option: 4\n continuum opacity and emissivities (/cm**3/sec/10**38)\n";
        out << "channel, energy, opacity, scattered, rec. in, rec. out, source\n";
        for (std::size_t i = 1u; i < n; ++i) {
            const double op = vector_value(ws.opakc, i);
            const double rin = flat_plane(ws.rccemis, 2u, 0u, i);
            const double rout = flat_plane(ws.rccemis, 2u, 1u, i);
            out << std::setw(7) << (i+1u) << std::setw(13) << std::uppercase << std::scientific
                << std::setprecision(5) << eval->radiation_energy_ev[i] << std::setw(13) << op
                << std::setw(13) << 0.0 << std::setw(13) << rin << std::setw(13) << rout << "\n";
        }
        out << "\n print option: 6\n continuum luminosities (/sec/10**38) and depths\n";
        out << " real quantities are as follows:\n";
        for (std::size_t i = 0u; i < n; ++i) {
            out << std::setw(7) << (i+1u) << std::setw(13) << std::uppercase << std::scientific
                << std::setprecision(5) << eval->radiation_energy_ev[i];
            for (std::size_t plane = 0u; plane < 5u; ++plane) out << std::setw(13) << flat_plane(ws.zrems, 5u, plane, i);
            out << std::setw(13) << flat_plane(ws.dpthc, 2u, 0u, i)
                << std::setw(13) << flat_plane(ws.dpthc, 2u, 1u, i) << "\n";
        }
        out << " norms: retained source-normalization scalars unavailable\n";
    }

    if (lprint >= 4) {
        out << "\n print option:18\n line wavelengths and levels\n";
        out << "       index wavelength  ion            lo                  up\n";
        for (const auto* id : source_lines) {
            out << std::setw(10) << id->line_index << std::setw(13) << std::uppercase
                << std::scientific << std::setprecision(5) << id->wavelength_angstrom << " "
                << std::left << std::setw(9) << id->ion_label.substr(0,9)
                << std::setw(25) << id->lower_level.substr(0,25)
                << std::setw(25) << id->upper_level.substr(0,25) << std::right
                << std::setw(7) << id->lower_local_index << std::setw(7) << id->upper_local_index << "\n";
        }

        out << "\n print option:29\n rates\n doing pprint(29)\n";
        std::vector<const xstar_run_state::RecordProductDiagnosticState*> rates;
        for (const auto& row : eval->record_product_diagnostics) {
            // pprint(29) prints the final source rates(1,ml) workspace.  The
            // detailed calc_hmc_ion pass never calls UCalc for rate 8, rate
            // 15, or the rate-1/Type-53 ownership case, so those source rates
            // remain zero.  The retained native diagnostic inventory is wider
            // than that source pass and also contains records outside the
            // source active ion-stage window; exclude both classes before
            // applying the literal abs(rates(1,ml)) > 1.e-34 predicate.
            if (row.rate_type == 8 || row.rate_type == 15 ||
                (row.rate_type == 1 && row.data_type == 53)) continue;
            if (const auto active = eval->source_detail_active_windows.find(row.element_z);
                active != eval->source_detail_active_windows.end()) {
                const int min_stage = active->second[0];
                const int max_stage = active->second[1];
                if (row.ion_stage < min_stage || row.ion_stage > max_stage) continue;
            }
            if (std::abs(row.ans[0]) > 1.0e-34) rates.push_back(&row);
        }
        std::stable_sort(rates.begin(), rates.end(), [](const auto* a, const auto* b) {
            if (a->record != b->record) return a->record < b->record;
            return a->source_position < b->source_position;
        });
        for (const auto* row : rates) {
            out << std::setw(10) << row->record << " z" << row->element_z << "_" << row->ion_stage
                << std::setw(8) << row->data_type << std::setw(8) << row->rate_type
                << std::setw(8) << row->lower_row << std::setw(8) << row->upper_row;
            for (double value : row->ans) out << std::setw(13) << std::uppercase << std::scientific << std::setprecision(5) << value;
            out << "\n";
        }
        out << " done with pprint(29)\n";

        out << "\n print option:30\n auger and fluorescence yields\n";
        out << "ion     K shell pi rate  k fluorescence rate auger rate fluorescence yield\n";
        for (const auto& [z, fractions] : eval->source_ion_stage_fractions) {
            if (!active_z(z, 1.0e-34)) continue;
            const int nstage = std::min<int>(z, static_cast<int>(fractions.size()));
            for (int stage = 1; stage < nstage; ++stage) {
                const double fraction = fractions[static_cast<std::size_t>(stage-1)];
                if (!(fraction > 1.0e-12)) continue;
                const auto found = ion_labels.find({z,stage});
                const std::string label = found != ion_labels.end() ? found->second : ("z" + std::to_string(z) + "_" + std::to_string(stage));
                // The native retained state does not expose the temporary
                // K-shell aggregation performed only inside pprint(30).  Emit
                // the source-selected ion inventory while explicitly marking
                // those non-retained scalar fields unavailable; do not invent
                // numerical yields.
                out << " " << std::left << std::setw(8) << label.substr(0,8) << std::right
                    << " retained-k-shell-scalars-unavailable\n";
            }
        }
    }
    out.unsetf(std::ios::floatfield);
    out << std::setprecision(17);
}

void append_source_like_timing_footer(std::ofstream& out,
                                      double measured_run_seconds,
                                      double formatter_seconds) {
    const double total_seconds = std::max(0.0, measured_run_seconds) + std::max(0.0, formatter_seconds);
    out << "\nnative output timing (measured):\n";
    out << "  native_step_log_formatter " << std::setprecision(9) << formatter_seconds << "\n";
    out << "  native_controller_and_fits " << std::setprecision(9) << measured_run_seconds << "\n";
    out << "total time " << std::setprecision(9) << total_seconds << "\n";
    out << "total time human " << human_time(total_seconds) << "\n";
}

} // namespace

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write the native STEP diagnostic/publication log from the committed radial/product state using the accepted per-option publication semantics.
// Reference context: XSTAR Manual ch5 (output/print controls) plus ss11.5-11.6 for the reported line/continuum/RRC quantities.
// XSTAR-FUNCTION-COMMENT-END
Result write_native_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    require_legacy_pprint_payload(state);
    const auto started = std::chrono::steady_clock::now();
    std::filesystem::create_directories(output_dir);
    const auto path = output_dir / "xout_step.log";
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create native xout_step.log");
    out << std::setprecision(17);
    out << " xstar_tools version " << state.release << "\n";
    std::size_t source_nry = 0;
    std::size_t output_nry = 0;
    if (!state.radial_zones.empty()) {
        const auto& eval = state.radial_zones.back().accepted_controller.evaluation;
        source_nry = eval.source_workspace.native_continuum_count > 0
            ? eval.source_workspace.native_continuum_count
            : eval.source_continuum_tau_workspace_count;
        output_nry = eval.radiation_energy_ev.size();
    }
    out << " nry= " << std::setw(11) << source_nry << std::setw(12) << output_nry << "\n";
    out << " Loading Atomic Database...\n";
    out << " Atomic Data Version: " << read_atomic_data_version(state.atomic_database_path) << "\n";
    out << " in readtbl:\n";
    out << " native readtbl pointer/reals/integers/characters counters: unavailable (not retained by native ATDB lowering)\n";
    out << " native atomic line/rrc database totals: unavailable (not retained by native ATDB lowering)\n";
    out << " done with setptrs\n";
    append_native_input_parameters(out, state);
    append_native_radial_summary(out, output_dir, state);
    const int lprint = static_cast<int>(std::llround(parameter_number(state, "lprint", 0.0)));
    if (lprint >= 0) out << "\n print option:11\n";
    if (lprint >= 1) append_native_product_sections(out, output_dir, state);
    append_native_lprint_extra_sections(out, state, lprint);
    const char* debug_product_summary = std::getenv("XSTAR_DEBUG_PRODUCT_STATE_SUMMARY");
    const bool emit_product_state_summary =
        debug_product_summary && std::string(debug_product_summary) == "1";
    if (emit_product_state_summary) {
        for (const auto& line : state.legacy_pprint.buffered_lines) {
            out << line << '\n';
        }
    }
    const double formatter_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();
    append_source_like_timing_footer(out, state.measured_run_seconds, formatter_seconds);
    out.close();

    state.xout_step_computed_from_native_state = true;
    state.xout_step_timing_values_measured = true;
    Result result;
    result.lines_written = count_lines(path);
    result.prefix_exact_except_version = false;
    result.full_raw_exact_asset_written = false;
    result.full_log_complete = state.legacy_pprint.complete() && !state.legacy_pprint.buffered_lines.empty();
    result.computed_from_native_state = true;
    result.timing_values_measured = true;
    result.product_parity_qualified = false;
    return result;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write python step log from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
Result write_python_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    return write_native_step_log(output_dir, state);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write python step log prefix from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ch5 and ss11.5-11.6; publication helper, not a new physical rate.
// XSTAR-FUNCTION-COMMENT-END
Result write_python_step_log_prefix(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    return write_native_step_log(output_dir, state);
}

} // namespace xstar_step_log
