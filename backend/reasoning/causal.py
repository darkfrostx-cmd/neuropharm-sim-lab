"""Simplified causal inference helpers.

The implementation provides a light-weight alternative to DoWhy/EconML.  It
estimates an average treatment effect using a difference-in-means estimator with
Student's t confidence scoring.  The estimator intentionally accepts plain
numeric sequences so that unit tests can seed synthetic observations without
external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

try:  # pragma: no cover - optional dependency
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pd = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from dowhy import CausalModel  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    CausalModel = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from econml.dml import LinearDML  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    LinearDML = None  # type: ignore


@dataclass(slots=True)
class CounterfactualScenario:
    """Structured counterfactual prediction for a treatment setting."""

    label: str
    treatment_value: float
    predicted_outcome: float


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
    assumption_graph: str | None = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    counterfactuals: List[CounterfactualScenario] = field(default_factory=list)


class CausalEffectEstimator:
    """Estimate treatment effects using DoWhy when available."""

    def __init__(self, minimum_samples: int = 2, bootstrap_iterations: int = 200, random_seed: int | None = 13) -> None:
        self.minimum_samples = minimum_samples
        self.bootstrap_iterations = bootstrap_iterations
        self.random_seed = random_seed

    def estimate_effect(
        self,
        treatment_values: Sequence[float],
        outcome_values: Sequence[float],
        treatment_name: str,
        outcome_name: str,
        assumptions: Dict[str, Any] | None = None,
    ) -> CausalSummary | None:
        base_summary = self._difference_in_means_summary(
            treatment_values,
            outcome_values,
            treatment_name,
            outcome_name,
            assumptions,
        )
        if base_summary is None:
            return None
        dowhy_summary = self._dowhy_summary(
            treatment_values,
            outcome_values,
            treatment_name,
            outcome_name,
            base_summary,
            assumptions or {},
        )
        if dowhy_summary is not None:
            return dowhy_summary
        econml_summary = self._econml_counterfactuals(
            treatment_values,
            outcome_values,
            treatment_name,
            outcome_name,
            base_summary,
            assumptions or {},
        )
        if econml_summary is not None:
            return econml_summary
        return base_summary

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _difference_in_means_summary(
        self,
        treatment_values: Sequence[float],
        outcome_values: Sequence[float],
        treatment_name: str,
        outcome_name: str,
        assumptions: Dict[str, Any] | None,
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
        assumption_graph = None
        diagnostics: Dict[str, Any] = {
            "method": "difference_in_means",
            "standard_error": se,
            "baseline_outcome": float(outcome.mean()),
            "median_treatment": float(np.median(treatment)),
        }
        if assumptions:
            if assumptions.get("graph"):
                assumption_graph = str(assumptions["graph"])
            diagnostics["assumptions"] = {
                "confounders": list(assumptions.get("confounders", [])),
                "mediators": list(assumptions.get("mediators", [])),
                "instruments": list(assumptions.get("instruments", [])),
            }
        counterfactuals = self._compute_counterfactuals(treatment, outcome)
        bootstrap_stats = self._bootstrap_interval(treatment, outcome)
        if bootstrap_stats is not None:
            ci_low, ci_high, stability = bootstrap_stats
            diagnostics["bootstrap_ci"] = (ci_low, ci_high)
            diagnostics["bootstrap_stability"] = stability
            if ci_low > 0 or ci_high < 0:
                confidence = float(max(confidence, min(0.99, 0.7 + stability * 0.25)))
            else:
                confidence = float(max(confidence, min(0.95, 0.6 + stability * 0.2)))
        description = self._build_description(
            method="Difference-in-means",
            effect=effect,
            direction=direction,
            outcome_name=outcome_name,
            treatment_name=treatment_name,
            confidence=confidence,
            n_treated=int(treated_outcomes.size),
            n_control=int(control_outcomes.size),
            confidence_interval=diagnostics.get("bootstrap_ci"),
            extra_note="Counterfactuals available." if counterfactuals else None,
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
            assumption_graph=assumption_graph,
            diagnostics=diagnostics,
            counterfactuals=counterfactuals,
        )

    def _dowhy_summary(
        self,
        treatment_values: Sequence[float],
        outcome_values: Sequence[float],
        treatment_name: str,
        outcome_name: str,
        base_summary: CausalSummary,
        assumptions: Dict[str, Any],
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
            graph = assumptions.get("graph") or "digraph { treatment -> outcome; }"
            model = CausalModel(
                data=frame,
                treatment="treatment",
                outcome="outcome",
                graph=str(graph),
            )
            identified = model.identify_effect()
            estimate = model.estimate_effect(identified, method_name="backdoor.linear_regression")
            effect_value = float(getattr(estimate, "value", 0.0))
        except Exception:  # pragma: no cover - depends on optional dependency
            return None

        direction = "increase" if effect_value > 0 else "decrease" if effect_value < 0 else "neutral"
        base_confidence = float(base_summary.confidence)
        confidence = float(max(base_confidence, min(0.95, 0.6 + min(0.3, abs(effect_value)))))
        description = self._build_description(
            method="DoWhy linear regression",
            effect=effect_value,
            direction=direction,
            outcome_name=outcome_name,
            treatment_name=treatment_name,
            confidence=confidence,
            n_treated=base_summary.n_treated,
            n_control=base_summary.n_control,
            confidence_interval=base_summary.diagnostics.get("bootstrap_ci"),
            extra_note="Refutation available." if base_summary.counterfactuals else None,
        )
        diagnostics = dict(base_summary.diagnostics)
        diagnostics.update(
            {
                "method": "dowhy.backdoor.linear_regression",
                "dowhy_effect": effect_value,
            }
        )
        if assumptions.get("graph"):
            diagnostics.setdefault("assumptions", {})
            diagnostics["assumptions"]["graph"] = str(assumptions["graph"])

        try:  # pragma: no cover - optional dependency
            refutation = model.refute_estimate(identified, estimate, method_name="random_common_cause")
            new_effect = getattr(refutation, "new_effect", None)
            if new_effect is not None:
                shift = abs(float(new_effect) - effect_value)
                confidence = float(max(confidence, min(0.95, 0.65 + max(0.0, 0.2 - shift))))
                description += f" Refutation via random common cause altered the effect by {shift:.3f}."
                diagnostics["dowhy_refutation_delta"] = shift
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
            assumption_graph=base_summary.assumption_graph or str(assumptions.get("graph") or ""),
            diagnostics=diagnostics,
            counterfactuals=list(base_summary.counterfactuals),
        )

    def _econml_counterfactuals(
        self,
        treatment_values: Sequence[float],
        outcome_values: Sequence[float],
        treatment_name: str,
        outcome_name: str,
        base_summary: CausalSummary,
        assumptions: Dict[str, Any],
    ) -> CausalSummary | None:
        if LinearDML is None:  # pragma: no cover - optional dependency
            return None
        try:
            treatment = np.asarray(treatment_values, dtype=float)
            outcome = np.asarray(outcome_values, dtype=float)
            if treatment.size != outcome.size or treatment.size < self.minimum_samples * 2:
                return None
            controls = assumptions.get("controls")
            x: np.ndarray | None
            if controls is not None:
                x = np.asarray(controls, dtype=float)
                if x.ndim == 1:
                    x = x.reshape(-1, 1)
                if x.shape[0] != treatment.size:
                    x = None
            else:
                x = None
            model = LinearDML()
            model.fit(Y=outcome, T=treatment, X=x, W=None)
            scenarios = [
                float(np.quantile(treatment, 0.1)),
                float(np.median(treatment)),
                float(np.quantile(treatment, 0.9)),
            ]
            counterfactuals: List[CounterfactualScenario] = []
            baseline = float(np.mean(outcome))
            effects = model.effect(x) if x is not None else model.effect(None)
            cate = float(np.mean(effects))
            mean_treatment = float(np.mean(treatment))
            for label, value in zip(["p10", "median", "p90"], scenarios):
                delta = value - mean_treatment
                predicted = baseline + cate * delta
                counterfactuals.append(
                    CounterfactualScenario(
                        label=f"econml_{label}",
                        treatment_value=value,
                        predicted_outcome=float(predicted),
                    )
                )
        except Exception:  # pragma: no cover - optional dependency
            return None

        diagnostics = dict(base_summary.diagnostics)
        diagnostics["method"] = "econml.lineardml"

        description = self._build_description(
            method="EconML LinearDML",
            effect=base_summary.effect,
            direction=base_summary.direction,
            outcome_name=outcome_name,
            treatment_name=treatment_name,
            confidence=base_summary.confidence,
            n_treated=base_summary.n_treated,
            n_control=base_summary.n_control,
            confidence_interval=base_summary.diagnostics.get("bootstrap_ci"),
            extra_note="Counterfactuals enhanced via EconML.",
        )

        return CausalSummary(
            treatment=treatment_name,
            outcome=outcome_name,
            effect=base_summary.effect,
            direction=base_summary.direction,
            confidence=base_summary.confidence,
            n_treated=base_summary.n_treated,
            n_control=base_summary.n_control,
            description=description,
            assumption_graph=base_summary.assumption_graph,
            diagnostics=diagnostics,
            counterfactuals=counterfactuals,
        )

    def _compute_counterfactuals(self, treatment: np.ndarray, outcome: np.ndarray) -> List[CounterfactualScenario]:
        if treatment.size == 0:
            return []
        variance = float(np.var(treatment, ddof=1)) if treatment.size > 1 else 0.0
        baseline = float(np.mean(outcome))
        if variance <= 1e-12:
            return [
                CounterfactualScenario(
                    label="observed",
                    treatment_value=float(treatment.mean()),
                    predicted_outcome=baseline,
                )
            ]
        covariance = float(np.cov(treatment, outcome, ddof=1)[0, 1]) if treatment.size > 1 else 0.0
        slope = covariance / variance if variance else 0.0
        intercept = baseline - slope * float(np.mean(treatment))
        quantiles = {
            "p10": float(np.quantile(treatment, 0.1)),
            "median": float(np.median(treatment)),
            "p90": float(np.quantile(treatment, 0.9)),
        }
        scenarios: List[CounterfactualScenario] = []
        for label, value in quantiles.items():
            predicted = intercept + slope * value
            scenarios.append(
                CounterfactualScenario(label=label, treatment_value=value, predicted_outcome=float(predicted))
            )
        return scenarios

    def _build_description(
        self,
        *,
        method: str,
        effect: float,
        direction: str,
        outcome_name: str,
        treatment_name: str,
        confidence: float,
        n_treated: int,
        n_control: int,
        confidence_interval: Tuple[float, float] | None = None,
        extra_note: str | None = None,
    ) -> str:
        description = (
            f"{method} suggests a {direction} of {effect:.3f} in {outcome_name} when manipulating {treatment_name} "
            f"(confidence {confidence:.2f}, n_treated={n_treated}, n_control={n_control})."
        )
        if confidence_interval is not None:
            description = (
                f"{description} Bootstrap 95% CI [{confidence_interval[0]:.3f}, {confidence_interval[1]:.3f}]."
            )
        if extra_note:
            description = f"{description} {extra_note}"
        return description

    def _bootstrap_interval(self, treatment: np.ndarray, outcome: np.ndarray) -> Tuple[float, float, float] | None:
        if self.bootstrap_iterations <= 0 or treatment.size != outcome.size:
            return None
        if treatment.size < self.minimum_samples * 2:
            return None
        rng = np.random.default_rng(self.random_seed)
        diffs: List[float] = []
        for _ in range(self.bootstrap_iterations):
            sample_idx = rng.integers(0, treatment.size, size=treatment.size)
            sampled_treatment = treatment[sample_idx]
            sampled_outcome = outcome[sample_idx]
            treated_mask = sampled_treatment > np.median(sampled_treatment)
            control_mask = ~treated_mask
            if treated_mask.sum() < self.minimum_samples or control_mask.sum() < self.minimum_samples:
                continue
            diff = float(sampled_outcome[treated_mask].mean() - sampled_outcome[control_mask].mean())
            diffs.append(diff)
        if len(diffs) < max(10, self.bootstrap_iterations // 10):
            return None
        low = float(np.percentile(diffs, 2.5))
        high = float(np.percentile(diffs, 97.5))
        stability = float(1.0 / (1.0 + float(np.std(diffs))))
        return low, high, stability


__all__ = ["CausalEffectEstimator", "CausalSummary", "CounterfactualScenario"]
