from pathlib import Path
import csv

from xstar_atomic.xstar_element_basis_remap import (
    audit_element_basis_remap,
    write_element_basis_remap_products,
)


def _write_csv(path, fields, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def test_element_basis_remap_maps_parent_alias_and_final_slot(tmp_path):
    bench = tmp_path / "bench" / "solver_products" / "o_vii"
    bench.mkdir(parents=True)
    _write_csv(
        bench / "xstar_like_element_solver_global_index.csv",
        ["global_index","element","element_z","ion_stage","level_index","level_kind","level_label","is_continuum","is_superlevel"],
        [
            {"global_index":0,"element":"O","element_z":8,"ion_stage":7,"level_index":1,"level_kind":"spectroscopic","level_label":"o7g","is_continuum":False,"is_superlevel":False},
            {"global_index":1,"element":"O","element_z":8,"ion_stage":7,"level_index":3,"level_kind":"continuum","level_label":"continuum","is_continuum":True,"is_superlevel":False},
            {"global_index":2,"element":"O","element_z":8,"ion_stage":8,"level_index":1,"level_kind":"spectroscopic","level_label":"o8g","is_continuum":False,"is_superlevel":False},
            {"global_index":3,"element":"O","element_z":8,"ion_stage":8,"level_index":2,"level_kind":"spectroscopic","level_label":"continuum","is_continuum":False,"is_superlevel":False},
        ],
    )
    probe = tmp_path / "xstar_element_basis_probe.csv"
    fields = ["basis_solve_call_id","basis_capture_index","row_kind","ml_element","element_z","nionp_current","nsp_current","ml_ion","klion","jkk_ion","nlev","ion_start_ipmat2","ion_start_ipmat","local_level_index","element_ipmat_index","xstar_ipmat2_index","x_population","nsup","nion","t_xstar_1e4K","xee","xpx","cfrac"]
    rows = [
        {"basis_solve_call_id":1,"basis_capture_index":1,"row_kind":"basis_begin","ml_element":10,"element_z":8,"nionp_current":-1,"nsp_current":-1,"ml_ion":-1,"klion":-1,"jkk_ion":-1,"nlev":-1,"ion_start_ipmat2":-1,"ion_start_ipmat":-1,"local_level_index":-1,"element_ipmat_index":-1,"xstar_ipmat2_index":-1,"x_population":0,"nsup":-1,"nion":-1,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
        {"basis_solve_call_id":1,"basis_capture_index":2,"row_kind":"ion_population_row","ml_element":10,"element_z":8,"nionp_current":7,"nsp_current":1,"ml_ion":70,"klion":7,"jkk_ion":7,"nlev":3,"ion_start_ipmat2":0,"ion_start_ipmat":0,"local_level_index":1,"element_ipmat_index":1,"xstar_ipmat2_index":1,"x_population":0.2,"nsup":1,"nion":7,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
        {"basis_solve_call_id":1,"basis_capture_index":3,"row_kind":"ion_population_row","ml_element":10,"element_z":8,"nionp_current":7,"nsp_current":1,"ml_ion":70,"klion":7,"jkk_ion":7,"nlev":3,"ion_start_ipmat2":0,"ion_start_ipmat":0,"local_level_index":2,"element_ipmat_index":2,"xstar_ipmat2_index":2,"x_population":0.0,"nsup":1,"nion":7,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
        {"basis_solve_call_id":1,"basis_capture_index":4,"row_kind":"ion_parent_continuum_link","ml_element":10,"element_z":8,"nionp_current":7,"nsp_current":1,"ml_ion":70,"klion":7,"jkk_ion":7,"nlev":3,"ion_start_ipmat2":0,"ion_start_ipmat":0,"local_level_index":3,"element_ipmat_index":3,"xstar_ipmat2_index":3,"x_population":0.7,"nsup":-1,"nion":-1,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
        {"basis_solve_call_id":1,"basis_capture_index":5,"row_kind":"ion_population_row","ml_element":10,"element_z":8,"nionp_current":8,"nsp_current":2,"ml_ion":80,"klion":8,"jkk_ion":8,"nlev":2,"ion_start_ipmat2":2,"ion_start_ipmat":3,"local_level_index":1,"element_ipmat_index":4,"xstar_ipmat2_index":3,"x_population":0.7,"nsup":2,"nion":8,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
        {"basis_solve_call_id":1,"basis_capture_index":6,"row_kind":"ion_parent_continuum_link","ml_element":10,"element_z":8,"nionp_current":8,"nsp_current":2,"ml_ion":80,"klion":8,"jkk_ion":8,"nlev":2,"ion_start_ipmat2":2,"ion_start_ipmat":3,"local_level_index":2,"element_ipmat_index":5,"xstar_ipmat2_index":4,"x_population":0.1,"nsup":-1,"nion":-1,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
        {"basis_solve_call_id":1,"basis_capture_index":7,"row_kind":"final_parent_continuum_slot","ml_element":10,"element_z":8,"nionp_current":8,"nsp_current":3,"ml_ion":-1,"klion":-1,"jkk_ion":-1,"nlev":-1,"ion_start_ipmat2":-1,"ion_start_ipmat":-1,"local_level_index":-1,"element_ipmat_index":-1,"xstar_ipmat2_index":4,"x_population":0.1,"nsup":3,"nion":8,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
    ]
    _write_csv(probe, fields, rows)
    audit = audit_element_basis_remap(benchmark_dir=tmp_path/"bench", ion="O VII", element_basis_probe_csv=probe, occurrence_rank=-1)
    s = audit["summary"]
    assert s["n_unique_xstar_basis_rows"] == 4
    assert s["n_python_rows_mapped_by_ion_stage_level"] == 4
    assert s["n_python_alias_groups"] == 1
    remap = audit["python_remap_rows"]
    assert [r["corrected_xstar_ipmat2_index"] for r in remap] == [1,3,3,4]
    assert s["source_equivalent_basis_mapping_ready"] is True
    paths = write_element_basis_remap_products(tmp_path/"out", audit)
    assert Path(paths["python_remap_csv"]).exists()


def test_element_basis_remap_population_coverage(tmp_path):
    bench = tmp_path / "bench" / "solver_products" / "o_vii"
    bench.mkdir(parents=True)
    _write_csv(bench / "xstar_like_element_solver_global_index.csv", ["global_index","element","element_z","ion_stage","level_index","level_kind","level_label"], [
        {"global_index":0,"element":"O","element_z":8,"ion_stage":8,"level_index":1,"level_kind":"spectroscopic","level_label":"g"},
    ])
    probe = tmp_path / "xstar_element_basis_probe.csv"
    fields = ["basis_solve_call_id","basis_capture_index","row_kind","ml_element","element_z","nionp_current","nsp_current","ml_ion","klion","jkk_ion","nlev","ion_start_ipmat2","ion_start_ipmat","local_level_index","element_ipmat_index","xstar_ipmat2_index","x_population","nsup","nion","t_xstar_1e4K","xee","xpx","cfrac"]
    _write_csv(probe, fields, [
        {"basis_solve_call_id":5,"basis_capture_index":1,"row_kind":"basis_begin","ml_element":10,"element_z":8,"nionp_current":-1,"nsp_current":-1,"ml_ion":-1,"klion":-1,"jkk_ion":-1,"nlev":-1,"ion_start_ipmat2":-1,"ion_start_ipmat":-1,"local_level_index":-1,"element_ipmat_index":-1,"xstar_ipmat2_index":-1,"x_population":0,"nsup":-1,"nion":-1,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
        {"basis_solve_call_id":5,"basis_capture_index":2,"row_kind":"ion_population_row","ml_element":10,"element_z":8,"nionp_current":8,"nsp_current":1,"ml_ion":80,"klion":8,"jkk_ion":8,"nlev":2,"ion_start_ipmat2":0,"ion_start_ipmat":0,"local_level_index":1,"element_ipmat_index":1,"xstar_ipmat2_index":1,"x_population":0,"nsup":1,"nion":8,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
        {"basis_solve_call_id":5,"basis_capture_index":3,"row_kind":"ion_parent_continuum_link","ml_element":10,"element_z":8,"nionp_current":8,"nsp_current":1,"ml_ion":80,"klion":8,"jkk_ion":8,"nlev":2,"ion_start_ipmat2":0,"ion_start_ipmat":0,"local_level_index":2,"element_ipmat_index":2,"xstar_ipmat2_index":2,"x_population":0,"nsup":-1,"nion":-1,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
        {"basis_solve_call_id":5,"basis_capture_index":4,"row_kind":"final_parent_continuum_slot","ml_element":10,"element_z":8,"nionp_current":8,"nsp_current":2,"ml_ion":-1,"klion":-1,"jkk_ion":-1,"nlev":-1,"ion_start_ipmat2":-1,"ion_start_ipmat":-1,"local_level_index":-1,"element_ipmat_index":-1,"xstar_ipmat2_index":2,"x_population":0,"nsup":2,"nion":8,"t_xstar_1e4K":100,"xee":1,"xpx":1e8,"cfrac":1},
    ])
    pop = tmp_path / "xstar_population_closure_probe.csv"
    _write_csv(pop, ["capture_index","solve_call_id","stage","level_index","x_population","nion","nsup"], [
        {"capture_index":1,"solve_call_id":5,"stage":"after_msolvelucy","level_index":1,"x_population":0.8,"nion":8,"nsup":1},
        {"capture_index":1,"solve_call_id":5,"stage":"after_msolvelucy","level_index":2,"x_population":0.2,"nion":8,"nsup":2},
    ])
    audit = audit_element_basis_remap(benchmark_dir=tmp_path/"bench", ion="O VII", element_basis_probe_csv=probe, population_probe_csv=pop, basis_solve_call_id=5)
    s = audit["summary"]
    assert abs(s["xstar_after_population_on_corrected_python_mapped_rows"] - 0.8) < 1e-12
    assert abs(s["xstar_after_population_on_unrepresented_basis_rows"] - 0.2) < 1e-12
