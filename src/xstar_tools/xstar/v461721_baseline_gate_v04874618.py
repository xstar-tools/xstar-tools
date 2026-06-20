"""Validate the accepted v46.17.2.1 post-continuum baseline for v46.18."""
from __future__ import annotations
import argparse, json
from pathlib import Path
RELEASE='0.6.48.7.46.20.2'
SCHEMA='xstar-tools-v064874618-v461721-baseline-v1'
REQUIRED=(
 'ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610',
 'CONTINUUM_UNEXPLAINED_COMPONENT_DELTAS_ZERO',
 'V06487_FIXED_STATE_PARITY_PRESERVED',
 'DENSE_EXACT_SYSTEMS_183_PRESERVED',
 'DENSE_MISMATCH_CELLS_ZERO_PRESERVED',
 'NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1029',
 'PRODUCTION_PROMOTION_BLOCKED',
)
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('checker',type=Path); p.add_argument('--output-json',type=Path,required=True); a=p.parse_args(argv)
 errors=[]
 try: source=json.loads(a.checker.read_text())
 except Exception as exc: source={}; errors.append(f'checker_read:{exc}')
 gates=source.get('gates',{})
 if source.get('result')!='ACCEPT': errors.append('baseline_result')
 accepted={name:('ACCEPT' if gates.get(name)=='ACCEPT' else 'REJECT') for name in REQUIRED}
 errors.extend(name for name,value in accepted.items() if value!='ACCEPT')
 if source.get('native_computed_values_exact')!=1029 or source.get('native_computed_values_total')!=2440:
  errors.append('baseline_exact_1029')
 report={'schema':SCHEMA,'release':RELEASE,'baseline_release':'0.6.48.7.46.17.2.1','result':'ACCEPT' if not errors else 'REJECT','errors':errors,'accepted_gates':accepted,'native_computed_values_exact':source.get('native_computed_values_exact'),'native_computed_values_total':source.get('native_computed_values_total'),'qualification_only':True,'production_promotion_ready':False}
 a.output_json.parent.mkdir(parents=True,exist_ok=True); a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); print(json.dumps(report,indent=2,sort_keys=True)); return 0 if not errors else 2
if __name__=='__main__': raise SystemExit(main())
