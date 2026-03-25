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
