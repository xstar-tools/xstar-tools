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
  --source-fit-weights-csv o7_cascade_source_fit/o7_source_fit_weights.csv \
  --out-dir o7_recomb_cascade_workflow_fit_weights \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

A convenience diagnostic mode is also available:

```bash
--source-mode o7-xstar-fit
```

When no explicit `--source-fit-weights-csv` is supplied, this mode looks for the packaged/source-tree reference file `xstar_test_run/o7_source_fit_weights.csv`. These fitted weights are empirical diagnostics derived from the current O VII/XSTAR comparison, not true level-resolved recombination rates.
