#include "xstar_run_state.hpp"

#include <fstream>
#include <iomanip>
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

} // namespace

ProductWritingState build_product_writing_state(const WholeRunAccumulatedState& state) {
    ProductWritingState product;
    product.release = state.release;
    product.backend = state.backend;
    product.parameters_path = state.parameters_path;
    product.atomic_database_path = state.atomic_database_path;
    product.radial_zones = state.radial_zones;
    product.run_state_layers_distinct = true;
    product.product_state_complete = state.radial_state_complete;
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
        << "  \"schema\": \"xstar-tools-v064874622-native-physical-run-state-v1\",\n"
        << "  \"release\": \"" << json_escape(whole.release) << "\",\n"
        << "  \"backend\": \"" << json_escape(whole.backend) << "\",\n"
        << "  \"parameters_path\": \"" << json_escape(whole.parameters_path.string()) << "\",\n"
        << "  \"atomic_database_path\": \"" << json_escape(whole.atomic_database_path.string()) << "\",\n"
        << "  \"native_case_path\": \"" << json_escape(whole.native_case_path.string()) << "\",\n"
        << "  \"source_trajectory_path\": \"" << json_escape(whole.source_trajectory_path.string()) << "\",\n"
        << "  \"layers\": {\n"
        << "    \"fixed_evaluation_state\": {\"count\": " << whole.fixed_evaluations.size() << "},\n"
        << "    \"accepted_controller_state\": {\"count\": " << whole.accepted_controller_states.size() << "},\n"
        << "    \"radial_zone_state\": {\"count\": " << whole.radial_zones.size()
        << ", \"complete\": " << (whole.radial_state_complete ? "true" : "false") << "},\n"
        << "    \"whole_run_accumulated_state\": {\"python_callbacks\": " << whole.python_callbacks
        << ", \"controller_trajectory_qualified\": " << (whole.controller_trajectory_qualified ? "true" : "false") << "},\n"
        << "    \"product_writing_state\": {\"count\": " << product.radial_zones.size()
        << ", \"complete\": " << (product.product_state_complete ? "true" : "false")
        << ", \"product_parity_qualified\": " << (product.product_parity_qualified ? "true" : "false") << "}\n"
        << "  },\n"
        << "  \"run_state_layers_distinct\": " << (product.run_state_layers_distinct ? "true" : "false") << ",\n"
        << "  \"product_level_parity\": \"NOT_CLAIMED\",\n"
        << "  \"production_promotion_ready\": false,\n"
        << "  \"result\": \"ACCEPT_INFRASTRUCTURE\"\n"
        << "}\n";
}

} // namespace xstar_run_state
