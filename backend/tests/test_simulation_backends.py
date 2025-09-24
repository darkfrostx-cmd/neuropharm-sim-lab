from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from backend.simulation import circuit, molecular, pkpd
from backend.simulation.assets import (
    get_default_ospsuite_project_path,
    load_reference_connectivity,
    load_reference_pbpk_curves,
    load_reference_pathway,
)
from backend.simulation.circuit import CircuitParameters
from backend.simulation.molecular import MolecularCascadeParams
from backend.simulation.pkpd import PKPDParameters


@pytest.fixture
def cascade_params() -> MolecularCascadeParams:
    pathway = load_reference_pathway()
    return MolecularCascadeParams(
        pathway=pathway.get("pathway", "monoamine_neurotrophin_cascade"),
        receptor_states={"HTR1A": 0.6, "HTR2A": 0.4},
        receptor_weights={"HTR1A": 0.8, "HTR2A": 0.6},
        receptor_evidence={"HTR1A": 0.7, "HTR2A": 0.65},
        downstream_nodes=pathway.get("downstream_nodes", {"CREB": 0.2}),
        stimulus=1.0,
        timepoints=[0.0, 1.0, 2.0, 3.0],
    )


@pytest.fixture
def pkpd_params() -> PKPDParameters:
    return PKPDParameters(
        compound="composite_ssri",
        dose_mg=50.0,
        dosing_interval_h=24.0,
        regimen="acute",
        clearance_rate=0.2,
        bioavailability=0.6,
        brain_plasma_ratio=0.7,
        receptor_occupancy={"HTR1A": 0.5},
        kg_confidence=0.8,
        simulation_hours=48.0,
        time_step=6.0,
    )


@pytest.fixture
def circuit_params() -> CircuitParameters:
    regions, base_weights = load_reference_connectivity()
    n_regions = len(regions)
    connectivity = {
        (regions[i], regions[j]): float(base_weights[i, j])
        for i in range(n_regions)
        for j in range(n_regions)
        if i != j
    }
    return CircuitParameters(
        regions=tuple(regions),
        connectivity=connectivity,
        neuromodulator_drive={"serotonin": 0.6, "dopamine": 0.4, "noradrenaline": 0.3},
        regimen="chronic",
        timepoints=np.linspace(0.0, 10.0, 11),
        coupling_baseline=0.3,
        kg_confidence=0.75,
    )


def test_reference_assets_are_packaged() -> None:
    pathway = load_reference_pathway()
    assert pathway["pathway"] == "monoamine_neurotrophin_cascade"
    assert set(pathway["downstream_nodes"]).issuperset({"CREB", "BDNF", "mTOR"})

    project_path = Path(get_default_ospsuite_project_path())
    assert project_path.exists()

    time, plasma, brain, region_curves = load_reference_pbpk_curves()
    assert time.size > 0 and plasma.size == time.size and brain.size == time.size
    assert np.all(plasma >= 0.0)
    assert np.all(brain >= 0.0)
    assert region_curves and all(series.size == time.size for series in region_curves.values())

    regions, weights = load_reference_connectivity()
    assert regions
    assert weights.shape == (len(regions), len(regions))


def test_molecular_prefers_pysb_when_available(monkeypatch: pytest.MonkeyPatch, cascade_params: MolecularCascadeParams) -> None:
    calls: dict[str, float] = {}

    def fake_simulate_with_pysb(params: MolecularCascadeParams, receptor_effect: float, time: np.ndarray) -> dict[str, np.ndarray]:
        calls["effect"] = receptor_effect
        return {node: np.full_like(time, 0.42, dtype=float) for node in params.downstream_nodes}

    monkeypatch.setenv("MOLECULAR_SIM_BACKEND", "")
    monkeypatch.setattr(molecular, "Model", object(), raising=False)
    monkeypatch.setattr(molecular, "_simulate_with_pysb", fake_simulate_with_pysb)

    result = molecular.simulate_cascade(cascade_params)

    assert calls["effect"] > 0.0
    assert result.summary["backend"] == "pysb"
    assert all(math.isfinite(value) for value in result.summary.values() if isinstance(value, float))


def test_pkpd_prefers_ospsuite_when_available(
    monkeypatch: pytest.MonkeyPatch, pkpd_params: PKPDParameters
) -> None:
    time, plasma, brain, region_curves = load_reference_pbpk_curves()

    class _FakeSimulation:
        def __init__(self, model: object) -> None:
            self.model = model
            self.time = time
            self.plasma_concentration = plasma
            self.brain_concentration = brain
            self.region_curves = region_curves

        def set_dosing(self, **_: float) -> None:
            return None

        def set_clearance(self, _: float) -> None:
            return None

        def run(self, *, duration: float) -> None:
            self.duration = duration

    class _FakeModel:
        def __init__(self, path: str) -> None:
            self.path = path

    fake_module = SimpleNamespace(Model=_FakeModel, Simulation=_FakeSimulation)

    monkeypatch.setenv("PKPD_SIM_BACKEND", "")
    monkeypatch.delenv("PKPD_OSPSUITE_MODEL", raising=False)
    monkeypatch.setattr(pkpd, "ospsuite", fake_module, raising=False)
    monkeypatch.setattr(pkpd, "HAS_OSPSUITE", True, raising=False)

    profile = pkpd.simulate_pkpd(pkpd_params)

    assert profile.summary["backend"] == "ospsuite"
    assert profile.timepoints[-1] == pytest.approx(48.0, rel=1e-3)
    assert profile.plasma_concentration.shape == profile.brain_concentration.shape


def test_circuit_prefers_tvb_when_available(monkeypatch: pytest.MonkeyPatch, circuit_params: CircuitParameters) -> None:
    regions = circuit_params.regions
    n_regions = len(regions)

    class _FakeConnectivity:
        def __init__(self) -> None:
            self.number_of_regions = 0
            self.region_labels: np.ndarray | None = None
            self.weights: np.ndarray | None = None
            self.tract_lengths: np.ndarray | None = None

        def configure(self) -> None:  # pragma: no cover - simple stub
            return None

    class _FakeSimulator:
        def __init__(self, *, model: object, connectivity: _FakeConnectivity, coupling: object, integrator: object, monitors: tuple[object, ...]) -> None:
            self.model = model
            self.connectivity = connectivity
            self.coupling = coupling
            self.integrator = integrator
            self.monitors = monitors

        def configure(self) -> None:  # pragma: no cover - simple stub
            return None

        def run(self, *, simulation_length: float) -> list[tuple[np.ndarray, np.ndarray]]:
            tvb_time = np.linspace(0.0, simulation_length, 6)
            series = np.stack([np.linspace(0.1 * (idx + 1), 0.5 * (idx + 1), tvb_time.size) for idx in range(n_regions)])
            series = series[:, :, np.newaxis]
            return [(tvb_time, series)]

    fake_connectivity = SimpleNamespace(Connectivity=_FakeConnectivity)
    fake_coupling = SimpleNamespace(Linear=lambda **kwargs: SimpleNamespace(**kwargs))
    fake_integrators = SimpleNamespace(HeunDeterministic=lambda **kwargs: SimpleNamespace(**kwargs))
    fake_models = SimpleNamespace(Generic2dOscillator=lambda: SimpleNamespace(tau=0.0))
    fake_monitors = SimpleNamespace(TemporalAverage=lambda **kwargs: SimpleNamespace(**kwargs))
    fake_simulator = SimpleNamespace(Simulator=_FakeSimulator)

    monkeypatch.setenv("CIRCUIT_SIM_BACKEND", "")
    monkeypatch.setattr(circuit, "connectivity", fake_connectivity, raising=False)
    monkeypatch.setattr(circuit, "coupling", fake_coupling, raising=False)
    monkeypatch.setattr(circuit, "integrators", fake_integrators, raising=False)
    monkeypatch.setattr(circuit, "models", fake_models, raising=False)
    monkeypatch.setattr(circuit, "monitors", fake_monitors, raising=False)
    monkeypatch.setattr(circuit, "simulator", fake_simulator, raising=False)
    monkeypatch.setattr(circuit, "HAS_TVB", True, raising=False)

    response = circuit.simulate_circuit_response(circuit_params)

    assert response.global_metrics["backend"] == "tvb"
    assert all(region in response.region_activity for region in regions)
    assert response.timepoints.shape[0] == circuit_params.timepoints.shape[0]


def test_molecular_falls_back_to_scipy(monkeypatch: pytest.MonkeyPatch, cascade_params: MolecularCascadeParams) -> None:
    monkeypatch.delenv("MOLECULAR_SIM_BACKEND", raising=False)
    monkeypatch.setattr(molecular, "Model", None, raising=False)
    monkeypatch.setattr(molecular, "HAS_PYSB", False, raising=False)

    result = molecular.simulate_cascade(cascade_params)

    assert result.summary["backend"] == "scipy"
    assert set(result.node_activity) == set(cascade_params.downstream_nodes)
    assert all(np.all(node_activity >= 0.0) for node_activity in result.node_activity.values())


def test_pkpd_falls_back_to_scipy(monkeypatch: pytest.MonkeyPatch, pkpd_params: PKPDParameters) -> None:
    monkeypatch.delenv("PKPD_SIM_BACKEND", raising=False)
    monkeypatch.setattr(pkpd, "HAS_OSPSUITE", False, raising=False)
    monkeypatch.setattr(pkpd, "ospsuite", None, raising=False)

    profile = pkpd.simulate_pkpd(pkpd_params)

    assert profile.summary["backend"] == "scipy"
    assert profile.timepoints[0] == pytest.approx(0.0)
    assert np.all(profile.plasma_concentration >= 0.0)
    assert np.all(profile.brain_concentration >= 0.0)


def test_circuit_falls_back_to_scipy(monkeypatch: pytest.MonkeyPatch, circuit_params: CircuitParameters) -> None:
    monkeypatch.delenv("CIRCUIT_SIM_BACKEND", raising=False)
    monkeypatch.setattr(circuit, "HAS_TVB", False, raising=False)
    monkeypatch.setattr(circuit, "connectivity", None, raising=False)

    response = circuit.simulate_circuit_response(circuit_params)

    assert response.global_metrics["backend"] == "scipy"
    assert set(response.region_activity) == set(circuit_params.regions)
    assert response.timepoints.shape[0] == circuit_params.timepoints.shape[0]
