"""Strict binary64 parity classification for native spectral shadows.

Every field remains bit-exact except ``opakc`` in the emissivity phase, where
one ULP is explicitly tolerated for the far Gaussian-profile tail.  This
bounded exception accounts for NumPy scalar ``exp`` versus platform C++ libm
without permitting any material physics or ordering drift.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def binary64_ordered_bits(values: np.ndarray) -> np.ndarray:
    """Return monotonic unsigned encodings for binary64 ULP comparisons."""
    bits = np.ascontiguousarray(np.asarray(values, dtype=np.float64)).view(np.uint64)
    sign = np.uint64(0x8000000000000000)
    return np.where((bits & sign) != 0, ~bits, bits | sign)


def classify_spectral_shadow_arrays(
    pairs: Sequence[tuple[str, Any, Any]], *, phase: str
) -> tuple[str, dict[str, Any]]:
    """Classify exact spectral parity, allowing one ULP only for ``opakc``."""
    tolerated: dict[str, Any] = {}
    for name, accepted, candidate in pairs:
        left = np.asarray(accepted, dtype=np.float64).reshape(-1)
        right = np.asarray(candidate, dtype=np.float64).reshape(-1)
        if left.shape != right.shape:
            return "shadow_mismatch", {
                "phase": phase,
                "field": name,
                "reason": "shape",
                "python_shape": tuple(left.shape),
                "native_shape": tuple(right.shape),
            }
        exact = (left == right) | (np.isnan(left) & np.isnan(right))
        if bool(np.all(exact)):
            continue
        where = np.flatnonzero(~exact)
        at = int(where[0])
        detail: dict[str, Any] = {
            "phase": phase,
            "field": name,
            "flat_index": at,
            "python": left[at].item(),
            "native": right[at].item(),
            "differing_values": int(where.size),
        }
        if (
            name == "opakc"
            and phase == "emis"
            and bool(np.all(np.isfinite(left[where])))
            and bool(np.all(np.isfinite(right[where])))
        ):
            lbits = binary64_ordered_bits(left[where])
            rbits = binary64_ordered_bits(right[where])
            distances = np.where(lbits >= rbits, lbits - rbits, rbits - lbits)
            max_ulp = int(np.max(distances)) if distances.size else 0
            detail["max_ulp"] = max_ulp
            detail["policy"] = "emis_opakc_only_max_1_ulp"
            if max_ulp <= 1:
                tolerated = detail
                continue
        return "shadow_mismatch", detail
    if tolerated:
        return "shadow_ulp_tolerated", tolerated
    return "shadow_match", {}


__all__ = ["binary64_ordered_bits", "classify_spectral_shadow_arrays"]
