from __future__ import annotations

from pathlib import Path

import pytest

from xstar_tools.benchmarks.public_suite import Case, _run_command


def test_python_benchmark_uses_current_unified_run_cli(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    run_script = tmp_path / "run_xstar.sh"
    run_script.write_text("#!/usr/bin/env bash\n")
    data = tmp_path / "data"
    data.mkdir()
    atdb = data / "atdb.fits"
    coheat = data / "coheat.dat"
    atdb.write_bytes(b"atdb")
    coheat.write_bytes(b"coheat")
    output = tmp_path / "out"
    case = Case("helike_type69/example", run_script)

    command = _run_command(
        "pure-python", case, package, atdb, coheat, output, tmp_path / "cache", None
    )

    assert command[3:6] == ["xstar_tools.cli.main", "run", str(run_script)]
    assert "--mode" in command and command[command.index("--mode") + 1] == "pure-python"
    assert "--data-dir" in command and command[command.index("--data-dir") + 1] == str(data)
    assert "--output-dir" in command and command[command.index("--output-dir") + 1] == str(output)
    assert "--summary-json" in command
    assert "--cache-dir" in command
    for retired in ("--run-script", "--atdb", "--coheat-data", "--print-summary"):
        assert retired not in command


def test_python_benchmark_rejects_split_data_roots(tmp_path: Path) -> None:
    run_script = tmp_path / "run_xstar.sh"
    run_script.write_text("#!/usr/bin/env bash\n")
    atdb = tmp_path / "a" / "atdb.fits"
    coheat = tmp_path / "b" / "coheat.dat"
    atdb.parent.mkdir(); coheat.parent.mkdir()
    atdb.write_bytes(b"a"); coheat.write_bytes(b"b")
    case = Case("helike_type69/example", run_script)
    with pytest.raises(RuntimeError, match="must share one data directory"):
        _run_command("zone-python", case, tmp_path, atdb, coheat, tmp_path / "out", None, None)
