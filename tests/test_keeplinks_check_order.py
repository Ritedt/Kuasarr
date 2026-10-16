# -*- coding: utf-8 -*-
"""Tests fuer die Reihenfolge der Antwort-Pruefungen nach dem CAPTCHA-POST.

Der Dispatcher hat zuerst auf eine Ablehnung geprueft und die Links erst
danach gelesen. Damit wurde eine wirklich richtige Loesung verworfen,
sobald Keeplinks das Captcha-Bild trotz geoeffnetem Container mitschickt -
und der Solver bekam fuer eine korrekte Antwort eine Erstattung, die ihm
nicht zusteht.

Die Referenzimplementierung liest umgekehrt: erst die Links, und nur wer
keine hat, darf aus dem Captcha-Bild auf eine Ablehnung schliessen.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from kuasarr.downloads.linkcrypters.keeplinks import get_keeplinks_links
from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

CONTAINER_URL = "https://www.keeplinks.org/p26/6aa36f6b8697a"
CAPTCHA_URL = "https://www.keeplinks.org/coolcaptcha/captcha.php"


class _FakeResponse:
    def __init__(self, text, content=b"", status_code=200):
        self.text = text
        self.content = content or text.encode()
        self.status_code = status_code


class _SolverResult:
    def __init__(self, text, captcha_id=1234):
        self.text = text
        self.captcha_id = captcha_id


def _container_page(variant="Cool"):
    return (
        "<html><body><form name='frmprotect'>"
        f"<input type='hidden' name='captchatype' value='{variant}'>"
        "<input type='hidden' name='hiddenpwd' value=''>"
        f"<img src='{CAPTCHA_URL}'>"
        "</form></body></html>"
    )


# Der realistische Problemfall: der Container ist offen, die Links stehen im
# HTML - und Keeplinks schickt das Captcha-Bild trotzdem noch mit.
OPEN_WITH_STALE_CAPTCHA = (
    "<html><body>"
    f"<img src='{CAPTCHA_URL}'>"
    "<textarea class='trurl'>https://rapidgator.net/file/aaaa1111</textarea>"
    "</body></html>"
)

OPEN_WITH_ERROR_BANNER = (
    "<html><body>"
    "<div class='msg-error'>Your session expired, please try again</div>"
    "<textarea class='trurl'>https://rapidgator.net/file/bbbb2222</textarea>"
    "</body></html>"
)

REJECTED = (
    "<html><body>"
    f"<img src='{CAPTCHA_URL}'>"
    "<div class='msg-error'>Wrong captcha</div>"
    "</body></html>"
)


class _DispatcherCase:
    """Ein CAPTCHA-Durchlauf mit fester Antwort-Seite."""

    def _dispatcher(self):
        dispatcher = DBCDispatcher(state_module=SimpleNamespace(values={}))
        client = MagicMock()
        client.solve_captcha.return_value = _SolverResult("abcd")
        client.report_incorrect = MagicMock(return_value=True)
        dispatcher._client = client
        return dispatcher, client

    def _run(self, page_html):
        dispatcher, client = self._dispatcher()
        session = MagicMock()
        session.get.return_value = _FakeResponse(
            _container_page(), content=b"\x89PNG" + b"0" * 200
        )
        session.post.return_value = _FakeResponse(page_html)
        result = dispatcher._solve_keeplinks_captcha(
            session, BeautifulSoup(_container_page(), "html.parser"),
            CONTAINER_URL, {"User-Agent": "Kuasarr-Test"}, "", None,
        )
        return result, client


class LinksWinOverStaleCaptchaTest(_DispatcherCase, unittest.TestCase):
    """Offener Container mit mitgeschicktem Captcha-Bild ist ein Erfolg."""

    def test_links_are_returned(self):
        result, _ = self._run(OPEN_WITH_STALE_CAPTCHA)
        self.assertIsNotNone(result, "Offener Container wurde als Ablehnung gewertet")
        self.assertEqual(result["links"], ["https://rapidgator.net/file/aaaa1111"])

    def test_solver_is_not_charged_a_refund(self):
        """Eine korrekte Antwort darf nicht als falsch gemeldet werden."""
        _, client = self._run(OPEN_WITH_STALE_CAPTCHA)
        self.assertFalse(
            client.report_incorrect.called,
            "Der Solver bekam eine Erstattung fuer eine korrekte Antwort",
        )


class LinksWinOverErrorBannerTest(_DispatcherCase, unittest.TestCase):
    """Eine mitgeschickte Fehlermeldung verfaelscht kein Ergebnis."""

    def test_links_are_returned(self):
        result, _ = self._run(OPEN_WITH_ERROR_BANNER)
        self.assertIsNotNone(result, "Fehlermeldung hat die Links ueberschrieben")
        self.assertEqual(result["links"], ["https://rapidgator.net/file/bbbb2222"])


class RealRejectionStillDetectedTest(_DispatcherCase, unittest.TestCase):
    """Eine echte Ablehnung wird weiterhin erkannt."""

    def test_rejection_returns_none(self):
        result, _ = self._run(REJECTED)
        self.assertIsNone(result)

    def test_rejection_is_reported_to_the_solver(self):
        _, client = self._run(REJECTED)
        self.assertTrue(client.report_incorrect.called,
                        "Echte Ablehnung wurde nicht als Erstattung gemeldet")


class WebUiCheckOrderTest(unittest.TestCase):
    """Im WebUI-Pfad gilt dieselbe Reihenfolge."""

    # Banner, das auf das Fehlermuster des WebUI-Pfads trifft
    # (wrong|invalid|incorrect) - ein Text-Match ueber die ganze Seite.
    OPEN_WITH_MATCHING_BANNER = (
        "<html><body>"
        "<div class='msg-error'>Invalid captcha, please try again</div>"
        "<textarea class='trurl'>https://rapidgator.net/file/cccc3333</textarea>"
        "</body></html>"
    )

    def _run(self, page_html):
        captcha_page = (
            "<html><body><form name='frmprotect'>"
            "<input type='hidden' name='captchatype' value='Cool'>"
            f"<img src='{CAPTCHA_URL}'>"
            "<input type='text' name='captcha_cool'>"
            "</form></body></html>"
        )
        shared_state = SimpleNamespace(values={"user_agent": "Kuasarr-Test"})
        with unittest.mock.patch(
            "kuasarr.downloads.linkcrypters.keeplinks.requests.Session"
        ) as factory:
            session = factory.return_value
            session.get.return_value = _FakeResponse(captcha_page)
            session.post.return_value = _FakeResponse(page_html)
            return get_keeplinks_links(shared_state, "abcd", "Titel", CONTAINER_URL)

    def test_error_banner_does_not_hide_links(self):
        result = self._run(self.OPEN_WITH_MATCHING_BANNER)
        self.assertEqual(result, {
            "status": "success",
            "links": ["https://rapidgator.net/file/cccc3333"],
        })

    def test_rejection_still_returns_false(self):
        result = self._run(REJECTED)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()