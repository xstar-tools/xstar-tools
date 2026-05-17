from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from xstar_atomic.source_port import (
    EscapeStateError,
    load_escape_state_from_xstar_run,
    write_escape_state_npz,
)
from xstar_atomic.source_port_element_cli import _load_escape_npz


def _write_radial(path: Path, columns_by_zone: list[list[fits.Column]]) -> None:
    hdus = [fits.PrimaryHDU()]
    for columns in columns_by_zone:
        hdus.append(fits.BinTableHDU.from_columns(columns, name="XSTAR_RADIAL"))
    fits.HDUList(hdus).writeto(path)


def test_escape_state_maps_detal2_and_detal3_indices_and_selects_last_zone(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    _write_radial(
        run / "xo01_detal2.fits",
        [
            [
                fits.Column(name="index", format="J", array=np.asarray([1], dtype=np.int32)),
                fits.Column(name="tau_in", format="D", array=np.asarray([1.0])),
                fits.Column(name="tau_out", format="D", array=np.asarray([2.0])),
            ],
            [
                fits.Column(name="index", format="J", array=np.asarray([1, 3], dtype=np.int32)),
                fits.Column(name="tau_in", format="D", array=np.asarray([0.1, 0.3])),
                fits.Column(name="tau_out", format="D", array=np.asarray([0.2, 0.4])),
            ],
        ],
    )
    _write_radial(
        run / "xo01_detal3.fits",
        [
            [
                fits.Column(name="rrc index", format="J", array=np.asarray([1], dtype=np.int32)),
                fits.Column(name="tau_in", format="D", array=np.asarray([5.0])),
                fits.Column(name="tau_out", format="D", array=np.asarray([6.0])),
            ],
            [
                fits.Column(name="rrc index", format="J", array=np.asarray([2], dtype=np.int32)),
                fits.Column(name="tau_in", format="D", array=np.asarray([0.5])),
                fits.Column(name="tau_out", format="D", array=np.asarray([0.6])),
            ],
        ],
    )
    derived = SimpleNamespace(nlsvn=4, ncsvn=3)
    result = load_escape_state_from_xstar_run(run, derived, zone="last")
    assert result.line_hdu_index == 2
    assert result.rrc_hdu_index == 2
    assert result.n_line_indices_loaded == 2
    assert result.n_rrc_indices_loaded == 1
    assert result.n_line_indices_missing == 2
    assert result.n_rrc_indices_missing == 2
    assert result.context.line_taus(1) == pytest.approx((0.1, 0.2))
    assert result.context.line_taus(2) == (None, None)
    assert result.context.line_taus(3) == pytest.approx((0.3, 0.4))
    assert result.context.continuum_taus(2) == pytest.approx((0.5, 0.6))

    target = write_escape_state_npz(result, tmp_path / "escape.npz")
    loaded = _load_escape_npz(str(target), False)
    assert loaded.line_taus(1) == pytest.approx((0.1, 0.2))
    assert loaded.line_taus(2) == (None, None)
    assert loaded.continuum_taus(2) == pytest.approx((0.5, 0.6))


def test_escape_state_requires_both_source_detail_files(tmp_path: Path):
    derived = SimpleNamespace(nlsvn=1, ncsvn=1)
    with pytest.raises(EscapeStateError, match="xo01_detal2.fits"):
        load_escape_state_from_xstar_run(tmp_path, derived)


def test_missing_escape_npz_has_actionable_error(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="--xstar-run-dir"):
        _load_escape_npz(str(tmp_path / "not-created.npz"), False)
