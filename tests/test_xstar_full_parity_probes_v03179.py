from pathlib import Path
import shutil
import subprocess

from xstar_atomic.xstar_full_parity_probes import prepare_full_parity_probe_products


def test_full_parity_helper_has_backward_compatible_wrappers(tmp_path: Path):
    result = prepare_full_parity_probe_products(out_dir=tmp_path)
    helper = Path(result["paths"]["helper_fortran"])
    text = helper.read_text(encoding="utf-8")
    assert result["summary"]["audit_version"] == "v0.3.179"
    assert "subroutine xap_ucalc" in text
    assert "subroutine xap_mrow" in text
    assert "subroutine xstar_atomic_probe_ucalc_record" in text
    assert "subroutine xstar_atomic_probe_matrix_row" in text

    gfortran = shutil.which("gfortran")
    if gfortran is not None:
        subprocess.run([gfortran, "-c", str(helper), "-o", str(tmp_path / "helper.o")], check=True)
