#include "xstar_xspec_initable_internal.hpp"

#include <cstdio>
#include <exception>
#include <filesystem>
#include <string>
#include <vector>

namespace {
void usage(const char *argv0) {
    std::fprintf(stderr,
        "Usage: %s [--output-dir DIR] key=value [key=value ...]\n"
        "Create canonical-compatible xstinitable.lis and xstinitable.fits.\n"
        "Arguments use the historical xstinitable/XPI parameter names.\n",
        argv0);
}
}

int main(int argc, char **argv) {
    std::filesystem::path output_dir = ".";
    std::vector<std::string> parameters;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--output-dir" && i + 1 < argc) output_dir = argv[++i];
        else if (arg == "--help" || arg == "-h") { usage(argv[0]); return 0; }
        else if (!arg.empty() && arg[0] == '-') { std::fprintf(stderr, "unknown option: %s\n", arg.c_str()); return 64; }
        else parameters.push_back(arg);
    }
    if (parameters.empty()) { usage(argv[0]); return 64; }
    try {
        const auto config = xstar_xspec_initable::parse_key_value_arguments(parameters);
        const auto result = xstar_xspec_initable::write_native_xstinitable(config, output_dir);
        std::printf("XSTAR_XSTINITABLE_0683_NINTPARM=%d\n", result.n_interpolated);
        std::printf("XSTAR_XSTINITABLE_0683_NADDPARM=%d\n", result.n_additive);
        std::printf("XSTAR_XSTINITABLE_0683_JOBS=%zu\n", result.job_count);
        std::printf("XSTAR_XSTINITABLE_0683_LOOPCONTROL_FIRST=1\n");
        std::printf("XSTAR_XSTINITABLE_0683_LOOPCONTROL_LAST=%zu\n", result.job_count);
        std::printf("XSTAR_XSTINITABLE_0683_RESULT=ACCEPT\n");
        return 0;
    } catch (const std::exception &exc) {
        std::fprintf(stderr, "xstar-xspec-initable: %s\n", exc.what());
        return 1;
    }
}
