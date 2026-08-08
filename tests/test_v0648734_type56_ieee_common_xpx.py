from __future__ import annotations

import math
import re
from pathlib import Path

from xstar_tools.xstar.constants import (
    COLLISION_RATE_COEFFICIENT_PER_SQRT_K,
    LEGACY_COLLISION_ERG_PER_EV,
    MODERN_BOLTZMANN_EV_PER_K,
    SOURCE_COLLISION_BOLTZMANN_EV_PER_K,
)
from xstar_tools.xstar.call2_helium_type56_xpx_restoration import RELEASE


def test_release_and_shared_constant_values() -> None:
    assert RELEASE == "0.6.48.7.34"
    assert SOURCE_COLLISION_BOLTZMANN_EV_PER_K == 8.61707e-5
    assert MODERN_BOLTZMANN_EV_PER_K == 8.617333262145e-5
    assert COLLISION_RATE_COEFFICIENT_PER_SQRT_K == 8.626e-6
    assert LEGACY_COLLISION_ERG_PER_EV == 1.602197e-12


def test_constants_def_is_single_numeric_source_for_python_and_cpp() -> None:
    root = Path("src/xstar_tools")
    definition = root / "xstar/cpp/constants.def"
    python_loader = root / "xstar/constants.py"
    cpp_header = root / "xstar/cpp/xstar_constants.h"
    assert definition.is_file()
    assert 'with_name("cpp") / "constants.def"' in python_loader.read_text()
    assert '#include "constants.def"' in cpp_header.read_text()

    pattern = re.compile(
        r"(8\.617(?:07|333262(?:145)?|385)?e-[58]|0\.8617(?:07|333262145)?)"
    )
    hits: list[str] = []
    for suffix in ("*.py", "*.cpp", "*.h"):
        for path in root.rglob(suffix):
            if path == python_loader:
                continue
            for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{path}:{line_number}")
    assert hits == []


def test_type56_python_expression_contract() -> None:
    text = Path("src/xstar_tools/collisions.py").read_text()
    assert "KB_EV_PER_K = SOURCE_COLLISION_BOLTZMANN_EV_PER_K" in text
    assert "QCOEF = COLLISION_RATE_COEFFICIENT_PER_SQRT_K" in text
    assert "rootT = math.sqrt(temperature_k)" in text
    assert "QCOEF * u * math.exp(-float(delta_e_ev) / kT)" in text

    upsilon = 2.75
    delta_e_ev = 41.25
    g_lower = 3.0
    g_upper = 5.0
    temperature_k = 1.23456789e6
    root_t = math.sqrt(temperature_k)
    k_t = SOURCE_COLLISION_BOLTZMANN_EV_PER_K * temperature_k
    q_exc = (
        COLLISION_RATE_COEFFICIENT_PER_SQRT_K
        * upsilon
        * math.exp(-delta_e_ev / k_t)
        / (g_lower * root_t)
    )
    q_deexc = (
        COLLISION_RATE_COEFFICIENT_PER_SQRT_K
        * upsilon
        / (g_upper * root_t)
    )
    assert math.isfinite(q_exc) and q_exc > 0.0
    assert math.isfinite(q_deexc) and q_deexc > 0.0


def test_cpp_type56_and_common_xpx_contract() -> None:
    text = Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "xstar_constants::kSourceCollisionBoltzmannEvPerK * input.temperature_k" in text
    assert "const double root_t = std::sqrt(input.temperature_k);" in text
    assert "xstar_constants::kCollisionRateCoefficientPerSqrtK * ups" in text
    assert "xstar_constants::kLegacyCollisionErgPerEv" in text
    assert "out.type56_upsilon = ups;" in text
    assert "c.density_scale = record.matrix_enabled ? input.hydrogen_density_cm3 : 1.0;" in text
    assert "density_scale=input.hydrogen_density_cm3" not in text
    assert "density_scale = input.hydrogen_density_cm3" not in text


def test_capture_audit_runner_and_gates() -> None:
    capture = Path(
        "src/xstar_tools/xstar/v0472_call2_helium_solve_state_capture.py"
    ).read_text()
    audit = Path(
        "src/xstar_tools/xstar/call2_helium_type56_xpx_restoration.py"
    ).read_text()
    runner = Path("run_v048734_type56_ieee_common_xpx.sh").read_text()
    assert "v0472_call2_eval1_he_type56_records.csv" in capture
    assert "diag_upsilon" in capture
    for gate in (
        "CALL2_HE_TYPE56_UPSILON_EXACT",
        "CALL2_HE_TYPE56_ANS1_EXACT",
        "CALL2_HE_TYPE56_ANS2_EXACT",
        "CALL2_HE_TYPE56_ANS5_EXACT",
        "CALL2_HE_TYPE56_ANS6_EXACT",
        "CALL2_HE_TYPE56_THERMAL_COEFFICIENTS_EXACT",
        "CALL2_HE_COMMON_XPX_MATRIX_SCALING",
        "CALL2_HE_TYPE53_NOT_DOUBLE_SCALED",
        "CALL2_HE_TYPE63_NOT_DOUBLE_SCALED",
    ):
        assert gate in audit
    assert '--temperature-k "$TYPE56_TEMPERATURE"' in runner
    assert "call2_helium_type56_xpx_restoration" in runner
