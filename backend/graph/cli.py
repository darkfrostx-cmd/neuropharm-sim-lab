"""Command line helpers for orchestrating graph ingestion."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List

from .ingest_runner import IngestionPlan, _default_jobs
from .pipeline import IngestionOrchestrator
from .service import GraphService


def _parse_jobs(names: Iterable[str]):
    available = {job.name: job for job in _default_jobs()}
    selected_classes = []
    for name in names:
        if name not in available:
            raise SystemExit(f"Unknown ingestion job '{name}'. Available: {', '.join(sorted(available))}")
        selected_classes.append(available[name].__class__)
    return [job_cls() for job_cls in selected_classes]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Neuropharm knowledge-graph ingestion utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Run one or more ingestion jobs")
    ingest_parser.add_argument("--job", dest="jobs", action="append", help="Name of a specific job to run")
    ingest_parser.add_argument("--limit", type=int, default=None, help="Record limit for each job")
    ingest_parser.add_argument("--strict", action="store_true", help="Raise if a job fails instead of skipping")
    ingest_parser.add_argument(
        "--ignore-cooldown",
        action="store_true",
        help="Execute jobs even if they ran within their cooldown window",
    )
    ingest_parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help="Override the ingestion state file location",
    )

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ingest":
        graph_service = GraphService()
        orchestrator = IngestionOrchestrator(graph_service, state_path=args.state_file)

        if args.jobs:
            jobs = _parse_jobs(args.jobs)
        else:
            jobs = _default_jobs()
        plan = IngestionPlan(jobs=jobs)

        result = orchestrator.run(
            plan,
            limit=args.limit,
            strict=args.strict,
            respect_cooldown=not args.ignore_cooldown,
        )

        for report in result.executed:
            print(
                f"{report.name}: records={report.records_processed} nodes={report.nodes_created} "
                f"edges={report.edges_created}",
                file=sys.stdout,
            )
        if result.skipped:
            print("Skipped jobs due to cooldown:", ", ".join(sorted(result.skipped)))
        return 0

    parser.error("Unknown command")
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())

