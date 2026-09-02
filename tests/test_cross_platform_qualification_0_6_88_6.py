from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def text(path):
    return (ROOT / path).read_text()


def test_version_metadata():
    assert 'version = "0.6.88.6"' in text("pyproject.toml")
    assert "PACKAGE_VERSION ?= 0.6.88.6" in (CPP / "Makefile").read_text()
    assert 'kPackageVersion = "0.6.88.6"' in (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert 'kPackageVersion = "0.6.88.6"' in (CPP / "xstar_xspec_mpi.cpp").read_text()


def test_windows_user_guide_is_indexed_and_actionable():
    guide = text("docs/user/windows_installation_and_usage.md")
    assert "MSYS2 UCRT64" in guide
    assert "mingw-w64-ucrt-x86_64-cfitsio" in guide
    assert "make -j4 PLATFORM=windows xstar-cpp.exe" in guide
    assert "c5_ne1e8.par" in guide
    assert "--processes 2" in guide
    assert "windows_installation_and_usage" in text("docs/user/index.md")


def test_cross_platform_design_is_indexed():
    assert "CROSS_PLATFORM_QUALIFICATION" in text("cross_platform_qualification_0_6_88_6.md")
    assert "cross_platform_qualification_0_6_88_6" in text("docs/developer/index.md")
    assert "CROSS_PLATFORM_QUALIFICATION" in text("docs/developer/cross_platform_qualification_0_6_88_6.md")


def test_windows_predecessor_acceptance_is_recorded():
    record = text("xstar_tools-0.6.88.5.7_formal_host_acceptance.md")
    assert "formally accepted" in record.lower()
    assert "warning-free" in record
    assert "MSYS2 UCRT64" in record


def test_cross_platform_workflow_has_four_targets():
    workflow = text(".github/workflows/cross-platform-qualification.yml")
    for token in ("ubuntu-24.04", "macos-15", "macos-15-intel", "windows-latest", "UCRT64"):
        assert token in workflow
    assert "run_cross_platform_qualification_host_0_6_88_6.py" in workflow


def test_runner_carries_frozen_fixed_state_hashes():
    runner = text("tools/qualification/run_cross_platform_qualification_host_0_6_88_6.py")
    assert "5508313e40d514d63b4d5443bc67198fe1a62a82f76f428958e6a5ea07cafa38" in runner
    assert "e430573df3bd1666fef4b3e5e8305f0b912e06456685aa921f4737f305e875f4" in runner
    assert "7d1addd4a66f29eda03d96954f8f07b3aa5bd627e8d506d84a3079f47474c3a3" in runner


def test_runner_requires_warning_free_build_and_regression():
    runner = text("tools/qualification/run_cross_platform_qualification_host_0_6_88_6.py")
    assert "WARNING_FREE_BUILD" in runner
    assert "FIXED_STATE_HASHES" in runner
    assert "PYTHON_BACKEND_SELF_TEST" in runner
    assert "PYTHON_BRIDGE_TEST" in runner
    assert "REGRESSION" in runner


def test_portable_process_smoke_fixture():
    src = text("tests/cross_platform_process_smoke_0_6_88_6.cpp")
    assert "xstar_process::spawn_program" in src
    assert "xstar_process::wait_process" in src
    assert "CROSS_PLATFORM_PROCESS_SMOKE_06886_RESULT=ACCEPT" in src


def test_portable_xspec_fake_fixture_is_scheduler_only():
    src = text("tests/cross_platform_xspec_fake_tool_0_6_88_6.cpp")
    assert '"xstinitable.fits"' in src
    assert '"xout_mtable.fits"' in src
    assert '"xout_step.log"' in src
    assert '"fake\\n"' in src


def test_windows_mpi_remains_out_of_scope():
    guide = text("docs/user/windows_installation_and_usage.md")
    design = text("cross_platform_qualification_0_6_88_6.md")
    assert "Windows MPI remains out of scope" in guide
    assert "Windows MPI remains out of scope" in design
