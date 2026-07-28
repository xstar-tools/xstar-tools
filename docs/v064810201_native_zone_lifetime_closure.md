# v0.6.48.10.2.0.1 native-zone active-stage/lifetime initialization closure

## Scope

This hotfix keeps the v0.6.48.10.2.0 persistent native single-zone DSEC architecture, but corrects two zone-entry source-lifetime states before the first native fixed-state evaluation of each radial shell. It does not change the accepted Type49/53, Type50, rate, matrix, emissivity, opacity, thermal, final-recompute, binemis, transport, or FITS numerical kernels.

## Rejected 10.2.0 behavior

The first native zone independently widened the Mg active window to stage 2..12, whereas the source/Python pre-matrix selector retained a narrower compact window. The same bridge also interpreted a legitimate zone-1 neutral-hydrogen density of zero as missing and substituted `1e4 cm^-3`. The result was an immediate thermal trajectory error (`log(t)` about 4.95 instead of about 4.81), bad `h-c(%)`, and only three completed zones.

## 10.2.0.1 correction

At entry to every native zone, Python executes only the source-faithful pre-matrix ion-window selector and passes the resulting `(mml, mmu)` for every active element to the persistent C++ context. A new state-lifetime setter seeds those windows before DSEC evaluation 1. Zone-1 source sequences 2..4 retain the seeded window; subsequent evaluations resume ordinary source recomputation.

Hydrogen entry state is now literal source state:

`xh0 = xpx * xilevg(H I ground) * abundance(H)`

`xh1 = xpx * (1 - xilevg(H I ground)) * abundance(H)`

Zero is valid and is never replaced by a synthetic floor. Repeated evaluations continue from the native H-ground population produced by the preceding fixed-state evaluation.

## Qualification policy

The host runner executes `--zone-backend cpp` first. Before launching the expensive `--zone-backend python` fallback, a candidate preflight requires:

- four completed zones;
- DSEC counts 20/1/17/16;
- ABI 604810201;
- all four source-entry Mg window markers present with no stage-2 leak;
- exact zone-1 H entry densities for the Mg XI benchmark (`xh0=0`, `xh1=1e8 cm^-3`);
- four native DSEC terminal markers and a broad zone-1 temperature sanity gate;
- zero product identities and zero cells above 1% versus the accepted 10.1.1 products.

Only then is the Python-zone fallback run. It must remain bit-exact to 10.1.1, followed by the existing structural, detal4, and spectrum science gates.
