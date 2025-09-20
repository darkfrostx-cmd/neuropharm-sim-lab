"""Simplified causal inference helpers.

The implementation provides a light-weight alternative to DoWhy/EconML.  It
estimates an average treatment effect using a difference-in-means estimator with
Student's t confidence scoring.  The estimator intentionally accepts plain
numeric sequences so that unit tests can seed synthetic observations without
external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np


@dataclass(slots=True)
class CausalSummary:
    """Summary of an estimated causal effect."""

    treatment: str
    outcome: str
    effect: float
    direction: str
    confidence: float
    n_treated: int
    n_control: int
    description: str


class CausalEffectEstimator:
    """Estimate treatment effects from observational samples."""

    def __init__(self, minimum_samples: int = 2) -> None:
        self.minimum_samples = minimum_samples

    def estimate_effect(
        self,
        treatment_values: Sequence[float],
        outcome_values: Sequence[float],
        treatment_name: str,
        outcome_name: str,
    ) -> CausalSummary | None:
        if len(treatment_values) != len(outcome_values) or len(treatment_values) < self.minimum_samples * 2:
            return None
        treatment = np.asarray(treatment_values, dtype=float)
        outcome = np.asarray(outcome_values, dtype=float)
        treated_mask = treatment > np.median(treatment)
        control_mask = ~treated_mask
        if treated_mask.sum() < self.minimum_samples or control_mask.sum() < self.minimum_samples:
            return None
        treated_outcomes = outcome[treated_mask]
        control_outcomes = outcome[control_mask]
        treat_mean = float(treated_outcomes.mean())
        control_mean = float(control_outcomes.mean())
        effect = treat_mean - control_mean
        direction = "increase" if effect > 0 else "decrease" if effect < 0 else "neutral"
        variance_treated = float(treated_outcomes.var(ddof=1)) if treated_outcomes.size > 1 else 0.0
        variance_control = float(control_outcomes.var(ddof=1)) if control_outcomes.size > 1 else 0.0
        se = math.sqrt(
            (variance_treated / max(treated_outcomes.size, 1)) + (variance_control / max(control_outcomes.size, 1))
        )
        if se == 0:
            confidence = 0.5 if effect == 0 else 0.95
        else:
            t_stat = abs(effect) / se
            confidence = float(1 / (1 + math.exp(-t_stat)))
        description = (
            f"{treatment_name} is estimated to cause a {direction} of {effect:.3f} "
            f"in {outcome_name} (confidence {confidence:.2f}, n_treated={treated_outcomes.size}, "
            f"n_control={control_outcomes.size})."
        )
        return CausalSummary(
            treatment=treatment_name,
            outcome=outcome_name,
            effect=effect,
            direction=direction,
            confidence=confidence,
            n_treated=int(treated_outcomes.size),
            n_control=int(control_outcomes.size),
            description=description,
        )


__all__ = ["CausalEffectEstimator", "CausalSummary"]

