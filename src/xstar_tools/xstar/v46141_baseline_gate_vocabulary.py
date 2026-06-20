"""Validate the accepted v46.14.1 Thermal diagonal-domain baseline."""
from __future__ import annotations
import argparse, json
from pathlib import Path

RELEASE = "0.6.48.7.46.21.3.1"
BASELINE_RELEASE = "0.6.48.7.46.14.1"
REQUIRED = (
    "ALL_61_THERMAL_EVALUATIONS", "ALL_61_THERMAL_DIAGONAL_SOURCE_DOMAIN_APPLIED",
    "THERMAL_DIAGONAL_SOURCE_ORDER_STREAMS_EXACT_183", "THERMAL_DIAGONAL_TERMS_ALL_INCLUDED",
    "CONTINUUM_SECONDARY_LEDGER_EXACT_61", "COMMITTED_THERMAL_CLOSURE_UNCHANGED",
    "COMPACT_POPULATION_TRANSPORT_PRESERVED_40149", "THERMAL_COMPONENT_CLOSURE_AUDIT",
    "RESUMABLE_NATIVE_REPLAY_COMPLETE_61", "V06487_FIXED_STATE_PARITY_PRESERVED",
    "DENSE_EXACT_SYSTEMS_183_PRESERVED", "DENSE_MISMATCH_CELLS_ZERO_PRESERVED",
    "PYTHON_CALLBACKS_ZERO", "V06488_THERMAL_PARITY", "PRODUCTION_PROMOTION_BLOCKED",
)

def validate(report: dict) -> dict:
    gates = report.get("gates", {}) if isinstance(report.get("gates"), dict) else {}
    errors = []
    if report.get("release") != BASELINE_RELEASE: errors.append("baseline_release")
    if report.get("result") != "ACCEPT": errors.append("baseline_result")
    errors += [name for name in REQUIRED if gates.get(name) != "ACCEPT"]
    return {"schema":"xstar-tools-v064874615-v46141-baseline-v1", "release":RELEASE,
            "baseline_release":BASELINE_RELEASE, "result":"ACCEPT" if not errors else "REJECT",
            "gates":{name:gates.get(name) for name in REQUIRED}, "errors":errors,
            "qualification_only":True, "production_promotion_ready":False}

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("checker_report",type=Path); p.add_argument("--output-json",type=Path); a=p.parse_args()
    result=validate(json.loads(a.checker_report.read_text())); text=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if a.output_json: a.output_json.parent.mkdir(parents=True,exist_ok=True); a.output_json.write_text(text)
    print(text,end=""); print("V04874615_BASELINE_V46141="+result["result"])
    return 0 if result["result"]=="ACCEPT" else 2
if __name__=="__main__": raise SystemExit(main())
