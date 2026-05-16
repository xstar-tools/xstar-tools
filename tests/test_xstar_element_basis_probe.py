from pathlib import Path
import subprocess

from xstar_atomic.xstar_element_basis_probe import (
    element_basis_fortran_helper,
    summarize_element_basis_probe_csv,
    write_element_basis_probe_products,
)


def test_element_basis_probe_prepare_no_csv(tmp_path):
    audit = summarize_element_basis_probe_csv(None)
    assert audit["summary"]["status"] == "csv_not_supplied"
    paths = write_element_basis_probe_products(tmp_path, audit)
    assert Path(paths["helper_fortran"]).exists()
    assert Path(paths["basis_begin_insertion"]).read_text().count("xap_basis_begin") == 1
    assert Path(paths["basis_ion_rows_insertion"]).read_text().count("xap_basis_ion") == 1
    assert Path(paths["basis_final_row_insertion"]).read_text().count("xap_basis_final") == 1


def test_element_basis_probe_validate_minimal_csv(tmp_path):
    p = tmp_path / "xstar_element_basis_probe.csv"
    p.write_text(
        "basis_solve_call_id,basis_capture_index,row_kind,ml_element,element_z,nionp_current,nsp_current,"
        "ml_ion,klion,jkk_ion,nlev,ion_start_ipmat2,ion_start_ipmat,local_level_index,"
        "element_ipmat_index,xstar_ipmat2_index,x_population,nsup,nion,t_xstar_1e4K,xee,xpx,cfrac\n"
        "1,1,basis_begin,100,8,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,0,-1,-1,100,1,1e8,1\n"
        "1,2,ion_population_row,100,8,1,1,200,1,7,3,0,0,1,1,1,0.5,1,1,100,1,1e8,1\n"
        "1,3,ion_parent_continuum_link,100,8,1,1,200,1,7,3,0,0,3,3,3,0.0,-1,-1,100,1,1e8,1\n"
        "1,4,final_parent_continuum_slot,100,8,1,2,-1,-1,-1,-1,-1,-1,-1,-1,3,0.5,2,1,100,1,1e8,1\n",
        encoding="utf-8",
    )
    audit = summarize_element_basis_probe_csv(p)
    s = audit["summary"]
    assert s["status"] == "csv_loaded_ready"
    assert s["n_ready_basis_solve_calls"] == 1
    assert s["n_parent_continuum_link_rows"] == 1
    assert audit["solve_summary"][0]["n_unique_solver_population_rows"] == 2


def test_element_basis_helper_syntax_compiles_when_gfortran_available(tmp_path):
    src = tmp_path / "xstar_atomic_element_basis_probe_helpers.f90"
    src.write_text(element_basis_fortran_helper(), encoding="utf-8")
    try:
        result = subprocess.run(["gfortran", "-c", str(src)], cwd=tmp_path, text=True, capture_output=True)
    except FileNotFoundError:
        return
    assert result.returncode == 0, result.stderr
