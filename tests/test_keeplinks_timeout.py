# -*- coding: utf-8 -*-
"""Tests fuer die Timeouts aller Keeplinks-Container-Requests.

Der POST mit der geloesten Captcha-Antwort lief in
``Read timed out. (read timeout=10)``, waehrend dieselbe Kette bis eben
durchlief. Live gemessen antwortet Keeplinks eine *falsche* Antwort in
~0,08 s. Der Unterschied: nur ein *richtiger* Answer laesst den Server den
Container auch entsperren - entschluesseln und die entriegelte Seite
rendern. Genau dieser teure Pfad bekam das HTTP-Default von 10 s und lief
deshalb genau dann in den Timeout, wenn die Antwort richtig war.

Die Referenzimplementierung gibt diesem POST 30 s, der WebUI-Pfad in
``downloads/linkcrypters/keeplinks.py`` ebenfalls. Hier wird festgeschrieben,
dass alle vier Requests der Keeplinks-Kette dieselbe, groessere Konstante
benutzen - ein einzelner vergessener Request waere sonst wieder 10 s.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from kuasarr.constants import (
    HTTP_DEFAULT_TIMEOUT_SECONDS,
    KEEPLINKS_TIMEOUT_SECONDS,
    get_timeout,
)
from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

CONTAINER_URL = "https://www.keeplinks.org/p26/6aa36f6b8697a"
CAPTCHA_URL = "https://www.keeplinks.org/coolcaptcha/captcha.php"

# Seite vor dem Proceed-Klick: Formular mit showpageval=1.
PROCEED_PAGE = (
    "<html><body><form name='frmprotect' method='post' "
    f"action='{CONTAINER_URL}'>"
    "<input type='hidden' name='showpageval' value='1'>"
    "<input type='submit' name='hbtncheck' value=''>"
    "</form></body></html>"
)

# Antwort auf den Proceed-POST: entriegelter Container mit Download-Link.
UNLOCKED_PAGE = (
    "<html><body><textarea class='trurl'>"
    "https://rapidgator.net/file/abcdef123"
    "</textarea></body></html>"
)

# Seite mit Captcha, wie sie _solve_keeplinks_captcha bekommt.
CAPTCHA_PAGE = (
    "<html><body><form name='frmprotect'>"
    "<input type='hidden' name='captchatype' value='Cool'>"
    "<input type='hidden' name='hiddenpwd' value=''>"
    f"<img src='{CAPTCHA_URL}'>"
    "</form></body></html>"
)

PAGE_HEADERS = {
    "User-Agent": "Kuasarr-Test/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": CONTAINER_URL,
}


class _FakeResponse:
    def __init__(self, text, content=b"", status_code=200, content_type="text/html"):
        self.text = text
        self.content = content or text.encode()
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}


class _SolverResult:
    text = "cleck"
    captcha_id = 1234


def _dispatcher():
    dispatcher = DBCDispatcher(state_module=SimpleNamespace(values={
        "user_agent": "Kuasarr-Test/1.0",
    }))
    client = MagicMock()
    client.solve_captcha.return_value = _SolverResult()
    client.report_incorrect = MagicMock(return_value=True)
    dispatcher._client = client
    return dispatcher


class KeeplinksTimeoutConstantTest(unittest.TestCase):
    """Die Konstante selbst - der Wert, um den es hier geht."""

    def test_keeplinks_timeout_is_thirty_seconds(self):
        self.assertEqual(KEEPLINKS_TIMEOUT_SECONDS, 30)

    def test_keeplinks_timeout_exceeds_the_http_default(self):
        """Die eigentliche Invariante.

        Solange beide Werte gleich sind, faellt der Unterschied beim Lesen
        des Codes nicht mehr auf und ein Request faellt unbemerkt auf 10 s
        zurueck. Genau das war der Auslieferungszustand.
        """
        self.assertGreater(
            get_timeout(KEEPLINKS_TIMEOUT_SECONDS),
            get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS),
        )


class KeeplinksContainerRequestTimeoutTest(unittest.TestCase):
    """Initial-GET und Proceed-POST aus _solve_keeplinks_with_dbc."""

    def setUp(self):
        self.dispatcher = _dispatcher()
        self.session = MagicMock()
        self.session.get.return_value = _FakeResponse(PROCEED_PAGE)
        self.session.post.return_value = _FakeResponse(UNLOCKED_PAGE)

        with unittest.mock.patch.object(self.dispatcher, "_same_origin_guard_for",
                                       return_value=self.session):
            self.dispatcher._solve_keeplinks_with_dbc(
                "Titel", CONTAINER_URL, None)

        self.initial_get = self.session.get.call_args_list[0]
        self.proceed_post = self.session.post.call_args_list[0]

    def test_initial_get_uses_the_keeplinks_timeout(self):
        _, kwargs = self.initial_get
        self.assertEqual(kwargs["timeout"],
                         get_timeout(KEEPLINKS_TIMEOUT_SECONDS))

    def test_proceed_post_uses_the_keeplinks_timeout(self):
        _, kwargs = self.proceed_post
        self.assertEqual(kwargs["timeout"],
                         get_timeout(KEEPLINKS_TIMEOUT_SECONDS))

    def test_neither_container_request_uses_the_http_default(self):
        """Regression: genau diese beiden standen vorher auf dem Default."""
        for call in (self.initial_get, self.proceed_post):
            _, kwargs = call
            self.assertNotEqual(kwargs["timeout"],
                                get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))


class KeeplinksCaptchaRequestTimeoutTest(unittest.TestCase):
    """Bild-GET und Solution-POST aus _solve_keeplinks_captcha."""

    def setUp(self):
        self.dispatcher = _dispatcher()
        self.session = MagicMock()
        self.session.get.return_value = _FakeResponse(
            "x", content=b"\x89PNG" + b"0" * 300, content_type="image/png")
        self.session.post.return_value = _FakeResponse("<html></html>")

        self.dispatcher._solve_keeplinks_captcha(
            self.session, BeautifulSoup(CAPTCHA_PAGE, "html.parser"),
            CONTAINER_URL, dict(PAGE_HEADERS), "", None,
        )
        self.image_get = self.session.get.call_args
        self.solution_post = self.session.post.call_args

    def test_captcha_image_get_uses_the_keeplinks_timeout(self):
        _, kwargs = self.image_get
        self.assertEqual(kwargs["timeout"],
                         get_timeout(KEEPLINKS_TIMEOUT_SECONDS))

    def test_solution_post_uses_the_keeplinks_timeout(self):
        """Der Regressionstest fuer den gemeldeten Timeout."""
        _, kwargs = self.solution_post
        self.assertEqual(kwargs["timeout"],
                         get_timeout(KEEPLINKS_TIMEOUT_SECONDS))

    def test_solution_post_timeout_exceeds_the_http_default(self):
        """Genau diese 10 s standen im Produktivlog als read timeout=10."""
        _, kwargs = self.solution_post
        self.assertGreater(kwargs["timeout"],
                           get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))

    def test_solution_post_still_follows_redirects(self):
        """Mehr Zeit ja - aber die Redirect-Kette bleibt, sonst kaemen die
        Links aus der Antwort des Folge-Requests statt aus dem POST."""
        _, kwargs = self.solution_post
        self.assertTrue(kwargs.get("allow_redirects"))


if __name__ == "__main__":
    unittest.main()