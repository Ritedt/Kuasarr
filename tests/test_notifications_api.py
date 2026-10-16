# -*- coding: utf-8 -*-
"""Tests fuer die Benachrichtigungs-API der React-WebUI.

Hintergrund: Die SPA sendet Event-Namen (``download_complete``, ...), das
Backend kannte nur die ``NotificationType``-Werte (``solved``, ``failed``...).
Die Speicherschleife uebernahm die Events ungeprueft, die Auswertung filterte
ueber ``NOTIFICATION_TYPES`` - die Schluessel passten nie.  Jedes angehakte
Event blieb wirkungslos, ohne jede Fehlermeldung.  Ausserdem wurden ``silent``,
``enabled`` und ``global_enabled`` beim Speichern bzw. beim Laden ignoriert.

Die Routen brauchen keinen echten Request: ``request``/``response`` sowie die
Storage-Abhaengigkeiten werden auf Modulebene ersetzt (Muster wie in
``test_provider_routes.py``).
"""

import json

import pytest

from kuasarr.api import notifications as notifications_api
from kuasarr.api.notifications import (
    SUPPORTED_WEBUI_EVENTS,
    UNSUPPORTED_WEBUI_EVENTS,
    WEBUI_EVENT_NOTIFICATION_TYPES,
    setup_notifications_routes,
)
from kuasarr.providers.notifications.helpers.notification_types import (
    NotificationType,
)
from kuasarr.storage.setup import notifications as notifications_storage


DISCORD_WEBHOOK = "https://discord.com/api/webhooks/111/stored-webhook"
NEW_DISCORD_WEBHOOK = "https://discord.com/api/webhooks/999/typed-just-now"
TELEGRAM_TOKEN = "123456:STOREDTOKEN"
TELEGRAM_CHAT_ID = "-100123456789"
NEW_TELEGRAM_TOKEN = "987654:NEWTOKEN"


# ---------------------------------------------------------------------------
# Doubletten fuer Request, Response, Config und Datenbank
# ---------------------------------------------------------------------------


class _FakeApp:
    """Collects whatever setup_notifications_routes registers.

    Routen werden nach Methode und Pfad unterschieden - ``/api/notifications``
    existiert als GET und als POST.
    """

    def __init__(self):
        self.routes = {}

    def _register(self, method, path):
        def decorator(fn):
            self.routes[(method, path)] = fn
            return fn
        return decorator

    def get(self, path):
        return self._register("GET", path)

    def post(self, path):
        return self._register("POST", path)


class _FakeBody:
    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return self._raw


class _FakeRequest:
    def __init__(self, payload=None, method="POST", path="/api/notifications"):
        self.method = method
        self.headers = {}
        self.forms = {}
        self.path = path
        self.body = _FakeBody(
            b"" if payload is None else json.dumps(payload).encode("utf-8")
        )

    @property
    def json(self):
        return json.loads(self.body.read().decode("utf-8"))


class _FakeResponse:
    def __init__(self):
        self.status = 200
        self.content_type = "text/html"
        self.headers = {}

    def set_header(self, key, value):
        self.headers[key] = value


class _FakeConfig:
    """Ersetzt ``kuasarr.storage.config.Config``."""

    values = {}

    def __init__(self, section):
        self.section = section

    def get(self, key, default=None):
        return self.values.get(key, default)

    def save(self, key, value):
        self.values[key] = value


class _FakeDB:
    """Ersetzt ``kuasarr.storage.sqlite_database.DataBase``."""

    values = {}

    def __init__(self, table):
        self.table = table

    def retrieve(self, key):
        return self.values.get(key)

    def update_store(self, key, value):
        self.values[key] = value


class _FakeSharedState:
    def __init__(self):
        self.values = {}

    def update(self, key, value):
        self.values[key] = value


class _FakeHTTPResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_storage():
    _FakeConfig.values = {}
    _FakeDB.values = {}
    yield
    _FakeConfig.values = {}
    _FakeDB.values = {}


@pytest.fixture
def context(monkeypatch):
    """Registriert die Routen und patchet alle Abhaengigkeiten."""
    shared_state = _FakeSharedState()
    app = _FakeApp()
    fake_request = _FakeRequest()
    fake_response = _FakeResponse()

    for module in (notifications_api, notifications_storage):
        monkeypatch.setattr(module, "Config", _FakeConfig)
        monkeypatch.setattr(module, "DataBase", _FakeDB)

    monkeypatch.setattr(notifications_api, "request", fake_request)
    monkeypatch.setattr(notifications_api, "response", fake_response)

    setup_notifications_routes(app, shared_state)

    class _Context:
        pass

    ctx = _Context()
    ctx.app = app
    ctx.shared_state = shared_state
    ctx.request = fake_request
    ctx.response = fake_response
    ctx.config = _FakeConfig
    ctx.db = _FakeDB
    return ctx


def _post(ctx, payload):
    """Setzt den Request-Body und ruft die Save-Route auf."""
    ctx.request.body = _FakeBody(json.dumps(payload).encode("utf-8"))
    return json.loads(ctx.app.routes[("POST", "/api/notifications")]())


def _post_test(ctx, payload):
    ctx.request.body = _FakeBody(json.dumps(payload).encode("utf-8"))
    raw = ctx.app.routes[("POST", "/api/notifications/test")]()
    return json.loads(raw)


def _seed_stored_credentials(ctx):
    ctx.config.values["discord_webhook"] = DISCORD_WEBHOOK
    ctx.config.values["telegram_token"] = TELEGRAM_TOKEN
    ctx.config.values["telegram_chat_id"] = TELEGRAM_CHAT_ID


# ---------------------------------------------------------------------------
# 1) Jedes gueltige WebUI-Event wird akzeptiert und korrekt abgebildet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "event,notification_type",
    sorted(WEBUI_EVENT_NOTIFICATION_TYPES.items(), key=lambda item: item[0]),
)
def test_every_webui_event_maps_to_its_notification_type(
    context, event, notification_type
):
    """Das Event muss genau einen NotificationType-Toggle aktivieren."""
    payload = {
        "global_enabled": True,
        "configs": [
            {
                "provider": "discord",
                "enabled": True,
                "settings": {"webhook_url": DISCORD_WEBHOOK},
                "events": [event],
            }
        ],
    }

    result = _post(context, payload)

    assert context.response.status == 200, result
    for other in notifications_storage.NOTIFICATION_TYPES:
        key = f"discord_{other.value}"
        expected = "true" if other is notification_type else "false"
        assert _FakeDB.values[key] == expected, (
            f"{key} sollte {expected} sein, war {_FakeDB.values[key]!r}"
        )


def test_webui_events_cover_all_fired_notification_types(context):
    """Die Tabelle bildet genau die Typen ab, die das Backend wirklich feuert.

    ``DISABLED`` und ``UPDATE`` haben zwar einen NotificationType, werden aber
    nirgends im Repo ausgeloest (``send_*_message(..., case=...)`` feuert nur
    unprotected, captcha, solved, failed).  Sie bekommen deshalb bewusst kein
    WebUI-Event - ein Toggle, den nie etwas ausloest, waere wieder eine stille
    Verwerfung.
    """
    assert set(WEBUI_EVENT_NOTIFICATION_TYPES.values()) == {
        NotificationType.UNPROTECTED,
        NotificationType.CAPTCHA,
        NotificationType.SOLVED,
        NotificationType.FAILED,
    }
    assert NotificationType.TEST not in WEBUI_EVENT_NOTIFICATION_TYPES.values()
    assert NotificationType.DISABLED not in WEBUI_EVENT_NOTIFICATION_TYPES.values()
    assert NotificationType.UPDATE not in WEBUI_EVENT_NOTIFICATION_TYPES.values()
    assert SUPPORTED_WEBUI_EVENTS


def test_get_returns_webui_event_names(context):
    """Der GET liefert die Event-Namen der WebUI, nicht die NotificationType.

    Gespeichert wird nach ``NotificationType`` (der Aufrufstelle), das
    ``events``-Feld der Antwort trägt die Namen, mit denen die SPA ihre
    Kaestchen beschriftet. Genau diese Umbenennung war das Problem:
    vorher bekam die WebUI Enum-Werte und zeigte alles als aktiv an.
    """
    # Ohne gespeicherten Wert gilt ``True`` - deshalb erst alles aus.
    for notification_type in set(WEBUI_EVENT_NOTIFICATION_TYPES.values()):
        _FakeDB.values[f"discord_{notification_type.value}"] = "false"
    _FakeDB.values[
        f"discord_{WEBUI_EVENT_NOTIFICATION_TYPES['captcha_required'].value}"
    ] = "true"
    _FakeConfig.values["discord_webhook"] = DISCORD_WEBHOOK

    raw = json.loads(context.app.routes[("GET", "/api/notifications")]())
    events = raw["data"]["configs"][0]["events"]

    assert events == ["captcha_required"]
    assert "captcha" not in events
    # Und nichts davon ist ein Enum-Wert: die WebUI vergleicht die Namen
    # gegen ihre eigenen Labels, nicht gegen ``NotificationType``.
    assert not any(
        event in {t.value for t in NotificationType} for event in events
    )


# ---------------------------------------------------------------------------
# 2) Unbekanntes Event -> 400, Konfiguration bleibt unangetastet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "event",
    [
        "download_banana",
        "solved",
        "",
        None,
    ],
)
def test_unknown_event_is_rejected_with_400(context, event):
    _seed_stored_credentials(context)
    _FakeDB.values["discord_solved"] = "true"
    config_before = dict(_FakeConfig.values)
    db_before = dict(_FakeDB.values)

    result = _post(context, {
        "global_enabled": True,
        "configs": [
            {
                "provider": "discord",
                "enabled": True,
                "settings": {"webhook_url": "https://discord.com/api/webhooks/1/new"},
                "events": [event],
            }
        ],
    })

    assert context.response.status == 400
    assert "error" in result and result["error"]["message"]
    assert str(event) in result["error"]["message"]
    assert _FakeConfig.values == config_before, "Config wurde doch veraendert"
    assert _FakeDB.values == db_before, "Datenbank wurde doch veraendert"


def test_unsupported_event_names_are_rejected_with_an_explanation(context):
    """``jd_connected`` hat keine Entsprechung im Backend - das muss sagen."""
    for event, reason in UNSUPPORTED_WEBUI_EVENTS.items():
        _FakeConfig.values = {}
        _FakeDB.values = {}
        context.response.status = 200

        result = _post(context, {
            "configs": [
                {
                    "provider": "discord",
                    "enabled": True,
                    "settings": {"webhook_url": DISCORD_WEBHOOK},
                    "events": [event],
                }
            ],
        })

        assert context.response.status == 400
        assert event in result["error"]["message"]
        assert reason.split(" has ")[0] in result["error"]["message"]


# ---------------------------------------------------------------------------
# 3) ``silent`` ueberlebt ein Speichern
# ---------------------------------------------------------------------------


def test_silent_settings_survive_a_save(context):
    _seed_stored_credentials(context)
    _FakeDB.values["discord_solved_silent"] = "true"
    _FakeDB.values["telegram_failed_silent"] = "true"

    result = _post(context, {
        "global_enabled": True,
        "configs": [
            {
                "provider": "discord",
                "enabled": True,
                "settings": {"webhook_url": DISCORD_WEBHOOK},
                "events": ["download_complete"],
            },
            {
                "provider": "telegram",
                "enabled": True,
                "settings": {
                    "bot_token": TELEGRAM_TOKEN,
                    "chat_id": TELEGRAM_CHAT_ID,
                },
                "events": ["download_failed"],
            },
        ],
    })

    assert context.response.status == 200, result
    assert _FakeDB.values["discord_solved_silent"] == "true", (
        "pro-Event-Mute wurde beim Speichern geloescht"
    )
    assert _FakeDB.values["telegram_failed_silent"] == "true"


def test_silent_survives_a_save_without_any_config(context):
    """Auch ein leeres Speichern darf die Mute-Einstellungen nicht loeschen."""
    _seed_stored_credentials(context)
    _FakeDB.values["discord_captcha_silent"] = "true"

    _post(context, {"global_enabled": True, "configs": []})

    assert _FakeDB.values["discord_captcha_silent"] == "true"


# ---------------------------------------------------------------------------
# 4) ``enabled: false`` bleibt erhalten
# ---------------------------------------------------------------------------


def test_disabled_provider_stays_disabled(context):
    _seed_stored_credentials(context)

    result = _post(context, {
        "global_enabled": True,
        "configs": [
            {
                "provider": "discord",
                "enabled": False,
                "settings": {"webhook_url": DISCORD_WEBHOOK},
                "events": ["download_complete"],
            },
            {
                "provider": "telegram",
                "enabled": True,
                "settings": {
                    "bot_token": TELEGRAM_TOKEN,
                    "chat_id": TELEGRAM_CHAT_ID,
                },
                "events": ["download_failed"],
            },
        ],
    })

    assert context.response.status == 200, result
    assert _FakeDB.values["notifications_provider_enabled_discord"] == "false"
    assert _FakeDB.values["notifications_provider_enabled_telegram"] == "true"

    loaded = json.loads(context.app.routes[("GET", "/api/notifications")]())["data"]
    by_provider = {cfg["provider"]: cfg["enabled"] for cfg in loaded["configs"]}
    assert by_provider["discord"] is False
    assert by_provider["telegram"] is True


def test_enabled_defaults_to_true_for_a_fresh_provider(context):
    _FakeConfig.values["discord_webhook"] = DISCORD_WEBHOOK

    _post(context, {
        "configs": [
            {
                "provider": "discord",
                "settings": {"webhook_url": DISCORD_WEBHOOK},
                "events": [],
            }
        ],
    })

    loaded = json.loads(context.app.routes[("GET", "/api/notifications")]())["data"]
    assert loaded["configs"][0]["enabled"] is True


# ---------------------------------------------------------------------------
# 5) ``global_enabled: false`` bleibt erhalten
# ---------------------------------------------------------------------------


def test_global_enabled_false_survives_without_configs(context):
    result = _post(context, {"global_enabled": False, "configs": []})

    assert context.response.status == 200, result
    assert _FakeDB.values["notifications_global_enabled"] == "false"

    loaded = json.loads(context.app.routes[("GET", "/api/notifications")]())["data"]
    assert loaded["global_enabled"] is False
    assert loaded["configs"] == []


def test_global_enabled_true_is_remembered(context):
    _seed_stored_credentials(context)

    _post(context, {
        "global_enabled": True,
        "configs": [
            {
                "provider": "discord",
                "enabled": True,
                "settings": {"webhook_url": DISCORD_WEBHOOK},
                "events": ["package_added"],
            }
        ],
    })

    loaded = json.loads(context.app.routes[("GET", "/api/notifications")]())["data"]
    assert loaded["global_enabled"] is True
    assert loaded["configs"][0]["events"] == ["package_added"]


# ---------------------------------------------------------------------------
# 6) Unbekannte Provider -> 400
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["pushover", "email", "webhook"])
def test_unknown_provider_is_rejected_with_400(context, provider):
    config_before = dict(_FakeConfig.values)
    db_before = dict(_FakeDB.values)

    result = _post(context, {
        "configs": [
            {
                "provider": provider,
                "enabled": True,
                "settings": {"url": "https://example.invalid/hook"},
                "events": ["download_complete"],
            }
        ],
    })

    assert context.response.status == 400
    assert provider in result["error"]["message"]
    assert "discord" in result["error"]["message"]
    assert _FakeConfig.values == config_before
    assert _FakeDB.values == db_before


# ---------------------------------------------------------------------------
# 7) Die Test-Route liefert die ``data``-Huelle
# ---------------------------------------------------------------------------


def test_test_route_returns_the_data_envelope(context, monkeypatch):
    from kuasarr.providers.notifications import discord as discord_provider

    _seed_stored_credentials(context)
    monkeypatch.setattr(
        discord_provider.requests,
        "post",
        lambda *args, **kwargs: _FakeHTTPResponse(status_code=204),
    )

    result = _post_test(context, {"provider": "discord", "settings": {}})

    assert context.response.status == 200
    assert "data" in result, "Die Antwort muss in einer data-Huelle stecken"
    assert result["data"]["success"] is True
    assert "Discord" in result["data"]["message"]


def test_test_route_reports_failures_readably(context):
    """Ohne Webhook muss der Grund fuer den Nutzer lesbar kommen."""
    _FakeConfig.values.pop("discord_webhook", None)

    body = _post_test(context, {"provider": "discord", "settings": {}})

    assert context.response.status == 400
    assert body["error"]["message"]
    assert "discord" in body["error"]["message"].lower()
    # Die Meldung steckt in error.message - so liest es fetchApi der WebUI aus.
    assert "success" not in body


# ---------------------------------------------------------------------------
# 8) Die Test-Route benutzt die uebergebenen Einstellungen
# ---------------------------------------------------------------------------


def test_test_route_uses_the_submitted_settings_not_the_saved_ones(
    context, monkeypatch
):
    """Der Nutzer traegt eine neue Webhook-URL ein - genau die wird getestet."""
    from kuasarr.providers.notifications import discord as discord_provider

    _seed_stored_credentials(context)
    calls = []

    def _fake_post(url, data=None, headers=None, timeout=None):
        calls.append({"url": url, "data": json.loads(data)})
        return _FakeHTTPResponse(status_code=204)

    monkeypatch.setattr(discord_provider.requests, "post", _fake_post)

    result = _post_test(context, {
        "provider": "discord",
        "settings": {"webhook_url": NEW_DISCORD_WEBHOOK},
    })

    assert context.response.status == 200, result
    assert calls, "Der Test hat den Discord-Webhook gar nicht aufgerufen"
    assert calls[0]["url"] == NEW_DISCORD_WEBHOOK, (
        "Es wurde die gespeicherte URL getestet statt der eingegebenen"
    )
    assert DISCORD_WEBHOOK not in calls[0]["url"]

    # Der Test darf nichts speichern.
    assert _FakeConfig.values["discord_webhook"] == DISCORD_WEBHOOK
    assert context.shared_state.values["notification_settings"][
        "discord_webhook"
    ] == DISCORD_WEBHOOK


def test_test_route_falls_back_to_saved_neighbour_fields(context, monkeypatch):
    """Ein halb ausgefuelltes Telegram-Formular bleibt testbar."""
    from kuasarr.providers.notifications import telegram as telegram_provider

    _seed_stored_credentials(context)
    calls = []

    def _fake_get(url, params=None, timeout=None, headers=None):
        # Der echte Provider fragt beim Test-Versuch auch das Avatar-Bild
        # ab (`_build_photo_upload`, mit `headers`). Der laeuft hier in den
        # Ausnahme-Zweig und landet damit im Text-Fallback - genau den
        # will der Test sehen.
        if url.endswith("/getChat"):
            payload = {"ok": True, "result": {"type": "private"}}
        elif url.endswith("/getMe"):
            payload = {"ok": True, "result": {"id": 42}}
        elif url.startswith("https://api.telegram.org"):
            payload = {"ok": True, "result": {"status": "administrator"}}
        else:
            raise AssertionError(f"Unerwarteter GET: {url}")
        return _FakeHTTPResponse(payload=payload)

    def _fake_post(url, data=None, files=None, timeout=None):
        calls.append({"url": url, "data": data})
        return _FakeHTTPResponse(payload={"ok": True})

    monkeypatch.setattr(telegram_provider.requests, "get", _fake_get)
    monkeypatch.setattr(telegram_provider.requests, "post", _fake_post)

    result = _post_test(context, {
        "provider": "telegram",
        "settings": {"bot_token": NEW_TELEGRAM_TOKEN},
    })

    assert context.response.status == 200, result
    assert calls, "Der Telegram-Test hat nichts gesendet"
    send_calls = [call for call in calls if call["data"] is not None]
    assert send_calls, "Es wurde nur inspiziert, aber nichts gesendet"
    # Das Avatar-Bild laesst der Test bewusst nicht abrufbar, deshalb
    # landet die Nachricht im Text-Fallback - der Token und die
    # gespeicherte Chat-ID muessen trotzdem stimmen.
    assert send_calls[0]["url"] == (
        f"https://api.telegram.org/bot{NEW_TELEGRAM_TOKEN}/sendMessage"
    )
    assert send_calls[0]["data"]["chat_id"] == TELEGRAM_CHAT_ID


def test_test_route_rejects_unknown_provider(context):
    _post_test(context, {"provider": "pushover", "settings": {}})

    assert context.response.status == 400


# ---------------------------------------------------------------------------
# Die Schalter muessen beim Senden greifen, nicht nur beim Speichern
# ---------------------------------------------------------------------------


class _RuntimeState:
    """Minimaler Shared State: nur die Felder, die der Nachrichtenbau liest."""

    def __init__(self, settings):
        self.values = {
            "notification_settings": settings,
            "external_address": "http://kuasarr.invalid",
            "internal_address": "http://kuasarr.invalid",
            "timezone": "Europe/Berlin",
        }


def _patch_provider(monkeypatch, sent):
    """Ersetzt Discord und Telegram durch Attrappen, die mitzaehlen."""

    class _Discord:
        @staticmethod
        def send(shared_state, message, silent=False):
            sent.append(("discord", message))
            return True

    class _Telegram:
        @staticmethod
        def send(shared_state, message, silent=False):
            sent.append(("telegram", message))
            return True

    import kuasarr.providers.notifications as notifications

    monkeypatch.setattr(notifications, "discord", _Discord, raising=False)
    monkeypatch.setattr(notifications, "telegram", _Telegram, raising=False)
    return notifications


def _settings(**overrides):
    base = {
        "discord_webhook": DISCORD_WEBHOOK,
        "telegram_bot_token": TELEGRAM_TOKEN,
        "telegram_chat_id": TELEGRAM_CHAT_ID,
    }
    base.update(overrides)
    return base


def test_global_enabled_false_suppresses_every_provider(monkeypatch):
    """Der Hauptschalter war gespeichert, beim Senden aber nicht gelesen.

    Die WebUI zeigte "aus", jede Benachrichtigung ging trotzdem raus - ein
    Zustand, den es gar nicht gibt.
    """
    sent = []
    module = _patch_provider(monkeypatch, sent)
    state = _RuntimeState(_settings(global_enabled=False))

    assert module.send_notification(state, "Ein Titel", "captcha") is False
    assert sent == []


def test_a_disabled_provider_is_skipped_but_the_other_one_still_sends(
        monkeypatch):
    sent = []
    module = _patch_provider(monkeypatch, sent)
    state = _RuntimeState(_settings(provider_enabled={"discord": False,
                                                       "telegram": True}))

    assert module.send_notification(state, "Ein Titel", "captcha") is True
    assert [provider for provider, _ in sent] == ["telegram"]


def test_an_unknown_provider_key_does_not_disable_anything(monkeypatch):
    """Ein Provider ohne Eintrag bleibt an.

    Sonst wuerde eine aeltere Config ohne ``provider_enabled`` stillschweigend
    alles abschalten, weil ``.get`` hier fehlende Schluessel liefert.
    """
    sent = []
    module = _patch_provider(monkeypatch, sent)
    state = _RuntimeState(_settings(provider_enabled={}))

    assert module.send_notification(state, "Ein Titel", "captcha") is True
    assert sorted(provider for provider, _ in sent) == ["discord", "telegram"]


def test_per_type_toggles_still_win_over_the_master_switches(monkeypatch):
    """Die drei Ebenen bleiben unabhaengig voneinander."""
    sent = []
    module = _patch_provider(monkeypatch, sent)
    state = _RuntimeState(_settings(
        global_enabled=True,
        provider_enabled={"discord": True, "telegram": True},
        toggles={"discord": {"solved": False}, "telegram": {}},
    ))

    assert module.send_notification(state, "Ein Titel", "solved") is True
    assert [provider for provider, _ in sent] == ["telegram"]


def test_the_legacy_shims_ignore_the_switches(monkeypatch):
    """Die alten Direktaufrufe sind die Testknöpfe der WebUI.

    ``POST /api/notifications/test/discord`` ruft ``send_discord_message``
    auf - dieser Knopf soll auch dann etwas schicken, wenn der eigentliche
    Kanal abgeschaltet ist, sonst koennte der Nutzer sein Setup nicht mehr
    pruefen.
    """
    sent = []
    module = _patch_provider(monkeypatch, sent)
    state = _RuntimeState(_settings(global_enabled=False,
                                    provider_enabled={"discord": False,
                                                      "telegram": False}))

    assert module.send_discord_message(state, "Ein Titel", "captcha") is True
    assert module.send_telegram_message(state, "Ein Titel", "captcha") is True
    assert sorted(provider for provider, _ in sent) == ["discord", "telegram"]


def test_loading_the_settings_mirrors_the_switches_into_the_runtime_state(
        context, monkeypatch):
    """Was gespeichert wurde, muss nach dem Laden wieder im Shared State stehen.

    Sonst waere zwar die WebUI-Anzeige korrekt, der Versand aber trotzdem an -
    die beiden Seiten laufen aneinander vorbei.
    """
    _post(context, {
        "global_enabled": False,
        "configs": [
            {"provider": "discord", "webhook_url": NEW_DISCORD_WEBHOOK,
             "silent": []},
            {"provider": "telegram", "bot_token": TELEGRAM_TOKEN,
             "chat_id": TELEGRAM_CHAT_ID, "silent": []},
        ],
    })

    monkeypatch.setattr(
        notifications_storage, "read_notification_provider_enabled",
        lambda db, provider: provider != "discord",
    )

    runtime = notifications_storage._read_notification_settings()

    assert runtime["global_enabled"] is False
    assert runtime["provider_enabled"] == {"discord": False, "telegram": True}