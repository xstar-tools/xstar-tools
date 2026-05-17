"""Machine-readable translation ledger for the source-faithful XSTAR port."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence
import csv
import json


class PortStatus(str, Enum):
    UNPORTED = "unported"
    SCAFFOLD = "scaffold"
    PARTIAL = "partial"
    TRANSLATED = "translated"
    VALIDATED = "validated"


@dataclass(frozen=True)
class PortLedgerEntry:
    source_file: str
    routine: str
    stage: str
    status: PortStatus
    python_target: str
    validation_oracle: str = ""
    limitations: str = ""


@dataclass
class XSTARPortLedger:
    entries: List[PortLedgerEntry]

    def status_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in self.entries:
            counts[entry.status.value] = counts.get(entry.status.value, 0) + 1
        return counts

    def upsert(self, entry: PortLedgerEntry) -> None:
        for i, current in enumerate(self.entries):
            if (
                current.source_file == entry.source_file
                and current.routine == entry.routine
            ):
                self.entries[i] = entry
                return
        self.entries.append(entry)

    def write(self, out_dir: str) -> Dict[str, str]:
        output = Path(out_dir)
        output.mkdir(parents=True, exist_ok=True)
        csv_path = output / "xstar_python_port_ledger.csv"
        json_path = output / "xstar_python_port_ledger.json"

        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "source_file",
                    "routine",
                    "stage",
                    "status",
                    "python_target",
                    "validation_oracle",
                    "limitations",
                ],
            )
            writer.writeheader()
            for entry in sorted(
                self.entries, key=lambda e: (e.stage, e.source_file, e.routine)
            ):
                row = asdict(entry)
                row["status"] = entry.status.value
                writer.writerow(row)

        payload = {
            "status_counts": self.status_counts(),
            "entries": [
                {**asdict(entry), "status": entry.status.value}
                for entry in self.entries
            ],
        }
        json_path.write_text(json.dumps(payload, indent=2) + "\n")
        return {"csv": str(csv_path), "json": str(json_path)}


def default_port_ledger() -> XSTARPortLedger:
    """Return the initial ledger at the v0.4 source-port pivot.

    Status is deliberately conservative.  A translated atomic kernel is not
    marked as a translated full source file when surrounding branches or state
    coupling remain incomplete.
    """
    entries = [
        PortLedgerEntry(
            "xstar/xstarlib/src/ucalc.f90",
            "ucalc",
            "atomic_rates",
            PortStatus.PARTIAL,
            "xstar_atomic.source_port.ucalc_dispatch.UCalcDispatcher",
            "direct ucalc and matrix probes",
            "Only data types with registered native branches are executable.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/phint53.f90",
            "phint53",
            "atomic_rates",
            PortStatus.VALIDATED,
            "xstar_atomic.rates_type53.evaluate_phint53_exact",
            "standalone original-Fortran comparison",
            "phint53hunt, opacity, and RRC emissivity remain separate.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/calt71.f90",
            "calt71",
            "atomic_rates",
            PortStatus.VALIDATED,
            "xstar_atomic.rates_type71.evaluate_calt71_record",
            "direct ucalc and matrix probes",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/upsil.f90",
            "upsil",
            "atomic_rates",
            PortStatus.VALIDATED,
            "xstar_atomic.rates_type51.evaluate_type51_ucalc_record",
            "direct ucalc and matrix probes",
            "Validated through type-51 five-point records.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/upsiln.f90",
            "upsiln",
            "atomic_rates",
            PortStatus.PARTIAL,
            "xstar_atomic.rates_type51.evaluate_type51_ucalc_record",
            "focused unit tests",
            "Needs direct nine-point XSTAR record coverage.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/calc_hmc_ion.f90",
            "calc_hmc_ion",
            "population_solver",
            PortStatus.PARTIAL,
            "xstar_atomic source-aligned matrix-term builders",
            "direct calc_hmc_ion insertion probes",
            "No complete translated ion loop yet.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/calc_hmc_element.f90",
            "calc_hmc_element",
            "population_solver",
            PortStatus.SCAFFOLD,
            "xstar_atomic.source_port.driver.XSTARPythonDriver",
            "607-row basis and six-row conditional probes",
            "Full element assembly and solve are not translated.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/msolvelucy.f90",
            "msolvelucy",
            "population_solver",
            PortStatus.PARTIAL,
            "xstar_atomic existing Lucy solver helpers",
            "selected solver tests",
            "Full source-order superlevel iteration is not translated.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/setptrs.f90",
            "setptrs",
            "atomic_database",
            PortStatus.SCAFFOLD,
            "xstar_atomic.source_port.state.XSTARAtomicState",
            "ATDB extraction and pointer audits",
            "Complete pointer hierarchy translation is the first source-port milestone.",
        ),
        PortLedgerEntry(
            "xstar/src/xstar/xstar.f90",
            "xstar",
            "driver",
            PortStatus.SCAFFOLD,
            "xstar_atomic.source_port.driver.XSTARPythonDriver",
            "",
            "Outer zone/pass execution is not translated.",
        ),
    ]
    return XSTARPortLedger(entries)
