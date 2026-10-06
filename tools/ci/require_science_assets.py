#!/usr/bin/env python3
"""Resolve canonical science-CI assets on a labeled self-hosted runner."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

DEFAULTS = {
    "suite": "/opt/xstar-ci/original_xstar_benchmark_run.tar.gz",
    "data": "/opt/xstar-ci/data",
    "fortran": "/opt/xstar-ci/original_xstar.tar.gz",
    "cpp44": "/opt/xstar-ci/v064812344_all62_three_mode.tar.gz",
}
ENV = {
    "suite": "XSTAR_TOOLS_CI_SUITE_ARCHIVE",
    "data": "XSTAR_TOOLS_CI_DATA_DIR",
    "fortran": "XSTAR_TOOLS_CI_FORTRAN_REFERENCE",
    "cpp44": "XSTAR_TOOLS_CI_CPP44_REFERENCE",
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--github-output")
    p.add_argument("--need-cpp44", action="store_true")
    args = p.parse_args(argv)
    values = {key: Path(os.environ.get(ENV[key], DEFAULTS[key])).expanduser().resolve() for key in DEFAULTS}
    required = ["suite", "data", "fortran"] + (["cpp44"] if args.need_cpp44 else [])
    missing = [f"{key}={values[key]}" for key in required if not values[key].exists()]
    if missing:
        print("CI_SCIENCE_ASSETS=REJECT")
        for item in missing:
            print("CI_SCIENCE_ASSET_MISSING=" + item)
        return 1
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    print("CI_SCIENCE_ASSETS=ACCEPT")
    for key in required:
        print(f"CI_SCIENCE_ASSET_{key.upper()}={values[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
