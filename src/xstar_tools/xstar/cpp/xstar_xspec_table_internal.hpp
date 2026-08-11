#ifndef XSTAR_XSPEC_TABLE_INTERNAL_HPP
#define XSTAR_XSPEC_TABLE_INTERNAL_HPP

#include <cstddef>
#include <string>
#include <utility>
#include <vector>

namespace xstar_xspec {

enum class ParameterKind { interpolated, additive };

struct Parameter {
    ParameterKind kind = ParameterKind::interpolated;
    std::string name;
    int method = 0;
    float initial = 0.0f;
    float delta = -1.0f;
    float hard_min = 0.0f;
    float soft_min = 0.0f;
    float soft_max = 0.0f;
    float hard_max = 0.0f;
    std::vector<float> values;
};

struct Config {
    std::string model_name = "XSTAR table";
    std::string spectrum_name = "pow";
    std::string spectrum_file = "spct.dat";
    std::string abundance_table = "xdef";
    int spectrum_units = 0;
    int redshift = 1;
    float elow_ev = 100.0f;
    float ehigh_ev = 20000.0f;
    int nsteps = 3;
    int niter = 0;
    int write_switch = -1;
    int print_switch = -1;
    int step_size = 0;
    int npass = 1;
    int pressure_switch = 0;
    float emult = 0.5f;
    float taumax = 5.0f;
    float xeemin = 0.1f;
    float critf = 1.0e-7f;
    float radexp = 0.0f;
    int ncn2 = 9999;
    std::vector<Parameter> parameters;
    std::vector<std::pair<std::string, float>> constants;
};

Config parse_config(const std::string &path);
void build_tables(const Config &config, const std::vector<std::string> &spectra, const std::string &output_dir);

}  // namespace xstar_xspec

#endif
