from __future__ import annotations

import hashlib
import json
from pathlib import Path

from xstar_atomic.benchmarks import oxygen_milestone3_v0422_path
from xstar_atomic.source_port import (
    COMPLETED_SOURCE_PORT_MILESTONES,
    NEXT_COHERENT_SOURCE_PORT_TARGET,
    PORT_LEDGER_VERSION,
    PortStatus,
    default_port_ledger,
)


def _benchmark_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "oxygen_milestone3_v0422"


def test_updated_translation_ledger_marks_milestones_1_to_3_and_next_target():
    ledger = default_port_ledger()
    by_routine = {entry.routine: entry for entry in ledger.entries}

    assert PORT_LEDGER_VERSION == "v0.4.83"
    assert COMPLETED_SOURCE_PORT_MILESTONES == (1, 2, 3)
    assert NEXT_COHERENT_SOURCE_PORT_TARGET == (
        "rerun the Python zone-1 diagnostic after the v0.4.83 type-59 source-guard "
        "zero-return correction; require record 6077 and the ten physical gates to pass, "
        "then rerun c5_ne1 ten-product parity before the canonical four-case and 62-case suites"
    )
    for routine in (
        "readtbl", "setptrs", "ucalc", "levwk", "levwkelement",
        "calc_hmc_ion", "calc_hmc_element", "msolvelucy",
        "leqt2f", "ludcmp", "lubksb", "mprove",
    ):
        assert by_routine[routine].status is PortStatus.VALIDATED

    assert by_routine["calc_ion_rates"].status is PortStatus.VALIDATED
    assert by_routine["istruc"].status is PortStatus.VALIDATED
    assert by_routine["ioneqm"].status is PortStatus.VALIDATED
    assert by_routine["cmpfnc"].status is PortStatus.VALIDATED
    assert by_routine["comp2"].status is PortStatus.VALIDATED
    assert by_routine["freef"].status is PortStatus.VALIDATED
    assert by_routine["bremem"].status is PortStatus.VALIDATED
    assert by_routine["heatf"].status is PortStatus.VALIDATED
    assert by_routine["bremsmap"].status is PortStatus.VALIDATED
    assert by_routine["calc_hmc_all"].status is PortStatus.TRANSLATED
    assert by_routine["dsec"].status is PortStatus.TRANSLATED
    assert by_routine["calc_emis_all"].status is PortStatus.VALIDATED
    assert by_routine["xstarcalc"].status is PortStatus.VALIDATED
    for routine in ("step", "trnfrc", "stpcut", "trnfrn"):
        assert by_routine[routine].status is PortStatus.VALIDATED
    assert by_routine["heatt"].status is PortStatus.VALIDATED
    assert by_routine["gsmooth"].status is PortStatus.VALIDATED
    assert by_routine["unsavd"].status is PortStatus.VALIDATED
    assert by_routine["xstar"].status is PortStatus.SCAFFOLD


def test_frozen_oxygen_milestone3_manifest_is_accepted_and_hash_locked():
    root = _benchmark_dir()
    manifest = json.loads((root / "benchmark_manifest.json").read_text())

    assert manifest["freeze_release"] == "v0.4.22"
    assert manifest["source_run_release"] == "v0.4.21"
    assert manifest["topology"]["compact_rows"] == 607
    assert manifest["topology"]["matrix_terms"] == 26920
    assert manifest["assembly_acceptance"]["records_blocked"] == 0
    assert manifest["assembly_acceptance"]["source_ipmat_endpoint_clamps"] == 0
    assert manifest["solver_acceptance"]["solver_converged"] is True
    assert manifest["population_acceptance"]["ready"] is True
    assert manifest["population_acceptance"]["n_rows_within_tolerance"] == 607
    assert manifest["population_acceptance"]["n_rows_outside_tolerance"] == 0
    assert manifest["population_acceptance"]["native_final_vs_xstar_after_l1"] < 2.1e-5
    assert manifest["type56_closure_v0422"]["records"] == [22861, 22862, 22863]

    for name, expected in manifest["frozen_products_sha256"].items():
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        assert actual == expected


def test_frozen_benchmark_is_available_as_installed_package_data():
    root = oxygen_milestone3_v0422_path()
    assert (root / "benchmark_manifest.json").is_file()
    manifest = json.loads((root / "benchmark_manifest.json").read_text())
    assert manifest["benchmark_id"] == "oxygen_o3_o8_solve_call_219_milestone3_v0422"
    assert manifest["population_acceptance"]["ready"] is True
