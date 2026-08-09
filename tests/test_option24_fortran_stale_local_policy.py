from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "qualification/current/compare_step_log_science.py"
spec = importlib.util.spec_from_file_location("stepcmp_current", PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def row(ion: str, v1: float, v2: float = 0.0, energy: float = 1.0):
    return {"ion": ion, "value_1": v1, "value_2": v2, "energy": energy}


def test_option24_accepts_qualified_fortran_stale_local_alias_inventory():
    c = {178: row("he_ii", 1.498e-21), 208: row("he_ii", 5.883e-3)}
    r = {6: row("he_ii", 9.824e-19), 900: row("he_ii", 1.0e-20)}
    # Common-row science is represented separately; make one clean common slot.
    c[100] = row("h_i", 2.0e-4)
    r[100] = row("h_i", 2.0e-4)
    # Historical rule accepts only if reference-only tails are negligible.  The
    # synthetic stale-alias slots above are not tails, so use the actual shape:
    r.pop(6); r.pop(900)
    r[777] = row("he_ii", 9.0e-16 * 0.1)
    out = mod.compare_option24_fortran_semantics(c, r)
    assert out["numeric_science_accept"]
    assert not out["inventory_exact"]
    assert out["candidate_only_clean_heii"]
    assert out["reference_only_tail_max_abs"] < 1.0e-15
    assert out["fortran_stale_local_quirk_gate"]
    assert out["scientific_accept"]


def test_option24_rejects_non_heii_candidate_only_identity():
    c = {100: row("h_i", 2e-4), 200: row("ca_xviii", 1e-20)}
    r = {100: row("h_i", 2e-4)}
    out = mod.compare_option24_fortran_semantics(c, r)
    assert out["numeric_science_accept"]
    assert not out["candidate_only_clean_heii"]
    assert not out["fortran_stale_local_quirk_gate"]
    assert not out["scientific_accept"]


def test_option24_rejects_material_reference_only_tail():
    c = {100: row("h_i", 2e-4), 200: row("he_ii", 1e-20)}
    r = {100: row("h_i", 2e-4), 300: row("he_ii", 1.0e-12)}
    out = mod.compare_option24_fortran_semantics(c, r)
    assert out["numeric_science_accept"]
    assert out["candidate_only_clean_heii"]
    assert out["reference_only_tail_max_abs"] >= 1.0e-15
    assert not out["fortran_stale_local_quirk_gate"]
    assert not out["scientific_accept"]
