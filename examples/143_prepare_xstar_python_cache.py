#!/usr/bin/env python3
"""Build/validate vectorized NPZ caches used by the physical Python runner."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from xstar_atomic import prepare_xstar_python_cache


def _progress(event: str, details: dict[str, object]) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    payload = " ".join(f"{key}={value}" for key, value in sorted(details.items()))
    print(f"[{stamp}] {event}" + (f" {payload}" if payload else ""), flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atdb", required=True)
    parser.add_argument("--cache-dir")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--summary-json")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = prepare_xstar_python_cache(
        atdb_path=args.atdb,
        cache_dir=args.cache_dir,
        rebuild_cache=args.rebuild_cache,
        progress_callback=_progress if args.progress else None,
    )
    summary = result.as_dict()
    if args.summary_json:
        path = Path(args.summary_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.print_summary:
        print("XSTAR Python vectorized cache")
        print("-----------------------------")
        for key in (
            "ready", "atdb_path", "pointer_cache_path", "pointer_cache_status",
            "metadata_cache_path", "metadata_cache_status", "n_records", "n_ions",
            "n_levels", "n_lines", "n_continua", "elapsed_seconds",
        ):
            print(f"{key}={summary[key]}")
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
