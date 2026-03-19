# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""Persistence helpers for manual link ingestion jobs and their events."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from kuasarr.providers import shared_state


# Job lifecycle statuses. These cover the complete flow from submission to
# completion/cancellation. Additional statuses can be added later without
# breaking existing entries because we persist the raw status string.
STATUS_PENDING_REVIEW = "pending_review"
STATUS_PROCESSING = "processing"
STATUS_AWAITING_CAPTCHA = "awaiting_captcha"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

VALID_STATUSES = {
    STATUS_PENDING_REVIEW,
    STATUS_PROCESSING,
    STATUS_AWAITING_CAPTCHA,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_CANCELLED,
}


def _utc_timestamp() -> str:
    """Return an ISO-8601 timestamp in UTC with a trailing ``Z``."""

    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class ManualLinkJob:
    """Dataclass representing a manual ingestion job."""

    job_id: str
    links: List[str]
    download_path: str
    status: str = STATUS_PENDING_REVIEW
    created_at: str = field(default_factory=_utc_timestamp)
    updated_at: str = field(default_factory=_utc_timestamp)
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.links = [link.strip() for link in self.links if link and str(link).strip()]
        self.download_path = (self.download_path or "").strip()
        if self.status not in VALID_STATUSES:
            # Allow forward compatibility without failing deserialisation
            VALID_STATUSES.add(self.status)

    def touch(self) -> None:
        self.updated_at = _utc_timestamp()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.job_id,
            "links": self.links,
            "download_path": self.download_path,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_error": self.last_error,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "ManualLinkJob":
        return cls(**json.loads(raw))


@dataclass
class ManualJobEvent:
    """Timeline entry for a manual job."""

    event_id: str
    job_id: str
    event_type: str
    timestamp: str = field(default_factory=_utc_timestamp)
    message: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.event_id,
            "job_id": self.job_id,
            "type": self.event_type,
            "timestamp": self.timestamp,
            "message": self.message,
            "data": self.data,
        }

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "ManualJobEvent":
        return cls(**json.loads(raw))


class ManualJobStore:
    """High-level helper around the sqlite key/value store."""

    JOBS_TABLE = "manual_jobs"
    EVENTS_TABLE = "manual_job_events"

    def __init__(self, db_factory=None):
        # ``shared_state.values['database']`` is populated during startup with
        # the ``DataBase`` constructor. We keep the dependency injectable to
        # ease testing.
        self._db_factory = db_factory or shared_state.values["database"]

    # -- internal helpers -------------------------------------------------
    def _jobs(self):
        return self._db_factory(self.JOBS_TABLE)

    def _events(self):
        return self._db_factory(self.EVENTS_TABLE)

    def _load_job(self, job_id: str) -> Optional[ManualLinkJob]:
        raw = self._jobs().retrieve(job_id)
        return ManualLinkJob.from_json(raw) if raw else None

    def _persist_job(self, job: ManualLinkJob) -> ManualLinkJob:
        job.touch()
        self._jobs().update_store(job.job_id, job.to_json())
        return job

    # -- job operations ---------------------------------------------------
    def create_job(
        self,
        links: Iterable[str],
        download_path: str,
        *,
        status: str = STATUS_PENDING_REVIEW,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        job = ManualLinkJob(
            job_id=str(uuid.uuid4()),
            links=list(links),
            download_path=download_path,
            status=status,
            metadata=dict(metadata or {}),
        )
        self._jobs().store(job.job_id, job.to_json())
        self.add_event(job.job_id, "created", message="Job created", data={"link_count": len(job.links)})
        return job.to_dict()

    def update_job(
        self,
        job_id: str,
        *,
        links: Optional[Iterable[str]] = None,
        download_path: Optional[str] = None,
        status: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        job = self._load_job(job_id)
        if not job:
            raise ValueError(f"Manual job '{job_id}' not found")

        if links is not None:
            job.links = [link.strip() for link in links if link and str(link).strip()]
        if download_path is not None:
            job.download_path = download_path.strip()
        if status is not None:
            job.status = status
        if error is not None:
            job.last_error = error
        if metadata:
            job.metadata.update(metadata)

        return self._persist_job(job).to_dict()

    def set_links(self, job_id: str, links: Iterable[str]) -> Dict[str, Any]:
        return self.update_job(job_id, links=links)

    def set_status(
        self,
        job_id: str,
        status: str,
        *,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.update_job(job_id, status=status, error=error, metadata=metadata)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self._load_job(job_id)
        return job.to_dict() if job else None

    def list_jobs(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        entries = self._jobs().retrieve_all_titles() or []
        jobs = [ManualLinkJob.from_json(value) for _, value in entries]
        if status:
            jobs = [job for job in jobs if job.status == status]
        jobs.sort(key=lambda job: job.created_at, reverse=True)
        sliced = jobs[offset: offset + limit] if limit else jobs[offset:]
        return [job.to_dict() for job in sliced]

    def delete_job(self, job_id: str) -> bool:
        return self._jobs().delete(job_id)

    def reset(self) -> None:
        self._jobs().reset()
        self._events().reset()

    # -- event operations --------------------------------------------------
    def add_event(
        self,
        job_id: str,
        event_type: str,
        *,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event = ManualJobEvent(
            event_id=str(uuid.uuid4()),
            job_id=job_id,
            event_type=event_type,
            message=message,
            data=dict(data or {}),
        )
        self._events().store(event.event_id, event.to_json())
        return event.to_dict()

    def get_events(self, job_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        entries = self._events().retrieve_all_titles() or []
        events = [ManualJobEvent.from_json(value) for _, value in entries]
        filtered = [event for event in events if event.job_id == job_id]
        filtered.sort(key=lambda event: event.timestamp, reverse=True)
        if limit:
            filtered = filtered[:limit]
        return [event.to_dict() for event in filtered]


def get_store() -> ManualJobStore:
    return ManualJobStore()


# Convenience faÃ§ade mirroring the legacy functional API -----------------


def create_job(
    links: Iterable[str],
    download_path: str,
    *,
    metadata: Optional[Dict[str, Any]] = None,
    status: str = STATUS_PENDING_REVIEW,
) -> Dict[str, Any]:
    return get_store().create_job(links, download_path, status=status, metadata=metadata)


def update_job(
    job_id: str,
    *,
    links: Optional[Iterable[str]] = None,
    download_path: Optional[str] = None,
    status: Optional[str] = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return get_store().update_job(
        job_id,
        links=links,
        download_path=download_path,
        status=status,
        error=error,
        metadata=metadata,
    )


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    return get_store().get_job(job_id)


def list_jobs(
    *,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    return get_store().list_jobs(status=status, limit=limit, offset=offset)


def set_status(
    job_id: str,
    status: str,
    *,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return get_store().set_status(job_id, status, error=error, metadata=metadata)


def delete_job(job_id: str) -> bool:
    return get_store().delete_job(job_id)


def clear_jobs() -> None:
    get_store().reset()


def add_event(
    job_id: str,
    event_type: str,
    *,
    message: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return get_store().add_event(job_id, event_type, message=message, data=data)


def get_events(job_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    return get_store().get_events(job_id, limit=limit)


__all__ = [
    "ManualLinkJob",
    "ManualJobEvent",
    "ManualJobStore",
    "STATUS_PENDING_REVIEW",
    "STATUS_PROCESSING",
    "STATUS_AWAITING_CAPTCHA",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_CANCELLED",
    "create_job",
    "update_job",
    "get_job",
    "list_jobs",
    "set_status",
    "delete_job",
    "clear_jobs",
    "add_event",
    "get_events",
    "get_store",
]





