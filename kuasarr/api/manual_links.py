from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional

from urllib.parse import urlencode

from bottle import Bottle, HTTPError, redirect, request, response

import kuasarr.providers.ui.html_images as images
try:
    import kuasarr.downloads.manual_jobs as manual_jobs
except ModuleNotFoundError as exc:  # pragma: no cover - defensive
    raise ImportError(
        "Manual link ingestion requires the updated 'kuasarr.downloads.manual_jobs' module."
        " Please reinstall or upgrade kuasarr."
    ) from exc
from kuasarr.providers.ui.html_templates import render_button, render_centered_html, render_fail
from kuasarr.storage.manual_jobs import (
    STATUS_AWAITING_CAPTCHA,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING_REVIEW,
    STATUS_PROCESSING,
)


_ALLOWED_STATUSES = {
    STATUS_PENDING_REVIEW,
    STATUS_PROCESSING,
    STATUS_AWAITING_CAPTCHA,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_CANCELLED,
}

_STATUS_LABELS = {
    STATUS_PENDING_REVIEW: "Pending Review",
    STATUS_PROCESSING: "Processing",
    STATUS_AWAITING_CAPTCHA: "Awaiting CAPTCHA",
    STATUS_COMPLETED: "Completed",
    STATUS_FAILED: "Failed",
    STATUS_CANCELLED: "Cancelled",
}

_MESSAGE_MAP = {
    "created": "Manual job created. Review details below before starting.",
    "updated": "Job details updated.",
    "started": "Processing started.",
    "cancelled": "Job cancelled.",
    "error": "Something went wrong. Please try again.",
}


def _escape(value: Any) -> str:
    return html.escape(str(value) if value is not None else "")


def _page_header(subtitle: str) -> str:
    return (
        f'<h1><img src="{images.logo}" type="image/png" alt="kuasarr logo" class="logo"/>kuasarr</h1>'
        f"<h2>{_escape(subtitle)}</h2>"
    )


def _status_badge(status: str) -> str:
    label = _STATUS_LABELS.get(status, status.title())
    css_class = status.replace("_", "-")
    return f'<span class="status status-{css_class}">{_escape(label)}</span>'


def _json(obj: Any) -> Any:
    response.content_type = "application/json"
    return obj


def _parse_links(payload: Dict[str, Any]) -> Optional[List[str]]:
    links_raw = payload.get("links")
    if links_raw is None:
        return None
    if isinstance(links_raw, str):
        return [line.strip() for line in links_raw.replace("\r", "").split("\n") if line.strip()]
    if isinstance(links_raw, list):
        return [str(item).strip() for item in links_raw if str(item).strip()]
    raise HTTPError(400, "Invalid links payload")


def setup_manual_link_routes(app: Bottle) -> None:
    def _message_html(message: Optional[str]) -> str:
        if not message:
            return ""
        return f'<div class="alert">{_escape(message)}</div>'

    def _overview_page(message: Optional[str] = None) -> str:
        jobs = manual_jobs.list_jobs(limit=200)
        rows = []
        for job in jobs:
            job_id = job.get("id")
            link_count = len(job.get("links") or [])
            path = job.get("download_path") or "Default (kuasarr/<jd:packagename>)"
            status_html = _status_badge(job.get("status"))
            updated = job.get("updated_at") or job.get("created_at") or ""
            rows.append(
                "<tr>"
                f"<td>{status_html}</td>"
                f"<td>{_escape(link_count)}</td>"
                f"<td>{_escape(path)}</td>"
                f"<td>{_escape(updated)}</td>"
                f"<td><a class=\"btn-link\" href=\"/manual-links/{_escape(job_id)}\">Open</a></td>"
                "</tr>"
            )

        if not rows:
            rows = ["<tr><td colspan=5>No manual jobs yet. Submit your first job to get started.</td></tr>"]

        table = (
            "<table class=\"jobs-table\">"
            "<thead><tr><th>Status</th><th>Links</th><th>Download Path</th><th>Updated</th><th></th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
        )

        actions = (
            '<div class="manual-actions">'
            + render_button(
                'Submit Manual Links',
                'primary',
                {"onclick": "location.href='/manual-links/new'"},
            )
            + render_button(
                'Refresh',
                'secondary',
                {"onclick": "location.href='/manual-links'"},
            )
            + render_button(
                'Back',
                'secondary',
                {"onclick": "location.href='/'"},
            )
            + "</div>"
        )

        style = """
        <style>
            .jobs-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 1.5rem;
            }
            .jobs-table th, .jobs-table td {
                padding: 0.6rem 0.8rem;
                border-bottom: 1px solid #ddd;
                text-align: left;
            }
            .jobs-table tbody tr:hover {
                background-color: rgba(0, 0, 0, 0.03);
            }
            .manual-actions {
                display: flex;
                gap: 0.75rem;
                flex-wrap: wrap;
                justify-content: center;
                margin-top: 1rem;
            }
            .status {
                display: inline-block;
                padding: 0.2rem 0.6rem;
                border-radius: 9999px;
                font-size: 0.85rem;
                font-weight: 600;
                background-color: rgba(13, 110, 253, 0.1);
                color: #0d6efd;
            }
            .status-processing { background-color: rgba(13, 110, 253, 0.15); color: #0d6efd; }
            .status-awaiting-captcha { background-color: rgba(255, 193, 7, 0.2); color: #b58100; }
            .status-completed { background-color: rgba(25, 135, 84, 0.18); color: #1e7b47; }
            .status-failed { background-color: rgba(220, 53, 69, 0.18); color: #c12c3e; }
            .status-cancelled { background-color: rgba(108, 117, 125, 0.18); color: #495057; }
            .alert {
                margin-top: 1rem;
                padding: 0.75rem 1rem;
                border-radius: 0.5rem;
                background-color: rgba(13, 110, 253, 0.1);
                color: #0d6efd;
                font-weight: 500;
            }
            .btn-link {
                color: #0d6efd;
                font-weight: 600;
            }
        </style>
        """

        content = (
            _page_header("Manual Link Intake")
            + _message_html(message)
            + "<p>Use this workspace to submit supported forum links, review pending jobs, and trigger downloads.</p>"
            + actions
            + table
            + style
        )
        return render_centered_html(content)

    def _new_job_form(form_data: Optional[Dict[str, str]] = None, message: Optional[str] = None) -> str:
        form_data = form_data or {}
        links_value = _escape(form_data.get("links", ""))
        path_value = _escape(form_data.get("download_path", ""))
        notes_value = _escape(form_data.get("notes", ""))

        submit_button = render_button("Save Job", "primary", {"type": "submit"})
        back_button = render_button("Cancel", "secondary", {"type": "button", "onclick": "location.href='/manual-links'"})

        style = """
        <style>
            form.manual-form textarea {
                width: 100%;
                min-height: 8rem;
                resize: vertical;
                font-family: monospace;
            }
            form.manual-form .actions {
                margin-top: 1rem;
                display: flex;
                gap: 0.75rem;
                justify-content: center;
                flex-wrap: wrap;
            }
            form.manual-form input[type="text"],
            form.manual-form textarea {
                margin-bottom: 1rem;
            }
        </style>
        """

        form = (
            f"<form method='post' class='manual-form'>"
            f"<label for='links'>Forum links (one per line)</label>"
            f"<textarea id='links' name='links' required placeholder='https://example.com/thread/...'>{links_value}</textarea>"
            f"<label for='download_path'>Download path (optional)</label>"
            f"<input id='download_path' name='download_path' type='text' placeholder='/downloads/software' value='{path_value}' />"
            f"<label for='notes'>Notes (optional)</label>"
            f"<textarea id='notes' name='notes' rows='3' placeholder='Internal notes'>{notes_value}</textarea>"
            f"<div class='actions'>{submit_button}{back_button}</div>"
            "</form>"
        )

        content = _page_header("Submit Manual Links") + _message_html(message) + form + style
        return render_centered_html(content)

    def _detail_page(job: Dict[str, Any], events: List[Dict[str, Any]], message: Optional[str] = None) -> str:
        metadata = job.get("metadata") or {}
        notes = metadata.get("notes")
        protected_packages = metadata.get("protected_packages") or []
        items = metadata.get("items") or []

        links_html = "".join(
            f"<li><code>{_escape(link)}</code></li>" for link in job.get("links", [])
        ) or "<li>No links stored.</li>"

        items_rows = []
        for item in items:
            item_status = _status_badge(item.get("status", "unknown"))
            error = item.get("error")
            error_html = f"<div class='item-error'>{_escape(error)}</div>" if error else ""
            package_html = (
                f"<div class='item-package'>Package: <code>{_escape(item.get('package_id'))}</code></div>"
                if item.get("package_id")
                else ""
            )
            items_rows.append(
                "<tr>"
                f"<td>{_escape(item.get('index', 0) + 1 if isinstance(item.get('index'), int) else item.get('index'))}</td>"
                f"<td><code>{_escape(item.get('link'))}</code></td>"
                f"<td>{item_status}{package_html}{error_html}</td>"
                "</tr>"
            )

        items_table = ""
        if items_rows:
            items_table = (
                "<h3>Processed Links</h3>"
                "<table class='items-table'>"
                "<thead><tr><th>#</th><th>Link</th><th>Status</th></tr></thead>"
                f"<tbody>{''.join(items_rows)}</tbody>"
                "</table>"
            )

        events_list = "".join(
            "<li>"
            f"<strong>{_escape(evt.get('timestamp'))}</strong> â€” {_escape(evt.get('type'))}"
            f"<div>{_escape(evt.get('message') or '')}</div>"
            + (
                f"<pre>{_escape(json.dumps(evt.get('data'), indent=2) or '')}</pre>"
                if evt.get("data") else ""
            )
            + "</li>"
            for evt in events
        ) or "<li>No events recorded yet.</li>"

        status_html = _status_badge(job.get("status"))
        path_display = job.get("download_path") or "Default (kuasarr/<jd:packagename>)"

        update_form = (
            f"<form method='post' action='/manual-links/{_escape(job['id'])}/update' class='manual-form'>"
            f"<label for='download_path'>Download path</label>"
            f"<input id='download_path' name='download_path' type='text' value='{_escape(job.get('download_path') or '')}' placeholder='/downloads/software' />"
            f"<label for='notes'>Notes</label>"
            f"<textarea id='notes' name='notes' rows='3'>{_escape(notes or '')}</textarea>"
            f"<div class='actions'>{render_button('Save Changes', 'primary', {'type': 'submit'})}</div>"
            "</form>"
        )

        actions = []
        if job.get("status") in {STATUS_PENDING_REVIEW, STATUS_FAILED}:
            actions.append(
                f"<form method='post' action='/manual-links/{_escape(job['id'])}/start'>"
                f"{render_button('Start Processing', 'primary', {'type': 'submit'})}"
                "</form>"
            )
        if job.get("status") not in {STATUS_CANCELLED, STATUS_COMPLETED}:
            actions.append(
                f"<form method='post' action='/manual-links/{_escape(job['id'])}/cancel' onsubmit=\"return confirm('Cancel this job?');\">"
                f"{render_button('Cancel Job', 'secondary', {'type': 'submit'})}"
                "</form>"
            )
        if job.get("status") == STATUS_AWAITING_CAPTCHA or protected_packages:
            captcha_button = render_button(
                'Open CAPTCHA Helper',
                'primary',
                {"onclick": "location.href='/captcha'"},
            )
            actions.append(f"<div class='inline-action'>{captcha_button}</div>")
        actions.append(render_button('Back to Overview', 'secondary', {'onclick': "location.href='/manual-links'"}))

        actions_html = "<div class='manual-actions'>" + "".join(actions) + "</div>"

        protected_html = ""
        if protected_packages:
            package_list = "".join(f"<li><code>{_escape(pkg)}</code></li>" for pkg in protected_packages)
            protected_html = (
                "<div class='protected-box'>"
                "<strong>Pending CAPTCHA packages:</strong>"
                f"<ul>{package_list}</ul>"
                "</div>"
            )

        style = """
        <style>
            .status {
                display: inline-block;
                padding: 0.2rem 0.6rem;
                border-radius: 9999px;
                font-size: 0.85rem;
                font-weight: 600;
                background-color: rgba(13, 110, 253, 0.1);
                color: #0d6efd;
            }
            .status-processing { background-color: rgba(13, 110, 253, 0.15); color: #0d6efd; }
            .status-awaiting-captcha { background-color: rgba(255, 193, 7, 0.2); color: #b58100; }
            .status-completed { background-color: rgba(25, 135, 84, 0.18); color: #1e7b47; }
            .status-failed { background-color: rgba(220, 53, 69, 0.18); color: #c12c3e; }
            .status-cancelled { background-color: rgba(108, 117, 125, 0.18); color: #495057; }
            .job-meta { margin: 1rem 0; text-align: left; }
            .job-meta dt { font-weight: 600; }
            .job-meta dd { margin: 0 0 0.75rem 0; }
            .items-table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
            .items-table th, .items-table td { padding: 0.5rem 0.75rem; border-bottom: 1px solid #ddd; text-align: left; }
            .items-table code { word-break: break-all; }
            .item-error { margin-top: 0.3rem; color: #c12c3e; }
            .manual-actions { display: flex; gap: 0.75rem; flex-wrap: wrap; justify-content: center; margin-top: 1.5rem; }
            .manual-form .actions { display: flex; gap: 0.75rem; justify-content: center; margin-top: 1rem; }
            .manual-form textarea, .manual-form input { width: 100%; margin-bottom: 1rem; }
            .event-list { text-align: left; margin-top: 1.5rem; }
            .event-list li { margin-bottom: 0.75rem; }
            .event-list pre { background-color: rgba(0,0,0,0.05); padding: 0.5rem; border-radius: 0.5rem; overflow-x: auto; }
            .protected-box { margin-top: 1rem; border: 1px solid rgba(13,110,253,0.3); padding: 0.75rem; border-radius: 0.75rem; text-align: left; }
            .alert { margin-top: 1rem; padding: 0.75rem 1rem; border-radius: 0.5rem; background-color: rgba(13,110,253,0.1); color: #0d6efd; font-weight: 500; }
        </style>
        """

        content = (
            _page_header(f"Manual Job {job.get('id')}")
            + _message_html(message)
            + f"<div class='job-meta'><dl>"
            + f"<dt>Status</dt><dd>{status_html}</dd>"
            + f"<dt>Download Path</dt><dd><code>{_escape(path_display)}</code></dd>"
            + f"<dt>Created</dt><dd>{_escape(job.get('created_at'))}</dd>"
            + f"<dt>Updated</dt><dd>{_escape(job.get('updated_at'))}</dd>"
            + (f"<dt>Notes</dt><dd>{_escape(notes)}</dd>" if notes else "")
            + "</dl></div>"
            + protected_html
            + "<h3>Queued Links</h3><ul>" + links_html + "</ul>"
            + items_table
            + update_form
            + actions_html
            + "<h3>Activity Log</h3><ul class='event-list'>" + events_list + "</ul>"
            + style
        )
        return render_centered_html(content)

    @app.get('/manual-links')
    def manual_links_overview_view():
        msg_code = request.query.get('msg')
        message = _MESSAGE_MAP.get(msg_code, msg_code if msg_code else None)
        return _overview_page(message)

    @app.get('/manual-links/new')
    def manual_links_new_view():
        return _new_job_form()

    @app.post('/manual-links/new')
    def manual_links_create_view():
        links_raw = request.forms.get('links', '')
        links = [line.strip() for line in links_raw.replace('\r', '').split('\n') if line.strip()]
        download_path = request.forms.get('download_path', '').strip()
        notes = request.forms.get('notes', '')

        if not links:
            return _new_job_form(
                form_data={
                    'links': links_raw,
                    'download_path': download_path,
                    'notes': notes,
                },
                message="Please provide at least one link.",
            )

        try:
            job = manual_jobs.create_job(links, download_path, notes=notes)
        except Exception as exc:  # pragma: no cover - defensive
            return _new_job_form(
                form_data={
                    'links': links_raw,
                    'download_path': download_path,
                    'notes': notes,
                },
                message=str(exc) or "Could not create job.",
            )

        redirect(f"/manual-links/{job['id']}?{urlencode({'msg': 'created'})}")

    @app.get('/manual-links/<job_id>')
    def manual_links_detail_view(job_id: str):
        msg_code = request.query.get('msg')
        message = _MESSAGE_MAP.get(msg_code, msg_code if msg_code else None)
        try:
            detail = manual_jobs.get_job_with_events(job_id, limit=50)
        except ValueError as exc:
            return render_fail(str(exc))
        return _detail_page(detail["job"], detail.get("events", []), message)

    @app.post('/manual-links/<job_id>/start')
    def manual_links_start_view(job_id: str):
        try:
            manual_jobs.process_job(job_id)
        except ValueError as exc:
            return render_fail(str(exc))
        except RuntimeError as exc:
            return render_fail(str(exc))
        redirect(f"/manual-links/{job_id}?{urlencode({'msg': 'started'})}")

    @app.post('/manual-links/<job_id>/cancel')
    def manual_links_cancel_view(job_id: str):
        try:
            manual_jobs.cancel_job(job_id)
        except ValueError as exc:
            return render_fail(str(exc))
        redirect(f"/manual-links/{job_id}?{urlencode({'msg': 'cancelled'})}")

    @app.post('/manual-links/<job_id>/update')
    def manual_links_update_view(job_id: str):
        download_path = request.forms.get('download_path', '')
        notes = request.forms.get('notes', '')
        try:
            manual_jobs.update_job(job_id, download_path=download_path, notes=notes)
        except ValueError as exc:
            return render_fail(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            return render_fail(str(exc))
        redirect(f"/manual-links/{job_id}?{urlencode({'msg': 'updated'})}")

    @app.get('/api/manual-links')
    def list_manual_links():
        try:
            status = request.query.get('status') or None
            limit = int(request.query.limit or 50)
            offset = int(request.query.offset or 0)
        except ValueError:
            raise HTTPError(400, "Invalid pagination parameters")

        if status and status not in _ALLOWED_STATUSES:
            raise HTTPError(400, f"Unknown status '{status}'")

        jobs = manual_jobs.list_jobs(status=status, limit=limit, offset=offset)
        return _json({"jobs": jobs})

    @app.post('/api/manual-links')
    def create_manual_link_job():
        payload = request.json or {}
        links = _parse_links(payload)
        if not links:
            raise HTTPError(400, "At least one link is required")

        download_path = payload.get("download_path") or ""
        notes = payload.get("notes")

        try:
            job = manual_jobs.create_job(links, download_path, notes=notes)
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPError(500, str(exc))

        response.status = 201
        return _json({"job": job})

    @app.get('/api/manual-links/<job_id>')
    def get_manual_link_job(job_id: str):
        events_limit = request.query.get('events_limit')
        try:
            limit = int(events_limit) if events_limit else 100
        except ValueError:
            raise HTTPError(400, "events_limit must be numeric")

        try:
            detail = manual_jobs.get_job_with_events(job_id, limit=limit)
        except ValueError as exc:
            raise HTTPError(404, str(exc))
        return _json(detail)

    @app.post('/api/manual-links/<job_id>/update')
    def update_manual_link_job(job_id: str):
        payload = request.json or {}
        links = _parse_links(payload)
        download_path = payload.get("download_path") if "download_path" in payload else None
        notes = payload.get("notes") if "notes" in payload else None
        try:
            job = manual_jobs.update_job(
                job_id,
                download_path=download_path,
                links=links,
                notes=notes,
            )
        except ValueError as exc:
            raise HTTPError(404, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPError(400, str(exc))
        return _json({"job": job})

    @app.post('/api/manual-links/<job_id>/start')
    def start_manual_link_job(job_id: str):
        try:
            job = manual_jobs.process_job(job_id)
        except ValueError as exc:
            raise HTTPError(404, str(exc))
        except RuntimeError as exc:
            raise HTTPError(409, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPError(500, str(exc))
        return _json({"job": job})

    @app.post('/api/manual-links/<job_id>/cancel')
    def cancel_manual_link_job(job_id: str):
        try:
            job = manual_jobs.cancel_job(job_id)
        except ValueError as exc:
            raise HTTPError(404, str(exc))
        return _json({"job": job})


__all__ = ["setup_manual_link_routes"]



