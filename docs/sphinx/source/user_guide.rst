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

The resolver checks an explicit path, ``XSTAR_ATDB_FITS`` or ``XSTAR_ATDB``, the persistent
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

The v0.3.131 API adds a CHIANTI-tools-style workflow layer, and v0.3.132--v0.3.139 make
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
namespace placeholders.  In v0.3.132--v0.3.139, ``db.rates.type50(...)``,
``db.audit.type50_line_pumping(...)``, ``db.context.*``, and
``db.validate.compare_xstar_run(...)`` and ``db.validate.reproduce_xstar_run(...)`` are callable.  Full type-50 solver
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

Function-by-function top-level API examples
------------------------------------------

The examples below make each top-level public helper visible as a copy-pasteable
call. They assume:

.. code-block:: python

   import xstar_atomic as xa

   ATDB = "/path/to/xstar/data/atdb.fits"
   db = xa.open_database(ATDB, index_cache=True)

Database and data-path helpers:

.. code-block:: python

   # xa.open_database(...): open one reusable database handle.
   db = xa.open_database(ATDB, index_cache=True)

   # xa.set_data_path(...) and xa.get_data_path(...): configure a default ATDB path.
   xa.set_data_path(ATDB)
   print(xa.get_data_path())

   # xa.find_atdb_file(...) and xa.resolve_atdb_path(...): locate the database.
   candidate = xa.find_atdb_file()
   resolved = xa.resolve_atdb_path(ATDB)

   # xa.download_data(...): fetch or configure the XSTAR database when needed.
   # db_path = xa.download_data()

Atomic level and line helpers:

.. code-block:: python

   # xa.get_levels(...): decoded level rows.
   levels = xa.get_levels("O VII", db=db)

   # xa.get_lines(...): decoded radiative lines in a wavelength window.
   lines = xa.get_lines("O VII", db=db, wavelength=(21.4, 22.2), slim=True)

   # xa.get_wavelengths(...) and xa.get_energies(...): quick arrays.
   wavelengths = xa.get_wavelengths("O VIII", db=db, wavelength=(18.8, 19.1))
   energies = xa.get_energies("O VIII", db=db, wavelength=(18.8, 19.1))

   # xa.match_line(...) and xa.match_lines(...): nearest line identification.
   ly_alpha = xa.match_line("O VIII", db=db, wavelength=18.969, tolerance_A=0.02)
   matches = xa.match_lines("O VIII", db=db, wavelengths=[18.969, 18.973], tolerance_A=0.03)

Atomic-process helpers:

.. code-block:: python

   # xa.get_collisions(...): collision summaries and evaluated rates.
   collisions = xa.get_collisions(
       "O VIII",
       db=db,
       temperatures=[1.0e6, 3.0e6],
       wavelength=(18.8, 19.1),
   )

   # xa.get_photoionization(...): bound-free records, optionally including grids.
   photoionization = xa.get_photoionization("O VII", db=db, include_grid=True)

   # xa.get_recombination(...): recombination records/evaluations.
   recombination = xa.get_recombination(
       "O VII",
       db=db,
       temperatures=[1.0e6],
       electron_densities=[1.0e8],
   )

   # xa.calc_emissivity(...): direct-excitation emissivity products.
   emissivity = xa.calc_emissivity(
       "O VIII",
       db=db,
       temperatures=[1.0e6],
       wavelength=(18.8, 19.1),
   )

Context helpers:

.. code-block:: python

   # xa.LocalPlasmaState(...): local thermodynamic/ionization state.
   state = xa.LocalPlasmaState(
       temperature_K=7.66552e4,
       electron_density_cm3=1.20466e8,
       log_xi=1.5,
       ion_fraction=0.255926,
   )

   # xa.RadiationField(...): sampled local radiation field.
   radiation = xa.RadiationField.from_pairs(
       [(0.50, 1.0e4), (0.574, 2.5e4), (1.00, 1.0e4)],
       source="manual example",
   )

   # xa.EscapeContext(...): escape/covering quantities used by type-50 audits.
   escape = xa.EscapeContext(cfrac=0.0, ptmp1=0.2, ptmp2=0.3, flinabs_ptmp1=0.8)

   # xa.context_from_values(...): combine explicit local inputs into XSTARContext.
   ctx = xa.context_from_values(
       ion="O VII",
       temperature_K=state.temperature_K,
       electron_density_cm3=state.electron_density_cm3,
       log_xi=state.log_xi,
       ion_fraction=state.ion_fraction,
       radiation_field=radiation,
       escape_context=escape,
   )

   # xa.context_from_xstar_run(...): start from an XSTAR run directory when available.
   ctx_from_run = xa.context_from_xstar_run(
       "xstar_runs/helike_type69/o7_ne1e8",
       ion="O VII",
       target_electron_density=1e8,
       nearest_density=True,
   )

Rate, triplet, solver, and matrix helpers:

.. code-block:: python

   # xa.calc_rate(...): dispatch to an implemented provenance-rich rate evaluator.
   rate = xa.calc_rate(
       "type50",
       ion="O VII",
       lower_level=1,
       upper_level=7,
       aij_s_inv=3.0e12,
       oscillator_strength=0.7,
       wavelength_A=21.602,
       vtherm_cm_s=1.0e7,
       bremsa_nb1=2.5e4,
       plasma_state=state,
       radiation_field=radiation,
       escape_context=escape,
   )
   assert isinstance(rate, xa.RateEvaluation)
   print(rate.to_dict())

   # xa.calc_triplet(...): summarize existing f/i/r rows from XSTAR outputs or CSV rows.
   triplet = xa.calc_triplet(
       "O VII",
       rows=[
           {"upper_level": "1s1.2s1.3S_1", "emit_outward": 8.0},
           {"upper_level": "1s1.2p1.3P_1", "emit_outward": 1.5},
           {"upper_level": "1s1.2p1.1P_1", "emit_outward": 2.0},
       ],
   )
   print(triplet.to_dict())

   # xa.solve_populations(...): prototype wrapper around the current diagnostic solver.
   solution = xa.solve_populations("O VII", db=db, context=ctx)

   # xa.build_matrix(...): prototype helper returning available matrix-related products.
   matrix_products = xa.build_matrix("O VII", db=db, context=ctx)

Expert object namespace examples:

.. code-block:: python

   # db.context.* mirrors the module-level context helpers.
   ctx = db.context.from_values(
       ion="O VII",
       temperature_K=7.66552e4,
       electron_density_cm3=1.20466e8,
       log_xi=1.5,
   )
   ctx = db.context.from_xstar_run("xstar_runs/helike_type69/o7_ne1e8", ion="O VII")

   # db.rates.type50(...): object-oriented access to the audit-only type-50 evaluator.
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

   # db.audit.type50_line_pumping(...): reusable Python API behind example 55.
   audit = db.audit.type50_line_pumping(
       "helike_local_state_validation_v03131/helike_local_state_cases.csv",
       solver_root=".",
       xstar_source_root="../xstar",
       out_dir="helike_type50_line_pumping_audit_v03131",
   )

   # db.validate.compare_xstar_run(...): lightweight same-run triplet/context comparison.
   comparison = db.validate.compare_xstar_run(
       "xstar_runs/helike_type69/o7_ne1e8",
       ion="O VII",
       wavelength=(21.4, 22.2),
   )

   # db.solve.ion(...) and db.matrix.build_ion(...): prototype object wrappers.
   solution = db.solve.ion("O VII", context=ctx)
   matrix_products = db.matrix.build_ion("O VII", context=ctx)

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
photoexcitation into the population matrix in v0.3.133.

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


Same-run XSTAR reproduction benchmark
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After the API reorganization, the first benchmark step is to reproduce exactly
what the same XSTAR run wrote to ``xout_abund1.fits`` and ``xout_lines1.fits``.
This is target extraction, not a new solver-physics correction.

.. code-block:: python

   import xstar_atomic as xa

   target = xa.build_xstar_local_target(
       "xstar_runs/helike_type69/o7_ne1e8",
       ion="O VII",
   )
   print(target.local_state_row())
   print(target.triplet_row())

   comparison = xa.reproduce_xstar_run(
       "xstar_runs/helike_type69/o7_ne1e8",
       ion="O VII",
       run_solver=False,
   )
   print(comparison.comparison_row())

   comparison = db.validate.reproduce_xstar_run(
       "xstar_runs/helike_type69/o7_ne1e8",
       ion="O VII",
   )

The command-line wrapper is:

.. code-block:: bash

   PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
     --run-dir xstar_runs/helike_type69/o7_ne1e8 \
     --ion "O VII" \
     --out-dir xstar_o7_local_reproduction \
     --print-summary

Use the built-in standard case table for the C V / O VII / Mg XI / Ca XIX suite:

.. code-block:: bash

   PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
     --standard-helike-suite \
     --xstar-runs-root xstar_runs \
     --out-dir helike_local_reproduction_suite \
     --print-summary

For a solver comparison, use the source-code-first local-state preset rather than the lightweight workflow-default solver:

.. code-block:: bash

   PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
     --standard-helike-suite \
     --xstar-runs-root xstar_runs \
     --run-solver \
     --solver-preset xstar-local-state \
     --out-dir helike_local_reproduction_suite_solver_v03139 \
     --print-summary

The comparison outputs include XSTAR and solver ``f/i/r``, ``R=f/i``, ``G=(f+i)/r``, L2, residuals, and the solver-triplet source.

To create an editable CSV first, run:

.. code-block:: bash

   PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
     --write-standard-cases-csv helike_reproduction_cases.csv \
     --xstar-runs-root xstar_runs \
     --print-summary
   PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
     --cases-csv helike_reproduction_cases.csv \
     --out-dir helike_local_reproduction_suite \
     --print-summary

Python XSTAR-output recreation planning
---------------------------------------

``xstar-atomic`` is not yet a full replacement for the XSTAR thermal/ionization/radiative-transfer driver.  It now includes a planning API for building that replacement in a source-code-parity way.

.. code-block:: python

   import xstar_atomic as xa

   params = xa.parse_xstar_command(
       "xstar spectrum='pow' nsteps=10 density=1 rlogxi=1.5 cfrac=1.0 vturbi=100"
   )
   plan = xa.xstar_recreation_plan(params)
   paths = xa.write_xstar_recreation_plan(params, "xstar_python_recreation_plan")

A run script can be parsed from the command line:

.. code-block:: bash

   PYTHONPATH=src python examples/58_plan_xstar_output_recreation.py \
     --command-file xstar_runs/helike_type69/o7_ne1e8/run_xstar.sh \
     --out-dir xstar_python_recreation_plan_o7 \
     --print-summary

The plan covers ``xo01_detail.fits``, ``xo01_detal2.fits``, ``xo01_detal3.fits``, ``xo01_detal4.fits``, ``xout_abund1.fits``, ``xout_lines1.fits``, ``xout_rrc1.fits``, ``xout_cont1.fits``, and ``xout_spect1.fits``.  Exact recreation from input parameters alone requires the same live internal state used by XSTAR: ``epi(:)``, ``bremsa(:)``, ``bremsint(:)``, ``tau0(1:2,line)``, ``tauc/dpthc(1:2,continuum)``, ``cfrac``, ``vturbi``, ion fractions, and level populations.

Python XSTAR live-state skeleton
--------------------------------

The recreation plan identifies the products and phases.  The live-state skeleton creates the Python containers that later source-code-parity loops must populate.  These objects are the future single source of truth for writing ``xo01_detail.fits``, ``xo01_detal2.fits``, ``xo01_detal3.fits``, ``xo01_detal4.fits``, ``xout_abund1.fits``, ``xout_lines1.fits``, ``xout_rrc1.fits``, ``xout_cont1.fits``, and ``xout_spect1.fits``.

.. code-block:: python

   import xstar_atomic as xa

   params = xa.parse_xstar_command(
       "xstar spectrum='pow' nsteps=10 density=1 rlogxi=1.5 cfrac=1.0 vturbi=100"
   )
   state = xa.create_initial_xstar_run_state_from_input(params)
   zone = state.zones[0]
   print(zone.cfrac, zone.vturbi, zone.temperature, zone.electron_density)
   print(zone.missing_core_fields())

.. code-block:: bash

   PYTHONPATH=src python examples/59_create_xstar_live_state_skeleton.py \
     --command-file xstar_runs/helike_type69/o7_ne1e8/run_xstar.sh \
     --out-dir xstar_live_state_skeleton_o7 \
     --print-summary

The current skeleton is input-seeded, not a full XSTAR calculation.  It explicitly carries ``epi(:)``, ``bremsa(:)``, ``bremsint(:)``, ``tau0(1:2,line)``, ``tauc/dpthc(1:2,continuum)``, ``cfrac``, ``vturbi``, local ``T/ne``, ion fractions, and level populations so that future Python and C++ backends can populate the same arrays used by the XSTAR Fortran path.
