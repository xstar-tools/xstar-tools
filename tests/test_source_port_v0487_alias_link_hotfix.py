from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from xstar_atomic.xstar_zone1_dsec_probe import zone1_extra_helper


def test_v0487_alias_reset_is_external_and_uses_module_state():
    helper = zone1_extra_helper()
    assert "module xap_zone1_alias_probe_state" in helper
    assert "contains\n  subroutine xap_zone1_alias_reset" not in helper
    assert "subroutine xap_zone1_alias_reset()\n  use xap_zone1_alias_probe_state" in helper


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran unavailable")
def test_v0487_alias_reset_external_symbol_links(tmp_path: Path):
    # Compile the exact generated alias-state block plus a caller that uses the
    # external call form present in calc_hmc_all.f90.
    helper = zone1_extra_helper()
    start = helper.index("module xap_zone1_alias_probe_state")
    end = helper.index("subroutine xap_zone1_hydrogen_state", start)
    unit = tmp_path / "alias_helper.f90"
    unit.write_text(helper[start:end], encoding="utf-8")
    caller = tmp_path / "caller.f90"
    caller.write_text(
        "program alias_link_test\n"
        "  implicit none\n"
        "  call xap_zone1_alias_reset()\n"
        "end program alias_link_test\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["gfortran", str(unit), str(caller), "-o", str(tmp_path / "alias_link_test")],
        check=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
