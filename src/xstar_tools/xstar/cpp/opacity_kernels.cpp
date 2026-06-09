#include "xstar_backend_common.hpp"

#include <algorithm>
#include <cmath>
#include <chrono>
#include <cstddef>
#include <cstring>
#include <sstream>
#include <vector>

namespace {

static void write_message(char* message, std::size_t message_size, const char* text) {
    if (!message || message_size == 0) return;
    std::strncpy(message, text ? text : "", message_size - 1);
    message[message_size - 1] = '\0';
}

static double voigte(double vs, double a) {
    static const double ak[19] = {
        -1.12470432, -0.15516677, 3.28867591, -2.34357915, 0.42139162,
        -4.48480194, 9.39456063, -6.61487486, 1.98919585, -0.22041650,
        0.554153432, 0.278711796, -0.188325687, 0.042991293,
        -0.003278278, 0.979895023, -0.962846325, 0.532770573,
        -0.122727278
    };
    const double sqp = 1.772453851;
    const double sq2 = 1.414213562;
    const double v = std::abs(vs);
    const double aa = a;
    const double u = aa + v;
    const double v2 = v * v;
    if (aa == 0.0) return v2 >= 100.0 ? 0.0 : std::exp(-v2);
    if (aa <= 0.2 && v >= 5.0) {
        return aa * (15.0 + 6.0 * v2 + 4.0 * v2 * v2) /
               (4.0 * std::pow(v2, 3.0) * sqp);
    }
    if (aa > 1.4 || u > 3.2) {
        const double a2 = aa * aa;
        const double uu = sq2 * (a2 + v2);
        const double u2 = 1.0 / (uu * uu);
        return sq2 / sqp * aa / uu *
               (1.0 + u2 * (3.0 * v2 - a2) +
                u2 * u2 * (15.0 * v2 * v2 - 30.0 * v2 * a2 + 3.0 * a2 * a2));
    }
    const double ex = v2 >= 100.0 ? 0.0 : std::exp(-v2);
    double quo = 1.0;
    int start = 0;
    if (v >= 2.4) {
        quo = 1.0 / (v2 - 1.5);
        start = 10;
    } else if (v >= 1.3) {
        start = 5;
    }
    const double h1 = quo * (ak[start] + v * (ak[start + 1] +
        v * (ak[start + 2] + v * (ak[start + 3] + v * ak[start + 4]))));
    if (aa <= 0.2) return h1 * aa + ex * (1.0 + aa * aa * (1.0 - 2.0 * v2));
    const double pqs = 2.0 / sqp;
    const double h1p = h1 + pqs * ex;
    const double h2p = pqs * h1p - 2.0 * v2 * ex;
    const double h3p = (pqs * (1.0 - ex * (1.0 - 2.0 * v2)) - 2.0 * v2 * h1p) / 3.0 + pqs * h2p;
    const double h4p = (2.0 * v2 * v2 * ex - pqs * h1p) / 3.0 + pqs * h3p;
    const double psi = ak[15] + aa * (ak[16] + aa * (ak[17] + aa * ak[18]));
    return psi * (ex + aa * (h1p + aa * (h2p + aa * (h3p + aa * h4p))));
}

static int huntf(const double* xx, int n, double x) {
    if (!xx || n < 2) return 1;
    const double floor = 1.0e-24;
    const double xx1 = xx[0];
    const double xx2 = xx[1];
    const double xxn = xx[n - 1];
    const double xtmp = std::max(x, xx2);
    if (x < floor || xx1 <= floor || xxn <= floor) return 1;
    int jlo = static_cast<int>((n - 1) * std::log(xtmp / xx1) / std::log(xxn / xx1)) + 1;
    if (jlo < n) {
        const double tst = std::abs(std::log(x / (floor + xx[jlo - 1])));
        const double tst2 = std::abs(std::log(x / (floor + xx[jlo])));
        if (tst2 < tst) ++jlo;
    }
    return std::max(1, std::min(n, jlo));
}

static int nbinc(double e, const double* epi, int ncn2) {
    const int numcon2 = std::max(2, ncn2 / 50);
    const int numcon3 = ncn2 - numcon2;
    return numcon3 < 2 ? 1 : huntf(epi, numcon3, e);
}

} // namespace

extern "C" {

int xstar_opacity_abi_version() { return 60460; }

const char* xstar_opacity_backend_name() {
    return "xstar_opacity_native_line_profile_v0646";
}

int xstar_opacity_feature_flags() {
    return 1 | 2 | 4;
}

int xstar_opacity_probe(int n_records, char* message, std::size_t message_size) {
    if (!xstar_backend::valid_count(n_records)) {
        xstar_backend::write_message(message, message_size, "invalid negative n_records");
        return xstar_backend::XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    std::ostringstream out;
    out << "libxstar_opacity.so native line-profile backend available; n_records=" << n_records;
    xstar_backend::write_message(message, message_size, out.str());
    return xstar_backend::XSTAR_BACKEND_OK;
}

int xstar_opacity_apply_line_profile_v1(
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
) {
    const auto started = std::chrono::steady_clock::now();
    if (!seed_profiles || !epi || !opakc || !rccemis || !updated_bins || !opacity_seconds) {
        write_message(errbuf, errbuf_size, "null pointer passed to xstar_opacity_apply_line_profile_v1");
        return 3;
    }
    const int n = ncn2;
    if (n < 3 || seed_radius < 0 || !std::isfinite(optpp) || !std::isfinite(line_energy_ev) ||
        !std::isfinite(vturb_km_s) || !std::isfinite(temperature_1e4k) ||
        !std::isfinite(atomic_mass_amu) || !std::isfinite(natural_width_ev)) {
        write_message(errbuf, errbuf_size, "invalid input to xstar_opacity_apply_line_profile_v1");
        return 4;
    }
    *updated_bins = 0;
    *opacity_seconds = 0.0;
    if (optpp <= 0.0 || line_energy_ev <= epi[0] || line_energy_ev >= epi[n - 1]) {
        write_message(errbuf, errbuf_size, "native opacity profile no-op");
        return 0;
    }
    const int nbtpp = 20000;
    const double dpcrit = 1.0e-6;
    int ml1 = nbinc(line_energy_ev, epi, n);
    ml1 = std::max(2, std::min(n - 1, ml1));
    const double mass = std::max(atomic_mass_amu, 1.0e-30);
    const double vth = 12.9 * std::sqrt(temperature_1e4k / mass);
    const double deleturb = line_energy_ev * (vturb_km_s / 3.0e5);
    const double deleth = line_energy_ev * (vth / 3.0e5);
    const double dele = std::sqrt(deleth * deleth + deleturb * deleturb);
    if (dele <= 0.0) {
        write_message(errbuf, errbuf_size, "native opacity profile zero-width no-op");
        return 0;
    }
    const double aasmall = natural_width_ev / (1.0e-24 + dele) / 12.56;
    const bool use_voigt = aasmall > 1.0e-9;
    const double e00 = epi[ml1 - 1];
    const double deleepi = epi[ml1] - epi[ml1 - 1];
    int ncut = static_cast<int>(deleepi / dele);
    ncut = std::max(1, std::min(nbtpp / 10, ncut));
    const double deleused = deleepi / static_cast<double>(ncut);
    int mlc = 0, ldir = 1, ldon0 = 0, ldon1 = 0;
    int mlmin = nbtpp, mlmax = 1, ml1min = n + 1, ml1max = 0;
    const int ml2 = nbtpp / 2;
    std::vector<double> etpp(static_cast<std::size_t>(nbtpp), 0.0);
    std::vector<double> optpp2(static_cast<std::size_t>(nbtpp), 0.0);
    double delet = (e00 - line_energy_ev) / dele;
    double profile = seed_profiles[0];
    etpp[ml2 - 1] = e00;
    optpp2[ml2 - 1] = optpp * profile;
    double tst = 1.0;
    while ((ldon0 * ldon1 == 0) && mlc < nbtpp / 2) {
        ++mlc;
        for (int ij = 0; ij < 2; ++ij) {
            ldir = -ldir;
            int& ldon = (ij == 0) ? ldon0 : ldon1;
            if (ldon == 1) continue;
            const int mlm = ml2 + ldir * mlc;
            const double etptst = e00 + static_cast<double>(ldir * mlc) * deleused;
            if (mlm <= nbtpp && mlm >= 1 && etptst > 0.0 && etptst < epi[n - 1]) {
                mlmin = std::min(mlmin, mlm);
                mlmax = std::max(mlmax, mlm);
                etpp[mlm - 1] = etptst;
                delet = (etptst - line_energy_ev) / dele;
                if (mlc <= seed_radius) {
                    const int seed_index = 2 * mlc - ((ldir < 0) ? 1 : 0);
                    profile = seed_profiles[seed_index];
                } else {
                    profile = use_voigt ? voigte(std::abs(delet), aasmall) / 1.772
                                         : std::exp(-delet * delet) / 1.772;
                }
                optpp2[mlm - 1] = optpp * profile;
                tst = profile;
            }
            const double delet_now = (etptst - line_energy_ev) / dele;
            if ((tst < dpcrit || mlm <= 1 || mlm >= nbtpp || etptst <= 0.0 ||
                 etptst >= epi[n - 1] || std::abs(delet_now) > std::max(50.0, 200.0 * aasmall)) &&
                ml1min < ml1 - 2 && ml1max > ml1 + 2 && ml1min >= 1 && ml1max <= n) {
                ldon = 1;
            }
        }
    }
    if (mlmin <= mlmax) {
        ml1min = nbinc(etpp[mlmin - 1], epi, n);
        ml1max = nbinc(etpp[mlmax - 1], epi, n);
        int ml1m = ml1min;
        mlmin = std::max(2, mlmin);
        mlmax = std::min(nbtpp, mlmax);
        double sume = 0.0, opsum = 0.0, tmpop = 0.0;
        for (int mlm = mlmin + 1; mlm <= mlmax; ++mlm) {
            const double tmpopo = tmpop;
            tmpop = optpp2[mlm - 1];
            const double tmpe = std::abs(etpp[mlm - 1] - etpp[mlm - 2]);
            sume += tmpe;
            opsum += (tmpop + tmpopo) * tmpe / 2.0;
            if (etpp[mlm - 1] > epi[ml1m - 1]) {
                if (sume > 1.0e-34) {
                    const double optp2 = opsum / sume;
                    while (etpp[mlm - 1] > epi[ml1m - 1] && ml1m < n) {
                        opakc[ml1m - 1] += optp2;
                        rccemis[ml1m - 1] += 0.0;
                        rccemis[n + ml1m - 1] += 0.0;
                        ++(*updated_bins);
                        ++ml1m;
                    }
                }
                opsum = 0.0;
                sume = 0.0;
            }
        }
    }
    const auto ended = std::chrono::steady_clock::now();
    *opacity_seconds = std::chrono::duration<double>(ended - started).count();
    write_message(errbuf, errbuf_size, use_voigt ? "native opacity voigt profile applied" : "native opacity gaussian profile applied");
    return 0;
}

} // extern "C"
