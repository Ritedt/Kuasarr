# -*- coding: utf-8 -*-
"""Tests fuer die Weitergabe der geloesten Keeplinks-Antwort.

Der Dispatcher hat die Antwort des Solvers vor dem POST normalisiert: bei
``cool`` wurden alle Nicht-Buchstaben entfernt, bei ``simple`` wiederholte
Zeichen zusammengefasst. Damit ging gegebenenfalls genau die Information
verloren, die Keeplinks zur Pruefung braucht - eine Loesung wie ``a1b2``
wurde zu ``ab`` verkuerzt und konnte nicht mehr stimmen.

Die Referenzimplementierung postet ``solved_text`` unveraendert. Genau das
wird hier festgeschrieben; ``_normalize_keeplinks_answer`` bleibt als
Plausibilitaetspruefung erhalten (leeres Ergebnis nach dem Aufraeumen ist
unbrauchbar), veraendert den POST aber nicht mehr.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

CONTAINER_URL = "https://www.keeplinks.org/p26/6aa36f6b8697a"

COOL_PAGE_HTML = (
    "<html><body>"
    "<form name='frmprotect' method='post'>"
    "<input type='hidden' name='captchatype' value='Cool'>"
    "<input type='hidden' name='hiddenpwd' value=''>"
    "<img src='https://www.keeplinks.org/coolcaptcha/captcha.php'>"
    "</form>"
    "</body></html>"
)

# Antwort des Containers auf eine korrekte Loesung.
UNLOCKED_PAGE_HTML = (
    "<html><body><label class='form_box_title'>"
    "<a class='selecttext' href='https://rapidgator.net/file/abcdef123'>DL</a>"
    "</label></body></html>"
)


class _FakeResponse:
    def __init__(self, text, content=b"", status_code=200, content_type="text/html"):
        self.text = text
        self.content = content or text.encode()
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}


class _SolverResult:
    def __init__(self, text):
        self.text = text
        self.captcha_id = 1234


class AnswerPassthroughTest(unittest.TestCase):
    """Der POST traegt genau die Antwort, die der Solver geliefert hat."""

    def _run_with(self, variant_html, solved_text):
        """Dispatcher laufen lassen, gibt (session, result) zurueck."""
        from bs4 import BeautifulSoup

        dispatcher = DBCDispatcher(state_module=SimpleNamespace(values={
            "user_agent": "Kuasarr-Test",
        }))
        client = MagicMock()
        client.solve_captcha.return_value = _SolverResult(solved_text)
        dispatcher._client = client

        session = MagicMock()
        session.get.return_value = _FakeResponse(
            variant_html, content=b"\x89PNG" + b"0" * 200, content_type="image/png"
        )
        session.post.return_value = _FakeResponse(UNLOCKED_PAGE_HTML)

        soup = BeautifulSoup(variant_html, "html.parser")
        result = dispatcher._solve_keeplinks_captcha(
            session, soup, CONTAINER_URL, {"User-Agent": "Kuasarr-Test"}, "", None
        )
        return session, result

    def test_cool_answer_with_digits_is_posted_unchanged(self):
        """'cool': Ziffern duerfen die Antwort nicht mehr entfernen."""
        session, result = self._run_with(COOL_PAGE_HTML, "f1owled")

        self.assertTrue(session.post.called, "Es wurde nicht gepostet")
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["data"]["captcha_cool"], "f1owled")
        self.assertIsNotNone(result)
        self.assertEqual(result["links"], ["https://rapidgator.net/file/abcdef123"])

    def test_cool_answer_without_any_letter_is_rejected_before_posting(self):
        """'cool' ist alphabetisch - eine reine Ziffernfolge geht nicht raus."""
        session, result = self._run_with(COOL_PAGE_HTML, "1234")

        self.assertFalse(session.post.called, "Reine Ziffern wurden gepostet")
        self.assertIsNone(result)

    def test_simple_answer_with_repeated_glyphs_is_posted_unchanged(self):
        """'simple': 'aabb' wird nicht mehr zu 'ab' zusammengefasst."""
        simple_page = COOL_PAGE_HTML.replace(
            "captchatype' value='Cool", "captchatype' value='Simple"
        ).replace("coolcaptcha/captcha.php", "simplecaptcha/captcha.php")

        session, result = self._run_with(simple_page, "aabb")

        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["data"]["norobot"], "aabb")
        self.assertIsNotNone(result)

    def test_empty_solver_result_is_still_rejected_before_posting(self):
        """Die Normalisierung bleibt als Plausibilitaetspruefung aktiv."""
        session, result = self._run_with(COOL_PAGE_HTML, "123")

        self.assertFalse(session.post.called, "Unbrauchbare Antwort wurde gepostet")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()