# -*- coding: utf-8 -*-
"""Regression test for the hide.cx provider route.

``download_package`` takes ``package_id`` as its fourth argument. The route
omitted it, so every hide.cx decryption started from the WebUI died with a
TypeError before a single link reached JDownloader.
"""

import pytest

from kuasarr.api.captcha import provider_routes


class _FakeApp:
    """Collects whatever setup_provider_routes registers."""

    def __init__(self):
        self.routes = {}

    def get(self, path):
        def decorator(fn):
            self.routes[path] = fn
            return fn
        return decorator

    post = get


class _FakeDB:
    def __init__(self, captured):
        self._captured = captured

    def delete(self, package_id):
        self._captured["deleted"] = package_id

    def retrieve_all_titles(self):
        return []


class _FakeSharedState:
    def __init__(self, captured):
        self._captured = captured

    def download_package(self, links, title, password, package_id, destination_folder=None):
        # Mirrors the real signature on purpose: a call that omits package_id
        # raises TypeError here, which is the production failure being guarded.
        self._captured["package"] = {
            "links": links,
            "title": title,
            "password": password,
            "package_id": package_id,
        }
        return True

    def get_db(self, name):
        return _FakeDB(self._captured)


@pytest.fixture
def hide_route(monkeypatch):
    app = _FakeApp()
    provider_routes.setup_provider_routes(app)
    captured = {}

    monkeypatch.setattr(
        provider_routes, "decode_payload",
        lambda: {
            "package_id": "pkg-123",
            "title": "Some.Release.S01",
            "password": "the-password",
            "links": ["https://hide.cx/abc"],
        },
    )
    monkeypatch.setattr(provider_routes, "check_package_exists", lambda package_id: None)
    monkeypatch.setattr(
        provider_routes, "unhide_links",
        lambda shared_state, url, password: (["https://rapidgator.net/file/x"], None),
    )
    monkeypatch.setattr(provider_routes, "shared_state", _FakeSharedState(captured))

    return app.routes["/captcha/hide"], captured


def test_hide_route_hands_the_package_id_to_download_package(hide_route):
    """The decrypted links have to arrive at JDownloader, not blow up."""
    route, captured = hide_route

    route()

    assert "package" in captured, "download_package was never reached"
    package = captured["package"]
    assert package["links"] == ["https://rapidgator.net/file/x"]
    assert package["title"] == "Some.Release.S01"
    assert package["password"] == "the-password"
    assert package["package_id"] == "pkg-123"
    assert captured["deleted"] == "pkg-123", "the solved package was not cleaned up"
