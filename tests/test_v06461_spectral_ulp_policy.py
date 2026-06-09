from __future__ import annotations

import numpy as np

from xstar_tools.xstar.spectral_parity import classify_spectral_shadow_arrays


def test_exact_spectral_match_is_accepted() -> None:
    accepted = np.array([1.0, 2.0], dtype=np.float64)
    status, detail = classify_spectral_shadow_arrays(
        (("opakc", accepted, accepted.copy()),), phase="emis"
    )
    assert status == "shadow_match"
    assert detail == {}


def test_one_ulp_final_array_difference_is_rejected() -> None:
    accepted = np.array([1.0], dtype=np.float64)
    candidate = np.nextafter(accepted, np.inf)
    status, detail = classify_spectral_shadow_arrays(
        (("opakc", accepted, candidate),), phase="emis"
    )
    assert status == "shadow_mismatch"
    assert detail["field"] == "opakc"
    assert detail["max_ulp"] == 1
    assert detail["policy"] == "exact_temporary_grid_oracle"


def test_shape_difference_is_rejected() -> None:
    status, detail = classify_spectral_shadow_arrays(
        (("oplin", np.zeros(2), np.zeros(3)),), phase="emis"
    )
    assert status == "shadow_mismatch"
    assert detail["reason"] == "shape"
