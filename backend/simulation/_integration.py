"""Numerical integration utilities compatible across NumPy releases."""

from __future__ import annotations

from typing import Sequence

import numpy as np


def trapezoid_integral(values: Sequence[float] | np.ndarray, time: Sequence[float] | np.ndarray) -> float:
    """Return the area under the curve using the best available trapezoidal rule."""

    array_values = np.asarray(values, dtype=float)
    array_time = np.asarray(time, dtype=float)
    integrator = getattr(np, "trapezoid", None)
    if callable(integrator):
        return float(integrator(array_values, array_time))
    return float(np.trapz(array_values, array_time))


__all__ = ["trapezoid_integral"]
