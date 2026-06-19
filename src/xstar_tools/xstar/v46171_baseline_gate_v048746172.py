"""Validate the actual v0.6.48.7.46.17.1 production result for v46.17.2."""
from __future__ import annotations
import argparse, json
from pathlib import Path

RELEASE = "0.6.48.7.46.17.2.1"
SCHEMA = "xstar-tools-v0648746172-v46171-causal-baseline-v1"
ACCEPTED_GATES = (
    "ALL_61_CONTINUUM_WORKSPACES_RECONSTRUCTED",
    "CLBREMS_BIT_EXACT_61",
    "CLCOMP_BIT_EXACT_61",
    "CMP1_BIT_EXACT_61",
    "CMP2_BIT_EXACT_61",
    "CONTINUUM_BREMSAM_VALUES_EXACT_60939",
    "CONTINUUM_BREMSMAP_INDICES_EXACT_60939",
    "CONTINUUM_EPIM_BINARY64_VALUES_EXACT_60939",
    "CONTINUUM_EPIM_CANONICAL_BINARY64_VALUES_EXACT_999",
    "CONTINUUM_TOTAL_COMPONENTS_BIT_EXACT_244",
    "CONTINUUM_WORKSPACE_CANONICAL_V0472_61",
    "HTCOMP_BIT_EXACT_61",
    "V06487_FIXED_STATE_PARITY_PRESERVED",
    "DENSE_EXACT_SYSTEMS_183_PRESERVED",
    "DENSE_MISMATCH_CELLS_ZERO_PRESERVED",
)
EXPECTED_REJECTED_GATES = (
    "HTFREEF_BIT_EXACT_61",
    "ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610",
    "CONTINUUM_UNEXPLAINED_COMPONENT_DELTAS_ZERO",
    "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1029",
)

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('checker',type=Path); p.add_argument('--output-json',type=Path,required=True); a=p.parse_args(argv)
    source=json.loads(a.checker.read_text()); gates=source.get('gates',{}); errors=[]
    if source.get('release') != '0.6.48.7.46.17.1': errors.append('baseline_release')
    if source.get('result') != 'REJECT' or source.get('scientific_result') != 'REJECT': errors.append('baseline_expected_reject')
    if source.get('native_computed_values_exact') != 1016: errors.append('baseline_exact_1016')
    for name in ACCEPTED_GATES:
        if gates.get(name) != 'ACCEPT': errors.append(name)
    for name in EXPECTED_REJECTED_GATES:
        if gates.get(name) != 'REJECT': errors.append(name)
    h=source.get('continuum_component_summary',{}).get('htfreef',{})
    if h.get('bit_exact') != 48 or h.get('rows') != 61 or h.get('max_ulp_distance') != 2: errors.append('htfreef_48_of_61_max_ulp_2')
    result='ACCEPT' if not errors else 'REJECT'
    report={'schema':SCHEMA,'release':RELEASE,'baseline_release':'0.6.48.7.46.17.1','result':result,'errors':errors,
            'accepted_gates':{n:gates.get(n) for n in ACCEPTED_GATES},
            'expected_rejected_gates':{n:gates.get(n) for n in EXPECTED_REJECTED_GATES},
            'qualification_only':True,'production_promotion_ready':False}
    a.output_json.parent.mkdir(parents=True,exist_ok=True); a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if result=='ACCEPT' else 2
if __name__=='__main__': raise SystemExit(main())
