# 0.6.82.30.8.5 — Python Type-82 Fe UTA orientation closure

The accepted 0.6.82.30.8.4 C++ Fe run proves the canonical Fe reference closes when Type-82 UTA radiative records are inserted with the fixed-program low/high endpoint ABI.

Python has two relevant representations:

- `ucalc.py` deliberately returns canonical Type-82 `idest1=upper`, `idest2=lower`; `element_equilibrium.py::_lower_upper()` then performs the ordinary rate-type-4 energy ordering before emitting the first `(upper,lower)` matrix term. This pure-Python path was already correct and is unchanged numerically.
- `native_fixed_program.py` directly stores fixed-program `lower_row/upper_row`. It incorrectly used `upper_lower_source_pair()` for Type 82, reproducing the transposition fixed in C++ 0.6.82.30.8.4. This revision changes only that lowerer to `energy_order_source_pair()`.

No Type-82 rate coefficient, `ans1/ans2` ownership, thermal formula, solver equation, controller, transport, science revision, or ABI is changed.
