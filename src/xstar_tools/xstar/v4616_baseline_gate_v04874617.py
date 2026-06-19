"""Validate the accepted v0.6.48.7.46.18 baseline for v46.17."""
from __future__ import annotations
import argparse,json
from pathlib import Path
RELEASE="0.6.48.7.46.18";SCHEMA="xstar-tools-v064874617-v4616-baseline-v1"
REQUIRED_GATES=("ALL_61_THERMAL_EVALUATIONS","THERMAL_COMPACT_POPULATION_VALUES_EXACT_40149","ALL_61_THERMAL_DIAGONAL_SOURCE_DOMAIN_APPLIED","THERMAL_DIAGONAL_SOURCE_ORDER_STREAMS_EXACT_183","HE_TYPE50_REVERSE_ENERGY_ROWS_CHANGED_554","HE_NON_TYPE53_COOLING_SOURCE_SCALE_61","PYTHON_CALLBACKS_ZERO","V06487_FIXED_STATE_PARITY_PRESERVED","V06488_THERMAL_PARITY","DENSE_EXACT_SYSTEMS_183_PRESERVED","DENSE_MISMATCH_CELLS_ZERO_PRESERVED","PRODUCTION_PROMOTION_BLOCKED")
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("checker",type=Path);p.add_argument("--output-json",type=Path,required=True);a=p.parse_args();errors=[]
 try:s=json.loads(a.checker.read_text())
 except Exception as e:s={};errors.append(str(e))
 g=s.get("gates",{});checked={x:("ACCEPT" if g.get(x)=="ACCEPT" else "REJECT") for x in REQUIRED_GATES}
 if s.get("release")!="0.6.48.7.46.16":errors.append("baseline_release")
 if s.get("result")!="ACCEPT":errors.append("baseline_result")
 errors += [x for x,v in checked.items() if v!="ACCEPT"]
 r={"schema":SCHEMA,"release":RELEASE,"baseline_release":s.get("release"),"result":"ACCEPT" if not errors else "REJECT","gates":checked,"errors":errors,"qualification_only":True,"production_promotion_ready":False}
 a.output_json.parent.mkdir(parents=True,exist_ok=True);a.output_json.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n");print(json.dumps(r,indent=2,sort_keys=True));return 0 if r["result"]=="ACCEPT" else 2
if __name__=="__main__":raise SystemExit(main())
