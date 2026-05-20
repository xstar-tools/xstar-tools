from __future__ import annotations

import csv
import subprocess
from pathlib import Path

from xstar_atomic.xstar_dsec_probe import (
    dsec_insertion_snippets,
    dsec_probe_helper,
    write_dsec_probe_products,
)


def test_dsec_probe_has_all_control_flow_hooks() -> None:
    helper = dsec_probe_helper()
    snippets = dsec_insertion_snippets()
    assert "xstar_dsec_trajectory_probe.csv" in helper
    assert "XSTAR_ATOMIC_DSEC_TARGET_CALL" in helper
    assert set(snippets) == {
        "dsec_begin", "after_calc_hmc_all", "charge_multiply",
        "charge_divide", "charge_secant", "charge_loop_exit",
        "temperature_divide", "temperature_multiply",
        "temperature_stagnation", "temperature_secant",
        "too_many_iterations", "finish",
    }


def test_generated_dsec_probe_helper_compiles(tmp_path: Path) -> None:
    products = write_dsec_probe_products(tmp_path)
    helper = products["helper_fortran"]
    completed = subprocess.run(
        ["gfortran", "-c", "-ffree-line-length-none", str(helper), "-o", str(tmp_path / "helper.o")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "helper.o").is_file()



def test_generated_dsec_probe_helper_writes_parseable_csv(tmp_path: Path) -> None:
    products = write_dsec_probe_products(tmp_path)
    driver = tmp_path / "test_driver.f90"
    driver.write_text(
        """program test
  implicit none
  call xap_dsec_begin(10,10,10,10,10,1.d0,0.01d0,1.2d0,1.d8, &
      0.d0,0.d0,0.d0,1.d0,1.d0,-1.d0,0.d0,0.d0,1.d30,0,0,0,0,0)
  call xap_dsec_event('after_calc_hmc_all',1,1,1,1,0,0,10,10,10,10,10, &
      1.d0,0.01d0,1.2d0,1.d8,0.d0,0.d0,0.d0,1.d0,0.2d0,1.d0,-1.d0, &
      0.1d0,0.d0,0.d0,1.d30,0.166d0,huge(1.d0),0,0,0,0,0,0,0)
end program
""",
        encoding="utf-8",
    )
    executable = tmp_path / "test_driver"
    compiled = subprocess.run(
        [
            "gfortran",
            "-ffree-line-length-none",
            str(products["helper_fortran"]),
            str(driver),
            "-o",
            str(executable),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert compiled.returncode == 0, compiled.stderr
    completed = subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "XSTAR_ATOMIC_DSEC_TARGET_CALL": "1"},
    )
    assert completed.returncode == 0, completed.stderr
    with (tmp_path / "xstar_dsec_trajectory_probe.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert [row["event"].strip() for row in rows] == [
        "begin",
        "after_calc_hmc_all",
    ]
    assert len(rows[0]) == 39
