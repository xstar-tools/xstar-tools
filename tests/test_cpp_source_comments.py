from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "qualification"))
from local_zone_naming_compat import current_path, current_rel, normalize_bytes
from function_comment_overlay import strip_cpp_function_comments
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


def _cleanup():
    return json.loads((ROOT / "qualification" / "cpp_history_cleanup_0_6_57.json").read_text())


def _warning():
    return json.loads((ROOT / "qualification" / "cpp_warning_cleanup_0_6_58.json").read_text())


def _resolve(rel: str) -> Path | None:
    p = current_path(rel)
    if p.is_file():
        return p
    for info in _cleanup()["archived_cpp_sources"].values():
        if info["original_path"] == rel:
            hp = ROOT / info["historical_path"]
            return hp if hp.is_file() else None
    return None


def test_all_active_cpp_h_hpp_files_have_source_correspondence_blocks():
    files = sorted(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "src/xstar_tools/xstar/cpp").iterdir()
        if p.is_file() and p.suffix in {".cpp", ".h", ".hpp"}
    )
    data = _overlay()
    overlay = data["files"]
    cleanup = _cleanup()
    archived_originals = {x["original_path"] for x in cleanup["archived_cpp_sources"].values()}
    assert data["schema"] == "xstar-tools-cpp-source-comment-overlay-v2"
    assert data["productization_version"] == "0.6.54"
    assert len(files) == 45
    assert files == sorted(current_rel(rel) for rel in (set(overlay) - archived_originals))
    for rel in files:
        text = (ROOT / rel).read_text(errors="replace")[:3000]
        assert text.startswith("// XSTAR-SOURCE-CORRESPONDENCE-BEGIN\n")
        for field in ("Fortran:", "Role:", "Relation:", "Concordance:", "Qualification:"):
            assert f"// {field}" in text


def test_cpp_source_comment_overlay_pins_active_and_archived_0654_bytes():
    historical_present = (ROOT / "historical").is_dir()
    cleanup_by_original = {x["original_path"]: x for x in _cleanup()["archived_cpp_sources"].values()}
    for rel, info in _overlay()["files"].items():
        p = _resolve(rel)
        if p is None:
            assert not historical_present
            assert cleanup_by_original[rel]["comment_overlay_annotated_sha256_0_6_54"] == info["annotated_sha256_0_6_54"]
            continue
        raw = normalize_bytes(strip_cpp_function_comments(p.read_bytes()))
        warning = _warning()["files"]
        if rel in warning:
            winfo = warning[rel]
            assert winfo["base_sha256_0_6_57"] == info["annotated_sha256_0_6_54"]
            assert winfo["comment_overlay_normalized_sha256_0_6_54"] == info["normalized_sha256_0_6_54"]
            assert _sha(raw) == winfo["cleaned_sha256_0_6_58"]
        else:
            assert _sha(raw) == info["annotated_sha256_0_6_54"]
            assert _sha(_strip(raw)) == info["normalized_sha256_0_6_54"]


def test_pinned_cpp_hashes_match_parity_freeze_after_stripping_top_comments():
    overlay = _overlay()["files"]
    frozen = json.loads((ROOT / "qualification" / "parity_freeze_science_hashes.json").read_text())
    cleanup_by_original = {x["original_path"]: x for x in _cleanup()["archived_cpp_sources"].values()}
    for rel, expected in frozen.items():
        if rel not in overlay:
            continue
        p = _resolve(rel)
        if p is None:
            assert cleanup_by_original[rel]["science_freeze_sha256"] == expected
        else:
            warning = _warning()["files"]
            if rel in warning:
                assert _sha(normalize_bytes(strip_cpp_function_comments(p.read_bytes()))) == warning[rel]["cleaned_sha256_0_6_58"]
                assert warning[rel]["science_freeze_sha256"] == expected
            else:
                assert _sha(_strip(normalize_bytes(strip_cpp_function_comments(p.read_bytes())))) == expected
