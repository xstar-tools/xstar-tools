// Optional XSTAR matrix-assembly kernels.
//
// v0.5.67 starts libxstar_matrix.so as a plain C ABI shared library.  The
// first implemented kernel owns the repeated Mg record_type=7 matrix-term
// construction after Python has produced the source-faithful ucalc ans1..ans6
// values.  This deliberately mirrors the previous libxstar_rates.so term
// builder so the new matrix library can be validated without changing physics.

#include <cmath>
#include <cstddef>
#include <cstring>
#include <limits>

namespace {

void write_message(char* errbuf, std::size_t errbuf_size, const char* message) {
    if (!errbuf || errbuf_size == 0) return;
    std::strncpy(errbuf, message ? message : "", errbuf_size - 1);
    errbuf[errbuf_size - 1] = '\0';
}

bool finite6(double a, double b, double c, double d, double e, double f) {
    return std::isfinite(a) && std::isfinite(b) && std::isfinite(c) &&
           std::isfinite(d) && std::isfinite(e) && std::isfinite(f);
}


}  // namespace

extern "C" {

int xstar_matrix_abi_version() {
    return 1;
}

const char* xstar_matrix_backend_name() {
    return "xstar_matrix_mg_ion_direct_accumulator_v7";
}

int xstar_matrix_feature_flags() {
    // 1: skeleton/probe; 2: Mg record_type=7 matrix-term construction; 4: dense matrix fill; 8: selected simple ucalc branches; 16: data_type=51 ucalc; 32: Mg rates+matrix ABI.
    return 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 | 512;
}

int xstar_matrix_probe(
    int n_records,
    int n_basis_rows,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_records < 0 || n_basis_rows < 0) {
        write_message(errbuf, errbuf_size, "invalid probe dimensions");
        return 2;
    }
    write_message(errbuf, errbuf_size, "xstar_matrix ABI OK");
    return 0;
}

// Build the four source calc_hmc_ion matrix terms for each Mg record_type=7
// result. Python still evaluates ucalc ans1..ans6 in v0.5.67; this C++ kernel
// owns compact-index mapping, source-style endpoint clamping, and the repeated
// off-diagonal/diagonal term construction.
//
// int output columns per emitted term, 16 columns:
//   term_index, record, data_type, rate_type, ion_index, ion_stage,
//   role_code, row, col, idest1, idest2, lower_endpoint, upper_endpoint,
//   raw_row, raw_col, source_ipmat_clamped
// double output columns per emitted term, 4 columns:
//   aj1, aj2, cj, cj2
int xstar_matrix_build_mg_type7_terms(
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
        write_message(errbuf, errbuf_size, "invalid dimensions for xstar_matrix_build_mg_type7_terms");
        return 2;
    }
    if (!record || !data_type || !ion_index || !ion_stage || !compact_start ||
        !idest1 || !idest2 || !ans1 || !ans2 || !ans3 || !ans4 || !ans5 || !ans6 ||
        !out_i64 || !out_f64) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_matrix_build_mg_type7_terms");
        return 3;
    }
    if (!std::isfinite(xpx)) {
        write_message(errbuf, errbuf_size, "non-finite density scale passed to xstar_matrix_build_mg_type7_terms");
        return 4;
    }

    for (int k = 0; k < n_records; ++k) {
        const long long id1 = idest1[k];
        const long long id2 = idest2[k];
        if (id1 <= 0 || id2 <= 0) {
            write_message(errbuf, errbuf_size, "non-positive endpoint passed to xstar_matrix_build_mg_type7_terms");
            return 5;
        }
        if (!finite6(ans1[k], ans2[k], ans3[k], ans4[k], ans5[k], ans6[k])) {
            write_message(errbuf, errbuf_size, "non-finite rate answer passed to xstar_matrix_build_mg_type7_terms");
            return 6;
        }

        const long long raw_lower = compact_start[k] + id1 - 1;
        const long long raw_upper = compact_start[k] + id2 - 1;
        long long lower = raw_lower;
        long long upper = raw_upper;
        if (lower > basis_n_rows) lower = basis_n_rows;
        if (upper > basis_n_rows) upper = basis_n_rows;
        if (lower <= 0 || upper <= 0) {
            write_message(errbuf, errbuf_size, "endpoint maps outside compact basis in xstar_matrix_build_mg_type7_terms");
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
    write_message(errbuf, errbuf_size, "xstar_matrix_build_mg_type7_terms evaluated");
    return 0;
}


// Coarse Mg rates+matrix ABI skeleton.
//
// This is intentionally still conservative: Python may continue to own ucalc
// evaluation for a record, but C++ owns the dominant Mg rate/data group handoff
// and the four source calc_hmc_ion matrix-term insertions for supported rows.
// The ABI is designed to grow until it owns record traversal and ucalc as well.
//
// Supported in this first release:
//   rate_type=3, data_type=51 (Mg Burgess-Tully collisional excitation rows)
//
// out_stats columns:
//   0 records_seen
//   1 records_supported
//   2 records_batched
//   3 cpp_calls
//   4 emitted_matrix_terms
//   5 fallback_unsupported_rate_data
//   6 fallback_nonpositive_endpoint
//   7 fallback_nonfinite_answer
int xstar_matrix_build_mg_rates_and_matrix(
    int n_records,
    int basis_n_rows,
    int term_start,
    const long long* record,
    const long long* rate_type,
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
    long long* out_stats,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_records < 0 || basis_n_rows <= 0 || term_start <= 0) {
        write_message(errbuf, errbuf_size, "invalid dimensions for xstar_matrix_build_mg_rates_and_matrix");
        return 2;
    }
    if (!record || !rate_type || !data_type || !ion_index || !ion_stage || !compact_start ||
        !idest1 || !idest2 || !ans1 || !ans2 || !ans3 || !ans4 || !ans5 || !ans6 ||
        !out_i64 || !out_f64 || !out_stats) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_matrix_build_mg_rates_and_matrix");
        return 3;
    }
    if (!std::isfinite(xpx)) {
        write_message(errbuf, errbuf_size, "non-finite density scale passed to xstar_matrix_build_mg_rates_and_matrix");
        return 4;
    }

    long long records_seen = 0;
    long long records_supported = 0;
    long long emitted_terms = 0;
    long long fallback_unsupported_rate_data = 0;
    long long fallback_nonpositive_endpoint = 0;
    long long fallback_nonfinite_answer = 0;

    for (int k = 0; k < n_records; ++k) {
        ++records_seen;
        if (!(rate_type[k] == 3 && data_type[k] == 51)) {
            ++fallback_unsupported_rate_data;
            continue;
        }
        const long long id1 = idest1[k];
        const long long id2 = idest2[k];
        if (id1 <= 0 || id2 <= 0) {
            ++fallback_nonpositive_endpoint;
            continue;
        }
        if (!finite6(ans1[k], ans2[k], ans3[k], ans4[k], ans5[k], ans6[k])) {
            ++fallback_nonfinite_answer;
            continue;
        }

        const long long raw_lower = compact_start[k] + id1 - 1;
        const long long raw_upper = compact_start[k] + id2 - 1;
        long long lower = raw_lower;
        long long upper = raw_upper;
        if (lower > basis_n_rows) lower = basis_n_rows;
        if (upper > basis_n_rows) upper = basis_n_rows;
        if (lower <= 0 || upper <= 0) {
            ++fallback_nonpositive_endpoint;
            continue;
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
        const double aj1_vals[4] = {a1, a2, -a1, -a2};
        const double aj2_vals[4] = {a2, a1, -a1, -a2};
        const double cj_vals[4] = {0.0, 0.0, c4 * xpx, -c3 * xpx};
        const double cj2_vals[4] = {0.0, 0.0, c6 * xpx, -c5 * xpx};

        const long long base = emitted_terms;
        for (int j = 0; j < 4; ++j) {
            const long long out_row = base + j;
            long long* oi = out_i64 + 16 * out_row;
            double* of = out_f64 + 4 * out_row;
            oi[0] = static_cast<long long>(term_start) + out_row;
            oi[1] = record[k];
            oi[2] = data_type[k];
            oi[3] = rate_type[k];
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
            of[0] = aj1_vals[j];
            of[1] = aj2_vals[j];
            of[2] = cj_vals[j];
            of[3] = cj2_vals[j];
        }
        emitted_terms += 4;
        ++records_supported;
    }

    out_stats[0] = records_seen;
    out_stats[1] = records_supported;
    out_stats[2] = n_records;
    out_stats[3] = n_records > 0 ? 1 : 0;
    out_stats[4] = emitted_terms;
    out_stats[5] = fallback_unsupported_rate_data;
    out_stats[6] = fallback_nonpositive_endpoint;
    out_stats[7] = fallback_nonfinite_answer;
    write_message(errbuf, errbuf_size, records_supported > 0 ? "xstar_matrix_build_mg_rates_and_matrix evaluated" : "xstar_matrix_build_mg_rates_and_matrix no supported records");
    return 0;
}



// Fill dense, heating, and secondary-heating matrices from emitted term arrays.
// This is the first broader matrix-assembly loop moved into libxstar_matrix.so.
// Rows/columns are one-based compact indices, matching MatrixTerm.row/column.
int xstar_matrix_dense_fill_terms(
    int n_terms,
    int n_rows,
    const long long* rows,
    const long long* cols,
    const double* aj1,
    const double* cj,
    const double* cj2,
    double* dense,
    double* heat,
    double* heat2,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_terms < 0 || n_rows <= 0) {
        write_message(errbuf, errbuf_size, "invalid dimensions for xstar_matrix_dense_fill_terms");
        return 2;
    }
    if (!rows || !cols || !aj1 || !cj || !cj2 || !dense || !heat || !heat2) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_matrix_dense_fill_terms");
        return 3;
    }
    const std::size_t nn = static_cast<std::size_t>(n_rows) * static_cast<std::size_t>(n_rows);
    for (std::size_t k = 0; k < nn; ++k) {
        dense[k] = 0.0;
        heat[k] = 0.0;
        heat2[k] = 0.0;
    }
    for (int k = 0; k < n_terms; ++k) {
        const long long r = rows[k];
        const long long c = cols[k];
        if (r <= 0 || c <= 0 || r > n_rows || c > n_rows) {
            write_message(errbuf, errbuf_size, "matrix term index outside compact basis in xstar_matrix_dense_fill_terms");
            return 4;
        }
        if (!std::isfinite(aj1[k]) || !std::isfinite(cj[k]) || !std::isfinite(cj2[k])) {
            write_message(errbuf, errbuf_size, "non-finite matrix term passed to xstar_matrix_dense_fill_terms");
            return 5;
        }
        const std::size_t idx = static_cast<std::size_t>(r - 1) * static_cast<std::size_t>(n_rows) + static_cast<std::size_t>(c - 1);
        dense[idx] += aj1[k];
        heat[idx] += cj[k];
        heat2[idx] += cj2[k];
    }
    write_message(errbuf, errbuf_size, "xstar_matrix_dense_fill_terms evaluated");
    return 0;
}


// Evaluate selected compact analytic ucalc branches used by matrix assembly.
// This first ABI covers simple no-grid/no-level branches that depend only on
// temperature and density.  It is a parity-gated building block for moving
// larger rate-construction batches into libxstar_matrix.so.
// Supported data_type values: 1, 2, 3, 7, 8, 20.
int xstar_matrix_eval_simple_ucalc(
    int n_records,
    const long long* record,
    const long long* data_type,
    const long long* rate_type,
    const long long* int0,
    const long long* int1,
    const double* r0,
    const double* r1,
    const double* r2,
    const double* r3,
    const double* r4,
    const double* r5,
    const double* r6,
    const double* r7,
    double t_1e4,
    double electron_density_cm3,
    double neutral_h_density_cm3,
    double ionized_h_density_cm3,
    long long nlevp,
    double* out_ans,
    long long* out_i64,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_records < 0 || !record || !data_type || !rate_type || !int0 || !int1 ||
        !r0 || !r1 || !r2 || !r3 || !r4 || !r5 || !r6 || !r7 || !out_ans || !out_i64) {
        write_message(errbuf, errbuf_size, "invalid input to xstar_matrix_eval_simple_ucalc");
        return 2;
    }
    if (!std::isfinite(t_1e4) || t_1e4 <= 0.0 || !std::isfinite(electron_density_cm3) ||
        !std::isfinite(neutral_h_density_cm3) || !std::isfinite(ionized_h_density_cm3)) {
        write_message(errbuf, errbuf_size, "non-finite thermodynamic input to xstar_matrix_eval_simple_ucalc");
        return 3;
    }
    const double kt_ev_per_1e4k = 0.861707;
    const auto expo = [](double x) -> double {
        if (x < -60.0) x = -60.0;
        if (x > 60.0) x = 60.0;
        return std::exp(x);
    };
    int applied = 0;
    for (int k = 0; k < n_records; ++k) {
        double* ans = out_ans + 6 * k;
        long long* oi = out_i64 + 6 * k;
        for (int j = 0; j < 6; ++j) ans[j] = 0.0;
        oi[0] = record[k];
        oi[1] = data_type[k];
        oi[2] = rate_type[k];
        oi[3] = 0; // idest1
        oi[4] = 0; // idest2
        oi[5] = 0; // status: 1 evaluated, 0 unsupported
        const long long dt = data_type[k];
        if (dt == 1) {
            const double arad = r0[k];
            const double eta = r1[k];
            ans[0] = arad / std::pow(t_1e4, eta) * electron_density_cm3;
            oi[3] = 1; oi[5] = 1; ++applied;
        } else if (dt == 2) {
            oi[3] = 1; oi[4] = nlevp;
            if (t_1e4 <= 5.0) {
                const double rate = r0[k] * expo(std::log(t_1e4) * r1[k]) *
                    std::max(0.0, 1.0 + r2[k] * expo(r3[k] * t_1e4)) * 1.0e-9;
                double a1 = rate * neutral_h_density_cm3;
                double a2 = 0.0;
                if (rate_type[k] == 5) { a2 = a1; a1 = 0.0; }
                ans[0] = a1; ans[1] = a2;
            }
            oi[5] = 1; ++applied;
        } else if (dt == 3) {
            const double cai = r0[k];
            const double eai = r1[k];
            ans[0] = cai * expo(-eai / (kt_ev_per_1e4k * t_1e4)) /
                     std::sqrt(t_1e4) * electron_density_cm3;
            oi[3] = 1; oi[4] = 1; oi[5] = 1; ++applied;
        } else if (dt == 7) {
            const double rate = r0[k] * 1.0e-6 * expo(-r2[k] / t_1e4) *
                (1.0 + r1[k] * expo(-r3[k] / t_1e4)) / (t_1e4 * std::sqrt(t_1e4));
            ans[0] = rate * electron_density_cm3;
            oi[3] = 1; oi[5] = 1; ++applied;
        } else if (dt == 8) {
            double rate = 0.0;
            rate += r0[k] * expo(-r4[k] / (kt_ev_per_1e4k * t_1e4));
            rate += r1[k] * expo(-r5[k] / (kt_ev_per_1e4k * t_1e4));
            rate += r2[k] * expo(-r6[k] / (kt_ev_per_1e4k * t_1e4));
            rate += r3[k] * expo(-r7[k] / (kt_ev_per_1e4k * t_1e4));
            rate *= 1.0e-6 * std::pow(t_1e4, -1.5);
            ans[0] = rate * electron_density_cm3;
            oi[3] = 1; oi[5] = 1; ++applied;
        } else if (dt == 20) {
            const double rate = r0[k] * std::pow(t_1e4, r1[k]) *
                (1.0 + r2[k] * expo(r3[k] * t_1e4)) * expo(-r4[k] / t_1e4) * 1.0e-9;
            ans[0] = rate * ionized_h_density_cm3;
            oi[3] = int0[k]; oi[4] = nlevp; oi[5] = 1; ++applied;
        }
    }
    write_message(errbuf, errbuf_size, applied > 0 ? "xstar_matrix_eval_simple_ucalc evaluated" : "xstar_matrix_eval_simple_ucalc no supported records");
    return 0;
}


// Batched source-faithful data_type=51 Burgess-Tully collision ucalc branch.
// This covers the dominant Mg thermal-balance rate_construction group in the
// forensic run: rate_type=3, data_type=51.  It returns ans1/ans2/ans5/ans6 and
// source endpoints only; the existing matrix-term builder inserts the four
// calc_hmc_ion matrix rows from those results.
namespace {

double xstar_matrix_expo_limited(double x) {
    if (x < -60.0) x = -60.0;
    if (x > 60.0) x = 60.0;
    return std::exp(x);
}

double xstar_matrix_splinem5(const double* p, double x) {
    const double s = 1.0 / 30.0;
    const double s2 = 32.0 * s * (19.0*p[0] - 43.0*p[1] + 30.0*p[2] - 7.0*p[3] + p[4]);
    const double s3 = 160.0 * s * (-p[0] + 7.0*p[1] - 12.0*p[2] + 7.0*p[3] - p[4]);
    const double s4 = 32.0 * s * (p[0] - 7.0*p[1] + 30.0*p[2] - 43.0*p[3] + 19.0*p[4]);
    double x0 = 0.0, t0 = 0.0, t1 = 0.0, t2 = 0.0, t3 = 0.0;
    if (x <= 0.25) {
        x0 = x - 0.125; t3 = 0.0; t2 = 0.5 * s2; t1 = 4.0 * (p[1] - p[0]); t0 = 0.5 * (p[0] + p[1]) - 0.015625 * t2;
    } else if (x <= 0.5) {
        x0 = x - 0.375; t3 = 20.0 * s * (s3 - s2); t2 = 0.25 * (s2 + s3); t1 = 4.0 * (p[2] - p[1]) - 0.015625 * t3; t0 = 0.5 * (p[1] + p[2]) - 0.015625 * t2;
    } else if (x <= 0.75) {
        x0 = x - 0.625; t3 = 20.0 * s * (s4 - s3); t2 = 0.25 * (s3 + s4); t1 = 4.0 * (p[3] - p[2]) - 0.015625 * t3; t0 = 0.5 * (p[2] + p[3]) - 0.015625 * t2;
    } else {
        x0 = x - 0.875; t3 = 0.0; t2 = 0.5 * s4; t1 = 4.0 * (p[4] - p[3]); t0 = 0.5 * (p[3] + p[4]) - 0.015625 * t2;
    }
    return t0 + x0 * (t1 + x0 * (t2 + x0 * t3));
}


double xstar_matrix_spline9_natural(const double* y, double x) {
    const int n = 9;
    double xa[n];
    for (int i = 0; i < n; ++i) xa[i] = 0.125 * static_cast<double>(i);
    double y2[n] = {0.0};
    double u[n] = {0.0};
    for (int i = 1; i < n - 1; ++i) {
        const double denom = xa[i + 1] - xa[i - 1];
        if (denom == 0.0) continue;
        const double sig = (xa[i] - xa[i - 1]) / denom;
        const double pp = sig * y2[i - 1] + 2.0;
        y2[i] = (sig - 1.0) / pp;
        const double term = (y[i + 1] - y[i]) / (xa[i + 1] - xa[i]) - (y[i] - y[i - 1]) / (xa[i] - xa[i - 1]);
        u[i] = (6.0 * term / denom - sig * u[i - 1]) / pp;
    }
    for (int k = n - 2; k >= 0; --k) y2[k] = y2[k] * y2[k + 1] + u[k];
    if (x <= xa[0]) return y[0];
    if (x >= xa[n - 1]) return y[n - 1];
    int klo = 0, khi = n - 1;
    while (khi - klo > 1) {
        const int k = (khi + klo) / 2;
        if (xa[k] > x) khi = k; else klo = k;
    }
    const double h = xa[khi] - xa[klo];
    if (h == 0.0) return y[klo];
    const double a = (xa[khi] - x) / h;
    const double b = (x - xa[klo]) / h;
    return a*y[klo] + b*y[khi] + ((a*a*a-a)*y2[klo] + (b*b*b-b)*y2[khi]) * h*h / 6.0;
}

bool xstar_matrix_type51_upsilon9(long long bt_type, double eij_ryd, double c_bt, const double* y, double temperature_k, double* out) {
    if (!out || eij_ryd <= 0.0 || c_bt <= 0.0 || temperature_k <= 0.0) return false;
    const double kte = temperature_k / eij_ryd / 1.57888e5;
    double xt = 0.0;
    if (bt_type == 1 || bt_type == 4) {
        const double denom = std::log(kte + c_bt);
        if (denom == 0.0 || !std::isfinite(denom)) return false;
        xt = 1.0 - std::log(c_bt) / denom;
    } else if (bt_type == 2 || bt_type == 3 || bt_type == 5 || bt_type == 6) {
        xt = kte / (kte + c_bt);
    } else {
        return false;
    }
    double sups = xstar_matrix_spline9_natural(y, xt);
    double val = sups;
    if (bt_type == 1) val = sups * std::log(kte + std::exp(1.0));
    else if (bt_type == 2) val = sups;
    else if (bt_type == 3) val = sups / (kte + 1.0);
    else if (bt_type == 4) val = sups * std::log(kte + c_bt);
    else if (bt_type == 5) val = (kte != 0.0 ? sups / kte : std::numeric_limits<double>::quiet_NaN());
    else if (bt_type == 6) val = std::pow(10.0, sups);
    if (!std::isfinite(val)) return false;
    *out = val;
    return true;
}

bool xstar_matrix_type51_upsilon5(long long bt_type, double eij_ryd, double c_bt, const double* y, double temperature_k, double* out) {
    if (!out || eij_ryd <= 0.0 || c_bt <= 0.0 || temperature_k <= 0.0) return false;
    const double e = std::fabs(temperature_k / (1.57888e5 * eij_ryd));
    double x = 0.0;
    if (bt_type == 1 || bt_type == 4) {
        const double denom = std::log(e + c_bt);
        if (denom == 0.0 || !std::isfinite(denom)) return false;
        x = std::log((e + c_bt) / c_bt) / denom;
    } else if (bt_type == 2 || bt_type == 3) {
        x = e / (e + c_bt);
    } else {
        return false;
    }
    double val = xstar_matrix_splinem5(y, x);
    if (bt_type == 1) val *= std::log(e + 2.71828);
    else if (bt_type == 3) val /= (e + 1.0);
    else if (bt_type == 4) val *= std::log(e + c_bt);
    if (!std::isfinite(val)) return false;
    *out = val;
    return true;
}

} // namespace

extern "C" int xstar_matrix_eval_type51_ucalc_batch(
    int n_records,
    const long long* record,
    const long long* ion_index,
    const long long* ion_stage,
    const long long* lower_level,
    const long long* upper_level,
    const long long* bt_type,
    const long long* n_points,
    const double* eij_ryd,
    const double* c_bt,
    const double* g_lower,
    const double* g_upper,
    const double* delta_e_ev,
    const double* y_values,
    double temperature_k,
    double electron_density_cm3,
    double* out_ans,
    long long* out_i64,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_records < 0 || !record || !ion_index || !ion_stage || !lower_level || !upper_level || !bt_type || !n_points ||
        !eij_ryd || !c_bt || !g_lower || !g_upper || !delta_e_ev || !y_values || !out_ans || !out_i64) {
        write_message(errbuf, errbuf_size, "invalid input to xstar_matrix_eval_type51_ucalc_batch");
        return 2;
    }
    if (!std::isfinite(temperature_k) || temperature_k <= 0.0 || !std::isfinite(electron_density_cm3) || electron_density_cm3 < 0.0) {
        write_message(errbuf, errbuf_size, "invalid thermodynamic input to xstar_matrix_eval_type51_ucalc_batch");
        return 3;
    }
    int applied = 0;
    for (int k = 0; k < n_records; ++k) {
        double* ans = out_ans + 6 * k;
        long long* oi = out_i64 + 8 * k;
        for (int j = 0; j < 6; ++j) ans[j] = 0.0;
        oi[0] = record[k]; oi[1] = 51; oi[2] = 3; oi[3] = lower_level[k]; oi[4] = upper_level[k]; oi[5] = ion_index[k]; oi[6] = ion_stage[k]; oi[7] = 0;
        if ((n_points[k] != 5 && n_points[k] != 9) || eij_ryd[k] <= 0.0 || c_bt[k] <= 0.0 || g_lower[k] <= 0.0 || g_upper[k] <= 0.0 || delta_e_ev[k] <= 0.0) continue;
        double ups = 0.0;
        const double* y = y_values + 9 * k;
        const double eij_ev = eij_ryd[k] * 13.605692;
        const double wavelength_a = 12398.4016 / eij_ev;
        const double floor_k = 2.8777e6 / wavelength_a;
        const double bt_temperature_k = std::max(temperature_k, floor_k);
        bool ok = false;
        if (n_points[k] == 5) ok = xstar_matrix_type51_upsilon5(bt_type[k], eij_ryd[k], c_bt[k], y, bt_temperature_k, &ups);
        else ok = xstar_matrix_type51_upsilon9(bt_type[k], eij_ryd[k], c_bt[k], y, bt_temperature_k, &ups);
        if (!ok) continue;
        const double t_xstar = temperature_k / 1.0e4;
        const double tsq = std::sqrt(t_xstar);
        const double ekt_ev = 0.861707 * t_xstar;
        if (tsq <= 0.0 || ekt_ev <= 0.0) continue;
        const double delta = eij_ev / ekt_ev;
        const double q_deexc = 8.626e-8 * ups / tsq / g_upper[k];
        const double q_exc = q_deexc * g_upper[k] * xstar_matrix_expo_limited(-delta) / g_lower[k];
        const double ans1 = q_exc * electron_density_cm3;
        const double ans2 = q_deexc * electron_density_cm3;
        ans[0] = ans1;
        ans[1] = ans2;
        ans[4] = ans2 * delta_e_ev[k] * 1.602197e-12;
        ans[5] = ans1 * delta_e_ev[k] * 1.602197e-12;
        oi[7] = 1;
        ++applied;
    }
    write_message(errbuf, errbuf_size, applied > 0 ? "xstar_matrix_eval_type51_ucalc_batch evaluated" : "xstar_matrix_eval_type51_ucalc_batch no supported records");
    return 0;
}

// Coarse Mg type-51 rates+matrix ABI.
//
// This owns the dominant Mg rate_type=3/data_type=51 ucalc evaluation and
// matrix-term construction in one source-ordered C++ batch.  Python is still
// responsible for decoding the XSTAR packed record into compact payload arrays;
// this ABI then traverses those payload rows in source order, evaluates the
// Burgess-Tully collision rate, and emits the four calc_hmc_ion matrix terms.
//
// out_stats columns:
//   0 records_seen
//   1 records_supported
//   2 records_batched
//   3 cpp_calls
//   4 emitted_matrix_terms
//   5 fallback_unsupported_rate_data
//   6 fallback_nonpositive_endpoint
//   7 fallback_nonfinite_answer
//   8 ucalc_cpp_applied
//   9 ucalc_cpp_unsupported
int xstar_matrix_build_mg_type51_rates_and_matrix(
    int n_records,
    int basis_n_rows,
    int term_start,
    const long long* record,
    const long long* ion_index,
    const long long* ion_stage,
    const long long* compact_start,
    const long long* lower_level,
    const long long* upper_level,
    const long long* bt_type,
    const long long* n_points,
    const double* eij_ryd,
    const double* c_bt,
    const double* g_lower,
    const double* g_upper,
    const double* delta_e_ev,
    const double* y_values,
    double temperature_k,
    double electron_density_cm3,
    double hydrogen_density_cm3,
    long long* out_i64,
    double* out_f64,
    long long* out_stats,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_records < 0 || basis_n_rows <= 0 || term_start <= 0) {
        write_message(errbuf, errbuf_size, "invalid dimensions for xstar_matrix_build_mg_type51_rates_and_matrix");
        return 2;
    }
    if (!record || !ion_index || !ion_stage || !compact_start || !lower_level || !upper_level || !bt_type || !n_points ||
        !eij_ryd || !c_bt || !g_lower || !g_upper || !delta_e_ev || !y_values || !out_i64 || !out_f64 || !out_stats) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_matrix_build_mg_type51_rates_and_matrix");
        return 3;
    }
    if (!std::isfinite(temperature_k) || temperature_k <= 0.0 || !std::isfinite(electron_density_cm3) || electron_density_cm3 < 0.0 ||
        !std::isfinite(hydrogen_density_cm3)) {
        write_message(errbuf, errbuf_size, "invalid thermodynamic input to xstar_matrix_build_mg_type51_rates_and_matrix");
        return 4;
    }

    long long records_seen = 0;
    long long records_supported = 0;
    long long emitted_terms = 0;
    long long fallback_unsupported_rate_data = 0;
    long long fallback_nonpositive_endpoint = 0;
    long long fallback_nonfinite_answer = 0;
    long long ucalc_cpp_applied = 0;
    long long ucalc_cpp_unsupported = 0;

    for (int k = 0; k < n_records; ++k) {
        ++records_seen;
        const long long id1 = lower_level[k];
        const long long id2 = upper_level[k];
        if (id1 <= 0 || id2 <= 0) {
            ++fallback_nonpositive_endpoint;
            ++ucalc_cpp_unsupported;
            continue;
        }
        if ((n_points[k] != 5 && n_points[k] != 9) || eij_ryd[k] <= 0.0 || c_bt[k] <= 0.0 ||
            g_lower[k] <= 0.0 || g_upper[k] <= 0.0 || delta_e_ev[k] <= 0.0) {
            ++fallback_unsupported_rate_data;
            ++ucalc_cpp_unsupported;
            continue;
        }
        double ups = 0.0;
        const double* y = y_values + 9 * k;
        const double eij_ev = eij_ryd[k] * 13.605692;
        const double wavelength_a = 12398.4016 / eij_ev;
        const double floor_k = 2.8777e6 / wavelength_a;
        const double bt_temperature_k = std::max(temperature_k, floor_k);
        bool ok = false;
        if (n_points[k] == 5) ok = xstar_matrix_type51_upsilon5(bt_type[k], eij_ryd[k], c_bt[k], y, bt_temperature_k, &ups);
        else ok = xstar_matrix_type51_upsilon9(bt_type[k], eij_ryd[k], c_bt[k], y, bt_temperature_k, &ups);
        if (!ok || !std::isfinite(ups)) {
            ++fallback_nonfinite_answer;
            ++ucalc_cpp_unsupported;
            continue;
        }
        const double t_xstar = temperature_k / 1.0e4;
        const double tsq = std::sqrt(t_xstar);
        const double ekt_ev = 0.861707 * t_xstar;
        if (tsq <= 0.0 || ekt_ev <= 0.0) {
            ++fallback_nonfinite_answer;
            ++ucalc_cpp_unsupported;
            continue;
        }
        const double delta = eij_ev / ekt_ev;
        const double q_deexc = 8.626e-8 * ups / tsq / g_upper[k];
        const double q_exc = q_deexc * g_upper[k] * xstar_matrix_expo_limited(-delta) / g_lower[k];
        const double ans1 = q_exc * electron_density_cm3;
        const double ans2 = q_deexc * electron_density_cm3;
        const double ans3 = 0.0;
        const double ans4 = 0.0;
        const double ans5 = ans2 * delta_e_ev[k] * 1.602197e-12;
        const double ans6 = ans1 * delta_e_ev[k] * 1.602197e-12;
        if (!finite6(ans1, ans2, ans3, ans4, ans5, ans6)) {
            ++fallback_nonfinite_answer;
            ++ucalc_cpp_unsupported;
            continue;
        }

        const long long raw_lower = compact_start[k] + id1 - 1;
        const long long raw_upper = compact_start[k] + id2 - 1;
        long long lower = raw_lower;
        long long upper = raw_upper;
        if (lower > basis_n_rows) lower = basis_n_rows;
        if (upper > basis_n_rows) upper = basis_n_rows;
        if (lower <= 0 || upper <= 0) {
            ++fallback_nonpositive_endpoint;
            ++ucalc_cpp_unsupported;
            continue;
        }
        const long long clamped_forward = (raw_upper != upper || raw_lower != lower) ? 1LL : 0LL;

        const long long rows[4] = {upper, lower, lower, upper};
        const long long cols[4] = {lower, upper, lower, upper};
        const long long raw_rows[4] = {raw_upper, raw_lower, raw_lower, raw_upper};
        const long long raw_cols[4] = {raw_lower, raw_upper, raw_lower, raw_upper};
        const long long role[4] = {1, 2, 3, 4};
        const double aj1_vals[4] = {ans1, ans2, -ans1, -ans2};
        const double aj2_vals[4] = {ans2, ans1, -ans1, -ans2};
        const double cj_vals[4] = {0.0, 0.0, ans4 * hydrogen_density_cm3, -ans3 * hydrogen_density_cm3};
        const double cj2_vals[4] = {0.0, 0.0, ans6 * hydrogen_density_cm3, -ans5 * hydrogen_density_cm3};

        const long long base = emitted_terms;
        for (int j = 0; j < 4; ++j) {
            const long long out_row = base + j;
            long long* oi = out_i64 + 20 * out_row;
            double* of = out_f64 + 10 * out_row;
            oi[0] = static_cast<long long>(term_start) + out_row;
            oi[1] = record[k];
            oi[2] = 51;
            oi[3] = 3;
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
            oi[16] = 1; // ucalc status evaluated
            oi[17] = bt_type[k];
            oi[18] = n_points[k];
            oi[19] = 0;
            of[0] = aj1_vals[j];
            of[1] = aj2_vals[j];
            of[2] = cj_vals[j];
            of[3] = cj2_vals[j];
            of[4] = ans1;
            of[5] = ans2;
            of[6] = ans3;
            of[7] = ans4;
            of[8] = ans5;
            of[9] = ans6;
        }
        emitted_terms += 4;
        ++records_supported;
        ++ucalc_cpp_applied;
    }

    out_stats[0] = records_seen;
    out_stats[1] = records_supported;
    out_stats[2] = n_records;
    out_stats[3] = n_records > 0 ? 1 : 0;
    out_stats[4] = emitted_terms;
    out_stats[5] = fallback_unsupported_rate_data;
    out_stats[6] = fallback_nonpositive_endpoint;
    out_stats[7] = fallback_nonfinite_answer;
    out_stats[8] = ucalc_cpp_applied;
    out_stats[9] = ucalc_cpp_unsupported;
    write_message(errbuf, errbuf_size, records_supported > 0 ? "xstar_matrix_build_mg_type51_rates_and_matrix evaluated" : "xstar_matrix_build_mg_type51_rates_and_matrix no supported records");
    return 0;
}



// Mg ion-level C++ backend boundary.
//
// This v0.6.0a8 entry point intentionally keeps the flat cpp/ layout and
// widens the ABI from a record-batch name to an ion-level name.  The payload
// rows are still decoded by Python, but the call is now explicitly scoped to
// one Mg ion block and returns ion-level accounting.  Future releases can move
// source-pointer traversal into this function without changing Python's high
// level call site.
//
// out_stats columns match xstar_matrix_build_mg_type51_rates_and_matrix:
//   0 records_seen
//   1 records_supported
//   2 records_batched
//   3 cpp_calls
//   4 emitted_matrix_terms
//   5 fallback_unsupported_rate_data
//   6 fallback_nonpositive_endpoint
//   7 fallback_nonfinite_answer
//   8 ucalc_cpp_applied
//   9 ucalc_cpp_unsupported
//  10 ion_cpp_calls
//  11 ion_records_batched
int xstar_matrix_eval_mg_ion_type51_rates_and_matrix(
    int n_records,
    int basis_n_rows,
    int term_start,
    long long ion_index_expected,
    long long ion_stage_expected,
    long long nlev,
    const long long* record,
    const long long* ion_index,
    const long long* ion_stage,
    const long long* compact_start,
    const long long* lower_level,
    const long long* upper_level,
    const long long* bt_type,
    const long long* n_points,
    const double* eij_ryd,
    const double* c_bt,
    const double* g_lower,
    const double* g_upper,
    const double* delta_e_ev,
    const double* y_values,
    double temperature_k,
    double electron_density_cm3,
    double hydrogen_density_cm3,
    long long* out_i64,
    double* out_f64,
    long long* out_stats,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (nlev <= 0) {
        write_message(errbuf, errbuf_size, "invalid nlev for xstar_matrix_eval_mg_ion_type51_rates_and_matrix");
        return 2;
    }
    int rc = xstar_matrix_build_mg_type51_rates_and_matrix(
        n_records, basis_n_rows, term_start,
        record, ion_index, ion_stage, compact_start, lower_level, upper_level, bt_type, n_points,
        eij_ryd, c_bt, g_lower, g_upper, delta_e_ev, y_values,
        temperature_k, electron_density_cm3, hydrogen_density_cm3,
        out_i64, out_f64, out_stats, errbuf, errbuf_size
    );
    if (out_stats) {
        out_stats[10] = (n_records > 0 && rc == 0) ? 1 : 0;
        out_stats[11] = n_records;
    }
    if (rc == 0 && errbuf && errbuf_size > 0) {
        bool ion_ok = true;
        if (ion_index && n_records > 0) ion_ok = ion_ok && (ion_index[0] == ion_index_expected);
        if (ion_stage && n_records > 0) ion_ok = ion_ok && (ion_stage[0] == ion_stage_expected);
        write_message(errbuf, errbuf_size, ion_ok ?
            "xstar_matrix_eval_mg_ion_type51_rates_and_matrix evaluated" :
            "xstar_matrix_eval_mg_ion_type51_rates_and_matrix evaluated with ion metadata mismatch");
    }
    return rc;
}


// Traverse source-pointer chains for one Mg ion in C++.
//
// The Python source-faithful evaluator still owns unsupported payload decoding,
// but this ABI moves the npfi/npnxt/npar linked-list traversal to C++ and
// returns source-ordered record headers.  supported_mask bits:
//   1: rate_type=3/data_type=51 type-51 collision group
//   2: rate_type=7 continuum/rate matrix-term group
//   4: selected simple ucalc data_type group (1,2,3,7,8,20)
// skip_mask bits:
//   1: calc_hmc_ion source exclusion (rate_type=1,data_type=53 or rate_type 8/15)
int xstar_matrix_scan_mg_ion_source_records(
    int n_data_types,
    int n_records,
    long long ion_index,
    long long ion_record,
    const long long* npfi_col,
    const long long* npar,
    const long long* npnxt,
    const long long* record_rate_type,
    const long long* record_data_type,
    long long* out_i64,
    long long* out_stats,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_data_types <= 0 || n_records <= 0 || ion_index <= 0 || ion_record <= 0) {
        write_message(errbuf, errbuf_size, "invalid dimensions for xstar_matrix_scan_mg_ion_source_records");
        return 2;
    }
    if (!npfi_col || !npar || !npnxt || !record_rate_type || !record_data_type || !out_i64 || !out_stats) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_matrix_scan_mg_ion_source_records");
        return 3;
    }

    long long seen = 0;
    long long supported = 0;
    long long emitted = 0;
    long long type51 = 0;
    long long type7 = 0;
    long long simple = 0;
    long long skipped = 0;
    long long guard_hits = 0;

    for (int data_chain = 1; data_chain < n_data_types; ++data_chain) {
        long long rec = npfi_col[data_chain];
        long long guard = 0;
        while (rec > 0 && rec <= n_records && npar[rec] == ion_record) {
            if (++guard > n_records) {
                ++guard_hits;
                break;
            }
            const long long rt = record_rate_type[rec];
            const long long dt = record_data_type[rec];
            long long support_mask = 0;
            long long skip_mask = 0;
            if ((rt == 1 && dt == 53) || rt == 8 || rt == 15) {
                skip_mask |= 1LL;
                ++skipped;
            } else {
                if (rt == 3 && dt == 51) {
                    support_mask |= 1LL;
                    ++type51;
                }
                if (rt == 7) {
                    support_mask |= 2LL;
                    ++type7;
                }
                if (dt == 1 || dt == 2 || dt == 3 || dt == 7 || dt == 8 || dt == 20) {
                    support_mask |= 4LL;
                    ++simple;
                }
                if (support_mask != 0) ++supported;
            }
            const long long base = emitted * 8;
            out_i64[base + 0] = emitted + 1;
            out_i64[base + 1] = rec;
            out_i64[base + 2] = rt;
            out_i64[base + 3] = dt;
            out_i64[base + 4] = data_chain;
            out_i64[base + 5] = (rec > 0 && rec <= n_records) ? npnxt[rec] : 0;
            out_i64[base + 6] = support_mask;
            out_i64[base + 7] = skip_mask;
            ++emitted;
            ++seen;
            rec = (rec > 0 && rec <= n_records) ? npnxt[rec] : 0;
        }
    }

    out_stats[0] = seen;
    out_stats[1] = supported;
    out_stats[2] = emitted;
    out_stats[3] = emitted > 0 ? 1 : 0;
    out_stats[4] = emitted;
    out_stats[5] = type51;
    out_stats[6] = type7;
    out_stats[7] = simple;
    out_stats[8] = skipped;
    out_stats[9] = guard_hits;
    out_stats[10] = ion_index;
    out_stats[11] = ion_record;
    write_message(errbuf, errbuf_size, "xstar_matrix_scan_mg_ion_source_records traversed ion source chains");
    return 0;
}


// Scan one Mg ion's source-pointer chains, decode selected simple packed
// payloads directly from nptrs/rdat1/idat1, and evaluate no-grid/no-level
// ucalc branches inside the ion-level matrix ABI.  This is the next step after
// xstar_matrix_scan_mg_ion_source_records: Python no longer has to construct
// UCalcRecord objects for rate/data groups that this ABI supports.
//
// Supported payload/evaluation groups:
//   data_type 1,2,3,7,8,20, across active Mg ion source chains
// Unsupported rows are not emitted; the caller falls back to Python.
//
// out_i64 columns per emitted row (10):
//   record, rate_type, data_type, data_chain, next_record, idest1, idest2,
//   status_code, support_mask, skip_mask
// out_f64 columns per emitted row (6): ans1..ans6
// out_stats columns:
//   0 records_seen
//   1 records_supported
//   2 rows_emitted
//   3 cpp_calls
//   4 simple_payload_rows
//   5 type1
//   6 type2
//   7 type3
//   8 type7
//   9 type8
//   10 type20
//   11 skipped_source_exclusions
//   12 unsupported_records
//   13 loop_guard_hits
int xstar_matrix_eval_mg_ion_source_simple_payloads(
    int n_data_types,
    int n_records,
    int n_rdat,
    int n_idat,
    long long ion_index,
    long long ion_record,
    const long long* npfi_col,
    const long long* npar,
    const long long* npnxt,
    const long long* nptrs_flat,
    const double* rdat1,
    const long long* idat1,
    double t_1e4,
    double electron_density_cm3,
    double neutral_h_density_cm3,
    double ionized_h_density_cm3,
    long long nlevp,
    long long* out_i64,
    double* out_f64,
    long long* out_stats,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_data_types <= 0 || n_records <= 0 || n_rdat < 0 || n_idat < 0 || ion_index <= 0 || ion_record <= 0) {
        write_message(errbuf, errbuf_size, "invalid dimensions for xstar_matrix_eval_mg_ion_source_simple_payloads");
        return 2;
    }
    if (!npfi_col || !npar || !npnxt || !nptrs_flat || !rdat1 || !idat1 || !out_i64 || !out_f64 || !out_stats) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_matrix_eval_mg_ion_source_simple_payloads");
        return 3;
    }
    if (!std::isfinite(t_1e4) || t_1e4 <= 0.0 || !std::isfinite(electron_density_cm3) ||
        !std::isfinite(neutral_h_density_cm3) || !std::isfinite(ionized_h_density_cm3)) {
        write_message(errbuf, errbuf_size, "non-finite thermodynamic input to xstar_matrix_eval_mg_ion_source_simple_payloads");
        return 4;
    }

    const double kt_ev_per_1e4k = 0.861707;
    const auto expo = [](double x) -> double {
        if (x < -60.0) x = -60.0;
        if (x > 60.0) x = 60.0;
        return std::exp(x);
    };
    const auto get_ptr = [&](long long rec, int col) -> long long {
        // nptrs is passed as zero-based C rows with 10 columns; rec is one-based.
        return nptrs_flat[(rec - 1) * 10 + col];
    };
    const auto get_real = [&](long long one_based) -> double {
        if (one_based <= 0 || one_based > n_rdat) return 0.0;
        return rdat1[one_based - 1];
    };
    long long seen = 0;
    long long supported = 0;
    long long emitted = 0;
    long long n_type1 = 0, n_type2 = 0, n_type3 = 0, n_type7 = 0, n_type8 = 0, n_type20 = 0;
    long long skipped = 0;
    long long unsupported = 0;
    long long guard_hits = 0;

    for (int data_chain = 1; data_chain < n_data_types; ++data_chain) {
        long long rec = npfi_col[data_chain];
        long long guard = 0;
        while (rec > 0 && rec <= n_records && npar[rec] == ion_record) {
            if (++guard > n_records) {
                ++guard_hits;
                break;
            }
            ++seen;
            const long long dt = get_ptr(rec, 1);
            const long long rt = get_ptr(rec, 2);
            const long long nreal = get_ptr(rec, 4);
            const long long real_ptr = get_ptr(rec, 7);
            long long skip_mask = 0;
            if ((rt == 1 && dt == 53) || rt == 8 || rt == 15) {
                skip_mask = 1;
                ++skipped;
                rec = (rec > 0 && rec <= n_records) ? npnxt[rec] : 0;
                continue;
            }
            bool ok = false;
            double ans[6] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
            long long id1 = 0;
            long long id2 = 0;
            long long support_mask = 0;
            const double r0 = nreal >= 1 ? get_real(real_ptr + 0) : 0.0;
            const double r1 = nreal >= 2 ? get_real(real_ptr + 1) : 0.0;
            const double r2 = nreal >= 3 ? get_real(real_ptr + 2) : 0.0;
            const double r3 = nreal >= 4 ? get_real(real_ptr + 3) : 0.0;
            const double r4 = nreal >= 5 ? get_real(real_ptr + 4) : 0.0;
            const double r5 = nreal >= 6 ? get_real(real_ptr + 5) : 0.0;
            const double r6 = nreal >= 7 ? get_real(real_ptr + 6) : 0.0;
            const double r7 = nreal >= 8 ? get_real(real_ptr + 7) : 0.0;
            if (dt == 1 && nreal >= 2) {
                ans[0] = r0 / std::pow(t_1e4, r1) * electron_density_cm3;
                id1 = 1;
                ok = true;
                ++n_type1;
            } else if (dt == 2 && nreal >= 4) {
                id1 = 1;
                id2 = nlevp;
                if (t_1e4 <= 5.0) {
                    const double rate = r0 * std::pow(t_1e4, r1) * std::max(0.0, 1.0 + r2 * expo(r3 * t_1e4)) * 1.0e-9;
                    double a1 = rate * neutral_h_density_cm3;
                    double a2 = 0.0;
                    if (rt == 5) { a2 = a1; a1 = 0.0; }
                    ans[0] = a1; ans[1] = a2;
                }
                ok = true;
                ++n_type2;
            } else if (dt == 3 && nreal >= 2) {
                ans[0] = r0 * expo(-r1 / (kt_ev_per_1e4k * t_1e4)) / std::sqrt(t_1e4) * electron_density_cm3;
                id1 = 1;
                id2 = 1;
                ok = true;
                ++n_type3;
            } else if (dt == 7 && nreal >= 4) {
                const double rate = r0 * 1.0e-6 * expo(-r2 / t_1e4) * (1.0 + r1 * expo(-r3 / t_1e4)) / (t_1e4 * std::sqrt(t_1e4));
                ans[0] = rate * electron_density_cm3;
                id1 = 1;
                ok = true;
                ++n_type7;
            } else if (dt == 8 && nreal >= 8) {
                double rate = 0.0;
                rate += r0 * expo(-r4 / (kt_ev_per_1e4k * t_1e4));
                rate += r1 * expo(-r5 / (kt_ev_per_1e4k * t_1e4));
                rate += r2 * expo(-r6 / (kt_ev_per_1e4k * t_1e4));
                rate += r3 * expo(-r7 / (kt_ev_per_1e4k * t_1e4));
                rate *= 1.0e-6 * std::pow(t_1e4, -1.5);
                ans[0] = rate * electron_density_cm3;
                id1 = 1;
                ok = true;
                ++n_type8;
            } else if (dt == 20 && nreal >= 5) {
                const double rate = r0 * std::pow(t_1e4, r1) * (1.0 + r2 * expo(r3 * t_1e4)) * expo(-r4 / t_1e4) * 1.0e-9;
                ans[0] = rate * ionized_h_density_cm3;
                id1 = 1;
                id2 = nlevp;
                ok = true;
                ++n_type20;
            }

            if (!ok || !finite6(ans[0], ans[1], ans[2], ans[3], ans[4], ans[5]) || id1 <= 0) {
                ++unsupported;
                rec = (rec > 0 && rec <= n_records) ? npnxt[rec] : 0;
                continue;
            }
            support_mask = 4;
            long long* oi = out_i64 + emitted * 10;
            double* of = out_f64 + emitted * 6;
            oi[0] = rec;
            oi[1] = rt;
            oi[2] = dt;
            oi[3] = data_chain;
            oi[4] = (rec > 0 && rec <= n_records) ? npnxt[rec] : 0;
            oi[5] = id1;
            oi[6] = id2;
            oi[7] = 1;
            oi[8] = support_mask;
            oi[9] = skip_mask;
            for (int j = 0; j < 6; ++j) of[j] = ans[j];
            ++emitted;
            ++supported;
            rec = (rec > 0 && rec <= n_records) ? npnxt[rec] : 0;
        }
    }

    out_stats[0] = seen;
    out_stats[1] = supported;
    out_stats[2] = emitted;
    out_stats[3] = emitted > 0 ? 1 : 0;
    out_stats[4] = emitted;
    out_stats[5] = n_type1;
    out_stats[6] = n_type2;
    out_stats[7] = n_type3;
    out_stats[8] = n_type7;
    out_stats[9] = n_type8;
    out_stats[10] = n_type20;
    out_stats[11] = skipped;
    out_stats[12] = unsupported;
    out_stats[13] = guard_hits;
    write_message(errbuf, errbuf_size, supported > 0 ? "xstar_matrix_eval_mg_ion_source_simple_payloads evaluated" : "xstar_matrix_eval_mg_ion_source_simple_payloads no supported payloads");
    return 0;
}


// Experimental direct Mg-ion accumulator for selected simple payload groups.
//
// This ABI combines source-pointer traversal, payload decoding, selected
// ucalc evaluation, and direct matrix-term emission.  It is intentionally
// conservative and currently emits only records with positive compact
// endpoints.  Unsupported records are left for Python fallback.
//
// out_i64 columns per emitted term, 16 columns, identical to
// xstar_matrix_build_mg_type7_terms.
// out_f64 columns per emitted term, 4 columns: aj1, aj2, cj, cj2.
// out_stats columns:
//   0 records_seen
//   1 records_supported
//   2 emitted_terms
//   3 cpp_calls
//   4 direct_accumulated_records
//   5 type1
//   6 type2
//   7 type3
//   8 type7
//   9 type8
//   10 type20
//   11 skipped_source_exclusions
//   12 unsupported_records
//   13 loop_guard_hits
int xstar_matrix_accumulate_mg_ion_source_simple_terms(
    int n_data_types,
    int n_records,
    int n_rdat,
    int n_idat,
    int basis_n_rows,
    int term_start,
    long long ion_index,
    long long ion_stage,
    long long ion_record,
    long long compact_start,
    long long nlevp,
    const long long* npfi_col,
    const long long* npar,
    const long long* npnxt,
    const long long* nptrs_flat,
    const double* rdat1,
    const long long* idat1,
    double t_1e4,
    double electron_density_cm3,
    double neutral_h_density_cm3,
    double ionized_h_density_cm3,
    double xpx,
    long long* out_i64,
    double* out_f64,
    long long* out_stats,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (n_data_types <= 0 || n_records <= 0 || n_rdat < 0 || n_idat < 0 || basis_n_rows <= 0 ||
        term_start <= 0 || ion_index <= 0 || ion_stage <= 0 || ion_record <= 0 || compact_start <= 0 || nlevp <= 0) {
        write_message(errbuf, errbuf_size, "invalid dimensions for xstar_matrix_accumulate_mg_ion_source_simple_terms");
        return 2;
    }
    if (!npfi_col || !npar || !npnxt || !nptrs_flat || !rdat1 || !idat1 || !out_i64 || !out_f64 || !out_stats) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_matrix_accumulate_mg_ion_source_simple_terms");
        return 3;
    }
    if (!std::isfinite(t_1e4) || t_1e4 <= 0.0 || !std::isfinite(electron_density_cm3) ||
        !std::isfinite(neutral_h_density_cm3) || !std::isfinite(ionized_h_density_cm3) || !std::isfinite(xpx)) {
        write_message(errbuf, errbuf_size, "non-finite thermodynamic input to xstar_matrix_accumulate_mg_ion_source_simple_terms");
        return 4;
    }

    const double kt_ev_per_1e4k = 0.861707;
    const auto expo = [](double x) -> double {
        if (x < -60.0) x = -60.0;
        if (x > 60.0) x = 60.0;
        return std::exp(x);
    };
    const auto get_ptr = [&](long long rec, int col) -> long long {
        return nptrs_flat[(rec - 1) * 10 + col];
    };
    const auto get_real = [&](long long one_based) -> double {
        if (one_based <= 0 || one_based > n_rdat) return 0.0;
        return rdat1[one_based - 1];
    };
    const auto emit_terms = [&](long long rec, long long dt, long long rt, long long id1, long long id2,
                                const double ans[6], long long& emitted_terms) -> bool {
        if (id1 <= 0 || id2 <= 0 || !finite6(ans[0], ans[1], ans[2], ans[3], ans[4], ans[5])) return false;
        const long long raw_lower = compact_start + id1 - 1;
        const long long raw_upper = compact_start + id2 - 1;
        if (raw_lower <= 0 || raw_upper <= 0) return false;
        long long lower = raw_lower;
        long long upper = raw_upper;
        if (lower > basis_n_rows) lower = basis_n_rows;
        if (upper > basis_n_rows) upper = basis_n_rows;
        if (lower <= 0 || upper <= 0) return false;
        const long long clamped = (raw_upper != upper || raw_lower != lower) ? 1LL : 0LL;
        const long long rows[4] = {upper, lower, lower, upper};
        const long long cols[4] = {lower, upper, lower, upper};
        const long long raw_rows[4] = {raw_upper, raw_lower, raw_lower, raw_upper};
        const long long raw_cols[4] = {raw_lower, raw_upper, raw_lower, raw_upper};
        const long long role[4] = {1, 2, 3, 4};
        const double aj1[4] = {ans[0], ans[1], -ans[0], -ans[1]};
        const double aj2[4] = {ans[1], ans[0], -ans[0], -ans[1]};
        const double cj[4] = {0.0, 0.0, ans[3] * xpx, -ans[2] * xpx};
        const double cj2[4] = {0.0, 0.0, ans[5] * xpx, -ans[4] * xpx};
        for (int j = 0; j < 4; ++j) {
            long long* oi = out_i64 + 16 * (emitted_terms + j);
            double* of = out_f64 + 4 * (emitted_terms + j);
            oi[0] = static_cast<long long>(term_start + emitted_terms + j);
            oi[1] = rec;
            oi[2] = dt;
            oi[3] = rt;
            oi[4] = ion_index;
            oi[5] = ion_stage;
            oi[6] = role[j];
            oi[7] = rows[j];
            oi[8] = cols[j];
            oi[9] = id1;
            oi[10] = id2;
            oi[11] = id1;
            oi[12] = id2;
            oi[13] = raw_rows[j];
            oi[14] = raw_cols[j];
            oi[15] = clamped;
            of[0] = aj1[j];
            of[1] = aj2[j];
            of[2] = cj[j];
            of[3] = cj2[j];
        }
        emitted_terms += 4;
        return true;
    };

    long long seen = 0, supported = 0, emitted_terms = 0;
    long long n_type1 = 0, n_type2 = 0, n_type3 = 0, n_type7 = 0, n_type8 = 0, n_type20 = 0;
    long long skipped = 0, unsupported = 0, guard_hits = 0;

    for (int data_chain = 1; data_chain < n_data_types; ++data_chain) {
        long long rec = npfi_col[data_chain];
        long long guard = 0;
        while (rec > 0 && rec <= n_records && npar[rec] == ion_record) {
            if (++guard > n_records) { ++guard_hits; break; }
            ++seen;
            const long long dt = get_ptr(rec, 1);
            const long long rt = get_ptr(rec, 2);
            const long long nreal = get_ptr(rec, 4);
            const long long real_ptr = get_ptr(rec, 7);
            if ((rt == 1 && dt == 53) || rt == 8 || rt == 15) {
                ++skipped;
                rec = (rec > 0 && rec <= n_records) ? npnxt[rec] : 0;
                continue;
            }
            double ans[6] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
            long long id1 = 0;
            long long id2 = 0;
            const double r0 = nreal >= 1 ? get_real(real_ptr + 0) : 0.0;
            const double r1 = nreal >= 2 ? get_real(real_ptr + 1) : 0.0;
            const double r2 = nreal >= 3 ? get_real(real_ptr + 2) : 0.0;
            const double r3 = nreal >= 4 ? get_real(real_ptr + 3) : 0.0;
            const double r4 = nreal >= 5 ? get_real(real_ptr + 4) : 0.0;
            const double r5 = nreal >= 6 ? get_real(real_ptr + 5) : 0.0;
            const double r6 = nreal >= 7 ? get_real(real_ptr + 6) : 0.0;
            const double r7 = nreal >= 8 ? get_real(real_ptr + 7) : 0.0;

            bool evaluated = false;
            if (dt == 1 && nreal >= 2) {
                ans[0] = r0 / std::pow(t_1e4, r1) * electron_density_cm3;
                id1 = 1; id2 = nlevp;
                evaluated = true; ++n_type1;
            } else if (dt == 2 && nreal >= 4) {
                id1 = 1; id2 = nlevp;
                if (t_1e4 <= 5.0) {
                    const double rate = r0 * std::pow(t_1e4, r1) * std::max(0.0, 1.0 + r2 * expo(r3 * t_1e4)) * 1.0e-9;
                    double a1 = rate * neutral_h_density_cm3;
                    double a2 = 0.0;
                    if (rt == 5) { a2 = a1; a1 = 0.0; }
                    ans[0] = a1; ans[1] = a2;
                }
                evaluated = true; ++n_type2;
            } else if (dt == 3 && nreal >= 2) {
                ans[0] = r0 * expo(-r1 / (kt_ev_per_1e4k * t_1e4)) / std::sqrt(t_1e4) * electron_density_cm3;
                id1 = 1; id2 = nlevp;
                evaluated = true; ++n_type3;
            } else if (dt == 7 && nreal >= 4) {
                const double rate = r0 * 1.0e-6 * expo(-r2 / t_1e4) * (1.0 + r1 * expo(-r3 / t_1e4)) / (t_1e4 * std::sqrt(t_1e4));
                ans[0] = rate * electron_density_cm3;
                id1 = 1; id2 = nlevp;
                evaluated = true; ++n_type7;
            } else if (dt == 8 && nreal >= 8) {
                double rate = 0.0;
                rate += r0 * expo(-r4 / (kt_ev_per_1e4k * t_1e4));
                rate += r1 * expo(-r5 / (kt_ev_per_1e4k * t_1e4));
                rate += r2 * expo(-r6 / (kt_ev_per_1e4k * t_1e4));
                rate += r3 * expo(-r7 / (kt_ev_per_1e4k * t_1e4));
                rate *= 1.0e-6 * std::pow(t_1e4, -1.5);
                ans[0] = rate * electron_density_cm3;
                id1 = 1; id2 = nlevp;
                evaluated = true; ++n_type8;
            } else if (dt == 20 && nreal >= 5) {
                const double rate = r0 * std::pow(t_1e4, r1) * (1.0 + r2 * expo(r3 * t_1e4)) * expo(-r4 / t_1e4) * 1.0e-9;
                ans[0] = rate * ionized_h_density_cm3;
                id1 = 1; id2 = nlevp;
                evaluated = true; ++n_type20;
            }

            if (!evaluated || !emit_terms(rec, dt, rt, id1, id2, ans, emitted_terms)) {
                ++unsupported;
            } else {
                ++supported;
            }
            rec = (rec > 0 && rec <= n_records) ? npnxt[rec] : 0;
        }
    }

    out_stats[0] = seen;
    out_stats[1] = supported;
    out_stats[2] = emitted_terms;
    out_stats[3] = supported > 0 ? 1 : 0;
    out_stats[4] = supported;
    out_stats[5] = n_type1;
    out_stats[6] = n_type2;
    out_stats[7] = n_type3;
    out_stats[8] = n_type7;
    out_stats[9] = n_type8;
    out_stats[10] = n_type20;
    out_stats[11] = skipped;
    out_stats[12] = unsupported;
    out_stats[13] = guard_hits;
    write_message(errbuf, errbuf_size, supported > 0 ? "xstar_matrix_accumulate_mg_ion_source_simple_terms evaluated" : "xstar_matrix_accumulate_mg_ion_source_simple_terms no supported records");
    return 0;
}


}  // extern "C"
