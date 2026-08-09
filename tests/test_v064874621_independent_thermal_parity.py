from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_shared_source_order_reducer_is_used_by_both_engines() -> None:
    element = (CPP / "element_engine.cpp").read_text()
    fixed = (CPP / "local_zone_engine.cpp").read_text()
    assert '#include "source_order_thermal_reducer.hpp"' in element
    assert '#include "source_order_thermal_reducer.hpp"' in fixed
    assert "FourChannelAccumulator thermal_reducer" in element
    assert (
        "TaggedFourChannelAccumulator thermal_reducer" in fixed
        or "xstar_canonical_thermal::reduce" in fixed
    )
    assert "last_computed_helium_non_type53_budget" in fixed
    assert "double h53 = 0.0" not in fixed


def test_abundance_is_applied_after_unweighted_binary64_sum(tmp_path: Path) -> None:
    source = tmp_path / "probe.cpp"
    binary = tmp_path / "probe"
    source.write_text(r'''
#include "source_order_thermal_reducer.hpp"
#include <iostream>
int main() {
  constexpr double p1=2.4768104848499264e-07;
  constexpr double c1=0.005941479333551856;
  constexpr double p2=0.0029152796001020095;
  constexpr double c2=2.5579603102860847e-11;
  constexpr double abundance=1.479397427340123e-08;
  xstar_source_order_thermal::FourChannelAccumulator acc;
  acc.accumulate_primary(p1,c1); acc.accumulate_primary(p2,c2);
  const double source=(p1*c1+p2*c2)*abundance;
  const double misplaced=(p1*abundance)*c1+(p2*abundance)*c2;
  const double reduced=acc.abundance_weighted(abundance)[1];
  if (source != reduced || source == misplaced) return 2;
  std::cout << std::hexfloat << reduced << "\n";
  return 0;
}
''')
    subprocess.run([
        "g++", "-std=c++17", "-ffp-contract=off", "-I", str(CPP),
        str(source), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)


def test_independent_mode_forbids_source_scalar_closures() -> None:
    fixed = (CPP / "local_zone_engine.cpp").read_text()
    runner = (ROOT / "run_v04874621_independent_thermal_parity.sh").read_text()
    assert "XSTAR_QUALIFICATION_INDEPENDENT_THERMAL_PARITY" in fixed
    assert "independent Thermal parity forbids" in fixed
    assert "XSTAR_QUALIFICATION_INDEPENDENT_THERMAL_PARITY=1" in runner
    assert "XSTAR_QUALIFICATION_FIXED_STATE_PARITY_CLOSURE=1" not in runner
    assert "XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE=1" not in runner
    assert "XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE=1" not in runner


def test_elcter_is_charge_residual_not_computed_fraction() -> None:
    fixed = (CPP / "local_zone_engine.cpp").read_text()
    standalone = (CPP / "xstar_standalone.cpp").read_text()
    assert "output.electron_fraction_xee = computed_electron_fraction" in fixed
    assert "output.elcter = input.electron_fraction_xee - computed_electron_fraction" in fixed
    assert "snapshot.computed_electron_fraction = output.electron_fraction_xee" in standalone
    assert "snapshot.charge_residual = output.elcter" in standalone
    assert "evaluation->elcter = output.elcter" in standalone


def test_element_engine_has_strict_fp_policy() -> None:
    makefile = (CPP / "Makefile").read_text()
    assert "ELEMENT_STRICT_FP_FLAGS ?= -ffp-contract=off" in makefile
    assert "$(ELEMENT_STRICT_FP_FLAGS) $(SO_LDFLAGS)" in makefile


def test_readiness_checker_accepts(tmp_path: Path) -> None:
    report = tmp_path / "readiness.json"
    subprocess.run([
        "python", str(ROOT / "check_v04874621_independent_thermal_parity_readiness.py"),
        "--package-dir", str(ROOT), "--output-json", str(report),
    ], check=True)
    result = json.loads(report.read_text())
    assert result["result"] == "ACCEPT"
    assert result["module_contract"]["runner_fixed_scalar_closure"] == 0


def test_source_answer_audit_wraps_final_ucalc_result() -> None:
    module = (ROOT / "src/xstar_tools/xstar/v0472_all61_independent_thermal_capture_v04874621.py").read_text()
    assert "def _v04874621_install_answer_hook" in module
    assert "original_evaluate = SourceFaithfulUCalc.evaluate_record_number" in module
    assert 'status == "evaluated"' in module
    assert 'sink = _STATE.setdefault("v04874621_answer_channels", {})' in module
    assert "non-unique Thermal answer context" in module
    assert "_v04874621_capture_answer_channels" not in module


def test_resume_prefers_canonical_evaluation_workspace() -> None:
    resume = (ROOT / "src/xstar_tools/xstar/native_replay_resume_v04874621.py").read_text()
    evaluation = resume.index('workspaces / f"evaluation_{sequence:04d}"')
    sequence = resume.index('workspaces / f"sequence_{sequence:04d}"')
    recorded = resume.index('item.get("workspace_directory", "")')
    assert evaluation < sequence < recorded
