# -*- coding: utf-8 -*-
"""Regression tests for the FileCrypt proof-of-work gate on the dispatcher path.

The dispatcher (automatic solving) and the WebUI submission route (manual
solving) are two separate implementations of the same FileCrypt flow. Only the
manual one learned about the proof-of-work gate, so the dispatcher treated a PoW
page as an image/cut captcha, asked a captcha service for a token that no service
can ever produce, and reported the result as a rejected token.
"""

import unittest

import requests
from types import SimpleNamespace
from unittest.mock import patch

from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

# A FileCrypt page that is gated by the proof-of-work. Real pages carry ~650 kB of
# ads around it; only the marker matters for detection.
POW_PAGE_HTML = (
    "<html><head><title>Filecrypt</title></head>"
    "<body><div id=\"pow-captcha\" class=\"pow-captcha\"></div></body></html>"
)

# What the page looks like once the browser cleared the gate: the container form
# plus the download block the dispatcher extracts links from.
SOLVED_PAGE_HTML = (
    "<html><head><title>Filecrypt</title></head><body>"
    "<form class=\"cnlform\"></form>"
    "<div class=\"container\">"
    "<div class=\"dlpart\">"
    "<a href=\"https://rapidgator.net/file/abc\" class=\"ln\">rapidgator</a>"
    "</div></div></body></html>"
)


class _FakeResponse:
    def __init__(self, text, url="https://filecrypt.cc/Container/468F7D93BA.html",
                 status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code


def _make_dispatcher():
    state_module = SimpleNamespace(values={"user_agent": "test-agent"})
    return DBCDispatcher(state_module=state_module)


class TestDispatcherHandlesPowGate(unittest.TestCase):
    """The dispatcher must solve the PoW gate, not ask a captcha service for a token."""

    def test_pow_page_is_solved_by_the_browser_not_by_a_captcha_service(self):
        dispatcher = _make_dispatcher()
        solved = _FakeResponse(SOLVED_PAGE_HTML)

        with patch(
            "kuasarr.providers.captcha.dbc_dispatcher.ensure_session_cf_bypassed",
            return_value=(requests.Session(), {"User-Agent": "test-agent"}, _FakeResponse(POW_PAGE_HTML)),
        ), patch(
            "kuasarr.providers.captcha.dbc_dispatcher._submit_pow_challenge",
            return_value=solved,
        ) as mock_pow, patch.object(
            dispatcher, "_get_captcha_token", return_value="should-not-be-called"
        ) as mock_token:
            dispatcher._solve_filecrypt_with_dbc(
                title="American.Dad.S16",
                url="https://filecrypt.cc/Container/468F7D93BA.html",
                password=None,
            )

        self.assertEqual(
            mock_pow.call_count, 1,
            "A Filecrypt page showing #pow-captcha must go through the browser PoW solve",
        )
        mock_token.assert_not_called()

    def test_failed_pow_solve_stops_instead_of_posting_a_bogus_token(self):
        """Without a solved page there is nothing to post, so the link must fail cleanly."""
        dispatcher = _make_dispatcher()

        with patch(
            "kuasarr.providers.captcha.dbc_dispatcher.ensure_session_cf_bypassed",
            return_value=(requests.Session(), {"User-Agent": "test-agent"}, _FakeResponse(POW_PAGE_HTML)),
        ), patch(
            "kuasarr.providers.captcha.dbc_dispatcher._submit_pow_challenge",
            return_value=None,
        ) as mock_pow:
            result = dispatcher._solve_filecrypt_with_dbc(
                title="American.Dad.S16",
                url="https://filecrypt.cc/Container/468F7D93BA.html",
                password=None,
            )

        self.assertEqual(mock_pow.call_count, 1)
        self.assertIsNone(result)

    def test_plain_captcha_page_still_asks_the_captcha_service(self):
        """The PoW branch must not swallow the captcha types that do need a service."""
        dispatcher = _make_dispatcher()
        captcha_page = (
            "<html><body><div class=\"container\"></div>"
            "<img id=\"captcha_img\" src=\"https://filecrypt.cc/captcha.jpg\"></body></html>"
        )

        with patch(
            "kuasarr.providers.captcha.dbc_dispatcher.ensure_session_cf_bypassed",
            return_value=(requests.Session(), {"User-Agent": "test-agent"}, _FakeResponse(captcha_page)),
        ), patch(
            "kuasarr.providers.captcha.dbc_dispatcher._submit_pow_challenge",
        ) as mock_pow, patch.object(
            dispatcher, "_get_captcha_token", return_value="the-token"
        ) as mock_token:
            dispatcher._solve_filecrypt_with_dbc(
                title="American.Dad.S16",
                url="https://filecrypt.cc/Container/468F7D93BA.html",
                password=None,
            )

        mock_pow.assert_not_called()
        self.assertEqual(mock_token.call_count, 1)


if __name__ == "__main__":
    unittest.main()