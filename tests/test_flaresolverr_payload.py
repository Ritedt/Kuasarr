# -*- coding: utf-8 -*-
"""Tests for the FlareSolverr payload that actually leaves the process.

The wait fix in ``imdb_metadata`` shipped broken: ``flaresolverr_get`` never
accepted ``wait``, so the call raised TypeError and every IMDb search failed
with "unexpected keyword argument". The unit tests did not catch it because
they replaced ``flaresolverr_get`` with a mock, and a MagicMock accepts any
keyword argument it is given.

These tests therefore assert against the real call chain - a stubbed
``requests.post`` - so a wrapper that drops or rejects a parameter fails here
instead of in production.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from kuasarr.providers.imdb_metadata import (
    IMDB_WAF_SETTLE_SECONDS,
    get_localized_title,
)
from kuasarr.providers.network.cloudflare import flaresolverr_get


class _FakeConfigSection:
    """Stand-in for ``Config('FlareSolverr')`` - only ``.get`` is ever called."""

    def __init__(self, values):
        self._values = values

    def get(self, key):
        return self._values.get(key)


class _FakeConfig:
    """shared_state.values["config"] is a callable, not a plain dict."""

    def __init__(self, sections):
        self._sections = sections

    def __call__(self, section):
        return _FakeConfigSection(self._sections.get(section, {}))


def _mock_shared_state(flaresolverr_url="http://flaresolverr.invalid/v1"):
    """shared_state with the parts the real code path touches.

    The ``config`` indirection is exactly what a bare MagicMock hides - and why
    the earlier mock-based test passed against a wrapper that could not accept
    ``wait`` at all.
    """
    state = MagicMock()
    state.values = {
        "user_agent": "TestBot/1.0",
        "config": _FakeConfig({"FlareSolverr": {"url": flaresolverr_url}}),
    }
    state.get_recently_searched = lambda _self, context, threshold: {}
    state.update = lambda context, data: None
    return state


@pytest.fixture
def captured_payload():
    """Capture the JSON body that flaresolverr_request posts to FlareSolverr."""
    payload = {}

    def fake_post(_url, **kwargs):
        payload.update(kwargs["json"])
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "status": "ok",
            "solution": {"url": "https://www.imdb.com/title/tt0397306/",
                         "status": 200, "headers": {}, "response": "<html>ok</html>"},
        }
        return response

    with patch("kuasarr.providers.network.cloudflare.requests.post", side_effect=fake_post):
        yield payload


class TestWaitReachesFlaresolverr:

    def test_get_forwards_wait_into_the_payload(self, captured_payload):
        """The wrapper has to pass wait through, not swallow it.

        This is the regression: flaresolverr_request understood wait all along,
        but the get wrapper did not accept it, so the keyword never arrived.
        """
        flaresolverr_get(_mock_shared_state(), "https://www.imdb.com/title/tt0397306/",
                         wait=IMDB_WAF_SETTLE_SECONDS)

        assert captured_payload.get("waitInSeconds") == IMDB_WAF_SETTLE_SECONDS

    def test_wait_is_omitted_when_not_requested(self, captured_payload):
        """No wait means no key - standard FlareSolverr rejects unknown keys."""
        flaresolverr_get(_mock_shared_state(), "https://www.imdb.com/title/tt0397306/")

        assert "waitInSeconds" not in captured_payload

    def test_imdb_lookup_sends_the_wait_it_needs(self, captured_payload):
        """The real lookup must produce a solvable request, not just a valid call.

        Asserting only that the call does not raise would pass against a
        wrapper that silently drops the parameter, which is what happened.
        """
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=202, text="")

            get_localized_title(state, "tt0397306")

        assert captured_payload.get("url") == "https://www.imdb.com/title/tt0397306/"
        assert captured_payload.get("cmd") == "request.get"
        assert captured_payload.get("waitInSeconds") == IMDB_WAF_SETTLE_SECONDS

    def test_payload_is_valid_json_serialisable(self, captured_payload):
        """The body goes over the wire as JSON - no exotic types may leak in."""
        flaresolverr_get(_mock_shared_state(), "https://example.invalid/", wait=5)

        # Re-serialising is what requests.post does before sending.
        assert json.loads(json.dumps(captured_payload)) == captured_payload