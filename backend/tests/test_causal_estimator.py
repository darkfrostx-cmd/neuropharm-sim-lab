from __future__ import annotations

import pytest

import backend.reasoning.causal as causal_module
from backend.reasoning.causal import CausalEffectEstimator


def _synthetic_observations() -> tuple[list[float], list[float]]:
    treatment = [0.0, 0.1, 0.2, 0.8, 1.0, 1.2]
    outcome = [0.05, 0.1, 0.2, 0.9, 1.1, 1.25]
    return treatment, outcome


def test_difference_in_means_counterfactuals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(causal_module, "CausalModel", None)
    monkeypatch.setattr(causal_module, "LinearDML", None)
    estimator = CausalEffectEstimator()
    treatment, outcome = _synthetic_observations()
    summary = estimator.estimate_effect(
        treatment,
        outcome,
        treatment_name="HGNC:6",
        outcome_name="HP:0000729",
        assumptions={"graph": 'digraph { "HGNC:6" -> "HP:0000729"; }'},
    )
    assert summary is not None
    assert summary.diagnostics.get("method") == "difference_in_means"
    assert summary.assumption_graph is not None
    assert len(summary.counterfactuals) >= 1
    assert summary.counterfactuals[0].label in {"observed", "p10"}
    assert "bootstrap_ci" in summary.diagnostics
    assert "Bootstrap 95% CI" in summary.description


@pytest.mark.skipif(causal_module.CausalModel is None, reason="DoWhy not installed")
def test_dowhy_enriches_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(causal_module, "LinearDML", None)
    estimator = CausalEffectEstimator()
    treatment, outcome = _synthetic_observations()
    summary = estimator.estimate_effect(
        treatment,
        outcome,
        treatment_name="HGNC:6",
        outcome_name="HP:0000729",
        assumptions={"graph": 'digraph { "HGNC:6" -> "HP:0000729"; }'},
    )
    assert summary is not None
    assert summary.diagnostics.get("method", "").startswith("dowhy")
    assert summary.assumption_graph is not None
    assert summary.counterfactuals
