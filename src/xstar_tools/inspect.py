"""
xstar_tools_reader_inspect.py

Read and inspect XSTAR's packed atomic database FITS file, data/atdb.fits.
This is intentionally a *low-level* reader that mirrors XSTAR's Fortran
readtbl.f90 + dread.f90 logic.

The XSTAR atdb.fits layout is not one semantic FITS table per process.  It is
four packed vector extensions:

  HDU 1: POINTERS   integer vector, length = 10 * number_of_records
  HDU 2: REALS      real*4 vector
  HDU 3: INTEGERS   integer vector
  HDU 4: CHARS      byte/character vector

Each database record has a 10-integer pointer/header block:

  p[0]  original record pointer/index
  p[1]  data type       (ltyp)
  p[2]  rate type       (lrtyp)
  p[3]  continuation flag, currently not used by XSTAR dread.f90
  p[4]  number of real values in this record
  p[5]  number of integer values in this record
  p[6]  number of character bytes in this record
  p[7]  1-based pointer into REALS
  p[8]  1-based pointer into INTEGERS
  p[9]  1-based pointer into CHARS

Usage examples:

  # Fast: reads only the POINTERS extension and prints counts
  python xstar_tools_reader_inspect.py ./xstar/data/atdb.fits --summary

  # Dump a few raw records, including reals/integers/chars
  python xstar_tools_reader_inspect.py ./xstar/data/atdb.fits --records 1 2 3 10

  # Dump first 5 records of a data type
  python xstar_tools_reader_inspect.py ./xstar/data/atdb.fits --data-type 13 --limit 5 --dump

  # Write compact inventory tables without reading the huge REALS vector
  python xstar_tools_reader_inspect.py ./xstar/data/atdb.fits --inventory atdb_inventory.csv

Dependencies:
  pip install astropy numpy
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from astropy.io import fits


# From xstarlib/src/dbwk2.f90.  These labels are useful but not a complete
# semantic parser for every data type.
RATE_TYPES: Dict[int, str] = {
    1: "ground state ionization",
    2: "level ionization/recombination",
    3: "bound-bound collision",
    4: "bound-bound radiative",
    5: "bound-free collision (level)",
    6: "total recombination",
    7: "bound-free radiative (level)",
    8: "total recombination",
    9: "2 photon decay",
    11: "element data",
    12: "ion data",
    13: "level data",
    14: "radiative superlevel->spectroscopic level",
    15: "CI total rate",
    23: "collisional superlevel->spectroscopic level",
    40: "CI from superlevels",
}

DATA_TYPES: Dict[int, str] = {
    1: "radiative recombination: Aldrovandi & Pequignot",
    2: "charge exchange H0: Kingdon & Ferland",
    3: "autoionization: Hamilton, Sarazin, Chevalier",
    4: "line data radiative: Mendoza; Raymond & Smith",
    5: "2 photon transition collisional",
    6: "level data",
    7: "dielectronic recombination: Aldrovandi & Pequignot",
    8: "dielectronic recombination: Arnaud & Raymond",
    9: "charge exchange H0 Kingdon & Ferland",
    10: "charge exchange H+ Kingdon & Ferland",
    11: "2 photon radiative",
    12: "photoionization, excited levels: hydrogenic",
    13: "element data",
    14: "ion data",
    15: "photoionization: Barfield, Koontz & Huebner",
    16: "Arnaud & Raymond collisional ionization",
    17: "collisional excitation hydrogenic: Cota",
    18: "radiative recombination hydrogenic: Cota",
    19: "photoionization: HULLAC",
    20: "charge exchange H+ Kingdon & Ferland",
    21: "PI cross section continued",
    22: "dielectronic recombination: Storey",
    23: "photoionization, excited levels: Clark",
    24: "PI cross section Clark continued",
    25: "collisional ionization: Raymond & Smith",
    26: "collisional ionization hydrogenic: Cota",
    27: "photoionization: hydrogenic",
    28: "line data collisional: Mendoza; Raymond & Smith",
    29: "collisional ionization data: scaled hydrogenic",
    30: "radiative recombination hydrogenic: Gould & Thakur",
    31: "line data no levels",
    32: "collisional ionization: Cota",
    33: "line data collisional: HULLAC",
    34: "line data radiative: Mendoza; Raymond & Smith",
    35: "photoionization: table from BKH",
    36: "photoionization, excited levels: hydrogenic no level",
    49: "OP PI cross sections for inner shells",
    50: "OP line radiative rates",
    51: "OP and CHIANTI line collisional rates",
    52: "same as 59 but rate type 7",
    53: "OP PI cross sections",
    54: "H-like Cij, Bautista, H-like ion",
    55: "hydrogenic PI cross sections, Bautista format",
    56: "tabulated collision strength, Bautista",
    57: "effective charge for collisional ionization",
    58: "H-like recombination rates, Bautista",
    59: "Verner PI cross sections",
    60: "Calloway H-like collision strength",
    61: "H-like Cij, Bautista, non-H-like ion",
    62: "Calloway H-like collision strength",
    63: "H-like Cij, Bautista, H-like ion",
    64: "hydrogenic PI cross sections, Bautista format",
    65: "effective charge for collisional ionization",
    66: "like type 69 but fine-structure data",
    67: "effective collision strengths from Keenan et al.",
    68: "He-like collision strengths by Zhang & Sampson",
    69: "Kato & Nakazaki fit to He-like collision strengths",
    70: "coefficients for photoionization cross sections of superlevels",
    71: "transition rates from superlevel to spectroscopic levels",
    72: "autoionization rates for satellite levels",
    73: "fit to collisional strengths, satellite levels, He-like ions",
    74: "delta functions added to photoionization cross sections for DR",
    75: "autoionization data for Fe XXIV satellites",
    76: "2 photon decay",
    77: "collisional rates from 71",
    78: "Auger level data",
    79: "fluorescence line data",
    80: "collisional ionization rates, ground of Fe and Ni",
    81: "Bhatia Fe XIX collision strengths",
    82: "Fe UTA radiative rates",
    83: "Fe UTA level data",
    84: "Iron K PI cross sections, spectator Auger binned",
    85: "Iron K PI cross sections, spectator Auger summed",
    86: "Iron K Auger data",
}


@dataclass
class RecordHeader:
    recno: int              # 1-based record number, as in Fortran
    raw0: int               # nptrs(1, recno), original pointer/index
    data_type: int          # nptrs(2, recno)
    rate_type: int          # nptrs(3, recno)
    continuation: int       # nptrs(4, recno)
    nreal: int              # nptrs(5, recno)
    nint: int               # nptrs(6, recno)
    nchar: int              # nptrs(7, recno)
    real_ptr: int           # nptrs(8, recno), 1-based
    int_ptr: int            # nptrs(9, recno), 1-based
    char_ptr: int           # nptrs(10, recno), 1-based

    @property
    def data_type_label(self) -> str:
        return DATA_TYPES.get(self.data_type, "")

    @property
    def rate_type_label(self) -> str:
        return RATE_TYPES.get(self.rate_type, "")


@dataclass
class RawRecord:
    header: RecordHeader
    reals: Optional[List[float]] = None
    integers: Optional[List[int]] = None
    chars: Optional[str] = None


class XSTARATDB:
    """Low-level packed-array reader for XSTAR atdb.fits."""

    def __init__(self, filename: str | Path, load_reals: bool = False):
        self.filename = Path(filename)
        self.hdul = fits.open(self.filename, memmap=True, lazy_load_hdus=True)
        self.date = self.hdul[0].header.get("DATE")
        self.creator = self.hdul[0].header.get("CREATOR")

        self.n_records = int(self.hdul["POINTERS"].header["LENGTH"])
        self.n_reals = int(self.hdul["REALS"].header["LENGTH"])
        self.n_integers = int(self.hdul["INTEGERS"].header["LENGTH"])
        self.n_chars = int(self.hdul["CHARS"].header["LENGTH"])

        # POINTERS is modest compared with REALS, so load it immediately.
        pointers = np.asarray(self.hdul["POINTERS"].data[0][0], dtype=np.int64)
        expected = 10 * self.n_records
        if pointers.size != expected:
            raise ValueError(f"POINTERS length {pointers.size} != 10 * LENGTH {expected}")
        self.pointers = pointers.reshape(self.n_records, 10)

        self._integers = None
        self._chars = None
        self._reals = None
        if load_reals:
            self.load_reals()

    def close(self) -> None:
        self.hdul.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    @property
    def integers(self) -> np.ndarray:
        if self._integers is None:
            self._integers = np.asarray(self.hdul["INTEGERS"].data[0][0], dtype=np.int64)
        return self._integers

    @property
    def chars(self) -> np.ndarray:
        if self._chars is None:
            self._chars = np.asarray(self.hdul["CHARS"].data[0][0], dtype=np.uint8)
        return self._chars

    @property
    def reals(self) -> np.ndarray:
        if self._reals is None:
            self.load_reals()
        return self._reals

    def load_reals(self) -> np.ndarray:
        # The FITS column is REAL*4.  XSTAR converts to real(8) after reading;
        # for inspection, keeping float32 is sufficient and saves memory.
        self._reals = np.asarray(self.hdul["REALS"].data[0][0], dtype=np.float32)
        return self._reals

    def header(self, recno: int) -> RecordHeader:
        if recno < 1 or recno > self.n_records:
            raise IndexError(f"recno={recno} outside 1..{self.n_records}")
        p = self.pointers[recno - 1]
        return RecordHeader(
            recno=recno,
            raw0=int(p[0]),
            data_type=int(p[1]),
            rate_type=int(p[2]),
            continuation=int(p[3]),
            nreal=int(p[4]),
            nint=int(p[5]),
            nchar=int(p[6]),
            real_ptr=int(p[7]),
            int_ptr=int(p[8]),
            char_ptr=int(p[9]),
        )

    def record(self, recno: int, include_reals: bool = True) -> RawRecord:
        """Return one raw database record, following dread.f90 indexing."""
        h = self.header(recno)

        reals = None
        if include_reals and h.nreal > 0:
            i0 = h.real_ptr - 1
            reals = self.reals[i0 : i0 + h.nreal].astype(float).tolist()

        integers = None
        if h.nint > 0:
            i0 = h.int_ptr - 1
            integers = self.integers[i0 : i0 + h.nint].astype(int).tolist()

        chars = None
        if h.nchar > 0:
            i0 = h.char_ptr - 1
            byte_values = self.chars[i0 : i0 + h.nchar]
            chars = bytes(byte_values.tolist()).decode("ascii", errors="replace")

        return RawRecord(h, reals=reals, integers=integers, chars=chars)

    def find_records(
        self,
        data_type: Optional[int] = None,
        rate_type: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[int]:
        mask = np.ones(self.n_records, dtype=bool)
        if data_type is not None:
            mask &= self.pointers[:, 1] == data_type
        if rate_type is not None:
            mask &= self.pointers[:, 2] == rate_type
        recnos = np.nonzero(mask)[0] + 1
        if limit is not None:
            recnos = recnos[:limit]
        return recnos.astype(int).tolist()

    def count_by(self, cols: Sequence[int]) -> Dict[Tuple[int, ...], int]:
        arr = self.pointers[:, list(cols)]
        keys, counts = np.unique(arr, axis=0, return_counts=True)
        return {tuple(map(int, k)): int(c) for k, c in zip(keys, counts)}

    def basic_summary(self) -> Dict[str, object]:
        by_data = self.count_by([1])
        by_rate = self.count_by([2])
        by_data_rate = self.count_by([1, 2])
        return {
            "filename": str(self.filename),
            "date": self.date,
            "creator": self.creator,
            "n_records": self.n_records,
            "n_reals": self.n_reals,
            "n_integers": self.n_integers,
            "n_chars": self.n_chars,
            "counts_by_data_type": {
                str(k[0]): {"count": v, "label": DATA_TYPES.get(k[0], "")}
                for k, v in sorted(by_data.items())
            },
            "counts_by_rate_type": {
                str(k[0]): {"count": v, "label": RATE_TYPES.get(k[0], "")}
                for k, v in sorted(by_rate.items())
            },
            "counts_by_data_rate_type": {
                f"{k[0]},{k[1]}": {
                    "count": v,
                    "data_label": DATA_TYPES.get(k[0], ""),
                    "rate_label": RATE_TYPES.get(k[1], ""),
                }
                for k, v in sorted(by_data_rate.items())
            },
        }

    def write_inventory_csv(self, path: str | Path) -> None:
        """Write one row per record.  Does not read REALS, INTEGERS, or CHARS."""
        path = Path(path)
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "recno", "raw0", "data_type", "rate_type", "continuation",
                "nreal", "nint", "nchar", "real_ptr", "int_ptr", "char_ptr",
                "data_type_label", "rate_type_label",
            ])
            for recno in range(1, self.n_records + 1):
                h = self.header(recno)
                writer.writerow([
                    h.recno, h.raw0, h.data_type, h.rate_type, h.continuation,
                    h.nreal, h.nint, h.nchar, h.real_ptr, h.int_ptr, h.char_ptr,
                    h.data_type_label, h.rate_type_label,
                ])


def short_list(x: Optional[List], n: int = 12):
    if x is None:
        return None
    if len(x) <= n:
        return x
    return x[:n] + [f"... ({len(x)-n} more)"]


def print_record(rec: RawRecord, max_values: int = 20) -> None:
    h = rec.header
    print(f"\nRecord {h.recno}")
    print("-" * 72)
    print(f"data_type={h.data_type}  {h.data_type_label}")
    print(f"rate_type={h.rate_type}  {h.rate_type_label}")
    print(f"continuation={h.continuation}")
    print(f"nreal={h.nreal} nint={h.nint} nchar={h.nchar}")
    print(f"real_ptr={h.real_ptr} int_ptr={h.int_ptr} char_ptr={h.char_ptr}")
    if rec.reals is not None:
        print(f"reals:    {short_list(rec.reals, max_values)}")
    if rec.integers is not None:
        print(f"integers: {short_list(rec.integers, max_values)}")
    if rec.chars is not None:
        print(f"chars:    {rec.chars!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Low-level inspector for XSTAR atdb.fits")
    ap.add_argument("fitsfile", help="Path to atdb.fits")
    ap.add_argument("--summary", action="store_true", help="Print JSON summary")
    ap.add_argument("--summary-json", help="Write JSON summary to this path")
    ap.add_argument("--inventory", help="Write compact one-row-per-record CSV inventory")
    ap.add_argument("--records", nargs="*", type=int, default=None, help="Record numbers to dump")
    ap.add_argument("--data-type", type=int, help="Select records by data type")
    ap.add_argument("--rate-type", type=int, help="Select records by rate type")
    ap.add_argument("--limit", type=int, default=10, help="Limit selected records; default 10")
    ap.add_argument("--dump", action="store_true", help="Dump selected records")
    ap.add_argument("--no-reals", action="store_true", help="Do not read/dump real values")
    ap.add_argument("--max-values", type=int, default=20, help="Max values shown from each array")
    args = ap.parse_args()

    with XSTARATDB(args.fitsfile, load_reals=False) as db:
        if args.summary or args.summary_json:
            summary = db.basic_summary()
            if args.summary:
                print(json.dumps(summary, indent=2))
            if args.summary_json:
                Path(args.summary_json).write_text(json.dumps(summary, indent=2))
                print(f"Wrote {args.summary_json}")

        if args.inventory:
            db.write_inventory_csv(args.inventory)
            print(f"Wrote {args.inventory}")

        selected: List[int] = []
        if args.records is not None and len(args.records) > 0:
            selected.extend(args.records)
        if args.data_type is not None or args.rate_type is not None:
            selected.extend(db.find_records(args.data_type, args.rate_type, args.limit))

        if args.dump or selected:
            if not selected:
                selected = list(range(1, min(db.n_records, args.limit) + 1))
            for recno in selected:
                rec = db.record(recno, include_reals=not args.no_reals)
                print_record(rec, max_values=args.max_values)

        if not (args.summary or args.summary_json or args.inventory or selected or args.dump):
            # Default behavior: cheap summary, no huge REALS load.
            print(json.dumps(db.basic_summary(), indent=2))


if __name__ == "__main__":
    main()
