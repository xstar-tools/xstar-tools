#!/usr/bin/env python3
"""Download/configure XSTAR ``atdb.fits`` and open it with xstar-atomic.

Examples
--------
Interactive download or local-path configuration::

    PYTHONPATH=src python examples/14_download_or_configure_data.py

Configure an existing file non-interactively::

    PYTHONPATH=src python examples/14_download_or_configure_data.py --set-path /path/to/atdb.fits
"""

from __future__ import annotations

import argparse

from xstar_atomic import XSTARAtomic, download_data, set_data_path, resolve_atdb_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-path", help="Existing atdb.fits path to remember")
    parser.add_argument("--no-open", action="store_true", help="Only configure/download; do not open the database")
    args = parser.parse_args()

    if args.set_path:
        data_dir = set_data_path(args.set_path)
        path = resolve_atdb_path(args.set_path, prompt=False)
        print(f"Saved data path: {data_dir}")
    else:
        path = download_data()

    print(f"atdb.fits: {path}")
    if not args.no_open:
        with XSTARAtomic(index_cache=True, index_cache_format="npz", build_index=False) as db:
            print(f"Opened: {db.fitsfile}")


if __name__ == "__main__":
    main()
