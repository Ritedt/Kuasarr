# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""Discord notification provider for Kuasarr."""

import json

import requests

from kuasarr.constants import (
    KUASARR_AVATAR,
    SESSION_REQUEST_TIMEOUT_SECONDS,
    SUPPRESS_NOTIFICATIONS,
)
from kuasarr.providers.log import info
from kuasarr.providers.notifications.helpers.abstract_notification_formatter import (
    AbstractNotificationFormatter,
)
from kuasarr.providers.notifications.helpers.notification_message import (
    NotificationFactsEntry,
    NotificationLinkEntry,
    NotificationMessage,
    NotificationTextEntry,
    NotificationValueEntry,
)


class DiscordNotificationFormatter(AbstractNotificationFormatter):
    @staticmethod
    def _format_link(text, url, link_text=None):
        target_text = link_text or text
        if target_text and target_text in text:
            return text.replace(target_text, f"[{target_text}]({url})", 1)
        return f"[{text}]({url})"

    def render_text_entry(self, entry: NotificationTextEntry):
        return {"name": entry.title, "value": entry.text}

    def render_link_entry(self, entry: NotificationLinkEntry):
        return {
            "name": entry.title,
            "value": self._format_link(entry.text, entry.url, entry.link_text),
        }

    def render_facts_entry(self, entry: NotificationFactsEntry):
        return {
            "name": entry.title,
            "value": " | ".join(
                f"**{fact.label}:** {fact.value}" for fact in entry.facts
            ),
        }

    def render_value_entry(self, entry: NotificationValueEntry):
        return {"name": entry.title, "value": entry.value}

    def render_message(self, message: NotificationMessage):
        embed = {"title": message.title, "description": message.description}
        fields = self.render_entries(message.entries)
        if fields:
            embed["fields"] = fields

        if message.image_url:
            poster_object = {"url": message.image_url}
            embed["thumbnail"] = poster_object
            embed["image"] = poster_object
        elif message.thumbnail_url:
            embed["thumbnail"] = {"url": message.thumbnail_url}

        return embed


def _get_discord_webhook(shared_state):
    settings = shared_state.values.get("notification_settings")
    if not isinstance(settings, dict):
        return ""
    return str(settings.get("discord_webhook") or "").strip()


def send(shared_state, message, silent=True):
    """Send a rendered Discord webhook notification. Returns True on success."""
    webhook_url = _get_discord_webhook(shared_state)
    if not webhook_url:
        return False

    if not isinstance(message, NotificationMessage):
        info(f"Invalid Discord notification payload: {type(message).__name__}")
        return False

    embed = DiscordNotificationFormatter().render_message(message)
    data = {
        "username": "Kuasarr",
        "avatar_url": KUASARR_AVATAR,
        "embeds": [embed],
    }

    if silent:
        data["flags"] = SUPPRESS_NOTIFICATIONS

    response = requests.post(
        webhook_url,
        data=json.dumps(data),
        headers={"Content-Type": "application/json"},
        timeout=SESSION_REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code != 204:
        info(
            f"Failed to send message to Discord webhook. "
            f"Status code: {response.status_code}"
        )
        return False
    return True
