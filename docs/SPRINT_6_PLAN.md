# Sprint 6 Plan — Notifications WebUI

## Ziel

Dedizierte Notification-Einstellungsseite im WebUI für Discord und Telegram.
Nutzer sollen Webhooks/Tokens konfigurieren und direkt testen können.

## Analyse des Ist-Zustands

- `kuasarr/providers/notifications.py`: Enthält `send_discord_message()` und `send_telegram_message()`. Beide lesen aus `Config('Notifications')`.
- `kuasarr/storage/config.py`: Sektion `Notifications` bereits definiert mit `discord_webhook` (secret), `telegram_token` (secret), `telegram_chat_id` (str).
- `kuasarr/api/__init__.py`: Kein Notification-Button im Quick-Action-Grid.
- Die generische `/settings`-Seite zeigt Notifications bereits, aber ohne Test-Funktion und ohne spezielle UI.

## Aufgaben

### Task 1 — `kuasarr/api/notifications/__init__.py` (NEU)

Neues Modul mit folgenden Routes:

**GET `/notifications`** — Render Notification Settings Page
- HTML-Formular mit Feldern:
  - Discord Webhook URL (type=password, mit "Show"-Toggle)
  - Telegram Bot Token (type=password, mit "Show"-Toggle)
  - Telegram Chat ID (type=text)
- "Test Discord" Button → ruft `/api/notifications/test/discord` via fetch() auf
- "Test Telegram" Button → ruft `/api/notifications/test/telegram` via fetch() auf
- "Save" Button → POST `/api/notifications/save`
- "Back" Button → zurück zur `/`

**POST `/api/notifications/save`** — Einstellungen speichern
- Liest discord_webhook, telegram_token, telegram_chat_id aus dem Formular
- Speichert via `Config('Notifications').save()`
- Secrets nur speichern wenn nicht leer (wie in `/settings`)
- Redirect zu `/notifications` nach Erfolg

**POST `/api/notifications/test/discord`** — Discord Test
- Sendet Test-Nachricht via `send_discord_message()`
- Nutzt einen neuen `case="test"` in notifications.py
- JSON-Response: `{"success": true}` oder `{"success": false, "error": "..."}`

**POST `/api/notifications/test/telegram`** — Telegram Test
- Sendet Test-Nachricht via `send_telegram_message()`
- JSON-Response: `{"success": true}` oder `{"success": false, "error": "..."}`

### Task 2 — `kuasarr/providers/notifications.py` anpassen

`send_discord_message()` um `case="test"` erweitern:
```python
elif case == "test":
    description = 'This is a test notification from Kuasarr.'
    fields = None
```

Außerdem: Aktuell wird `send_telegram_message()` immer aufgerufen wenn Discord aufgerufen wird (Zeile 148). Das ist inkonsistent. Verhalten beibehalten aber sicherstellen, dass Test-Nachrichten korrekt funktionieren.

### Task 3 — `kuasarr/api/__init__.py` — Route registrieren + Button

1. Import hinzufügen: `from kuasarr.api.notifications import setup_notifications_routes`
2. Aufruf in `get_api()`: `setup_notifications_routes(app, shared_state)`
3. Quick-Action-Button im Index hinzufügen:
   ```html
   <button class="action-btn" onclick="location.href='/notifications'">
       <span class="action-icon">🔔</span>
       <span class="action-text">Notifications</span>
   </button>
   ```

## Dateistruktur nach Sprint 6

```
kuasarr/api/notifications/
└── __init__.py      (NEU)
```

## Sicherheitsanforderungen

- Test-Endpoints: POST (nicht GET) um CSRF zu vermeiden
- Webhook-URLs und Tokens: Maskiert anzeigen (type=password), nur updaten wenn nicht leer
- Kein XSS: `html.escape()` für alle Nutzereingaben die in HTML gerendert werden
- Auth: Die Seite `/notifications` wird durch das globale `webui_basic_auth` Hook geschützt (keine zusätzliche Implementierung nötig)

## Reihenfolge der Implementierung

1. Task 2: notifications.py um `case="test"` erweitern
2. Task 1: `kuasarr/api/notifications/__init__.py` erstellen
3. Task 3: `kuasarr/api/__init__.py` erweitern

## Versionsbump

Version in `version.json` und `Hier_Version_Ändern.txt` auf **1.15.0** anheben.
