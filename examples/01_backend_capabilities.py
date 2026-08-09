#!/usr/bin/env python3
"""Print stable xstar-tools execution modes and backend capabilities."""
from __future__ import annotations

import argparse
import json

from xstar_tools.backends import available, describe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the full machine-readable capability record.")
    args = parser.parse_args()
    if args.json:
        print(json.dumps(describe(), indent=2, sort_keys=True))
    else:
        for mode, ready in available().items():
            print(f"{mode:11s} {'available' if ready else 'unavailable'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
