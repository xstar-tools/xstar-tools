"""CLI generating the complete v0.4.48 matching-state XSTAR probe bundle."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .xstar_calc_hmc_all_probe import write_calc_hmc_all_probe_products
from .xstar_dsec_probe import write_dsec_probe_products


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the shared call-correlation helper, calc_hmc_all matching-state "
            "probe, dsec trajectory/thermal probe, and all insertion snippets."
        )
    )
    parser.add_argument("--out-dir", required=True)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    calc_products = write_calc_hmc_all_probe_products(out)
    dsec_products = write_dsec_probe_products(out)
    manifest = out / "README_v0448_matching_state_probe.md"
    manifest.write_text(
        "# XSTAR v0.4.48 call-correlated matching-state probe\n\n"
        "Compile in this order:\n\n"
        "1. `xstar_atomic_call_correlation_helpers.f90`\n"
        "2. `xstar_atomic_calc_hmc_all_probe_helpers.f90`\n"
        "3. `xstar_atomic_dsec_probe_helpers.f90`\n"
        "4. the instrumented XSTAR source files.\n\n"
        "Set:\n\n"
        "```bash\n"
        "export XSTAR_ATOMIC_DSEC_TARGET_CALL=1\n"
        "export XSTAR_ATOMIC_HMC_TARGET_DSEC_CALL=1\n"
        "export XSTAR_ATOMIC_HMC_TARGET_DSEC_EVALUATION=1\n"
        "export XSTAR_ATOMIC_HMC_TARGET_DSEC_PHASE=dsec_input_and_post\n"
        "export XSTAR_ATOMIC_HMC_TARGET_ELEMENT=0\n"
        "```\n\n"
        "Delete old probe CSVs before the run. The correlation file identifies "
        "the exact first internal and post-dsec `calc_hmc_all` call IDs.\n",
        encoding="utf-8",
    )
    seen = set()
    for prefix, products in (("calc_hmc", calc_products), ("dsec", dsec_products)):
        for key, value in products.items():
            resolved = str(Path(value))
            if resolved in seen:
                continue
            seen.add(resolved)
            print(f"{prefix}_{key}={value}")
    print(f"manifest={manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
