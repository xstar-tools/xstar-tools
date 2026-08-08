from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN = b"// XSTAR-SOURCE-CORRESPONDENCE-BEGIN\n"
END = b"// XSTAR-SOURCE-CORRESPONDENCE-END\n\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strip(data: bytes) -> bytes:
    assert data.startswith(BEGIN)
    pos = data.find(END, len(BEGIN))
    assert pos >= 0
    return data[pos + len(END):]


def _overlay():
    return json.loads((ROOT / "qualification" / "cpp_source_comment_overlay.json").read_text())


def test_all_cpp_h_hpp_files_have_source_correspondence_blocks():
    files = sorted(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "src/xstar_tools/xstar/cpp").iterdir()
        if p.is_file() and p.suffix in {".cpp", ".h", ".hpp"}
    )
    overlay = _overlay()["files"]
    assert len(files) == 47
    assert files == sorted(overlay)
    for rel in files:
        text = (ROOT / rel).read_text(errors="replace")[:3000]
        assert text.startswith("// XSTAR-SOURCE-CORRESPONDENCE-BEGIN\n")
        for field in ("Fortran:", "Role:", "Relation:", "Concordance:", "Qualification:"):
            assert f"// {field}" in text


def test_cpp_source_comments_are_reversible_to_0_6_52_bytes():
    for rel, info in _overlay()["files"].items():
        raw = (ROOT / rel).read_bytes()
        assert _sha(raw) == info["annotated_sha256_0_6_53"]
        assert _sha(_strip(raw)) == info["baseline_sha256_0_6_52"]


def test_pinned_cpp_baseline_hashes_still_match_parity_freeze_after_stripping_comments():
    overlay = _overlay()["files"]
    frozen = json.loads((ROOT / "qualification" / "parity_freeze_science_hashes.json").read_text())
    for rel, expected in frozen.items():
        if rel not in overlay:
            continue
        assert _sha(_strip((ROOT / rel).read_bytes())) == expected
