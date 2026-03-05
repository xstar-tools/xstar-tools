import os
import pytest


def test_solver_summary_uses_xstar_same_n_status(tmp_path):
    pytest.importorskip("astropy")
    fitsfile = os.environ.get("XSTAR_ATDB_FITS")
    if not fitsfile:
        pytest.skip("Set XSTAR_ATDB_FITS to run real solver status test")

    from xstar_atomic.solver import main

    out = tmp_path / "lines.csv"
    summary = tmp_path / "summary.json"
    main([
        fitsfile,
        "--element", "O",
        "--ion-stage", "8",
        "--wavelength-min", "18.8",
        "--wavelength-max", "19.1",
        "--temperatures", "1e6",
        "--electron-densities", "1.0",
        "--component-mode", "ground",
        "--out-lines-csv", str(out),
        "--summary-json", str(summary),
    ])
    import json
    data = json.loads(summary.read_text())
    assert data["same_n_lmixing_status"] == "xstar_amcrs_collision_decoder_enabled"
