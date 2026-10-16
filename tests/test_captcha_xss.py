# -*- coding: utf-8 -*-
"""Fremdbestimmter Inhalt darf auf der CAPTCHA-Seite kein Markup einschleusen.

Der Release-Titel, der Mirror-Name und die Container-URL stammen von der
gescrapten Seite. Wer sie kontrolliert - und bei DDL-Hostern ist das der
Hoster, nicht der Betreiber -, kontrolliert damit auch diese Seite. Vor dem
Fix landeten sie roh in Attributen und Textknoten:

    <option value="{link[0]}">{link[1]}</option>
    <input type="hidden" name="title" value="{title}" />
    <div id="mirrors-select">Mirror: <b>{link[1]}</b></div>

Ein Titel wie ``x" onerror="alert(1)`` genügte, um das value-Attribut zu
verlassen und ein Attribut zu eröffnen, das sofort ausgeführt wird.
"""

import unittest
from unittest.mock import MagicMock, patch

from kuasarr.api.captcha.ui_components import render_bypass_section
from kuasarr.providers.ui.html_templates import render_button

PAYLOAD = '"><img src=x onerror=alert(1)>'
SCRIPT_PAYLOAD = '</script><img src=x onerror=alert(1)>'


class TestRenderButtonEscapes(unittest.TestCase):
    def test_attribute_value_cannot_close_the_attribute(self):
        html = render_button("Go", "primary", {"onclick": PAYLOAD})
        self.assertNotIn('onerror=alert(1)>', html)
        self.assertIn("&quot;", html)

    def test_text_is_escaped(self):
        html = render_button("<b>not bold</b>", "primary")
        self.assertNotIn("<b>not bold</b>", html)
        self.assertIn("&lt;b&gt;not bold&lt;/b&gt;", html)

    def test_ordinary_button_still_works(self):
        """Escaping darf onclick nicht unbrauchbar machen.

        `&#x27;` ist innerhalb eines doppelt gequoteten Attributs genau das
        gleiche wie `'` - der HTML-Parser dekodiert es, bevor JS die Zeile
        sieht. Deshalb wird an dieser Stelle auch `'` escaped und nicht nur
        das Anfuehrungszeichen, das das Attribut wirklich schliessen koennte.
        """
        html = render_button("Zurück", "secondary", {"onclick": "location.href='/'"})
        self.assertIn("btn-secondary", html)
        self.assertIn("Zurück", html)
        self.assertIn("location.href=&#x27;/&#x27;", html)


class TestBypassSectionEscapes(unittest.TestCase):
    def _render(self, **kwargs):
        params = dict(
            url="https://filecrypt.cc/Container/ABC.html",
            package_id="pkg-1",
            title=PAYLOAD,
            password=PAYLOAD,
        )
        params.update(kwargs)
        with patch("kuasarr.api.captcha.ui_components.request") as request:
            request.urlparts.scheme = "http"
            request.urlparts.netloc = "kuasarr:9999"
            return render_bypass_section(**params)

    def test_title_cannot_break_out_of_its_value_attribute(self):
        """Der entscheidende Punkt ist das fehlende rohe ``<``.

        ``onerror=alert(1)`` als Textfolge bleibt im escaped Wert durchaus
        stehen - entscheidend ist, dass es nirgends als Attribut einer neuen
        Marke gelesen werden kann, weil das ``<`` davor zu ``&lt;`` wurde.
        """
        html = self._render()
        self.assertNotIn("<img src=x", html)
        self.assertNotIn('value=""><img', html)

    def test_password_cannot_break_out_of_its_value_attribute(self):
        html = self._render()
        self.assertNotIn('name="password" value=""', html)
        self.assertIn('name="password" value="&quot;&gt;&lt;img', html)

    def test_title_value_is_escaped_verbatim(self):
        html = self._render()
        self.assertIn('name="title" value="&quot;&gt;&lt;img src=x', html)


class _FakeApp:
    def __init__(self):
        self.routes = {}

    def get(self, path):
        def decorator(fn):
            self.routes[path] = fn
            return fn
        return decorator

    post = get


class TestCutcaptchaRouteEscapes(unittest.TestCase):
    """The real route, not a re-implementation of the escaping."""

    def _render(self, mirror_name, title=PAYLOAD):
        from kuasarr.api.captcha import provider_routes

        app = _FakeApp()
        with patch.object(provider_routes, "decode_payload", return_value={
            "package_id": "pkg-1",
            "title": title,
            "password": "",
            "links": [["https://filecrypt.cc/Container/ABC.html", mirror_name]],
        }), \
             patch.object(provider_routes, "check_package_exists"), \
             patch.object(provider_routes, "captcha_values",
                          return_value={"api_key": "k'"}):
            provider_routes.setup_provider_routes(app)
            # The route has to run inside the patch context: outside it the
            # real decode_payload runs, needs a request and hands back None.
            return app.routes["/captcha/cutcaptcha"]()

    def test_mirror_name_cannot_close_the_option(self):
        html = self._render(PAYLOAD)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x", html)

    def test_package_title_cannot_close_its_element(self):
        html = self._render("rapidgator")
        self.assertNotIn("<img src=x", html)

    def test_api_key_cannot_break_out_of_the_js_string(self):
        html = self._render("rapidgator")
        self.assertNotIn("var api_key = \"k'\";", html)
        self.assertIn("var api_key = \"k\\'\";", html)

    def test_title_cannot_close_the_script_element(self):
        """``</script>`` beendet den Script-Block, auch ohne ein einziges Anfuehrungszeichen.

        Der HTML-Parser liest den Inhalt eines ``<script>`` als Rohtext, bis er
        auf ``</script>`` stoesst. Escaping der Anfuehrungszeichen allein
        genuegt darum nicht - der oeffnende Winkel des Schluss-Tags muss auch
        verschwinden.
        """
        html = self._render("rapidgator", title=SCRIPT_PAYLOAD)
        self.assertNotIn(SCRIPT_PAYLOAD, html)
        # Was danach noch als Text uebrig ist, steht in einem JS-String
        # innerhalb eines <script>-Elements und kann dort nichts eroeffnen -
        # entscheidend ist, dass kein oehnender Winkel das Element verlassen kann.
        self.assertIn("title: '\\u003c/script>", html)


if __name__ == "__main__":
    unittest.main()