User guide
==========

``xstar-atomic`` reads XSTAR's packed ``atdb.fits`` atomic database,
evaluates selected source-code-aligned rate formulae, builds prototype
level-population products, and provides validation/audit tools for same-run
XSTAR outputs.  This Sphinx page mirrors the public-API organization of
``docs/user_guide.md`` and ``docs/user_guide.tex``.

The package is not intended to replace XSTAR.  Its purpose is to make local
atomic-data and rate pieces auditable from Python with explicit provenance for
XSTAR records, source-code branches, local plasma state, radiation field,
escape treatment, and future population-matrix terms.

Installation and data setup
---------------------------

Install from a source checkout:

.. code-block:: bash

   python -m pip install -e .
   python -m pip install -e .[dev]

Configure ``atdb.fits`` explicitly:

.. code-block:: python

   from xstar_atomic import XSTARAtomic

   db = XSTARAtomic("/path/to/xstar/data/atdb.fits")

or save a persistent data path:

.. code-block:: python

   import xstar_atomic as xa

   xa.set_data_path("/path/to/xstar/data/atdb.fits")
   db = xa.open_database()

The resolver checks an explicit path, ``XSTAR_ATDB_FITS``, the persistent
``datapath`` file, and ``data/atdb.fits``.  Interactive configuration is also
available:

.. code-block:: bash

   python -m xstar_atomic.data
   xstar-atomic-download-data

Quick start
-----------

Use the object API when you will make repeated queries against one database:

.. code-block:: python

   from xstar_atomic import XSTARAtomic

   db = XSTARAtomic("/path/to/xstar/data/atdb.fits", index_cache=True)
   print(db.summary())

   levels = db.levels("O VII")
   lines = db.lines("O VII", wavelength=(21.4, 22.2), slim=True)
   coll = db.collisions("O VIII", temperatures=[1e6, 3e6], wavelength=(18.8, 19.1))
   emiss = db.emissivity("O VIII", temperatures=[1e6], wavelength=(18.8, 19.1))

Run without installation from a checkout:

.. code-block:: bash

   PYTHONPATH=src python -m xstar_atomic.lines /path/to/atdb.fits \
     --element O --ion-stage 8 \
     --line-search --wavelength-min 18.8 --wavelength-max 19.1

Public API layers
-----------------

The v0.3.131 API adds a CHIANTI-tools-style workflow layer, and v0.3.132 makes
this layer explicit in Markdown, LaTeX, and Sphinx documentation.

.. list-table:: Public API layers
   :header-rows: 1
   :widths: 25 50 25

   * - Layer
     - Use when
     - Example
   * - Module-level workflow API
     - You want quick notebook/script calls without navigating internal modules.
     - ``xa.get_lines("O VII", db=db)``
   * - ``XSTARAtomic`` object API
     - You want to keep one opened ``atdb.fits`` handle and reuse cached indices.
     - ``db.lines("O VII", wavelength=(21.4, 22.2))``
   * - Expert namespace API
     - You need source-code-first contexts, rate evaluators, audits, validation, and future matrix/solver workflows.
     - ``db.rates.type50("O VII", ...)``

The API intentionally separates implemented stable helpers from future
namespace placeholders.  In v0.3.132, ``db.rates.type50(...)``,
``db.audit.type50_line_pumping(...)``, ``db.context.*``, and
``db.validate.compare_xstar_run(...)`` are callable.  Full type-50 solver
injection and some resonance-budget audits remain future work.

Workflow-first module-level API
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import xstar_atomic as xa

   db = xa.open_database("/path/to/xstar/data/atdb.fits")

   levels = xa.get_levels("O VII", db=db)
   lines = xa.get_lines("O VII", db=db, wavelength=(21.4, 22.2), slim=True)
   wavelengths = xa.get_wavelengths("O VIII", db=db, wavelength=(18.8, 19.1))
   match = xa.match_line("O VIII", db=db, wavelength=18.969, tolerance_A=0.02)

   coll = xa.get_collisions("O VIII", db=db, temperatures=[1e6, 3e6])
   pi = xa.get_photoionization("O VII", db=db)
   rr = xa.get_recombination("O VII", db=db, temperatures=[1e6])
   emiss = xa.calc_emissivity("O VIII", db=db, temperatures=[1e6], wavelength=(18.8, 19.1))

The same functions can receive ``fitsfile="/path/to/atdb.fits"`` instead of an
opened database object.  Passing an opened ``db`` is faster for repeated queries.

.. list-table:: Workflow API summary
   :header-rows: 1
   :widths: 35 50 15

   * - Function
     - Purpose
     - Status
   * - ``xa.open_database(...)``
     - Open ``atdb.fits`` as an ``XSTARAtomic`` object.
     - implemented
   * - ``xa.get_levels(...)`` / ``xa.get_lines(...)``
     - Decode level and radiative line records.
     - implemented
   * - ``xa.get_wavelengths(...)`` / ``xa.get_energies(...)``
     - Return sorted line wavelengths or energies.
     - implemented
   * - ``xa.match_line(...)`` / ``xa.match_lines(...)``
     - Match nearest line(s) by wavelength or energy.
     - implemented
   * - ``xa.get_collisions(...)``
     - Return collision summaries and evaluated rows.
     - implemented
   * - ``xa.get_photoionization(...)``
     - Return photoionization summaries/grids.
     - implemented
   * - ``xa.get_recombination(...)``
     - Return recombination and optional source rows.
     - implemented
   * - ``xa.calc_emissivity(...)``
     - Build direct-excitation emissivity products.
     - implemented
   * - ``xa.context_from_values(...)``
     - Build an ``XSTARContext`` from explicit local values.
     - implemented
   * - ``xa.context_from_xstar_run(...)``
     - Build an ``XSTARContext`` from an XSTAR output directory.
     - lightweight
   * - ``xa.calc_rate("type50", ...)``
     - Dispatch to the audit-only type-50 evaluator.
     - type 50
   * - ``xa.calc_triplet(...)``
     - Summarize He-like f/i/r rows.
     - implemented
   * - ``xa.solve_populations(...)`` / ``xa.build_matrix(...)``
     - Wrap the current diagnostic population solver.
     - prototype

Local context objects
---------------------

XSTAR rates can depend on local plasma state, radiation field, optical depth,
escape probability, and covering factor.  ``xstar-atomic`` therefore exposes
explicit context objects rather than hiding those quantities in scalar helpers.

.. code-block:: python

   from xstar_atomic import LocalPlasmaState, RadiationField, EscapeContext, context_from_values

   state = LocalPlasmaState(
       temperature_K=7.66552e4,
       electron_density_cm3=1.20466e8,
       log_xi=1.5,
       ion_fraction=0.255926,
   )

   rad = RadiationField.from_pairs([
       (0.50, 1.0e4),
       (0.574, 2.5e4),
       (1.00, 1.0e4),
   ])

   escape = EscapeContext(cfrac=0.0, ptmp1=0.2, ptmp2=0.3, flinabs_ptmp1=0.8)

   ctx = context_from_values(
       ion="O VII",
       temperature_K=state.temperature_K,
       electron_density_cm3=state.electron_density_cm3,
       log_xi=state.log_xi,
       ion_fraction=state.ion_fraction,
       radiation_field=rad,
       escape_context=escape,
   )

To start from an XSTAR run directory:

.. code-block:: python

   ctx = xa.context_from_xstar_run(
       "xstar_runs/helike_type69/o7_ne1e8",
       ion="O VII",
       target_electron_density=1e8,
       nearest_density=True,
   )

Type-50 rate evaluator
----------------------

The audit-only type-50 evaluator records XSTAR's ``ucalc.f90`` branch swap and
returns a structured ``RateEvaluation`` object.  It does not inject
photoexcitation into the population matrix in v0.3.132.

.. code-block:: python

   from xstar_atomic import evaluate_type50_bound_bound

   rate = evaluate_type50_bound_bound(
       aij_s_inv=3.0e12,
       oscillator_strength=0.7,
       wavelength_A=21.602,
       vtherm_cm_s=1.0e7,
       bremsa_nb1=2.5e4,
       plasma_state=state,
       radiation_field=rad,
       escape_context=escape,
       ion="O VII",
       lower_level=1,
       upper_level=7,
   )

   print(rate.value_s_inv)
   print(rate.lower_to_upper_photoexcitation_s_inv)
   print(rate.upper_to_lower_escaped_decay_s_inv)
   print(rate.source_formula)
   print(rate.terms)

Expert namespace API
--------------------

``XSTARAtomic`` exposes namespace-style entry points for advanced workflows:

.. code-block:: python

   ctx = db.context.from_values(
       ion="O VII",
       temperature_K=7.66552e4,
       electron_density_cm3=1.20466e8,
       log_xi=1.5,
   )

   rate = db.rates.type50(
       "O VII",
       aij_s_inv=3.0e12,
       oscillator_strength=0.7,
       wavelength_A=21.602,
       vtherm_cm_s=1.0e7,
       bremsa_nb1=2.5e4,
       ptmp1=0.2,
       ptmp2=0.3,
       flinabs_ptmp1=0.8,
       cfrac=0.0,
   )

   ctx = db.context.from_xstar_run("xstar_runs/helike_type69/o7_ne1e8", ion="O VII")
   comparison = db.validate.compare_xstar_run(
       "xstar_runs/helike_type69/o7_ne1e8",
       ion="O VII",
       wavelength=(21.4, 22.2),
   )

   solution = db.solve.ion("O VII", context=ctx)
   matrix_products = db.matrix.build_ion("O VII", context=ctx)

The solver and matrix namespace methods are wrappers around the current
diagnostic solver.  They do not enable type-50 photoexcitation as solver physics.

Public namespace modules
------------------------

Users can also import public namespaces directly:

.. code-block:: python

   from xstar_atomic import rates, solve, matrix, validate, runs

   rate = rates.type50_bound_bound(
       ion="O VII",
       aij_s_inv=3.0e12,
       oscillator_strength=0.7,
       wavelength_A=21.602,
       vtherm_cm_s=1.0e7,
       bremsa_nb1=2.5e4,
       ptmp1=0.2,
       ptmp2=0.3,
       flinabs_ptmp1=0.8,
       cfrac=0.0,
   )

   triplet_comparison = validate.compare_xstar_run(
       "xstar_runs/helike_type69/o7_ne1e8",
       ion="O VII",
       wavelength=(21.4, 22.2),
   )

Audit workflows
---------------

The type-50 line-pumping audit is available as both a Python API and a CLI
wrapper:

.. code-block:: python

   from xstar_atomic.audit import type50_line_pumping

   audit = type50_line_pumping(
       cases_csv="helike_local_state_validation_v03131/helike_local_state_cases.csv",
       solver_root=".",
       xstar_source_root="../xstar",
       out_dir="helike_type50_line_pumping_audit_v03131",
       print_summary=True,
   )

   print(audit.summary)

.. code-block:: bash

   PYTHONPATH=src python examples/55_audit_helike_type50_line_pumping.py \
     --cases-csv helike_local_state_validation_v03131/helike_local_state_cases.csv \
     --solver-root . \
     --xstar-source-root ../xstar \
     --out-dir helike_type50_line_pumping_audit_v03131 \
     --print-summary

Examples and source-module migration
------------------------------------

The package includes grouped runnable examples in ``examples/README.md``.  The
same migration plan is summarized in ``docs/example_to_source_api_map.md``.
High-priority migrations are:

.. list-table:: Example-to-API migration
   :header-rows: 1
   :widths: 45 55

   * - Current example
     - Candidate source API
   * - ``51_run_helike_local_state_validation.py``
     - ``xstar_atomic.runs.select_local_states(...)``
   * - ``52_summarize_helike_local_state_comparison.py``
     - ``xstar_atomic.validate.summarize_local_state_comparison(...)``
   * - ``53_audit_helike_resonance_deficit.py``
     - ``xstar_atomic.audit.resonance_deficit(...)``
   * - ``54_audit_helike_resonance_population_flux.py``
     - ``xstar_atomic.audit.resonance_population_flux(...)``
   * - ``55_audit_helike_type50_line_pumping.py``
     - ``xstar_atomic.audit.type50_line_pumping(...)``

Solver profiling and Stage-6 workflows
--------------------------------------

Solver step profiling:

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

Prototype O VII recombination/cascade workflow:

.. code-block:: bash

   PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
     ../xstar/data/atdb.fits \
     --out-dir o7_recomb_cascade_workflow \
     --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
     --print-summary

O VII density-grid source-fit diagnostic:

.. code-block:: bash

   PYTHONPATH=src python examples/21_o7_solver_source_fit_density_grid.py \
     ../xstar/data/atdb.fits \
     --out-dir o7_density_grid_source_fit \
     --print-summary

Build documentation
-------------------

.. code-block:: bash

   python -m pip install -e .[docs]
   cd docs/sphinx
   make html

Development policy
------------------

- No empirical triplet scale factors as final physics.
- New physics starts as audit-only.
- Solver-changing modes must be opt-in until validated.
- Every solver-changing rate must have source-code and record provenance.
- Radiation-dependent rates must expose the radiation context.
- Escape-dependent rates must expose ``cfrac``, ``tau``/``ptmp``, and escape treatment.
- Same-run XSTAR outputs are preferred over generic target CSVs.
