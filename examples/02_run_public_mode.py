#!/usr/bin/env python3
"""Run one XSTAR case through a stable public execution mode."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from xstar_tools import BackendMode, run_xstar


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=[m.value for m in BackendMode], required=True)
    parser.add_argument("--run-script", required=True, help="Existing XSTAR run_xstar.sh input script.")
    parser.add_argument("--atdb", required=True, help="Path to atdb.fits.")
    parser.add_argument("--coheat", help="Optional explicit coheat.dat path.")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    result = run_xstar(
        mode=args.mode,
        run_script=Path(args.run_script),
        atdb_path=Path(args.atdb),
        coheat_path=Path(args.coheat) if args.coheat else None,
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True, default=str))
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
