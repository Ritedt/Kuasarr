# Sprint 5 — WebUI: Packages-UI

**Version:** Kuasarr v1.14.0
**Stand:** 2026-03-20
**Status:** Bereit zur Implementierung

---

## 1. Executive Summary

Sprint 5 bringt eine vollwertige Download-Monitoring-UI in den Browser. JDownloader-Pakete
(Linkgrabber, aktive Downloads, History, CAPTCHA-Queue, "protected"-DB, "failed"-DB) werden
auf einer eigenen Seite `/packages` angezeigt. Die Liste aktualisiert sich im Hintergrund
automatisch via AJAX.

**Was wird gebaut:**
- `GET /packages` — dedizierte HTML-Seite mit Paketliste
- `GET /api/packages/content` — AJAX-Endpunkt für Hintergrund-Refresh
- `GET /api/packages` — JSON-Endpunkt für maschinenlesbare Daten
- `GET /packages/delete/<package_id>` — Löschen via URL-Redirect
- `POST /api/packages/pause` — Pause einzelner Pakete (via myjd_api.py Erweiterung)
- `POST /api/packages/resume` — Resume einzelner Pakete (via myjd_api.py Erweiterung)
- Neues Modul `kuasarr/api/packages/__init__.py`
- Quick-Action-Button auf der Startseite
- **Nebenbefund-Fix:** `setup_search_routes()` registrieren (war bisher nicht eingebunden)

---

## 2. Architektur-Überblick

```
kuasarr/
├── api/
│   ├── __init__.py              ← +3 Zeilen: imports + Aufrufe
│   ├── packages/
│   │   └── __init__.py          ← NEU: alle Package-Routen
│   └── search.py                ← wird endlich registriert
├── providers/
│   ├── myjd_api.py              ← +2 Methoden: set_enabled() + set_pause()
│   └── ui/
│       └── html_templates.py    ← UNVERÄNDERT (bereits vorhandene Helpers)
```

---

## 3. Task-Liste

### Task 1 — myjd_api.py Erweitern (Pause/Resume)

**Datei:** `kuasarr/providers/myjd_api.py`
**Abhängigkeiten:** keine

**Neue Methoden in `Downloads` Klasse:**
```python
def set_enabled(self, link_ids=None, package_ids=None, enabled=True):
    """Enable/disable links and packages."""
    params = [enabled]
    if link_ids:
        params.append(link_ids)
    else:
        params.append([])
    if package_ids:
        params.append(package_ids)
    else:
        params.append([])
    return self.device.action(f"/{self.path}/setEnabled", params)

def set_pause(self, paused=True):
    """Pause/unpause all downloads."""
    return self.device.action(f"/{self.path}/setPause", [paused])
```

### Task 2 — Neues Modul `kuasarr/api/packages/__init__.py`

**Datei:** `kuasarr/api/packages/__init__.py` (NEU)
**Abhängigkeiten:** Task 1

**Funktionen zu implementieren:**
- `_format_size(mb=None, bytes_val=None)` — Größenformatierung
- `_escape_js(s)` — JavaScript-Escaping
- `_get_category_emoji(cat)` — Emoji-Lookup für Kategorien
- `_render_queue_item(item)` — Einzelnes Queue-Element rendern
- `_render_history_item(item)` — Einzelnes History-Element rendern
- `_render_packages_content()` — Haupt-HTML-Fragment
- `_render_not_connected_page()` — JD-Disconnect-Hinweis
- `setup_packages_routes(app)` — Alle Routen registrieren

**Routen:**
- `GET /packages` — Hauptseite
- `GET /api/packages/content` — AJAX-HTML-Fragment
- `GET /api/packages` — JSON-API
- `GET /packages/delete/<package_id>` — Löschen
- `POST /api/packages/pause` — Pause (mit myjd_api.py)
- `POST /api/packages/resume` — Resume (mit myjd_api.py)

### Task 3 — AJAX-Refresh und Detail-Modal

**Datei:** `kuasarr/api/packages/__init__.py`
**Abhängigkeiten:** Task 2

**JavaScript-Funktionen (im HTML-Template):**
- `refreshContent()` — AJAX-Call alle 5 Sekunden
- `saveScrollPosition()` / `restoreScrollPosition()`
- `showPackageDetails(packageId)` — Detail-Modal öffnen
- `confirmDelete(packageId, title)` — Delete-Bestätigung
- `performDelete(packageId)` — Löschen ausführen
- `pausePackage(packageId)` — Pause via POST
- `resumePackage(packageId)` — Resume via POST

### Task 4 — api/__init__.py Registrierung

**Datei:** `kuasarr/api/__init__.py`
**Abhängigkeiten:** Task 2, Task 5 (Nebenbefund)

**Änderungen:**
1. Import hinzufügen:
```python
from kuasarr.api.packages import setup_packages_routes
```
2. Aufruf in `get_api()`:
```python
setup_packages_routes(app)
```
3. Quick-Action-Button auf Index-Seite:
```html
<button class="action-btn" onclick="location.href='/packages'">
    <span class="action-icon">📦</span>
    <span class="action-text">Packages</span>
</button>
```

### Task 5 — Nebenbefund: setup_search_routes registrieren

**Datei:** `kuasarr/api/__init__.py`
**Abhängigkeiten:** keine

**Änderung:**
```python
from kuasarr.api.search import setup_search_routes
# ...
setup_search_routes(app)  # war bisher nicht eingebunden!
```

---

## 4. API-Endpunkte-Spezifikation

### `GET /packages`
- WebUI-Seite (HTML)
- Auth: WebUI BasicAuth (wenn konfiguriert)
- Query-Params: `deleted=1|0`, `paused=1|0`, `resumed=1|0`

### `GET /api/packages/content`
- AJAX-Endpunkt (HTML-Fragment)
- Response: HTML-String mit Paketliste
- Auto-Refresh: alle 5 Sekunden

### `GET /api/packages`
- JSON-Endpunkt
- Response:
```json
{
  "connected": true,
  "queue": [...],
  "history": [...]
}
```

### `GET /packages/delete/<package_id>`
- Action-URL mit Redirect
- Query: `title=<paketname>` (optional)
- Redirect: `/packages?deleted=1|0`

### `POST /api/packages/pause`
- JSON-Body: `{ "package_id": "..." }`
- Response: `{ "success": true|false }`

### `POST /api/packages/resume`
- JSON-Body: `{ "package_id": "..." }`
- Response: `{ "success": true|false }`

---

## 5. UI-Komponenten

### Package-Card Queue
```
▶️  Serienname S01E01
████████░░░░░░░  50%
⏱️ 00:15:00  💾 450 MB  📺
[⏸️] [ℹ️] [🗑️]
```

### Package-Card Paused
```
⏸️  Serienname S01E01
···············  0%
⏱️ --:--:--  💾 450 MB  📺
[▶️] [ℹ️] [🗑️]
```

### Package-Card CAPTCHA
```
🔒  Serienname S01E01
···············  0%
⏱️ 23:59:59  💾 900 MB  📺
[ℹ️] [🔓 Solve CAPTCHA] [🗑️]
```

### Detail-Modal
- Name, Storage-Pfad, ID, Status
- Fortschritt, Größe, ETA, Kategorie
- [⏸️ Pause] / [▶️ Resume] Buttons
- [🗑️ Delete Package & Files] Button

---

## 6. CAPTCHA-Impact-Analyse

**Keine Berührungspunkte** mit bestehenden CAPTCHA-Routen:
- `/captcha/*` — unverändert
- `/api/captcha/*` — unverändert
- `/dbc/api/*` — unverändert

CAPTCHA-Pakete werden als `protected`-Typ in der Queue angezeigt mit 🔒-Badge.

---

## 7. Test-Plan

### Automatische Tests
- [ ] Import-Smoke-Test: `kuasarr.api.packages` lädt ohne Fehler
- [ ] myjd_api.py: `set_enabled()` und `set_pause()` existieren

### Manuelle Tests
- [ ] `/packages` zeigt Pakete korrekt an
- [ ] AJAX-Refresh funktioniert alle 5 Sekunden
- [ ] Scroll-Position bleibt erhalten
- [ ] Detail-Modal öffnet/schließt korrekt
- [ ] Delete löscht Paket und Dateien
- [ ] Pause/Resume funktioniert über POST-API
- [ ] Quick-Action-Button auf Startseite sichtbar
- [ ] `/search` ist jetzt erreichbar (Nebenbefund-Fix)

---

## 8. Risiken

| Risiko | Mitigation |
|--------|-----------|
| `/api/*` von WebUI-Auth ausgenommen | Design-Entscheidung dokumentieren |
| Große Paketanzahl → langsamer Refresh | Slow-Warning bei >5s, Caching bestehend |
| myjd_api.py Änderungen | Unit-Test der neuen Methoden |

---

## Implementierungsreihenfolge

| Schritt | Task | Datei | Agent |
|---------|------|-------|-------|
| 1 | Task 5 (Nebenbefund) | `api/__init__.py` | Agent A |
| 2 | Task 1 (myjd_api.py) | `providers/myjd_api.py` | Agent B |
| 3 | Task 2 (Basis-Modul) | `api/packages/__init__.py` | Agent C |
| 4 | Task 3 (AJAX+Modal) | `api/packages/__init__.py` | Agent C |
| 5 | Task 4 (Registrierung) | `api/__init__.py` | Agent A |
| 6 | Tests | — | Alle |

**Gesamt:** ~6 Stunden
