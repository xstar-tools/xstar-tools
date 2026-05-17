from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import xstar_atomic.source_port_element_cli as cli


class _Closer:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_population_parity_is_deferred_when_strict_assembly_cannot_solve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closer = _Closer()
    built = SimpleNamespace(master=object(), derived=object(), atomic_state=closer)
    monkeypatch.setattr(cli, "load_atomic_database_state", lambda *a, **k: built)
    monkeypatch.setattr(
        cli,
        "load_xstar_runtime_context_reference",
        lambda *a, **k: SimpleNamespace(
            temperature_k=7.6655e4,
            hydrogen_density_cm3=1.0e8,
            electron_fraction_xee=1.2,
            electron_density_cm3=1.2e8,
            covering_fraction=1.0,
            solve_call_id="219",
            occurrence_rank=1,
            n_rows=2,
            metadata={},
        ),
    )
    assembly = SimpleNamespace(
        basis=SimpleNamespace(n_rows=2),
        strict_assembly_ready=False,
        blocked_records=[
            {
                "data_type": 95,
                "rate_type": 5,
                "status": "source_branch_rejected_record",
                "reason": "eint_failed",
            }
        ],
        n_records_blocked=1,
        n_unmapped_endpoints=0,
    )
    result = SimpleNamespace(
        assembly=assembly,
        solve=None,
        full_element_direct_solve_ready=False,
        population_parity=None,
        msolvelucy_state_parity=None,
    )
    monkeypatch.setattr(cli, "solve_element_statistical_equilibrium", lambda *a, **k: result)

    def _write_products(_result, out_dir):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        return {}

    monkeypatch.setattr(cli, "write_element_equilibrium_products", _write_products)

    out = tmp_path / "out"
    status = cli.main(
        [
            "--atdb", str(tmp_path / "atdb.fits"),
            "--temperature-k", "1e6",
            "--hydrogen-density-cm3", "1e8",
            "--electron-fraction-xee", "1",
            "--xstar-population-probe-csv", str(tmp_path / "population.csv"),
            "--xstar-population-solve-call-id", "219",
            "--xstar-msolvelucy-state-probe-dir", str(tmp_path / "state"),
            "--out-dir", str(out),
        ]
    )

    assert status == 2
    assert closer.closed
    blocker_json = (out / "xstar_element_assembly_blocker_summary.json").read_text()
    assert '"population_parity_status": "not_run_due_to_incomplete_strict_assembly"' in blocker_json
    runtime_json = (out / "xstar_element_runtime_context.json").read_text()
    assert '"population_parity_status": "not_run_due_to_incomplete_strict_assembly"' in runtime_json
    assert '"msolvelucy_state_parity_status": "not_run_due_to_population_parity_unavailable"' in runtime_json
