#include "xstar_backend_common.hpp"
#include "xstar_spectral_engine.h"
#include "xstar_constants.h"

#include <algorithm>
#include <cmath>
#include <chrono>
#include <cfloat>
#include <cstddef>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <memory>
#include <sstream>
#include <vector>

#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
#include <immintrin.h>
#endif

namespace {

#if defined(__FAST_MATH__)
#error "opacity_kernels.cpp requires strict IEEE arithmetic; do not compile with -ffast-math"
#endif

// v0.6.48.9.3 Type-50 performance fast path.  This translation unit is
// compiled with -ffp-contract=off and without fast-math.  On platforms where
// FLT_EVAL_METHOD==0, each scalar binary64 operation already rounds to double
// at the source statement, so the former volatile store/load barriers were
// redundant and accounted for a large fraction of the 749-million-bin profile
// workload.  Preserve the historical barriers automatically on targets that
// evaluate expressions with excess precision.
#if FLT_EVAL_METHOD == 0 && !defined(XSTAR_V064893_LEGACY_FP_BARRIERS)
static inline double source_add(double a, double b) { return a + b; }
static inline double source_sub(double a, double b) { return a - b; }
static inline double source_mul(double a, double b) { return a * b; }
static inline double source_div(double a, double b) { return a / b; }
#else
static inline double source_add(double a, double b) { volatile double x = a; volatile double y = b; volatile double z = x + y; return z; }
static inline double source_sub(double a, double b) { volatile double x = a; volatile double y = b; volatile double z = x - y; return z; }
static inline double source_mul(double a, double b) { volatile double x = a; volatile double y = b; volatile double z = x * y; return z; }
static inline double source_div(double a, double b) { volatile double x = a; volatile double y = b; volatile double z = x / y; return z; }
#endif
static inline double source_real_literal(double value) { return static_cast<double>(static_cast<float>(value)); }


// v0.6.48.12.3.24: generic Type-50 profile diagnostics and AVX2 capability.
// These counters are observational only; they never enter science state.
thread_local std::uint64_t g_type50_vectorized_profiles_v064812324 = 0u;
thread_local std::uint64_t g_type50_scalar_profiles_v064812324 = 0u;
thread_local std::uint64_t g_type50_vectorized_points_v064812324 = 0u;
thread_local std::uint64_t g_type50_bound_correction_steps_v064812324 = 0u;
thread_local int g_last_profile_vectorized_v064812324 = 0;

static bool env_truthy_v064812324(const char* name) {
    const char* value = std::getenv(name);
    return value && *value && std::strcmp(value, "0") != 0 &&
        std::strcmp(value, "false") != 0 && std::strcmp(value, "FALSE") != 0;
}

static bool cpu_avx2_available_v064812324() {
#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
    static const bool available = [] {
        __builtin_cpu_init();
        return __builtin_cpu_supports("avx2");
    }();
    return available;
#else
    return false;
#endif
}

#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
__attribute__((target("avx2")))
static inline void voigte_small_a_farwing4_v064812324(
    const double* v, double aa, double* out) {
    const __m256d vv = _mm256_loadu_pd(v);
    const __m256d v2 = _mm256_mul_pd(vv, vv);
    const __m256d v2sq = _mm256_mul_pd(v2, v2);
    const __m256d term6 = _mm256_mul_pd(_mm256_set1_pd(source_real_literal(6.0)), v2);
    const __m256d term4 = _mm256_mul_pd(_mm256_set1_pd(source_real_literal(4.0)), v2sq);
    const __m256d num0 = _mm256_add_pd(_mm256_set1_pd(source_real_literal(15.0)), term6);
    const __m256d num = _mm256_add_pd(num0, term4);
    const __m256d den0 = _mm256_mul_pd(_mm256_set1_pd(source_real_literal(4.0)), v2);
    const __m256d den1 = _mm256_mul_pd(den0, v2);
    const __m256d den2 = _mm256_mul_pd(den1, v2);
    const __m256d den = _mm256_mul_pd(den2, _mm256_set1_pd(source_real_literal(1.772453851)));
    const __m256d scaled = _mm256_mul_pd(_mm256_set1_pd(aa), num);
    _mm256_storeu_pd(out, _mm256_div_pd(scaled, den));
}
#endif

static void write_message(char* message, std::size_t message_size, const char* text) {
    if (!message || message_size == 0) return;
    std::strncpy(message, text ? text : "", message_size - 1);
    message[message_size - 1] = '\0';
}

static double voigte(double vs, double a) {
    // Literal voigte.f90 declares all working values REAL(8), but its DATA,
    // PARAMETER, and branch literals are default REAL.  Preserve the
    // binary32 rounding of those source literals before promotion to double.
    static const double ak[19] = {
        source_real_literal(-1.12470432), source_real_literal(-0.15516677),
        source_real_literal(3.28867591), source_real_literal(-2.34357915),
        source_real_literal(0.42139162), source_real_literal(-4.48480194),
        source_real_literal(9.39456063), source_real_literal(-6.61487486),
        source_real_literal(1.98919585), source_real_literal(-0.22041650),
        source_real_literal(0.554153432), source_real_literal(0.278711796),
        source_real_literal(-0.188325687), source_real_literal(0.042991293),
        source_real_literal(-0.003278278), source_real_literal(0.979895023),
        source_real_literal(-0.962846325), source_real_literal(0.532770573),
        source_real_literal(-0.122727278)
    };
    const double un = source_real_literal(1.0);
    const double two = source_real_literal(2.0);
    const double sqp = source_real_literal(1.772453851);
    const double sq2 = source_real_literal(1.414213562);
    const double v = std::abs(vs);
    const double aa = a;
    const double u = aa + v;
    const double v2 = v * v;
    if (aa == source_real_literal(0.0))
        return v2 >= source_real_literal(100.0) ? 0.0 : std::exp(-v2);
    if (aa <= source_real_literal(0.2) && v >= source_real_literal(5.0)) {
        return aa * (source_real_literal(15.0) + source_real_literal(6.0) * v2 +
                     source_real_literal(4.0) * v2 * v2) /
               (source_real_literal(4.0) * v2 * v2 * v2 * sqp);
    }
    // voigte.f90 label 120 is entered only after the a>0.2 test.  Do not
    // apply the u>3.2 asymptotic branch to small-a line cores.
    if (aa > source_real_literal(0.2) && (aa > source_real_literal(1.4) || u > source_real_literal(3.2))) {
        const double a2 = aa * aa;
        const double uu = sq2 * (a2 + v2);
        const double u2 = un / (uu * uu);
        return sq2 / sqp * aa / uu *
               (un + u2 * (source_real_literal(3.0) * v2 - a2) +
                u2 * u2 * (source_real_literal(15.0) * v2 * v2 -
                           source_real_literal(30.0) * v2 * a2 +
                           source_real_literal(3.0) * a2 * a2));
    }
    const double ex = v2 >= source_real_literal(100.0) ? 0.0 : std::exp(-v2);
    double quo = un;
    int start = 0;
    if (v >= source_real_literal(2.4)) {
        quo = un / (v2 - source_real_literal(1.5));
        start = 10;
    } else if (v >= source_real_literal(1.3)) {
        start = 5;
    }
    const double h1 = quo * (ak[start] + v * (ak[start + 1] +
        v * (ak[start + 2] + v * (ak[start + 3] + v * ak[start + 4]))));
    if (aa <= source_real_literal(0.2))
        return h1 * aa + ex * (un + aa * aa * (un - two * v2));
    const double pqs = two / sqp;
    const double h1p = h1 + pqs * ex;
    const double h2p = pqs * h1p - two * v2 * ex;
    const double h3p = (pqs * (un - ex * (un - two * v2)) - two * v2 * h1p) /
        source_real_literal(3.0) + pqs * h2p;
    const double h4p = (two * v2 * v2 * ex - pqs * h1p) /
        source_real_literal(3.0) + pqs * h3p;
    const double psi = ak[15] + aa * (ak[16] + aa * (ak[17] + aa * ak[18]));
    return psi * (ex + aa * (h1p + aa * (h2p + aa * (h3p + aa * h4p))));
}

// v0.6.48.9.6 specialization for the overwhelmingly common Type-50
// damping regime 0 < a <= 0.2.  It is the identical branch of voigte.f90
// with the invariant a-tests removed; arithmetic association is deliberately
// unchanged so each returned binary64 value is bit-identical to voigte().
static inline double voigte_small_a_positive_v064896(double v, double aa) {
    static const double ak[15] = {
        source_real_literal(-1.12470432), source_real_literal(-0.15516677),
        source_real_literal(3.28867591), source_real_literal(-2.34357915),
        source_real_literal(0.42139162), source_real_literal(-4.48480194),
        source_real_literal(9.39456063), source_real_literal(-6.61487486),
        source_real_literal(1.98919585), source_real_literal(-0.22041650),
        source_real_literal(0.554153432), source_real_literal(0.278711796),
        source_real_literal(-0.188325687), source_real_literal(0.042991293),
        source_real_literal(-0.003278278)
    };
    const double un = source_real_literal(1.0);
    const double two = source_real_literal(2.0);
    const double sqp = source_real_literal(1.772453851);
    const double v2 = v * v;
    if (v >= source_real_literal(5.0)) {
        return aa * (source_real_literal(15.0) + source_real_literal(6.0) * v2 +
                     source_real_literal(4.0) * v2 * v2) /
               (source_real_literal(4.0) * v2 * v2 * v2 * sqp);
    }
    const double ex = v2 >= source_real_literal(100.0) ? 0.0 : std::exp(-v2);
    double quo = un;
    int start = 0;
    if (v >= source_real_literal(2.4)) {
        quo = un / (v2 - source_real_literal(1.5));
        start = 10;
    } else if (v >= source_real_literal(1.3)) {
        start = 5;
    }
    const double h1 = quo * (ak[start] + v * (ak[start + 1] +
        v * (ak[start + 2] + v * (ak[start + 3] + v * ak[start + 4]))));
    return h1 * aa + ex * (un + aa * aa * (un - two * v2));
}

static int huntf(const double* xx, int n, double x) {
    if (!xx || n < 2) return 1;
    const double floor = source_real_literal(1.0e-34);
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
    return "xstar_opacity_exact_grid_qualification_v06472";
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

int xstar_opacity_apply_exact_grid_v1(
    const double* packed_grid,
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
    if (!packed_grid || !epi || !opakc || !rccemis || !updated_bins || !opacity_seconds) {
        write_message(errbuf, errbuf_size, "null pointer passed to exact-grid opacity oracle");
        return 3;
    }
    const int n = ncn2;
    if (n < 3 || packed_grid[0] != XSTAR_SPECTRAL_EXACT_GRID_MAGIC) {
        write_message(errbuf, errbuf_size, "invalid exact-grid opacity oracle");
        return 4;
    }
    const int mlmin_header = static_cast<int>(std::llround(packed_grid[1]));
    const int mlmax_header = static_cast<int>(std::llround(packed_grid[2]));
    const int ml1min_header = static_cast<int>(std::llround(packed_grid[3]));
    const int ml1max_header = static_cast<int>(std::llround(packed_grid[4]));
    const long long valid_points = static_cast<long long>(std::llround(packed_grid[5]));
    (void)ml1max_header;
    *updated_bins = 0;
    *opacity_seconds = 0.0;
    if (valid_points <= 0 || mlmin_header > mlmax_header) {
        write_message(errbuf, errbuf_size, "exact-grid opacity oracle no-op");
        return 0;
    }
    if (mlmin_header < 1 || mlmax_header > static_cast<int>(XSTAR_SPECTRAL_EXACT_GRID_POINTS) ||
        ml1min_header < 1 || ml1min_header > n) {
        write_message(errbuf, errbuf_size, "exact-grid opacity oracle header out of range");
        return 4;
    }
    const double* etpp = packed_grid + XSTAR_SPECTRAL_EXACT_GRID_HEADER_VALUES;
    const double* optpp2 = etpp + XSTAR_SPECTRAL_EXACT_GRID_POINTS;
    int mlmin = std::max(2, mlmin_header);
    const int mlmax = std::min(static_cast<int>(XSTAR_SPECTRAL_EXACT_GRID_POINTS), mlmax_header);
    int ml1m = ml1min_header;
    double sume = 0.0;
    double opsum = 0.0;
    double tmpop = 0.0;
    for (int mlm = mlmin + 1; mlm <= mlmax; ++mlm) {
        const double tmpopo = tmpop;
        tmpop = optpp2[mlm - 1];
        const double tmpe = std::abs(source_sub(etpp[mlm - 1], etpp[mlm - 2]));
        sume = source_add(sume, tmpe);
        const double pair = source_add(tmpop, tmpopo);
        const double weighted = source_mul(pair, tmpe);
        const double interval = source_div(weighted, 2.0);
        opsum = source_add(opsum, interval);
        if (etpp[mlm - 1] > epi[ml1m - 1]) {
            if (sume > 1.0e-34) {
                const double raw_optp2 = source_div(opsum, sume);
                const double optp2 = std::isfinite(raw_optp2) && raw_optp2 > 0.0 ? raw_optp2 : 0.0;
                while (etpp[mlm - 1] > epi[ml1m - 1] && ml1m < n) {
                    const double current = std::isfinite(opakc[ml1m - 1]) && opakc[ml1m - 1] > 0.0
                        ? opakc[ml1m - 1] : 0.0;
                    opakc[ml1m - 1] = source_add(current, optp2);
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
    const auto ended = std::chrono::steady_clock::now();
    *opacity_seconds = std::chrono::duration<double>(ended - started).count();
    write_message(errbuf, errbuf_size, "exact source temporary-grid opacity oracle applied");
    return 0;
}

static int xstar_opacity_apply_line_profile_legacy_v0648951(
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
    const double dpcrit = xstar_constants::kLegacyLinopacDpcrit;
    int ml1 = nbinc(line_energy_ev, epi, n);
    ml1 = std::max(2, std::min(n - 1, ml1));
    const double mass = std::max(atomic_mass_amu, 1.0e-30);
    const double vth = source_mul(xstar_constants::kLegacyLinopacThermalSpeedCoefficient,
        std::sqrt(source_div(temperature_1e4k, mass)));
    const double deleturb = source_div(source_mul(line_energy_ev, vturb_km_s), 3.0e5);
    const double deleth = source_div(source_mul(line_energy_ev, vth), 3.0e5);
    const double dele = std::sqrt(source_add(source_mul(deleth, deleth), source_mul(deleturb, deleturb)));
    if (dele <= 0.0) {
        write_message(errbuf, errbuf_size, "native opacity profile zero-width no-op");
        return 0;
    }
    const double aasmall = source_div(
        source_div(natural_width_ev, source_add(xstar_constants::kLegacyLinopacWidthFloorEv, dele)),
        xstar_constants::kLegacyLinopacDampingGeometryFactor);
    const bool use_voigt = aasmall > xstar_constants::kLegacyLinopacWingVoigtThreshold;
    const double e00 = epi[ml1 - 1];
    const double deleepi = source_sub(epi[ml1], epi[ml1 - 1]);
    int ncut = static_cast<int>(deleepi / dele);
    ncut = std::max(1, std::min(nbtpp / 10, ncut));
    const double deleused = source_div(deleepi, static_cast<double>(static_cast<float>(ncut)));
    int mlc = 0, ldir = 1, ldon0 = 0, ldon1 = 0;
    int mlmin = nbtpp, mlmax = 1, ml1min = n + 1, ml1max = 0;
    const int ml2 = nbtpp / 2;
    // v0.6.48.9.3: Type-50 profiles previously allocated and zero-filled
    // two 20,000-double temporary planes for every line.  The source scan
    // overwrites every slot in the contiguous [mlmin, mlmax] interval before
    // the rebin pass reads it, so clearing those planes is unnecessary.
    // Reuse thread-local scratch storage while preserving the exact source
    // temporary-grid values, profile evaluations, and accumulation order.
    struct ProfileScratchV064893 {
        std::unique_ptr<double[]> etpp{new double[20000]};
        std::unique_ptr<double[]> optpp2{new double[20000]};
    };
    static thread_local ProfileScratchV064893 scratch_v064893;
    double* const etpp = scratch_v064893.etpp.get();
    double* const optpp2 = scratch_v064893.optpp2.get();
    double delet = source_div(source_sub(e00, line_energy_ev), dele);
    // Source linopac evaluates the center temporary-grid point at its
    // actual fractional Doppler displacement.  seed_profiles[0] is the
    // profile at zero displacement and is generally wrong because e00 is
    // the lower continuum-grid boundary, not the exact line center.
    // The source uses the stricter 1e-6 Voigt threshold at this center
    // point (the outward temporary points retain the 1e-9 threshold).
    const double center_profile = aasmall > xstar_constants::kLegacyLinopacCenterVoigtThreshold
        ? source_div(voigte(std::abs(delet), aasmall), xstar_constants::kLegacyLinopacProfileNormalization)
        : source_div(std::exp(-delet * delet), xstar_constants::kLegacyLinopacProfileNormalization);
    double profile = std::isfinite(center_profile) && center_profile > 0.0
        ? center_profile : 0.0;
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
            const double etptst = source_add(e00,
                source_mul(static_cast<double>(static_cast<float>(ldir * mlc)), deleused));
            if (mlm <= nbtpp && mlm >= 1 && etptst > 0.0 && etptst < epi[n - 1]) {
                mlmin = std::min(mlmin, mlm);
                mlmax = std::max(mlmax, mlm);
                etpp[mlm - 1] = etptst;
                delet = source_div(source_sub(etptst, line_energy_ev), dele);
                // Source linopac evaluates the profile at the actual
                // temporary-grid displacement for every point.  The former
                // native path used integer-offset seed samples for the first
                // ten substeps; when one continuum bin spans many Doppler
                // widths, those samples describe the wrong displacement and
                // can overpopulate entire optical/UV bins by many orders of
                // magnitude.  Retain seeds only as an API/qualification
                // precondition; compute the live Gaussian/Voigt value here.
                profile = use_voigt
                    ? source_div(voigte(std::abs(delet), aasmall), xstar_constants::kLegacyLinopacProfileNormalization)
                    : source_div(std::exp(-delet * delet), xstar_constants::kLegacyLinopacProfileNormalization);
                optpp2[mlm - 1] = optpp * profile;
                tst = profile;
            }
            const double delet_now = source_div(source_sub(etptst, line_energy_ev), dele);
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
            const double tmpe = std::abs(source_sub(etpp[mlm - 1], etpp[mlm - 2]));
            sume = source_add(sume, tmpe);
            const double pair = source_add(tmpop, tmpopo);
            const double weighted = source_mul(pair, tmpe);
            const double interval = source_div(weighted, 2.0);
            opsum = source_add(opsum, interval);
            if (etpp[mlm - 1] > epi[ml1m - 1]) {
                if (sume > 1.0e-34) {
                    const double raw_optp2 = source_div(opsum, sume);
                    const double optp2 = std::isfinite(raw_optp2) && raw_optp2 > 0.0 ? raw_optp2 : 0.0;
                    while (etpp[mlm - 1] > epi[ml1m - 1] && ml1m < n) {
                        const double current = std::isfinite(opakc[ml1m - 1]) && opakc[ml1m - 1] > 0.0
                            ? opakc[ml1m - 1] : 0.0;
                        opakc[ml1m - 1] = source_add(current, optp2);
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


// v0.6.48.9.6: exact Type-50 hot path.  The 9.5.1 implementation first
// materialized the complete 20,000-point temporary energy/profile planes and
// then traversed them again to rebin.  In literal linopac.f90, ml1min/ml1max
// are not updated until after that temporary-grid loop, so the ldon early-stop
// predicate cannot fire during full-profile construction.  The only values
// that can affect public opakc are therefore the monotonically ordered points
// consumed by the later rebin loop.  Compute those source-identical points at
// the moment they are consumed, preserving each default-REAL conversion,
// Voigt/Gaussian decision, trapezoid operation order, and public-bin update
// order.  This removes the dead temporary-plane traffic without changing the
// source arithmetic that reaches output.
static int xstar_opacity_apply_line_profile_optimized_v064896(
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

    constexpr int nbtpp = 20000;
    constexpr int ml2 = nbtpp / 2;
    const double mass = std::max(atomic_mass_amu, 1.0e-30);
    const double vth = source_mul(xstar_constants::kLegacyLinopacThermalSpeedCoefficient,
        std::sqrt(source_div(temperature_1e4k, mass)));
    const double deleturb = source_div(source_mul(line_energy_ev, vturb_km_s), 3.0e5);
    const double deleth = source_div(source_mul(line_energy_ev, vth), 3.0e5);
    const double dele = std::sqrt(source_add(source_mul(deleth, deleth), source_mul(deleturb, deleturb)));
    if (dele <= 0.0) {
        write_message(errbuf, errbuf_size, "native opacity profile zero-width no-op");
        return 0;
    }
    const double aasmall = source_div(
        source_div(natural_width_ev, source_add(xstar_constants::kLegacyLinopacWidthFloorEv, dele)),
        xstar_constants::kLegacyLinopacDampingGeometryFactor);
    const bool use_voigt = aasmall > xstar_constants::kLegacyLinopacWingVoigtThreshold;
    const bool use_small_a_voigt = use_voigt && aasmall <= source_real_literal(0.2);

    int ml1 = nbinc(line_energy_ev, epi, n);
    ml1 = std::max(2, std::min(n - 1, ml1));
    const double e00 = epi[ml1 - 1];
    const double deleepi = source_sub(epi[ml1], epi[ml1 - 1]);
    int ncut = static_cast<int>(deleepi / dele);
    ncut = std::max(1, std::min(nbtpp / 10, ncut));
    const double deleused = source_div(deleepi, static_cast<double>(ncut));

    auto temporary_energy = [e00, deleused](int mlm_one_based) {
        const int offset = mlm_one_based - ml2;
        return source_add(e00,
            source_mul(static_cast<double>(offset), deleused));
    };
    const double energy_ceiling = epi[n - 1];
    auto valid_temporary_energy = [energy_ceiling](double energy) {
        return energy > 0.0 && energy < energy_ceiling;
    };

    // Literal outward construction can address temporary indices 1..20000,
    // but index 1 is later discarded when mlmin is clamped to 2 and the
    // rebin loop begins at mlmin+1.  Find the same raw bounds from the outside
    // inward using the exact source energy expression; no profile value is
    // needed to determine these bounds because ldon is invariantly false.
    // 12.3.24: localize the same raw bounds algebraically, then correct
    // locally using the literal source temporary-energy predicate.  The old
    // implementation linearly scanned thousands of guaranteed-invalid slots
    // for every accepted Type-50 profile.  Only the final corrected integer
    // bounds affect linopac arithmetic.
    const double lower_crossing = static_cast<double>(ml2) - source_div(e00, deleused);
    int raw_mlmin = 1;
    if (lower_crossing >= static_cast<double>(ml2)) raw_mlmin = ml2;
    else if (lower_crossing > 1.0) raw_mlmin = static_cast<int>(std::floor(lower_crossing)) + 1;
    while (raw_mlmin > 1 && valid_temporary_energy(temporary_energy(raw_mlmin - 1))) {
        --raw_mlmin;
        ++g_type50_bound_correction_steps_v064812324;
    }
    while (raw_mlmin < ml2 && !valid_temporary_energy(temporary_energy(raw_mlmin))) {
        ++raw_mlmin;
        ++g_type50_bound_correction_steps_v064812324;
    }
    const double upper_crossing = static_cast<double>(ml2) +
        source_div(source_sub(energy_ceiling, e00), deleused);
    int raw_mlmax = nbtpp;
    if (upper_crossing <= static_cast<double>(ml2)) raw_mlmax = ml2;
    else if (upper_crossing < static_cast<double>(nbtpp))
        raw_mlmax = static_cast<int>(std::ceil(upper_crossing)) - 1;
    while (raw_mlmax < nbtpp && valid_temporary_energy(temporary_energy(raw_mlmax + 1))) {
        ++raw_mlmax;
        ++g_type50_bound_correction_steps_v064812324;
    }
    while (raw_mlmax > ml2 && !valid_temporary_energy(temporary_energy(raw_mlmax))) {
        --raw_mlmax;
        ++g_type50_bound_correction_steps_v064812324;
    }
    // If one side has no valid outward temporary point, literal linopac leaves
    // that raw extremum at its sentinel rather than promoting the center.
    // This is outside the benchmark hot shape; fall back to the frozen 9.5.1
    // implementation so edge-grid semantics remain exact.
    if (raw_mlmin >= ml2 || raw_mlmax <= ml2) {
        ++g_type50_scalar_profiles_v064812324;
        return xstar_opacity_apply_line_profile_legacy_v0648951(
            optpp, line_energy_ev, vturb_km_s, temperature_1e4k, atomic_mass_amu,
            natural_width_ev, seed_profiles, seed_radius, epi, ncn2, opakc,
            rccemis, updated_bins, opacity_seconds, errbuf, errbuf_size);
    }

    const int ml1min = nbinc(temporary_energy(raw_mlmin), epi, n);
    int ml1m = ml1min;
    const int mlmin = std::max(2, raw_mlmin);
    const int mlmax = std::min(nbtpp, raw_mlmax);
    double sume = 0.0;
    double opsum = 0.0;
    double tmpop = 0.0;
    double previous_energy = temporary_energy(mlmin);

    static const bool force_scalar_v064812324 =
        env_truthy_v064812324("XSTAR_V064812324_FORCE_SCALAR_TYPE50");
    const bool avx2_enabled_v064812324 = use_small_a_voigt &&
        cpu_avx2_available_v064812324() && !force_scalar_v064812324;
    bool profile_used_avx2_v064812324 = false;

    auto consume_profile_point_v064812324 = [&](int mlm, double current_energy, double profile) {
        const double tmpopo = tmpop;
        tmpop = optpp * profile;
        const double tmpe = std::abs(source_sub(current_energy, previous_energy));
        previous_energy = current_energy;
        sume = source_add(sume, tmpe);
        const double pair = source_add(tmpop, tmpopo);
        const double weighted = source_mul(pair, tmpe);
        const double interval = source_div(weighted, 2.0);
        opsum = source_add(opsum, interval);
        if (current_energy > epi[ml1m - 1]) {
            if (sume > 1.0e-34) {
                const double optp2 = source_div(opsum, sume);
                while (current_energy > epi[ml1m - 1] && ml1m < n) {
                    opakc[ml1m - 1] = source_add(opakc[ml1m - 1], optp2);
                    ++(*updated_bins);
                    ++ml1m;
                }
            }
            opsum = 0.0;
            sume = 0.0;
        }
        (void)mlm;
    };

    int mlm = mlmin + 1;
    while (mlm <= mlmax) {
#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
        if (avx2_enabled_v064812324 && mlm + 3 <= mlmax &&
            !(mlm <= ml2 && ml2 <= mlm + 3)) {
            double energies[4];
            double av[4];
            bool all_far = true;
            for (int lane = 0; lane < 4; ++lane) {
                energies[lane] = temporary_energy(mlm + lane);
                const double delet_lane = source_div(
                    source_sub(energies[lane], line_energy_ev), dele);
                av[lane] = std::abs(delet_lane);
                all_far = all_far && av[lane] >= source_real_literal(5.0);
            }
            if (all_far) {
                double raw[4];
                voigte_small_a_farwing4_v064812324(av, aasmall, raw);
                for (int lane = 0; lane < 4; ++lane) {
                    const double profile = source_div(
                        raw[lane], xstar_constants::kLegacyLinopacProfileNormalization);
                    consume_profile_point_v064812324(mlm + lane, energies[lane], profile);
                }
                profile_used_avx2_v064812324 = true;
                g_type50_vectorized_points_v064812324 += 4u;
                mlm += 4;
                continue;
            }
        }
#endif
        const double current_energy = temporary_energy(mlm);
        const double delet = source_div(source_sub(current_energy, line_energy_ev), dele);
        double profile;
        if (mlm == ml2) {
            if (aasmall > xstar_constants::kLegacyLinopacCenterVoigtThreshold) {
                const double av = std::abs(delet);
                const double raw = use_small_a_voigt
                    ? voigte_small_a_positive_v064896(av, aasmall)
                    : voigte(av, aasmall);
                profile = source_div(raw, xstar_constants::kLegacyLinopacProfileNormalization);
            } else {
                profile = source_div(std::exp(-delet * delet), xstar_constants::kLegacyLinopacProfileNormalization);
            }
        } else if (use_voigt) {
            const double av = std::abs(delet);
            const double raw = use_small_a_voigt
                ? voigte_small_a_positive_v064896(av, aasmall)
                : voigte(av, aasmall);
            profile = source_div(raw, xstar_constants::kLegacyLinopacProfileNormalization);
        } else {
            profile = source_div(std::exp(-delet * delet), xstar_constants::kLegacyLinopacProfileNormalization);
        }
        consume_profile_point_v064812324(mlm, current_energy, profile);
        ++mlm;
    }
    g_last_profile_vectorized_v064812324 = profile_used_avx2_v064812324 ? 1 : 0;
    if (profile_used_avx2_v064812324) ++g_type50_vectorized_profiles_v064812324;
    else ++g_type50_scalar_profiles_v064812324;
    const auto ended = std::chrono::steady_clock::now();
    *opacity_seconds = std::chrono::duration<double>(ended - started).count();
    write_message(errbuf, errbuf_size, use_voigt ? "native opacity voigt profile applied" : "native opacity gaussian profile applied");
    return 0;
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
    g_last_profile_vectorized_v064812324 = 0;
    // Same executable, same ABI: set once before process start to force the
    // exact 0.6.48.9.5.1 Type-50 implementation for blocking A/B runs.
    static const bool use_optimized_standalone_v064896 = [] {
        const char* native_sequence = std::getenv("XSTAR_NATIVE_SOURCE_SEQUENCE");
        const bool standalone_native = native_sequence && *native_sequence;
        const char* forced = std::getenv("XSTAR_V064896_FORCE_LEGACY_TYPE50");
        const bool force_legacy = forced && *forced && std::strcmp(forced, "0") != 0 &&
            std::strcmp(forced, "false") != 0 && std::strcmp(forced, "FALSE") != 0;
        if (standalone_native) {
            std::fputs(force_legacy
                ? "V064896_TYPE50_MODE=LEGACY_0951_FORCED\n"
                : "V064896_TYPE50_MODE=OPTIMIZED_STANDALONE\n", stdout);
            std::fflush(stdout);
        }
        if (force_legacy) return false;
        // XSTAR_NATIVE_SOURCE_SEQUENCE is owned by the standalone native
        // controller.  Python source-port/C++-backend calls do not set it, so
        // 9.6 changes only the requested standalone-C++ Type-50 path.
        return standalone_native;
    }();
    if (!use_optimized_standalone_v064896) {
        return xstar_opacity_apply_line_profile_legacy_v0648951(
            optpp, line_energy_ev, vturb_km_s, temperature_1e4k, atomic_mass_amu,
            natural_width_ev, seed_profiles, seed_radius, epi, ncn2, opakc,
            rccemis, updated_bins, opacity_seconds, errbuf, errbuf_size);
    }
    return xstar_opacity_apply_line_profile_optimized_v064896(
        optpp, line_energy_ev, vturb_km_s, temperature_1e4k, atomic_mass_amu,
        natural_width_ev, seed_profiles, seed_radius, epi, ncn2, opakc,
        rccemis, updated_bins, opacity_seconds, errbuf, errbuf_size);
}


void xstar_opacity_type50_vector_perf_reset_v064812324(void) {
    g_type50_vectorized_profiles_v064812324 = 0u;
    g_type50_scalar_profiles_v064812324 = 0u;
    g_type50_vectorized_points_v064812324 = 0u;
    g_type50_bound_correction_steps_v064812324 = 0u;
    g_last_profile_vectorized_v064812324 = 0;
}

void xstar_opacity_type50_vector_perf_snapshot_v064812324(
    std::uint64_t* vectorized_profiles,
    std::uint64_t* scalar_profiles,
    std::uint64_t* vectorized_points,
    std::uint64_t* bound_correction_steps) {
    if (vectorized_profiles) *vectorized_profiles = g_type50_vectorized_profiles_v064812324;
    if (scalar_profiles) *scalar_profiles = g_type50_scalar_profiles_v064812324;
    if (vectorized_points) *vectorized_points = g_type50_vectorized_points_v064812324;
    if (bound_correction_steps) *bound_correction_steps = g_type50_bound_correction_steps_v064812324;
}

int xstar_opacity_last_profile_vectorized_v064812324(void) {
    return g_last_profile_vectorized_v064812324;
}

} // extern "C"
