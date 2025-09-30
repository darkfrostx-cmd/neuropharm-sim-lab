import math

from backend.engine.receptors import canonical_receptor_name
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
    assert "SocialAffiliation" in result.scores
    assert result.behavioral_tags["DriveInvigoration"]["rdoc"]["id"] == "RDoC:POS_APPR"
    assert result.behavioral_tags["SocialAffiliation"]["domain"] == "Social Processes"
    assert len(result.timepoints) == len(result.trajectories["plasma_concentration"])
    assert 0.0 <= result.confidence["DriveInvigoration"] <= 1.0
    assert result.scores["ApathyBlunting"] >= 0.0
    molecular_summary = result.module_summaries["molecular"]
    pkpd_summary = result.module_summaries["pkpd"]
    assert molecular_summary["backend"] in {"analytic", "pysb", "scipy"}
    assert pkpd_summary["backend"] in {"analytic", "ospsuite", "scipy"}
    assert math.isfinite(molecular_summary["transient_peak"])
    assert math.isfinite(molecular_summary["steady_state"])
    assert math.isfinite(molecular_summary["activation_index"])
    assert pkpd_summary["auc"] >= 0.0
    assert pkpd_summary["exposure_index"] >= 0.0
    assert "region_brain_concentration" in pkpd_summary
    assert "region_exposure_scalars" in result.module_summaries


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

    canonical = canonical_receptor_name("HTR1A")
    assert (
        high_result.module_summaries["receptor_inputs"][canonical]["kg_weight"]
        > low_result.module_summaries["receptor_inputs"][canonical]["kg_weight"]
    )
    assert high_result.scores["DriveInvigoration"] >= low_result.scores["DriveInvigoration"]


def test_assumption_flags_adjust_nodes_and_behavioural_axes():
    engine = SimulationEngine(time_step=6.0)
    receptors = {
        "MOR": ReceptorEngagement(
            name="MOR",
            occupancy=0.6,
            mechanism="agonist",
            kg_weight=0.65,
            evidence=0.7,
        ),
        "A2A": ReceptorEngagement(
            name="A2A",
            occupancy=0.5,
            mechanism="antagonist",
            kg_weight=0.55,
            evidence=0.68,
        ),
    }

    baseline = engine.run(
        EngineRequest(
            receptors=receptors,
            regimen="acute",
            adhd=False,
            gut_bias=False,
            pvt_weight=0.4,
        )
    )
    enriched = engine.run(
        EngineRequest(
            receptors=receptors,
            regimen="acute",
            adhd=False,
            gut_bias=False,
            pvt_weight=0.4,
            assumptions={
                "mu_opioid_bonding": True,
                "a2a_d2_heteromer": True,
                "alpha2c_gate": True,
            },
        )
    )

    assert "cascade_oxytocin" not in baseline.trajectories
    assert "cascade_oxytocin" in enriched.trajectories
    assert "cascade_darpp32" in enriched.trajectories

    base_axes = baseline.module_summaries.get("behavioural_axes", {})
    enriched_axes = enriched.module_summaries["behavioural_axes"]
    assert enriched_axes["social_affiliation"] > base_axes.get("social_affiliation", 0.0)
    assert enriched_axes["exploration"] > base_axes.get("exploration", 0.0)
    assert enriched_axes["cognitive_flexibility"] > base_axes.get("cognitive_flexibility", 0.0)

    assumption_axes = enriched.module_summaries["assumption_axes"]
    assert assumption_axes["social_affiliation"] > 0.0
    assert enriched.module_summaries["assumptions"]["mu_opioid_bonding"] is True
