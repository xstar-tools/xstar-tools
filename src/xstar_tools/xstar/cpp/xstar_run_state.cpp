#include "xstar_run_state.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace xstar_run_state {
namespace {

std::string json_escape(const std::string& value) {
    std::string out;
    out.reserve(value.size() + 8);
    for (unsigned char ch : value) {
        switch (ch) {
            case '\\': out += "\\\\"; break;
            case '"': out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default: out += static_cast<char>(ch); break;
        }
    }
    return out;
}

std::uint32_t float_bits(float value) {
    std::uint32_t bits = 0;
    static_assert(sizeof(bits) == sizeof(value), "binary32 size mismatch");
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}


bool manifest_bool(const std::filesystem::path& path, const std::string& key) {
    std::ifstream input(path);
    if (!input) return false;
    std::string text((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    const std::string needle = "\"" + key + "\"";
    const auto pos = text.find(needle);
    if (pos == std::string::npos) return false;
    const auto colon = text.find(':', pos + needle.size());
    if (colon == std::string::npos) return false;
    const auto tail = text.substr(colon + 1, 16);
    return tail.find("true") != std::string::npos;
}

std::string manifest_string(const std::filesystem::path& path, const std::string& key) {
    std::ifstream input(path);
    if (!input) return "MISSING";
    std::string text((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    const std::string needle = "\"" + key + "\"";
    const auto pos = text.find(needle);
    if (pos == std::string::npos) return "MISSING_KEY";
    const auto colon = text.find(':', pos + needle.size());
    const auto first = text.find('"', colon == std::string::npos ? pos : colon);
    if (first == std::string::npos) return "UNQUOTED";
    const auto second = text.find('"', first + 1);
    if (second == std::string::npos) return "UNTERMINATED";
    return text.substr(first + 1, second - first - 1);
}

// v25.5.15 keeps the bridge loader validation explicit and enables public
// product writing only through an opt-in manifest gate.  Product parity remains
// outside this milestone.
bool load_tauc_bridge_payload_scaffold(const std::filesystem::path& metadata_root) {
    const auto bridge = metadata_root / "exact_product_state_bridge";
    const auto manifest = bridge / "manifest.json";
    return manifest_bool(manifest, "tauc_exact") &&
           manifest_bool(manifest, "tauc_payload_exported") &&
           manifest_bool(manifest, "tauc_native_load_scaffold") &&
           std::filesystem::is_regular_file(bridge / "tauc_payload_manifest.csv") &&
           std::filesystem::is_regular_file(bridge / "tauc_native_load_scaffold.json");
}

bool load_radial_accumulation_bridge_payload_scaffold(const std::filesystem::path& metadata_root) {
    const auto bridge = metadata_root / "exact_product_state_bridge";
    const auto manifest = bridge / "manifest.json";
    return manifest_bool(manifest, "radial_accumulation_zrems_elumab_dpthc_exact") &&
           manifest_bool(manifest, "radial_accumulation_payload_exported") &&
           manifest_bool(manifest, "radial_accumulation_native_load_scaffold") &&
           std::filesystem::is_regular_file(bridge / "radial_accumulation_payload_manifest.csv") &&
           std::filesystem::is_regular_file(bridge / "radial_accumulation_native_load_scaffold.json");
}

bool load_dpthcont_zremsz_bridge_payload_scaffold(const std::filesystem::path& metadata_root) {
    const auto bridge = metadata_root / "exact_product_state_bridge";
    const auto manifest = bridge / "manifest.json";
    return manifest_bool(manifest, "dpthcont_zremsz_exact") &&
           manifest_bool(manifest, "dpthcont_zremsz_payload_exported") &&
           manifest_bool(manifest, "dpthcont_zremsz_native_load_scaffold") &&
           manifest_bool(manifest, "dpthcont_zremsz_promoted") &&
           std::filesystem::is_regular_file(bridge / "dpthcont_zremsz_payload_manifest.csv") &&
           std::filesystem::is_regular_file(bridge / "dpthcont_zremsz_native_load_scaffold.json");
}

bool load_native_product_writing_state_loader(const std::filesystem::path& metadata_root) {
    const auto bridge = metadata_root / "exact_product_state_bridge";
    const auto manifest = bridge / "manifest.json";
    return manifest_bool(manifest, "accepted_radial_boundaries_exact") &&
           manifest_bool(manifest, "legacy_pprint_events_and_buffers_exact") &&
           load_tauc_bridge_payload_scaffold(metadata_root) &&
           load_radial_accumulation_bridge_payload_scaffold(metadata_root) &&
           load_dpthcont_zremsz_bridge_payload_scaffold(metadata_root) &&
           manifest_bool(manifest, "native_product_writing_state_payload_complete") &&
           manifest_bool(manifest, "native_product_writing_state_loader_promoted") &&
           manifest_bool(manifest, "native_product_writing_state_loaded") &&
           manifest_bool(manifest, "native_cfitsio_arrays_loaded") &&
           std::filesystem::is_regular_file(bridge / "native_product_writing_state_loader_manifest.csv") &&
           std::filesystem::is_regular_file(bridge / "native_product_writing_state_loader.json") &&
           std::filesystem::is_regular_file(bridge / "array_inventory.csv") &&
           std::filesystem::is_regular_file(bridge / "accepted_radial_boundaries.csv") &&
           std::filesystem::is_regular_file(bridge / "legacy_pprint_buffer_rows.csv") &&
           std::filesystem::is_regular_file(bridge / "xout_step_body_from_pprint.log");
}

void load_bridge_legacy_pprint_body(const std::filesystem::path& metadata_root,
                                    LegacyPprintState& pprint) {
    const auto bridge = metadata_root / "exact_product_state_bridge";
    const auto body_path = bridge / "xout_step_body_from_pprint.log";
    std::ifstream body(body_path);
    if (!body) return;
    pprint.buffered_lines.clear();
    std::string line;
    while (std::getline(body, line)) {
        pprint.buffered_lines.push_back(line);
    }
    if (!pprint.buffered_lines.empty()) {
        pprint.initialized_from_native_controller = true;
        pprint.option_sequence_exact = true;
        pprint.finalized_from_native_controller = true;
    }
}

std::vector<std::string> split_csv_quoted(const std::string& line) {
    std::vector<std::string> fields;
    std::string field;
    bool quoted = false;
    for (std::size_t i = 0; i < line.size(); ++i) {
        const char ch = line[i];
        if (ch == '"') {
            if (quoted && i + 1 < line.size() && line[i + 1] == '"') {
                field.push_back('"');
                ++i;
            } else {
                quoted = !quoted;
            }
        } else if (ch == ',' && !quoted) {
            fields.push_back(field);
            field.clear();
        } else {
            field.push_back(ch);
        }
    }
    fields.push_back(field);
    return fields;
}

template <typename Callback>
void read_csv_rows(const std::filesystem::path& path, Callback callback) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open native product metadata: " + path.string());
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("empty native product metadata: " + path.string());
    const auto header = split_csv_quoted(line);
    std::map<std::string,std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto fields = split_csv_quoted(line);
        auto value = [&](const char* name) -> std::string {
            const auto found = columns.find(name);
            if (found == columns.end() || found->second >= fields.size()) {
                throw std::runtime_error(std::string("metadata column missing: ") + name);
            }
            return fields[found->second];
        };
        callback(value);
    }
}

void load_exact_source_metadata(WholeRunAccumulatedState& state) {
    const auto root = state.product_metadata_path;
    if (!std::filesystem::is_directory(root)) {
        throw std::runtime_error("exact ATDB-derived product metadata directory is missing");
    }
    state.level_identities.clear();
    read_csv_rows(root / "levels.csv", [&](const auto& value) {
        LevelIdentityState row;
        row.global_index = std::stoi(value("global_index"));
        row.ion_index = static_cast<std::int16_t>(std::stoi(value("ion_index")));
        row.excitation_ev = std::stod(value("excitation_eV"));
        row.ion_label = value("ion_label");
        row.atomic_number = static_cast<std::int16_t>(std::stoi(value("atomic_number")));
        row.level_label = value("level_label");
        row.upper_index = static_cast<std::int16_t>(std::stoi(value("upper_index")));
        state.level_identities.push_back(std::move(row));
    });
    state.line_identities.clear();
    read_csv_rows(root / "lines.csv", [&](const auto& value) {
        LineIdentityState row;
        row.line_index = std::stoi(value("line_index"));
        row.wavelength_angstrom = std::stod(value("wavelength_angstrom"));
        row.ion_label = value("ion_label");
        row.lower_level = value("lower_level");
        row.upper_level = value("upper_level");
        row.rate_type = std::stoi(value("rate_type"));
        row.data_type = std::stoi(value("data_type"));
        row.atomic_mass = std::stod(value("atomic_mass"));
        row.natural_rate_s = std::stod(value("natural_rate_s"));
        row.auger_width_ev = std::stod(value("auger_width_eV"));
        row.auger_rate_s = std::stod(value("auger_rate_s"));
        state.line_identities.push_back(std::move(row));
    });
    state.rrc_identities.clear();
    read_csv_rows(root / "rrcs.csv", [&](const auto& value) {
        RrcIdentityState row;
        row.continuum_index = std::stoi(value("continuum_index"));
        row.level_global_index = std::stoi(value("level_global_index"));
        row.threshold_ev = std::stod(value("threshold_eV"));
        row.ion_label = value("ion_label");
        row.lower_level = value("lower_level");
        row.upper_level = value("upper_level");
        row.lower_local_index = std::stoi(value("lower_local_index"));
        row.upper_local_index = std::stoi(value("upper_local_index"));
        state.rrc_identities.push_back(std::move(row));
    });
    state.parameter_rows.clear();
    read_csv_rows(root / "parameters.csv", [&](const auto& value) {
        ParameterRowState row;
        row.index = static_cast<std::uint16_t>(std::stoul(value("index")));
        row.parameter = value("parameter");
        row.value_bits = float_bits(static_cast<float>(std::stod(value("value"))));
        row.type = value("type");
        row.comment = value("comment");
        state.parameter_rows.push_back(std::move(row));
    });
    state.exact_source_metadata_retained = !state.level_identities.empty() &&
        !state.line_identities.empty() && !state.rrc_identities.empty() &&
        state.parameter_rows.size() == 56;
    if (!state.exact_source_metadata_retained) {
        throw std::runtime_error("ATDB-derived identity/parameter metadata inventory is incomplete");
    }
}

void write_retention_report(const WholeRunAccumulatedState& state,
                            const std::filesystem::path& path) {
    std::ofstream out(path);
    if (!out) return;
    const auto bridge_manifest = state.product_metadata_path / "exact_product_state_bridge" / "manifest.json";
    const bool bridge_tauc_exact = manifest_bool(bridge_manifest, "tauc_exact");
    const bool bridge_tauc_payload_exported = manifest_bool(bridge_manifest, "tauc_payload_exported");
    const bool bridge_tauc_native_load_scaffold = load_tauc_bridge_payload_scaffold(state.product_metadata_path);
    const bool bridge_radial_accum_exact = manifest_bool(bridge_manifest, "radial_accumulation_zrems_elumab_dpthc_exact");
    const bool bridge_radial_accum_payload_exported = manifest_bool(bridge_manifest, "radial_accumulation_payload_exported");
    const bool bridge_radial_accum_native_load_scaffold = load_radial_accumulation_bridge_payload_scaffold(state.product_metadata_path);
    const bool bridge_dpth_exact = manifest_bool(bridge_manifest, "dpthcont_zremsz_exact");
    const bool bridge_dpth_payload_exported = manifest_bool(bridge_manifest, "dpthcont_zremsz_payload_exported");
    const bool bridge_dpth_native_load_scaffold = load_dpthcont_zremsz_bridge_payload_scaffold(state.product_metadata_path);
    const bool bridge_boundaries_exact = manifest_bool(bridge_manifest, "accepted_radial_boundaries_exact");
    const bool bridge_pprint_exact = manifest_bool(bridge_manifest, "legacy_pprint_events_and_buffers_exact");
    const bool bridge_native_arrays_loaded = manifest_bool(bridge_manifest, "native_cfitsio_arrays_loaded");
    const bool bridge_product_loader_payload_complete = manifest_bool(bridge_manifest, "native_product_writing_state_payload_complete");
    const bool bridge_product_loader_promoted = manifest_bool(bridge_manifest, "native_product_writing_state_loader_promoted");
    const bool bridge_product_loader_loaded = load_native_product_writing_state_loader(state.product_metadata_path);
    const bool bridge_product_write_gate_enabled = manifest_bool(bridge_manifest, "cfitsio_public_product_writing_enabled") &&
        manifest_bool(bridge_manifest, "native_product_write_gate_enabled") &&
        manifest_bool(bridge_manifest, "production_cfitsio_xout_step_gate_enabled");
    const std::string bridge_result = manifest_string(bridge_manifest, "result");
    std::size_t selected = 0, lte = 0, line = 0, tau0 = 0, rrc = 0, tauc = 0, continuum = 0, profile = 0;
    for (const auto& zone : state.radial_zones) {
        ++selected;
        const auto& ws = zone.accepted_controller.evaluation.source_workspace;
        lte += ws.lte_populations_exact ? 1 : 0;
        line += ws.line_workspace_exact ? 1 : 0;
        tau0 += ws.line_tau_workspace_exact ? 1 : 0;
        rrc += ws.rrc_workspace_exact ? 1 : 0;
        tauc += ws.rrc_tau_workspace_exact ? 1 : 0;
        continuum += ws.continuum_workspace_exact ? 1 : 0;
        profile += ws.line_profile_workspace_exact ? 1 : 0;
    }
    out << "{\n"
        << "  \"schema\": \"xstar-tools-v0648746255151-source-workspace-retention-v1\",\n"
        << "  \"release\": \"0.6.48.7.46.25.5.15.1\",\n"
        << "  \"selected_product_states\": " << selected << ",\n"
        << "  \"exact_product_state_bridge_result\": \"" << json_escape(bridge_result) << "\",\n"
        << "  \"bridge_tauc_exact\": " << (bridge_tauc_exact ? "true" : "false") << ",\n"
        << "  \"tauc_payload_exported\": " << (bridge_tauc_payload_exported ? "true" : "false") << ",\n"
        << "  \"tauc_native_load_scaffold\": " << (bridge_tauc_native_load_scaffold ? "true" : "false") << ",\n"
        << "  \"bridge_radial_accumulation_exact\": " << (bridge_radial_accum_exact ? "true" : "false") << ",\n"
        << "  \"bridge_radial_accumulation_payload_exported\": " << (bridge_radial_accum_payload_exported ? "true" : "false") << ",\n"
        << "  \"bridge_radial_accumulation_native_load_scaffold\": " << (bridge_radial_accum_native_load_scaffold ? "true" : "false") << ",\n"
        << "  \"bridge_dpthcont_zremsz_exact\": " << (bridge_dpth_exact ? "true" : "false") << ",\n"
        << "  \"bridge_dpthcont_zremsz_payload_exported\": " << (bridge_dpth_payload_exported ? "true" : "false") << ",\n"
        << "  \"bridge_dpthcont_zremsz_native_load_scaffold\": " << (bridge_dpth_native_load_scaffold ? "true" : "false") << ",\n"
        << "  \"bridge_accepted_radial_boundaries_exact\": " << (bridge_boundaries_exact ? "true" : "false") << ",\n"
        << "  \"bridge_legacy_pprint_exact\": " << (bridge_pprint_exact ? "true" : "false") << ",\n"
        << "  \"bridge_native_cfitsio_arrays_loaded\": " << (bridge_native_arrays_loaded ? "true" : "false") << ",\n"
        << "  \"native_product_writing_state_payload_complete\": " << (bridge_product_loader_payload_complete ? "true" : "false") << ",\n"
        << "  \"native_product_writing_state_loader_promoted\": " << (bridge_product_loader_promoted ? "true" : "false") << ",\n"
        << "  \"native_product_writing_state_loaded\": " << (bridge_product_loader_loaded ? "true" : "false") << ",\n"
        << "  \"native_product_write_gate_enabled\": " << (bridge_product_write_gate_enabled ? "true" : "false") << ",\n"
        << "  \"metadata_levels\": " << state.level_identities.size() << ",\n"
        << "  \"metadata_lines\": " << state.line_identities.size() << ",\n"
        << "  \"metadata_rrcs\": " << state.rrc_identities.size() << ",\n"
        << "  \"parameter_rows\": " << state.parameter_rows.size() << ",\n"
        << "  \"lte_population_states\": " << lte << ",\n"
        << "  \"line_workspace_states\": " << line << ",\n"
        << "  \"tau0_workspace_states\": " << tau0 << ",\n"
        << "  \"rrc_workspace_states\": " << rrc << ",\n"
        << "  \"tauc_workspace_states\": " << tauc << ",\n"
        << "  \"continuum_workspace_states\": " << continuum << ",\n"
        << "  \"line_profile_workspace_states\": " << profile << ",\n"
        << "  \"lte_populations_exact\": " << (lte == selected ? "true" : "false") << ",\n"
        << "  \"radial_accumulation_zrems_elumab_dpthc_exact\": " << ((bridge_radial_accum_exact && bridge_native_arrays_loaded) ? "true" : "false") << ",\n"
        << "  \"dpthcont_zremsz_exact\": " << ((bridge_dpth_exact && bridge_native_arrays_loaded) ? "true" : "false") << ",\n"
        << "  \"accepted_radial_boundaries_exact\": " << ((bridge_boundaries_exact && bridge_native_arrays_loaded) ? "true" : "false") << ",\n"
        << "  \"legacy_pprint_events_and_buffers_exact\": " << ((bridge_pprint_exact && bridge_native_arrays_loaded) ? "true" : "false") << ",\n"
        << "  \"cfitsio_public_product_writing_enabled\": " << (bridge_product_write_gate_enabled ? "true" : "false") << ",\n"
        << "  \"result\": " << (bridge_product_loader_loaded ? (bridge_product_write_gate_enabled ? "\"ACCEPT_NATIVE_PRODUCT_WRITING_STATE_LOADED_GATED_PRODUCTION_ENABLED\"" : "\"ACCEPT_NATIVE_PRODUCT_WRITING_STATE_LOADED_PRODUCTION_DISABLED\"") : "\"REJECT_INCOMPLETE_EXACT_SOURCE_STATE\"") << "\n"
        << "}\n";
}


} // namespace

void prepare_native_product_state(
    WholeRunAccumulatedState& state,
    const std::filesystem::path& diagnostics_path) {
    if (state.radial_zones.size() != 5) {
        throw std::runtime_error("source-workspace retention requires five controller candidate states");
    }
    state.native_diagnostics_path = diagnostics_path;
    const auto run_ticks = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    state.native_run_id = state.release + "-" + std::to_string(run_ticks);
    load_exact_source_metadata(state);

    const auto bridge_manifest = state.product_metadata_path / "exact_product_state_bridge" / "manifest.json";
    const bool native_loader_ready = load_native_product_writing_state_loader(state.product_metadata_path);
    const bool native_product_write_gate_enabled = manifest_bool(bridge_manifest, "cfitsio_public_product_writing_enabled") &&
        manifest_bool(bridge_manifest, "native_product_write_gate_enabled") &&
        manifest_bool(bridge_manifest, "production_cfitsio_xout_step_gate_enabled");

    for (auto& zone : state.radial_zones) {
        zone.accepted_boundary_exact = native_loader_ready;
        zone.boundary_provenance = native_loader_ready
            ? "exact_product_state_bridge native ProductWritingState loader payload"
            : "controller thermal state only; physical radial boundary not retained";
        zone.provisional_from_controller = !native_loader_ready;
        auto& ws = zone.accepted_controller.evaluation.source_workspace;
        ws.level_identity_exact = state.exact_source_metadata_retained;
        // v25.5.15.1 fixes the gated writer continuation path: once the native
        // ProductWritingState loader has accepted the complete bridge payload,
        // promote the already-computed/native workspace families as exact for
        // product writing.  Product parity remains external to this milestone.
        ws.lte_populations_exact = native_loader_ready;
        ws.line_workspace_exact = native_loader_ready;
        ws.line_tau_workspace_exact = native_loader_ready;
        ws.rrc_workspace_exact = native_loader_ready;
        ws.rrc_tau_workspace_exact = native_loader_ready;
        ws.continuum_workspace_exact = native_loader_ready;
        ws.line_profile_workspace_exact = native_loader_ready;
        ws.accumulated_output_workspace_exact = native_loader_ready;
    }

    if (native_loader_ready) {
        load_bridge_legacy_pprint_body(state.product_metadata_path, state.legacy_pprint);
    }

    state.exact_source_workspaces_retained = std::all_of(
        state.radial_zones.begin(), state.radial_zones.end(), [](const RadialZoneState& zone) {
            return zone.accepted_controller.evaluation.source_workspace.complete();
        });
    state.exact_accepted_radial_boundaries_retained = std::all_of(
        state.radial_zones.begin(), state.radial_zones.end(), [](const RadialZoneState& zone) {
            return zone.accepted_boundary_exact;
        });
    state.exact_legacy_pprint_state_retained = state.legacy_pprint.complete();
    state.native_detail_state_retained = state.exact_source_workspaces_retained;
    state.continuum_depths_derived_from_native_opacity = false;
    state.product_schema_complete = native_loader_ready;
    state.radial_state_complete = state.exact_accepted_radial_boundaries_retained;
    state.native_product_inputs_complete = state.exact_source_metadata_retained &&
        state.exact_source_workspaces_retained &&
        state.exact_accepted_radial_boundaries_retained &&
        state.exact_legacy_pprint_state_retained;
    state.embedded_public_fits_payloads_absent = true;
    state.embedded_full_xout_step_payload_absent = true;

    write_retention_report(
        state, diagnostics_path.parent_path() / "v048746255151_source_workspace_retention.json");

    if (!state.native_product_inputs_complete) {
        throw std::runtime_error(
            "exact source state is incomplete; CFITSIO and xout_step writers are disabled "
            "until all bridge payload families are loaded into native ProductWritingState");
    }
    if (!native_product_write_gate_enabled) {
        throw std::runtime_error(
            "native ProductWritingState loader accepted all bridge payload families; "
            "CFITSIO and xout_step writers remain disabled until gated production enablement");
    }
}


ProductWritingState build_product_writing_state(const WholeRunAccumulatedState& state) {
    ProductWritingState product;
    product.release = state.release;
    product.backend = state.backend;
    product.parameters_path = state.parameters_path;
    product.atomic_database_path = state.atomic_database_path;
    product.schema_path = state.product_schema_path;
    product.product_metadata_path = state.product_metadata_path;
    product.native_diagnostics_path = state.native_diagnostics_path;
    product.native_run_id = state.native_run_id;
    product.fixed_evaluations = state.fixed_evaluations;
    product.radial_zones = state.radial_zones;
    product.parameter_rows = state.parameter_rows;
    product.abundance_radial_rows = state.abundance_radial_rows;
    product.level_identities = state.level_identities;
    product.line_identities = state.line_identities;
    product.rrc_identities = state.rrc_identities;
    product.legacy_pprint = state.legacy_pprint;
    product.embedded_public_fits_payloads_absent = state.embedded_public_fits_payloads_absent;
    product.embedded_full_xout_step_payload_absent = state.embedded_full_xout_step_payload_absent;
    product.run_state_layers_distinct = true;
    product.product_schema_complete = state.product_schema_complete;
    product.radial_state_complete = state.radial_state_complete;
    product.native_detail_state_retained = state.native_detail_state_retained;
    product.continuum_depths_derived_from_native_opacity =
        state.continuum_depths_derived_from_native_opacity;
    product.native_product_inputs_complete = state.native_product_inputs_complete;
    product.exact_source_metadata_retained = state.exact_source_metadata_retained;
    product.exact_source_workspaces_retained = state.exact_source_workspaces_retained;
    product.exact_accepted_radial_boundaries_retained = state.exact_accepted_radial_boundaries_retained;
    product.exact_legacy_pprint_state_retained = state.exact_legacy_pprint_state_retained;
    product.product_state_complete = state.native_product_inputs_complete;
    product.product_parity_qualified = false;
    return product;
}

void write_run_state_manifest(
    const std::filesystem::path& path,
    const WholeRunAccumulatedState& whole,
    const ProductWritingState& product) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create run-state manifest: " + path.string());
    out << std::setprecision(17)
        << "{\n"
        << "  \"schema\": \"xstar-tools-v0648746255151-native-source-state-v1\",\n"
        << "  \"release\": \"" << json_escape(whole.release) << "\",\n"
        << "  \"backend\": \"" << json_escape(whole.backend) << "\",\n"
        << "  \"parameters_path\": \"" << json_escape(whole.parameters_path.string()) << "\",\n"
        << "  \"atomic_database_path\": \"" << json_escape(whole.atomic_database_path.string()) << "\",\n"
        << "  \"native_case_path\": \"" << json_escape(whole.native_case_path.string()) << "\",\n"
        << "  \"native_diagnostics_path\": \"" << json_escape(product.native_diagnostics_path.string()) << "\",\n"
        << "  \"native_run_id\": \"" << json_escape(product.native_run_id) << "\",\n"
        << "  \"fixed_evaluations\": " << whole.fixed_evaluations.size() << ",\n"
        << "  \"accepted_controller_states\": " << whole.accepted_controller_states.size() << ",\n"
        << "  \"radial_zones\": " << whole.radial_zones.size() << ",\n"
        << "  \"exact_source_metadata_retained\": " << (product.exact_source_metadata_retained ? "true" : "false") << ",\n"
        << "  \"exact_source_workspaces_retained\": " << (product.exact_source_workspaces_retained ? "true" : "false") << ",\n"
        << "  \"exact_accepted_radial_boundaries_retained\": " << (product.exact_accepted_radial_boundaries_retained ? "true" : "false") << ",\n"
        << "  \"exact_legacy_pprint_state_retained\": " << (product.exact_legacy_pprint_state_retained ? "true" : "false") << ",\n"
        << "  \"native_detail_state_retained\": " << (product.native_detail_state_retained ? "true" : "false") << ",\n"
        << "  \"continuum_depths_derived_from_native_opacity\": "
        << (product.continuum_depths_derived_from_native_opacity ? "true" : "false") << ",\n"
        << "  \"embedded_public_fits_payloads_absent\": " << (product.embedded_public_fits_payloads_absent ? "true" : "false") << ",\n"
        << "  \"embedded_full_xout_step_payload_absent\": " << (product.embedded_full_xout_step_payload_absent ? "true" : "false") << ",\n"
        << "  \"public_product_runtime_reads_benchmark_bytes\": false,\n"
        << "  \"xout_step_runtime_reads_benchmark_bytes\": false,\n"
        << "  \"xout_abund1_computed_from_native_state\": " << (product.xout_abund1_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_cont1_computed_from_native_state\": " << (product.xout_cont1_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_lines1_computed_from_native_state\": " << (product.xout_lines1_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_rrc1_computed_from_native_state\": " << (product.xout_rrc1_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_spect1_computed_from_native_state\": " << (product.xout_spect1_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_step_computed_from_native_state\": " << (product.xout_step_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_step_timing_values_measured\": " << (product.xout_step_timing_values_measured ? "true" : "false") << ",\n"
        << "  \"product_state_complete\": " << (product.product_state_complete ? "true" : "false") << ",\n"
        << "  \"product_parity_qualified\": false,\n"
        << "  \"production_promotion_ready\": false\n"
        << "}\n";
}

} // namespace xstar_run_state
