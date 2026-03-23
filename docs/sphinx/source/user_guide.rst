User guide
==========

The full user guide is maintained in Markdown and LaTeX in the main ``docs/``
directory:

- ``docs/user_guide.md``
- ``docs/user_guide.tex``

Quick start
-----------

Open the database with the high-level API:

.. code-block:: python

   from xstar_atomic import XSTARAtomic

   db = XSTARAtomic("/path/to/xstar/data/atdb.fits")
   lines = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)

Run without installation:

.. code-block:: bash

   PYTHONPATH=src python -m xstar_atomic.lines /path/to/atdb.fits \
     --element O --ion-stage 8 \
     --line-search --wavelength-min 18.8 --wavelength-max 19.1



Band-emissivity export
----------------------

Line-based X-ray band products are written with ``--bands-kev``:

.. code-block:: bash

   PYTHONPATH=src python -m xstar_atomic.export /path/to/atdb.fits \
     --ions "O VIII,Ne IX" \
     --temperatures 1e6 3e6 1e7 \
     --wavelength-min 1.0 --wavelength-max 40.0 \
     --bands-kev soft:0.5:2.0 osoft:0.3:0.6 med:0.6:1.0 hard:2.0:10.0 \
     --formats csv,hdf5 \
     --out-dir atomic_export \
     --print-summary

This creates ``*_band_emissivity.csv`` files and a ``/band_emissivity`` group
inside each per-ion HDF5 file.  A validated Stage-4 real-ATDB test with four
bands and three temperatures gives 12 band rows per ion and keeps nonblank
``ion`` and ``methods_used`` fields even for zero-line bands.

Build the Sphinx documentation:

.. code-block:: bash

   python -m pip install -e .[docs]
   cd docs/sphinx
   make html

Stage-3 sparse solver diagnostics
---------------------------------

Use ``--linear-solver sparse`` with the XSTAR type-63 same-``n`` l-mixing
impact-parameter density:

.. code-block:: bash

   PYTHONPATH=src python -m xstar_atomic.solver /path/to/atdb.fits \
     --element O --ion-stage 8 \
     --wavelength-min 18.8 --wavelength-max 19.1 \
     --temperatures 1e6 \
     --electron-densities 1.0 \
     --electron-density-for-lmixing 1.0 \
     --component-mode ground \
     --linear-solver sparse \
     --summary-json o8_sparse_solver_summary.json \
     --print-summary

The summary includes matrix nonzero counts, density, singular-value rank,
condition number, sparse availability/use, and linear residual diagnostics.
The optional ``--prune-unconnected-levels`` flag removes isolated levels while
preserving ground, output, and explicit source/sink levels.

For O VII triplet stress tests, ``examples/10_o7_triplet_sparse_solver.py``
writes prototype ``R=f/i`` and ``G=(f+i)/r`` diagnostic tables.
Solver timing example
---------------------

Use ``examples/11_solver_timing.py`` to benchmark end-to-end solver execution.
The timing includes ATDB decoding, record selection, matrix assembly, the
linear solve, and output writing.

.. code-block:: bash

   PYTHONPATH=src python examples/11_solver_timing.py /path/to/atdb.fits \
     --repeat 3 \
     --out-dir solver_timing_example

To include the heavier O VII triplet sparse stress test:

.. code-block:: bash

   PYTHONPATH=src python examples/11_solver_timing.py /path/to/atdb.fits \
     --include-o7 \
     --repeat 2 \
     --out-dir solver_timing_example \
     --out-csv solver_timing.csv

The resulting CSV includes elapsed wall time, solver used, sparse status,
matrix size, nonzero count, matrix density, condition number, and residual
metrics.  SciPy already provides a compiled sparse linear solver; a future C++
backend would be most useful for repeated record filtering, rate evaluation,
matrix assembly, emissivity aggregation, and direct HDF5 packing.



ATDB index caching
------------------

Repeated solver and export workflows can reuse an on-disk hierarchy index cache.
The first cached run writes ``atdb.fits.xstar_atomic_index.npz`` by default; later
runs with ``--index-cache`` can load that cache instead of scanning all ATDB
records again.

.. code-block:: bash

   PYTHONPATH=src python examples/12_profile_solver_steps.py \
     ../xstar/data/atdb.fits \
     --element O --ion-stage 8 \
     --wavelength-min 18.8 --wavelength-max 19.1 \
     --temperature 1e6 --electron-density 1.0 \
     --linear-solver sparse \
     --index-cache \
     --out-dir solver_profile_example

The solver and export CLIs also accept ``--index-cache`` and
``--rebuild-index-cache``.  Summaries report ``index_cache_status`` and
``index_cache_path``.

Solver profiling and Stage-6 cascade examples are documented in the examples page.


NumPy/NPZ index cache
---------------------

The ATDB hierarchy scan is often the dominant startup cost because it walks more than one million packed records. Use `--index-cache` to store and reuse a compact NumPy/NPZ hierarchy cache:

.. code-block:: bash

   
   PYTHONPATH=src python examples/12_profile_solver_steps.py \
     ../xstar/data/atdb.fits \
     --element O --ion-stage 8 \
     --wavelength-min 18.8 --wavelength-max 19.1 \
     --temperature 1e6 --electron-density 1.0 \
     --linear-solver sparse \
     --index-cache \
     --index-cache-format npz \
     --out-dir solver_profile_example_npz


The default cache file is `atdb.fits.xstar_atomic_index.npz`. The legacy pickle cache is still available with `--index-cache-format pickle`. Use `--rebuild-index-cache` to force regeneration.


Array-backed NPZ index cache
----------------------------

Version 0.2.26 adds an array-backed NPZ cache through ``ATDBIndexArrays``. For targeted workflows, the package can load numeric index arrays, select records by element, ion stage, data type, or rate type, and convert only those selected rows to ``IndexedRecord`` objects. This is enabled with ``--index-cache --index-cache-format npz`` in the solver, export, and profiling examples.
