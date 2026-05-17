"""Command-line interface for the source-faithful element equilibrium port."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np

from .source_port.escape_state import (
    EscapeStateError,
    load_escape_state_from_xstar_run,
    write_escape_state_npz,
    write_escape_state_summary,
)

from .source_port import (
    ElementEquilibriumContext,
    EscapeProbabilityContext,
    load_atomic_database_state,
    load_derived_pointer_cache,
    solve_element_statistical_equilibrium,
    write_element_equilibrium_products,
)


def _select_live_state(path: str | None, selector: str) -> Any:
    if not path:
        return None
    from .xstar_live_rate_grid_probe import read_live_rate_grid_probe_csv

    states = read_live_rate_grid_probe_csv(path)
    if not states:
        raise ValueError(f"no live radiation states found in {path}")
    token = str(selector).strip().lower()
    if token == "first":
        return states[0]
    if token == "last":
        return states[-1]
    capture = int(token)
    for state in states:
        if int(state.metadata.get("capture_index", -1)) == capture:
            return state
    raise ValueError(f"capture index {capture} was not found in {path}")


def _load_escape_npz(path: str | None, assume_optically_thin: bool) -> EscapeProbabilityContext:
    if path is None:
        return EscapeProbabilityContext(allow_missing_as_zero=assume_optically_thin)
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(
            f"escape NPZ does not exist: {target}. Supply a real file, use --xstar-run-dir "
            "to derive it from xo01_detal2.fits/xo01_detal3.fits, or use "
            "--assume-optically-thin only for a controlled optically thin test."
        )
    with np.load(target, allow_pickle=False) as z:
        def maybe(name: str):
            return np.asarray(z[name], dtype=float) if name in z.files else None
        return EscapeProbabilityContext(
            line_tau_in=maybe("line_tau_in"),
            line_tau_out=maybe("line_tau_out"),
            continuum_tau_in=maybe("continuum_tau_in"),
            continuum_tau_out=maybe("continuum_tau_out"),
            allow_missing_as_zero=assume_optically_thin,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Translate and execute levwkelement -> calc_hmc_ion -> "
            "calc_hmc_element -> msolvelucy for one complete XSTAR element."
        )
    )
    parser.add_argument("--atdb", required=True, help="Path to XSTAR atdb.fits")
    parser.add_argument("--pointer-cache", help="Optional v0.4.1 derived-pointer NPZ cache")
    parser.add_argument("--element-z", type=int, default=8)
    parser.add_argument("--min-ion-stage", type=int, default=3)
    parser.add_argument("--max-ion-stage", type=int, default=8)
    parser.add_argument("--temperature-k", type=float, required=True)
    parser.add_argument("--hydrogen-density-cm3", type=float, required=True)
    parser.add_argument("--electron-fraction-xee", type=float, required=True)
    parser.add_argument("--covering-fraction", type=float, default=1.0)
    parser.add_argument("--turbulent-velocity-km-s", type=float, default=0.0)
    parser.add_argument("--neutral-h-density-cm3", type=float, default=0.0)
    parser.add_argument("--ionized-h-density-cm3", type=float, default=0.0)
    parser.add_argument("--abundance", type=float, default=1.0)
    parser.add_argument("--lfast", type=int, default=2)
    parser.add_argument("--live-rate-grid-probe-csv")
    parser.add_argument("--live-rate-grid-state", default="last", help="first, last, or capture_index")
    escape_group = parser.add_mutually_exclusive_group()
    escape_group.add_argument("--escape-npz", help="NPZ with line_tau_in/out and continuum_tau_in/out")
    escape_group.add_argument(
        "--xstar-run-dir",
        help="Build escape state from xo01_detal2.fits (lines) and xo01_detal3.fits (RRCs)",
    )
    parser.add_argument(
        "--escape-zone", default="last",
        help="XSTAR radial zone/HDU selector for --xstar-run-dir: first, last, integer zone, or HDU index",
    )
    parser.add_argument(
        "--write-derived-escape-npz",
        help="Optional path for saving escape arrays derived from --xstar-run-dir",
    )
    parser.add_argument(
        "--escape-detail-policy",
        choices=("source_sparse_reconstruct", "strict_selected_zone"),
        default="source_sparse_reconstruct",
        help="Reconstruct sparse detail history (default) or require rows in the selected zone only",
    )
    parser.add_argument(
        "--assume-optically-thin",
        action="store_true",
        help="Use zero optical depth when an escape array is not supplied",
    )
    parser.add_argument(
        "--allow-context-blocked",
        action="store_true",
        help="Write partial assembly products and run the solve if terms exist; readiness remains false",
    )
    parser.add_argument("--max-lucy-iterations", type=int, default=200)
    parser.add_argument("--max-fixed-point-iterations", type=int, default=200)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    built = load_atomic_database_state(
        args.atdb,
        pointer_cache=args.pointer_cache,
    )
    try:
        radiation = _select_live_state(args.live_rate_grid_probe_csv, args.live_rate_grid_state)
        escape_build = None
        try:
            if args.xstar_run_dir:
                escape_build = load_escape_state_from_xstar_run(
                    args.xstar_run_dir,
                    built.derived,
                    zone=args.escape_zone,
                    allow_missing_as_zero=args.assume_optically_thin,
                    detail_policy=args.escape_detail_policy,
                )
                escape = escape_build.context
                if args.write_derived_escape_npz:
                    write_escape_state_npz(escape_build, args.write_derived_escape_npz)
                write_escape_state_summary(escape_build, args.out_dir)
            else:
                escape = _load_escape_npz(args.escape_npz, args.assume_optically_thin)
        except (FileNotFoundError, EscapeStateError) as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        context = ElementEquilibriumContext(
            temperature_k=args.temperature_k,
            hydrogen_density_cm3=args.hydrogen_density_cm3,
            electron_fraction_xee=args.electron_fraction_xee,
            min_ion_stage=args.min_ion_stage,
            max_ion_stage=args.max_ion_stage,
            radiation=radiation,
            escape=escape,
            covering_fraction=args.covering_fraction,
            turbulent_velocity_km_s=args.turbulent_velocity_km_s,
            neutral_h_density_cm3=args.neutral_h_density_cm3,
            ionized_h_density_cm3=args.ionized_h_density_cm3,
            abundance=args.abundance,
            lfast=args.lfast,
            strict_context=not args.allow_context_blocked,
            max_lucy_iterations=args.max_lucy_iterations,
            max_fixed_point_iterations=args.max_fixed_point_iterations,
        )
        result = solve_element_statistical_equilibrium(
            built.master,
            built.derived,
            element_z=args.element_z,
            context=context,
        )
        outputs = write_element_equilibrium_products(result, args.out_dir)
        if args.print_summary:
            a = result.assembly
            s = result.solve
            print("XSTAR complete element statistical-equilibrium subsystem")
            print("------------------------------------------------------")
            print("port_version=v0.4.5")
            print("status=element_statistical_equilibrium_subsystem_completed")
            print(f"element_z={a.basis.element_z}")
            print(f"ion_stage_range={a.basis.min_ion_stage}..{a.basis.max_ion_stage}")
            print(f"n_compact_rows={a.basis.n_rows}")
            print(f"n_ion_blocks={len(a.basis.blocks)}")
            print(f"n_superlevels={a.basis.n_superlevels}")
            print(f"normalization_row={a.basis.normalization_row}")
            print(f"n_shared_alias_rows={sum(r.is_shared_alias for r in a.basis.rows)}")
            if escape_build is not None:
                print("escape_state_source=xstar_run_detail_files")
                print(f"escape_state_zone_selector={escape_build.zone_selector}")
                print(f"escape_state_detail_policy={escape_build.detail_policy}")
                print(f"escape_state_exact_live_arrays={escape_build.exact_live_arrays}")
                print(f"escape_state_source_writer_threshold_reconstruction={escape_build.source_writer_threshold_reconstruction}")
                print(f"n_escape_line_indices_carried_forward={escape_build.n_line_indices_carried_forward}")
                print(f"n_escape_rrc_indices_carried_forward={escape_build.n_rrc_indices_carried_forward}")
                print(f"n_escape_line_indices_zero_filled={escape_build.n_line_indices_zero_filled}")
                print(f"n_escape_rrc_indices_zero_filled={escape_build.n_rrc_indices_zero_filled}")
                print(f"n_escape_line_indices_loaded={escape_build.n_line_indices_loaded}")
                print(f"n_escape_line_indices_missing={escape_build.n_line_indices_missing}")
                print(f"n_escape_rrc_indices_loaded={escape_build.n_rrc_indices_loaded}")
                print(f"n_escape_rrc_indices_missing={escape_build.n_rrc_indices_missing}")
                print(f"escape_state_global_arrays_complete={escape_build.complete}")
            elif args.escape_npz:
                print(f"escape_state_source=npz:{args.escape_npz}")
            elif args.assume_optically_thin:
                print("escape_state_source=explicit_optically_thin_zero_depth")
            else:
                print("escape_state_source=missing_strict_context")
            print(f"n_records_seen={a.n_records_seen}")
            print(f"n_records_evaluated={a.n_records_evaluated}")
            print(f"n_records_source_noop={a.n_records_source_noop}")
            print(f"n_records_skipped={a.n_records_skipped}")
            print(f"n_records_blocked={a.n_records_blocked}")
            print(f"n_unmapped_matrix_endpoints={a.n_unmapped_endpoints}")
            print(f"n_matrix_terms={len(a.terms)}")
            print(f"strict_matrix_assembly_ready={a.strict_assembly_ready}")
            if s is not None:
                print(f"solver_converged={s.converged}")
                print(f"solver_method={s.solver_method}")
                print(f"outer_iterations={s.outer_iterations}")
                print(f"fixed_point_iterations={s.fixed_point_iterations}")
                print(f"n_negative_populations={s.n_negative_populations}")
                print(f"population_normalization={s.normalization}")
                print(f"population_normalization_error={s.normalization_error}")
                print(f"max_relative_row_residual={s.max_relative_row_residual}")
                print(f"dense_normalized_matrix_rank={s.dense_rank}")
                print(f"dense_normalized_matrix_condition_number={s.dense_condition_number}")
            else:
                print("solver_converged=False")
                print("solver_status=not_run_due_to_incomplete_strict_assembly")
            print(f"full_element_direct_solve_ready={result.full_element_direct_solve_ready}")
            print("six_row_and_119_row_products_role=regression_subsets_only")
            print("dominant_next_target=generalize_validated_element_solve_to_all_30_elements_then_local_ionization_thermal_closure")
            for key, path in outputs.items():
                print(f"{key}: {path}")
        return 0 if result.full_element_direct_solve_ready or args.allow_context_blocked else 2
    finally:
        built.atomic_state.close()


if __name__ == "__main__":
    raise SystemExit(main())
