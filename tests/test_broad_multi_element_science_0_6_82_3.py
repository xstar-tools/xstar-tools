from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_broad_multi_element_06823_qualification_gate() -> None:
    env = dict(os.environ)
    # The repository test does not require external FORTRAN source, but when the
    # canonical tree is explicitly supplied the checker additionally hashes it.
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_broad_multi_element_science_0_6_82_3.py"],
        cwd=ROOT, text=True, capture_output=True, env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BROAD_MULTI_ELEMENT_SCIENCE_06823_RESULT=ACCEPT" in proc.stdout


def test_radius_retention_prefers_live_controller_geometry() -> None:
    text = (CPP / "xstar_standalone.cpp").read_text(encoding="utf-8")
    start = text.index("const auto& first_live_zone_v06823")
    end = text.index("const double total_depth", start)
    block = text[start:end]
    assert "first_live_zone_v06823.radius_cm - first_live_depth_v06823" in block
    assert "controller_radius_valid_v06823" in block
    assert block.index("? controller_radius0_v06823") < block.index('json_number_value(json, "initial_radius_cm"')


def test_type85_uses_photoionization_heating_not_recombination_cooling() -> None:
    text = (CPP / "local_zone_engine.cpp").read_text(encoding="utf-8")
    start = text.index("else if(dt==85)")
    end = text.index("if (dt != 64 && dt != 85)", start)
    block = text[start:end]
    version_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if any(f'version = "{version}"' in version_text for version in ("0.6.82.5", "0.6.82.6", "0.6.82.7")):
        # 0.6.82.5 corrected the second Type-85 post-phintfo rearrangement;
        # 0.6.82.6 is a publication-only successor and must preserve it.
        assert "c.ans4=-ph.ans[2]" in block
        assert "c.ans6=-ph.ans[4]" in block
    else:
        assert "c.ans4=ph.ans[3]" in block
        assert "c.ans6=ph.ans[5]" in block
    for zero in ("c.ans2=0.0", "c.ans3=0.0", "c.ans5=0.0"):
        assert zero in block


def test_adjacent_bound_free_cases_remain_present() -> None:
    text = (CPP / "local_zone_engine.cpp").read_text(encoding="utf-8")
    for opcode in (
        "XSTAR_FIXED_OPCODE_TYPE54_ANGULAR_REDIS",
        "XSTAR_FIXED_OPCODE_TYPE57_COLLISIONAL_IONIZATION",
        "XSTAR_FIXED_OPCODE_TYPE59_VERNER_BOUND_FREE",
    ):
        assert f"case {opcode}:" in text
