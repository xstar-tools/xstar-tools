# XSTAR test runs for xstar-atomic validation

This directory contains small direct-XSTAR test outputs used to validate
`xstar-atomic` against XSTAR's own `xout_lines1.fits` line lists.

The included FITS files are direct XSTAR outputs. The included CSV files were
created from those FITS files with `xstar_atomic.xstar_outputs`.

## Directory contents

```text
xstar_test_run/
  o_ne_xi3/xout_lines1.fits
  o7_xi15/xout_lines1.fits
  o7_xi15_highdens/xout_lines1.fits
  ne_xi25/xout_lines1.fits
  ne_xi35/xout_lines1.fits
  xstar_o_ne_xi3_lines.csv
  xstar_o8_lya_lines.csv
  xstar_o7_triplet_lines.csv
  xstar_ne9_triplet_lines.csv
  xstar_ne10_lya_lines.csv
```


The Ne IX / Ne X Stage-5 validation products included here were generated with
the commands in Section 2. The saved comparisons match all selected Ne IX and
Ne X lines within 0.02 Angstrom: five Ne IX triplet/near-triplet components and
two Ne X Ly-alpha components.

The `xout_lines1.fits` table has the XSTAR `XSTAR_LINES` HDU columns:

```text
index, ion, lower_level, upper_level, wavelength,
emit_inward, emit_outward, depth_inward, depth_outward
```

## 1. O VIII / Ne IX high-ionization line validation

This run is the closest match to the `xstar_atomic` tests for O VIII Ly-alpha
and Ne IX/type-98 collision lines. It uses high ionization, O+Ne only, and a
small column.

Run it in a clean directory, for example `xstar_runs/o_ne_xi3/`, because XSTAR
writes fixed output names such as `xout_lines1.fits`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_o_ne_xi3' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e10 \
  rlrad38=1e6 column=1e20 rlogxi=3.0 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=1 fabund=0 neabund=1 naabund=0 mgabund=0 \
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0
```


## 2. Ne IX / Ne X focused XSTAR comparison runs

The O+Ne high-ionization run above is useful for both O VIII and Ne IX, but
Stage-5 validation should also include Ne-only runs that make the Ne IX and
Ne X features easier to inspect. Run each model in a clean directory because
XSTAR writes fixed output names such as `xout_lines1.fits`.

### 2.1 Ne IX focused run

This run uses neon only, with a moderately high ionization parameter intended
to keep strong He-like neon lines. A useful directory name is
`xstar_runs/ne_xi25/`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_ne_xi25' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e10 \
  rlrad38=1e6 column=1e20 rlogxi=2.5 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=0 fabund=0 neabund=1 naabund=0 mgabund=0 \
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0
```

### 2.2 Ne X focused run

This run uses neon only and a higher ionization parameter to favor H-like Ne X
features. A useful directory name is `xstar_runs/ne_xi35/`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_ne_xi35' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e10 \
  rlrad38=1e6 column=1e20 rlogxi=3.5 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=0 fabund=0 neabund=1 naabund=0 mgabund=0 \
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0
```

Suggested first-pass line filters after each run:

```bash
# Ne IX He-like triplet/near-triplet region
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/ne_xi25/xout_lines1.fits \
  --ion "Ne IX" \
  --wavelength-min 13.3 \
  --wavelength-max 13.8 \
  --out-csv xstar_ne9_triplet_lines.csv \
  --print-summary \
  --print-rows

# Ne X Ly-alpha region
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/ne_xi35/xout_lines1.fits \
  --ion "Ne X" \
  --wavelength-min 12.0 \
  --wavelength-max 12.3 \
  --out-csv xstar_ne10_lya_lines.csv \
  --print-summary \
  --print-rows
```

Comparison commands:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_ne9_triplet_lines.csv \
  --ion "Ne IX" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_ne9_triplet_wavelength.csv \
  --out-json compare_ne9_triplet_wavelength.json \
  --print-summary

PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_ne10_lya_lines.csv \
  --ion "Ne X" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_ne10_lya_wavelength.csv \
  --out-json compare_ne10_lya_wavelength.json \
  --print-summary
```

If either line list is weak or empty, rerun a small `rlogxi` scan around the
suggested values; the best ionization balance depends on the SED, density, and
column used in the XSTAR model.


## 3. Mg XI / Mg XII, Si XIII / Si XIV, and Fe XXV / Fe XXVI Stage-5 runs

These runs extend the Stage-5 wavelength-validation workflow from O and Ne to
Mg, Si, and Fe.  Run each model in a clean directory because XSTAR writes fixed
output names such as `xout_lines1.fits`.  The `rlogxi` values below are intended
as first-pass validation points.  If a selected line list is weak or empty, run a
small `rlogxi` scan around the suggested value.

### 3.1 Mg XI focused run

This run uses magnesium only and a moderately high ionization parameter to keep
He-like Mg XI lines near 9.17--9.31 Angstrom.  A useful directory name is
`xstar_runs/mg_xi25/`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_mg_xi25' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e10 \
  rlrad38=1e6 column=1e20 rlogxi=2.5 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=0 fabund=0 neabund=0 naabund=0 mgabund=1 \
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0
```

### 3.2 Mg XII focused run

This run uses magnesium only and a higher ionization parameter to favor H-like
Mg XII Ly-alpha near 8.42 Angstrom.  A useful directory name is
`xstar_runs/mg_xi35/`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_mg_xi35' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e10 \
  rlrad38=1e6 column=1e20 rlogxi=3.5 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=0 fabund=0 neabund=0 naabund=0 mgabund=1 \
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0
```

### 3.3 Si XIII focused run

This run uses silicon only and is intended for He-like Si XIII lines near
6.65--6.74 Angstrom.  A useful directory name is `xstar_runs/si_xi30/`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_si_xi30' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e10 \
  rlrad38=1e6 column=1e20 rlogxi=3.0 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=0 fabund=0 neabund=0 naabund=0 mgabund=0 \
  alabund=0 siabund=1 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0
```

### 3.4 Si XIV focused run

This run uses silicon only and a higher ionization parameter to favor H-like
Si XIV Ly-alpha near 6.18 Angstrom.  A useful directory name is
`xstar_runs/si_xi40/`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_si_xi40' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e10 \
  rlrad38=1e6 column=1e20 rlogxi=4.0 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=0 fabund=0 neabund=0 naabund=0 mgabund=0 \
  alabund=0 siabund=1 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0
```

### 3.5 Fe XXV focused run

This run uses iron only and is intended for He-like Fe XXV K-alpha lines near
1.85 Angstrom.  A useful directory name is `xstar_runs/fe_xi35/`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_fe_xi35' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e10 \
  rlrad38=1e6 column=1e20 rlogxi=3.5 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=0 fabund=0 neabund=0 naabund=0 mgabund=0 \
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=1 coabund=0 niabund=0 cuabund=0 znabund=0
```

### 3.6 Fe XXVI focused run

This run uses iron only and a higher ionization parameter to favor H-like
Fe XXVI Ly-alpha near 1.78 Angstrom.  A useful directory name is
`xstar_runs/fe_xi45/`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_fe_xi45' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e10 \
  rlrad38=1e6 column=1e20 rlogxi=4.5 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=0 fabund=0 neabund=0 naabund=0 mgabund=0 \
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=1 coabund=0 niabund=0 cuabund=0 znabund=0
```

Suggested first-pass line filters after each run:

```bash
# Mg XI He-like triplet/near-triplet region
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/mg_xi25/xout_lines1.fits \
  --ion "Mg XI" \
  --wavelength-min 9.0 \
  --wavelength-max 9.4 \
  --out-csv xstar_mg11_triplet_lines.csv \
  --print-summary \
  --print-rows

# Mg XII Ly-alpha region
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/mg_xi35/xout_lines1.fits \
  --ion "Mg XII" \
  --wavelength-min 8.35 \
  --wavelength-max 8.50 \
  --out-csv xstar_mg12_lya_lines.csv \
  --print-summary \
  --print-rows

# Si XIII He-like triplet/near-triplet region
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/si_xi30/xout_lines1.fits \
  --ion "Si XIII" \
  --wavelength-min 6.55 \
  --wavelength-max 6.80 \
  --out-csv xstar_si13_triplet_lines.csv \
  --print-summary \
  --print-rows

# Si XIV Ly-alpha region
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/si_xi40/xout_lines1.fits \
  --ion "Si XIV" \
  --wavelength-min 6.10 \
  --wavelength-max 6.25 \
  --out-csv xstar_si14_lya_lines.csv \
  --print-summary \
  --print-rows

# Fe XXV He-like K-alpha region
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/fe_xi35/xout_lines1.fits \
  --ion "Fe XXV" \
  --wavelength-min 1.83 \
  --wavelength-max 1.88 \
  --out-csv xstar_fe25_ka_lines.csv \
  --print-summary \
  --print-rows

# Fe XXVI Ly-alpha region
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/fe_xi45/xout_lines1.fits \
  --ion "Fe XXVI" \
  --wavelength-min 1.76 \
  --wavelength-max 1.80 \
  --out-csv xstar_fe26_lya_lines.csv \
  --print-summary \
  --print-rows
```

Comparison commands:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits xstar_mg11_triplet_lines.csv \
  --ion "Mg XI" --wavelength-column wavelength --reference-column emit_outward \
  --mode wavelength --temperature 1e6 --wavelength-tolerance 0.02 \
  --out-csv compare_mg11_triplet_wavelength.csv \
  --out-json compare_mg11_triplet_wavelength.json --print-summary

PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits xstar_mg12_lya_lines.csv \
  --ion "Mg XII" --wavelength-column wavelength --reference-column emit_outward \
  --mode wavelength --temperature 1e6 --wavelength-tolerance 0.02 \
  --out-csv compare_mg12_lya_wavelength.csv \
  --out-json compare_mg12_lya_wavelength.json --print-summary

PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits xstar_si13_triplet_lines.csv \
  --ion "Si XIII" --wavelength-column wavelength --reference-column emit_outward \
  --mode wavelength --temperature 1e6 --wavelength-tolerance 0.02 \
  --out-csv compare_si13_triplet_wavelength.csv \
  --out-json compare_si13_triplet_wavelength.json --print-summary

PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits xstar_si14_lya_lines.csv \
  --ion "Si XIV" --wavelength-column wavelength --reference-column emit_outward \
  --mode wavelength --temperature 1e6 --wavelength-tolerance 0.02 \
  --out-csv compare_si14_lya_wavelength.csv \
  --out-json compare_si14_lya_wavelength.json --print-summary

PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits xstar_fe25_ka_lines.csv \
  --ion "Fe XXV" --wavelength-column wavelength --reference-column emit_outward \
  --mode wavelength --temperature 1e6 --wavelength-tolerance 0.02 \
  --out-csv compare_fe25_ka_wavelength.csv \
  --out-json compare_fe25_ka_wavelength.json --print-summary

PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits xstar_fe26_lya_lines.csv \
  --ion "Fe XXVI" --wavelength-column wavelength --reference-column emit_outward \
  --mode wavelength --temperature 1e6 --wavelength-tolerance 0.02 \
  --out-csv compare_fe26_lya_wavelength.csv \
  --out-json compare_fe26_lya_wavelength.json --print-summary
```

## 4. O VII triplet / recombination-cascade validation

For O VII, use a lower ionization parameter. This run is mainly for the O VII
triplet around 21.6--22.1 Angstrom and recombination/cascade behavior.

Run it in a clean directory, for example `xstar_runs/o7_xi15/`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_o7_xi15' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e10 \
  rlrad38=1e6 column=1e20 rlogxi=1.5 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=1 fabund=0 neabund=0 naabund=0 mgabund=0 \
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0
```

## 5. O VII triplet / recombination-cascade validation at higher density

This is similar to the second run, but at higher density to test
density-sensitive level-population effects. It is useful for checking the
influence of same-`n` l-mixing and metastable coupling.

Run it in a clean directory, for example `xstar_runs/o7_xi15_highdens/`.

```bash
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_o7_xi15_highdens' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1e12 \
  rlrad38=1e6 column=1e20 rlogxi=1.5 vturbi=100 \
  habund=1 heabund=1 \
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \
  oabund=1 fabund=0 neabund=0 naabund=0 mgabund=0 \
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0
```

## Converting XSTAR FITS outputs to CSV

Convert the full O/Ne line list:

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/o_ne_xi3/xout_lines1.fits \
  --out-csv xstar_o_ne_xi3_lines.csv \
  --print-summary
```

Filter O VIII Ly-alpha-like lines:

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/o_ne_xi3/xout_lines1.fits \
  --ion "O VIII" \
  --wavelength-min 18.8 \
  --wavelength-max 19.1 \
  --out-csv xstar_o8_lya_lines.csv \
  --print-summary \
  --print-rows
```

Filter O VII triplet lines:

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xstar_runs/o7_xi15/xout_lines1.fits \
  --ion "O VII" \
  --wavelength-min 21.4 \
  --wavelength-max 22.2 \
  --out-csv xstar_o7_triplet_lines.csv \
  --print-summary \
  --print-rows
```

## Comparing with xstar-atomic

O VIII Ly-alpha wavelength comparison:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_test_run/xstar_o8_lya_lines.csv \
  --ion "O VIII" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_o8_lya_wavelength.csv \
  --out-json compare_o8_lya_wavelength.json \
  --print-summary
```

O VII triplet wavelength comparison:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_test_run/xstar_o7_triplet_lines.csv \
  --ion "O VII" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_o7_triplet_wavelength.csv \
  --out-json compare_o7_triplet_wavelength.json \
  --print-summary
```

Ne IX triplet/near-triplet wavelength comparison using the included CSV:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_test_run/xstar_ne9_triplet_lines.csv \
  --ion "Ne IX" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_ne9_triplet_wavelength.csv \
  --out-json compare_ne9_triplet_wavelength.json \
  --print-summary
```

Ne X Ly-alpha wavelength comparison using the included CSV:

```bash
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits \
  xstar_test_run/xstar_ne10_lya_lines.csv \
  --ion "Ne X" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_ne10_lya_wavelength.csv \
  --out-json compare_ne10_lya_wavelength.json \
  --print-summary
```

The first validation goal is wavelength and transition identification. XSTAR
`emit_inward` and `emit_outward` are full model outputs, while `xstar-atomic`
emissivity rows are local atomic coefficients; their absolute values are not
expected to agree without reproducing XSTAR's ion fractions, geometry, column,
density, and radiative-transfer treatment.
