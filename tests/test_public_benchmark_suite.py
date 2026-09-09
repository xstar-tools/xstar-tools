from __future__ import annotations
from pathlib import Path
import json

from xstar_tools.benchmarks.public_suite import (
    CPP_REFERENCE_MODE, DEFAULT_PYTHON_CASES, FULL_MODES, PYTHON_MODES,
    discover_cases, find_suite_root, run_suite,
)


def make_suite(root: Path) -> Path:
    suite=root/'original_xstar'
    for i in range(62):
        group='helike_type69' if i<50 else 'mg_ca_triplet_targets'
        case=f'case_{i:02d}'
        d=suite/group/case; d.mkdir(parents=True,exist_ok=True)
        (d/'run_xstar.sh').write_text('#!/usr/bin/env bash\ntrue\n')
    return suite


def test_public_benchmark_defaults():
    assert FULL_MODES == ('zone-cpp','zone-all','xstar-cpp')
    assert PYTHON_MODES == ('pure-python','zone-python')
    assert CPP_REFERENCE_MODE == {'zone-cpp':'cpp-zone','zone-all':'cpp-all','xstar-cpp':'standalone-cpp'}
    assert DEFAULT_PYTHON_CASES == (
        'helike_type69/o7_ne1e10','helike_type69/mg11_ne1e8','helike_type69/ca19_xi2_ne1'
    )


def test_discovers_exact_62_case_layout(tmp_path: Path):
    suite=make_suite(tmp_path)
    assert find_suite_root(tmp_path)==suite
    cases=discover_cases(tmp_path)
    assert len(cases)==62
    assert cases[0].relative.startswith('helike_type69/')


def test_dry_run_plans_all_full_mode_cases(tmp_path: Path):
    suite=make_suite(tmp_path/'suite')
    data=tmp_path/'data'; data.mkdir()
    out=tmp_path/'out'
    result=run_suite(
        package=Path(__file__).resolve().parents[1], suite_archive=None, suite_root=suite,
        data_dir=data, out_dir=out, full_modes=('zone-cpp',), python_modes=(), python_cases=(), dry_run=True,
    )
    assert result['case_count']==62
    assert result['planned_run_count']==62
    assert result['all_runs_accept'] is True
    manifest=(out/'run_manifest.csv').read_text()
    assert 'zone-cpp' in manifest


