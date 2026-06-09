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
    Error(int code, const std::string& message)
        : std::runtime_error(message), code_(code) {}
    int code() const noexcept { return code_; }
private:
    int code_;
};

class Context {
public:
    explicit Context(const xstar_config_v1& config) : context_(nullptr) {
        const int status = xstar_context_create_v1(&config, &context_);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, std::string("xstar_context_create_v1: ") + xstar_status_string(status));
        }
    }
    ~Context() { xstar_context_destroy(context_); }
    Context(const Context&) = delete;
    Context& operator=(const Context&) = delete;
    Context(Context&& other) noexcept : context_(std::exchange(other.context_, nullptr)) {}
    Context& operator=(Context&& other) noexcept {
        if (this != &other) {
            xstar_context_destroy(context_);
            context_ = std::exchange(other.context_, nullptr);
        }
        return *this;
    }

    void run(const xstar_zone_input_v1& input, xstar_zone_output_v1& output) {
        const int status = xstar_context_run_zone_v1(context_, &input, &output);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
    }

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

    void run_element(const xstar_element_input_v1& input, xstar_element_output_v1& output) {
        const int status = xstar_context_run_element_v1(context_, &input, &output);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
    }

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

    xstar_element_engine_stats_v1 element_stats() const {
        xstar_element_engine_stats_v1 stats{};
        xstar_element_engine_stats_init_v1(&stats);
        const int status = xstar_context_get_element_stats_v1(context_, &stats);
        if (status != XSTAR_STATUS_OK) {
            throw Error(status, xstar_context_last_error(context_));
        }
        return stats;
    }

    xstar_context* get() noexcept { return context_; }
    const xstar_context* get() const noexcept { return context_; }

private:
    xstar_context* context_;
};

} // namespace xstar

#endif
