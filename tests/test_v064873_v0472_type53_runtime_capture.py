from __future__ import annotations

import csv
import json
import tarfile
from pathlib import Path

import pytest

from xstar_tools.xstar import v0472_type53_runtime_capture as capture
from xstar_tools.xstar.type53_semantics import analyze, verify_reference


def _fake_source_archive(tmp_path: Path) -> Path:
    root = tmp_path / "fake-source/xstar_tools-0.6.47.2"
    package = root / "src/xstar_tools"
    package.mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname="xstar-tools"\nversion = "0.6.47.2"\n', encoding="utf-8")
    (package / "__init__.py").write_text('__version__ = "0.6.47.2"\n', encoding="utf-8")
    (package / "rates_type53.py").write_text(
        '''\nclass Type53LiveRadiationState:\n    @classmethod\n    def from_sequences(cls, energy, incident, integral, metadata=None):\n        return cls()\n\ndef evaluate_type53_ucalc_record(record, radiation, **kwargs):\n    t = float(record["threshold_eV"])\n    return {\n        "status": "evaluated",\n        "ans1_photoionization_s^-1": t,\n        "ans2_milne_recombination_s^-1": t + 1.0,\n        "ans3_cooling_signed_erg_s^-1": -(t + 2.0),\n        "ans4_heating_signed_erg_s^-1": -(t + 3.0),\n        "ans5_electron_pov_cooling_signed_erg_s^-1": -(t + 4.0),\n        "ans6_electron_pov_heating_signed_erg_s^-1": -(t + 5.0),\n        "rnist": 0.5, "sumr": t, "sumi": t + 1, "sumh": t + 3,\n        "sumh2": t + 5, "sumc": t + 2, "sumc2": t + 4,\n        "phint53_diagnostics": {"nb1_1based": 2, "klmax_1based": 4},\n    }\n''',
        encoding="utf-8",
    )
    archive = tmp_path / "fake-v0472.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(root, arcname=root.name)
    return archive


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    lowered = tmp_path / "lowered"
    lowered.mkdir()
    (lowered / "manifest.txt").write_text(
        "active_atdb_lowered=true\nactive_element_z=1,2,12\n", encoding="utf-8"
    )
    with (lowered / "rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["element_index", "row", "energy_ev", "statistical_weight"])
        writer.writeheader()
        writer.writerow({"element_index": 1, "row": 1, "energy_ev": 0.0, "statistical_weight": 2.0})
        writer.writerow({"element_index": 1, "row": 2, "energy_ev": 100.0, "statistical_weight": 1.0})
    record_fields = [
        "source_position", "record", "element_index", "lower_row", "upper_row",
        "real_offset", "real_count", "line_energy_ev",
    ]
    with (lowered / "records.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=record_fields)
        writer.writeheader()
        for index in range(31):
            writer.writerow({
                "source_position": 100 + 4 * index, "record": 1000 + index,
                "element_index": 1, "lower_row": 1, "upper_row": 2,
                "real_offset": 4 * index, "real_count": 4, "line_energy_ev": index + 1.0,
            })
    (lowered / "reals.txt").write_text("".join("0\n1e-18\n1\n5e-19\n" for _ in range(31)), encoding="utf-8")

    audit = tmp_path / "audit/diagnostics"
    audit.mkdir(parents=True)
    fields = ["evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type", "lower_row", "upper_row"]
    with (audit / "evaluation_0061_records.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(31):
            writer.writerow({
                "evaluation_ordinal": 61, "source_position": 100 + 4 * index,
                "record": 1000 + index, "element_z": 2, "ion_stage": 2,
                "data_type": 53, "lower_row": 1, "upper_row": 2,
            })
    (audit / "evaluation_0061_state.json").write_text(json.dumps({
        "evaluation_ordinal": 61, "radiation_bin_count": 9999,
        "temperature_k": 65000.0, "hydrogen_density_cm3": 1e8,
        "electron_fraction_input": 1.2,
    }), encoding="utf-8")

    radiation = tmp_path / "radiation.csv"
    with radiation.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["energy", "incident"])
        writer.writeheader()
        for index in range(9999):
            writer.writerow({"energy": 0.1 + index, "incident": 1e12})
    return lowered, audit.parent, radiation


def test_exact_source_replay_capture_and_freeze(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _fake_source_archive(tmp_path)
    monkeypatch.setattr(capture, "SOURCE_ARCHIVE_SHA256", capture._sha256(archive))
    lowered, audit, radiation = _inputs(tmp_path)
    bundle = tmp_path / "bundle"
    result = capture.capture_and_freeze(archive, lowered, audit, radiation, bundle)
    assert result["result"] == "ACCEPT"
    assert result["runtime_oracle_available"] is True
    assert verify_reference(bundle)["result"] == "ACCEPT"
    rows = list(csv.DictReader((bundle / "type53_runtime_oracle.csv").open()))
    assert len(rows) == 31
    assert float(rows[0]["ans1"]) == 1.0
    assert float(rows[-1]["ans6"]) == -36.0
    provenance = json.loads((bundle / "capture_provenance.json").read_text())
    assert "/tmp/" not in json.dumps(provenance)
    assert provenance["capture_kind"] == "exact_v06472_fixed_state_evaluator_replay"


def test_capture_rejects_wrong_source_archive(tmp_path: Path) -> None:
    archive = _fake_source_archive(tmp_path)
    lowered, audit, radiation = _inputs(tmp_path)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        capture.capture_runtime(archive, lowered, audit, radiation, tmp_path / "out.csv")


def test_bundled_runtime_oracle_is_complete() -> None:
    bundle = Path(__file__).parents[1] / "src/xstar_tools/benchmarks/v064873_type53_runtime_oracle_v0472"
    verified = verify_reference(bundle)
    assert verified["result"] == "ACCEPT"
    provenance = json.loads((bundle / "capture_provenance.json").read_text())
    assert provenance["source_package_version"] == "0.6.47.2"
    assert provenance["records"] == 31
    assert provenance["full_dsec_runtime_capture"] is False
