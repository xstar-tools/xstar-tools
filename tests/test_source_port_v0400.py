from __future__ import annotations

import io
import tarfile
from pathlib import Path

import numpy as np
import pytest

from xstar_atomic.source_port import (
    FortranArray,
    FortranRuntimeError,
    PortStatus,
    UCalcBranch,
    UCalcDispatcher,
    UnportedXSTARRoutine,
    XSTARPythonDriver,
    XSTARStage,
    build_source_inventory,
    default_port_ledger,
    fortran_mod,
    fortran_nint,
)


def test_fortran_array_uses_one_based_indices():
    arr = FortranArray.zeros((3, 2))
    arr[1, 1] = 4.0
    arr[3, 2] = 7.0
    assert arr.fortran_shape == (3, 2)
    assert arr[1, 1] == 4.0
    assert arr.active_view().shape == (3, 2)
    with pytest.raises(FortranRuntimeError):
        _ = arr[0, 1]


def test_fortran_intrinsics_preserve_source_semantics():
    assert fortran_nint(1.5) == 2
    assert fortran_nint(-1.5) == -2
    assert fortran_mod(-5, 3) == -2


def test_source_inventory_from_tar(tmp_path: Path):
    tar_path = tmp_path / "source.tar.gz"
    source = b"""
subroutine alpha(x)
  use globals
  call beta(x)
end subroutine alpha
function beta(x)
  beta=x
end function beta
"""
    with tarfile.open(tar_path, "w:gz") as archive:
        info = tarfile.TarInfo("xstar/src/alpha.f90")
        info.size = len(source)
        archive.addfile(info, io.BytesIO(source))
    inventory = build_source_inventory(source_tar=str(tar_path))
    assert inventory.n_files == 1
    assert {r.name for r in inventory.routines} == {"alpha", "beta"}
    assert inventory.files[0].calls == ("beta",)


def test_driver_fails_at_first_unported_stage():
    driver = XSTARPythonDriver()
    driver.register(XSTARStage.SETUP, lambda state: state.control.update(setup=True))
    with pytest.raises(UnportedXSTARRoutine) as exc:
        driver.run()
    assert exc.value.stage is XSTARStage.READ_ATOMIC_DATABASE


def test_driver_runs_registered_source_order():
    driver = XSTARPythonDriver()
    order = []
    for stage in XSTARStage:
        driver.register(stage, lambda state, stage=stage: order.append(stage))
    state = driver.run()
    assert order[0] is XSTARStage.SETUP
    assert order[-1] is XSTARStage.OUTPUT
    assert state.provenance["completed_stages"][0] == "setup"


def test_ucalc_registry_is_explicit():
    dispatcher = UCalcDispatcher()
    dispatcher.register(UCalcBranch(999, ("dummy.f90",), lambda x: x + 1, "test"))
    assert dispatcher.evaluate(999, 4) == 5
    with pytest.raises(NotImplementedError):
        dispatcher.evaluate(998, 4)


def test_default_ledger_is_conservative():
    ledger = default_port_ledger()
    statuses = ledger.status_counts()
    assert statuses[PortStatus.VALIDATED.value] >= 1
    assert any(
        entry.routine == "xstar" and entry.status is PortStatus.SCAFFOLD
        for entry in ledger.entries
    )
