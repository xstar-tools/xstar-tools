"""Strict binary64 parity classification for native spectral shadows.

v0.6.46.3 removes final-array ULP tolerance. Qualification supplies complete
source-profile samples for Gaussian/Voigt lines, so every committed spectral
array must compare exactly.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def binary64_ordered_bits(values: np.ndarray) -> np.ndarray:
    """Return monotonic unsigned encodings for diagnostic ULP reporting."""
    bits = np.ascontiguousarray(np.asarray(values, dtype=np.float64)).view(np.uint64)
    sign = np.uint64(0x8000000000000000)
    return np.where((bits & sign) != 0, ~bits, bits | sign)


def classify_spectral_shadow_arrays(
    pairs: Sequence[tuple[str, Any, Any]], *, phase: str
) -> tuple[str, dict[str, Any]]:
    """Require exact equality for every spectral shadow array."""
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
            "policy": "exact_profile_oracle",
        }
        finite = np.isfinite(left[where]) & np.isfinite(right[where])
        if bool(np.all(finite)):
            lbits = binary64_ordered_bits(left[where])
            rbits = binary64_ordered_bits(right[where])
            distances = np.where(lbits >= rbits, lbits - rbits, rbits - lbits)
            detail["max_ulp"] = int(np.max(distances)) if distances.size else 0
        return "shadow_mismatch", detail
    return "shadow_match", {}


__all__ = ["binary64_ordered_bits", "classify_spectral_shadow_arrays"]
