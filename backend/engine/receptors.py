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
        },
        "description": "Gi/o coupled melatonin receptor; synchronises circadian rhythms; agonism improves sleep architecture and indirectly lifts mood; antagonists unknown clinically.",
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
    compact = compact.replace("--", "-")
    if compact in RECEPTORS:
        return compact

    compact_no_dash = compact.replace("-", "")
    for canon in RECEPTORS:
        if compact_no_dash == canon.replace("-", ""):
            return canon

    return raw
