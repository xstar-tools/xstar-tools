#!/usr/bin/env python3
"""Run the complete source-faithful Python port of XSTAR ``ucalc.f90``."""

from xstar_atomic.source_port_ucalc_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
