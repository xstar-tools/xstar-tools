// Optional XSTAR emissivity/output kernels.
//
// v0.6.0a19 starts libxstar_emissivity.so as a plain C ABI shared library.
// The first production kernel owns the binemis strong-line profile loop that
// dominated final_product_build after the Mg rate_type=7 matrix accumulator
// moved the rate-construction hot path to C++.

#include <cmath>
#include <cstddef>
#include <cstring>
#include <algorithm>
#include <limits>

namespace {

inline double source_real_literal(double value) {
    return static_cast<double>(static_cast<float>(value));
}

void write_message(char* errbuf, std::size_t errbuf_size, const char* message) {
    if (!errbuf || errbuf_size == 0) return;
    std::strncpy(errbuf, message ? message : "", errbuf_size - 1);
    errbuf[errbuf_size - 1] = '\0';
}

static inline double voigte_cpp(double vs, double a) {
    static const double ak[19] = {
        -1.12470432, -0.15516677, 3.28867591, -2.34357915, 0.42139162,
        -4.48480194, 9.39456063, -6.61487486, 1.98919585, -0.22041650,
        0.554153432, 0.278711796, -0.188325687, 0.042991293,
        -0.003278278, 0.979895023, -0.962846325, 0.532770573,
        -0.122727278
    };
    const double sqp = 1.772453851;
    const double sq2 = 1.414213562;
    const double v = std::fabs(vs);
    const double aa = a;
    const double u = aa + v;
    const double v2 = v * v;
    if (aa == 0.0) return (v2 >= 100.0) ? 0.0 : std::exp(-v2);
    if (aa <= 0.2 && v >= 5.0) {
        return aa * (15.0 + 6.0 * v2 + 4.0 * v2 * v2) / (4.0 * v2 * v2 * v2 * sqp);
    }
    if (aa > 1.4 || u > 3.2) {
        const double a2 = aa * aa;
        const double uu = sq2 * (a2 + v2);
        const double u2 = 1.0 / (uu * uu);
        return sq2 / sqp * aa / uu * (1.0 + u2 * (3.0 * v2 - a2) + u2 * u2 * (15.0 * v2 * v2 - 30.0 * v2 * a2 + 3.0 * a2 * a2));
    }
    const double ex = (v2 >= 100.0) ? 0.0 : std::exp(-v2);
    double quo = 1.0;
    int start = 0;
    if (v >= 2.4) { quo = 1.0 / (v2 - 1.5); start = 10; }
    else if (v >= 1.3) { start = 5; }
    else { start = 0; }
    const double* a1 = ak + start;
    const double h1 = quo * (a1[0] + v * (a1[1] + v * (a1[2] + v * (a1[3] + v * a1[4]))));
    if (aa <= 0.2) return h1 * aa + ex * (1.0 + aa * aa * (1.0 - 2.0 * v2));
    const double pqs = 2.0 / sqp;
    const double h1p = h1 + pqs * ex;
    const double h2p = pqs * h1p - 2.0 * v2 * ex;
    const double h3p = (pqs * (1.0 - ex * (1.0 - 2.0 * v2)) - 2.0 * v2 * h1p) / 3.0 + pqs * h2p;
    const double h4p = (2.0 * v2 * v2 * ex - pqs * h1p) / 3.0 + pqs * h3p;
    const double psi = ak[15] + aa * (ak[16] + aa * (ak[17] + aa * ak[18]));
    return psi * (ex + aa * (h1p + aa * (h2p + aa * (h3p + aa * h4p))));
}

static inline int huntf_cpp(const double* xx, double x, int n) {
    const double floor = source_real_literal(1.0e-34);
    if (!xx || n < 2) return 1;
    const double xx1 = xx[0];
    const double xx2 = xx[1];
    const double xxn = xx[n - 1];
    const double xf = x;
    const double xtmp = std::max(xf, xx2);
    if (xf < floor || xx1 <= floor || xxn <= floor) return 1;
    int jlo = static_cast<int>((n - 1) * std::log(xtmp / xx1) / std::log(xxn / xx1)) + 1;
    if (jlo < n) {
        const double tst = std::fabs(std::log(xf / (floor + xx[jlo - 1])));
        const double tst2 = std::fabs(std::log(xf / (floor + xx[jlo])));
        if (tst2 < tst) jlo += 1;
    }
    if (jlo < 1) jlo = 1;
    if (jlo > n) jlo = n;
    return jlo;
}

static inline int nbinc_cpp(double e, const double* epi, int ncn2) {
    int n = ncn2;
    int numcon2 = std::max(2, n / 50);
    int numcon3 = n - numcon2;
    if (numcon3 < 2) return 1;
    return huntf_cpp(epi, e, numcon3);
}

} // namespace

extern "C" {

int xstar_emissivity_abi_version() { return 60460; }

const char* xstar_emissivity_backend_name() { return "xstar_emissivity_native_spectral_engine_v0646"; }

int xstar_emissivity_feature_flags() { return 1 | 2 | 4 | 8 | 16; }

int xstar_emissivity_build_binemis_profile(
    int ncn2,
    int nbtpp,
    int ncols,
    int n_line_slots,
    int n_lum_lines,
    double xlum,
    double temperature_1e4k,
    double turbulent_velocity_km_s,
    const double* epi_ev,
    const double* dpthc_flat,
    const double* elum_flat,
    const double* original_flat,
    const double* incident,
    const long long* slot_line_index,
    const double* line_wavelength,
    const long long* line_data_type,
    const double* line_atomic_mass,
    const double* line_natural_rate_s,
    const double* line_auger_width_ev,
    const double* line_auger_rate_s,
    double* out_flat,
    double* stats,
    char* errbuf,
    std::size_t errbuf_size
) {
    if (ncn2 <= 0 || nbtpp <= 0 || ncols < ncn2 || n_line_slots < 0 || n_lum_lines < 0) {
        write_message(errbuf, errbuf_size, "invalid dimensions for xstar_emissivity_build_binemis_profile");
        return 2;
    }
    if (!epi_ev || !dpthc_flat || !elum_flat || !original_flat || !incident || !slot_line_index ||
        !line_wavelength || !line_data_type || !line_atomic_mass || !line_natural_rate_s ||
        !line_auger_width_ev || !line_auger_rate_s || !out_flat || !stats) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_emissivity_build_binemis_profile");
        return 3;
    }
    for (int i = 0; i < 16; ++i) stats[i] = 0.0;
    const int n = ncn2;
    const int rows = 5;
    const double gate = 1.0e-15 * xlum;
    const double dpcrit = 1.0e-6;
    // Source contract: copy original tail, zero active rows first.
    for (int r = 0; r < rows; ++r) {
        for (int k = 0; k < ncols; ++k) out_flat[r * ncols + k] = original_flat[r * ncols + k];
        for (int k = 0; k < n; ++k) out_flat[r * ncols + k] = 0.0;
    }
    double* temp_binned0 = new double[static_cast<std::size_t>(nbtpp)]();
    double* temp_binned1 = new double[static_cast<std::size_t>(nbtpp)]();
    double* temp_prof0 = new double[static_cast<std::size_t>(nbtpp)]();
    double* temp_prof1 = new double[static_cast<std::size_t>(nbtpp)]();
    double* temp_energy = new double[static_cast<std::size_t>(nbtpp)]();
    long long attempted = 0, applied = 0;
    for (int s = 0; s < n_line_slots; ++s) {
        const long long line_index_ll = slot_line_index[s];
        if (line_index_ll <= 0 || line_index_ll > n_lum_lines) continue;
        ++attempted;
        const int j = static_cast<int>(line_index_ll) - 1;
        const double wl = std::fabs(line_wavelength[j]);
        const double line_energy = source_real_literal(12398.4016) / (source_real_literal(1.0e-34) + wl);
        const int nb1 = nbinc_cpp(line_energy, epi_ev, n);
        const double lum0 = elum_flat[j];
        const double lum1 = elum_flat[n_lum_lines + j];
        if (!((lum0 > gate || lum1 > gate) && nb1 > 2 && line_data_type[j] != 76)) continue;
        if (nb1 >= n) {
            delete[] temp_binned0; delete[] temp_binned1; delete[] temp_prof0; delete[] temp_prof1; delete[] temp_energy;
            write_message(errbuf, errbuf_size, "binemis source would read epi(nb1+1) beyond ncn2");
            return 4;
        }
        if (nbtpp < 20) {
            delete[] temp_binned0; delete[] temp_binned1; delete[] temp_prof0; delete[] temp_prof1; delete[] temp_energy;
            write_message(errbuf, errbuf_size, "binemis temporary grid capacity is too short");
            return 5;
        }
        const double mass = std::max(line_atomic_mass[j], std::numeric_limits<double>::min());
        const double vth = 12.0 * std::sqrt(temperature_1e4k / mass);
        const double vturb = std::max(turbulent_velocity_km_s, vth);
        const double e0 = source_real_literal(12398.42) / std::max(wl, 1.0e-49);
        const double deleturb = e0 * (vturb / source_real_literal(3.0e5));
        const double deleth = e0 * (vth / source_real_literal(3.0e5));
        const double dele = std::sqrt(deleth * deleth + deleturb * deleturb);
        if (!(dele > 0.0)) continue;
        const double delea = (line_auger_rate_s[j] != 0.0) ? line_auger_rate_s[j] * source_real_literal(4.14e-15) : line_auger_width_ev[j];
        const double deler = line_natural_rate_s[j] * source_real_literal(4.14e-15);
        const double aasmall = (delea + deler) / (source_real_literal(1.0e-36) + dele) / source_real_literal(12.56);
        const int ml1 = nb1;
        const double e00 = epi_ev[ml1 - 1];
        const double etmp = e0;
        const double deleepi = epi_ev[ml1] - epi_ev[ml1 - 1];
        int ncut = static_cast<int>(deleepi / dele);
        ncut = std::max(1, std::min(ncut, nbtpp / 10));
        const double deleused = deleepi / static_cast<double>(static_cast<float>(ncut));
        int mlc = 0;
        int ldir = 1;
        int ldon0 = 0, ldon1 = 0;
        int mlmin = nbtpp;
        int mlmax = 1;
        int ml1min = nbtpp + 1;
        int ml1max = 0;
        const int ml2 = nbtpp / 2;
        const int center = ml2 - 1;
        double delet = (e00 - etmp) / dele;
        double profile = (aasmall > source_real_literal(1.0e-9) ? voigte_cpp(std::fabs(delet), aasmall) : std::exp(-delet * delet)) / source_real_literal(1.772);
        profile = profile / dele / source_real_literal(1.602197e-12);
        temp_energy[center] = e00;
        temp_prof0[center] = lum0 * profile;
        temp_prof1[center] = lum1 * profile;
        double tst = 1.0;
        while (ldon0 * ldon1 == 0 && mlc < nbtpp / 2) {
            ++mlc;
            for (int ij = 0; ij < 2; ++ij) {
                ldir = -ldir;
                int& ldon = (ij == 0) ? ldon0 : ldon1;
                if (ldon == 1) continue;
                int mlm = ml2 + ldir * mlc;
                mlm = std::min(nbtpp, std::max(1, mlm));
                const double etptst = e00 + static_cast<double>(static_cast<float>(ldir * mlc)) * deleused;
                if (mlm < nbtpp && mlm > 1 && etptst > 0.0 && etptst < epi_ev[n - 1]) {
                    mlmin = std::min(mlm, mlmin);
                    mlmax = std::max(mlm, mlmax);
                    temp_energy[mlm - 1] = etptst;
                    delet = (etptst - etmp) / dele;
                    profile = (aasmall > source_real_literal(1.0e-9) ? voigte_cpp(std::fabs(delet), aasmall) : std::exp(-delet * delet)) / source_real_literal(1.772);
                    profile = profile / dele / source_real_literal(1.602197e-12);
                    temp_prof0[mlm - 1] = lum0 * profile;
                    temp_prof1[mlm - 1] = lum1 * profile;
                    tst = profile;
                }
                const double deletmax = std::max(50.0, 200.0 * aasmall);
                if (((tst < dpcrit) || mlm <= 1 || mlm >= nbtpp || etptst <= 0.0 || etptst >= epi_ev[n - 1] || mlc > nbtpp || std::fabs((etptst - etmp) / dele) > deletmax) &&
                    ml1min < ml1 - 2 && ml1max > ml1 + 2 && ml1min >= 1 && ml1max <= nbtpp) {
                    ldon = 1;
                }
            }
        }
        if (mlmin > mlmax) continue;
        ++applied;
        ml1min = nbinc_cpp(temp_energy[mlmin - 1], epi_ev, n);
        ml1max = nbinc_cpp(temp_energy[mlmax - 1], epi_ev, n);
        int ml1m = ml1min;
        mlmin = std::max(mlmin, 2);
        mlmax = std::min(mlmax, nbtpp);
        double sume = 0.0, zrsum1 = 0.0, zrsum2 = 0.0;
        for (int mlm = mlmin + 1; mlm <= mlmax; ++mlm) {
            const double tmpe = std::fabs(temp_energy[mlm - 1] - temp_energy[mlm - 2]);
            sume += tmpe;
            zrsum1 += (temp_prof0[mlm - 1] + temp_prof0[mlm - 2]) * tmpe / 2.0;
            zrsum2 += (temp_prof1[mlm - 1] + temp_prof1[mlm - 2]) * tmpe / 2.0;
            if (temp_energy[mlm - 1] > epi_ev[ml1m - 1]) {
                if (mlm == mlmax) ml1m = std::max(1, ml1m - 1);
                if (sume > 1.0e-24) {
                    const double zrtp2 = zrsum2 / sume;
                    const double zrtp1 = zrsum1 / sume;
                    while (temp_energy[mlm - 1] > epi_ev[ml1m - 1] && ml1m < n) {
                        temp_binned0[ml1m - 1] = zrtp1;
                        temp_binned1[ml1m - 1] = zrtp2;
                        ++ml1m;
                    }
                }
                zrsum2 = 0.0; zrsum1 = 0.0; sume = 0.0;
            }
        }
        for (int q = mlmin - 1; q < mlmax; ++q) { temp_prof0[q] = 0.0; temp_prof1[q] = 0.0; }
        const int lo = std::max(1, ml1min);
        const int hi = std::min(n, ml1max);
        if (lo <= hi) {
            for (int k = lo; k <= hi; ++k) {
                out_flat[3 * ncols + (k - 1)] += temp_binned1[k - 1];
                out_flat[2 * ncols + (k - 1)] += temp_binned0[k - 1];
                temp_binned0[k - 1] = 0.0;
                temp_binned1[k - 1] = 0.0;
            }
        }
    }
    for (int kl = 0; kl < n; ++kl) {
        out_flat[2 * ncols + kl] += original_flat[1 * ncols + kl];
        out_flat[3 * ncols + kl] += original_flat[2 * ncols + kl];
        out_flat[1 * ncols + kl] = incident[kl] * std::exp(-dpthc_flat[kl]);
        out_flat[0 * ncols + kl] = incident[kl];
        out_flat[4 * ncols + kl] = original_flat[3 * ncols + kl];
    }
    stats[0] = static_cast<double>(attempted);
    stats[1] = static_cast<double>(applied);
    stats[2] = static_cast<double>(n_line_slots);
    delete[] temp_binned0; delete[] temp_binned1; delete[] temp_prof0; delete[] temp_prof1; delete[] temp_energy;
    write_message(errbuf, errbuf_size, "xstar_emissivity_build_binemis_profile evaluated");
    return 0;
}

} // extern "C"

// v0.6.46 persistent native emissivity/opacity contribution engine.
#include "xstar_spectral_engine.h"
#include <chrono>
#include <cstdint>
#include <new>

extern "C" int xstar_opacity_apply_exact_grid_v1(
    const double* packed_grid,
    const double* epi,
    int ncn2,
    double* opakc,
    double* rccemis,
    long long* updated_bins,
    double* opacity_seconds,
    char* errbuf,
    std::size_t errbuf_size
);

extern "C" int xstar_opacity_apply_line_profile_v1(
    double optpp,
    double line_energy_ev,
    double vturb_km_s,
    double temperature_1e4k,
    double atomic_mass_amu,
    double natural_width_ev,
    const double* seed_profiles,
    int seed_radius,
    const double* epi,
    int ncn2,
    double* opakc,
    double* rccemis,
    long long* updated_bins,
    double* opacity_seconds,
    char* errbuf,
    std::size_t errbuf_size
);

struct xstar_spectral_context {
    xstar_spectral_stats_v1 cumulative{};
};

namespace {

bool valid_workspace(const xstar_spectral_workspace_v1* w, char* error, std::size_t error_size) {
    if (!w || w->struct_size < sizeof(xstar_spectral_workspace_v1) ||
        w->abi_version != XSTAR_SPECTRAL_ENGINE_ABI_VERSION) {
        write_message(error, error_size, "invalid spectral workspace header");
        return false;
    }
    if (!w->rcem || !w->oplin || !w->cemab || !w->cabab || !w->opakab ||
        !w->rccemis || !w->opakc || !w->opakcont || !w->fline || !w->flinel || !w->epi_eV) {
        write_message(error, error_size, "null spectral workspace array");
        return false;
    }
    if (w->energy_count < 4 || w->rccemis_count < 2 * w->energy_count ||
        w->opakc_count < w->energy_count || w->opakcont_count < w->energy_count ||
        w->flinel_count < w->energy_count || (w->rcem_count % 2) != 0 ||
        (w->cemab_count % 2) != 0 || (w->fline_count % 2) != 0) {
        write_message(error, error_size, "spectral workspace capacity mismatch");
        return false;
    }
    return true;
}

void add_stats(xstar_spectral_stats_v1& dst, const xstar_spectral_stats_v1& src) {
    dst.calls += src.calls;
    dst.contributions_attempted += src.contributions_attempted;
    dst.contributions_committed += src.contributions_committed;
    dst.emissivity_contributions += src.emissivity_contributions;
    dst.opacity_contributions += src.opacity_contributions;
    dst.line_profiles += src.line_profiles;
    dst.source_order_violations += src.source_order_violations;
    dst.construction_seconds += src.construction_seconds;
    dst.opacity_seconds += src.opacity_seconds;
    dst.commit_seconds += src.commit_seconds;
    dst.status_flags |= src.status_flags;
}

} // namespace

extern "C" {

uint32_t xstar_spectral_engine_abi_version(void) {
    return XSTAR_SPECTRAL_ENGINE_ABI_VERSION;
}

const char* xstar_spectral_engine_backend_name(void) {
    return "xstar_native_emissivity_opacity_exact_grid_engine_v06472";
}

uint32_t xstar_spectral_engine_feature_flags(void) {
    return XSTAR_SPECTRAL_STATUS_SOURCE_ORDERED |
           XSTAR_SPECTRAL_STATUS_NATIVE_EMISSIVITY |
           XSTAR_SPECTRAL_STATUS_NATIVE_OPACITY |
           XSTAR_SPECTRAL_STATUS_PERSISTENT_CONTEXT |
           XSTAR_SPECTRAL_STATUS_EXACT_GRID_ORACLE;
}

void xstar_spectral_workspace_init_v1(xstar_spectral_workspace_v1* workspace) {
    if (!workspace) return;
    std::memset(workspace, 0, sizeof(*workspace));
    workspace->struct_size = sizeof(*workspace);
    workspace->abi_version = XSTAR_SPECTRAL_ENGINE_ABI_VERSION;
}

void xstar_spectral_stats_init_v1(xstar_spectral_stats_v1* stats) {
    if (!stats) return;
    std::memset(stats, 0, sizeof(*stats));
    stats->struct_size = sizeof(*stats);
    stats->abi_version = XSTAR_SPECTRAL_ENGINE_ABI_VERSION;
}

int xstar_spectral_context_create_v1(
    xstar_spectral_context** context,
    char* error,
    size_t error_size
) {
    if (!context) {
        write_message(error, error_size, "null spectral context output");
        return 2;
    }
    try {
        *context = new xstar_spectral_context();
        xstar_spectral_stats_init_v1(&(*context)->cumulative);
        write_message(error, error_size, "spectral context created");
        return 0;
    } catch (const std::bad_alloc&) {
        *context = nullptr;
        write_message(error, error_size, "spectral context allocation failed");
        return 5;
    }
}

void xstar_spectral_context_destroy(xstar_spectral_context* context) {
    delete context;
}

int xstar_spectral_context_reset_v1(
    xstar_spectral_context* context,
    char* error,
    size_t error_size
) {
    if (!context) {
        write_message(error, error_size, "null spectral context");
        return 2;
    }
    xstar_spectral_stats_init_v1(&context->cumulative);
    write_message(error, error_size, "spectral context reset");
    return 0;
}

int xstar_spectral_apply_contributions_v1(
    xstar_spectral_context* context,
    const xstar_spectral_contribution_v1* contributions,
    size_t contribution_count,
    const double* seed_profiles,
    size_t seed_profile_stride,
    xstar_spectral_workspace_v1* workspace,
    xstar_spectral_stats_v1* stats,
    char* error,
    size_t error_size
) {
    if (!context || (!contributions && contribution_count != 0) || !stats) {
        write_message(error, error_size, "invalid spectral contribution arguments");
        return 2;
    }
    if (!valid_workspace(workspace, error, error_size)) return 3;
    xstar_spectral_stats_init_v1(stats);
    stats->calls = 1;
    stats->status_flags = xstar_spectral_engine_feature_flags();
    const auto call_started = std::chrono::steady_clock::now();
    uint64_t previous_position = 0;
    const size_t line_capacity = workspace->oplin_count;
    const size_t continuum_capacity = workspace->opakab_count;
    const size_t rcem_stride = workspace->rcem_count / 2;
    const size_t cemab_stride = workspace->cemab_count / 2;
    const size_t fline_stride = workspace->fline_count / 2;
    for (size_t i = 0; i < contribution_count; ++i) {
        const xstar_spectral_contribution_v1& c = contributions[i];
        ++stats->contributions_attempted;
        if (c.source_position == 0 || (previous_position != 0 && c.source_position <= previous_position)) {
            ++stats->source_order_violations;
            write_message(error, error_size, "spectral contribution source order violation");
            return 6;
        }
        previous_position = c.source_position;
        const auto construct_started = std::chrono::steady_clock::now();
        const int index = c.output_index;
        if (c.kind == XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE) {
            if (index <= 0 || static_cast<size_t>(index) >= continuum_capacity ||
                static_cast<size_t>(index) >= cemab_stride || static_cast<size_t>(index) >= workspace->cabab_count) {
                write_message(error, error_size, "bound-free contribution output index out of range");
                return 7;
            }
            const double denom = c.ptmp1 + c.ptmp2;
            if (denom == 0.0) {
                write_message(error, error_size, "zero continuum escape denominator");
                return 8;
            }
            // Bound-free opakab is carried as a cross section.  Convert it
            // to the source cm^-1 threshold opacity once, matching ucalc's
            // abund1*ansar1*xpx convention.
            workspace->opakab[index] = c.opakab * c.abundance_lower * c.hydrogen_density;
            workspace->cabab[index] = std::abs(c.ans4) * c.abundance_lower * c.hydrogen_density;
            workspace->cemab[index] = c.ptmp1 * std::abs(c.ans3) / denom * c.abundance_upper * c.hydrogen_density;
            workspace->cemab[cemab_stride + index] = c.ptmp2 * std::abs(c.ans3) / denom * c.abundance_upper * c.hydrogen_density;
            ++stats->emissivity_contributions;
            ++stats->opacity_contributions;
        } else if (c.kind == XSTAR_SPECTRAL_KIND_EMISAB_LINE) {
            if (c.rate_type == 4 && index > 0) {
                if (static_cast<size_t>(index) >= line_capacity || static_cast<size_t>(index) >= rcem_stride) {
                    write_message(error, error_size, "line contribution output index out of range");
                    return 7;
                }
                const double denom = c.ptmp1 + c.ptmp2;
                if (denom == 0.0) {
                    write_message(error, error_size, "zero line escape denominator");
                    return 8;
                }
                workspace->rcem[index] = -c.abundance_upper * c.ans3 * c.ptmp1 / denom;
                workspace->rcem[rcem_stride + index] = -c.abundance_upper * c.ans3 * c.ptmp2 / denom;
                workspace->oplin[index] = c.opakab * c.abundance_lower;
                ++stats->emissivity_contributions;
                ++stats->opacity_contributions;
            }
        } else if (c.kind == XSTAR_SPECTRAL_KIND_EMIS_OPACITY_ONLY) {
            if (index <= 0 || static_cast<size_t>(index) >= continuum_capacity) {
                write_message(error, error_size, "continuum opacity output index out of range");
                return 7;
            }
            workspace->opakab[index] = c.opakab;
            ++stats->opacity_contributions;
        } else if (c.kind == XSTAR_SPECTRAL_KIND_EMIS_LINE) {
            if (index <= 0 || static_cast<size_t>(index) >= line_capacity ||
                static_cast<size_t>(index) >= fline_stride || c.bin_one_based <= 0 ||
                static_cast<size_t>(c.bin_one_based) > workspace->flinel_count ||
                !(c.bin_width_eV > 0.0)) {
                write_message(error, error_size, "native line contribution index or width invalid");
                return 7;
            }
            const double opakb1 = c.opakab * c.abundance_lower;
            const double net = c.ans2 * c.abundance_upper - c.ans1 * c.abundance_lower;
            const double erg_per_ev = 1.602176634e-12;
            const double rcem1 = std::max(net * c.line_energy_eV * erg_per_ev * c.ptmp1, 0.0);
            const double rcem2 = std::max(net * c.line_energy_eV * erg_per_ev * c.ptmp2, 0.0);
            const double flinel_delta = (rcem1 + rcem2) * 2.0 / c.bin_width_eV / erg_per_ev;
            workspace->oplin[index] = opakb1;
            workspace->fline[index] = rcem1;
            workspace->fline[fline_stride + index] = rcem2;
            workspace->flinel[c.bin_one_based - 1] += flinel_delta;
            ++stats->emissivity_contributions;
            ++stats->opacity_contributions;
            const double* seed = nullptr;
            int seed_radius = 0;
            const bool exact_grid_oracle =
                seed_profiles && seed_profile_stride == XSTAR_SPECTRAL_EXACT_GRID_STRIDE;
            if (seed_profiles && (exact_grid_oracle ||
                (seed_profile_stride >= 21 && (seed_profile_stride % 2) == 1))) {
                seed = seed_profiles + i * seed_profile_stride;
                if (!exact_grid_oracle) {
                    seed_radius = static_cast<int>((seed_profile_stride - 1) / 2);
                }
            }
            if (!seed || (!exact_grid_oracle && seed_radius < 10)) {
                write_message(error, error_size, "native line contribution lacks valid seed or exact-grid oracle");
                return 9;
            }
            long long updated = 0;
            double opacity_elapsed = 0.0;
            char opacity_error[512] = {0};
            const int rc = exact_grid_oracle
                ? xstar_opacity_apply_exact_grid_v1(
                    seed, workspace->epi_eV, static_cast<int>(workspace->energy_count),
                    workspace->opakc, workspace->rccemis, &updated, &opacity_elapsed,
                    opacity_error, sizeof(opacity_error))
                : xstar_opacity_apply_line_profile_v1(
                    opakb1, c.line_energy_eV, c.turbulent_velocity_km_s,
                    c.temperature_1e4K, c.atomic_mass_amu, c.natural_width_eV,
                    seed, seed_radius, workspace->epi_eV, static_cast<int>(workspace->energy_count),
                    workspace->opakc, workspace->rccemis, &updated, &opacity_elapsed,
                    opacity_error, sizeof(opacity_error));
            stats->opacity_seconds += opacity_elapsed;
            if (rc != 0) {
                write_message(error, error_size, opacity_error[0] ? opacity_error : "native opacity line profile failed");
                return 10;
            }
            ++stats->line_profiles;
        } else {
            write_message(error, error_size, "unsupported native spectral contribution kind");
            return 11;
        }
        const auto construct_ended = std::chrono::steady_clock::now();
        stats->construction_seconds += std::chrono::duration<double>(construct_ended - construct_started).count();
        ++stats->contributions_committed;
    }
    const auto call_ended = std::chrono::steady_clock::now();
    stats->commit_seconds = std::chrono::duration<double>(call_ended - call_started).count();
    add_stats(context->cumulative, *stats);
    write_message(error, error_size, "native spectral contributions applied");
    return 0;
}

} // extern "C"
