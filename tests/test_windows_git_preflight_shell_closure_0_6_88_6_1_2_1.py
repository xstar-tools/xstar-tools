from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
QUAL = ROOT / "tools/qualification"
sys.path.insert(0, str(QUAL))

from fixed_state_equivalence_0_6_88_6_1 import (  # noqa: E402
    MAX_ULP,
    REL_TOL,
    compare_fixed_state,
)

REF = ROOT / "qualification/cross_platform_fixed_state_reference_0_6_88_6_1"


def text(path):
    return (ROOT / path).read_text()


def test_version_metadata():
    assert 'version = "0.6.88.6.1.2.1"' in text("pyproject.toml")
    assert "PACKAGE_VERSION ?= 0.6.88.6.1.2.1" in (CPP / "Makefile").read_text()
    assert 'kPackageVersion = "0.6.88.6.1.2.1"' in (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert 'kPackageVersion = "0.6.88.6.1.2.1"' in (CPP / "xstar_xspec_mpi.cpp").read_text()


def test_predecessor_rejection_is_recorded():
    record = text("xstar_tools-0.6.88.6.1.2_host_rejection.md")
    for token in ("Linux GCC", "macOS arm64", "macOS Intel", "Windows", "git: command not found"):
        assert token in record
    assert "historical" in record.lower()


def test_equivalence_design_is_indexed():
    assert "WINDOWS_GIT_PREFLIGHT_SHELL_CLOSURE" in text("windows_git_preflight_shell_closure_0_6_88_6_1_2_1.md")
    assert "windows_git_preflight_shell_closure_0_6_88_6_1_2_1" in text("docs/developer/index.md")
    assert "WINDOWS_GIT_PREFLIGHT_SHELL_CLOSURE" in text("docs/developer/windows_git_preflight_shell_closure_0_6_88_6_1_2_1.md")


def test_reference_payload_hashes_are_frozen():
    import hashlib
    expected = {
        "xout_step.log": "5508313e40d514d63b4d5443bc67198fe1a62a82f76f428958e6a5ea07cafa38",
        "xout_native_state.fits": "e430573df3bd1666fef4b3e5e8305f0b912e06456685aa921f4737f305e875f4",
        "visited_records.csv": "7d1addd4a66f29eda03d96954f8f07b3aa5bd627e8d506d84a3079f47474c3a3",
    }
    for name, digest in expected.items():
        payload = (REF / name).read_bytes()
        if name in {"xout_step.log", "visited_records.csv"}:
            payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        assert hashlib.sha256(payload).hexdigest() == digest


def test_reference_compares_exactly_to_itself():
    result = compare_fixed_state(REF, REF)
    assert result.ok
    assert result.numeric.differing == 0
    assert result.numeric.max_ulp == 0


def test_crlf_text_serialization_is_equivalent(tmp_path):
    cand = tmp_path / "cand"
    shutil.copytree(REF, cand)
    for name in ("xout_step.log", "visited_records.csv"):
        payload = (cand / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        (cand / name).write_bytes(payload.replace(b"\n", b"\r\n"))
    result = compare_fixed_state(REF, cand)
    assert result.ok
    assert result.visited_records_exact
    assert result.step_discrete_exact


def test_last_bit_step_difference_is_equivalent(tmp_path):
    cand = tmp_path / "cand"
    shutil.copytree(REF, cand)
    p = cand / "xout_step.log"
    s = p.read_text()
    s = s.replace("total_heating=6.4304308882626018e-12", "total_heating=6.430430888262601e-12")
    p.write_text(s)
    result = compare_fixed_state(REF, cand)
    assert result.ok
    assert result.numeric.differing >= 1


def test_discrete_state_change_is_rejected(tmp_path):
    cand = tmp_path / "cand"
    shutil.copytree(REF, cand)
    p = cand / "xout_step.log"
    p.write_text(p.read_text().replace("records_evaluated=23", "records_evaluated=22"))
    result = compare_fixed_state(REF, cand)
    assert not result.ok
    assert not result.step_discrete_exact


def test_visited_record_change_is_rejected(tmp_path):
    cand = tmp_path / "cand"
    shutil.copytree(REF, cand)
    p = cand / "visited_records.csv"
    p.write_text(p.read_text().replace("56,1", "56,2"))
    result = compare_fixed_state(REF, cand)
    assert not result.ok
    assert not result.visited_records_exact


def test_numeric_contract_is_strict():
    assert REL_TOL == 1.0e-13
    assert MAX_ULP == 64


def test_reference_payload_git_attributes_are_binary_safe():
    attrs = text(".gitattributes")
    assert "qualification/cross_platform_fixed_state_reference_0_6_88_6_1/xout_step.log -text" in attrs
    assert "qualification/cross_platform_fixed_state_reference_0_6_88_6_1/visited_records.csv -text" in attrs
    assert "qualification/cross_platform_fixed_state_reference_0_6_88_6_1/xout_native_state.fits binary" in attrs


def test_runner_uses_same_host_determinism_and_equivalence():
    runner = text("tools/qualification/run_cross_platform_fixed_state_equivalence_closure_host_0_6_88_6_1.py")
    for token in (
        "FIXED_STATE_SAME_HOST_DETERMINISM",
        "FIXED_STATE_VISITED_RECORDS_EXACT",
        "FIXED_STATE_STEP_DISCRETE_STATE",
        "FIXED_STATE_FITS_STRUCTURE",
        "FIXED_STATE_NUMERIC_EQUIVALENCE",
        "FIXED_STATE_REFERENCE_EQUIVALENCE",
    ):
        assert token in runner
    assert 'gate("FIXED_STATE_HASHES"' not in runner


def _qualifying_workflows(base):
    d = base / ".github/workflows"
    if not d.is_dir():
        return []
    out = []
    for p in sorted(set(d.glob("*.yml")) | set(d.glob("*.yaml"))):
        w = p.read_text(errors="replace")
        if all(token in w for token in (
            "ubuntu-24.04", "macos-15", "macos-15-intel", "windows-latest", "UCRT64",
            "run_windows_git_preflight_shell_closure_host_0_6_88_6_1_2_1.py",
        )):
            out.append(p)
    return out


def test_workflow_discovery_accepts_any_yaml_filename():
    matches = _qualifying_workflows(ROOT)
    assert matches
    workflow = matches[0].read_text(errors="replace")
    assert "make mpi" not in workflow
    assert "mingw-w64-ucrt-x86_64-msmpi" not in workflow


def test_windows_git_preflight_uses_native_powershell_and_asserts_attributes():
    matches = _qualifying_workflows(ROOT)
    assert matches
    workflow = matches[0].read_text(errors="replace")
    verify = workflow.index("name: Verify canonical fixture attributes")
    setup = workflow.index("name: Set up MSYS2 UCRT64")
    assert verify < setup
    block = workflow[verify:setup]
    assert "shell: pwsh" in block
    assert "git check-attr text --" in block
    assert "git check-attr binary --" in block
    assert "text: unset" in block
    assert "binary: set" in block
    assert "$LASTEXITCODE" in block
    assert "shell: msys2" not in block


def test_checker_does_not_hardcode_workflow_filename():
    checker = text("tools/qualification/check_windows_git_preflight_shell_closure_0_6_88_6_1_2_1.py")
    assert 'glob("*.yml")' in checker
    assert 'glob("*.yaml")' in checker
    assert 'read(root / ".github/workflows/cross-platform-qualification.yml")' not in checker
