"""XSTAR2XSPEC/xstar2table compatibility and future grid workflows."""

from .build import build_xspec_tables
from .schema import XSpecTableProducts

__all__ = ["XSpecTableProducts", "build_xspec_tables"]
