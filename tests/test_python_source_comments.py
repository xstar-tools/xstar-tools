from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
    assert data["schema"] == "xstar-tools-python-source-comment-overlay-v1"
    assert data["productization_version"] == "0.6.55"
    assert data["base_productization_version"] == "0.6.54"
    assert len(data["files"]) == 45
    assert sum(bool(v["atomic_data_comment"]) for v in data["files"].values()) == 20


def test_python_source_comments_are_byte_exact_overlay():
    for rel, info in _overlay()["files"].items():
        raw = (ROOT / rel).read_bytes()
        assert _sha(raw) == info["annotated_sha256_0_6_55"]
        assert _sha(_strip(raw)) == info["baseline_sha256_0_6_54"]


def test_atomic_data_comments_preserve_data_type_rate_type_distinction():
    for rel, info in _overlay()["files"].items():
        if not info["atomic_data_comment"]:
            continue
        text = (ROOT / rel).read_text(errors="replace")[:6000]
        assert "Atomic-data note" in text
        assert "data type" in text.lower()
        assert "rate type" in text.lower()


def test_parity_pinned_python_files_are_covered_by_overlay():
    frozen = json.loads((ROOT / "qualification" / "parity_freeze_science_hashes.json").read_text())
    overlay = _overlay()["files"]
    pinned_python = {rel: digest for rel, digest in frozen.items() if rel.endswith(".py")}
    assert len(pinned_python) == 7
    assert set(pinned_python) <= set(overlay)
    for rel, expected in pinned_python.items():
        assert _sha(_strip((ROOT / rel).read_bytes())) == expected
