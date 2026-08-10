from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "qualification"))
from local_zone_naming_compat import normalize_bytes
from function_comment_overlay import strip_python_function_comments
BEGIN = b"# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN\n"
END = b"# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END\n\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strip(data: bytes) -> bytes:
    assert data.startswith(BEGIN)
    pos = data.find(END, len(BEGIN))
    assert pos >= 0
    return data[pos + len(END):]


def _overlay():
    return json.loads((ROOT / "qualification" / "python_source_comment_overlay.json").read_text())


def test_python_source_comment_overlay_has_expected_scope():
    data = _overlay()
    assert data["schema"] == "xstar-tools-python-source-comment-overlay-v2"
    assert data["productization_version"] == "0.6.56"
    assert data["active_comment_overlay_origin_version"] == "0.6.55"
    assert data["base_productization_version"] == "0.6.54"
    assert len(data["files"]) == 44
    assert len(data["archived_files"]) == 1
    assert sum(bool(v["atomic_data_comment"]) for v in data["files"].values()) == 19
    assert sum(bool(v["atomic_data_comment"]) for v in data["archived_files"].values()) == 1


def test_python_source_comments_are_byte_exact_overlay():
    data = _overlay()
    for rel, info in data["files"].items():
        raw = normalize_bytes(strip_python_function_comments((ROOT / rel).read_bytes()))
        assert _sha(raw) == info["annotated_sha256_0_6_55"]
        assert _sha(_strip(raw)) == info["baseline_sha256_0_6_54"]
    if (ROOT / "historical").is_dir():
        for rel, info in data["archived_files"].items():
            raw = normalize_bytes(strip_python_function_comments((ROOT / rel).read_bytes()))
            assert _sha(raw) == info["annotated_sha256_0_6_55"]
            assert _sha(_strip(raw)) == info["baseline_sha256_0_6_54"]


def test_atomic_data_comments_preserve_data_type_rate_type_distinction():
    data = _overlay()
    tables = [data["files"]]
    if (ROOT / "historical").is_dir():
        tables.append(data["archived_files"])
    for table in tables:
        for rel, info in table.items():
            if not info["atomic_data_comment"]:
                continue
            text = (ROOT / rel).read_text(errors="replace")[:6000]
            assert "Atomic-data note" in text
            assert "data type" in text.lower()
            assert "rate type" in text.lower()


def test_parity_pinned_python_files_remain_active_and_covered_by_overlay():
    frozen = json.loads((ROOT / "qualification" / "parity_freeze_science_hashes.json").read_text())
    overlay = _overlay()["files"]
    pinned_python = {rel: digest for rel, digest in frozen.items() if rel.endswith(".py")}
    assert len(pinned_python) == 7
    assert set(pinned_python) <= set(overlay)
    for rel, expected in pinned_python.items():
        assert _sha(_strip(normalize_bytes(strip_python_function_comments((ROOT / rel).read_bytes())))) == expected
