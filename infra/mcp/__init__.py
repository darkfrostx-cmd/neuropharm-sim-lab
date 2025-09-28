"""Model Context Protocol utilities for Neuropharm Simulation Lab."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("neuropharm-sim-lab-mcp")
except PackageNotFoundError:  # pragma: no cover - package metadata only when installed
    __version__ = "0.0.0"

__all__ = ["__version__"]
