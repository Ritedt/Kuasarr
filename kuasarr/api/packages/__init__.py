# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import html
import json
import logging

from bottle import request, response, redirect

import kuasarr.providers.ui.html_images as images
from kuasarr.downloads.packages import delete_package, get_packages
from kuasarr.providers import shared_state
from kuasarr.providers.auth import require_api_key, is_browser_authenticated
from kuasarr.providers.ui.html_templates import render_button, render_centered_html

logger = logging.getLogger(__name__)

_CATEGORY_EMOJI = {
    "movies": "🎬",
    "tv": "📺",
    "docs": "📄",
    "music": "🎵",
    "not_quasarr": "❓",
}


def _get_category_emoji(cat: str) -> str:
    return _CATEGORY_EMOJI.get(cat, "❓")


def _format_size(mb: float | None = None, bytes_val: int | None = None) -> str:
    if bytes_val is not None:
        if bytes_val == 0:
            return "? MB"
        if bytes_val < 1024:
            return f"{bytes_val} B"
        if bytes_val < 1024 * 1024:
            return f"{bytes_val // 1024} KB"
        mb = bytes_val / (1024 * 1024)
    if mb is None or mb == 0:
        return "? MB"
    if mb < 1024:
        return f"{mb:.0f} MB"
    return f"{mb / 1024:.1f} GB"


def _escape_js(s: str) -> str:
    """Escape a string for safe embedding as a JavaScript string literal.

    Uses json.dumps for correct unicode + special-char handling, then
    strips the surrounding double-quotes so callers can wrap the value
    in whichever quote style they need.
    """
    return json.dumps(str(s))[1:-1]  # e.g.  hello\nworld  ->  hello\\nworld



def _render_queue_item(item: dict) -> str:
    filename = item.get("filename", "Unknown")
    percentage = item.get("percentage", 0)
    timeleft = item.get("timeleft", "??:??:??")
    bytes_val = item.get("bytes", 0)
    mb = item.get("mb", 0)
    cat = item.get("cat", "not_quasarr")
    is_archive = item.get("is_archive", False)
    nzo_id = item.get("nzo_id", "")
    storage = item.get("storage", "")

    is_captcha = "[CAPTCHA" in filename
    status_text = "Downloading"
    if is_captcha:
        status_emoji = "🔒"
        status_text = "Waiting for CAPTCHA Solution!"
    elif "[Extracting]" in filename:
        status_emoji = "📦"
        status_text = "Extracting"
    elif "[Paused]" in filename:
        status_emoji = "⏸️"
        status_text = "Paused"
    elif "[Linkgrabber]" in filename:
        status_emoji = "🔗"
        status_text = "Linkgrabber"
    else:
        status_emoji = "▶️"

    display_name = filename
    for prefix in [
        "[Downloading] ",
        "[Extracting] ",
        "[Paused] ",
        "[Linkgrabber] ",
        "[CAPTCHA not solved!] ",
    ]:
        display_name = display_name.replace(prefix, "")

    display_name = html.escape(display_name)
    archive_badge = "📦" if is_archive else ""
    cat_emoji = _get_category_emoji(cat)
    size_str = _format_size(bytes_val=bytes_val) if bytes_val else _format_size(mb=mb)

    if percentage == 0:
        progress_html = '<span class="progress-waiting">waiting...</span>'
    else:
        progress_html = (
            f'<div class="progress-track">'
            f'<div class="progress-fill" style="width: {percentage}%"></div>'
            f'</div>'
        )

    _raw_name = item.get("filename", item.get("name", "Unknown"))
    for prefix in [
        "[Downloading] ",
        "[Extracting] ",
        "[Paused] ",
        "[Linkgrabber] ",
        "[CAPTCHA not solved!] ",
    ]:
        _raw_name = _raw_name.replace(prefix, "")
    info_onclick = (
        f"showPackageDetails("
        f"{json.dumps(nzo_id)}, "
        f"{json.dumps(_raw_name)}, "
        f"{json.dumps(cat)}, "
        f"{json.dumps('Yes' if is_archive else 'No')}, "
        f"{json.dumps('')}, "
        f"{json.dumps(timeleft)}, "
        f"{json.dumps(size_str)}, "
        f"{json.dumps(str(percentage))}, "
        f"{json.dumps(status_text)}, "
        f"{json.dumps(storage)}, "
        f"{str(is_captcha).lower()})"
    )
    info_btn = f'<button class="btn-small info" onclick="{html.escape(info_onclick)}">ℹ️</button>'

    if is_captcha and nzo_id:
        actions = f"""
            <div class="package-actions">
                {info_btn}
                <button class="btn-small primary-thin" onclick="location.href='/captcha?package_id={html.escape(nzo_id)}'">🔓 Solve CAPTCHA</button>
                <span class="spacer"></span>
                <button class="btn-small danger" onclick="{html.escape(f'confirmDelete({json.dumps(nzo_id)}, {json.dumps(_raw_name)})')}">🗑️</button>
            </div>
        """
    elif nzo_id:
        actions = f"""
            <div class="package-actions">
                {info_btn}
                <span class="spacer"></span>
                <button class="btn-small danger" onclick="{html.escape(f'confirmDelete({json.dumps(nzo_id)}, {json.dumps(_raw_name)})')}">🗑️</button>
            </div>
        """
    else:
        actions = f"""
            <div class="package-actions">
                {info_btn}
                <span class="spacer"></span>
            </div>
        """

    cat_html = f'<span title="Category: {html.escape(cat)}">{cat_emoji}</span>'
    archive_html = (
        f'<span title="Archive: {html.escape(str(is_archive))}">{archive_badge}</span>'
        if is_archive
        else ""
    )

    return f"""
        <div class="package-card">
            <div class="package-header">
                <span class="status-emoji">{status_emoji}</span>
                <span class="package-name">{display_name}</span>
            </div>
            <div class="package-progress">
                {progress_html}
                <span class="progress-percent">{percentage}%</span>
            </div>
            <div class="package-details">
                <span>⏱️ {timeleft}</span>
                <span>💾 {size_str}</span>
                {cat_html}
                {archive_html}
            </div>
            {actions}
        </div>
    """


def _render_history_item(item: dict) -> str:
    name = html.escape(item.get("name", "Unknown"))
    status = item.get("status", "Unknown")
    bytes_val = item.get("bytes", 0)
    category = item.get("category", "not_quasarr")
    is_archive = item.get("is_archive", False)
    extraction_status = item.get("extraction_status", "")
    fail_message = html.escape(item.get("fail_message", ""))
    nzo_id = item.get("nzo_id", "")
    storage = item.get("storage", "")

    is_error = status.lower() in ["failed", "error"] or bool(fail_message)
    card_class = "package-card error" if is_error else "package-card"

    cat_emoji = _get_category_emoji(category)
    size_str = _format_size(bytes_val=bytes_val)

    archive_emoji = ""
    if is_archive:
        if extraction_status == "SUCCESSFUL":
            archive_emoji = "✅"
        elif extraction_status == "RUNNING":
            archive_emoji = "⏳"
        else:
            archive_emoji = "📦"

    status_emoji = "❌" if is_error else "✅"
    error_html = (
        f'<div class="package-error">⚠️ {fail_message}</div>' if fail_message else ""
    )

    _raw_hist_name = item.get("name", "Unknown")
    info_onclick = (
        f"showPackageDetails("
        f"{json.dumps(nzo_id)}, "
        f"{json.dumps(_raw_hist_name)}, "
        f"{json.dumps(category)}, "
        f"{json.dumps('Yes' if is_archive else 'No')}, "
        f"{json.dumps(extraction_status)}, "
        f"{json.dumps('')}, "
        f"{json.dumps(size_str)}, "
        f"{json.dumps('')}, "
        f"{json.dumps(status)}, "
        f"{json.dumps(storage)}, "
        f"false)"
    )
    info_btn = f'<button class="btn-small info" onclick="{html.escape(info_onclick)}">ℹ️</button>'

    if nzo_id:
        actions = f"""
            <div class="package-actions">
                {info_btn}
                <span class="spacer"></span>
                <button class="btn-small danger" onclick="{html.escape(f'confirmDelete({json.dumps(nzo_id)}, {json.dumps(_raw_hist_name)})')}">🗑️</button>
            </div>
        """
    else:
        actions = f"""
            <div class="package-actions">
                {info_btn}
                <span class="spacer"></span>
            </div>
        """

    cat_html = f'<span title="Category: {html.escape(category)}">{cat_emoji}</span>'
    archive_html = (
        f'<span title="Archive Status: {html.escape(extraction_status)}">{archive_emoji}</span>'
        if is_archive
        else ""
    )

    return f"""
        <div class="{card_class}">
            <div class="package-header">
                <span class="status-emoji">{status_emoji}</span>
                <span class="package-name">{name}</span>
            </div>
            <div class="package-details">
                <span>💾 {size_str}</span>
                {cat_html}
                {archive_html}
            </div>
            {error_html}
            {actions}
        </div>
    """


def _render_packages_content() -> str:
    """Render the packages content div (used for both full page and AJAX refresh)."""
    downloads = get_packages(shared_state)
    queue = downloads.get("queue", [])
    history = downloads.get("history", [])

    kuasarr_queue = [p for p in queue if p.get("cat") != "not_quasarr"]
    other_queue = [p for p in queue if p.get("cat") == "not_quasarr"]
    kuasarr_history = [p for p in history if p.get("category") != "not_quasarr"]
    other_history = [p for p in history if p.get("category") == "not_quasarr"]

    has_kuasarr_content = bool(kuasarr_queue or kuasarr_history)
    has_other_content = bool(other_queue or other_history)
    has_any_content = has_kuasarr_content or has_other_content

    queue_html = ""
    if kuasarr_queue:
        queue_items = "".join(_render_queue_item(item) for item in kuasarr_queue)
        queue_html = f"""
            <div class="section">
                <h3>⬇️ Downloading</h3>
                <div class="packages-list">{queue_items}</div>
            </div>
        """

    history_html = ""
    if kuasarr_history:
        history_items = "".join(
            _render_history_item(item) for item in kuasarr_history[:10]
        )
        history_html = f"""
            <div class="section">
                <h3>📜 Recent History</h3>
                <div class="packages-list">{history_items}</div>
            </div>
        """

    other_html = ""
    other_count = len(other_queue) + len(other_history)
    if other_count > 0:
        other_items = ""
        if other_queue:
            other_items += f"<h4>Queue ({len(other_queue)})</h4>"
            other_items += "".join(_render_queue_item(item) for item in other_queue)
        if other_history:
            other_items += f"<h4>History ({len(other_history)})</h4>"
            other_items += "".join(
                _render_history_item(item) for item in other_history[:5]
            )

        plural = "s" if other_count != 1 else ""
        section_class = (
            "other-packages-section"
            if has_kuasarr_content
            else "other-packages-section no-separator"
        )
        other_html = f"""
            <div class="{section_class}">
                <details id="otherPackagesDetails">
                    <summary id="otherPackagesSummary">Show {other_count} other package{plural}</summary>
                    <div class="other-packages-content">{other_items}</div>
                </details>
            </div>
        """

    empty_html = ""
    if not has_any_content:
        empty_html = '<p class="empty-message">No packages</p>'

    return f"""
        <div class="packages-container">
            {queue_html}
            {history_html}
            {other_html}
            {empty_html}
        </div>
    """


def _render_not_connected_page() -> str:
    back_btn = render_button("Back", "secondary", {"onclick": "location.href='/'"})
    content = f"""
        <h1><img src="{images.logo}" type="image/webp" alt="Kuasarr logo" class="logo"/>kuasarr</h1>
        <h2>Packages</h2>
        <div class="status-bar">
            <span class="status-pill error">
                ❌ JDownloader disconnected
            </span>
        </div>
        <p>Connect JDownloader via the <a href="/">home page</a> to view packages.</p>
        <p>{back_btn}</p>
    """
    return render_centered_html(content)


def setup_packages_routes(app) -> None:
    @app.get("/packages")
    def packages_page():
        device = shared_state.values.get("device")
        if not device:
            return _render_not_connected_page()

        deleted = request.query.get("deleted")
        status_message = ""
        if deleted == "1":
            status_message = (
                '<div class="status-message success">✅ Package deleted successfully.</div>'
            )
        elif deleted == "0":
            status_message = (
                '<div class="status-message error">❌ Failed to delete package.</div>'
            )

        packages_content = _render_packages_content()
        back_btn = render_button("Back", "secondary", {"onclick": "location.href='/'"})

        packages_html = f"""
            <h1><img src="{images.logo}" type="image/webp" alt="Kuasarr logo" class="logo"/>kuasarr</h1>
            <h2>Packages</h2>

            {status_message}

            <div id="slow-warning" class="slow-warning" style="display:none;">⚠️ Slow connection detected</div>

            <div id="packages-content">
                {packages_content}
            </div>

            <p>{back_btn}</p>

            <style>
                .packages-container {{ max-width: 600px; margin: 0 auto; }}
                .section {{ margin: 20px 0; }}
                .section h3 {{ margin-bottom: 15px; padding-bottom: 8px; border-bottom: 1px solid var(--border-color, #ddd); }}
                .packages-list {{ display: flex; flex-direction: column; gap: 10px; }}

                .package-card {{
                    background: var(--card-bg, #f8f9fa);
                    border: 1px solid var(--card-border, #dee2e6);
                    border-radius: 8px;
                    padding: 12px 15px;
                    transition: transform 0.2s, box-shadow 0.2s;
                }}
                .package-card:hover {{ transform: translateY(-1px); box-shadow: 0 2px 8px var(--card-shadow, rgba(0,0,0,0.1)); }}
                .package-card.error {{ border-color: var(--error-border, #dc3545); background: var(--error-bg, #fff5f5); }}

                .package-header {{ display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; }}
                .status-emoji {{ font-size: 1.2em; flex-shrink: 0; }}
                .package-name {{ flex: 1; font-weight: 500; word-break: break-word; line-height: 1.3; }}
                .package-progress {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
                .progress-track {{ flex: 1; height: 8px; background: var(--progress-track, #e0e0e0); border-radius: 4px; overflow: hidden; }}
                .progress-fill {{ height: 100%; background: var(--progress-fill, #4caf50); border-radius: 4px; min-width: 4px; }}
                .progress-waiting {{ flex: 1; color: var(--text-muted, #888); font-style: italic; font-size: 0.85em; }}
                .progress-percent {{ font-weight: bold; min-width: 40px; text-align: right; font-size: 0.9em; }}

                .package-details {{ display: flex; flex-wrap: wrap; gap: 15px; font-size: 0.85em; color: var(--text-muted, #666); }}
                .package-error {{ margin-top: 8px; padding: 8px; background: var(--error-msg-bg, #ffebee); border-radius: 4px; font-size: 0.85em; color: var(--error-msg-color, #c62828); }}

                .package-actions {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-color, #eee); display: flex; gap: 8px; align-items: center; }}
                .package-actions .spacer {{ flex: 1; }}
                .btn-small {{ line-height: 1; padding: 5px 12px; font-size: 0.8em; border-radius: 4px; cursor: pointer; transition: all 0.2s; }}
                .btn-small.primary {{ background: var(--btn-primary-bg, #007bff); color: white; border: none; }}
                .btn-small.primary:hover {{ background: var(--btn-primary-hover, #0056b3); }}
                .btn-small.danger {{ background: transparent; color: var(--btn-danger-text, #dc3545); border: 1px solid var(--btn-danger-border, #dc3545); }}
                .btn-small.danger:hover {{ background: var(--btn-danger-hover-bg, #dc3545); color: white; }}
                .btn-small.info {{ background: transparent; color: var(--btn-info-bg, #17a2b8); border: 1px solid var(--btn-info-bg, #17a2b8); }}
                .btn-small.info:hover {{ background: var(--btn-info-bg, #17a2b8); color: white; }}
                .btn-small.primary-thin {{ background: transparent; color: var(--btn-primary-bg, #007bff); border: 1px solid var(--btn-primary-bg, #007bff); }}
                .btn-small.primary-thin:hover {{ background: var(--btn-primary-bg, #007bff); color: white; }}

                .empty-message {{ color: var(--text-muted, #888); font-style: italic; text-align: center; padding: 20px; }}

                .slow-warning {{
                    text-align: center;
                    font-size: 0.85em;
                    color: #856404;
                    background: #fff3cd;
                    border: 1px solid #ffc107;
                    padding: 8px 12px;
                    border-radius: 6px;
                    margin-bottom: 15px;
                }}
                @media (prefers-color-scheme: dark) {{
                    .slow-warning {{
                        color: #ffc107;
                        background: #3d3510;
                        border-color: #665c00;
                    }}
                }}

                .other-packages-section {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid var(--border-color, #ddd); }}
                .other-packages-section.no-separator {{ margin-top: 0; padding-top: 0; border-top: none; }}
                .other-packages-section summary {{ cursor: pointer; padding: 8px 0; color: var(--text-muted, #666); }}
                .other-packages-section summary:hover {{ color: var(--link-color, #0066cc); }}
                .other-packages-content {{ margin-top: 15px; }}
                .other-packages-content h4 {{ margin: 15px 0 10px 0; font-size: 0.95em; color: var(--text-muted, #666); }}

                .status-message {{
                    padding: 10px 15px;
                    border-radius: 6px;
                    margin-bottom: 15px;
                    font-weight: 500;
                }}
                .status-message.success {{
                    background: var(--success-bg, #d1e7dd);
                    color: var(--success-color, #198754);
                    border: 1px solid var(--success-border, #a3cfbb);
                }}
                .status-message.error {{
                    background: var(--error-bg, #f8d7da);
                    color: var(--error-color, #dc3545);
                    border: 1px solid var(--error-border, #f1aeb5);
                }}

                @media (prefers-color-scheme: dark) {{
                    :root {{
                        --progress-track: #4a5568; --progress-fill: #68d391;
                        --error-msg-bg: #3d2d2d; --error-msg-color: #fc8181;
                        --btn-primary-bg: #3182ce; --btn-primary-hover: #2c5282;
                        --btn-danger-text: #fc8181; --btn-danger-border: #fc8181; --btn-danger-hover-bg: #e53e3e;
                        --btn-info-bg: #38b2ac;
                    }}
                }}
            </style>

            <script>
                let refreshPaused = false;
                let slowConnection = false;
                let refreshTimer = null;
                let isFetching = false;
                const SCROLL_STORAGE_KEY = 'kuasarr_packages_scroll_y';

                function saveScrollPosition() {{
                    sessionStorage.setItem(SCROLL_STORAGE_KEY, String(window.scrollY || 0));
                }}

                function restoreScrollPosition() {{
                    const saved = Number(sessionStorage.getItem(SCROLL_STORAGE_KEY) || '0');
                    if (!Number.isFinite(saved)) return;
                    window.scrollTo(0, saved);
                }}

                async function refreshContent() {{
                    if (refreshPaused || isFetching) return;

                    isFetching = true;
                    const startTime = Date.now();
                    const warningEl = document.getElementById('slow-warning');

                    saveScrollPosition();

                    const slowTimer = setTimeout(() => {{
                        slowConnection = true;
                        if (warningEl) warningEl.style.display = 'block';
                    }}, 5000);

                    try {{
                        const resp = await kuasarrApiFetch('/api/packages/content');
                        const elapsed = Date.now() - startTime;

                        clearTimeout(slowTimer);

                        if (elapsed < 5000) {{
                            slowConnection = false;
                            if (warningEl) warningEl.style.display = 'none';
                        }} else {{
                            slowConnection = true;
                            if (warningEl) warningEl.style.display = 'block';
                        }}

                        if (resp.ok) {{
                            const html = await resp.text();
                            const container = document.getElementById('packages-content');
                            if (container && html) {{
                                container.innerHTML = html;
                                restoreCollapseState();
                                restoreScrollPosition();
                                requestAnimationFrame(restoreScrollPosition);
                            }}
                        }}
                    }} catch (e) {{
                        clearTimeout(slowTimer);
                    }} finally {{
                        isFetching = false;
                    }}

                    if (!refreshPaused) {{
                        if (refreshTimer) clearTimeout(refreshTimer);
                        refreshTimer = setTimeout(refreshContent, 5000);
                    }}
                }}

                function restoreCollapseState() {{
                    const otherDetails = document.getElementById('otherPackagesDetails');
                    const otherSummary = document.getElementById('otherPackagesSummary');
                    if (otherDetails && otherSummary) {{
                        const match = otherSummary.textContent.match(/\\d+/);
                        const count = match ? match[0] : '0';
                        const plural = count !== '1' ? 's' : '';
                        if (localStorage.getItem('otherPackagesOpen') === 'true') {{
                            otherDetails.open = true;
                            otherSummary.textContent = 'Hide ' + count + ' other package' + plural;
                        }}
                        otherDetails.onclick = null;
                        otherDetails.addEventListener('toggle', function () {{
                            localStorage.setItem('otherPackagesOpen', this.open);
                            const summaryEl = document.getElementById('otherPackagesSummary');
                            if (summaryEl) {{
                                summaryEl.textContent = (this.open ? 'Hide ' : 'Show ') + count + ' other package' + plural;
                            }}
                        }});
                    }}
                }}

                restoreCollapseState();
                restoreScrollPosition();
                window.addEventListener('scroll', saveScrollPosition, {{ passive: true }});

                if (window.location.search.includes('deleted=')) {{
                    const url = new URL(window.location);
                    url.searchParams.delete('deleted');
                    window.history.replaceState({{}}, '', url);

                    const statusMsg = document.querySelector('.status-message');
                    if (statusMsg) {{
                        setTimeout(() => {{
                            statusMsg.style.transition = 'opacity 0.3s';
                            statusMsg.style.opacity = '0';
                            setTimeout(() => statusMsg.remove(), 300);
                        }}, 5000);
                    }}

                    setTimeout(refreshContent, 5000);
                }} else {{
                    setTimeout(refreshContent, 5000);
                }}

                // --- Delete modal ---
                let deletePackageId = null;
                let deletePackageName = null;

                function confirmDelete(packageId, packageName) {{
                    if (refreshTimer) clearTimeout(refreshTimer);
                    refreshPaused = true;

                    deletePackageId = packageId;
                    deletePackageName = packageName;

                    const content = `
                        <p class="modal-package-name" style="font-weight: 500; word-break: break-word; padding: 10px; background: var(--code-bg, #f5f5f5); border-radius: 6px; margin: 10px 0;">${{packageName}}</p>
                        <div class="modal-warning" style="background: var(--error-msg-bg, #ffebee); color: var(--error-msg-color, #c62828); padding: 12px; border-radius: 6px; margin: 15px 0; font-size: 0.9em; text-align: left;">
                            <strong>⛔ Warning:</strong> This will permanently delete the package AND all associated files from disk. This action cannot be undone!
                        </div>
                    `;

                    const buttons = `
                        <button class="btn-secondary" onclick="closeModal()">Back</button>
                        <button class="btn-danger" onclick="performDelete()">🗑️ Delete Package &amp; Files</button>
                    `;

                    showModal('🗑️ Delete Package?', content, buttons);
                }}

                function performDelete() {{
                    if (!deletePackageId) return;
                    fetch('/api/packages/delete', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{package_id: deletePackageId}})
                    }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
                        if (data.success) {{
                            closeModal();
                            showStatusMessage('Package deleted', 'success');
                            refreshContent();
                        }} else {{
                            showStatusMessage('Delete failed: ' + (data.error || 'Unknown'), 'error');
                        }}
                    }}).catch(function(e) {{
                        showStatusMessage('Delete failed: ' + e, 'error');
                    }});
                }}

                // --- Info modal ---
                function showPackageDetails(id, name, category, isArchive, extractionStatus, eta, size, percentage, status, storage, isCaptcha) {{
                    if (refreshTimer) clearTimeout(refreshTimer);
                    refreshPaused = true;

                    let captchaBtn = '';
                    if (isCaptcha) {{
                        captchaBtn = `<button class="btn-small primary-thin" onclick="location.href='/captcha?package_id=${{id}}'">🔓 Solve CAPTCHA</button>`;
                    }}

                    const content = `
                        <div style="text-align: left; padding: 10px;">
                            <p style="margin-bottom: 8px;"><strong>Name:</strong></p>
                            <p style="font-family: monospace; text-align: center; background: var(--code-bg, #eee); padding: 4px; border-radius: 4px; word-break: break-word;">${{name}}</p>
                            ${{storage ? `<p style="margin-bottom: 4px;"><strong>Storage:</strong></p><p style="margin-bottom: 8px; font-family: monospace; text-align: center; background: var(--code-bg, #eee); padding: 4px; border-radius: 4px; word-break: break-all;">${{storage}}</p>` : ''}}
                            <p style="margin-bottom: 4px;"><strong>ID:</strong></p>
                            <p style="margin-bottom: 8px; font-family: monospace; text-align: center; background: var(--code-bg, #eee); padding: 4px; border-radius: 4px;">${{id}}</p>
                            <p style="margin-bottom: 8px;"><strong>Status:</strong> ${{status}}</p>
                            ${{percentage ? `<p style="margin-bottom: 8px;"><strong>Percentage:</strong> ${{percentage}}%</p>` : ''}}
                            ${{size ? `<p style="margin-bottom: 8px;"><strong>Size:</strong> ${{size}}</p>` : ''}}
                            ${{eta ? `<p style="margin-bottom: 8px;"><strong>ETA:</strong> ${{eta}}</p>` : ''}}
                            <p style="margin-bottom: 8px;"><strong>Category:</strong> ${{category}}</p>
                            <p style="margin-bottom: 8px;"><strong>Archive:</strong> ${{isArchive}}</p>
                            ${{extractionStatus ? `<p style="margin-bottom: 8px;"><strong>Extraction Status:</strong> ${{extractionStatus}}</p>` : ''}}
                        </div>
                    `;

                    const buttons = `
                        <button class="btn-secondary" onclick="closeModal()">Back</button>
                        ${{captchaBtn}}
                    `;

                    showModal('ℹ️ Package Details', content, buttons);
                }}

                // --- Pause / Resume ---
                async function pausePackage(packageId) {{
                    try {{
                        await kuasarrApiFetch('/api/packages/pause', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{package_id: packageId}})
                        }});
                    }} catch (e) {{
                        console.error('pausePackage failed:', e);
                    }}
                }}

                async function resumePackage(packageId) {{
                    try {{
                        await kuasarrApiFetch('/api/packages/resume', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{package_id: packageId}})
                        }});
                    }} catch (e) {{
                        console.error('resumePackage failed:', e);
                    }}
                }}

                // Resume refresh when modal closes
                document.addEventListener('DOMContentLoaded', function () {{
                    const baseCloseModal = window.closeModal;
                    window.closeModal = function () {{
                        if (baseCloseModal) baseCloseModal();
                        if (refreshTimer) clearTimeout(refreshTimer);
                        refreshPaused = false;
                        refreshContent();
                    }};
                }});
            </script>
        """

        return render_centered_html(packages_html)

    @app.get("/api/packages/content")
    @require_api_key
    def packages_content_api():
        """AJAX endpoint — returns only the packages content HTML for background refresh."""
        if not is_browser_authenticated():
            response.status = 401
            response.set_header("WWW-Authenticate", 'Basic realm="Kuasarr WebUI"')
            response.content_type = "application/json"
            return '{"error": "Unauthorized"}'
        device = shared_state.values.get("device")
        if not device:
            return """
                <div class="status-bar">
                    <span class="status-pill error">
                        ❌ JDownloader disconnected
                    </span>
                </div>
            """
        return _render_packages_content()

    @app.get("/api/packages")
    @require_api_key
    def packages_json_api():
        """JSON status endpoint."""
        response.content_type = "application/json"
        if not is_browser_authenticated():
            response.status = 401
            response.set_header("WWW-Authenticate", 'Basic realm="Kuasarr WebUI"')
            return '{"error": "Unauthorized"}'
        device = shared_state.values.get("device")
        if not device:
            return json.dumps({"connected": False, "queue": [], "history": []})

        downloads = get_packages(shared_state)
        return json.dumps({
            "connected": True,
            "queue": downloads.get("queue", []),
            "history": downloads.get("history", []),
        })

    @app.post("/api/packages/delete")
    @require_api_key
    def packages_delete():
        """Delete a package by ID. POST replaces the old GET route to prevent CSRF."""
        response.content_type = "application/json"
        if not is_browser_authenticated():
            response.status = 401
            response.set_header("WWW-Authenticate", 'Basic realm="Kuasarr WebUI"')
            return '{"error": "Unauthorized"}'
        device = shared_state.values.get("device")
        if not device:
            return json.dumps({"success": False, "error": "Not connected"})

        try:
            data = json.loads(request.body.read().decode("utf-8"))
            package_id = data.get("package_id")
        except (ValueError, UnicodeDecodeError) as exc:
            logger.debug("delete: invalid JSON body — %s", exc)
            return json.dumps({"success": False, "error": "Invalid JSON"})

        if not package_id:
            return json.dumps({"success": False, "error": "Missing package_id"})

        try:
            success = delete_package(shared_state, package_id)
            return json.dumps({"success": success})
        except Exception as exc:
            logger.debug("delete failed: %s", exc)
            return json.dumps({"success": False, "error": str(exc)})

    @app.post("/api/packages/pause")
    @require_api_key
    def packages_pause():
        """Pause a specific package or the global download controller."""
        response.content_type = "application/json"
        if not is_browser_authenticated():
            response.status = 401
            response.set_header("WWW-Authenticate", 'Basic realm="Kuasarr WebUI"')
            return '{"error": "Unauthorized"}'
        device = shared_state.values.get("device")
        if not device:
            return json.dumps({"success": False, "error": "Not connected"})

        try:
            data = json.loads(request.body.read().decode("utf-8"))
            package_id = data.get("package_id")
        except (ValueError, UnicodeDecodeError) as exc:
            logger.debug("pause: invalid JSON body — %s", exc)
            return json.dumps({"success": False, "error": "Invalid JSON"})

        try:
            if package_id:
                device.downloads.set_enabled(package_ids=[package_id], enabled=False)
            else:
                device.downloadcontroller.set_pause(True)
        except Exception as exc:
            logger.debug("pause failed: %s", exc)
            return json.dumps({"success": False, "error": str(exc)})

        return json.dumps({"success": True})

    @app.post("/api/packages/resume")
    @require_api_key
    def packages_resume():
        """Resume a specific package or the global download controller."""
        response.content_type = "application/json"
        if not is_browser_authenticated():
            response.status = 401
            response.set_header("WWW-Authenticate", 'Basic realm="Kuasarr WebUI"')
            return '{"error": "Unauthorized"}'
        device = shared_state.values.get("device")
        if not device:
            return json.dumps({"success": False, "error": "Not connected"})

        try:
            data = json.loads(request.body.read().decode("utf-8"))
            package_id = data.get("package_id")
        except (ValueError, UnicodeDecodeError) as exc:
            logger.debug("resume: invalid JSON body — %s", exc)
            return json.dumps({"success": False, "error": "Invalid JSON"})

        try:
            if package_id:
                device.downloads.set_enabled(package_ids=[package_id], enabled=True)
            else:
                device.downloadcontroller.set_pause(False)
        except Exception as exc:
            logger.debug("resume failed: %s", exc)
            return json.dumps({"success": False, "error": str(exc)})

        return json.dumps({"success": True})
