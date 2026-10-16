# -*- coding: utf-8 -*-
"""Tests for kuasarr.providers.imdb_metadata."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from kuasarr.providers.imdb_metadata import (
    IMDB_WAF_SETTLE_SECONDS,
    _extract_title_from_html,
    _is_waf_challenge,
    get_clean_title,
    get_localized_title,
)


# ---------------------------------------------------------------------------
# Helpers to build IMDb-like HTML snippets
# ---------------------------------------------------------------------------

def _make_jsonld_html(title):
    """IMDb page with a JSON-LD block containing *title*."""
    import json
    return f"""<html><head>
<script type="application/ld+json">{json.dumps({"@type": "TVSeries", "name": title})}</script>
</head><body></body></html>"""


def _make_next_data_html(title):
    """IMDb page with a __NEXT_DATA__ block containing *title*."""
    import json
    blob = {
        "props": {
            "pageProps": {
                "aboveTheFoldData": {
                    "titleText": {"text": title}
                }
            }
        }
    }
    return f"""<html><head>
<script id="__NEXT_DATA__" type="application/json">{json.dumps(blob)}</script>
</head><body></body></html>"""


def _make_title_tag_html(title_text):
    """IMDb page with only a <title> tag (legacy format)."""
    return f"<html><head><title>{title_text}</title></head><body></body></html>"


def _make_empty_html():
    return "<html><head></head><body></body></html>"


def _make_waf_challenge_html():
    """The AWS WAF interstitial IMDb serves instead of the page.

    Real one is ~2 kB and announces itself twice: the cookie-domain list and
    the challenge script it fetches from a us-east-1 awswaf.com host.
    """
    return """<html lang="en"><head>
<title></title>
<script>window.awsWafCookieDomainList = ['imdb.com']; window.gokuProps = {"key":"AQID"};</script>
<script src="https://fb423e1ef94f.6277d64d.us-east-1.token.awswaf.com/fb423e1ef94f/c3382d439950/916d943f6a58/challenge.js"></script>
</head><body><div id="challenge-container"></div>
<noscript><h1>JavaScript is disabled</h1></noscript></body></html>"""


def _make_served_page_html(title):
    """A served IMDb page, which carries the WAF marker in its own scripts.

    Measured against imdb.com: the 2 kB interstitial and the real 2.4 MB page
    both contain awsWafCookieDomainList and the awswaf.com challenge script.
    The marker alone therefore cannot tell the two apart.
    """
    import json
    return f"""<html><head>
<script>window.awsWafCookieDomainList = ['imdb.com'];</script>
<script src="https://x.token.awswaf.com/x/challenge.js"></script>
<script type="application/ld+json">{json.dumps({"@type": "TVSeries", "name": title})}</script>
</head><body></body></html>"""


# ---------------------------------------------------------------------------
# _extract_title_from_html
# ---------------------------------------------------------------------------

class TestExtractTitleFromHtml:

    def test_jsonld_extracts_name(self):
        html = _make_jsonld_html("American Dad")
        assert _extract_title_from_html(html) == "American Dad"

    def test_jsonld_with_html_entities(self):
        html = _make_jsonld_html("Die Fascinierenden &lt;Wunder&gt;")
        assert _extract_title_from_html(html) == "Die Fascinierenden <Wunder>"

    def test_jsonld_with_german_umlauts(self):
        html = _make_jsonld_html("Die Ärzte - Türkisch für Anfänger")
        assert _extract_title_from_html(html) == "Die Ärzte - Türkisch für Anfänger"

    def test_next_data_extracts_title_text(self):
        html = _make_next_data_html("Shawshank Redemption")
        assert _extract_title_from_html(html) == "Shawshank Redemption"

    def test_next_data_with_html_entities(self):
        html = _make_next_data_html("Tom &amp; Jerry")
        assert _extract_title_from_html(html) == "Tom & Jerry"

    def test_title_tag_strips_imdb_suffix(self):
        html = _make_title_tag_html("Breaking Bad - IMDb")
        assert _extract_title_from_html(html) == "Breaking Bad"

    def test_title_tag_strips_pipe_suffix(self):
        html = _make_title_tag_html("The Wire | IMDb")
        assert _extract_title_from_html(html) == "The Wire"

    def test_title_tag_strips_parenthetical(self):
        html = _make_title_tag_html("American Dad! (TV Series 2005\u20132023) - IMDb")
        assert _extract_title_from_html(html) == "American Dad!"

    def test_title_tag_with_year_only(self):
        html = _make_title_tag_html("The Matrix (1999) - IMDb")
        assert _extract_title_from_html(html) == "The Matrix"

    def test_jsonld_takes_priority_over_title_tag(self):
        """When both JSON-LD and <title> exist, JSON-LD wins."""
        import json
        page = f"""<html><head>
<script type="application/ld+json">{json.dumps({"name": "From JSON-LD"})}</script>
<title>From Title Tag - IMDb</title>
</head><body></body></html>"""
        assert _extract_title_from_html(page) == "From JSON-LD"

    def test_next_data_fallback_when_no_jsonld(self):
        """When no JSON-LD, __NEXT_DATA__ is used."""
        html = _make_next_data_html("From Next Data")
        assert _extract_title_from_html(html) == "From Next Data"

    def test_title_tag_fallback_when_no_structured_data(self):
        """When no JSON-LD or __NEXT_DATA__, <title> is used."""
        html = _make_title_tag_html("Fallback Title - IMDb")
        assert _extract_title_from_html(html) == "Fallback Title"

    def test_returns_none_on_empty_html(self):
        assert _extract_title_from_html(_make_empty_html()) is None

    def test_returns_none_on_minimal_html(self):
        assert _extract_title_from_html("<html></html>") is None

    def test_jsonld_with_empty_name_falls_through(self):
        """JSON-LD with name="" should fall through to next strategy."""
        import json
        page = f"""<html><head>
<script type="application/ld+json">{json.dumps({"name": ""})}</script>
<title>Fallback - IMDb</title>
</head><body></body></html>"""
        assert _extract_title_from_html(page) == "Fallback"

    def test_jsonld_with_invalid_json_falls_through(self):
        """Malformed JSON-LD should not crash, falls through."""
        page = """<html><head>
<script type="application/ld+json">{invalid json</script>
<title>Fallback - IMDb</title>
</head><body></body></html>"""
        assert _extract_title_from_html(page) == "Fallback"

    def test_next_data_with_missing_title_text_falls_through(self):
        """__NEXT_DATA__ without titleText.text falls through."""
        import json
        blob = {"props": {"pageProps": {"aboveTheFoldData": {"titleText": {}}}}}
        page = f"""<html><head>
<script id="__NEXT_DATA__" type="application/json">{json.dumps(blob)}</script>
<title>Fallback - IMDb</title>
</head><body></body></html>"""
        assert _extract_title_from_html(page) == "Fallback"

    def test_realistic_imdb_page(self):
        """Test with a realistic IMDb HTML structure combining all three."""
        import json
        ld = json.dumps({"@type": "TVSeries", "name": "American Dad!"})
        page = f"""<!DOCTYPE html><html><head>
<meta charset="utf-8"/>
<script type="application/ld+json">{ld}</script>
<title>American Dad! (TV Series 2005\u20132023) - IMDb</title>
</head><body><div>content</div></body></html>"""
        assert _extract_title_from_html(page) == "American Dad!"


# ---------------------------------------------------------------------------
# get_localized_title  (mocked HTTP + cache)
# ---------------------------------------------------------------------------

def _mock_shared_state(cache=None):
    """Build a lightweight shared_state mock."""
    state = MagicMock()
    state.values = {"user_agent": "TestBot/1.0"}

    # In-memory cache store
    _store = dict(cache or {})

    def fake_get_recently_searched(_, context, threshold):
        return _store

    state.get_recently_searched = fake_get_recently_searched

    # update writes back into _store
    def fake_update(context, data):
        _store.update(data)

    state.update = fake_update

    return state


class TestGetLocalizedTitle:

    @pytest.fixture(autouse=True)
    def _no_api_tier(self):
        """Keep this class focused on the HTML/FlareSolverr tier.

        There is no longer a JSON API tier in front of the imdb.com scrape:
        the former api.imdbapi.dev endpoint stopped resolving entirely and was
        removed (see imdb_metadata_api.py). ``search_imdb_id`` still exists
        for the title -> id direction and is switched off here so these tests
        keep measuring only what they were written to measure.
        """
        from kuasarr.providers import imdb_metadata_api
        assert not hasattr(imdb_metadata_api, "get_localized"), (
            "Der JSON-API-Tier fuer lokalisierte Titel ist entfernt - wenn er "
            "zurueckkommt, hat dieser Test hier eine Antwort darauf."
        )
        with patch.object(imdb_metadata_api, "search_imdb_id", return_value=None):
            yield

    def test_returns_title_from_successful_request(self):
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = _make_jsonld_html("Shawshank Redemption")
            mock_get.return_value = mock_resp

            result = get_localized_title(state, "tt0111161")
            assert result == "Shawshank Redemption"

    def test_returns_none_when_all_requests_fail(self):
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.return_value = MagicMock(status_code=403, text="")
            mock_fs.side_effect = RuntimeError("no FS")

            result = get_localized_title(state, "tt0000000")
            assert result is None

    def test_falls_back_to_flaresolverr_on_403(self):
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.return_value = MagicMock(status_code=403, text="")
            fs_resp = MagicMock()
            fs_resp.text = _make_jsonld_html("American Dad!")
            fs_resp.status_code = 200
            mock_fs.return_value = fs_resp

            result = get_localized_title(state, "tt0397306")
            # Title sanitizer strips "!" — only alphanumeric + umlauts + &-' kept
            assert result == "American Dad"
            mock_fs.assert_called_once()

    def test_caches_successful_result(self):
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = _make_jsonld_html("The Matrix")
            mock_get.return_value = mock_resp

            # First call hits HTTP
            result1 = get_localized_title(state, "tt0133093")
            assert result1 == "The Matrix"
            assert mock_get.call_count == 1

            # Second call should be cached
            result2 = get_localized_title(state, "tt0133093")
            assert result2 == "The Matrix"
            assert mock_get.call_count == 1  # no additional HTTP call

    def test_caches_none_for_1_hour(self):
        """A None result should be cached and returned for 1 hour."""
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.return_value = MagicMock(status_code=403, text="")
            mock_fs.side_effect = RuntimeError("down")

            # First call: caches None
            result1 = get_localized_title(state, "tt0000000")
            assert result1 is None

            # Reset mocks to prove second call doesn't hit HTTP
            mock_get.reset_mock()
            mock_fs.reset_mock()

            # Second call: should return cached None without HTTP
            result2 = get_localized_title(state, "tt0000000")
            assert result2 is None
            mock_get.assert_not_called()

    def test_sanitizes_special_characters(self):
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = _make_jsonld_html("Hello (World)! @#$%")
            mock_get.return_value = mock_resp

            result = get_localized_title(state, "tt0000001")
            # Only printable safe chars remain
            assert "@" not in result
            assert "#" not in result

    def test_language_param_passed_to_request(self):
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = _make_jsonld_html("irgendein Titel")
            mock_get.return_value = mock_resp

            get_localized_title(state, "tt0111161", language="en")
            call_headers = mock_get.call_args[1].get("headers") or mock_get.call_args.kwargs.get("headers")
            assert call_headers.get("Accept-Language") == "en"

    def test_connection_error_falls_back_to_flaresolverr(self):
        import requests as real_requests
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.side_effect = real_requests.exceptions.ConnectionError("timeout")
            fs_resp = MagicMock()
            fs_resp.text = _make_jsonld_html("Rescued Title")
            fs_resp.status_code = 200
            mock_fs.return_value = fs_resp

            result = get_localized_title(state, "tt0000002")
            assert result == "Rescued Title"

    def test_empty_html_returns_none(self):
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "<html><head></head><body></body></html>"
            mock_get.return_value = mock_resp

            result = get_localized_title(state, "tt0000003")
            assert result is None

    def test_status_202_triggers_flaresolverr(self):
        """IMDb returns 202 (AWS WAF challenge) — must fall back to FlareSolverr."""
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.return_value = MagicMock(status_code=202, text="<!DOCTYPE html><html>...")
            fs_resp = MagicMock()
            fs_resp.text = _make_jsonld_html("American Dad!")
            fs_resp.status_code = 200
            mock_fs.return_value = fs_resp

            result = get_localized_title(state, "tt0397306")
            assert result == "American Dad"
            mock_fs.assert_called_once()

    def test_waf_challenge_html_triggers_flaresolverr(self):
        """Status 200 but HTML contains AWS WAF challenge markers."""
        state = _mock_shared_state()
        waf_html = '<!DOCTYPE html><html><head><title></title><script>window.awsWafCookieDomainList = [];</script></head></html>'
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.return_value = MagicMock(status_code=200, text=waf_html)
            fs_resp = MagicMock()
            fs_resp.text = _make_jsonld_html("The Matrix")
            fs_resp.status_code = 200
            mock_fs.return_value = fs_resp

            result = get_localized_title(state, "tt0133093")
            assert result == "The Matrix"
            mock_fs.assert_called_once()

    def test_status_202_and_flaresolverr_fails_returns_none(self):
        """Both direct request (202) and FlareSolverr fail → None."""
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.return_value = MagicMock(status_code=202, text="")
            mock_fs.side_effect = RuntimeError("FlareSolverr down")

            result = get_localized_title(state, "tt0000004")
            assert result is None
            mock_fs.assert_called_once()

    def test_flaresolverr_is_asked_to_wait_for_the_waf_challenge(self):
        """The regression: FlareSolverr returns the challenge page unless it waits.

        Without ``wait`` it evaluates the page as soon as ``load`` fires and
        hands back the WAF interstitial, which has no title. The wait is what
        lets the challenge JavaScript set its cookie and reload.
        """
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.return_value = MagicMock(status_code=202, text="")
            # What FlareSolverr returns once the wait has elapsed.
            mock_fs.return_value = MagicMock(
                status_code=200, text=_make_jsonld_html("American Dad!"))

            result = get_localized_title(state, "tt0397306")

            assert result == "American Dad"
            assert mock_fs.call_args.kwargs.get("wait") == IMDB_WAF_SETTLE_SECONDS

    def test_wait_is_long_enough_for_the_challenge_to_clear(self):
        """Measured against imdb.com: 8 s returns the real page, 0 s the interstitial."""
        assert IMDB_WAF_SETTLE_SECONDS >= 8

    def test_challenge_from_flaresolverr_is_reported_as_such(self):
        """A challenge that survives the wait must not read as "no title".

        FlareSolverr answers 200 for the interstitial, so without an explicit
        check the log only says the title could not be found.
        """
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs, \
             patch("kuasarr.providers.imdb_metadata.info") as mock_info:
            mock_get.return_value = MagicMock(status_code=202, text="")
            mock_fs.return_value = MagicMock(
                status_code=200, text=_make_waf_challenge_html())

            assert get_localized_title(state, "tt0397306") is None

            messages = " ".join(str(c) for c in mock_info.call_args_list)
            assert "WAF challenge still present" in messages

    def test_waf_challenge_failure_expires_faster_than_a_plain_miss(self):
        """A WAF challenge lifts itself, so it must not be cached for the full hour.

        Otherwise one blocked lookup keeps returning None long after IMDb
        answers again - and no local change can fix what is cached.
        """
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.return_value = MagicMock(status_code=202, text="")
            mock_fs.return_value = MagicMock(
                status_code=200, text=_make_waf_challenge_html())

            assert get_localized_title(state, "tt0397306") is None

            entry = state.get_recently_searched(state, "recents_imdb_titles", 0)["tt0397306_de"]
            assert entry["title"] is None
            assert entry["retry_after"] < 60 * 60

    def test_plain_miss_still_uses_the_full_hour(self):
        """A genuine "IMDb has no such title" keeps the historic retry window."""
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, text=_make_empty_html())

            assert get_localized_title(state, "tt0000099") is None

            entry = state.get_recently_searched(state, "recents_imdb_titles", 0)["tt0000099_de"]
            assert entry["retry_after"] == 60 * 60

    def test_blocked_lookup_expires_faster_than_a_plain_miss(self):
        """The regression: 202 must not be cached as a missing title.

        The instance logged::

            IMDb request blocked for tt1844624 (status 202), retrying via FlareSolverr
            FlareSolverr fallback for IMDb tt1844624 failed: ...

        and then kept returning the cached miss for the full hour, so the retry
        never ran again. A refusal is recognised by its status code - the 202
        carries no WAF marker to inspect.
        """
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.return_value = MagicMock(status_code=202, text="")
            mock_fs.side_effect = RuntimeError("FlareSolverr down")

            assert get_localized_title(state, "tt1844624") is None

            entry = state.get_recently_searched(state, "recents_imdb_titles", 0)["tt1844624_de"]
            assert entry["retry_after"] < 60 * 60

    def test_403_without_flaresolverr_also_expires_fast(self):
        """Same refusal, other status code - the rule must not be 202-specific."""
        state = _mock_shared_state()
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get, \
             patch("kuasarr.providers.imdb_metadata.flaresolverr_get") as mock_fs:
            mock_get.return_value = MagicMock(status_code=403, text="Forbidden")
            mock_fs.side_effect = RuntimeError("FlareSolverr down")

            assert get_localized_title(state, "tt1844624") is None

            entry = state.get_recently_searched(state, "recents_imdb_titles", 0)["tt1844624_de"]
            assert entry["retry_after"] < 60 * 60

    def test_legacy_cache_entry_without_retry_after_still_respects_the_hour(self):
        """Entries written by an older version have no retry_after and must not expire early."""
        cached = {"tt0397306_de": {"title": None, "timestamp": datetime.now()}}
        state = _mock_shared_state(cache=cached)
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, text=_make_empty_html())

            # Just-written legacy entry: still inside the hour, so no HTTP call.
            assert get_localized_title(state, "tt0397306") is None
            mock_get.assert_not_called()

    def test_expired_legacy_entry_is_retried(self):
        """Once the hour has passed a legacy entry is retried like any other."""
        cached = {"tt0397306_de": {
            "title": None, "timestamp": datetime.now() - timedelta(hours=2)}}
        state = _mock_shared_state(cache=cached)
        with patch("kuasarr.providers.imdb_metadata.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, text=_make_jsonld_html("American Dad!"))

            assert get_localized_title(state, "tt0397306") == "American Dad"
            mock_get.assert_called_once()


# ---------------------------------------------------------------------------
# _is_waf_challenge
# ---------------------------------------------------------------------------

class TestIsWafChallenge:

    def test_detects_the_interstitial(self):
        assert _is_waf_challenge(MagicMock(text=_make_waf_challenge_html())) is True

    def test_real_page_is_not_a_challenge(self):
        assert _is_waf_challenge(MagicMock(text=_make_jsonld_html("American Dad"))) is False

    def test_served_page_with_the_waf_marker_is_not_a_challenge(self):
        """The regression: a served page carries the marker too.

        Checking the marker alone reported a successfully fetched page as
        blocked - which logged "IMDb is not reachable right now" right next to a
        title that had just been parsed, and cached the hit for 5 minutes
        instead of 24 hours.
        """
        html = _make_served_page_html("American Dad")
        assert "awsWafCookieDomainList" in html  # the premise has to hold
        assert _is_waf_challenge(MagicMock(text=html)) is False

    def test_none_is_not_a_challenge(self):
        assert _is_waf_challenge(None) is False

    def test_empty_body_is_not_a_challenge(self):
        """An empty body is a different failure and keeps the full retry window."""
        assert _is_waf_challenge(MagicMock(text="")) is False

    def test_unreadable_response_does_not_raise(self):
        """A response object without .text must not break the check."""
        assert _is_waf_challenge(object()) is False


# ---------------------------------------------------------------------------
# get_clean_title
# ---------------------------------------------------------------------------

class TestGetCleanTitle:

    def test_basic_title(self):
        assert get_clean_title("The.Matrix.1999") == "The+Matrix"

    def test_with_german_tag(self):
        assert get_clean_title("Inception.German.DL.1080p") == "Inception"

    def test_with_quality_tag(self):
        assert get_clean_title("Movie.720p.BluRay") == "Movie"

    def test_with_season_tag(self):
        assert get_clean_title("Show.S02.Complete") == "Show"

    def test_preserves_simple_title(self):
        assert get_clean_title("SimpleTitle") == "SimpleTitle"

    def test_with_year(self):
        result = get_clean_title("The.Matrix.1999.1080p")
        assert "Matrix" in result

    def test_returns_original_on_failure(self):
        # Input that doesn't match the regex pattern at all
        title = "SomethingThatDoesNotMatch"
        result = get_clean_title(title)
        assert result == title
