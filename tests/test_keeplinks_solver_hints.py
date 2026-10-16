# -*- coding: utf-8 -*-
"""Tests fuer die Solver-Hinweise beim Keeplinks-Captcha.

Keeplinks weiss genau, wie die Antwort aussehen muss: "cool" ist ein
verzerrtes Wort aus Buchstaben, "simple" ist eine feste vierstellige Zahl.
Diese Information wurde dem Solver nie mitgegeben - er bekam nur ein Bild
und durfte raten. Die Referenzimplementierung gibt sie mit
(2Captcha-``ImageToTextTask``-Semantik: numeric=1 nur Ziffern,
numeric=2 nur Buchstaben, plus minLen/maxLen).

Geprueft wird beides: dass der Dispatcher die richtigen Hinweise uebergibt
und dass der 2Captcha-Client sie in den Task schreibt, ohne dass ein
Aufrufer ohne Hinste davon betroffen ist.
"""

import base64
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from kuasarr.providers.captcha.dbc_dispatcher import (
    KEEPLINKS_ANSWER_LENGTH,
    KEEPLINKS_SOLVER_HINTS,
    DBCDispatcher,
)
from kuasarr.providers.captcha.twocaptcha_client import TwoCaptchaClient

CONTAINER_URL = "https://www.keeplinks.org/p26/6aa36f6b8697a"


def _captcha_page(variant):
    """Containerseite mit dem Captcha-Bild der jeweiligen Variante."""
    return (
        "<html><body>"
        "<form name='frmprotect' method='post'>"
        f"<input type='hidden' name='captchatype' value='{variant.title()}'>"
        "<input type='hidden' name='hiddenpwd' value=''>"
        f"<img src='https://www.keeplinks.org/{variant}captcha/captcha.php'>"
        "</form>"
        "</body></html>"
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


class SolverHintDispatchTest(unittest.TestCase):
    """Der Dispatcher uebergibt die Hinweise der erkannten Variante."""

    def _solver_call_kwargs(self, variant):
        from bs4 import BeautifulSoup

        dispatcher = DBCDispatcher(state_module=SimpleNamespace(values={
            "user_agent": "Kuasarr-Test",
        }))
        client = MagicMock()
        client.solve_captcha.return_value = _SolverResult("abcd")
        dispatcher._client = client

        session = MagicMock()
        session.get.return_value = _FakeResponse(
            _captcha_page(variant), content=b"\x89PNG" + b"0" * 200,
            content_type="image/png",
        )
        session.post.return_value = _FakeResponse("<html></html>")

        page = _captcha_page(variant)
        dispatcher._solve_keeplinks_captcha(
            session, BeautifulSoup(page, "html.parser"), CONTAINER_URL,
            {"User-Agent": "Kuasarr-Test"}, "", None,
        )
        return client.solve_captcha.call_args

    def test_cool_gets_letters_only(self):
        """'cool' akzeptiert nur Buchstaben."""
        _, kwargs = self._solver_call_kwargs("cool")
        self.assertEqual(kwargs["numeric"], 2)
        self.assertNotIn("min_len", kwargs)
        self.assertNotIn("max_len", kwargs)

    def test_simple_gets_four_digits(self):
        """'simple' akzeptiert genau vier Ziffern."""
        _, kwargs = self._solver_call_kwargs("simple")
        self.assertEqual(kwargs["numeric"], 1)
        self.assertEqual(kwargs["min_len"], 4)
        self.assertEqual(kwargs["max_len"], 4)
        self.assertEqual(kwargs["min_len"], KEEPLINKS_ANSWER_LENGTH)

    def test_hints_cover_both_variants(self):
        """Beide Varianten sind hinterlegt - keine faellt auf 'leer' zurueck."""
        self.assertEqual(set(KEEPLINKS_SOLVER_HINTS), {"cool", "simple"})
        for hints in KEEPLINKS_SOLVER_HINTS.values():
            self.assertIn("numeric", hints)


class TwoCaptchaTaskTest(unittest.TestCase):
    """Der 2Captcha-Client schreibt die Hinweise in den Task."""

    def _task_for(self, **kwargs):
        client = TwoCaptchaClient(api_key="k", timeout=10, max_retries=1,
                                  retry_backoff=1)
        client.get_balance = MagicMock()
        client._create_task = MagicMock(return_value=42)
        client._get_task_result = MagicMock(
            return_value=SimpleNamespace(text="abcd", is_correct=True,
                                         status="solved", captcha_id=42)
        )
        client.solve_captcha(b"\x89PNG-fake", **kwargs)
        return client._create_task.call_args[0][0]

    def test_numeric_lands_in_task(self):
        task = self._task_for(numeric=2)
        self.assertEqual(task["numeric"], 2)
        self.assertNotIn("minLen", task)
        self.assertNotIn("maxLen", task)

    def test_length_hints_land_in_task(self):
        task = self._task_for(numeric=1, min_len=4, max_len=4)
        self.assertEqual(task["numeric"], 1)
        self.assertEqual(task["minLen"], 4)
        self.assertEqual(task["maxLen"], 4)

    def test_task_stays_plain_without_hints(self):
        """Aufrufer ohne Hinste bekommen unveraendert den bisherigen Task."""
        task = self._task_for()
        self.assertEqual(task, {
            "type": "ImageToTextTask",
            "body": base64.b64encode(b"\x89PNG-fake").decode("utf-8"),
        })

    def test_body_is_untouched_by_the_hints(self):
        """Die Hinste duerfen das Bild nicht veraendern."""
        task = self._task_for(numeric=2)
        self.assertEqual(task["type"], "ImageToTextTask")
        self.assertTrue(task["body"])


if __name__ == "__main__":
    unittest.main()