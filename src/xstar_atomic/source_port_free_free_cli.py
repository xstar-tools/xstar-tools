"""CLI for the bounded XSTAR ``freef`` source-port milestone."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .source_port import (
    compare_freef_probe,
    load_freef_probe_reference,
    validate_oxygen_call73_regression,
    validate_v0438_all_element_regression,
    validate_v0439_comp2_regression,
    write_freef_parity_products,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Translate and validate calc_hmc_all -> freef using the exact "
            "same-call continuum, incoming opacity workspace, and source-order integration."
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
    parser.add_argument("--rtol", type=float, default=5.0e-12)
    parser.add_argument("--atol", type=float, default=1.0e-40)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    reference = load_freef_probe_reference(
        args.xstar_calc_hmc_probe_dir,
        call_id=args.xstar_calc_hmc_call_id,
    )
    parity = compare_freef_probe(reference, rtol=args.rtol, atol=args.atol)
    oxygen = validate_oxygen_call73_regression(args.oxygen_call73_regression_dir)
    all_element = validate_v0438_all_element_regression(
        args.all_element_v0438_regression_dir
    )
    comp2 = validate_v0439_comp2_regression(args.comp2_v0439_regression_dir)
    acceptance = bool(parity.ready and oxygen.ready and all_element.ready and comp2.ready)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = write_freef_parity_products(parity, out, port_version="v0.4.40")
    summary = {
        "port_version": "v0.4.40",
        "calc_hmc_all_call_id": reference.call_id,
        "freef_translated": parity.freef_translated,
        "gaunt_factor_mode_unity": parity.gaunt_factor_mode_unity,
        "continuum_grid_parity": parity.continuum_grid_parity_ready,
        "free_free_opacity_increment_parity": parity.free_free_opacity_increment_parity_ready,
        "free_free_opacity_mutation_parity": parity.free_free_opacity_mutation_parity_ready,
        "htfreef_parity": parity.htfreef_parity_ready,
        "frozen_oxygen_regression": oxygen.ready,
        "frozen_h_he_o_pre_continuum_regression": all_element.ready,
        "frozen_comp2_regression": comp2.ready,
        "v0440_freef_acceptance_ready": acceptance,
        "oxygen_regression_source": oxygen.source_path,
        "all_element_regression_source": all_element.source_path,
        "comp2_regression_source": comp2.source_path,
        "freef_probe_summary": reference.summary_path,
        "freef_probe_grid": reference.grid_path,
        "remaining_source_sequence": "bremem -> heatf",
    }
    summary_path = out / "xstar_calc_hmc_all_v0440_acceptance_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "xstar_calc_hmc_all_v0440_acceptance_summary.md"
    md_path.write_text(
        "# xstar-atomic v0.4.40 freef acceptance\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    paths["acceptance_json"] = summary_path
    paths["acceptance_markdown"] = md_path

    if args.print_summary:
        print("XSTAR free-free absorption subsystem parity")
        print("-------------------------------------------")
        for key in (
            "port_version",
            "calc_hmc_all_call_id",
            "freef_translated",
            "gaunt_factor_mode_unity",
            "continuum_grid_parity",
            "free_free_opacity_increment_parity",
            "free_free_opacity_mutation_parity",
            "htfreef_parity",
            "frozen_oxygen_regression",
            "frozen_h_he_o_pre_continuum_regression",
            "frozen_comp2_regression",
            "v0440_freef_acceptance_ready",
            "remaining_source_sequence",
        ):
            print(f"{key}={summary[key]}")
        for key, path in paths.items():
            print(f"{key}: {path}")
    return 0 if acceptance else 2


if __name__ == "__main__":
    raise SystemExit(main())
