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
            "port_version": PORT_LEDGER_VERSION,
            "completed_milestones": list(COMPLETED_SOURCE_PORT_MILESTONES),
            "current_milestone": 5,
            "next_coherent_target": NEXT_COHERENT_SOURCE_PORT_TARGET,
            "status_counts": self.status_counts(),
            "entries": [
                {**asdict(entry), "status": entry.status.value}
                for entry in self.entries
            ],
        }
        json_path.write_text(json.dumps(payload, indent=2) + "\n")
        return {"csv": str(csv_path), "json": str(json_path)}


PORT_LEDGER_VERSION = "v0.4.71"
COMPLETED_SOURCE_PORT_MILESTONES = (1, 2, 3, 4)
NEXT_COHERENT_SOURCE_PORT_TARGET = (
    "build the physical input-to-state Python runner for the canonical four-case "
    "all-ATDB benchmark, then require strict detail/final-output parity before "
    "expanding to the complete 62-case suite or considering a C++ backend"
)


def default_port_ledger() -> XSTARPortLedger:
    """Return the source-port ledger through the bounded radial-shell release.

    ``validated`` means validated for the stated oracle and scope.  It does not
    imply physical all-ATDB standard-benchmark parity.  The bounded radial
    caller, saved/pass state, detail/final FITS products, and the default
    legacy ``pprint`` products are accepted.  Physical all-ATDB standard
    benchmark output parity remains the open acceptance gate.
    """
    E = PortLedgerEntry
    V, T, P, S, U = (
        PortStatus.VALIDATED,
        PortStatus.TRANSLATED,
        PortStatus.PARTIAL,
        PortStatus.SCAFFOLD,
        PortStatus.UNPORTED,
    )
    entries = [
        E("xstar/xstarlib/src/readtbl.f90", "readtbl", "milestone1_atomic_database", V,
          "xstar_atomic.source_port.atomic_database.readtbl",
          "production atdb.fits packed-vector loading and synthetic FITS tests",
          "Validated for normal noninteractive XSTAR database initialization."),
        E("xstar/xstarlib/src/setptrs.f90", "setptrs", "milestone1_atomic_database", V,
          "xstar_atomic.source_port.atomic_database.setptrs",
          "complete production pointer cache, ion/level/line/continuum traversal",
          "Interactive database editing is outside the production source-port path."),
        E("xstar/xstarlib/src/dbwk2.f90", "dbwk2", "milestone1_atomic_database", P,
          "xstar_atomic.source_port.atomic_database.dbwk2",
          "normal pointer-build/report path",
          "Interactive delete/sort/terminal editing modes are intentionally deferred."),
        E("xstar/xstarlib/src/ucalc.f90", "ucalc", "milestone2_atomic_rates", V,
          "xstar_atomic.source_port.ucalc.SourceFaithfulUCalc",
          "complete labels 1..102, solve-call-219 record/matrix probes, frozen oxygen benchmark",
          "All branches execute or preserve source no-op behavior; minor strict legacy-family closure is tracked separately."),
        E("xstar/xstarlib/src/ucalc leaf routines", "ucalc_called_rate_helpers", "milestone2_atomic_rates", V,
          "xstar_atomic.source_port.ucalc_leaves and rate modules",
          "source-formula tests and production type 50/53/56/57/63/71/74/95/99 parity",
          "Validation scope is the production ATDB families exercised by the frozen oxygen case plus focused unit cases."),
        E("xstar/xstarlib/src/phint53.f90", "phint53", "milestone2_atomic_rates", V,
          "xstar_atomic.rates_type53.evaluate_phint53_exact",
          "original-Fortran comparisons and complete oxygen type-53 matrix parity"),
        E("xstar/xstarlib/src/phint53hunt.f90", "phint53hunt", "milestone2_atomic_rates", V,
          "xstar_atomic.source_port.ucalc._phint53hunt",
          "type-99 solve-call-219 topology/rate parity"),
        E("xstar/xstarlib/src/hunt3.f90", "hunt3", "milestone2_atomic_rates", V,
          "xstar_atomic.source_port.compton.hunt3_one_based and xstar_atomic.collisions.interp_type56_upsilon",
          "type-56 edge extrapolation plus direct original-Fortran comp2/cmpfnc boundary tests",
          "The generic ascending-grid path is translated for cmpfnc; the historical collision helper remains specialized to label 56."),
        E("xstar/xstarlib/src/upsil.f90", "upsil", "milestone2_atomic_rates", V,
          "xstar_atomic.rates_type51.evaluate_type51_ucalc_record",
          "direct type-51 ucalc and matrix probes"),
        E("xstar/xstarlib/src/upsiln.f90", "upsiln", "milestone2_atomic_rates", P,
          "xstar_atomic.rates_type51.evaluate_type51_ucalc_record",
          "focused generalized Burgess-Tully tests",
          "Needs broader direct production coverage of nine-point records."),
        E("xstar/xstarlib/src/levwk.f90", "levwk", "milestone3_element_equilibrium", V,
          "xstar_atomic.source_port.element_equilibrium.levwk",
          "solve-call-219 LTE seeds and level ordering"),
        E("xstar/xstarlib/src/levwkelement.f90", "levwkelement", "milestone3_element_equilibrium", V,
          "xstar_atomic.source_port.element_equilibrium.levwkelement",
          "frozen 607-row oxygen compact basis, 13 superlevels, five shared aliases"),
        E("xstar/xstarlib/src/calc_hmc_ion.f90", "calc_hmc_ion", "milestone3_element_equilibrium", V,
          "xstar_atomic.source_port.element_equilibrium.assemble_element_matrix",
          "zero blockers, 26,920 native terms, endpoint clamps zero, record-level probes",
          "Strict parity for several dynamically weak legacy families remains in the deferred ledger."),
        E("xstar/xstarlib/src/calc_hmc_element.f90", "calc_hmc_element", "milestone3_element_equilibrium", V,
          "xstar_atomic.source_port.element_equilibrium.solve_element_statistical_equilibrium",
          "frozen O III-O VIII 607-row solve and all-population acceptance"),
        E("xstar/xstarlib/src/msolvelucy.f90", "msolvelucy", "milestone3_element_equilibrium", V,
          "xstar_atomic.source_port.element_equilibrium.msolvelucy",
          "native solve convergence, 607/607 population parity, source-order xtot semantics, and synchronized final-iteration snapshot tooling",
          "The returned source xtot is formed from the start vector of the final Lucy outer iteration and excludes the final compact row, exactly as in the Fortran routine."),
        E("xstar/xstarlib/src/leqt2f.f90", "leqt2f", "milestone3_linear_algebra", V,
          "xstar_atomic.source_port.linear_algebra.leqt2f", "source-order LU/refinement tests"),
        E("xstar/xstarlib/src/ludcmp.f90", "ludcmp", "milestone3_linear_algebra", V,
          "xstar_atomic.source_port.linear_algebra.ludcmp", "source-order LU tests"),
        E("xstar/xstarlib/src/lubksb.f90", "lubksb", "milestone3_linear_algebra", V,
          "xstar_atomic.source_port.linear_algebra.lubksb", "source-order back-substitution tests"),
        E("xstar/xstarlib/src/mprove.f90", "mprove", "milestone3_linear_algebra", V,
          "xstar_atomic.source_port.linear_algebra.mprove", "source-order iterative-refinement tests"),
        E("xstar/xstarlib/src/calc_ion_rates.f90", "calc_ion_rates", "milestone4_local_zone", V,
          "xstar_atomic.source_port.ion_balance.calc_ion_rates",
          "bounded calc_hmc_all call-73 pre-matrix probe: all oxygen pirt/rrrt rows within tolerance",
          "Validated for the captured oxygen fixed-state benchmark; broader all-element coverage remains future work."),
        E("xstar/xstarlib/src/istruc.f90", "istruc", "milestone4_local_zone", V,
          "xstar_atomic.source_port.ion_balance.istruc",
          "bounded call-73 oxygen ion fractions plus exact mml/mmu/critf selection",
          "Validated for the captured oxygen fixed-state benchmark."),
        E("xstar/xstarlib/src/ioneqm.f90", "ioneqm", "milestone4_local_zone", V,
          "xstar_atomic.source_port.ion_balance.ioneqm",
          "bounded call-73 oxygen preliminary ion fractions and source-ratio regression tests",
          "Validated through istruc for the captured oxygen fixed-state benchmark."),
        E("xstar/xstarlib/src/cmpfnc.f90", "cmpfnc", "milestone4_local_zone", V,
          "xstar_atomic.source_port.compton.cmpfnc",
          "direct original-Fortran interpolation comparisons and accepted call-73 same-call probe",
          "Accepted in the frozen v0.4.39 Compton regression."),
        E("xstar/xstarlib/src/comp2.f90", "comp2", "milestone4_local_zone", V,
          "xstar_atomic.source_port.compton.comp2",
          "direct original-Fortran comparison and exact call-73 cmp1/cmp2/htcomp/clcomp parity",
          "Accepted in the frozen v0.4.39 Compton regression."),
        E("xstar/xstarlib/src/freef.f90", "freef", "milestone4_local_zone", V,
          "xstar_atomic.source_port.free_free.freef",
          "direct original-Fortran comparison and exact call-73 opacity-increment/mutation/htfreef parity",
          "Accepted in the frozen v0.4.40 freef regression."),
        E("xstar/xstarlib/src/bremem.f90", "bremem", "milestone4_local_zone", V,
          "xstar_atomic.source_port.bremsstrahlung.bremem",
          "direct original-Fortran comparison and exact call-73 brcems reset/emissivity and opacity-preservation parity",
          "Accepted in the frozen v0.4.41 bremem regression."),
        E("xstar/xstarlib/src/heatf.f90", "heatf", "milestone4_local_zone", V,
          "xstar_atomic.source_port.thermal_balance.heatf",
          "direct original-Fortran comparison plus exact accepted call-73 thermal accumulation parity",
          "Accepted in the frozen v0.4.42 heatf regression."),
        E("xstar/xstarlib/src/calc_hmc_all.f90", "calc_hmc_all", "milestone4_local_zone", T,
          "xstar_atomic.source_port.local_zone.calc_hmc_all",
          "call-73 pre-matrix/runtime parity, source-ordinal npilev mapping, separated second-pass pirt/rrrt, probe-aware abundance, exact same-call xileve input capture/replay, complete type-50/type-71 ans3/ans4 energy channels, corrected type-72 packed endpoints, record-level rate-7 cj2 diagnosis, exact mutable-leveltemp reads for types 49/53/99, XSTAR thermal-family probes, exact same-call aj1/aj2/cj/cj2 comparison, and synchronized final msolvelucy matrix/x/xo capture",
          "The accepted v0.4.34 oxygen call-73 result remains mandatory. v0.4.36 translated native H I type-62/calt6062 records 488-491 and established the H/He/O gate. v0.4.37 closed the literal type-77 sub-eV source-zero gate. v0.4.38 separates the returned final-x ion fractions (`xii`/`xiin`) from the final-outer-start `xtot` diagnostics, closing the last H I global-ion export discrepancy. v0.4.39 accepted `comp2 -> cmpfnc -> hunt3` plus the global `coheat.dat` state. v0.4.40 accepted `freef`. v0.4.41 accepted `bremem`. v0.4.42 accepted `heatf`. v0.4.43 integrates the complete fixed-state source sequence and adds a final same-call thermal/charge return-state gate. v0.4.44 separates explicit pre-continuum totals from final post-heatf totals and corrects the same-call validator; the existing v0.4.43 probe products are reused for acceptance."),
        E("xstar/xstarlib/src/dsec.f90", "dsec", "milestone4_local_zone", T,
          "xstar_atomic.source_port.dsec.dsec",
          "exact source-order nested charge/thermal control flow, mutable population/leveltemp replay, synthetic branch tests, and trajectory-probe tooling",
          "The Fortran control algorithm is translated in v0.4.45. v0.4.46 adds the turnkey physical calc_hmc_all-backed runner. v0.4.47 corrects population-state ownership by carrying global xilevg and remapping it after each dynamic istruc basis selection. v0.4.48 correlates every dsec evaluation with its exact calc_hmc_all call, captures the matching input state, separates the post-dsec reference, records thermal decomposition, and adds fast prefix validation. v0.4.49 permits the source-valid zero first seed only for the correlated first call, and v0.4.50 repairs progress reporting. v0.4.51 captures and diagnoses the evaluation-2 entry mismatch. v0.4.52 makes dense native-index xilevg/bilevg/rnisg arrays authoritative, replays complete inactive-ion and continuum/next-ground alias writeback with the two source bilevg floors, resets leveltemp to the correlated entry state between calc_hmc_all calls, and adds the four-mode causality scan. The physical scan proved those state corrections do not cause the evaluation-2 primary cooling discrepancy. v0.4.53 adds an exact XSTAR-seeded evaluation-2 replay and per-element thermal/solver decomposition. v0.4.54 localizes the first failure to the terminal compact solver row. v0.4.55 reproduces the literal source write `x(ipmat2+1)=0.` before `msolvelucy`; the user-side causality run reduces the evaluation-2 cooling and hmctot discrepancies to about 5.7e-7 and 1.3e-6. v0.4.56 accepts the natural four-evaluation source branch/thermal prefix while keeping strict runtime and transition-array roundoff visible. v0.4.57 adds the unrestricted all-evaluation convergence and post-dsec fixed-state acceptance wrapper. The user-side run converges in the same 33 evaluations and follows the same residual-sign branch sequence; one near-zero normalized hmctot row fails only relative tolerance while all underlying heating/cooling components pass. v0.4.58 adds exact post-dsec call-entry replay that separates converged-root roundoff from fixed-state calc_hmc_all physics. v0.4.59 verifies the exact heatf residual expression and literal dsec `abs(hmctot)<=1.e-4` convergence decision, accepts the final local-zone source semantics while preserving strict residual failure diagnostics, and unlocks bremsmap. v0.4.60 translates and directly validates bremsmap -> nbinc -> huntf, including caller-owned bremsint tail semantics. v0.4.61 translates and validates calc_emisab_all -> calc_emisab_element -> calc_emisab_ion; calc_emis_all is next."),
        E("xstar/xstarlib/src/bremsmap.f90", "bremsmap", "milestone4_local_zone", V,
          "xstar_atomic.source_port.radiation.bremsmap",
          "direct compilation of the original bremsmap/nbinc/huntf source against two frozen synthetic caller-owned states",
          "Accepted in v0.4.60. The translation preserves the reduced nbinc search extent, default-real constants, partial bremsam mutation, descending ncn2m bremsint loop, and incoming bremsint(ncn2m+1) tail boundary."),
        E("xstar/xstarlib/src/calc_emisab_all.f90", "calc_emisab_all", "milestone4_local_zone", V,
          "xstar_atomic.source_port.emissivity.calc_emisab_all",
          "bounded source-order synthetic parity for density branches, output resets, carried continuum side effects, compact continuum aliases, inactive-ion offsets, and rate types 4/7/9/14",
          "Accepted in v0.4.61 together with calc_emisab_element and calc_emisab_ion. The translation preserves all-ion compact mapping before stage filtering, source-order shared continuum aliases, mutable leveltemp writes only for active ions, one-based line/RRC pointers, ucalc continuum-array side effects, and the distinct source ownership of reset versus carried arrays."),
        E("xstar/xstarlib/src/calc_emis_all.f90", "calc_emis_all", "milestone4_local_zone", V,
          "xstar_atomic.source_port.emergent_emissivity.calc_emis_all",
          "bounded source-order synthetic parity for rlbin ranking, calc_emis_element/calc_emis_ion traversal, rate-type 7/9/42 behavior, fline/flinel ownership, Thomson reset, freef, and bremem",
          "Accepted in v0.4.62. The translation preserves ranking from precomputed calc_emisab arrays before continuum reset, the source rank-limit quirk, all-ion compact aliases and inactive offsets, rate-type-9 double ucalc execution, retained kkkl reuse by rate types 9/42, caller-owned fline/flinel, and final freef/bremem source slots. v0.4.63 composes this routine with calc_emisab_all on one full-grid caller workspace while preserving the reduced-grid active range."),
        E("xstar/xstarlib/src/xstarcalc.f90", "xstarcalc", "milestone4_local_zone", V,
          "xstar_atomic.source_port.xstarcalc.run_complete_local_xstarcalc",
          "bounded complete-local assembly validates literal bremsmap -> optional dsec -> final calc_hmc_all -> calc_emisab_all -> calc_emis_all order, shared array ownership, nlimdt skip, lpri save/restore, and final nry",
          "Accepted in v0.4.63 for the complete local-zone caller contract. Physical all-ATDB end-to-end emissivity parity remains part of later radial-zone integration."),
        E("xstar/xstarlib/src/step.f90", "step", "milestone5_transfer", V,
          "xstar_atomic.source_port.radial_transfer.step",
          "direct compilation of the unmodified original routine plus bounded first-pass zone-2 call-order validation",
          "Accepted in v0.4.64. Preserves the overwritten first tst expression, opacity floor, energy/depth/flux gates, and final remaining-column limit."),
        E("xstar/xstarlib/src/trnfrc.f90", "trnfrc", "milestone5_transfer", V,
          "xstar_atomic.source_port.radial_transfer.trnfrc",
          "direct original-Fortran outward/inward continuum references and active-range/tail ownership validation",
          "Accepted in v0.4.64. Preserves source direction semantics, two cleared high bins, descending integration, default-real constants, and caller-owned rows above ncn2."),
        E("xstar/xstarlib/src/stpcut.f90", "stpcut", "milestone5_transfer", V,
          "xstar_atomic.source_port.radial_transfer.stpcut",
          "direct original-Fortran continuum, line, and RRC optical-depth accumulation reference",
          "Accepted in v0.4.64. Mutates only the source-selected direction row and active ncn2/nlsvn/ncsvn ranges."),
        E("xstar/xstarlib/src/trnfrn.f90", "trnfrn", "milestone5_transfer", V,
          "xstar_atomic.source_port.radial_transfer.trnfrn",
          "direct original-Fortran active-range transfer-state commit and caller-tail preservation",
          "Accepted in v0.4.64 for continuum, line, and RRC old-state arrays."),
        E("xstar/xstarlib/src/heatt.f90", "heatt", "milestone5_transfer", V,
          "xstar_atomic.source_port.heatt.heatt",
          "direct compilation of the unmodified original routine for continuum, line, RRC, and leveltemp outputs plus bounded radial composition",
          "Accepted in v0.4.65. Preserves active-range caller ownership, old-array luminosity construction, the stale final-continuum optp2 value consumed by the first inward line term, source-order packed RRC traversal, and partial leveltemp overwrite. The source-uninitialized local cmp1/cmp2 Compton diagnostic is reported explicitly rather than invented."),
        E("xstar/xstarlib/src/gsmooth.f90", "gsmooth", "milestone5_transfer", V,
          "xstar_atomic.source_port.gsmooth.gsmooth",
          "direct compilation of the unmodified gsmooth/gsmooth2 routines plus nonzero-turbulence radial composition",
          "Accepted in v0.4.66. Preserves the literal brcems -> rccemis(1) -> rccemis(2) -> opakc helper order, bins 1-2 ownership, the 20-keV pass-through, source stopping tests, and caller-owned tails."),
        E("xstar/xstarlib/src/unsavd.f90", "unsavd", "milestone5_transfer", V,
          "xstar_atomic.source_port.saved_radial_state.unsavd",
          "direct compilation of unmodified unsavd plus caller-owned REAL(4) shell/pass snapshots and three alternating radial passes",
          "Accepted in v0.4.67. Restores all saved scalar/population/line/RRC/continuum state, only the direction-owned optical-depth row, and preserves the source-local zrems temporary semantics. The in-memory state reproduces savd FITS REAL(4) persistence and one-based HDU insertion/shift order without claiming an output writer."),
        E("xstar/src/xstar/xstar.f90", "tabulated_density_and_pass_control", "milestone5_transfer", V,
          "xstar_atomic.source_port.radial_control",
          "compiled literal inline density.dat fragment plus bounded source-loop and fixed requested-pass contract validation",
          "Accepted in v0.4.68. Preserves the initial pre-pass density read, sequential post-shell reads, retained rnew/dennew values at EOF, post-update-density column accumulation, radius-error stop, literal first/later shell predicates, (-1)**kk directions, numrec<=0 forcing npass=1, and the absence of an adaptive pass-convergence test."),
        E("xstar/xstarlib/src/fheader.f90", "fheader", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers._primary_hdu",
          "bounded FITS primary-header schema and checksum validation",
          "Accepted in v0.4.69 for CREATOR, MODEL, ATDATA, primary/parameter/data HDU ordering, and checksums. The legacy source BITPIX declaration is not claimed byte-identical because Astropy emits a standards-compliant empty primary HDU."),
        E("xstar/xstarlib/src/fparmlist.f90", "fparmlist", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.build_parameter_table",
          "bounded source schema, 1I parameter index, REAL(4) values, strings, and FITS layout",
          "Accepted in v0.4.69 for the caller-owned parameter table used by detail and final products."),
        E("xstar/xstarlib/src/savd.f90", "savd", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.append_detail_output_from_state",
          "bounded radial composition with per-pass caller-owned stores and source HDU insertion order",
          "Accepted in v0.4.69. Preserves fstepr -> fstepr2 -> fstepr3 -> fstepr4 order and pass-specific fnappend filenames."),
        E("xstar/xstarlib/src/fstepr.f90", "fstepr", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.build_detail_level_table",
          "direct original-Fortran row selection plus REAL(4) schema validation",
          "Accepted in v0.4.69 for populated-level detail rows and shell header values."),
        E("xstar/xstarlib/src/fstepr2.f90", "fstepr2", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.build_detail_line_table",
          "direct original-Fortran active-line row selection and schema validation",
          "Accepted in v0.4.69. The source-undefined no-active-line path fails explicitly rather than inventing an uninitialized row."),
        E("xstar/xstarlib/src/fstepr3.f90", "fstepr3", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.build_detail_rrc_table",
          "direct original-Fortran RRC row selection and schema validation",
          "Accepted in v0.4.69 for active type-7 RRC detail rows."),
        E("xstar/xstarlib/src/fstepr4.f90", "fstepr4", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.build_detail_continuum_table",
          "direct original-Fortran continuum columns and REAL(4) persistence",
          "Accepted in v0.4.69 for the active continuum range and shell header contract."),
        E("xstar/xstarlib/src/voigte.f90", "voigte", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.voigte",
          "direct compilation of unmodified original Fortran at three profile points",
          "Accepted in v0.4.69 as the line-profile helper used by binemis."),
        E("xstar/xstarlib/src/binemis.f90", "binemis", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.build_binemis_spectrum",
          "direct compilation of unmodified binemis/rlbin/nbinc/huntf/voigte/drd for a strong-line fixture",
          "Accepted in v0.4.69 for source ranking, profile integration/rebinning, active-range mutation, and caller-owned tails; the compiled comparison uses a 5e-7 bound for source-visible default-real/grid rounding."),
        E("xstar/xstarlib/src/writespectra.f90", "writespectra", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.build_final_spectrum_table",
          "direct source schema and final spectrum construction validation",
          "Accepted in v0.4.69. Preserves the source quirk that defines six descriptors but writes tfields=5, dropping the scattered column."),
        E("xstar/xstarlib/src/writespectra2.f90", "writespectra2", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.build_final_line_table",
          "direct original-Fortran line selection/ranking fragment and 600-row limit",
          "Accepted in v0.4.69 for the strongest final line table."),
        E("xstar/xstarlib/src/writespectra3.f90", "writespectra3", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.build_final_continuum_table",
          "direct compiled literal transmitted-continuum loop and column schema",
          "Accepted in v0.4.69 for incident, transmitted, inward, and outward continuum columns."),
        E("xstar/xstarlib/src/writespectra4.f90", "writespectra4", "milestone5_outputs", V,
          "xstar_atomic.source_port.output_writers.build_final_rrc_table",
          "direct original-Fortran RRC selection fragment and schema validation",
          "Accepted in v0.4.69 for final RRC rows when either direction exceeds the source floor."),
        E("xstar/xstarlib/src/pprint.f90", "pprint", "milestone5_outputs", V,
          "xstar_atomic.source_port.pprint_legacy",
          "direct compiled source-format/equation references, bounded radial composition, and FITS/text product validation",
          "Accepted in v0.4.70 for the source-default lpri=0 path: pprint(3), pprint(2), per-pass pprint(17), per-shell/final-pass pprint(9/12), and final pprint(22/11). Writes xout_step.log and xout_abund1.fits with source REAL(4) table persistence. Verbose lpri>0 diagnostic report branches fail explicitly."),
        E("xstar/src/xstar/xstar.f90", "physical_output_parity", "milestone5_outputs", P,
          "xstar_atomic.source_port.physical_output_parity",
          "schema/value comparator self-test on all legacy/detail/final products",
          "v0.4.70 provides the independent XSTAR-versus-Python output comparator. Physical all-ATDB parity is not claimed until both standard benchmark directories are supplied and all files pass."),
        E("benchmark input suite", "physical_benchmark_suite", "milestone5_outputs", P,
          "xstar_atomic.source_port.physical_benchmark_suite",
          "safe run-script parsing, 62-case inventory, canonical four-case selection, original-run orchestration, and strict ten-product case comparison",
          "v0.4.71 turns the supplied original_xstar run tree into a reproducible benchmark manifest and strict parity gate. The archive omits physical products and the general Python input-to-state runner remains open, so no physical all-ATDB parity is claimed."),
        E("xstar/src/xstar/xstar.f90", "xstar", "driver", S,
          "xstar_atomic.source_port.driver.XSTARPythonDriver",
          "source-level xstarcalc and zone call-order plans with explicit untranslated-routine failure",
          "Milestones 1-4 are complete. The accepted oxygen and H/He/O pre-continuum gates are frozen. v0.4.39 accepted the relativistic Compton subsystem and v0.4.40 accepted `freef`. v0.4.41 accepted `bremem`. v0.4.42 accepted `heatf`. v0.4.43 adds complete fixed-state calc_hmc_all thermal/charge closure. v0.4.44 corrects pre/post-continuum state ownership without changing physics or XSTAR probes. v0.4.45 translates the exact stateful dsec control algorithm and trajectory tooling. v0.4.46 adds the physical example-119 runner with per-trial continuum reconstruction and same-process acceptance products. v0.4.47 replaces invalid compact-vector replay with source-faithful global xilevg carry/remapping across changing dsec bases. v0.4.48 adds call correlation, exact matching input-state capture, distinct input/post-dsec references, per-evaluation thermal decomposition, and fast prefix mode. v0.4.51 diagnoses the first repeated-call transition mismatch, and v0.4.52 corrects dense native global alias writeback plus per-call leveltemp lifecycle with a controlled four-mode causality scan. v0.4.53 adds exact evaluation-2 replay, v0.4.54 localizes the solver-entry mismatch, v0.4.55 restores the literal terminal zero seed, and v0.4.56 accepts the natural four-evaluation source branch/thermal prefix. v0.4.57 adds unrestricted all-evaluation convergence and post-dsec fixed-state acceptance. v0.4.58 adds exact post-dsec call-entry replay. v0.4.59 confirms that the only strict replay failure is the near-zero normalized `hmctot`: both Python and XSTAR exactly reproduce the source heatf expression, both satisfy the literal dsec `1.e-4` convergence test, and every underlying fixed-state quantity passes. Milestone-4 local-zone balance is source-semantically accepted. v0.4.60 validates bremsmap. v0.4.61 translates and validates calc_emisab_all -> calc_emisab_element -> calc_emisab_ion. v0.4.62 accepts calc_emis_all, v0.4.63 accepts complete local xstarcalc, and v0.4.64 accepts the bounded first-pass step -> trnfrc -> xstarcalc -> heatt-handler -> stpcut -> trnfrn caller contract. v0.4.65 translates and directly validates heatt and replaces that handler in the same radial sequence. v0.4.66 translates and directly validates gsmooth/gsmooth2 and closes the nonzero-turbulence branch before heatt. v0.4.67 translates and directly validates unsavd, adds caller-owned REAL(4) shell/pass state with source HDU insertion semantics, and accepts three alternating radial passes. v0.4.68 closes the inline density.dat branch and makes the fixed requested-pass, direction, shell-loop, and numrec<=0 contracts explicit without inventing adaptive convergence. v0.4.69 translates and validates the savd/fstepr detail FITS sequence, binemis/voigte, and writespectra1-4 final FITS sequence in caller order. v0.4.70 translates the source-default legacy pprint path, writes xout_step.log and xout_abund1.fits, and adds an independent physical output-parity comparator. v0.4.71 inventories the supplied 62-case original-XSTAR script tree, defines the canonical C V/O VII/Mg XI/Ca XIX four-case gate, optionally regenerates original outputs without sourcing shell scripts, and compares all ten required products. Physical all-ATDB parity remains open until an independent Python physical input-to-state runner produces the matching case directories."),
    ]
    return XSTARPortLedger(entries)
