"""Python tools for reading and evaluating XSTAR's packed ``atdb.fits`` atomic database."""

__version__ = "0.3.166"

# Pure-Python public API infrastructure.  These remain importable even on
# systems where astropy is not available yet.
from .context import LocalPlasmaState, RadiationField, EscapeContext, XSTARContext, context_from_values, context_from_xstar_run
from .rates_type50 import RateEvaluation, evaluate_type50_bound_bound
from .audit import type50_line_pumping
from .benchmark import (
    XSTARLocalTarget,
    XSTARBenchmarkComparison,
    default_helike_benchmark_cases,
    write_default_helike_cases_csv,
    build_xstar_local_target,
    compare_solver_to_xstar_target,
    reproduce_xstar_run,
    run_xstar_benchmark_suite,
    write_xstar_benchmark_outputs,
    write_xstar_benchmark_suite,
    solver_kwargs_from_preset,
    xstar_local_state_solver_kwargs,
)

from .xstar_run import (
    XSTARInputParameters,
    XSTAROutputProductSpec,
    parse_xstar_command,
    parse_xstar_command_file,
    standard_xstar_output_products,
    xstar_recreation_plan,
    write_xstar_recreation_plan,
)
from .xstar_state import (
    XSTARContinuumState,
    XSTARLineTransferState,
    XSTARZoneState,
    XSTARRunState,
    required_live_state_fields,
    create_initial_xstar_run_state,
    create_initial_xstar_run_state_from_input,
    write_xstar_state_skeleton,
)

from .xstar_detail import (
    read_xstar_parameters_from_run_dir,
    reconstruct_bremsa_from_detal4_rows,
    reconstruct_bremsint,
    read_xstar_detail_run_state,
    summarize_xstar_detail_state,
    write_xstar_detail_state,
    pescl_xstar,
    ptmp_from_tau_xstar,
    xstar_nbinc_index,
    type50_vtherm_xstar,
    audit_xstar_detail_type50_rates,
    write_xstar_detail_type50_rate_audit,
)
from .workflow import (
    TripletResult,
    open_database,
    get_levels,
    get_lines,
    get_wavelengths,
    get_energies,
    match_line,
    match_lines,
    get_collisions,
    get_photoionization,
    get_recombination,
    calc_emissivity,
    calc_rate,
    calc_triplet,
    solve_populations,
    build_matrix,
)

try:
    from .hierarchy import ATDB
    from .api import XSTARAtomic, parse_ion
    from .data import download_data, find_atdb_file, get_data_path, get_data_paths, resolve_atdb_path, set_data_path
    from .xstar_element_solver import solve_element_reference
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency guard
    if exc.name != "astropy":
        raise

    def _missing_astropy(*args, **kwargs):
        raise ImportError("This xstar_atomic feature requires astropy. Install package dependencies or `pip install astropy`.")

    ATDB = _missing_astropy  # type: ignore
    XSTARAtomic = _missing_astropy  # type: ignore
    parse_ion = _missing_astropy  # type: ignore
    download_data = _missing_astropy  # type: ignore
    find_atdb_file = _missing_astropy  # type: ignore
    get_data_path = _missing_astropy  # type: ignore
    get_data_paths = _missing_astropy  # type: ignore
    resolve_atdb_path = _missing_astropy  # type: ignore
    set_data_path = _missing_astropy  # type: ignore
    solve_element_reference = _missing_astropy  # type: ignore

__all__ = [
    "ATDB",
    "XSTARAtomic",
    "parse_ion",
    "download_data",
    "find_atdb_file",
    "get_data_path",
    "get_data_paths",
    "resolve_atdb_path",
    "set_data_path",
    "solve_element_reference",
    "LocalPlasmaState",
    "RadiationField",
    "EscapeContext",
    "XSTARContext",
    "context_from_values",
    "context_from_xstar_run",
    "RateEvaluation",
    "evaluate_type50_bound_bound",
    "type50_line_pumping",
    "XSTARLocalTarget",
    "XSTARBenchmarkComparison",
    "default_helike_benchmark_cases",
    "write_default_helike_cases_csv",
    "build_xstar_local_target",
    "compare_solver_to_xstar_target",
    "reproduce_xstar_run",
    "run_xstar_benchmark_suite",
    "write_xstar_benchmark_outputs",
    "write_xstar_benchmark_suite",
    "solver_kwargs_from_preset",
    "xstar_local_state_solver_kwargs",
    "TripletResult",
    "open_database",
    "get_levels",
    "get_lines",
    "get_wavelengths",
    "get_energies",
    "match_line",
    "match_lines",
    "get_collisions",
    "get_photoionization",
    "get_recombination",
    "calc_emissivity",
    "calc_rate",
    "calc_triplet",
    "solve_populations",
    "build_matrix",
    "XSTARInputParameters",
    "XSTAROutputProductSpec",
    "parse_xstar_command",
    "parse_xstar_command_file",
    "standard_xstar_output_products",
    "xstar_recreation_plan",
    "write_xstar_recreation_plan",
    "XSTARContinuumState",
    "XSTARLineTransferState",
    "XSTARZoneState",
    "XSTARRunState",
    "required_live_state_fields",
    "create_initial_xstar_run_state",
    "create_initial_xstar_run_state_from_input",
    "write_xstar_state_skeleton",
    "read_xstar_parameters_from_run_dir",
    "reconstruct_bremsa_from_detal4_rows",
    "reconstruct_bremsint",
    "read_xstar_detail_run_state",
    "summarize_xstar_detail_state",
    "write_xstar_detail_state",
]
