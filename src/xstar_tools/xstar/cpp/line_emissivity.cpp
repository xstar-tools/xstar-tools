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
    const double floor = 1.0e-34;
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

int xstar_emissivity_abi_version() { return 1; }

const char* xstar_emissivity_backend_name() { return "xstar_emissivity_binemis_profile_v1"; }

int xstar_emissivity_feature_flags() { return 1 | 2; }

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
        const double line_energy = 12398.4016 / (1.0e-34 + wl);
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
        const double e0 = 12398.42 / std::max(wl, 1.0e-49);
        const double deleturb = e0 * (vturb / 3.0e5);
        const double deleth = e0 * (vth / 3.0e5);
        const double dele = std::sqrt(deleth * deleth + deleturb * deleturb);
        if (!(dele > 0.0)) continue;
        const double delea = (line_auger_rate_s[j] != 0.0) ? line_auger_rate_s[j] * 4.14e-15 : line_auger_width_ev[j];
        const double deler = line_natural_rate_s[j] * 4.14e-15;
        const double aasmall = (delea + deler) / (1.0e-36 + dele) / 12.56;
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
        double profile = (aasmall > 1.0e-9 ? voigte_cpp(std::fabs(delet), aasmall) : std::exp(-delet * delet)) / 1.772;
        profile = profile / dele / 1.602197e-12;
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
                    profile = (aasmall > 1.0e-9 ? voigte_cpp(std::fabs(delet), aasmall) : std::exp(-delet * delet)) / 1.772;
                    profile = profile / dele / 1.602197e-12;
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
