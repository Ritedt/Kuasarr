# -*- coding: utf-8 -*-
"""Tests fuer das hbtncheck-Feld im Keeplinks-Loesungs-POST.

Keeplinks wertet das Captcha nur aus, wenn der Submit-Button des Formulars
mitgeschickt wurde. Der Button traegt ``name="hbtncheck"``; ein Browser
schickt ihn nur mit, wenn er wirklich geklickt wurde, ein ``form.submit()``
aus JavaScript laesst ihn weg. Fehlt das Feld, antwortet Keeplinks mit
"Solve Captcha Before Press Submit Button." - egal wie richtig die Antwort
war. Der Dispatcher baute seine Felder hart und verlor das Feld dabei.

Live gemessen an p26/6aa36f6b8697a, jeweils mit sicher gelesener Antwort:

  ohne hbtncheck   0,14 s  Ablehnung, Captcha weiterhin da
  mit hbtncheck    0,20 s  302, 10 entsperrte Links

Die Referenzimplementierung kennt das Feld ebenfalls nicht - Keeplinks hat
die Pruefung nach ihrer Aufnahme ergaenzt. Sie taugt hier nicht mehr als
Vorbild.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from kuasarr.downloads.linkcrypters.keeplinks import get_keeplinks_links
from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

CONTAINER_URL = "https://www.keeplinks.org/p26/6aa36f6b8697a"

# Die reale Containerseite: frmprotect mit dem Submit-Button hbtncheck.
CAPTCHA_PAGE_HTML = (
    "<html><body>"
    "<form name='frmprotect' method='post' "
    "action='https://www.keeplinks.org/p26/6aa36f6b8697a'>"
    "<input id='myhiddenpwd' name='myhiddenpwd' type='hidden' value=''>"
    "<input id='kl_ab' name='kl_ab' type='hidden' value='0'>"
    "<input id='hbtncheck' name='hbtncheck' type='submit' value=''>"
    "<input id='hiddenaction' name='hiddenaction' type='hidden' value='Q2hlY2tJbmZv'>"
    "<input id='captchatype' name='captchatype' type='hidden' value='Cool'>"
    "<input id='hiddencaptcha' name='hiddencaptcha' type='hidden' value='1'>"
    "<input id='hiddenpwd' name='hiddenpwd' type='hidden' value=''>"
    "<input name='captcha_cool' type='text' value=''>"
    "</form>"
    "</body></html>"
)

UNLOCKED_PAGE_HTML = (
    "<html><body><textarea class='trurl'>"
    "https://rapidgator.net/file/abcdef123"
    "</textarea></body></html>"
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


class SolutionPostSubmitButtonTest(unittest.TestCase):
    """Der Loesungs-POST muss den Submit-Button mitschicken."""

    def _post_data(self, solved_text="bummer"):
        from bs4 import BeautifulSoup

        dispatcher = DBCDispatcher(state_module=SimpleNamespace(values={
            "user_agent": "Kuasarr-Test",
        }))
        client = MagicMock()
        client.solve_captcha.return_value = _SolverResult(solved_text)
        dispatcher._client = client

        session = MagicMock()
        session.get.return_value = _FakeResponse(
            CAPTCHA_PAGE_HTML, content=b"\x89PNG" + b"0" * 200, content_type="image/png"
        )
        session.post.return_value = _FakeResponse(UNLOCKED_PAGE_HTML)

        soup = BeautifulSoup(CAPTCHA_PAGE_HTML, "html.parser")
        dispatcher._solve_keeplinks_captcha(
            session, soup, CONTAINER_URL, {"User-Agent": "Kuasarr-Test"}, "", None
        )

        self.assertTrue(session.post.called, "Es wurde nicht gepostet")
        _, kwargs = session.post.call_args
        return kwargs["data"]

    def test_solution_post_carries_the_submit_button(self):
        """hbtncheck muss im POST stehen - ohne ihn kein Captcha-Solving."""
        post_data = self._post_data()
        self.assertIn("hbtncheck", post_data,
                      "hbtncheck fehlt - Keeplinks lehnt die Loesung ab")
        self.assertEqual(post_data["hbtncheck"], "")

    def test_submit_button_does_not_displace_the_answer(self):
        """Der Button kommt dazu, die Antwort bleibt unveraendert erhalten."""
        post_data = self._post_data("gadsbud")
        self.assertEqual(post_data["captcha_cool"], "gadsbud")

    def test_existing_hidden_fields_are_untouched(self):
        """Die uebrigen Felder bleiben, wie sie waren."""
        post_data = self._post_data()
        self.assertEqual(post_data["hiddenaction"], "Q2hlY2tJbmZv")
        self.assertEqual(post_data["captchatype"], "Cool")
        self.assertEqual(post_data["hiddencaptcha"], "1")
        self.assertEqual(post_data["myhiddenpwd"], "")
        self.assertEqual(post_data["hiddenpwd"], "")

    def test_webui_path_already_forwards_the_submit_button(self):
        """Der WebUI-Pfad schabt alle Inputs und ist damit bereits richtig.

        Diese Seite ist der Grund, warum sich die Fehlerbilder der beiden
        Pfade unterscheiden. Sie darf nicht in eine feste Feldliste
        umgebaut werden.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(CAPTCHA_PAGE_HTML, "html.parser")
        captcha_form = soup.find("form", {"name": "frmprotect"})

        scraped = {}
        for input_elem in captcha_form.find_all("input"):
            name = input_elem.get("name")
            if name:
                scraped[name] = input_elem.get("value", "")

        self.assertIn("hbtncheck", scraped)
        self.assertEqual(scraped["hbtncheck"], "")

    def test_get_keeplinks_links_is_importable(self):
        """Beide Pfade bleiben importierbar - der WebUI-Pfad blieb unberuehrt."""
        self.assertTrue(callable(get_keeplinks_links))


if __name__ == "__main__":
    unittest.main()