# -*- coding: utf-8 -*-
"""The Circle-Captcha fallback must produce a URL the container answers on.

The fallback built its per-link URL from the bare netloc, hardcoding
``http://``. FileCrypt serves containers over https and answers that http URL
with a 302 to the same host over https. The origin guard - which pins a session
to the container's origin - reads such a redirect as leaving that origin and
refuses it, so every Circle-Captcha attempt failed with::

    Circle-Captcha attempt 1 failed: Refusing to follow redirect off the
    container origin: ('https', 'filecrypt.cc', 443)

which reads as if the guard were refusing the container's own origin. It was
refusing a plain-http origin that FileCrypt never serves.
"""

import unittest
from types import SimpleNamespace

import requests
from bs4 import BeautifulSoup

from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher
from kuasarr.providers.network.origin_guard import origin_of

# A solved container whose Click'n'Load form and DLC button are both unusable.
BUTTON_ONLY_PAGE = (
    "<html><body><div class=\"container\"><table><tr>"
    "<td><a class=\"external_link\">rapidgator</a></td>"
    "<td><button data-id=\"490996A648\" data-i18n=\"go\">Go</button></td>"
    "</tr></table></div></body></html>"
)


class _State(SimpleNamespace):
    pass


def _state():
    return _State(values={"user_agent": "test-agent"})


def _session():
    """A session carrying the container session the fallback needs to proceed."""
    session = requests.Session()
    session.cookies.set("PHPSESSID", "container-session", domain="filecrypt.cc", path="/")
    return session


class TestCircleFallbackKeepsTheContainerScheme(unittest.TestCase):
    def _fallback(self, container_url):
        dispatcher = DBCDispatcher(state_module=_state())
        soup = BeautifulSoup(BUTTON_ONLY_PAGE, "html.parser")
        return dispatcher._extract_filecrypt_links(
            _session(), soup, container_url, "Family.Guy.S21E01", {"User-Agent": "test-agent"}
        )

    def test_https_container_yields_an_https_link_url(self):
        result = self._fallback("https://filecrypt.cc/Container/E440886DD7.html")

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "replaced")
        self.assertTrue(
            result["replace_url"].startswith("https://"),
            f"a https container must not be handed a plain-http URL: {result['replace_url']}",
        )

    def test_the_link_url_is_pinned_to_the_container_origin(self):
        """The pinned origin has to be the one the redirect target is on."""
        container = "https://filecrypt.cc/Container/E440886DD7.html"
        result = self._fallback(container)

        self.assertEqual(
            origin_of(result["replace_url"]),
            origin_of(container),
            "the Circle-Captcha step would start on a different origin than the container",
        )

    def test_a_plain_http_container_still_stays_plain_http(self):
        """No silent upgrade: the fix mirrors the container, it does not force https."""
        result = self._fallback("http://filecrypt.cc/Container/E440886DD7.html")

        self.assertTrue(result["replace_url"].startswith("http://"))


if __name__ == "__main__":
    unittest.main()