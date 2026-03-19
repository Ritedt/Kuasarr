"""Manual link ingestion processing utilities."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from kuasarr.downloads import download
from kuasarr.providers import shared_state
from kuasarr.providers.log import info
from kuasarr.storage.manual_jobs import (
    STATUS_AWAITING_CAPTCHA,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING_REVIEW,
    STATUS_PROCESSING,
    add_event,
    create_job as store_create_job,
    get_events,
    get_job as store_get_job,
    get_store,
    list_jobs as store_list_jobs,
    set_status as store_set_status,
    update_job as store_update_job,
)


_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _dedupe_links(links: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for link in links:
        cleaned = (link or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _derive_title(link: str, fallback: str) -> str:
    parsed = urlparse(link)
    candidate = parsed.path.rstrip("/") if parsed.path else ""
    if candidate:
        candidate = candidate.split("/")[-1]
    if not candidate:
        candidate = parsed.netloc or fallback

    candidate = candidate.replace("-", " ").replace("_", " ")
    candidate = _SLUG_RE.sub(" ", candidate)
    candidate = candidate.strip() or fallback

    try:
        return shared_state.sanitize_title(candidate)
    except AttributeError:
        return candidate


def _normalise_notes(notes: Optional[str]) -> Optional[str]:
    if notes is None:
        return None
    cleaned = notes.strip()
    return cleaned or None


def create_job(
    links: Iterable[str],
    download_path: Optional[str] = None,
    *,
    notes: Optional[str] = None,
) -> Dict[str, object]:
    cleaned_links = _dedupe_links(links)
    metadata: Dict[str, object] = {}
    canonical_notes = _normalise_notes(notes)
    if canonical_notes:
        metadata["notes"] = canonical_notes
    job = store_create_job(cleaned_links, download_path or "", metadata=metadata)
    return job


def update_job(
    job_id: str,
    *,
    download_path: Optional[str] = None,
    links: Optional[Iterable[str]] = None,
    notes: Optional[str] = None,
) -> Dict[str, object]:
    metadata: Dict[str, object] = {}
    if notes is not None:
        canonical_notes = _normalise_notes(notes)
        if canonical_notes:
            metadata["notes"] = canonical_notes
        else:
            metadata["notes"] = None  # sentinel to remove later

    job = store_get_job(job_id)
    if not job:
        raise ValueError(f"Manual job '{job_id}' not found")

    meta_update: Dict[str, Any]
    if metadata:
        meta_update = job.get("metadata", {}).copy() if isinstance(job.get("metadata"), dict) else {}
        for key, value in metadata.items():
            if value is None:
                meta_update.pop(key, None)
            else:
                meta_update[key] = value
    else:
        meta_update = {}

    updated = store_update_job(
        job_id,
        download_path=download_path,
        links=_dedupe_links(links) if links is not None else None,
        metadata=meta_update if meta_update else None,
    )
    add_event(job_id, "updated", message="Job metadata updated")
    return updated


def cancel_job(job_id: str) -> Dict[str, object]:
    job = store_get_job(job_id)
    if not job:
        raise ValueError(f"Manual job '{job_id}' not found")
    if job["status"] == STATUS_CANCELLED:
        return job
    updated = store_set_status(job_id, STATUS_CANCELLED)
    add_event(job_id, "cancelled", message="Job cancelled")
    return updated


def process_job(job_id: str) -> Dict[str, object]:
    job = store_get_job(job_id)
    if not job:
        raise ValueError(f"Manual job '{job_id}' not found")
    if job["status"] == STATUS_CANCELLED:
        return job
    if job["status"] == STATUS_PROCESSING:
        raise RuntimeError("Job is already being processed")

    if job["status"] not in {
        STATUS_PENDING_REVIEW,
        STATUS_FAILED,
        STATUS_AWAITING_CAPTCHA,
        STATUS_COMPLETED,
    }:
        info(f"Processing manual job {job_id} from unexpected status {job['status']}")

    store_set_status(job_id, STATUS_PROCESSING, metadata={"items": []})
    add_event(job_id, "processing_started", message="Manual processing started")

    destination = (job.get("download_path") or "").strip() or None

    items: List[Dict[str, object]] = []
    errors: List[str] = []
    awaiting_captcha = False
    all_success = True
    protected_package_ids: List[str] = []

    protected_db = shared_state.values["database"]("protected")

    for index, link in enumerate(job.get("links", [])):
        title = _derive_title(link, fallback=f"Manual Job {job_id}")
        item: Dict[str, object] = {"index": index, "link": link, "title": title}

        try:
            result = download(
                shared_state,
                "Manual",
                title,
                link,
                mirror=None,
                size_mb=None,
                password="",
                imdb_id=None,
                destination_folder=destination,
                manual_job_id=job_id,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            all_success = False
            message = str(exc)
            item.update({"status": STATUS_FAILED, "error": message})
            errors.append(message)
            add_event(job_id, "link_failed", message=message, data={"link": link})
            items.append(item)
            continue

        item["result"] = result
        package_id = result.get("package_id")
        if package_id:
            item["package_id"] = package_id

        if result.get("success"):
            protected_blob = protected_db.retrieve(package_id) if package_id else None
            if protected_blob:
                awaiting_captcha = True
                item["status"] = STATUS_AWAITING_CAPTCHA
                protected_package_ids.append(package_id)
                add_event(
                    job_id,
                    "captcha_required",
                    message=f"CAPTCHA required for package {package_id}",
                    data={"package_id": package_id, "link": link},
                )
            else:
                item["status"] = STATUS_COMPLETED
                add_event(
                    job_id,
                    "link_completed",
                    message=f"Link {index + 1} processed successfully",
                    data={"package_id": package_id, "link": link},
                )
        else:
            all_success = False
            item["status"] = STATUS_FAILED
            message = result.get("message") or "Pipeline returned failure"
            item["error"] = message
            errors.append(message)
            add_event(
                job_id,
                "link_failed",
                message=message,
                data={"package_id": package_id, "link": link},
            )

        items.append(item)

    final_status = STATUS_COMPLETED
    if awaiting_captcha:
        final_status = STATUS_AWAITING_CAPTCHA
    elif not all_success:
        final_status = STATUS_FAILED

    error_message = "; ".join(errors) if errors and final_status == STATUS_FAILED else None

    meta_update: Dict[str, Any] = {"items": items}
    if protected_package_ids:
        meta_update["protected_packages"] = protected_package_ids
    if error_message:
        meta_update["last_error_message"] = error_message
    else:
        meta_update.pop("last_error_message", None)

    updated = store_set_status(
        job_id,
        final_status,
        error=error_message,
        metadata=meta_update,
    )
    add_event(
        job_id,
        "processing_finished",
        message=f"Job finished with status {final_status}",
        data={"protected_packages": protected_package_ids},
    )
    return updated


def list_jobs(
    *,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, object]]:
    return store_list_jobs(status=status, limit=limit, offset=offset)


def get_job(job_id: str) -> Optional[Dict[str, object]]:
    return store_get_job(job_id)


def get_job_with_events(job_id: str, *, limit: int = 100) -> Dict[str, object]:
    job = store_get_job(job_id)
    if not job:
        raise ValueError(f"Manual job '{job_id}' not found")
    events = get_events(job_id, limit=limit)
    return {"job": job, "events": events}


def _extract_manual_job_id(package_id: str) -> Optional[str]:
    if not package_id:
        return None
    try:
        _, potential_id = package_id.rsplit("_", 1)
    except ValueError:
        return None
    if potential_id and "-" in potential_id and len(potential_id) >= 8:
        return potential_id
    return None


def get_download_path_for_package(package_id: str) -> Optional[str]:
    job_id = _extract_manual_job_id(package_id)
    if not job_id:
        return None
    job = store_get_job(job_id)
    if not job:
        return None
    path = job.get("download_path") or ""
    return path.strip() or None


def update_job_from_package_event(
    package_id: str,
    *,
    success: bool,
    error: Optional[str] = None,
) -> Optional[Dict[str, object]]:
    job_id = _extract_manual_job_id(package_id)
    if not job_id:
        return None

    job = store_get_job(job_id)
    if not job:
        return None

    metadata = job.get("metadata") or {}
    items = metadata.get("items") or []

    matched = False
    for item in items:
        if item.get("package_id") == package_id:
            matched = True
            item["status"] = STATUS_COMPLETED if success else STATUS_FAILED
            if success:
                item.pop("error", None)
            elif error:
                item["error"] = error
    if not matched:
        return None

    if success:
        protected_packages = metadata.get("protected_packages") or []
        metadata["protected_packages"] = [pkg for pkg in protected_packages if pkg != package_id]
        if not metadata["protected_packages"]:
            metadata.pop("protected_packages", None)

    metadata["items"] = items

    statuses = {item.get("status") for item in items}
    error_message = None if success else (error or job.get("last_error"))

    if STATUS_FAILED in statuses:
        new_status = STATUS_FAILED
    elif STATUS_AWAITING_CAPTCHA in statuses:
        new_status = STATUS_AWAITING_CAPTCHA
    elif statuses and all(status == STATUS_COMPLETED for status in statuses):
        new_status = STATUS_COMPLETED
    else:
        new_status = STATUS_PROCESSING

    updated = store_set_status(job_id, new_status, error=error_message, metadata=metadata)
    event_type = "captcha_resolved" if success else "captcha_failed"
    message = "CAPTCHA solved successfully" if success else error or "CAPTCHA handling failed"
    add_event(job_id, event_type, message=message, data={"package_id": package_id})
    return updated


__all__ = [
    "create_job",
    "update_job",
    "cancel_job",
    "process_job",
    "list_jobs",
    "get_job",
    "get_job_with_events",
    "get_download_path_for_package",
    "update_job_from_package_event",
]



