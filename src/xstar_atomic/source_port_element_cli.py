"""Command-line interface for the source-faithful element equilibrium port."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from collections import Counter
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
    PopulationParityError,
    load_xstar_population_reference,
    load_xstar_runtime_context_reference,
    compare_element_population_parity,
    write_element_population_parity_products,
    MSolveStateParityError,
    compare_msolvelucy_state_probe,
    write_msolvelucy_state_parity_products,
    FullElementMatrixParityError,
    compare_full_element_matrix_probe,
    write_full_element_matrix_parity_products,
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
    parser.add_argument(
        "--xstar-population-probe-csv",
        help="Paired before/after msolvelucy population probe used for the Milestone-3 parity gate",
    )
    parser.add_argument(
        "--xstar-population-solve-call-id",
        help="Explicit solve_call_id in --xstar-population-probe-csv; default selects by occurrence rank",
    )
    parser.add_argument(
        "--xstar-population-occurrence-rank", type=int, default=-1,
        help="1-based matching O-element solve occurrence, or -1 for latest (default)",
    )
    parser.add_argument(
        "--population-probe-runtime-policy",
        choices=("use", "check", "ignore"),
        default="use",
        help=(
            "How to handle T/xpx/xee/cfrac stored in the selected population probe: "
            "use them before matrix assembly (default), require explicit inputs to match, "
            "or ignore them for a controlled mismatch test"
        ),
    )
    parser.add_argument(
        "--population-probe-runtime-relative-tolerance",
        type=float,
        default=5.0e-8,
        help="Relative tolerance for --population-probe-runtime-policy check",
    )
    parser.add_argument("--population-parity-max-abs-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--population-parity-l1-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--population-parity-relative-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--population-parity-relative-floor", type=float, default=1.0e-12)
    parser.add_argument(
        "--no-xstar-before-seeded-solve", action="store_true",
        help="Skip the controlled alternate solve initialized from XSTAR's captured pre-msolvelucy vector",
    )
    parser.add_argument(
        "--write-msolvelucy-trace", action="store_true",
        help="Write outer, superlevel, condensed-matrix, and fixed-point Python solver states",
    )
    parser.add_argument(
        "--xstar-msolvelucy-state-probe-dir",
        help="Directory containing the iteration-level XSTAR msolvelucy probe CSVs",
    )
    parser.add_argument("--msolvelucy-state-absolute-tolerance", type=float, default=1.0e-10)
    parser.add_argument("--msolvelucy-state-relative-tolerance", type=float, default=5.0e-5)
    parser.add_argument("--msolvelucy-state-relative-floor", type=float, default=1.0e-30)
    parser.add_argument(
        "--xstar-ucalc-probe-csv",
        help="Instrumented xstar_ucalc_record_probe.csv for complete record-level matrix parity",
    )
    parser.add_argument(
        "--xstar-matrix-probe-csv",
        help="Instrumented xstar_calc_hmc_ion_matrix_probe.csv for complete record-level matrix parity",
    )
    parser.add_argument("--full-element-matrix-absolute-tolerance", type=float, default=1.0e-10)
    parser.add_argument("--full-element-matrix-relative-tolerance", type=float, default=5.0e-5)
    parser.add_argument("--full-element-matrix-relative-floor", type=float, default=1.0e-30)
    parser.add_argument(
        "--require-full-element-matrix-parity", action="store_true",
        help="Return a nonzero status unless the supplied record-level XSTAR matrix probes match",
    )
    parser.add_argument(
        "--require-msolvelucy-state-parity", action="store_true",
        help="Return a nonzero status unless the supplied iteration-level state probe matches",
    )
    parser.add_argument(
        "--require-xstar-population-parity", action="store_true",
        help="Return a nonzero status unless the supplied XSTAR population parity gate passes",
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser



def _write_assembly_blocker_summary(assembly: object, out_dir: str | Path) -> dict[str, Path]:
    """Write a compact grouped summary when strict assembly cannot execute.

    Population and Lucy parity require a native solve, but a context-blocked
    assembly is itself a valuable source-port diagnostic.  Preserve that
    result instead of raising before the ordinary element products are written.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    blocked = list(getattr(assembly, "blocked_records", ()) or ())
    counts: Counter[tuple[str, str, str, str]] = Counter()
    for row in blocked:
        data_type = str(row.get("data_type", ""))
        rate_type = str(row.get("rate_type", ""))
        status = str(row.get("status", ""))
        reason = str(row.get("reason", "") or status or "unspecified")
        counts[(data_type, rate_type, status, reason)] += 1
    rows = [
        {
            "data_type": key[0],
            "rate_type": key[1],
            "status": key[2],
            "reason": key[3],
            "count": count,
        }
        for key, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1], item[0][3]),
        )
    ]
    csv_path = out / "xstar_element_assembly_blocker_summary.csv"
    fields = ["data_type", "rate_type", "status", "reason", "count"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "port_version": "v0.4.14",
        "status": "strict_element_assembly_incomplete",
        "n_records_blocked": int(getattr(assembly, "n_records_blocked", len(blocked))),
        "n_unmapped_matrix_endpoints": int(getattr(assembly, "n_unmapped_endpoints", 0)),
        "n_grouped_blocker_reasons": len(rows),
        "top_blockers": rows[:20],
        "population_parity_status": "not_run_due_to_incomplete_strict_assembly",
        "msolvelucy_state_parity_status": "not_run_due_to_incomplete_strict_assembly",
    }
    json_path = out / "xstar_element_assembly_blocker_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    md_path = out / "xstar_element_assembly_blocker_summary.md"
    lines = [
        "# XSTAR element strict-assembly blocker summary",
        "",
        f"- Port version: `v0.4.14`",
        f"- Blocked records: `{summary['n_records_blocked']}`",
        f"- Unmapped endpoints: `{summary['n_unmapped_matrix_endpoints']}`",
        f"- Grouped reasons: `{summary['n_grouped_blocker_reasons']}`",
        "- Population parity: `not run; no strict native solve was executed`",
        "- Lucy-state parity: `not run; no strict native solve was executed`",
        "",
        "| Count | Data type | Rate type | Status | Reason |",
        "|---:|---:|---:|---|---|",
    ]
    for row in rows[:50]:
        reason = str(row["reason"]).replace("|", "\\|")
        status = str(row["status"]).replace("|", "\\|")
        lines.append(
            f"| {row['count']} | {row['data_type']} | {row['rate_type']} | {status} | {reason} |"
        )
    md_path.write_text("\n".join(lines) + "\n")
    return {
        "assembly_blocker_summary_csv": csv_path,
        "assembly_blocker_summary_json": json_path,
        "assembly_blocker_summary_markdown": md_path,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    requested_runtime = {
        "temperature_k": float(args.temperature_k),
        "hydrogen_density_cm3": float(args.hydrogen_density_cm3),
        "electron_fraction_xee": float(args.electron_fraction_xee),
        "electron_density_cm3": float(args.hydrogen_density_cm3) * float(args.electron_fraction_xee),
        "covering_fraction": float(args.covering_fraction),
    }
    runtime_reference = None
    effective_runtime = dict(requested_runtime)
    runtime_context_source = "explicit_cli"
    if args.xstar_population_probe_csv and args.population_probe_runtime_policy != "ignore":
        try:
            runtime_reference = load_xstar_runtime_context_reference(
                args.xstar_population_probe_csv,
                element_z=args.element_z,
                solve_call_id=args.xstar_population_solve_call_id,
                occurrence_rank=args.xstar_population_occurrence_rank,
            )
        except (FileNotFoundError, PopulationParityError, ValueError) as exc:
            raise SystemExit(f"ERROR: {exc}") from exc
        probe_runtime = {
            "temperature_k": runtime_reference.temperature_k,
            "hydrogen_density_cm3": runtime_reference.hydrogen_density_cm3,
            "electron_fraction_xee": runtime_reference.electron_fraction_xee,
            "electron_density_cm3": runtime_reference.electron_density_cm3,
            "covering_fraction": runtime_reference.covering_fraction,
        }
        if args.population_probe_runtime_policy == "check":
            tol = float(args.population_probe_runtime_relative_tolerance)
            mismatches = []
            for key, reference_value in probe_runtime.items():
                requested_value = requested_runtime[key]
                scale = max(abs(reference_value), abs(requested_value), 1.0e-300)
                if abs(requested_value - reference_value) > tol * scale:
                    mismatches.append(
                        f"{key}: requested={requested_value:.17g}, probe={reference_value:.17g}"
                    )
            if mismatches:
                raise SystemExit(
                    "ERROR: explicit runtime context does not match the selected XSTAR population probe: "
                    + "; ".join(mismatches)
                )
            runtime_context_source = "explicit_cli_verified_against_xstar_population_probe"
        else:
            effective_runtime = probe_runtime
            runtime_context_source = "xstar_population_probe"

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
            temperature_k=effective_runtime["temperature_k"],
            hydrogen_density_cm3=effective_runtime["hydrogen_density_cm3"],
            electron_fraction_xee=effective_runtime["electron_fraction_xee"],
            min_ion_stage=args.min_ion_stage,
            max_ion_stage=args.max_ion_stage,
            radiation=radiation,
            escape=escape,
            covering_fraction=effective_runtime["covering_fraction"],
            turbulent_velocity_km_s=args.turbulent_velocity_km_s,
            neutral_h_density_cm3=args.neutral_h_density_cm3,
            ionized_h_density_cm3=args.ionized_h_density_cm3,
            abundance=args.abundance,
            lfast=args.lfast,
            strict_context=not args.allow_context_blocked,
            max_lucy_iterations=args.max_lucy_iterations,
            max_fixed_point_iterations=args.max_fixed_point_iterations,
            capture_lucy_trace=bool(
                args.write_msolvelucy_trace
                or args.xstar_population_probe_csv
                or args.xstar_msolvelucy_state_probe_dir
            ),
        )
        result = solve_element_statistical_equilibrium(
            built.master,
            built.derived,
            element_z=args.element_z,
            context=context,
        )
        if runtime_reference is not None and runtime_reference.n_rows != result.assembly.basis.n_rows:
            raise SystemExit(
                "ERROR: selected population-probe runtime context has "
                f"ipmat2={runtime_reference.n_rows}, but the native basis has "
                f"{result.assembly.basis.n_rows} rows"
            )
        matrix_parity = None
        matrix_parity_outputs = {}
        if bool(args.xstar_ucalc_probe_csv) != bool(args.xstar_matrix_probe_csv):
            raise SystemExit(
                "ERROR: --xstar-ucalc-probe-csv and --xstar-matrix-probe-csv must be supplied together"
            )
        if args.xstar_ucalc_probe_csv and args.xstar_matrix_probe_csv:
            try:
                matrix_parity = compare_full_element_matrix_probe(
                    result.assembly,
                    args.xstar_ucalc_probe_csv,
                    args.xstar_matrix_probe_csv,
                    absolute_tolerance=args.full_element_matrix_absolute_tolerance,
                    relative_tolerance=args.full_element_matrix_relative_tolerance,
                    relative_floor=args.full_element_matrix_relative_floor,
                )
            except (FileNotFoundError, FullElementMatrixParityError, ValueError) as exc:
                raise SystemExit(f"ERROR: {exc}") from exc
            result.full_element_matrix_parity = matrix_parity
        parity = None
        parity_outputs = {}
        population_parity_status = "not_supplied"
        if args.xstar_population_probe_csv:
            if result.solve is None:
                population_parity_status = "not_run_due_to_incomplete_strict_assembly"
            else:
                try:
                    reference = load_xstar_population_reference(
                        args.xstar_population_probe_csv,
                        element_z=args.element_z,
                        n_rows=result.assembly.basis.n_rows,
                        solve_call_id=args.xstar_population_solve_call_id,
                        occurrence_rank=args.xstar_population_occurrence_rank,
                    )
                    parity = compare_element_population_parity(
                        result.assembly,
                        result.solve,
                        context,
                        reference,
                        run_xstar_before_seeded_solve=not args.no_xstar_before_seeded_solve,
                        max_abs_tolerance=args.population_parity_max_abs_tolerance,
                        l1_tolerance=args.population_parity_l1_tolerance,
                        relative_tolerance=args.population_parity_relative_tolerance,
                        relative_floor=args.population_parity_relative_floor,
                    )
                except (FileNotFoundError, PopulationParityError, ValueError) as exc:
                    raise SystemExit(f"ERROR: {exc}") from exc
                result.population_parity = parity
                population_parity_status = "completed"
        state_parity = None
        state_parity_outputs = {}
        msolvelucy_state_parity_status = "not_supplied"
        if args.xstar_msolvelucy_state_probe_dir:
            if not args.xstar_population_probe_csv:
                raise SystemExit(
                    "ERROR: --xstar-msolvelucy-state-probe-dir requires "
                    "--xstar-population-probe-csv so the same solve_call_id and XSTAR-before seed are selected"
                )
            if parity is None:
                msolvelucy_state_parity_status = "not_run_due_to_population_parity_unavailable"
            else:
                comparison_solve = parity.seeded_solve if parity.seeded_solve is not None else result.solve
                comparison_trace_source = (
                    "xstar_before_seeded_python_solve"
                    if parity.seeded_solve is not None else "python_native_seed_solve"
                )
                if comparison_solve is None or comparison_solve.trace is None:
                    msolvelucy_state_parity_status = "not_run_due_to_missing_python_trace"
                else:
                    try:
                        state_parity = compare_msolvelucy_state_probe(
                            comparison_solve.trace,
                            args.xstar_msolvelucy_state_probe_dir,
                            solve_call_id=parity.reference.solve_call_id,
                            comparison_trace_source=comparison_trace_source,
                            absolute_tolerance=args.msolvelucy_state_absolute_tolerance,
                            relative_tolerance=args.msolvelucy_state_relative_tolerance,
                            relative_floor=args.msolvelucy_state_relative_floor,
                        )
                    except (FileNotFoundError, MSolveStateParityError, ValueError) as exc:
                        raise SystemExit(f"ERROR: {exc}") from exc
                    result.msolvelucy_state_parity = state_parity
                    msolvelucy_state_parity_status = "completed"
        outputs = write_element_equilibrium_products(result, args.out_dir)
        if not result.assembly.strict_assembly_ready:
            outputs.update(_write_assembly_blocker_summary(result.assembly, args.out_dir))
        runtime_context_summary = {
            "port_version": "v0.4.14",
            "status": "element_runtime_context_selected",
            "runtime_context_source": runtime_context_source,
            "population_probe_runtime_policy": args.population_probe_runtime_policy,
            "requested_runtime": requested_runtime,
            "effective_runtime": effective_runtime,
            "selected_xstar_population_solve_call_id": (
                None if runtime_reference is None else runtime_reference.solve_call_id
            ),
            "selected_xstar_population_occurrence_rank": (
                None if runtime_reference is None else runtime_reference.occurrence_rank
            ),
            "selected_xstar_population_n_rows": (
                None if runtime_reference is None else runtime_reference.n_rows
            ),
            "selected_probe_metadata": (
                {} if runtime_reference is None else runtime_reference.metadata
            ),
            "population_parity_status": population_parity_status,
            "msolvelucy_state_parity_status": msolvelucy_state_parity_status,
        }
        runtime_json = Path(args.out_dir) / "xstar_element_runtime_context.json"
        runtime_json.write_text(json.dumps(runtime_context_summary, indent=2, sort_keys=True) + "\n")
        runtime_md = Path(args.out_dir) / "xstar_element_runtime_context.md"
        runtime_md.write_text(
            "# XSTAR element runtime-context selection\n\n"
            f"- Port version: `v0.4.14`\n"
            f"- Source: `{runtime_context_source}`\n"
            f"- Policy: `{args.population_probe_runtime_policy}`\n"
            f"- Requested T: `{requested_runtime['temperature_k']}` K\n"
            f"- Effective T: `{effective_runtime['temperature_k']}` K\n"
            f"- Requested xpx: `{requested_runtime['hydrogen_density_cm3']}` cm^-3\n"
            f"- Effective xpx: `{effective_runtime['hydrogen_density_cm3']}` cm^-3\n"
            f"- Requested xee: `{requested_runtime['electron_fraction_xee']}`\n"
            f"- Effective xee: `{effective_runtime['electron_fraction_xee']}`\n"
            f"- Effective ne: `{effective_runtime['electron_density_cm3']}` cm^-3\n"
            f"- Effective cfrac: `{effective_runtime['covering_fraction']}`\n"
        )
        outputs["runtime_context_json"] = runtime_json
        outputs["runtime_context_markdown"] = runtime_md
        if matrix_parity is not None:
            matrix_parity_outputs = write_full_element_matrix_parity_products(matrix_parity, args.out_dir)
            outputs.update(matrix_parity_outputs)
        if parity is not None:
            parity_outputs = write_element_population_parity_products(parity, args.out_dir)
            outputs.update(parity_outputs)
        if state_parity is not None:
            state_parity_outputs = write_msolvelucy_state_parity_products(state_parity, args.out_dir)
            outputs.update(state_parity_outputs)
        if args.print_summary:
            a = result.assembly
            s = result.solve
            print("XSTAR complete element statistical-equilibrium subsystem")
            print("------------------------------------------------------")
            print("port_version=v0.4.14")
            print("status=element_statistical_equilibrium_subsystem_completed")
            print(f"runtime_context_source={runtime_context_source}")
            print(f"population_probe_runtime_policy={args.population_probe_runtime_policy}")
            print(f"requested_temperature_k={requested_runtime['temperature_k']}")
            print(f"effective_temperature_k={effective_runtime['temperature_k']}")
            print(f"requested_hydrogen_density_cm3={requested_runtime['hydrogen_density_cm3']}")
            print(f"effective_hydrogen_density_cm3={effective_runtime['hydrogen_density_cm3']}")
            print(f"requested_electron_fraction_xee={requested_runtime['electron_fraction_xee']}")
            print(f"effective_electron_fraction_xee={effective_runtime['electron_fraction_xee']}")
            print(f"effective_electron_density_cm3={effective_runtime['electron_density_cm3']}")
            print(f"effective_covering_fraction={effective_runtime['covering_fraction']}")
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
            print(f"n_source_ipmat_endpoint_clamps={a.n_source_ipmat_endpoint_clamps}")
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
                print(f"max_active_relative_row_residual={s.max_active_relative_row_residual}")
                print(f"l1_relative_row_residual={s.l1_relative_row_residual}")
                print(f"n_zero_scale_rows={s.n_zero_scale_rows}")
                print(f"msolvelucy_trace_captured={s.trace is not None}")
                print(f"dense_normalized_matrix_rank={s.dense_rank}")
                print(f"dense_normalized_matrix_condition_number={s.dense_condition_number}")
            else:
                print("solver_converged=False")
                print("solver_status=not_run_due_to_incomplete_strict_assembly")
            print(f"full_element_direct_solve_ready={result.full_element_direct_solve_ready}")
            print("six_row_and_119_row_products_role=regression_subsets_only")
            if matrix_parity is not None:
                print(f"full_element_matrix_parity_ready={matrix_parity.full_element_matrix_parity_ready}")
                print(f"full_element_matrix_terms_matched={matrix_parity.n_matched_terms}")
                print(f"full_element_matrix_terms_outside_tolerance={matrix_parity.n_terms_outside_tolerance}")
                print(f"full_element_matrix_first_failing_data_type={matrix_parity.first_failing_data_type}")
                print(f"full_element_matrix_first_failing_rate_type={matrix_parity.first_failing_rate_type}")
                print(f"full_element_matrix_parity_diagnosis={matrix_parity.diagnosis}")
            else:
                print("full_element_matrix_parity_ready=False")
                print("full_element_matrix_parity_status=not_supplied")
            if parity is not None:
                print(f"selected_xstar_population_solve_call_id={parity.reference.solve_call_id}")
                print(f"python_initial_vs_xstar_before_l1={parity.initial_metrics.l1_difference}")
                print(f"python_native_final_vs_xstar_after_l1={parity.native_final_metrics.l1_difference}")
                print(
                    "python_xstar_before_seeded_final_vs_xstar_after_l1="
                    + ("not_run" if parity.seeded_final_metrics is None else str(parity.seeded_final_metrics.l1_difference))
                )
                print(f"xstar_population_parity_ready={parity.xstar_population_parity_ready}")
                print(f"population_parity_diagnosis={parity.diagnosis}")
            if state_parity is not None:
                print(f"msolvelucy_state_parity_ready={state_parity.msolvelucy_state_parity_ready}")
                print(f"msolvelucy_first_failing_component={state_parity.first_failing_component}")
                print(f"msolvelucy_first_failing_comparison_key={state_parity.first_failing_comparison_key}")
                print(f"msolvelucy_first_failing_outer_iteration={state_parity.first_failing_outer_iteration}")
                print(f"msolvelucy_first_failing_fixed_iteration={state_parity.first_failing_fixed_iteration}")
                print(f"msolvelucy_state_parity_diagnosis={state_parity.diagnosis}")
            else:
                print("msolvelucy_state_parity_ready=False")
                print(f"msolvelucy_state_parity_status={msolvelucy_state_parity_status}")
            if parity is None:
                print("xstar_population_parity_ready=False")
                print(f"population_parity_status={population_parity_status}")
            if not a.strict_assembly_ready:
                dominant_next_target = "resolve_remaining_element_matrix_assembly_blockers"
            elif s is None:
                dominant_next_target = "execute_full_element_population_solve"
            elif not s.converged or s.n_negative_populations > 0:
                dominant_next_target = "resolve_msolvelucy_convergence"
            elif not result.full_element_direct_solve_ready:
                dominant_next_target = "resolve_full_element_execution_acceptance"
            elif matrix_parity is not None and not matrix_parity.full_element_matrix_parity_ready:
                dominant_next_target = matrix_parity.diagnosis
            elif parity is None:
                dominant_next_target = "run_xstar_population_parity_gate_before_generalization"
            elif not parity.xstar_population_parity_ready:
                dominant_next_target = parity.diagnosis
            elif state_parity is None:
                dominant_next_target = "run_msolvelucy_iteration_state_parity_before_generalization"
            elif not state_parity.msolvelucy_state_parity_ready:
                dominant_next_target = state_parity.diagnosis
            else:
                dominant_next_target = "generalize_population_validated_element_solve_then_local_ionization_thermal_closure"
            print(f"dominant_next_target={dominant_next_target}")
            for key, path in outputs.items():
                print(f"{key}: {path}")
        if args.require_full_element_matrix_parity:
            return 0 if matrix_parity is not None and matrix_parity.full_element_matrix_parity_ready else 2
        if args.require_msolvelucy_state_parity:
            return 0 if state_parity is not None and state_parity.msolvelucy_state_parity_ready else 2
        if args.require_xstar_population_parity:
            return 0 if parity is not None and parity.xstar_population_parity_ready else 2
        return 0 if result.full_element_direct_solve_ready or args.allow_context_blocked else 2
    finally:
        built.atomic_state.close()


if __name__ == "__main__":
    raise SystemExit(main())
