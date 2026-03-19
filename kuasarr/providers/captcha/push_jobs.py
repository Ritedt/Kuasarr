# -*- coding: utf-8 -*-
"""Persistent management of captcha push jobs with TTL cleanup."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from kuasarr.providers import shared_state

PUSH_JOB_STORE_KEY = "captcha_push_jobs"
PUSH_JOB_TTL_SECONDS = 180  # Analog zu PARALLEL_JOB_TTL_SECONDS


def _load_jobs() -> Dict[str, Any]:
    jobs = shared_state.values.get(PUSH_JOB_STORE_KEY)
    if isinstance(jobs, dict):
        return dict(jobs)
    return {}


def _save_jobs(jobs: Dict[str, Any]) -> None:
    shared_state.update(PUSH_JOB_STORE_KEY, jobs)


def _now_ts() -> float:
    return time.time()


def cleanup_expired_jobs(now: Optional[float] = None) -> int:
    """Entfernt abgelaufene Push-Jobs und liefert die Anzahl gelöschter Einträge."""
    jobs = _load_jobs()
    if not jobs:
        return 0
    now_ts = now or _now_ts()
    removed = 0
    for job_id, job in list(jobs.items()):
        expires_at = float(job.get("expires_at", 0.0))
        if expires_at and now_ts > expires_at:
            jobs.pop(job_id, None)
            removed += 1
    if removed:
        _save_jobs(jobs)
    return removed


def upsert_job(job_id: str, payload: Dict[str, Any], ttl_seconds: int = PUSH_JOB_TTL_SECONDS) -> Dict[str, Any]:
    """Legt einen Push-Job neu an oder aktualisiert ihn atomar."""
    if not job_id:
        raise ValueError("job_id darf nicht leer sein")
    jobs = _load_jobs()
    now_ts = _now_ts()
    job = jobs.get(job_id, {})
    job.update(
        {
            "job_id": job_id,
            "status": payload.get("status", job.get("status", "pending")),
            "handler_id": payload.get("handler_id", job.get("handler_id")),
            "attempt": int(payload.get("attempt", job.get("attempt", 1))),
            "payload": payload.get("payload", job.get("payload", {})),
            "created_at": job.get("created_at", now_ts),
            "updated_at": now_ts,
            "expires_at": now_ts + max(1, ttl_seconds),
        }
    )
    jobs[job_id] = job
    _save_jobs(jobs)
    return job


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    return _load_jobs().get(job_id)


def list_jobs() -> Dict[str, Any]:
    """Gibt eine Kopie aller gespeicherten Jobs zurück."""
    return _load_jobs()


def update_job_status(job_id: str, status: str, **extra_fields) -> Optional[Dict[str, Any]]:
    jobs = _load_jobs()
    job = jobs.get(job_id)
    if not job:
        return None
    now_ts = _now_ts()
    job["status"] = status
    job["updated_at"] = now_ts
    if extra_fields:
        job.update(extra_fields)
    jobs[job_id] = job
    _save_jobs(jobs)
    return job


def remove_job(job_id: str) -> bool:
    jobs = _load_jobs()
    if job_id not in jobs:
        return False
    jobs.pop(job_id, None)
    _save_jobs(jobs)
    return True


__all__ = [
    "PUSH_JOB_TTL_SECONDS",
    "cleanup_expired_jobs",
    "upsert_job",
    "get_job",
    "list_jobs",
    "update_job_status",
    "remove_job",
]
