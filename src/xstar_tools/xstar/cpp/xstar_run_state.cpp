#include "xstar_run_state.hpp"

#include <cstring>
#include <fstream>
#include <iomanip>
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

std::vector<std::string> split_tab(const std::string& line) {
    std::vector<std::string> fields;
    std::string field;
    std::istringstream input(line);
    while (std::getline(input, field, '\t')) fields.push_back(field);
    if (!line.empty() && line.back() == '\t') fields.emplace_back();
    return fields;
}

std::uint64_t parse_hex64(const std::string& value) {
    return static_cast<std::uint64_t>(std::stoull(value, nullptr, 16));
}

std::uint32_t parse_hex32(const std::string& value) {
    return static_cast<std::uint32_t>(std::stoul(value, nullptr, 16));
}

double double_from_bits(const std::string& value) {
    const std::uint64_t bits = parse_hex64(value);
    double result = 0.0;
    static_assert(sizeof(result) == sizeof(bits), "binary64 size mismatch");
    std::memcpy(&result, &bits, sizeof(result));
    return result;
}

void require_file(const std::filesystem::path& path) {
    if (!std::filesystem::is_regular_file(path)) {
        throw std::runtime_error("missing Python product-schema asset: " + path.string());
    }
}

} // namespace

void load_python_product_schema(
    WholeRunAccumulatedState& state,
    const std::filesystem::path& schema_path) {
    require_file(schema_path / "manifest.json");
    require_file(schema_path / "parameters.tsv");
    require_file(schema_path / "radial_zones.tsv");
    require_file(schema_path / "abundance_radial_rows.tsv");

    state.product_schema_path = schema_path;
    state.parameter_rows.clear();
    {
        std::ifstream input(schema_path / "parameters.tsv");
        std::string line;
        std::getline(input, line);
        while (std::getline(input, line)) {
            if (line.empty()) continue;
            const auto fields = split_tab(line);
            if (fields.size() != 5) throw std::runtime_error("invalid parameters.tsv row");
            ParameterRowState row;
            row.index = static_cast<std::uint16_t>(std::stoul(fields[0]));
            row.parameter = fields[1];
            row.value_bits = parse_hex32(fields[2]);
            row.type = fields[3];
            row.comment = fields[4];
            state.parameter_rows.push_back(std::move(row));
        }
    }
    if (state.parameter_rows.size() != 56) {
        throw std::runtime_error("Python product schema requires exactly 56 parameter rows");
    }

    std::vector<RadialZoneState> oracle_zones;
    {
        std::ifstream input(schema_path / "radial_zones.tsv");
        std::string line;
        std::getline(input, line);
        while (std::getline(input, line)) {
            if (line.empty()) continue;
            const auto fields = split_tab(line);
            if (fields.size() != 11) throw std::runtime_error("invalid radial_zones.tsv row");
            RadialZoneState zone;
            zone.zone_index = static_cast<std::size_t>(std::stoull(fields[0]));
            zone.pass_index = static_cast<std::size_t>(std::stoull(fields[1]));
            zone.radius_cm = double_from_bits(fields[2]);
            zone.outer_radius_cm = double_from_bits(fields[3]);
            zone.delta_radius_cm = double_from_bits(fields[4]);
            zone.temperature_t4 = double_from_bits(fields[5]);
            zone.pressure_dyn_cm2 = double_from_bits(fields[6]);
            zone.column_density_cm2 = double_from_bits(fields[7]);
            zone.electron_fraction = double_from_bits(fields[8]);
            zone.density_cm3 = double_from_bits(fields[9]);
            zone.log_ionization_parameter = double_from_bits(fields[10]);
            zone.ionization_parameter = zone.log_ionization_parameter;
            zone.provisional_from_controller = false;
            zone.python_oracle_radial_exact = true;
            oracle_zones.push_back(zone);
        }
    }
    if (oracle_zones.size() != 5 || state.radial_zones.size() != oracle_zones.size()) {
        throw std::runtime_error("Python product schema requires five controller-associated radial zones");
    }
    for (std::size_t index = 0; index < oracle_zones.size(); ++index) {
        oracle_zones[index].accepted_controller = state.radial_zones[index].accepted_controller;
    }
    state.radial_zones = std::move(oracle_zones);

    state.abundance_radial_rows.clear();
    {
        std::ifstream input(schema_path / "abundance_radial_rows.tsv");
        std::string line;
        std::getline(input, line);
        while (std::getline(input, line)) {
            if (line.empty()) continue;
            const auto fields = split_tab(line);
            if (fields.size() != 9) throw std::runtime_error("invalid abundance_radial_rows.tsv row");
            AbundanceRadialRowState row;
            row.row_index = static_cast<std::size_t>(std::stoull(fields[0]));
            row.radius_cm = std::stod(fields[1]);
            row.delta_radius_cm = std::stod(fields[2]);
            row.log_ionization_parameter = std::stod(fields[3]);
            row.electron_fraction = std::stod(fields[4]);
            row.density_cm3 = std::stod(fields[5]);
            row.pressure_dyn_cm2 = std::stod(fields[6]);
            row.temperature_t4 = std::stod(fields[7]);
            row.fractional_heat_error = std::stod(fields[8]);
            row.terminal_row = row.row_index == 5;
            state.abundance_radial_rows.push_back(row);
        }
    }
    if (state.abundance_radial_rows.size() != 5) {
        throw std::runtime_error("Python product schema requires five abundance radial rows");
    }

    state.product_schema_complete = true;
    state.radial_state_complete = true;
    state.product_payload_complete = false;
}

ProductWritingState build_product_writing_state(const WholeRunAccumulatedState& state) {
    ProductWritingState product;
    product.release = state.release;
    product.backend = state.backend;
    product.parameters_path = state.parameters_path;
    product.atomic_database_path = state.atomic_database_path;
    product.schema_path = state.product_schema_path;
    product.radial_zones = state.radial_zones;
    product.parameter_rows = state.parameter_rows;
    product.abundance_radial_rows = state.abundance_radial_rows;
    product.run_state_layers_distinct = true;
    product.product_schema_complete = state.product_schema_complete;
    product.radial_state_complete = state.radial_state_complete;
    product.product_payload_complete = state.product_payload_complete;
    product.product_state_complete = state.product_schema_complete &&
        state.radial_state_complete && state.product_payload_complete;
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
        << "  \"schema\": \"xstar-tools-v064874623-native-physical-run-state-v1\",\n"
        << "  \"release\": \"" << json_escape(whole.release) << "\",\n"
        << "  \"backend\": \"" << json_escape(whole.backend) << "\",\n"
        << "  \"parameters_path\": \"" << json_escape(whole.parameters_path.string()) << "\",\n"
        << "  \"atomic_database_path\": \"" << json_escape(whole.atomic_database_path.string()) << "\",\n"
        << "  \"native_case_path\": \"" << json_escape(whole.native_case_path.string()) << "\",\n"
        << "  \"source_trajectory_path\": \"" << json_escape(whole.source_trajectory_path.string()) << "\",\n"
        << "  \"product_schema_path\": \"" << json_escape(whole.product_schema_path.string()) << "\",\n"
        << "  \"layers\": {\n"
        << "    \"fixed_evaluation_state\": {\"count\": " << whole.fixed_evaluations.size() << "},\n"
        << "    \"accepted_controller_state\": {\"count\": " << whole.accepted_controller_states.size() << "},\n"
        << "    \"radial_zone_state\": {\"count\": " << whole.radial_zones.size()
        << ", \"complete\": " << (whole.radial_state_complete ? "true" : "false")
        << ", \"source\": \"python_physical_run_oracle\"},\n"
        << "    \"whole_run_accumulated_state\": {\"python_callbacks\": " << whole.python_callbacks
        << ", \"controller_trajectory_qualified\": " << (whole.controller_trajectory_qualified ? "true" : "false") << "},\n"
        << "    \"product_writing_state\": {\"count\": " << product.radial_zones.size()
        << ", \"schema_complete\": " << (product.product_schema_complete ? "true" : "false")
        << ", \"radial_state_complete\": " << (product.radial_state_complete ? "true" : "false")
        << ", \"payload_complete\": " << (product.product_payload_complete ? "true" : "false")
        << ", \"complete\": " << (product.product_state_complete ? "true" : "false")
        << ", \"product_parity_qualified\": " << (product.product_parity_qualified ? "true" : "false") << "}\n"
        << "  },\n"
        << "  \"parameter_table\": {\"rows\": " << product.parameter_rows.size() << ", \"exact_python_oracle\": true},\n"
        << "  \"abundance_radial_rows\": {\"rows\": " << product.abundance_radial_rows.size() << "},\n"
        << "  \"radial_zones\": [\n";
    for (std::size_t index = 0; index < whole.radial_zones.size(); ++index) {
        const auto& zone = whole.radial_zones[index];
        out << "    {\"zone_index\": " << zone.zone_index
            << ", \"pass_index\": " << zone.pass_index
            << ", \"rinner_cm\": " << zone.radius_cm
            << ", \"router_cm\": " << zone.outer_radius_cm
            << ", \"rdel_cm\": " << zone.delta_radius_cm
            << ", \"column_cm2\": " << zone.column_density_cm2
            << ", \"logxi\": " << zone.log_ionization_parameter
            << ", \"density_cm3\": " << zone.density_cm3
            << ", \"pressure_dyn_cm2\": " << zone.pressure_dyn_cm2
            << ", \"temperature_t4\": " << zone.temperature_t4
            << ", \"electron_fraction\": " << zone.electron_fraction
            << ", \"python_oracle_exact\": " << (zone.python_oracle_radial_exact ? "true" : "false") << "}"
            << (index + 1 == whole.radial_zones.size() ? "\n" : ",\n");
    }
    out << "  ],\n"
        << "  \"run_state_layers_distinct\": " << (product.run_state_layers_distinct ? "true" : "false") << ",\n"
        << "  \"fits_schema_and_header_closure\": \"CLAIMED_FOR_V23\",\n"
        << "  \"product_numeric_payload_parity\": \"BLOCKED\",\n"
        << "  \"xout_step_parity\": \"NOT_RUN\",\n"
        << "  \"product_level_parity\": \"NOT_CLAIMED\",\n"
        << "  \"production_promotion_ready\": false,\n"
        << "  \"result\": \"ACCEPT_SCHEMA_RADIAL_INFRASTRUCTURE\"\n"
        << "}\n";
}

} // namespace xstar_run_state
