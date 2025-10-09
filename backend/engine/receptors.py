"""
receptors
=========

This module declares the serotonin receptor subtypes and related
neuromodulator targets used by the simulation engine.  Each entry in
``RECEPTORS`` is a mapping from a receptor name to a description of
how activation or blockade of that receptor influences a set of high
level behavioural or physiological metrics.  The intent of this file
is not to capture every nuance of receptor pharmacology but to
provide a realistic but tractable model that can be tuned and
extended.

Alongside canonical receptors we also expose a few "composite" nodes
that correspond to optional model assumptions (e.g. μ-opioid bonding
microcircuits or A2A–D2 heteromer facilitation).  These entries allow
the simulation engine – and the ingestion pipeline that surfaces
supporting evidence – to reason about the behavioural footprint of the
assumption toggles without special-casing them elsewhere in the code
base.

The high level metrics considered by the simulation are:

``drive``
    Motivation and invigoration.  High values correspond to high
    energy, willingness to initiate actions and explore.

``apathy``
    Emotional blunting or lack of drive.  High values correspond to
    reduced interest, negative symptoms and amotivation.

``motivation``
    The positive counterpart of apathy.  It partially overlaps with
    ``drive`` but emphasises goal‑directed behaviour and reward
    seeking.

``cognitive_flexibility``
    The ability to shift strategies, update beliefs and avoid
    perseveration.  High values correspond to agile thinking.

``anxiety``
    A measure of arousal in the negative sense; heightened startle
    response, worry and fear.  SSRIs are often prescribed to reduce
    anxiety, whereas excessive serotonergic tone can sometimes
    increase it.

``sleep_quality``
    A crude proxy for circadian alignment and restorative sleep.  High
    values mean good sleep with robust rhythms, low values represent
    insomnia or disrupted sleep architecture.

``social_affiliation``
    Prosocial bonding, attachment and affiliative motivation.  Positive
    values promote social approach, negative values bias towards
    withdrawal.

``exploration``
    Tendency to explore novel stimuli and environments.  Positive values
    favour exploration whereas negative values foster behavioural
    inhibition.

``salience``
    Salience tagging for emotionally relevant cues.  Higher values mean
    stronger cue-reactivity and attentional capture.

Each receptor entry contains a ``weights`` dictionary mapping these
metrics to per‑unit activation weights.  Positive weights increase
the associated metric, negative weights decrease it.  The magnitude
of the weight reflects the importance of the receptor on that
dimension; all weights are heuristically chosen to provide plausible
outcomes but can be tuned based on future research findings.  The
weights are multiplied by 20 in the simulation (see ``backend.main``)
to produce changes relative to a baseline of 50.

``MECHANISM_EFFECTS`` defines how different pharmacological mechanisms
map to numeric factors: agonists increase receptor activity (1.0),
antagonists block it (–1.0), inverse agonists not only block but
actively reduce basal signalling (–1.3), and partial agonists supply
half activation (0.5).
"""

from __future__ import annotations

from typing import Dict, Mapping

RECEPTORS: Mapping[str, Dict[str, object]] = {
    "5-HT2C": {
        "weights": {
            "drive": -0.4,
            "apathy": 0.5,
            "motivation": -0.3,
            "cognitive_flexibility": -0.2,
            "anxiety": 0.4,
            "sleep_quality": -0.1,
            "social_affiliation": -0.25,
            "exploration": -0.4,
            "salience": 0.18,
        },
        "description": "Gq‑coupled receptor; activation reduces DA burst via VTA GABA INs and raises effort cost; chronic activation increases apathy and blunts reward.",
    },
    "5-HT1B": {
        "weights": {
            "drive": -0.3,
            "apathy": 0.2,
            "motivation": -0.1,
            "cognitive_flexibility": 0.0,
            "anxiety": 0.1,
            "sleep_quality": 0.0,
            "social_affiliation": -0.05,
            "exploration": -0.2,
            "salience": 0.15,
        },
        "description": "Gi/o heteroreceptor; presynaptic filter for glutamate and GABA inputs; can dampen phasic drive but sometimes disinhibit DA via VTA GABA terminals depending on circuit.",
    },
    "5-HT2A": {
        "weights": {
            "drive": 0.1,
            "apathy": -0.1,
            "motivation": 0.2,
            "cognitive_flexibility": 0.4,
            "anxiety": 0.3,
            "sleep_quality": -0.2,
            "social_affiliation": 0.05,
            "exploration": 0.3,
            "salience": 0.35,
        },
        "description": "Gq‑coupled cortical receptor; acute activation enhances glutamatergic output and plasticity; chronic over‑activation may cause anxiety or agitation.",
    },
    "5-HT3": {
        "weights": {
            "drive": -0.1,
            "apathy": 0.2,
            "motivation": -0.1,
            "cognitive_flexibility": -0.2,
            "anxiety": 0.2,
            "sleep_quality": -0.3,
            "social_affiliation": -0.15,
            "exploration": -0.25,
            "salience": 0.22,
        },
        "description": "Ionotropic cation channel; located on interneurons; activation produces fast inhibitory postsynaptic currents; linked to nausea and cognitive fog.",
    },
    "5-HT7": {
        "weights": {
            "drive": 0.2,
            "apathy": -0.2,
            "motivation": 0.3,
            "cognitive_flexibility": 0.3,
            "anxiety": 0.1,
            "sleep_quality": 0.3,
            "social_affiliation": 0.15,
            "exploration": 0.25,
            "salience": 0.1,
        },
        "description": "Gs‑coupled receptor enriched in thalamus, hippocampus and PFC; regulates circadian phase, dendritic growth and pattern separation; antagonists display antidepressant effects in rodents.",
    },
    "5-HT1A": {
        "weights": {
            "drive": 0.2,
            "apathy": -0.2,
            "motivation": 0.1,
            "cognitive_flexibility": 0.1,
            "anxiety": -0.4,
            "sleep_quality": 0.2,
            "social_affiliation": 0.25,
            "exploration": 0.18,
            "salience": -0.12,
        },
        "description": "Gi/o coupled receptor; expressed somatodendritically on raphe (autoreceptor) and postsynaptically in cortex and hippocampus; agonism reduces anxiety and releases cortical inhibition.",
    },
    "MT2": {
        "weights": {
            "drive": 0.1,
            "apathy": -0.2,
            "motivation": 0.1,
            "cognitive_flexibility": 0.1,
            "anxiety": -0.1,
            "sleep_quality": 0.4,
            "social_affiliation": 0.05,
            "exploration": 0.05,
            "salience": -0.05,
        },
        "description": "Gi/o coupled melatonin receptor; synchronises circadian rhythms; agonism improves sleep architecture and indirectly lifts mood; antagonists unknown clinically.",
    },
    "MOR": {
        "weights": {
            "drive": 0.35,
            "apathy": -0.45,
            "motivation": 0.4,
            "cognitive_flexibility": 0.1,
            "anxiety": -0.3,
            "sleep_quality": 0.15,
            "social_affiliation": 0.6,
            "exploration": 0.2,
            "salience": -0.05,
        },
        "description": "μ-opioid receptor; hedonic hotspot engagement promotes social bonding, warmth and motivation; antagonism blunts attachment and reward sensitivity.",
    },
    "MOR-BONDING": {
        "weights": {
            "drive": 0.25,
            "apathy": -0.4,
            "motivation": 0.3,
            "cognitive_flexibility": 0.08,
            "anxiety": -0.32,
            "sleep_quality": 0.12,
            "social_affiliation": 0.75,
            "exploration": 0.22,
            "salience": -0.08,
        },
        "description": "Composite node capturing μ-opioid driven social bonding (periaqueductal grey and nucleus accumbens hedonic hotspots) with downstream oxytocin/enkephalin release.",
    },
    "A2A": {
        "weights": {
            "drive": -0.2,
            "apathy": 0.3,
            "motivation": -0.25,
            "cognitive_flexibility": 0.1,
            "anxiety": 0.05,
            "sleep_quality": -0.05,
            "social_affiliation": -0.1,
            "exploration": -0.2,
            "salience": 0.15,
        },
        "description": "Striatal adenosine A2A receptor; dampens D2 signalling and raises effort cost; antagonism (e.g. caffeine) can restore drive in striatal circuits.",
    },
    "A2A-D2": {
        "weights": {
            "drive": 0.25,
            "apathy": -0.25,
            "motivation": 0.3,
            "cognitive_flexibility": 0.15,
            "anxiety": -0.1,
            "sleep_quality": 0.05,
            "social_affiliation": 0.2,
            "exploration": 0.35,
            "salience": 0.28,
        },
        "description": "A2A–D2 heteromer integrating adenosine and dopamine tone; stabilises motivational gating and shapes goal-directed exploration in ventral striatum.",
    },
    "A2A-D2-HETEROMER": {
        "weights": {
            "drive": 0.28,
            "apathy": -0.28,
            "motivation": 0.34,
            "cognitive_flexibility": 0.2,
            "anxiety": -0.12,
            "sleep_quality": 0.08,
            "social_affiliation": 0.18,
            "exploration": 0.42,
            "salience": 0.34,
        },
        "description": "Composite ventral striatal A2A–D2 heteromer node used when enabling the heteromer facilitation assumption; emphasises exploration bias and salience weighting via DARPP-32 and cAMP cascades.",
    },
    "ACh-BLA": {
        "weights": {
            "drive": 0.1,
            "apathy": -0.1,
            "motivation": 0.2,
            "cognitive_flexibility": 0.15,
            "anxiety": 0.18,
            "sleep_quality": -0.05,
            "social_affiliation": 0.12,
            "exploration": 0.05,
            "salience": 0.45,
        },
        "description": "Basolateral amygdala cholinergic burst; heightens cue salience and social relevance learning during emotionally charged events.",
    },
    "OXTR": {
        "weights": {
            "drive": 0.05,
            "apathy": -0.1,
            "motivation": 0.15,
            "cognitive_flexibility": 0.05,
            "anxiety": -0.25,
            "sleep_quality": 0.05,
            "social_affiliation": 0.55,
            "exploration": 0.1,
            "salience": 0.12,
        },
        "description": "Oxytocin receptor; facilitates social bonding, trust and affiliation particularly in limbic-prefrontal loops.",
    },
    "AVPR1A": {
        "weights": {
            "drive": 0.08,
            "apathy": -0.06,
            "motivation": 0.1,
            "cognitive_flexibility": -0.05,
            "anxiety": 0.32,
            "sleep_quality": -0.05,
            "social_affiliation": 0.18,
            "exploration": -0.12,
            "salience": 0.28,
        },
        "description": "Arginine vasopressin 1A receptor; heightens threat surveillance and territorial vigilance while coupling to social dominance circuits.",
    },
    "TRKB": {
        "weights": {
            "drive": 0.3,
            "apathy": -0.35,
            "motivation": 0.35,
            "cognitive_flexibility": 0.25,
            "anxiety": -0.2,
            "sleep_quality": 0.15,
            "social_affiliation": 0.32,
            "exploration": 0.22,
            "salience": 0.18,
        },
        "description": "TrkB (NTRK2) neurotrophin receptor; activation supports BDNF-dependent plasticity, AMPA potentiation and rapid antidepressant responses.",
    },
    "ADRA2A": {
        "weights": {
            "drive": 0.05,
            "apathy": -0.22,
            "motivation": 0.18,
            "cognitive_flexibility": 0.35,
            "anxiety": -0.18,
            "sleep_quality": 0.1,
            "social_affiliation": 0.12,
            "exploration": -0.28,
            "salience": -0.08,
        },
        "description": "α2A-adrenergic receptor; engages PFC HCN channel closure to stabilise working memory and top-down control while tempering exploratory drive.",
    },
    "ADRA2C": {
        "weights": {
            "drive": 0.08,
            "apathy": -0.18,
            "motivation": 0.16,
            "cognitive_flexibility": 0.28,
            "anxiety": -0.22,
            "sleep_quality": 0.12,
            "social_affiliation": 0.1,
            "exploration": -0.22,
            "salience": -0.05,
        },
        "description": "α2C-adrenergic receptor; cortico-striatal gate dampening excessive norepinephrine tone while tightening thalamo-cortical gain control during stress states.",
    },
    # You can extend this dictionary with additional receptors or neuromodulators.
}

MECHANISM_EFFECTS: Mapping[str, float] = {
    # positive activation
    "agonist": 1.0,
    # blockade
    "antagonist": -1.0,
    # partial agonist (buspirone or vilazodone like)
    "partial": 0.5,
    # inverse agonist (reduces constitutive signalling below baseline)
    "inverse": -1.3,
}

def get_receptor_weights(name: str) -> Dict[str, float]:
    """Return the weights dictionary for a receptor.

    Parameters
    ----------
    name:
        The canonical receptor name (e.g. ``"5-HT2C"``).  Raises
        ``KeyError`` if not found.

    Returns
    -------
    dict
        A mapping from metric names to per‑unit weights.
    """
    return RECEPTORS[name]["weights"]


def get_mechanism_factor(mech: str) -> float:
    """Return the numeric factor associated with a pharmacological mechanism.

    Parameters
    ----------
    mech:
        One of ``"agonist"``, ``"antagonist"``, ``"partial"`` or ``"inverse"``.

    Returns
    -------
    float
        The multiplier applied to weights to reflect mechanism direction.

    Raises
    ------
    ValueError
        If ``mech`` is not one of the supported mechanisms.
    """

    try:
        return MECHANISM_EFFECTS[mech]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Unsupported mechanism '{mech}'") from exc


def canonical_receptor_name(name: str) -> str:
    """Return the canonical receptor identifier used by the engine."""

    raw = name.strip().upper()
    if raw in RECEPTORS:
        return raw

    compact = raw.replace(" ", "").replace("_", "")
    if compact in RECEPTORS:
        return compact

    if compact.startswith("5HT"):
        compact = "5-HT" + compact[3:]
    elif compact.startswith("HTR"):
        candidate = "5-HT" + compact[3:]
        if candidate in RECEPTORS:
            return candidate
    compact = compact.replace("--", "-")
    if compact in RECEPTORS:
        return compact

    compact_no_dash = compact.replace("-", "")
    alias_map = {
        "NTRK2": "TRKB",
        "TRKB": "TRKB",
        "BDNFR": "TRKB",
        "ADRA2A": "ADRA2A",
        "ALPHA2A": "ADRA2A",
        "ADRENALPHA2A": "ADRA2A",
        "MUOPIOIDBONDING": "MOR-BONDING",
        "MORBONDED": "MOR-BONDING",
        "MORBONING": "MOR-BONDING",
        "A2AD2HETEROMER": "A2A-D2-HETEROMER",
        "ADRA2C": "ADRA2C",
        "ALPHA2C": "ADRA2C",
        "ALPHA2CGATE": "ADRA2C",
    }
    if compact_no_dash in alias_map:
        target = alias_map[compact_no_dash]
        if target in RECEPTORS:
            return target
    for canon in RECEPTORS:
        if compact_no_dash == canon.replace("-", ""):
            return canon

    return raw
