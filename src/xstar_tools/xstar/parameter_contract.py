"""XSTAR 2.59g public parameter contract for xstar_tools 0.6.82.23.

The executable validation envelope comes from the supplied stock ``xstar.par``.
Manual Table-1/detailed-default conflicts are recorded in the packaged ledger
and are not silently reconciled.  This module intentionally contains no new
science algorithms; it normalizes defaults, types, ranges, and provenance.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Final, Mapping
import math

@dataclass(frozen=True)
class ParameterRule:
    name: str
    kind: str
    default: Any
    minimum: float | int | None = None
    maximum: float | int | None = None
    mode: str = "h"
    classification: str = "science"

ELEMENT_SYMBOLS: Final = ("h","he","li","be","b","c","n","o","f","ne","na","mg","al","si","p","s","cl","ar","k","ca","sc","ti","v","cr","mn","fe","co","ni","cu","zn")
ABUNDANCE_PARAMETER_NAMES: Final = tuple(symbol + "abund" for symbol in ELEMENT_SYMBOLS)

_RULE_ROWS = [('cfrac', 'real', 0.0, 0.0, 1.0, 'h', 'science'), ('temperature', 'real', 400.0, 0.0, 10000.0, 'a', 'science'), ('lcpres', 'integer', 0, 0, 1, 'h', 'science'), ('pressure', 'real', 0.03, 0.0, 1.0, 'a', 'science'), ('density', 'real', 10000.0, 0.0, 1e+21, 'a', 'science'), ('spectrum', 'string', 'pow', None, None, 'a', 'science'), ('spectrum_file', 'string', 'spct.dat', None, None, 'a', 'science'), ('spectun', 'integer', 0, 0, 1, 'a', 'science'), ('trad', 'real', -1.0, None, None, 'a', 'science'), ('rlrad38', 'real', 1e-06, 0.0, 10000000000.0, 'a', 'science'), ('column', 'real', 1e+17, 0.0, 1e+25, 'a', 'science'), ('rlogxi', 'real', 5.0, -10.0, 10.0, 'a', 'science'), ('abundtbl', 'string', 'xdef', None, None, 'a', 'science'), ('habund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('heabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('liabund', 'real', 0.0, 0.0, 100.0, 'h', 'science'), ('beabund', 'real', 0.0, 0.0, 100.0, 'h', 'science'), ('babund', 'real', 0.0, 0.0, 100.0, 'h', 'science'), ('cabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('nabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('oabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('fabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('neabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('naabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('mgabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('alabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('siabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('pabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('sabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('clabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('arabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('kabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('caabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('scabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('tiabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('vabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('crabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('mnabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('feabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('coabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('niabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('cuabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('znabund', 'real', 1.0, 0.0, 100.0, 'h', 'science'), ('modelname', 'string', 'XSTAR Default', None, None, 'a', 'metadata/interface'), ('nsteps', 'integer', 3, 1, 1000, 'h', 'radial-control'), ('niter', 'integer', 0, None, None, 'h', 'science'), ('lwrite', 'integer', 0, 0, 1, 'h', 'output-control'), ('lprint', 'integer', 0, -1, 6, 'h', 'output-control'), ('lstep', 'integer', 0, None, None, 'h', 'output-control'), ('emult', 'real', 0.5, 1e-06, 1000000.0, 'h', 'radial-control'), ('taumax', 'real', 5.0, 1.0, 10000.0, 'h', 'radial-control'), ('xeemin', 'real', 0.1, 1e-06, 0.5, 'h', 'radial-control'), ('critf', 'real', 1e-07, 1e-24, 0.1, 'h', 'science'), ('vturbi', 'real', 1.0, 0.0, 30000.0, 'h', 'science'), ('radexp', 'real', 0.0, -3.0, 3.0, 'h', 'radial-control'), ('ncn2', 'integer', 9999, 999, 999999, 'h', 'science'), ('loopcontrol', 'integer', 0, 0, 30000, 'h', 'metadata/interface'), ('npass', 'integer', 1, 1, 10000, 'h', 'radial-control'), ('mode', 'string', 'ql', None, None, 'h', 'metadata/interface')]
PARAMETER_RULES: Final = {name: ParameterRule(name, kind, default, minimum, maximum, mode, classification) for name,kind,default,minimum,maximum,mode,classification in _RULE_ROWS}
XSTAR_PAR_DEFAULTS: Final = {name: rule.default for name, rule in PARAMETER_RULES.items()}

def coerce_and_validate_parameter(name: str, value: Any) -> Any:
    key=str(name).strip().lower()
    if key not in PARAMETER_RULES:
        raise KeyError(key)
    rule=PARAMETER_RULES[key]
    if rule.kind == "string":
        return str(value)
    if rule.kind == "integer":
        if isinstance(value, bool):
            iv=int(value)
        else:
            fv=float(value)
            if not math.isfinite(fv) or fv != math.trunc(fv):
                raise ValueError(f"{key} must be an integer")
            iv=int(fv)
        result=iv
    else:
        result=float(value)
        if not math.isfinite(result):
            raise ValueError(f"{key} must be finite")
    # XSTAR 2.59g source has a hidden density.dat branch at radexp < -99.
    # Keep the stock XPI analytic envelope (-3..3), but admit that literal
    # source sentinel domain through the public runtime. Values in the gap
    # [-99,-3) remain invalid.
    source_density_table_sentinel = key == "radexp" and result < -99.0
    if rule.minimum is not None and result < rule.minimum and not source_density_table_sentinel:
        raise ValueError(f"{key} must be >= {rule.minimum}")
    if rule.maximum is not None and result > rule.maximum:
        raise ValueError(f"{key} must be <= {rule.maximum}")
    return result

def normalize_public_parameter_values(values: Mapping[str, Any]) -> dict[str, Any]:
    out=dict(XSTAR_PAR_DEFAULTS)
    for key,value in values.items():
        name=str(key).strip().lower()
        if name in PARAMETER_RULES:
            out[name]=coerce_and_validate_parameter(name,value)
        else:
            out[name]=value
    return out

__all__=["ParameterRule","PARAMETER_RULES","XSTAR_PAR_DEFAULTS","ELEMENT_SYMBOLS","ABUNDANCE_PARAMETER_NAMES","coerce_and_validate_parameter","normalize_public_parameter_values"]
