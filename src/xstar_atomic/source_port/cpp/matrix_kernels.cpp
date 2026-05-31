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
    return "xstar_matrix_mg_type7_terms_dense_ucalc_type51_v1";
}

int xstar_matrix_feature_flags() {
    // 1: skeleton/probe; 2: Mg record_type=7 matrix-term construction; 4: dense matrix fill; 8: selected simple ucalc branches.
    return 1 | 2 | 4 | 8 | 16;
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
        if (n_points[k] != 5 || eij_ryd[k] <= 0.0 || c_bt[k] <= 0.0 || g_lower[k] <= 0.0 || g_upper[k] <= 0.0 || delta_e_ev[k] <= 0.0) continue;
        double ups = 0.0;
        const double* y = y_values + 9 * k;
        const double eij_ev = eij_ryd[k] * 13.605692;
        const double wavelength_a = 12398.4016 / eij_ev;
        const double floor_k = 2.8777e6 / wavelength_a;
        const double bt_temperature_k = std::max(temperature_k, floor_k);
        if (!xstar_matrix_type51_upsilon5(bt_type[k], eij_ryd[k], c_bt[k], y, bt_temperature_k, &ups)) continue;
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
        ans[4] = ans2 * delta_e_ev[k] * 1.602176634e-12;
        ans[5] = ans1 * delta_e_ev[k] * 1.602176634e-12;
        oi[7] = 1;
        ++applied;
    }
    write_message(errbuf, errbuf_size, applied > 0 ? "xstar_matrix_eval_type51_ucalc_batch evaluated" : "xstar_matrix_eval_type51_ucalc_batch no supported records");
    return 0;
}


}  // extern "C"
