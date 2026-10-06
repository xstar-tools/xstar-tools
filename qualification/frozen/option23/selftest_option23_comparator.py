#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
P='V064812345332_'

def emit(k,v): print(f'{P}{k}={v}',flush=True)

def load_cmp():
    p=HERE/'compare_step_log_science.py'
    spec=importlib.util.spec_from_file_location('v064812345332_stepcmp',p)
    mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod)
    return mod

def row(rank,line,wl,v1,v2=0.0):
    return {'rank':rank,'line_index':line,'wavelength':wl,'ion':'he_ii','value_1':v1,'value_2':v2}

def check(name,cond):
    emit(name,'ACCEPT' if cond else 'REJECT')
    return bool(cond)

def main():
    m=load_cmp(); ok=True
    # Mimic the C5 508/515 near-degenerate crossing: numerical rank surface
    # is well inside 1%, while row identities are swapped.
    ref=[row(1,508,4687.07,1.92448e-7),row(2,515,6650.44,1.92423e-7)]
    cand=[row(1,515,6650.44,1.92421e-7),row(2,508,4687.07,1.92394e-7)]
    got=m.compare_ranked_rows('23',cand,ref)
    ok &= check('SELFTEST_OPTION23_NUMERIC_ACCEPT', got['numeric_science_accept'])
    ok &= check('SELFTEST_OPTION23_SCIENCE_ACCEPT_WITH_RANK_SWAP', got['scientific_accept'])
    ok &= check('SELFTEST_OPTION23_RANK_SWAP_RETAINED_DIAGNOSTIC', got['rank_or_order_membership_diagnostic'])
    ok &= check('SELFTEST_OPTION23_IDENTITY_MISMATCH_RETAINED', got['identity_mismatches']==2)
    ok &= check('SELFTEST_OPTION23_ROWWISE_GT1PCT_ZERO', got['rank_rowwise_gt1pct_diagnostics']==0)
    # A genuine >1% ranked-array discrepancy must still fail science.
    bad=[row(1,508,4687.07,2.2e-7),row(2,515,6650.44,2.2e-7)]
    badgot=m.compare_ranked_rows('23',bad,ref)
    ok &= check('SELFTEST_OPTION23_GT1PCT_NUMERIC_REJECT', not badgot['numeric_science_accept'])
    ok &= check('SELFTEST_OPTION23_GT1PCT_SCIENCE_REJECT', not badgot['scientific_accept'])
    emit('SELFTEST_RESULT','ACCEPT' if ok else 'REJECT')
    return 0 if ok else 1
if __name__=='__main__': raise SystemExit(main())
