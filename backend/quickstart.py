"""Command-line helper for exploring the Neuropharm simulation locally."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence

from .engine.receptors import canonical_receptor_name
from .graph.ingest_runner import load_seed_graph
from .graph.service import GraphService
from .simulation import (
    EngineRequest,
    GraphBackedReceptorAdapter,
    ReceptorEngagement,
    SimulationEngine,
)


@dataclass(frozen=True)
class Preset:
    """Describe a ready-made receptor mix for the quickstart CLI."""

    receptors: Mapping[str, Mapping[str, object]]
    description: str


_PRESETS: Dict[str, Preset] = {
    "starter": Preset(
        receptors={
            "5HT1A": {"occ": 0.6, "mech": "agonist"},
            "5HT2A": {"occ": 0.25, "mech": "antagonist"},
        },
        description="Balanced SSRI-style mix that emphasises anxiety relief and cognitive flexibility.",
    ),
    "sleep_support": Preset(
        receptors={
            "5HT2C": {"occ": 0.35, "mech": "antagonist"},
            "MT2": {"occ": 0.5, "mech": "agonist"},
        },
        description="Focuses on sleep consolidation by blending 5-HT2C antagonism with melatonin agonism.",
    ),
    "pro_social": Preset(
        receptors={
            "5HT1A": {"occ": 0.5, "mech": "agonist"},
            "MOR": {"occ": 0.35, "mech": "agonist"},
        },
        description="Boosts affiliation/attachment signalling with serotonin 1A and μ-opioid engagement.",
    ),
}

_VALID_MECHANISMS: set[str] = {"agonist", "antagonist", "partial", "inverse"}
_REF_PATH = Path(__file__).with_name("refs.json")


class QuickstartError(Exception):
    """Raised when the quickstart helper receives invalid input."""


def available_presets() -> Mapping[str, Preset]:
    """Return the preset configurations shipped with the CLI."""

    return dict(_PRESETS)


def _load_receptor_references() -> Dict[str, Sequence[Mapping[str, str]]]:
    if not _REF_PATH.exists():
        return {}
    try:
        payload = json.loads(_REF_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, list)}


def _normalise_receptors(receptors: Mapping[str, Mapping[str, object]]) -> Dict[str, Mapping[str, object]]:
    normalised: Dict[str, Mapping[str, object]] = {}
    for raw_name, raw_spec in receptors.items():
        if "occ" not in raw_spec or "mech" not in raw_spec:
            raise QuickstartError(f"Receptor '{raw_name}' must include 'occ' and 'mech' fields")
        try:
            occ = float(raw_spec["occ"])  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise QuickstartError(f"Receptor '{raw_name}' has an invalid occupancy value: {raw_spec['occ']!r}") from exc
        if not 0.0 <= occ <= 1.0:
            raise QuickstartError(f"Receptor '{raw_name}' occupancy must be between 0 and 1 (inclusive)")
        mech_raw = str(raw_spec["mech"]).strip().lower()
        if mech_raw not in _VALID_MECHANISMS:
            raise QuickstartError(
                f"Receptor '{raw_name}' mechanism must be one of {sorted(_VALID_MECHANISMS)} (received {raw_spec['mech']!r})"
            )
        canon = canonical_receptor_name(raw_name)
        normalised[canon] = {"occ": occ, "mech": mech_raw}
    return normalised


def _parse_receptor_override(values: Iterable[str]) -> Dict[str, Mapping[str, object]]:
    overrides: Dict[str, Mapping[str, object]] = {}
    for value in values:
        try:
            name_part, payload_part = value.split("=", 1)
            occ_part, mech_part = payload_part.split(":", 1)
        except ValueError as exc:
            raise QuickstartError(
                "Overrides must use the format NAME=OCC:MECH (for example 5HT1A=0.6:agonist)"
            ) from exc
        overrides[name_part.strip()] = {"occ": occ_part.strip(), "mech": mech_part.strip()}
    return overrides


def run_quickstart(
    receptors: Mapping[str, Mapping[str, object]] | None = None,
    *,
    regimen: str = "chronic",
    adhd: bool = False,
    gut_bias: bool = False,
    pvt_weight: float = 0.35,
    time_step: float = 1.0,
) -> Dict[str, object]:
    """Execute a simulation locally and return a structured summary."""

    if regimen not in {"acute", "chronic"}:
        raise QuickstartError("Regimen must be either 'acute' or 'chronic'")
    if not 0.0 <= float(pvt_weight) <= 1.0:
        raise QuickstartError("PVT weight must fall between 0 and 1")

    preset = _PRESETS["starter"] if receptors is None else Preset(receptors=receptors, description="custom")
    normalised = _normalise_receptors(preset.receptors)
    if not normalised:
        raise QuickstartError("At least one receptor must be supplied")

    references = _load_receptor_references()

    graph_service = GraphService()
    if not load_seed_graph(graph_service):
        raise QuickstartError("Seed graph could not be loaded; reinstall the repository data files")
    adapter = GraphBackedReceptorAdapter(graph_service)
    engine = SimulationEngine(time_step=time_step)

    engagements: Dict[str, ReceptorEngagement] = {}
    receptor_context: Dict[str, Dict[str, object]] = {}

    for canon, spec in normalised.items():
        bundle = adapter.derive(canon)
        engagement = ReceptorEngagement(
            name=canon,
            occupancy=float(spec["occ"]),
            mechanism=spec["mech"],  # type: ignore[arg-type]
            kg_weight=bundle.kg_weight,
            evidence=bundle.evidence_score,
            affinity=bundle.affinity,
            expression=bundle.expression,
            evidence_sources=bundle.evidence_sources,
        )
        engagements[canon] = engagement
        evidence_score = bundle.evidence_score if bundle.evidence_score is not None else 0.4
        receptor_context[canon] = {
            "kg_weight": bundle.kg_weight,
            "evidence": bundle.evidence_score,
            "affinity": bundle.affinity,
            "expression": bundle.expression,
            "uncertainty": float(max(0.0, min(1.0, 1.0 - evidence_score))),
            "evidence_items": bundle.evidence_count,
            "sources": list(bundle.evidence_sources),
            "citations": list(references.get(canon, [])),
        }

    request = EngineRequest(
        receptors=engagements,
        regimen=regimen,  # type: ignore[arg-type]
        adhd=adhd,
        gut_bias=gut_bias,
        pvt_weight=float(pvt_weight),
        assumptions={},
    )
    result = engine.run(request)

    return {
        "scores": dict(result.scores),
        "confidence": dict(result.confidence),
        "behavioral_tags": {metric: dict(annotation) for metric, annotation in result.behavioral_tags.items()},
        "timepoints": list(result.timepoints),
        "trajectories": {name: list(values) for name, values in result.trajectories.items()},
        "receptor_context": receptor_context,
        "engine": {
            "backends": dict(result.executed_backends),
            "fallbacks": {name: list(events) for name, events in result.fallbacks.items()},
        },
    }


def summarise_quickstart(payload: Mapping[str, object], *, top_n: int = 5) -> str:
    """Create a human-readable summary of a quickstart simulation."""

    scores = payload.get("scores", {})
    confidence = payload.get("confidence", {})
    tags = payload.get("behavioral_tags", {})
    receptor_context = payload.get("receptor_context", {})
    engine = payload.get("engine", {})

    def _format_score(metric: str, score: float) -> str:
        conf = confidence.get(metric, 0.0)
        tag = tags.get(metric, {})
        label = tag.get("label", metric)
        domain = tag.get("domain")
        bits = [f"{label}: {score:.2f} (confidence {conf:.2f})"]
        if domain:
            bits.append(f"Domain: {domain}")
        return " - ".join(bits)

    lines = ["Top predicted effects:"]
    if isinstance(scores, Mapping):
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        for metric, score in ordered[: max(1, top_n)]:
            lines.append(f"  • {_format_score(metric, float(score))}")
    else:
        lines.append("  • No score data available")

    if isinstance(receptor_context, Mapping):
        lines.append("\nReceptor inputs:")
        for name, context in receptor_context.items():
            kg_weight = context.get("kg_weight")
            evidence = context.get("evidence")
            uncertainty = context.get("uncertainty")
            summary = f"  • {name}: weight {kg_weight:.2f}" if isinstance(kg_weight, (int, float)) else f"  • {name}:"
            if isinstance(evidence, (int, float)):
                summary += f", evidence {evidence:.2f}"
            if isinstance(uncertainty, (int, float)):
                summary += f", uncertainty {uncertainty:.2f}"
            lines.append(summary)
            sources = context.get("sources", [])
            if sources:
                formatted_sources = ", ".join(str(item) for item in sources[:3])
                if len(sources) > 3:
                    formatted_sources += "…"
                lines.append(f"     Sources: {formatted_sources}")
            citations = context.get("citations", [])
            if citations:
                citation = citations[0]
                title = citation.get("title") if isinstance(citation, Mapping) else None
                if title:
                    lines.append(f"     Key study: {title}")
    if isinstance(engine, Mapping):
        backends = engine.get("backends", {})
        if isinstance(backends, Mapping) and backends:
            backend_list = ", ".join(f"{module}: {name}" for module, name in backends.items())
            lines.append(f"\nSimulation backends: {backend_list}")
        fallbacks = engine.get("fallbacks", {})
        if isinstance(fallbacks, Mapping) and any(fallbacks.values()):
            details = []
            for module, events in fallbacks.items():
                if events:
                    details.append(f"{module}→{'/'.join(str(ev) for ev in events)}")
            if details:
                lines.append("Fallbacks triggered: " + ", ".join(details))

    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Neuropharm simulation with friendly defaults.")
    parser.add_argument("--preset", choices=sorted(_PRESETS), default="starter", help="Which receptor mix to use as a baseline")
    parser.add_argument(
        "--receptor",
        action="append",
        default=[],
        metavar="NAME=OCC:MECH",
        help="Override or add a receptor specification (repeatable)",
    )
    parser.add_argument("--regimen", choices=["acute", "chronic"], default="chronic", help="Duration model to simulate")
    parser.add_argument("--adhd", action="store_true", help="Flag ADHD comorbidity for the PK/PD heuristics")
    parser.add_argument("--gut-bias", action="store_true", help="Bias metabolism toward gut first-pass extraction")
    parser.add_argument("--pvt-weight", type=float, default=0.35, help="Relative weight for psychomotor vigilance (0-1)")
    parser.add_argument("--time-step", type=float, default=1.0, help="Simulation time step in hours")
    parser.add_argument("--top", type=int, default=5, help="How many metrics to display in the text summary")
    parser.add_argument("--json", action="store_true", help="Print the raw JSON payload instead of a summary")
    parser.add_argument("--list-presets", action="store_true", help="List built-in presets and exit")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_presets:
        lines = ["Available presets:"]
        for name in sorted(_PRESETS):
            lines.append(f"  • {name}: {_PRESETS[name].description}")
        print("\n".join(lines))
        return 0

    preset = _PRESETS[args.preset]
    overrides = _parse_receptor_override(args.receptor)
    combined = dict(preset.receptors)
    combined.update(overrides)

    try:
        payload = run_quickstart(
            combined,
            regimen=args.regimen,
            adhd=args.adhd,
            gut_bias=args.gut_bias,
            pvt_weight=args.pvt_weight,
            time_step=args.time_step,
        )
    except QuickstartError as exc:
        parser.error(str(exc))
        return 2

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=float))
    else:
        print(summarise_quickstart(payload, top_n=args.top))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
