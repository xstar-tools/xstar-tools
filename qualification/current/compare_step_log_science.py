#!/usr/bin/env python3
"""Current public STEP comparator overlay.

The frozen 0.6.48.12.3.45.3.3.2 comparator remains immutable under
``qualification/frozen/option23``.  This productization overlay restores the
already-qualified 0.6.48.12.3.42.1.x Option-24 semantic quarantine for the
canonical XSTAR Fortran ``pprint(24)`` stale-local alias bug.

No candidate science is changed.  Common-row numerical/energy science must
still pass the frozen <1% criterion.  Publication inventory is accepted only
when every candidate-only Option-24 identity is clean He II metadata and every
reference-only identity is a numerically negligible (<1e-15) tail.  Exact
inventory also passes trivially.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
FROZEN = HERE.parent / "frozen" / "option23" / "compare_step_log_science.py"
_spec = importlib.util.spec_from_file_location("xstar_tools_frozen_stepcmp_option23", FROZEN)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load frozen STEP comparator: {FROZEN}")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_base_compare_identity_rows = _base.compare_identity_rows


def compare_option24_fortran_semantics(
    c: dict[Any, dict[str, Any]],
    r: dict[Any, dict[str, Any]],
) -> dict[str, Any]:
    """Apply the frozen numerical gate plus the historical Option-24 quarantine."""
    result = _base_compare_identity_rows(
        "24", c, r, ("value_1", "value_2"), ("energy",), ignore_membership=False
    )
    ckeys, rkeys = set(c), set(r)
    conly = ckeys - rkeys
    ronly = rkeys - ckeys
    inventory_exact = not conly and not ronly
    candidate_only_clean_heii = all(
        str(c[key].get("ion", "")).lower() == "he_ii" for key in conly
    )
    reference_only_tail_max = max(
        (
            max(
                abs(float(r[key].get("value_1", 0.0))),
                abs(float(r[key].get("value_2", 0.0))),
            )
            for key in ronly
        ),
        default=0.0,
    )
    stale_local_gate = inventory_exact or (
        candidate_only_clean_heii and reference_only_tail_max < 1.0e-15
    )
    result.update(
        {
            "inventory_exact": inventory_exact,
            "candidate_only_clean_heii": candidate_only_clean_heii,
            "reference_only_tail_max_abs": reference_only_tail_max,
            "fortran_stale_local_quirk_gate": stale_local_gate,
            "science_gate_policy": (
                "common-row numeric/energy science <1%; Option-24 inventory is accepted "
                "only for the qualified Fortran pprint(24) stale-local alias pattern "
                "(candidate-only clean He II and reference-only max abs <1e-15)"
            ),
            "scientific_accept": bool(result.get("numeric_science_accept") and stale_local_gate),
        }
    )
    return result


def _patched_compare_identity_rows(
    section: str,
    c: dict[Any, dict[str, Any]],
    r: dict[Any, dict[str, Any]],
    value_fields: tuple[str, ...],
    metadata_fields: tuple[str, ...] = (),
    ignore_membership: bool = False,
) -> dict[str, Any]:
    if str(section) == "24":
        return compare_option24_fortran_semantics(c, r)
    return _base_compare_identity_rows(
        section, c, r, value_fields, metadata_fields, ignore_membership=ignore_membership
    )


_base.compare_identity_rows = _patched_compare_identity_rows


def _json_argument(argv: list[str]) -> Path | None:
    for i, arg in enumerate(argv):
        if arg == "--json" and i + 1 < len(argv):
            return Path(argv[i + 1])
        if arg.startswith("--json="):
            return Path(arg.split("=", 1)[1])
    return None


def main() -> int:
    rc = int(_base.main())
    json_path = _json_argument(sys.argv[1:])
    if json_path is not None and json_path.is_file():
        try:
            doc = json.loads(json_path.read_text())
            o24 = doc.get("sections", {}).get("24", {})
            print(
                "V064812345332_STEP_OPTION24_NUMERIC_SCIENCE="
                + ("ACCEPT" if o24.get("numeric_science_accept") else "REJECT")
            )
            print(
                "V064812345332_STEP_OPTION24_INVENTORY_EXACT="
                + ("YES" if o24.get("inventory_exact") else "NO")
            )
            print(
                "V064812345332_STEP_OPTION24_FORTRAN_STALE_LOCAL_QUIRK="
                + ("ACCEPT" if o24.get("fortran_stale_local_quirk_gate") else "REJECT")
            )
            print(
                "V064812345332_STEP_OPTION24_REFERENCE_ONLY_MAX_ABS="
                + f"{float(o24.get('reference_only_tail_max_abs', 0.0)):.17g}"
            )
        except Exception:
            pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
