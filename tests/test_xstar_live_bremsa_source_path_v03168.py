from pathlib import Path
import tarfile

from xstar_atomic.xstar_source_provenance import summarize_bremsa_variant_gap


def _write_variant_csv(path: Path) -> None:
    path.write_text(
        "bremsa_variant,median_matrix_over_variant_detail,n_within_10pct_without_free_scale,n_within_10pct_after_variant_scale\n"
        "sum_zrems_no_att_over_fpr2,43.95,0,209\n"
        "default_reader_bremsa,44.03,0,208\n",
        encoding="utf-8",
    )


def test_variant_summary_missing_path_is_explicit(tmp_path: Path):
    missing = tmp_path / "does_not_exist.csv"
    summary = summarize_bremsa_variant_gap(missing)
    assert summary["variant_summary_status"] == "missing"
    assert summary["variant_summary_path_exists"] is False
    assert summary["best_variant"] is None
    assert "not loaded" in summary["interpretation"]


def test_variant_summary_directory_resolution(tmp_path: Path):
    out = tmp_path / "audit_dir"
    out.mkdir()
    csv_path = out / "xstar_type53_detail_phint53_bremsa_variants_audit_variant_summary.csv"
    _write_variant_csv(csv_path)
    summary = summarize_bremsa_variant_gap(out)
    assert summary["variant_summary_status"] == "loaded"
    assert summary["variant_summary_source"] == str(csv_path)
    assert summary["best_variant"] == "sum_zrems_no_att_over_fpr2"
    assert summary["best_median_matrix_over_detail"] == 43.95
    assert summary["best_within10_without_scale"] == 0


def test_variant_summary_tarball_resolution(tmp_path: Path):
    csv_path = tmp_path / "xstar_type53_detail_phint53_bremsa_variants_audit_variant_summary.csv"
    _write_variant_csv(csv_path)
    tar_path = tmp_path / "audit.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(csv_path, arcname="audit/xstar_type53_detail_phint53_bremsa_variants_audit_variant_summary.csv")
    summary = summarize_bremsa_variant_gap(tar_path)
    assert summary["variant_summary_status"] == "loaded"
    assert "audit/xstar_type53_detail_phint53_bremsa_variants_audit_variant_summary.csv" in summary["variant_summary_source"]
    assert summary["best_variant"] == "sum_zrems_no_att_over_fpr2"
    assert summary["n_numeric_variants"] == 2
