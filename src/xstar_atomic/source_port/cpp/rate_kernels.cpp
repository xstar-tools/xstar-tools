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
}  // namespace

extern "C" {

int xstar_rates_abi_version() {
    return XSTAR_RATES_ABI_VERSION;
}

const char* xstar_rates_backend_name() {
    return "xstar_rates_mg_type7_type4_linopac_v1";
}

int xstar_rates_feature_flags() {
    return XSTAR_RATES_FEATURE_SKELETON | XSTAR_RATES_FEATURE_MG_TYPE7_MATRIX_TERMS | XSTAR_RATES_FEATURE_MG_TYPE4_LINE_EMISSIVITY | XSTAR_RATES_FEATURE_LINOPAC_PROFILE;
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
// This v0.5.61 C ABI intentionally supports only the Gaussian-profile branch.
// If the natural-width Voigt branch is needed, it returns code 6 and the Python
// caller falls back to the existing source-faithful Python linopac translation.
int xstar_rates_apply_linopac_profile(
    double optpp,
    double rcem1,
    double rcem2,
    double line_energy_ev,
    double vturb_km_s,
    double temperature_1e4k,
    double atomic_mass_amu,
    double natural_width_ev,
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
    if (!epi || !opakc || !rccemis || !out_i64 || !out_f64) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_rates_apply_linopac_profile");
        return 3;
    }
    const int n = static_cast<int>(ncn2);
    if (n < 3 || !std::isfinite(optpp) || !std::isfinite(line_energy_ev) ||
        !std::isfinite(vturb_km_s) || !std::isfinite(temperature_1e4k) ||
        !std::isfinite(atomic_mass_amu) || !std::isfinite(natural_width_ev)) {
        write_message(errbuf, errbuf_size, "invalid input to xstar_rates_apply_linopac_profile");
        return 4;
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
    if (aasmall > 1.0e-9) {
        write_message(errbuf, errbuf_size, "linopac Voigt branch not implemented in C++ v0.5.61");
        return 6;
    }
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
    double profile = std::exp(-delet * delet) / 1.772;
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
                profile = std::exp(-delet * delet) / 1.772;
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
    out_i64[1] = 1;
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
    write_message(errbuf, errbuf_size, "xstar_rates_apply_linopac_profile evaluated");
    return 0;
}


}  // extern "C"
