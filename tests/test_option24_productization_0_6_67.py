from __future__ import annotations

from pathlib import Path

from xstar_tools.execution import SCIENCE_REVISION, package_version
from xstar_tools.source_port_physical_runner_cli import _make_progress_printer


def test_public_benchmark_uses_current_option24_overlay():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src/xstar_tools/benchmarks/public_suite.py").read_text()
    assert 'qualification/current/compare_step_log_science.py' in text
    assert (root / "qualification/frozen/option23/compare_step_log_science.py").is_file()


def test_product_and_science_versions_are_labeled_separately(capsys):
    assert package_version() == "0.6.67"
    assert SCIENCE_REVISION == "0.6.48.12.3.45.3.3.8"
    progress = _make_progress_printer()
    progress("output_writer_start", {})
    out = capsys.readouterr().out
    assert "xstar_tools package version 0.6.67" in out
    assert "xstar_tools science revision 0.6.48.12.3.45.3.3.8" in out
    assert "xstar_tools version 0.6.48.12.3.45.3.3.8" not in out
