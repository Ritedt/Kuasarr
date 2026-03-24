# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""Notifications module for Kuasarr.

Unified interface for sending notifications to Discord and Telegram.
"""

from kuasarr.providers.log import info
from kuasarr.providers.notifications.helpers import resolve_poster_url
from kuasarr.providers.notifications.helpers.message_builder import (
    build_notification_message,
)
from kuasarr.providers.notifications.helpers.notification_types import (
    NotificationType,
    normalize_notification_type,
)


def _get_notification_settings(shared_state):
    settings = shared_state.values.get("notification_settings")
    return settings if isinstance(settings, dict) else {}


def _provider_case_enabled(shared_state, provider, notification_type):
    toggles = _get_notification_settings(shared_state).get("toggles")
    if not isinstance(toggles, dict):
        return True

    provider_toggles = toggles.get(provider)
    if not isinstance(provider_toggles, dict):
        return True

    return bool(provider_toggles.get(notification_type.value, True))


def _provider_case_silent(shared_state, provider, notification_type):
    silent_settings = _get_notification_settings(shared_state).get("silent")
    if not isinstance(silent_settings, dict):
        return False

    provider_silent = silent_settings.get(provider)
    if not isinstance(provider_silent, dict):
        return False

    return bool(provider_silent.get(notification_type.value, False))


def send_notification(
    shared_state, title, case, imdb_id=None, details=None, source=None
):
    """
    Send a notification to all configured providers (Discord, Telegram).

    Each provider is attempted independently — a failure in one does not block others.

    :param shared_state: Shared state object containing configuration.
    :param title: Title of the notification.
    :param case: A string representing the scenario (e.g., 'captcha', 'failed', 'unprotected').
    :param imdb_id: A string starting with "tt" followed by at least 7 digits, representing an object on IMDb
    :param details: A dictionary containing additional details, such as version and link for updates.
    :param source: Optional source of the notification, sent as a field in the embed.
    :return: True if at least one provider sent successfully, False otherwise.
    """
    from kuasarr.providers.notifications import discord, telegram

    notification_type = normalize_notification_type(case)
    if notification_type is None:
        info(f"Unknown notification case: {case}")
        return False

    notification_settings = _get_notification_settings(shared_state)
    has_discord = bool(notification_settings.get("discord_webhook"))
    has_telegram = bool(notification_settings.get("telegram_bot_token")) and bool(
        notification_settings.get("telegram_chat_id")
    )

    if not has_discord and not has_telegram:
        return False

    # Resolve poster image once for all providers.
    image_url = None
    if notification_type in (NotificationType.UNPROTECTED, NotificationType.CAPTCHA):
        image_url = resolve_poster_url(shared_state, title, imdb_id)

    message = build_notification_message(
        shared_state,
        title,
        notification_type,
        details=details,
        source=source,
        image_url=image_url,
    )
    if message is None:
        return False

    any_success = False

    if has_discord and _provider_case_enabled(
        shared_state, "discord", notification_type
    ):
        discord_silent = _provider_case_silent(
            shared_state, "discord", notification_type
        )
        try:
            if discord.send(shared_state, message, silent=discord_silent):
                any_success = True
        except Exception as e:
            info(f"Discord notification error: {e}")

    if has_telegram and _provider_case_enabled(
        shared_state, "telegram", notification_type
    ):
        telegram_silent = _provider_case_silent(
            shared_state, "telegram", notification_type
        )
        try:
            if telegram.send(shared_state, message, silent=telegram_silent):
                any_success = True
        except Exception as e:
            info(f"Telegram notification error: {e}")

    return any_success


# Backward compatibility shims for legacy notification functions
def send_discord_message(shared_state, title, case, imdb_id=None, details=None, source=None):
    """
    Legacy Discord notification function for backward compatibility.

    Sends a notification only to Discord (if configured).
    """
    from kuasarr.providers.notifications import discord

    notification_type = normalize_notification_type(case)
    if notification_type is None:
        info(f"Unknown notification case: {case}")
        return False

    notification_settings = _get_notification_settings(shared_state)
    if not notification_settings.get("discord_webhook"):
        return False

    # Resolve poster image
    image_url = None
    if notification_type in (NotificationType.UNPROTECTED, NotificationType.CAPTCHA):
        image_url = resolve_poster_url(shared_state, title, imdb_id)

    message = build_notification_message(
        shared_state,
        title,
        notification_type,
        details=details,
        source=source,
        image_url=image_url,
    )
    if message is None:
        return False

    try:
        return discord.send(shared_state, message, silent=False)
    except Exception as e:
        info(f"Discord notification error: {e}")
        return False


def send_telegram_message(shared_state, title, case, imdb_id=None, details=None, source=None):
    """
    Legacy Telegram notification function for backward compatibility.

    Sends a notification only to Telegram (if configured).
    """
    from kuasarr.providers.notifications import telegram

    notification_type = normalize_notification_type(case)
    if notification_type is None:
        info(f"Unknown notification case: {case}")
        return False

    notification_settings = _get_notification_settings(shared_state)
    if not notification_settings.get("telegram_bot_token") or not notification_settings.get("telegram_chat_id"):
        return False

    # Resolve poster image
    image_url = None
    if notification_type in (NotificationType.UNPROTECTED, NotificationType.CAPTCHA):
        image_url = resolve_poster_url(shared_state, title, imdb_id)

    message = build_notification_message(
        shared_state,
        title,
        notification_type,
        details=details,
        source=source,
        image_url=image_url,
    )
    if message is None:
        return False

    try:
        return telegram.send(shared_state, message, silent=False)
    except Exception as e:
        info(f"Telegram notification error: {e}")
        return False
