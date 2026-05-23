"""Generate the original-XSTAR v0.4.79 zone-1 DSEC probe bundle."""
from __future__ import annotations
import argparse
from pathlib import Path
from .xstar_zone1_dsec_probe import write_zone1_probe_products


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    products = write_zone1_probe_products(Path(args.out_dir))
    for key, value in sorted(products.items()):
        print(f"{key}={value}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
