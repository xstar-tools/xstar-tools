"""CLI for the bounded XSTAR ``heatf`` source-port milestone."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .xstar import (
    compare_heatf_probe,
    load_heatf_probe_reference,
    validate_oxygen_call73_regression,
    validate_v0438_all_element_regression,
    validate_v0439_comp2_regression,
    validate_v0440_freef_regression,
    validate_v0441_bremem_regression,
    write_heatf_parity_products,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Translate and validate calc_hmc_all -> heatf using exact same-call "
            "Compton, free-free, bremsstrahlung, and incoming element totals."
        )
    )
    parser.add_argument("--xstar-calc-hmc-probe-dir", required=True)
    parser.add_argument("--xstar-calc-hmc-call-id", type=int, default=73)
    parser.add_argument(
        "--oxygen-call73-regression-dir",
        required=True,
        help="Accepted v0.4.34 oxygen output directory or parity summary JSON",
    )
    parser.add_argument(
        "--all-element-v0438-regression-dir",
        help=(
            "Accepted v0.4.38 H/He/O output directory or parity summary JSON. "
            "Omit to use the exact packaged frozen result."
        ),
    )
    parser.add_argument(
        "--comp2-v0439-regression-dir",
        help=(
            "Accepted v0.4.39 comp2 output directory or acceptance summary JSON. "
            "Omit to use the exact packaged frozen result."
        ),
    )
    parser.add_argument(
        "--freef-v0440-regression-dir",
        help=(
            "Accepted v0.4.40 freef output directory or acceptance summary JSON. "
            "Omit to use the exact packaged frozen result."
        ),
    )
    parser.add_argument(
        "--bremem-v0441-regression-dir",
        help=(
            "Accepted v0.4.41 bremem output directory or acceptance summary JSON. "
            "Omit to use the exact packaged frozen result."
        ),
    )
    parser.add_argument("--rtol", type=float, default=5.0e-12)
    parser.add_argument("--atol", type=float, default=1.0e-40)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    reference = load_heatf_probe_reference(
        args.xstar_calc_hmc_probe_dir,
        call_id=args.xstar_calc_hmc_call_id,
    )
    parity = compare_heatf_probe(reference, rtol=args.rtol, atol=args.atol)
    oxygen = validate_oxygen_call73_regression(args.oxygen_call73_regression_dir)
    all_element = validate_v0438_all_element_regression(
        args.all_element_v0438_regression_dir
    )
    comp2 = validate_v0439_comp2_regression(args.comp2_v0439_regression_dir)
    freef = validate_v0440_freef_regression(args.freef_v0440_regression_dir)
    bremem = validate_v0441_bremem_regression(args.bremem_v0441_regression_dir)
    acceptance = bool(
        parity.ready
        and oxygen.ready
        and all_element.ready
        and comp2.ready
        and freef.ready
        and bremem.ready
    )

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = write_heatf_parity_products(parity, out, port_version="v0.4.42")
    summary = {
        "port_version": "v0.4.42",
        "calc_hmc_all_call_id": reference.call_id,
        "heatf_translated": parity.heatf_translated,
        "continuum_grid_parity": parity.continuum_grid_parity_ready,
        "bremsstrahlung_cooling_integral_parity": parity.bremsstrahlung_cooling_integral_parity_ready,
        "compton_heating_accumulation_parity": parity.compton_heating_accumulation_parity_ready,
        "compton_cooling_accumulation_parity": parity.compton_cooling_accumulation_parity_ready,
        "free_free_heating_accumulation_parity": parity.free_free_heating_accumulation_parity_ready,
        "bremsstrahlung_cooling_accumulation_parity": parity.bremsstrahlung_cooling_accumulation_parity_ready,
        "primary_heating_cooling_totals_parity": parity.primary_heating_cooling_totals_parity_ready,
        "secondary_heating_cooling_totals_parity": parity.secondary_heating_cooling_totals_parity_ready,
        "hmctot_parity": parity.hmctot_parity_ready,
        "frozen_oxygen_regression": oxygen.ready,
        "frozen_h_he_o_pre_continuum_regression": all_element.ready,
        "frozen_comp2_regression": comp2.ready,
        "frozen_freef_regression": freef.ready,
        "frozen_bremem_regression": bremem.ready,
        "v0442_heatf_acceptance_ready": acceptance,
        "oxygen_regression_source": oxygen.source_path,
        "all_element_regression_source": all_element.source_path,
        "comp2_regression_source": comp2.source_path,
        "freef_regression_source": freef.source_path,
        "bremem_regression_source": bremem.source_path,
        "heatf_probe_summary": reference.summary_path,
        "heatf_probe_grid": reference.grid_path,
        "remaining_source_sequence": "complete fixed-state calc_hmc_all thermal/charge parity",
    }
    summary_path = out / "xstar_calc_hmc_all_v0442_acceptance_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_path = out / "xstar_calc_hmc_all_v0442_acceptance_summary.md"
    md_path.write_text(
        "# xstar-atomic v0.4.42 heatf acceptance\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    paths["acceptance_json"] = summary_path
    paths["acceptance_markdown"] = md_path

    if args.print_summary:
        print("XSTAR local thermal accumulation subsystem parity")
        print("--------------------------------------------------")
        for key in (
            "port_version",
            "calc_hmc_all_call_id",
            "heatf_translated",
            "continuum_grid_parity",
            "bremsstrahlung_cooling_integral_parity",
            "compton_heating_accumulation_parity",
            "compton_cooling_accumulation_parity",
            "free_free_heating_accumulation_parity",
            "bremsstrahlung_cooling_accumulation_parity",
            "primary_heating_cooling_totals_parity",
            "secondary_heating_cooling_totals_parity",
            "hmctot_parity",
            "frozen_oxygen_regression",
            "frozen_h_he_o_pre_continuum_regression",
            "frozen_comp2_regression",
            "frozen_freef_regression",
            "frozen_bremem_regression",
            "v0442_heatf_acceptance_ready",
            "remaining_source_sequence",
        ):
            print(f"{key}={summary[key]}")
        for key, path in paths.items():
            print(f"{key}: {path}")
    return 0 if acceptance else 2


if __name__ == "__main__":
    raise SystemExit(main())
