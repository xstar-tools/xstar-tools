"""Aggregate 61 independent run-fixed-evaluation outputs for v0.6.48.7.43."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path


def read_csv(path: Path):
    with path.open(newline='') as f: return list(csv.DictReader(f))


def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--source-inputs',type=Path,required=True); p.add_argument('--evaluations-dir',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv); a.output.mkdir(parents=True,exist_ok=True)
    source=read_csv(a.source_inputs); rows=[]; callbacks=0; records=0; elements=0; errors=[]
    fields=['sequence','kind','call_index','evaluation_index','temperature_t4','electron_fraction_input','computed_electron_fraction','charge_residual','hmctot']
    for item in source:
        seq=int(item['sequence']); root=a.evaluations_dir/f'evaluation_{seq:04d}'
        state_path=root/'native_evaluation.csv'; summary_path=root/'native_evaluation_summary.json'
        if not state_path.is_file() or not summary_path.is_file(): errors.append(f'missing:evaluation_{seq:04d}'); continue
        state=read_csv(state_path)[0]; summary=json.loads(summary_path.read_text())
        callbacks += int(summary.get('python_callbacks',0)); records += int(summary.get('records_evaluated',0)); elements += int(summary.get('elements_solved',0))
        rows.append({'sequence':seq,'kind':item['kind'],'call_index':item['dsec_call_id'],'evaluation_index':item['evaluation_index'],
                     'temperature_t4':item['temperature_t4'],'electron_fraction_input':item['electron_fraction_input'],
                     'computed_electron_fraction':state['native_electron_fraction'],'charge_residual':state['native_charge_residual'],'hmctot':state['native_hmctot']})
    with (a.output/'native_dsec_trajectory.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    summary={'schema_version':'0.6.48.7.43','trajectory_mode':'all61_independent_reference_input_state_qualification','total_evaluations':len(rows),
             'python_callbacks':callbacks,'records_evaluated':records,'elements_solved':elements,'errors':errors,'production_promotion_ready':False}
    (a.output/'native_dsec_summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    print(json.dumps(summary,indent=2,sort_keys=True)); return 0 if len(rows)==61 and callbacks==0 and not errors else 2
if __name__=='__main__': raise SystemExit(main())
