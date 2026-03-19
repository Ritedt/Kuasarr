# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

from __future__ import annotations

import json
from base64 import urlsafe_b64decode
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

from bottle import Bottle, HTTPError, request, response

from kuasarr.downloads import download
from kuasarr.downloads.packages import get_packages
from kuasarr.providers import shared_state
from kuasarr.providers.ui.html_templates import render_centered_html, render_button
from kuasarr.providers.log import debug, info
from kuasarr.search import get_search_results


def setup_search_routes(app: Bottle) -> None:
    def _json(payload: Any) -> Any:
        response.content_type = "application/json"
        return payload

    def _format_size(size_bytes: Optional[int]) -> Dict[str, Optional[str]]:
        if size_bytes is None:
            return {"bytes": None, "formatted": "Unbekannt"}

        try:
            size_bytes = int(size_bytes)
        except (TypeError, ValueError):
            return {"bytes": None, "formatted": "Unbekannt"}

        units = ["Bytes", "KB", "MB", "GB", "TB"]
        value = float(size_bytes)
        unit_index = 0
        while value >= 1024 and unit_index < len(units) - 1:
            value /= 1024
            unit_index += 1

        if unit_index == 0:
            formatted = f"{int(value)} {units[unit_index]}"
        else:
            formatted = f"{value:.1f} {units[unit_index]}"

        return {"bytes": size_bytes, "formatted": formatted}

    def _parse_date(raw: Optional[str]) -> Dict[str, Optional[str]]:
        if not raw:
            return {"iso": None, "label": "Unbekannt"}

        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=None)
        except Exception:
            try:
                dt = datetime.fromisoformat(raw)
            except Exception:
                return {"iso": None, "label": raw}

        iso_value = dt.strftime("%Y-%m-%d")
        label = dt.strftime("%d.%m.%Y %H:%M")
        return {"iso": iso_value, "label": label}

    def _decode_payload(link: str) -> Optional[Dict[str, Optional[str]]]:
        if not link:
            return None
        try:
            parsed = urlparse(link)
            payload = parse_qs(parsed.query).get("payload", [None])[0]
            if not payload:
                return None
            decoded = urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
            parts = decoded.split("|")
            if len(parts) != 6:
                return None
            title, url, mirror, size_str, password, imdb_id = parts
            size_mb = None
            try:
                size_mb = float(size_str)
            except (TypeError, ValueError):
                size_mb = None
            size_bytes = int(size_mb * 1024 * 1024) if size_mb else None
            return {
                "title": title,
                "url": url,
                "mirror": mirror if mirror and mirror.lower() != "none" else None,
                "size_bytes": size_bytes,
                "password": password if password and password.lower() != "none" else "",
                "imdb_id": imdb_id or None,
            }
        except Exception:
            debug("Fehler beim Dekodieren des Download-Payloads")
            return None

    def _normalise_result(raw: Dict[str, Any]) -> Dict[str, Any]:
        details = raw.get("details") or {}
        decoded = _decode_payload(details.get("link"))

        title = details.get("title") or (decoded.get("title") if decoded else "Unbekannt")
        hostname = (details.get("hostname") or "").upper()
        mirror = details.get("mirror") or (decoded.get("mirror") if decoded else None)
        size_bytes = details.get("size")
        if size_bytes is None and decoded and decoded.get("size_bytes"):
            size_bytes = decoded["size_bytes"]

        date_info = _parse_date(details.get("date"))
        size_info = _format_size(size_bytes)

        source = details.get("source") or (decoded.get("url") if decoded else "")

        return {
            "title": title,
            "hostname": hostname,
            "mirror": mirror,
            "size": size_info,
            "date": date_info,
            "link": details.get("link"),
            "source": source,
            "imdb_id": details.get("imdb_id") or (decoded.get("imdb_id") if decoded else None),
            "password": decoded.get("password") if decoded else "",
        }

    def _collect_filters(results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        hosters = sorted({item.get("hostname") for item in results if item.get("hostname")})
        mirrors = sorted({(item.get("mirror") or "").lower() for item in results if item.get("mirror")})

        dates = [item.get("date", {}).get("iso") for item in results if item.get("date", {}).get("iso")]
        if dates:
            dates_sorted = sorted(dates)
            date_range = {"min": dates_sorted[0], "max": dates_sorted[-1]}
        else:
            date_range = {"min": None, "max": None}

        return {"hostnames": hosters, "mirrors": mirrors, "date": date_range}

    def _parse_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        items_raw = payload.get("items")
        if not isinstance(items_raw, list) or not items_raw:
            raise HTTPError(400, "Mindestens ein Eintrag muss ausgewählt werden")

        parsed_items = []
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            link = item.get("link")
            if not link:
                continue
            decoded = _decode_payload(link)
            if not decoded:
                continue
            parsed_items.append({
                "title": item.get("title") or decoded.get("title") or "Unbekannt",
                "link": link,
                "decoded": decoded,
            })

        if not parsed_items:
            raise HTTPError(400, "Die ausgewählten Einträge konnten nicht verarbeitet werden")

        return parsed_items

    def _download_item(item: Dict[str, Any]) -> Dict[str, Any]:
        decoded = item["decoded"]
        title = item.get("title")
        url = decoded.get("url")
        mirror = decoded.get("mirror")
        imdb_id = decoded.get("imdb_id")

        size_bytes = decoded.get("size_bytes")
        size_mb = str(int(size_bytes / (1024 * 1024))) if size_bytes else "0"

        result = download(
            shared_state,
            "WebUI",
            title,
            url,
            mirror,
            size_mb,
            decoded.get("password") or "",
            imdb_id=imdb_id,
        )

        package_id = result.get("package_id")
        captcha_pending = False
        if package_id:
            try:
                entry = shared_state.get_db("protected").retrieve(package_id)
                captcha_pending = bool(entry)
            except Exception:
                captcha_pending = False

        return {
            "title": result.get("title", title),
            "package_id": package_id,
            "success": bool(result.get("success")),
            "captcha_required": captcha_pending,
        }

    def _collect_status() -> Dict[str, Any]:
        packages = get_packages(shared_state)

        queue_items = [
            {
                "id": item.get("nzo_id"),
                "name": item.get("filename"),
                "status": item.get("status"),
                "progress": item.get("percentage"),
                "category": item.get("cat"),
                "type": item.get("type"),
                "timeleft": item.get("timeleft"),
            }
            for item in packages.get("queue", [])
        ]

        history_items = [
            {
                "id": item.get("nzo_id"),
                "name": item.get("name"),
                "status": item.get("status"),
                "storage": item.get("storage"),
                "category": item.get("category"),
                "fail_message": item.get("fail_message"),
            }
            for item in packages.get("history", [])
        ]

        captcha_list: List[Dict[str, Any]] = []
        try:
            pending = shared_state.get_db("protected").retrieve_all_titles()
            for package_id, blob in pending:
                title = "Unbekannt"
                try:
                    data = json.loads(blob)
                    if isinstance(data, str):
                        data = json.loads(data)
                    title = data.get("title", title)
                except Exception:
                    pass
                captcha_list.append({"package_id": package_id, "title": title})
        except Exception:
            pass

        return {
            "queue": queue_items,
            "history": history_items,
            "captcha": captcha_list,
        }

    @app.get('/search')
    def search_page() -> str:
        info("WebUI-Suche geöffnet")

        refresh_button = render_button("Status aktualisieren", "secondary", {"id": "statusRefresh"})
        search_button = render_button("Suchen", "primary", {"type": "button", "id": "searchSubmit"})
        back_button = render_button("Zurück", "secondary", {"type": "button", "onclick": "location.href='/'"})
        download_button = render_button("Auswahl herunterladen", "primary", {"id": "downloadSelected", "disabled": "true"})

        content = """
        <h1><img src="{images.logo}" type="image/png" alt="kuasarr logo" class="logo"/>kuasarr</h1>
        <h2>🔍 Manuelle Suche</h2>

        <div class="tabs">
            <button class="tab-btn active" data-tab="search">Suche</button>
            <button class="tab-btn" data-tab="status">Status</button>
        </div>

        <div id="tab-search" class="tab-panel active">
            <form id="searchForm" class="search-form" onsubmit="return false;">
                <label for="searchInput">Suchbegriff</label>
                <input id="searchInput" type="text" placeholder="Titel, Schauspieler, Stichwort" required>
                <div class="search-actions">
                    __SEARCH_BUTTON__
                    __BACK_BUTTON__
                </div>
            </form>

            <div id="filterSection" class="section filters" hidden>
                <h3>Filter</h3>
                <div class="filter-group">
                    <span>Portale:</span>
                    <div id="filterHostnames" class="chip-list"></div>
                </div>
                <div class="filter-group">
                    <span>Mirror:</span>
                    <div id="filterMirrors" class="chip-list"></div>
                </div>
                <div class="filter-group">
                    <span>Datum:</span>
                    <label>von <input type="date" id="filterDateStart"></label>
                    <label>bis <input type="date" id="filterDateEnd"></label>
                </div>
            </div>

            <div class="section">
                <div class="result-actions">
                    __DOWNLOAD_BUTTON__
                </div>
                <div id="searchMessage" class="message" hidden></div>
                <div id="resultsContainer" class="results"></div>
            </div>
        </div>

        <div id="tab-status" class="tab-panel">
            <div class="status-header">
                __REFRESH_BUTTON__
            </div>
            <div id="statusMessage" class="message" hidden></div>
            <div class="status-grid">
                <div>
                    <h3>Aktive Downloads</h3>
                    <ul id="statusQueue" class="status-list"></ul>
                </div>
                <div>
                    <h3>CAPTCHA erforderlich</h3>
                    <ul id="statusCaptcha" class="status-list"></ul>
                </div>
                <div>
                    <h3>Verlauf</h3>
                    <ul id="statusHistory" class="status-list"></ul>
                </div>
            </div>
        </div>

        <style>
            .tabs { display: flex; gap: 0.5rem; justify-content: center; margin: 1rem 0; }
            .tab-btn {
                background-color: rgba(13, 110, 253, 0.12);
                color: #0d6efd;
                border-radius: 999px;
                padding: 0.4rem 1.2rem;
                border: none;
                cursor: pointer;
                font-weight: 600;
            }
            .tab-btn.active { background-color: #0d6efd; color: #fff; }
            .tab-panel { display: none; text-align: left; }
            .tab-panel.active { display: block; }
            .search-form { text-align: left; }
            .search-form input[type="text"] { margin-bottom: 1rem; }
            .search-actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }
            .filters { text-align: left; }
            .filter-group { margin: 0.75rem 0; display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
            .chip-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
            .chip { padding: 0.3rem 0.8rem; border-radius: 999px; border: 1px solid rgba(13,110,253,0.4); cursor: pointer; font-size: 0.9rem; }
            .chip.active { background-color: #0d6efd; color: #fff; }
            .results { margin-top: 1rem; display: grid; gap: 1rem; }
            .result-card { border: 1px solid rgba(0,0,0,0.1); border-radius: 0.75rem; padding: 1rem; background: var(--card-bg); box-shadow: 0 0.5rem 1rem var(--card-shadow);
                           transition: transform 0.2s ease; }
            .result-card:hover { transform: translateY(-2px); }
            .result-header { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
            .result-meta { margin-top: 0.5rem; display: flex; gap: 0.75rem; flex-wrap: wrap; font-size: 0.9rem; color: rgba(0,0,0,0.65); }
            body.dark .result-meta { color: rgba(255,255,255,0.7); }
            .result-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.75rem; }
            .badge { padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.8rem; background-color: rgba(13,110,253,0.15); color: #0d6efd; font-weight: 600; }
            .message { margin-top: 1rem; padding: 0.75rem 1rem; border-radius: 0.5rem; background-color: rgba(13,110,253,0.1); color: #0d6efd; font-weight: 500; white-space: pre-wrap; }
            .message.error { background-color: rgba(220,53,69,0.1); color: #c12c3e; }
            .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; text-align: left; }
            .status-header { display: flex; justify-content: flex-end; margin-bottom: 1rem; }
            .status-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.75rem; }
            .status-item { border: 1px solid rgba(0,0,0,0.1); border-radius: 0.75rem; padding: 0.75rem; background: var(--card-bg); }
            .status-item strong { display: block; margin-bottom: 0.25rem; }
            .status-progress { font-size: 0.85rem; color: rgba(0,0,0,0.65); }
            @media (max-width: 600px) {
                .search-actions, .result-actions { justify-content: center; }
                .result-meta { flex-direction: column; align-items: flex-start; }
            }
        </style>

        <script>
        (() => {
            console.log('[SearchUI] Skript initialisiert');
            const state = {
                results: [],
                filtered: [],
                selected: new Map(),
                filters: { hostnames: [], mirrors: [], date: { min: null, max: null } }
            };

            const dom = {
                form: document.getElementById('searchForm'),
                input: document.getElementById('searchInput'),
                submitButton: document.getElementById('searchSubmit'),
                message: document.getElementById('searchMessage'),
                filterSection: document.getElementById('filterSection'),
                filterHostnames: document.getElementById('filterHostnames'),
                filterMirrors: document.getElementById('filterMirrors'),
                filterDateStart: document.getElementById('filterDateStart'),
                filterDateEnd: document.getElementById('filterDateEnd'),
                downloadSelected: document.getElementById('downloadSelected'),
                resultsContainer: document.getElementById('resultsContainer'),
                statusRefresh: document.getElementById('statusRefresh'),
                statusMessage: document.getElementById('statusMessage'),
                statusQueue: document.getElementById('statusQueue'),
                statusHistory: document.getElementById('statusHistory'),
                statusCaptcha: document.getElementById('statusCaptcha'),
            };

            console.log('[SearchUI] DOM Elemente', {
                form: !!dom.form,
                input: !!dom.input,
                submitButton: !!dom.submitButton,
                message: !!dom.message,
                resultsContainer: !!dom.resultsContainer
            });

            function setMessage(element, text, isError = false) {
                if (!element) return;
                if (!text) {
                    element.hidden = true;
                    element.textContent = '';
                    element.classList.remove('error');
                    return;
                }
                element.textContent = text;
                element.hidden = false;
                element.classList.toggle('error', isError);
            }

            function renderFilters() {
                const { hostnames, mirrors, date } = state.filters;
                if (!dom.filterHostnames || !dom.filterMirrors || !dom.filterDateStart || !dom.filterDateEnd) {
                    console.warn('[SearchUI] Filter-Elemente nicht gefunden');
                    return;
                }
                dom.filterHostnames.innerHTML = '';
                dom.filterMirrors.innerHTML = '';

                hostnames.forEach(host => {
                    const chip = document.createElement('button');
                    chip.type = 'button';
                    chip.className = 'chip';
                    chip.textContent = host;
                    chip.dataset.value = host;
                    chip.addEventListener('click', () => {
                        chip.classList.toggle('active');
                        applyFilters();
                    });
                    dom.filterHostnames.appendChild(chip);
                });

                mirrors.forEach(mirror => {
                    const chip = document.createElement('button');
                    chip.type = 'button';
                    chip.className = 'chip';
                    chip.textContent = mirror;
                    chip.dataset.value = mirror;
                    chip.addEventListener('click', () => {
                        chip.classList.toggle('active');
                        applyFilters();
                    });
                    dom.filterMirrors.appendChild(chip);
                });

                dom.filterDateStart.value = date.min || '';
                dom.filterDateEnd.value = date.max || '';
                dom.filterDateStart.onchange = applyFilters;
                dom.filterDateEnd.onchange = applyFilters;

                dom.filterSection.hidden = !(hostnames.length || mirrors.length || date.min || date.max);
            }

            function applyFilters() {
                if (!dom.filterHostnames || !dom.filterMirrors || !dom.filterDateStart || !dom.filterDateEnd) {
                    return;
                }
                const selectedHosts = Array.from(dom.filterHostnames.querySelectorAll('.chip.active')).map(el => el.dataset.value);
                const selectedMirrors = Array.from(dom.filterMirrors.querySelectorAll('.chip.active')).map(el => el.dataset.value);
                const dateStart = dom.filterDateStart.value ? new Date(dom.filterDateStart.value) : null;
                const dateEnd = dom.filterDateEnd.value ? new Date(dom.filterDateEnd.value) : null;

                state.filtered = state.results.filter(item => {
                    if (selectedHosts.length && !selectedHosts.includes(item.hostname)) {
                        return false;
                    }
                    if (selectedMirrors.length) {
                        const mirrorValue = (item.mirror || '').toLowerCase();
                        if (!mirrorValue || !selectedMirrors.includes(mirrorValue)) {
                            return false;
                        }
                    }
                    if (dateStart || dateEnd) {
                        const iso = item.date && item.date.iso ? new Date(item.date.iso) : null;
                        if (!iso) {
                            return false;
                        }
                        if (dateStart && iso < dateStart) {
                            return false;
                        }
                        if (dateEnd && iso > dateEnd) {
                            return false;
                        }
                    }
                    return true;
                });

                renderResults();
            }

            function renderResults() {
                if (!dom.resultsContainer) {
                    console.warn('[SearchUI] Results-Container nicht gefunden');
                    return;
                }
                dom.resultsContainer.innerHTML = '';
                state.selected.forEach((_, key) => {
                    if (!state.results.find(item => item.link === key)) {
                        state.selected.delete(key);
                    }
                });

                const list = state.filtered.length ? state.filtered : state.results;

                list.forEach(item => {
                    const card = document.createElement('div');
                    card.className = 'result-card';

                    const header = document.createElement('div');
                    header.className = 'result-header';

                    const infoBox = document.createElement('div');
                    const titleEl = document.createElement('strong');
                    titleEl.textContent = String(item.title || '');
                    infoBox.appendChild(titleEl);
                    header.appendChild(infoBox);

                    if (item.hostname) {
                        const badge = document.createElement('span');
                        badge.className = 'badge';
                        badge.textContent = String(item.hostname);
                        header.appendChild(badge);
                    }

                    const checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.checked = state.selected.has(item.link);
                    checkbox.addEventListener('change', () => {
                        if (checkbox.checked) {
                            state.selected.set(item.link, item);
                        } else {
                            state.selected.delete(item.link);
                        }
                        updateSelectionState();
                    });
                    header.insertBefore(checkbox, header.firstChild);

                    const meta = document.createElement('div');
                    meta.className = 'result-meta';
                    
                    const mirrorSpan = document.createElement('span');
                    mirrorSpan.textContent = 'Mirror: ' + String(item.mirror || 'Unbekannt');
                    meta.appendChild(mirrorSpan);
                    
                    const sizeSpan = document.createElement('span');
                    sizeSpan.textContent = 'Größe: ' + String(item.size && item.size.formatted ? item.size.formatted : 'Unbekannt');
                    meta.appendChild(sizeSpan);
                    
                    const dateSpan = document.createElement('span');
                    dateSpan.textContent = 'Datum: ' + String(item.date && item.date.label ? item.date.label : 'Unbekannt');
                    meta.appendChild(dateSpan);

                    const actions = document.createElement('div');
                    actions.className = 'result-actions';

                    const downloadBtn = document.createElement('button');
                    downloadBtn.className = 'btn-primary small';
                    downloadBtn.textContent = 'Sofort laden';
                    downloadBtn.addEventListener('click', async () => {
                        await performDownload([item]);
                    });

                    const sourceLink = document.createElement('a');
                    sourceLink.className = 'btn-secondary small';
                    sourceLink.textContent = 'Quelle öffnen';
                    sourceLink.href = String(item.source || '#');
                    sourceLink.target = '_blank';
                    sourceLink.rel = 'noopener noreferrer';

                    actions.appendChild(downloadBtn);
                    if (item.source && String(item.source)) {
                        actions.appendChild(sourceLink);
                    }

                    card.appendChild(header);
                    card.appendChild(meta);
                    card.appendChild(actions);

                    dom.resultsContainer.appendChild(card);
                });

                if (!dom.resultsContainer.children.length) {
                    const empty = document.createElement('div');
                    empty.className = 'message';
                    empty.textContent = 'Keine Ergebnisse vorhanden.';
                    dom.resultsContainer.appendChild(empty);
                }

                updateSelectionState();
            }

            function updateSelectionState() {
                const disabled = state.selected.size === 0;
                if (dom.downloadSelected) {
                    dom.downloadSelected.disabled = disabled;
                }
            }

            async function performSearch(query) {
                setMessage(dom.message, 'Suche läuft...');
                if (dom.resultsContainer) {
                    dom.resultsContainer.innerHTML = '';
                }
                if (dom.downloadSelected) {
                    dom.downloadSelected.disabled = true;
                }
                state.selected.clear();

                console.log('[SearchUI] performSearch', { query });

                try {
                    const res = await fetch('/api/search', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ query })
                    });

                    if (!res.ok) {
                        const errorText = await res.text();
                        throw new Error(errorText || 'Suche fehlgeschlagen');
                    }

                    const data = await res.json();
                    console.log('[SearchUI] Suchantwort erhalten', data);
                    state.results = Array.isArray(data.results) ? data.results : [];
                    state.filtered = state.results;
                    state.filters = data.filters || state.filters;

                    renderFilters();
                    renderResults();

                    setMessage(dom.message, state.results.length + ' Ergebnisse gefunden.');
                } catch (error) {
                    console.error('[SearchUI] Fehler bei performSearch', error);
                    setMessage(dom.message, error.message || 'Fehler bei der Suche.', true);
                }
            }

            async function performDownload(items) {
                if (!items || !items.length) {
                    return;
                }
                setMessage(dom.message, 'Download wird gestartet...');
                console.log('[SearchUI] performDownload', items);
                try {
                    const res = await fetch('/api/search/download', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ items: items.map(item => ({ link: item.link, title: item.title })) })
                    });
                    if (!res.ok) {
                        const text = await res.text();
                        throw new Error(text || 'Download fehlgeschlagen');
                    }
                    const data = await res.json();
                    console.log('[SearchUI] Downloadantwort', data);
                    const messages = data.results.map(entry => {
                        if (entry.captcha_required) {
                            return '⚠️ ' + String(entry.title || '') + ': CAPTCHA erforderlich.';
                        }
                        if (entry.success) {
                            return '✅ ' + String(entry.title || '') + ': Gestartet.';
                        }
                        return '❌ ' + String(entry.title || '') + ': Fehlgeschlagen.';
                    });
                    setMessage(dom.message, messages.join('\\n'));
                    await loadStatus();
                } catch (error) {
                    console.error(error);
                    setMessage(dom.message, error.message || 'Fehler beim Starten der Downloads.', true);
                }
            }

            async function loadStatus() {
                setMessage(dom.statusMessage, 'Lade Status...');
                console.log('[SearchUI] loadStatus ausgelöst');
                try {
                    const res = await fetch('/api/search/status');
                    if (!res.ok) {
                        throw new Error(await res.text());
                    }
                    const data = await res.json();
                    console.log('[SearchUI] Statusantwort', data);

                    renderStatusList(dom.statusQueue, data.queue, item => {
                        const progress = typeof item.progress === 'number' ? String(item.progress) + '%' : '–';
                        const name = document.createElement('strong');
                        name.textContent = String(item.name || 'Unbekannt');
                        const progressDiv = document.createElement('div');
                        progressDiv.className = 'status-progress';
                        progressDiv.textContent = String(item.status || '') + ' • ' + progress + ' • ' + String(item.timeleft || '');
                        return { name, progressDiv };
                    });

                    renderStatusList(dom.statusHistory, data.history, item => {
                        const suffix = item.fail_message ? '⚠️ ' + String(item.fail_message) : '✅ Fertig';
                        const name = document.createElement('strong');
                        name.textContent = String(item.name || 'Unbekannt');
                        const progressDiv = document.createElement('div');
                        progressDiv.className = 'status-progress';
                        progressDiv.textContent = suffix;
                        return { name, progressDiv };
                    });

                    renderStatusList(dom.statusCaptcha, data.captcha, item => {
                        const name = document.createElement('strong');
                        name.textContent = String(item.title || 'Unbekannt');
                        const progressDiv = document.createElement('div');
                        progressDiv.className = 'status-progress';
                        progressDiv.textContent = 'ID: ' + String(item.package_id || '');
                        return { name, progressDiv };
                    });

                    if (data.captcha && data.captcha.length) {
                        setMessage(dom.statusMessage, 'Es warten ' + data.captcha.length + ' Pakete auf die CAPTCHA-Lösung.');
                    } else {
                        setMessage(dom.statusMessage, 'Status aktualisiert.');
                    }
                } catch (error) {
                    console.error(error);
                    setMessage(dom.statusMessage, error.message || 'Status konnte nicht geladen werden.', true);
                }
            }

            function renderStatusList(container, items, template) {
                if (!container) {
                    console.warn('[SearchUI] Container fÃ¼r Status-Liste nicht gefunden');
                    return;
                }
                container.innerHTML = '';
                if (!items || !items.length) {
                    const li = document.createElement('li');
                    li.className = 'status-item';
                    li.textContent = 'Keine EintrÃ¤ge.';
                    container.appendChild(li);
                    return;
                }
                items.forEach(item => {
                    const li = document.createElement('li');
                    li.className = 'status-item';
                    const templateResult = template(item);
                    if (templateResult && templateResult.name) {
                        li.appendChild(templateResult.name);
                        if (templateResult.progressDiv) {
                            li.appendChild(templateResult.progressDiv);
                        }
                    } else {
                        li.textContent = 'Unbekannt';
                    }
                    container.appendChild(li);
                });
            }

            function triggerSearch() {
                const query = dom.input ? dom.input.value.trim() : '';
                console.log('[SearchUI] triggerSearch', { hasInput: !!dom.input, query });
                if (!query) {
                    setMessage(dom.message, 'Bitte einen Suchbegriff eingeben.', true);
                    return;
                }
                performSearch(query);
            }

            if (dom.form) {
                dom.form.addEventListener('submit', event => {
                    event.preventDefault();
                    console.log('[SearchUI] Formular-Submit abgefangen');
                    triggerSearch();
                });
            } else {
                console.warn('[SearchUI] Formular nicht gefunden â€“ Submit-Handler nicht aktiviert');
            }

            if (dom.submitButton) {
                console.log('[SearchUI] Submit-Button gefunden, Listener wird gesetzt');
                dom.submitButton.addEventListener('click', () => {
                    console.log('[SearchUI] Suchbutton geklickt');
                    triggerSearch();
                });
            } else {
                console.warn('[SearchUI] Submit-Button nicht gefunden');
            }

            if (dom.input) {
                dom.input.addEventListener('keydown', event => {
                    if (event.key === 'Enter') {
                        event.preventDefault();
                        console.log('[SearchUI] Enter-Key ausgelÃ¶st');
                        triggerSearch();
                    }
                });
            } else {
                console.warn('[SearchUI] Input-Feld nicht gefunden');
            }

            if (dom.downloadSelected) {
                dom.downloadSelected.addEventListener('click', async () => {
                    const items = Array.from(state.selected.values());
                    await performDownload(items);
                });
            } else {
                console.warn('[SearchUI] Download-Button nicht gefunden');
            }

            document.querySelectorAll('.tab-btn').forEach(button => {
                button.addEventListener('click', () => {
                    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                    document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
                    button.classList.add('active');
                    const target = document.getElementById('tab-' + button.dataset.tab);
                    if (target) {
                        target.classList.add('active');
                    }
                });
            });

            if (dom.statusRefresh) {
                dom.statusRefresh.addEventListener('click', loadStatus);
            } else {
                console.warn('[SearchUI] Status-Refresh-Button nicht gefunden');
            }

            // Vorab Status laden, damit der Tab gefÃ¼llt ist
            loadStatus();
        })();
        </script>
        """

        from kuasarr.providers.ui import html_images as images  # lazy import um Zyklus zu vermeiden
        content = (content
                   .replace("{images.logo}", images.logo)
                   .replace("__REFRESH_BUTTON__", refresh_button)
                   .replace("__SEARCH_BUTTON__", search_button)
                   .replace("__BACK_BUTTON__", back_button)
                   .replace("__DOWNLOAD_BUTTON__", download_button)
                   )
        return render_centered_html(content)

    @app.post('/api/search')
    def search_api() -> Dict[str, Any]:
        payload = request.json or {}
        query = str(payload.get("query", "")).strip()

        if not query:
            raise HTTPError(400, "Suchbegriff fehlt")

        info(f"WebUI-Suche gestartet: '{query}'")

        results_raw = get_search_results(
            shared_state,
            "WebUI",
            search_phrase=query,
            mirror=payload.get("mirror"),
        )

        normalised = [_normalise_result(entry) for entry in results_raw]
        filters = _collect_filters(normalised)

        return _json({
            "results": normalised,
            "filters": filters,
        })

    @app.post('/api/search/download')
    def search_download_api() -> Dict[str, Any]:
        payload = request.json or {}
        items = _parse_items(payload)

        info(f"WebUI-Downloadauftrag: {len(items)} Elemente")

        results = [_download_item(item) for item in items]

        return _json({
            "results": results,
        })

    @app.get('/api/search/status')
    def search_status_api() -> Dict[str, Any]:
        return _json(_collect_status())


__all__ = ["setup_search_routes"]





