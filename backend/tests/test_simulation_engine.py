from backend.simulation import (
    EngineRequest,
    ReceptorEngagement,
    SimulationEngine,
)


def test_engine_chronic_ssri_profile():
    engine = SimulationEngine(time_step=6.0)
    request = EngineRequest(
        receptors={
            "HTR1A": ReceptorEngagement(
                name="HTR1A",
                occupancy=0.7,
                mechanism="agonist",
                kg_weight=0.8,
                evidence=0.75,
            ),
            "HTR2A": ReceptorEngagement(
                name="HTR2A",
                occupancy=0.4,
                mechanism="antagonist",
                kg_weight=0.6,
                evidence=0.7,
            ),
        },
        regimen="chronic",
        adhd=False,
        gut_bias=True,
        pvt_weight=0.2,
    )

    result = engine.run(request)

    assert result.timepoints[-1] >= 168.0
    assert "DriveInvigoration" in result.scores
    assert len(result.timepoints) == len(result.trajectories["plasma_concentration"])
    assert 0.0 <= result.confidence["DriveInvigoration"] <= 1.0
    assert result.scores["ApathyBlunting"] >= 0.0


def test_affinity_expression_scaling_modulates_weights():
    engine = SimulationEngine(time_step=6.0)

    low_request = EngineRequest(
        receptors={
            "HTR1A": ReceptorEngagement(
                name="HTR1A",
                occupancy=0.6,
                mechanism="agonist",
                kg_weight=0.5,
                evidence=0.6,
                affinity=0.2,
                expression=0.2,
            )
        },
        regimen="acute",
        adhd=False,
        gut_bias=False,
        pvt_weight=0.5,
    )
    high_request = EngineRequest(
        receptors={
            "HTR1A": ReceptorEngagement(
                name="HTR1A",
                occupancy=0.6,
                mechanism="agonist",
                kg_weight=0.5,
                evidence=0.6,
                affinity=0.95,
                expression=0.9,
            )
        },
        regimen="acute",
        adhd=False,
        gut_bias=False,
        pvt_weight=0.5,
    )

    low_result = engine.run(low_request)
    high_result = engine.run(high_request)

    assert (
        high_result.module_summaries["receptor_inputs"]["HTR1A"]["kg_weight"]
        > low_result.module_summaries["receptor_inputs"]["HTR1A"]["kg_weight"]
    )
    assert high_result.scores["DriveInvigoration"] >= low_result.scores["DriveInvigoration"]
