#ifndef XSTAR_XSPEC_INITABLE_INTERNAL_HPP
#define XSTAR_XSPEC_INITABLE_INTERNAL_HPP

#include <filesystem>
#include <string>
#include <utility>
#include <vector>

namespace xstar_xspec_initable {

enum class VariationType : int { constant = 0, additive = 1, interpolated = 2 };
enum class InterpolationMethod : int { linear = 0, logarithmic = 1 };

struct PhysicalParameter {
    std::string name;
    VariationType type = VariationType::constant;
    InterpolationMethod method = InterpolationMethod::linear;
    float initial = 0.0f;
    float delta = -1.0f;
    float hard_minimum = 0.0f;
    float soft_minimum = 0.0f;
    float soft_maximum = 0.0f;
    float hard_maximum = 0.0f;
    int number_of_values = 0;
    std::vector<float> values;
    int xstar_sequence_number = 0;
};

struct PlannerConfig {
    std::string spectrum_name = "pow";
    std::string spectrum_file = "spect.dat";
    int spectrum_units = 0;
    int redshift = 1;
    int nsteps = 3;
    int niter = 99;
    int lwrite = 0;
    int lprint = 0;
    int lstep = 0;
    int npass = 1;
    int lcpres = 0;
    std::string model_name = "template";
    std::string abundance_table = "xdef";
    float emult = 0.5f;
    float taumax = 5.0f;
    float xeemin = 0.1f;
    float critf = 1.0e-4f;
    float radexp = 0.0f;
    int ncn2 = 9999;
    float energy_low = 100.0f;
    float energy_high = 20000.0f;
    std::vector<PhysicalParameter> physical;
};

struct PlannerResult {
    std::filesystem::path lis_path;
    std::filesystem::path fits_path;
    int n_interpolated = 0;
    int n_additive = 0;
    std::size_t job_count = 0;
};

PlannerConfig parse_key_value_arguments(const std::vector<std::string> &arguments);
PlannerResult write_native_xstinitable(const PlannerConfig &config, const std::filesystem::path &output_dir);

}  // namespace xstar_xspec_initable

#endif
