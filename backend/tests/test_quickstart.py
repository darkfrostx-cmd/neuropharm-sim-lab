from __future__ import annotations

import pytest

from backend import quickstart


def test_run_quickstart_returns_payload():
    payload = quickstart.run_quickstart({"5HT1A": {"occ": 0.6, "mech": "agonist"}})
    assert "scores" in payload and payload["scores"], "Simulation should return scores"
    assert "receptor_context" in payload
    assert "5-HT1A" in payload["receptor_context"]
    summary = quickstart.summarise_quickstart(payload, top_n=3)
    assert "Top predicted effects" in summary
    assert "Receptor inputs" in summary


def test_run_quickstart_invalid_regimen():
    with pytest.raises(quickstart.QuickstartError):
        quickstart.run_quickstart({"5HT1A": {"occ": 0.4, "mech": "agonist"}}, regimen="weekly")


def test_available_presets_lists_expected_options():
    presets = quickstart.available_presets()
    assert "starter" in presets
    assert presets["starter"].receptors
