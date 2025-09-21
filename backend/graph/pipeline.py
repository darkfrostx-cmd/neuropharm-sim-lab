"""Orchestration helpers for scheduled graph ingestion runs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence

from .ingest_base import BaseIngestionJob, IngestionReport
from .ingest_runner import IngestionPlan, _default_jobs, execute_jobs
from .service import GraphService

LOGGER = logging.getLogger(__name__)

DEFAULT_STATE_PATH = Path(__file__).resolve().parent / "data" / "ingestion_state.json"

DEFAULT_COOLDOWNS: Mapping[str, float] = {
    "ChEMBL": 72.0,
    "BindingDB": 72.0,
    "IUPHAR": 48.0,
    "Indra": 24.0,
    "AllenAtlas": 168.0,
    "EBrainsAtlas": 168.0,
    "OpenAlex": 12.0,
    "__default__": 24.0,
}


@dataclass(slots=True)
class JobState:
    """Persisted summary of a job's most recent execution."""

    name: str
    last_run: datetime
    records_processed: int
    nodes_created: int
    edges_created: int

    def to_json(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "last_run": self.last_run.isoformat(),
            "records_processed": self.records_processed,
            "nodes_created": self.nodes_created,
            "edges_created": self.edges_created,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, object]) -> "JobState":
        timestamp = str(payload.get("last_run", ""))
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            parsed = datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return cls(
            name=str(payload.get("name", "unknown")),
            last_run=parsed,
            records_processed=int(payload.get("records_processed", 0)),
            nodes_created=int(payload.get("nodes_created", 0)),
            edges_created=int(payload.get("edges_created", 0)),
        )


@dataclass(slots=True)
class PipelineState:
    """Collection of job states stored between orchestrator runs."""

    jobs: MutableMapping[str, JobState] = field(default_factory=dict)

    def to_json(self) -> Dict[str, object]:
        return {
            "version": 1,
            "jobs": {name: state.to_json() for name, state in self.jobs.items()},
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, object]) -> "PipelineState":
        jobs_payload = payload.get("jobs", {})
        jobs: Dict[str, JobState] = {}
        if isinstance(jobs_payload, Mapping):
            for name, state_payload in jobs_payload.items():
                if isinstance(state_payload, Mapping):
                    jobs[str(name)] = JobState.from_json(dict(state_payload))
        return cls(jobs=jobs)


@dataclass(slots=True)
class PipelineResult:
    """Structured output returned by :class:`IngestionOrchestrator`."""

    executed: List[IngestionReport]
    skipped: List[str]


class IngestionOrchestrator:
    """Coordinate ingestion jobs with cooldown-aware scheduling."""

    def __init__(
        self,
        graph_service: GraphService,
        *,
        state_path: Path | None = None,
        cooldown_hours: Mapping[str, float] | None = None,
    ) -> None:
        self.graph_service = graph_service
        self.state_path = state_path or DEFAULT_STATE_PATH
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.cooldowns: Dict[str, float] = dict(DEFAULT_COOLDOWNS)
        if cooldown_hours:
            self.cooldowns.update({key: float(value) for key, value in cooldown_hours.items()})
        self.state = self._load_state()

    # ------------------------------------------------------------------
    # State handling
    # ------------------------------------------------------------------
    def _load_state(self) -> PipelineState:
        if not self.state_path.exists():
            return PipelineState()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive guard
            LOGGER.warning("Failed to load ingestion state at %s: %s", self.state_path, exc)
            return PipelineState()
        return PipelineState.from_json(payload)

    def _save_state(self) -> None:
        snapshot = self.state.to_json()
        try:
            self.state_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive guard
            LOGGER.warning("Failed to persist ingestion state at %s: %s", self.state_path, exc)

    # ------------------------------------------------------------------
    # Scheduling helpers
    # ------------------------------------------------------------------
    def _should_skip(self, job_name: str, now: datetime) -> bool:
        state = self.state.jobs.get(job_name)
        if state is None:
            return False
        cooldown = self.cooldowns.get(job_name, self.cooldowns.get("__default__", 24.0))
        elapsed = now - state.last_run
        return elapsed < timedelta(hours=cooldown)

    def _update_state(self, reports: Iterable[IngestionReport], timestamp: datetime) -> None:
        for report in reports:
            self.state.jobs[report.name] = JobState(
                name=report.name,
                last_run=timestamp,
                records_processed=report.records_processed,
                nodes_created=report.nodes_created,
                edges_created=report.edges_created,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(
        self,
        plan: IngestionPlan | None = None,
        *,
        limit: int | None = None,
        strict: bool = False,
        respect_cooldown: bool = True,
    ) -> PipelineResult:
        """Execute ``plan`` while honouring cooldown windows."""

        now = datetime.now(timezone.utc)
        jobs = list(plan.jobs) if plan else _default_jobs()
        if limit is None and plan and plan.limit is not None:
            limit = plan.limit

        runnable: List[BaseIngestionJob] = []
        skipped: List[str] = []
        for job in jobs:
            if respect_cooldown and self._should_skip(job.name, now):
                skipped.append(job.name)
                continue
            runnable.append(job)

        reports: List[IngestionReport] = []
        if runnable:
            reports = execute_jobs(self.graph_service, runnable, limit=limit, strict=strict)
            self._update_state(reports, now)
            self._save_state()

        return PipelineResult(executed=reports, skipped=skipped)


__all__ = [
    "DEFAULT_COOLDOWNS",
    "DEFAULT_STATE_PATH",
    "IngestionOrchestrator",
    "JobState",
    "PipelineResult",
    "PipelineState",
]

