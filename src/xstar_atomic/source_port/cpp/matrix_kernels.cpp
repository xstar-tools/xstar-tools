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
    return "xstar_matrix_mg_type7_terms_dense_ucalc_v1";
}

int xstar_matrix_feature_flags() {
    // 1: skeleton/probe; 2: Mg record_type=7 matrix-term construction; 4: dense matrix fill; 8: selected simple ucalc branches.
    return 1 | 2 | 4 | 8;
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


}  // extern "C"
