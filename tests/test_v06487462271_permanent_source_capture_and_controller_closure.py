from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_tools.xstar import source_capture_resolver_v0487462271 as resolver
from xstar_tools.xstar import source_order_electron_controller_closure_v048746227 as focused


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_source_order_accumulator_has_no_element_subtotal() -> None:
    text = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "element_electron_fraction" not in text
    assert "computed_electron_fraction + source_term" in text
    assert "computed_electron_fraction + fully_stripped_source_term" in text
    assert "volatile double source_term" in text


def test_runner_verifies_or_recaptures_before_fixed_replay() -> None:
    text = (root() / "run_v048746227_source_order_electron_controller_closure.sh").read_text()
    source_index = text.index("XSTAR_V048746217_SOURCE_CAPTURE_PREFLIGHT_ONLY=1")
    replay_index = text.index("run_v048746227_native_fixed_replay.sh")
    assert source_index < replay_index
    assert "v048746217_source_capture_dir.txt" in text


def test_resolver_reuses_only_verified_candidate(tmp_path: Path, monkeypatch) -> None:
    bad = tmp_path / "bad" / resolver.CAPTURE_BASENAME
    good = tmp_path / "v048746212_corrected" / resolver.CAPTURE_BASENAME
    bad.mkdir(parents=True)
    good.mkdir(parents=True)

    def fake_verify(path: Path):
        if path == good:
            return {"result": "ACCEPT", "evaluations": 61, "type99_capture_result": "ACCEPT", "errors": []}
        return {"result": "REJECT", "evaluations": 41, "type99_capture_result": "REJECT", "errors": ["partial"]}

    monkeypatch.setattr(resolver.capture_mod, "verify", fake_verify)
    result = resolver.resolve(
        candidates=[bad, good], search_roots=[], generated_dir=tmp_path / "generated",
        source_archive=tmp_path / "source.tar.gz", atdb_path=tmp_path / "atdb.fits",
        parameters_json=tmp_path / "parameters.json", coheat_path=None,
    )
    assert result["result"] == "ACCEPT"
    assert result["selected_dir"] == str(good.resolve())
    assert result["recaptured"] is False
    assert [attempt["result"] for attempt in result["attempts"]][-2:] == ["REJECT", "ACCEPT"]


def test_resolver_atomically_recaptures_when_all_candidates_are_stale(tmp_path: Path, monkeypatch) -> None:
    stale = tmp_path / "stale" / resolver.CAPTURE_BASENAME
    stale.mkdir(parents=True)
    generated = tmp_path / "generated" / resolver.CAPTURE_BASENAME

    def fake_verify(path: Path):
        if (path / "accepted.marker").is_file():
            return {"result": "ACCEPT", "evaluations": 61, "type99_capture_result": "ACCEPT", "errors": []}
        return {"result": "REJECT", "evaluations": 41, "type99_capture_result": "REJECT", "errors": ["stale"]}

    def fake_capture(_source, _atdb, output, _parameters, _coheat):
        output.mkdir(parents=True, exist_ok=True)
        (output / "accepted.marker").write_text("accepted\n")
        return {"result": "ACCEPT", "evaluations": 61, "type99_capture_result": "ACCEPT", "errors": []}

    monkeypatch.setattr(resolver.capture_mod, "verify", fake_verify)
    monkeypatch.setattr(resolver.capture_mod, "capture", fake_capture)
    result = resolver.resolve(
        candidates=[stale], search_roots=[], generated_dir=generated,
        source_archive=tmp_path / "source.tar.gz", atdb_path=tmp_path / "atdb.fits",
        parameters_json=tmp_path / "parameters.json", coheat_path=None,
    )
    assert result["result"] == "ACCEPT"
    assert result["selected_mode"] == "fresh_atomic_recapture"
    assert result["recaptured"] is True
    assert Path(result["selected_dir"]) == generated.resolve()
    assert (generated / "accepted.marker").is_file()


def test_focused_audit_reports_missing_dependency_without_filenotfound(tmp_path: Path) -> None:
    result = focused.audit(
        tmp_path / "source", tmp_path / "native", tmp_path / "controller",
        tmp_path / "missing_canonical.json", 2,
    )
    assert result["result"] == "REJECT"
    assert any(error.startswith("canonical_report_missing:") for error in result["errors"])
    assert not any("FileNotFoundError" in error for error in result["errors"])
    assert result["gates"]["FOCUSED_AUDIT_SCHEMA_COMPATIBLE"] == "ACCEPT"
    assert result["gates"]["SEQUENCE4_FIXED_ELCTER_BIT_EXACT"] == "BLOCKED_BY_CANONICAL_DEPENDENCY"


def test_focused_audit_accepts_all_requested_gates(tmp_path: Path) -> None:
    source = tmp_path / "source"
    native = tmp_path / "native"
    controller = tmp_path / "controller"
    canonical = tmp_path / "canonical.json"

    sequence4_xee = 1.2003632957721315
    sequence4_residual = 3.5395526509773845e-09
    sequence28_hmctot = -0.0038913671499111627

    write_csv(
        source / "v0472_all61_input_states.csv",
        ["sequence", "kind", "dsec_call_id", "evaluation_index", "electron_fraction_input"],
        [
            {"sequence": 4, "kind": "dsec", "dsec_call_id": 1, "evaluation_index": 4, "electron_fraction_input": sequence4_xee},
            {"sequence": 28, "kind": "dsec", "dsec_call_id": 3, "evaluation_index": 6, "electron_fraction_input": 1.2},
        ],
    )
    write_csv(
        source / "v0472_all61_thermal_budget.csv",
        ["sequence", "elcter", "hmctot"],
        [
            {"sequence": 4, "elcter": sequence4_residual, "hmctot": -1.0},
            {"sequence": 28, "elcter": 1.0e-4, "hmctot": sequence28_hmctot},
        ],
    )
    write_csv(
        native / "evaluation_0004" / "native_thermal_budget.csv",
        ["charge_residual", "hmctot"],
        [{"charge_residual": sequence4_residual, "hmctot": -1.0}],
    )
    write_csv(
        controller / "native_dsec_trajectory.csv",
        ["kind", "call_index", "evaluation_index", "electron_fraction_input", "charge_residual", "hmctot"],
        [
            {"kind": "dsec", "call_index": 1, "evaluation_index": 4, "electron_fraction_input": sequence4_xee, "charge_residual": sequence4_residual, "hmctot": -1.0},
            {"kind": "dsec", "call_index": 3, "evaluation_index": 6, "electron_fraction_input": 1.2, "charge_residual": 1.0e-4, "hmctot": -0.0038913671499164687},
        ],
    )
    canonical.write_text(json.dumps({"scientific_result": "ACCEPT", "rejected_differences": 0}))
    result = focused.audit(source, native, controller, canonical, 0)
    assert result["result"] == "ACCEPT"
    assert set(result["gates"].values()) == {"ACCEPT"}
    assert result["product_level_parity"] == "NOT_IN_SCOPE"


def test_fresh_plan_uses_non_error_reason() -> None:
    text = (root() / "run_v048746227_native_fixed_replay.sh").read_text()
    assert "fresh_replay_required" in text


def test_canonical_checker_missing_report_is_structured(tmp_path: Path) -> None:
    import importlib.util

    module_path = root() / "check_v048746217_canonical_thermal_controller_parity.py"
    spec = importlib.util.spec_from_file_location("canonical_checker_v2171", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.check(tmp_path / "audit", tmp_path / "baseline.json", tmp_path / "source.json")
    assert result["result"] == "REJECT"
    assert result["errors"][0].startswith("canonical_audit_report_missing:")
    assert "FileNotFoundError" not in result["errors"][0]
    assert result["production_promotion_status"] == "BLOCKED_BY_CANONICAL_AUDIT_DEPENDENCY"


def test_public_cpp_version_label_and_abi() -> None:
    text = (root() / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.7.46.21.17.1"' in text
    assert "60487" in text
