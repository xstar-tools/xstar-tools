import csv
from pathlib import Path

from xstar_atomic.xstar_population_closure_diagnosis import diagnose_population_closure_from_family_scan


def test_population_closure_diagnosis_rate_replay_not_population_moving(tmp_path: Path):
    p = tmp_path / "xstar_record_level_ucalc_replay_family_scan.csv"
    rows = [
        {
            "family_key": "type53_rate7:global_type53_phint53_matrix_term",
            "n_replayed_terms": "1098",
            "median_old_over_new": "44",
            "delta_triplet_population_f_fraction": "8e-7",
            "delta_triplet_population_i_fraction": "-8e-7",
            "delta_triplet_population_r_fraction": "2e-11",
        }
    ]
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)
    audit = diagnose_population_closure_from_family_scan(p, population_delta_threshold=1e-4)
    assert audit["summary"]["dominant_next_target"] == "population_source_closure"
    assert audit["summary"]["rate_replay_moves_population"] is False
