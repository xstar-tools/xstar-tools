from pathlib import Path

from xstar_atomic.xstar_matrix_parity import audit_type53_detail_phint53_scale, write_type53_detail_phint53_scale_audit


def test_type53_detail_phint53_scale_detects_common_factor(tmp_path: Path):
    csv_path = tmp_path / "records.csv"
    csv_path.write_text(
        "ion,record,triplet_component,bound_level_label,matrix_photoionization_rate_s^-1,detail_phint53_photo_ans1_s^-1,classification\n"
        "O VII,1,f,lev1,44.0,1.0,matrix_differs_from_detail_phint53_ans1\n"
        "O VII,2,i,lev2,88.0,2.0,matrix_differs_from_detail_phint53_ans1\n"
        "O VII,3,r,lev3,132.0,3.0,matrix_differs_from_detail_phint53_ans1\n",
        encoding="utf-8",
    )
    audit = audit_type53_detail_phint53_scale(records_csv=csv_path)
    summary = audit["summary"]
    assert summary["n_evaluated_rows"] == 3
    assert abs(summary["median_matrix_over_detail"] - 44.0) < 1.0e-12
    assert summary["n_within_10pct_after_scaling"] == 3
    assert all(r["scaled_classification"] == "scaled_detail_within_10pct" for r in audit["rows"])
    paths = write_type53_detail_phint53_scale_audit(audit, tmp_path / "out")
    assert Path(paths["scaled_records_csv"]).exists()
    assert Path(paths["group_summary_csv"]).exists()
    assert Path(paths["markdown"]).exists()


def test_type53_detail_phint53_scale_handles_outlier(tmp_path: Path):
    csv_path = tmp_path / "records.csv"
    csv_path.write_text(
        "ion,record,triplet_component,bound_level_label,matrix_photoionization_rate_s^-1,detail_phint53_photo_ans1_s^-1\n"
        "O VII,1,f,lev1,44.0,1.0\n"
        "O VII,2,i,lev2,88.0,2.0\n"
        "O VII,3,r,lev3,1000.0,1.0\n",
        encoding="utf-8",
    )
    audit = audit_type53_detail_phint53_scale(records_csv=csv_path)
    assert audit["summary"]["n_evaluated_rows"] == 3
    assert audit["summary"]["n_within_factor2_after_scaling"] < 3
