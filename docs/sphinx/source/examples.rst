Examples
========

The package ships with runnable Python examples under ``examples/``.

High-level API quickstart
-------------------------

.. literalinclude:: ../../../examples/06_high_level_api_quickstart.py
   :language: python

O VIII Ly-alpha lines
---------------------

.. literalinclude:: ../../../examples/01_o8_lya_lines.py
   :language: python

O VIII Ly-alpha collisions
--------------------------

.. literalinclude:: ../../../examples/02_o8_lya_collisions.py
   :language: python

O VIII Ly-alpha emissivity
--------------------------

.. literalinclude:: ../../../examples/03_o8_lya_emissivity.py
   :language: python

Oxygen recombination inventory
------------------------------

.. literalinclude:: ../../../examples/04_oxygen_recombination_inventory.py
   :language: python

Low-level ATDB indexing
-----------------------

.. literalinclude:: ../../../examples/05_low_level_atdb_index.py
   :language: python


Additional examples
-------------------

The package includes additional scripts under ``examples/``:

* ``07_collision_decoder_validation.py``: inventory and validate collision decoder targets.
* ``08_compare_xstar_outputs.py``: compare xstar-atomic rows with user-supplied XSTAR output CSVs.
* ``09_export_band_emissivity.py``: export CSV/HDF5 line-based X-ray band emissivity products.
* ``10_o7_triplet_sparse_solver.py``: run an O VII sparse-solver/triplet diagnostic stress test.
* ``11_solver_timing.py``: benchmark dense/sparse level-population solver execution times.

Plasma export and band emissivity
---------------------------------

Use the export CLI to write compact CSV/JSON/HDF5 bundles for selected ions::

   PYTHONPATH=src python -m xstar_atomic.export atdb.fits \
     --ions "O VIII,Ne IX" \
     --temperatures 1e6 3e6 1e7 \
     --wavelength-min 1.0 --wavelength-max 40.0 \
     --formats csv,hdf5 \
     --out-dir atomic_export \
     --print-summary

Line-based broad-band products are enabled with ``--bands-kev``::

   PYTHONPATH=src python -m xstar_atomic.export atdb.fits \
     --ions "O VIII,Ne IX" \
     --temperatures 1e6 3e6 1e7 \
     --wavelength-min 1.0 --wavelength-max 40.0 \
     --bands-kev soft:0.5:2.0 osoft:0.3:0.6 med:0.6:1.0 hard:2.0:10.0 \
     --formats csv,hdf5 \
     --out-dir atomic_export \
     --print-summary

The band export writes ``*_band_emissivity.csv`` and a ``/band_emissivity``
group in each per-ion HDF5 file.  Zero-line bands keep the ion label and use
``methods_used="none"``.

Band-emissivity example
-----------------------

.. literalinclude:: ../../../examples/09_export_band_emissivity.py
   :language: python


O VII sparse solver triplet diagnostic example
----------------------------------------------

.. literalinclude:: ../../../examples/10_o7_triplet_sparse_solver.py
   :language: python

Solver step profiling
---------------------

Profile the main stages of one O VIII solver run::

   PYTHONPATH=src python examples/12_profile_solver_steps.py \
     ../xstar/data/atdb.fits \
     --element O --ion-stage 8 \
     --wavelength-min 18.8 --wavelength-max 19.1 \
     --temperature 1e6 --electron-density 1.0 \
     --linear-solver sparse \
     --index-cache \
     --index-cache-format npz \
     --out-dir solver_profile_npz_arrays_hit

Prototype O VII recombination/cascade workflow
----------------------------------------------

Run the current Stage-6 prototype source/cascade workflow::

   PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
     ../xstar/data/atdb.fits \
     --out-dir o7_recomb_cascade_workflow \
     --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv

The O VII workflow uses total recombination rates and approximate radiative
branching redistribution.  It is intended for solver/source-file validation and
sensitivity studies, not final physical triplet predictions.


Solver profiling and O VII cascade workflow
-------------------------------------------

The profiling example reports wall-clock timings for ATDB opening, index
building, level/line/collision extraction, collision evaluation, matrix
assembly, linear solving, and output writing::

   PYTHONPATH=src python examples/12_profile_solver_steps.py \
     ../xstar/data/atdb.fits \
     --element O --ion-stage 8 \
     --wavelength-min 18.8 --wavelength-max 19.1 \
     --temperature 1e6 --electron-density 1.0 \
     --linear-solver sparse \
     --index-cache \
     --index-cache-format npz \
     --out-dir solver_profile_npz_arrays_hit

The Stage-6 prototype O VII recombination/cascade workflow evaluates total
O VIII -> O VII recombination, redistributes source terms through an approximate
radiative-branching cascade, feeds the source CSV into the sparse solver, and
computes prototype R=f/i and G=(f+i)/r diagnostics::

   PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
     ../xstar/data/atdb.fits \
     --out-dir o7_recomb_cascade_workflow \
     --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
     --print-summary

This is a source-interface and sensitivity workflow, not yet a final
level-resolved recombination/cascade model.

Data download/configuration example
-----------------------------------

Use ``examples/14_download_or_configure_data.py`` to download ``atdb.fits`` or
save the path to an existing local copy:

.. code-block:: bash

   PYTHONPATH=src python examples/14_download_or_configure_data.py

or:

.. code-block:: bash

   PYTHONPATH=src python examples/14_download_or_configure_data.py --set-path /path/to/atdb.fits


Stage 6 O VII cascade-yield workflow
------------------------------------

The O VII recombination/cascade workflow can now use ``selected-cascade-yield``
source allocation.  This weights selected source levels by their radiative
cascade probability of feeding selected target levels.

.. code-block:: bash

   PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
     ../xstar/data/atdb.fits \
     --source-mode selected-cascade-yield \
     --cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0 \
     --cascade-weight-floor 0.02 \
     --out-dir o7_recomb_cascade_workflow \
     --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
     --print-summary


Stage-6 O VII triplet target maps
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The recommended Stage-6 baseline is the equal-target map ``--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0``, because it preserved the good ``G=(f+i)/r`` agreement with the XSTAR O VII reference. For experiments that try to reduce ``R=f/i`` without strongly changing ``G``, use a forbidden-to-intercombination shift preset such as ``--cascade-target-preset o7-triplet-f2i025-rkeep``. It expands to ``2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0`` and preserves the resonance target plus the approximate total triplet-target weight. Manual ``--cascade-target-levels`` overrides any preset.

.. code-block:: bash

   PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
     ../xstar/data/atdb.fits \
     --source-mode selected-cascade-yield \
     --cascade-target-preset o7-triplet-f2i025-rkeep \
     --cascade-weight-floor 0.02 \
     --out-dir o7_recomb_cascade_workflow_f2i025_rkeep \
     --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
     --print-summary

Stage-6 O VII cascade tuning scan
---------------------------------

The equal-target ``selected-cascade-yield`` map remains the recommended Stage-6
baseline because it preserves the good XSTAR agreement in ``G=(f+i)/r``::

  --source-mode selected-cascade-yield \
  --cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0

For controlled experiments, the preferred presets now shift target weight from
forbidden into intercombination levels while preserving the resonance target and
the total triplet-target weight. This is intended to reduce ``R=f/i`` without
strongly moving ``G=(f+i)/r`` away from the equal-target baseline::

  o7-triplet-f2i010-rkeep -> 2:0.90,3:1.0333333333,4:1.0333333333,5:1.0333333333,7:1.0
  o7-triplet-f2i015-rkeep -> 2:0.85,3:1.05,4:1.05,5:1.05,7:1.0
  o7-triplet-f2i025-rkeep -> 2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0
  o7-triplet-f2i050-rkeep -> 2:0.50,3:1.1666666667,4:1.1666666667,5:1.1666666667,7:1.0

The older simple ``fdown`` presets remain available for reproducibility, but
they reduced ``G`` too much in the first tuning scan.

Use the tuning scan helper to run the equal baseline plus the experimental
presets and summarize ``R=f/i`` and ``G=(f+i)/r`` relative to the saved XSTAR O
VII reference::

  PYTHONPATH=src python examples/15_o7_cascade_tuning_scan.py \
    ../xstar/data/atdb.fits \
    --out-dir o7_cascade_tuning_scan \
    --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
    --print-summary

The scan writes ``o7_cascade_tuning_scan.csv`` and a JSON summary. The aim is to
reduce ``R`` while keeping ``G`` close to the equal-target/XSTAR value; the equal
map should remain the baseline unless an experimental preset improves both.



O VII metastable/intercombination coupling diagnostics
------------------------------------------------------

The Stage-6 O VII triplet workflow can be followed by an explicit inspection of
metastable/intercombination coupling rates.  This diagnostic focuses on level
2 to levels 3, 4, and 5 and compares collisional transfer rates with decoded
radiative rates as a function of electron density.

.. code-block:: bash

   PYTHONPATH=src python examples/16_o7_metastable_coupling_diagnostics.py \
     ../xstar/data/atdb.fits \
     --temperature 1e6 \
     --electron-densities 1 1e4 1e8 1e10 1e12 \
     --index-cache --index-cache-format npz \
     --out-dir o7_metastable_coupling \
     --print-summary

The output files are ``o7_metastable_coupling_rates.csv`` and
``o7_metastable_coupling_summary.json``.


Type-68-aware O VII cascade tuning scan
---------------------------------------

After He-like collision data types 67/68/69 are enabled, O VII includes the
metastable-to-intercombination coupling from level 2 into levels 3, 4, and 5.
This gives the expected density-sensitive behavior in ``R=f/i``, but it can make
the low-density ``G=(f+i)/r`` too small for the previous cascade-source map.
The type-68-aware scan keeps the equal triplet weights fixed and progressively
downweights the resonance target level 7::

  o7-triplet-type68-r095 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.95
  o7-triplet-type68-r090 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.90
  o7-triplet-type68-r085 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.85
  o7-triplet-type68-r080 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.80
  o7-triplet-type68-r075 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.75
  o7-triplet-type68-r070 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.70
  o7-triplet-type68-r060 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.60
  o7-triplet-type68-r050 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.50

Run the scan with::

  PYTHONPATH=src python examples/17_o7_type68_cascade_tuning_scan.py \
    ../xstar/data/atdb.fits \
    --out-dir o7_type68_cascade_tuning_scan \
    --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
    --print-summary

The scan writes ``o7_type68_cascade_tuning_scan.csv``,
``o7_type68_cascade_tuning_scan_all_densities.csv``, and a JSON summary. Use this
scan after the type-67/68/69 He-like collision decoders are active. The equal
target map remains the reference baseline; the type-68-aware presets are
experiments for restoring ``G`` while preserving the density-sensitive ``R``
physics.


Type-68-aware two-parameter O VII cascade scan
------------------------------------------------

The broader Stage-6 scan varies both forbidden/intercombination redistribution
and resonance suppression after He-like type 67/68/69 collision coupling is
enabled.  For a forbidden-to-intercombination shift ``d`` and resonance weight
``r``, it scans target maps of the form::

  2:(1-d),3:(1+d/3),4:(1+d/3),5:(1+d/3),7:r

Run it with::

  PYTHONPATH=src python examples/18_o7_type68_2d_cascade_tuning_scan.py \
    ../xstar/data/atdb.fits \
    --out-dir o7_type68_2d_cascade_tuning_scan \
    --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
    --print-summary

The helper writes compact, ranked, and all-density CSV tables plus a JSON
summary.  The equal-target map remains the baseline; this scan is for testing
whether a combined resonance-suppression and forbidden-to-intercombination
redistribution improves both ``R=f/i`` and ``G=(f+i)/r`` relative to the saved
XSTAR O VII reference.

.. literalinclude:: ../../../examples/18_o7_type68_2d_cascade_tuning_scan.py
   :language: python

Stage-6 cascade source-fit diagnostic
-------------------------------------

The example ``examples/19_o7_cascade_source_fit.py`` builds a radiative cascade
matrix ``Y(source level -> forbidden, intercombination, resonance)`` and solves
for nonnegative source weights that best reproduce the saved XSTAR O VII triplet
ratios.

.. code-block:: bash

   PYTHONPATH=src python examples/19_o7_cascade_source_fit.py \
     ../xstar/data/atdb.fits \
     --index-cache --index-cache-format npz \
     --out-dir o7_cascade_source_fit \
     --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
     --print-summary

The example writes ``o7_cascade_yield_matrix.csv``,
``o7_source_fit_weights.csv``, and ``o7_source_fit_summary.json``.  The result is
a diagnostic for source-level feeding, not a final physical recombination model.


### Stage-6 empirical source-fit mode

The O VII cascade source-fit diagnostic writes `o7_source_fit_weights.csv`. These weights can be reused as an empirical diagnostic source allocation with:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-fit-weights \
  --source-fit-weights-csv xstar_test_run/o7_source_fit_weights.csv \
  --out-dir o7_recomb_cascade_workflow_fit_weights \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

A convenience diagnostic mode is also available:

```bash
--source-mode o7-xstar-fit
```

When no explicit `--source-fit-weights-csv` is supplied, this mode looks for the packaged/source-tree reference file `xstar_test_run/o7_source_fit_weights.csv`. These fitted weights are empirical diagnostics derived from the current O VII/XSTAR comparison, not true level-resolved recombination rates.

### Stage-6 full-solver source-fit diagnostic

The cascade-yield fit in `examples/19_o7_cascade_source_fit.py` is useful for testing the radiative branching network, but its fitted weights are not guaranteed to reproduce the same R/G ratios when injected into the full statistical-equilibrium solver.  For the stricter full-solver diagnostic, use the rank-aware SVD treatment that was validated against the saved XSTAR O VII triplet reference:

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit \
  --print-summary
```

The recommended diagnostic solver settings are:

```text
linear_solver = svd
rank_deficient_action = svd
negative_population_action = keep
prune_null_rate_levels = true
source_total_rate = 1.0 s^-1
```

These settings are important because the O VII statistical-equilibrium matrix is rank-deficient and highly ill-conditioned.  In the validation run, the combined-source solve used `numpy.linalg.svd_lstsq`, had matrix rank `231/238`, condition number about `3.1e18`, residuals `linear_residual_l2 ~ 0.0032` and `linear_residual_linf ~ 0.0032`, and one raw negative population retained for diagnostic linearity.  Null-rate pruning removed levels `44`, `45`, and `241`.

The script automatically performs a combined-source validation solve after fitting the weights.  Its summary reports the XSTAR R/G target, the fitted linear-response R/G prediction, and the actual simultaneous-solver R/G result, together with matrix rank, condition number, residuals, null-rate pruning diagnostics, source/sink summaries, and negative-population diagnostics.  Use `--skip-combined-validation` only when you want the older response-matrix-only behavior.

A validated v0.2.62 run gave:

```text
XSTAR R=3.20837 G=10.5622
Fitted linear-response R=3.20838 G=10.5622
Combined simultaneous-solver R=3.20838 G=10.5622
R/R_XSTAR = 1.00000146
G/G_XSTAR = 0.99999836
```

The compatible output weights can then be used with the recombination/cascade workflow.  Use the same SVD/rank-aware solver treatment and scale the solver source CSV to the same total source rate used by the fit:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-fit-weights \
  --source-fit-weights-csv o7_solver_source_fit/o7_source_fit_weights.csv \
  --solver-source-csv-mode initial \
  --solver-source-total-rate 1.0 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --out-dir o7_recomb_cascade_workflow_solver_fit \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

These weights are empirical diagnostics, not physical level-resolved recombination rates.  The recommended SVD path is the validated path for this O VII/XSTAR-fit diagnostic; direct dense or sparse solves should not be trusted for this rank-deficient matrix unless their residual and combined-source validation diagnostics are checked.




Validated O VII diagnostic commands
-----------------------------------

The validated O VII empirical solver-source-fit path uses SVD/rank-aware solving,
keeps raw negative populations for diagnostic linearity, prunes null-rate levels,
and uses a total fitted-source amplitude of ``1.0 s^-1``.

.. code-block:: bash

   PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
     ../xstar/data/atdb.fits \
     --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
     --linear-solver svd \
     --rank-deficient-action svd \
     --negative-population-action keep \
     --prune-null-rate-levels \
     --combined-source-total-rate 1.0 \
     --index-cache \
     --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
     --out-dir o7_solver_source_fit \
     --print-summary

Known limitation: the O VII fitted source weights are empirical diagnostics, not
physical level-resolved recombination rates.  Reference snapshots for the
density-grid diagnostic are saved under ``examples/reference_outputs/``.

O VII solver-source-fit density grid
------------------------------------

Use ``examples/21_o7_solver_source_fit_density_grid.py`` to test whether the
empirical O VII solver-response source weights are stable with density.  The
default grid is ``ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3``.

.. code-block:: bash

   PYTHONPATH=src python examples/21_o7_solver_source_fit_density_grid.py \
     ../xstar/data/atdb.fits \
     --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
     --linear-solver svd \
     --rank-deficient-action svd \
     --negative-population-action keep \
     --prune-null-rate-levels \
     --combined-source-total-rate 1.0 \
     --index-cache \
     --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
     --out-dir o7_solver_source_fit_density_grid \
     --print-summary

The diagnostic writes ``o7_solver_source_fit_density_grid.csv`` and
``o7_solver_source_fit_density_grid_summary.json``.  It reports the reused
low-density XSTAR R/G reference, fixed-``ne=1`` R/G, separately refitted R/G at
each density, matrix rank, residuals, negative-population diagnostics, and
source-weight changes.  v0.2.66 also adds ``fit_success_vs_xstar`` and
``target_reachable`` flags, R/G ratio columns comparing refitted, fixed, and
XSTAR targets, and per-density warnings for large fit objectives or unreachable
R/G targets.  A future extension may add density-dependent XSTAR reference
inputs such as ``--xstar-lines-csv-by-density`` or ``--xstar-grid-summary-csv``.
The weights remain empirical diagnostics, not physical level-resolved
recombination rates.


O VII density-dependent XSTAR reference grid
--------------------------------------------

Use ``examples/22_o7_solver_source_fit_density_xstar_grid.py`` when separate
XSTAR triplet CSVs are available for each density.  This compares each density
against its own XSTAR target instead of reusing the low-density reference.

A mapping CSV can contain columns such as ``electron_density_cm^-3`` and
``xstar_lines_csv``:

.. code-block:: text

   electron_density_cm^-3,xstar_lines_csv,xstar_value_column,xstar_target_label
   1,xstar_o7_ne1_lines.csv,emit_outward,O VII XSTAR ne=1
   1e10,xstar_o7_ne1e10_lines.csv,emit_outward,O VII XSTAR ne=1e10
   1e12,xstar_o7_ne1e12_lines.csv,emit_outward,O VII XSTAR ne=1e12

Run:

.. code-block:: bash

   Create a starter density-reference mapping CSV and edit its placeholder paths before using it for science validation::

  PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \
    --write-template-grid-csv xstar_o7_density_grid_references.csv

Then run the density-specific grid::

  PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \
     ../xstar/data/atdb.fits \
     --xstar-grid-summary-csv xstar_o7_density_grid_references.csv \
     --linear-solver svd \
     --rank-deficient-action svd \
     --negative-population-action keep \
     --prune-null-rate-levels \
     --combined-source-total-rate 1.0 \
     --index-cache \
     --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
     --out-dir o7_solver_source_fit_density_xstar_grid \
     --print-summary

Repeated ``--xstar-lines-csv-by-density DENSITY:CSV`` arguments can be used
instead of a mapping CSV.

Preparing O VII XSTAR density-grid runs
---------------------------------------

Use ``examples/23_prepare_o7_xstar_density_grid.py`` when the density-specific
XSTAR runs required by ``examples/22_o7_solver_source_fit_density_xstar_grid.py``
do not exist yet.  It writes one clean run directory per density, full XSTAR
``run_xstar.sh`` scripts, O VII triplet conversion scripts, and the mapping CSV
used by the density-dependent comparison.

.. code-block:: bash

   PYTHONPATH=src python examples/23_prepare_o7_xstar_density_grid.py \
     --root . \
     --mapping-csv xstar_o7_density_grid_references.csv \
     --print-summary

After running the generated XSTAR scripts externally and converting each
``xout_lines1.fits``, run example 22 with the generated mapping CSV.

O VII high-density mismatch diagnostics
---------------------------------------

After running the density-dependent XSTAR-grid comparison, use
``examples/24_o7_high_density_mismatch_diagnostics.py`` to focus on the
high-density failure case, usually ``ne=1e12 cm^-3``::

  PYTHONPATH=src python examples/24_o7_high_density_mismatch_diagnostics.py \
    ../xstar/data/atdb.fits \
    --density-grid-dir o7_solver_source_fit_density_xstar_grid \
    --density 1e12 \
    --reference-density 1 \
    --index-cache \
    --out-dir o7_high_density_mismatch \
    --print-summary

The diagnostic writes component-mismatch, source-weight-change, optional
collision-rate, and JSON summary products.  It reports which triplet component
is responsible for the mismatch, whether fitted weights collapse onto a small
number of levels, solver rank/residual diagnostics, and type-68/69 level-2 to
level-3/4/5 collision rates when ``atdb.fits`` is supplied.  The output remains
empirical and diagnostic, not a physical level-resolved recombination model.

O VII high-density expanded source scan
---------------------------------------

``examples/25_o7_high_density_expanded_source_scan.py`` scans expanded empirical source-level sets for the high-density O VII mismatch and reports reachability, source-weight collapse, component mismatch, and solver diagnostics for each source basis.

O VII high-density rate-sensitivity diagnostic
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``examples/26_o7_high_density_rate_sensitivity.py`` scans temporary diagnostic
collision-rate scale factors for the high-density O VII mismatch.  The built-in
families include level-2-to-3/4/5 metastable coupling and XSTAR type-68/type-69
collision blocks.  These scale factors are sensitivity probes only.

.. code-block:: bash

   PYTHONPATH=src python examples/26_o7_high_density_rate_sensitivity.py \
     ../xstar/data/atdb.fits \
     --density-grid-dir o7_solver_source_fit_density_xstar_grid \
     --density 1e12 \
     --families metastable,type68,type69 \
     --scales 0.1,0.2,0.5,1,2,5,10 \
     --linear-solver svd \
     --rank-deficient-action svd \
     --negative-population-action keep \
     --prune-null-rate-levels \
     --combined-source-total-rate 1.0 \
     --index-cache \
     --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
     --out-dir o7_high_density_rate_sensitivity \
     --print-summary

O VII type-69 transition sensitivity
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Version 0.2.74 adds ``examples/27_o7_type69_transition_sensitivity.py`` to scan individual type-69 collision records or level pairs at high density. This is a diagnostic probe used after the rate-family scan has shown sensitivity to type-69 rates.

.. code-block:: bash

   PYTHONPATH=src python examples/27_o7_type69_transition_sensitivity.py \
     ../xstar/data/atdb.fits \
     --density-grid-dir o7_solver_source_fit_density_xstar_grid \
     --density 1e12 \
     --scan-mode record \
     --scales 0.1,0.2,0.5,2,5,10 \
     --linear-solver svd \
     --rank-deficient-action svd \
     --negative-population-action keep \
     --prune-null-rate-levels \
     --combined-source-total-rate 1.0 \
     --index-cache \
     --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
     --out-dir o7_type69_transition_sensitivity \
     --print-summary

O VII type-69 record audit
~~~~~~~~~~~~~~~~~~~~~~~~~~

Version 0.2.75 adds ``examples/28_o7_type69_record_audit.py`` to inspect the raw XSTAR type-69 records that control the high-density O VII mismatch.  It reports raw ``idat``/``rdat`` fields, decoded level metadata, ``calt69`` rates, detailed-balance checks, and optional annotations from the v0.2.74 transition-sensitivity scan.

.. code-block:: bash

   PYTHONPATH=src python examples/28_o7_type69_record_audit.py \
     ../xstar/data/atdb.fits \
     --records 22490,22491,22492,22493,22494,22495 \
     --density 1e12 \
     --audit-temperature 1e6 \
     --temperature-grid 1e5,3e5,1e6,3e6,1e7 \
     --transition-sensitivity o7_type69_transition_sensitivity \
     --index-cache \
     --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
     --out-dir o7_type69_record_audit \
     --print-summary
