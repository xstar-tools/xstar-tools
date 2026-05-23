from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import xstar_atomic as xa
from xstar_atomic.source_port import (
    REQUIRED_XSTAR_PRODUCTS,
    XSTARPythonAcceptanceError,
    ener_grid,
    normalize_xstar_parameters,
    parse_run_xstar_script,
    powerlaw_spectrum,
    run_c5_ne1_acceptance,
    run_output_writer_validation,
)
from xstar_atomic.source_port import physical_runner as runner


C5_COMMAND = r"""
xstar \
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \
  modelname='xstar_atomic_c5_xi1p5_ne1' abundtbl='xdef' \
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density=1 \
  rlrad38=1e6 column=1e+20 rlogxi=1.5 vturbi=100 \
  habund=1 heabund=1 liabund=0 beabund=0 babund=0 cabund=1 \
  nabund=0 oabund=0 fabund=0 neabund=0 naabund=0 mgabund=0 \
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0
"""


def _write_script(path: Path) -> Path:
    path.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")\"\n" + C5_COMMAND,
        encoding="utf-8",
    )
    return path


def test_v0472_public_api_exports_and_version():
    assert xa.__version__ == "0.4.74"
    assert callable(xa.run_xstar_python)
    assert callable(xa.run_xstar_python_command)
    assert callable(xa.run_xstar_python_script)
    assert callable(xa.run_xstar_from_parameters)


def test_v0472_c5_parameter_normalization_matches_rread1():
    parsed = runner._parse_literal_xstar_command(C5_COMMAND)
    result = normalize_xstar_parameters(parsed)
    assert result.lcdd == 1
    assert result.temperature_t4 == 100.0
    assert result.temperature_k == 1.0e6
    assert result.density_cm3 == 1.0
    assert result.ionization_parameter == pytest.approx(10.0 ** 1.5)
    assert result.initial_radius_cm == pytest.approx(np.sqrt(1.0e6 / (10.0 ** 1.5)) * 1.0e19)
    assert result.rmax_cm == pytest.approx(1.0e20)
    assert result.physical_abundances[0] == pytest.approx(1.0)
    assert result.physical_abundances[1] == pytest.approx(0.1)
    assert result.physical_abundances[5] == pytest.approx(3.7e-4)
    assert np.count_nonzero(result.physical_abundances) == 3


def test_v0472_source_energy_and_powerlaw_setup():
    epi = ener_grid(9999)
    assert epi.shape == (9999,)
    assert epi[0] == pytest.approx(0.1)
    assert epi[-1] > 1.0e6  # literal ener.f90 second-loop overshoot
    z = powerlaw_spectrum(index=-1.0, luminosity_1e38=1.0e6, epi_eV=epi)
    assert z.shape == epi.shape
    assert np.all(np.isfinite(z))
    assert np.all(z > 0.0)


def test_v0472_literal_56_row_fparmlist_contract():
    normalized = normalize_xstar_parameters(runner._parse_literal_xstar_command(C5_COMMAND))
    rows = runner._output_parameters(normalized)
    assert len(rows) == 56
    assert tuple(row.name for row in rows[:18]) == (
        "cfrac", "temperature", "lcpres", "pressure", "density",
        "spectrum", "spectrum_file", "spectun", "trad", "rlrad38",
        "column", "rlogxi", "nsteps", "niter", "lwrite", "lprint",
        "lstep", "abundtbl",
    )
    assert rows[5].parameter_type == "string" and rows[5].comment == "pow"
    assert rows[54].name == "modelname"
    assert rows[54].comment == "xstar_atomic_c5_xi1p5_ne1"
    assert rows[55].name == "loopcontrol"



def test_v0472_short_direct_api_uses_sparse_abundance_shorthand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    observed = {}

    def fake_run(parameters, **kwargs):
        observed.update(kwargs)
        observed["parameters"] = dict(parameters)
        return "sparse-result"

    monkeypatch.setattr(runner, "run_xstar_from_parameters", fake_run)
    result = runner.run_xstar_python(
        atdb_path=tmp_path / "atdb.fits",
        output_dir=tmp_path / "out",
        spectrum="pow",
        habund=1,
        heabund=1,
        cabund=1,
    )
    assert result == "sparse-result"
    assert observed["zero_unspecified_abundances"] is True
    assert observed["parameters"]["cabund"] == 1


def test_v0472_command_and_script_wrappers_never_launch_fortran(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    captured: list[object] = []

    def fake_run(parameters, **kwargs):
        captured.append((parameters, kwargs))
        return "python-only-result"

    monkeypatch.setattr(runner, "run_xstar_from_parameters", fake_run)
    assert runner.run_xstar_python_command(
        C5_COMMAND, atdb_path=tmp_path / "atdb.fits", output_dir=tmp_path / "command"
    ) == "python-only-result"
    script = _write_script(tmp_path / "run_xstar.sh")
    assert runner.run_xstar_python_script(
        script, atdb_path=tmp_path / "atdb.fits", output_dir=tmp_path / "script"
    ) == "python-only-result"
    assert len(captured) == 2
    assert captured[0][0].get("modelname") == "xstar_atomic_c5_xi1p5_ne1"
    assert parse_run_xstar_script(script).parameters["density"] == "1"


@dataclass
class _FakePythonRun:
    output_dir: Path
    ready: bool = True

    def close(self) -> None:
        pass

    def as_dict(self):
        return {
            "ready": self.ready,
            "output_dir": str(self.output_dir),
            "products": {name: str(self.output_dir / name) for name in REQUIRED_XSTAR_PRODUCTS},
            "completed_passes": 1,
            "completed_zones": 10,
            "source_order": [],
            "warnings": [],
            "provenance": {"xstar_outputs_used_as_python_inputs": False},
            "parameters": {},
        }


def _generated_products(root: Path) -> Path:
    summary = run_output_writer_validation(out_dir=root)
    return Path(summary["validation_root"]) / "generated_fits"


def test_v0472_c5_acceptance_runs_independent_products_then_direct_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    original = _generated_products(tmp_path / "original_generation")
    python = _generated_products(tmp_path / "python_generation")
    script = _write_script(tmp_path / "run_xstar.sh")

    def fake_python_script(*args, **kwargs):
        assert Path(args[0]) == script
        return _FakePythonRun(output_dir=python)

    monkeypatch.setattr(runner, "run_xstar_python_script", fake_python_script)
    result = run_c5_ne1_acceptance(
        run_script=script,
        atdb_path=tmp_path / "atdb.fits",
        python_output_dir=python,
        original_run_dir=original,
        raise_on_failure=True,
    )
    assert result.ready is True
    assert result.original_products_available is True
    assert result.all_ten_python_products_ready is True
    assert result.all_files_match is True
    assert tuple(result.parity.required_files) == REQUIRED_XSTAR_PRODUCTS
    assert result.as_dict()["xstar_outputs_used_as_python_inputs"] is False


def test_v0472_acceptance_refuses_missing_original_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    python = _generated_products(tmp_path / "python_generation")
    script = _write_script(tmp_path / "run_xstar.sh")
    monkeypatch.setattr(
        runner, "run_xstar_python_script", lambda *args, **kwargs: _FakePythonRun(output_dir=python)
    )
    with pytest.raises(XSTARPythonAcceptanceError, match="ten original XSTAR products"):
        run_c5_ne1_acceptance(
            run_script=script,
            atdb_path=tmp_path / "atdb.fits",
            python_output_dir=python,
            original_run_dir=tmp_path / "missing_original",
        )
