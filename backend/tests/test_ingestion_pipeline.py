from __future__ import annotations

from pathlib import Path

from backend.graph.ingest_base import BaseIngestionJob
from backend.graph.ingest_runner import IngestionPlan
from backend.graph.models import BiolinkEntity, BiolinkPredicate, Edge, Node
from backend.graph.pipeline import IngestionOrchestrator
from backend.graph.service import GraphService


class DummyJob(BaseIngestionJob):
    name = "Dummy"

    def fetch(self, limit: int | None = None):  # type: ignore[override]
        count = 2 if limit is None else min(limit, 2)
        for idx in range(count):
            yield {"idx": idx}

    def transform(self, record: dict):  # type: ignore[override]
        identifier = f"CHEMBL:{record['idx']}"
        node = Node(id=identifier, name=f"Compound {record['idx']}", category=BiolinkEntity.CHEMICAL_SUBSTANCE)
        edge = Edge(
            subject=identifier,
            predicate=BiolinkPredicate.RELATED_TO,
            object="HGNC:TEST",
            confidence=0.5,
        )
        return [node], [edge]


def test_orchestrator_respects_cooldown(tmp_path: Path) -> None:
    service = GraphService()
    orchestrator = IngestionOrchestrator(
        service,
        state_path=tmp_path / "state.json",
        cooldown_hours={"Dummy": 48.0},
    )
    plan = IngestionPlan(jobs=[DummyJob()])

    first_run = orchestrator.run(plan)
    assert first_run.executed and first_run.executed[0].records_processed == 2
    assert (tmp_path / "state.json").exists()

    second_run = orchestrator.run(plan)
    assert not second_run.executed
    assert second_run.skipped == ["Dummy"]

    forced_run = orchestrator.run(plan, respect_cooldown=False)
    assert forced_run.executed
