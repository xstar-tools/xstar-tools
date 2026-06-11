#ifndef XSTAR_SCIENCE_FITS_HPP
#define XSTAR_SCIENCE_FITS_HPP

#include <array>
#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

namespace xstar_science_fits {

struct Snapshot {
    double temperature_t4 = 0.0;
    double electron_fraction_input = 0.0;
    double computed_electron_fraction = 0.0;
    double charge_residual = 0.0;
    double hmctot = 0.0;
    double total_heating = 0.0;
    double total_cooling = 0.0;
    double element_heating = 0.0;
    double element_cooling = 0.0;
    double continuum_heating = 0.0;
    double continuum_cooling = 0.0;
    std::vector<double> populations;
    std::vector<double> continuum_spectrum;
    std::vector<double> spectrum;
    std::vector<double> opacity;
};

struct Result {
    std::size_t files_written = 0;
    bool schema_complete = false;
    bool computed_from_native_state = false;
    bool continuum_and_spectrum_paths_separate = false;
    bool physical_equivalence_qualified = false;
    std::vector<std::string> filenames;
};

Result write_historical_science_products(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    const std::vector<Snapshot>& radial_snapshots,
    const std::array<double,64>& native_energy_ev);

} // namespace xstar_science_fits

#endif
