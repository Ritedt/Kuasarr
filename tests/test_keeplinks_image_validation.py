# -*- coding: utf-8 -*-
"""Tests fuer die Validierung des heruntergeladenen Captcha-Bildes.

Keeplinks antwortet auf ein abgelehntes oder abgelaufenes Captcha mit
HTTP 200 und einer HTML-Seite. Kuasarr hat diese Antwort ungeprueft als
"Bild" an den Solver gegeben - der lieferte dann ein Wort zurueck, das
gar nicht zu einer Bilddatei gehoert, und beim POST kam
"Rejected solution" heraus. Der Fehler sah damit aus wie eine schlechte
Erkennung, obwohl die Ursache eine kaputte Session war.

Die Referenzimplementierung prueft vor dem Solving, ob die Antwort
tatsaechlich ein Bild ist und ob sie ueberhaupt Bytes hat.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from kuasarr.providers.captcha.dbc_dispatcher import (
    KEEPLINKS_MIN_IMAGE_BYTES,
    DBCDispatcher,
)

CONTAINER_URL = "https://www.keeplinks.org/p26/6aa36f6b8697a"
CAPTCHA_URL = "https://www.keeplinks.org/coolcaptcha/captcha.php"

CONTAINER_PAGE = (
    "<html><body><form name='frmprotect'>"
    "<input type='hidden' name='captchatype' value='Cool'>"
    "<input type='hidden' name='hiddenpwd' value=''>"
    f"<img src='{CAPTCHA_URL}'>"
    "</form></body></html>"
)


class _FakeResponse:
    def __init__(self, text, content=b"", status_code=200, content_type="text/html"):
        self.text = text
        self.content = content or text.encode()
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}


class _SolverResult:
    def __init__(self, text="abcd"):
        self.text = text
        self.captcha_id = 1234


class CaptchaImageValidationTest(unittest.TestCase):
    def _run(self, image_response):
        dispatcher = DBCDispatcher(state_module=SimpleNamespace(values={}))
        client = MagicMock()
        client.solve_captcha.return_value = _SolverResult()
        client.report_incorrect = MagicMock(return_value=True)
        dispatcher._client = client

        session = MagicMock()
        session.get.return_value = image_response
        session.post.return_value = _FakeResponse("<html></html>")

        result = dispatcher._solve_keeplinks_captcha(
            session, BeautifulSoup(CONTAINER_PAGE, "html.parser"),
            CONTAINER_URL, {"User-Agent": "Kuasarr-Test"}, "", None,
        )
        return result, client

    def test_html_error_page_never_reaches_the_solver(self):
        """HTTP 200 mit HTML ist keine Bilddatei."""
        result, client = self._run(_FakeResponse(
            "<html><body>Session expired</body></html>",
            content=b"<html><body>Session expired</body></html>",
            content_type="text/html; charset=utf-8",
        ))

        self.assertFalse(client.solve_captcha.called,
                         "HTML ging als Bild an den Solver")
        self.assertIsNone(result)

    def test_tiny_image_is_refused(self):
        """Ein 10-Byte-"Bild" ist keins."""
        result, client = self._run(_FakeResponse(
            "x", content=b"x" * 10, content_type="image/png"
        ))

        self.assertFalse(client.solve_captcha.called)
        self.assertIsNone(result)

    def test_boundary_is_accepted(self):
        """Genau an der Grenze wird noch akzeptiert."""
        result, client = self._run(_FakeResponse(
            "x", content=b"x" * KEEPLINKS_MIN_IMAGE_BYTES, content_type="image/png"
        ))

        self.assertTrue(client.solve_captcha.called,
                        "Ein Bild an der Groessengrenze wurde abgelehnt")

    def test_real_image_is_accepted(self):
        result, client = self._run(_FakeResponse(
            "x", content=b"\x89PNG" + b"0" * 300, content_type="image/png"
        ))

        self.assertTrue(client.solve_captcha.called)
        self.assertEqual(
            client.solve_captcha.call_args[0][0], b"\x89PNG" + b"0" * 300,
            "Es wurden nicht die Bildbytes an den Solver gegeben",
        )

    def test_gif_content_type_is_accepted(self):
        """Nicht-PNG-Bilder sind equally gueltig - nur 'image' zaehlt."""
        _, client = self._run(_FakeResponse(
            "x", content=b"GIF89a" + b"0" * 300, content_type="image/gif"
        ))
        self.assertTrue(client.solve_captcha.called)

    def test_missing_content_type_is_refused(self):
        """Ohne Content-Type lässt sich nichts Belastbares sagen."""
        response = _FakeResponse("x", content=b"\x89PNG" + b"0" * 300)
        response.headers = {}
        result, client = self._run(response)

        self.assertFalse(client.solve_captcha.called)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()