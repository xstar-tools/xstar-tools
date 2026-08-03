import ast
import math
from pathlib import Path

def test_type39_uses_literal_exp_not_expo_clamp():
    source=Path(__file__).resolve().parents[1]/'src/xstar_tools/xstar/ucalc.py'
    tree=ast.parse(source.read_text())
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_eval_type39')
    calls=[]
    for n in ast.walk(fn):
        if isinstance(n,ast.Call):
            if isinstance(n.func,ast.Name):calls.append(n.func.id)
            elif isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name):calls.append(f'{n.func.value.id}.{n.func.attr}')
    assert 'math.exp' in calls
    assert '_expo' not in calls
    # The numerical distinction that caused the 12.3.35 false attribution is enormous.
    assert math.exp(-300.0) < math.exp(-60.0)*1.0e-90
