from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CPP_ZONE = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
PY_EMIS = ROOT / "src/xstar_tools/xstar/emergent_emissivity.py"
RUNNER = ROOT / "tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3_8_4.py"


def test_version_bumped_after_3383_host_rejection():
    assert 'version = "0.6.82.29.3.3.8.4"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3.8.4' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert changelog.startswith("## 0.6.82.29.3.3.8.4")
    assert "displaced rank-10" in changelog


def test_cpp_private_pprint4_replay_precedes_operational_consumer_gate():
    text = CPP_ZONE.read_text()
    anchor = text.index("0.6.82.29.3.3.8.4: pprint(4) is a source-owned publication")
    private_consumer = text.index("const auto pprint4_consumer_v068229336 = source_calc_emis_consumer(", anchor)
    operational_consumer = text.index("const auto line_consumer_v82_patch5208 = source_calc_emis_consumer(", anchor)
    operational_continue = text.index("if (!line_consumer_v82_patch5208.actual_consumer) continue;", anchor)
    selected_push = text.index("selected_lines_v82_patch5206.push_back(c);", anchor)
    assert anchor < private_consumer < operational_consumer < operational_continue < selected_push


def test_cpp_private_membership_does_not_feed_operational_selected_lines():
    text = CPP_ZONE.read_text()
    anchor = text.index("0.6.82.29.3.3.8.4: pprint(4) is a source-owned publication")
    end = text.index("selected_lines_v82_patch5206.push_back(c);", anchor)
    block = text[anchor:end]
    assert "source_pprint4_nlbin_v068229336" in block
    assert "source_calc_emis_nlbin_v82_patch5208" in block
    # The operational copy is created only after the operational table accepts.
    assert block.index("source_pprint4_nlbin_v068229336") < block.index("auto c = original_c;")
    assert block.index("source_calc_emis_nlbin_v82_patch5208") < block.index("auto c = original_c;")


def test_python_rlbin_displacement_can_retain_rank10_and_consumer_accepts_it(monkeypatch):
    # The module only needs astropy for ATDB I/O, not for these pure rank helpers.
    # Provide an import stub so this focused source-semantics test stays lightweight.
    import sys
    import types
    astropy = types.ModuleType("astropy")
    astropy_io = types.ModuleType("astropy.io")
    astropy_fits = types.ModuleType("astropy.io.fits")
    astropy.io = astropy_io
    astropy_io.fits = astropy_fits
    monkeypatch.setitem(sys.modules, "astropy", astropy)
    monkeypatch.setitem(sys.modules, "astropy.io", astropy_io)
    monkeypatch.setitem(sys.modules, "astropy.io.fits", astropy_fits)

    from xstar_tools.xstar.emergent_emissivity import (
        XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM,
        _feature_is_ranked,
        nbinc,
        rlbin_insert,
    )

    # Put nine weak lines into one source bin.  Inserting a stronger tenth line
    # at rank 1 shifts the previous rank-9 identity into rank 10.  Canonical
    # rlbin.f90 retains that displaced rank-10 slot even though a candidate
    # which *arrives* at rank 10 is discarded.
    epi = np.asarray([10.0, 20.0, 40.0, 80.0], dtype=float)
    n = len(epi)
    wavelength = XSTAR_CALC_EMIS_WAVELENGTH_EV_ANGSTROM / 40.0
    bin_one_based = nbinc(40.0, epi, n)

    wavelengths = np.zeros(11, dtype=float)
    wavelengths[1:] = wavelength
    emissivity = np.zeros((2, 11), dtype=float)
    opacity = np.zeros(11, dtype=float)
    for feature in range(1, 10):
        emissivity[0, feature] = float(10 - feature)  # 9,8,...,1
    emissivity[0, 10] = 10.0

    table = np.zeros((11, n + 1), dtype=int)  # source ranks 1..10
    table[1:10, bin_one_based] = np.arange(1, 10, dtype=int)

    trace = rlbin_insert(
        feature_kind="line",
        feature_index=10,
        wavelengths_angstrom=wavelengths,
        emissivity=emissivity,
        opacity=opacity,
        epi_eV=epi,
        ncn2=n,
        rank_table=table,
        rank_by_opacity=False,
    )
    assert trace.stored
    assert trace.rank_one_based == 1
    assert int(table[10, bin_one_based]) == 9
    assert _feature_is_ranked(table, 9, bin_one_based)


def test_python_final_line_consumer_uses_full_source_rank_table_including_rank10():
    text = PY_EMIS.read_text()
    assert "def _feature_is_ranked" in text
    assert "while int(table[mm, bin_one_based]) != 0" in text
    assert "and mm < nrank" in text
    assert "int(table[mm, bin_one_based]) == int(feature_index)" in text
    # Both the precomputed line metadata and direct final replay call the same
    # rank-table consumer; no top-9 selected-set prefilter is required.
    assert text.count("ranked = bool(_feature_is_ranked(line_rank_table, line_index, nb1))") >= 2


def test_cpp_rank_table_shift_preserves_displaced_rank10_slot():
    text = CPP_ZONE.read_text()
    assert "if (mm >= nrank) continue;" in text
    assert "for (int mm2 = nrank - 1; mm2 >= mm; --mm2)" in text
    assert "row[static_cast<std::size_t>(mm2)] = row[static_cast<std::size_t>(mm2 - 1)];" in text
    assert "row[static_cast<std::size_t>(mm - 1)] = c.slot_one_based;" in text


def test_3384_provenance_is_external_and_reports_rank10_channel330():
    text = RUNNER.read_text()
    assert 'OUTPUT_CONTROL_OPTION4_0682293384_CPP_RESULT' in text
    assert "pprint4_flinel_provenance_0682293384.csv" in text
    assert "XSTAR_V0682293384_PPRINT4_FLINEL_PROVENANCE_PATH" in text
    assert "provenance rank10 rows:" in text
    assert "provenance channel 330 rank10:" in text


def test_science_revision_and_abis_remain_frozen():
    api = (ROOT / 'src/xstar_tools/xstar/cpp/xstar_api.h').read_text()
    prod = (ROOT / 'src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h').read_text()
    fixed = (ROOT / 'src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h').read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert '#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110' in prod
    assert '#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u' in fixed
