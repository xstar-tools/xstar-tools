from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "build_support.py"
NATIVE_RUNTIME = ROOT / "src/xstar_tools/native_runtime.py"
SUPPORT_SHA = "93fbfcb4987def93853daa1a22c67077f0cc8b6a13b28f2f8d50baf4b546b3f8"
NATIVE_RUNTIME_SHA = "c764699e128f7c0c457124001d26ddafa587859a7e737c417d2b117998ea3bd1"


def normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def normalized_hash(path: Path) -> str:
    return hashlib.sha256(normalized_bytes(path)).hexdigest()


def test_frozen_packaging_sources_match_canonical_lf_hashes() -> None:
    assert normalized_hash(SUPPORT) == SUPPORT_SHA
    assert normalized_hash(NATIVE_RUNTIME) == NATIVE_RUNTIME_SHA


def test_crlf_checkout_is_qualification_equivalent(tmp_path: Path) -> None:
    for source, expected in ((SUPPORT, SUPPORT_SHA), (NATIVE_RUNTIME, NATIVE_RUNTIME_SHA)):
        target = tmp_path / source.name
        target.write_bytes(normalized_bytes(source).replace(b"\n", b"\r\n"))
        assert normalized_hash(target) == expected
        assert hashlib.sha256(target.read_bytes()).hexdigest() != expected


def test_host_runner_persists_context_before_source_qualification() -> None:
    runner = (ROOT / "tools/qualification/run_pip_source_line_ending_equivalence_closure_host_0_6_89_1_3.py").read_text()
    assert '(output / "host_context.json").write_text' in runner
    assert runner.index('(output / "host_context.json").write_text') < runner.index('source = subprocess.run(')
