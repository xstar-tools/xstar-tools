#include "xstar_xspec_table.h"

#include <fitsio.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

struct xstar_xspec_spectrum_handle_v1 {
    std::vector<float> energy;
    std::vector<float> incident;
    std::vector<float> transmitted;
    std::vector<float> emit_inward;
    std::vector<float> emit_outward;
};

namespace {

void set_message(char *message, size_t message_size, const std::string &text) {
    if (message == nullptr || message_size == 0) {
        return;
    }
    std::snprintf(message, message_size, "%s", text.c_str());
}

std::string fits_error(int status) {
    char text[FLEN_STATUS] = {0};
    fits_get_errstatus(status, text);
    return std::string(text);
}

void require_view(const xstar_xspec_spectrum_v1 *spectrum) {
    if (spectrum == nullptr || spectrum->struct_size < sizeof(*spectrum) ||
        spectrum->abi_version != XSTAR_XSPEC_TABLE_ABI_VERSION ||
        spectrum->bin_count < 2 || spectrum->energy_ev == nullptr ||
        spectrum->incident == nullptr || spectrum->transmitted == nullptr ||
        spectrum->emit_inward == nullptr || spectrum->emit_outward == nullptr) {
        throw std::runtime_error("invalid xstar_xspec_spectrum_v1");
    }
}

void read_float_column(fitsfile *fptr, const char *name, long nrows, std::vector<float> &out) {
    int status = 0;
    int colnum = 0;
    int anynull = 0;
    float null_value = 0.0f;
    if (fits_get_colnum(fptr, CASEINSEN, const_cast<char *>(name), &colnum, &status)) {
        throw std::runtime_error(std::string("missing FITS column ") + name + ": " + fits_error(status));
    }
    out.assign(static_cast<size_t>(nrows), 0.0f);
    status = 0;
    if (fits_read_col(fptr, TFLOAT, colnum, 1, 1, nrows, &null_value, out.data(), &anynull, &status)) {
        throw std::runtime_error(std::string("cannot read FITS column ") + name + ": " + fits_error(status));
    }
}

}  // namespace

extern "C" int xstar_xspec_spectrum_open_v1(
    const char *path,
    xstar_xspec_spectrum_handle_v1 **handle,
    xstar_xspec_spectrum_v1 *view,
    char *message,
    size_t message_size) {
    if (handle == nullptr || view == nullptr || path == nullptr) {
        set_message(message, message_size, "null argument");
        return 1;
    }
    *handle = nullptr;
    fitsfile *fptr = nullptr;
    int status = 0;
    try {
        if (fits_open_file(&fptr, path, READONLY, &status)) {
            throw std::runtime_error("cannot open spectrum FITS: " + fits_error(status));
        }
        status = 0;
        if (fits_movnam_hdu(fptr, ASCII_TBL, const_cast<char *>("XSTAR_SPECTRA"), 0, &status)) {
            status = 0;
            if (fits_movnam_hdu(fptr, BINARY_TBL, const_cast<char *>("XSTAR_SPECTRA"), 0, &status)) {
                throw std::runtime_error("missing XSTAR_SPECTRA extension: " + fits_error(status));
            }
        }
        long nrows = 0;
        status = 0;
        if (fits_get_num_rows(fptr, &nrows, &status) || nrows < 2) {
            throw std::runtime_error("invalid XSTAR_SPECTRA row count");
        }
        auto owned = std::make_unique<xstar_xspec_spectrum_handle_v1>();
        read_float_column(fptr, "energy", nrows, owned->energy);
        read_float_column(fptr, "incident", nrows, owned->incident);
        read_float_column(fptr, "transmitted", nrows, owned->transmitted);
        read_float_column(fptr, "emit_inward", nrows, owned->emit_inward);
        read_float_column(fptr, "emit_outward", nrows, owned->emit_outward);
        for (long i = 1; i < nrows; ++i) {
            if (!(owned->energy[static_cast<size_t>(i)] > owned->energy[static_cast<size_t>(i - 1)])) {
                throw std::runtime_error("XSTAR_SPECTRA energy grid is not strictly increasing");
            }
        }
        status = 0;
        fits_close_file(fptr, &status);
        fptr = nullptr;

        view->struct_size = sizeof(*view);
        view->abi_version = XSTAR_XSPEC_TABLE_ABI_VERSION;
        view->bin_count = owned->energy.size();
        view->energy_ev = owned->energy.data();
        view->incident = owned->incident.data();
        view->transmitted = owned->transmitted.data();
        view->emit_inward = owned->emit_inward.data();
        view->emit_outward = owned->emit_outward.data();
        *handle = owned.release();
        set_message(message, message_size, "ACCEPT");
        return 0;
    } catch (const std::exception &exc) {
        if (fptr != nullptr) {
            int close_status = 0;
            fits_close_file(fptr, &close_status);
        }
        set_message(message, message_size, exc.what());
        return 1;
    }
}

extern "C" void xstar_xspec_spectrum_close_v1(xstar_xspec_spectrum_handle_v1 *handle) {
    delete handle;
}

extern "C" int xstar_xspec_slice_energy_v1(
    const xstar_xspec_spectrum_v1 *spectrum,
    float elow_ev,
    float ehigh_ev,
    xstar_xspec_slice_v1 *slice,
    char *message,
    size_t message_size) {
    try {
        require_view(spectrum);
        if (slice == nullptr) {
            throw std::runtime_error("null slice output");
        }
        if (ehigh_ev < elow_ev) {
            throw std::runtime_error("EHIGH must be greater than or equal to ELOW");
        }
        const size_t n = spectrum->bin_count;
        const float first = spectrum->energy_ev[0];
        const float last = spectrum->energy_ev[n - 1];
        if (elow_ev < first || elow_ev > last) {
            elow_ev = first;
        }
        if (ehigh_ev < first || ehigh_ev > last) {
            ehigh_ev = last;
        }

        /*
         * Bounds-safe transcription of SliceEnergySpectra from
         * xstar/src/xstar2table/xstar2table.c.  The low boundary includes
         * the bin straddling ELOW.  Historical SliceEnergySpectra reports
         * eBinHigh as an energy-edge index while nEnergyBins counts intervals;
         * therefore the selected interval count is high-low, not an inclusive
         * high-low+1 count.  When EHIGH reaches the final grid value, the last
         * usable edge index is n-2.
         */
        size_t low = 0;
        bool low_set = false;
        for (size_t j = 1; j < n; ++j) {
            if (spectrum->energy_ev[j] >= elow_ev && spectrum->energy_ev[j] <= ehigh_ev &&
                spectrum->energy_ev[j - 1] < elow_ev) {
                low = j - 1;
                low_set = true;
                break;
            }
        }
        if (!low_set) {
            if (elow_ev <= first) {
                low = 0;
            } else {
                auto it = std::upper_bound(spectrum->energy_ev, spectrum->energy_ev + n, elow_ev);
                size_t j = static_cast<size_t>(it - spectrum->energy_ev);
                low = (j == 0 ? 0 : j - 1);
                if (low >= n - 1) low = n - 2;
            }
        }

        size_t high = low;
        bool high_set = false;
        for (size_t j = 1; j + 1 < n; ++j) {
            if (spectrum->energy_ev[j] >= elow_ev && spectrum->energy_ev[j] <= ehigh_ev &&
                spectrum->energy_ev[j + 1] > ehigh_ev) {
                high = (j == 0 ? 0 : j - 1);
                high_set = true;
                break;
            }
        }
        if (!high_set) {
            if (ehigh_ev >= last) {
                high = n - 2;
            } else {
                auto it = std::upper_bound(spectrum->energy_ev, spectrum->energy_ev + n, ehigh_ev);
                size_t j = static_cast<size_t>(it - spectrum->energy_ev);
                high = (j >= 2 ? j - 2 : 0);
            }
        }
        if (high < low) {
            throw std::runtime_error("energy range selects no complete XSTAR table bins");
        }
        slice->first_bin = low;
        slice->bin_count = high - low;
        set_message(message, message_size, "ACCEPT");
        return 0;
    } catch (const std::exception &exc) {
        set_message(message, message_size, exc.what());
        return 1;
    }
}

extern "C" int xstar_xspec_transform_v1(
    const xstar_xspec_spectrum_v1 *spectrum,
    xstar_xspec_slice_v1 slice,
    float luminosity_1e38,
    float *ain,
    float *aout,
    float *mtable,
    float *etable,
    char *message,
    size_t message_size) {
    try {
        require_view(spectrum);
        if (luminosity_1e38 <= 0.0f) {
            throw std::runtime_error("rlrad38/luminosity must be positive");
        }
        if (slice.bin_count == 0 || slice.first_bin + slice.bin_count >= spectrum->bin_count) {
            throw std::runtime_error("invalid energy slice");
        }
        if (ain == nullptr || aout == nullptr || mtable == nullptr || etable == nullptr) {
            throw std::runtime_error("null transform output buffer");
        }
        constexpr double kLegacyNormalization = 8.356e-7;
        for (size_t k = 0; k < slice.bin_count; ++k) {
            const size_t i = slice.first_bin + k;
            const float energy = spectrum->energy_ev[i];
            const float delta = spectrum->energy_ev[i + 1] - energy;
            const float enorm = static_cast<float>(kLegacyNormalization * delta / (luminosity_1e38 * energy));
            ain[k] = enorm * spectrum->emit_inward[i];
            aout[k] = enorm * spectrum->emit_outward[i];
            if (spectrum->incident[i] == 0.0f) {
                mtable[k] = 0.0f;
            } else {
                mtable[k] = spectrum->transmitted[i] / spectrum->incident[i];
            }
            float transmission = mtable[k];
            if (transmission < 1.0e-32f) {
                transmission = 1.0e-32f;
            }
            etable[k] = static_cast<float>(-std::log(static_cast<double>(transmission)));
        }
        set_message(message, message_size, "ACCEPT");
        return 0;
    } catch (const std::exception &exc) {
        set_message(message, message_size, exc.what());
        return 1;
    }
}

extern "C" int xstar_xspec_read_parameter_v1(
    const char *path,
    const char *name,
    float *value,
    char *message,
    size_t message_size) {
    if (path == nullptr || name == nullptr || value == nullptr) {
        set_message(message, message_size, "null argument");
        return 1;
    }
    fitsfile *fptr = nullptr;
    int status = 0;
    try {
        if (fits_open_file(&fptr, path, READONLY, &status)) {
            throw std::runtime_error("cannot open spectrum FITS: " + fits_error(status));
        }
        status = 0;
        int hdutype = 0;
        if (fits_movnam_hdu(fptr, ANY_HDU, const_cast<char *>("PARAMETERS"), 0, &status)) {
            throw std::runtime_error("missing PARAMETERS extension: " + fits_error(status));
        }
        fits_get_hdu_type(fptr, &hdutype, &status);
        int name_col = 0;
        int value_col = 0;
        status = 0;
        if (fits_get_colnum(fptr, CASEINSEN, const_cast<char *>("parameter"), &name_col, &status)) {
            status = 0;
            if (fits_get_colnum(fptr, CASEINSEN, const_cast<char *>("name"), &name_col, &status)) {
                throw std::runtime_error("PARAMETERS has no parameter/name column");
            }
        }
        status = 0;
        if (fits_get_colnum(fptr, CASEINSEN, const_cast<char *>("value"), &value_col, &status)) {
            throw std::runtime_error("PARAMETERS has no value column");
        }
        long nrows = 0;
        status = 0;
        fits_get_num_rows(fptr, &nrows, &status);
        for (long row = 1; row <= nrows; ++row) {
            char storage[FLEN_VALUE] = {0};
            char *ptr = storage;
            char null_string[] = "";
            int anynull = 0;
            status = 0;
            if (fits_read_col(fptr, TSTRING, name_col, row, 1, 1, null_string, &ptr, &anynull, &status)) {
                throw std::runtime_error("cannot read PARAMETERS name column");
            }
            std::string got(storage);
            while (!got.empty() && got.back() == ' ') got.pop_back();
            if (got == name) {
                float null_value = 0.0f;
                status = 0;
                if (fits_read_col(fptr, TFLOAT, value_col, row, 1, 1, &null_value, value, &anynull, &status)) {
                    throw std::runtime_error("cannot read PARAMETERS value column");
                }
                status = 0;
                fits_close_file(fptr, &status);
                fptr = nullptr;
                set_message(message, message_size, "ACCEPT");
                return 0;
            }
        }
        throw std::runtime_error(std::string("parameter not found: ") + name);
    } catch (const std::exception &exc) {
        if (fptr != nullptr) {
            int close_status = 0;
            fits_close_file(fptr, &close_status);
        }
        set_message(message, message_size, exc.what());
        return 1;
    }
}
