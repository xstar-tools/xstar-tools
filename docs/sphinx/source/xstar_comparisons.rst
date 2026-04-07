XSTAR comparison examples
=========================

Saved comparison artifacts
--------------------------

The package includes saved XSTAR-vs-``xstar-atomic`` comparison outputs under::

   docs/validation/xstar_outputs/
   examples/reference_outputs/

The source Markdown page is maintained at ``docs/xstar_comparison_examples.md``.


Included XSTAR test-run data
----------------------------

The package includes a reproducibility directory::

   xstar_test_run/

It contains direct-XSTAR ``xout_lines1.fits`` files, converted CSV line
tables, and a README with the exact XSTAR commands and FITS-to-CSV conversion
commands.  The test runs are:

* O VIII / Ne IX high-ionization validation.
* Ne IX focused Stage-5 validation.
* Ne X focused Stage-5 validation.
* Pending Mg XI/Mg XII, Si XIII/Si XIV, and Fe XXV/Fe XXVI Stage-5 run recipes.
* O VII triplet / recombination-cascade validation.
* O VII triplet validation at higher density.

Example comparison using the included O VII triplet CSV::

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

O VIII Ly-alpha
---------------

The O VIII Ly-alpha wavelength comparison matches XSTAR ``xout_lines1.fits``
against ``xstar-atomic`` wavelengths for the two fine-structure components.
The maximum wavelength difference is approximately ``1.7e-5`` Angstrom.

O VII triplet
-------------

The O VII triplet/near-triplet wavelength comparison matches XSTAR wavelengths
near 21.6--22.1 Angstrom.  The wavelength differences are approximately
``1e-7`` to ``8e-7`` Angstrom.


Ne IX / Ne X Stage-5 comparisons
----------------------------------

The neon Stage-5 XSTAR outputs are now included as validation artifacts:

* ``xstar_test_run/ne_xi25/xout_lines1.fits``
* ``xstar_test_run/ne_xi35/xout_lines1.fits``
* ``xstar_test_run/xstar_ne9_triplet_lines.csv``
* ``xstar_test_run/xstar_ne10_lya_lines.csv``
* ``docs/validation/xstar_outputs/compare_ne9_triplet_wavelength.csv``
* ``docs/validation/xstar_outputs/compare_ne10_lya_wavelength.csv``

The Ne IX He-like triplet/near-triplet comparison matches five lines within
0.02 Angstrom.  The maximum wavelength difference is approximately
``4.41e-05`` Angstrom.

The Ne X Ly-alpha comparison matches two fine-structure components within
0.02 Angstrom.  The maximum wavelength difference is approximately
``1.52e-05`` Angstrom.

Reproduce the Ne IX comparison::

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

Reproduce the Ne X comparison::

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


Pending Mg, Si, and Fe Stage-5 runs
--------------------------------------

The next Stage-5 validation targets are documented as XSTAR run recipes in
``xstar_test_run/README.md``.  The recommended first-pass line windows are::

   Mg XI   He-like triplet region: 9.0--9.4 Angstrom
   Mg XII  Ly-alpha region:        8.35--8.50 Angstrom
   Si XIII He-like triplet region: 6.55--6.80 Angstrom
   Si XIV  Ly-alpha region:        6.10--6.25 Angstrom
   Fe XXV  K-alpha region:         1.83--1.88 Angstrom
   Fe XXVI Ly-alpha region:        1.76--1.80 Angstrom

For each ion, run the documented XSTAR command, save ``xout_lines1.fits``,
convert the selected line region to CSV with ``python -m xstar_atomic.xstar_outputs``,
and compare with ``examples/08_compare_xstar_outputs.py`` in wavelength mode.
The Mg/Si/Fe comparisons remain pending until those XSTAR outputs and
CSV/JSON comparison files are added to the validation archive.

Reproduction workflow
---------------------

Convert an XSTAR line-output FITS file to CSV::

   PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
     xout_lines1.fits \
     --out-csv xstar_lines.csv \
     --print-summary

Then compare selected lines::

   PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
     /path/to/atdb.fits \
     xstar_lines.csv \
     --ion "O VIII" \
     --wavelength-column wavelength \
     --reference-column emit_outward \
     --mode wavelength \
     --temperature 1e6 \
     --wavelength-tolerance 0.02 \
     --out-csv compare_lines.csv \
     --out-json compare_lines.json

.. note::

   Wavelength comparisons validate line identification and database decoding.
   Absolute comparisons between local atomic emissivity coefficients and XSTAR
   ``emit_inward``/``emit_outward`` model outputs require ion fractions, density,
   geometry, column, and radiative-transfer assumptions.
