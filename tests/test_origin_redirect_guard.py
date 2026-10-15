# -*- coding: utf-8 -*-
"""Tests for the redirect-aware origin guard.

A URL check on the initial request is not sufficient: with
``allow_redirects=True`` a container can answer 302 to an internal host and
``requests`` follows it, carrying the request body along. These tests drive
that path against a local HTTP server.
"""

import threading
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests

from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

TARGET = {}  # urls seen by the handler, per test


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _route(self):
        path = self.path.split("?")[0]
        if path == "/loop":
            # An open redirect chain that stays on the origin.
            self.send_response(302)
            self.send_header("Location", "/loop")
            self.end_headers()
            return True
        if path == "/start":
            self.send_response(302)
            self.send_header("Location", TARGET["location"])
            self.end_headers()
            return True
        if path == "/internal":
            # Stands in for a link-local metadata service.
            TARGET["reached"].append("/internal")
            body = b"SECRET-METADATA"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True
        if path == "/final":
            TARGET["reached"].append("/final")
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True
        return False

    def do_GET(self):
        if not self._route():
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        TARGET.setdefault("bodies", []).append(body)
        if not self._route():
            self.send_response(404)
            self.end_headers()


@pytest.fixture
def origin_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


class TestRedirectGuard:
    """The session must refuse to leave the container origin."""

    def test_same_origin_redirect_is_followed(self, origin_server):
        """A redirect within the origin is normal and has to keep working."""
        TARGET["reached"] = []
        TARGET["location"] = f"{origin_server}/final"

        session = DBCDispatcher._same_origin_guard_for(
            requests.Session(), f"{origin_server}/start")
        response = session.get(f"{origin_server}/start", timeout=10)

        assert response.status_code == 200
        assert response.content == b"OK"
        assert TARGET["reached"] == ["/final"]

    def test_redirect_off_origin_is_refused(self, origin_server):
        """A 302 pointing at another host must raise, not be followed."""
        TARGET["reached"] = []
        TARGET["location"] = "http://169.254.169.254/latest/meta-data/"

        session = DBCDispatcher._same_origin_guard_for(
            requests.Session(), f"{origin_server}/start")

        with pytest.raises(requests.TooManyRedirects):
            session.get(f"{origin_server}/start", timeout=10)

        assert TARGET["reached"] == []

    def test_post_body_is_not_sent_off_origin(self, origin_server):
        """The captcha POST body must not reach a foreign host."""
        TARGET["reached"] = []
        TARGET["bodies"] = []
        TARGET["location"] = "http://evil.example/steal"

        session = DBCDispatcher._same_origin_guard_for(
            requests.Session(), f"{origin_server}/start")

        with pytest.raises(requests.TooManyRedirects):
            session.post(f"{origin_server}/start", data={"myhiddenpwd": "deadbeef"},
                         timeout=10)

        # Nothing beyond /start may have received the hidden field.
        assert TARGET["reached"] == []

    def test_history_is_preserved(self, origin_server):
        """Following a same-origin hop keeps the redirect history."""
        TARGET["reached"] = []
        TARGET["location"] = f"{origin_server}/final"

        session = DBCDispatcher._same_origin_guard_for(
            requests.Session(), f"{origin_server}/start")
        response = session.get(f"{origin_server}/start", timeout=10)

        assert len(response.history) == 1
        assert response.history[0].status_code == 302

    def test_unparsable_base_url_leaves_session_alone(self, origin_server):
        """Without a usable origin host the session is returned untouched."""
        plain = requests.Session()
        assert DBCDispatcher._same_origin_guard_for(plain, "not-a-url") is plain

    def test_redirect_loop_on_the_origin_is_capped(self, origin_server):
        """A same-origin redirect loop must raise, not spin forever.

        Wrapping ``Session.send`` bypasses ``requests``' own hop counting, so
        the guard has to do it itself.
        """
        session = requests.Session()
        session.max_redirects = 3
        guarded = DBCDispatcher._same_origin_guard_for(session, f"{origin_server}/loop")

        with pytest.raises(requests.TooManyRedirects):
            guarded.get(f"{origin_server}/loop", timeout=10)

# --- The FileCrypt path -------------------------------------------------------
#
# The captcha paths above have been guarded since the redirect work landed.
# FileCrypt was not, and it posts the container password the same way. The
# tests below drive that path so it cannot silently lose the guard again.

FILECRYPT_HTML = (
    "<html><body>"
    "<input type=\"password\" name=\"p4assw0rd\">"
    "<form class=\"cnlform\"></form>"
    "<div class=\"container\"><a href=\"https://example.invalid/x\">x</a></div>"
    "</body></html>"
)


class _FilecryptHandler(BaseHTTPRequestHandler):
    """A FileCrypt container whose password POST redirects to another origin."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = FILECRYPT_HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(302)
        self.send_header("Location", TARGET["location"])
        self.end_headers()


class _InternalHandler(BaseHTTPRequestHandler):
    """Stands in for an internal service the redirect must not reach."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        TARGET["internal_hits"].append(self.path)
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        TARGET["internal_bodies"].append(self.rfile.read(length))
        TARGET["internal_hits"].append(self.path)
        self.send_response(200)
        self.end_headers()


def _serve(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def filecrypt_server():
    server, url = _serve(_FilecryptHandler)
    yield url
    server.shutdown()


@pytest.fixture
def internal_server():
    server, url = _serve(_InternalHandler)
    yield url
    server.shutdown()


class TestFilecryptPathIsGuarded:
    """The container password must not follow a redirect to a foreign host."""

    def test_password_post_cannot_be_redirected_off_origin(
            self, filecrypt_server, internal_server, monkeypatch):
        from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

        TARGET["location"] = f"{internal_server}/steal"
        TARGET["internal_hits"] = []
        TARGET["internal_bodies"] = []

        captured = {}

        def fake_bypass(info, shared_state, session, url, headers):
            captured["session"] = session
            response = requests.Response()
            response.status_code = 200
            response.url = url
            response._content = FILECRYPT_HTML.encode()
            return session, headers, response

        monkeypatch.setattr(
            "kuasarr.providers.captcha.dbc_dispatcher.ensure_session_cf_bypassed",
            fake_bypass)

        state = SimpleNamespace(values={"user_agent": "test-agent"})
        dispatcher = DBCDispatcher(state_module=state)

        result = dispatcher._solve_filecrypt_with_dbc(
            title="Some.Release.S01",
            url=f"{filecrypt_server}/Container/ABCD.html",
            password="serienfans.org",
        )

        assert TARGET["internal_hits"] == [], "redirect off the container origin was followed"
        assert TARGET["internal_bodies"] == [], "the password reached a foreign host"
        assert result is None
        # The guard has to be on this exact session object, not a copy.
        assert getattr(captured["session"].send, "__name__", "") == "send"
