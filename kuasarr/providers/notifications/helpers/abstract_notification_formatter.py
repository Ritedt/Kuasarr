# -*- coding: utf-8 -*-
# Kuasarr

from abc import ABC, abstractmethod

from kuasarr.providers.notifications.helpers.notification_message import (
    AbstractNotificationEntry,
    NotificationFactsEntry,
    NotificationLinkEntry,
    NotificationTextEntry,
    NotificationValueEntry,
)


class AbstractNotificationFormatter(ABC):
    def render_entry(self, entry: AbstractNotificationEntry):
        if isinstance(entry, NotificationTextEntry):
            return self.render_text_entry(entry)
        if isinstance(entry, NotificationLinkEntry):
            return self.render_link_entry(entry)
        if isinstance(entry, NotificationFactsEntry):
            return self.render_facts_entry(entry)
        if isinstance(entry, NotificationValueEntry):
            return self.render_value_entry(entry)
        raise TypeError(f"Unsupported notification entry type: {type(entry).__name__}")

    def render_entries(self, entries: tuple[AbstractNotificationEntry, ...]):
        return [self.render_entry(entry) for entry in entries]

    @abstractmethod
    def render_text_entry(self, entry: NotificationTextEntry):
        pass

    @abstractmethod
    def render_link_entry(self, entry: NotificationLinkEntry):
        pass

    @abstractmethod
    def render_facts_entry(self, entry: NotificationFactsEntry):
        pass

    @abstractmethod
    def render_value_entry(self, entry: NotificationValueEntry):
        pass
