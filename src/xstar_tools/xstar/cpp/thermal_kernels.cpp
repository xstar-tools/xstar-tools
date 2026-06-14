#include "xstar_thermal_engine.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <new>
#include <vector>

namespace {
using clock_type = std::chrono::steady_clock;
constexpr double kFourPi = static_cast<double>(static_cast<float>(12.56));
constexpr double kRadiusScale = 1.0e-19;
constexpr double kFacThreshold = static_cast<double>(static_cast<float>(0.01));
constexpr double kOpacityFloor = 1.0e-49;
constexpr double kRrcFloor = 1.0e-49;
constexpr double kErgPerEv = 1.602176634e-12;
constexpr double kChargeDenominatorFloor = 1.0e-48;
constexpr double kTemperatureFactor = static_cast<double>(static_cast<float>(1.2));
constexpr double kElectronFactor = static_cast<double>(static_cast<float>(1.2));
constexpr double kFarFromEquilibrium = static_cast<double>(static_cast<float>(0.9));
constexpr double kTinfProximityFactor = static_cast<double>(static_cast<float>(1.01));
constexpr double kInitialPreviousTemperature = static_cast<double>(static_cast<float>(1.0e30));
constexpr double kDefaultChargeTolerance = static_cast<double>(static_cast<float>(1.0e-4));
constexpr double kDefaultThermalTolerance = static_cast<double>(static_cast<float>(1.0e-4));
constexpr double kDefaultStagnationTolerance = static_cast<double>(static_cast<float>(2.0e-9));

void set_error(char *error, std::size_t error_size, const char *message) {
    if (!error || error_size == 0) return;
    std::snprintf(error, error_size, "%s", message ? message : "");
}

double elapsed(const clock_type::time_point &start) {
    return std::chrono::duration<double>(clock_type::now() - start).count();
}

double source_fac(double tau) {
    return tau > kFacThreshold ? (1.0 - std::exp(-tau)) / tau : 1.0;
}

double fortran_divide(double numerator, double denominator) {
    return numerator / denominator;
}

// v0.6.48.7.25.2: source calc_hmc_all stores temperature in kelvin and the
// mutable DSEC state commits it back to T4 after every evaluation.  Even when
// the physical value is unchanged, the explicit K -> T4 round trip can move a
// binary64 value by one ULP.  Preserve the two source operations and their
// rounding points instead of algebraically cancelling the scale factors.
double source_temperature_commit_t4(double temperature_t4) {
    volatile double temperature_k = temperature_t4 * 1.0e4;
    volatile double committed_t4 = temperature_k / 1.0e4;
    return committed_t4;
}

// Preserve the source/Python evaluation order for the late temperature
// secant.  Named volatile intermediates prohibit reassociation or accidental
// fused multiply-subtract contraction under optimized builds.
double source_temperature_secant(double tl, double hmctth,
                                  double th, double hmcttl) {
    volatile double low_product = tl * hmctth;
    volatile double high_product = th * hmcttl;
    volatile double numerator = low_product - high_product;
    volatile double denominator = hmctth - hmcttl;
    volatile double quotient = numerator / denominator;
    return quotient;
}

bool finite_nonnegative(double value) {
    return std::isfinite(value) && value >= 0.0;
}

struct TraceWriter {
    xstar_thermal_trace_event_v1 *data = nullptr;
    std::size_t capacity = 0;
    std::size_t count = 0;

    void add(uint32_t event_code, uint32_t evaluation_index,
             int ntotit, int nnt, int nntt, int nnx, int nnxx, int lnerr,
             const xstar_thermal_state_v1 &state, double hmctot, double elcter,
             double charge_residual, double stagnation) {
        if (count < capacity && data) {
            auto &row = data[count];
            std::memset(&row, 0, sizeof(row));
            row.event_code = event_code;
            row.evaluation_index = evaluation_index;
            row.ntotit = ntotit;
            row.nnt = nnt;
            row.nntt = nntt;
            row.nnx = nnx;
            row.nnxx = nnxx;
            row.lnerr = lnerr;
            row.temperature_t4 = state.temperature_t4;
            row.electron_fraction_xee = state.electron_fraction_xee;
            row.hmctot = hmctot;
            row.elcter = elcter;
            row.normalized_charge_residual = charge_residual;
            row.temperature_stagnation_metric = stagnation;
        }
        ++count;
    }
};
}  // namespace

struct xstar_thermal_context {
    uint64_t heatt_calls = 0;
    uint64_t dsec_calls = 0;
    std::vector<double> scratch;
};

extern "C" {

uint32_t xstar_thermal_engine_abi_version(void) { return XSTAR_THERMAL_ENGINE_ABI_VERSION; }
const char *xstar_thermal_engine_backend_name(void) { return "xstar_thermal_heatt_dsec_state_commit_engine_v06471"; }
uint32_t xstar_thermal_engine_feature_flags(void) {
    return XSTAR_THERMAL_STATUS_NATIVE_HEATT |
           XSTAR_THERMAL_STATUS_NATIVE_DSEC |
           XSTAR_THERMAL_STATUS_NATIVE_STATE_PROPAGATION |
           XSTAR_THERMAL_STATUS_PERSISTENT_CONTEXT |
           XSTAR_THERMAL_STATUS_CALLBACK_EVALUATION |
           XSTAR_THERMAL_STATUS_CALLBACK_STATE_PROPAGATION;
}

void xstar_heatt_workspace_init_v1(xstar_heatt_workspace_v1 *workspace) {
    if (!workspace) return;
    std::memset(workspace, 0, sizeof(*workspace));
    workspace->struct_size = sizeof(*workspace);
    workspace->abi_version = XSTAR_THERMAL_ENGINE_ABI_VERSION;
}
void xstar_heatt_stats_init_v1(xstar_heatt_stats_v1 *stats) {
    if (!stats) return;
    std::memset(stats, 0, sizeof(*stats));
    stats->struct_size = sizeof(*stats);
    stats->abi_version = XSTAR_THERMAL_ENGINE_ABI_VERSION;
}
void xstar_dsec_config_init_v1(xstar_dsec_config_v1 *config) {
    if (!config) return;
    std::memset(config, 0, sizeof(*config));
    config->struct_size = sizeof(*config);
    config->abi_version = XSTAR_THERMAL_ENGINE_ABI_VERSION;
    config->nlim = 1;
    config->maximum_evaluations = 0;
    config->tinf_t4 = 0.099;
    config->charge_tolerance = kDefaultChargeTolerance;
    config->thermal_tolerance = kDefaultThermalTolerance;
    config->temperature_stagnation_tolerance = kDefaultStagnationTolerance;
}
void xstar_thermal_state_init_v1(xstar_thermal_state_v1 *state) {
    if (!state) return;
    std::memset(state, 0, sizeof(*state));
    state->struct_size = sizeof(*state);
    state->abi_version = XSTAR_THERMAL_ENGINE_ABI_VERSION;
}
void xstar_thermal_evaluation_init_v1(xstar_thermal_evaluation_v1 *evaluation) {
    if (!evaluation) return;
    std::memset(evaluation, 0, sizeof(*evaluation));
    evaluation->struct_size = sizeof(*evaluation);
    evaluation->abi_version = XSTAR_THERMAL_ENGINE_ABI_VERSION;
    evaluation->hmctot = std::numeric_limits<double>::quiet_NaN();
    evaluation->elcter = std::numeric_limits<double>::quiet_NaN();
    evaluation->temperature_t4 = std::numeric_limits<double>::quiet_NaN();
    evaluation->electron_fraction_xee = std::numeric_limits<double>::quiet_NaN();
    evaluation->hydrogen_density_cm3 = std::numeric_limits<double>::quiet_NaN();
}
void xstar_dsec_stats_init_v1(xstar_dsec_stats_v1 *stats) {
    if (!stats) return;
    std::memset(stats, 0, sizeof(*stats));
    stats->struct_size = sizeof(*stats);
    stats->abi_version = XSTAR_THERMAL_ENGINE_ABI_VERSION;
}

int xstar_thermal_context_create_v1(xstar_thermal_context **out_context, char *error, size_t error_size) {
    if (!out_context) {
        set_error(error, error_size, "out_context is null");
        return XSTAR_THERMAL_ERROR_INVALID_ARGUMENT;
    }
    try {
        *out_context = new xstar_thermal_context();
    } catch (const std::bad_alloc &) {
        *out_context = nullptr;
        set_error(error, error_size, "thermal context allocation failed");
        return XSTAR_THERMAL_ERROR_INTERNAL;
    }
    set_error(error, error_size, "");
    return XSTAR_THERMAL_OK;
}

void xstar_thermal_context_destroy(xstar_thermal_context *context) { delete context; }

int xstar_thermal_context_reset_v1(xstar_thermal_context *context, char *error, size_t error_size) {
    if (!context) {
        set_error(error, error_size, "thermal context is null");
        return XSTAR_THERMAL_ERROR_INVALID_ARGUMENT;
    }
    context->heatt_calls = 0;
    context->dsec_calls = 0;
    context->scratch.clear();
    set_error(error, error_size, "");
    return XSTAR_THERMAL_OK;
}

int xstar_thermal_apply_heatt_v1(
    xstar_thermal_context *context,
    xstar_heatt_workspace_v1 *w,
    const xstar_heatt_line_v1 *lines,
    size_t line_count,
    const xstar_heatt_rrc_v1 *rrcs,
    size_t rrc_count,
    xstar_heatt_stats_v1 *stats,
    char *error,
    size_t error_size) {
    if (!context || !w || !stats) {
        set_error(error, error_size, "null thermal/heatt argument");
        return XSTAR_THERMAL_ERROR_INVALID_ARGUMENT;
    }
    if (w->abi_version != XSTAR_THERMAL_ENGINE_ABI_VERSION ||
        stats->abi_version != XSTAR_THERMAL_ENGINE_ABI_VERSION) {
        set_error(error, error_size, "thermal ABI mismatch");
        return XSTAR_THERMAL_ERROR_ABI_MISMATCH;
    }
    const size_t n = w->ncn2;
    const size_t nl = w->n_lines;
    const size_t nc = w->n_continua;
    if (n == 0 || !w->epi_eV || !w->bremsa || !w->opakc || !w->opakcont ||
        !w->brcems || !w->zrems || !w->zremso || !w->rccemis ||
        w->zrems_count < 5 * n || w->rccemis_count < 2 * n ||
        (nl && (!w->elum || !w->elumo || !w->rcem || !lines || line_count < nl)) ||
        (nc && (!w->elumab || !w->elumabo || !w->cemab))) {
        set_error(error, error_size, "invalid heatt workspace/capacity");
        return XSTAR_THERMAL_ERROR_CAPACITY;
    }
    for (size_t i = 0; i < n; ++i) {
        if (!std::isfinite(w->epi_eV[i]) || !std::isfinite(w->bremsa[i]) ||
            !std::isfinite(w->opakc[i]) || !std::isfinite(w->opakcont[i]) ||
            !std::isfinite(w->brcems[i])) {
            set_error(error, error_size, "non-finite heatt continuum input");
            return XSTAR_THERMAL_ERROR_NONFINITE;
        }
    }

    auto total_start = clock_type::now();
    xstar_heatt_stats_v1 local{};
    xstar_heatt_stats_init_v1(&local);
    local.status_flags = xstar_thermal_engine_feature_flags();
    local.calls = 1;
    local.continuum_bins = n;
    local.line_records = nl;
    local.rrc_records = rrc_count;

    const double r19 = w->radius_cm * kRadiusScale;
    const double fpr2 = kFourPi * r19 * r19;
    if (nl && fpr2 == 0.0) {
        set_error(error, error_size, "heatt line transfer requires nonzero radius");
        return XSTAR_THERMAL_ERROR_INVALID_ARGUMENT;
    }
    const double delrl = w->zone_thickness_cm;

    double clbrems = 0.0;
    double tmp2 = 0.0;
    for (size_t kl = 0; kl < n; ++kl) {
        const double tmp2o = tmp2;
        tmp2 = w->brcems[kl];
        if (kl >= 1) {
            clbrems += (tmp2 + tmp2o) * (w->epi_eV[kl] - w->epi_eV[kl - 1]) * kErgPerEv / 2.0;
        }
    }

    const auto continuum_start = clock_type::now();
    double hmctot = 0.0;
    double hpctot = 0.0;
    double epii = w->epi_eV[0];
    double hmctmp = 0.0;
    double hpctmp = 0.0;
    double optp2 = kOpacityFloor;
    for (size_t kl = 0; kl < n; ++kl) {
        optp2 = std::max(kOpacityFloor, w->opakc[kl]);
        const double epiio = epii;
        epii = w->epi_eV[kl];
        const double fac = source_fac(optp2 * delrl);
        const double tmph = w->bremsa[kl] * optp2;
        const double tmpc1 = w->rccemis[kl] + w->brcems[kl] * (1.0 - w->covering_fraction) / 2.0;
        const double tmpc2 = w->rccemis[n + kl] + w->brcems[kl] * (1.0 + w->covering_fraction) / 2.0;
        const double tmpc = (tmpc1 + tmpc2) * kFourPi;
        const double hmctmpo = hmctmp;
        const double hpctmpo = hpctmp;
        hmctmp = (tmph - tmpc) * fac;
        hpctmp = (tmph + tmpc) * fac;

        w->zrems[kl] = std::max(0.0, w->zremso[kl] - (tmph - kFourPi * (tmpc1 + tmpc2)) * fac * delrl * fpr2);
        w->zrems[n + kl] = w->zremso[n + kl] + kFourPi * tmpc1 * fac * delrl * fpr2;
        w->zrems[2 * n + kl] = w->zremso[2 * n + kl] + kFourPi * tmpc2 * fac * delrl * fpr2;
        if (kl >= 1) {
            const double de = epii - epiio;
            hmctot += (hmctmp + hmctmpo) * de * kErgPerEv / 2.0;
            hpctot += (hpctmp + hpctmpo) * de * kErgPerEv / 2.0;
        }
        optp2 = std::max(kOpacityFloor, w->opakcont[kl]);
        const double fac_cont = source_fac(optp2 * delrl);
        w->zrems[3 * n + kl] = w->zremso[3 * n + kl] + kFourPi * tmpc1 * fac_cont * delrl * fpr2;
        w->zrems[4 * n + kl] = w->zremso[4 * n + kl] + kFourPi * tmpc2 * fac_cont * delrl * fpr2;
    }
    local.continuum_seconds = elapsed(continuum_start);
    const double httot = (hmctot + hpctot) / 2.0;
    double cltot = (-hmctot + hpctot) / 2.0;

    const auto line_start = clock_type::now();
    for (size_t jk = 0; jk < nl; ++jk) {
        const auto &line = lines[jk];
        if (line.record != 0 && line.rate_type == 4 && line.wavelength_angstrom > 1.0 && line.wavelength_angstrom < 1.0e8) {
            const double inward_absorption = w->elumo[jk] * optp2 / fpr2;
            const double tmpc1 = w->rcem[jk];
            const double tmpc2 = w->rcem[nl + jk];
            const double tmpc = tmpc1 + tmpc2;
            optp2 = 0.0;
            hmctot -= tmpc;
            hpctot += tmpc;
            cltot += tmpc;
            w->elum[jk] = std::max(0.0, w->elumo[jk] + (-inward_absorption + tmpc1) * delrl * fpr2);
            const double tmph = w->elumo[nl + jk] * optp2 / fpr2;
            w->elum[nl + jk] = std::max(0.0, w->elumo[nl + jk] + (-tmph + tmpc2) * delrl * fpr2);
        }
    }
    local.line_seconds = elapsed(line_start);

    const auto rrc_start = clock_type::now();
    for (size_t i = 0; i < rrc_count; ++i) {
        const auto &rrc = rrcs[i];
        const int ci = rrc.continuum_index_one_based;
        if (!rrc.active || ci < 1 || static_cast<size_t>(ci) > nc) continue;
        const size_t j = static_cast<size_t>(ci - 1);
        const double emissivity_sum = w->cemab[j] + w->cemab[nc + j];
        if (emissivity_sum <= 2.0 * kRrcFloor) continue;
        const double increment = emissivity_sum * delrl * fpr2 / 2.0;
        w->elumab[j] = std::max(0.0, w->elumabo[j] + increment);
        w->elumab[nc + j] = std::max(0.0, w->elumabo[nc + j] + increment);
    }
    local.rrc_seconds = elapsed(rrc_start);
    local.commit_seconds = elapsed(total_start);
    local.state_commits = 1;
    local.fpr2 = fpr2;
    local.continuum_net_integral = hmctot;
    local.continuum_positive_integral = hpctot;
    local.pre_compton_heating = httot;
    local.pre_compton_cooling = cltot;
    local.bremsstrahlung_integral = clbrems;
    *stats = local;
    ++context->heatt_calls;
    set_error(error, error_size, "");
    return XSTAR_THERMAL_OK;
}

int xstar_thermal_run_evaluation_loop_v1(
    xstar_thermal_context *context,
    const xstar_dsec_config_v1 *config,
    xstar_thermal_state_v1 *state,
    xstar_thermal_evaluator_fn_v1 evaluator,
    void *user_data,
    xstar_thermal_trace_event_v1 *trace,
    size_t trace_capacity,
    size_t *trace_count,
    xstar_dsec_stats_v1 *stats,
    char *error,
    size_t error_size) {
    if (!context || !config || !state || !evaluator || !stats) {
        set_error(error, error_size, "null dsec argument");
        return XSTAR_THERMAL_ERROR_INVALID_ARGUMENT;
    }
    if (config->abi_version != XSTAR_THERMAL_ENGINE_ABI_VERSION ||
        state->abi_version != XSTAR_THERMAL_ENGINE_ABI_VERSION ||
        stats->abi_version != XSTAR_THERMAL_ENGINE_ABI_VERSION) {
        set_error(error, error_size, "thermal dsec ABI mismatch");
        return XSTAR_THERMAL_ERROR_ABI_MISMATCH;
    }
    if (!finite_nonnegative(state->electron_fraction_xee) ||
        !finite_nonnegative(state->hydrogen_density_cm3) ||
        !std::isfinite(state->temperature_t4) || state->temperature_t4 <= 0.0 ||
        !std::isfinite(config->tinf_t4) || config->tinf_t4 < 0.0) {
        set_error(error, error_size, "invalid initial dsec state/configuration");
        return XSTAR_THERMAL_ERROR_NONFINITE;
    }

    const auto orchestration_start = clock_type::now();
    const int nlim = config->nlim;
    const int maximum_evaluations = config->maximum_evaluations;
    const double crite = config->charge_tolerance > 0.0 ? config->charge_tolerance : kDefaultChargeTolerance;
    const double crith = config->thermal_tolerance > 0.0 ? config->thermal_tolerance : kDefaultThermalTolerance;
    const double critt = config->temperature_stagnation_tolerance > 0.0 ? config->temperature_stagnation_tolerance : kDefaultStagnationTolerance;
    const double tinf = config->tinf_t4;

    int ntotit = 0, nnt = 0, nntt = 0, lnerr = 0;
    int nlimt = std::max(nlim, 0), nlimx = std::abs(nlim);
    int nlimtt = std::max(nlimt, 1), nlimxx = std::max(nlimx, 1);
    double to = kInitialPreviousTemperature;
    double tl = 0.0, th = 0.0, xeel = 0.0, xeeh = 1.0;
    double elctrl = 1.0, elctrh = -1.0, hmctth = 0.0, hmcttl = 0.0;
    int iht = 0, ilt = 0, iuht = 0, iult = 0;
    uint32_t evaluation_index = 0;
    double last_hmctot = std::numeric_limits<double>::quiet_NaN();
    double last_elcter = std::numeric_limits<double>::quiet_NaN();
    double last_tst = std::numeric_limits<double>::quiet_NaN();
    double testt = std::numeric_limits<double>::quiet_NaN();
    bool prefix_terminated = false;
    double callback_seconds = 0.0;
    TraceWriter writer{trace, trace_capacity, 0};
    writer.add(XSTAR_THERMAL_EVENT_BEGIN, 0, 0, 0, 0, 0, 0, 0, *state,
               last_hmctot, last_elcter, last_tst, testt);

    while (true) {
        int nnx = 0;
        state->temperature_t4 = std::max(state->temperature_t4, tinf);
        if (state->temperature_t4 < tinf * kTinfProximityFactor) {
            nlimt = 0; nlimtt = 0; nlimx = 0; nlimxx = 0;
        } else {
            nlimt = std::max(nlim, 0); nlimx = std::abs(nlim); nlimxx = nlimx;
        }
        int nnxx = 0, ihx = 0, ilx = 0;

        while (true) {
            xstar_thermal_evaluation_v1 result{};
            xstar_thermal_evaluation_init_v1(&result);
            const auto callback_start = clock_type::now();
            ++evaluation_index;
            int rc = evaluator(user_data, state, &result, error, error_size);
            callback_seconds += elapsed(callback_start);
            if (rc != 0) {
                if (!error || !error[0]) set_error(error, error_size, "thermal evaluator callback failed");
                return XSTAR_THERMAL_ERROR_EVALUATOR;
            }
            if (!std::isfinite(result.hmctot) || !std::isfinite(result.elcter)) {
                set_error(error, error_size, "thermal evaluator returned non-finite residuals");
                return XSTAR_THERMAL_ERROR_NONFINITE;
            }
            // Source calc_hmc_all commits its mutable state before returning to
            // dsec.  v0.6.47 propagated only density/generation, leaving the
            // controller on the pre-callback temperature/electron state.  That
            // can alter the terminal secant/stagnation branch and downstream
            // float32 optical-depth writes.  Commit all callback-owned state
            // before residual tests, exactly where the Python source path does.
            if (!std::isfinite(result.temperature_t4) || result.temperature_t4 <= 0.0 ||
                !finite_nonnegative(result.electron_fraction_xee) ||
                !finite_nonnegative(result.hydrogen_density_cm3)) {
                set_error(error, error_size, "thermal evaluator returned invalid committed state");
                return XSTAR_THERMAL_ERROR_NONFINITE;
            }
            state->temperature_t4 = source_temperature_commit_t4(result.temperature_t4);
            state->electron_fraction_xee = result.electron_fraction_xee;
            state->hydrogen_density_cm3 = result.hydrogen_density_cm3;
            if (result.state_generation > state->state_generation) state->state_generation = result.state_generation;
            last_hmctot = result.hmctot;
            last_elcter = result.elcter;
            ++ntotit; ++nnx; ++nnxx;
            last_tst = std::abs(last_elcter) / std::max(kChargeDenominatorFloor, state->electron_fraction_xee);
            writer.add(XSTAR_THERMAL_EVENT_AFTER_EVALUATION, evaluation_index, ntotit, nnt, nntt, nnx, nnxx, lnerr,
                       *state, last_hmctot, last_elcter, last_tst, testt);

            if (maximum_evaluations > 0 && static_cast<int>(evaluation_index) >= maximum_evaluations) {
                prefix_terminated = true;
                break;
            }
            if (nnxx >= nlimxx || last_tst < crite) break;
            if (last_elcter < 0.0) {
                ihx = 1; xeeh = state->electron_fraction_xee; elctrh = last_elcter;
                if (ilx != 1) {
                    state->electron_fraction_xee *= kElectronFactor;
                    writer.add(XSTAR_THERMAL_EVENT_CHARGE_MULTIPLY, evaluation_index, ntotit, nnt, nntt, nnx, nnxx, lnerr,
                               *state, last_hmctot, last_elcter, last_tst, testt);
                    continue;
                }
            } else {
                ilx = 1; xeel = state->electron_fraction_xee; elctrl = last_elcter;
                if (ihx != 1) {
                    state->electron_fraction_xee /= kElectronFactor;
                    writer.add(XSTAR_THERMAL_EVENT_CHARGE_DIVIDE, evaluation_index, ntotit, nnt, nntt, nnx, nnxx, lnerr,
                               *state, last_hmctot, last_elcter, last_tst, testt);
                    continue;
                }
            }
            state->electron_fraction_xee = fortran_divide(xeel * elctrh - xeeh * elctrl, elctrh - elctrl);
            writer.add(XSTAR_THERMAL_EVENT_CHARGE_SECANT, evaluation_index, ntotit, nnt, nntt, nnx, nnxx, lnerr,
                       *state, last_hmctot, last_elcter, last_tst, testt);
        }
        if (prefix_terminated) break;
        ++nntt; ++nnt;
        writer.add(XSTAR_THERMAL_EVENT_CHARGE_EXIT, evaluation_index, ntotit, nnt, nntt, nnx, nnxx, lnerr,
                   *state, last_hmctot, last_elcter, last_tst, testt);
        if (std::abs(last_hmctot) <= crith || nntt >= nlimtt) break;
        if (nnt < nlimt) {
            if (last_hmctot < 0.0) {
                iht = 1; th = state->temperature_t4; hmctth = last_hmctot; iuht = 1;
                if (iult == 0) hmcttl /= 2.0;
                iult = 0;
                if (ilt != 1) {
                    state->temperature_t4 /= kTemperatureFactor;
                    if (std::abs(last_hmctot) > kFarFromEquilibrium) state->temperature_t4 /= kTemperatureFactor;
                    writer.add(XSTAR_THERMAL_EVENT_TEMPERATURE_DIVIDE, evaluation_index, ntotit, nnt, nntt, nnx, nnxx, lnerr,
                               *state, last_hmctot, last_elcter, last_tst, testt);
                    continue;
                }
            } else {
                ilt = 1; tl = state->temperature_t4; hmcttl = last_hmctot; iult = 1;
                if (iuht == 0) hmctth /= 2.0;
                iuht = 0;
                if (iht != 1) {
                    state->temperature_t4 *= kTemperatureFactor;
                    if (std::abs(last_hmctot) > kFarFromEquilibrium) state->temperature_t4 *= kTemperatureFactor;
                    writer.add(XSTAR_THERMAL_EVENT_TEMPERATURE_MULTIPLY, evaluation_index, ntotit, nnt, nntt, nnx, nnxx, lnerr,
                               *state, last_hmctot, last_elcter, last_tst, testt);
                    continue;
                }
            }
            testt = std::abs(1.0 - fortran_divide(state->temperature_t4, to));
            if (testt < critt) {
                lnerr = -2;
                writer.add(XSTAR_THERMAL_EVENT_TEMPERATURE_STAGNATION, evaluation_index, ntotit, nnt, nntt, nnx, nnxx, lnerr,
                           *state, last_hmctot, last_elcter, last_tst, testt);
                break;
            }
            to = state->temperature_t4;
            state->temperature_t4 = source_temperature_secant(tl, hmctth, th, hmcttl);
            writer.add(XSTAR_THERMAL_EVENT_TEMPERATURE_SECANT, evaluation_index, ntotit, nnt, nntt, nnx, nnxx, lnerr,
                       *state, last_hmctot, last_elcter, last_tst, testt);
            continue;
        }
        lnerr = 2;
        break;
    }
    writer.add(XSTAR_THERMAL_EVENT_FINISH, evaluation_index, ntotit, nnt, nntt, 0, 0, lnerr,
               *state, last_hmctot, last_elcter, last_tst, testt);
    if (trace_count) *trace_count = writer.count;

    xstar_dsec_stats_v1 local{};
    xstar_dsec_stats_init_v1(&local);
    local.status_flags = xstar_thermal_engine_feature_flags();
    local.lnerr = lnerr;
    local.ntotit = ntotit;
    local.temperature_iterations = nnt;
    local.temperature_attempts = nntt;
    local.charge_converged = std::isfinite(last_tst) && last_tst < crite;
    local.thermal_converged = std::isfinite(last_hmctot) && std::abs(last_hmctot) <= crith;
    local.prefix_terminated = prefix_terminated;
    local.evaluations_requested = evaluation_index;
    local.evaluations_completed = evaluation_index;
    local.state_commits = state->state_generation;
    local.callback_seconds = callback_seconds;
    local.orchestration_seconds = elapsed(orchestration_start) - callback_seconds;
    local.final_hmctot = last_hmctot;
    local.final_elcter = last_elcter;
    local.final_charge_residual = last_tst;
    local.final_temperature_t4 = state->temperature_t4;
    local.final_electron_fraction_xee = state->electron_fraction_xee;
    local.final_temperature_stagnation_metric = testt;
    *stats = local;
    ++context->dsec_calls;
    set_error(error, error_size, "");
    return XSTAR_THERMAL_OK;
}

// Legacy probes retained for compatibility with pre-v0.6.47.1 component loading.
int xstar_thermal_probe() { return 1; }
int xstar_thermal_abi_version() { return static_cast<int>(XSTAR_THERMAL_ENGINE_ABI_VERSION); }
const char *xstar_thermal_backend_name() { return xstar_thermal_engine_backend_name(); }
uint32_t xstar_thermal_feature_flags() { return xstar_thermal_engine_feature_flags(); }

}  // extern "C"
