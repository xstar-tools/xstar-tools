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
