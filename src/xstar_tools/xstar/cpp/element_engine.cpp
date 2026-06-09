#include "xstar_element_engine.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

extern "C" int xstar_solver_leqt2f(
    const double* a,
    const double* b,
    int n,
    int clamp,
    double* solution,
    double* residual,
    double* max_scaled_residual,
    char* error_message,
    size_t error_message_len
);

namespace {

using clock_type = std::chrono::steady_clock;

void copy_text(char* target, std::size_t capacity, const std::string& value) {
    if (!target || capacity == 0) return;
    const std::size_t n = std::min(capacity - 1, value.size());
    std::memcpy(target, value.data(), n);
    target[n] = '\0';
}

double seconds_since(const clock_type::time_point& start) {
    return std::chrono::duration<double>(clock_type::now() - start).count();
}

struct Workspace {
    int n = 0;
    int nsp = 0;
    int nion = 0;
    std::vector<double> dense;
    std::vector<double> heat;
    std::vector<double> heat2;
    std::vector<double> rhs;
    std::vector<double> x;
    std::vector<double> xo;
    std::vector<double> outer_start;
    std::vector<double> final_outer_start;
    std::vector<double> p;
    std::vector<double> rr;
    std::vector<double> condensed;
    std::vector<double> solve_rhs;
    std::vector<double> solve_result;
    std::vector<double> solve_residual;
    std::vector<double> xold;
    std::vector<double> riu;
    std::vector<double> rui;
    std::vector<double> ril;
    std::vector<double> rli;
    std::vector<double> gamma;
    std::vector<double> alpha;
    std::vector<double> fgamma;
    std::vector<double> falpha;
    std::vector<double> gammamax;
    std::vector<double> alphamax;
    std::vector<std::int64_t> igammamax;
    std::vector<std::int64_t> ialphamax;
    std::vector<double> ion_population_totals;
    std::vector<double> ion_population_totals_final;
    std::vector<double> ionization_totals;
    std::vector<double> recombination_totals;
    std::vector<double> ionization_components;
    std::vector<double> recombination_components;
    std::vector<double> residual;
    std::vector<double> row_scale;
    std::vector<double> relative_residual;

    bool ensure(int new_n, int new_nsp, int new_nion) {
        const bool resized = new_n != n || new_nsp != nsp || new_nion != nion;
        n = new_n;
        nsp = new_nsp;
        nion = new_nion;
        const std::size_t nn = static_cast<std::size_t>(n) * static_cast<std::size_t>(n);
        const std::size_t ss = static_cast<std::size_t>(nsp) * static_cast<std::size_t>(nsp);
        dense.assign(nn, 0.0);
        heat.assign(nn, 0.0);
        heat2.assign(nn, 0.0);
        rhs.assign(static_cast<std::size_t>(n), 0.0);
        x.resize(static_cast<std::size_t>(n));
        xo.resize(static_cast<std::size_t>(n));
        outer_start.resize(static_cast<std::size_t>(n));
        final_outer_start.resize(static_cast<std::size_t>(n));
        p.resize(static_cast<std::size_t>(nsp));
        rr.resize(static_cast<std::size_t>(n));
        condensed.resize(ss);
        solve_rhs.resize(static_cast<std::size_t>(std::max(n, nsp)));
        solve_result.resize(static_cast<std::size_t>(std::max(n, nsp)));
        solve_residual.resize(static_cast<std::size_t>(std::max(n, nsp)));
        xold.resize(static_cast<std::size_t>(n));
        riu.resize(static_cast<std::size_t>(n));
        rui.resize(static_cast<std::size_t>(n));
        ril.resize(static_cast<std::size_t>(n));
        rli.resize(static_cast<std::size_t>(n));
        gamma.assign(static_cast<std::size_t>(n), 0.0);
        alpha.assign(static_cast<std::size_t>(n), 0.0);
        fgamma.assign(static_cast<std::size_t>(5 * n), 0.0);
        falpha.assign(static_cast<std::size_t>(5 * n), 0.0);
        gammamax.assign(static_cast<std::size_t>(n), 0.0);
        alphamax.assign(static_cast<std::size_t>(n), 0.0);
        igammamax.assign(static_cast<std::size_t>(n), 0);
        ialphamax.assign(static_cast<std::size_t>(n), 0);
        ion_population_totals.assign(static_cast<std::size_t>(nion), 0.0);
        ion_population_totals_final.assign(static_cast<std::size_t>(nion), 0.0);
        ionization_totals.assign(static_cast<std::size_t>(nion), 0.0);
        recombination_totals.assign(static_cast<std::size_t>(nion), 0.0);
        ionization_components.assign(static_cast<std::size_t>(3 * nion), 0.0);
        recombination_components.assign(static_cast<std::size_t>(3 * nion), 0.0);
        residual.assign(static_cast<std::size_t>(n), 0.0);
        row_scale.assign(static_cast<std::size_t>(n), 0.0);
        relative_residual.assign(static_cast<std::size_t>(n), 0.0);
        return resized;
    }
};

struct xstar_element_engine_context_impl {
    Workspace workspace;
    xstar_element_engine_stats_v1 stats{};
};

inline std::size_t index2(int row, int col, int ncols) {
    return static_cast<std::size_t>(row) * static_cast<std::size_t>(ncols) + static_cast<std::size_t>(col);
}

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void validate_input(const xstar_element_input_v1& input) {
    require(input.struct_size >= sizeof(xstar_element_input_v1), "element input struct_size is too small");
    require(input.abi_version == XSTAR_ELEMENT_ENGINE_ABI_VERSION, "element input ABI mismatch");
    require(input.n_rows > 0, "element input requires n_rows > 0");
    require(input.n_superlevels > 0, "element input requires n_superlevels > 0");
    require(input.n_ions > 0, "element input requires n_ions > 0");
    require(input.normalization_row >= 1 && input.normalization_row <= input.n_rows,
            "normalization_row is outside the compact basis");
    require(input.max_lucy_iterations > 0 && input.max_fixed_point_iterations > 0,
            "iteration limits must be positive");
    require(input.lucy_tolerance >= 0.0 && input.fixed_point_tolerance >= 0.0,
            "iteration tolerances must be non-negative");
    require(input.superlevel_by_row != nullptr, "superlevel_by_row is null");
    require(input.ion_by_row != nullptr, "ion_by_row is null");
    require(input.initial_populations != nullptr, "initial_populations is null");
    if (input.term_count > 0) require(input.terms != nullptr, "terms pointer is null");
    for (int i = 0; i < input.n_rows; ++i) {
        require(input.superlevel_by_row[i] >= 1 && input.superlevel_by_row[i] <= input.n_superlevels,
                "superlevel index outside range");
        require(input.ion_by_row[i] >= 1 && input.ion_by_row[i] <= input.n_ions,
                "ion index outside range");
        require(std::isfinite(input.initial_populations[i]) && input.initial_populations[i] >= 0.0,
                "initial populations must be finite and non-negative");
    }
}

void validate_output(const xstar_element_input_v1& input, xstar_element_output_v1& output) {
    require(output.struct_size >= sizeof(xstar_element_output_v1), "element output struct_size is too small");
    require(output.abi_version == XSTAR_ELEMENT_ENGINE_ABI_VERSION, "element output ABI mismatch");
    const std::size_t n = static_cast<std::size_t>(input.n_rows);
    const std::size_t nion = static_cast<std::size_t>(input.n_ions);
    require(output.populations && output.populations_capacity >= n, "populations output buffer too small");
    require(output.gamma && output.gamma_capacity >= n, "gamma output buffer too small");
    require(output.alpha && output.alpha_capacity >= n, "alpha output buffer too small");
    require(output.fgamma && output.fgamma_capacity >= 5u * n, "fgamma output buffer too small");
    require(output.falpha && output.falpha_capacity >= 5u * n, "falpha output buffer too small");
    require(output.igammamax_record && output.igammamax_capacity >= n, "igammamax output buffer too small");
    require(output.ialphamax_record && output.ialphamax_capacity >= n, "ialphamax output buffer too small");
    require(output.ion_population_totals && output.ion_population_totals_capacity >= nion,
            "ion population totals output buffer too small");
    require(output.ion_population_totals_final_vector && output.ion_population_totals_final_capacity >= nion,
            "final ion population totals output buffer too small");
    require(output.ionization_totals && output.ionization_totals_capacity >= nion,
            "ionization totals output buffer too small");
    require(output.recombination_totals && output.recombination_totals_capacity >= nion,
            "recombination totals output buffer too small");
    require(output.ionization_components && output.ionization_components_capacity >= 3u * nion,
            "ionization components output buffer too small");
    require(output.recombination_components && output.recombination_components_capacity >= 3u * nion,
            "recombination components output buffer too small");
    if (input.flags & XSTAR_ELEMENT_RETURN_MATRICES) {
        const std::size_t nn = n * n;
        require(output.dense_matrix && output.dense_matrix_capacity >= nn, "dense matrix output buffer too small");
        require(output.heating_matrix && output.heating_matrix_capacity >= nn, "heating matrix output buffer too small");
        require(output.heating_matrix2 && output.heating_matrix2_capacity >= nn, "heating matrix2 output buffer too small");
        require(output.rhs && output.rhs_capacity >= n, "rhs output buffer too small");
    }
    if (input.flags & XSTAR_ELEMENT_DIAGNOSTICS_SUMMARY) {
        require(output.row_residual && output.row_residual_capacity >= n, "row residual output buffer too small");
        require(output.row_scale && output.row_scale_capacity >= n, "row scale output buffer too small");
        require(output.relative_row_residual && output.relative_row_residual_capacity >= n,
                "relative row residual output buffer too small");
        require(output.final_outer_start_populations && output.final_outer_start_capacity >= n,
                "final outer-start output buffer too small");
    }
}

bool verify_source_order(const xstar_element_input_v1& input) {
    std::int64_t previous = std::numeric_limits<std::int64_t>::min();
    for (std::size_t i = 0; i < input.term_count; ++i) {
        const auto& term = input.terms[i];
        require(term.row >= 1 && term.row <= input.n_rows, "term row outside compact basis");
        require(term.column >= 1 && term.column <= input.n_rows, "term column outside compact basis");
        require(std::isfinite(term.aj1) && std::isfinite(term.aj2) &&
                std::isfinite(term.cj) && std::isfinite(term.cj2), "non-finite matrix term");
        if (term.source_position < previous) return false;
        previous = term.source_position;
    }
    return true;
}

void solve_normalized(
    std::vector<double>& matrix,
    int dimension,
    int normalization_row_one_based,
    std::vector<double>& rhs,
    std::vector<double>& result,
    std::vector<double>& residual,
    const char* label
) {
    std::fill(rhs.begin(), rhs.begin() + dimension, 0.0);
    const int row = normalization_row_one_based - 1;
    for (int col = 0; col < dimension; ++col) matrix[index2(row, col, dimension)] = 1.0;
    rhs[static_cast<std::size_t>(row)] = 1.0;
    double max_scaled = 0.0;
    char error[1024] = {};
    const int rc = xstar_solver_leqt2f(
        matrix.data(), rhs.data(), dimension, 1, result.data(), residual.data(),
        &max_scaled, error, sizeof(error));
    if (rc != 0) {
        std::ostringstream text;
        text << label << " solve failed: " << error;
        throw std::runtime_error(text.str());
    }
}

double source_fixed_difference(const std::vector<double>& previous, const std::vector<double>& current) {
    double diff2 = 0.0;
    double tst = 0.0;
    std::size_t index = 0;
    while (diff2 < 1.0e3 && index < current.size() && tst < 1.0e3) {
        tst = 1.0;
        if (current[index] > 1.0e-6) tst = previous[index] / current[index];
        const double d = tst - 1.0;
        diff2 += d * d;
        ++index;
    }
    return diff2;
}

double source_outer_difference(const std::vector<double>& previous, const std::vector<double>& current) {
    double diff = 0.0;
    std::size_t index = 0;
    while (index < current.size() && diff < 1.0e3) {
        if (diff < 1.0e10 && current[index] > 1.0e-6) {
            const double ratio = (previous[index] - current[index]) /
                                 (previous[index] + current[index]);
            const double capped = std::min(1.0e10, ratio);
            diff += capped * capped;
        }
        ++index;
    }
    return diff;
}

template <typename T>
void copy_vector(const std::vector<T>& source, T* target, std::size_t capacity, const char* label) {
    require(target != nullptr && capacity >= source.size(), std::string(label) + " output buffer too small");
    std::copy(source.begin(), source.end(), target);
}

int run_element_impl(
    xstar_element_engine_context_impl& context,
    const xstar_element_input_v1& input,
    xstar_element_output_v1& output,
    std::string& status_message
) {
    validate_input(input);
    validate_output(input, output);
    context.stats.elements_attempted += 1;

    const bool ordered = verify_source_order(input);
    if ((input.flags & XSTAR_ELEMENT_STRICT_SOURCE_ORDER) && !ordered) {
        context.stats.source_order_failures += 1;
        throw std::runtime_error("element term stream is not in source-position order");
    }

    Workspace& w = context.workspace;
    if (w.ensure(input.n_rows, input.n_superlevels, input.n_ions)) context.stats.workspace_resizes += 1;
    const int n = input.n_rows;
    const int nsp = input.n_superlevels;
    const int nion = input.n_ions;

    const auto assembly_t0 = clock_type::now();
    std::fill(w.dense.begin(), w.dense.end(), 0.0);
    std::fill(w.heat.begin(), w.heat.end(), 0.0);
    std::fill(w.heat2.begin(), w.heat2.end(), 0.0);
    std::fill(w.rhs.begin(), w.rhs.end(), 0.0);
    for (std::size_t i = 0; i < input.term_count; ++i) {
        const auto& term = input.terms[i];
        const std::size_t p = index2(term.row - 1, term.column - 1, n);
        w.dense[p] += term.aj1;
        w.heat[p] += term.cj;
        w.heat2[p] += term.cj2;
    }
    w.rhs[static_cast<std::size_t>(input.normalization_row - 1)] = 1.0;
    output.matrix_assembly_seconds = seconds_since(assembly_t0);
    context.stats.matrix_assembly_seconds += output.matrix_assembly_seconds;
    context.stats.terms_committed += input.term_count;

    const auto solver_t0 = clock_type::now();
    std::copy(input.initial_populations, input.initial_populations + n, w.x.begin());
    w.final_outer_start = w.x;
    double outer_diff = 1.0;
    double fixed_diff = 0.0;
    int outer = 0;
    int total_fixed = 0;
    bool dense_rescue_used = false;

    while (outer_diff > input.lucy_tolerance && outer < input.max_lucy_iterations) {
        ++outer;
        w.xo = w.x;
        w.outer_start = w.x;
        w.final_outer_start = w.outer_start;
        std::fill(w.p.begin(), w.p.end(), 0.0);
        for (int i = 0; i < n; ++i) {
            const int sp = input.superlevel_by_row[i] - 1;
            w.p[static_cast<std::size_t>(sp)] += w.x[static_cast<std::size_t>(i)];
        }
        std::fill(w.rr.begin(), w.rr.end(), 1.0);
        for (int i = 0; i < n; ++i) {
            const int sp = input.superlevel_by_row[i] - 1;
            if (w.p[static_cast<std::size_t>(sp)] > 1.0e-36) {
                w.rr[static_cast<std::size_t>(i)] =
                    w.x[static_cast<std::size_t>(i)] /
                    (1.0e-48 + w.p[static_cast<std::size_t>(sp)]);
            }
        }
        std::fill(w.condensed.begin(), w.condensed.end(), 0.0);
        for (std::size_t k = 0; k < input.term_count; ++k) {
            const auto& term = input.terms[k];
            const int mm = std::min(n, term.row) - 1;
            const int nn = std::min(n, term.column) - 1;
            const int spm = input.superlevel_by_row[mm] - 1;
            const int spn = input.superlevel_by_row[nn] - 1;
            if (spm != spn && (std::fabs(term.aj1) > 1.0e-48 || std::fabs(term.aj2) > 1.0e-48)) {
                w.condensed[index2(spm, spn, nsp)] += term.aj1 * w.rr[static_cast<std::size_t>(nn)];
                w.condensed[index2(spm, spm, nsp)] -= term.aj2 * w.rr[static_cast<std::size_t>(mm)];
            }
        }
        solve_normalized(w.condensed, nsp, nsp, w.solve_rhs, w.solve_result, w.solve_residual,
                         "condensed Lucy");
        for (int i = 0; i < n; ++i) {
            const int sp = input.superlevel_by_row[i] - 1;
            w.x[static_cast<std::size_t>(i)] =
                w.rr[static_cast<std::size_t>(i)] * w.solve_result[static_cast<std::size_t>(sp)];
        }

        fixed_diff = 10.0;
        int fixed_iter = 0;
        while (fixed_iter < input.max_fixed_point_iterations &&
               fixed_diff >= input.fixed_point_tolerance) {
            ++fixed_iter;
            ++total_fixed;
            w.xold = w.x;
            std::fill(w.riu.begin(), w.riu.end(), 0.0);
            std::fill(w.rui.begin(), w.rui.end(), 0.0);
            std::fill(w.ril.begin(), w.ril.end(), 0.0);
            std::fill(w.rli.begin(), w.rli.end(), 0.0);
            for (std::size_t k = 0; k < input.term_count; ++k) {
                const auto& term = input.terms[k];
                const int mm = term.row - 1;
                const int nn = std::min(n, term.column) - 1;
                if (nn > mm) {
                    w.riu[static_cast<std::size_t>(mm)] += std::fabs(term.aj2);
                    w.rui[static_cast<std::size_t>(mm)] +=
                        std::fabs(term.aj1) * w.x[static_cast<std::size_t>(nn)];
                } else if (nn < mm) {
                    w.ril[static_cast<std::size_t>(mm)] += std::fabs(term.aj2);
                    w.rli[static_cast<std::size_t>(mm)] +=
                        std::fabs(term.aj1) * w.x[static_cast<std::size_t>(nn)];
                }
            }
            double total = 0.0;
            for (int i = 0; i < n; ++i) {
                const std::size_t ii = static_cast<std::size_t>(i);
                w.x[ii] = (w.rli[ii] + w.rui[ii]) / (w.ril[ii] + w.riu[ii] + 1.0e-24);
                total += w.x[ii];
            }
            if ((!std::isfinite(total) || total <= 0.0) &&
                (input.flags & XSTAR_ELEMENT_ALLOW_DENSE_RESCUE)) {
                std::vector<double> dense_copy = w.dense;
                solve_normalized(dense_copy, n, input.normalization_row, w.solve_rhs,
                                 w.solve_result, w.solve_residual, "dense rescue");
                std::copy(w.solve_result.begin(), w.solve_result.begin() + n, w.x.begin());
                dense_rescue_used = true;
                fixed_diff = 0.0;
                outer_diff = 0.0;
                break;
            }
            const double denominator = 1.0e-24 + total;
            for (double& value : w.x) value /= denominator;
            fixed_diff = source_fixed_difference(w.xold, w.x);
            if (fixed_diff >= 1.0e3) break;
        }
        if (dense_rescue_used) break;
        outer_diff = source_outer_difference(w.xo, w.x);
    }

    output.solver_seconds = seconds_since(solver_t0);
    context.stats.solver_seconds += output.solver_seconds;

    const auto commit_t0 = clock_type::now();
    std::fill(w.gamma.begin(), w.gamma.end(), 0.0);
    std::fill(w.alpha.begin(), w.alpha.end(), 0.0);
    std::fill(w.fgamma.begin(), w.fgamma.end(), 0.0);
    std::fill(w.falpha.begin(), w.falpha.end(), 0.0);
    std::fill(w.gammamax.begin(), w.gammamax.end(), 0.0);
    std::fill(w.alphamax.begin(), w.alphamax.end(), 0.0);
    std::fill(w.igammamax.begin(), w.igammamax.end(), 0);
    std::fill(w.ialphamax.begin(), w.ialphamax.end(), 0);
    std::fill(w.ion_population_totals.begin(), w.ion_population_totals.end(), 0.0);
    std::fill(w.ion_population_totals_final.begin(), w.ion_population_totals_final.end(), 0.0);
    std::fill(w.ionization_totals.begin(), w.ionization_totals.end(), 0.0);
    std::fill(w.recombination_totals.begin(), w.recombination_totals.end(), 0.0);
    std::fill(w.ionization_components.begin(), w.ionization_components.end(), 0.0);
    std::fill(w.recombination_components.begin(), w.recombination_components.end(), 0.0);

    output.heating = 0.0;
    output.cooling = 0.0;
    output.heating2 = 0.0;
    output.cooling2 = 0.0;
    for (std::size_t k = 0; k < input.term_count; ++k) {
        const auto& term = input.terms[k];
        if (term.row == term.column) {
            const double population = w.x[static_cast<std::size_t>(term.row - 1)];
            if (term.cj > 0.0) output.cooling += population * term.cj;
            else output.heating -= population * term.cj;
            if (term.cj2 > 0.0) output.cooling2 += population * term.cj2;
            else output.heating2 -= population * term.cj2;
        }
    }

    for (int i = 0; i < std::max(0, n - 1); ++i) {
        const int ion_slot = input.ion_by_row[i] - 1;
        w.ion_population_totals[static_cast<std::size_t>(ion_slot)] +=
            w.final_outer_start[static_cast<std::size_t>(i)];
        w.ion_population_totals_final[static_cast<std::size_t>(ion_slot)] +=
            w.x[static_cast<std::size_t>(i)];
    }

    for (std::size_t k = 0; k < input.term_count; ++k) {
        const auto& term = input.terms[k];
        const int mm = std::min(n, term.row) - 1;
        const int nn = std::min(n, term.column) - 1;
        if (mm != nn) {
            const double out_rate = std::fabs(term.aj2);
            const double in_rate = std::fabs(term.aj1) * w.x[static_cast<std::size_t>(nn)];
            w.gamma[static_cast<std::size_t>(mm)] += out_rate;
            w.alpha[static_cast<std::size_t>(mm)] += in_rate;
            if (out_rate > w.gammamax[static_cast<std::size_t>(mm)]) {
                w.gammamax[static_cast<std::size_t>(mm)] = out_rate;
                w.igammamax[static_cast<std::size_t>(mm)] = term.record;
            }
            if (in_rate > w.alphamax[static_cast<std::size_t>(mm)]) {
                w.alphamax[static_cast<std::size_t>(mm)] = in_rate;
                w.ialphamax[static_cast<std::size_t>(mm)] = term.record;
            }

            int category = -1;
            if (term.rate_type == 3) category = 0;
            else if (term.rate_type == 4) category = 1;
            else if (term.rate_type == 5) category = 2;
            else if (term.rate_type == 7) category = 3;
            if (category >= 0) {
                w.fgamma[index2(category, mm, n)] += out_rate;
                if (term.rate_type == 5) {
                    w.falpha[index2(category, mm, n)] =
                        w.falpha[index2(category, nn, n)] + in_rate;
                } else {
                    w.falpha[index2(category, mm, n)] += in_rate;
                }
            }
        }
        if (term.row < term.column && (term.rate_type == 5 || term.rate_type == 7)) {
            const int ion_mm = input.ion_by_row[mm] - 1;
            const int ion_nn = input.ion_by_row[nn] - 1;
            if (ion_mm >= 0 && ion_mm < nion && ion_nn >= ion_mm) {
                const double recomb = std::fabs(term.aj1) * w.x[static_cast<std::size_t>(nn)];
                const double ionize = std::fabs(term.aj2) * w.x[static_cast<std::size_t>(mm)];
                w.recombination_totals[static_cast<std::size_t>(ion_mm)] += recomb;
                w.ionization_totals[static_cast<std::size_t>(ion_mm)] += ionize;
                const int component = term.rate_type == 7 ? 0 : 1;
                w.recombination_components[index2(component, ion_mm, nion)] += recomb;
                w.ionization_components[index2(component, ion_mm, nion)] += ionize;
            }
        }
    }

    output.max_relative_row_residual = std::numeric_limits<double>::quiet_NaN();
    output.max_active_relative_row_residual = std::numeric_limits<double>::quiet_NaN();
    output.l1_row_residual = std::numeric_limits<double>::quiet_NaN();
    output.l1_relative_row_residual = std::numeric_limits<double>::quiet_NaN();
    if (input.flags & XSTAR_ELEMENT_DIAGNOSTICS_SUMMARY) {
        double max_rel = 0.0;
        double max_active = 0.0;
        double l1 = 0.0;
        double sum_scale = 0.0;
        for (int row = 0; row < n; ++row) {
            double residual = 0.0;
            double scale = 0.0;
            for (int col = 0; col < n; ++col) {
                const double a = w.dense[index2(row, col, n)];
                residual += a * w.x[static_cast<std::size_t>(col)];
                scale += std::fabs(a) * std::fabs(w.x[static_cast<std::size_t>(col)]);
            }
            w.residual[static_cast<std::size_t>(row)] = residual;
            w.row_scale[static_cast<std::size_t>(row)] = scale;
            const double rel = std::fabs(residual) / std::max(scale, 1.0e-300);
            w.relative_residual[static_cast<std::size_t>(row)] = rel;
            max_rel = std::max(max_rel, rel);
            if (scale > 1.0e-12) max_active = std::max(max_active, rel);
            l1 += std::fabs(residual);
            sum_scale += scale;
        }
        output.max_relative_row_residual = max_rel;
        output.max_active_relative_row_residual = max_active;
        output.l1_row_residual = l1;
        output.l1_relative_row_residual = l1 / std::max(sum_scale, 1.0e-300);
    }

    output.element_z = input.element_z;
    output.outer_iterations = outer;
    output.fixed_point_iterations = total_fixed;
    output.final_outer_difference = outer_diff;
    output.final_fixed_point_difference = fixed_diff;
    output.normalization = 0.0;
    output.n_negative_populations = 0;
    for (double value : w.x) {
        output.normalization += value;
        if (value < 0.0) ++output.n_negative_populations;
    }
    output.normalization_error = std::fabs(output.normalization - 1.0);
    output.condensed_dimension = nsp;
    output.status_flags = XSTAR_ELEMENT_STATUS_NATIVE_MATRIX_ASSEMBLY |
                          XSTAR_ELEMENT_STATUS_NATIVE_LUCY_SOLVE |
                          XSTAR_ELEMENT_STATUS_STATE_COMMITTED;
    if (ordered) output.status_flags |= XSTAR_ELEMENT_STATUS_SOURCE_ORDER_VERIFIED;
    if (outer_diff <= input.lucy_tolerance && fixed_diff < input.fixed_point_tolerance) {
        output.status_flags |= XSTAR_ELEMENT_STATUS_CONVERGED;
    }
    if (dense_rescue_used) output.status_flags |= XSTAR_ELEMENT_STATUS_DENSE_RESCUE_USED;

    copy_vector(w.x, output.populations, output.populations_capacity, "populations");
    output.populations_count = static_cast<std::size_t>(n);
    copy_vector(w.gamma, output.gamma, output.gamma_capacity, "gamma");
    copy_vector(w.alpha, output.alpha, output.alpha_capacity, "alpha");
    copy_vector(w.fgamma, output.fgamma, output.fgamma_capacity, "fgamma");
    copy_vector(w.falpha, output.falpha, output.falpha_capacity, "falpha");
    copy_vector(w.igammamax, output.igammamax_record, output.igammamax_capacity, "igammamax");
    copy_vector(w.ialphamax, output.ialphamax_record, output.ialphamax_capacity, "ialphamax");
    copy_vector(w.ion_population_totals, output.ion_population_totals,
                output.ion_population_totals_capacity, "ion population totals");
    copy_vector(w.ion_population_totals_final, output.ion_population_totals_final_vector,
                output.ion_population_totals_final_capacity, "final ion population totals");
    copy_vector(w.ionization_totals, output.ionization_totals,
                output.ionization_totals_capacity, "ionization totals");
    copy_vector(w.recombination_totals, output.recombination_totals,
                output.recombination_totals_capacity, "recombination totals");
    copy_vector(w.ionization_components, output.ionization_components,
                output.ionization_components_capacity, "ionization components");
    copy_vector(w.recombination_components, output.recombination_components,
                output.recombination_components_capacity, "recombination components");

    if (input.flags & XSTAR_ELEMENT_DIAGNOSTICS_SUMMARY) {
        copy_vector(w.final_outer_start, output.final_outer_start_populations,
                    output.final_outer_start_capacity, "final outer-start populations");
        output.final_outer_start_count = static_cast<std::size_t>(n);
        copy_vector(w.residual, output.row_residual, output.row_residual_capacity, "row residual");
        copy_vector(w.row_scale, output.row_scale, output.row_scale_capacity, "row scale");
        copy_vector(w.relative_residual, output.relative_row_residual,
                    output.relative_row_residual_capacity, "relative row residual");
    } else {
        output.final_outer_start_count = 0;
    }

    if (input.flags & XSTAR_ELEMENT_RETURN_MATRICES) {
        copy_vector(w.dense, output.dense_matrix, output.dense_matrix_capacity, "dense matrix");
        copy_vector(w.heat, output.heating_matrix, output.heating_matrix_capacity, "heating matrix");
        copy_vector(w.heat2, output.heating_matrix2, output.heating_matrix2_capacity, "heating matrix2");
        copy_vector(w.rhs, output.rhs, output.rhs_capacity, "rhs");
        output.dense_matrix_count = w.dense.size();
        output.heating_matrix_count = w.heat.size();
        output.heating_matrix2_count = w.heat2.size();
        output.rhs_count = w.rhs.size();
    } else {
        output.dense_matrix_count = 0;
        output.heating_matrix_count = 0;
        output.heating_matrix2_count = 0;
        output.rhs_count = 0;
    }

    copy_text(output.solver_method, sizeof(output.solver_method), "xstar_solver_so_leqt2f_v1+native_lucy_v0645");
    std::ostringstream text;
    text << "native element engine completed Z=" << input.element_z
         << "; rows=" << n << "; terms=" << input.term_count
         << "; outer=" << outer << "; fixed=" << total_fixed
         << "; converged=" << ((output.status_flags & XSTAR_ELEMENT_STATUS_CONVERGED) ? "true" : "false");
    status_message = text.str();
    copy_text(output.message, sizeof(output.message), status_message);
    output.state_commit_seconds = seconds_since(commit_t0);
    context.stats.state_commit_seconds += output.state_commit_seconds;
    context.stats.elements_completed += 1;
    return 0;
}

} // namespace

struct xstar_element_engine_context {
    xstar_element_engine_context_impl impl;
};

extern "C" {

uint32_t xstar_element_engine_abi_version(void) {
    return XSTAR_ELEMENT_ENGINE_ABI_VERSION;
}

const char* xstar_element_engine_backend_name(void) {
    return "xstar_element_engine_h_he_mg_native_matrix_lucy_v0645";
}

int xstar_element_engine_feature_flags(void) {
    return 0x1F;
}

int xstar_element_input_init_v1(xstar_element_input_v1* input) {
    if (!input) return 1;
    std::memset(input, 0, sizeof(*input));
    input->struct_size = sizeof(*input);
    input->abi_version = XSTAR_ELEMENT_ENGINE_ABI_VERSION;
    input->flags = XSTAR_ELEMENT_STRICT_SOURCE_ORDER;
    input->max_lucy_iterations = 100;
    input->max_fixed_point_iterations = 200;
    input->lucy_tolerance = 1.0e-2;
    input->fixed_point_tolerance = 1.0e-2;
    return 0;
}

int xstar_element_output_init_v1(xstar_element_output_v1* output) {
    if (!output) return 1;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->abi_version = XSTAR_ELEMENT_ENGINE_ABI_VERSION;
    return 0;
}

int xstar_element_engine_stats_init_v1(xstar_element_engine_stats_v1* stats) {
    if (!stats) return 1;
    std::memset(stats, 0, sizeof(*stats));
    stats->struct_size = sizeof(*stats);
    stats->abi_version = XSTAR_ELEMENT_ENGINE_ABI_VERSION;
    return 0;
}

int xstar_element_engine_context_create_v1(
    xstar_element_engine_context** context,
    char* message,
    size_t message_size
) {
    if (!context) return 1;
    try {
        auto* value = new xstar_element_engine_context();
        xstar_element_engine_stats_init_v1(&value->impl.stats);
        *context = value;
        copy_text(message, message_size, "native element-engine persistent context created");
        return 0;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return 2;
    }
}

void xstar_element_engine_context_destroy(xstar_element_engine_context* context) {
    delete context;
}

int xstar_element_engine_context_reset_v1(
    xstar_element_engine_context* context,
    char* message,
    size_t message_size
) {
    if (!context) return 1;
    xstar_element_engine_stats_init_v1(&context->impl.stats);
    copy_text(message, message_size, "native element-engine statistics reset; workspace retained");
    return 0;
}

int xstar_element_engine_get_stats_v1(
    const xstar_element_engine_context* context,
    xstar_element_engine_stats_v1* stats,
    char* message,
    size_t message_size
) {
    if (!context || !stats || stats->struct_size < sizeof(*stats)) return 1;
    *stats = context->impl.stats;
    copy_text(message, message_size, "native element-engine statistics returned");
    return 0;
}

int xstar_element_engine_run_element_v1(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* input,
    xstar_element_output_v1* output,
    char* message,
    size_t message_size
) {
    if (!context || !input || !output) return 1;
    try {
        std::string status;
        const int rc = run_element_impl(context->impl, *input, *output, status);
        copy_text(message, message_size, status);
        return rc;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        copy_text(output->message, sizeof(output->message), exc.what());
        return 2;
    } catch (...) {
        copy_text(message, message_size, "unknown native element-engine exception");
        return 3;
    }
}

int xstar_element_engine_run_evaluation_v1(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* inputs,
    size_t element_count,
    xstar_element_output_v1* outputs,
    char* message,
    size_t message_size
) {
    if (!context || (element_count && (!inputs || !outputs))) return 1;
    context->impl.stats.evaluations_attempted += 1;
    try {
        for (std::size_t i = 0; i < element_count; ++i) {
            std::string status;
            const int rc = run_element_impl(context->impl, inputs[i], outputs[i], status);
            if (rc != 0) {
                std::ostringstream text;
                text << "evaluation element " << i << " failed: " << status;
                copy_text(message, message_size, text.str());
                return rc;
            }
        }
        context->impl.stats.evaluations_completed += 1;
        std::ostringstream text;
        text << "native element evaluation completed; elements=" << element_count;
        copy_text(message, message_size, text.str());
        return 0;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return 2;
    }
}

} // extern "C"
