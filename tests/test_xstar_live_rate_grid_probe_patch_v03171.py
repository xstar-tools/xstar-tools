from pathlib import Path

from xstar_atomic.xstar_live_rate_grid_probe import (
    live_rate_grid_probe_fortran_helper,
    live_rate_grid_probe_xstarcalc_insertion_block,
    locate_xstarcalc_bremsmap_site,
    prepare_live_rate_grid_probe_patch_products,
)


def test_fortran_helper_contains_header_and_bremsam():
    text = live_rate_grid_probe_fortran_helper()
    assert "xstar_atomic_write_live_rate_grid_probe" in text
    assert "zone_index,pass_index,ldir," in text
    assert "grid_index,ncn2m,epim_eV," in text
    assert "bremsam(jk)" in text
    assert "xee" not in text  # helper receives already computed electron density


def test_insertion_block_uses_expected_xstarcalc_units():
    text = live_rate_grid_probe_xstarcalc_insertion_block(zone_expression="izone")
    assert "after bremsmap" in text
    assert "izone" in text
    assert "t*1.d4" in text
    assert "xee*xpx" in text


def test_locate_xstarcalc_bremsmap_site(tmp_path):
    src = tmp_path / "xstarlib" / "src"
    src.mkdir(parents=True)
    (src / "xstarcalc.f90").write_text(
        "      subroutine xstarcalc\n"
        "      call bremsmap(bremsa,bremsam,bremsint,epi,epim,ncn2,ncn2m,lpri2,lun11)\n"
        "      end\n",
        encoding="utf-8",
    )
    result = locate_xstarcalc_bremsmap_site(tmp_path)
    assert result["status"] == "bremsmap_call_found"
    assert result["bremsmap_line_number"] == 2


def test_prepare_patch_products(tmp_path):
    outputs = prepare_live_rate_grid_probe_patch_products(tmp_path)
    for key in ["helper_fortran", "insertion_block", "json", "markdown"]:
        assert Path(outputs[key]).exists()
    assert "xstar_atomic_write_live_rate_grid_probe" in Path(outputs["helper_fortran"]).read_text(encoding="utf-8")
    assert "bremsmap" in Path(outputs["insertion_block"]).read_text(encoding="utf-8")
