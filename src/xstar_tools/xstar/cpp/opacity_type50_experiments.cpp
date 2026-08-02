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
static inline void add_opacity4_v064812326(double* dst, double value) {
    const __m256d current = _mm256_loadu_pd(dst);
    const __m256d addend = _mm256_set1_pd(value);
    _mm256_storeu_pd(dst, _mm256_add_pd(current, addend));
}
#endif

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


#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
// Experimental 12.3.25 bulk AVX2 path. This function is entered once per
// accepted small-a line, not once per four profile points. Independent Voigt
// values may be generated in parallel, but the caller consumes the resulting
// profile array sequentially so trapezoid/rebin/opakc arithmetic is unchanged.
__attribute__((target("avx2")))
static void fill_small_a_profile_bulk_v064812325(
    int ml_start, int ml_end, int ml2, double e00, double deleused,
    double line_energy_ev, double dele, double aasmall, double* profiles,
    std::uint64_t* vectorized_points) {
    std::uint64_t points = 0u;
    int mlm = ml_start;
    while (mlm <= ml_end) {
        if (mlm + 3 <= ml_end && !(mlm <= ml2 && ml2 <= mlm + 3)) {
            double av[4];
            bool all_far = true;
            for (int lane = 0; lane < 4; ++lane) {
                const int one_based = mlm + lane;
                const int offset = one_based - ml2;
                const double energy = source_add(e00,
                    source_mul(static_cast<double>(offset), deleused));
                const double delet = source_div(source_sub(energy, line_energy_ev), dele);
                av[lane] = std::abs(delet);
                all_far = all_far && av[lane] >= source_real_literal(5.0);
            }
            if (all_far) {
                double raw[4];
                voigte_small_a_farwing4_v064812324(av, aasmall, raw);
                for (int lane = 0; lane < 4; ++lane) {
                    profiles[(mlm + lane) - ml_start] = source_div(
                        raw[lane], xstar_constants::kLegacyLinopacProfileNormalization);
                }
                points += 4u;
                mlm += 4;
                continue;
            }
        }
        const int offset = mlm - ml2;
        const double energy = source_add(e00,
            source_mul(static_cast<double>(offset), deleused));
        const double delet = source_div(source_sub(energy, line_energy_ev), dele);
        if (mlm == ml2 && aasmall <= xstar_constants::kLegacyLinopacCenterVoigtThreshold) {
            profiles[mlm - ml_start] = source_div(
                std::exp(-delet * delet), xstar_constants::kLegacyLinopacProfileNormalization);
        } else {
            const double raw = voigte_small_a_positive_v064896(std::abs(delet), aasmall);
            profiles[mlm - ml_start] = source_div(
                raw, xstar_constants::kLegacyLinopacProfileNormalization);
        }
        ++mlm;
    }
    if (vectorized_points) *vectorized_points = points;
}
#endif

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

namespace {
thread_local std::uint64_t g_type50_phase_profiles_v064812326 = 0u;
thread_local std::uint64_t g_type50_phase_span_events_v064812326 = 0u;
thread_local std::uint64_t g_type50_phase_span_bins_v064812326 = 0u;
thread_local std::uint64_t g_type50_phase_vectorizable_span_events_v064812326 = 0u;
thread_local std::uint64_t g_type50_phase_vectorizable_span_bins_v064812326 = 0u;
thread_local std::uint64_t g_type50_phase_max_span_v064812326 = 0u;
thread_local double g_type50_phase_profile_value_seconds_v064812326 = 0.0;
thread_local double g_type50_phase_rebin_seconds_v064812326 = 0.0;
thread_local double g_type50_phase_range_update_seconds_v064812326 = 0.0;
thread_local std::uint64_t g_type50_range_avx2_profiles_v064812326 = 0u;
thread_local std::uint64_t g_type50_range_avx2_blocks_v064812326 = 0u;
thread_local std::uint64_t g_type50_range_avx2_bins_v064812326 = 0u;
thread_local std::uint64_t g_type50_range_scalar_bins_v064812326 = 0u;
}

extern "C" int xstar_opacity_apply_line_profile_v1(
    double optpp, double line_energy_ev, double vturb_km_s, double temperature_1e4k,
    double atomic_mass_amu, double natural_width_ev, const double* seed_profiles,
    int seed_radius, const double* epi, int ncn2, double* opakc, double* rccemis,
    long long* updated_bins, double* opacity_seconds, char* errbuf, std::size_t errbuf_size);

extern "C" int xstar_opacity_apply_line_profile_experimental_v064812326(
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
        return xstar_opacity_apply_line_profile_v1(
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

    static const bool phase_decomposition_v064812326 =
        env_truthy_v064812324("XSTAR_V064812326_TYPE50_PHASE_DECOMPOSITION");
    static const bool experimental_range_avx2_v064812326 =
        env_truthy_v064812324("XSTAR_V064812326_ENABLE_EXPERIMENTAL_RANGE_AVX2");

    // No experiment requested: execute the literal 12.3.25 optimized body.
    // This preserves the frozen high-density scalar baseline without adding
    // any new branch, counter, or clock inside its temporary/rebin/bin loops.
    if (!phase_decomposition_v064812326 && !experimental_range_avx2_v064812326) {
        static const bool force_scalar_v064812324 =
            env_truthy_v064812324("XSTAR_V064812324_FORCE_SCALAR_TYPE50");
        static const bool experimental_bulk_avx2_v064812325 =
            env_truthy_v064812324("XSTAR_V064812325_ENABLE_EXPERIMENTAL_BULK_AVX2");
        const bool avx2_enabled_v064812325 = use_small_a_voigt &&
            experimental_bulk_avx2_v064812325 && cpu_avx2_available_v064812324() &&
            !force_scalar_v064812324;
        bool profile_used_avx2_v064812324 = false;
        std::vector<double> bulk_profiles_v064812325;
        std::uint64_t bulk_vectorized_points_v064812325 = 0u;
        if (avx2_enabled_v064812325 && mlmin + 1 <= mlmax) {
    #if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
            bulk_profiles_v064812325.resize(static_cast<std::size_t>(mlmax - mlmin));
            fill_small_a_profile_bulk_v064812325(
                mlmin + 1, mlmax, ml2, e00, deleused, line_energy_ev, dele, aasmall,
                bulk_profiles_v064812325.data(), &bulk_vectorized_points_v064812325);
            profile_used_avx2_v064812324 = bulk_vectorized_points_v064812325 > 0u;
            g_type50_vectorized_points_v064812324 += bulk_vectorized_points_v064812325;
    #endif
        }

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
            const double current_energy = temporary_energy(mlm);
            double profile;
            if (!bulk_profiles_v064812325.empty()) {
                profile = bulk_profiles_v064812325[static_cast<std::size_t>(mlm - (mlmin + 1))];
            } else {
                const double delet = source_div(source_sub(current_energy, line_energy_ev), dele);
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

    static const bool force_scalar_v064812324 =
        env_truthy_v064812324("XSTAR_V064812324_FORCE_SCALAR_TYPE50");
    const bool range_avx2_enabled_v064812326 = experimental_range_avx2_v064812326 &&
        cpu_avx2_available_v064812324() && !force_scalar_v064812324 &&
        !phase_decomposition_v064812326;
    bool range_used_avx2_v064812326 = false;

    auto scalar_profile_v064812326 = [&](int mlm, double current_energy) {
        const double delet = source_div(source_sub(current_energy, line_energy_ev), dele);
        if (mlm == ml2) {
            if (aasmall > xstar_constants::kLegacyLinopacCenterVoigtThreshold) {
                const double av = std::abs(delet);
                const double raw = use_small_a_voigt
                    ? voigte_small_a_positive_v064896(av, aasmall)
                    : voigte(av, aasmall);
                return source_div(raw, xstar_constants::kLegacyLinopacProfileNormalization);
            }
            return source_div(std::exp(-delet * delet), xstar_constants::kLegacyLinopacProfileNormalization);
        }
        if (use_voigt) {
            const double av = std::abs(delet);
            const double raw = use_small_a_voigt
                ? voigte_small_a_positive_v064896(av, aasmall)
                : voigte(av, aasmall);
            return source_div(raw, xstar_constants::kLegacyLinopacProfileNormalization);
        }
        return source_div(std::exp(-delet * delet), xstar_constants::kLegacyLinopacProfileNormalization);
    };

    struct SpanEventV064812326 {
        int begin_index;
        int end_index;
        double value;
    };

    // Diagnostic-only three-pass decomposition.  The event pass advances
    // ml1m with the literal source threshold loop but does not touch opakc.
    // Events are then replayed in original order, preserving every per-bin
    // addition while allowing profile, rebin, and range-update time to be
    // measured independently with only three clocks per accepted profile.
    if (phase_decomposition_v064812326) {
        std::vector<double> profiles(static_cast<std::size_t>(mlmax - mlmin));
        const auto profile_started = std::chrono::steady_clock::now();
        for (int point = mlmin + 1; point <= mlmax; ++point) {
            const double current_energy = temporary_energy(point);
            profiles[static_cast<std::size_t>(point - (mlmin + 1))] =
                scalar_profile_v064812326(point, current_energy);
        }
        const auto profile_ended = std::chrono::steady_clock::now();

        std::vector<SpanEventV064812326> spans;
        spans.reserve(static_cast<std::size_t>(mlmax - mlmin));
        const auto rebin_started = std::chrono::steady_clock::now();
        for (int point = mlmin + 1; point <= mlmax; ++point) {
            const double current_energy = temporary_energy(point);
            const double profile = profiles[static_cast<std::size_t>(point - (mlmin + 1))];
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
                    const int begin = ml1m - 1;
                    while (current_energy > epi[ml1m - 1] && ml1m < n) ++ml1m;
                    const int end_index = ml1m - 1;
                    if (end_index > begin) {
                        spans.push_back({begin, end_index, optp2});
                        const auto span = static_cast<std::uint64_t>(end_index - begin);
                        ++g_type50_phase_span_events_v064812326;
                        g_type50_phase_span_bins_v064812326 += span;
                        if (span >= 4u) {
                            ++g_type50_phase_vectorizable_span_events_v064812326;
                            g_type50_phase_vectorizable_span_bins_v064812326 += span;
                        }
                        g_type50_phase_max_span_v064812326 =
                            std::max(g_type50_phase_max_span_v064812326, span);
                    }
                }
                opsum = 0.0;
                sume = 0.0;
            }
        }
        const auto rebin_ended = std::chrono::steady_clock::now();

        const auto range_started = std::chrono::steady_clock::now();
        for (const auto& span : spans) {
            for (int idx = span.begin_index; idx < span.end_index; ++idx) {
                opakc[idx] = source_add(opakc[idx], span.value);
                ++(*updated_bins);
            }
        }
        const auto range_ended = std::chrono::steady_clock::now();
        ++g_type50_phase_profiles_v064812326;
        g_type50_phase_profile_value_seconds_v064812326 +=
            std::chrono::duration<double>(profile_ended - profile_started).count();
        g_type50_phase_rebin_seconds_v064812326 +=
            std::chrono::duration<double>(rebin_ended - rebin_started).count();
        g_type50_phase_range_update_seconds_v064812326 +=
            std::chrono::duration<double>(range_ended - range_started).count();
        g_type50_scalar_profiles_v064812324 += 1u;
        g_last_profile_vectorized_v064812324 = 0;
        const auto ended = std::chrono::steady_clock::now();
        *opacity_seconds = std::chrono::duration<double>(ended - started).count();
        write_message(errbuf, errbuf_size, "native opacity phase-decomposition profile applied");
        return 0;
    }

    auto consume_profile_point_scalar_v064812326 = [&](int mlm, double current_energy, double profile) {
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

    auto consume_profile_point_range_avx2_v064812326 = [&](int mlm, double current_energy, double profile) {
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
#if (defined(__x86_64__) || defined(__i386__)) && (defined(__GNUC__) || defined(__clang__))
                while (ml1m + 3 < n && current_energy > epi[ml1m + 2]) {
                    add_opacity4_v064812326(opakc + (ml1m - 1), optp2);
                    ml1m += 4;
                    *updated_bins += 4;
                    ++g_type50_range_avx2_blocks_v064812326;
                    g_type50_range_avx2_bins_v064812326 += 4u;
                    range_used_avx2_v064812326 = true;
                }
#endif
                while (current_energy > epi[ml1m - 1] && ml1m < n) {
                    opakc[ml1m - 1] = source_add(opakc[ml1m - 1], optp2);
                    ++(*updated_bins);
                    ++g_type50_range_scalar_bins_v064812326;
                    ++ml1m;
                }
            }
            opsum = 0.0;
            sume = 0.0;
        }
        (void)mlm;
    };

    auto run_profile_loop_v064812326 = [&](auto&& consume) {
        int mlm = mlmin + 1;
        while (mlm <= mlmax) {
            const double current_energy = temporary_energy(mlm);
            const double profile = scalar_profile_v064812326(mlm, current_energy);
            consume(mlm, current_energy, profile);
            ++mlm;
        }
    };
    if (range_avx2_enabled_v064812326) {
        run_profile_loop_v064812326(consume_profile_point_range_avx2_v064812326);
    } else {
        run_profile_loop_v064812326(consume_profile_point_scalar_v064812326);
    }
    if (range_used_avx2_v064812326) ++g_type50_range_avx2_profiles_v064812326;
    g_last_profile_vectorized_v064812324 = 0;
    ++g_type50_scalar_profiles_v064812324;
    const auto ended = std::chrono::steady_clock::now();
    *opacity_seconds = std::chrono::duration<double>(ended - started).count();
    write_message(errbuf, errbuf_size, use_voigt ? "native opacity voigt profile applied" : "native opacity gaussian profile applied");
    return 0;
}


extern "C" {
void xstar_opacity_type50_phase_perf_reset_v064812326(void) {
    g_type50_phase_profiles_v064812326 = 0u;
    g_type50_phase_span_events_v064812326 = 0u;
    g_type50_phase_span_bins_v064812326 = 0u;
    g_type50_phase_vectorizable_span_events_v064812326 = 0u;
    g_type50_phase_vectorizable_span_bins_v064812326 = 0u;
    g_type50_phase_max_span_v064812326 = 0u;
    g_type50_phase_profile_value_seconds_v064812326 = 0.0;
    g_type50_phase_rebin_seconds_v064812326 = 0.0;
    g_type50_phase_range_update_seconds_v064812326 = 0.0;
    g_type50_range_avx2_profiles_v064812326 = 0u;
    g_type50_range_avx2_blocks_v064812326 = 0u;
    g_type50_range_avx2_bins_v064812326 = 0u;
    g_type50_range_scalar_bins_v064812326 = 0u;
}

void xstar_opacity_type50_phase_perf_snapshot_v064812326(
    std::uint64_t* phase_profiles,
    std::uint64_t* span_events,
    std::uint64_t* span_bins,
    std::uint64_t* vectorizable_span_events,
    std::uint64_t* vectorizable_span_bins,
    std::uint64_t* max_span,
    double* profile_value_seconds,
    double* rebin_seconds,
    double* range_update_seconds,
    std::uint64_t* range_avx2_profiles,
    std::uint64_t* range_avx2_blocks,
    std::uint64_t* range_avx2_bins,
    std::uint64_t* range_scalar_bins) {
    if (phase_profiles) *phase_profiles = g_type50_phase_profiles_v064812326;
    if (span_events) *span_events = g_type50_phase_span_events_v064812326;
    if (span_bins) *span_bins = g_type50_phase_span_bins_v064812326;
    if (vectorizable_span_events) *vectorizable_span_events = g_type50_phase_vectorizable_span_events_v064812326;
    if (vectorizable_span_bins) *vectorizable_span_bins = g_type50_phase_vectorizable_span_bins_v064812326;
    if (max_span) *max_span = g_type50_phase_max_span_v064812326;
    if (profile_value_seconds) *profile_value_seconds = g_type50_phase_profile_value_seconds_v064812326;
    if (rebin_seconds) *rebin_seconds = g_type50_phase_rebin_seconds_v064812326;
    if (range_update_seconds) *range_update_seconds = g_type50_phase_range_update_seconds_v064812326;
    if (range_avx2_profiles) *range_avx2_profiles = g_type50_range_avx2_profiles_v064812326;
    if (range_avx2_blocks) *range_avx2_blocks = g_type50_range_avx2_blocks_v064812326;
    if (range_avx2_bins) *range_avx2_bins = g_type50_range_avx2_bins_v064812326;
    if (range_scalar_bins) *range_scalar_bins = g_type50_range_scalar_bins_v064812326;
}

}
