# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

import re
from contextlib import contextmanager

from bottle import request, response

from kuasarr.constants import NOTIFICATION_PROVIDERS, KUASARR_AVATAR
from kuasarr.providers.log import info
from kuasarr.providers.notifications.helpers.message_builder import (
    build_notification_message,
)
from kuasarr.providers.notifications.helpers.notification_types import (
    NotificationType,
    get_user_configurable_notification_types,
)
from kuasarr.storage.config import Config
from kuasarr.storage.sqlite_database import DataBase

NOTIFICATION_TYPES = get_user_configurable_notification_types()
NOTIFICATION_SETTINGS_TABLE = "notification_settings"

# Schluessel fuer die Schalter, die nicht an einen NotificationType gebunden
# sind: der globale Schalter der WebUI und der Enabled-Schalter je Provider.
NOTIFICATION_GLOBAL_ENABLED_KEY = "notifications_global_enabled"
NOTIFICATION_PROVIDER_ENABLED_KEY_PREFIX = "notifications_provider_enabled_"


def _notification_toggle_key(provider, notification_type):
    return f"{provider}_{notification_type.value}"


def _notification_silent_key(provider, notification_type):
    return f"{provider}_{notification_type.value}_silent"


def notification_provider_enabled_key(provider):
    return f"{NOTIFICATION_PROVIDER_ENABLED_KEY_PREFIX}{provider}"


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _read_notification_setting(notification_settings_db, key, default=True):
    stored_value = notification_settings_db.retrieve(key)
    return _coerce_bool(stored_value, default)


def _read_notification_toggle(notification_settings_db, key):
    return _read_notification_setting(notification_settings_db, key, default=True)


def _read_notification_silent(notification_settings_db, key):
    return _read_notification_setting(notification_settings_db, key, default=False)


def read_notification_global_enabled(notification_settings_db, default=True):
    """Liest den globalen Benachrichtigungsschalter der WebUI."""
    return _read_notification_setting(
        notification_settings_db,
        NOTIFICATION_GLOBAL_ENABLED_KEY,
        default=default,
    )


def read_notification_provider_enabled(
    notification_settings_db, provider, default=True
):
    """Liest den Enabled-Schalter eines Providers."""
    return _read_notification_setting(
        notification_settings_db,
        notification_provider_enabled_key(provider),
        default=default,
    )


def _read_notification_settings():
    notification_config = Config("Notifications")
    notification_settings_db = DataBase(NOTIFICATION_SETTINGS_TABLE)

    settings = {
        "discord_webhook": notification_config.get("discord_webhook") or "",
        "telegram_bot_token": notification_config.get("telegram_token") or "",
        "telegram_chat_id": notification_config.get("telegram_chat_id") or "",
        "toggles": {"discord": {}, "telegram": {}},
        "silent": {"discord": {}, "telegram": {}},
        # Hauptschalter und Provider-Schalter gehoeren in den Laufzeitzustand,
        # weil der Versandweg ausschliesslich `shared_state.values` liest. Ohne
        # diese Spiegelung wuerden die Schalter in der Datenbank landen, von
        # `GET /api/notifications` zurueckgelesen und in der Oberflaeche
        # angezeigt - ohne die Zustellung je zu beeinflussen.
        "global_enabled": read_notification_global_enabled(
            notification_settings_db
        ),
        "provider_enabled": {
            provider: read_notification_provider_enabled(
                notification_settings_db, provider
            )
            for provider in NOTIFICATION_PROVIDERS
        },
    }

    for provider in NOTIFICATION_PROVIDERS:
        for notification_type in NOTIFICATION_TYPES:
            case_key = notification_type.value
            settings["toggles"][provider][case_key] = _read_notification_toggle(
                notification_settings_db,
                _notification_toggle_key(provider, notification_type),
            )
            settings["silent"][provider][case_key] = _read_notification_silent(
                notification_settings_db,
                _notification_silent_key(provider, notification_type),
            )

    return settings


def _validate_notification_provider_credentials(
    discord_webhook,
    telegram_bot_token,
    telegram_chat_id,
):
    discord_webhook_pattern = r"^https://discord\.com/api/webhooks/\d+/[A-Za-z0-9_-]+$"
    telegram_token_pattern = r"^\d+:[A-Za-z0-9_-]+$"

    if discord_webhook and not re.match(discord_webhook_pattern, discord_webhook):
        return "Invalid Discord Webhook URL"

    if telegram_bot_token or telegram_chat_id:
        if not telegram_bot_token or not telegram_chat_id:
            return "Telegram setup requires both bot token and chat ID"
        if not re.match(telegram_token_pattern, telegram_bot_token):
            return "Invalid Telegram bot token format"

    return None


def refresh_notification_settings(shared_state, backfill_defaults=False):
    del backfill_defaults

    settings = _read_notification_settings()

    shared_state.update("notification_settings", settings)

    return settings


def initialize_notification_settings(shared_state):
    return refresh_notification_settings(shared_state)


def get_notification_settings_data(shared_state):
    settings = refresh_notification_settings(shared_state)
    return {"success": True, "settings": settings}


def save_notification_settings(shared_state):
    data = request.json
    if not isinstance(data, dict):
        return {"success": False, "message": "Invalid JSON payload"}

    discord_webhook = str(data.get("discord_webhook", "")).strip()
    telegram_bot_token = str(data.get("telegram_bot_token", "")).strip()
    telegram_chat_id = str(data.get("telegram_chat_id", "")).strip()
    toggles = data.get("toggles") if isinstance(data.get("toggles"), dict) else {}
    silent = data.get("silent") if isinstance(data.get("silent"), dict) else {}

    validation_error = _validate_notification_provider_credentials(
        discord_webhook,
        telegram_bot_token,
        telegram_chat_id,
    )
    if validation_error:
        return {"success": False, "message": validation_error}

    notification_settings_db = DataBase(NOTIFICATION_SETTINGS_TABLE)

    for provider in NOTIFICATION_PROVIDERS:
        provider_toggles = toggles.get(provider)
        provider_silent = silent.get(provider)
        for notification_type in NOTIFICATION_TYPES:
            enabled_key = _notification_toggle_key(provider, notification_type)
            current_enabled = _read_notification_toggle(
                notification_settings_db,
                enabled_key,
            )
            if (
                isinstance(provider_toggles, dict)
                and notification_type.value in provider_toggles
            ):
                next_enabled = _coerce_bool(
                    provider_toggles.get(notification_type.value),
                    current_enabled,
                )
            else:
                next_enabled = current_enabled
            notification_settings_db.update_store(
                enabled_key, "true" if next_enabled else "false"
            )

            silent_key = _notification_silent_key(provider, notification_type)
            current_silent = _read_notification_silent(
                notification_settings_db,
                silent_key,
            )
            if (
                isinstance(provider_silent, dict)
                and notification_type.value in provider_silent
            ):
                next_silent = _coerce_bool(
                    provider_silent.get(notification_type.value),
                    current_silent,
                )
            else:
                next_silent = current_silent
            notification_settings_db.update_store(
                silent_key, "true" if next_silent else "false"
            )

    settings = refresh_notification_settings(shared_state)

    return {
        "success": True,
        "message": "Notification settings saved successfully",
        "settings": settings,
    }


# Der Test benutzt die Einstellungen aus dem Request, nicht die gespeicherten.
_TEST_SETTING_KEYS = {
    "webhook_url": "discord_webhook",
    "bot_token": "telegram_bot_token",
    "chat_id": "telegram_chat_id",
}


def _build_test_settings(stored_settings, provided_settings):
    """Mischt die uebergebenen Einstellungen mit den gespeicherten.

    Leere oder fehlende Felder fallen auf die gespeicherten Werte zurueck:
    ein halb ausgefuelltes Formular soll testbar sein, ohne dass ein
    Nachbarfeld aus der alten Konfiguration stammen muss.
    """
    settings = dict(stored_settings or {})
    if not isinstance(provided_settings, dict):
        return settings

    for provided_key, stored_key in _TEST_SETTING_KEYS.items():
        if provided_key not in provided_settings:
            continue
        value = str(provided_settings.get(provided_key) or "").strip()
        if value:
            settings[stored_key] = value

    return settings


@contextmanager
def _temporary_notification_settings(shared_state, settings):
    """Legt die Test-Zugangsdaten fuer die Dauer des Tests in den Shared State.

    Die Provider (``discord.send`` / ``telegram.send``) lesen ihre
    Zugangsdaten ausschliesslich aus ``shared_state``.  Damit der Testknopf
    prueft, was der Nutzer gerade eingetragen hat, werden die Zugangsdaten
    hier kurzzeitig ueberschrieben und danach unveraendert zurueckgesetzt -
    gespeichert wird dabei nichts.
    """
    values = getattr(shared_state, "values", None)
    if not isinstance(values, dict):
        yield
        return

    previous = values.get("notification_settings")
    merged = dict(previous) if isinstance(previous, dict) else {}
    for stored_key in _TEST_SETTING_KEYS.values():
        merged[stored_key] = settings.get(stored_key, "") or ""

    values["notification_settings"] = merged
    try:
        yield
    finally:
        if previous is None:
            values.pop("notification_settings", None)
        else:
            values["notification_settings"] = previous


def send_notification_test(shared_state, payload=None):
    """Sendet eine Testnachricht an einen Provider.

    ``payload`` ist der bereits gelesene Request-Body
    (``{"provider": ..., "settings": {...}}``).  Wird er nicht uebergeben,
    wird er - wie bisher - direkt aus dem Request gelesen.
    """
    if payload is None:
        payload = request.json
    if not isinstance(payload, dict):
        return {"success": False, "message": "Invalid JSON payload"}

    provider = str(payload.get("provider", "")).strip().lower()
    if provider not in NOTIFICATION_PROVIDERS:
        return {
            "success": False,
            "message": (
                f"Unknown provider '{payload.get('provider', '')}'. "
                f"Supported providers: {', '.join(NOTIFICATION_PROVIDERS)}"
            ),
        }

    settings = _build_test_settings(
        refresh_notification_settings(shared_state),
        payload.get("settings"),
    )
    title = "Kuasarr Notification Test"
    test_image_url = KUASARR_AVATAR

    if provider == "discord":
        if not settings["discord_webhook"]:
            return {
                "success": False,
                "message": "Discord webhook is not configured",
            }
        from kuasarr.providers.notifications import discord

        message = build_notification_message(
            shared_state,
            title=title,
            case=NotificationType.TEST,
            details={"provider": "Discord"},
            image_url=test_image_url,
        )
        if message is None:
            return {"success": False, "message": "Failed to build Discord test message"}

        try:
            with _temporary_notification_settings(shared_state, settings):
                sent = discord.send(shared_state, message, silent=False)
        except Exception as e:
            # Der Grund wandert ins Log, nicht in die Antwort: eine
            # Exception kann URLs mit Token, Pfade oder Antwortkoepfe des
            # Providers enthalten. Alles davon steht in ``kuasarr.log``.
            info(f"Discord test notification error: {e}")
            return {
                "success": False,
                "message": "Failed to send Discord test message",
            }
        if sent:
            return {"success": True, "message": "Discord test message sent"}
        return {
            "success": False,
            "message": "Failed to send Discord test message",
        }

    if not settings["telegram_bot_token"] or not settings["telegram_chat_id"]:
        return {
            "success": False,
            "message": "Telegram bot token and chat ID are required",
        }

    from kuasarr.providers.notifications import telegram

    message = build_notification_message(
        shared_state,
        title=title,
        case=NotificationType.TEST,
        details={"provider": "Telegram"},
        image_url=test_image_url,
    )
    if message is None:
        return {"success": False, "message": "Failed to build Telegram test message"}

    telegram_destination = None
    try:
        with _temporary_notification_settings(shared_state, settings):
            sent = telegram.send(shared_state, message, silent=False)
            if not sent:
                telegram_destination = telegram.inspect_destination(shared_state)
    except Exception as e:
        # Siehe Discord weiter oben: die Exception wandert ins Log, der
        # Testknopf bekommt eine Meldung ohne Interna.
        info(f"Telegram test notification error: {e}")
        return {
            "success": False,
            "message": "Failed to send Telegram test message",
        }
    if sent:
        return {"success": True, "message": "Telegram test message sent"}

    destination_message = telegram_destination.get("message") if telegram_destination else None
    if destination_message:
        return {
            "success": False,
            "message": f"Failed to send Telegram test message: {destination_message}",
        }
    return {"success": False, "message": "Failed to send Telegram test message"}
