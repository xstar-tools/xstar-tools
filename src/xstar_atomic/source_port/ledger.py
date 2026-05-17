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
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.ucalc.SourceFaithfulUCalc",
            "complete 1..102 control-flow inventory, packed-ATDB index-only execution, and existing direct ucalc probes",
            "All source branches are translated or source-defined no-ops; broader record-level numerical parity is still required for several legacy families.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/ucalc leaf routines",
            "ucalc_called_rate_helpers",
            "atomic_rates",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.ucalc_leaves",
            "source-formula unit tests plus existing collision/photoionization parity tests",
            "Some specialized legacy branches are translated but not yet directly probed across the production ATDB.",
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
            "xstar/xstarlib/src/levwk.f90",
            "levwk",
            "population_solver",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.element_equilibrium.levwk",
            "source-order level-table and LTE seed tests",
            "Broader production-ion numerical validation follows the full-zone state port.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/levwkelement.f90",
            "levwkelement",
            "population_solver",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.element_equilibrium.levwkelement",
            "exact oxygen compact-basis and shared-continuum alias tests",
            "Production population parity requires the complete plasma/radiation state.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/calc_hmc_ion.f90",
            "calc_hmc_ion",
            "population_solver",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.element_equilibrium.assemble_element_matrix",
            "four-term insertion, endpoint, context-blocker, and existing direct insertion probes",
            "Numerical completeness is limited only by the runtime context supplied to ucalc branches.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/calc_hmc_element.f90",
            "calc_hmc_element",
            "population_solver",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.element_equilibrium.solve_element_statistical_equilibrium",
            "607-row oxygen basis, full-element assembly, normalization, and synthetic direct-solve tests",
            "A production 607-row numerical run still requires source-equivalent plasma, escape, and live-radiation state.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/msolvelucy.f90",
            "msolvelucy",
            "population_solver",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.element_equilibrium.msolvelucy",
            "two-level analytic balance, superlevel iteration, normalization, positivity, and residual tests",
            "Broader direct population parity remains a production-runtime acceptance gate.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/leqt2f.f90",
            "leqt2f",
            "linear_algebra",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.linear_algebra.leqt2f",
            "source-order LU/refinement tests",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/ludcmp.f90",
            "ludcmp",
            "linear_algebra",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.linear_algebra.ludcmp",
            "source-order LU tests",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/lubksb.f90",
            "lubksb",
            "linear_algebra",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.linear_algebra.lubksb",
            "source-order back-substitution tests",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/mprove.f90",
            "mprove",
            "linear_algebra",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.linear_algebra.mprove",
            "source-order iterative-refinement tests",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/readtbl.f90",
            "readtbl",
            "atomic_database",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.atomic_database.readtbl",
            "packed-FITS synthetic source tests and existing low-level ATDB reader",
            "Full production-atdb run remains an environment-dependent validation gate.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/setptrs.f90",
            "setptrs",
            "atomic_database",
            PortStatus.TRANSLATED,
            "xstar_atomic.source_port.atomic_database.setptrs",
            "source-ordered synthetic element/ion/level/line/continuum pointer tests",
            "Full production-atdb pointer comparison remains an environment-dependent validation gate.",
        ),
        PortLedgerEntry(
            "xstar/xstarlib/src/dbwk2.f90",
            "dbwk2",
            "atomic_database",
            PortStatus.PARTIAL,
            "xstar_atomic.source_port.atomic_database.dbwk2",
            "runtime pointer-build and non-mutating report tests",
            "Interactive delete/sort/terminal editing modes are intentionally not ported because normal XSTAR setup does not call them.",
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
