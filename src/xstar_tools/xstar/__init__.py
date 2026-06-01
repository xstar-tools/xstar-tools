"""Source-faithful one-model XSTAR runtime package.

Most implementation modules are imported explicitly to keep
``import xstar_tools.xstar`` lightweight in environments where optional runtime
dependencies such as astropy are not installed yet.
"""

from __future__ import annotations

__all__: list[str] = []
