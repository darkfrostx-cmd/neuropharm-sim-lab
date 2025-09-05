"""
neuropharm‑sim‑lab.backend.engine
=================================

This package contains the core computational primitives for the simulation
backend used by the neuropharm simulation lab.  The goal of this module
is to centralise definitions of receptor subtypes, their pharmacological
weights, and provide simple helpers to aggregate their effects on high
level behavioural and physiological metrics.  By separating this logic
out into its own package we make it trivial to extend or override the
behaviour of individual receptors without modifying the FastAPI entry
point.  Additional neurotransmitter systems can be added by creating
new modules alongside ``receptors.py`` and registering them in the
``simulate`` implementation.

Every receptor subtype defined in :mod:`receptors` carries a small
dictionary of weights describing how activation or blockade of that
receptor influences a handful of phenomenological metrics such as
``drive``, ``apathy``, ``motivation`` and ``cognitive_flexibility``.
Weights are dimensionless numbers; they are scaled and combined with
occupancy (0–1) and mechanism sign (+1 for agonism, −1 for antagonism,
−1.3 for inverse agonism, +0.5 for partial agonism) in the main
simulation routine to compute final scores.  See
``receptors.MECHANISM_EFFECTS`` for the mapping of mechanism names to
numeric factors.
"""

from .receptors import RECEPTORS, MECHANISM_EFFECTS  # noqa: F401

__all__ = ["RECEPTORS", "MECHANISM_EFFECTS"]
