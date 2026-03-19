# Kuasarr Sprint Plan — Upstream-Integration Quasarr v1.32 → v4.3.4

**Stand:** 2026-03-19
**Basis:** Kuasarr v1.12.5 (basiert auf Quasarr v1.31.0)
**Upstream-Ziel:** Quasarr v4.3.4

---

## Architektur-Hinweise

Kuasarr verwendet eine **funktionsbasierte Architektur**. Quasarr hingegen verwendet
`AbstractSearchSource`/`AbstractDownloadSource`-Klassen. Alle Source-Dateien aus Quasarr
müssen **adaptiert** werden (nicht 1:1 kopiert), um dem Kuasarr-Funktionsmuster zu entsprechen.

### Muster für eine neue Quelle (5 Pflichtschritte)

1. `kuasarr/search/sources/<xy>.py` — eigenständige Funktionen `xy_feed()` und `xy_search()`
2. `kuasarr/downloads/sources/<xy>.py` — eigenständige Funktion `get_xy_download_links()`
3. `kuasarr/search/__init__.py` — Registrierung in `imdb_map`, `feed_map`, optional `phrase_map`
4. `kuasarr/downloads/__init__.py` — Import hinzufügen, Handler-Funktion, URL-Match-Block in `download()`
5. `kuasarr/storage/config.py` — Hostname-Schlüssel in `_DEFAULT_CONFIG['Hostnames']` eintragen
   (Wert wird vom User manuell per UI/ini gesetzt — **kein Default-Hostname eintragen**)

---

## ⚠️ Constraints

- **Die eigene CAPTCHA-Integration muss vollständig funktional bleiben.**
  Kuasarr enthält eine eigene Captcha-Lösung (`kuasarr/api/captcha/`, `kuasarr/providers/captcha/`) bestehend aus:
  - DBC (Death by Captcha) Client & Dispatcher
  - 2Captcha Client
  - Push-Jobs (manuelles Lösen per Userscript)
  - Eigene UI-Komponenten und Routen

  Upstream-Änderungen rund um den SponsorsHelper (Quasarr-eigener bezahlter Dienst) werden **nicht** übernommen.
  Jede Änderung am CAPTCHA-Flow muss gegen alle drei Provider (DBC, 2Captcha, manuell) getestet werden.

---

## Sprint 1 — Neue Download-Quellen (Prio: Hoch)

**Ziel:** AT-, RM- und HS-Quellen aus Quasarr integrieren

**Implementierungshinweis:** Alle drei Quellen verwenden in Quasarr klassenbasierte Architektur.
Die Adaptation auf Kuasarrs Funktionsmuster ist Pflicht (siehe Architektur-Hinweise oben).
Referenz-Implementierung: https://github.com/rix1337/Quasarr

| Task | Dateien | Quasarr-Ref | Implementierungsnotizen |
|------|---------|-------------|------------------------|
| AT-Quelle (Anime) — Search + Download | `search/sources/at.py`, `downloads/sources/at.py` | v4.2.0 | Unterstützt IMDb-Lookup, Phrase-Suche, absolute Episodennummern für Anime. Enthält TheXEM-Metadaten-Auflösung für Saisonnamen (inline, `@lru_cache(maxsize=256)` — direkt übernehmen). Kein CAPTCHA erforderlich. |
| AT-Quelle: Base-Kategorie-Check fixen | `search/sources/at.py` | v4.2.1 | Kleiner Bugfix — direkt in die initiale AT-Integration einarbeiten, nicht als separaten Commit. |
| RM-Quelle (Movies/TV Feed) — Search + Download | `search/sources/rm.py`, `downloads/sources/rm.py` | v4.2.0 | Feed-basiert UND Suche (IMDb + Phrase). Deckt Filme und Serien ab. Verwendet XSRF-Token + Sessions für API-Calls. Kein CAPTCHA erforderlich. |
| HS-Quelle (Hostname-Provider) integrieren | `search/sources/hs.py`, `downloads/sources/hs.py` | v2.6.0 | RSS-Feed + IMDb-only-Suche. Verwendet **Filecrypt**-Links → bereits via `downloads/linkcrypters/filecrypt.py` unterstützt. Zweistufige Link-Extraktion: text-beschriftete Mirrors zuerst, Affiliate-Links als Fallback. Hat `_normalize_mirror_name()`-Hilfsfunktion. Kein CAPTCHA erforderlich. |
| AT, RM, HS in Source-Routing registrieren | `kuasarr/downloads/__init__.py`, `kuasarr/search/__init__.py` | v4.2.0 | Kuasarr nutzt **explizite** Registrierung (kein dynamisches Modul-Discovery wie Quasarr). Alle drei müssen manuell in `imdb_map`, `feed_map` und `download()`-URL-Match-Block eingetragen werden. |

**CAPTCHA-Hinweis:** AT, RM und HS verwenden keine SponsorsHelper-Aufrufe. Hide.cx- und Filecrypt-Links
werden über die bestehende Linkcrypter-Integration abgewickelt — diese bleibt unverändert.

---

## Sprint 2 — Provider-Härtung & Bugfixes (Prio: Hoch)

**Ziel:** Stabilität der bestehenden Quellen verbessern

**Implementierungshinweis:** NK KeyError ist ein bestätigter Production-Crash — sofort umsetzbar.
HE FlareSolverr ist **kein** HE-spezifisches CAPTCHA-Feature, sondern ein allgemeiner Browser-Bypass
(2-Strategie: direkter HTTP zuerst, FlareSolverr als Fallback).

| Task | Dateien | Quasarr-Ref | Implementierungsnotizen |
|------|---------|-------------|------------------------|
| NK: `release_imdb_id` KeyError fixen | `search/sources/nk.py` | v4.3.4 | **Bug bestätigt:** `release_imdb_id` wird nur innerhalb des try-Blocks gesetzt, aber außerhalb verwendet. Fix: `release_imdb_id = None` vor dem try-Block initialisieren. |
| HE: FlareSolverr als Browser-Bypass | `downloads/sources/he.py`, `search/sources/he.py` | v3.1.3 | Beide Dateien (Download + Search) aktualisieren. Muster: `is_cloudflare_challenge()` prüfen, bei Treffer `flaresolverr_get()` aus `providers/network/cloudflare.py` verwenden. Kein HE-spezifischer CAPTCHA-Push-Route nötig. |
| WD: FlareSolverr-Integration | `downloads/sources/wd.py`, `search/sources/wd.py` | v2.6.1 | Analoges Muster wie HE — `search/sources/wd.py` fehlt noch (Download bereits vorhanden). |
| NK: FileCrypt 403-Fallback | `downloads/linkcrypters/filecrypt.py` | v4.3.3 | Retry- oder Alternativ-Fetch-Pfad bei 403-Antworten. |
| AL: Verbesserte Saisonsuche (TheXEM) | `search/sources/al.py` | v3.1.6 | ⚠️ Offene Frage (siehe unten): Bezieht sich auf AL oder AT? |
| AL: Duplizierte Downloads verhindern (gleiche Source/Release) | `downloads/sources/al.py` | v2.1.1 | Deduplizierung auf Source-URL + Release-Titel-Ebene vor dem Einreihen. |
| Pillow CVE-Sicherheitsupdate | `requirements.txt` / `pyproject.toml` | v3.1.3 | Versionspinning auf gepatchte Pillow-Version prüfen. |

**CAPTCHA-Hinweis:** HE-Härtung betrifft ausschließlich den FlareSolverr-Bypass-Flow. Die bestehende
CAPTCHA-Push-Route (`/captcha/*`) und der generelle CAPTCHA-Flow (hide.cx, Filecrypt) bleiben unberührt.

---

## Sprint 3 — Kategorie-System (Prio: Mittel)

**Ziel:** Qualitäts- und Audio-Subkategorien sowie WebUI-Kategorienverwaltung

**Implementierungshinweis:** ✅ Implementierungsbereit — Upstream-Mechanismus vollständig geklärt.

**Quasarr-Kategorie-Modell (v4.0):**
- Kategorien sind **Konstanten** (keine DB-Spalten) mit numerischen IDs, definiert in `kuasarr/constants/__init__.py` (neu anlegen):
  ```python
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
- **Vererbungsmodell:** Subkategorien erben Settings der Basiskategorie via Modulo-1000
  (z.B. `Movies/HD` 2040 erbt von `Movies` 2000, weil `2040 % 1000 = 40 < 1000`)
- **Package-ID bleibt unverändert:** Format `kuasarr_{download_category}_{hash32}` — Subkategorie
  ist **nicht** Teil der package_id
- **DB:** Key-Value-Tabellen (bestehend) — keine neuen Spalten nötig
- **Neu anlegen:** `kuasarr/storage/categories.py` für Vererbungslogik (analog Quasarr)

| Task | Dateien | Quasarr-Ref | Implementierungsnotizen |
|------|---------|-------------|------------------------|
| Konstanten-Datei anlegen | `kuasarr/constants/__init__.py` (neu) | v4.0.0 | `SEARCH_CATEGORIES` und `DOWNLOAD_CATEGORIES` wie oben definiert. |
| Kategorie-Vererbungslogik | `kuasarr/storage/categories.py` (neu) | v4.0.0 | Modulo-1000-Muster: Subkategorien erben Settings der Basiskategorie. Referenz: `quasarr/storage/categories.py`. |
| Subkategorien einführen: Movies/HD, Movies/UHD, TV/HD, TV/UHD, Audio/MP3, Audio/FLAC | `kuasarr/constants/__init__.py`, `providers/` | v4.0.0 | Kategorien als Konstanten — keine DB-Schema-Änderung nötig. |
| Capability-aware Source-Routing | `downloads/sources/__init__.py` | v4.0.0 | Sources deklarieren unterstützte Kategorien/Qualitätsstufen; Router überspringt unpassende Sources. |
| Provider-aware Mirror-Filterung (TLD-agnostisch) | `providers/utils.py` | v4.0.0 | TLD-Normalisierung (z.B. `ddl.to` = `ddownload`) zentral in `providers/utils.py`. |
| Absolute Episodennummern (Anime) | `search/sources/al.py`, `downloads/sources/al.py` | v4.1.0 | |
| Untertitel-Sprachcodes für AL | `search/sources/al.py` | v4.1.0 | |
| Default-Kategorien: löschbar nein, änderbar ja | `api/config/` | v3.0.0 | Neue API-Endpunkte für Kategorie-CRUD. |
| Musik-Kategorie (Category 3000 / Audio) | `kuasarr/constants/__init__.py` | v3.1.0 | Bereits in DOWNLOAD_CATEGORIES als `"music"` enthalten. |

---

## Sprint 4 — WebUI: Kategorienverwaltung (Prio: Mittel)

**Ziel:** Kategorien vollständig im Browser konfigurierbar machen

**Abhängigkeit:** Vollständig blockiert auf Sprint 3. Erst nach finaler Klärung des
Kategorie-Speichermechanismus und fertiger Sprint-3-Implementierung beginnen.

| Task | Dateien | Quasarr-Ref | Implementierungsnotizen |
|------|---------|-------------|------------------------|
| WebUI: Download-Kategorien anlegen/bearbeiten/löschen | `api/__init__.py`, `providers/ui/html_templates.py` | v3.0.0 | Muster: analog `hostnames_ui`/`hostnames_api` in `api/config/__init__.py`. |
| WebUI: Mirror-Whitelist pro Kategorie | `api/__init__.py` | v3.0.0 | |
| WebUI: Hostname-Whitelist pro Such-Kategorie | `api/__init__.py` | v3.0.0 | |
| WebUI: Such-Kategorien-Interface | `api/__init__.py` | v3.1.0 | |

**CAPTCHA-Hinweis:** Neue Routen müssen `/categories/` oder `/api/categories/` verwenden —
kein Namenskonflikt mit `/captcha/*` erwartet, aber beim Routing explizit prüfen.

---

## Sprint 5 — WebUI: Packages-UI (Prio: Mittel)

**Ziel:** Laufende JDownloader-Pakete direkt im Browser anzeigen und verwalten

**Implementierungshinweis:** Infrastruktur existiert bereits vollständig in Kuasarr.
`downloads/packages/__init__.py` hat `get_packages()` und `delete_package()`.
`api/search.py` hat bereits `/api/search/status`. Sprint ist ohne Upstream-Blocker umsetzbar.

| Task | Dateien | Quasarr-Ref | Implementierungsnotizen |
|------|---------|-------------|------------------------|
| Packages-API-Endpunkte (`/api/packages`) | `api/__init__.py` | v2.0.0 | Dedizierter `/api/packages`-Endpunkt, getrennt vom bestehenden `/api/search/status`. |
| WebUI: Paketliste mit Status/Fortschritt | `providers/ui/html_templates.py` | v2.0.0 | |
| AJAX-Reload der Paketliste | `providers/ui/html_templates.py` | v2.1.2 | `setInterval` JS-Call auf `/api/packages` mit DOM-Update. |
| Package-Detail-UI-Verbesserungen | `providers/ui/html_templates.py` | v2.4.x | |
| Paket-Aktionen: pause, resume, remove | `api/__init__.py` | v2.4.x | Pause/Resume via `myjd_api.py` — JD-API-Verfügbarkeit vorab prüfen. |

**CAPTCHA-Hinweis:** Die Packages-UI darf keine CAPTCHA-Trigger-Logik enthalten — das bleibt
Aufgabe der bestehenden CAPTCHA-Routes.

---

## Sprint 6 — WebUI: Benachrichtigungen & Einstellungen (Prio: Mittel)

**Ziel:** Discord/Telegram-Benachrichtigungen im WebUI konfigurierbar machen

**Implementierungshinweis:** In sich geschlossen, kein Blocker. `providers/notifications.py`
hat bereits `send_discord_message()` und `send_telegram_message()`. Config-Sektion `Notifications`
mit `discord_webhook`, `telegram_token`, `telegram_chat_id` existiert. Direkt umsetzbar.

| Task | Dateien | Quasarr-Ref | Implementierungsnotizen |
|------|---------|-------------|------------------------|
| Discord/Telegram Notification Provider | `providers/notifications.py` | v4.3.0 | |
| WebUI: Notification-Einstellungen-Seite | `api/__init__.py` | v4.3.0 | Muster: analog `captcha-config`-Route. |
| Misserfolgsgrund in Benachrichtigungen | `providers/notifications.py` | v4.3.0 | `reason`-Parameter zum `"failed"`-Case in `send_discord_message()` hinzufügen. |
| Discord: Deaktivierungs-Benachrichtigung (adaptiert für Kuasarr) | `providers/notifications.py` | v2.4.1 | SponsorsHelper-Trigger entfernen, durch Kuasarr-eigenen Service-Trigger ersetzen. |

---

## Sprint 7 — WebUI: Slow Mode & Timeouts (Prio: Niedrig)

**Ziel:** Granulare Timeout-Steuerung pro Operation

**Implementierungshinweis:** ✅ Implementierungsbereit — alle Werte und der Mechanismus sind geklärt.

**Quasarr-Timeout-Modell (v4.3.2):**
- Konstanten in `kuasarr/constants/__init__.py` (zusammen mit Sprint 3 anlegen):
  ```python
  TIMEOUT_SLOW_MODE_MULTIPLIER = 3

  TIMEOUT_SLOW_MODE_DEFINITIONS = {
      "search":   {"label": "Search Timeout",   "base_seconds": 15},
      "feed":     {"label": "Feed Timeout",      "base_seconds": 30},
      "download": {"label": "Download Timeout",  "base_seconds": 30},
      "session":  {"label": "Session Timeout",   "base_seconds": 30},
  }
  # Effektive Werte bei Slow Mode (× 3):
  # search: 45s | feed: 90s | download: 90s | session: 90s
  ```
- **State:** `shared_state.values["timeout_slow_mode"]` — Dict mit Boolean pro Typ
- **Persistenz:** Key-Value-DB (bestehende Tabellen) via `storage/setup/timeouts.py` (neu anlegen)
- **API:** `GET/POST /api/timeouts/settings` in `api/__init__.py`
- **Hilfsfunktionen** (neu in `kuasarr/storage/setup/timeouts.py`):
  - `initialize_timeout_slow_mode_settings(shared_state)`
  - `refresh_timeout_slow_mode_settings(shared_state)`
  - `get_timeout_slow_mode_settings_data(shared_state)`
  - `save_timeout_slow_mode_settings(shared_state)`

| Task | Dateien | Quasarr-Ref | Implementierungsnotizen |
|------|---------|-------------|------------------------|
| Timeout-Konstanten anlegen | `kuasarr/constants/__init__.py` (neu, zusammen mit Sprint 3) | v4.3.2 | `TIMEOUT_SLOW_MODE_DEFINITIONS` + `TIMEOUT_SLOW_MODE_MULTIPLIER` wie oben. |
| Timeout-Setup-Modul anlegen | `kuasarr/storage/setup/timeouts.py` (neu) | v4.3.2 | `initialize_`, `refresh_`, `get_`, `save_` Funktionen. Persistenz via Key-Value-DB. |
| Per-Timeout Slow-Mode-Toggles (Search/Feed/Download/Session) | `api/__init__.py`, `providers/ui/html_templates.py` | v4.3.2 | `GET/POST /api/timeouts/settings`. Grid-UI mit Kategorie, aktuellem Wert und Toggle-Checkbox. |
| Live-Vorschau effektiver Timeout-Werte beim Umschalten | `providers/ui/html_templates.py` | v4.3.2 | JS: `effectiveSeconds = checked ? base × 3 : base` — Echtzeit-Update ohne Page-Reload. |
| Timeout-Werte an Sources weitergeben | `kuasarr/providers/shared_state.py`, alle Source-Dateien | v4.3.2 | Sources lesen Timeout aus `shared_state.values["timeout_slow_mode"]` statt Hardcode. |
| Graceful JDownloader-Reconnect mit Retry bei Token-/Timeout-Fehlern | `providers/jdownloader.py` | v4.3.2 | Bestehende Retry-Logik in `connect_to_jd()` um Token-Expiry-Handling erweitern. |
| Veraltete Hostname-Issues beim Start löschen | `providers/` | v4.3.2 | Startup-Bereinigung über bestehende Key-Value-DB. |

---

## Sprint 8 — IMDb & Such-Verbesserungen (Prio: Niedrig)

**Ziel:** Bessere Metadaten und Suchqualität

**Implementierungshinweis:** Weitgehend implementierungsbereit. `providers/imdb_metadata.py`
und `providers/network/cloudflare.py` sind vorhanden. `ThreadPoolExecutor` für non-blocking
bereits in `search/__init__.py` verfügbar.

| Task | Dateien | Quasarr-Ref | Implementierungsnotizen |
|------|---------|-------------|------------------------|
| IMDb-Metadaten beim Suchen vorausfüllen | `providers/imdb_metadata.py`, `api/search.py` | v2.3.0 | Suchergebnisse mit Poster/Titel aus IMDb anreichern. |
| FlareSolverr-Verfügbarkeitscheck: non-blocking | `providers/network/cloudflare.py` | v2.3.0 | Check in `ThreadPoolExecutor` oder Background-Thread auslagern. |
| IMDb: CDN-Fallback via FlareSolverr | `providers/imdb_metadata.py` | v2.3.2 | Bei 403 auf IMDb-CDN: `flaresolverr_get()` als Fallback verwenden. |
| Suche: Jahr-Parameter bei TV-Serien für NK/HE entfernen | `search/sources/nk.py`, `search/sources/he.py` | v2.3.1 | |
| Suchpaginierung (bis 1000 Ergebnisse) | `api/search.py` | v2.7.0 | Paginierung post-search auf gesammelten Ergebnissen (nicht per Source). |
| Feed-Suche: Ergebnisse nach Datum sortieren | `search/` | v2.7.2 | `date`-Feld existiert bereits in Result-Dict — einzeilige Sortierung. |
| Feed-Paginierung fixen | `search/` | v2.7.3 | Voraussetzt v2.7.0-Paginierung. |

---

## Implementierungsreihenfolge

Empfohlene Reihenfolge basierend auf Blocker-Analyse und Implementierungsbereitschaft:

| Priorität | Sprint | Status | Begründung |
|-----------|--------|--------|------------|
| 1 | **Sprint 2** (Bugfixes) | ✅ Bereit | NK KeyError ist bestätigter Production-Crash. Sofort umsetzbar. |
| 2 | **Sprint 5** (Packages-UI) | ✅ Bereit | Infrastruktur vollständig vorhanden. |
| 3 | **Sprint 6** (Benachrichtigungen) | ✅ Bereit | In sich geschlossen, kein externer Blocker. |
| 4 | **Sprint 1** (Neue Quellen: AT, RM, HS) | ✅ Bereit | Adaptation-Muster dokumentiert, Upstream-Dateien verfügbar. |
| 5 | **Sprint 8** (IMDb/Suche) | ✅ Bereit | Weitgehend bereit, kein Research-Blocker. |
| 6 | **Sprint 7** (Slow Mode) | ✅ Bereit | Konstanten, Werte und Architektur vollständig geklärt. |
| 7 | **Sprint 3** (Kategorie-System) | ✅ Bereit | Konstanten-Modell und Vererbungslogik vollständig geklärt. |
| 8 | **Sprint 4** (WebUI Kategorien) | 🔴 Blockiert | Vollständig abhängig von Sprint 3. |

---

## Offene Fragen

1. **Sprint 2 — AL TheXEM-Zuordnung:**
   Bezieht sich "AL: Verbesserte Saisonsuche (TheXEM)" auf `search/sources/al.py`
   oder auf `search/sources/at.py`? TheXEM ist bisher nur in AT dokumentiert.
   → Vor Implementierung des AL-TheXEM-Tasks klären.

---

## Nicht zu übernehmen (Quasarr-intern)

| Feature | Grund |
|---------|-------|
| SponsorsHelper-Endpunkte | Quasarr-eigener Bezahldienst — Kuasarr hat eigene Captcha-Lösung |
| SponsorsHelper-Status im Footer | Nicht relevant ohne SponsorsHelper |
| APIKEY_2CAPTCHA via SponsorsHelper | Kuasarr hat eigene 2Captcha-Integration |
| Userscript-Whitelisting (`.user.js`) | Kuasarr-Userscripts separat gemanagt |
| Form/Basic-Auth Login (v2.0.0) | Eigene Auth-Implementierung prüfen |
| CLI Mock Client | Entwicklertool, kein Endnutzerfeature |
| uv Build-System-Migration | Separates CI/CD-Thema |

---

## Versionsplan

| Sprint | Kuasarr Version |
|--------|----------------|
| Sprint 2 (Bugfixes) | v1.13.0 |
| Sprint 5 (Packages-UI) | v1.14.0 |
| Sprint 6 (Benachrichtigungen) | v1.14.1 |
| Sprint 1 (neue Quellen AT/RM/HS) | v1.15.0 |
| Sprint 8 (IMDb/Suche) | v1.15.1 |
| Sprint 7 (Slow Mode) | v1.16.0 |
| Sprint 3 (Kategorie-System) | v1.17.0 |
| Sprint 4 (WebUI Kategorien) | v1.18.0 |
