from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import types

import xstar_tools
from xstar_tools.cli import main as cli_main_module


USER_COMMANDS = ("run", "inspect", "data", "backends", "compare", "doctor", "version")
LEGACY_SCRIPTS = (
    "xstar-tools-benchmark", "xstar-tools-run-xstar", "xstar-tools-inspect-atdb",
    "xstar-tools-xstinitable", "xstar-tools-xstar2table", "xstar-tools-xstar2xspec",
    "xstar-tools-mpixstar", "xstar-tools-inspect", "xstar-tools-download-data",
    "xstar-tools-run-python", "xstar-tools-original-parity-gate", "xstar-tools-cpp-parity-gate",
    "xstar-tools-qualification",
)


class FakeConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.output_dir = Path(kwargs["output_dir"]).resolve()

    @classmethod
    def from_par_file(cls, path, **kwargs):
        return cls(input_file=path, **kwargs)


class FakeResult:
    success = True
    status = "success"
    return_code = 0
    runtime_seconds = 1.25
    warnings = ()
    mode = "zone-cpp"

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def as_dict(self):
        return {
            "success": True,
            "status": "success",
            "return_code": 0,
            "output_dir": str(self.output_dir),
            "products": {},
            "produced_fits": [],
            "step_log": str(self.output_dir / "xout_step.log"),
            "runtime_seconds": self.runtime_seconds,
            "timings": {},
            "provenance": {"execution": {"actual_mode": "zone-cpp", "public_api": "XStarConfig"}},
            "diagnostics": [],
            "warnings": [],
        }


def test_primary_help_exposes_milestone5_user_tree(capsys):
    assert cli_main_module.main(["--help"]) == 0
    out = capsys.readouterr().out
    for command in USER_COMMANDS:
        assert f"  {command}" in out
    assert "  dev" in out
    assert "  qualify" in out


def test_run_delegates_to_public_python_api_and_writes_json_events(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(xstar_tools, "XStarConfig", FakeConfig)

    def fake_run(config):
        calls.append(config)
        return FakeResult(config.output_dir)

    monkeypatch.setattr(xstar_tools, "run_xstar", fake_run)
    event_log = tmp_path / "events.jsonl"
    summary = tmp_path / "summary.json"
    out = tmp_path / "run"
    rc = cli_main_module.main([
        "run", str(tmp_path / "xstar.par"), "--mode", "zone-cpp",
        "--data-dir", str(tmp_path / "data"), "--output-dir", str(out),
        "--threads", "2", "--no-progress", "--json-log", str(event_log),
        "--summary-json", str(summary),
    ])
    assert rc == 0
    assert len(calls) == 1
    cfg = calls[0]
    assert cfg.kwargs["mode"] == "zone-cpp"
    assert cfg.kwargs["threads"] == 2
    assert cfg.kwargs["progress"] is False
    assert cfg.kwargs["data_dir"] == str(tmp_path / "data")
    events = [json.loads(line) for line in event_log.read_text().splitlines()]
    assert [row["event"] for row in events] == ["run_started", "run_completed"]
    assert events[-1]["provenance"]["execution"]["public_api"] == "XStarConfig"
    assert json.loads(summary.read_text())["provenance"]["execution"]["actual_mode"] == "zone-cpp"


def test_run_failure_writes_structured_failure_event(tmp_path, monkeypatch):
    monkeypatch.setattr(xstar_tools, "XStarConfig", FakeConfig)
    monkeypatch.setattr(xstar_tools, "run_xstar", lambda _config: (_ for _ in ()).throw(RuntimeError("boom")))
    event_log = tmp_path / "events.jsonl"
    rc = cli_main_module.main([
        "run", str(tmp_path / "xstar.par"), "--data-dir", str(tmp_path / "data"),
        "--output-dir", str(tmp_path / "run"), "--json-log", str(event_log),
    ])
    assert rc == 2
    rows = [json.loads(line) for line in event_log.read_text().splitlines()]
    assert rows[-1]["event"] == "run_failed"
    assert rows[-1]["error"] == "RuntimeError"


def test_inspect_and_data_delegate_existing_supported_tools(monkeypatch):
    seen = []
    inspect_mod = types.ModuleType("xstar_tools.inspect")
    inspect_mod.main = lambda argv=None: seen.append(("inspect", argv)) or 0
    monkeypatch.setitem(sys.modules, "xstar_tools.inspect", inspect_mod)
    import xstar_tools.data as data_mod
    monkeypatch.setattr(data_mod, "main", lambda argv=None: seen.append(("data", argv)) or 0)
    assert cli_main_module.main(["inspect", "atdb.fits", "--summary"]) == 0
    assert cli_main_module.main(["data", "--show"]) == 0
    assert seen == [("inspect", ["atdb.fits", "--summary"]), ("data", ["--show"])]


def test_compare_delegates_accepted_public_suite_comparator(monkeypatch, capsys):
    import xstar_tools.benchmarks.public_suite as suite
    calls = []
    monkeypatch.setattr(suite, "_repo_root", lambda: Path("/package"))
    monkeypatch.setattr(suite, "compare_suite", lambda **kwargs: calls.append(kwargs) or {
        "fortran_all_science_accept": True,
        "cpp44_all_exact_accept": None,
    })
    rc = cli_main_module.main([
        "compare", "--run-root", "runs", "--fortran-reference-archive", "fortran.tar.gz", "--out", "cmp",
    ])
    assert rc == 0
    assert calls[0]["run_root"] == "runs"
    assert calls[0]["fortran_reference_archive"] == "fortran.tar.gz"
    assert json.loads(capsys.readouterr().out)["fortran_all_science_accept"] is True


def test_dev_and_qualify_namespaces_have_help(capsys):
    assert cli_main_module.main(["dev", "--help"]) == 0
    dev = capsys.readouterr().out
    assert "legacy-run" in dev and "benchmark" in dev
    assert cli_main_module.main(["qualify", "--help"]) == 0
    qualify = capsys.readouterr().out
    for token in ("benchmark", "original-parity", "cpp-parity", "reference"):
        assert token in qualify


def test_legacy_console_scripts_remain_installed_for_deprecation_cycle():
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    for name in LEGACY_SCRIPTS:
        assert f"{name} =" in pyproject


def test_top_level_benchmark_alias_warns_and_remains_compatible(monkeypatch, capsys):
    import xstar_tools.benchmarks.public_suite as suite
    monkeypatch.setattr(suite, "main", lambda argv=None: 0)
    assert cli_main_module.main(["benchmark", "list"]) == 0
    assert "deprecated" in capsys.readouterr().err


def test_version_reports_package_science_and_abis(capsys):
    assert cli_main_module.main(["version", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["package_version"] == xstar_tools.__package_version__
    assert data["science_revision"] == "0.6.90.5.5"
    assert data["c_api_abi"] == 60487
    assert data["production_zone_abi"] == 6048110


def test_module_help_works_without_importing_astropy():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "xstar_tools.cli.main", "--help"],
        cwd=root, text=True, capture_output=True,
        env={**__import__("os").environ, "PYTHONPATH": str(root / "src")},
    )
    assert proc.returncode == 0
    assert "xstar-tools run" not in proc.stderr
