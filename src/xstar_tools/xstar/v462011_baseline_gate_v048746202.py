"""Validate accepted v46.20.1.1 as the direct v46.20.2 baseline."""
from __future__ import annotations
import argparse, json
from pathlib import Path

RELEASE = "0.6.48.7.46.21.2"
SCHEMA = "xstar-tools-v0648746202-v462011-baseline-v1"


def validate(path: Path) -> dict:
    obj = json.loads(path.read_text())
    gates = obj.get("gates", {})
    accepted = {
        "V462011_ACCEPTED": obj.get("result") == "ACCEPT" and obj.get("scientific_result") == "ACCEPT",
        "V462011_MG_COOLING_EXACT_8_OF_61": obj.get("mg_cooling_exact") == 8 and obj.get("mg_cooling_total") == 61,
        "V462011_NATIVE_EXACT_1080": obj.get("native_computed_values_exact") == 1080 and obj.get("native_computed_values_total") == 2440,
        "V462011_TYPE99_FAMILY_EXACT": gates.get("TYPE99_PRIMARY_COOLING_FAMILY_EXACT_61") == "ACCEPT",
        "V462011_TYPE50_CORE_EXACT": gates.get("TYPE50_CORE_CLOSURE_PRESERVED") == "ACCEPT",
        "V462011_SOURCE_ORDER_REQUIRED": gates.get("MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_REDUCTION_REQUIRED") == "ACCEPT",
        "V462011_PRODUCTION_BLOCKED": gates.get("PRODUCTION_PROMOTION_BLOCKED") == "ACCEPT",
    }
    errors = [name for name, ok in accepted.items() if not ok]
    return {
        "schema": SCHEMA, "release": RELEASE,
        "baseline_release": "0.6.48.7.46.20.1.1",
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "accepted_gates": {name: "ACCEPT" if ok else "REJECT" for name, ok in accepted.items()},
        "qualification_only": True, "production_promotion_ready": False,
    }


def main(argv=None) -> int:
    p=argparse.ArgumentParser(); p.add_argument("checker_json",type=Path); p.add_argument("--output-json",type=Path,required=True)
    a=p.parse_args(argv)
    try: r=validate(a.checker_json)
    except Exception as exc: r={"schema":SCHEMA,"release":RELEASE,"result":"REJECT","errors":[str(exc)],"qualification_only":True,"production_promotion_ready":False}
    a.output_json.parent.mkdir(parents=True,exist_ok=True); a.output_json.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r["result"]=="ACCEPT" else 2
if __name__=="__main__": raise SystemExit(main())
