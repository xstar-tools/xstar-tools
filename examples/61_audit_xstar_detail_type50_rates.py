#!/usr/bin/env python3
"""Audit XSTAR detail-state type-50 rates against source-code formulas.

This example reads an existing XSTAR run with detail products, selects He-like
triplet line rows from ``xo01_detal2.fits``, reconstructs the detail-state
continuum arrays from ``xo01_detal4.fits``, matches lines to ATDB type-50
records when possible, and evaluates the XSTAR ``calc_hmc_ion.f90`` +
``ucalc.f90`` type-50 escaped-decay/photoexcitation terms.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    here = Path(__file__).resolve()
    root = here.parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


_bootstrap_src_path()

from xstar_atomic.data import resolve_atdb_path
from xstar_atomic.xstar_detail import audit_xstar_detail_type50_rates, write_xstar_detail_type50_rate_audit


def _default_window(ion: str) -> tuple[float | None, float | None]:
    key = ion.strip().lower().replace("_", " ")
    if key == "o vii":
        return 21.4, 22.2
    if key == "c v":
        return 39.8, 41.8
    if key == "mg xi":
        return 9.0, 9.4
    if key == "ca xix":
        return 3.15, 3.25
    return None, None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit XSTAR detail-state type-50 rates for He-like triplet lines.")
    parser.add_argument("--run-dir", required=True, help="XSTAR run directory containing xo01_detal2.fits/xo01_detal4.fits")
    parser.add_argument("--ion", default="O VII", help="Ion label, e.g. 'O VII'")
    parser.add_argument("--atdb", help="Path to atdb.fits; if omitted, the configured datapath/environment is used")
    parser.add_argument("--zone-index", default="last", help="1-based detail zone index or 'last' [default]")
    parser.add_argument("--wavelength-min", type=float, help="Minimum wavelength in Angstrom; default uses common He-like triplet window")
    parser.add_argument("--wavelength-max", type=float, help="Maximum wavelength in Angstrom; default uses common He-like triplet window")
    parser.add_argument("--tolerance-A", type=float, default=0.03, help="ATDB/matrix wavelength matching tolerance in Angstrom")
    parser.add_argument("--matrix-terms-csv", help="Optional solver matrix-terms CSV for residual columns")
    parser.add_argument("--out-dir", default="xstar_detail_type50_rate_audit", help="Output directory")
    parser.add_argument("--print-summary", action="store_true", help="Print a compact summary")
    args = parser.parse_args(argv)

    wmin = args.wavelength_min
    wmax = args.wavelength_max
    if wmin is None and wmax is None:
        wmin, wmax = _default_window(args.ion)

    atdb = args.atdb
    if atdb is None:
        try:
            atdb = str(resolve_atdb_path(prompt=False))
        except Exception:
            atdb = None

    rows = audit_xstar_detail_type50_rates(
        args.run_dir,
        ion=args.ion,
        atdb=atdb,
        zone_index=args.zone_index,
        wavelength_min=wmin,
        wavelength_max=wmax,
        tolerance_A=args.tolerance_A,
        matrix_terms_csv=args.matrix_terms_csv,
    )
    paths = write_xstar_detail_type50_rate_audit(rows, args.out_dir)
    if args.print_summary:
        print("XSTAR detail-state type-50 rate audit")
        print("---------------------------------------")
        print(f"run_dir={args.run_dir}")
        print(f"ion={args.ion}")
        print(f"zone_index={args.zone_index}")
        print(f"atdb={atdb}")
        print(f"wavelength_window={wmin},{wmax}")
        print(f"n_rows={len(rows)}")
        for row in rows:
            print(
                "kind={kind} wav={wav} tau={tin}/{tout} ptmp_sum={psum} "
                "A={A} escaped={esc} photo={photo} matrix={mstat}".format(
                    kind=row.get("line_kind"),
                    wav=row.get("detail_wavelength_A"),
                    tin=row.get("tau_in"),
                    tout=row.get("tau_out"),
                    psum=row.get("ptmp_sum"),
                    A=row.get("atdb_A_s^-1"),
                    esc=row.get("ucalc_pre_swap_ans1_escaped_decay_s^-1"),
                    photo=row.get("ucalc_pre_swap_ans2_photoexcitation_s^-1"),
                    mstat=row.get("matrix_match_status"),
                )
            )
        for key, path in paths.items():
            print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
