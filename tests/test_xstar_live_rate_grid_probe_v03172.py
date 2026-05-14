from xstar_atomic.xstar_live_rate_grid_probe import read_live_rate_grid_probe_csv, summarize_live_rate_grid_probe_csv


def test_probe_reader_splits_repeated_grid_index_blocks(tmp_path):
    csv_path = tmp_path / "probe_blocks.csv"
    csv_path.write_text(
        "zone_index,pass_index,ldir,grid_index,ncn2m,epim_eV,bremsam,bremsint\n"
        "-1,1,0,1,2,10.0,1.0,5.0\n"
        "-1,1,0,2,2,20.0,2.0,4.0\n"
        "-1,1,0,1,2,11.0,3.0,3.0\n"
        "-1,1,0,2,2,21.0,4.0,2.0\n",
        encoding="utf-8",
    )
    states = read_live_rate_grid_probe_csv(csv_path)
    assert len(states) == 2
    assert states[0].epim_eV == (10.0, 20.0)
    assert states[1].epim_eV == (11.0, 21.0)
    assert states[0].metadata["capture_index"] == 1
    assert states[1].metadata["capture_index"] == 2
    summary = summarize_live_rate_grid_probe_csv(csv_path)
    assert summary["probe_status"] == "probe_csv_loaded"
    assert summary["n_probe_states"] == 2
    assert summary["n_probe_grid_points_total"] == 4
    assert summary["n_probe_states_non_monotonic_energy"] == 0
    assert summary["n_probe_states_ncn2m_mismatch"] == 0
    assert summary["probe_block_split_method"] == "nominal_key_then_grid_index_reset_v03172"
    assert summary["probe_ready_for_type53_phint53_live_bremsam_audit"] is True
