# Kuasarr Sprint Plan — Upstream-Integration Quasarr v1.32 → v4.3.4

**Stand:** 2026-03-16
**Basis:** Kuasarr v1.12.2 (basiert auf Quasarr v1.31.0)
**Upstream-Ziel:** Quasarr v4.3.4

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
**Ziel:** AT- und RM-Quellen aus Quasarr v4.2.0 integrieren

| Task | Dateien | Quasarr-Ref |
|------|---------|-------------|
| AT-Quelle (Anime) — Search + Download | `search/sources/at.py`, `downloads/sources/at.py` | v4.2.0 |
| RM-Quelle (Movies/TV Feed) — Search + Download | `search/sources/rm.py`, `downloads/sources/rm.py` | v4.2.0 |
| AT-Quelle: Base-Kategorie-Check fixen | `search/sources/at.py` | v4.2.1 |
| HS-Quelle (Hostname-Provider) integrieren | `search/sources/hs.py`, `downloads/sources/hs.py` | v2.6.0 |
| RM/AT in Source-Routing registrieren | `downloads/sources/__init__.py`, `search/sources/__init__.py` | v4.2.0 |

**CAPTCHA-Hinweis:** AT und RM verwenden voraussichtlich `hide.cx`-Links — bestehende Hide-Linkcrypter-Integration unverändert lassen.

---

## Sprint 2 — Provider-Härtung & Bugfixes (Prio: Hoch)
**Ziel:** Stabilität der bestehenden Quellen verbessern

| Task | Dateien | Quasarr-Ref |
|------|---------|-------------|
| HE: FlareSolverr als Pflichtabhängigkeit | `downloads/sources/he.py`, `search/sources/he.py` | v3.1.3 |
| WD: FlareSolverr-Integration | `downloads/sources/wd.py`, `search/sources/wd.py` | v2.6.1 |
| NK: `release_imdb_id` KeyError fixen | `search/sources/nk.py` | v4.3.4 |
| NK: FileCrypt 403-Fallback | `downloads/linkcrypters/filecrypt.py` | v4.3.3 |
| AL: Verbesserte Saisonsuche (TheXEM) | `search/sources/al.py`, `providers/` | v3.1.6 |
| AL: Duplizierte Downloads verhindern (gleiche Source/Release) | `downloads/sources/al.py` | v2.1.1 |
| Pillow CVE-Sicherheitsupdate | `requirements.txt` / `pyproject.toml` | v3.1.3 |

**CAPTCHA-Hinweis:** HE-Härtung darf nicht die bestehende CAPTCHA-Push-Route für HE-Captchas verändern.

---

## Sprint 3 — Kategorie-System (Prio: Mittel)
**Ziel:** Qualitäts- und Audio-Subkategorien sowie WebUI-Kategorienverwaltung

| Task | Dateien | Quasarr-Ref |
|------|---------|-------------|
| Subkategorien einführen: Movies/HD, Movies/4K, TV/HD, TV/4K, Audio/MP3, Audio/FLAC | `storage/`, `providers/` | v4.0.0 |
| Capability-aware Source-Routing | `downloads/sources/__init__.py` | v4.0.0 |
| Provider-aware Mirror-Filterung (TLD-agnostisch) | `providers/utils.py` | v4.0.0 |
| Absolute Episodennummern (Anime) | `search/sources/al.py`, `downloads/sources/al.py` | v4.1.0 |
| Untertitel-Sprachcodes für AL | `search/sources/al.py` | v4.1.0 |
| Default-Kategorien: löschbar nein, änderbar ja | `api/config/` | v3.0.0 |
| Musik-Kategorie (Category 3000) | `storage/container.py` | v3.1.0 |

---

## Sprint 4 — WebUI: Kategorienverwaltung (Prio: Mittel)
**Ziel:** Kategorien vollständig im Browser konfigurierbar machen

| Task | Dateien | Quasarr-Ref |
|------|---------|-------------|
| WebUI: Download-Kategorien anlegen/bearbeiten/löschen | `api/__init__.py`, `providers/ui/html_templates.py` | v3.0.0 |
| WebUI: Mirror-Whitelist pro Kategorie | `api/__init__.py` | v3.0.0 |
| WebUI: Hostname-Whitelist pro Such-Kategorie | `api/__init__.py` | v3.0.0 |
| WebUI: Such-Kategorien-Interface | `api/__init__.py` | v3.1.0 |

**CAPTCHA-Hinweis:** Keine Überschneidung erwartet. Trotzdem sicherstellen, dass neue Routen keinen Namenskonflikt mit `/captcha/*` erzeugen.

---

## Sprint 5 — WebUI: Packages-UI (Prio: Mittel)
**Ziel:** Laufende JDownloader-Pakete direkt im Browser anzeigen und verwalten

| Task | Dateien | Quasarr-Ref |
|------|---------|-------------|
| Packages-API-Endpunkte (`/api/packages`) | `api/__init__.py` | v2.0.0 |
| WebUI: Paketliste mit Status/Fortschritt | `providers/ui/html_templates.py` | v2.0.0 |
| AJAX-Reload der Paketliste | `providers/ui/html_templates.py` | v2.1.2 |
| Package-Detail-UI-Verbesserungen | `providers/ui/html_templates.py` | v2.4.x |
| Paket-Aktionen: pause, resume, remove | `api/__init__.py` | v2.4.x |

**CAPTCHA-Hinweis:** Die Packages-UI darf keine CAPTCHA-Trigger-Logik enthalten — das bleibt Aufgabe der bestehenden CAPTCHA-Routes.

---

## Sprint 6 — WebUI: Benachrichtigungen & Einstellungen (Prio: Mittel)
**Ziel:** Discord/Telegram-Benachrichtigungen im WebUI konfigurierbar machen

| Task | Dateien | Quasarr-Ref |
|------|---------|-------------|
| Discord/Telegram Notification Provider | `providers/notifications.py` | v4.3.0 |
| WebUI: Notification-Einstellungen-Seite | `api/__init__.py` | v4.3.0 |
| Misserfolgsgrund in Benachrichtigungen | `providers/notifications.py` | v4.3.0 |
| Discord: Deaktivierungs-Benachrichtigung bei SponsorsHelper (adaptiert für Kuasarr) | `providers/notifications.py` | v2.4.1 |

---

## Sprint 7 — WebUI: Slow Mode & Timeouts (Prio: Niedrig)
**Ziel:** Granulare Timeout-Steuerung pro Operation

| Task | Dateien | Quasarr-Ref |
|------|---------|-------------|
| Per-Timeout Slow-Mode-Toggles (Search/Feed/Download/Session) | `api/__init__.py`, `providers/ui/html_templates.py` | v4.3.2 |
| Live-Vorschau effektiver Timeout-Werte beim Umschalten | `providers/ui/html_templates.py` | v4.3.2 |
| Graceful JDownloader-Reconnect mit Retry bei Token-/Timeout-Fehlern | `providers/jdownloader.py` | v4.3.2 |
| Veraltete Hostname-Issues beim Start löschen | `providers/` | v4.3.2 |

---

## Sprint 8 — IMDb & Such-Verbesserungen (Prio: Niedrig)
**Ziel:** Bessere Metadaten und Suchqualität

| Task | Dateien | Quasarr-Ref |
|------|---------|-------------|
| IMDb-Metadaten beim Suchen vorausfüllen | `providers/imdb_metadata.py`, `api/search.py` | v2.3.0 |
| FlareSolverr-Verfügbarkeitscheck: non-blocking | `providers/network/cloudflare.py` | v2.3.0 |
| IMDb: CDN-Fallback via FlareSolverr | `providers/imdb_metadata.py` | v2.3.2 |
| Suche: Jahr-Parameter bei TV-Serien für NK/HE entfernen | `search/sources/nk.py`, `search/sources/he.py` | v2.3.1 |
| Suchpaginierung (bis 1000 Ergebnisse) | `api/search.py` | v2.7.0 |
| Feed-Suche: Ergebnisse nach Datum sortieren | `search/` | v2.7.2 |
| Feed-Paginierung fixen | `search/` | v2.7.3 |

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
| Sprint 1 (neue Quellen) | v1.13.0 |
| Sprint 2 (Bugfixes) | v1.13.1 |
| Sprint 3 (Kategorie-System) | v1.14.0 |
| Sprint 4 (WebUI Kategorien) | v1.15.0 |
| Sprint 5 (Packages-UI) | v1.16.0 |
| Sprint 6 (Benachrichtigungen) | v1.17.0 |
| Sprint 7 (Slow Mode) | v1.17.1 |
| Sprint 8 (IMDb/Suche) | v1.18.0 |
