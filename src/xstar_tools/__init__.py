"""xstar-tools: source-faithful Python/C++ tools for XSTAR workflows.

Top-level imports are intentionally lightweight.  Use subpackages such as
``xstar_tools.atomic`` and ``xstar_tools.xstar`` for functionality.
"""

from __future__ import annotations

__version__ = "0.6.48.12.3.45.3.3.8"
__science_revision__ = __version__

# Stable execution-mode API is imported lazily enough to keep top-level startup light.
from .execution import BackendMode, ExecutionMode, package_version, run_xstar
from .config import XStarConfig
from .result import XStarProducts, XStarResult
from .data import XStarData
__package_version__ = package_version()

__all__ = ["__version__", "__science_revision__", "__package_version__", "BackendMode", "ExecutionMode", "XStarConfig", "XStarResult", "XStarProducts", "XStarData", "run_xstar"]
