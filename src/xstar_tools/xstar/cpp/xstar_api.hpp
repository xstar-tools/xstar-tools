// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: No direct Fortran routine; wraps the xstar_api.h boundary around xstarcalc-equivalent execution.
// Role: C++ RAII/convenience wrapper for the public C ABI.
// Relation: Infrastructure only; must be behaviorally transparent to scientific results.
// Concordance: BACKEND-001
// Qualification: ABI 6048110 freeze
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_API_HPP
#define XSTAR_API_HPP

#include "xstar_api.h"
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace xstar {

class Error : public std::runtime_error {
public:
    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Provide the C++ RAII Error wrapper around the stable C ABI; ownership/error handling is isolated here from the scientific implementation.
    // Reference context: Implementation/API helper; no independent scientific formula.
    // XSTAR-FUNCTION-COMMENT-END
    Error(int code, const std::string& message)
        : std::runtime_error(message), code_(code) {}
    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke code through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    int code() const noexcept { return code_; }
private:
    int code_;
};

class Context {
public:
    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Provide the C++ RAII Context wrapper around the stable C ABI; ownership/error handling is isolated here from the scientific implementation.
    // Reference context: Implementation/API helper; no independent scientific formula.
    // XSTAR-FUNCTION-COMMENT-END
    explicit Context(const xstar_config_v1& config) : context_(nullptr) {
        const int status = xstar_context_create_v1(&config, &context_);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, std::string("xstar_context_create_v1: ") + xstar_status_string(status));
        }
    }
    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Provide the C++ RAII ~Context wrapper around the stable C ABI; ownership/error handling is isolated here from the scientific implementation.
    // Reference context: Implementation/API helper; no independent scientific formula.
    // XSTAR-FUNCTION-COMMENT-END
    ~Context() { xstar_context_destroy(context_); }
    Context(const Context&) = delete;
    Context& operator=(const Context&) = delete;
    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Provide the C++ RAII Context wrapper around the stable C ABI; ownership/error handling is isolated here from the scientific implementation.
    // Reference context: Implementation/API helper; no independent scientific formula.
    // XSTAR-FUNCTION-COMMENT-END
    Context(Context&& other) noexcept : context_(std::exchange(other.context_, nullptr)) {}
    Context& operator=(Context&& other) noexcept {
        if (this != &other) {
            xstar_context_destroy(context_);
            context_ = std::exchange(other.context_, nullptr);
        }
        return *this;
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke run through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    void run(const xstar_zone_input_v1& input, xstar_zone_output_v1& output) {
        const int status = xstar_context_run_zone_v1(context_, &input, &output);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke run batch through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    void run_batch(const std::vector<xstar_zone_input_v1>& inputs,
                   std::vector<xstar_zone_output_v1>& outputs) {
        if (inputs.size() != outputs.size()) {
            throw std::invalid_argument("input/output batch sizes differ");
        }
        const int status = xstar_context_run_batch_v1(
            context_, inputs.data(), inputs.size(), outputs.data());
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke run element construction through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    void run_element_construction(
        const xstar_element_input_v1& input,
        const std::vector<xstar_element_contribution_v1>& contributions,
        xstar_element_output_v1& output
    ) {
        const int status = xstar_context_run_element_construction_v1(
            context_, &input, contributions.data(), contributions.size(), &output);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke run element through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    void run_element(const xstar_element_input_v1& input, xstar_element_output_v1& output) {
        const int status = xstar_context_run_element_v1(context_, &input, &output);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke run construction evaluation through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    void run_construction_evaluation(
        const std::vector<xstar_element_input_v1>& inputs,
        const std::vector<std::vector<xstar_element_contribution_v1>>& contributions,
        std::vector<xstar_element_output_v1>& outputs
    ) {
        if (inputs.size() != outputs.size() || inputs.size() != contributions.size()) {
            throw std::invalid_argument("construction input/contribution/output sizes differ");
        }
        std::vector<const xstar_element_contribution_v1*> arrays(inputs.size(), nullptr);
        std::vector<std::size_t> counts(inputs.size(), 0);
        for (std::size_t i = 0; i < inputs.size(); ++i) {
            arrays[i] = contributions[i].empty() ? nullptr : contributions[i].data();
            counts[i] = contributions[i].size();
        }
        const int status = xstar_context_run_construction_evaluation_v1(
            context_, inputs.data(), arrays.data(), counts.data(), inputs.size(), outputs.data());
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke run evaluation through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    void run_evaluation(const std::vector<xstar_element_input_v1>& inputs,
                        std::vector<xstar_element_output_v1>& outputs) {
        if (inputs.size() != outputs.size()) {
            throw std::invalid_argument("element input/output sizes differ");
        }
        const int status = xstar_context_run_evaluation_v1(
            context_, inputs.data(), inputs.size(), outputs.data());
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke apply spectral through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    xstar_spectral_stats_v1 apply_spectral(
        const std::vector<xstar_spectral_contribution_v1>& contributions,
        const std::vector<double>& seed_profiles,
        std::size_t seed_profile_stride,
        xstar_spectral_workspace_v1& workspace
    ) {
        xstar_spectral_stats_v1 stats{};
        xstar_spectral_stats_init_v1(&stats);
        const int status = xstar_context_apply_spectral_contributions_v1(
            context_, contributions.empty() ? nullptr : contributions.data(), contributions.size(),
            seed_profiles.empty() ? nullptr : seed_profiles.data(), seed_profile_stride,
            &workspace, &stats);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
        return stats;
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke apply heatt through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    xstar_heatt_stats_v1 apply_heatt(
        xstar_heatt_workspace_v1& workspace,
        const std::vector<xstar_heatt_line_v1>& lines,
        const std::vector<xstar_heatt_rrc_v1>& rrcs
    ) {
        xstar_heatt_stats_v1 stats{};
        stats.struct_size = sizeof(stats);
        stats.abi_version = XSTAR_THERMAL_ENGINE_ABI_VERSION;
        const int status = xstar_context_apply_heatt_v1(
            context_, &workspace, lines.empty() ? nullptr : lines.data(), lines.size(),
            rrcs.empty() ? nullptr : rrcs.data(), rrcs.size(), &stats);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
        return stats;
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke run thermal evaluation loop through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    xstar_dsec_stats_v1 run_thermal_evaluation_loop(
        const xstar_dsec_config_v1& config,
        xstar_thermal_state_v1& state,
        xstar_thermal_evaluator_fn_v1 evaluator,
        void* user_data,
        std::vector<xstar_thermal_trace_event_v1>& trace
    ) {
        xstar_dsec_stats_v1 stats{};
        stats.struct_size = sizeof(stats);
        stats.abi_version = XSTAR_THERMAL_ENGINE_ABI_VERSION;
        std::size_t trace_count = 0;
        const int status = xstar_context_run_thermal_evaluation_loop_v1(
            context_, &config, &state, evaluator, user_data,
            trace.empty() ? nullptr : trace.data(), trace.size(), &trace_count, &stats);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
        if (trace_count < trace.size()) trace.resize(trace_count);
        return stats;
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke element stats through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    xstar_element_engine_stats_v1 element_stats() const {
        xstar_element_engine_stats_v1 stats{};
        xstar_element_engine_stats_init_v1(&stats);
        const int status = xstar_context_get_element_stats_v1(context_, &stats);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
        return stats;
    }

    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke get through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    xstar_context* get() noexcept { return context_; }
    // XSTAR-FUNCTION-COMMENT-BEGIN
    // Purpose: Invoke get through the stable C ABI while preserving the same shared scientific engine used by the C and Python-facing paths.
    // Reference context: Implementation/API helper; scientific semantics are owned by the called engine and the frozen ABI contract.
    // XSTAR-FUNCTION-COMMENT-END
    const xstar_context* get() const noexcept { return context_; }

private:
    xstar_context* context_;
};

} // namespace xstar

#endif
