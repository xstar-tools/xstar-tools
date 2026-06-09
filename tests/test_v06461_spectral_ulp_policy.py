from __future__ import annotations

import numpy as np

from xstar_tools.xstar.spectral_parity import classify_spectral_shadow_arrays


def test_opakc_one_ulp_is_explicitly_tolerated() -> None:
    accepted = np.asarray([0.0, 1.0, 2.0], dtype=np.float64)
    candidate = accepted.copy()
    candidate[1] = np.nextafter(candidate[1], np.inf)
    status, detail = classify_spectral_shadow_arrays(
        (("opakc", accepted, candidate),), phase="emis"
    )
    assert status == "shadow_ulp_tolerated"
    assert detail["field"] == "opakc"
    assert detail["max_ulp"] == 1
    assert detail["differing_values"] == 1


def test_opakc_two_ulps_is_rejected() -> None:
    accepted = np.asarray([1.0], dtype=np.float64)
    candidate = np.nextafter(np.nextafter(accepted, np.inf), np.inf)
    status, detail = classify_spectral_shadow_arrays(
        (("opakc", accepted, candidate),), phase="emis"
    )
    assert status == "shadow_mismatch"
    assert detail["max_ulp"] == 2


def test_non_opakc_one_ulp_is_rejected() -> None:
    accepted = np.asarray([1.0], dtype=np.float64)
    candidate = np.nextafter(accepted, np.inf)
    status, detail = classify_spectral_shadow_arrays(
        (("fline", accepted, candidate),), phase="emis"
    )
    assert status == "shadow_mismatch"
    assert detail["field"] == "fline"


def test_later_exact_field_does_not_hide_tolerated_opakc() -> None:
    accepted = np.asarray([1.0], dtype=np.float64)
    candidate = np.nextafter(accepted, np.inf)
    status, detail = classify_spectral_shadow_arrays(
        (("opakc", accepted, candidate), ("fline", accepted, accepted.copy())),
        phase="emis",
    )
    assert status == "shadow_ulp_tolerated"
    assert detail["max_ulp"] == 1
