from pathlib import Path
import csv

from xstar_atomic.xstar_population_closure_probe import (
    population_closure_probe_schema_rows,
    population_closure_fortran_helper,
    summarize_population_closure_probe_csv,
    write_population_closure_probe_products,
)


def test_population_closure_probe_schema_and_helper(tmp_path):
    rows = population_closure_probe_schema_rows()
    cols = {r["column"] for r in rows}
    assert "stage" in cols
    assert "x_population" in cols
    helper = population_closure_fortran_helper()
    assert "subroutine xap_pbefore" in helper
    assert "subroutine xap_pafter" in helper
    assert "subroutine xap_pstate" in helper
    assert "xstar_population_closure_probe.csv" not in helper  # filename is supplied by call site
    paths = write_population_closure_probe_products(tmp_path)
    assert Path(paths["helper_fortran"]).exists()
    assert Path(paths["before_msolvelucy_insertion"]).read_text().count("before_msolvelucy") >= 1
    assert Path(paths["after_msolvelucy_insertion"]).read_text().count("after_msolvelucy") >= 1


def test_population_closure_probe_summary_ready(tmp_path):
    p = tmp_path / "xstar_population_closure_probe.csv"
    fields = [
        "capture_index", "stage", "ml_element", "element_z", "ipmat2", "nsp", "nionp",
        "nindbe", "nit", "nit2", "nit3", "level_index", "x_population", "nsup", "nion",
        "t_xstar_1e4K", "xee", "xpx", "cfrac",
    ]
    rows = []
    for cap, stage, nit in [(1, "before_msolvelucy", 0), (2, "after_msolvelucy", 4)]:
        for i, x in [(1, 0.2), (2, 0.3), (3, 0.5)]:
            rows.append({
                "capture_index": cap, "stage": stage, "ml_element": 123, "element_z": 8,
                "ipmat2": 3, "nsp": 2, "nionp": 1, "nindbe": 10, "nit": nit,
                "nit2": 0, "nit3": 0, "level_index": i, "x_population": x,
                "nsup": min(i, 2), "nion": 1, "t_xstar_1e4K": 100.0, "xee": 1.0,
                "xpx": 1.0e8, "cfrac": 1.0,
            })
    with p.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    summary = summarize_population_closure_probe_csv(p)
    assert summary["status"] == "csv_loaded_ready"
    assert summary["probe_ready_for_population_closure_parity"] is True
    assert summary["n_before_after_pairs"] == 1
    assert summary["n_bad_ipmat2_captures"] == 0



def test_population_closure_probe_summary_salvages_legacy_extra_after(tmp_path):
    p = tmp_path / "xstar_population_closure_probe.csv"
    fields = [
        "capture_index", "stage", "ml_element", "element_z", "ipmat2", "nsp", "nionp",
        "nindbe", "nit", "nit2", "nit3", "level_index", "x_population", "nsup", "nion",
        "t_xstar_1e4K", "xee", "xpx", "cfrac",
    ]
    rows = []
    # A bad stale/extra after capture with merged rows.
    for i, x in [(1, 0.2), (2, 0.8), (3, 1.0), (4, 0.0)]:
        rows.append({
            "capture_index": 1, "stage": "after_msolvelucy", "ml_element": 999, "element_z": 8,
            "ipmat2": 2, "nsp": 2, "nionp": 1, "nindbe": 10, "nit": 2,
            "nit2": 0, "nit3": 0, "level_index": i, "x_population": x,
            "nsup": 1, "nion": 1, "t_xstar_1e4K": 100.0, "xee": 1.0,
            "xpx": 1.0e8, "cfrac": 1.0,
        })
    for cap, stage, nit, vals in [
        (2, "before_msolvelucy", 0, [0.2, 0.3, 0.5]),
        (3, "after_msolvelucy", 4, [0.1, 0.2, 0.7]),
    ]:
        for i, x in enumerate(vals, start=1):
            rows.append({
                "capture_index": cap, "stage": stage, "ml_element": 123, "element_z": 8,
                "ipmat2": 3, "nsp": 2, "nionp": 1, "nindbe": 10, "nit": nit,
                "nit2": 0, "nit3": 0, "level_index": i, "x_population": x,
                "nsup": min(i, 2), "nion": 1, "t_xstar_1e4K": 100.0, "xee": 1.0,
                "xpx": 1.0e8, "cfrac": 1.0,
            })
    with p.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    summary = summarize_population_closure_probe_csv(p)
    assert summary["probe_ready_for_population_closure_parity"] is True
    assert summary["status"] == "csv_loaded_ready_with_unpaired_or_bad_extra_captures"
    assert summary["n_before_after_pairs"] == 1
    assert summary["n_bad_ipmat2_captures"] == 1
    assert summary["n_paired_bad_ipmat2_captures"] == 0
