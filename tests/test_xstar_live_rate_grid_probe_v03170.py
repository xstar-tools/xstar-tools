from pathlib import Path

from xstar_atomic.xstar_live_rate_grid_probe import (
    LIVE_RATE_GRID_REQUIRED_COLUMNS,
    live_rate_grid_probe_schema_rows,
    prepare_live_rate_grid_probe_products,
    read_live_rate_grid_probe_csv,
    summarize_live_rate_grid_probe_csv,
)


def test_live_rate_grid_probe_schema_contains_required_columns():
    rows = live_rate_grid_probe_schema_rows()
    cols = {r["column"] for r in rows}
    for col in LIVE_RATE_GRID_REQUIRED_COLUMNS:
        assert col in cols


def test_live_rate_grid_probe_reader_groups_states(tmp_path):
    csv_path = tmp_path / "probe.csv"
    csv_path.write_text(
        "zone_index,pass_index,ldir,grid_index,ncn2m,epim_eV,bremsam,bremsint\n"
        "5,1,1,1,2,10.0,1.0e-3,2.0e-3\n"
        "5,1,1,2,2,20.0,2.0e-3,3.0e-3\n",
        encoding="utf-8",
    )
    states = read_live_rate_grid_probe_csv(csv_path)
    assert len(states) == 1
    st = states[0]
    assert st.zone_index == 5
    assert st.ncn2m == 2
    assert st.epim_eV == (10.0, 20.0)
    assert st.bremsam == (1.0e-3, 2.0e-3)
    summary = summarize_live_rate_grid_probe_csv(csv_path)
    assert summary["probe_status"] == "probe_csv_loaded"
    assert summary["probe_ready_for_type53_phint53_live_bremsam_audit"] is True


def test_prepare_live_rate_grid_probe_products(tmp_path):
    outputs = prepare_live_rate_grid_probe_products(tmp_path)
    for key in ["schema_csv", "fortran_template", "json", "markdown"]:
        assert Path(outputs[key]).exists()
    text = Path(outputs["fortran_template"]).read_text(encoding="utf-8")
    assert "bremsam" in text
    assert "after the xstarcalc.f90 call to bremsmap" in text
