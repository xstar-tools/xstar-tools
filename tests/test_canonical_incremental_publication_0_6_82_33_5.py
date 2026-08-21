from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(rel: str) -> str:
    return (ROOT / rel).read_text()


def load_runner():
    path = ROOT / 'tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_5.py'
    spec = importlib.util.spec_from_file_location('runner_0682335', path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_version_and_baseline():
    assert 'version = "0.6.82.33.5"' in text('pyproject.toml')
    assert 'PACKAGE_VERSION ?= 0.6.82.33.5' in text('src/xstar_tools/xstar/cpp/Makefile')
    r = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_5.py')
    assert 'BASELINE_VERSION = "0.6.82.32"' in r
    assert 'CANDIDATE_VERSION = "0.6.82.33.5"' in r


def test_zero_valued_marker_is_not_replaced_by_missing_sentinel():
    r = load_runner()
    assert r.metric_int({'legacy': 0}, 'legacy', 999) == 0
    assert r.metric_int({'legacy': '0'}, 'legacy', 999) == 0
    assert r.metric_int({}, 'legacy', 999) == 999


def test_runner_uses_zero_preserving_parser_for_lifetime_markers():
    r = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_5.py')
    assert 'legacy_final_history_peak = metric_int(candidate_perf, "V0682332_FINAL_SNAPSHOTS_PEAK_BYTES", 999)' in r
    assert 'snapshot_peak_count = metric_int(candidate_perf, "V0682334_FINAL_SNAPSHOTS_PEAK_COUNT", 999)' in r
    assert 'candidate_perf.get("V0682332_FINAL_SNAPSHOTS_PEAK_BYTES", 999) or 999' not in r
    assert 'legacy_final_history_peak == 0' in r


def test_host_return_values_now_satisfy_lifetime_gate_semantics():
    r = load_runner()
    candidate = {
        'V0682334_FINAL_TRANSFER_MODE': 'IMMEDIATE_SINGLE_PASS_PRODUCTION',
        'V0682334_FINAL_SNAPSHOTS_PEAK_COUNT': 1,
        'V0682334_FINAL_SNAPSHOTS_PEAK_BYTES': 114747497,
        'V0682332_FINAL_SNAPSHOTS_PEAK_BYTES': 0,
        'V0682334_ACCEPTED_BOUNDARIES': 2,
        'V0682334_FINAL_SNAPSHOTS_O1': 'ACCEPT',
    }
    transfer_mode = str(candidate['V0682334_FINAL_TRANSFER_MODE'])
    peak_count = r.metric_int(candidate, 'V0682334_FINAL_SNAPSHOTS_PEAK_COUNT', 999)
    legacy_peak = r.metric_int(candidate, 'V0682332_FINAL_SNAPSHOTS_PEAK_BYTES', 999)
    accepted = r.metric_int(candidate, 'V0682334_ACCEPTED_BOUNDARIES', 0)
    lifetime_ok = (
        transfer_mode == 'IMMEDIATE_SINGLE_PASS_PRODUCTION'
        and peak_count <= 1
        and accepted > 0
        and legacy_peak == 0
        and candidate['V0682334_FINAL_SNAPSHOTS_O1'] == 'ACCEPT'
    )
    assert lifetime_ok


def test_0334_cpp_implementation_is_frozen_byte_for_byte():
    expected = {
        'src/xstar_tools/xstar/cpp/xstar_standalone.cpp': 'e52a9da06d5b0fa4605c18ea3652faad6702f2d4f2aac29c16d55f268da5086f',
        'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp': 'f142cd43ee6b66029a20e93407a04116f4d3a4989ce44763395ca97eee28fd64',
    }
    for rel, digest in expected.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == digest


def test_existing_0334_telemetry_names_are_intentionally_retained():
    s = text('src/xstar_tools/xstar/cpp/xstar_standalone.cpp')
    for marker in (
        'V0682334_FINAL_TRANSFER_MODE=',
        'V0682334_ACCEPTED_BOUNDARIES=',
        'V0682334_FINAL_SNAPSHOTS_PEAK_COUNT=',
        'V0682334_FINAL_SNAPSHOTS_PEAK_BYTES=',
        'V0682334_FINAL_SNAPSHOTS_O1=',
    ):
        assert marker in s


def test_exact_science_memory_and_tiered_host_gates_are_unchanged():
    r = text('tools/qualification/run_canonical_incremental_publication_host_0_6_82_33_5.py')
    assert 'compare_fits_payloads' in r
    assert 'hashlib.sha256(payload)' in r
    assert 'rss_ratio <= 0.30' in r
    assert 'wall_ratio <= 1.05' in r
    assert 'args.case or ["fe_reference_ne1e8"]' in r
    assert '--milestone-all' in r


def test_deferred_034_correctness_plan_is_unchanged():
    c = text('CHANGELOG.md')
    for item in ('0.6.82.34', 'N VI', 'Cr II', 'O IV', 'Mg II', 'cemab/cabab/opakab/tauc', 'Si VI / Ni VI', '1e-49'):
        assert item in c
