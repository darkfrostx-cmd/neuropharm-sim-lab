"""Regression tests for the multiscale simulation pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.main import app
from backend.simulation import ReceptorInput, SimulationConfig, run_multiscale_pipeline


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_chronic_ssri_regression() -> None:
    """Chronic SSRI scenario should remain numerically stable over time."""

    config = SimulationConfig(
        receptors={
            "5-HT1A": ReceptorInput(occupancy=0.7, mechanism="agonist"),
            "5-HT1B": ReceptorInput(occupancy=0.4, mechanism="partial"),
            "5-HT2C": ReceptorInput(occupancy=0.3, mechanism="antagonist"),
            "5-HT7": ReceptorInput(occupancy=0.5, mechanism="agonist"),
        },
        exposure="chronic",
        adhd=False,
        gut_bias=False,
        pvt_weight=0.4,
        propagate_uncertainty=True,
    )

    result = run_multiscale_pipeline(config)

    expected_scores = {
        "DriveInvigoration": 52.348964366858326,
        "ApathyBlunting": 50.68958768827599,
        "Motivation": 52.30007586034499,
        "CognitiveFlexibility": 52.10645724022999,
        "Anxiety": 50.45335109588086,
        "SleepQuality": 53.4930238115713,
    }
    for key, expected in expected_scores.items():
        assert result.behavioural_scores[key] == pytest.approx(expected)

    combined_uncertainty = {
        "DriveInvigoration": 0.06327113762376532,
        "ApathyBlunting": 0.054974254230853635,
        "Motivation": 0.06302669509119863,
        "CognitiveFlexibility": 0.062058601990623644,
        "Anxiety": 0.053793071268878015,
        "SleepQuality": 0.058991434847330174,
    }
    for key, expected in combined_uncertainty.items():
        assert result.uncertainty_breakdown["combined"][key] == pytest.approx(expected)


def test_simulate_endpoint_uncertainty_toggle(client: TestClient) -> None:
    """Endpoint exposes time series and responds to uncertainty toggles."""

    payload = {
        "receptors": {"5-HT1A": {"occ": 0.6, "mech": "agonist"}},
        "adhd": True,
        "gut_bias": False,
        "pvt_weight": 0.5,
        "exposure": "acute",
        "propagate_uncertainty": False,
    }

    response = client.post("/simulate", json=payload)
    assert response.status_code == 200
    body = response.json()

    scores = body["scores"]
    assert set(scores) == {
        "DriveInvigoration",
        "ApathyBlunting",
        "Motivation",
        "CognitiveFlexibility",
        "Anxiety",
        "SleepQuality",
    }

    details = body["details"]
    assert details["assumptions"]["exposure"] == "acute"
    assert details["assumptions"]["propagate_uncertainty"] is False
    assert len(details["time"]) > 10
    assert details["uncertainty"]["molecular"]["global"] == pytest.approx(0.01)

    combined = details["uncertainty"]["combined"]["DriveInvigoration"]
    assert combined < 0.05  # toggle suppresses uncertainty propagation
