"""CLI for the bounded XSTAR ``comp2``/``cmpfnc`` source-port milestone."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .source_port import (
    compare_comp2_probe,
    load_comp2_probe_reference,
    load_compton_table,
    validate_oxygen_call73_regression,
    validate_v0438_all_element_regression,
    write_comp2_parity_products,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Translate and validate calc_hmc_all -> comp2 -> cmpfnc -> hunt3 "
            "using the exact same-call XSTAR continuum and coheat.dat table."
        )
    )
    parser.add_argument("--atdb", help="Optional atdb.fits path; coheat.dat is resolved beside it")
    parser.add_argument("--coheat-data", help="Explicit XSTAR coheat.dat path")
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
    parser.add_argument("--rtol", type=float, default=5.0e-12)
    parser.add_argument("--atol", type=float, default=1.0e-30)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    table = load_compton_table(args.coheat_data, atdb_path=args.atdb)
    reference = load_comp2_probe_reference(
        args.xstar_calc_hmc_probe_dir,
        call_id=args.xstar_calc_hmc_call_id,
    )
    parity = compare_comp2_probe(
        reference,
        table=table,
        rtol=args.rtol,
        atol=args.atol,
    )
    oxygen = validate_oxygen_call73_regression(args.oxygen_call73_regression_dir)
    all_element = validate_v0438_all_element_regression(
        args.all_element_v0438_regression_dir
    )
    acceptance = bool(parity.ready and oxygen.ready and all_element.ready)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = write_comp2_parity_products(parity, out, port_version="v0.4.39")
    summary = {
        "port_version": "v0.4.39",
        "calc_hmc_all_call_id": reference.call_id,
        "comp2_translated": parity.comp2_translated,
        "cmpfnc_table_loaded": parity.cmpfnc_table_loaded,
        "cmp1_parity": parity.cmp1_parity_ready,
        "cmp2_parity": parity.cmp2_parity_ready,
        "compton_heating_coefficient_parity": parity.compton_heating_parity_ready,
        "compton_cooling_coefficient_parity": parity.compton_cooling_parity_ready,
        "frozen_oxygen_regression": oxygen.ready,
        "frozen_h_he_o_pre_continuum_regression": all_element.ready,
        "v0439_comp2_acceptance_ready": acceptance,
        "oxygen_regression_source": oxygen.source_path,
        "all_element_regression_source": all_element.source_path,
        "comp2_probe_summary": reference.summary_path,
        "comp2_probe_grid": reference.grid_path,
        "coheat_data": table.source_path,
        "coheat_sha256": table.source_sha256,
        "remaining_source_sequence": "freef -> bremem -> heatf",
    }
    summary_path = out / "xstar_calc_hmc_all_v0439_acceptance_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "xstar_calc_hmc_all_v0439_acceptance_summary.md"
    md_path.write_text(
        "# xstar-atomic v0.4.39 Compton acceptance\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    paths["acceptance_json"] = summary_path
    paths["acceptance_markdown"] = md_path

    if args.print_summary:
        print("XSTAR relativistic Compton subsystem parity")
        print("-------------------------------------------")
        for key in (
            "port_version",
            "calc_hmc_all_call_id",
            "comp2_translated",
            "cmpfnc_table_loaded",
            "cmp1_parity",
            "cmp2_parity",
            "compton_heating_coefficient_parity",
            "compton_cooling_coefficient_parity",
            "frozen_oxygen_regression",
            "frozen_h_he_o_pre_continuum_regression",
            "v0439_comp2_acceptance_ready",
            "remaining_source_sequence",
        ):
            print(f"{key}={summary[key]}")
        for key, path in paths.items():
            print(f"{key}: {path}")
    return 0 if acceptance else 2


if __name__ == "__main__":
    raise SystemExit(main())
