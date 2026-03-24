# -*- coding: utf-8 -*-
# Kuasarr

from abc import ABC
from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationFact:
    label: str
    value: str


@dataclass(frozen=True)
class AbstractNotificationEntry(ABC):
    title: str


@dataclass(frozen=True)
class NotificationTextEntry(AbstractNotificationEntry):
    text: str


@dataclass(frozen=True)
class NotificationLinkEntry(AbstractNotificationEntry):
    text: str
    url: str
    link_text: str | None = None


@dataclass(frozen=True)
class NotificationFactsEntry(AbstractNotificationEntry):
    facts: tuple[NotificationFact, ...]


@dataclass(frozen=True)
class NotificationValueEntry(AbstractNotificationEntry):
    value: str


@dataclass(frozen=True)
class NotificationMessage:
    title: str
    description: str
    entries: tuple[AbstractNotificationEntry, ...] = ()
    image_url: str | None = None
    thumbnail_url: str | None = None
