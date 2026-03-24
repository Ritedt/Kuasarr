# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""Telegram notification provider for Kuasarr."""

import json
from html import escape
from urllib.parse import urlparse

import requests

from kuasarr.constants import SESSION_REQUEST_TIMEOUT_SECONDS
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


def _get_telegram_credentials(shared_state):
    settings = shared_state.values.get("notification_settings")
    if not isinstance(settings, dict):
        return "", ""
    bot_token = str(settings.get("telegram_bot_token") or "").strip()
    chat_id = str(settings.get("telegram_chat_id") or "").strip()
    return bot_token, chat_id


def _escape_html_text(value):
    return escape(str(value), quote=False)


def _escape_html_attribute(value):
    return escape(str(value), quote=True)


def _get_photo_request_headers(shared_state, image_url):
    headers = {"Accept": "image/*,*/*;q=0.8"}
    user_agent = shared_state.values.get("user_agent")
    if user_agent:
        headers["User-Agent"] = user_agent

    hostname = (urlparse(image_url).hostname or "").lower()
    if hostname.endswith("media-amazon.com") or hostname.endswith("media-imdb.com"):
        headers["Referer"] = "https://www.imdb.com/"

    return headers


def _build_photo_upload(shared_state, image_url):
    response = requests.get(
        image_url,
        headers=_get_photo_request_headers(shared_state, image_url),
        timeout=SESSION_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip()
    if not content_type.startswith("image/"):
        raise ValueError(f"Unexpected poster content type: {content_type or 'unknown'}")

    image_bytes = response.content
    if not image_bytes:
        raise ValueError("Poster download returned an empty response")

    parsed_url = urlparse(image_url)
    filename = parsed_url.path.rsplit("/", 1)[-1] or "poster.jpg"
    if "." not in filename:
        filename += ".jpg"

    return {"photo": (filename, image_bytes, content_type)}


def _parse_json_response(response):
    try:
        return response.json()
    except ValueError:
        return {}


def _telegram_get(api_base_url, method, params):
    response = requests.get(
        f"{api_base_url}/{method}",
        params=params,
        timeout=SESSION_REQUEST_TIMEOUT_SECONDS,
    )
    return response, _parse_json_response(response)


def _telegram_post(api_base_url, method, payload, files=None):
    response = requests.post(
        f"{api_base_url}/{method}",
        data=payload,
        files=files,
        timeout=SESSION_REQUEST_TIMEOUT_SECONDS,
    )
    return response, _parse_json_response(response)


def _extract_chat_capabilities(api_base_url, chat_id):
    chat_response, chat_result = _telegram_get(
        api_base_url, "getChat", {"chat_id": chat_id}
    )
    if not chat_result.get("ok"):
        description = chat_result.get("description", chat_response.status_code)
        return {
            "ok": False,
            "message": f"Telegram chat inspection failed: {description}",
        }

    chat = chat_result.get("result") or {}
    permissions = chat.get("permissions") or {}
    chat_type = str(chat.get("type") or "unknown")

    me_response, me_result = _telegram_get(api_base_url, "getMe", {})
    if not me_result.get("ok"):
        description = me_result.get("description", me_response.status_code)
        return {
            "ok": False,
            "message": f"Telegram bot inspection failed: {description}",
            "chat_type": chat_type,
        }

    bot_id = (me_result.get("result") or {}).get("id")
    member = {}
    status = None
    if bot_id is not None:
        member_response, member_result = _telegram_get(
            api_base_url,
            "getChatMember",
            {"chat_id": chat_id, "user_id": bot_id},
        )
        if member_result.get("ok"):
            member = member_result.get("result") or {}
            status = member.get("status")
        else:
            status = "unknown"
            description = member_result.get("description", member_response.status_code)
            return {
                "ok": False,
                "message": f"Telegram chat member inspection failed: {description}",
                "chat_type": chat_type,
            }

    can_send_photos = None
    can_add_previews = None

    if chat_type == "private":
        can_send_photos = True
        can_add_previews = True
    elif status in {"administrator", "creator"}:
        can_send_photos = True
        can_add_previews = True
    elif status == "restricted":
        can_send_photos = bool(member.get("can_send_photos", False))
        can_add_previews = bool(member.get("can_add_web_page_previews", False))
    elif status in {"left", "kicked"}:
        can_send_photos = False
        can_add_previews = False
    else:
        if "can_send_photos" in permissions:
            can_send_photos = bool(permissions.get("can_send_photos"))
        if "can_add_web_page_previews" in permissions:
            can_add_previews = bool(permissions.get("can_add_web_page_previews"))

    return {
        "ok": True,
        "chat_type": chat_type,
        "member_status": status,
        "can_send_photos": can_send_photos,
        "can_add_web_page_previews": can_add_previews,
    }


def _describe_chat_capabilities(capabilities):
    if not isinstance(capabilities, dict):
        return "Telegram destination capabilities are unknown."

    if not capabilities.get("ok"):
        return capabilities.get("message") or "Telegram destination inspection failed."

    chat_type = capabilities.get("chat_type") or "chat"
    member_status = capabilities.get("member_status") or "unknown"
    can_send_photos = capabilities.get("can_send_photos")
    can_add_previews = capabilities.get("can_add_web_page_previews")

    if can_send_photos is False and can_add_previews is False:
        return (
            f"Telegram {chat_type} permissions block both photos and web page previews "
            f"for bot status '{member_status}'. Enable media permissions or promote the bot."
        )
    if can_send_photos is False and can_add_previews is True:
        return (
            f"Telegram {chat_type} permissions block photos for bot status "
            f"'{member_status}'. Kuasarr will use a large link preview for the poster."
        )
    if can_send_photos is True:
        return (
            f"Telegram {chat_type} permissions allow photo delivery for bot status "
            f"'{member_status}'."
        )
    if can_add_previews is True:
        return (
            f"Telegram {chat_type} permissions allow link previews for bot status "
            f"'{member_status}'."
        )
    return (
        f"Telegram {chat_type} permissions could not be determined for bot status "
        f"'{member_status}'."
    )


def _allow_link_preview(capabilities):
    return capabilities.get("can_add_web_page_previews") is not False


def _send_text_message(
    api_base_url,
    chat_id,
    text,
    disable_notification,
    image_url=None,
    use_link_preview=False,
):
    message_payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_notification": disable_notification,
    }
    if image_url and use_link_preview:
        message_payload["link_preview_options"] = json.dumps(
            {
                "url": image_url,
                "prefer_large_media": True,
                "show_above_text": True,
            }
        )
    else:
        message_payload["disable_web_page_preview"] = True

    response, result = _telegram_post(api_base_url, "sendMessage", message_payload)
    if not result.get("ok"):
        description = result.get("description", response.status_code)
        info(f"Failed to send Telegram notification: {description}")
        return False
    return True


def inspect_destination(shared_state):
    bot_token, chat_id = _get_telegram_credentials(shared_state)
    if not bot_token or not chat_id:
        return {
            "ok": False,
            "message": "Telegram bot token and chat ID are required.",
        }

    api_base_url = f"https://api.telegram.org/bot{bot_token}"
    capabilities = _extract_chat_capabilities(api_base_url, chat_id)
    capabilities["message"] = _describe_chat_capabilities(capabilities)
    return capabilities


class TelegramNotificationFormatter(AbstractNotificationFormatter):
    @staticmethod
    def _format_link(text, url, link_text=None):
        safe_url = _escape_html_attribute(url)
        target_text = link_text or text
        safe_target_text = _escape_html_text(target_text)
        rendered_link = f'<a href="{safe_url}">{safe_target_text}</a>'
        if target_text and target_text in text:
            return _escape_html_text(text).replace(safe_target_text, rendered_link, 1)
        return rendered_link

    @staticmethod
    def _render_titled_entry(title, value):
        return f"<b>{_escape_html_text(title)}</b>\n{value}"

    def render_text_entry(self, entry: NotificationTextEntry):
        return self._render_titled_entry(entry.title, _escape_html_text(entry.text))

    def render_link_entry(self, entry: NotificationLinkEntry):
        return self._render_titled_entry(
            entry.title,
            self._format_link(entry.text, entry.url, entry.link_text),
        )

    def render_facts_entry(self, entry: NotificationFactsEntry):
        facts_text = " | ".join(
            f"<b>{_escape_html_text(fact.label)}:</b> {_escape_html_text(fact.value)}"
            for fact in entry.facts
        )
        return self._render_titled_entry(entry.title, facts_text)

    def render_value_entry(self, entry: NotificationValueEntry):
        return self._render_titled_entry(entry.title, _escape_html_text(entry.value))

    def render_message(self, message: NotificationMessage):
        parts = [
            f"<b>{_escape_html_text(message.title)}</b>",
            _escape_html_text(message.description),
        ]
        parts.extend(self.render_entries(message.entries))
        return "\n\n".join(parts)


def send(shared_state, message, silent=True):
    """Send a rendered Telegram notification. Returns True on success."""
    bot_token, chat_id = _get_telegram_credentials(shared_state)
    if not bot_token or not chat_id:
        return False

    if not isinstance(message, NotificationMessage):
        info(f"Invalid Telegram notification payload: {type(message).__name__}")
        return False

    text = TelegramNotificationFormatter().render_message(message)
    disable_notification = bool(silent)
    api_base_url = f"https://api.telegram.org/bot{bot_token}"
    capabilities = inspect_destination(shared_state)

    if message.image_url:
        photo_allowed = capabilities.get("can_send_photos")
        preview_allowed = _allow_link_preview(capabilities)

        if photo_allowed is False:
            info(capabilities.get("message") or "Telegram chat blocks photo delivery.")
            return _send_text_message(
                api_base_url,
                chat_id,
                text,
                disable_notification,
                image_url=message.image_url,
                use_link_preview=preview_allowed,
            )

        photo_payload = {
            "chat_id": chat_id,
            "disable_notification": disable_notification,
        }
        if len(text) <= 1024:
            photo_payload["caption"] = text
            photo_payload["parse_mode"] = "HTML"

        try:
            photo_files = _build_photo_upload(shared_state, message.image_url)
        except Exception as e:
            info(f"Failed to fetch Telegram photo notification image: {e}")
            return _send_text_message(
                api_base_url,
                chat_id,
                text,
                disable_notification,
                image_url=message.image_url,
                use_link_preview=preview_allowed,
            )

        photo_response, photo_result = _telegram_post(
            api_base_url, "sendPhoto", photo_payload, files=photo_files
        )
        if not photo_result.get("ok"):
            description = photo_result.get("description", photo_response.status_code)
            info(f"Failed to send Telegram photo notification: {description}")
            if preview_allowed:
                return _send_text_message(
                    api_base_url,
                    chat_id,
                    text,
                    disable_notification,
                    image_url=message.image_url,
                    use_link_preview=True,
                )
            return _send_text_message(
                api_base_url,
                chat_id,
                text,
                disable_notification,
            )
        if len(text) <= 1024:
            return True

    return _send_text_message(api_base_url, chat_id, text, disable_notification)
