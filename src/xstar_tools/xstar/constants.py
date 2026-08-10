# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: constants.f90; literal-sensitive uses in rread1.f90 / dsec.f90 / trnfrc.f90
#   Role: Expose the source constants shared by the Python translation and the relocated cpp/constants.def table.
#   Relation: Source-exact or qualification-pinned constants; do not modernize rounded legacy literals without science requalification.
#   Concordance: INPUT-001; THERM-001; RADIAL-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Shared XSTAR numerical constants loaded from ``xstar/cpp/constants.def``.

The definition file lives with the native backend because C++ includes it directly;
Python parses the same file so both implementations share one numerical source of
truth.  The current benchmark contract intentionally keeps the source-faithful
collision value.  A future CODATA promotion must update the definition file only
after reference recapture.
"""
from __future__ import annotations

from pathlib import Path
import re

_DEFINITION = re.compile(
    r"^XSTAR_CONSTANT\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*([^\)]+?)\s*\)\s*$"
)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load constants for this module while preserving the surrounding source/runtime invariants.
# Reference context: Source constant loading and Fortran-kind preservation; no independent paper algorithm.
# XSTAR-FUNCTION-COMMENT-END
def _load_constants() -> dict[str, float]:
    path = Path(__file__).with_name("cpp") / "constants.def"
    values: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("//"):
            continue
        match = _DEFINITION.match(text)
        if not match:
            raise RuntimeError(f"invalid XSTAR constant definition: {text}")
        name, literal = match.groups()
        values[name] = float(literal)
    return values


_VALUES = _load_constants()
globals().update(_VALUES)

LEGACY_ROUNDED_BOLTZMANN_EV_PER_K = kLegacyRoundedBoltzmannEvPerK
SOURCE_COLLISION_BOLTZMANN_EV_PER_K = kSourceCollisionBoltzmannEvPerK
MODERN_SHORT_BOLTZMANN_EV_PER_K = kModernShortBoltzmannEvPerK
MODERN_BOLTZMANN_EV_PER_K = kModernBoltzmannEvPerK
LEGACY_BOLTZMANN_KEV_PER_K = kLegacyBoltzmannKevPerK
LEGACY_BOLTZMANN_EV_PER_T4 = kLegacyBoltzmannEvPerT4
MODERN_BOLTZMANN_EV_PER_T4 = kModernBoltzmannEvPerT4
BOLTZMANN_ERG_PER_K = kBoltzmannErgPerK
LEGACY_COLLISION_ERG_PER_EV = kLegacyCollisionErgPerEv
MODERN_ERG_PER_EV = kModernErgPerEv
COLLISION_RATE_COEFFICIENT_PER_SQRT_K = kCollisionRateCoefficientPerSqrtK
COLLISION_RATE_COEFFICIENT_PER_SQRT_T4 = kCollisionRateCoefficientPerSqrtT4

__all__ = sorted(_VALUES) + [
    "LEGACY_ROUNDED_BOLTZMANN_EV_PER_K",
    "SOURCE_COLLISION_BOLTZMANN_EV_PER_K",
    "MODERN_SHORT_BOLTZMANN_EV_PER_K",
    "MODERN_BOLTZMANN_EV_PER_K",
    "LEGACY_BOLTZMANN_KEV_PER_K",
    "LEGACY_BOLTZMANN_EV_PER_T4",
    "MODERN_BOLTZMANN_EV_PER_T4",
    "BOLTZMANN_ERG_PER_K",
    "LEGACY_COLLISION_ERG_PER_EV",
    "MODERN_ERG_PER_EV",
    "COLLISION_RATE_COEFFICIENT_PER_SQRT_K",
    "COLLISION_RATE_COEFFICIENT_PER_SQRT_T4",
]
