# Kuasarr Sprint Plan v2 — Remaining Work

**Stand:** 2026-03-23
**Basis:** Kuasarr v1.16.0 (main) + PR #35 (Sprint 8, pending)
**Upstream-Ref:** Quasarr v4.3.4 @ `/home/ubuntu/Quasarr-ref/`

---

## Bereits erledigt (Referenz)

| Sprint | Inhalt | Version | PR |
|--------|--------|---------|-----|
| Sprint 2 | Bugfixes (NK KeyError, HE/WD FlareSolverr, TheXEM) | v1.13.0 | #20 |
| Sprint 5 | Packages-UI | v1.14.0 | #23 |
| Sprint 6 | Notifications UI (Discord/Telegram) | ~v1.14.1 | #24 |
| Sprint 1 | AT/RM/HS Quellen | v1.16.0 | #29 |
| Sprint 8 | IMDb/Suche (Pagination, Sorting, FlareSolverr non-blocking) | v1.17.0 | #35 (open) |

---

## Implementierungsreihenfolge

| Priorität | Sprint | Version | Blocker |
|-----------|--------|---------|---------|
| 1 | **Sprint A** — UI/Accessibility Fixes | v1.17.1 | — |
| 2 | **Sprint B** — Auth Hardening | v1.18.0 | — |
| 3 | **Sprint C** — Notifications Refactor | v1.18.1 | — |
| 4 | **Sprint D** — Slow Mode & Timeouts | v1.19.0 | — |
| 5 | **Sprint E** — Kategorie-System | v1.20.0 | Sprint D (constants/) |
| 6 | **Sprint F** — WebUI Kategorien | v1.21.0 | Sprint E + Sprint B |

---

## Sprint A — UI/Accessibility Fixes (Prio: Hoch)

**Ziel:** Kritische Accessibility-Bugs fixen, UX verbessern
**Version:** v1.17.1
**Datei:** `kuasarr/providers/ui/html_templates.py`

### A1 — Button Focus-Styles (🔴 KRITISCH — WCAG-Pflicht)

Buttons haben aktuell keinen `:focus`-Stil → Tastatur-Navigation kaputt.

```css
button:focus-visible {
    outline: 2px solid var(--primary);
    outline-offset: 2px;
}
a:focus-visible {
    outline: 2px solid var(--primary);
    outline-offset: 2px;
}
```

### A2 — Dark-Mode Primärfarbe (🔴 KRITISCH — WCAG AA-Fehler)

`--primary: #375a7f` im Dark Mode → Kontrast ~2.5:1 gegen weißen Button-Text (WCAG AA erfordert 4.5:1).

```css
/* Im :root[data-theme="dark"] Block: */
--primary: #4d8fd4;        /* war: #375a7f — Kontrast ~4.6:1 ✓ */
--primary-hover: #3a7bc8;  /* war: #2b4764 */
```

Kontrast-Check: https://contrast-ratio.com/ → `#4d8fd4` auf `#1e1e1e` = ~4.6:1 ✓

### A3 — `prefers-reduced-motion` (🟡 Hoch)

Alle Transitions laufen auch bei Nutzern mit deaktivierten Animationen.

```css
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
    }
}
```

### A4 — `button:active` Press-Feedback (🟡 Hoch)

Aktuelles `button:active { transform: translateY(0); }` hat keinen Effekt (kein -1px Normalzustand).

```css
button:not(:disabled):active {
    transform: translateY(1px);
    box-shadow: none;
}
```

### A5 — `render_success` UX (🟢 Mittel)

"Wait time... 10" ersetzen durch Auto-Redirect mit Countdown und abbrechbarem Button.

```python
def render_success(message, timeout=5, optional_text=""):
    script = f'''
        <script>
            let counter = {timeout};
            const btn = document.getElementById('nextButton');
            const info = document.getElementById('redirect-info');
            const interval = setInterval(() => {{
                counter--;
                if (info) info.textContent = `Redirecting in ${{counter}}s...`;
                if (counter === 0) {{
                    clearInterval(interval);
                    window.location.href = '/';
                }}
            }}, 1000);
            btn.onclick = () => {{ clearInterval(interval); window.location.href = '/'; }};
        </script>
    '''
    button_html = render_button("Go to Home", "primary", {{"id": "nextButton"}})
    content = f"""
    <h1><img src="{images.logo}" type="image/png" alt="kuasarr logo" class="logo"/>kuasarr</h1>
    <h2>{message}</h2>
    {optional_text}
    <p id="redirect-info" style="color:var(--text-muted);font-size:0.85rem;">Redirecting in {timeout}s...</p>
    {button_html}
    {script}
    """
    return render_centered_html(content)
```

### A6 — Persistente Navigation (🟢 Mittel)

Neue Hilfsfunktion `render_nav()` und Integration in `render_form()`.

```python
def render_nav(active_page=""):
    pages = [
        ("/", "Home"),
        ("/settings", "Settings"),
        ("/captcha-config", "CAPTCHA"),
        ("/hosters", "Hosters"),
        ("/notifications", "Notifications"),
    ]
    items = "".join(
        f'<a href="{url}" class="nav-link{"  nav-active" if url == active_page else ""}">{label}</a>'
        for url, label in pages
    )
    return f'<nav class="top-nav">{items}</nav>'

# render_form() bekommt neuen Parameter: active_page=""
def render_form(header, form="", script="", footer_content="", active_page=""):
    nav = render_nav(active_page)
    # nav direkt nach <h1> einfügen, vor <h2>
```

CSS-Block für `.top-nav`, `.nav-link`, `.nav-active` (siehe `docs/ui_optimierung.md`).

**Route-Dateien die `render_form()` aufrufen** — alle müssen `active_page=` ergänzen:
- `kuasarr/api/config/__init__.py` (Settings → `active_page="/settings"`)
- `kuasarr/api/captcha/main_routes.py` (`active_page="/captcha-config"`)
- `kuasarr/api/hosters/__init__.py` (`active_page="/hosters"`)
- `kuasarr/api/notifications/__init__.py` (`active_page="/notifications"`)

### A7 — Inter-Font (⚪ Optional)

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

CSS: `font-family: 'Inter', system-ui, -apple-system, sans-serif;`

**⚠️ Hinweis:** Externe Font-Requests — nur implementieren wenn User zustimmt (Datenschutz/offline-Nutzung).

---

## Sprint B — Auth Hardening (Prio: Hoch)

**Ziel:** Auth-System auf Quasarr v4.3.0-Stand bringen, API-Key-Absicherung, XSS/Open-Redirect-Fixes
**Version:** v1.18.0
**Quasarr-Ref:** `quasarr/providers/auth.py` @ v4.3.0

### B1 — `auth.py` erweitern

Kuasarr hat aktuell **keine** `auth.py`. Auth-Logik ist in `kuasarr/__init__.py` oder verteilt.

**Neue Datei:** `kuasarr/providers/auth.py`

Folgende Funktionen von Quasarr v4.3.0 portieren (SponsorsHelper-Referenzen entfernen):

```python
# Dekoratoren
def public_endpoint(func)         # Markiert Route als öffentlich (kein Auth nötig)
def require_api_key(func)         # API-Endpunkte absichern — prüft X-API-Key Header oder ?apikey= param
def require_browser_auth(func)    # Browser-Routen absichern

# Hilfsfunktionen
def is_browser_authenticated()    # Prüft ob aktuelle Browser-Session authentifiziert ist
def _normalize_next_url(next_url) # Open-Redirect-Fix: nur relative interne URLs erlaubt
def audit_route_auth_modes(app, api_key_prefixes=None, public_whitelist=None)
                                  # Dev-Hilfsfunktion: prüft alle Routes auf Auth-Mode

# XSS-Fix im Login-Formular
# html.escape(str(error)) bei Fehlerausgabe
# html.escape(_normalize_next_url(...), quote=True) bei ?next= Parameter
```

**Auth-Hook vereinfachen** (aktuell explizite Whitelist mit `/api`, `/download/`, etc.):
```python
# NEU: nur .user.js ist public, alles andere über Dekoratoren gesteuert
add_auth_hook(app, whitelist=[".user.js"])
```

**Alle API-Endpunkte** in `kuasarr/api/` mit `@require_api_key` dekorieren.

### B2 — API-Key-Injection ins WebUI

In `kuasarr/providers/ui/html_templates.py` — `render_centered_html()` erweitern:

```python
from kuasarr.providers.auth import is_auth_enabled, is_browser_authenticated

def render_centered_html(content, footer_content=""):
    api_key = ""
    if not is_auth_enabled() or is_browser_authenticated():
        try:
            api_key = Config("API").get("key") or ""
        except Exception:
            api_key = ""

    api_key_script = f"""
        <script>
            window.KUASARR_API_KEY = {repr(api_key)};
            // Auto-inject apikey in alle Formulare die /api-Ziele haben
            document.addEventListener('DOMContentLoaded', function() {{
                if (window.KUASARR_API_KEY) {{
                    document.querySelectorAll('form[action^="/api"]').forEach(function(form) {{
                        if (form.querySelector('input[name="apikey"]')) return;
                        const input = document.createElement('input');
                        input.type = 'hidden';
                        input.name = 'apikey';
                        input.value = window.KUASARR_API_KEY;
                        form.appendChild(input);
                    }});
                }}
            }});

            // Zentrale Fetch-Hilfsfunktion — setzt X-API-Key Header automatisch
            function kuasarrApiFetch(path, options) {{
                const requestOptions = options ? {{ ...options }} : {{}};
                const headers = new Headers(requestOptions.headers || {{}});
                if (window.KUASARR_API_KEY && !headers.has('X-API-Key')) {{
                    headers.set('X-API-Key', window.KUASARR_API_KEY);
                }}
                requestOptions.headers = headers;
                return fetch(path, requestOptions);
            }}
        </script>
    """ if api_key else ""
    # api_key_script in <head> oder am Ende von <body> einfügen
```

**Alle bestehenden `fetch()`-Calls** in `html_templates.py` auf `kuasarrApiFetch()` umstellen.

**⚠️ Kuasarr-Anpassung:** Variable heißt `KUASARR_API_KEY` (nicht `QUASARR_API_KEY`).

---

## Sprint C — Notifications Refactor (Prio: Mittel)

**Ziel:** `providers/notifications.py` (Flat-File) zu `providers/notifications/` Modul refactorn — analog Quasarr v4.3.0
**Version:** v1.18.1
**Quasarr-Ref:** `quasarr/providers/notifications/` @ v4.3.0

### C1 — Modul-Struktur anlegen

```
kuasarr/providers/notifications/
├── __init__.py          # send_discord_message(), send_telegram_message() — öffentliche API
├── discord.py           # DiscordNotificationFormatter
├── telegram.py          # TelegramNotificationFormatter
└── helpers/
    ├── __init__.py
    ├── notification_types.py    # NotificationType Enum (Kuasarr-angepasst)
    ├── notification_message.py  # NotificationMessage, Entry-Klassen
    ├── message_builder.py       # build_notification_message()
    └── common.py                # Gemeinsame Hilfsfunktionen
```

### C2 — NotificationType anpassen (Kuasarr-spezifisch)

Quasarr-spezifische Typen aus `notification_types.py` entfernen/umbenennen:

```python
class NotificationType(str, Enum):
    UNPROTECTED = "unprotected"    # beibehalten
    CAPTCHA     = "captcha"        # beibehalten
    SOLVED      = "solved"         # beibehalten
    DISABLED    = "disabled"       # Label: "Kuasarr Disabled" (war: "SponsorsHelper Disabled")
    FAILED      = "failed"         # Label: "Failed" (war: "SponsorsHelper Failed")
    UPDATE      = "update"         # Label: "Kuasarr Updates" (war: "QUASARR_UPDATE")
    TEST        = "test"           # beibehalten
```

Aktuell in `kuasarr/providers/notifications.py` — Enum ist bereits definiert, muss nur umstrukturiert werden.

### C3 — Storage-Setup für Notifications

Neue Datei: `kuasarr/storage/setup/notifications.py`
(analog `quasarr/storage/setup/notifications.py` @ v4.3.0)

Funktionen:
- `initialize_notification_settings(shared_state)` — DB-Tabelle anlegen
- `get_notification_settings_data(shared_state)` — Settings als JSON für API
- `save_notification_settings(shared_state)` — POST-Handler
- `send_notification_test(shared_state)` — Test-Nachricht senden

**⚠️ Hinweis:** Quasarr verwendet `NOTIFICATION_PROVIDERS` Konstante aus `constants/__init__.py` — in Kuasarr analog anlegen (Sprint D erstellt `constants/__init__.py`, daher ggf. zusammen implementieren).

### C4 — API-Endpunkte ergänzen

In `kuasarr/api/notifications/__init__.py`:

```python
@app.get("/api/notifications/settings")
@require_api_key   # aus Sprint B
def get_notification_settings_api():
    return get_notification_settings_data(shared_state)

@app.post("/api/notifications/settings")
@require_api_key
def save_notification_settings_api():
    return save_notification_settings(shared_state)

@app.post("/api/notifications/test")
@require_api_key
def send_notification_test_api():
    return send_notification_test(shared_state)
```

---

## Sprint D — Slow Mode & Timeouts (Prio: Mittel)

**Ziel:** Granulare Timeout-Steuerung pro Operation
**Version:** v1.19.0
**Quasarr-Ref:** `quasarr/storage/setup/timeouts.py` + `quasarr/constants/__init__.py` @ v4.3.2

### D1 — `kuasarr/constants/__init__.py` anlegen (NEU)

Diese Datei wird auch von Sprint E (Kategorien) und ggf. Sprint C (Notifications) benötigt.

```python
# Slow Mode
TIMEOUT_SLOW_MODE_MULTIPLIER = 3

TIMEOUT_SLOW_MODE_DEFINITIONS = {
    "search":   {"label": "Search Timeout",   "base_seconds": 15},
    "feed":     {"label": "Feed Timeout",      "base_seconds": 30},
    "download": {"label": "Download Timeout",  "base_seconds": 30},
    "session":  {"label": "Session Timeout",   "base_seconds": 30},
}

# Notification providers (für Sprint C)
NOTIFICATION_PROVIDERS = ["discord", "telegram"]

# Search Categories (für Sprint E)
SEARCH_CATEGORIES = {
    2000: {"name": "Movies",           "emoji": "🎬"},
    2040: {"name": "Movies/HD",        "emoji": "🎬"},
    2045: {"name": "Movies/UHD",       "emoji": "🎬"},
    3000: {"name": "Audio",            "emoji": "🎵"},
    3010: {"name": "Audio/MP3",        "emoji": "🎵"},
    3040: {"name": "Audio/FLAC",       "emoji": "🎵"},
    5000: {"name": "TV",               "emoji": "📺"},
    5040: {"name": "TV/HD",            "emoji": "📺"},
    5045: {"name": "TV/UHD",           "emoji": "📺"},
    5070: {"name": "TV/Anime",         "emoji": "⛩️"},
    5080: {"name": "TV/Documentary",   "emoji": "🎥"},
    7000: {"name": "Books",            "emoji": "📚"},
}

DOWNLOAD_CATEGORIES = {
    "movies": {"emoji": "🎬"},
    "music":  {"emoji": "🎵"},
    "tv":     {"emoji": "📺"},
    "docs":   {"emoji": "📄"},
}
```

### D2 — `kuasarr/storage/setup/timeouts.py` anlegen (NEU)

**Verzeichnis:** `kuasarr/storage/setup/` muss ggf. als Package angelegt werden (`__init__.py`).

```python
# Funktionen analog quasarr/storage/setup/timeouts.py:

def initialize_timeout_slow_mode_settings(shared_state):
    """Initialisiert slow_mode Einträge in der Key-Value-DB beim Start."""

def refresh_timeout_slow_mode_settings(shared_state):
    """Lädt aktuelle Werte aus DB in shared_state.values["timeout_slow_mode"]."""

def get_timeout_slow_mode_settings_data(shared_state):
    """Gibt Settings als JSON-serialisierbares Dict zurück (für GET-API)."""

def save_timeout_slow_mode_settings(shared_state):
    """Liest POST-Body und speichert in DB (für POST-API)."""
```

**State-Struktur:** `shared_state.values["timeout_slow_mode"]` = `Dict[str, bool]`
Beispiel: `{"search": False, "feed": True, "download": False, "session": False}`

**Persistenz:** Key-Value-DB via `DataBase` (bestehende Tabellen).

### D3 — API-Endpunkt

In `kuasarr/api/__init__.py` oder neue Datei `kuasarr/api/timeouts/__init__.py`:

```python
@app.get("/api/timeouts/settings")
@require_api_key
def get_timeout_settings():
    return get_timeout_slow_mode_settings_data(shared_state)

@app.post("/api/timeouts/settings")
@require_api_key
def save_timeout_settings():
    return save_timeout_slow_mode_settings(shared_state)
```

### D4 — WebUI

In `kuasarr/providers/ui/html_templates.py` oder als Route in `api/`:

Grid-UI mit: Kategorie | Base-Wert | Slow-Mode-Toggle (Checkbox) | Effektiver Wert

JS Live-Preview:
```javascript
function updateEffective(checkbox, base) {
    const effectiveSeconds = checkbox.checked ? base * 3 : base;
    // DOM-Update ohne Page-Reload
}
```

Aufruf via `kuasarrApiFetch('/api/timeouts/settings', { method: 'POST', ... })` (aus Sprint B).

### D5 — Timeout-Werte an Sources weitergeben

`shared_state.values["timeout_slow_mode"]` in allen Source-Dateien lesen statt hardcoded Werte:

```python
# Beispiel in nk.py:
slow_mode = shared_state.values.get("timeout_slow_mode", {})
base = TIMEOUT_SLOW_MODE_DEFINITIONS["search"]["base_seconds"]
multiplier = TIMEOUT_SLOW_MODE_MULTIPLIER if slow_mode.get("search") else 1
timeout = base * multiplier
```

Betroffene Dateien: alle `search/sources/*.py` und `downloads/sources/*.py`.

### D6 — Startup-Bereinigung (Bonus)

Veraltete Hostname-Issues beim Start löschen:
```python
# In kuasarr/__init__.py run():
# Cleanup stale hostname issue keys from previous sessions
```

---

## Sprint E — Kategorie-System (Prio: Mittel)

**Ziel:** Subkategorien, Vererbungslogik, Source-Routing
**Version:** v1.20.0
**Quasarr-Ref:** `quasarr/storage/categories.py` @ v4.0.0–v4.3.0
**Blocker:** Sprint D muss zuerst `constants/__init__.py` anlegen

### E1 — `kuasarr/storage/categories.py` anlegen (NEU)

Port von `quasarr/storage/categories.py` — Modulo-1000-Vererbungsmuster:

```python
# Vererbungsmodell: Subkategorie erbt Settings der Basiskategorie
# Beispiel: Movies/HD (2040) erbt von Movies (2000) weil 2040 % 1000 = 40 < 1000
def get_search_category_whitelist_owner(cat_id: int) -> int:
    base = cat_id - (cat_id % 1000)
    return base if base != cat_id else cat_id

def get_search_category_sources(cat_id: int) -> list:
    """Gibt konfigurierte Sources für eine Suchkategorie zurück."""

def get_download_category_mirrors(category_name: str) -> list:
    """Gibt konfigurierte Mirrors für eine Download-Kategorie zurück."""
```

**DB-Tabellen:** `categories_search`, `categories_download` (Key-Value, bestehende Infrastruktur).
**Keine neuen DB-Spalten** — alles über Key-Value-Tabellen.

**Package-ID bleibt:** Format `kuasarr_{download_category}_{hash32}` — Subkategorie ist NICHT Teil der package_id.

### E2 — Capability-aware Source-Routing

In `kuasarr/downloads/sources/__init__.py` oder je Source-Datei:

Sources deklarieren unterstützte Kategorien:
```python
# Beispiel in at.py:
SUPPORTED_CATEGORIES = [5070]  # TV/Anime only

# Router überspringt Source wenn requested category nicht supported
```

### E3 — Provider-aware Mirror-Filterung

In `kuasarr/providers/utils.py` — TLD-Normalisierung zentral:
```python
# Beispiel: "ddl.to" == "ddownload" (gleicher Anbieter, andere TLD)
MIRROR_TLD_MAP = {
    "ddl.to": "ddownload",
    # ...
}
def normalize_mirror_name(name: str) -> str:
    ...
```

**Quasarr-Ref:** `quasarr/providers/utils.py` @ v4.0.0

### E4 — Anime/AL Extras (aus altem Sprint 3)

- Absolute Episodennummern in `search/sources/al.py`, `downloads/sources/al.py` (Quasarr v4.1.0)
- Untertitel-Sprachcodes in `search/sources/al.py` (Quasarr v4.1.0)

---

## Sprint F — WebUI Kategorien (Prio: Mittel)

**Ziel:** Kategorien vollständig im Browser konfigurierbar
**Version:** v1.21.0
**Quasarr-Ref:** `quasarr/api/config/__init__.py` @ v3.0.0–v3.1.0
**Blocker:** Sprint E (Kategorie-System) + Sprint B (Auth/API-Key)

### F1 — Download-Kategorien CRUD

```python
# In kuasarr/api/config/__init__.py oder neue kuasarr/api/categories/__init__.py

@app.get("/api/categories")
@require_api_key
def list_download_categories(): ...

@app.post("/api/categories")
@require_api_key
def create_download_category(): ...

@app.post("/api/categories/<name>")
@require_api_key
def update_download_category(name): ...

@app.delete("/api/categories/<name>")
@require_api_key
def delete_download_category(name): ...
```

**Default-Kategorien** (`movies`, `music`, `tv`, `docs`): löschbar = Nein, änderbar = Ja.

**Muster:** analog `hostnames_ui`/`hostnames_api` in `kuasarr/api/config/__init__.py`.

### F2 — Mirror-Whitelist pro Kategorie

```python
@app.get("/api/categories/<name>/mirrors")
@app.post("/api/categories/<name>/mirrors")
```

### F3 — Suchkategorien API

```python
@app.get("/api/categories_search")
@app.get("/api/categories_search/<cat_id>/search_sources")
@app.post("/api/categories_search/<cat_id>/search_sources")
@app.delete("/api/categories_search/<cat_id>")
```

### F4 — WebUI

In `kuasarr/providers/ui/html_templates.py`:

- Download-Kategorien-Seite mit Add/Edit/Delete
- Mirror-Whitelist-Editor pro Kategorie
- Suchkategorien-Seite mit Source-Zuordnung

**JS-Fetch via `kuasarrApiFetch()`** (aus Sprint B).

**Route:** `/categories` (kein Konflikt mit `/captcha/*`).

---

## Constraints (unverändert)

- **CAPTCHA-Integration muss funktional bleiben** — DBC, 2Captcha, Push-Jobs
- **SponsorsHelper nicht übernehmen** — alle Quasarr-Referenzen auf SponsorsHelper entfernen
- **Keine Hostnames bundlen**
- **SABnzbd + Newznab API-Contract erhalten**
- **Multi-arch Docker:** `linux/amd64`, `linux/arm64`, `linux/arm/v7`

## Nicht zu übernehmen

| Feature | Grund |
|---------|-------|
| `quasarr/providers/sessions/al.py` | Quasarr-eigene Session-Abstraktion, in Kuasarr nicht nötig |
| `audit_route_auth_modes()` in Prod | Nur Dev-Tool — nicht in Produktion aktivieren |
| SponsorsHelper-Typen in NotificationType | Durch Kuasarr-eigene Labels ersetzen |
| uv Build-System | Separates CI/CD-Thema |
| Form/Basic-Auth Login v2.0.0 | Eigene Auth-Implementierung prüfen |
