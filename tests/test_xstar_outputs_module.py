def test_xstar_outputs_module_imports():
    import pytest
    pytest.importorskip("astropy")
    from xstar_atomic import xstar_outputs

    assert hasattr(xstar_outputs, "read_xout_lines")
    assert hasattr(xstar_outputs, "convert_xout_lines")


def test_xstar_outputs_filter_rows():
    import pytest
    pytest.importorskip("astropy")
    from xstar_atomic.xstar_outputs import filter_rows, summarize_lines

    rows = [
        {"ion": "O VIII", "wavelength": 18.97, "emit_outward": 1.0, "emit_inward": 0.0},
        {"ion": "Ne IX", "wavelength": 13.45, "emit_outward": 0.0, "emit_inward": 0.0},
    ]
    selected = filter_rows(rows, ion="O VIII", wavelength_min=18.8, wavelength_max=19.1)
    assert len(selected) == 1
    summary = summarize_lines(selected, "dummy.fits")
    assert summary["n_lines"] == 1
    assert summary["counts_by_ion"]["O VIII"] == 1
