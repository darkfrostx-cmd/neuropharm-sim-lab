"""State management helpers for collaborative gap triage."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, MutableMapping, Optional, Sequence

from .models import BiolinkPredicate


def _utcnow() -> datetime:
    now = datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


@dataclass(slots=True)
class TriageComment:
    """Audit log entry attached to a research queue item."""

    author: str
    body: str
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class ResearchQueueEntry:
    """Research queue payload tracked alongside gap candidates."""

    id: str
    subject: str
    object: str
    predicate: BiolinkPredicate
    status: str = "new"
    priority: int = 2
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    watchers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    comments: List[TriageComment] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)
    history: List[Dict[str, object]] = field(default_factory=list)

    def touch(self, *, actor: str, changes: MutableMapping[str, object]) -> None:
        self.updated_at = _utcnow()
        entry = {"timestamp": self.updated_at.isoformat(), "actor": actor, "changes": dict(changes)}
        self.history.append(entry)


class ResearchQueueStore:
    """In-memory management of collaborative triage state."""

    allowed_status: Sequence[str] = ("new", "triaging", "in_review", "resolved")

    def __init__(self) -> None:
        self._entries: Dict[str, ResearchQueueEntry] = {}

    @staticmethod
    def _entry_id(subject: str, predicate: BiolinkPredicate, object_: str) -> str:
        return f"{subject}|{predicate.value}|{object_}"

    def list(self) -> List[ResearchQueueEntry]:
        return sorted(self._entries.values(), key=lambda entry: (entry.priority, entry.updated_at), reverse=False)

    def get(self, entry_id: str) -> ResearchQueueEntry:
        if entry_id not in self._entries:
            raise KeyError(entry_id)
        return self._entries[entry_id]

    def enqueue(
        self,
        *,
        subject: str,
        predicate: BiolinkPredicate,
        object_: str,
        reason: str,
        author: str,
        priority: int = 2,
        watchers: Optional[Iterable[str]] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> ResearchQueueEntry:
        entry_id = self._entry_id(subject, predicate, object_)
        existing = self._entries.get(entry_id)
        if existing:
            existing.priority = priority
            if metadata:
                existing.metadata.update(metadata)
            if watchers:
                new_watchers = {w.strip() for w in watchers if w and w.strip()}
                existing_watchers = set(existing.watchers)
                existing.watchers = sorted(existing_watchers.union(new_watchers))
            existing.touch(actor=author, changes={"action": "enqueue:update"})
            return existing
        metadata_payload = dict(metadata or {})
        entry = ResearchQueueEntry(
            id=entry_id,
            subject=subject,
            object=object_,
            predicate=predicate,
            priority=priority,
            watchers=sorted({w.strip() for w in (watchers or []) if w and w.strip()}),
            metadata=metadata_payload,
        )
        entry.comments.append(TriageComment(author=author, body=reason))
        entry.touch(actor=author, changes={"action": "enqueue"})
        self._entries[entry_id] = entry
        return entry

    def update(
        self,
        entry_id: str,
        *,
        actor: str,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        add_watchers: Optional[Iterable[str]] = None,
        remove_watchers: Optional[Iterable[str]] = None,
        comment: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> ResearchQueueEntry:
        entry = self.get(entry_id)
        changes: Dict[str, object] = {}
        if status and status != entry.status:
            if status not in self.allowed_status:
                raise ValueError(f"Invalid status '{status}'")
            entry.status = status
            changes["status"] = status
        if priority is not None and priority != entry.priority:
            entry.priority = max(1, min(5, int(priority)))
            changes["priority"] = entry.priority
        if add_watchers:
            new_watchers = {w.strip() for w in add_watchers if w and w.strip()}
            if new_watchers:
                updated = set(entry.watchers)
                updated.update(new_watchers)
                entry.watchers = sorted(updated)
                changes.setdefault("watchers", {})["added"] = sorted(new_watchers)
        if remove_watchers:
            remove_set = {w.strip() for w in remove_watchers if w and w.strip()}
            if remove_set:
                remaining = [watcher for watcher in entry.watchers if watcher not in remove_set]
                entry.watchers = remaining
                changes.setdefault("watchers", {})["removed"] = sorted(remove_set)
        if metadata:
            entry.metadata.update(metadata)
            changes["metadata"] = metadata
        if comment:
            note = TriageComment(author=actor, body=comment)
            entry.comments.append(note)
            changes.setdefault("comments", []).append(note.body)
        if changes:
            entry.touch(actor=actor, changes=changes)
        return entry


__all__ = [
    "ResearchQueueEntry",
    "ResearchQueueStore",
    "TriageComment",
]

