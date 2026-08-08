// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: ucalc.f90; calc_hmc_ion.f90; calc_emisab_ion.f90; linopac.f90
// Role: Modular native rate-to-matrix, line-emissivity, and selected line-opacity kernels.
// Relation: Source-equivalent low-level kernels; unsuffixed REAL literal behavior and one-based matrix
//   endpoints are preserved where observable.
// Concordance: MATRIX-001; EMISAB-001; TYPE50-001
// Qualification: modular-kernel qualification leading to 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

// Modular rates backend for xstar_atomic/source_port.
//
// v0.5.54 adds the first real Mg record_type=7 C++ kernel.  The Python
// source-faithful ucalc implementation still evaluates the physical rate
// formulas (ans1..ans6).  This backend then performs the repeated
// calc_hmc_ion rate-to-matrix construction for Mg continuum/RRC records in a
// compact batch, preserving XSTAR one-based indexing and ipmat endpoint
// clamping.  Keeping this as a plain C ABI lets the same file be loaded from
// Python with ctypes and later linked into a standalone xstar_tools engine.

#include <cstddef>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <vector>

namespace {
constexpr int XSTAR_RATES_ABI_VERSION = 2;
constexpr int XSTAR_RATES_FEATURE_SKELETON = 1;
constexpr int XSTAR_RATES_FEATURE_MG_TYPE7_MATRIX_TERMS = 2;
constexpr int XSTAR_RATES_FEATURE_MG_TYPE4_LINE_EMISSIVITY = 4;
constexpr int XSTAR_RATES_FEATURE_LINOPAC_PROFILE = 8;
constexpr int XSTAR_RATES_FEATURE_MG_TYPE4_TYPE50_COARSE = 16;

void write_message(char* errbuf, std::size_t errbuf_size, const char* message) {
    if (errbuf == nullptr || errbuf_size == 0) {
        return;
    }
    std::snprintf(errbuf, errbuf_size, "%s", message == nullptr ? "" : message);
}

bool finite6(double a, double b, double c, double d, double e, double f) {
    return std::isfinite(a) && std::isfinite(b) && std::isfinite(c) &&
           std::isfinite(d) && std::isfinite(e) && std::isfinite(f);
}

// Fortran unsuffixed REAL literals in the original XSTAR source are default
// real before assignment/use in REAL(8) expressions.  Mirror the Python
// source-faithful _source_real policy by rounding those literals to float32
// and promoting back to double.  Do not use this for D-suffixed literals.
inline double source_real_literal(double value) {
    return static_cast<double>(static_cast<float>(value));
}
}  // namespace

extern "C" {

int xstar_rates_abi_version() {
    return XSTAR_RATES_ABI_VERSION;
}

const char* xstar_rates_backend_name() {
    return "xstar_rates_mg_type7_type4_linopac_type50_voigt_pow3_exact_v2";
}

int xstar_rates_feature_flags() {
    return XSTAR_RATES_FEATURE_SKELETON | XSTAR_RATES_FEATURE_MG_TYPE7_MATRIX_TERMS | XSTAR_RATES_FEATURE_MG_TYPE4_LINE_EMISSIVITY | XSTAR_RATES_FEATURE_LINOPAC_PROFILE | XSTAR_RATES_FEATURE_MG_TYPE4_TYPE50_COARSE;
}

int xstar_rates_eval_mg(
    int n_ions,
    int n_records,
    const void* compact_payload,
    std::size_t compact_payload_size,
    char* errbuf,
    std::size_t errbuf_size
) {
    (void)compact_payload;
    (void)compact_payload_size;
    if (n_ions < 0 || n_records < 0) {
        write_message(errbuf, errbuf_size, "xstar_rates_eval_mg received negative dimensions");
        return 2;
    }
    write_message(errbuf, errbuf_size, "xstar_rates_eval_mg ABI OK; use xstar_rates_build_mg_type7_terms for v0.5.54 kernel");
    return 0;
}

// Build four source calc_hmc_ion matrix terms for each evaluated Mg
// record_type=7 result.  All arrays use one-based XSTAR endpoint semantics;
// output term rows are flattened with four rows per record and 16 int64
// columns plus 4 double columns:
//
// int output columns:
//   term_index, record, data_type, rate_type, ion_index, ion_stage,
//   role_code, row, column, idest1, idest2, lower_endpoint, upper_endpoint,
//   source_row_unclamped, source_column_unclamped, source_ipmat_clamped
// double output columns:
//   aj1, aj2, cj, cj2
//
// role_code follows Python MatrixTerm construction:
//   1 forward_offdiag, 2 reverse_offdiag, 3 forward_diag_loss, 4 reverse_diag_loss
int xstar_rates_build_mg_type7_terms(
    int n_records,
    int basis_n_rows,
    int term_start,
    const long long* record,
    const long long* data_type,
    const long long* ion_index,
    const long long* ion_stage,
    const long long* compact_start,
    const long long* idest1,
    const long long* idest2,
    const double* ans1,
    const double* ans2,
    const double* ans3,
    const double* ans4,
    const double* ans5,
    const double* ans6,
    double xpx,
    long long* out_i64,
    double* out_f64,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_records < 0 || basis_n_rows <= 0 || term_start <= 0) {
        write_message(errbuf, errbuf_size, "invalid dimensions for xstar_rates_build_mg_type7_terms");
        return 2;
    }
    if (!record || !data_type || !ion_index || !ion_stage || !compact_start ||
        !idest1 || !idest2 || !ans1 || !ans2 || !ans3 || !ans4 || !ans5 || !ans6 ||
        !out_i64 || !out_f64) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_rates_build_mg_type7_terms");
        return 3;
    }
    if (!std::isfinite(xpx)) {
        write_message(errbuf, errbuf_size, "non-finite density scale passed to xstar_rates_build_mg_type7_terms");
        return 4;
    }

    for (int k = 0; k < n_records; ++k) {
        const long long id1 = idest1[k];
        const long long id2 = idest2[k];
        if (id1 <= 0 || id2 <= 0) {
            write_message(errbuf, errbuf_size, "non-positive endpoint passed to xstar_rates_build_mg_type7_terms");
            return 5;
        }
        if (!finite6(ans1[k], ans2[k], ans3[k], ans4[k], ans5[k], ans6[k])) {
            write_message(errbuf, errbuf_size, "non-finite rate answer passed to xstar_rates_build_mg_type7_terms");
            return 6;
        }

        const long long raw_lower = compact_start[k] + id1 - 1;
        const long long raw_upper = compact_start[k] + id2 - 1;
        long long lower = raw_lower;
        long long upper = raw_upper;
        if (lower > basis_n_rows) lower = basis_n_rows;
        if (upper > basis_n_rows) upper = basis_n_rows;
        if (lower <= 0 || upper <= 0) {
            write_message(errbuf, errbuf_size, "endpoint maps outside compact basis in xstar_rates_build_mg_type7_terms");
            return 7;
        }
        const long long clamped_forward = (raw_upper != upper || raw_lower != lower) ? 1LL : 0LL;

        const double a1 = ans1[k];
        const double a2 = ans2[k];
        const double c3 = ans3[k];
        const double c4 = ans4[k];
        const double c5 = ans5[k];
        const double c6 = ans6[k];

        const long long rows[4] = {upper, lower, lower, upper};
        const long long cols[4] = {lower, upper, lower, upper};
        const long long raw_rows[4] = {raw_upper, raw_lower, raw_lower, raw_upper};
        const long long raw_cols[4] = {raw_lower, raw_upper, raw_lower, raw_upper};
        const long long role[4] = {1, 2, 3, 4};
        const double aj1[4] = {a1, a2, -a1, -a2};
        const double aj2[4] = {a2, a1, -a1, -a2};
        const double cj[4] = {0.0, 0.0, c4 * xpx, -c3 * xpx};
        const double cj2[4] = {0.0, 0.0, c6 * xpx, -c5 * xpx};

        for (int j = 0; j < 4; ++j) {
            const int out_row = 4 * k + j;
            long long* oi = out_i64 + 16 * out_row;
            double* of = out_f64 + 4 * out_row;
            oi[0] = static_cast<long long>(term_start + out_row);
            oi[1] = record[k];
            oi[2] = data_type[k];
            oi[3] = 7;
            oi[4] = ion_index[k];
            oi[5] = ion_stage[k];
            oi[6] = role[j];
            oi[7] = rows[j];
            oi[8] = cols[j];
            oi[9] = id1;
            oi[10] = id2;
            oi[11] = id1;
            oi[12] = id2;
            oi[13] = raw_rows[j];
            oi[14] = raw_cols[j];
            oi[15] = clamped_forward;
            of[0] = aj1[j];
            of[1] = aj2[j];
            of[2] = cj[j];
            of[3] = cj2[j];
        }
    }
    write_message(errbuf, errbuf_size, "xstar_rates_build_mg_type7_terms evaluated");
    return 0;
}


// Build per-line source scalar products for Mg record_type=4 line emissivity.
// Python still owns source-faithful ucalc and linopac/profile side effects in
// v0.5.58.  The v0.5.59 Python caller batches records before this C ABI owns the repeated scalar arithmetic after ucalc:
//   opakb1 = opakab * abund_lower
//   net = ans2 * abund_upper - ans1 * abund_lower
//   rcem1/rcem2 = max(net * energy_eV * erg_per_ev * escape_prob, 0)
//   flinel_delta = (rcem1 + rcem2) * 2 / bin_width_eV / erg_per_ev
// Output rows: 8 int64 columns and 5 double columns per input record.
int xstar_rates_build_mg_type4_line_emissivity(
    int n_records,
    const long long* record,
    const long long* data_type,
    const long long* ion_index,
    const long long* ion_stage,
    const long long* line_index,
    const long long* nb1,
    const double* ans1,
    const double* ans2,
    const double* opakab,
    const double* abund_lower,
    const double* abund_upper,
    const double* ptmp1,
    const double* ptmp2,
    const double* energy_ev,
    const double* bin_width_ev,
    double erg_per_ev,
    long long* out_i64,
    double* out_f64,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_records < 0) {
        write_message(errbuf, errbuf_size, "invalid n_records for xstar_rates_build_mg_type4_line_emissivity");
        return 2;
    }
    if (!record || !data_type || !ion_index || !ion_stage || !line_index || !nb1 ||
        !ans1 || !ans2 || !opakab || !abund_lower || !abund_upper || !ptmp1 || !ptmp2 ||
        !energy_ev || !bin_width_ev || !out_i64 || !out_f64) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_rates_build_mg_type4_line_emissivity");
        return 3;
    }
    if (!std::isfinite(erg_per_ev) || erg_per_ev <= 0.0) {
        write_message(errbuf, errbuf_size, "invalid erg_per_ev passed to xstar_rates_build_mg_type4_line_emissivity");
        return 4;
    }
    for (int k = 0; k < n_records; ++k) {
        const double a1 = ans1[k];
        const double a2 = ans2[k];
        const double op = opakab[k];
        const double ab1 = abund_lower[k];
        const double ab2 = abund_upper[k];
        const double p1 = ptmp1[k];
        const double p2 = ptmp2[k];
        const double e = energy_ev[k];
        const double w = bin_width_ev[k];
        if (!std::isfinite(a1) || !std::isfinite(a2) || !std::isfinite(op) ||
            !std::isfinite(ab1) || !std::isfinite(ab2) || !std::isfinite(p1) ||
            !std::isfinite(p2) || !std::isfinite(e) || !std::isfinite(w) || w <= 0.0) {
            write_message(errbuf, errbuf_size, "non-finite or invalid line emissivity scalar input");
            return 5;
        }
        const double opakb1 = op * ab1;
        const double net = a2 * ab2 - a1 * ab1;
        double rcem1 = net * e * erg_per_ev * p1;
        double rcem2 = net * e * erg_per_ev * p2;
        if (rcem1 < 0.0) rcem1 = 0.0;
        if (rcem2 < 0.0) rcem2 = 0.0;
        const double flinel_delta = (rcem1 + rcem2) * 2.0 / w / erg_per_ev;
        long long* oi = out_i64 + 8 * k;
        double* of = out_f64 + 5 * k;
        oi[0] = record[k];
        oi[1] = data_type[k];
        oi[2] = 4;
        oi[3] = ion_index[k];
        oi[4] = ion_stage[k];
        oi[5] = line_index[k];
        oi[6] = nb1[k];
        oi[7] = 1;
        of[0] = opakb1;
        of[1] = net;
        of[2] = rcem1;
        of[3] = rcem2;
        of[4] = flinel_delta;
    }
    write_message(errbuf, errbuf_size, "xstar_rates_build_mg_type4_line_emissivity evaluated");
    return 0;
}



static double xstar_rates_voigte(double vs, double a) {
    static const double ak[19] = {
        -1.12470432, -0.15516677, 3.28867591, -2.34357915, 0.42139162,
        -4.48480194, 9.39456063, -6.61487486, 1.98919585, -0.22041650,
        0.554153432, 0.278711796, -0.188325687, 0.042991293,
        -0.003278278, 0.979895023, -0.962846325, 0.532770573,
        -0.122727278
    };
    const double sqp = 1.772453851;
    const double sq2 = 1.414213562;
    const double v = std::abs(vs);
    const double aa = a;
    const double u = aa + v;
    const double v2 = v * v;
    if (aa == 0.0) {
        return v2 >= 100.0 ? 0.0 : std::exp(-v2);
    }
    if (aa <= 0.2 && v >= 5.0) {
        // Python's accepted voigte translation spells the denominator as
        // ``v2**3``.  Use the corresponding libm power operation here rather
        // than reassociating it into three multiplications; the latter shifts
        // far-wing results by a few binary64 ULPs and can cross a float32
        // science-output rounding boundary after many opacity additions.
        return aa * (15.0 + 6.0 * v2 + 4.0 * v2 * v2) /
               (4.0 * std::pow(v2, 3.0) * sqp);
    }
    // voigte.f90 label 120 is reachable only for a>0.2.
    if (aa > 0.2 && (aa > 1.4 || u > 3.2)) {
        const double a2 = aa * aa;
        const double uu = sq2 * (a2 + v2);
        const double u2 = 1.0 / (uu * uu);
        return sq2 / sqp * aa / uu * (1.0 + u2 * (3.0 * v2 - a2) + u2 * u2 * (15.0 * v2 * v2 - 30.0 * v2 * a2 + 3.0 * a2 * a2));
    }
    const double ex = v2 >= 100.0 ? 0.0 : std::exp(-v2);
    double quo = 1.0;
    int start = 0;
    if (v >= 2.4) {
        quo = 1.0 / (v2 - 1.5);
        start = 10;
    } else if (v >= 1.3) {
        start = 5;
    }
    const double h1 = quo * (ak[start] + v * (ak[start + 1] + v * (ak[start + 2] + v * (ak[start + 3] + v * ak[start + 4]))));
    if (aa <= 0.2) {
        return h1 * aa + ex * (1.0 + aa * aa * (1.0 - 2.0 * v2));
    }
    const double pqs = 2.0 / sqp;
    const double h1p = h1 + pqs * ex;
    const double h2p = pqs * h1p - 2.0 * v2 * ex;
    const double h3p = (pqs * (1.0 - ex * (1.0 - 2.0 * v2)) - 2.0 * v2 * h1p) / 3.0 + pqs * h2p;
    const double h4p = (2.0 * v2 * v2 * ex - pqs * h1p) / 3.0 + pqs * h3p;
    const double psi = ak[15] + aa * (ak[16] + aa * (ak[17] + aa * ak[18]));
    return psi * (ex + aa * (h1p + aa * (h2p + aa * (h3p + aa * h4p))));
}

static int xstar_rates_huntf(const double* xx, int n, double x) {
    if (!xx || n < 2) return 1;
    const double floor = 1.0e-24;
    const double xx1 = xx[0];
    const double xx2 = xx[1];
    const double xxn = xx[n - 1];
    const double xf = x;
    const double xtmp = std::max(xf, xx2);
    int jlo = 1;
    if (xf < floor || xx1 <= floor || xxn <= floor) return jlo;
    jlo = static_cast<int>((n - 1) * std::log(xtmp / xx1) / std::log(xxn / xx1)) + 1;
    if (jlo < n) {
        const double tst = std::abs(std::log(xf / (floor + xx[jlo - 1])));
        const double tst2 = std::abs(std::log(xf / (floor + xx[jlo])));
        if (tst2 < tst) ++jlo;
    }
    if (jlo < 1) jlo = 1;
    if (jlo > n) jlo = n;
    return jlo;
}

static int xstar_rates_nbinc(double e, const double* epi, int ncn2) {
    const int n = static_cast<int>(ncn2);
    const int numcon2 = std::max(2, n / 50);
    const int numcon3 = n - numcon2;
    if (numcon3 < 2) return 1;
    return xstar_rates_huntf(epi, numcon3, e);
}

// Apply the source linopac full-profile opacity handoff for one line.
// v0.5.65 supports both the Gaussian branch and the source voigte.f90
// natural-width/Voigt branch, so Mg type-4 data_type=50 can use the shared
// library for the linopac side effect instead of returning a Python fallback.
int xstar_rates_apply_linopac_profile(
    double optpp,
    double rcem1,
    double rcem2,
    double line_energy_ev,
    double vturb_km_s,
    double temperature_1e4k,
    double atomic_mass_amu,
    double natural_width_ev,
    const double* seed_profiles,
    int seed_radius,
    const double* epi,
    int ncn2,
    double* opakc,
    double* rccemis,
    long long* out_i64,
    double* out_f64,
    char* errbuf,
    std::size_t errbuf_size
) {
    (void)rcem1;
    (void)rcem2;
    if (!seed_profiles || !epi || !opakc || !rccemis || !out_i64 || !out_f64) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_rates_apply_linopac_profile");
        return 3;
    }
    const int n = static_cast<int>(ncn2);
    if (n < 3 || !std::isfinite(optpp) || !std::isfinite(line_energy_ev) ||
        !std::isfinite(vturb_km_s) || !std::isfinite(temperature_1e4k) ||
        !std::isfinite(atomic_mass_amu) || !std::isfinite(natural_width_ev) ||
        seed_radius < 0) {
        write_message(errbuf, errbuf_size, "invalid input to xstar_rates_apply_linopac_profile");
        return 4;
    }
    for (int i = 0; i < 2 * seed_radius + 1; ++i) {
        if (!std::isfinite(seed_profiles[i])) {
            write_message(errbuf, errbuf_size, "non-finite seed profile passed to xstar_rates_apply_linopac_profile");
            return 4;
        }
    }
    for (int i = 0; i < 8; ++i) out_i64[i] = 0;
    for (int i = 0; i < 12; ++i) out_f64[i] = 0.0;
    if (optpp <= 0.0 || line_energy_ev <= 0.0 || line_energy_ev <= epi[0] || line_energy_ev >= epi[n - 1]) {
        write_message(errbuf, errbuf_size, "xstar_rates_apply_linopac_profile no-op");
        return 0;
    }
    const int nbtpp = 20000;
    const double dpcrit = 1.0e-6;
    int ml1 = xstar_rates_nbinc(line_energy_ev, epi, n);
    if (ml1 < 2) ml1 = 2;
    if (ml1 > n - 1) ml1 = n - 1;
    const double mass = std::max(atomic_mass_amu, 1.0e-30);
    const double vth = 12.9 * std::sqrt(temperature_1e4k / mass);
    const double e0 = line_energy_ev;
    const double deleturb = e0 * (vturb_km_s / 3.0e5);
    const double deleth = e0 * (vth / 3.0e5);
    const double dele = std::sqrt(deleth * deleth + deleturb * deleturb);
    if (dele <= 0.0) {
        out_i64[2] = ml1;
        write_message(errbuf, errbuf_size, "xstar_rates_apply_linopac_profile no-width no-op");
        return 0;
    }
    const double aasmall = natural_width_ev / (1.0e-24 + dele) / 12.56;
    // The accepted seed contains the center sample with its stricter 1e-6
    // branch threshold. The remaining C++ scan uses linopac's 1e-9 threshold.
    const bool use_voigt = (aasmall > 1.0e-9);
    const double e00 = epi[ml1 - 1];
    const double etmp = e0;
    const double deleepi = epi[ml1] - epi[ml1 - 1];
    int ncut = static_cast<int>(deleepi / dele);
    if (ncut < 1) ncut = 1;
    if (ncut > nbtpp / 10) ncut = nbtpp / 10;
    const double deleused = deleepi / static_cast<double>(ncut);
    const double prftmp = (ml1 >= 2 && ml1 < n) ? (2.0 / (epi[ml1] - epi[ml1 - 2])) : 0.0;
    const double opsv4 = optpp * dele;
    int mlc = 0;
    int ldir = 1;
    int ldon0 = 0;
    int ldon1 = 0;
    int mlmin = nbtpp;
    int mlmax = 1;
    int ml1min = n + 1;
    int ml1max = 0;
    const int ml2 = nbtpp / 2;
    std::vector<double> etpp(nbtpp, 0.0);
    std::vector<double> optpp2(nbtpp, 0.0);
    double delet = (e00 - etmp) / dele;
    double profile = seed_profiles[0];
    etpp[ml2 - 1] = e00;
    optpp2[ml2 - 1] = optpp * profile;
    double tst = 1.0;
    while ((ldon0 * ldon1 == 0) && mlc < nbtpp / 2) {
        ++mlc;
        for (int ij = 0; ij < 2; ++ij) {
            ldir = -ldir;
            int& ldon = (ij == 0) ? ldon0 : ldon1;
            if (ldon == 1) continue;
            const int mlm = ml2 + ldir * mlc;
            const double etptst = e00 + static_cast<double>(ldir * mlc) * deleused;
            if (mlm <= nbtpp && mlm >= 1 && etptst > 0.0 && etptst < epi[n - 1]) {
                if (mlm < mlmin) mlmin = mlm;
                if (mlm > mlmax) mlmax = mlm;
                etpp[mlm - 1] = etptst;
                delet = (etptst - etmp) / dele;
                if (mlc <= seed_radius) {
                    const int seed_index = 2 * mlc - ((ldir < 0) ? 1 : 0);
                    profile = seed_profiles[seed_index];
                } else {
                    profile = use_voigt ? (xstar_rates_voigte(std::abs(delet), aasmall) / 1.772) : (std::exp(-delet * delet) / 1.772);
                }
                optpp2[mlm - 1] = optpp * profile;
                tst = profile;
            }
            const double delet_now = (dele != 0.0) ? ((etptst - etmp) / dele) : 0.0;
            if ((tst < dpcrit || mlm <= 1 || mlm >= nbtpp || etptst <= 0.0 || etptst >= epi[n - 1] ||
                 mlc > nbtpp || std::abs(delet_now) > std::max(50.0, 200.0 * aasmall)) &&
                ml1min < ml1 - 2 && ml1max > ml1 + 2 && ml1min >= 1 && ml1max <= n) {
                ldon = 1;
            }
        }
    }
    if (mlmin > mlmax) {
        out_i64[2] = ml1;
        write_message(errbuf, errbuf_size, "xstar_rates_apply_linopac_profile empty profile");
        return 0;
    }
    ml1min = xstar_rates_nbinc(etpp[mlmin - 1], epi, n);
    ml1max = xstar_rates_nbinc(etpp[mlmax - 1], epi, n);
    int ml1m = ml1min;
    if (mlmin < 2) mlmin = 2;
    if (mlmax > nbtpp) mlmax = nbtpp;
    double sume = 0.0;
    double opsum = 0.0;
    double tmpop = 0.0;
    long long updated = 0;
    double max_added = 0.0;
    for (int mlm = mlmin + 1; mlm <= mlmax; ++mlm) {
        const double tmpopo = tmpop;
        tmpop = optpp2[mlm - 1];
        const double tmpe = std::abs(etpp[mlm - 1] - etpp[mlm - 2]);
        sume += tmpe;
        const double interval_ops = (tmpop + tmpopo) * tmpe / 2.0;
        opsum += interval_ops;
        if (etpp[mlm - 1] > epi[ml1m - 1]) {
            if (sume > 1.0e-34) {
                const double optp2 = opsum / sume;
                while (etpp[mlm - 1] > epi[ml1m - 1] && ml1m < n) {
                    opakc[ml1m - 1] += optp2;
                    // Source Python also multiplies rcem contributions by zero for lfasto=2.
                    rccemis[0 * n + (ml1m - 1)] += 0.0;
                    rccemis[1 * n + (ml1m - 1)] += 0.0;
                    ++updated;
                    if (std::abs(optp2) > max_added) max_added = std::abs(optp2);
                    ++ml1m;
                }
            }
            opsum = 0.0;
            sume = 0.0;
        }
    }
    out_i64[0] = updated;
    out_i64[1] = use_voigt ? 2 : 1;
    out_i64[2] = ml1;
    out_i64[3] = nbtpp;
    out_i64[4] = ncut;
    out_i64[5] = ml1min;
    out_i64[6] = ml1max;
    out_i64[7] = mlmax - mlmin + 1;
    out_f64[0] = max_added;
    out_f64[1] = e0;
    out_f64[2] = dele;
    out_f64[3] = deleused;
    out_f64[4] = prftmp;
    out_f64[5] = opsv4;
    out_f64[6] = aasmall;
    out_f64[7] = optpp;
    out_f64[8] = use_voigt ? 1.0 : 0.0;
    write_message(errbuf, errbuf_size, use_voigt ? "xstar_rates_apply_linopac_profile evaluated voigt" : "xstar_rates_apply_linopac_profile evaluated gaussian");
    return 0;
}


// Coarse selected Mg record_type=4/data_type=50 backend.
// This evaluates the source type-50 ucalc branch, scalar line emissivity, and
// linopac/oplin/fline/flinel array side effects in one C++ batch.  Unsupported
// records are reported per-row so Python can fall back safely.
int xstar_rates_apply_mg_type4_type50_coarse(
    int n_records,
    const long long* record,
    const long long* data_type,
    const long long* ion_index,
    const long long* ion_stage,
    const long long* line_index,
    const long long* nb1,
    const double* wavelength_a,
    const double* aij_s,
    const double* source_upper_weight,
    const double* source_lower_weight,
    const double* endpoint_energy_ev,
    const double* bremsa_nb1,
    const double* ptmp1,
    const double* ptmp2,
    const double* abund_lower,
    const double* abund_upper,
    const double* bin_width_ev,
    double cfrac,
    double hydrogen_density_cm3,
    double turbulent_velocity_km_s,
    double temperature_1e4k,
    double atomic_mass_amu,
    double erg_per_ev,
    const double* natural_width_ev,
    const double* seed_profiles,
    int seed_radius,
    const double* epi,
    int ncn2,
    double* opakc,
    double* rccemis,
    double* oplin,
    int n_lines_capacity,
    double* fline,
    int fline_stride,
    double* flinel,
    long long* out_i64,
    double* out_f64,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_records < 0 || ncn2 < 3 || n_lines_capacity < 1 || fline_stride < 1) {
        write_message(errbuf, errbuf_size, "invalid dimensions for xstar_rates_apply_mg_type4_type50_coarse");
        return 2;
    }
    if (!record || !data_type || !ion_index || !ion_stage || !line_index || !nb1 ||
        !wavelength_a || !aij_s || !source_upper_weight || !source_lower_weight ||
        !endpoint_energy_ev || !bremsa_nb1 || !ptmp1 || !ptmp2 || !abund_lower ||
        !abund_upper || !bin_width_ev || !natural_width_ev || !seed_profiles ||
        seed_radius < 0 || !epi || !opakc ||
        !rccemis || !oplin || !fline || !flinel || !out_i64 || !out_f64) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_rates_apply_mg_type4_type50_coarse");
        return 3;
    }
    if (!std::isfinite(cfrac) || !std::isfinite(hydrogen_density_cm3) ||
        !std::isfinite(turbulent_velocity_km_s) || !std::isfinite(temperature_1e4k) ||
        !std::isfinite(atomic_mass_amu) || !std::isfinite(erg_per_ev) || erg_per_ev <= 0.0) {
        write_message(errbuf, errbuf_size, "non-finite scalar passed to xstar_rates_apply_mg_type4_type50_coarse");
        return 4;
    }
    const double cover = std::max(0.0, 1.0 - cfrac);
    const double mass = std::max(atomic_mass_amu, 1.0e-30);
    const double temp = std::max(temperature_1e4k, 1.0e-48);
    const double vtherm = std::sqrt((turbulent_velocity_km_s * 1.0e5) * (turbulent_velocity_km_s * 1.0e5) +
                                    (1.29e6 / std::sqrt(std::max(mass / temp, 1.0e-48))) *
                                    (1.29e6 / std::sqrt(std::max(mass / temp, 1.0e-48))));
    long long applied = 0;
    long long unsupported = 0;
    long long linopac_calls = 0;
    long long linopac_updated = 0;
    for (int k = 0; k < n_records; ++k) {
        long long* oi = out_i64 + 12 * k;
        double* of = out_f64 + 12 * k;
        for (int j = 0; j < 12; ++j) { oi[j] = 0; of[j] = 0.0; }
        oi[0] = record[k];
        oi[1] = data_type[k];
        oi[2] = 4;
        oi[3] = ion_index[k];
        oi[4] = ion_stage[k];
        oi[5] = line_index[k];
        oi[6] = nb1[k];
        if (data_type[k] != 50) { oi[7] = -50; ++unsupported; continue; }
        const double lam = wavelength_a[k];
        const double aij = aij_s[k];
        const double gu = source_upper_weight[k];
        const double gl = source_lower_weight[k];
        const double de = endpoint_energy_ev[k];
        const double brem = bremsa_nb1[k];
        const double p1 = ptmp1[k];
        const double p2 = ptmp2[k];
        const double ab1 = abund_lower[k];
        const double ab2 = abund_upper[k];
        const double width = bin_width_ev[k];
        bool finite_seed_profiles = true;
        const double* record_seed_profiles = seed_profiles +
            static_cast<std::size_t>(k) * static_cast<std::size_t>(2 * seed_radius + 1);
        for (int j = 0; j < 2 * seed_radius + 1; ++j) {
            if (!std::isfinite(record_seed_profiles[j])) {
                finite_seed_profiles = false;
                break;
            }
        }
        if (!finite6(lam, aij, gu, gl, de, brem) || !finite6(p1, p2, ab1, ab2, width, natural_width_ev[k]) ||
            !finite_seed_profiles ||
            lam <= 0.0 || aij < 0.0 || gu <= 0.0 || gl <= 0.0 || de < 0.0 || width <= 0.0 || vtherm <= 0.0) {
            oi[7] = -1; ++unsupported; continue;
        }
        const double flin = 1.0e-16 * aij * gu * lam * lam / (0.667274 * gl);
        const double escaped_raw = aij * (p1 + p2);
        const double escaped = std::max(escaped_raw, 1.0e-20 * hydrogen_density_cm3);
        double photo = 0.0;
        if (!(lam > 0.99e9) && cover > 0.0) {
            photo = 0.02655 * flin * lam * 1.0e-8 * brem / 3.0e10 * cover;
        }
        double opakab = 0.0;
        if (!(lam > 0.99e9)) {
            opakab = 0.02655 * flin * lam * 1.0e-8 / vtherm;
        }
        const double opakb1 = opakab * ab1;
        const double net = escaped * ab2 - photo * ab1;
        double rcem1 = net * (source_real_literal(12398.4016) / lam) * erg_per_ev * p1;
        double rcem2 = net * (source_real_literal(12398.4016) / lam) * erg_per_ev * p2;
        if (rcem1 < 0.0) rcem1 = 0.0;
        if (rcem2 < 0.0) rcem2 = 0.0;
        const double flinel_delta = (rcem1 + rcem2) * 2.0 / width / erg_per_ev;
        const int li = static_cast<int>(line_index[k]);
        const int nb = static_cast<int>(nb1[k]);
        long long tmp_i[8] = {0,0,0,0,0,0,0,0};
        double tmp_f[12] = {0.0};
        int lrc = xstar_rates_apply_linopac_profile(
            opakb1, rcem1, rcem2, source_real_literal(12398.4016) / lam,
            turbulent_velocity_km_s, temperature_1e4k, atomic_mass_amu, natural_width_ev[k],
            record_seed_profiles,
            seed_radius,
            epi, ncn2, opakc, rccemis, tmp_i, tmp_f, errbuf, errbuf_size);
        if (lrc == 0) {
            if (li > 0 && li < n_lines_capacity) {
                oplin[li] = opakb1;
                fline[0 * fline_stride + li] = rcem1;
                fline[1 * fline_stride + li] = rcem2;
            }
            if (nb > 0 && nb <= ncn2) {
                flinel[nb - 1] += flinel_delta;
            }
            ++linopac_calls;
            linopac_updated += tmp_i[0];
            oi[7] = 1;
            oi[8] = tmp_i[0];
            oi[9] = tmp_i[2];
        } else {
            oi[7] = -6;
            ++unsupported;
            continue;
        }
        of[0] = photo;
        of[1] = escaped;
        of[2] = -escaped * de * erg_per_ev;
        of[3] = -photo * de * erg_per_ev;
        of[4] = opakab;
        of[5] = opakb1;
        of[6] = net;
        of[7] = rcem1;
        of[8] = rcem2;
        of[9] = flinel_delta;
        of[10] = flin;
        of[11] = vtherm;
        ++applied;
    }
    if (n_records > 0) {
        out_i64[10] = applied;
        out_i64[11] = unsupported;
        if (n_records > 1) {
            out_i64[22] = linopac_calls;
            out_i64[23] = linopac_updated;
        }
    }
    write_message(errbuf, errbuf_size, "xstar_rates_apply_mg_type4_type50_coarse evaluated");
    return 0;
}


}  // extern "C"
