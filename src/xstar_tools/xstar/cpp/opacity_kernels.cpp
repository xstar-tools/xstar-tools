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
#include <limits>
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


// v0.6.48.12.3.25: generic Type-50 profile diagnostics.  Production uses
// the scalar source-faithful profile path.  AVX2 is opt-in experimental only
// and is dispatched once per accepted line through a bulk profile generator;
// rebin and public opacity accumulation remain scalar/source ordered.
// These counters are observational only; they never enter science state.
thread_local std::uint64_t g_type50_vectorized_profiles_v064812324 = 0u;
thread_local std::uint64_t g_type50_scalar_profiles_v064812324 = 0u;
thread_local std::uint64_t g_type50_vectorized_points_v064812324 = 0u;
thread_local std::uint64_t g_type50_bound_correction_steps_v064812324 = 0u;
thread_local int g_last_profile_vectorized_v064812324 = 0;


// v0.6.48.12.3.28 production Type-50 promotion and consume/rebin diagnostics.
// The 12.3.27 one-dispatch small-a far-wing AVX2 arithmetic is now the normal
// standalone-C++ path on AVX2-capable x86.  The exact 12.3.25 scalar kernel is
// retained as runtime fallback.  The ncut==4 consume specialization is generic
// and opt-in until host qualification; all counters are observational only.
thread_local std::uint64_t g_type50_prod_avx2_profiles_v064812328 = 0u;
thread_local std::uint64_t g_type50_prod_scalar_profiles_v064812328 = 0u;
thread_local std::uint64_t g_type50_prod_avx2_blocks_v064812328 = 0u;
thread_local std::uint64_t g_type50_prod_avx2_points_v064812328 = 0u;
thread_local std::uint64_t g_type50_prod_scalar_profile_points_v064812328 = 0u;
thread_local std::uint64_t g_type50_ncut4_profiles_v064812328 = 0u;
thread_local std::uint64_t g_type50_ncut4_fast_blocks_v064812328 = 0u;
thread_local std::uint64_t g_type50_ncut4_boundary_fallback_blocks_v064812328 = 0u;
thread_local std::uint64_t g_type50_ncut4_fast_points_v064812328 = 0u;
thread_local std::uint64_t g_type50_decomp_profiles_v064812328 = 0u;
thread_local std::uint64_t g_type50_decomp_avx2_points_v064812328 = 0u;
thread_local std::uint64_t g_type50_decomp_scalar_points_v064812328 = 0u;
thread_local double g_type50_decomp_avx2_profile_seconds_v064812328 = 0.0;
thread_local double g_type50_decomp_scalar_profile_seconds_v064812328 = 0.0;
thread_local double g_type50_decomp_consume_seconds_v064812328 = 0.0;

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



// v0.6.48.12.3.28: source-order consume state shared by the promoted AVX2
// profile path and the ncut==4 no-boundary specialization.  The arithmetic is
// the same statement order as the accepted 12.3.27 implementation.
struct Type50ConsumeStateV064812328 {
    double sume = 0.0;
    double opsum = 0.0;
    double tmpop = 0.0;
    double previous_energy = 0.0;
    int ml1m = 0;
};

static inline void type50_consume_no_boundary_v064812328(
    double optpp, double current_energy, double profile,
    Type50ConsumeStateV064812328& state) {
    const double tmpopo = state.tmpop;
    state.tmpop = optpp * profile;
    const double tmpe = std::abs(source_sub(current_energy, state.previous_energy));
    state.previous_energy = current_energy;
    state.sume = source_add(state.sume, tmpe);
    const double pair = source_add(state.tmpop, tmpopo);
    const double weighted = source_mul(pair, tmpe);
    const double interval = source_div(weighted, 2.0);
    state.opsum = source_add(state.opsum, interval);
}

static inline void type50_apply_boundary_v064812328(
    double current_energy, const double* epi, int n, double* opakc,
    long long* updated_bins, Type50ConsumeStateV064812328& state) {
    if (current_energy > epi[state.ml1m - 1]) {
        if (state.sume > 1.0e-34) {
            const double optp2 = source_div(state.opsum, state.sume);
            while (current_energy > epi[state.ml1m - 1] && state.ml1m < n) {
                opakc[state.ml1m - 1] = source_add(opakc[state.ml1m - 1], optp2);
                ++(*updated_bins);
                ++state.ml1m;
            }
        }
        state.opsum = 0.0;
        state.sume = 0.0;
    }
}

static inline void type50_consume_full_v064812328(
    double optpp, double current_energy, double profile,
    const double* epi, int n, double* opakc, long long* updated_bins,
    Type50ConsumeStateV064812328& state) {
    type50_consume_no_boundary_v064812328(optpp, current_energy, profile, state);
    type50_apply_boundary_v064812328(current_energy, epi, n, opakc, updated_bins, state);
}

static std::pair<int,int> small_a_core_bounds_v064812328(
    int first_point, int last_point, double e00, double deleused,
    double line_energy_ev, double dele) {
    constexpr int ml2 = 10000;
    if (first_point > last_point) return {last_point + 1, first_point - 1};
    auto signed_delet = [=](int point) {
        const double energy = source_add(e00,
            source_mul(static_cast<double>(point - ml2), deleused));
        return source_div(source_sub(energy, line_energy_ev), dele);
    };
    int lo = first_point, hi = last_point + 1;
    while (lo < hi) {
        const int mid = lo + (hi - lo) / 2;
        if (signed_delet(mid) > source_real_literal(-5.0)) hi = mid;
        else lo = mid + 1;
    }
    const int first_core = lo;
    lo = first_point; hi = last_point + 1;
    while (lo < hi) {
        const int mid = lo + (hi - lo) / 2;
        if (signed_delet(mid) >= source_real_literal(5.0)) hi = mid;
        else lo = mid + 1;
    }
    const int last_core = lo - 1;
    return {first_core, last_core};
}

#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
__attribute__((target("avx2")))
static int run_inline_farwing_profile_v064812328(
    double optpp, double line_energy_ev, double dele, double aasmall,
    double e00, double deleused, const double* epi, int n,
    int mlmin, int mlmax, int ml1min, int first_core, int last_core,
    bool ncut4_fast_enabled, double* opakc, long long* updated_bins) {
    constexpr int ml2 = 10000;
    auto energy_for = [=](int point) {
        return source_add(e00, source_mul(static_cast<double>(point - ml2), deleused));
    };
    Type50ConsumeStateV064812328 state;
    state.previous_energy = energy_for(mlmin);
    state.ml1m = ml1min;

    auto scalar_point = [&](int point) {
        const double current_energy = energy_for(point);
        const double delet = source_div(source_sub(current_energy, line_energy_ev), dele);
        double profile;
        if (point == ml2 && aasmall <= xstar_constants::kLegacyLinopacCenterVoigtThreshold) {
            profile = source_div(std::exp(-delet * delet),
                xstar_constants::kLegacyLinopacProfileNormalization);
        } else {
            const double raw = voigte_small_a_positive_v064896(std::abs(delet), aasmall);
            profile = source_div(raw, xstar_constants::kLegacyLinopacProfileNormalization);
        }
        type50_consume_full_v064812328(
            optpp, current_energy, profile, epi, n, opakc, updated_bins, state);
        ++g_type50_prod_scalar_profile_points_v064812328;
    };

    const __m256d deleused4 = _mm256_set1_pd(deleused);
    const __m256d e004 = _mm256_set1_pd(e00);
    const __m256d line4 = _mm256_set1_pd(line_energy_ev);
    const __m256d dele4 = _mm256_set1_pd(dele);
    const __m256d aa4 = _mm256_set1_pd(aasmall);
    const __m256d six4 = _mm256_set1_pd(source_real_literal(6.0));
    const __m256d four4 = _mm256_set1_pd(source_real_literal(4.0));
    const __m256d fifteen4 = _mm256_set1_pd(source_real_literal(15.0));
    const __m256d sqp4 = _mm256_set1_pd(source_real_literal(1.772453851));
    const __m256d norm4 = _mm256_set1_pd(xstar_constants::kLegacyLinopacProfileNormalization);
    const __m256d sign = _mm256_set1_pd(-0.0);

#define XSTAR_V064812328_EXTRACT4(VEC, A0, A1, A2, A3) do { \
        const __m128d lo_v064812328 = _mm256_castpd256_pd128((VEC)); \
        const __m128d hi_v064812328 = _mm256_extractf128_pd((VEC), 1); \
        (A0) = _mm_cvtsd_f64(lo_v064812328); \
        (A1) = _mm_cvtsd_f64(_mm_unpackhi_pd(lo_v064812328, lo_v064812328)); \
        (A2) = _mm_cvtsd_f64(hi_v064812328); \
        (A3) = _mm_cvtsd_f64(_mm_unpackhi_pd(hi_v064812328, hi_v064812328)); \
    } while (0)

#define XSTAR_V064812328_PROCESS_FAR_RANGE(BEGIN_VALUE, END_VALUE) do { \
        int point_v064812328 = (BEGIN_VALUE); \
        const int end_v064812328 = (END_VALUE); \
        while (point_v064812328 + 3 <= end_v064812328) { \
            const double o0 = static_cast<double>(point_v064812328 - ml2); \
            const double o1 = static_cast<double>(point_v064812328 + 1 - ml2); \
            const double o2 = static_cast<double>(point_v064812328 + 2 - ml2); \
            const double o3 = static_cast<double>(point_v064812328 + 3 - ml2); \
            const __m256d offsets = _mm256_set_pd(o3, o2, o1, o0); \
            const __m256d energies = _mm256_add_pd(e004, _mm256_mul_pd(offsets, deleused4)); \
            const __m256d signed_v = _mm256_div_pd(_mm256_sub_pd(energies, line4), dele4); \
            const __m256d v = _mm256_andnot_pd(sign, signed_v); \
            const __m256d v2 = _mm256_mul_pd(v, v); \
            const __m256d v4 = _mm256_mul_pd(v2, v2); \
            const __m256d n1 = _mm256_mul_pd(six4, v2); \
            const __m256d n2 = _mm256_mul_pd(four4, v4); \
            const __m256d num = _mm256_add_pd(_mm256_add_pd(fifteen4, n1), n2); \
            const __m256d scaled = _mm256_mul_pd(aa4, num); \
            const __m256d d0 = _mm256_mul_pd(four4, v2); \
            const __m256d d1 = _mm256_mul_pd(d0, v2); \
            const __m256d d2 = _mm256_mul_pd(d1, v2); \
            const __m256d raw = _mm256_div_pd(scaled, _mm256_mul_pd(d2, sqp4)); \
            const __m256d profiles = _mm256_div_pd(raw, norm4); \
            double e0, e1, e2, e3, p0, p1, p2, p3; \
            XSTAR_V064812328_EXTRACT4(energies, e0, e1, e2, e3); \
            XSTAR_V064812328_EXTRACT4(profiles, p0, p1, p2, p3); \
            if (ncut4_fast_enabled && e3 <= epi[state.ml1m - 1]) { \
                type50_consume_no_boundary_v064812328(optpp, e0, p0, state); \
                type50_consume_no_boundary_v064812328(optpp, e1, p1, state); \
                type50_consume_no_boundary_v064812328(optpp, e2, p2, state); \
                type50_consume_no_boundary_v064812328(optpp, e3, p3, state); \
                ++g_type50_ncut4_fast_blocks_v064812328; \
                g_type50_ncut4_fast_points_v064812328 += 4u; \
            } else { \
                type50_consume_full_v064812328(optpp, e0, p0, epi, n, opakc, updated_bins, state); \
                type50_consume_full_v064812328(optpp, e1, p1, epi, n, opakc, updated_bins, state); \
                type50_consume_full_v064812328(optpp, e2, p2, epi, n, opakc, updated_bins, state); \
                type50_consume_full_v064812328(optpp, e3, p3, epi, n, opakc, updated_bins, state); \
                if (ncut4_fast_enabled) ++g_type50_ncut4_boundary_fallback_blocks_v064812328; \
            } \
            ++g_type50_prod_avx2_blocks_v064812328; \
            g_type50_prod_avx2_points_v064812328 += 4u; \
            point_v064812328 += 4; \
        } \
        while (point_v064812328 <= end_v064812328) { \
            scalar_point(point_v064812328); \
            ++point_v064812328; \
        } \
    } while (0)

    const int first_point = mlmin + 1;
    const int last_point = mlmax;
    const int left_begin = first_point;
    const int left_end = std::min(last_point, first_core - 1);
    if (left_begin <= left_end) {
        if (aasmall <= xstar_constants::kLegacyLinopacCenterVoigtThreshold &&
            left_begin <= ml2 && ml2 <= left_end) {
            XSTAR_V064812328_PROCESS_FAR_RANGE(left_begin, ml2 - 1);
            scalar_point(ml2);
            XSTAR_V064812328_PROCESS_FAR_RANGE(ml2 + 1, left_end);
        } else {
            XSTAR_V064812328_PROCESS_FAR_RANGE(left_begin, left_end);
        }
    }
    for (int point = std::max(first_point, first_core);
         point <= std::min(last_point, last_core); ++point) scalar_point(point);
    const int right_begin = std::max(first_point, last_core + 1);
    const int right_end = last_point;
    if (right_begin <= right_end) {
        if (aasmall <= xstar_constants::kLegacyLinopacCenterVoigtThreshold &&
            right_begin <= ml2 && ml2 <= right_end) {
            XSTAR_V064812328_PROCESS_FAR_RANGE(right_begin, ml2 - 1);
            scalar_point(ml2);
            XSTAR_V064812328_PROCESS_FAR_RANGE(ml2 + 1, right_end);
        } else {
            XSTAR_V064812328_PROCESS_FAR_RANGE(right_begin, right_end);
        }
    }
#undef XSTAR_V064812328_PROCESS_FAR_RANGE
#undef XSTAR_V064812328_EXTRACT4
    return 0;
}
#endif

#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
// Diagnostic-only 12.3.28 profile materializer.  It uses the same far-wing
// vector arithmetic as production, but stores results so profile arithmetic
// can be timed separately from the scalar consume/rebin phase.
__attribute__((target("avx2")))
static std::uint64_t fill_farwing_profile_blocks_v064812328(
    int begin, int end, int first_point, int ml2, double e00, double deleused,
    double line_energy_ev, double dele, double aasmall, double* profiles) {
    if (begin > end) return 0u;
    const __m256d deleused4 = _mm256_set1_pd(deleused);
    const __m256d e004 = _mm256_set1_pd(e00);
    const __m256d line4 = _mm256_set1_pd(line_energy_ev);
    const __m256d dele4 = _mm256_set1_pd(dele);
    const __m256d aa4 = _mm256_set1_pd(aasmall);
    const __m256d six4 = _mm256_set1_pd(source_real_literal(6.0));
    const __m256d four4 = _mm256_set1_pd(source_real_literal(4.0));
    const __m256d fifteen4 = _mm256_set1_pd(source_real_literal(15.0));
    const __m256d sqp4 = _mm256_set1_pd(source_real_literal(1.772453851));
    const __m256d norm4 = _mm256_set1_pd(xstar_constants::kLegacyLinopacProfileNormalization);
    const __m256d sign = _mm256_set1_pd(-0.0);
    std::uint64_t points = 0u;
    int point = begin;
    while (point + 3 <= end) {
        if (point <= ml2 && ml2 <= point + 3) {
            point += 4;
            continue;
        }
        const double o0 = static_cast<double>(point - ml2);
        const double o1 = static_cast<double>(point + 1 - ml2);
        const double o2 = static_cast<double>(point + 2 - ml2);
        const double o3 = static_cast<double>(point + 3 - ml2);
        const __m256d offsets = _mm256_set_pd(o3, o2, o1, o0);
        const __m256d energies = _mm256_add_pd(e004, _mm256_mul_pd(offsets, deleused4));
        const __m256d signed_v = _mm256_div_pd(_mm256_sub_pd(energies, line4), dele4);
        const __m256d v = _mm256_andnot_pd(sign, signed_v);
        const __m256d v2 = _mm256_mul_pd(v, v);
        const __m256d v4 = _mm256_mul_pd(v2, v2);
        const __m256d num = _mm256_add_pd(
            _mm256_add_pd(fifteen4, _mm256_mul_pd(six4, v2)),
            _mm256_mul_pd(four4, v4));
        const __m256d scaled = _mm256_mul_pd(aa4, num);
        const __m256d d0 = _mm256_mul_pd(four4, v2);
        const __m256d d1 = _mm256_mul_pd(d0, v2);
        const __m256d d2 = _mm256_mul_pd(d1, v2);
        const __m256d raw = _mm256_div_pd(scaled, _mm256_mul_pd(d2, sqp4));
        const __m256d out = _mm256_div_pd(raw, norm4);
        _mm256_storeu_pd(profiles + (point - first_point), out);
        points += 4u;
        point += 4;
    }
    return points;
}
#endif

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

    static const bool force_scalar_v064812328 =
        env_truthy_v064812324("XSTAR_V064812328_FORCE_SCALAR_TYPE50") ||
        env_truthy_v064812324("XSTAR_V064812324_FORCE_SCALAR_TYPE50");
    static const bool enable_ncut4_unrolled_v064812328 =
        env_truthy_v064812324("XSTAR_V064812328_ENABLE_NCUT4_UNROLLED_CONSUME");
    const bool production_inline_avx2_v064812328 = use_small_a_voigt &&
        cpu_avx2_available_v064812324() && !force_scalar_v064812328;
    static const bool decompose_v064812328 =
        env_truthy_v064812324("XSTAR_V064812328_TYPE50_DECOMPOSE");

#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
    if (production_inline_avx2_v064812328 && decompose_v064812328) {
        const int first_point = mlmin + 1;
        const int last_point = mlmax;
        const auto core = small_a_core_bounds_v064812328(
            first_point, last_point, e00, deleused, line_energy_ev, dele);
        const std::size_t count = static_cast<std::size_t>(std::max(0, last_point - first_point + 1));
        std::vector<double> profiles(count, std::numeric_limits<double>::quiet_NaN());
        std::uint64_t avx_points = 0u;

        const auto avx_started = std::chrono::steady_clock::now();
        avx_points += fill_farwing_profile_blocks_v064812328(
            first_point, std::min(last_point, core.first - 1), first_point, ml2,
            e00, deleused, line_energy_ev, dele, aasmall, profiles.data());
        avx_points += fill_farwing_profile_blocks_v064812328(
            std::max(first_point, core.second + 1), last_point, first_point, ml2,
            e00, deleused, line_energy_ev, dele, aasmall, profiles.data());
        g_type50_decomp_avx2_profile_seconds_v064812328 += std::chrono::duration<double>(
            std::chrono::steady_clock::now() - avx_started).count();

        const auto scalar_started = std::chrono::steady_clock::now();
        std::uint64_t scalar_points = 0u;
        for (int point = first_point; point <= last_point; ++point) {
            double& profile = profiles[static_cast<std::size_t>(point - first_point)];
            if (!std::isnan(profile)) continue;
            const double current_energy = temporary_energy(point);
            const double delet = source_div(source_sub(current_energy, line_energy_ev), dele);
            if (point == ml2 && aasmall <= xstar_constants::kLegacyLinopacCenterVoigtThreshold) {
                profile = source_div(std::exp(-delet * delet),
                    xstar_constants::kLegacyLinopacProfileNormalization);
            } else {
                const double raw = voigte_small_a_positive_v064896(std::abs(delet), aasmall);
                profile = source_div(raw, xstar_constants::kLegacyLinopacProfileNormalization);
            }
            ++scalar_points;
        }
        g_type50_decomp_scalar_profile_seconds_v064812328 += std::chrono::duration<double>(
            std::chrono::steady_clock::now() - scalar_started).count();

        const auto consume_started = std::chrono::steady_clock::now();
        Type50ConsumeStateV064812328 state;
        state.previous_energy = temporary_energy(mlmin);
        state.ml1m = ml1min;
        for (int point = first_point; point <= last_point; ++point) {
            const double current_energy = temporary_energy(point);
            const double profile = profiles[static_cast<std::size_t>(point - first_point)];
            type50_consume_full_v064812328(
                optpp, current_energy, profile, epi, n, opakc, updated_bins, state);
        }
        g_type50_decomp_consume_seconds_v064812328 += std::chrono::duration<double>(
            std::chrono::steady_clock::now() - consume_started).count();
        ++g_type50_decomp_profiles_v064812328;
        g_type50_decomp_avx2_points_v064812328 += avx_points;
        g_type50_decomp_scalar_points_v064812328 += scalar_points;
        ++g_type50_prod_avx2_profiles_v064812328;
        ++g_type50_vectorized_profiles_v064812324;
        g_last_profile_vectorized_v064812324 = 1;
        const auto ended = std::chrono::steady_clock::now();
        *opacity_seconds = std::chrono::duration<double>(ended - started).count();
        write_message(errbuf, errbuf_size, "v064812328 optimized Type50 decomposition applied");
        return 0;
    }

    if (production_inline_avx2_v064812328) {
        const int first_point = mlmin + 1;
        const int last_point = mlmax;
        const auto core = small_a_core_bounds_v064812328(
            first_point, last_point, e00, deleused, line_energy_ev, dele);
        const bool ncut4_fast = enable_ncut4_unrolled_v064812328 && ncut == 4;
        if (ncut4_fast) ++g_type50_ncut4_profiles_v064812328;
        run_inline_farwing_profile_v064812328(
            optpp, line_energy_ev, dele, aasmall, e00, deleused, epi, n,
            mlmin, mlmax, ml1min, core.first, core.second, ncut4_fast,
            opakc, updated_bins);
        ++g_type50_prod_avx2_profiles_v064812328;
        ++g_type50_vectorized_profiles_v064812324;
        g_last_profile_vectorized_v064812324 = 1;
        const auto ended = std::chrono::steady_clock::now();
        *opacity_seconds = std::chrono::duration<double>(ended - started).count();
        write_message(errbuf, errbuf_size,
            ncut4_fast ? "v064812328 production inline-farwing AVX2 ncut4 consume"
                       : "v064812328 production inline-farwing AVX2");
        return 0;
    }
#endif

    // Exact 12.3.25 scalar fallback.  No bulk/profile-vector experiment is
    // reachable from the normal 12.3.28 production path.
    ++g_type50_prod_scalar_profiles_v064812328;
    ++g_type50_scalar_profiles_v064812324;
    g_last_profile_vectorized_v064812324 = 0;
    auto consume_profile_point_v064812328 = [&](double current_energy, double profile) {
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
    };

    for (int mlm = mlmin + 1; mlm <= mlmax; ++mlm) {
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
                profile = source_div(std::exp(-delet * delet),
                    xstar_constants::kLegacyLinopacProfileNormalization);
            }
        } else if (use_voigt) {
            const double av = std::abs(delet);
            const double raw = use_small_a_voigt
                ? voigte_small_a_positive_v064896(av, aasmall)
                : voigte(av, aasmall);
            profile = source_div(raw, xstar_constants::kLegacyLinopacProfileNormalization);
        } else {
            profile = source_div(std::exp(-delet * delet),
                xstar_constants::kLegacyLinopacProfileNormalization);
        }
        consume_profile_point_v064812328(current_energy, profile);
        ++g_type50_prod_scalar_profile_points_v064812328;
    }
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

// Retired 12.3.26/12.3.27 experiment telemetry remains ABI-callable as zero
// so older timing reporters do not pull the retired experiment translation
// unit back into the production opacity library.
void xstar_opacity_type50_phase_perf_reset_v064812326(void) {}
void xstar_opacity_type50_phase_perf_snapshot_v064812326(
    std::uint64_t* phase_profiles, std::uint64_t* span_events, std::uint64_t* span_bins,
    std::uint64_t* vectorizable_span_events, std::uint64_t* vectorizable_span_bins,
    std::uint64_t* max_span, double* profile_value_seconds, double* rebin_seconds,
    double* range_update_seconds, std::uint64_t* range_avx2_profiles,
    std::uint64_t* range_avx2_blocks, std::uint64_t* range_avx2_bins,
    std::uint64_t* range_scalar_bins) {
    if (phase_profiles) *phase_profiles = 0u;
    if (span_events) *span_events = 0u;
    if (span_bins) *span_bins = 0u;
    if (vectorizable_span_events) *vectorizable_span_events = 0u;
    if (vectorizable_span_bins) *vectorizable_span_bins = 0u;
    if (max_span) *max_span = 0u;
    if (profile_value_seconds) *profile_value_seconds = 0.0;
    if (rebin_seconds) *rebin_seconds = 0.0;
    if (range_update_seconds) *range_update_seconds = 0.0;
    if (range_avx2_profiles) *range_avx2_profiles = 0u;
    if (range_avx2_blocks) *range_avx2_blocks = 0u;
    if (range_avx2_bins) *range_avx2_bins = 0u;
    if (range_scalar_bins) *range_scalar_bins = 0u;
}

void xstar_opacity_type50_perf_reset_v064812327(void) {}
void xstar_opacity_type50_perf_snapshot_v064812327(
    std::uint64_t* schedule_profiles, std::uint64_t* cache_hits,
    std::uint64_t* cache_misses, std::uint64_t* cache_uncached,
    std::uint64_t* distinct_cached_keys, std::uint64_t* cache_bytes,
    std::uint64_t* cached_events, double* schedule_build_seconds,
    std::uint64_t* ncut_histogram, std::size_t ncut_histogram_len,
    std::uint64_t* gaussian_points, std::uint64_t* small_a_core_points,
    std::uint64_t* small_a_farwing_points, std::uint64_t* large_a_points,
    std::uint64_t* inline_avx2_profiles, std::uint64_t* inline_avx2_blocks,
    std::uint64_t* inline_avx2_points, std::uint64_t* inline_scalar_points) {
    if (schedule_profiles) *schedule_profiles = 0u;
    if (cache_hits) *cache_hits = 0u;
    if (cache_misses) *cache_misses = 0u;
    if (cache_uncached) *cache_uncached = 0u;
    if (distinct_cached_keys) *distinct_cached_keys = 0u;
    if (cache_bytes) *cache_bytes = 0u;
    if (cached_events) *cached_events = 0u;
    if (schedule_build_seconds) *schedule_build_seconds = 0.0;
    if (ncut_histogram) for (std::size_t i=0;i<ncut_histogram_len;++i) ncut_histogram[i]=0u;
    if (gaussian_points) *gaussian_points = 0u;
    if (small_a_core_points) *small_a_core_points = 0u;
    if (small_a_farwing_points) *small_a_farwing_points = 0u;
    if (large_a_points) *large_a_points = 0u;
    if (inline_avx2_profiles) *inline_avx2_profiles = 0u;
    if (inline_avx2_blocks) *inline_avx2_blocks = 0u;
    if (inline_avx2_points) *inline_avx2_points = 0u;
    if (inline_scalar_points) *inline_scalar_points = 0u;
}

void xstar_opacity_type50_perf_reset_v064812328(void) {
    g_type50_prod_avx2_profiles_v064812328 = 0u;
    g_type50_prod_scalar_profiles_v064812328 = 0u;
    g_type50_prod_avx2_blocks_v064812328 = 0u;
    g_type50_prod_avx2_points_v064812328 = 0u;
    g_type50_prod_scalar_profile_points_v064812328 = 0u;
    g_type50_ncut4_profiles_v064812328 = 0u;
    g_type50_ncut4_fast_blocks_v064812328 = 0u;
    g_type50_ncut4_boundary_fallback_blocks_v064812328 = 0u;
    g_type50_ncut4_fast_points_v064812328 = 0u;
    g_type50_decomp_profiles_v064812328 = 0u;
    g_type50_decomp_avx2_points_v064812328 = 0u;
    g_type50_decomp_scalar_points_v064812328 = 0u;
    g_type50_decomp_avx2_profile_seconds_v064812328 = 0.0;
    g_type50_decomp_scalar_profile_seconds_v064812328 = 0.0;
    g_type50_decomp_consume_seconds_v064812328 = 0.0;
}

void xstar_opacity_type50_perf_snapshot_v064812328(
    std::uint64_t* prod_avx2_profiles, std::uint64_t* prod_scalar_profiles,
    std::uint64_t* prod_avx2_blocks, std::uint64_t* prod_avx2_points,
    std::uint64_t* prod_scalar_profile_points, std::uint64_t* ncut4_profiles,
    std::uint64_t* ncut4_fast_blocks, std::uint64_t* ncut4_boundary_fallback_blocks,
    std::uint64_t* ncut4_fast_points, std::uint64_t* decomp_profiles,
    std::uint64_t* decomp_avx2_points, std::uint64_t* decomp_scalar_points,
    double* decomp_avx2_profile_seconds, double* decomp_scalar_profile_seconds,
    double* decomp_consume_seconds) {
    if (prod_avx2_profiles) *prod_avx2_profiles = g_type50_prod_avx2_profiles_v064812328;
    if (prod_scalar_profiles) *prod_scalar_profiles = g_type50_prod_scalar_profiles_v064812328;
    if (prod_avx2_blocks) *prod_avx2_blocks = g_type50_prod_avx2_blocks_v064812328;
    if (prod_avx2_points) *prod_avx2_points = g_type50_prod_avx2_points_v064812328;
    if (prod_scalar_profile_points) *prod_scalar_profile_points = g_type50_prod_scalar_profile_points_v064812328;
    if (ncut4_profiles) *ncut4_profiles = g_type50_ncut4_profiles_v064812328;
    if (ncut4_fast_blocks) *ncut4_fast_blocks = g_type50_ncut4_fast_blocks_v064812328;
    if (ncut4_boundary_fallback_blocks) *ncut4_boundary_fallback_blocks = g_type50_ncut4_boundary_fallback_blocks_v064812328;
    if (ncut4_fast_points) *ncut4_fast_points = g_type50_ncut4_fast_points_v064812328;
    if (decomp_profiles) *decomp_profiles = g_type50_decomp_profiles_v064812328;
    if (decomp_avx2_points) *decomp_avx2_points = g_type50_decomp_avx2_points_v064812328;
    if (decomp_scalar_points) *decomp_scalar_points = g_type50_decomp_scalar_points_v064812328;
    if (decomp_avx2_profile_seconds) *decomp_avx2_profile_seconds = g_type50_decomp_avx2_profile_seconds_v064812328;
    if (decomp_scalar_profile_seconds) *decomp_scalar_profile_seconds = g_type50_decomp_scalar_profile_seconds_v064812328;
    if (decomp_consume_seconds) *decomp_consume_seconds = g_type50_decomp_consume_seconds_v064812328;
}

} // extern "C"
