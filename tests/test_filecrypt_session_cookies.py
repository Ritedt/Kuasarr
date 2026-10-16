# -*- coding: utf-8 -*-
"""Regression tests for the FileCrypt session after the proof-of-work solve.

The PoW is cleared inside a FlareSolverr browser, so the container session only
counts once those browser cookies are carried back into the requests session.
They were merged instead of replacing, and FlareSolverr reports the domain with
a leading dot (".filecrypt.cc") where requests had stored it bare
("filecrypt.cc"). Two cookies named PHPSESSID therefore coexisted, and every
later read of the cookie raised CookieConflictError while every later request
carried an ambiguous session that FileCrypt answered with an anonymous page.
"""

import unittest
import requests
from types import SimpleNamespace
from unittest.mock import patch

from kuasarr.downloads.linkcrypters.filecrypt import (
    _apply_pow_result,
    get_filecrypt_phpsessid,
)
from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

CONTAINER_URL = "https://filecrypt.cc/Container/1AAE0F1834.html"


class _FakeFlareSolverrResponse:
    """Stands in for the browser session FlareSolverr reports back."""

    def __init__(self, cookies):
        self.cookies = cookies


def _session_with_phpsessid(domain="filecrypt.cc", path="/"):
    session = requests.Session()
    session.cookies.set("PHPSESSID", "INITIAL-SESSION", domain=domain, path=path)
    return session


def _phpsessid_cookies(session):
    return [c for c in session.cookies if c.name == "PHPSESSID"]


class TestApplyPowResultReplacesCookies(unittest.TestCase):
    """The PoW browser session is authoritative and must win as a whole."""

    def test_result_does_not_leave_two_phpsessid_cookies(self):
        session = _session_with_phpsessid()
        _apply_pow_result(session, _FakeFlareSolverrResponse([
            {"name": "PHPSESSID", "value": "POW-SESSION", "domain": ".filecrypt.cc", "path": "/"},
        ]))

        self.assertEqual(
            len(_phpsessid_cookies(session)), 1,
            "the solved browser session must replace the pre-PoW one, not sit next to it",
        )

    def test_solved_session_is_readable_without_a_cookie_conflict(self):
        session = _session_with_phpsessid()
        _apply_pow_result(session, _FakeFlareSolverrResponse([
            {"name": "PHPSESSID", "value": "POW-SESSION", "domain": ".filecrypt.cc", "path": "/"},
        ]))

        # This call raised CookieConflictError before and aborted link extraction.
        self.assertEqual(session.cookies.get("PHPSESSID"), "POW-SESSION")

    def test_cookies_handed_to_the_browser_are_not_dropped(self):
        """The browser was seeded with the whole jar, so replacing keeps a superset."""
        session = _session_with_phpsessid()
        session.cookies.set("fc_last_seen", "1", domain="filecrypt.cc", path="/")
        _apply_pow_result(session, _FakeFlareSolverrResponse([
            {"name": "PHPSESSID", "value": "POW-SESSION", "domain": ".filecrypt.cc", "path": "/"},
            {"name": "fc_last_seen", "value": "1", "domain": ".filecrypt.cc", "path": "/"},
        ]))

        self.assertEqual(session.cookies.get("fc_last_seen"), "1")

    def test_an_empty_result_does_not_wipe_the_session(self):
        session = _session_with_phpsessid()
        _apply_pow_result(session, _FakeFlareSolverrResponse([]))

        self.assertEqual(session.cookies.get("PHPSESSID"), "INITIAL-SESSION")


class TestGetFilecryptPhpsessid(unittest.TestCase):
    """The lookup itself must not abort extraction when the jar is ambiguous."""

    def test_returns_the_cookie_for_the_container_origin(self):
        session = requests.Session()
        session.cookies.set("PHPSESSID", "OTHER-HOST", domain="rapidgator.net", path="/")
        session.cookies.set("PHPSESSID", "CONTAINER", domain=".filecrypt.cc", path="/")

        self.assertEqual(get_filecrypt_phpsessid(session, CONTAINER_URL), "CONTAINER")

    def test_tolerates_a_duplicate_name_and_prefers_the_newest(self):
        session = _session_with_phpsessid()
        session.cookies.set("PHPSESSID", "SECOND", domain=".filecrypt.cc", path="/")

        self.assertEqual(get_filecrypt_phpsessid(session, CONTAINER_URL), "SECOND")

    def test_returns_none_when_the_container_session_is_absent(self):
        self.assertIsNone(get_filecrypt_phpsessid(requests.Session(), CONTAINER_URL))


# A solved container whose Click'n'Load form and DLC button are both unusable, so
# extraction has to fall back to the per-link buttons.
BUTTON_ONLY_PAGE_HTML = (
    "<html><body><div class=\"container\"><table><tr>"
    "<td><a class=\"external_link\">rapidgator</a></td>"
    "<td><button data-id=\"ABC123\" data-i18n=\"go\">Go</button></td>"
    "</tr></table></div></body></html>"
)


class TestDispatcherSurvivesDuplicateSessionCookies(unittest.TestCase):
    """The circle-captcha fallback used to crash the whole link on a cookie conflict."""

    def _extract(self, session):
        from bs4 import BeautifulSoup
        dispatcher = DBCDispatcher(
            state_module=SimpleNamespace(values={"user_agent": "test-agent"})
        )
        soup = BeautifulSoup(BUTTON_ONLY_PAGE_HTML, "html.parser")
        return dispatcher._extract_filecrypt_links(
            session, soup, CONTAINER_URL, "American.Dad.S17E01", {"User-Agent": "test-agent"}
        )

    def test_fallback_returns_the_replacement_info_instead_of_raising(self):
        session = _session_with_phpsessid()
        session.cookies.set("PHPSESSID", "SECOND", domain=".filecrypt.cc", path="/")

        result = self._extract(session)

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "replaced")
        # https, because the container is: a plain-http URL here is answered with
        # a redirect to the same host over https, which the origin guard refuses.
        self.assertEqual(result["replace_url"], "https://filecrypt.cc/Link/ABC123.html")
        self.assertEqual(result["mirror"], "rapidgator")
        self.assertIsNotNone(result["session"])

    def test_missing_session_cookie_is_reported_not_raised(self):
        self.assertIsNone(self._extract(requests.Session()))


if __name__ == "__main__":
    unittest.main()