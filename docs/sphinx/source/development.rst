Development notes
=================

Docstrings and Sphinx
---------------------

Sphinx ``autodoc`` generates API pages from Python docstrings, not from ordinary
inline comments. Use docstrings for public modules, classes, methods, and
functions.

Recommended docstring style is NumPy-style, for example:

.. code-block:: python

   def lines(self, ion, wavelength=None):
       """Return decoded radiative lines for an ion.

       Parameters
       ----------
       ion : str
           Ion name such as ``"O VIII"`` or ``"o_viii"``.
       wavelength : tuple[float, float], optional
           Wavelength interval in Angstrom.

       Returns
       -------
       list[dict]
           Decoded line records.
       """

Testing with the real database
------------------------------

.. code-block:: bash

   XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits PYTHONPATH=src pytest -q

Near-term physics TODOs
-----------------------

- Complete collision ``data_type=51`` and ``data_type=98``.
- Implement the same-``n`` ``l``-mixing / XSTAR ``amcrs`` branch for ``data_type=63``.
- Continue searching for true level-resolved recombination/cascade data.
- Add sparse-matrix support to the level-population solver.
- Validate against XSTAR outputs and external atomic data where applicable.
