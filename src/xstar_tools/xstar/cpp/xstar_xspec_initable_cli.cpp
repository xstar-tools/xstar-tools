#include "xstar_xspec_initable_internal.hpp"

#include <cstdio>
#include <exception>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void usage(const char *argv0) {
    std::fprintf(stderr,
        "Usage:\n"
        "  %s [--xstar cpp|fortran] [--input xstinitable.par] [--data-dir DIR] [--output-dir DIR] [key=value ...]\n"
        "  %s [--xstar cpp|fortran] [--output-dir DIR] key=value [key=value ...]\n\n"
        "Create xstinitable.lis and xstinitable.fits.\n"
        "The generated xstinitable.lis targets xstar-cpp by default.\n"
        "Use --xstar fortran to reproduce the canonical Fortran `xstar key=value` contract.\n\n"
        "Options:\n"
        "  --xstar TARGET        cpp (default) or fortran; alias: -xstar\n"
        "  --input PATH          HEASoft/IRAF-style xstinitable.par file\n"
        "  --data-dir DIR       xstar-cpp atomic-data directory emitted into native .lis lines\n"
        "                       alias accepted for compatibility: -data-dir\n"
        "  --output-dir DIR     directory for xstinitable.lis and xstinitable.fits\n"
        "  --help, -h           show this help\n\n"
        "Trailing key=value arguments override values loaded from --input.\n",
        argv0, argv0);
}

std::string trim(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1u);
}

std::vector<std::string> parse_csv_row(const std::string &line) {
    std::vector<std::string> fields;
    std::string current;
    bool quoted = false;
    for (std::size_t i = 0; i < line.size(); ++i) {
        const char c = line[i];
        if (quoted) {
            if (c == '"') {
                if (i + 1 < line.size() && line[i + 1] == '"') {
                    current.push_back('"');
                    ++i;
                } else {
                    quoted = false;
                }
            } else {
                current.push_back(c);
            }
        } else if (c == '"') {
            quoted = true;
        } else if (c == ',') {
            fields.push_back(current);
            current.clear();
        } else {
            current.push_back(c);
        }
    }
    if (quoted) throw std::runtime_error("unterminated quoted field in .par file");
    fields.push_back(current);
    return fields;
}

std::vector<std::string> load_par_file(const std::filesystem::path &path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("could not read parameter file: " + path.string());
    std::vector<std::string> parameters;
    std::string line;
    std::size_t lineno = 0;
    while (std::getline(in, line)) {
        ++lineno;
        const std::string stripped = trim(line);
        if (stripped.empty() || stripped[0] == '#') continue;
        const auto fields = parse_csv_row(line);
        if (fields.size() >= 4u) {
            const std::string key = trim(fields[0]);
            const std::string value = trim(fields[3]);
            if (!key.empty()) parameters.push_back(key + "=" + value);
        } else if (fields.size() == 1u) {
            const auto pos = fields[0].find('=');
            if (pos == std::string::npos || pos == 0u) {
                throw std::runtime_error("unsupported parameter row " + std::to_string(lineno) + " in " + path.string());
            }
            parameters.push_back(trim(fields[0].substr(0, pos)) + "=" + trim(fields[0].substr(pos + 1u)));
        } else {
            throw std::runtime_error("unsupported parameter row " + std::to_string(lineno) + " in " + path.string());
        }
    }
    if (parameters.empty()) throw std::runtime_error("no xstinitable parameters found in " + path.string());
    return parameters;
}

xstar_xspec_initable::XStarCommandTarget parse_target(const std::string &value) {
    if (value == "cpp") return xstar_xspec_initable::XStarCommandTarget::cpp;
    if (value == "fortran") return xstar_xspec_initable::XStarCommandTarget::fortran;
    throw std::runtime_error("--xstar must be 'cpp' or 'fortran'");
}

}  // namespace

int main(int argc, char **argv) {
    std::filesystem::path output_dir = ".";
    std::filesystem::path input_file;
    std::filesystem::path data_dir;
    auto target = xstar_xspec_initable::XStarCommandTarget::cpp;
    std::vector<std::string> overrides;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        auto require_value = [&](const char *name) -> std::string {
            if (i + 1 >= argc) throw std::runtime_error(std::string("missing value for ") + name);
            return argv[++i];
        };
        try {
            if (arg == "--output-dir") output_dir = require_value("--output-dir");
            else if (arg == "--input") input_file = require_value("--input");
            else if (arg == "--data-dir" || arg == "-data-dir") data_dir = require_value(arg.c_str());
            else if (arg == "--xstar" || arg == "-xstar") target = parse_target(require_value(arg.c_str()));
            else if (arg == "--help" || arg == "-h") { usage(argv[0]); return 0; }
            else if (!arg.empty() && arg[0] == '-') throw std::runtime_error("unknown option: " + arg);
            else overrides.push_back(arg);
        } catch (const std::exception &exc) {
            std::fprintf(stderr, "xstar-xspec-initable: %s\n", exc.what());
            usage(argv[0]);
            return 64;
        }
    }

    try {
        std::vector<std::string> parameters;
        if (!input_file.empty()) parameters = load_par_file(input_file);
        parameters.insert(parameters.end(), overrides.begin(), overrides.end());
        if (parameters.empty()) {
            usage(argv[0]);
            return 64;
        }

        auto config = xstar_xspec_initable::parse_key_value_arguments(parameters);
        config.xstar_target = target;
        config.data_dir = data_dir;
        const auto result = xstar_xspec_initable::write_native_xstinitable(config, output_dir);
        std::printf("XSTAR_XSTINITABLE_06831_XSTAR=%s\n", target == xstar_xspec_initable::XStarCommandTarget::cpp ? "CPP" : "FORTRAN");
        std::printf("XSTAR_XSTINITABLE_06831_NINTPARM=%d\n", result.n_interpolated);
        std::printf("XSTAR_XSTINITABLE_06831_NADDPARM=%d\n", result.n_additive);
        std::printf("XSTAR_XSTINITABLE_06831_JOBS=%zu\n", result.job_count);
        std::printf("XSTAR_XSTINITABLE_06831_LOOPCONTROL_FIRST=1\n");
        std::printf("XSTAR_XSTINITABLE_06831_LOOPCONTROL_LAST=%zu\n", result.job_count);
        std::printf("XSTAR_XSTINITABLE_06831_RESULT=ACCEPT\n");
        return 0;
    } catch (const std::exception &exc) {
        std::fprintf(stderr, "xstar-xspec-initable: %s\n", exc.what());
        return 1;
    }
}
