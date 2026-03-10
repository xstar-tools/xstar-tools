XSTAR comparison examples
=========================

Saved comparison artifacts
--------------------------

The package includes saved XSTAR-vs-``xstar-atomic`` comparison outputs under::

   docs/validation/xstar_outputs/
   examples/reference_outputs/

The source Markdown page is maintained at ``docs/xstar_comparison_examples.md``.

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
