#include "xstar_xspec_table_internal.hpp"

#include <cstdio>
#include <exception>
#include <string>
#include <vector>

namespace {
void usage(const char *argv0) {
    std::fprintf(stderr,
        "Usage:\n"
        "  %s --initable xstinitable.fits --output-dir DIR xout_spect1_1.fits [xout_spect1_2.fits ...]\n"
        "  %s --metadata CONFIG --output-dir DIR xout_spect1_1.fits [xout_spect1_2.fits ...]\n"
        "Build canonical-compatible xout_ain/aout/mtable/etable FITS tables from ordinary XSTAR spectra.\n",
        argv0, argv0);
}
}

int main(int argc, char **argv) {
    std::string metadata;
    std::string initable;
    std::string output_dir;
    std::vector<std::string> spectra;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--metadata" && i + 1 < argc) metadata = argv[++i];
        else if (arg == "--initable" && i + 1 < argc) initable = argv[++i];
        else if (arg == "--output-dir" && i + 1 < argc) output_dir = argv[++i];
        else if (arg == "--help" || arg == "-h") { usage(argv[0]); return 0; }
        else if (!arg.empty() && arg[0] == '-') { std::fprintf(stderr, "unknown option: %s\n", arg.c_str()); return 64; }
        else spectra.push_back(arg);
    }
    if ((metadata.empty() == initable.empty()) || output_dir.empty() || spectra.empty()) { usage(argv[0]); return 64; }
    try {
        const auto config = !initable.empty() ? xstar_xspec::parse_initable_fits(initable) : xstar_xspec::parse_config(metadata);
        xstar_xspec::build_tables(config, spectra, output_dir);
        std::printf("XSTAR_XSPEC_TABLE_0681_RESULT=ACCEPT\n");
        std::printf("XSTAR_XSPEC_TABLE_0681_SPECTRA=%zu\n", spectra.size());
        return 0;
    } catch (const std::exception &exc) {
        std::fprintf(stderr, "xstar-xspec-table: %s\n", exc.what());
        return 1;
    }
}
