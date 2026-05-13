from pathlib import Path

from xstar_atomic.xstar_source_provenance import (
    audit_xstar_live_rate_grid_bremsa_path,
    write_xstar_live_rate_grid_bremsa_path_audit,
)


def _write_minimal_source(root: Path) -> None:
    src = root / "xstarlib" / "src"
    src.mkdir(parents=True)
    (src / "trnfrc.f90").write_text(
        "subroutine trnfrc\n"
        "bremsa(jk)=zremsz(jk)*exp(-dpthc(1,jk))/fpr2\n"
        "end\n",
        encoding="utf-8",
    )
    (src / "xstarcalc.f90").write_text(
        "subroutine xstarcalc\n"
        "call bremsmap(bremsa,bremsam,bremsint,epi,epim,ncn2,ncn2m,lpri2,lun11)\n"
        "call calc_hmc_all(lpri2,lun11,vturbi,critf,t,trad,r,delr,xee,xpx,abel,cfrac,p,lcdd,zeta,mml,mmu,epim,ncn2m,bremsam,bremsint)\n"
        "epim,ncn2m,bremsam,bremsint\n"
        "end\n",
        encoding="utf-8",
    )
    (src / "bremsmap.f90").write_text(
        "subroutine bremsmap\n"
        "bremsam(mmm)=bremsa(mm)\n"
        "end\n",
        encoding="utf-8",
    )
    (src / "calc_hmc_ion.f90").write_text(
        "subroutine calc_hmc_ion\n"
        "epi,ncn2,bremsa,bremsint\n"
        "end\n",
        encoding="utf-8",
    )
    (src / "phint53.f90").write_text(
        "subroutine phint53\n"
        "bremtmp=bremsa(kl)/(12.56)\n"
        "end\n",
        encoding="utf-8",
    )


def test_live_rate_grid_bremsa_path_audit(tmp_path: Path) -> None:
    _write_minimal_source(tmp_path)
    variant = tmp_path / "variant_summary.csv"
    variant.write_text(
        "variant,median_matrix_over_variant_detail,n_within_10pct_without_free_scale,n_within_10pct_after_variant_scale\n"
        "default_reader_bremsa,44.0,0,29\n",
        encoding="utf-8",
    )
    audit = audit_xstar_live_rate_grid_bremsa_path(
        xstar_source_root=tmp_path,
        variant_summary_csv=variant,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.169"
    assert summary["n_source_snippets_matched"] == summary["n_source_snippet_specs"]
    assert summary["status"] == "rate_grid_source_path_confirmed_detail_variants_do_not_recover_live_bremsam"
    assert "bremsam" in summary["correct_live_rate_field"]
    assert len(audit["capture_columns"]) >= 8
    assert len(audit["instrumentation_steps"]) >= 3


def test_live_rate_grid_bremsa_path_writer(tmp_path: Path) -> None:
    _write_minimal_source(tmp_path / "srcroot")
    audit = audit_xstar_live_rate_grid_bremsa_path(xstar_source_root=tmp_path / "srcroot")
    paths = write_xstar_live_rate_grid_bremsa_path_audit(audit, tmp_path / "out")
    for key in ("snippets_csv", "capture_columns_csv", "instrumentation_steps_csv", "probe_notes", "json", "markdown"):
        assert Path(paths[key]).exists()
    assert "epim" in Path(paths["markdown"]).read_text(encoding="utf-8")
