"""CLI for complete fixed-state ``calc_hmc_all`` thermal/charge parity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .source_port import (
    BremsstrahlungContext,
    Comp2Context,
    FreeFreeContext,
    HeatFContext,
    compare_bremem_probe,
    compare_calc_hmc_all_pre_continuum_probe,
    compare_comp2_probe,
    compare_complete_fixed_state_calc_hmc_all,
    compare_freef_probe,
    compare_heatf_probe,
    load_all_element_fixed_state_plan,
    load_atomic_database_state,
    load_bremem_probe_reference,
    load_calc_hmc_all_final_state_reference,
    load_calc_hmc_all_probe_critf,
    load_compton_table,
    load_comp2_probe_reference,
    load_freef_probe_reference,
    load_heatf_probe_reference,
    run_all_element_fixed_state,
    validate_v0438_all_element_regression,
    validate_v0439_comp2_regression,
    validate_v0440_freef_regression,
    validate_v0441_bremem_regression,
    validate_v0442_heatf_regression,
    write_bremem_parity_products,
    write_calc_hmc_all_pre_continuum_parity_products,
    write_complete_fixed_state_parity_products,
    write_comp2_parity_products,
    write_fixed_state_calc_hmc_all_products,
    write_freef_parity_products,
    write_heatf_parity_products,
)
from .source_port_all_element_cli import _resolve_runtime
from .source_port_element_cli import _load_escape_npz, _select_live_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the complete fixed-state calc_hmc_all source sequence and "
            "validate final thermal and charge state against one same-call XSTAR probe."
        )
    )
    parser.add_argument("--atdb", required=True)
    parser.add_argument("--pointer-cache")
    parser.add_argument("--temperature-k", type=float, required=True)
    parser.add_argument("--hydrogen-density-cm3", type=float, required=True)
    parser.add_argument("--electron-fraction-xee", type=float, required=True)
    parser.add_argument("--covering-fraction", type=float, default=1.0)
    parser.add_argument("--turbulent-velocity-km-s", type=float, default=0.0)
    parser.add_argument("--pressure", type=float, default=0.0)
    parser.add_argument("--lcdd", type=int, default=1)
    parser.add_argument("--lfast", type=int, default=2)
    parser.add_argument("--critf", type=float)
    parser.add_argument("--live-rate-grid-probe-csv", required=True)
    parser.add_argument("--live-rate-grid-state", default="last")
    parser.add_argument("--escape-npz")
    parser.add_argument("--assume-optically-thin", action="store_true")
    parser.add_argument("--xstar-population-probe-csv", required=True)
    parser.add_argument("--xstar-population-solve-call-id")
    parser.add_argument(
        "--population-probe-runtime-policy",
        choices=("use", "check", "ignore"),
        default="use",
    )
    parser.add_argument("--runtime-reference-element-z", type=int, default=8)
    parser.add_argument("--xstar-calc-hmc-probe-dir", required=True)
    parser.add_argument("--xstar-calc-hmc-call-id", type=int, default=73)
    parser.add_argument("--coheat-data")
    parser.add_argument("--oxygen-call73-regression-dir", required=True)
    parser.add_argument("--all-element-v0438-regression-dir")
    parser.add_argument("--comp2-v0439-regression-dir")
    parser.add_argument("--freef-v0440-regression-dir")
    parser.add_argument("--bremem-v0441-regression-dir")
    parser.add_argument("--heatf-v0442-regression-dir")
    parser.add_argument(
        "--initial-population-policy",
        choices=("use-available", "require-all", "ignore"),
        default="require-all",
    )
    parser.add_argument("--abundance-floor", type=float, default=1.0e-24)
    parser.add_argument("--pre-continuum-rtol", type=float, default=5.0e-3)
    parser.add_argument("--pre-continuum-atol", type=float, default=1.0e-12)
    parser.add_argument("--final-rtol", type=float, default=5.0e-3)
    parser.add_argument("--final-atol", type=float, default=1.0e-12)
    parser.add_argument("--continuum-rtol", type=float, default=5.0e-12)
    parser.add_argument("--continuum-atol", type=float, default=1.0e-30)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    temperature_k, xpx, xee, cfrac, runtime_source = _resolve_runtime(args)
    call_id = int(args.xstar_calc_hmc_call_id)
    probe_dir = Path(args.xstar_calc_hmc_probe_dir)

    plan = load_all_element_fixed_state_plan(
        probe_dir,
        oxygen_regression_dir=args.oxygen_call73_regression_dir,
        call_id=call_id,
        abundance_floor=args.abundance_floor,
    )
    if args.critf is None:
        critf = float(
            load_calc_hmc_all_probe_critf(probe_dir, element_z=8, call_id=call_id).critf
        )
        critf_source = "xstar_calc_hmc_probe"
    else:
        critf = float(args.critf)
        critf_source = "command_line"

    radiation = _select_live_state(args.live_rate_grid_probe_csv, args.live_rate_grid_state)
    escape = _load_escape_npz(args.escape_npz, args.assume_optically_thin)

    comp2_ref = load_comp2_probe_reference(probe_dir, call_id=call_id)
    freef_ref = load_freef_probe_reference(probe_dir, call_id=call_id)
    bremem_ref = load_bremem_probe_reference(probe_dir, call_id=call_id)
    heatf_ref = load_heatf_probe_reference(probe_dir, call_id=call_id)
    final_ref = load_calc_hmc_all_final_state_reference(probe_dir, call_id=call_id)
    table = load_compton_table(args.coheat_data, atdb_path=args.atdb)

    comp2_context = Comp2Context(
        comp2_ref.epi_eV,
        comp2_ref.bremsa,
        table,
        ncn2=comp2_ref.ncn2,
        source="xstar_v0443_same_call_probe",
    )
    freef_context = FreeFreeContext(
        freef_ref.epi_eV,
        freef_ref.bremsa,
        freef_ref.opakc_before_cm_inv,
        ncn2=freef_ref.ncn2,
        source="xstar_v0443_same_call_probe",
    )
    bremem_context = BremsstrahlungContext(
        bremem_ref.epi_eV,
        bremem_ref.brcems_before,
        bremem_ref.opakc_before_cm_inv,
        ncn2=bremem_ref.ncn2,
        source="xstar_v0443_same_call_probe",
    )
    heatf_context = HeatFContext(
        heatf_ref.epi_eV,
        heatf_ref.brcems,
        heatf_ref.htfreef_erg_cm3_s,
        heatf_ref.cmp1,
        heatf_ref.cmp2,
        heatf_ref.httot_before,
        heatf_ref.cltot_before,
        heatf_ref.httot2_before,
        heatf_ref.cltot2_before,
        radius_cm=heatf_ref.radius_cm,
        zone_thickness_cm=heatf_ref.zone_thickness_cm,
        ncn2=heatf_ref.ncn2,
        source="xstar_v0443_same_call_probe",
    )

    built = load_atomic_database_state(
        args.atdb,
        pointer_cache=args.pointer_cache,
        use_pointer_cache=True,
    )
    try:
        run = run_all_element_fixed_state(
            built.master,
            built.derived,
            plan=plan,
            temperature_k=temperature_k,
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=xee,
            radiation=radiation,
            escape=escape,
            covering_fraction=cfrac,
            turbulent_velocity_km_s=args.turbulent_velocity_km_s,
            pressure=args.pressure,
            lcdd=args.lcdd,
            lfast=args.lfast,
            critf=critf,
            initial_population_policy=args.initial_population_policy,
            compton_context=comp2_context,
            free_free_context=freef_context,
            bremem_context=bremem_context,
            heatf_context=heatf_context,
        )
        result = run.result
        result.diagnostics.update(
            {
                "runtime_context_source": runtime_source,
                "effective_critf": critf,
                "critf_source": critf_source,
                "v0444_complete_fixed_state_execution": True,
                "v0444_pre_continuum_state_ownership_correction": True,
                "v0443_probe_products_reused": True,
            }
        )
        pre = compare_calc_hmc_all_pre_continuum_probe(
            result,
            probe_dir,
            call_id=call_id,
            rtol=args.pre_continuum_rtol,
            atol=args.pre_continuum_atol,
        )
        comp2 = compare_comp2_probe(
            comp2_ref,
            table=table,
            rtol=args.continuum_rtol,
            atol=args.continuum_atol,
        )
        freef = compare_freef_probe(
            freef_ref,
            rtol=args.continuum_rtol,
            atol=args.continuum_atol,
        )
        bremem = compare_bremem_probe(
            bremem_ref,
            rtol=args.continuum_rtol,
            atol=args.continuum_atol,
        )
        heatf = compare_heatf_probe(
            heatf_ref,
            rtol=args.continuum_rtol,
            atol=args.continuum_atol,
        )
        final = compare_complete_fixed_state_calc_hmc_all(
            result,
            final_ref,
            rtol=args.final_rtol,
            atol=args.final_atol,
            continuum_rtol=args.continuum_rtol,
            continuum_atol=args.continuum_atol,
        )
    finally:
        built.master.close()

    oxygen = plan.oxygen_regression
    all_element_frozen = validate_v0438_all_element_regression(
        args.all_element_v0438_regression_dir
    )
    comp2_frozen = validate_v0439_comp2_regression(args.comp2_v0439_regression_dir)
    freef_frozen = validate_v0440_freef_regression(args.freef_v0440_regression_dir)
    bremem_frozen = validate_v0441_bremem_regression(args.bremem_v0441_regression_dir)
    heatf_frozen = validate_v0442_heatf_regression(args.heatf_v0442_regression_dir)

    acceptance = bool(
        final.ready
        and pre.all_element_pre_continuum_acceptance_ready
        and comp2.ready
        and freef.ready
        and bremem.ready
        and heatf.ready
        and oxygen.ready
        and all_element_frozen.ready
        and comp2_frozen.ready
        and freef_frozen.ready
        and bremem_frozen.ready
        and heatf_frozen.ready
    )

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        f"fixed_state_{key}": str(value)
        for key, value in write_fixed_state_calc_hmc_all_products(
            result, out, port_version="v0.4.44"
        ).items()
    }
    writers = (
        ("pre_continuum", write_calc_hmc_all_pre_continuum_parity_products(pre, out, port_version="v0.4.44")),
        ("comp2", write_comp2_parity_products(comp2, out, port_version="v0.4.44")),
        ("freef", write_freef_parity_products(freef, out, port_version="v0.4.44")),
        ("bremem", write_bremem_parity_products(bremem, out, port_version="v0.4.44")),
        ("heatf", write_heatf_parity_products(heatf, out, port_version="v0.4.44")),
        ("complete", write_complete_fixed_state_parity_products(final, out, port_version="v0.4.44")),
    )
    for prefix, product_paths in writers:
        for key, value in product_paths.items():
            paths[f"{prefix}_{key}"] = str(value)

    summary = {
        "port_version": "v0.4.44",
        "calc_hmc_all_call_id": call_id,
        "fixed_state_calc_hmc_all_translated": final.fixed_state_calc_hmc_all_translated,
        "pre_matrix_ready": final.pre_matrix_ready,
        "element_loop_ready": final.element_loop_ready,
        "charge_scope_complete": final.charge_scope_complete,
        "continuum_sequence_complete": final.continuum_sequence_complete,
        "current_all_element_pre_continuum_parity": pre.all_element_pre_continuum_acceptance_ready,
        "current_comp2_parity": comp2.ready,
        "current_freef_parity": freef.ready,
        "current_bremem_parity": bremem.ready,
        "current_heatf_parity": heatf.ready,
        "runtime_state_parity": final.runtime_state_parity_ready,
        "continuum_component_parity": final.continuum_component_parity_ready,
        "primary_heating_cooling_totals_parity": final.primary_heating_cooling_totals_parity_ready,
        "secondary_heating_cooling_totals_parity": final.secondary_heating_cooling_totals_parity_ready,
        "electron_contribution_parity": final.electron_contribution_parity_ready,
        "charge_residual_parity": final.charge_residual_parity_ready,
        "charge_identity_parity": final.charge_identity_ready,
        "hmctot_parity": final.hmctot_parity_ready,
        "complete_fixed_state_ready": final.complete_fixed_state_ready,
        "frozen_oxygen_regression": oxygen.ready,
        "frozen_h_he_o_pre_continuum_regression": all_element_frozen.ready,
        "frozen_comp2_regression": comp2_frozen.ready,
        "frozen_freef_regression": freef_frozen.ready,
        "frozen_bremem_regression": bremem_frozen.ready,
        "frozen_heatf_regression": heatf_frozen.ready,
        "pre_continuum_state_owned_explicitly": True,
        "v0443_probe_products_reused": True,
        "v0444_complete_fixed_state_acceptance_ready": acceptance,
        "final_probe_source": final_ref.summary_path,
        "oxygen_regression_source": oxygen.source_path,
        "all_element_regression_source": all_element_frozen.source_path,
        "comp2_regression_source": comp2_frozen.source_path,
        "freef_regression_source": freef_frozen.source_path,
        "bremem_regression_source": bremem_frozen.source_path,
        "heatf_regression_source": heatf_frozen.source_path,
        "remaining_source_sequence": "dsec",
    }
    acceptance_json = out / "xstar_calc_hmc_all_v0444_acceptance_summary.json"
    acceptance_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    acceptance_md = out / "xstar_calc_hmc_all_v0444_acceptance_summary.md"
    acceptance_md.write_text(
        "# xstar-atomic v0.4.44 complete fixed-state acceptance\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    paths["acceptance_json"] = str(acceptance_json)
    paths["acceptance_markdown"] = str(acceptance_md)

    if args.print_summary:
        print("XSTAR complete fixed-state calc_hmc_all thermal/charge parity")
        print("------------------------------------------------------------")
        for key in (
            "port_version",
            "calc_hmc_all_call_id",
            "fixed_state_calc_hmc_all_translated",
            "pre_matrix_ready",
            "element_loop_ready",
            "charge_scope_complete",
            "continuum_sequence_complete",
            "current_all_element_pre_continuum_parity",
            "current_comp2_parity",
            "current_freef_parity",
            "current_bremem_parity",
            "current_heatf_parity",
            "runtime_state_parity",
            "continuum_component_parity",
            "primary_heating_cooling_totals_parity",
            "secondary_heating_cooling_totals_parity",
            "electron_contribution_parity",
            "charge_residual_parity",
            "charge_identity_parity",
            "hmctot_parity",
            "complete_fixed_state_ready",
            "frozen_oxygen_regression",
            "frozen_h_he_o_pre_continuum_regression",
            "frozen_comp2_regression",
            "frozen_freef_regression",
            "frozen_bremem_regression",
            "frozen_heatf_regression",
            "pre_continuum_state_owned_explicitly",
            "v0443_probe_products_reused",
            "v0444_complete_fixed_state_acceptance_ready",
            "remaining_source_sequence",
        ):
            print(f"{key}={summary[key]}")
        for key, value in paths.items():
            print(f"{key}: {value}")
    return 0 if acceptance else 2


if __name__ == "__main__":
    raise SystemExit(main())
