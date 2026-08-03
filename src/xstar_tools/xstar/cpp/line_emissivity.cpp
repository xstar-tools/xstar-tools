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
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <string>

namespace {

inline double source_real_literal(double value) {
    return static_cast<double>(static_cast<float>(value));
}

// v0.6.48.12.3.22: source-faithful Type-50-family linopac eligibility.
// This predicate is deliberately element-agnostic.  FORTRAN ucalc label 50
// applies the default-REAL opakb1 > 1.e-34 gate before linopac for ordinary
// radiative-line records.  Data type 91 explicitly jumps to label 50 and
// therefore shares the same rule.  Data type 89 does not: its source branch
// uses a different optical-depth gate (opakb1*delr > 1.e-8), so it must not be
// folded into this predicate.
inline bool source_type50_linopac_family(int data_type, int rate_type) {
    return rate_type == 4 && (data_type == 50 || data_type == 91);
}

inline bool source_type50_linopac_accept(double opakb1, int data_type, int rate_type) {
    if (!source_type50_linopac_family(data_type, rate_type)) return true;
    return std::isfinite(opakb1) && opakb1 > source_real_literal(1.0e-34);
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
    // voigte.f90 label 120 is reachable only for a>0.2.
    if (aa > 0.2 && (aa > 1.4 || u > 3.2)) {
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


// binemis.f90 uses nbtpp=ncn, where the source ncn parameter is 999999.
// The temporary profile therefore reaches q=-499997..+499999 relative to
// ml2=int(nbtpp/2).  We reproduce the source rebin boundary crossings without
// materializing or traversing the million-point array.  Outside |v|>=50 the
// profile is already in the smooth asymptotic wing; for a<=0.2 the literal
// voigte label-121 expression has a closed-form integral.  For larger damping
// use fixed Gauss-Legendre quadrature of the same source profile formula.
constexpr long long kSourceBinemisNegativeHalfSteps = 499997LL;
constexpr long long kSourceBinemisPositiveHalfSteps = 499999LL;
constexpr double kSourceBinemisFarV = 50.0;

static inline double binemis_profile_cpp(double energy, double etmp, double dele, double aasmall) {
    const double delet = (energy - etmp) / dele;
    double h = aasmall > source_real_literal(1.0e-9)
        ? voigte_cpp(std::fabs(delet), aasmall)
        : std::exp(-delet * delet);
    return h / source_real_literal(1.772) / dele / source_real_literal(1.602197e-12);
}

static inline double binemis_far_segment_average_cpp(
    double e1, double e2, double etmp, double dele, double aasmall) {
    if (!(e2 > e1) || !(dele > 0.0)) return 0.0;
    const double v1 = (e1 - etmp) / dele;
    const double v2 = (e2 - etmp) / dele;
    if (!(v1 * v2 > 0.0) || std::min(std::fabs(v1), std::fabs(v2)) < kSourceBinemisFarV) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    if (aasmall <= 0.0) return 0.0;
    if (aasmall <= source_real_literal(0.2)) {
        const auto primitive = [](double v) {
            const double v2l = v * v;
            return -1.0 / v - 0.5 / (v * v2l) - 0.75 / (v * v2l * v2l);
        };
        // voigte label 121:
        // H = a/sqrt(pi) * (v^-2 + 1.5 v^-4 + 3.75 v^-6).
        // binemis divides by source-REAL 1.772, dele and erg/eV; dE=dele dv.
        const double coeff = aasmall /
            (source_real_literal(1.772453851) * source_real_literal(1.772) * source_real_literal(1.602197e-12));
        const double integral = coeff * (primitive(v2) - primitive(v1));
        return integral / (e2 - e1);
    }
    // Smooth large-a far wing: 8-point Gauss-Legendre integration.
    static constexpr double x[4] = {
        0.1834346424956498, 0.5255324099163290,
        0.7966664774136267, 0.9602898564975363
    };
    static constexpr double w[4] = {
        0.3626837833783620, 0.3137066458778873,
        0.2223810344533745, 0.1012285362903763
    };
    const double mid = 0.5 * (e1 + e2);
    const double half = 0.5 * (e2 - e1);
    double sum = 0.0;
    for (int i = 0; i < 4; ++i) {
        const double dx = half * x[i];
        sum += w[i] * (binemis_profile_cpp(mid - dx, etmp, dele, aasmall) +
                       binemis_profile_cpp(mid + dx, etmp, dele, aasmall));
    }
    return 0.5 * sum; // integral/(e2-e1) = half*sum/(2*half)
}

static inline long long binemis_source_qmin(double e00, double h) {
    long long q = std::max(-kSourceBinemisNegativeHalfSteps,
        static_cast<long long>(std::floor(-e00 / h)) + 1LL);
    while (q <= kSourceBinemisPositiveHalfSteps && e00 + static_cast<double>(q) * h <= 0.0) ++q;
    return q;
}

static inline long long binemis_source_qmax(double e00, double h, double emax) {
    long long q = std::min(kSourceBinemisPositiveHalfSteps,
        static_cast<long long>(std::ceil((emax - e00) / h)) - 1LL);
    while (q >= -kSourceBinemisNegativeHalfSteps && e00 + static_cast<double>(q) * h >= emax) --q;
    return q;
}

static inline long long binemis_first_q_above(double boundary, double e00, double h) {
    long long q = static_cast<long long>(std::floor((boundary - e00) / h)) + 1LL;
    while (e00 + static_cast<double>(q) * h <= boundary) ++q;
    return q;
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
    const double gate = source_real_literal(1.0e-15) * xlum;
    const double dpcrit = source_real_literal(1.0e-6);
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
    long long attempted = 0, applied = 0, far_wing_bins = 0;
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
        std::fill(temp_binned0, temp_binned0 + n, 0.0);
        std::fill(temp_binned1, temp_binned1 + n, 0.0);
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
        const double core_energy_min = temp_energy[mlmin - 1];
        const double core_energy_max = temp_energy[mlmax - 1];
        ml1min = nbinc_cpp(core_energy_min, epi_ev, n);
        ml1max = nbinc_cpp(core_energy_max, epi_ev, n);
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
        const int core_lo = std::max(1, ml1min);
        const int core_hi = std::min(n, ml1max);

        // Source-capacity continuation with literal binemis boundary-crossing
        // ownership.  The old continuation required an entire public bin to
        // lie inside the +/-499999-step reach and endpoint-averaged that bin.
        // Source binemis instead accumulates fine-grid intervals until the
        // first temporary point strictly exceeds an epi boundary.  If the last
        // valid temporary point is itself that crossing point, the literal
        // mlm==mlmax branch decrements ml1m and overwrites the preceding bin.
        // Reproduce those event boundaries exactly; an endpoint that does not
        // cross a public boundary publishes no terminal partial segment.
        const long long qmin = binemis_source_qmin(e00, deleused);
        const long long qmax = binemis_source_qmax(e00, deleused, epi_ev[n - 1]);
        int full_lo = core_lo;
        int full_hi = core_hi;
        if (qmin < qmax) {
            const double source_energy_min = e00 + static_cast<double>(qmin) * deleused;
            const double source_energy_max = e00 + static_cast<double>(qmax) * deleused;
            full_lo = std::max(1, nbinc_cpp(source_energy_min, epi_ev, n));
            full_hi = std::min(n, nbinc_cpp(source_energy_max, epi_ev, n));
            long long qprev = qmin;
            int k = full_lo;
            while (k < n) {
                const int k0 = k;
                long long qevent = binemis_first_q_above(epi_ev[k0 - 1], e00, deleused);
                qevent = std::max(qevent, qmin + 1LL);
                if (qevent > qmax) break;
                const double e1 = e00 + static_cast<double>(qprev) * deleused;
                const double e2 = e00 + static_cast<double>(qevent) * deleused;
                const double avg_profile = binemis_far_segment_average_cpp(e1, e2, etmp, dele, aasmall);
                int kwrite = (qevent == qmax) ? std::max(1, k0 - 1) : k0;
                int next_k = kwrite;
                while (next_k < n && e2 > epi_ev[next_k - 1]) {
                    if (std::isfinite(avg_profile)) {
                        temp_binned0[next_k - 1] = lum0 * avg_profile;
                        temp_binned1[next_k - 1] = lum1 * avg_profile;
                        ++far_wing_bins;
                    }
                    ++next_k;
                }
                // Normally kwrite==k0.  At the literal terminal mlmax event
                // binemis decrements ml1m once, overwriting the preceding bin;
                // nevertheless the next unprocessed boundary is next_k.
                k = std::max(k0 + 1, next_k);
                qprev = qevent;
                if (qevent == qmax) break;
            }
        }

        // The compact core is literal for near-center segments.  Far source
        // event averages above overwrite any artificial compact-edge values.
        const int add_lo = std::max(1, std::min(core_lo, full_lo));
        const int add_hi = std::min(n, std::max(core_hi, full_hi));
        if (add_lo <= add_hi) {
            for (int k = add_lo; k <= add_hi; ++k) {
                out_flat[3 * ncols + (k - 1)] += temp_binned1[k - 1];
                out_flat[2 * ncols + (k - 1)] += temp_binned0[k - 1];
            }
        }
        for (int q = mlmin - 1; q < mlmax; ++q) { temp_prof0[q] = 0.0; temp_prof1[q] = 0.0; }
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
    stats[3] = static_cast<double>(far_wing_bins);
    stats[4] = 499999.0;
    stats[5] = static_cast<double>(nbtpp);
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

extern "C" int xstar_opacity_apply_line_profile_experimental_v064812326(
    double optpp, double line_energy_ev, double vturb_km_s, double temperature_1e4k,
    double atomic_mass_amu, double natural_width_ev, const double* seed_profiles,
    int seed_radius, const double* epi, int ncn2, double* opakc, double* rccemis,
    long long* updated_bins, double* opacity_seconds, char* errbuf, std::size_t errbuf_size);

extern "C" int xstar_opacity_apply_line_profile_experimental_v064812327(
    double optpp, double line_energy_ev, double vturb_km_s, double temperature_1e4k,
    double atomic_mass_amu, double natural_width_ev, const double* seed_profiles,
    int seed_radius, const double* epi, int ncn2, double* opakc, double* rccemis,
    long long* updated_bins, double* opacity_seconds, char* errbuf, std::size_t errbuf_size);

extern "C" int xstar_opacity_last_profile_vectorized_v064812324(void);
extern "C" void xstar_opacity_type50_phase_perf_reset_v064812326(void);
extern "C" void xstar_opacity_type50_phase_perf_snapshot_v064812326(
    std::uint64_t* phase_profiles, std::uint64_t* span_events, std::uint64_t* span_bins,
    std::uint64_t* vectorizable_span_events, std::uint64_t* vectorizable_span_bins,
    std::uint64_t* max_span, double* profile_value_seconds, double* rebin_seconds,
    double* range_update_seconds, std::uint64_t* range_avx2_profiles,
    std::uint64_t* range_avx2_blocks, std::uint64_t* range_avx2_bins,
    std::uint64_t* range_scalar_bins);

extern "C" void xstar_opacity_type50_perf_reset_v064812327(void);
extern "C" void xstar_opacity_type50_perf_snapshot_v064812327(
    std::uint64_t* schedule_profiles, std::uint64_t* cache_hits,
    std::uint64_t* cache_misses, std::uint64_t* cache_uncached,
    std::uint64_t* distinct_cached_keys, std::uint64_t* cache_bytes,
    std::uint64_t* cached_events, double* schedule_build_seconds,
    std::uint64_t* ncut_histogram, std::size_t ncut_histogram_len,
    std::uint64_t* gaussian_points, std::uint64_t* small_a_core_points,
    std::uint64_t* small_a_farwing_points, std::uint64_t* large_a_points,
    std::uint64_t* inline_avx2_profiles, std::uint64_t* inline_avx2_blocks,
    std::uint64_t* inline_avx2_points, std::uint64_t* inline_scalar_points);

extern "C" void xstar_opacity_type50_perf_reset_v064812328(void);
extern "C" void xstar_opacity_type50_perf_snapshot_v064812328(
    std::uint64_t* prod_avx2_profiles, std::uint64_t* prod_scalar_profiles,
    std::uint64_t* prod_avx2_blocks, std::uint64_t* prod_avx2_points,
    std::uint64_t* prod_scalar_profile_points, std::uint64_t* ncut4_profiles,
    std::uint64_t* ncut4_fast_blocks, std::uint64_t* ncut4_boundary_fallback_blocks,
    std::uint64_t* ncut4_fast_points, std::uint64_t* decomp_profiles,
    std::uint64_t* decomp_avx2_points, std::uint64_t* decomp_scalar_points,
    double* decomp_avx2_profile_seconds, double* decomp_scalar_profile_seconds,
    double* decomp_consume_seconds);
extern "C" void xstar_opacity_type50_perf_reset_v064812329(void);
extern "C" void xstar_opacity_type50_perf_snapshot_v064812329(
    std::uint64_t* register_profiles, std::uint64_t* hint_profiles,
    std::uint64_t* consumed_points, std::uint64_t* boundary_true_points,
    std::uint64_t* boundary_false_points, std::uint64_t* boundary_events,
    std::uint64_t* output_bins_advanced, std::uint64_t* max_bins_per_event);
extern "C" void xstar_opacity_type50_perf_reset_v064812330(void);
extern "C" void xstar_opacity_type50_perf_snapshot_v064812330(
    std::uint64_t* prod_hint_profiles, std::uint64_t* fallback_12328_profiles,
    std::uint64_t* next_epi_profiles, std::uint64_t* local_bins_profiles,
    std::uint64_t* cursor_profiles);
extern "C" void xstar_opacity_type50_perf_reset_v064812331(void);
extern "C" void xstar_opacity_type50_perf_snapshot_v064812331(
    std::uint64_t* prod_cursor_profiles, std::uint64_t* fallback_hint_profiles,
    std::uint64_t* decomp_profiles, std::uint64_t* decomp_avx2_points,
    std::uint64_t* decomp_scalar_points, std::uint64_t* decomp_boundary_events,
    std::uint64_t* decomp_opakc_bins, double* decomp_avx2_seconds,
    double* decomp_scalar_seconds, double* decomp_trapezoid_seconds,
    double* decomp_boundary_rebin_seconds, double* decomp_opakc_seconds);


struct xstar_spectral_context {
    xstar_spectral_stats_v1 cumulative{};
};

namespace {

thread_local xstar_spectral_perf_v064892 g_spectral_perf_v064892{};
thread_local std::uint64_t g_type50_vectorized_profiles_v064812324 = 0u;
thread_local std::uint64_t g_type50_scalar_profiles_v064812324 = 0u;
static int apply_line_profile_dispatch_v064812326(
    double optpp, double line_energy_ev, double vturb_km_s, double temperature_1e4k,
    double atomic_mass_amu, double natural_width_ev, const double* seed_profiles,
    int seed_radius, const double* epi, int ncn2, double* opakc, double* rccemis,
    long long* updated_bins, double* opacity_seconds, char* errbuf, std::size_t errbuf_size) {
    // 12.3.28: production Type-50 selection lives entirely inside
    // xstar_opacity_apply_line_profile_v1.  Retired 12.3.26/12.3.27
    // experiment dispatches are not part of the normal emissivity path.
    return xstar_opacity_apply_line_profile_v1(
        optpp, line_energy_ev, vturb_km_s, temperature_1e4k, atomic_mass_amu,
        natural_width_ev, seed_profiles, seed_radius, epi, ncn2, opakc, rccemis,
        updated_bins, opacity_seconds, errbuf, errbuf_size);
}

std::size_t spectral_family_slot_v064892(int data_type) {
    switch (data_type) {
        case 49: return 0u;
        case 50: return 1u;
        case 53: return 2u;
        case 76: return 3u;
        case 86: return 4u;
        case 88: return 5u;
        case 99: return 6u;
        default: return 7u;
    }
}

void add_perf_v064892(xstar_spectral_perf_v064892& dst, const xstar_spectral_perf_v064892& src) {
    dst.apply_calls += src.apply_calls;
    dst.contributions += src.contributions;
    dst.line_profiles += src.line_profiles;
    dst.exact_grid_profiles += src.exact_grid_profiles;
    dst.native_profile_profiles += src.native_profile_profiles;
    dst.updated_continuum_bins += src.updated_continuum_bins;
    dst.exact_grid_valid_points += src.exact_grid_valid_points;
    dst.kind_bound_free += src.kind_bound_free;
    dst.kind_emisab_line += src.kind_emisab_line;
    dst.kind_opacity_only += src.kind_opacity_only;
    dst.kind_emis_line += src.kind_emis_line;
    dst.kind_full_line += src.kind_full_line;
    for (std::size_t i = 0; i < XSTAR_SPECTRAL_PERF_V064892_FAMILY_COUNT; ++i) {
        dst.family_contributions[i] += src.family_contributions[i];
        dst.family_line_profiles[i] += src.family_line_profiles[i];
        dst.family_updated_bins[i] += src.family_updated_bins[i];
        dst.family_profile_seconds[i] += src.family_profile_seconds[i];
    }
    dst.apply_seconds += src.apply_seconds;
    dst.profile_kernel_seconds += src.profile_kernel_seconds;
    dst.exact_grid_profile_seconds += src.exact_grid_profile_seconds;
    dst.native_profile_seconds += src.native_profile_seconds;
}

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

void xstar_spectral_perf_init_v064892(xstar_spectral_perf_v064892* perf) {
    if (!perf) return;
    std::memset(perf, 0, sizeof(*perf));
    perf->struct_size = sizeof(*perf);
    perf->abi_version = XSTAR_SPECTRAL_PERF_V064892_ABI_VERSION;
}

void xstar_spectral_perf_reset_v064892(void) {
    xstar_spectral_perf_init_v064892(&g_spectral_perf_v064892);
}

int xstar_spectral_perf_snapshot_v064892(xstar_spectral_perf_v064892* perf) {
    if (!perf) return 2;
    *perf = g_spectral_perf_v064892;
    if (perf->struct_size == 0u) {
        perf->struct_size = sizeof(*perf);
        perf->abi_version = XSTAR_SPECTRAL_PERF_V064892_ABI_VERSION;
    }
    return 0;
}

void xstar_spectral_type50_vector_perf_reset_v064812324(void) {
    g_type50_vectorized_profiles_v064812324 = 0u;
    g_type50_scalar_profiles_v064812324 = 0u;
}

void xstar_spectral_type50_vector_perf_snapshot_v064812324(
    std::uint64_t* vectorized_profiles, std::uint64_t* scalar_profiles) {
    if (vectorized_profiles) *vectorized_profiles = g_type50_vectorized_profiles_v064812324;
    if (scalar_profiles) *scalar_profiles = g_type50_scalar_profiles_v064812324;
}

void xstar_spectral_type50_phase_perf_reset_v064812326(void) {
    xstar_opacity_type50_phase_perf_reset_v064812326();
}

void xstar_spectral_type50_perf_reset_v064812327(void) {
    xstar_opacity_type50_perf_reset_v064812327();
}


void xstar_spectral_type50_perf_reset_v064812328(void) {
    xstar_opacity_type50_perf_reset_v064812328();
}

void xstar_spectral_type50_perf_reset_v064812329(void) {
    xstar_opacity_type50_perf_reset_v064812329();
}

void xstar_spectral_type50_perf_snapshot_v064812329(
    std::uint64_t* register_profiles, std::uint64_t* hint_profiles,
    std::uint64_t* consumed_points, std::uint64_t* boundary_true_points,
    std::uint64_t* boundary_false_points, std::uint64_t* boundary_events,
    std::uint64_t* output_bins_advanced, std::uint64_t* max_bins_per_event) {
    xstar_opacity_type50_perf_snapshot_v064812329(
        register_profiles, hint_profiles, consumed_points, boundary_true_points,
        boundary_false_points, boundary_events, output_bins_advanced, max_bins_per_event);
}

void xstar_spectral_type50_perf_reset_v064812330(void) {
    xstar_opacity_type50_perf_reset_v064812330();
}

void xstar_spectral_type50_perf_snapshot_v064812330(
    std::uint64_t* prod_hint_profiles, std::uint64_t* fallback_12328_profiles,
    std::uint64_t* next_epi_profiles, std::uint64_t* local_bins_profiles,
    std::uint64_t* cursor_profiles) {
    xstar_opacity_type50_perf_snapshot_v064812330(
        prod_hint_profiles, fallback_12328_profiles, next_epi_profiles,
        local_bins_profiles, cursor_profiles);
}

void xstar_spectral_type50_perf_reset_v064812331(void) {
    xstar_opacity_type50_perf_reset_v064812331();
}

void xstar_spectral_type50_perf_snapshot_v064812331(
    std::uint64_t* prod_cursor_profiles, std::uint64_t* fallback_hint_profiles,
    std::uint64_t* decomp_profiles, std::uint64_t* decomp_avx2_points,
    std::uint64_t* decomp_scalar_points, std::uint64_t* decomp_boundary_events,
    std::uint64_t* decomp_opakc_bins, double* decomp_avx2_seconds,
    double* decomp_scalar_seconds, double* decomp_trapezoid_seconds,
    double* decomp_boundary_rebin_seconds, double* decomp_opakc_seconds) {
    xstar_opacity_type50_perf_snapshot_v064812331(
        prod_cursor_profiles, fallback_hint_profiles, decomp_profiles,
        decomp_avx2_points, decomp_scalar_points, decomp_boundary_events,
        decomp_opakc_bins, decomp_avx2_seconds, decomp_scalar_seconds,
        decomp_trapezoid_seconds, decomp_boundary_rebin_seconds,
        decomp_opakc_seconds);
}

void xstar_spectral_type50_perf_snapshot_v064812328(
    std::uint64_t* prod_avx2_profiles, std::uint64_t* prod_scalar_profiles,
    std::uint64_t* prod_avx2_blocks, std::uint64_t* prod_avx2_points,
    std::uint64_t* prod_scalar_profile_points, std::uint64_t* ncut4_profiles,
    std::uint64_t* ncut4_fast_blocks, std::uint64_t* ncut4_boundary_fallback_blocks,
    std::uint64_t* ncut4_fast_points, std::uint64_t* decomp_profiles,
    std::uint64_t* decomp_avx2_points, std::uint64_t* decomp_scalar_points,
    double* decomp_avx2_profile_seconds, double* decomp_scalar_profile_seconds,
    double* decomp_consume_seconds) {
    xstar_opacity_type50_perf_snapshot_v064812328(
        prod_avx2_profiles, prod_scalar_profiles, prod_avx2_blocks, prod_avx2_points,
        prod_scalar_profile_points, ncut4_profiles, ncut4_fast_blocks,
        ncut4_boundary_fallback_blocks, ncut4_fast_points, decomp_profiles,
        decomp_avx2_points, decomp_scalar_points, decomp_avx2_profile_seconds,
        decomp_scalar_profile_seconds, decomp_consume_seconds);
}

void xstar_spectral_type50_perf_snapshot_v064812327(
    std::uint64_t* schedule_profiles, std::uint64_t* cache_hits,
    std::uint64_t* cache_misses, std::uint64_t* cache_uncached,
    std::uint64_t* distinct_cached_keys, std::uint64_t* cache_bytes,
    std::uint64_t* cached_events, double* schedule_build_seconds,
    std::uint64_t* ncut_histogram, std::size_t ncut_histogram_len,
    std::uint64_t* gaussian_points, std::uint64_t* small_a_core_points,
    std::uint64_t* small_a_farwing_points, std::uint64_t* large_a_points,
    std::uint64_t* inline_avx2_profiles, std::uint64_t* inline_avx2_blocks,
    std::uint64_t* inline_avx2_points, std::uint64_t* inline_scalar_points) {
    xstar_opacity_type50_perf_snapshot_v064812327(
        schedule_profiles, cache_hits, cache_misses, cache_uncached,
        distinct_cached_keys, cache_bytes, cached_events, schedule_build_seconds,
        ncut_histogram, ncut_histogram_len, gaussian_points, small_a_core_points,
        small_a_farwing_points, large_a_points, inline_avx2_profiles,
        inline_avx2_blocks, inline_avx2_points, inline_scalar_points);
}

void xstar_spectral_type50_phase_perf_snapshot_v064812326(
    std::uint64_t* phase_profiles, std::uint64_t* span_events, std::uint64_t* span_bins,
    std::uint64_t* vectorizable_span_events, std::uint64_t* vectorizable_span_bins,
    std::uint64_t* max_span, double* profile_value_seconds, double* rebin_seconds,
    double* range_update_seconds, std::uint64_t* range_avx2_profiles,
    std::uint64_t* range_avx2_blocks, std::uint64_t* range_avx2_bins,
    std::uint64_t* range_scalar_bins) {
    xstar_opacity_type50_phase_perf_snapshot_v064812326(
        phase_profiles, span_events, span_bins, vectorizable_span_events,
        vectorizable_span_bins, max_span, profile_value_seconds, rebin_seconds,
        range_update_seconds, range_avx2_profiles, range_avx2_blocks,
        range_avx2_bins, range_scalar_bins);
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
    xstar_spectral_perf_v064892 perf_v064892{};
    xstar_spectral_perf_init_v064892(&perf_v064892);
    perf_v064892.apply_calls = 1u;
    const char* type50_diag_root_v064812321 = std::getenv("XSTAR_V064812321_DIAGNOSTICS_DIR");
    const char* type50_phase_env_v064812321 = std::getenv("XSTAR_V064812321_TYPE50_PHASE");
    const bool type50_diag_active_v064812321 =
        type50_diag_root_v064812321 && *type50_diag_root_v064812321 &&
        type50_phase_env_v064812321 && *type50_phase_env_v064812321;
    const std::string type50_phase_v064812321 =
        type50_diag_active_v064812321 ? std::string(type50_phase_env_v064812321) : std::string();
    const char* type50_seq_env_v064812321 = std::getenv("XSTAR_NATIVE_SOURCE_SEQUENCE");
    const std::string type50_sequence_v064812321 =
        (type50_seq_env_v064812321 && *type50_seq_env_v064812321) ? std::string(type50_seq_env_v064812321) : std::string("0");
    const char* force_legacy_type50_env_v064812322 =
        std::getenv("XSTAR_V0648123220_FORCE_PRE_GATE_FULL_LINE_TYPE50");
    const bool force_legacy_type50_v064812322 =
        force_legacy_type50_env_v064812322 && *force_legacy_type50_env_v064812322 &&
        std::strcmp(force_legacy_type50_env_v064812322, "0") != 0;
    std::uint64_t type50_rows_v064812321 = 0u;
    std::uint64_t type50_source_inner_accepts_v064812321 = 0u;
    std::uint64_t type50_actual_profile_calls_v064812321 = 0u;
    std::uint64_t type50_source_rejected_but_called_v064812321 = 0u;
    std::uint64_t type50_updated_bins_v064812321 = 0u;
    std::uint64_t type50_rejected_call_updated_bins_v064812321 = 0u;
    double type50_profile_seconds_v064812321 = 0.0;
    double type50_rejected_call_seconds_v064812321 = 0.0;
    uint64_t previous_position = 0;
    const size_t line_capacity = workspace->oplin_count;
    const size_t continuum_capacity = workspace->opakab_count;
    const size_t rcem_stride = workspace->rcem_count / 2;
    const size_t cemab_stride = workspace->cemab_count / 2;
    const size_t fline_stride = workspace->fline_count / 2;
    for (size_t i = 0; i < contribution_count; ++i) {
        const xstar_spectral_contribution_v1& c = contributions[i];
        ++stats->contributions_attempted;
        ++perf_v064892.contributions;
        const std::size_t family_slot_v064892 = spectral_family_slot_v064892(c.data_type);
        ++perf_v064892.family_contributions[family_slot_v064892];
        switch (c.kind) {
            case XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE: ++perf_v064892.kind_bound_free; break;
            case XSTAR_SPECTRAL_KIND_EMISAB_LINE: ++perf_v064892.kind_emisab_line; break;
            case XSTAR_SPECTRAL_KIND_EMIS_OPACITY_ONLY: ++perf_v064892.kind_opacity_only; break;
            case XSTAR_SPECTRAL_KIND_EMIS_LINE: ++perf_v064892.kind_emis_line; break;
            case XSTAR_SPECTRAL_KIND_FULL_LINE: ++perf_v064892.kind_full_line; break;
            default: break;
        }
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
        } else if (c.kind == XSTAR_SPECTRAL_KIND_EMISAB_LINE ||
                   c.kind == XSTAR_SPECTRAL_KIND_FULL_LINE) {
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
                // calc_emisab_ion defines abund2 as level population times
                // elemental abundance times xpx.  Keep rcem in the same
                // volumetric units; omitting xpx suppressed every line
                // luminosity by the hydrogen density (1e8 in this case).
                workspace->rcem[index] = -c.abundance_upper * c.hydrogen_density *
                    c.ans3 * c.ptmp1 / denom;
                workspace->rcem[rcem_stride + index] = -c.abundance_upper * c.hydrogen_density *
                    c.ans3 * c.ptmp2 / denom;
                // Source linopac consumes cm^-1 line opacity.  Type-50 opakab is a
                // cross section, while abundance_lower is the dimensionless
                // level population times elemental abundance.  The previous
                // native path omitted xpx (hydrogen density), suppressing
                // line opacity by approximately 1e8 in this benchmark and
                // corrupting opakc, dpthc, option-17 h-c, and option-5 energy
                // absorption.
                workspace->oplin[index] = c.opakab * c.abundance_lower * c.hydrogen_density;
                ++stats->emissivity_contributions;
                ++stats->opacity_contributions;
                if (c.kind == XSTAR_SPECTRAL_KIND_FULL_LINE) {
                    if (static_cast<size_t>(index) >= fline_stride ||
                        c.bin_one_based <= 0 || static_cast<size_t>(c.bin_one_based) > workspace->flinel_count ||
                        !(c.bin_width_eV > 0.0)) {
                        write_message(error, error_size, "full line profile index or width invalid");
                        return 7;
                    }
                    const double net = (c.ans2 * c.abundance_upper -
                        c.ans1 * c.abundance_lower) * c.hydrogen_density;
                    const double erg_per_ev = 1.602176634e-12;
                    const double line1 = std::max(net * c.line_energy_eV * erg_per_ev * c.ptmp1, 0.0);
                    const double line2 = std::max(net * c.line_energy_eV * erg_per_ev * c.ptmp2, 0.0);
                    workspace->fline[index] = line1;
                    workspace->fline[fline_stride + index] = line2;
                    workspace->flinel[c.bin_one_based - 1] +=
                        (line1 + line2) * 2.0 / c.bin_width_eV / erg_per_ev;
                    const double* seed = nullptr;
                    int seed_radius = 0;
                    const bool exact_grid_oracle =
                        seed_profiles && seed_profile_stride == XSTAR_SPECTRAL_EXACT_GRID_STRIDE;
                    if (seed_profiles && (exact_grid_oracle ||
                        (seed_profile_stride >= 21 && (seed_profile_stride % 2) == 1))) {
                        seed = seed_profiles + i * seed_profile_stride;
                        if (!exact_grid_oracle) seed_radius = static_cast<int>((seed_profile_stride - 1) / 2);
                    }
                    if (!seed || (!exact_grid_oracle && seed_radius < 10)) {
                        write_message(error, error_size, "full line contribution lacks valid seed or exact-grid oracle");
                        return 9;
                    }
                    const double opakb1_v064812321 = c.opakab * c.abundance_lower * c.hydrogen_density;
                    const bool source_inner_accept_v064812321 =
                        source_type50_linopac_accept(opakb1_v064812321, c.data_type, c.rate_type);
                    const bool source_type50_family_v064812322 =
                        source_type50_linopac_family(c.data_type, c.rate_type);
                    if (type50_diag_active_v064812321 && source_type50_family_v064812322) {
                        ++type50_rows_v064812321;
                        type50_source_inner_accepts_v064812321 += source_inner_accept_v064812321 ? 1u : 0u;
                    }
                    // FORTRAN ucalc computes/publishes the scalar line state above,
                    // but it does not call linopac when the Type-50 opacity is below
                    // the default-REAL 1.e-34 threshold.  Apply that exact rule in
                    // the shared FULL_LINE path for every element.  The environment
                    // override exists only for same-binary A/B qualification.
                    if (source_type50_family_v064812322 &&
                        !source_inner_accept_v064812321 &&
                        !force_legacy_type50_v064812322) {
                        continue;
                    }
                    long long updated = 0;
                    double opacity_elapsed = 0.0;
                    char opacity_error[512] = {0};
                    const int profile_rc = exact_grid_oracle
                        ? xstar_opacity_apply_exact_grid_v1(
                            seed, workspace->epi_eV, static_cast<int>(workspace->energy_count),
                            workspace->opakc, workspace->rccemis, &updated, &opacity_elapsed,
                            opacity_error, sizeof(opacity_error))
                        : apply_line_profile_dispatch_v064812326(
                            c.opakab * c.abundance_lower * c.hydrogen_density,
                            c.line_energy_eV, c.turbulent_velocity_km_s,
                            c.temperature_1e4K, c.atomic_mass_amu, c.natural_width_eV,
                            seed, seed_radius, workspace->epi_eV,
                            static_cast<int>(workspace->energy_count), workspace->opakc,
                            workspace->rccemis, &updated, &opacity_elapsed,
                            opacity_error, sizeof(opacity_error));
                    if (profile_rc != 0) {
                        write_message(error, error_size, opacity_error);
                        return 10;
                    }
                    if (!exact_grid_oracle && c.data_type == 50 && c.rate_type == 4) {
                        if (xstar_opacity_last_profile_vectorized_v064812324())
                            ++g_type50_vectorized_profiles_v064812324;
                        else
                            ++g_type50_scalar_profiles_v064812324;
                    }
                    if (type50_diag_active_v064812321 && source_type50_family_v064812322) {
                        ++type50_actual_profile_calls_v064812321;
                        type50_updated_bins_v064812321 += static_cast<std::uint64_t>(std::max<long long>(0, updated));
                        type50_profile_seconds_v064812321 += opacity_elapsed;
                        if (!source_inner_accept_v064812321) {
                            ++type50_source_rejected_but_called_v064812321;
                            type50_rejected_call_updated_bins_v064812321 += static_cast<std::uint64_t>(std::max<long long>(0, updated));
                            type50_rejected_call_seconds_v064812321 += opacity_elapsed;
                        }
                    }
                    ++stats->line_profiles;
                    ++perf_v064892.line_profiles;
                    ++perf_v064892.family_line_profiles[family_slot_v064892];
                    perf_v064892.updated_continuum_bins += static_cast<uint64_t>(std::max<long long>(0, updated));
                    perf_v064892.family_updated_bins[family_slot_v064892] += static_cast<uint64_t>(std::max<long long>(0, updated));
                    perf_v064892.profile_kernel_seconds += opacity_elapsed;
                    perf_v064892.family_profile_seconds[family_slot_v064892] += opacity_elapsed;
                    if (exact_grid_oracle) {
                        ++perf_v064892.exact_grid_profiles;
                        perf_v064892.exact_grid_profile_seconds += opacity_elapsed;
                        if (seed && seed[0] == XSTAR_SPECTRAL_EXACT_GRID_MAGIC && seed[5] > 0.0)
                            perf_v064892.exact_grid_valid_points += static_cast<uint64_t>(std::llround(seed[5]));
                    } else {
                        ++perf_v064892.native_profile_profiles;
                        perf_v064892.native_profile_seconds += opacity_elapsed;
                    }
                }
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
            // Match ucalc/linopac: convert the Type-50 cross section to cm^-1
            // exactly once with abundance and hydrogen density.
            const double opakb1 = c.opakab * c.abundance_lower * c.hydrogen_density;
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
            // v0.6.48.12.3.14: literal ordinary Type-50 UCalc gate. Source
            // UCalc publishes the scalar line quantities above but calls
            // linopac only when opakb1 exceeds default-REAL 1.e-34.
            if (source_type50_linopac_family(c.data_type, c.rate_type) &&
                !source_type50_linopac_accept(opakb1, c.data_type, c.rate_type)) {
                if (type50_diag_active_v064812321) {
                    ++type50_rows_v064812321;
                }
                continue;
            }
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
                : apply_line_profile_dispatch_v064812326(
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
            if (!exact_grid_oracle && c.data_type == 50 && c.rate_type == 4) {
                if (xstar_opacity_last_profile_vectorized_v064812324())
                    ++g_type50_vectorized_profiles_v064812324;
                else
                    ++g_type50_scalar_profiles_v064812324;
            }
            if (type50_diag_active_v064812321 && source_type50_linopac_family(c.data_type, c.rate_type)) {
                ++type50_rows_v064812321;
                ++type50_source_inner_accepts_v064812321;
                ++type50_actual_profile_calls_v064812321;
                type50_updated_bins_v064812321 += static_cast<std::uint64_t>(std::max<long long>(0, updated));
                type50_profile_seconds_v064812321 += opacity_elapsed;
            }
            ++stats->line_profiles;
            ++perf_v064892.line_profiles;
            ++perf_v064892.family_line_profiles[family_slot_v064892];
            perf_v064892.updated_continuum_bins += static_cast<uint64_t>(std::max<long long>(0, updated));
            perf_v064892.family_updated_bins[family_slot_v064892] += static_cast<uint64_t>(std::max<long long>(0, updated));
            perf_v064892.profile_kernel_seconds += opacity_elapsed;
            perf_v064892.family_profile_seconds[family_slot_v064892] += opacity_elapsed;
            if (exact_grid_oracle) {
                ++perf_v064892.exact_grid_profiles;
                perf_v064892.exact_grid_profile_seconds += opacity_elapsed;
                if (seed && seed[0] == XSTAR_SPECTRAL_EXACT_GRID_MAGIC && seed[5] > 0.0)
                    perf_v064892.exact_grid_valid_points += static_cast<uint64_t>(std::llround(seed[5]));
            } else {
                ++perf_v064892.native_profile_profiles;
                perf_v064892.native_profile_seconds += opacity_elapsed;
            }
        } else {
            write_message(error, error_size, "unsupported native spectral contribution kind");
            return 11;
        }
        const auto construct_ended = std::chrono::steady_clock::now();
        stats->construction_seconds += std::chrono::duration<double>(construct_ended - construct_started).count();
        ++stats->contributions_committed;
    }
    if (type50_diag_active_v064812321) {
        const std::filesystem::path path_v064812321 =
            std::filesystem::path(type50_diag_root_v064812321) / "type50_linopac_apply_summary.csv";
        const bool header_v064812321 = !std::filesystem::exists(path_v064812321);
        std::ofstream diag_v064812321(path_v064812321, std::ios::app);
        if (!diag_v064812321) {
            write_message(error, error_size, "cannot create v064812321 Type50 apply summary");
            return 11;
        }
        if (header_v064812321) {
            diag_v064812321 << "source_sequence,phase,type50_rows,source_inner_accepts,actual_profile_calls,source_rejected_but_called,updated_bins,rejected_call_updated_bins,profile_seconds,rejected_call_seconds,source_real_floor\n";
        }
        diag_v064812321 << std::setprecision(17)
            << type50_sequence_v064812321 << ',' << type50_phase_v064812321 << ','
            << type50_rows_v064812321 << ',' << type50_source_inner_accepts_v064812321 << ','
            << type50_actual_profile_calls_v064812321 << ',' << type50_source_rejected_but_called_v064812321 << ','
            << type50_updated_bins_v064812321 << ',' << type50_rejected_call_updated_bins_v064812321 << ','
            << type50_profile_seconds_v064812321 << ',' << type50_rejected_call_seconds_v064812321 << ','
            << source_real_literal(1.0e-34) << '\n';
    }
    const auto call_ended = std::chrono::steady_clock::now();
    stats->commit_seconds = std::chrono::duration<double>(call_ended - call_started).count();
    perf_v064892.apply_seconds = stats->commit_seconds;
    add_perf_v064892(g_spectral_perf_v064892, perf_v064892);
    add_stats(context->cumulative, *stats);
    write_message(error, error_size, "native spectral contributions applied");
    return 0;
}

} // extern "C"
