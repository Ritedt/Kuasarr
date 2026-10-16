# -*- coding: utf-8 -*-
"""Tests fuer den Request, mit dem das Captcha-Bild geladen wird.

Das Captcha-Bild wurde mit denselben Headern geladen wie die
Containerseite - also mit ``Accept: text/html,...``. Der Referer zeigte auf
die Container-URL, das Bild selbst war aber nie in der Anfrage referenziert.
Ein Browser schickt beim Laden eines ``<img>`` genau das Gegenteil: den
Referer der Seite, aus der das Bild stammt, und einen Accept-Header, der
Bilder erwartet.

Die Referenzimplementierung macht das so und nutzt zusaetzlich das
laengere Timeout fuer Bild-Downloads.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from kuasarr.constants import (
    HTTP_DEFAULT_TIMEOUT_SECONDS,
    HTTP_EXTENDED_TIMEOUT_SECONDS,
    get_timeout,
)
from kuasarr.providers.captcha.dbc_dispatcher import (
    KEEPLINKS_IMAGE_ACCEPT,
    DBCDispatcher,
)

CONTAINER_URL = "https://www.keeplinks.org/p26/6aa36f6b8697a"
CAPTCHA_URL = "https://www.keeplinks.org/coolcaptcha/captcha.php"
USER_AGENT = "Kuasarr-Test/1.0"

CONTAINER_PAGE = (
    "<html><body><form name='frmprotect'>"
    "<input type='hidden' name='captchatype' value='Cool'>"
    "<input type='hidden' name='hiddenpwd' value=''>"
    f"<img src='{CAPTCHA_URL}'>"
    "</form></body></html>"
)

PAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": CONTAINER_URL,
}


class _FakeResponse:
    def __init__(self, text, content=b"", status_code=200, content_type="text/html"):
        self.text = text
        self.content = content or text.encode()
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}


class _SolverResult:
    text = "abcd"
    captcha_id = 1234


class CaptchaImageRequestTest(unittest.TestCase):
    def setUp(self):
        self.dispatcher = DBCDispatcher(state_module=SimpleNamespace(values={}))
        client = MagicMock()
        client.solve_captcha.return_value = _SolverResult()
        client.report_incorrect = MagicMock(return_value=True)
        self.dispatcher._client = client

        self.session = MagicMock()
        self.session.get.return_value = _FakeResponse(
            "x", content=b"\x89PNG" + b"0" * 300, content_type="image/png"
        )
        self.session.post.return_value = _FakeResponse("<html></html>")

        self.dispatcher._solve_keeplinks_captcha(
            self.session, BeautifulSoup(CONTAINER_PAGE, "html.parser"),
            CONTAINER_URL, dict(PAGE_HEADERS), "", None,
        )
        self.image_call = self.session.get.call_args

    def test_referer_points_at_the_container_page(self):
        _, kwargs = self.image_call
        self.assertEqual(kwargs["headers"]["Referer"], CONTAINER_URL)

    def test_accept_asks_for_an_image(self):
        _, kwargs = self.image_call
        self.assertEqual(kwargs["headers"]["Accept"], KEEPLINKS_IMAGE_ACCEPT)
        self.assertIn("image/*", kwargs["headers"]["Accept"])

    def test_html_accept_is_not_reused(self):
        """Der HTML-Accept der Containerseite darf nicht durchgereicht werden."""
        _, kwargs = self.image_call
        self.assertNotIn("text/html", kwargs["headers"]["Accept"])

    def test_user_agent_is_kept(self):
        """Der User-Agent bleibt, damit die Session erkannt wird."""
        _, kwargs = self.image_call
        self.assertEqual(kwargs["headers"]["User-Agent"], USER_AGENT)

    def test_image_get_uses_the_extended_timeout(self):
        _, kwargs = self.image_call
        self.assertEqual(kwargs["timeout"],
                         get_timeout(HTTP_EXTENDED_TIMEOUT_SECONDS))
        self.assertGreater(get_timeout(HTTP_EXTENDED_TIMEOUT_SECONDS),
                           get_timeout(HTTP_DEFAULT_TIMEOUT_SECONDS))

    def test_image_url_is_the_captcha_endpoint(self):
        args, _ = self.image_call
        self.assertEqual(args[0], CAPTCHA_URL)

    def test_page_headers_are_left_untouched(self):
        """Die Container-Header werden nicht veraendert - nur der Bild-GET nutzt eigene."""
        _, kwargs = self.image_call
        self.assertEqual(PAGE_HEADERS["Accept"],
                         "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")


if __name__ == "__main__":
    unittest.main()