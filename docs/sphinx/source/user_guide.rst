User guide
==========

The full user guide is maintained in Markdown and LaTeX in the main ``docs/``
directory:

- ``docs/user_guide.md``
- ``docs/user_guide.tex``



Downloading and configuring atdb.fits
====================================

``xstar-atomic`` does not bundle XSTAR's large ``atdb.fits`` file.  Configure
or download it interactively with:

.. code-block:: bash

   python -m xstar_atomic.data

After installation, the equivalent command is:

.. code-block:: bash

   xstar-atomic-download-data

The helper reports the remote file size, asks whether to download
(pressing Enter means yes), asks for a destination directory, downloads with a
single-line ASCII progress bar, and writes the chosen data directory to
``datapath``. In a source checkout this file is stored at the project root
(for example ``datapath``), not under ``src/xstar_atomic/``. The default
destination is the project-level ``data/`` directory.

Example progress line::

   xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)

If ``atdb.fits`` already exists, decline the download and enter the full path to
the existing file.  The parent directory is saved, so future Python code can omit
the path:

.. code-block:: python

   from xstar_atomic import XSTARAtomic

   db = XSTARAtomic(index_cache=True, index_cache_format="npz")
   lines = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)

Non-interactive configuration is also available:

.. code-block:: bash

   python -m xstar_atomic.data --set-path /path/to/atdb.fits
   python -m xstar_atomic.data --show

Top-level data helpers are available from Python:

.. code-block:: python

   from xstar_atomic import (
       download_data,
       resolve_atdb_path,
       find_atdb_file,
       get_data_path,
       set_data_path,
   )

   path = download_data()
   set_data_path("/path/to/xstar/data/atdb.fits")
   path = resolve_atdb_path()

The resolver checks, in order: an explicit path, ``XSTAR_ATDB_FITS``, the
persistent ``datapath`` file, and ``data/atdb.fits``.

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



Recommended array-backed NPZ index cache
----------------------------------------

The ATDB hierarchy scan is often the dominant startup cost because it walks more
than one million packed records.  For repeated targeted workflows, use the
array-backed NumPy/NPZ cache.  This cache stores the hierarchy as numeric
arrays, filters by element, ion stage, data type, and rate type, and converts
only selected rows to ``IndexedRecord`` objects.

.. code-block:: bash

   PYTHONPATH=src python examples/12_profile_solver_steps.py \
     ../xstar/data/atdb.fits \
     --element O --ion-stage 8 \
     --wavelength-min 18.8 --wavelength-max 19.1 \
     --temperature 1e6 --electron-density 1.0 \
     --linear-solver sparse \
     --index-cache \
     --index-cache-format npz \
     --out-dir solver_profile_npz_arrays_hit

For the validated O VIII sparse-solver profile, the uncached run took about
``5.31 s``, while the NPZ array-backed cache-hit run took about ``0.53 s``.
The ``build_index`` stage dropped from about ``5.00 s`` to about ``0.058 s``.

The default cache file is ``atdb.fits.xstar_atomic_index.npz``.  Use
``--rebuild-index-cache`` after changing or replacing ``atdb.fits``.  Legacy
pickle caching remains available with ``--index-cache-format pickle``, but the
NPZ array-backed cache is the recommended path for solver, export, high-level
API, and profiling workflows.

The same cache should be used for repeated export workflows:

.. code-block:: bash

   PYTHONPATH=src python -m xstar_atomic.export ../xstar/data/atdb.fits \
     --ions "O VIII,Ne IX" \
     --temperatures 1e6 3e6 1e7 \
     --wavelength-min 1.0 --wavelength-max 40.0 \
     --bands-kev soft:0.5:2.0 med:0.6:1.0 hard:2.0:10.0 \
     --formats csv,hdf5 \
     --index-cache --index-cache-format npz \
     --out-dir atomic_export_cached \
     --print-summary

Solver and export summaries report ``index_cache_status`` and
``index_cache_path``; cache-hit workflows should report statuses such as
``npz_array_hit`` or ``array_memory``.

Solver profiling and Stage-6 cascade examples are documented in the examples page.

Download progress is shown on one in-place ASCII progress-bar line, for example:

```text
xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)
```
