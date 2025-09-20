"""Multiscale simulation components.

The :mod:`backend.simulation` package provides lightweight facades around the
specialised scientific simulators used by the Neuropharm Simulation Lab.  The
interfaces are deliberately typed and easily mockable so that unit tests can
exercise the orchestration logic without requiring PySB, The Virtual Brain, or
PK-Sim binaries at runtime.  Each submodule exposes a ``simulate_*`` function
that accepts a configuration dataclass and returns a structured result dataclass.
"""

from .engine import (
    MultiscaleResult,
    ReceptorInput,
    SimulationConfig,
    run_multiscale_pipeline,
)

__all__ = [
    "MultiscaleResult",
    "ReceptorInput",
    "SimulationConfig",
    "run_multiscale_pipeline",
]
