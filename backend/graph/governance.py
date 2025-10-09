"""Data governance registry for operational guardrails."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping


def _utcnow() -> datetime:
    now = datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


@dataclass(slots=True)
class GovernanceCheck:
    name: str
    passed: bool
    note: str | None = None


@dataclass(slots=True)
class DataSourceRecord:
    name: str
    category: str
    pii: bool = False
    retention: str = "standard"
    access_tier: str = "open"
    last_audited: datetime = field(default_factory=_utcnow)
    checks: List[GovernanceCheck] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)

    def record_check(self, name: str, passed: bool, note: str | None = None) -> None:
        self.checks.append(GovernanceCheck(name=name, passed=passed, note=note))
        if not passed and note:
            self.issues.append(note)
        self.last_audited = _utcnow()


class DataGovernanceRegistry:
    """Central registry tracking governance checks for datasources."""

    def __init__(self) -> None:
        self._records: Dict[str, DataSourceRecord] = {}

    def register(
        self,
        name: str,
        *,
        category: str,
        pii: bool = False,
        retention: str = "standard",
        access_tier: str = "open",
    ) -> DataSourceRecord:
        record = DataSourceRecord(
            name=name,
            category=category,
            pii=pii,
            retention=retention,
            access_tier=access_tier,
        )
        self._records[name] = record
        return record

    def get(self, name: str) -> DataSourceRecord:
        return self._records[name]

    def list(self) -> List[DataSourceRecord]:
        return sorted(self._records.values(), key=lambda record: record.name)

    def update_checks(self, name: str, checks: Iterable[Mapping[str, object]]) -> DataSourceRecord:
        record = self.get(name)
        record.checks.clear()
        record.issues.clear()
        for check in checks:
            record.record_check(
                str(check.get("name", "check")),
                bool(check.get("passed", False)),
                note=str(check.get("note")) if check.get("note") is not None else None,
            )
        return record


__all__ = [
    "DataGovernanceRegistry",
    "DataSourceRecord",
    "GovernanceCheck",
]

