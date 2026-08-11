#ifndef XSTAR_XSPEC_TABLE_H
#define XSTAR_XSPEC_TABLE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_XSPEC_TABLE_ABI_VERSION 1u

typedef struct xstar_xspec_spectrum_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    size_t bin_count;
    const float *energy_ev;
    const float *incident;
    const float *transmitted;
    const float *emit_inward;
    const float *emit_outward;
} xstar_xspec_spectrum_v1;

typedef struct xstar_xspec_slice_v1 {
    size_t first_bin;
    size_t bin_count;
} xstar_xspec_slice_v1;

/*
 * Read the legacy XSTAR_SPECTRA table using the historical TFLOAT data
 * contract.  The returned arrays are owned by the handle and remain valid
 * until xstar_xspec_spectrum_close_v1().
 */
typedef struct xstar_xspec_spectrum_handle_v1 xstar_xspec_spectrum_handle_v1;

int xstar_xspec_spectrum_open_v1(
    const char *path,
    xstar_xspec_spectrum_handle_v1 **handle,
    xstar_xspec_spectrum_v1 *view,
    char *message,
    size_t message_size);

void xstar_xspec_spectrum_close_v1(xstar_xspec_spectrum_handle_v1 *handle);

/* Historical SliceEnergySpectra semantics, made bounds-safe. */
int xstar_xspec_slice_energy_v1(
    const xstar_xspec_spectrum_v1 *spectrum,
    float elow_ev,
    float ehigh_ev,
    xstar_xspec_slice_v1 *slice,
    char *message,
    size_t message_size);

/* Historical xstar2table transformations.  Caller owns all output arrays. */
int xstar_xspec_transform_v1(
    const xstar_xspec_spectrum_v1 *spectrum,
    xstar_xspec_slice_v1 slice,
    float luminosity_1e38,
    float *ain,
    float *aout,
    float *mtable,
    float *etable,
    char *message,
    size_t message_size);

/* Read a named scalar from the PARAMETERS extension of xout_spect1.fits. */
int xstar_xspec_read_parameter_v1(
    const char *path,
    const char *name,
    float *value,
    char *message,
    size_t message_size);

#ifdef __cplusplus
}
#endif

#endif
