# -*- coding: utf-8 -*-
# Kuasarr

from enum import Enum


class NotificationType(str, Enum):
    UNPROTECTED = "unprotected"
    CAPTCHA = "captcha"
    SOLVED = "solved"
    DISABLED = "disabled"
    FAILED = "failed"
    UPDATE = "update"
    TEST = "test"


_NOTIFICATION_TYPE_LABELS = {
    NotificationType.UNPROTECTED: "Unprotected Links",
    NotificationType.CAPTCHA: "CAPTCHA Required",
    NotificationType.SOLVED: "CAPTCHA Solved",
    NotificationType.DISABLED: "Kuasarr Disabled",
    NotificationType.FAILED: "Failed",
    NotificationType.UPDATE: "Kuasarr Updates",
    NotificationType.TEST: "Test Message",
}


def normalize_notification_type(value):
    if isinstance(value, NotificationType):
        return value

    if value is None:
        return None

    normalized_value = str(value).strip().lower()
    for notification_type in NotificationType:
        if notification_type.value == normalized_value:
            return notification_type

    return None


def get_user_configurable_notification_types():
    return tuple(
        notification_type
        for notification_type in NotificationType
        if notification_type is not NotificationType.TEST
    )


def get_notification_type_label(notification_type):
    return _NOTIFICATION_TYPE_LABELS.get(
        notification_type,
        notification_type.value.replace("_", " ").title(),
    )
