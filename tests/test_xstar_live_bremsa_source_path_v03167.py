from pathlib import Path

from xstar_atomic.xstar_source_provenance import (
    SourceSnippetSpec,
    audit_xstar_live_bremsa_source_path,
    summarize_bremsa_variant_gap,
    write_xstar_live_bremsa_source_path_audit,
)


def test_summarize_bremsa_variant_gap(tmp_path: Path):
    csv_path = tmp_path / "variants.csv"
    csv_path.write_text(
        "bremsa_variant,median_matrix_over_variant_detail,n_within_10pct_without_free_scale,n_within_10pct_after_variant_scale\n"
        "a,44.0,0,29\n"
        "b,45.0,0,28\n",
        encoding="utf-8",
    )
    summary = summarize_bremsa_variant_gap(csv_path)
    assert summary["variant_summary_status"] == "loaded"
    assert summary["best_variant"] == "a"
    assert summary["best_within10_without_scale"] == 0
    assert "live zremsz" in summary["interpretation"]


def test_live_bremsa_source_path_audit_with_synthetic_source(tmp_path: Path):
    src = tmp_path / "xstarlib" / "src"
    src.mkdir(parents=True)
    (src / "trnfrc.f90").write_text(
        "subroutine trnfrc\n"
        "fpr2=(12.56)*r19*r19\n"
        "bremsa(jk)=zremsz(jk)*exp(-dpthc(1,jk))/fpr2\n"
        "end\n",
        encoding="utf-8",
    )
    specs = [
        SourceSnippetSpec(
            key="out",
            file="trnfrc.f90",
            pattern="bremsa(jk)=zremsz(jk)*exp(-dpthc(1,jk))/fpr2",
            role="test",
            interpretation="test interpretation",
        )
    ]
    audit = audit_xstar_live_bremsa_source_path(xstar_source_root=tmp_path, snippets=specs)
    assert audit["summary"]["audit_version"] == "v0.3.168"
    assert audit["summary"]["n_source_snippets_matched"] == 1
    paths = write_xstar_live_bremsa_source_path_audit(audit, tmp_path / "out")
    assert Path(paths["snippets_csv"]).exists()
    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
