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
