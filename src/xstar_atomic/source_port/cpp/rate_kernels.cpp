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

namespace {
constexpr int XSTAR_RATES_ABI_VERSION = 2;
constexpr int XSTAR_RATES_FEATURE_SKELETON = 1;
constexpr int XSTAR_RATES_FEATURE_MG_TYPE7_MATRIX_TERMS = 2;
constexpr int XSTAR_RATES_FEATURE_MG_TYPE4_LINE_EMISSIVITY = 4;

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
    return "xstar_rates_mg_type7_type4_v1";
}

int xstar_rates_feature_flags() {
    return XSTAR_RATES_FEATURE_SKELETON | XSTAR_RATES_FEATURE_MG_TYPE7_MATRIX_TERMS | XSTAR_RATES_FEATURE_MG_TYPE4_LINE_EMISSIVITY;
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
// v0.5.58.  This C ABI owns the repeated scalar arithmetic after ucalc:
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


}  // extern "C"
