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

try:  # pragma: no cover - optional dependency
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pd = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from dowhy import CausalModel  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    CausalModel = None  # type: ignore


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
    """Estimate treatment effects using DoWhy when available."""

    def __init__(self, minimum_samples: int = 2) -> None:
        self.minimum_samples = minimum_samples

    def estimate_effect(
        self,
        treatment_values: Sequence[float],
        outcome_values: Sequence[float],
        treatment_name: str,
        outcome_name: str,
    ) -> CausalSummary | None:
        base_summary = self._difference_in_means_summary(
            treatment_values, outcome_values, treatment_name, outcome_name
        )
        if base_summary is None:
            return None
        dowhy_summary = self._dowhy_summary(
            treatment_values,
            outcome_values,
            treatment_name,
            outcome_name,
            base_summary,
        )
        return dowhy_summary or base_summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _difference_in_means_summary(
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
            f"Difference-in-means suggests a {direction} of {effect:.3f} in {outcome_name} "
            f"when manipulating {treatment_name} (confidence {confidence:.2f}, "
            f"n_treated={treated_outcomes.size}, n_control={control_outcomes.size})."
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

    def _dowhy_summary(
        self,
        treatment_values: Sequence[float],
        outcome_values: Sequence[float],
        treatment_name: str,
        outcome_name: str,
        base_summary: CausalSummary,
    ) -> CausalSummary | None:
        if CausalModel is None or pd is None:  # pragma: no cover - optional dependency
            return None
        if base_summary.n_treated < self.minimum_samples or base_summary.n_control < self.minimum_samples:
            return None
        try:
            frame = pd.DataFrame(
                {
                    "treatment": list(treatment_values),
                    "outcome": list(outcome_values),
                }
            )
            model = CausalModel(
                data=frame,
                treatment="treatment",
                outcome="outcome",
                graph="digraph { treatment -> outcome; }",
            )
            identified = model.identify_effect()
            estimate = model.estimate_effect(identified, method_name="backdoor.linear_regression")
            effect_value = float(getattr(estimate, "value", 0.0))
        except Exception:  # pragma: no cover - depends on optional dependency
            return None

        direction = "increase" if effect_value > 0 else "decrease" if effect_value < 0 else "neutral"
        base_confidence = float(base_summary.confidence)
        confidence = float(max(base_confidence, min(0.95, 0.6 + min(0.3, abs(effect_value)))))
        description = (
            f"DoWhy linear regression estimates a {direction} of {effect_value:.3f} in {outcome_name} "
            f"when manipulating {treatment_name}. {base_summary.description}"
        )

        try:  # pragma: no cover - optional dependency
            refutation = model.refute_estimate(identified, estimate, method_name="random_common_cause")
            new_effect = getattr(refutation, "new_effect", None)
            if new_effect is not None:
                shift = abs(float(new_effect) - effect_value)
                confidence = float(max(confidence, min(0.95, 0.65 + max(0.0, 0.2 - shift))))
                description += f" Refutation via random common cause altered the effect by {shift:.3f}."
        except Exception:
            pass

        return CausalSummary(
            treatment=treatment_name,
            outcome=outcome_name,
            effect=effect_value,
            direction=direction,
            confidence=confidence,
            n_treated=base_summary.n_treated,
            n_control=base_summary.n_control,
            description=description,
        )


__all__ = ["CausalEffectEstimator", "CausalSummary"]

