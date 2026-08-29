// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: calc_hmc_element.f90; calc_hmc_ion.f90; calc_ion_rates.f90; istruc.f90; ioneqm.f90;
//   levwkelement.f90; msolvelucy.f90
// Role: Native per-element fixed-state ion/level population, rate, matrix, and thermal-contribution
//   evaluation.
// Relation: Source-equivalent operator with different storage; source traversal/order, endpoint clamping,
//   and solve invariants are qualified.
// Concordance: ION-001; LEVEL-001; MATRIX-001; THERM-001
// Qualification: matrix repair 12.3.25; all-62 C++ 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#include "xstar_element_engine.h"
#include "xstar_element_engine_internal.hpp"
#include "source_order_thermal_reducer.hpp"
#include "canonical_thermal_term.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
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

extern "C" int xstar_solver_leqt2f_trace_v1(
    const double* a,
    const double* b,
    int n,
    int clamp,
    double* first_lu_solution,
    double* refinement_residual,
    double* refinement_correction,
    double* refined_solution,
    double* solution,
    double* residual,
    double* max_scaled_residual,
    char* error_message,
    size_t error_message_len
);

namespace {

using clock_type = std::chrono::steady_clock;

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement copy text as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
void copy_text(char* target, std::size_t capacity, const std::string& value) {
    if (!target || capacity == 0) return;
    const std::size_t n = std::min(capacity - 1, value.size());
    std::memcpy(target, value.data(), n);
    target[n] = '\0';
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement seconds since as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
double seconds_since(const clock_type::time_point& start) {
    return std::chrono::duration<double>(clock_type::now() - start).count();
}


enum IterationTraceTerminationReason : int {
    ITERATION_TRACE_CONTINUE = 0,
    ITERATION_TRACE_TOLERANCE = 1,
    ITERATION_TRACE_DIVERGENCE = 2,
    ITERATION_TRACE_MAX_ITERATIONS = 3,
    ITERATION_TRACE_DENSE_RESCUE = 4
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute iteration trace reason text within the element/ion population workflow, preserving the source ion-stage ordering and active-stage semantics.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
const char* iteration_trace_reason_text(int reason) {
    switch (reason) {
        case ITERATION_TRACE_TOLERANCE: return "tolerance";
        case ITERATION_TRACE_DIVERGENCE: return "divergence_guard";
        case ITERATION_TRACE_MAX_ITERATIONS: return "max_iterations";
        case ITERATION_TRACE_DENSE_RESCUE: return "dense_rescue";
        default: return "continue";
    }
}

struct OuterIterationTraceRecord {
    int outer_iteration = 0;
    int fixed_iterations_this_outer = 0;
    int total_fixed_iterations_after_outer = 0;
    int fixed_termination_reason = ITERATION_TRACE_CONTINUE;
    int outer_termination_reason = ITERATION_TRACE_CONTINUE;
    double fixed_difference = 0.0;
    double outer_difference = 0.0;
    std::vector<double> outer_start;
    std::vector<double> superlevel_before_solve;
    std::vector<double> row_fraction;
    std::vector<double> condensed_matrix;
    std::vector<double> condensed_rhs;
    std::vector<double> first_lu_solution;
    std::vector<double> refinement_residual;
    std::vector<double> refinement_correction;
    std::vector<double> refined_superlevel_solution;
    std::vector<double> population_after_condensed;
    std::vector<double> population_after_fixed_point;
};

struct FixedIterationTraceRecord {
    int outer_iteration = 0;
    int fixed_iteration = 0;
    int global_fixed_iteration = 0;
    int termination_reason = ITERATION_TRACE_CONTINUE;
    double fixed_difference = 0.0;
    std::vector<double> population_before;
    std::vector<double> riu;
    std::vector<double> rui;
    std::vector<double> ril;
    std::vector<double> rli;
    std::vector<double> population_after;
};

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
    std::vector<double> final_superlevel_before_solve;
    std::vector<double> final_condensed_matrix;
    std::vector<double> final_condensed_rhs;
    std::vector<double> final_first_lu_solution;
    std::vector<double> final_refinement_residual;
    std::vector<double> final_refinement_correction;
    std::vector<double> final_refined_superlevel_solution;
    std::vector<double> final_population_after_condensed;
    std::vector<double> final_fixed_point_population_before;
    std::vector<double> final_fixed_point_population_after;
    int final_outer_iteration = 0;
    int final_fixed_iterations = 0;
    int total_fixed_point_iterations_trace = 0;
    int trace_element_z = 0;
    bool solve_stage_trace_valid = false;
    std::vector<OuterIterationTraceRecord> iteration_outer_trace;
    std::vector<FixedIterationTraceRecord> iteration_fixed_trace;
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

    bool ensure(int new_n, int new_nsp, int new_nion, bool return_matrices, bool retain_dense_diagnostics) {
        const bool resized = new_n != n || new_nsp != nsp || new_nion != nion;
        n = new_n;
        nsp = new_nsp;
        nion = new_nion;
        const std::size_t nn = static_cast<std::size_t>(n) * static_cast<std::size_t>(n);
        const std::size_t ss = static_cast<std::size_t>(nsp) * static_cast<std::size_t>(nsp);
        // 0.6.82.36.5: the full n*n dense matrix is not part of the normal
        // Lucy/fixed-point path.  Retain it only for explicit matrix/summary
        // diagnostics.  The dense-rescue path reconstructs the identical
        // source-ordered matrix on demand if a rescue is actually triggered.
        if (return_matrices || retain_dense_diagnostics) {
            dense.assign(nn, 0.0);
        } else if (dense.capacity() != 0u) {
            std::vector<double>().swap(dense);
        }
        // 0.6.82.36.4: heat/heat2 are output-only diagnostic matrices.
        // Production thermal totals are reduced directly from the canonical
        // term stream below; neither matrix participates in Lucy/fixed-point
        // arithmetic. Keep their exact historical contents only when the API
        // caller explicitly requests matrix outputs.
        if (return_matrices) {
            heat.assign(nn, 0.0);
            heat2.assign(nn, 0.0);
        } else {
            if (heat.capacity() != 0u) std::vector<double>().swap(heat);
            if (heat2.capacity() != 0u) std::vector<double>().swap(heat2);
        }
        rhs.assign(static_cast<std::size_t>(n), 0.0);
        x.resize(static_cast<std::size_t>(n));
        xo.resize(static_cast<std::size_t>(n));
        outer_start.resize(static_cast<std::size_t>(n));
        final_outer_start.resize(static_cast<std::size_t>(n));
        final_superlevel_before_solve.assign(static_cast<std::size_t>(nsp), 0.0);
        final_condensed_matrix.assign(ss, 0.0);
        final_condensed_rhs.assign(static_cast<std::size_t>(nsp), 0.0);
        final_first_lu_solution.assign(static_cast<std::size_t>(nsp), 0.0);
        final_refinement_residual.assign(static_cast<std::size_t>(nsp), 0.0);
        final_refinement_correction.assign(static_cast<std::size_t>(nsp), 0.0);
        final_refined_superlevel_solution.assign(static_cast<std::size_t>(nsp), 0.0);
        final_population_after_condensed.assign(static_cast<std::size_t>(n), 0.0);
        final_fixed_point_population_before.assign(static_cast<std::size_t>(n), 0.0);
        final_fixed_point_population_after.assign(static_cast<std::size_t>(n), 0.0);
        final_outer_iteration = 0;
        final_fixed_iterations = 0;
        total_fixed_point_iterations_trace = 0;
        trace_element_z = 0;
        solve_stage_trace_valid = false;
        iteration_outer_trace.clear();
        iteration_fixed_trace.clear();
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement index2 as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
inline std::size_t index2(int row, int col, int ncols) {
    return static_cast<std::size_t>(row) * static_cast<std::size_t>(ncols) + static_cast<std::size_t>(col);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement trim text as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
std::string trim_text(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement split simple csv as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
std::vector<std::string> split_simple_csv(const std::string& line) {
    std::vector<std::string> out;
    std::string current;
    for (char ch : line) {
        if (ch == ',') { out.push_back(trim_text(current)); current.clear(); }
        else current.push_back(ch);
    }
    out.push_back(trim_text(current));
    return out;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Validate the invariants required by required environment integer local; reject malformed dimensions, pointers, or state before scientific kernels are entered.
// Reference context: Implementation/safety helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
int required_environment_integer_local(const char* name) {
    const char* value = std::getenv(name);
    if (!value || !*value) throw std::runtime_error(std::string("missing environment integer: ") + name);
    char* end = nullptr;
    const long parsed = std::strtol(value, &end, 10);
    if (!end || *end != '\0' || parsed <= 0 || parsed > 1000000) {
        throw std::runtime_error(std::string("invalid environment integer: ") + name);
    }
    return static_cast<int>(parsed);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement environment flag local as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
bool environment_flag_local(const char* name) {
    const char* value = std::getenv(name);
    return value && std::string(value) == "1";
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute optional environment integer local within the element/ion population workflow, preserving the source ion-stage ordering and active-stage semantics.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
int optional_environment_integer_local(const char* name, int fallback) {
    const char* value = std::getenv(name);
    if (!value || !*value) return fallback;
    char* end = nullptr;
    const long parsed = std::strtol(value, &end, 10);
    if (!end || *end != '\0' || parsed <= 0 || parsed > 1000000) return fallback;
    return static_cast<int>(parsed);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement current source sequence local as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
int current_source_sequence_local() {
    const char* value = std::getenv("XSTAR_NATIVE_SOURCE_SEQUENCE");
    if (!value || !*value) value = std::getenv("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    if (!value || !*value) {
        throw std::runtime_error("iteration-resolved trace requires a source sequence");
    }
    char* end = nullptr;
    const long parsed = std::strtol(value, &end, 10);
    if (!end || *end != '\0' || parsed <= 0 || parsed > 1000000) {
        throw std::runtime_error("invalid source sequence for iteration-resolved trace");
    }
    return static_cast<int>(parsed);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute maybe dump element input within the element/ion population workflow, preserving the source ion-stage ordering and active-stage semantics.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
void maybe_dump_element_input(const xstar_element_input_v1& input) {
    const char* root_value = std::getenv("XSTAR_V70_DUMP_ELEMENT_INPUT_DIR");
    if (!root_value || !*root_value) return;
    const char* sequence_value = std::getenv("XSTAR_NATIVE_SOURCE_SEQUENCE");
    if (!sequence_value || !*sequence_value) return;
    char* end = nullptr;
    const long sequence_long = std::strtol(sequence_value, &end, 10);
    if (!end || *end != '\0' || sequence_long <= 0 || sequence_long > 1000000) return;
    const int sequence = static_cast<int>(sequence_long);
    const int target_sequence = optional_environment_integer_local(
        "XSTAR_V70_DUMP_ELEMENT_INPUT_SEQUENCE", 16);
    const int target_element = optional_environment_integer_local(
        "XSTAR_V70_DUMP_ELEMENT_INPUT_Z", 12);
    if (sequence != target_sequence || input.element_z != target_element) return;

    const std::filesystem::path root(root_value);
    std::filesystem::create_directories(root);
    std::ostringstream stem_builder;
    stem_builder << "sequence_" << std::setw(4) << std::setfill('0') << sequence
                 << "_element_" << std::setw(2) << std::setfill('0') << input.element_z;
    const std::string stem = stem_builder.str();
    const auto manifest_path = root / (stem + "_manifest.csv");
    if (std::filesystem::is_regular_file(manifest_path)) return;

    std::ofstream manifest(manifest_path);
    std::ofstream rows(root / (stem + "_rows.csv"));
    std::ofstream terms(root / (stem + "_terms.csv"));
    if (!manifest || !rows || !terms) {
        throw std::runtime_error("cannot create v70 element-input dump files");
    }
    manifest << "sequence,element_z,n_rows,n_superlevels,n_ions,normalization_row,max_lucy_iterations,max_fixed_point_iterations,lucy_tolerance,fixed_point_tolerance,term_count\n";
    manifest << std::setprecision(17)
             << sequence << ',' << input.element_z << ',' << input.n_rows << ','
             << input.n_superlevels << ',' << input.n_ions << ','
             << input.normalization_row << ',' << input.max_lucy_iterations << ','
             << input.max_fixed_point_iterations << ',' << input.lucy_tolerance << ','
             << input.fixed_point_tolerance << ',' << input.term_count << '\n';
    rows << "row,superlevel,ion,initial_population\n" << std::setprecision(17);
    for (int row = 0; row < input.n_rows; ++row) {
        rows << row + 1 << ',' << input.superlevel_by_row[row] << ','
             << input.ion_by_row[row] << ',' << input.initial_populations[row] << '\n';
    }
    terms << "source_position,term_index,record,data_type,rate_type,ion_index,ion_stage,row,column,aj1,aj2,cj,cj2\n"
          << std::setprecision(17);
    for (std::size_t index = 0; index < input.term_count; ++index) {
        const auto& term = input.terms[index];
        terms << term.source_position << ',' << term.term_index << ',' << term.record << ','
              << term.data_type << ',' << term.rate_type << ',' << term.ion_index << ','
              << term.ion_stage << ',' << term.row << ',' << term.column << ','
              << term.aj1 << ',' << term.aj2 << ',' << term.cj << ',' << term.cj2 << '\n';
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute iteration trace target within the element/ion population workflow, preserving the source ion-stage ordering and active-stage semantics.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
bool iteration_trace_target(int sequence, int element_z) {
    const char* raw = std::getenv("XSTAR_QUALIFICATION_ITERATION_TRACE_TARGETS");
    const std::string targets = raw && *raw ? raw : "1:1,6:1,1:2,1:12";
    if (targets == "all" || targets == "ALL") return true;
    std::string token;
    auto matches = [&](const std::string& value) {
        const auto colon = value.find(':');
        if (colon == std::string::npos) return false;
        try {
            const int target_sequence = std::stoi(trim_text(value.substr(0, colon)));
            const int target_z = std::stoi(trim_text(value.substr(colon + 1)));
            return target_sequence == sequence && target_z == element_z;
        } catch (...) {
            return false;
        }
    };
    for (char ch : targets) {
        if (ch == ',' || ch == ';') {
            if (matches(token)) return true;
            token.clear();
        } else {
            token.push_back(ch);
        }
    }
    return matches(token);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Write iteration resolved trace from already-computed state; this routine owns serialization/diagnostics rather than the underlying physical calculation.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
void write_iteration_resolved_trace(
    const xstar_element_input_v1& input,
    const Workspace& w,
    int sequence
) {
    const char* root_value = std::getenv("XSTAR_QUALIFICATION_ITERATION_TRACE_DIR");
    if (!root_value || !*root_value) {
        throw std::runtime_error("iteration-resolved trace requires XSTAR_QUALIFICATION_ITERATION_TRACE_DIR");
    }
    const std::filesystem::path root(root_value);
    std::filesystem::create_directories(root);
    std::ostringstream stem_builder;
    stem_builder << "sequence_" << std::setw(4) << std::setfill('0') << sequence
                 << "_element_" << std::setw(2) << std::setfill('0') << input.element_z;
    const std::string stem = stem_builder.str();
    std::ofstream manifest(root / (stem + "_manifest.csv"));
    std::ofstream outer_rows(root / (stem + "_outer_rows.csv"));
    std::ofstream superlevels(root / (stem + "_superlevels.csv"));
    std::ofstream matrix(root / (stem + "_condensed_matrix.csv"));
    std::ofstream fixed_rows(root / (stem + "_fixed_rows.csv"));
    if (!manifest || !outer_rows || !superlevels || !matrix || !fixed_rows) {
        throw std::runtime_error("cannot create iteration-resolved trace files");
    }
    manifest << "sequence,element_z,n_rows,n_superlevels,normalization_row,max_outer_iterations,max_fixed_iterations,lucy_tolerance,fixed_point_tolerance,outer_iterations,total_fixed_point_iterations,outer_trace_records,fixed_trace_records,trace_complete\n";
    outer_rows << "sequence,element_z,outer_iteration,compact_row,superlevel,ion,outer_start_population,row_fraction,population_after_condensed,population_after_fixed_point,fixed_iterations_this_outer,total_fixed_iterations_after_outer,fixed_difference,outer_difference,fixed_termination_reason,outer_termination_reason\n";
    superlevels << "sequence,element_z,outer_iteration,superlevel,population_before_condensed_solve,condensed_rhs,first_lu_solution,refinement_residual,refinement_correction,refined_superlevel_solution\n";
    matrix << "sequence,element_z,outer_iteration,row_superlevel,column_superlevel,normalized_matrix_value\n";
    fixed_rows << "sequence,element_z,outer_iteration,fixed_iteration,global_fixed_iteration,compact_row,superlevel,ion,population_before,riu,rui,ril,rli,population_after,fixed_difference,termination_reason\n";
    manifest << std::setprecision(17);
    outer_rows << std::setprecision(17);
    superlevels << std::setprecision(17);
    matrix << std::setprecision(17);
    fixed_rows << std::setprecision(17);
    const int total_fixed = w.iteration_fixed_trace.empty() ? 0 :
        w.iteration_fixed_trace.back().global_fixed_iteration;
    manifest << sequence << ',' << input.element_z << ',' << input.n_rows << ','
             << input.n_superlevels << ',' << input.normalization_row << ','
             << input.max_lucy_iterations << ',' << input.max_fixed_point_iterations << ','
             << input.lucy_tolerance << ',' << input.fixed_point_tolerance << ','
             << w.iteration_outer_trace.size() << ',' << total_fixed << ','
             << w.iteration_outer_trace.size() << ',' << w.iteration_fixed_trace.size() << ",1\n";
    for (const auto& record : w.iteration_outer_trace) {
        if (record.outer_start.size() != static_cast<std::size_t>(input.n_rows) ||
            record.row_fraction.size() != static_cast<std::size_t>(input.n_rows) ||
            record.population_after_condensed.size() != static_cast<std::size_t>(input.n_rows) ||
            record.population_after_fixed_point.size() != static_cast<std::size_t>(input.n_rows) ||
            record.superlevel_before_solve.size() != static_cast<std::size_t>(input.n_superlevels) ||
            record.condensed_matrix.size() != static_cast<std::size_t>(input.n_superlevels) * static_cast<std::size_t>(input.n_superlevels)) {
            throw std::runtime_error("iteration-resolved outer trace dimension mismatch");
        }
        for (int row = 0; row < input.n_rows; ++row) {
            outer_rows << sequence << ',' << input.element_z << ',' << record.outer_iteration << ','
                       << row + 1 << ',' << input.superlevel_by_row[row] << ',' << input.ion_by_row[row] << ','
                       << record.outer_start[static_cast<std::size_t>(row)] << ','
                       << record.row_fraction[static_cast<std::size_t>(row)] << ','
                       << record.population_after_condensed[static_cast<std::size_t>(row)] << ','
                       << record.population_after_fixed_point[static_cast<std::size_t>(row)] << ','
                       << record.fixed_iterations_this_outer << ','
                       << record.total_fixed_iterations_after_outer << ','
                       << record.fixed_difference << ',' << record.outer_difference << ','
                       << iteration_trace_reason_text(record.fixed_termination_reason) << ','
                       << iteration_trace_reason_text(record.outer_termination_reason) << '\n';
        }
        for (int sp = 0; sp < input.n_superlevels; ++sp) {
            superlevels << sequence << ',' << input.element_z << ',' << record.outer_iteration << ','
                        << sp + 1 << ',' << record.superlevel_before_solve[static_cast<std::size_t>(sp)] << ','
                        << record.condensed_rhs[static_cast<std::size_t>(sp)] << ','
                        << record.first_lu_solution[static_cast<std::size_t>(sp)] << ','
                        << record.refinement_residual[static_cast<std::size_t>(sp)] << ','
                        << record.refinement_correction[static_cast<std::size_t>(sp)] << ','
                        << record.refined_superlevel_solution[static_cast<std::size_t>(sp)] << '\n';
            for (int col = 0; col < input.n_superlevels; ++col) {
                matrix << sequence << ',' << input.element_z << ',' << record.outer_iteration << ','
                       << sp + 1 << ',' << col + 1 << ','
                       << record.condensed_matrix[index2(sp, col, input.n_superlevels)] << '\n';
            }
        }
    }
    for (const auto& record : w.iteration_fixed_trace) {
        if (record.population_before.size() != static_cast<std::size_t>(input.n_rows) ||
            record.population_after.size() != static_cast<std::size_t>(input.n_rows)) {
            throw std::runtime_error("iteration-resolved fixed trace dimension mismatch");
        }
        for (int row = 0; row < input.n_rows; ++row) {
            const auto index = static_cast<std::size_t>(row);
            fixed_rows << sequence << ',' << input.element_z << ',' << record.outer_iteration << ','
                       << record.fixed_iteration << ',' << record.global_fixed_iteration << ','
                       << row + 1 << ',' << input.superlevel_by_row[row] << ',' << input.ion_by_row[row] << ','
                       << record.population_before[index] << ',' << record.riu[index] << ','
                       << record.rui[index] << ',' << record.ril[index] << ',' << record.rli[index] << ','
                       << record.population_after[index] << ',' << record.fixed_difference << ','
                       << iteration_trace_reason_text(record.termination_reason) << '\n';
        }
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Apply matrix construction dense closure to the current model state while preserving the source ordering and normalization expected by later stages.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
void apply_matrix_construction_dense_closure(const xstar_element_input_v1& input, std::vector<double>& dense) {
    if (!environment_flag_local("XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE")) return;
    const char* root_value = std::getenv("XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE_DIR");
    if (!root_value || !*root_value) throw std::runtime_error("matrix-construction closure directory is missing");
    const int sequence = required_environment_integer_local("XSTAR_QUALIFICATION_SOURCE_SEQUENCE");
    std::ostringstream name;
    name << "sequence_" << std::setw(4) << std::setfill('0') << sequence
         << "_element_" << std::setw(2) << std::setfill('0') << input.element_z
         << "_dense.csv";
    const std::filesystem::path path = std::filesystem::path(root_value) / name.str();
    std::ifstream stream(path);
    if (!stream) throw std::runtime_error("cannot open matrix-closure dense file: " + path.string());
    std::string line;
    if (!std::getline(stream, line)) throw std::runtime_error("matrix-closure dense file is empty");
    const auto header = split_simple_csv(line);
    std::unordered_map<std::string, std::size_t> column;
    for (std::size_t i = 0; i < header.size(); ++i) column.emplace(header[i], i);
    for (const char* required : {"row", "column", "source_value"}) {
        if (!column.count(required)) throw std::runtime_error(std::string("matrix-closure dense file missing column: ") + required);
    }
    std::set<std::pair<int,int>> seen;
    while (std::getline(stream, line)) {
        if (trim_text(line).empty()) continue;
        const auto values = split_simple_csv(line);
        if (values.size() != header.size()) throw std::runtime_error("matrix-closure dense row width mismatch");
        const int row = std::stoi(values[column.at("row")]);
        const int col = std::stoi(values[column.at("column")]);
        const double value = std::stod(values[column.at("source_value")]);
        if (row < 1 || row > input.n_rows || col < 1 || col > input.n_rows || !std::isfinite(value)) {
            throw std::runtime_error("invalid matrix-closure dense cell");
        }
        if (!seen.emplace(row, col).second) throw std::runtime_error("duplicate matrix-closure dense cell");
        dense[index2(row - 1, col - 1, input.n_rows)] = value;
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Validate the invariants required by require; reject malformed dimensions, pointers, or state before scientific kernels are entered.
// Reference context: Implementation/safety helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Validate the invariants required by validate input; reject malformed dimensions, pointers, or state before scientific kernels are entered.
// Reference context: Implementation/safety helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Validate the invariants required by validate output; reject malformed dimensions, pointers, or state before scientific kernels are entered.
// Reference context: Implementation/safety helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement verify source order as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
bool verify_source_order(const xstar_element_input_v1& input) {
    const char* qualification_order = std::getenv("XSTAR_QUALIFICATION_TYPE53_ROW46_COUPLED_REPLACEMENT");
    const char* promoted_order = std::getenv("XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION");
    const char* matrix_closure_order = std::getenv("XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE");
    const char* native_production = std::getenv("XSTAR_NATIVE_PRODUCTION");
    const bool allow_original_dsec_order =
        (qualification_order && std::string(qualification_order) == "1") ||
        (promoted_order && std::string(promoted_order) == "1") ||
        (matrix_closure_order && std::string(matrix_closure_order) == "1") ||
        (native_production && std::string(native_production) == "1");
    std::int64_t previous = std::numeric_limits<std::int64_t>::min();
    for (std::size_t i = 0; i < input.term_count; ++i) {
        const auto& term = input.terms[i];
        require(term.row >= 1 && term.row <= input.n_rows, "term row outside compact basis");
        require(term.column >= 1 && term.column <= input.n_rows, "term column outside compact basis");
        require(std::isfinite(term.aj1) && std::isfinite(term.aj2) &&
                std::isfinite(term.cj) && std::isfinite(term.cj2), "non-finite matrix term");
        if (!allow_original_dsec_order && term.source_position < previous) return false;
        previous = term.source_position;
    }
    return true;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute solve normalized as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
void solve_normalized(
    std::vector<double>& matrix,
    int dimension,
    int normalization_row_one_based,
    std::vector<double>& rhs,
    std::vector<double>& result,
    std::vector<double>& residual,
    const char* label,
    std::vector<double>* first_lu_solution = nullptr,
    std::vector<double>* refinement_residual = nullptr,
    std::vector<double>* refinement_correction = nullptr,
    std::vector<double>* refined_solution = nullptr
) {
    std::fill(rhs.begin(), rhs.begin() + dimension, 0.0);
    const int row = normalization_row_one_based - 1;
    for (int col = 0; col < dimension; ++col) matrix[index2(row, col, dimension)] = 1.0;
    rhs[static_cast<std::size_t>(row)] = 1.0;
    double max_scaled = 0.0;
    char error[1024] = {};
    const bool trace = first_lu_solution && refinement_residual &&
        refinement_correction && refined_solution;
    int rc = 0;
    if (trace) {
        first_lu_solution->resize(static_cast<std::size_t>(dimension));
        refinement_residual->resize(static_cast<std::size_t>(dimension));
        refinement_correction->resize(static_cast<std::size_t>(dimension));
        refined_solution->resize(static_cast<std::size_t>(dimension));
        rc = xstar_solver_leqt2f_trace_v1(
            matrix.data(), rhs.data(), dimension, 1,
            first_lu_solution->data(), refinement_residual->data(),
            refinement_correction->data(), refined_solution->data(),
            result.data(), residual.data(), &max_scaled, error, sizeof(error));
    } else {
        rc = xstar_solver_leqt2f(
            matrix.data(), rhs.data(), dimension, 1, result.data(), residual.data(),
            &max_scaled, error, sizeof(error));
    }
    if (rc != 0) {
        std::ostringstream text;
        text << label << " solve failed: " << error;
        throw std::runtime_error(text.str());
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement source fixed difference as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement source outer difference as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
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
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement copy vector as a local helper for the element engine module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
void copy_vector(const std::vector<T>& source, T* target, std::size_t capacity, const char* label) {
    require(target != nullptr && capacity >= source.size(), std::string(label) + " output buffer too small");
    std::copy(source.begin(), source.end(), target);
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Build terms from contributions from the source-ordered inputs required by the next calculation stage.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
std::vector<xstar_element_term_v1> construct_terms_from_contributions(
    const xstar_element_input_v1& input,
    const xstar_element_contribution_v1* contributions,
    std::size_t contribution_count
) {
    if (contribution_count > 0) require(contributions != nullptr, "contributions pointer is null");
    std::vector<xstar_element_term_v1> terms;
    terms.reserve(contribution_count * 4u);
    std::int64_t previous_position = std::numeric_limits<std::int64_t>::min();
    const char* qualification_order = std::getenv("XSTAR_QUALIFICATION_TYPE53_ROW46_COUPLED_REPLACEMENT");
    const char* promoted_order = std::getenv("XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION");
    const char* matrix_closure_order = std::getenv("XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE");
    const char* native_production = std::getenv("XSTAR_NATIVE_PRODUCTION");
    const bool allow_original_dsec_order =
        (qualification_order && std::string(qualification_order) == "1") ||
        (promoted_order && std::string(promoted_order) == "1") ||
        (matrix_closure_order && std::string(matrix_closure_order) == "1") ||
        (native_production && std::string(native_production) == "1");
    for (std::size_t index = 0; index < contribution_count; ++index) {
        const auto& c = contributions[index];
        if (!allow_original_dsec_order) {
            require(c.source_position >= previous_position, "contribution stream is not in source-position order");
        }
        previous_position = c.source_position;
        require(c.lower_row >= 1 && c.lower_row <= input.n_rows, "contribution lower_row outside compact basis");
        require(c.upper_row >= 1 && c.upper_row <= input.n_rows, "contribution upper_row outside compact basis");
        require(std::isfinite(c.ans1) && std::isfinite(c.ans2) && std::isfinite(c.ans3) &&
                std::isfinite(c.ans4) && std::isfinite(c.ans5) && std::isfinite(c.ans6) &&
                std::isfinite(c.density_scale), "non-finite contribution scalar");
        const double a1 = c.ans1;
        const double a2 = c.ans2;
        const double xpx = c.density_scale;
        const int rows[4] = {c.upper_row, c.lower_row, c.lower_row, c.upper_row};
        const int cols[4] = {c.lower_row, c.upper_row, c.lower_row, c.upper_row};
        const double aj1[4] = {a1, a2, -a1, -a2};
        const double aj2[4] = {a2, a1, -a1, -a2};
        const double cj[4] = {0.0, 0.0, c.ans4 * xpx, -c.ans3 * xpx};
        const double cj2[4] = {0.0, 0.0, c.ans6 * xpx, -c.ans5 * xpx};
        for (int offset = 0; offset < 4; ++offset) {
            xstar_element_term_v1 term{};
            term.source_position = c.source_position + offset;
            term.term_index = c.source_position + offset;
            term.record = c.record;
            term.data_type = c.data_type;
            term.rate_type = c.rate_type;
            term.ion_index = c.ion_index;
            term.ion_stage = c.ion_stage;
            term.row = rows[offset];
            term.column = cols[offset];
            term.aj1 = aj1[offset];
            term.aj2 = aj2[offset];
            term.cj = cj[offset];
            term.cj2 = cj2[offset];
            terms.push_back(term);
        }
    }
    return terms;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute run element impl within the element/ion population workflow, preserving the source ion-stage ordering and active-stage semantics.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
int run_element_impl(
    xstar_element_engine_context_impl& context,
    const xstar_element_input_v1& input,
    xstar_element_output_v1& output,
    std::string& status_message,
    const xstar_canonical_thermal_term_v1* canonical_thermal_terms = nullptr,
    std::size_t canonical_thermal_term_count = 0,
    std::uint64_t* consumed_thermal_ledger_fingerprint = nullptr,
    bool trusted_thermal_ledger_v068240241 = false,
    std::uint64_t authoritative_thermal_ledger_fingerprint_v068240241 = 0u,
    bool authoritative_thermal_ledger_fingerprint_valid_v068240242 = true,
    bool* consumed_thermal_ledger_fingerprint_valid_v068240242 = nullptr
) {
    validate_input(input);
    validate_output(input, output);
    context.stats.elements_attempted += 1;

    const bool ordered = verify_source_order(input);
    const bool qualified_family_order =
        environment_flag_local("XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE") ||
        environment_flag_local("XSTAR_QUALIFICATION_TYPE53_ROW46_COUPLED_REPLACEMENT") ||
        environment_flag_local("XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION");
    if ((input.flags & XSTAR_ELEMENT_STRICT_SOURCE_ORDER) && !ordered && !qualified_family_order) {
        context.stats.source_order_failures += 1;
        throw std::runtime_error("element term stream is not in source-position order");
    }

    Workspace& w = context.workspace;
    const bool return_matrices = (input.flags & XSTAR_ELEMENT_RETURN_MATRICES) != 0u;
    const bool capture_solve_stage_trace =
        (input.flags & XSTAR_ELEMENT_DIAGNOSTICS_SUMMARY) != 0u;
    if (w.ensure(input.n_rows, input.n_superlevels, input.n_ions, return_matrices, capture_solve_stage_trace)) {
        context.stats.workspace_resizes += 1;
    }
    const int n = input.n_rows;
    const int nsp = input.n_superlevels;
    const int nion = input.n_ions;

    const auto assembly_t0 = clock_type::now();
    const bool retain_dense_matrix = !w.dense.empty();
    if (retain_dense_matrix) std::fill(w.dense.begin(), w.dense.end(), 0.0);
    if (return_matrices) {
        std::fill(w.heat.begin(), w.heat.end(), 0.0);
        std::fill(w.heat2.begin(), w.heat2.end(), 0.0);
    }
    std::fill(w.rhs.begin(), w.rhs.end(), 0.0);
    for (std::size_t i = 0; i < input.term_count; ++i) {
        const auto& term = input.terms[i];
        if (retain_dense_matrix) {
            const std::size_t p = index2(term.row - 1, term.column - 1, n);
            w.dense[p] += term.aj1;
        }
        if (return_matrices) {
            const std::size_t p = index2(term.row - 1, term.column - 1, n);
            w.heat[p] += term.cj;
            w.heat2[p] += term.cj2;
        }
    }
    if (retain_dense_matrix) apply_matrix_construction_dense_closure(input, w.dense);
    w.rhs[static_cast<std::size_t>(input.normalization_row - 1)] = 1.0;
    output.matrix_assembly_seconds = seconds_since(assembly_t0);
    context.stats.matrix_assembly_seconds += output.matrix_assembly_seconds;
    context.stats.terms_committed += input.term_count;

    maybe_dump_element_input(input);

    const auto solver_t0 = clock_type::now();
    std::copy(input.initial_populations, input.initial_populations + n, w.x.begin());
    w.final_outer_start = w.x;
    double outer_diff = 1.0;
    double fixed_diff = 0.0;
    int outer = 0;
    int total_fixed = 0;
    bool dense_rescue_used = false;
    w.solve_stage_trace_valid = false;
    w.trace_element_z = input.element_z;
    w.final_outer_iteration = 0;
    w.final_fixed_iterations = 0;
    w.total_fixed_point_iterations_trace = 0;
    const bool capture_iteration_resolved_trace =
        environment_flag_local("XSTAR_QUALIFICATION_ITERATION_RESOLVED_TRACE") &&
        iteration_trace_target(current_source_sequence_local(), input.element_z);
    w.iteration_outer_trace.clear();
    w.iteration_fixed_trace.clear();

    while (outer_diff > input.lucy_tolerance && outer < input.max_lucy_iterations) {
        ++outer;
        w.xo = w.x;
        w.outer_start = w.x;
        w.final_outer_start = w.outer_start;
        OuterIterationTraceRecord iteration_outer_record;
        if (capture_iteration_resolved_trace) {
            iteration_outer_record.outer_iteration = outer;
            iteration_outer_record.outer_start = w.outer_start;
        }
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
        if (capture_iteration_resolved_trace) {
            iteration_outer_record.superlevel_before_solve = w.p;
            iteration_outer_record.row_fraction = w.rr;
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
        if (capture_solve_stage_trace) {
            w.final_superlevel_before_solve = w.p;
        }
        std::vector<double> iteration_first_lu;
        std::vector<double> iteration_refinement_residual;
        std::vector<double> iteration_refinement_correction;
        std::vector<double> iteration_refined_solution;
        const bool capture_linear_trace = capture_solve_stage_trace || capture_iteration_resolved_trace;
        solve_normalized(
            w.condensed, nsp, nsp, w.solve_rhs, w.solve_result, w.solve_residual,
            "condensed Lucy",
            capture_linear_trace ? &iteration_first_lu : nullptr,
            capture_linear_trace ? &iteration_refinement_residual : nullptr,
            capture_linear_trace ? &iteration_refinement_correction : nullptr,
            capture_linear_trace ? &iteration_refined_solution : nullptr);
        if (capture_solve_stage_trace) {
            w.final_condensed_matrix = w.condensed;
            std::copy(w.solve_rhs.begin(), w.solve_rhs.begin() + nsp,
                      w.final_condensed_rhs.begin());
            w.final_first_lu_solution = iteration_first_lu;
            w.final_refinement_residual = iteration_refinement_residual;
            w.final_refinement_correction = iteration_refinement_correction;
            w.final_refined_superlevel_solution = iteration_refined_solution;
            w.final_outer_iteration = outer;
        }
        if (capture_iteration_resolved_trace) {
            iteration_outer_record.condensed_matrix = w.condensed;
            iteration_outer_record.condensed_rhs.assign(
                w.solve_rhs.begin(), w.solve_rhs.begin() + nsp);
            iteration_outer_record.first_lu_solution = iteration_first_lu;
            iteration_outer_record.refinement_residual = iteration_refinement_residual;
            iteration_outer_record.refinement_correction = iteration_refinement_correction;
            iteration_outer_record.refined_superlevel_solution = iteration_refined_solution;
        }
        for (int i = 0; i < n; ++i) {
            const int sp = input.superlevel_by_row[i] - 1;
            w.x[static_cast<std::size_t>(i)] =
                w.rr[static_cast<std::size_t>(i)] * w.solve_result[static_cast<std::size_t>(sp)];
        }
        if (capture_solve_stage_trace) {
            w.final_population_after_condensed = w.x;
        }
        if (capture_iteration_resolved_trace) {
            iteration_outer_record.population_after_condensed = w.x;
        }

        fixed_diff = 10.0;
        int fixed_iter = 0;
        while (fixed_iter < input.max_fixed_point_iterations &&
               fixed_diff >= input.fixed_point_tolerance) {
            ++fixed_iter;
            ++total_fixed;
            w.xold = w.x;
            FixedIterationTraceRecord iteration_fixed_record;
            if (capture_solve_stage_trace) {
                w.final_fixed_point_population_before = w.xold;
            }
            if (capture_iteration_resolved_trace) {
                iteration_fixed_record.outer_iteration = outer;
                iteration_fixed_record.fixed_iteration = fixed_iter;
                iteration_fixed_record.global_fixed_iteration = total_fixed;
                iteration_fixed_record.population_before = w.xold;
            }
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
                std::vector<double> dense_copy;
                if (!w.dense.empty()) {
                    dense_copy = w.dense;
                } else {
                    // 0.6.82.36.5 rescue-on-demand: reconstruct in the same
                    // source term order used by the historical eager matrix.
                    // This path is cold in accepted Fe production (zero rescues)
                    // but retains exact rescue behavior for other models.
                    const std::size_t dense_count =
                        static_cast<std::size_t>(n) * static_cast<std::size_t>(n);
                    dense_copy.assign(dense_count, 0.0);
                    for (std::size_t k = 0; k < input.term_count; ++k) {
                        const auto& term = input.terms[k];
                        dense_copy[index2(term.row - 1, term.column - 1, n)] += term.aj1;
                    }
                    apply_matrix_construction_dense_closure(input, dense_copy);
                }
                solve_normalized(dense_copy, n, input.normalization_row, w.solve_rhs,
                                 w.solve_result, w.solve_residual, "dense rescue");
                std::copy(w.solve_result.begin(), w.solve_result.begin() + n, w.x.begin());
                dense_rescue_used = true;
                fixed_diff = 0.0;
                outer_diff = 0.0;
                if (capture_iteration_resolved_trace) {
                    iteration_fixed_record.riu = w.riu;
                    iteration_fixed_record.rui = w.rui;
                    iteration_fixed_record.ril = w.ril;
                    iteration_fixed_record.rli = w.rli;
                    iteration_fixed_record.population_after = w.x;
                    iteration_fixed_record.fixed_difference = fixed_diff;
                    iteration_fixed_record.termination_reason = ITERATION_TRACE_DENSE_RESCUE;
                    w.iteration_fixed_trace.push_back(std::move(iteration_fixed_record));
                }
                break;
            }
            const double denominator = 1.0e-24 + total;
            for (double& value : w.x) value /= denominator;
            if (capture_solve_stage_trace) {
                w.final_fixed_point_population_after = w.x;
                w.final_fixed_iterations = fixed_iter;
                w.total_fixed_point_iterations_trace = total_fixed;
            }
            fixed_diff = source_fixed_difference(w.xold, w.x);
            if (capture_iteration_resolved_trace) {
                iteration_fixed_record.riu = w.riu;
                iteration_fixed_record.rui = w.rui;
                iteration_fixed_record.ril = w.ril;
                iteration_fixed_record.rli = w.rli;
                iteration_fixed_record.population_after = w.x;
                iteration_fixed_record.fixed_difference = fixed_diff;
                if (fixed_diff >= 1.0e3) {
                    iteration_fixed_record.termination_reason = ITERATION_TRACE_DIVERGENCE;
                } else if (fixed_diff < input.fixed_point_tolerance) {
                    iteration_fixed_record.termination_reason = ITERATION_TRACE_TOLERANCE;
                } else if (fixed_iter >= input.max_fixed_point_iterations) {
                    iteration_fixed_record.termination_reason = ITERATION_TRACE_MAX_ITERATIONS;
                }
                w.iteration_fixed_trace.push_back(std::move(iteration_fixed_record));
            }
            // Canonical msolvelucy.f90 uses diff2 >= 1.e3 only to stop
            // the per-row difference accumulation for the current fixed-point
            // iteration.  It does not terminate the fixed-point loop itself.
        }
        if (dense_rescue_used) {
            if (capture_iteration_resolved_trace) {
                iteration_outer_record.population_after_fixed_point = w.x;
                iteration_outer_record.fixed_iterations_this_outer = fixed_iter;
                iteration_outer_record.total_fixed_iterations_after_outer = total_fixed;
                iteration_outer_record.fixed_difference = fixed_diff;
                iteration_outer_record.outer_difference = 0.0;
                iteration_outer_record.fixed_termination_reason = ITERATION_TRACE_DENSE_RESCUE;
                iteration_outer_record.outer_termination_reason = ITERATION_TRACE_DENSE_RESCUE;
                w.iteration_outer_trace.push_back(std::move(iteration_outer_record));
            }
            break;
        }
        outer_diff = source_outer_difference(w.xo, w.x);
        if (capture_iteration_resolved_trace) {
            iteration_outer_record.population_after_fixed_point = w.x;
            iteration_outer_record.fixed_iterations_this_outer = fixed_iter;
            iteration_outer_record.total_fixed_iterations_after_outer = total_fixed;
            iteration_outer_record.fixed_difference = fixed_diff;
            iteration_outer_record.outer_difference = outer_diff;
            if (fixed_diff >= 1.0e3) {
                iteration_outer_record.fixed_termination_reason = ITERATION_TRACE_DIVERGENCE;
            } else if (fixed_diff < input.fixed_point_tolerance) {
                iteration_outer_record.fixed_termination_reason = ITERATION_TRACE_TOLERANCE;
            } else if (fixed_iter >= input.max_fixed_point_iterations) {
                iteration_outer_record.fixed_termination_reason = ITERATION_TRACE_MAX_ITERATIONS;
            }
            if (outer_diff <= input.lucy_tolerance) {
                iteration_outer_record.outer_termination_reason = ITERATION_TRACE_TOLERANCE;
            } else if (outer >= input.max_lucy_iterations) {
                iteration_outer_record.outer_termination_reason = ITERATION_TRACE_MAX_ITERATIONS;
            }
            w.iteration_outer_trace.push_back(std::move(iteration_outer_record));
        }
    }
    if (capture_solve_stage_trace && outer > 0) {
        w.solve_stage_trace_valid = true;
        w.final_outer_start = w.outer_start;
        w.final_outer_iteration = outer;
        w.total_fixed_point_iterations_trace = total_fixed;
    }
    if (capture_iteration_resolved_trace) {
        const int sequence = current_source_sequence_local();
        write_iteration_resolved_trace(input, w, sequence);
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

    if (canonical_thermal_term_count > 0) {
        const auto canonical = trusted_thermal_ledger_v068240241
            ? xstar_canonical_thermal::reduce_trusted_v068240241(
                canonical_thermal_terms, canonical_thermal_term_count,
                w.x.data(), static_cast<std::size_t>(n), input.element_z,
                authoritative_thermal_ledger_fingerprint_v068240241,
                authoritative_thermal_ledger_fingerprint_valid_v068240242)
            : xstar_canonical_thermal::reduce(
                canonical_thermal_terms, canonical_thermal_term_count,
                w.x.data(), static_cast<std::size_t>(n), input.element_z);
        const auto thermal_values = canonical.tagged.total.values();
        output.heating = thermal_values[0];
        output.cooling = thermal_values[1];
        output.heating2 = thermal_values[2];
        output.cooling2 = thermal_values[3];
        output.status_flags |= XSTAR_ELEMENT_STATUS_CANONICAL_THERMAL_LEDGER;
        if (consumed_thermal_ledger_fingerprint) {
            *consumed_thermal_ledger_fingerprint = canonical.fingerprint;
        }
        if (consumed_thermal_ledger_fingerprint_valid_v068240242) {
            *consumed_thermal_ledger_fingerprint_valid_v068240242 = canonical.fingerprint_valid;
        }
    } else {
        xstar_source_order_thermal::FourChannelAccumulator thermal_reducer;
        for (std::size_t k = 0; k < input.term_count; ++k) {
            const auto& term = input.terms[k];
            if (term.row != term.column) continue;
            const double population = w.x[static_cast<std::size_t>(term.row - 1)];
            thermal_reducer.accumulate(population, term.cj, term.cj2);
        }
        const auto thermal_values = thermal_reducer.values();
        output.heating = thermal_values[0];
        output.cooling = thermal_values[1];
        output.heating2 = thermal_values[2];
        output.cooling2 = thermal_values[3];
        if (consumed_thermal_ledger_fingerprint) {
            *consumed_thermal_ledger_fingerprint = 0;
        }
        if (consumed_thermal_ledger_fingerprint_valid_v068240242) {
            *consumed_thermal_ledger_fingerprint_valid_v068240242 = false;
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
    const std::uint32_t canonical_thermal_status =
        output.status_flags & XSTAR_ELEMENT_STATUS_CANONICAL_THERMAL_LEDGER;
    output.status_flags = XSTAR_ELEMENT_STATUS_NATIVE_MATRIX_ASSEMBLY |
                          XSTAR_ELEMENT_STATUS_NATIVE_LUCY_SOLVE |
                          XSTAR_ELEMENT_STATUS_STATE_COMMITTED |
                          canonical_thermal_status;
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Return the ABI version for the element engine interface so callers can reject incompatible binary layouts before execution.
// Reference context: Implementation/compatibility helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
uint32_t xstar_element_engine_abi_version(void) {
    return XSTAR_ELEMENT_ENGINE_ABI_VERSION;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Report the compiled element engine backend name capability metadata used by backend selection and provenance.
// Reference context: Implementation/provenance helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
const char* xstar_element_engine_backend_name(void) {
    return "xstar_element_engine_h_he_mg_native_construction_v06451";
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Report the compiled element engine feature flags capability metadata used by backend selection and provenance.
// Reference context: Implementation/provenance helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
int xstar_element_engine_feature_flags(void) {
    return 0x3F;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Initialize the element input init structure to its ABI-safe defaults before the caller supplies model-specific values.
// Reference context: Implementation/ABI helper; scientific meaning is defined by the consuming engine.
// XSTAR-FUNCTION-COMMENT-END
int xstar_element_input_init_v1(xstar_element_input_v1* input) {
    if (!input) return 1;
    std::memset(input, 0, sizeof(*input));
    input->struct_size = sizeof(*input);
    input->abi_version = XSTAR_ELEMENT_ENGINE_ABI_VERSION;
    input->flags = XSTAR_ELEMENT_STRICT_SOURCE_ORDER;
    input->max_lucy_iterations = 200;
    input->max_fixed_point_iterations = 200;
    input->lucy_tolerance = 1.0e-2;
    input->fixed_point_tolerance = 1.0e-2;
    return 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Initialize the element output init structure to its ABI-safe defaults before the caller supplies model-specific values.
// Reference context: Implementation/ABI helper; scientific meaning is defined by the consuming engine.
// XSTAR-FUNCTION-COMMENT-END
int xstar_element_output_init_v1(xstar_element_output_v1* output) {
    if (!output) return 1;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->abi_version = XSTAR_ELEMENT_ENGINE_ABI_VERSION;
    return 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Initialize the element engine stats init structure to its ABI-safe defaults before the caller supplies model-specific values.
// Reference context: Implementation/ABI helper; scientific meaning is defined by the consuming engine.
// XSTAR-FUNCTION-COMMENT-END
int xstar_element_engine_stats_init_v1(xstar_element_engine_stats_v1* stats) {
    if (!stats) return 1;
    std::memset(stats, 0, sizeof(*stats));
    stats->struct_size = sizeof(*stats);
    stats->abi_version = XSTAR_ELEMENT_ENGINE_ABI_VERSION;
    return 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Initialize the element solve stage trace init structure to its ABI-safe defaults before the caller supplies model-specific values.
// Reference context: Implementation/ABI helper; scientific meaning is defined by the consuming engine.
// XSTAR-FUNCTION-COMMENT-END
int xstar_element_solve_stage_trace_init_v1(
    xstar_element_solve_stage_trace_v1* trace
) {
    if (!trace) return 1;
    std::memset(trace, 0, sizeof(*trace));
    trace->struct_size = sizeof(*trace);
    trace->abi_version = XSTAR_ELEMENT_SOLVE_STAGE_TRACE_ABI_VERSION;
    return 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute element engine get last solve stage trace as part of the multilevel statistical-equilibrium system and its normalization/detailed-balance constraints.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001); Bautista & Kallman (2001).
// XSTAR-FUNCTION-COMMENT-END
int xstar_element_engine_get_last_solve_stage_trace_v1(
    const xstar_element_engine_context* context,
    xstar_element_solve_stage_trace_v1* trace,
    char* message,
    size_t message_size
) {
    if (!context || !trace || trace->struct_size < sizeof(*trace) ||
        trace->abi_version != XSTAR_ELEMENT_SOLVE_STAGE_TRACE_ABI_VERSION) {
        copy_text(message, message_size, "solve-stage trace ABI mismatch");
        return 1;
    }
    try {
        const Workspace& w = context->impl.workspace;
        trace->valid = w.solve_stage_trace_valid ? 1u : 0u;
        trace->element_z = w.trace_element_z;
        trace->n_rows = w.n;
        trace->n_superlevels = w.nsp;
        trace->final_outer_iteration = w.final_outer_iteration;
        trace->final_fixed_iterations = w.final_fixed_iterations;
        trace->total_fixed_point_iterations = w.total_fixed_point_iterations_trace;
        if (!w.solve_stage_trace_valid) {
            copy_text(message, message_size, "no solve-stage trace is available");
            return 0;
        }
        const std::size_t n = static_cast<std::size_t>(w.n);
        const std::size_t nsp = static_cast<std::size_t>(w.nsp);
        const std::size_t nsp2 = nsp * nsp;
        require(trace->final_outer_start_populations && trace->final_outer_start_capacity >= n,
                "final outer-start trace buffer too small");
        require(trace->final_superlevel_populations_before_solve &&
                trace->final_superlevel_populations_before_solve_capacity >= nsp,
                "final superlevel-before trace buffer too small");
        require(trace->final_condensed_matrix && trace->final_condensed_matrix_capacity >= nsp2,
                "final condensed-matrix trace buffer too small");
        require(trace->final_condensed_rhs && trace->final_condensed_rhs_capacity >= nsp,
                "final condensed-RHS trace buffer too small");
        require(trace->final_first_lu_solution && trace->final_first_lu_solution_capacity >= nsp,
                "first-LU trace buffer too small");
        require(trace->final_refinement_residual && trace->final_refinement_residual_capacity >= nsp,
                "refinement-residual trace buffer too small");
        require(trace->final_refinement_correction && trace->final_refinement_correction_capacity >= nsp,
                "refinement-correction trace buffer too small");
        require(trace->final_refined_superlevel_solution &&
                trace->final_refined_superlevel_solution_capacity >= nsp,
                "refined-superlevel trace buffer too small");
        require(trace->final_population_after_condensed &&
                trace->final_population_after_condensed_capacity >= n,
                "population-after-condensed trace buffer too small");
        require(trace->final_fixed_point_population_before &&
                trace->final_fixed_point_population_before_capacity >= n,
                "fixed-point-before trace buffer too small");
        require(trace->final_fixed_point_population_after &&
                trace->final_fixed_point_population_after_capacity >= n,
                "fixed-point-after trace buffer too small");

        std::copy(w.final_outer_start.begin(), w.final_outer_start.end(),
                  trace->final_outer_start_populations);
        std::copy(w.final_superlevel_before_solve.begin(), w.final_superlevel_before_solve.end(),
                  trace->final_superlevel_populations_before_solve);
        std::copy(w.final_condensed_matrix.begin(), w.final_condensed_matrix.end(),
                  trace->final_condensed_matrix);
        std::copy(w.final_condensed_rhs.begin(), w.final_condensed_rhs.end(),
                  trace->final_condensed_rhs);
        std::copy(w.final_first_lu_solution.begin(), w.final_first_lu_solution.end(),
                  trace->final_first_lu_solution);
        std::copy(w.final_refinement_residual.begin(), w.final_refinement_residual.end(),
                  trace->final_refinement_residual);
        std::copy(w.final_refinement_correction.begin(), w.final_refinement_correction.end(),
                  trace->final_refinement_correction);
        std::copy(w.final_refined_superlevel_solution.begin(),
                  w.final_refined_superlevel_solution.end(),
                  trace->final_refined_superlevel_solution);
        std::copy(w.final_population_after_condensed.begin(),
                  w.final_population_after_condensed.end(),
                  trace->final_population_after_condensed);
        std::copy(w.final_fixed_point_population_before.begin(),
                  w.final_fixed_point_population_before.end(),
                  trace->final_fixed_point_population_before);
        std::copy(w.final_fixed_point_population_after.begin(),
                  w.final_fixed_point_population_after.end(),
                  trace->final_fixed_point_population_after);
        trace->final_outer_start_count = n;
        trace->final_superlevel_populations_before_solve_count = nsp;
        trace->final_condensed_matrix_count = nsp2;
        trace->final_condensed_rhs_count = nsp;
        trace->final_first_lu_solution_count = nsp;
        trace->final_refinement_residual_count = nsp;
        trace->final_refinement_correction_count = nsp;
        trace->final_refined_superlevel_solution_count = nsp;
        trace->final_population_after_condensed_count = n;
        trace->final_fixed_point_population_before_count = n;
        trace->final_fixed_point_population_after_count = n;
        copy_text(message, message_size, "native final-outer solve-stage trace returned");
        return 0;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return 2;
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Create and validate persistent runtime state for element engine context create, loading only the data needed by subsequent calls.
// Reference context: Implementation/lifetime helper; the scientific work is performed by the shared engine routines called from this context.
// XSTAR-FUNCTION-COMMENT-END
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Destroy the persistent element engine context destroy context and release its owned resources without changing external science state.
// Reference context: Implementation/lifetime helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
void xstar_element_engine_context_destroy(xstar_element_engine_context* context) {
    delete context;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Reset reusable element engine context reset state between model evaluations while preserving immutable loaded data and ABI invariants.
// Reference context: Implementation/lifetime helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute element engine get stats within the element/ion population workflow, preserving the source ion-stage ordering and active-stage semantics.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute element engine run construction within the element/ion population workflow, preserving the source ion-stage ordering and active-stage semantics.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
int xstar_element_engine_run_construction_v1(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* input,
    const xstar_element_contribution_v1* contributions,
    size_t contribution_count,
    xstar_element_output_v1* output,
    char* message,
    size_t message_size
) {
    if (!context || !input || !output) return 1;
    try {
        const auto construction_t0 = clock_type::now();
        std::vector<xstar_element_term_v1> terms =
            construct_terms_from_contributions(*input, contributions, contribution_count);
        const double construction_seconds = seconds_since(construction_t0);
        xstar_element_input_v1 expanded = *input;
        expanded.terms = terms.empty() ? nullptr : terms.data();
        expanded.term_count = terms.size();
        std::string status;
        const int rc = run_element_impl(context->impl, expanded, *output, status);
        if (rc == 0) {
            output->status_flags |= XSTAR_ELEMENT_STATUS_NATIVE_CONSTRUCTION;
            output->construction_seconds = construction_seconds;
            output->records_constructed = contribution_count;
            output->terms_constructed = terms.size();
            context->impl.stats.construction_calls += 1;
            context->impl.stats.records_constructed += contribution_count;
            context->impl.stats.terms_constructed += terms.size();
            context->impl.stats.construction_seconds += construction_seconds;
            std::ostringstream text;
            text << status << "; native_records=" << contribution_count
                 << "; native_terms=" << terms.size();
            status = text.str();
            copy_text(output->message, sizeof(output->message), status);
        }
        copy_text(message, message_size, status);
        return rc;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        copy_text(output->message, sizeof(output->message), exc.what());
        return 2;
    } catch (...) {
        copy_text(message, message_size, "unknown native element-construction exception");
        return 3;
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute element engine run construction with thermal ledger as a contribution to, or control step in, the local thermal-equilibrium iteration.
// Reference context: XSTAR Manual s11.4.4 and s11.6; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
int xstar_element_engine_run_construction_with_thermal_ledger_v1(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* input,
    const xstar_element_contribution_v1* contributions,
    size_t contribution_count,
    const xstar_canonical_thermal_term_v1* thermal_terms,
    size_t thermal_term_count,
    uint64_t* consumed_thermal_ledger_fingerprint,
    xstar_element_output_v1* output,
    char* message,
    size_t message_size
) {
    if (!context || !input || !output || !consumed_thermal_ledger_fingerprint) return 1;
    try {
        xstar_canonical_thermal::validate(thermal_terms, thermal_term_count, input->n_rows);
        const auto construction_t0 = clock_type::now();
        std::vector<xstar_element_term_v1> terms =
            construct_terms_from_contributions(*input, contributions, contribution_count);
        const double construction_seconds = seconds_since(construction_t0);
        xstar_element_input_v1 expanded = *input;
        expanded.terms = terms.empty() ? nullptr : terms.data();
        expanded.term_count = terms.size();
        std::string status;
        const int rc = run_element_impl(
            context->impl, expanded, *output, status,
            thermal_terms, thermal_term_count, consumed_thermal_ledger_fingerprint);
        if (rc == 0) {
            output->status_flags |= XSTAR_ELEMENT_STATUS_NATIVE_CONSTRUCTION;
            output->construction_seconds = construction_seconds;
            output->records_constructed = contribution_count;
            output->terms_constructed = terms.size();
            context->impl.stats.construction_calls += 1;
            context->impl.stats.records_constructed += contribution_count;
            context->impl.stats.terms_constructed += terms.size();
            context->impl.stats.construction_seconds += construction_seconds;
            std::ostringstream text;
            text << status << "; native_records=" << contribution_count
                 << "; native_terms=" << terms.size()
                 << "; canonical_thermal_terms=" << thermal_term_count;
            status = text.str();
            copy_text(output->message, sizeof(output->message), status);
        }
        copy_text(message, message_size, status);
        return rc;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        copy_text(output->message, sizeof(output->message), exc.what());
        return 2;
    } catch (...) {
        copy_text(message, message_size, "unknown native canonical Thermal construction exception");
        return 3;
    }
}

// 0.6.82.40.2.41: private production entrypoint for a canonical Thermal
// ledger already validated/fingerprinted by the local-zone builder.  Public
// callers retain xstar_element_engine_run_construction_with_thermal_ledger_v1
// and its full verification behavior.
int xstar_element_engine_run_construction_with_trusted_thermal_ledger_v068240241(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* input,
    const xstar_element_contribution_v1* contributions,
    std::size_t contribution_count,
    const xstar_canonical_thermal_term_v1* thermal_terms,
    std::size_t thermal_term_count,
    std::uint64_t authoritative_thermal_ledger_fingerprint,
    bool authoritative_thermal_ledger_fingerprint_valid,
    std::uint64_t* consumed_thermal_ledger_fingerprint,
    bool* consumed_thermal_ledger_fingerprint_valid,
    xstar_element_output_v1* output,
    char* message,
    std::size_t message_size
) {
    if (!context || !input || !output || !consumed_thermal_ledger_fingerprint ||
        !consumed_thermal_ledger_fingerprint_valid) return 1;
    try {
        const auto construction_t0 = clock_type::now();
        std::vector<xstar_element_term_v1> terms =
            construct_terms_from_contributions(*input, contributions, contribution_count);
        const double construction_seconds = seconds_since(construction_t0);
        xstar_element_input_v1 expanded = *input;
        expanded.terms = terms.empty() ? nullptr : terms.data();
        expanded.term_count = terms.size();
        std::string status;
        const int rc = run_element_impl(
            context->impl, expanded, *output, status,
            thermal_terms, thermal_term_count, consumed_thermal_ledger_fingerprint,
            true, authoritative_thermal_ledger_fingerprint,
            authoritative_thermal_ledger_fingerprint_valid,
            consumed_thermal_ledger_fingerprint_valid);
        if (rc == 0) {
            output->status_flags |= XSTAR_ELEMENT_STATUS_NATIVE_CONSTRUCTION;
            output->construction_seconds = construction_seconds;
            output->records_constructed = contribution_count;
            output->terms_constructed = terms.size();
            context->impl.stats.construction_calls += 1;
            context->impl.stats.records_constructed += contribution_count;
            context->impl.stats.terms_constructed += terms.size();
            context->impl.stats.construction_seconds += construction_seconds;
            std::ostringstream text;
            text << status << "; native_records=" << contribution_count
                 << "; native_terms=" << terms.size()
                 << "; canonical_thermal_terms=" << thermal_term_count
                 << "; trusted_canonical_thermal=1";
            status = text.str();
            copy_text(output->message, sizeof(output->message), status);
        }
        copy_text(message, message_size, status);
        return rc;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        copy_text(output->message, sizeof(output->message), exc.what());
        return 2;
    } catch (...) {
        copy_text(message, message_size, "unknown trusted canonical Thermal construction exception");
        return 3;
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute element engine run element within the element/ion population workflow, preserving the source ion-stage ordering and active-stage semantics.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute element engine run construction evaluation within the element/ion population workflow, preserving the source ion-stage ordering and active-stage semantics.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
int xstar_element_engine_run_construction_evaluation_v1(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* inputs,
    const xstar_element_contribution_v1* const* contribution_arrays,
    const size_t* contribution_counts,
    size_t element_count,
    xstar_element_output_v1* outputs,
    char* message,
    size_t message_size
) {
    if (!context || (element_count && (!inputs || !outputs || !contribution_arrays || !contribution_counts))) return 1;
    context->impl.stats.evaluations_attempted += 1;
    for (std::size_t i = 0; i < element_count; ++i) {
        char local_message[XSTAR_ELEMENT_MESSAGE_SIZE] = {};
        const int rc = xstar_element_engine_run_construction_v1(
            context, &inputs[i], contribution_arrays[i], contribution_counts[i],
            &outputs[i], local_message, sizeof(local_message));
        if (rc != 0) {
            std::ostringstream text;
            text << "construction evaluation element " << i << " failed: " << local_message;
            copy_text(message, message_size, text.str());
            return rc;
        }
    }
    context->impl.stats.evaluations_completed += 1;
    std::ostringstream text;
    text << "native construction evaluation completed; elements=" << element_count;
    copy_text(message, message_size, text.str());
    return 0;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute element engine run evaluation within the element/ion population workflow, preserving the source ion-stage ordering and active-stage semantics.
// Reference context: XSTAR Manual ss11.4.1-11.4.3; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
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
