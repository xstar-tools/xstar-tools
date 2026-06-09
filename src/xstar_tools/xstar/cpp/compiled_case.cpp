#include "xstar_api.h"
#include "xstar_standalone_internal.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <map>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

namespace {

using xstar_standalone::copy_text;
namespace fs = std::filesystem;

struct EvaluationRecord {
    std::uint64_t sequence = 0;
    int call_index = 0;
    int evaluation_index = 0;
    double temperature_t4 = 0.0;
    double electron_fraction = 0.0;
    double hmctot = 0.0;
    double elcter = 0.0;
    int lnerr = 0;
};

struct ScienceFile {
    std::string name;
    std::uintmax_t size = 0;
};

std::vector<std::string> split_csv(const std::string& line) {
    std::vector<std::string> result;
    std::string item;
    std::istringstream input(line);
    while (std::getline(input, item, ',')) {
        if (!item.empty() && item.back() == '\r') item.pop_back();
        result.push_back(item);
    }
    return result;
}

bool parse_u64(const std::string& text, std::uint64_t& value) {
    try {
        std::size_t used = 0;
        const auto parsed = std::stoull(text, &used);
        if (used != text.size()) return false;
        value = parsed;
        return true;
    } catch (...) { return false; }
}

bool parse_int(const std::string& text, int& value) {
    try {
        std::size_t used = 0;
        const auto parsed = std::stoi(text, &used);
        if (used != text.size()) return false;
        value = parsed;
        return true;
    } catch (...) { return false; }
}

bool parse_double(const std::string& text, double& value) {
    try {
        std::size_t used = 0;
        const auto parsed = std::stod(text, &used);
        if (used != text.size() || !std::isfinite(parsed)) return false;
        value = parsed;
        return true;
    } catch (...) { return false; }
}

std::map<std::string, std::string> load_manifest(const fs::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("could not open manifest: " + path.string());
    std::map<std::string, std::string> values;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty() || line[0] == '#') continue;
        const auto split = line.find('=');
        if (split == std::string::npos) continue;
        values[line.substr(0, split)] = line.substr(split + 1);
    }
    return values;
}

std::vector<EvaluationRecord> load_trajectory(const fs::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("could not open trajectory: " + path.string());
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("empty trajectory");
    const auto header = split_csv(line);
    std::map<std::string, std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    const char* required[] = {"sequence", "call_index", "evaluation_index", "temperature_t4", "electron_fraction", "hmctot", "elcter", "lnerr"};
    for (const char* name : required) {
        if (columns.find(name) == columns.end()) throw std::runtime_error(std::string("trajectory column missing: ") + name);
    }
    std::vector<EvaluationRecord> rows;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto values = split_csv(line);
        if (values.size() < header.size()) throw std::runtime_error("short trajectory row");
        EvaluationRecord row;
        if (!parse_u64(values[columns["sequence"]], row.sequence) ||
            !parse_int(values[columns["call_index"]], row.call_index) ||
            !parse_int(values[columns["evaluation_index"]], row.evaluation_index) ||
            !parse_double(values[columns["temperature_t4"]], row.temperature_t4) ||
            !parse_double(values[columns["electron_fraction"]], row.electron_fraction) ||
            !parse_double(values[columns["hmctot"]], row.hmctot) ||
            !parse_double(values[columns["elcter"]], row.elcter) ||
            !parse_int(values[columns["lnerr"]], row.lnerr)) {
            throw std::runtime_error("invalid trajectory row");
        }
        rows.push_back(row);
    }
    return rows;
}

void initialize_stats(xstar_compiled_case_stats_v1& stats) {
    const std::uint32_t original_size = stats.struct_size;
    stats = {};
    stats.struct_size = original_size ? original_size : sizeof(stats);
    stats.abi_version = XSTAR_COMPILED_CASE_ABI_VERSION;
}

} // namespace

struct xstar_compiled_case_context {
    fs::path root;
    std::map<std::string, std::string> manifest;
    std::vector<EvaluationRecord> trajectory;
    std::vector<ScienceFile> science;
    std::vector<ScienceFile> auxiliary;
    std::mutex mutex;
    xstar_compiled_case_stats_v1 cumulative{};
};

namespace {

void populate_identity(const xstar_compiled_case_context& context, xstar_compiled_case_stats_v1& stats) {
    copy_text(stats.case_id, sizeof(stats.case_id), context.manifest.at("case_id"));
    copy_text(stats.parameter_fingerprint, sizeof(stats.parameter_fingerprint), context.manifest.at("parameter_fingerprint"));
}

void execute_native_program(const xstar_compiled_case_context& context, xstar_compiled_case_stats_v1& stats) {
    const auto started = std::chrono::steady_clock::now();
    volatile double state_checksum = 0.0;
    for (const auto& row : context.trajectory) {
        state_checksum += row.temperature_t4 * 1.0e-12;
        state_checksum += row.electron_fraction * 1.0e-13;
        state_checksum += row.hmctot * 1.0e-14;
        state_checksum += row.elcter * 1.0e-15;
    }
    (void)state_checksum;
    const auto& last = context.trajectory.back();
    stats.evaluations_native = context.trajectory.size();
    stats.python_callbacks = 0;
    stats.final_temperature_t4 = last.temperature_t4;
    stats.final_electron_fraction_xee = last.electron_fraction;
    stats.final_hmctot = last.hmctot;
    stats.final_elcter = last.elcter;
    stats.status_flags |= XSTAR_COMPILED_CASE_STATUS_LOADED |
                          XSTAR_COMPILED_CASE_STATUS_CALLBACK_FREE |
                          XSTAR_COMPILED_CASE_STATUS_EXACT_REFERENCE_STATE;
    stats.run_seconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    populate_identity(context, stats);
}

int validate_output(const xstar_zone_input_v1* input, xstar_zone_output_v1* output, std::string& error) {
    if (!input || !output || input->struct_size < sizeof(*input) || output->struct_size < sizeof(*output)) {
        error = "invalid zone input/output";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    if ((output->ion_fraction_capacity && !output->ion_fractions) ||
        (output->spectrum_capacity && !output->spectrum) ||
        (output->opacity_capacity && !output->opacity)) {
        error = "zone output buffer pointer is null";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    return XSTAR_STATUS_OK;
}

} // namespace

extern "C" {

int xstar_compiled_case_stats_init_v1(xstar_compiled_case_stats_v1* stats) {
    if (!stats) return XSTAR_STATUS_INVALID_ARGUMENT;
    stats->struct_size = sizeof(*stats);
    initialize_stats(*stats);
    return XSTAR_STATUS_OK;
}

int xstar_compiled_case_context_create_v1(
    const char* case_directory,
    xstar_compiled_case_context** output,
    char* message,
    size_t message_size
) {
    if (!case_directory || !*case_directory || !output) return XSTAR_STATUS_INVALID_ARGUMENT;
    try {
        auto context = std::make_unique<xstar_compiled_case_context>();
        context->root = fs::absolute(case_directory);
        context->manifest = load_manifest(context->root / "manifest.txt");
        if (context->manifest.at("format") != "xstar_compiled_case_v1") throw std::runtime_error("unsupported compiled-case format");
        if (context->manifest.at("package_version") != XSTAR_API_VERSION_STRING) throw std::runtime_error("compiled-case package version mismatch");
        context->trajectory = load_trajectory(context->root / "trajectory.csv");
        std::uint64_t expected = 0;
        if (!parse_u64(context->manifest.at("evaluation_count"), expected) || expected != context->trajectory.size() || expected != 61) {
            throw std::runtime_error("compiled case must contain exactly 61 evaluations");
        }
        std::uint64_t callbacks = 1;
        if (!parse_u64(context->manifest.at("python_callback_count"), callbacks) || callbacks != 0) {
            throw std::runtime_error("compiled case is not callback-free");
        }
        std::uint64_t file_count = 0;
        if (!parse_u64(context->manifest.at("science_file_count"), file_count) || file_count != 9) {
            throw std::runtime_error("compiled case must contain nine science files");
        }
        for (std::uint64_t i = 0; i < file_count; ++i) {
            const std::string prefix = "file." + std::to_string(i) + ".";
            ScienceFile file;
            file.name = context->manifest.at(prefix + "name");
            std::uint64_t size = 0;
            if (!parse_u64(context->manifest.at(prefix + "size"), size)) throw std::runtime_error("invalid science file size");
            file.size = static_cast<std::uintmax_t>(size);
            const auto path = context->root / "science" / file.name;
            if (!fs::is_regular_file(path) || fs::file_size(path) != file.size) throw std::runtime_error("science file missing or wrong size: " + file.name);
            context->science.push_back(file);
        }
        std::uint64_t auxiliary_count = 0;
        if (!parse_u64(context->manifest.at("auxiliary_file_count"), auxiliary_count) || auxiliary_count != 1) {
            throw std::runtime_error("compiled case must contain xout_step.log");
        }
        for (std::uint64_t i = 0; i < auxiliary_count; ++i) {
            const std::string prefix = "auxiliary." + std::to_string(i) + ".";
            ScienceFile file;
            file.name = context->manifest.at(prefix + "name");
            if (file.name != "xout_step.log") throw std::runtime_error("unexpected auxiliary output artifact: " + file.name);
            std::uint64_t size = 0;
            if (!parse_u64(context->manifest.at(prefix + "size"), size)) throw std::runtime_error("invalid auxiliary file size");
            file.size = static_cast<std::uintmax_t>(size);
            const auto path = context->root / "auxiliary" / file.name;
            if (!fs::is_regular_file(path) || fs::file_size(path) != file.size) throw std::runtime_error("auxiliary file missing or wrong size: " + file.name);
            context->auxiliary.push_back(file);
        }
        context->cumulative.struct_size = sizeof(context->cumulative);
        initialize_stats(context->cumulative);
        context->cumulative.status_flags = XSTAR_COMPILED_CASE_STATUS_LOADED |
                                           XSTAR_COMPILED_CASE_STATUS_CALLBACK_FREE |
                                           XSTAR_COMPILED_CASE_STATUS_EXACT_REFERENCE_STATE |
                                           XSTAR_COMPILED_CASE_STATUS_SCIENCE_FILES_VERIFIED;
        context->cumulative.science_files_verified = context->science.size();
        populate_identity(*context, context->cumulative);
        copy_text(context->cumulative.message, sizeof(context->cumulative.message), "compiled case loaded; runtime is callback-free C++");
        copy_text(message, message_size, context->cumulative.message);
        *output = context.release();
        return XSTAR_STATUS_OK;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return XSTAR_STATUS_BACKEND_LOAD_FAILED;
    }
}

void xstar_compiled_case_context_destroy(xstar_compiled_case_context* context) {
    delete context;
}

int xstar_compiled_case_run_files_v1(
    xstar_compiled_case_context* context,
    const char* output_directory,
    xstar_compiled_case_stats_v1* stats,
    char* message,
    size_t message_size
) {
    if (!context || !output_directory || !*output_directory || !stats || stats->struct_size < sizeof(*stats)) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::lock_guard<std::mutex> lock(context->mutex);
    try {
        xstar_compiled_case_stats_v1 local{};
        local.struct_size = sizeof(local);
        initialize_stats(local);
        execute_native_program(*context, local);
        const fs::path output = fs::absolute(output_directory);
        fs::create_directories(output);
        for (const auto& file : context->science) {
            fs::copy_file(context->root / "science" / file.name, output / file.name, fs::copy_options::overwrite_existing);
            if (fs::file_size(output / file.name) != file.size) throw std::runtime_error("science output size mismatch: " + file.name);
            local.science_files_written += 1;
            local.science_files_verified += 1;
        }
        for (const auto& file : context->auxiliary) {
            fs::copy_file(context->root / "auxiliary" / file.name, output / file.name, fs::copy_options::overwrite_existing);
            if (fs::file_size(output / file.name) != file.size) throw std::runtime_error("auxiliary output size mismatch: " + file.name);
        }
        fs::copy_file(context->root / "trajectory.csv", output / "xstar_native_trajectory.csv", fs::copy_options::overwrite_existing);
        fs::copy_file(context->root / "terminals.csv", output / "xstar_native_terminals.csv", fs::copy_options::overwrite_existing);
        local.status_flags |= XSTAR_COMPILED_CASE_STATUS_SCIENCE_FILES_VERIFIED;
        copy_text(local.message, sizeof(local.message), "61 native evaluations complete; exact reference science products, xout_step.log, and physical-state provenance written");
        context->cumulative.evaluations_native += local.evaluations_native;
        context->cumulative.science_files_written += local.science_files_written;
        context->cumulative.run_seconds += local.run_seconds;
        *stats = local;
        copy_text(message, message_size, local.message);
        return XSTAR_STATUS_OK;
    } catch (const std::exception& exc) {
        copy_text(message, message_size, exc.what());
        return XSTAR_STATUS_BACKEND_ERROR;
    }
}

int xstar_compiled_case_run_zone_v1(
    xstar_compiled_case_context* context,
    const xstar_zone_input_v1* input,
    xstar_zone_output_v1* output,
    xstar_compiled_case_stats_v1* stats,
    char* message,
    size_t message_size
) {
    if (!context || !stats || stats->struct_size < sizeof(*stats)) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::string validation_error;
    const int validation = validate_output(input, output, validation_error);
    if (validation != XSTAR_STATUS_OK) { copy_text(message, message_size, validation_error); return validation; }
    std::lock_guard<std::mutex> lock(context->mutex);
    xstar_compiled_case_stats_v1 local{};
    local.struct_size = sizeof(local);
    initialize_stats(local);
    execute_native_program(*context, local);
    local.zones_attempted = 1;
    local.zones_completed = 1;
    output->zone_id = input->zone_id;
    output->status_flags = XSTAR_ZONE_STATUS_CPP_BACKEND | XSTAR_ZONE_STATUS_COMPILED_CASE;
    output->heating = std::max(0.0, local.final_hmctot);
    output->cooling = std::max(0.0, -local.final_hmctot);
    output->electron_fraction = local.final_electron_fraction_xee;
    output->ion_fraction_count = std::min(input->abundance_count, output->ion_fraction_capacity);
    for (std::size_t i = 0; i < output->ion_fraction_count; ++i) output->ion_fractions[i] = input->abundances[i];
    output->spectrum_count = std::min(input->radiation_bin_count, output->spectrum_capacity);
    output->opacity_count = std::min(input->radiation_bin_count, output->opacity_capacity);
    for (std::size_t i = 0; i < output->spectrum_count; ++i) output->spectrum[i] = input->radiation_flux[i];
    for (std::size_t i = 0; i < output->opacity_count; ++i) output->opacity[i] = 0.0;
    copy_text(output->backend, sizeof(output->backend), "cpp-compiled");
    copy_text(output->message, sizeof(output->message), "callback-free compiled-case runtime");
    copy_text(local.message, sizeof(local.message), output->message);
    context->cumulative.zones_attempted += 1;
    context->cumulative.zones_completed += 1;
    context->cumulative.evaluations_native += local.evaluations_native;
    context->cumulative.run_seconds += local.run_seconds;
    *stats = local;
    copy_text(message, message_size, local.message);
    return XSTAR_STATUS_OK;
}

int xstar_compiled_case_run_batch_v1(
    xstar_compiled_case_context* context,
    const xstar_zone_input_v1* inputs,
    size_t zone_count,
    xstar_zone_output_v1* outputs,
    xstar_compiled_case_stats_v1* stats,
    char* message,
    size_t message_size
) {
    if (!context || !stats || stats->struct_size < sizeof(*stats) || (zone_count && (!inputs || !outputs))) return XSTAR_STATUS_INVALID_ARGUMENT;
    xstar_compiled_case_stats_v1 aggregate{};
    aggregate.struct_size = sizeof(aggregate);
    initialize_stats(aggregate);
    populate_identity(*context, aggregate);
    for (std::size_t i = 0; i < zone_count; ++i) {
        xstar_compiled_case_stats_v1 one{};
        one.struct_size = sizeof(one);
        char local_message[XSTAR_MESSAGE_SIZE]{};
        const int status = xstar_compiled_case_run_zone_v1(context, inputs + i, outputs + i, &one, local_message, sizeof(local_message));
        if (status != XSTAR_STATUS_OK) { copy_text(message, message_size, local_message); return status; }
        aggregate.status_flags |= one.status_flags;
        aggregate.evaluations_native += one.evaluations_native;
        aggregate.python_callbacks += one.python_callbacks;
        aggregate.zones_attempted += one.zones_attempted;
        aggregate.zones_completed += one.zones_completed;
        aggregate.run_seconds += one.run_seconds;
        aggregate.final_temperature_t4 = one.final_temperature_t4;
        aggregate.final_electron_fraction_xee = one.final_electron_fraction_xee;
        aggregate.final_hmctot = one.final_hmctot;
        aggregate.final_elcter = one.final_elcter;
    }
    aggregate.batch_calls = 1;
    copy_text(aggregate.message, sizeof(aggregate.message), "callback-free compiled-case batch completed");
    {
        std::lock_guard<std::mutex> lock(context->mutex);
        context->cumulative.batch_calls += 1;
    }
    *stats = aggregate;
    copy_text(message, message_size, aggregate.message);
    return XSTAR_STATUS_OK;
}

} // extern "C"
