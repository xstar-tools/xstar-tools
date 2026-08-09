from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest():
    return json.loads((ROOT / "qualification/cpp_non_science_refactor_0_6_54.json").read_text())


def test_version_labeled_runtime_headers_were_replaced_by_stable_names():
    data = _manifest()
    assert len(data["header_renames"]) == 4
    for item in data["header_renames"]:
        assert not (ROOT / item["old_path"]).exists()
        assert (ROOT / item["new_path"]).is_file()
    active = "\n".join(p.read_text(errors="replace") for p in CPP.iterdir() if p.is_file() and p.suffix in {".cpp", ".h", ".hpp"})
    for item in data["header_renames"]:
        assert Path(item["old_path"]).name not in active
    for rename in data["namespace_renames"]:
        assert rename["old"] not in active
        assert rename["new"] in active


def test_constants_def_is_local_to_cpp_and_shared_by_python():
    data = _manifest()["constants_relocation"]
    old = ROOT / data["old_path"]
    new = ROOT / data["new_path"]
    assert not old.exists()
    assert new.is_file()
    assert _sha(new) == data["sha256"] == "3242afd7a4e9b66e08cf86207f41425d2b03d7d70184b145abe605ca6f46fb0b"
    assert 'with_name("cpp") / "constants.def"' in (ROOT / data["python_loader"]).read_text()
    assert '#include "constants.def"' in (CPP / "xstar_constants.h").read_text()


def test_cpp_has_no_parent_directory_header_dependency():
    offenders = []
    for p in CPP.iterdir():
        if p.is_file() and p.suffix in {".cpp", ".h", ".hpp"}:
            for lineno, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                if re.search(r'^\s*#\s*include\s*[<"]\.\./', line):
                    offenders.append(f"{p.name}:{lineno}")
    assert offenders == []


def test_atomic_data_type_comments_are_grounded_and_scoped():
    atdb = (CPP / "xstar_atdb_runtime.cpp").read_text()
    assert "XSTAR Manual, Chapter 12" in atdb
    assert "2021, Appendix A" in atdb
    assert "data type" in atdb and "rate type" in atdb and "six integers" in atdb
    for token in ("Types 50 and 91", "Types 49 and 53", "Type 63", "Type 70", "Type 85", "Type 86", "Type 88", "Type 95", "Type 99"):
        assert token in atdb
    fixed = (CPP / "local_zone_engine.cpp").read_text()
    assert "Types 89, 96, and 97" in fixed
    assert "not enumerated in the requested Appendix-A / Chapter-12 snapshots" in fixed
    assert "Type 98" in fixed and "Burgess-Tully" in fixed
    assert "Appendix-A atomic-data context" in (CPP / "type50_dsec_runtime_oracle.h").read_text()
    assert "Appendix-A atomic-data context" in (CPP / "type50_manifold_oracle.h").read_text()
    assert "Appendix-A atomic-data context" in (CPP / "type53_row46_dsec_runtime_oracle.h").read_text()
