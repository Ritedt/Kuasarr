# -*- coding: utf-8 -*-
"""Regression tests for hide.cx link extraction without an API key.

Two separate failures showed up in the instance log while decrypting a
release that only had legacy /fc/Container/ links:

1. ``headers`` was built inside the "fetch the container by UUID" branch, so
   a legacy URL - which arrives with ``data`` already filled in by
   ``resolve_legacy_container`` - skipped the assignment and the per-link
   lookup below read an unbound local::

       Error fetching hide.cx links: cannot access local variable 'headers'

2. The dispatcher refused to touch hide.cx at all when no API key was
   configured, even though the public API needs no authentication and the
   docstring in the same module says so. Every package failed with
   "hide.cx API Key not configured - skipping" and ended up marked as failed
   after three retries.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from kuasarr.downloads.linkcrypters import hide as hide_module
from kuasarr.downloads.linkcrypters.hide import unhide_links
from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

LEGACY_URL = "https://hide.cx/fc/Container/63AFE2B591.html"
LEGACY_ID = "63AFE2B591"
CONTAINER_UUID = "d46dcc0c-0ee9-4200-a211-a0a69665313f"

# What resolve_legacy_container returns for LEGACY_ID: a container whose links
# carry no hoster_url, which forces the per-link lookup that needs the headers.
LEGACY_CONTAINER = {
    "id": CONTAINER_UUID,
    "access_status": "online",
    "links": [{"id": "link-1", "hoster_url": None, "link_status": "online"}],
}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _State(SimpleNamespace):
    """Shared state without an API key, which is the configuration that broke."""


def _state_without_key():
    """A state whose HideCX section carries no api_key.

    ``Config`` reads ``shared_state.values['configfile']`` off the module-level
    shared_state rather than off the object handed to unhide_links, so it has to
    be patched too or the key lookup raises before the code under test runs.
    """
    return _State(values={
        "user_agent": "test-agent",
        "configfile": "/nonexistent/kuasarr-test.ini",
        "config": lambda section: _Section({}),
    })


def _patched_config(monkeypatch_target, api_key=""):
    """Make Config() return a section with the given api_key."""
    return patch.object(
        hide_module,
        "get_hide_api_key",
        lambda shared_state: api_key or None,
    )


class _Section:
    def __init__(self, data):
        self._data = data

    def get(self, key):
        return self._data.get(key)


class TestLegacyContainerDoesNotNeedHeadersBinding(unittest.TestCase):
    """The legacy path skipped the branch that defines ``headers``."""

    def test_legacy_url_resolves_its_links_without_an_api_key(self):
        seen_headers = []

        def fake_get(url, headers=None, timeout=None, **kwargs):
            seen_headers.append(headers)
            if f"/fc/Container/{LEGACY_ID}" in url:
                return _FakeResponse(payload=LEGACY_CONTAINER)
            # Per-link lookup for the single entry whose hoster_url is null.
            return _FakeResponse(payload={"url": "https://rapidgator.net/file/x"})

        with patch("requests.get", side_effect=fake_get), \
             patch.object(hide_module, "get_hide_api_key", lambda s: None), \
             patch("kuasarr.downloads.linkcrypters.hide.StatsHelper"):
            links, error = unhide_links(_state_without_key(), LEGACY_URL)

        self.assertIsNone(error)
        self.assertEqual(links, ["https://rapidgator.net/file/x"])

    def test_the_per_link_request_carries_headers(self):
        """The request that used to read an unbound local must still send them."""
        seen = []

        def fake_get(url, headers=None, timeout=None, **kwargs):
            seen.append((url, headers))
            if f"/fc/Container/{LEGACY_ID}" in url:
                return _FakeResponse(payload=LEGACY_CONTAINER)
            return _FakeResponse(payload={"url": "https://rapidgator.net/file/x"})

        with patch("requests.get", side_effect=fake_get), \
             patch.object(hide_module, "get_hide_api_key", lambda s: None), \
             patch("kuasarr.downloads.linkcrypters.hide.StatsHelper"):
            unhide_links(_state_without_key(), LEGACY_URL)

        per_link = [(url, h) for url, h in seen if "/links/" in url]
        self.assertTrue(per_link, "the per-link lookup never ran")
        for url, headers in per_link:
            self.assertIsNotNone(headers, f"{url} was sent without headers")
            self.assertEqual(headers.get("User-Agent"), "test-agent")


class TestDispatcherDoesNotRequireAKey(unittest.TestCase):
    """hide.cx resolves without authentication, so a missing key is not a skip."""

    def _dispatcher(self):
        return DBCDispatcher(state_module=_state_without_key())

    def test_missing_api_key_does_not_skip_the_container(self):
        with patch("kuasarr.providers.captcha.dbc_dispatcher.unhide_links") as unhide:
            unhide.return_value = (["https://rapidgator.net/file/x"], None)
            result = self._dispatcher()._solve_hide_cx(
                "Dark.S03", LEGACY_URL, password=""
            )

        self.assertIsNotNone(result, "the dispatcher skipped a keyless container")
        unhide.assert_called_once()
        self.assertEqual(result["links"], ["https://rapidgator.net/file/x"])

    def test_a_configured_key_is_still_sent_when_present(self):
        """An existing key stays optional, not forbidden."""
        state = _State(values={
            "user_agent": "test-agent",
            "configfile": "/nonexistent/kuasarr-test.ini",
            "config": lambda section: _Section(
                {"api_key": "secret"} if section == "HideCX" else {}
            ),
        })
        with patch("kuasarr.providers.captcha.dbc_dispatcher.unhide_links") as unhide:
            unhide.return_value = (["https://rapidgator.net/file/x"], None)
            DBCDispatcher(state_module=state)._solve_hide_cx(
                "Dark.S03", LEGACY_URL, password=""
            )

        self.assertEqual(
            unhide.call_args.kwargs.get("password", None)
            if unhide.call_args.kwargs else None,
            None,
        )